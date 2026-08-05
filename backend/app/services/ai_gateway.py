from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _provider_config() -> dict[str, dict[str, str]]:
    return {
        "deepseek": {
            "base_url": settings.DEEPSEEK_BASE_URL,
            "api_key": settings.DEEPSEEK_API_KEY,
            "model": settings.DEEPSEEK_MODEL,
        },
        "qwen": {
            "base_url": settings.QWEN_BASE_URL,
            "api_key": settings.QWEN_API_KEY,
            "model": settings.QWEN_MODEL,
        },
        "glm": {
            "base_url": settings.GLM_BASE_URL,
            "api_key": settings.GLM_API_KEY,
            "model": settings.GLM_MODEL,
        },
    }


def extract_json(text: str) -> dict[str, Any] | list[Any] | None:
    cleaned = re.sub(r"^```(?:json)?\s*|```\s*$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}|\[.*\]", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None


class AIModelGateway:
    """统一模型网关：provider 注册、调用、JSON 解析与离线降级。"""

    def __init__(self, provider: str | None = None) -> None:
        self.provider = provider or settings.AI_PROVIDER
        self.providers = _provider_config()
        self.config = self.providers.get(self.provider, self.providers["deepseek"])

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        timeout: float = 60.0,
    ) -> str:
        if not self.config["api_key"]:
            return self._offline_reply(messages)

        url = f"{self.config['base_url'].rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.config['api_key']}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.config["model"],
            "messages": messages,
            "temperature": temperature,
        }
        try:
            response = httpx.post(url, headers=headers, json=payload, timeout=timeout)
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except Exception:
            logger.exception("AI provider %s request failed", self.provider)
            return self._offline_reply(messages)

    def generate_json(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.3,
    ) -> dict[str, Any] | list[Any]:
        text = self.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=temperature,
        )
        result = extract_json(text)
        return result if result is not None else {}

    @staticmethod
    def _offline_reply(messages: list[dict[str, str]]) -> str:
        last = messages[-1]["content"] if messages else ""
        return (
            "（离线降级响应）已收到请求：" + last[:120]
            + "。请在 .env 中配置模型 API Key 后获得完整能力。"
        )
