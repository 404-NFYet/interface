"""Interface MCP Server.

기존의 하드코딩된 크롤러와 스크리너를 MCP 도구로 래핑하여 노출합니다.
추후 이 파일은 실제 외부 MCP 서버로 대체될 수 있습니다.
"""

from typing import Any
import datetime as dt
from mcp.server.fastmcp import FastMCP

from .data_collection.news_crawler import crawl_news
from .data_collection.screener import screen_stocks
from .config import MARKET

# MCP 서버 인스턴스 생성
mcp = FastMCP("Interface Data Server")

@mcp.tool()
def search_news(query: str, market: str = "KR", days: int = 1) -> str:
    """뉴스 데이터를 검색/수집합니다.
    
    Args:
        query: 검색어 (현재는 무시됨 - RSS 기반)
        market: 시장 (KR/US)
        days: 최근 며칠간의 데이터를 가져올지 (기본 1일)
    """
    target_date = dt.date.today()
    # 기존 crawl_news 함수 재사용 (query는 RSS 방식이라 무시되지만 인터페이스는 유지)
    news_items = crawl_news(target_date, market)
    
    # 결과 요약 반환 (JSON string)
    import json
    return json.dumps(news_items, ensure_ascii=False)

@mcp.tool()
def get_top_gainers(market: str = "KR", limit: int = 5) -> str:
    """급등 주식 목록을 조회합니다.
    
    Args:
        market: 시장 (KR/US/ALL)
        limit: 가져올 종목 수
    """
    # 기존 screen_stocks 함수 재사용
    stocks = screen_stocks(market)
    
    # 상위 limit개만 반환
    top_stocks = stocks[:limit]
    
    import json
    return json.dumps(top_stocks, ensure_ascii=False)

if __name__ == "__main__":
    mcp.run()
