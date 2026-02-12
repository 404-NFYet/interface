"""뉴스/리포트 요약: GPT-5 mini Map/Reduce 요약 (v2).

동적 청크 분할 → Map(청크별 요약) → Reduce(통합 요약) 전략.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from ..config import (
    OPENAI_PHASE1_CHUNK_TARGET_INPUT_TOKENS,
    OPENAI_PHASE1_MAX_COMPLETION_TOKENS,
    OPENAI_PHASE1_MODEL,
    OPENAI_PHASE1_SUMMARY_MAX_RETRIES,
    OPENAI_PHASE1_TEMPERATURE,
    NEWS_DATA_DIR,
    RESEARCH_DATA_DIR,
)

logger = logging.getLogger(__name__)

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"

# ── 프롬프트 (인라인) ──

_NEWS_SUMMARY_PROMPT = """\
# News Summary

당일 수집된 뉴스 목록을 시장/테마별로 핵심 요약해주세요.

{news_items}

**출력 형식:**
- 3~5개 이슈(테마)로 구분
- 각 이슈당 2~3문장 요약
- 이슈 제목과 요약을 구분해서 작성"""

_REPORTS_SUMMARY_PROMPT = """\
# Reports Summary

당일 수집된 증권/리포트 목록을 시장·테마·이슈별로 핵심 요약해주세요.

{reports_list}

**출력 형식:**
- 3~5개 이슈(테마)로 구분
- 각 이슈당 2~3문장 요약
- 이슈 제목과 요약을 구분해서 작성"""


def _build_payload(prompt: str) -> dict:
    """모델 호환 파라미터로 Chat Completions payload 생성."""
    payload: dict[str, Any] = {
        "model": OPENAI_PHASE1_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_completion_tokens": OPENAI_PHASE1_MAX_COMPLETION_TOKENS,
    }
    # GPT-5 계열은 temperature 커스텀 미지원 가능 → 전달 시도, 실패 시 제거
    if not OPENAI_PHASE1_MODEL.lower().startswith("gpt-5"):
        payload["temperature"] = OPENAI_PHASE1_TEMPERATURE
    return payload


def _estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def _chunk_blocks(
    blocks: list[tuple[int, str]],
    target_input_tokens: int,
) -> list[list[tuple[int, str]]]:
    """입력 토큰 예산 기준으로 동적 청크 분할."""
    target = max(500, target_input_tokens)
    chunks: list[list[tuple[int, str]]] = []
    current: list[tuple[int, str]] = []
    current_tokens = 0

    for idx, block in blocks:
        block_tokens = _estimate_tokens(block) + 2
        if current and (current_tokens + block_tokens > target):
            chunks.append(current)
            current = []
            current_tokens = 0
        current.append((idx, block))
        current_tokens += block_tokens

    if current:
        chunks.append(current)
    return chunks


def _call_chat_summary(prompt: str, api_key: str, max_retries: int) -> dict:
    """요약 호출. 빈 content/length 종료 시 재시도."""
    retries = max(0, max_retries)
    last_error = "unknown_error"

    for attempt in range(1, retries + 2):
        payload = _build_payload(prompt)
        try:
            resp = requests.post(
                OPENAI_API_URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=90,
            )
        except requests.exceptions.RequestException as e:
            last_error = f"request_error: {e}"
            if attempt <= retries:
                continue
            raise RuntimeError(last_error)

        if not resp.ok:
            err_body = resp.text[:1200]
            # GPT-5 temperature 거부 시 제거 후 재시도
            if resp.status_code == 400 and "temperature" in err_body.lower():
                payload.pop("temperature", None)
                retry_resp = requests.post(
                    OPENAI_API_URL,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json=payload,
                    timeout=90,
                )
                if retry_resp.ok:
                    resp = retry_resp
                else:
                    last_error = f"OpenAI API error {resp.status_code}: {err_body}"
                    if attempt <= retries:
                        continue
                    raise RuntimeError(last_error)
            else:
                last_error = f"OpenAI API error {resp.status_code}: {err_body}"
                if attempt <= retries:
                    continue
                raise RuntimeError(last_error)

        data = resp.json()
        choice = data.get("choices", [{}])[0]
        content = choice.get("message", {}).get("content", "")
        finish_reason = choice.get("finish_reason")
        usage = data.get("usage", {})

        if isinstance(content, str) and content.strip():
            return {
                "summary": content.strip(),
                "finish_reason": finish_reason,
                "usage": usage,
                "attempts": attempt,
            }

        last_error = f"empty_content (finish_reason={finish_reason})"
        if attempt <= retries:
            continue

    raise RuntimeError(last_error)


def _format_news_blocks(items: list[dict]) -> list[tuple[int, str]]:
    blocks: list[tuple[int, str]] = []
    for i, n in enumerate(items, start=1):
        title = (n.get("title") or "").strip()
        source = (n.get("source") or "").strip()
        summary = (n.get("summary") or "")[:300]
        date = n.get("published_date", "")
        blocks.append((i, f"- [{source}] {title} ({date})\n  {summary}"))
    return blocks


def _format_report_blocks(items: list[dict]) -> list[tuple[int, str]]:
    blocks: list[tuple[int, str]] = []
    for i, r in enumerate(items, start=1):
        title = (r.get("title") or "").strip()
        source = (r.get("source") or "").strip()
        summary = (r.get("summary") or "")[:400]
        date = r.get("date", "")
        blocks.append((i, f"- [{source}] {title} ({date})\n  {summary}"))
    return blocks


def _build_reduce_prompt(kind: str, merged_chunks: str) -> str:
    label = "뉴스" if kind == "news" else "증권/리포트"
    return (
        f"다음은 당일 {label}를 여러 청크로 나눠 요약한 결과입니다.\n"
        "중복을 제거하고 핵심 이슈만 3~7개로 통합 요약하세요.\n\n"
        f"{merged_chunks}\n\n"
        "출력 형식:\n"
        "## 이슈 제목\n"
        "2~3문장 요약\n"
    )


def _summarize_with_map_reduce(
    *,
    kind: str,
    blocks: list[tuple[int, str]],
    prompt_template: str,
    prompt_key: str,
    no_items_text: str,
) -> str:
    """동적 청크 Map/Reduce 요약."""
    if not blocks:
        return no_items_text

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return f"(OPENAI_API_KEY 미설정) {kind} {len(blocks)}건"

    chunks = _chunk_blocks(blocks, OPENAI_PHASE1_CHUNK_TARGET_INPUT_TOKENS)
    retries = OPENAI_PHASE1_SUMMARY_MAX_RETRIES

    logger.info("[%s 요약] Map/Reduce 시작: %d건 → %d 청크", kind, len(blocks), len(chunks))

    successful_chunks: list[dict[str, Any]] = []
    failed_chunks = 0

    for chunk_index, chunk in enumerate(chunks, start=1):
        chunk_text = "\n\n".join(t for _, t in chunk)
        prompt = prompt_template.replace(f"{{{prompt_key}}}", chunk_text)

        try:
            result = _call_chat_summary(prompt, api_key, retries)
            successful_chunks.append({
                "chunk_index": chunk_index,
                "summary": result["summary"],
            })
        except Exception as e:
            failed_chunks += 1
            logger.warning("[%s 요약] 청크 %d 실패: %s", kind, chunk_index, e)

    if not successful_chunks:
        return "(요약 실패)"

    merged_input = "\n\n".join(
        f"### chunk {c['chunk_index']}\n{c['summary']}" for c in successful_chunks
    )
    reduce_prompt = _build_reduce_prompt(kind, merged_input)

    try:
        reduced = _call_chat_summary(reduce_prompt, api_key, retries)
        final_summary = reduced["summary"]
    except Exception:
        final_summary = "\n\n".join(c["summary"] for c in successful_chunks)

    logger.info("[%s 요약] 완료 (성공 %d/%d 청크)", kind, len(successful_chunks), len(chunks))
    return final_summary


def summarize_news(news_items: list[dict]) -> str:
    """뉴스 아이템을 GPT-5 mini Map/Reduce로 요약."""
    blocks = _format_news_blocks(news_items)
    return _summarize_with_map_reduce(
        kind="news",
        blocks=blocks,
        prompt_template=_NEWS_SUMMARY_PROMPT,
        prompt_key="news_items",
        no_items_text="(뉴스 없음)",
    )


def summarize_research(report_items: list[dict]) -> str:
    """리포트 아이템을 GPT-5 mini Map/Reduce로 요약."""
    blocks = _format_report_blocks(report_items)
    return _summarize_with_map_reduce(
        kind="reports",
        blocks=blocks,
        prompt_template=_REPORTS_SUMMARY_PROMPT,
        prompt_key="reports_list",
        no_items_text="(리포트 없음)",
    )
