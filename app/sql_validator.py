"""SQL 安全校验：用 sqlglot 解析 AST，只允许只读 SELECT，并强制 LIMIT。
这是防止模型生成危险 SQL 的第二道防线（第一道是只读数据库账号）。"""
import sqlglot
from sqlglot import exp

# 明确禁止出现在 SQL 中的关键字/操作（写操作、文件读取等）
_FORBIDDEN = {
    "INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE", "ALTER", "CREATE",
    "GRANT", "REVOKE", "RENAME", "SET", "CALL", "LOCK", "UNLOCK",
}
# 危险函数/关键字（子串匹配，防绕过）
_FORBIDDEN_FRAGMENTS = [
    "INTO OUTFILE", "INTO DUMPFILE", "LOAD_FILE", "SLEEP(", "BENCHMARK(",
    "information_schema.processlist", "--", "/*",
]


class SQLValidationError(Exception):
    """SQL 校验不通过。"""


def validate_sql(sql: str, allowed_tables: set[str], result_limit: int) -> str:
    """校验并规整 SQL，返回可执行的 SQL。

    - 拒绝非 SELECT 语句
    - 拒绝危险操作
    - 表名必须在白名单内
    - 无 LIMIT 时追加 LIMIT {result_limit}

    校验失败抛 SQLValidationError。
    """
    sql = sql.strip().rstrip(";").strip()

    # 1. 危险片段
    upper = sql.upper()
    for frag in _FORBIDDEN_FRAGMENTS:
        if frag in upper:
            raise SQLValidationError(f"SQL 包含危险片段: {frag!r}")

    # 2. AST 解析
    try:
        parsed = sqlglot.parse_one(sql, read="mysql")
    except Exception as e:  # 解析失败视为不安全
        raise SQLValidationError(f"SQL 解析失败: {e}") from e

    # 3. 必须是 SELECT
    if not isinstance(parsed, exp.Select):
        raise SQLValidationError(f"只允许 SELECT 查询，实际是: {type(parsed).__name__}")

    # 4. 检查是否包含写操作子查询
    if parsed.find(exp.Insert) or parsed.find(exp.Update) or parsed.find(exp.Delete):
        raise SQLValidationError("SQL 中包含写操作子查询")

    # 5. 表名白名单（含子查询里的表）
    referenced = set()
    for table in parsed.find_all(exp.Table):
        referenced.add(table.name)
    unknown = referenced - allowed_tables
    if unknown:
        raise SQLValidationError(f"引用了未授权的表: {sorted(unknown)}")

    # 6. 无 LIMIT 时追加（避免全表拉取）
    if not parsed.args.get("limit"):
        sql = sql.rstrip()
        sql += f"\nLIMIT {result_limit}"

    return sql
