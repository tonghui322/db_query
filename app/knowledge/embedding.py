"""Embedding 客户端：调用 OpenAI 兼容的 embedding 接口（默认千问 DashScope）。

与 llm.py 同理，用 requests 而非 openai SDK，规避 Windows 中文编码问题。
千问 text-embedding-v3 通过 DashScope 的 OpenAI 兼容模式调用。
"""
import requests

from ..config import Config


class Embedding:
    def __init__(self, cfg: Config):
        self.base_url = cfg.embed_base_url.rstrip("/")
        self.api_key = cfg.embed_api_key
        self.model = cfg.embed_model
        self.timeout = 30

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """批量把文本转成向量，返回 list of vector。"""
        url = f"{self.base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {"model": self.model, "input": texts}
        resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
        if resp.status_code != 200:
            raise RuntimeError(
                f"Embedding 请求失败 (HTTP {resp.status_code}): {resp.text[:300]}"
            )
        data = resp.json()
        # 返回顺序与 input 一致
        ordered = sorted(data["data"], key=lambda x: x["index"])
        return [d["embedding"] for d in ordered]
