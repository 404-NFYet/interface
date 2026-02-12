"""LangGraph StateGraph 정의: 데이터 수집 + 내러티브 생성 + 최종 조립 파이프라인.

노드 흐름:
  START → [라우터: input_path 유무]
    ├─ 파일 로드: load_curated_context → run_page_purpose ...
    └─ 데이터 수집: crawl_news → crawl_research → screen_stocks
        → summarize_news → summarize_research → curate_topics
        → build_curated_context → run_page_purpose ...
  ... → run_page_purpose → run_historical_case → run_narrative_body
    → validate_interface2
    → build_charts → build_glossary
    → assemble_pages → collect_sources → run_final_check
    → assemble_output → END
"""

from __future__ import annotations

from typing import Annotated, Any, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from .nodes.crawlers import crawl_news_node, crawl_research_node
from .nodes.curation import (
    build_curated_context_node,
    curate_topics_node,
    summarize_news_node,
    summarize_research_node,
)
from .nodes.interface1 import load_curated_context_node
from .nodes.interface2 import (
    run_historical_case_node,
    run_narrative_body_node,
    run_page_purpose_node,
    validate_interface2_node,
)
from .nodes.interface3 import (
    assemble_output_node,
    assemble_pages_node,
    build_charts_node,
    build_glossary_node,
    collect_sources_node,
    run_final_check_node,
)
from .nodes.screening import screen_stocks_node


# ── State 정의 ──

class BriefingPipelineState(TypedDict):
    """파이프라인 전체 상태."""

    # 입력
    input_path: Optional[str]     # None이면 데이터 수집 모드
    topic_index: int
    backend: str                  # "live" | "mock"
    market: str                   # "KR" | "US" | "ALL"

    # Data Collection 중간 결과
    raw_news: Optional[list]
    raw_reports: Optional[list]
    screened_stocks: Optional[list]
    matched_stocks: Optional[list]
    news_summary: Optional[str]
    research_summary: Optional[str]
    curated_topics: Optional[list]
    websearch_log: Optional[dict]

    # Interface 1 출력
    curated_context: Optional[dict]

    # Interface 2 중간 결과
    page_purpose: Optional[dict]
    historical_case: Optional[dict]
    narrative: Optional[dict]
    raw_narrative: Optional[dict]

    # Interface 3 중간 결과
    charts: Optional[dict]
    glossaries: Optional[dict]
    pages: Optional[list]
    sources: Optional[list]
    hallucination_checklist: Optional[list]

    # 최종 출력
    full_output: Optional[dict]
    output_path: Optional[str]

    # 메타
    error: Optional[str]
    metrics: Annotated[dict, lambda a, b: {**a, **b}]


# ── 조건부 라우팅 ──

def route_data_source(state: BriefingPipelineState) -> str:
    """input_path 유무로 데이터 소스 결정."""
    if state.get("input_path"):
        return "load_from_file"
    return "collect_data"


def check_error(state: BriefingPipelineState) -> str:
    """에러가 있으면 END로 라우팅."""
    if state.get("error"):
        return "end"
    return "continue"


# ── 그래프 빌더 ──

def build_graph() -> Any:
    """브리핑 파이프라인 LangGraph 컴파일."""
    graph = StateGraph(BriefingPipelineState)

    # Data Collection 노드 (7개)
    graph.add_node("crawl_news", crawl_news_node)
    graph.add_node("crawl_research", crawl_research_node)
    graph.add_node("screen_stocks", screen_stocks_node)
    graph.add_node("summarize_news", summarize_news_node)
    graph.add_node("summarize_research", summarize_research_node)
    graph.add_node("curate_topics", curate_topics_node)
    graph.add_node("build_curated_context", build_curated_context_node)

    # Interface 1 (파일 로드)
    graph.add_node("load_curated_context", load_curated_context_node)

    # Interface 2 (순차 4단계)
    graph.add_node("run_page_purpose", run_page_purpose_node)
    graph.add_node("run_historical_case", run_historical_case_node)
    graph.add_node("run_narrative_body", run_narrative_body_node)
    graph.add_node("validate_interface2", validate_interface2_node)

    # Interface 3
    graph.add_node("build_charts", build_charts_node)
    graph.add_node("build_glossary", build_glossary_node)
    graph.add_node("assemble_pages", assemble_pages_node)
    graph.add_node("collect_sources", collect_sources_node)
    graph.add_node("run_final_check", run_final_check_node)
    graph.add_node("assemble_output", assemble_output_node)

    # ── 엣지 ──

    # START → 라우터
    graph.add_conditional_edges(START, route_data_source, {
        "load_from_file": "load_curated_context",
        "collect_data": "crawl_news",
    })

    # 파일 로드 → Interface 2
    graph.add_conditional_edges(
        "load_curated_context",
        check_error,
        {"continue": "run_page_purpose", "end": END},
    )

    # 데이터 수집 체인 (순차)
    graph.add_edge("crawl_news", "crawl_research")
    graph.add_edge("crawl_research", "screen_stocks")
    graph.add_conditional_edges(
        "screen_stocks",
        check_error,
        {"continue": "summarize_news", "end": END},
    )
    graph.add_edge("summarize_news", "summarize_research")
    graph.add_edge("summarize_research", "curate_topics")
    graph.add_conditional_edges(
        "curate_topics",
        check_error,
        {"continue": "build_curated_context", "end": END},
    )
    graph.add_conditional_edges(
        "build_curated_context",
        check_error,
        {"continue": "run_page_purpose", "end": END},
    )

    # Interface 2: 순차 실행
    graph.add_conditional_edges(
        "run_page_purpose",
        check_error,
        {"continue": "run_historical_case", "end": END},
    )
    graph.add_conditional_edges(
        "run_historical_case",
        check_error,
        {"continue": "run_narrative_body", "end": END},
    )
    graph.add_conditional_edges(
        "run_narrative_body",
        check_error,
        {"continue": "validate_interface2", "end": END},
    )

    # Interface 2 → Interface 3
    graph.add_conditional_edges(
        "validate_interface2",
        check_error,
        {"continue": "build_charts", "end": END},
    )
    graph.add_edge("build_charts", "build_glossary")
    graph.add_edge("build_glossary", "assemble_pages")

    # assemble → collect → final_check → output
    graph.add_edge("assemble_pages", "collect_sources")
    graph.add_edge("collect_sources", "run_final_check")
    graph.add_edge("run_final_check", "assemble_output")
    graph.add_edge("assemble_output", END)

    return graph.compile()
