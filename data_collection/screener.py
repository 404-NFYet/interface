"""가격 변동 스크리닝: 단기(급등/급락/거래량) + 중장기(6-1 수익률).

FinanceDataReader로 OHLCV 데이터를 가져와 4가지 시그널을 감지한다.
"""

from __future__ import annotations

import logging
from typing import Any

import FinanceDataReader as fdr
import pandas as pd
from tqdm import tqdm

from ..config import (
    MID_TERM_FORMATION_DAYS,
    MID_TERM_RETURN_MIN,
    MID_TERM_SKIP_DAYS,
    MID_TERM_TOTAL_DAYS,
    SCAN_LIMIT,
    SHORT_TERM_DAYS,
    SHORT_TERM_RETURN_MIN,
    TOP_N,
    VOLUME_RATIO_MIN,
    get_price_period,
)

logger = logging.getLogger(__name__)


def _get_col(df: pd.DataFrame, primary: str, fallback: str) -> str | None:
    if primary in df.columns:
        return primary
    if fallback in df.columns:
        return fallback
    return None


def _get_symbol_col(df: pd.DataFrame) -> str:
    for c in ("Code", "Symbol"):
        if c in df.columns:
            return c
    raise ValueError("No symbol column")


def _get_name_col(df: pd.DataFrame) -> str:
    for c in ("Name", "company_name", "Security"):
        if c in df.columns:
            return c
    raise ValueError("No name column")


def _scan_stock(closes: pd.Series, volumes: pd.Series | None) -> list[dict]:
    """단일 종목에 대해 여러 시그널 판별."""
    signals: list[dict] = []
    price_now = closes.iloc[-1]

    vol_ratio = 1.0
    if volumes is not None and len(volumes) >= 20:
        vol_avg = volumes.tail(20).mean()
        vol_last = volumes.iloc[-1]
        vol_ratio = vol_last / vol_avg if vol_avg > 0 else 0
        if vol_ratio >= VOLUME_RATIO_MIN:
            signals.append({
                "signal": "volume_spike",
                "return_pct": 0.0,
                "volume_ratio": round(vol_ratio, 2),
                "period_days": 1,
            })

    if len(closes) >= SHORT_TERM_DAYS + 1:
        price_before = closes.iloc[-(SHORT_TERM_DAYS + 1)]
        if price_before > 0:
            short_ret = (price_now - price_before) / price_before * 100
            if short_ret >= SHORT_TERM_RETURN_MIN:
                signals.append({
                    "signal": "short_surge",
                    "return_pct": round(short_ret, 2),
                    "volume_ratio": round(vol_ratio, 2),
                    "period_days": SHORT_TERM_DAYS,
                })
            elif short_ret <= -SHORT_TERM_RETURN_MIN:
                signals.append({
                    "signal": "short_drop",
                    "return_pct": round(short_ret, 2),
                    "volume_ratio": round(vol_ratio, 2),
                    "period_days": SHORT_TERM_DAYS,
                })

    if len(closes) >= MID_TERM_TOTAL_DAYS:
        p_start = closes.iloc[-(MID_TERM_SKIP_DAYS + MID_TERM_FORMATION_DAYS)]
        p_end = closes.iloc[-(MID_TERM_SKIP_DAYS + 1)]
        if p_start > 0:
            mid_ret = (p_end - p_start) / p_start * 100
            if mid_ret >= MID_TERM_RETURN_MIN:
                signals.append({
                    "signal": "mid_term_up",
                    "return_pct": round(mid_ret, 2),
                    "volume_ratio": round(vol_ratio, 2),
                    "period_days": MID_TERM_FORMATION_DAYS,
                })

    return signals


def _get_min_price(market: str) -> float:
    return 1000.0 if market == "KR" else 5.0


def _screen_single_market(market: str) -> list[dict]:
    """단일 시장 가격 스크리닝."""
    start, end = get_price_period()
    min_price = _get_min_price(market)

    listing = fdr.StockListing("KRX") if market == "KR" else fdr.StockListing("S&P500")
    symbol_col = _get_symbol_col(listing)
    name_col = _get_name_col(listing)

    rows = list(listing.iterrows())
    if SCAN_LIMIT > 0:
        rows = rows[:SCAN_LIMIT]

    results: list[dict] = []

    for _, row in tqdm(rows, desc=f"가격 스크리닝 ({market})", unit="종목"):
        sym = str(row[symbol_col]).strip()
        name = str(row.get(name_col, sym))
        if not sym or sym == "nan":
            continue

        try:
            df = fdr.DataReader(sym, start, end)
        except Exception:
            continue
        if df is None or len(df) < SHORT_TERM_DAYS + 1:
            continue

        df = df.sort_index()
        close_col = _get_col(df, "Close", "close")
        vol_col = _get_col(df, "Volume", "volume")
        if not close_col:
            continue

        closes = df[close_col]
        volumes = df[vol_col] if vol_col else None

        if closes.iloc[-1] < min_price:
            continue

        for sig in _scan_stock(closes, volumes):
            results.append({"symbol": sym, "name": name, **sig})

    results.sort(key=lambda x: abs(x["return_pct"]), reverse=True)

    seen: set[str] = set()
    top: list[dict] = []
    for r in results:
        if r["symbol"] not in seen:
            seen.add(r["symbol"])
            top.append(r)
        elif len([t for t in top if t["symbol"] == r["symbol"]]) < 3:
            top.append(r)
        if len(seen) >= TOP_N:
            break

    return top


def screen_stocks(market: str = "KR") -> list[dict]:
    """가격 변동 기준 종목 스크리닝. market=ALL이면 KR+US 통합."""
    if market == "ALL":
        kr = _screen_single_market("KR")
        us = _screen_single_market("US")
        combined = kr + us
        combined.sort(key=lambda x: abs(x["return_pct"]), reverse=True)
        return combined
    return _screen_single_market(market)
