"""Financial Tools for Chart Agent.

DART(Corporate), ECOS(Exchange Rate), and Web Search tools.
"""

import logging
from typing import Optional, Any

from langchain_core.tools import tool

from ..config import DART_API_KEY, ECOS_API_KEY
from .multi_provider_client import get_multi_provider_client

logger = logging.getLogger(__name__)

# ── DART (Korean Corporate Data) ──


@tool
def get_corp_financials(corp_name: str, year: Optional[int] = None) -> dict:
    """
    Retrieves financial information (Revenue, Operating Income, Net Income) for a specific Korean corporation.

    Args:
        corp_name: Name of the corporation (e.g., "삼성전자").
        year: Target year (e.g., 2024). If None, returns the latest available data.

    Returns:
        JSON dictionary containing financial data.
    """
    logger.info(f"[Tool] get_corp_financials: {corp_name}, year={year}")

    if not DART_API_KEY:
        return {"error": "DART_API_KEY not configured", "mock_data": _get_mock_financials(corp_name, year)}

    # TODO: Real DART API implementation (corp_code lookup required)
    return _get_mock_financials(corp_name, year)


def _get_mock_financials(corp_name: str, year: Optional[int]) -> dict:
    base_year = year or 2025
    if "삼성" in corp_name:
        return {
            "corp_name": corp_name,
            "year": base_year,
            "data": {
                "sales": "300000000000000",
                "operating_income": "6000000000000",
                "net_income": "5500000000000",
            },
            "unit": "KRW",
            "source": "DART_Mock",
        }
    return {"error": "Data not found", "corp_name": corp_name}


# ── ECOS (Bank of Korea Exchange Rate) ──


@tool
def get_exchange_rate(target_date: str) -> dict:
    """
    Retrieves KRW/USD exchange rate for a specific date from BOK ECOS.

    Args:
        target_date: Date string in 'YYYYMMDD' format (e.g., "20240101").

    Returns:
        JSON dictionary with exchange rate.
    """
    logger.info(f"[Tool] get_exchange_rate: {target_date}")

    if not ECOS_API_KEY:
        return {"date": target_date, "rate": 1350.0, "source": "ECOS_Mock"}

    # TODO: Real ECOS API call
    return {"date": target_date, "rate": 1345.5, "source": "ECOS_Mock_KeyPresent"}


# ── Web Search (Perplexity) ──


@tool
def search_web_for_chart_data(query: str) -> dict:
    """
    Searches the web for quantitative data suitable for charting.
    Use this when specific API tools (DART, ECOS) are insufficient.

    Args:
        query: Search query (e.g., "US Treasury 10Y yield chart data 2024").

    Returns:
        JSON dictionary with search results/summary.
    """
    logger.info(f"[Tool] search_web_for_chart_data: {query}")

    client = get_multi_provider_client()

    if "perplexity" in client.providers:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a research assistant. Find precise quantitative data "
                    "for the user's query. Return the data in a structured format "
                    "(JSON-like) if possible, with sources."
                ),
            },
            {"role": "user", "content": query},
        ]
        try:
            result = client.chat_completion(
                provider="perplexity",
                model="sonar-pro",
                messages=messages,
                temperature=0.1,
            )
            content = result["choices"][0]["message"]["content"]
            return {"result": content, "source": "Perplexity"}
        except Exception as e:
            logger.error(f"Perplexity search failed: {e}")
            return {"error": str(e)}

    return {
        "result": f"Simulated search result for '{query}': Found trend data [10, 20, 15, 25] for 2024.",
        "source": "Mock_Search",
    }
