# MySQL 自然语言查询 Demo（NL2SQL）

一个**最小可运行**的 demo：你输入自然语言，系统自动生成 SQL、安全校验、执行、返回自然语言回答。
直接连你自己的 MySQL，配置在 `.env` 里填一下就行。

## 一、快速开始

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 配置
```bash
cp .env.example .env
```
编辑 `.env`，填三处关键信息：
- **DB_HOST / DB_PORT / DB_USER / DB_PASSWORD / DB_NAME** —— 你的 MySQL 连接
- **LLM_API_KEY** —— DeepSeek 的 API Key（默认 deepseek-chat；要换模型改 `LLM_BASE_URL` 和 `LLM_MODEL`）
- （可选）`DB_TABLES=orders,customers` —— 只让模型用这几张表

### 3. 运行
```bash
python -m app.cli
```
启动后直接输入问题，例如：
- 北京的用户有谁？
- 每种商品的销量（按数量求和）是多少？
- 上月总销售额是多少？
- 哪个城市的用户最多？

输入 `exit` 退出。

### 4. （可选）作为 HTTP API 服务供智能体调用
把问答能力包成 REST 接口，任何智能体都能通过 HTTP 调用：
```bash
python -m uvicorn app_server:app --host 0.0.0.0 --port 8000
```
- `GET /health` —— 健康检查
- `POST /query` —— 传入 `{"question": "你的问题"}`，返回结构化 JSON（sql / columns / rows / answer / used_tables）
- 鉴权：在 `.env` 配置 `API_KEY`，调用时带请求头 `X-API-Key: <值>`；留空则不开鉴权

---

## 二、没有 MySQL？先造个示例库试

1. 在 MySQL 里执行 `scripts/sample_db.sql`（会建库 `nl2sql_demo` 并造数）
2. `.env` 里 `DB_NAME=nl2sql_demo`
3. 运行 `python -m app.cli`

---

## 三、⚠️ 安全注意事项（务必看）

本 demo 是**最小实现**，请务必按下面做，不要直接拿生产库的高权限账号跑：

1. **建只读账号**（强烈建议，第一道防线）：
   ```sql
   CREATE USER 'nl2sql_read'@'%' IDENTIFIED BY '强密码';
   GRANT SELECT ON `你的库`.* TO 'nl2sql_read'@'%';
   ```
   `.env` 里用这个只读账号。

2. **代码内二次校验**（第二道防线）：`app/sql_validator.py` 用 sqlglot 解析 AST，
   只放行 `SELECT`、拦截写操作、强制加 `LIMIT`。已内置，无需额外操作。

3. 生产环境还应加：审计日志、结果脱敏、超时兜底。

---

## 四、项目结构

```
app/
  config.py          # 配置加载（读 .env）
  llm.py             # LLM 封装（OpenAI 兼容，可换模型）
  schema.py          # 从 information_schema 抽取表结构
  sql_validator.py   # SQL 安全校验（sqlglot AST）
  executor.py        # 执行 SQL（带超时）
  orchestrator.py    # 主流程编排（生成->校验->执行->纠错->回答）
  cli.py             # 命令行入口
scripts/sample_db.sql  # 示例数据库脚本
.env.example           # 配置模板
```

---

## 五、后续增强（当前 demo 未含，按需加）

- **Schema 检索/向量库**：表很多时，用向量库只检索相关表，而不是全部塞进 prompt
- **术语词典/指标口径**：业务黑话映射到字段，效果提升最明显
- **多轮对话**：改写补全指代（"那上个月呢"）
- **Web UI**：FastAPI + 简单前端
- **反馈闭环**：失败 case 回喂 few-shot

有需要我继续帮你加。
