"""LLM 호출 헬퍼: prompt_loader 연동 + JSON 추출.

generate_interface2.py의 extract_json_object() 로직을 재활용한다.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from ..prompts.prompt_loader import load_prompt
from ..config import PROMPTS_DIR
from .multi_provider_client import get_multi_provider_client

LOGGER = logging.getLogger(__name__)


def extract_json_object(raw_text: str) -> dict[str, Any]:
    """응답에서 JSON 객체 추출 (코드블록 처리 포함)."""
    text = raw_text.strip()

    # 코드블록 제거
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    # 직접 파싱 시도
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
        raise ValueError("Model output JSON is not an object.")
    except json.JSONDecodeError:
        pass

    # { ... } 범위 추출
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"No JSON object found in model output. (length={len(raw_text)})")

    candidate = text[start: end + 1]
    parsed = json.loads(candidate)
    if not isinstance(parsed, dict):
        raise ValueError("Parsed JSON is not an object.")
    return parsed


def call_llm_with_prompt(
    prompt_name: str,
    variables: dict[str, Any],
    prompts_dir: str | Path | None = None,
    max_retries: int = 3,
) -> dict[str, Any]:
    """프롬프트 로드 -> LLM 호출 -> JSON 파싱 (재시도 기능 포함).

    Args:
        prompt_name: 프롬프트 템플릿 이름 (확장자 없이).
        variables: 템플릿에 치환할 변수 (dict/list는 자동 JSON 직렬화).
        prompts_dir: 프롬프트 디렉토리 오버라이드.
        max_retries: JSON 파싱 실패 시 재시도 횟수.

    Returns:
        파싱된 JSON 딕셔너리.
    """
    # 변수를 문자열로 변환 (dict/list -> JSON string)
    str_vars: dict[str, str] = {}
    for k, v in variables.items():
        if isinstance(v, (dict, list)):
            str_vars[k] = json.dumps(v, ensure_ascii=False, indent=2)
        else:
            str_vars[k] = str(v)

    spec = load_prompt(prompt_name, prompts_dir=prompts_dir or PROMPTS_DIR, **str_vars)
    client = get_multi_provider_client()

    messages: list[dict[str, str]] = []
    if spec.system_message:
        messages.append({"role": "system", "content": spec.system_message})
    messages.append({"role": "user", "content": spec.body})

    last_exception = None

    for attempt in range(max_retries):
        try:
            result = client.chat_completion(
                provider=spec.provider,
                model=spec.model,
                messages=messages,
                thinking=spec.thinking,
                thinking_effort=spec.thinking_effort,
                temperature=spec.temperature,
                max_tokens=spec.max_tokens,
                response_format=(
                    {"type": "json_object"}
                    if spec.response_format == "json_object"
                    else None
                ),
            )

            content = result["choices"][0]["message"]["content"]
            parsed = extract_json_object(content)

            LOGGER.info(
                "LLM call done: prompt=%s provider=%s model=%s tokens=%s (attempt %d/%d)",
                prompt_name, spec.provider, spec.model, result.get("usage"), attempt + 1, max_retries
            )
            return parsed

        except (ValueError, json.JSONDecodeError) as e:
            last_exception = e
            LOGGER.warning(
                "JSON parse failed for prompt %s (attempt %d/%d): %s",
                prompt_name, attempt + 1, max_retries, e
            )
            continue
        except Exception as e:
            # 기타 예외는 즉시 발생
            LOGGER.error("LLM call failed with unexpected error: %s", e)
            raise e

    # 모든 재시도 실패
    LOGGER.error("All %d attempts failed for prompt %s.", max_retries, prompt_name)
    raise last_exception or ValueError(f"Failed to get valid JSON after {max_retries} attempts.")
