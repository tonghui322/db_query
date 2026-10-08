"""NL2SQL HTTP API 服务：把 Orchestrator 包成 REST 接口，供智能体调用。

启动：uvicorn app_server:app --host 0.0.0.0 --port 8000
鉴权：在 .env 配置 API_KEY（留空则不开鉴权）。
调用：
    POST /query
    Header:  X-API-Key: <API_KEY>   (若配置了 API_KEY)
    Body:    {"question": "每个标段的重大风险有多少"}
"""
import json
from contextlib import asynccontextmanager
from datetime import date, datetime
from decimal import Decimal

from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from app.config import Config
from app.orchestrator import Orchestrator


def _json_default(obj):
    """把 Decimal / 日期类型转成 JSON 可序列化的值（与 orchestrator 内一致）。"""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (datetime, date)):
        return str(obj)
    return str(obj)


# ---------- 启动时加载一次，常驻内存 ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.cfg = Config.from_env()
    app.state.orch = Orchestrator(app.state.cfg)
    print(f"[API] 就绪：数据库 {app.state.cfg.db_name}，"
          f"加载 {len(app.state.orch.tables)} 张表。")
    yield


app = FastAPI(title="NL2SQL API", version="1.0.0", lifespan=lifespan)


class QueryRequest(BaseModel):
    question: str


def _check_auth(x_api_key: Optional[str] = Header(default=None)):
    cfg = app.state.cfg
    if cfg.api_key and x_api_key != cfg.api_key:
        raise HTTPException(status_code=401, detail="无效的 API Key")
    return x_api_key


@app.get("/health")
def health():
    return {"status": "ok", "db": app.state.cfg.db_name}


@app.post("/query", dependencies=[Depends(_check_auth)])
def query(req: QueryRequest):
    question = (req.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question 不能为空")

    try:
        r = app.state.orch.query(question)
    except Exception as e:
        # 生成/执行失败（含模型判定 NO_ANSWER）统一返回 200 + error 字段，
        # 方便智能体把错误当普通结果处理。
        return {"ok": False, "error": str(e), "sql": "", "answer": "",
                "columns": [], "rows": [], "row_count": 0, "used_tables": []}

    result = r.exec_result or {}
    rows = result.get("rows") or []
    # 序列化行数据（Decimal/datetime -> JSON 安全值）
    cols = result.get("columns") or []
    rows_json = json.loads(
        json.dumps([dict(zip(cols, row)) for row in rows],
                   ensure_ascii=False, default=_json_default)
    )

    return {
        "ok": True,
        "sql": r.sql,
        "answer": r.answer,
        "columns": cols,
        "rows": rows_json,
        "row_count": result.get("row_count", len(rows)),
        "used_tables": r.used_tables,
    }
