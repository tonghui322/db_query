"""端到端冒烟测试：验证 orchestrator 主流程逻辑正确。
用假 LLM + 假执行，不连真实数据库、不发真实请求。
运行: python tests/test_smoke.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.orchestrator import Orchestrator, SQL_SYSTEM_PROMPT
from app.sql_validator import validate_sql, SQLValidationError


class FakeLLM:
    """模拟 LLM：第一次返回 SQL，后续（纠错时）返回修正 SQL。"""

    def __init__(self, responses):
        self.responses = list(responses)  # 队列
        self.calls = []

    def chat(self, system, user, max_tokens=2048):
        return self.responses.pop(0)

    def chat_messages(self, messages):
        self.calls.append(messages)
        # 若队列还有就弹，否则返回固定值
        return self.responses.pop(0) if self.responses else "SELECT 1"


class FakeConfig:
    """模拟配置，绕过真实 DB/LLM。"""

    def __init__(self):
        self.max_sql_retry = 3
        self.result_limit = 1000
        self.sql_timeout_ms = 10000


class FakeResult(dict):
    """模拟 execute_sql 的返回 dict：{'columns','rows','row_count'}。"""

    def __init__(self):
        super().__init__(columns=["count(*)"], rows=[[3]], row_count=1)


def test_pipeline_generates_and_answers():
    orch = Orchestrator.__new__(Orchestrator)  # 跳过 __init__（不连DB）
    orch.cfg = FakeConfig()
    orch.allowed_tables = {"customers", "orders"}
    orch.schema_text = "表 orders: id, customer_id, order_date, total_amount"

    # 假 LLM：生成SQL -> 回答
    orch.llm = FakeLLM([
        "SELECT COUNT(*) FROM orders",   # SQL 生成
        "共有 3 笔订单。",               # 回答
    ])

    # 打桩执行：返回假结果（必须打到 orchestrator 模块里引用的同名函数）
    import app.orchestrator as orch_mod
    orch_mod.execute_sql = lambda cfg, sql: FakeResult()

    q = orch.query("一共有多少订单？")
    assert q.sql.strip().startswith("SELECT"), f"SQL错误: {q.sql}"
    assert "LIMIT" in q.sql, "应追加 LIMIT"
    assert q.answer == "共有 3 笔订单。", f"回答错误: {q.answer}"
    print(f"  PASS  全链路: SQL=[{q.sql}] 回答=[{q.answer}]")


def test_system_prompt_is_clear():
    assert "SELECT" in SQL_SYSTEM_PROMPT
    assert "UPDATE" in SQL_SYSTEM_PROMPT
    print("  PASS  system prompt 包含只读约束")


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for fn in fns:
        try:
            fn()
            passed += 1
        except Exception:
            failed += 1
            print(f"  FAIL  {fn.__name__}")
            traceback.print_exc()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
