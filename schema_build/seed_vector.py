"""初始化向量库：读取表结构 -> 生成表描述 -> embedding -> 落盘到 .npz。

运行：python -m schema_build.seed_vector
需在 .env 配置 EMBED_API_KEY（千问/DashScope），DB_NAME 指向目标库。
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import Config
from app import schema as schema_mod
from app.knowledge.embedding import Embedding
from app.knowledge.vector_store import VectorStore


def main():
    cfg = Config.from_env()
    if not cfg.embed_api_key:
        print("[错误] 未配置 EMBED_API_KEY，请先在 .env 填入千问/DashScope 的 API Key。")
        sys.exit(1)

    print(f"加载数据库 {cfg.db_name} 的表结构 ...")
    tables = schema_mod.load_schema(cfg)
    print(f"共 {len(tables)} 张表，正在生成表描述 ...")
    descriptions = schema_mod.build_table_descriptions(tables)

    embed = Embedding(cfg)
    names, vectors = [], []
    # 分批 embedding，避免一次请求过大（千问单次 batch 上限 10）
    items = list(descriptions.items())
    batch = 10
    for i in range(0, len(items), batch):
        chunk = items[i:i + batch]
        texts = [d for _, d in chunk]
        vecs = embed.embed_texts(texts)
        for (n, _), v in zip(chunk, vecs):
            names.append(n)
            vectors.append(v)
        print(f"  已处理 {len(names)}/{len(items)}")

    store = VectorStore()
    store.build(names, vectors)
    store.save(cfg.vector_store_path)
    print(f"完成！向量已保存到 {cfg.vector_store_path}，共 {store.size} 张表。")


if __name__ == "__main__":
    main()
