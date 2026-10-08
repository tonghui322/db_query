
"""Schema 抽取：从 MySQL information_schema 拉取表结构、字段注释、外键关系。
生成的 Schema 描述会作为上下文喂给 LLM 生成 SQL。"""
from dataclasses import dataclass, field

import pymysql

from .config import Config


@dataclass
class Column:
    name: str
    type: str
    comment: str = ""
    is_pk: bool = False
    nullable: bool = True


@dataclass
class Table:
    name: str
    comment: str = ""
    columns: list[Column] = field(default_factory=list)


def _lower(row: dict) -> dict:
    """把 information_schema 返回的字典键统一转为小写（列名可能是大写的）。"""
    return {k.lower(): v for k, v in row.items()}


def _connect(cfg: Config) -> pymysql.connections.Connection:
    return pymysql.connect(
        host=cfg.db_host,
        port=cfg.db_port,
        user=cfg.db_user,
        password=cfg.db_password,
        database=cfg.db_name,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10,
    )


def load_schema(cfg: Config) -> list[Table]:
    """抽取目标库的表结构（含字段注释）。表列表在 cfg.db_tables 中指定，空则全部。"""
    conn = _connect(cfg)
    tables: list[Table] = []
    try:
        with conn.cursor() as cur:
            # 表清单（information_schema 列名是大写，用别名统一成小写）
            cur.execute(
                """
                SELECT table_name AS table_name, table_comment AS table_comment
                FROM information_schema.tables
                WHERE table_schema = %s AND table_type = 'BASE TABLE'
                ORDER BY table_name
                """,
                (cfg.db_name,),
            )
            rows = [_lower(r) for r in cur.fetchall()]
            table_names = [r["table_name"] for r in rows]
            if cfg.db_tables:
                # 只保留配置里指定的表（白名单）
                table_names = [t for t in table_names if t in cfg.db_tables]
            if cfg.db_table_blacklist:
                # 去掉前缀命中的表（黑名单，如框架表 qrtz_/sys_）
                table_names = [
                    t for t in table_names
                    if not any(t.startswith(p) for p in cfg.db_table_blacklist)
                ]

            # 主键集合
            cur.execute(
                """
                SELECT table_name, column_name
                FROM information_schema.key_column_usage
                WHERE table_schema = %s AND constraint_name = 'PRIMARY'
                """,
                (cfg.db_name,),
            )
            pks = {}
            for r in (_lower(x) for x in cur.fetchall()):
                pks.setdefault(r["table_name"], set()).add(r["column_name"])

            # 字段
            cur.execute(
                """
                SELECT table_name, column_name, column_type, column_comment, is_nullable
                FROM information_schema.columns
                WHERE table_schema = %s
                ORDER BY table_name, ordinal_position
                """,
                (cfg.db_name,),
            )
            cols_by_table = {}
            for r in (_lower(x) for x in cur.fetchall()):
                cols_by_table.setdefault(r["table_name"], []).append(
                    Column(
                        name=r["column_name"],
                        type=r["column_type"],
                        comment=r["column_comment"] or "",
                        is_pk=r["column_name"] in pks.get(r["table_name"], set()),
                        nullable=r["is_nullable"] == "YES",
                    )
                )

        for tn in table_names:
            comment = ""
            for r in rows:
                if r["table_name"] == tn:
                    comment = r["table_comment"] or ""
                    break
            tables.append(Table(name=tn, comment=comment, columns=cols_by_table.get(tn, [])))
    finally:
        conn.close()
    return tables


def schema_to_prompt(tables: list[Table]) -> str:
    """把表结构渲染成可读的 prompt 文本（含中文注释）。"""
    lines = []
    for t in tables:
        header = f"表 {t.name}" + (f" - {t.comment}" if t.comment else "")
        lines.append(f"## {header}")
        cols = []
        for c in t.columns:
            pk_mark = " [主键]" if c.is_pk else ""
            null_mark = "" if c.nullable else " [非空]"
            c_desc = f"`{c.name}` {c.type}{pk_mark}{null_mark}"
            if c.comment:
                c_desc += f" -- {c.comment}"
            cols.append(c_desc)
        lines.append("  字段: " + ", ".join(cols))
        lines.append("")
    return "\n".join(lines)


def build_table_descriptions(tables: list[Table]) -> dict[str, str]:
    """为每张表生成一段「业务描述」文本，用于向量检索时计算语义相似度。

    文本 = 表名拆词 + 表注释 + 各字段(名+注释)。表名/字段名按下划线拆词，
    这样「tunnel_workface」能被"隧道/掌子面"等中文语义命中。
    """
    descriptions: dict[str, str] = {}
    for t in tables:
        parts = [t.name]
        if t.comment:
            parts.append(t.comment)
        # 表名拆词（如 tunnel_workface -> tunnel workface）
        parts.extend(t.name.split("_"))
        for c in t.columns:
            parts.append(c.name)
            if c.comment:
                parts.append(c.comment)
        # 去重保序，拼成一句
        seen = set()
        desc = " ".join(p for p in parts if p and not (p in seen or seen.add(p)))
        descriptions[t.name] = desc
    return descriptions
