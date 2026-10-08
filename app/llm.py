"""LLM 客户端：直接调用 OpenAI 兼容接口（DeepSeek/GPT/Ollama 均适用）。

用 requests 而非 openai SDK，是为了规避 openai 底层 httpx 在 Windows 上
对含中文 header/body 强制 ascii 编码导致 UnicodeEncodeError 的兼容问题。
requests 的 json= 参数天然用 UTF-8 编码，无此问题。
"""
import re
import requests


# 匹配孤立代理项（U+D800-DFFF）。这类字符无法编码为合法 UTF-8，
# 一旦进入 JSON 序列化，DeepSeek 等服务端会报 "lone leading surrogate"。
_SURROGATE_RE = re.compile(r"[\ud800-\udfff]")


def _clean_surrogates(text: str) -> str:
    """剔除字符串中的孤立代理项，返回安全的纯文本。"""
    return _SURROGATE_RE.sub("", text or "")


class LLM:
    """极简 LLM 封装，只负责发 prompt 拿文本。"""

    def __init__(self, base_url: str, api_key: str, model: str, temperature: float = 0.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.timeout = 60

    def _post(self, messages: list[dict], max_tokens: int) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        # 发送前净化每条消息内容，剔除孤立代理项，避免服务端 JSON 解析失败
        cleaned = [
            {**m, "content": _clean_surrogates(m.get("content", ""))}
            for m in messages
        ]
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": max_tokens,
            "messages": cleaned,
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
        if resp.status_code != 200:
            raise RuntimeError(
                f"LLM 请求失败 (HTTP {resp.status_code}): {resp.text[:300]}"
            )
        data = resp.json()
        return data["choices"][0]["message"]["content"] or ""

    def chat(self, system: str, user: str, max_tokens: int = 2048) -> str:
        """发一轮对话，返回 assistant 文本。"""
        return self._post(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens,
        )

    def chat_messages(self, messages: list[dict], max_tokens: int = 2048) -> str:
        """直接传 messages 列表（用于多轮/纠错场景）。"""
        return self._post(messages, max_tokens)
