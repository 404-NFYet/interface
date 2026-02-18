"""데이터 수집 노드: 주가 스크리닝.

FinanceDataReader 기반 가격 변동 스크리닝 + MatchedStock 변환.
스크리닝 실패는 치명적 (종목 없으면 진행 불가).
"""

from __future__ import annotations

import logging
import time

from langsmith import traceable

logger = logging.getLogger(__name__)


def _update_metrics(state: dict, node_name: str, elapsed: float, status: str = "success") -> dict:
    """메트릭 업데이트 (Partial Update for Reducer)."""
    return {
        node_name: {
            "elapsed_s": round(elapsed, 2),
            "status": status
        }
    }


_MOCK_SCREENED = [
    {"symbol": "005930", "name": "삼성전자", "signal": "short_surge", "return_pct": 8.5, "volume_ratio": 2.1, "period_days": 5},
    {"symbol": "000660", "name": "SK하이닉스", "signal": "mid_term_up", "return_pct": 15.3, "volume_ratio": 1.8, "period_days": 126},
    {"symbol": "035420", "name": "NAVER", "signal": "volume_spike", "return_pct": 0.0, "volume_ratio": 3.2, "period_days": 1},
]


@traceable(name="screen_stocks", run_type="tool",
           metadata={"phase": "data_collection", "phase_name": "데이터 수집", "step": 3})
def screen_stocks_node(state: dict) -> dict:
    """가격 변동 기준 종목 스크리닝 + MatchedStock 변환."""
    if state.get("error"):
        return {"error": state["error"]}

    node_start = time.time()
    logger.info("[Node] screen_stocks")

    backend = state.get("backend", "live")
    market = state.get("market", "KR")

    if backend == "mock":
        from ..data_collection.intersection import screened_to_matched
        matched = [screened_to_matched(s) for s in _MOCK_SCREENED]
        logger.info("  screen_stocks mock: %d종목", len(matched))
        return {
            "screened_stocks": _MOCK_SCREENED,
            "matched_stocks": matched,
            "metrics": _update_metrics(state, "screen_stocks", time.time() - node_start),
        }

    try:
        from ..data_collection.intersection import screened_to_matched
        from ..mcp_client import call_mcp_tool
        from ..config import TOP_N

        # MCP 도구 호출 (기존 screen_stocks 대체)
        screened = call_mcp_tool("get_top_gainers", {
            "market": market,
            "limit": TOP_N
        })
        if not screened:
            return {
                "error": "스크리닝 결과가 없습니다. 시장 데이터를 확인하세요.",
                "metrics": _update_metrics(state, "screen_stocks", time.time() - node_start, "failed"),
            }

        matched = [screened_to_matched(s) for s in screened]
        logger.info("  screen_stocks 완료: %d종목 스크리닝, %d종목 매칭", len(screened), len(matched))

        return {
            "screened_stocks": screened,
            "matched_stocks": matched,
            "metrics": _update_metrics(state, "screen_stocks", time.time() - node_start),
        }

    except Exception as e:
        logger.error("  screen_stocks 실패: %s", e)
        return {
            "error": f"screen_stocks 실패: {e}",
            "metrics": _update_metrics(state, "screen_stocks", time.time() - node_start, "failed"),
        }
