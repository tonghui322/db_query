"""SQL 执行：连接只读账号执行校验后的 SQL，返回结果。"""
import pymysql

from .config import Config


def execute_sql(cfg: Config, sql: str) -> dict:
    """执行 SQL 并返回 {'columns': [...], 'rows': [[...]], 'row_count': n}。
    带执行超时保护。"""
    conn = pymysql.connect(
        host=cfg.db_host,
        port=cfg.db_port,
        user=cfg.db_user,
        password=cfg.db_password,
        database=cfg.db_name,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10,
        read_timeout=max(cfg.sql_timeout_ms // 1000, 5),
    )
    try:
        with conn.cursor() as cur:
            # MySQL 执行超时（秒）
            cur.execute("SET SESSION MAX_EXECUTION_TIME = %s", (cfg.sql_timeout_ms,))
            cur.execute(sql)
            if cur.description is None:
                return {"columns": [], "rows": [], "row_count": 0}
            columns = [d[0] for d in cur.description]
            rows = [list(r.values()) for r in cur.fetchall()]
            return {"columns": columns, "rows": rows, "row_count": len(rows)}
    finally:
        conn.close()
