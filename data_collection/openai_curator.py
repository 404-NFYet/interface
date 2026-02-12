"""GPT-5.2 + 웹서치 큐레이션 (v2).

OpenAI Responses API + web_search 도구 + strict JSON schema 검증.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from ..config import (
    OPENAI_PHASE2_MAX_OUTPUT_TOKENS,
    OPENAI_PHASE2_MODEL,
)

logger = logging.getLogger(__name__)

OPENAI_API_URL = "https://api.openai.com/v1/responses"

# ── 큐레이션 프롬프트 (인라인) ──
_CURATED_WEBSEARCH_PROMPT = """\
# Curated Web Search

당일 스크리닝된 종목, 뉴스 요약, 리포트 요약을 바탕으로 **웹 검색**을 활용해 투자 테마 큐레이션을 수행해주세요.

## 입력

### 뉴스 요약
{news_summary}

### 리포트 요약
{reports_summary}

### 스크리닝 종목
{screening_results}

## 지시사항

1. **웹 검색**을 사용해 종목·테마별 최신 뉴스를 검증·보강하세요.
2. 스크리닝 종목을 **3~5개 투자 테마**로 그룹화하세요.
3. 각 테마별로 `interface_1_curated_context`를 생성하세요.
4. `verified_news`: 웹 검색으로 확인한 뉴스 (title, url, source, summary, published_date)
5. `reports`: 입력 리포트 중 해당 테마 관련 항목
6. `concept`: 금융/투자 관점 개념 (name, definition, relevance)
7. 각 topic마다 `source_ids`, `evidence_source_urls`를 반드시 포함하세요.

**concept.name**은 기술 용어가 아니라 **금융/투자 관점의 개념**으로 (예: 반도체 사이클, 리레이팅, 실적 가시성).
**source_ids** 형식은 `ws{{번호}}_s{{번호}}` (예: `ws1_s3`)를 사용하세요.

## 출력

아래 JSON 형식으로만 답변하세요. 날짜는 {date}, 시장은 {market}입니다.
중요:
- 모든 topic의 `source_ids`, `evidence_source_urls`는 **빈 배열이면 안 됩니다**.
- `verified_news[].url`은 가능한 한 `evidence_source_urls`와 일치하게 작성하세요.
- `source_ids`, `evidence_source_urls`는 웹 검색에서 얻은 source만 사용하세요.

```json
{{
  "topics": [
    {{
      "topic": "<테마제목>",
      "interface_1_curated_context": {{
        "date": "{date}",
        "theme": "<부제목>",
        "one_liner": "<한줄요약>",
        "selected_stocks": [
          {{"ticker": "<코드>", "name": "<종목명>", "momentum": "상승|하락|횡보", "change_pct": 0, "period_days": 0}}
        ],
        "verified_news": [
          {{"title": "", "url": "", "source": "", "summary": "", "published_date": ""}}
        ],
        "reports": [
          {{"title": "", "source": "", "summary": "", "date": ""}}
        ],
        "concept": {{"name": "", "definition": "", "relevance": ""}},
        "source_ids": ["ws1_s1", "ws2_s3"],
        "evidence_source_urls": ["https://...", "https://..."]
      }}
    }}
  ]
}}
```"""

CURATED_TOPICS_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["topics"],
    "properties": {
        "topics": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["topic", "interface_1_curated_context"],
                "properties": {
                    "topic": {"type": "string", "minLength": 1},
                    "interface_1_curated_context": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "date", "theme", "one_liner", "selected_stocks",
                            "verified_news", "reports", "concept",
                            "source_ids", "evidence_source_urls",
                        ],
                        "properties": {
                            "date": {"type": "string", "minLength": 1},
                            "theme": {"type": "string", "minLength": 1},
                            "one_liner": {"type": "string", "minLength": 1},
                            "selected_stocks": {
                                "type": "array",
                                "minItems": 1,
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": ["ticker", "name", "momentum", "change_pct", "period_days"],
                                    "properties": {
                                        "ticker": {"type": "string", "minLength": 1},
                                        "name": {"type": "string", "minLength": 1},
                                        "momentum": {"type": "string", "enum": ["상승", "하락", "횡보"]},
                                        "change_pct": {"type": "number"},
                                        "period_days": {"type": "integer"},
                                    },
                                },
                            },
                            "verified_news": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": ["title", "url", "source", "summary", "published_date"],
                                    "properties": {
                                        "title": {"type": "string"},
                                        "url": {"type": "string"},
                                        "source": {"type": "string"},
                                        "summary": {"type": "string"},
                                        "published_date": {"type": "string"},
                                    },
                                },
                            },
                            "reports": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": ["title", "source", "summary", "date"],
                                    "properties": {
                                        "title": {"type": "string"},
                                        "source": {"type": "string"},
                                        "summary": {"type": "string"},
                                        "date": {"type": "string"},
                                    },
                                },
                            },
                            "concept": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["name", "definition", "relevance"],
                                "properties": {
                                    "name": {"type": "string", "minLength": 1},
                                    "definition": {"type": "string", "minLength": 1},
                                    "relevance": {"type": "string", "minLength": 1},
                                },
                            },
                            "source_ids": {
                                "type": "array",
                                "minItems": 1,
                                "items": {"type": "string", "minLength": 1},
                            },
                            "evidence_source_urls": {
                                "type": "array",
                                "minItems": 1,
                                "items": {"type": "string", "minLength": 1},
                            },
                        },
                    },
                },
            },
        }
    },
}


class CuratorValidationError(RuntimeError):
    """GPT-5.2 output schema/validation 실패."""

    def __init__(self, message: str, log_data: dict) -> None:
        super().__init__(message)
        self.log_data = log_data


def _extract_output_text(data: dict) -> str:
    for item in data.get("output", []):
        if item.get("type") == "message" and item.get("status") == "completed":
            for c in item.get("content", []):
                if c.get("type") == "output_text" and c.get("text"):
                    return c["text"]
    return ""


def _build_payload(prompt: str) -> dict:
    return {
        "model": OPENAI_PHASE2_MODEL,
        "tools": [{"type": "web_search"}],
        "tool_choice": "auto",
        "include": ["web_search_call.action.sources"],
        "input": prompt,
        "max_output_tokens": OPENAI_PHASE2_MAX_OUTPUT_TOKENS,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "curated_topics_response",
                "schema": CURATED_TOPICS_JSON_SCHEMA,
                "strict": True,
            }
        },
    }


def _request_responses(payload: dict, api_key: str) -> dict:
    resp = requests.post(
        OPENAI_API_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=180,
    )
    if not resp.ok:
        err_body = resp.text[:2000]
        raise RuntimeError(f"OpenAI Responses API error {resp.status_code}: {err_body}")
    return resp.json()


def _parse_web_search_log(output: list) -> dict:
    web_search_calls: list[dict] = []
    citations_used: list[dict] = []
    source_catalog: list[dict] = []
    call_index = 0

    for item in output:
        if item.get("type") == "web_search_call":
            call_index += 1
            action = item.get("action")
            if isinstance(action, dict):
                queries = action.get("queries", []) or []
                sources = action.get("sources", []) or []
            else:
                queries = getattr(action, "queries", []) or []
                sources = getattr(action, "sources", []) or []
            if not isinstance(queries, list):
                queries = [queries] if queries else []
            if not isinstance(sources, list):
                sources = [sources] if sources else []

            source_ids = []
            for si, source in enumerate(sources, start=1):
                source_url = str(source.get("url", "")).strip() if isinstance(source, dict) else str(source).strip()
                source_title = str(source.get("title", "")).strip() if isinstance(source, dict) else ""
                source_id = f"ws{call_index}_s{si}"
                source_ids.append(source_id)
                if source_url:
                    entry = {"source_id": source_id, "url": source_url}
                    if source_title:
                        entry["title"] = source_title
                    source_catalog.append(entry)

            web_search_calls.append({
                "queries": queries,
                "sources_count": len(sources),
                "source_ids": source_ids,
            })

        if item.get("type") == "message":
            for c in item.get("content", []):
                for a in c.get("annotations", []):
                    if a.get("type") == "url_citation":
                        uc = a.get("url_citation") or a
                        citations_used.append({
                            "url": uc.get("url", ""),
                            "title": uc.get("title", ""),
                        })

    return {
        "web_search_calls": web_search_calls,
        "citations_used": citations_used,
        "source_catalog": source_catalog,
        "summary": {
            "total_searches": len(web_search_calls),
            "total_sources_consulted": sum(c.get("sources_count", 0) for c in web_search_calls),
            "total_citations_in_output": len(citations_used),
        },
    }


def _parse_topics(data: dict) -> list[dict]:
    output_text = _extract_output_text(data).strip()
    if not output_text:
        raise ValueError("empty_output_text")
    parsed = json.loads(output_text)
    if not isinstance(parsed, dict):
        raise ValueError("output_root_not_object")
    topics = parsed.get("topics")
    if not isinstance(topics, list) or not topics:
        raise ValueError("topics_missing_or_empty")
    return topics


def _validate_topics(topics: list[dict], source_catalog: list[dict]) -> tuple[list[str], list[dict]]:
    errors: list[str] = []
    source_ids_available = {
        str(s.get("source_id", "")).strip()
        for s in source_catalog if isinstance(s, dict) and str(s.get("source_id", "")).strip()
    }

    for i, topic in enumerate(topics, start=1):
        topic_name = str(topic.get("topic", f"topic_{i}")) if isinstance(topic, dict) else f"topic_{i}"
        if not isinstance(topic, dict):
            errors.append(f"{topic_name}: topic_not_object")
            continue

        ctx = topic.get("interface_1_curated_context")
        if not isinstance(ctx, dict):
            errors.append(f"{topic_name}: missing_interface_1_curated_context")
            continue

        source_ids = [str(v).strip() for v in (ctx.get("source_ids") or []) if str(v).strip()]
        evidence_urls = [str(v).strip() for v in (ctx.get("evidence_source_urls") or []) if str(v).strip()]

        if not source_ids:
            errors.append(f"{topic_name}: source_ids_empty")
        if not evidence_urls:
            errors.append(f"{topic_name}: evidence_source_urls_empty")

        # ws0_* → ws1_* 보정
        normalized_ids = []
        for sid in source_ids:
            if sid not in source_ids_available:
                m = re.fullmatch(r"ws0_s(\d+)", sid)
                if m and f"ws1_s{m.group(1)}" in source_ids_available:
                    sid = f"ws1_s{m.group(1)}"
            if sid in source_ids_available:
                normalized_ids.append(sid)
            else:
                errors.append(f"{topic_name}: unknown_source_id={sid}")

    return errors, []


def _build_retry_prompt(prompt: str, errors: list[str], available_ids: list[str]) -> str:
    issues = "\n".join(f"- {e}" for e in errors[:20])
    ids_hint = ", ".join(available_ids[:80]) if available_ids else "(없음)"
    return (
        prompt + "\n\n[RETRY]\n"
        + "이전 출력이 스키마/검증 규칙을 충족하지 못했습니다. 아래 오류를 모두 수정해서 JSON만 다시 출력하세요.\n"
        + issues
        + "\n사용 가능한 source_ids 목록(이 값만 사용): " + ids_hint
        + "\n중요: 각 topic의 interface_1_curated_context에 source_ids, evidence_source_urls를 "
        + "반드시 비어있지 않게 포함하고, 값은 web_search source와 일치해야 합니다."
    )


def curate_with_websearch(
    news_summary: str,
    reports_summary: str,
    screening_results: str,
    date: str,
    market: str,
) -> tuple[list[dict], dict]:
    """GPT-5.2 + 웹서치로 curated JSON 생성.

    Returns:
        (topics 리스트, web_search_log dict)
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY required for v2 curated")

    base_prompt = _CURATED_WEBSEARCH_PROMPT.format(
        news_summary=news_summary,
        reports_summary=reports_summary,
        screening_results=screening_results,
        date=date,
        market=market,
    )

    previous_errors: list[str] = []
    previous_available_ids: list[str] = []
    last_log_data: dict = {}

    for attempt in (1, 2):
        prompt = (
            base_prompt if attempt == 1
            else _build_retry_prompt(base_prompt, previous_errors, previous_available_ids)
        )
        payload = _build_payload(prompt)
        data = _request_responses(payload, api_key)

        output = data.get("output", [])
        log_data = _parse_web_search_log(output)
        log_data["timestamp"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        log_data["market"] = market
        available_ids = sorted({
            str(s.get("source_id", "")).strip()
            for s in log_data.get("source_catalog", [])
            if isinstance(s, dict) and str(s.get("source_id", "")).strip()
        })
        previous_available_ids = available_ids

        try:
            topics = _parse_topics(data)
            errors, _ = _validate_topics(topics, log_data.get("source_catalog", []))
        except (ValueError, json.JSONDecodeError) as e:
            topics = []
            errors = [str(e)]

        log_data["schema_validation"] = {
            "status": "passed" if not errors else "failed",
            "attempt": attempt,
            "errors": errors,
        }
        last_log_data = log_data

        if not errors:
            logger.info("[큐레이션] 성공 (attempt=%d, topics=%d)", attempt, len(topics))
            return topics, log_data
        previous_errors = errors

    raise CuratorValidationError(
        "Schema validation failed after retry.\n" + "\n".join(f"- {e}" for e in previous_errors),
        last_log_data,
    )


def save_websearch_log(log_data: dict, log_dir: str | Path = "logs") -> Path:
    """웹서치 로그 저장."""
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = Path(log_dir) / f"curate_websearch_{ts}.json"
    path.write_text(json.dumps(log_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
