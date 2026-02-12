"""데이터 수집 노드: 뉴스/리포트 크롤링.

크롤러 실패는 비치명적 (빈 리스트 반환, 파이프라인 계속 진행).
"""

from __future__ import annotations

import datetime as dt
import logging
import time

from langsmith import traceable

logger = logging.getLogger(__name__)


def _update_metrics(state: dict, node_name: str, elapsed: float, status: str = "success") -> dict:
    metrics = dict(state.get("metrics") or {})
    metrics[node_name] = {"elapsed_s": round(elapsed, 2), "status": status}
    return metrics


# ── Mock 데이터 ──

_MOCK_NEWS = [
    {
        "title": "[Mock] 반도체 업황 개선 신호",
        "url": "https://example.com/mock-news-1",
        "source": "Mock Economy",
        "summary": "반도체 재고 조정이 마무리 국면에 접어들었어요.",
        "published_date": dt.date.today().isoformat(),
    },
    {
        "title": "[Mock] AI 관련주 상승세",
        "url": "https://example.com/mock-news-2",
        "source": "Mock Finance",
        "summary": "AI 인프라 투자 확대로 관련 종목이 강세를 보이고 있어요.",
        "published_date": dt.date.today().isoformat(),
    },
]

_MOCK_REPORTS = [
    {
        "title": "[Mock] 산업 전망 리포트",
        "source": "Mock Securities",
        "summary": "2026년 반도체 업황은 하반기 회복이 예상돼요.",
        "date": dt.date.today().isoformat(),
        "firm": "Mock Securities",
    },
]


@traceable(name="crawl_news", run_type="tool",
           metadata={"phase": "data_collection", "phase_name": "데이터 수집", "step": 1})
def crawl_news_node(state: dict) -> dict:
    """뉴스 RSS 크롤링."""
    if state.get("error"):
        return {"error": state["error"]}

    node_start = time.time()
    logger.info("[Node] crawl_news")

    backend = state.get("backend", "live")
    market = state.get("market", "KR")

    if backend == "mock":
        logger.info("  crawl_news mock: %d건", len(_MOCK_NEWS))
        return {
            "raw_news": _MOCK_NEWS,
            "metrics": _update_metrics(state, "crawl_news", time.time() - node_start),
        }

    try:
        from ..data_collection.news_crawler import crawl_news, to_news_items

        target_date = dt.date.today()
        raw_items = crawl_news(target_date, market=market)
        news_items = to_news_items(raw_items)

        logger.info("  crawl_news 완료: %d건", len(news_items))
        return {
            "raw_news": news_items,
            "metrics": _update_metrics(state, "crawl_news", time.time() - node_start),
        }

    except Exception as e:
        logger.warning("  crawl_news 실패 (비치명적): %s", e)
        return {
            "raw_news": [],
            "metrics": _update_metrics(state, "crawl_news", time.time() - node_start, "failed_nonfatal"),
        }


@traceable(name="crawl_research", run_type="tool",
           metadata={"phase": "data_collection", "phase_name": "데이터 수집", "step": 2})
def crawl_research_node(state: dict) -> dict:
    """Naver Finance 리포트 크롤링 + PDF 요약."""
    if state.get("error"):
        return {"error": state["error"]}

    node_start = time.time()
    logger.info("[Node] crawl_research")

    backend = state.get("backend", "live")

    if backend == "mock":
        logger.info("  crawl_research mock: %d건", len(_MOCK_REPORTS))
        return {
            "raw_reports": _MOCK_REPORTS,
            "metrics": _update_metrics(state, "crawl_research", time.time() - node_start),
        }

    try:
        from ..data_collection.research_crawler import crawl_research, to_report_items

        target_date = dt.date.today()
        raw_items = crawl_research(target_date)
        report_items = to_report_items(raw_items)

        logger.info("  crawl_research 완료: %d건", len(report_items))
        return {
            "raw_reports": report_items,
            "metrics": _update_metrics(state, "crawl_research", time.time() - node_start),
        }

    except Exception as e:
        logger.warning("  crawl_research 실패 (비치명적): %s", e)
        return {
            "raw_reports": [],
            "metrics": _update_metrics(state, "crawl_research", time.time() - node_start, "failed_nonfatal"),
        }
