"""主流程编排：用户问题 -> SQL 生成 -> 安全校验 -> 执行 -> 纠错 -> 自然语言回答。"""
import json
import os
from datetime import date, datetime
from decimal import Decimal

from . import schema as schema_mod
from .config import Config
from .executor import execute_sql
from .knowledge.embedding import Embedding
from .knowledge.vector_store import VectorStore
from .llm import LLM
from .schema_link import SchemaLinker
from .sql_validator import SQLValidationError, validate_sql

# 生成 SQL 的系统提示词（中文、强调只读）
SQL_SYSTEM_PROMPT = """你是一个 MySQL 数据库查询专家。你的任务是理解用户的自然语言问题，并生成**唯一一条**可执行的 MySQL SELECT 语句。

严格要求：
1. 只输出 SQL，不要任何解释、前后缀、Markdown 代码块标记。
2. 只能 SELECT 查询，绝不能生成 INSERT/UPDATE/DELETE/DROP 等写操作。
3. 使用上面给出的表结构和字段，字段名必须精确匹配，不要臆造字段。
4. 涉及中文比较时，确保字符串正确（必要时使用 LIKE 或精确匹配）。
5. 尽量高效：能用单表就不 join，能聚合就聚合。
6. 日期处理使用 MySQL 的 DATE_FORMAT 等函数。
7. 如果问题无法用现有表回答，直接输出：NO_ANSWER

现在根据用户问题生成 SQL。"""


def _json_default(obj):
    """把 Decimal / 日期类型转成 JSON 可序列化的值（展示用）。"""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (datetime, date)):
        return str(obj)
    return str(obj)


def _extract_sql(text: str) -> str:
    """从模型输出中提取 SQL（去掉可能的 Markdown 包裹）。"""
    t = text.strip()
    if t.startswith("```"):
        # 去掉 ```sql ... ``` 包裹
        lines = t.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    return t


class NL2SQLQuery:
    """一次查询的完整状态，包含最终 SQL、结果与自然语言回答。"""

    def __init__(self):
        self.question = ""
        self.sql = ""
        self.attempts = 0
        self.exec_result = None
        self.error = None
        self.answer = ""
        self.used_tables = []


class Orchestrator:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        cfg.validate()
        self.llm = LLM(
            base_url=cfg.llm_base_url,
            api_key=cfg.llm_api_key,
            model=cfg.llm_model,
            temperature=cfg.llm_temperature,
        )
        self.tables = schema_mod.load_schema(cfg)
        self.allowed_tables = {t.name for t in self.tables}
        if not self.tables:
            raise RuntimeError("未从数据库中读取到任何表，请检查 DB_NAME 和 DB_TABLES 配置。")

        # ---- Schema 检索 ----
        self._by_name = {t.name: t for t in self.tables}
        self.store = VectorStore()
        if os.path.exists(cfg.vector_store_path):
            self.store.load(cfg.vector_store_path)
            self._linker = SchemaLinker(cfg, self.store, Embedding(cfg))
            self._linker.load_index(self.store.table_names)
            print(f"[Schema检索] 已加载向量库（{self.store.size} 张表）")
        else:
            # 向量库未初始化：降级为全量 schema（旧行为，功能不受阻）
            self._linker = None
            print(f"[警告] 未找到向量库 {cfg.vector_store_path}，降级为全量 Schema。"
                  f"请运行 python -m schema_build.seed_vector 初始化。")

    # ---------- Schema 检索（第②步） ----------
    def _retrieve_schema(self, question: str) -> str:
        """检索与问题最相关的表，渲染成 prompt 文本。
        有向量库则检索 top-K；否则全量。"""
        if getattr(self, "_linker", None) is not None:
            hits = self._linker.retrieve(question)
            tables = [self._by_name[name] for name, _ in hits if name in self._by_name]
            self._last_hit_tables = [t.name for t in tables]
            return schema_mod.schema_to_prompt(tables)
        self._last_hit_tables = list(self.allowed_tables)
        return schema_mod.schema_to_prompt(getattr(self, "tables", []))

    # ---------- 第①步：生成 SQL（带纠错重试） ----------
    def _generate_sql(self, question: str):
        """生成并校验 SQL。校验或执行失败会带错误信息重试。
        返回 (sql, result, messages)。"""
        schema_text = self._retrieve_schema(question)
        user_prompt = (
            f"### 数据库表结构（含中文注释）\n{schema_text}\n\n"
            f"### 用户问题\n{question}\n\n请生成 SQL。"
        )
        messages = [
            {"role": "system", "content": SQL_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        last_sql = ""
        for attempt in range(1, self.cfg.max_sql_retry + 1):
            raw = self.llm.chat_messages(messages)
            sql = _extract_sql(raw)

            if sql.strip().upper() == "NO_ANSWER":
                raise RuntimeError("模型判定：现有表结构无法回答该问题。")

            # 1. 安全校验
            try:
                sql = validate_sql(sql, self.allowed_tables, self.cfg.result_limit)
            except SQLValidationError as e:
                # 把校验错误喂回模型，让它修正
                messages.append({"role": "assistant", "content": raw})
                messages.append({
                    "role": "user",
                    "content": f"你生成的 SQL 校验不通过：{e}\n请重新生成。",
                })
                continue

            # 2. 执行
            try:
                result = execute_sql(self.cfg, sql)
                last_sql = sql
                return sql, result, messages
            except Exception as e:
                messages.append({"role": "assistant", "content": raw})
                messages.append({
                    "role": "user",
                    "content": f"SQL 执行失败：{e}\n请修正后重新生成。",
                })
                last_sql = sql

        # 重试次数用尽
        raise RuntimeError(f"多次尝试后仍失败。最后一次 SQL: {last_sql}")

    # ---------- 第②步：结果转自然语言 ----------
    def _answer(self, question: str, result: dict) -> str:
        cols = result["columns"]
        rows = result["rows"]
        # 把结果渲染成紧凑文本给 LLM
        sample = rows[:50]
        data_preview = json.dumps(
            [dict(zip(cols, r)) for r in sample],
            ensure_ascii=False,
            indent=0,
            default=_json_default,
        )
        if not rows:
            return "查询执行成功，但结果为空（可能确实没有符合条件的数据，或问题表述需要调整）。"

        system = (
            "你是一个数据分析助手。根据查询到的数据，用自然语言简洁回答用户的问题。"
            "要点：1) 直接给出结论和关键数字；2) 如需对比，清晰列出；3) 不要编造数据。"
            "如果数据适合可视化，最后加一行『图表建议: 柱状图/折线图/饼图 之一』，不适合则不加。"
        )
        user = (
            f"### 用户问题\n{question}\n\n"
            f"### 查询到的数据（共 {result['row_count']} 行，展示前 {len(sample)} 行）\n"
            f"{data_preview}\n\n请组织自然语言回答。"
        )
        return self.llm.chat(system, user, max_tokens=512)

    # ---------- 对外主入口 ----------
    def query(self, question: str) -> NL2SQLQuery:
        q = NL2SQLQuery()
        q.question = question
        sql, result, _ = self._generate_sql(question)
        q.sql = sql
        q.exec_result = result
        q.answer = self._answer(question, result)
        q.used_tables = getattr(self, "_last_hit_tables", [])
        return q
