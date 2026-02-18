"""Interface MCP Client.

MCP 도구를 호출하는 클라이언트 헬퍼입니다.
현재 단계에서는 로컬 함수를 직접 호출하는 방식으로 MCP 통신을 시뮬레이션합니다.
추후 실제 MCP Client 연결 코드로 교체될 예정입니다.
"""

import json
import logging
from typing import Any, Dict, List, Optional

# 실제 MCP 통신 대신 로컬 서버 인스턴스 import (Simulation)
from .mcp_server import search_news, get_top_gainers

logger = logging.getLogger(__name__)

def call_mcp_tool(tool_name: str, arguments: Dict[str, Any]) -> Any:
    """MCP 도구를 호출합니다 (Simulated).
    
    Args:
        tool_name: 호출할 도구 이름 (search_news, get_top_gainers)
        arguments: 도구 인자 딕셔너리
    
    Returns:
        도구 실행 결과 (파싱된 Python 객체)
    """
    logger.info(f"[MCP Call] {tool_name} with args: {arguments}")
    
    try:
        if tool_name == "search_news":
            # 인자 매핑
            query = arguments.get("query", "")
            market = arguments.get("market", "KR")
            result_json = search_news(query=query, market=market)
            return json.loads(result_json)
            
        elif tool_name == "get_top_gainers":
            market = arguments.get("market", "KR")
            limit = arguments.get("limit", 5)
            result_json = get_top_gainers(market=market, limit=limit)
            return json.loads(result_json)
            
        else:
            raise ValueError(f"Unknown tool: {tool_name}")
            
    except Exception as e:
        logger.error(f"[MCP Error] {tool_name} failed: {e}")
        return []

