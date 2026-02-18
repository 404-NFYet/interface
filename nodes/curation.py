"""데이터 수집 노드: 요약 + 큐레이션 + CuratedContext 빌드.

4개 노드:
1. summarize_news: GPT-5 mini Map/Reduce 뉴스 요약
2. summarize_research: GPT-5 mini Map/Reduce 리포트 요약
3. curate_topics: GPT-5.2 web search 큐레이션
4. build_curated_context: topics[0] → CuratedContext 조립
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import time
from typing import Any

from langsmith import traceable

from ..schemas import CuratedContext

logger = logging.getLogger(__name__)


def _update_metrics(state: dict, node_name: str, elapsed: float, status: str = "success") -> dict:
    metrics = dict(state.get("metrics") or {})
    metrics[node_name] = {"elapsed_s": round(elapsed, 2), "status": status}
    return metrics


# ── Mock 데이터 ──

_MOCK_SUMMARY = """\
## 반도체
반도체 업황 개선 신호가 나타나고 있어요. 재고 조정이 마무리 국면에 접어들었어요.

## AI/테크
AI 인프라 투자 확대로 관련 종목이 강세를 보이고 있어요."""

_MOCK_TOPICS = [
    {
        "topic": "반도체 업황 회복",
        "interface_1_curated_context": {
            "date": dt.date.today().isoformat(),
            "theme": "반도체 업황 회복과 AI 수요 확대",
            "one_liner": "재고 조정 마무리와 AI 수요 확대가 맞물리며 반도체 업황이 회복세를 보이고 있어요.",
            "selected_stocks": [
                {"ticker": "005930", "name": "삼성전자", "momentum": "상승", "change_pct": 8.5, "period_days": 5},
                {"ticker": "000660", "name": "SK하이닉스", "momentum": "상승", "change_pct": 15.3, "period_days": 126},
            ],
            "verified_news": [
                {
                    "title": "[Mock] 반도체 업황 개선 신호",
                    "url": "https://example.com/mock-news-1",
                    "source": "Mock Economy",
                    "summary": "반도체 재고 조정이 마무리 국면에 접어들었어요.",
                    "published_date": dt.date.today().isoformat(),
                },
            ],
            "reports": [
                {
                    "title": "[Mock] 산업 전망 리포트",
                    "source": "Mock Securities",
                    "summary": "2026년 반도체 업황은 하반기 회복이 예상돼요.",
                    "date": dt.date.today().isoformat(),
                },
            ],
            "concept": {
                "name": "반도체 사이클",
                "definition": "수요와 공급의 엇갈림으로 상승과 하락이 반복되는 주기예요.",
                "relevance": "현재는 재고 조정 마무리와 AI 신수요가 동시에 나타나는 전환점이에요.",
            },
            "source_ids": ["ws1_s1", "ws1_s2"],
            "evidence_source_urls": ["https://example.com/mock-evidence-1"],
        },
    }
]


@traceable(name="summarize_news", run_type="llm",
           metadata={"phase": "data_collection", "phase_name": "데이터 수집", "step": 4})
def summarize_news_node(state: dict) -> dict:
    """뉴스 GPT-5 mini Map/Reduce 요약."""
    if state.get("error"):
        return {"error": state["error"]}

    node_start = time.time()
    logger.info("[Node] summarize_news")

    backend = state.get("backend", "live")
    raw_news = state.get("raw_news", [])

    if backend == "mock":
        logger.info("  summarize_news mock")
        return {
            "news_summary": _MOCK_SUMMARY,
            "metrics": _update_metrics(state, "summarize_news", time.time() - node_start),
        }

    try:
        from ..data_collection.news_summarizer import summarize_news
        summary = summarize_news(raw_news)
        logger.info("  summarize_news 완료: %d자", len(summary))
        return {
            "news_summary": summary,
            "metrics": _update_metrics(state, "summarize_news", time.time() - node_start),
        }
    except Exception as e:
        logger.warning("  summarize_news 실패 (비치명적): %s", e)
        return {
            "news_summary": "(뉴스 요약 실패)",
            "metrics": _update_metrics(state, "summarize_news", time.time() - node_start, "failed_nonfatal"),
        }


@traceable(name="summarize_research", run_type="llm",
           metadata={"phase": "data_collection", "phase_name": "데이터 수집", "step": 5})
def summarize_research_node(state: dict) -> dict:
    """리포트 GPT-5 mini Map/Reduce 요약."""
    if state.get("error"):
        return {"error": state["error"]}

    node_start = time.time()
    logger.info("[Node] summarize_research")

    backend = state.get("backend", "live")
    raw_reports = state.get("raw_reports", [])

    if backend == "mock":
        logger.info("  summarize_research mock")
        return {
            "research_summary": _MOCK_SUMMARY,
            "metrics": _update_metrics(state, "summarize_research", time.time() - node_start),
        }

    try:
        from ..data_collection.news_summarizer import summarize_research
        summary = summarize_research(raw_reports)
        logger.info("  summarize_research 완료: %d자", len(summary))
        return {
            "research_summary": summary,
            "metrics": _update_metrics(state, "summarize_research", time.time() - node_start),
        }
    except Exception as e:
        logger.warning("  summarize_research 실패 (비치명적): %s", e)
        return {
            "research_summary": "(리포트 요약 실패)",
            "metrics": _update_metrics(state, "summarize_research", time.time() - node_start, "failed_nonfatal"),
        }


@traceable(name="curate_topics", run_type="llm",
           metadata={"phase": "data_collection", "phase_name": "데이터 수집", "step": 6})
def curate_topics_node(state: dict) -> dict:
    """GPT-5.2 + web search → 투자 테마 큐레이션."""
    if state.get("error"):
        return {"error": state["error"]}

    node_start = time.time()
    logger.info("[Node] curate_topics")

    backend = state.get("backend", "live")

    if backend == "mock":
        logger.info("  curate_topics mock: %d topics", len(_MOCK_TOPICS))
        return {
            "curated_topics": _MOCK_TOPICS,
            "websearch_log": {"mock": True},
            "metrics": _update_metrics(state, "curate_topics", time.time() - node_start),
        }

    try:
        from ..data_collection.openai_curator import curate_with_websearch

        news_summary = state.get("news_summary", "(뉴스 없음)")
        research_summary = state.get("research_summary", "(리포트 없음)")

        # 스크리닝 결과를 텍스트로 포맷
        matched = state.get("matched_stocks", [])
        screening_lines = []
        for s in matched:
            screening_lines.append(
                f"- {s['name']} ({s['symbol']}): {s['signal']}, "
                f"수익률 {s['return_pct']}%, 거래량비 {s['volume_ratio']}x"
            )
        screening_results = "\n".join(screening_lines) or "(스크리닝 결과 없음)"

        market = state.get("market", "KR")
        date = dt.date.today().isoformat()

        topics, log_data = curate_with_websearch(
            news_summary=news_summary,
            reports_summary=research_summary,
            screening_results=screening_results,
            date=date,
            market=market,
        )

        logger.info("  curate_topics 완료: %d topics", len(topics))
        return {
            "curated_topics": topics,
            "websearch_log": log_data,
            "metrics": _update_metrics(state, "curate_topics", time.time() - node_start),
        }

    except Exception as e:
        logger.error("  curate_topics 실패: %s", e)
        return {
            "error": f"curate_topics 실패: {e}",
            "metrics": _update_metrics(state, "curate_topics", time.time() - node_start, "failed"),
        }


@traceable(name="build_curated_context", run_type="tool",
           metadata={"phase": "data_collection", "phase_name": "데이터 수집", "step": 7})
def build_curated_context_node(state: dict) -> dict:
    """curated_topics[topic_index] → CuratedContext 조립 + Pydantic 검증."""
    if state.get("error"):
        return {"error": state["error"]}

    node_start = time.time()
    logger.info("[Node] build_curated_context")

    try:
        topics = state.get("curated_topics", [])
        
        if not topics:
            return {
                "error": "큐레이션 결과가 없습니다.",
                "metrics": _update_metrics(state, "build_curated_context", time.time() - node_start, "failed"),
            }

        topic_index = state.get("topic_index", 0)
        if topic_index >= len(topics):
            topic_index = 0

        topic = topics[topic_index]
        raw_ctx = topic.get("interface_1_curated_context", topic)

        # Pydantic 검증
        curated = CuratedContext.model_validate(raw_ctx)
        logger.info("  build_curated_context 완료: theme=%s", curated.theme[:50])

        return {
            "curated_context": curated.model_dump(),
            "metrics": _update_metrics(state, "build_curated_context", time.time() - node_start),
        }

    except Exception as e:
        logger.error("  build_curated_context 실패: %s", e)
        return {
            "error": f"build_curated_context 실패: {e}",
            "metrics": _update_metrics(state, "build_curated_context", time.time() - node_start, "failed"),
        }
