# MySQL 自然语言问答系统（NL2SQL）完整方案

> 目标：基于 MySQL 数据库，让用户用自然语言查询业务数据，系统自动生成 SQL 执行并返回自然语言结果 + 图表。
> 场景：企业内部 BI 分析，表以单表/多表 join 为主。
>
> ✅ 当前已实现「最小可运行 demo」：见本目录 README.md 与 app/ 代码。方案后续增强项见各章「未实现/待加」标注。

---

## 一、总体架构

```
用户问题
  ↓
① 意图识别 / 多轮改写（补全指代："那上个月呢" → "华东区上个月销售额"）
  ↓
② Schema 检索（向量库：表名 + 字段注释 + 示例问题 → 选出相关表）
  ↓
③ Prompt 组装（问题 + 相关表 DDL + 术语词典 + few-shot 示例 + 指标口径）
  ↓
④ SQL 生成（强约束：只读 SELECT）
  ↓
⑤ 安全校验（sqlglot AST：非 SELECT 拒绝 + 危险函数拦截）
  ↓
⑥ MySQL 执行（只读账号 + MAX_EXECUTION_TIME + 强制 LIMIT）
  ↓
  ├─ 报错 → 错误信息回喂模型重写 SQL（重试 2~3 次）
  └─ 成功 → 结果交给模型组织自然语言回答 + 图表建议
  ↓
⑦ 反馈闭环（成功/失败 case 沉淀进向量库，持续提升）
```

---

## 二、技术选型

| 模块 | 选型 | 理由 |
|------|------|------|
| 语言/框架 | **Python 3.11 + FastAPI** | NL2SQL 生态成熟，异步好写，起一个 REST 服务 |
| NL2SQL 引擎 | **自研 pipeline**（不用 Vanna 全家桶，方便控制） | 灵活、可调试、沉淀问对归自己 |
| LLM 接入 | **统一 API 层**，可切换 DeepSeek / Qwen-Max / GPT / 本地 Qwen | 数据不出内网则用本地 Qwen 开源版 |
| Schema 检索 | **向量库**（Chroma 本地 或 Milvus/阿里云向量库） | 表数 < 100 用 Chroma 足够，简单零运维 |
| Embedding | bge-m3 或 text-embedding-v3 | 中文效果好 |
| SQL 安全校验 | **sqlglot**（MySQL 方言） | 官方库，AST 解析稳定 |
| 前端 | 简单 Web UI（可选，先 CLI/API 验证） | 一期可不做 UI |

---

## 三、项目目录结构

```
db_query/
├── app/
│   ├── main.py               # FastAPI 入口
│   ├── config.py             # 配置（DB、LLM、向量库）
│   ├── api/
│   │   ├── query.py          # POST /api/query 主接口
│   │   └── train.py          # POST /api/train 反馈训练
│   ├── core/
│   │   ├── orchestrator.py   # 主流程编排（第①~⑦步）
│   │   ├── dialogue.py       # 多轮改写（第①步）
│   │   ├── schema_link.py    # Schema 检索（第②步）
│   │   ├── prompt_builder.py # Prompt 组装（第③步）
│   │   ├── sql_gen.py        # SQL 生成（第④步）
│   │   ├── sql_validator.py  # sqlglot 安全校验（第⑤步）
│   │   ├── executor.py       # MySQL 执行（第⑥步）
│   │   ├── self_correct.py   # 报错重写循环（第⑥步）
│   │   └── answer_parser.py  # 结果转自然语言（第⑦步）
│   ├── knowledge/
│   │   ├── vector_store.py   # 向量库封装
│   │   └── glossary.py       # 术语词典 / 指标口径
│   └── prompts/              # 各种 prompt 模板（独立文件，好调）
│       ├── schema_link.py
│       ├── sql_gen.py
│       ├── self_correct.py
│       └── answer.py
├── schema_build/
│   ├── extract_meta.py       # 从 information_schema 抽取元数据
│   ├── build_glossary.py     # 生成表描述 / 术语词典
│   └── seed_vector.py        # 初始化向量库
├── scripts/
│   └── init_db.sql           # 只读账号创建脚本
├── tests/                    # 测试
├── requirements.txt
└── README.md
```

---

## 四、核心模块设计

### 1. 元数据抽取（schema_build/extract_meta.py）
从 MySQL `information_schema` 抽取，为每张表生成结构化描述：

```sql
-- 表及注释
SELECT table_name, table_comment
FROM information_schema.tables WHERE table_schema = '你的库名';

-- 字段及注释
SELECT table_name, column_name, column_type, column_comment,
       (SELECT 1 FROM information_schema.key_column_usage
        WHERE table_schema=t.table_schema AND table_name=t.table_name
        AND column_name=t.column_name AND constraint_name='PRIMARY') AS is_pk
FROM information_schema.columns t WHERE table_schema='你的库名';
```

生成三份资产，全部存入向量库：
- **表级描述**：`表名 | 表注释 | 字段清单 | 常见查询场景的自然语言描述`
- **字段级**：`字段名 | 注释 | 所属表`（可单独索引便于术语匹配）
- **示例问对**：`问题 → SQL`，人工维护，是效果提升的核心燃料

### 2. Schema 检索（schema_link.py）
用户问题 embedding 后，在向量库检索 top-K（如 5 张）最相关表，连同表 DDL 一起入 prompt。若表很多，先按字段命中 + 表描述相似度双重过滤。

### 3. Prompt 组装（prompt_builder.py）
关键：**宁可 prompt 长，不给模型猜的机会**。模板包含：
1. 系统角色说明 + 硬约束（只写 SELECT、只读、必须带 WHERE 防止全表扫描提示）
2. 术语词典：`业务黑话 → 字段/口径` 映射
3. 指标口径：`活跃用户 = created_at 当天 + status=1 且 30 天内登录`
4. 相关表 DDL（含注释）
5. 2~3 条同类 few-shot 示例（问题→SQL）
6. 当前问题

### 4. SQL 安全校验（sql_validator.py）
用 sqlglot 对生成 SQL 做 AST 校验：
- 仅允许顶层 `SELECT`（`SHOW`/`DESC`/`UPDATE`/`DELETE`/`DROP`/`INSERT`/`SET` 全部拒绝）
- 禁止子查询中的写操作、`INTO OUTFILE`、`LOAD_FILE`、存储过程调用
- 无 `LIMIT` 时强制追加 `LIMIT 1000`
- 白名单表名校验（只能查已授权的表）

### 5. 执行与自纠错（executor.py + self_correct.py）
- 连接 MySQL **只读账号**（仅 `SELECT` 权限，见 init_db.sql）
- 加 `SET SESSION MAX_EXECUTION_TIME=10000` 或 SQL hint `/*+ MAX_EXECUTION_TIME(10000) */`
- 报错（语法错、列名错）→ 把错误信息 + 原 SQL 回喂模型重写，最多 3 次
- 执行结果 > 阈值行数做截断，避免刷屏

### 6. 结果组织（answer_parser.py）
- 把查询结果（DataFrame）交给模型，让其输出：**自然语言结论 + 关键数字**，并建议图表类型（bar/line/pie）
- 若结果为空，模型判断是"真没数据"还是"问题表述歧义"，给出澄清建议

### 7. 反馈闭环（api/train.py）
- 每次查询保存：问题 / 生成的 SQL / 是否成功 / 用户是否纠正
- 人工修正后的「问题→SQL」对，写回向量库作 few-shot（这就是 Vanna 式"训练"，越用越准）
- 失败 case 汇总表，定期人工标注补进术语词典

---

## 五、安全与权限（init_db.sql）

```sql
-- 创建只读账号，只给需要查的库授权
CREATE USER 'nl2sql_read'@'%' IDENTIFIED BY '强密码';
GRANT SELECT ON `your_db`.* TO 'nl2sql_read'@'%';
-- 不给 UPDATE/DELETE/INSERT/DROP，不给 FILE 权限
```

多层防线：数据库只读账号（第一层）+ sqlglot AST 白名单（第二层）+ 强制 LIMIT/超时（第三层）+ 全链路审计日志（第四层）。

---

## 六、准确率预期（务实）

| 场景 | 准确率 |
|------|--------|
| 单表 / 双表 join + 中文注释齐全 | 85%+ |
| 复杂多表 join + 业务黑话多、未维护词典 | 60~70% |
| 上线后持续喂问对 1~3 个月 | 75% → 90%+ |

**提升准确率最有效的三件事（按优先级）**：
1. 把失败 case 人工修正后回喂（反馈闭环）
2. 维护术语词典 + 指标口径库
3. 复杂 join 固化为 MySQL 视图，让模型写简单 SQL

---

## 七、开发里程碑

| 阶段 | 内容 | 产出 |
|------|------|------|
| **M1** | 元数据抽取 + 向量库初始化 | 可检索的表描述 |
| **M2** | 最小链路：单表查询 → SQL → 执行 → 自然语言回答（无校验） | 跑通 80% 简单问题 |
| **M3** | sqlglot 安全校验 + 只读账号 + LIMIT/超时 | 可安全上线 |
| **M4** | Schema 检索 + 术语词典 + few-shot | 单表 85%+ |
| **M5** | 自纠错循环 + 反馈训练 API | 复杂 join 提升 |
| **M6** | 多轮对话改写 + Web UI | 完整产品 |

---

## 八、一期 MVP 建议

**先做 M1~M4**：单表 + 少量双表 join + 安全校验，跑通一个最小可用版本。不要一上来就追求全部功能。
MVP 验收标准：给定 20 个典型业务问题，单表查询正确率 ≥ 85%，且所有生成的 SQL 均为只读、无越权。
