"""멀티 프로바이더 AI 클라이언트.

datapipeline/ai/multi_provider_client.py에서 복제.
config 의존을 제거하고 환경변수를 직접 참조한다.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from openai import OpenAI

from ..config import OPENAI_API_KEY, PERPLEXITY_API_KEY, ANTHROPIC_API_KEY

LOGGER = logging.getLogger(__name__)


class MultiProviderClient:
    """OpenAI, Perplexity, Anthropic을 통합 관리하는 AI 클라이언트."""

    def __init__(
        self,
        openai_key: str = "",
        perplexity_key: str = "",
        anthropic_key: str = "",
    ) -> None:
        openai_key = openai_key or OPENAI_API_KEY
        perplexity_key = perplexity_key or PERPLEXITY_API_KEY
        anthropic_key = anthropic_key or ANTHROPIC_API_KEY

        self.providers: dict[str, Any] = {}

        # OpenAI
        if openai_key:
            self.providers["openai"] = OpenAI(api_key=openai_key)
            LOGGER.info("OpenAI provider initialized")

        # Perplexity (OpenAI 호환 API)
        if perplexity_key:
            self.providers["perplexity"] = OpenAI(
                api_key=perplexity_key,
                base_url="https://api.perplexity.ai",
            )
            LOGGER.info("Perplexity provider initialized")

        # Anthropic (선택적)
        if anthropic_key:
            try:
                from anthropic import Anthropic
                self._anthropic_client = Anthropic(api_key=anthropic_key)
                self.providers["anthropic"] = self._anthropic_client
                LOGGER.info("Anthropic provider initialized")
            except ImportError:
                LOGGER.warning("anthropic 패키지 미설치 - pip install anthropic")

    def chat_completion(
        self,
        provider: str,
        model: str,
        messages: list[dict[str, str]],
        thinking: bool = False,
        thinking_effort: str = "medium",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """프로바이더별 chat completion 호출."""
        if provider not in self.providers:
            raise ValueError(
                f"프로바이더 '{provider}'가 초기화되지 않았습니다. "
                f"사용 가능: {list(self.providers.keys())}"
            )

        started = time.perf_counter()
        LOGGER.info(
            "[%s] start model=%s messages=%d thinking=%s",
            provider.upper(), model, len(messages), thinking,
        )

        try:
            if provider == "anthropic":
                result = self._call_anthropic(model, messages, temperature, max_tokens)
            else:
                result = self._call_openai_compatible(
                    provider, model, messages, thinking, thinking_effort,
                    temperature, max_tokens, response_format, **kwargs,
                )
        except Exception as exc:
            elapsed = time.perf_counter() - started
            LOGGER.error(
                "[%s] error model=%s elapsed=%.2fs: %s",
                provider.upper(), model, elapsed, exc,
            )
            raise

        elapsed = time.perf_counter() - started
        LOGGER.info("[%s] done model=%s elapsed=%.2fs", provider.upper(), model, elapsed)
        return result

    def _call_openai_compatible(
        self, provider: str, model: str, messages: list[dict], thinking: bool,
        thinking_effort: str, temperature: float, max_tokens: int,
        response_format: Optional[dict], **kwargs: Any,
    ) -> dict[str, Any]:
        """OpenAI 호환 API 호출 (OpenAI, Perplexity)."""
        client = self.providers[provider]

        is_gpt5 = provider == "openai" and "gpt-5" in model

        call_kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
        }

        if is_gpt5:
            call_kwargs["max_completion_tokens"] = max_tokens
        else:
            call_kwargs["max_tokens"] = max_tokens
            call_kwargs["temperature"] = temperature

        if thinking and is_gpt5:
            call_kwargs["reasoning_effort"] = thinking_effort

        if response_format:
            call_kwargs["response_format"] = response_format

        call_kwargs.update(kwargs)

        response = client.chat.completions.create(**call_kwargs)

        return {
            "choices": [
                {
                    "message": {
                        "content": response.choices[0].message.content,
                        "role": response.choices[0].message.role,
                    }
                }
            ],
            "model": response.model,
            "usage": {
                "prompt_tokens": getattr(response.usage, 'prompt_tokens', 0),
                "completion_tokens": getattr(response.usage, 'completion_tokens', 0),
            },
        }

    def _call_anthropic(
        self, model: str, messages: list[dict], temperature: float, max_tokens: int,
    ) -> dict[str, Any]:
        """Anthropic Claude API 호출."""
        client = self._anthropic_client

        system_msg = ""
        user_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_msg += msg["content"] + "\n"
            else:
                user_messages.append(msg)

        if not user_messages:
            user_messages = [{"role": "user", "content": "위 지시사항을 수행해주세요."}]

        call_kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": user_messages,
        }
        if system_msg.strip():
            call_kwargs["system"] = system_msg.strip()

        response = client.messages.create(**call_kwargs)

        content = ""
        for block in response.content:
            if hasattr(block, "text"):
                content += block.text

        return {
            "choices": [
                {
                    "message": {
                        "content": content,
                        "role": "assistant",
                    }
                }
            ],
            "model": response.model,
            "usage": {
                "prompt_tokens": getattr(response.usage, 'input_tokens', 0),
                "completion_tokens": getattr(response.usage, 'output_tokens', 0),
            },
        }


# 싱글톤 인스턴스
_client: Optional[MultiProviderClient] = None


def get_multi_provider_client() -> MultiProviderClient:
    """멀티 프로바이더 클라이언트 싱글톤 반환."""
    global _client
    if _client is None:
        _client = MultiProviderClient()
    return _client
