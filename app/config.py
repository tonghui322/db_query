"""配置加载：从 .env 读取数据库与 LLM 配置。"""
import os
import sys
from dataclasses import dataclass, field
from dotenv import load_dotenv

# 强制 UTF-8，修复 Windows 下 HTTP 请求体含中文时报 'ascii' codec 的问题
if sys.platform == "win32":
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ.setdefault("PYTHONUTF8", "1")  # 让 openai/httpx 用 UTF-8 编码请求体
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 加载项目根目录下的 .env（若存在）
load_dotenv()


@dataclass
class Config:
    # MySQL
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = ""
    db_name: str = ""
    db_tables: list = field(default_factory=list)  # 空 = 全部表

    # LLM
    llm_base_url: str = "https://api.deepseek.com"
    llm_api_key: str = ""
    llm_model: str = "deepseek-chat"
    llm_temperature: float = 0.0

    # Embedding（Schema 检索用，默认千问 DashScope 兼容模式）
    embed_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    embed_api_key: str = ""
    embed_model: str = "text-embedding-v3"

    # Schema 检索
    db_table_blacklist: list = field(default_factory=list)  # 表名前缀黑名单，如 ["qrtz_", "sys_"]
    schema_top_k: int = 8          # 每次检索喂给模型的相关表数量
    vector_store_path: str = "schema_build/table_vectors.npz"  # 向量落盘路径

    # API 服务鉴权（留空 = 不开鉴权）
    api_key: str = ""

    # 运行参数
    max_sql_retry: int = 3
    sql_timeout_ms: int = 10000
    result_limit: int = 1000

    @classmethod
    def from_env(cls) -> "Config":
        cfg = cls(
            db_host=os.getenv("DB_HOST", "127.0.0.1"),
            db_port=int(os.getenv("DB_PORT", "3306")),
            db_user=os.getenv("DB_USER", "root"),
            db_password=os.getenv("DB_PASSWORD", ""),
            db_name=os.getenv("DB_NAME", ""),
            db_tables=[t.strip() for t in os.getenv("DB_TABLES", "").split(",") if t.strip()],
            llm_base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
            llm_api_key=os.getenv("LLM_API_KEY", ""),
            llm_model=os.getenv("LLM_MODEL", "deepseek-chat"),
            llm_temperature=float(os.getenv("LLM_TEMPERATURE", "0")),
            embed_base_url=os.getenv("EMBED_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
            embed_api_key=os.getenv("EMBED_API_KEY", ""),
            embed_model=os.getenv("EMBED_MODEL", "text-embedding-v3"),
            db_table_blacklist=[t.strip() for t in os.getenv("DB_TABLE_BLACKLIST", "").split(",") if t.strip()],
            schema_top_k=int(os.getenv("SCHEMA_TOP_K", "8")),
            vector_store_path=os.getenv("VECTOR_STORE_PATH", "schema_build/table_vectors.npz"),
            api_key=os.getenv("API_KEY", ""),
            max_sql_retry=int(os.getenv("MAX_SQL_RETRY", "3")),
            sql_timeout_ms=int(os.getenv("SQL_TIMEOUT_MS", "10000")),
            result_limit=int(os.getenv("RESULT_LIMIT", "1000")),
        )
        return cfg

    def validate(self):
        """启动前检查关键配置是否齐全。"""
        missing = []
        if not self.db_name:
            missing.append("DB_NAME")
        if not self.llm_api_key:
            missing.append("LLM_API_KEY")
        if missing:
            raise RuntimeError(
                f"配置缺失: {', '.join(missing)}。"
                "请先复制 .env.example 为 .env 并填写（数据库地址、LLM API Key）。"
            )
        # 检测未替换的占位符 Key（如"你的DeepSeekAPIKey"），给出清晰提示
        placeholder_hint = ("你的", "xxx", "sk-你的", "请输入")
        if any(p in self.llm_api_key for p in placeholder_hint):
            raise RuntimeError(
                "LLM_API_KEY 仍是占位符，请填入真实的 API Key"
                "（在 .env 中 LLM_API_KEY= 后填写，如 sk-xxxxxxxx）。"
            )
