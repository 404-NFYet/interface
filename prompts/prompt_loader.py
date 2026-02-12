"""프롬프트 로더: .md 프롬프트 템플릿을 로드하고 변수 치환을 수행한다.

datapipeline/prompts/prompt_loader.py에서 복제.

각 프롬프트 파일은 ``interface/prompts/templates/`` 에 위치하며 다음 형식을 따른다::

    ---
    provider: openai
    model: gpt-5-mini
    temperature: 0.7
    thinking: true
    thinking_effort: medium
    response_format: json_object
    system_message: >
      당신은 투자 전문가입니다.
    ---
    {{include:_tone_guide}} 를 통해 다른 .md 파일을 인라인할 수 있다.
    {{variable}} 를 통해 런타임 변수를 치환할 수 있다.

``load_prompt`` 은 ``PromptSpec`` 데이터클래스를 반환한다.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

# 기본 프롬프트 디렉토리 (이 파일 기준 sibling)
_DEFAULT_DIR = Path(__file__).resolve().parent / "templates"

# {{variable}} 패턴
_VAR_PATTERN = re.compile(r"\{\{(\w+)\}\}")

# {{include:filename}} 패턴
_INCLUDE_PATTERN = re.compile(r"\{\{include:(\w+)\}\}")

# frontmatter 구분자
_FM_DELIM = "---"


@dataclass
class PromptSpec:
    """파싱된 프롬프트 템플릿 + 메타데이터."""

    body: str
    provider: str = "openai"          # openai, perplexity, anthropic
    model: str = "gpt-4o-mini"        # 실제 모델명
    temperature: float = 0.7
    response_format: str | None = None  # "json_object" or None
    role: str = ""                     # "system" if system_message present
    system_message: str = ""
    max_tokens: int = 4096
    thinking: bool = False             # GPT-5 thinking 모드 활성화
    thinking_effort: str = "medium"    # low, medium, high
    extra: dict[str, Any] = field(default_factory=dict)


def _parse_frontmatter(raw: str) -> tuple[dict[str, str], str]:
    """frontmatter (YAML-like key: value)와 body를 분리한다."""
    lines = raw.split("\n")
    if not lines or lines[0].strip() != _FM_DELIM:
        return {}, raw

    meta_lines: list[str] = []
    body_start = 1
    found_end = False
    for idx, line in enumerate(lines[1:], start=1):
        if line.strip() == _FM_DELIM:
            body_start = idx + 1
            found_end = True
            break
        meta_lines.append(line)

    if not found_end:
        return {}, raw

    meta: dict[str, str] = {}
    current_key = ""
    current_value = ""
    for mline in meta_lines:
        stripped = mline.strip()
        if not stripped:
            continue
        if ":" in stripped and not stripped.startswith(" "):
            if current_key:
                meta[current_key] = current_value.strip()
            key, _, value = stripped.partition(":")
            current_key = key.strip()
            current_value = value.strip()
            if current_value == ">":
                current_value = ""
        elif current_key:
            current_value += " " + stripped
    if current_key:
        meta[current_key] = current_value.strip()

    body = "\n".join(lines[body_start:])
    return meta, body


def _resolve_includes(body: str, prompts_dir: Path) -> str:
    """{{include:filename}} 지시자를 참조된 파일 내용으로 치환한다."""

    def _replacer(match: re.Match[str]) -> str:
        name = match.group(1)
        include_path = prompts_dir / f"{name}.md"
        if not include_path.exists():
            LOGGER.warning("Include file not found: %s", include_path)
            return ""
        return include_path.read_text(encoding="utf-8").strip()

    return _INCLUDE_PATTERN.sub(_replacer, body)


def _substitute_vars(body: str, variables: dict[str, str]) -> str:
    """{{variable}} 플레이스홀더를 제공된 값으로 치환한다."""

    def _replacer(match: re.Match[str]) -> str:
        key = match.group(1)
        if key in variables:
            return variables[key]
        LOGGER.debug("Unresolved variable: {{%s}}", key)
        return ""

    return _VAR_PATTERN.sub(_replacer, body)


def _parse_bool(value: str) -> bool:
    """문자열을 bool로 변환."""
    return value.strip().lower() in {"true", "1", "yes", "on"}


def load_prompt(
    name: str,
    prompts_dir: str | Path | None = None,
    **kwargs: str,
) -> PromptSpec:
    """이름으로 프롬프트 템플릿을 로드하고, include 해결 및 변수 치환을 수행한다.

    Args:
        name: 확장자 없는 프롬프트 파일 이름 (예: "page_purpose").
        prompts_dir: 오버라이드 디렉토리. 기본값: ``interface/prompts/templates/``.
        **kwargs: 템플릿에 치환할 변수.

    Returns:
        렌더링된 body와 메타데이터가 담긴 PromptSpec.
    """
    directory = Path(prompts_dir) if prompts_dir else _DEFAULT_DIR
    filepath = directory / f"{name}.md"

    if not filepath.exists():
        raise FileNotFoundError(f"프롬프트 템플릿을 찾을 수 없습니다: {filepath}")

    raw = filepath.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(raw)

    # include 해결
    body = _resolve_includes(body, directory)

    # 변수 치환
    str_kwargs = {k: str(v) for k, v in kwargs.items()}
    body = _substitute_vars(body, str_kwargs)

    # system_message에도 include/변수 치환 적용
    sys_msg = meta.get("system_message", "")
    if sys_msg:
        sys_msg = _resolve_includes(sys_msg, directory)
        sys_msg = _substitute_vars(sys_msg, str_kwargs)
        meta["system_message"] = sys_msg

    # frontmatter에서 값 추출
    response_format = meta.get("response_format")
    try:
        temperature = float(meta.get("temperature", "0.7"))
    except (TypeError, ValueError):
        temperature = 0.7

    try:
        max_tokens = int(meta.get("max_tokens", "4096"))
    except (TypeError, ValueError):
        max_tokens = 4096

    return PromptSpec(
        body=body.strip(),
        provider=meta.get("provider", "openai"),
        model=meta.get("model", "gpt-4o-mini"),
        temperature=temperature,
        response_format=response_format if response_format else None,
        role=meta.get("role", ""),
        system_message=meta.get("system_message", ""),
        max_tokens=max_tokens,
        thinking=_parse_bool(meta.get("thinking", "false")),
        thinking_effort=meta.get("thinking_effort", "medium"),
        extra={
            k: v for k, v in meta.items()
            if k not in (
                "provider", "model", "temperature", "response_format",
                "role", "system_message", "max_tokens", "thinking", "thinking_effort",
            )
        },
    )
