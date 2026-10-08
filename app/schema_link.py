"""Schema 检索：用户问题 -> 相关表 top-K。

双过滤策略：
1. 语义检索：问题向量与表描述向量算余弦相似度，取 top-K。
2. 关键词命中：问题里的词若出现在表名/字段名，直接强制召回（防语义漏表）。
最终结果去重合并，语义为主、关键词为辅。
"""
import re
from typing import Optional

from .config import Config
from .knowledge.embedding import Embedding
from .knowledge.vector_store import VectorStore


class SchemaLinker:
    def __init__(self, cfg: Config, store: VectorStore, embed: Embedding):
        self.cfg = cfg
        self.store = store
        self.embed = embed
        # 建一个「小写词 -> 表名」倒排索引，用于关键词命中
        self._kw_index: dict[str, set[str]] = {}

    def _build_kw_index(self, table_names: list[str]):
        self._kw_index = {}
        for t in table_names:
            for w in set(re.split(r"[_\s]+", t.lower())):
                if w:
                    self._kw_index.setdefault(w, set()).add(t)

    def retrieve(self, question: str, top_k: Optional[int] = None) -> list[tuple[str, float]]:
        """返回 [(表名, 分数)]，语义相关表在前。"""
        top_k = top_k or self.cfg.schema_top_k
        if self.store.size == 0:
            return []

        q_vec = self.embed.embed_texts([question])[0]
        semantic = dict(self.store.search(q_vec, top_k * 2))  # 多取一点做合并

        # 关键词命中：问题里出现的英文词片段
        for tok in re.findall(r"[A-Za-z_]{2,}", question):
            base = tok.lower()
            # 逐段拆词命中
            for piece in base.split("_"):
                if piece in self._kw_index:
                    for t in self._kw_index[piece]:
                        semantic.setdefault(t, 0.0)

        ranked = sorted(semantic.items(), key=lambda kv: kv[1], reverse=True)
        return ranked[:top_k]

    def load_index(self, table_names: list[str]):
        """建关键词倒排索引（在向量加载后调用一次）。"""
        self._build_kw_index(table_names)
