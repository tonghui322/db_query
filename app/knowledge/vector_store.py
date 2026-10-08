"""向量存储：用 numpy 存表描述向量，余弦相似度检索。

276 张表规模很小，无需引入 Chroma/Milvus 等外部服务，纯 numpy 即可：
- 初始化：为每张表描述生成向量，落盘 .npz
- 检索：用户问题向量与所有表向量算余弦相似度，取 top-K
"""
import os

import numpy as np


class VectorStore:
    def __init__(self):
        self.table_names: list[str] = []
        self.matrix: np.ndarray = None  # shape (n, dim)
        self._norm: np.ndarray = None  # 预归一化

    @property
    def size(self) -> int:
        return len(self.table_names)

    def build(self, table_names: list[str], vectors: list[list[float]]):
        """用表名与对应向量构建索引。"""
        self.table_names = list(table_names)
        self.matrix = np.asarray(vectors, dtype=np.float32)
        self._norm = self.matrix / np.linalg.norm(self.matrix, axis=1, keepdims=True)

    def save(self, path: str):
        """落盘为 .npz。"""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        np.savez(path, names=np.array(self.table_names, dtype=object), matrix=self.matrix)

    def load(self, path: str):
        """从 .npz 加载。"""
        data = np.load(path, allow_pickle=True)
        self.build(list(data["names"]), data["matrix"].tolist())

    def search(self, query_vec: list[float], top_k: int) -> list[tuple[str, float]]:
        """按余弦相似度检索，返回 [(表名, 分数)] 降序。"""
        q = np.asarray(query_vec, dtype=np.float32)
        q = q / (np.linalg.norm(q) + 1e-9)
        scores = self._norm @ q
        order = np.argsort(scores)[::-1][:top_k]
        return [(self.table_names[i], float(scores[i])) for i in order]
