"""교집합 로직: v2에서는 narrative 매칭 없이 직접 변환.

screened_to_matched()로 ScreenedStock → MatchedStock 직접 변환.
"""

from __future__ import annotations


def screened_to_matched(stock: dict) -> dict:
    """스크리닝 결과를 MatchedStock 형태로 변환 (v2: narrative 없음)."""
    return {
        "symbol": stock["symbol"],
        "name": stock["name"],
        "signal": stock["signal"],
        "return_pct": stock["return_pct"],
        "volume_ratio": stock["volume_ratio"],
        "period_days": stock["period_days"],
        "narrative_headlines": [],
        "narrative_sources": [],
        "has_narrative": False,
    }
