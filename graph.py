"""LangGraph StateGraph 정의: 데이터 수집 + 내러티브 생성 + 최종 조립 파이프라인.

노드 흐름 (22개):
  START → [라우터: input_path 유무]
    ├─ 파일 로드: load_curated_context → run_page_purpose ...
    └─ 데이터 수집: crawl_news → crawl_research → screen_stocks
        → summarize_news → summarize_research → curate_topics
        → build_curated_context → run_page_purpose ...
  ... → run_page_purpose → run_historical_case → run_narrative_body
    → validate_interface2
    → run_theme → run_pages → run_hallcheck_pages
    → run_glossary → run_hallcheck_glossary → run_tone_final
    → run_chart_agent → run_hallcheck_chart
    → collect_sources → assemble_output → END
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
    run_theme_node,
    run_pages_node,
    run_hallcheck_pages_node,
    run_glossary_node,
    run_hallcheck_glossary_node,
    run_tone_final_node,
    collect_sources_node,
    assemble_output_node,
)
from .nodes.chart_agent import run_chart_agent_node, run_hallcheck_chart_node
from .nodes.screening import screen_stocks_node


def merge_metrics(a: dict, b: dict) -> dict:
    """메트릭 병합 (기존 값 + 새로운 값)."""
    if not a:
        a = {}
    if not b:
        b = {}
    return {**a, **b}


def merge_list(a: Optional[list], b: Optional[list]) -> list:
    """리스트 병합 (중복 제거 포함)."""
    # LangGraph는 a가 None일 수 있습니다.
    res = list(a or [])
    for item in (b or []):
        if item not in res:
            res.append(item)
    return res


def merge_last(a: Any, b: Any) -> Any:
    """마지막 값 선택 (병렬 노드 충돌 시 나중 것 선택)."""
    return b if b is not None else a


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
    i3_theme: Optional[dict]
    i3_pages: Optional[list]
    i3_validated: Optional[dict]
    i3_glossaries: Optional[list]
    i3_glossary_search_context: Optional[str]
    i3_validated_glossaries: Optional[list]
    charts: Optional[dict]
    pages: Optional[list]
    sources: Annotated[list, merge_list]
    hallucination_checklist: Annotated[list, merge_list]
    theme: Optional[str]
    one_liner: Optional[str]

    # 최종 출력
    full_output: Optional[dict]
    output_path: Optional[str]

    # 메타
    error: Annotated[Optional[str], merge_last]
    metrics: Annotated[dict, merge_metrics]





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


def check_join_readiness(state: BriefingPipelineState) -> str:
    """Interface 3 병렬 브랜치(Glossary, Chart) 종료 확인."""
    metrics = state.get("metrics", {})
    
    # 두 브랜치의 마지막 노드가 모두 완료되었는지 확인
    # run_hallcheck_glossary 완료 여부
    glossary_done = "run_hallcheck_glossary" in metrics
    
    # run_hallcheck_chart 완료 여부
    # chart_agent가 실행되지 않는 경우(차트 필요 없음)도 고려해야 하므로
    # metrics에 기록된 것으로 판단하거나, i3_validated_glossaries와 charts 유무로 판단.
    # 하지만 가장 확실한 건 metrics에 기록된 노드 이름.
    chart_done = "run_hallcheck_chart" in metrics

    if glossary_done and chart_done:
        return "ready"
    return "wait"


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

    # Interface 3 (10노드 순차)
    graph.add_node("run_theme", run_theme_node)
    graph.add_node("run_pages", run_pages_node)
    graph.add_node("run_hallcheck_pages", run_hallcheck_pages_node)
    graph.add_node("run_glossary", run_glossary_node)
    graph.add_node("run_hallcheck_glossary", run_hallcheck_glossary_node)
    graph.add_node("run_tone_final", run_tone_final_node)
    graph.add_node("run_chart_agent", run_chart_agent_node)
    graph.add_node("run_hallcheck_chart", run_hallcheck_chart_node)
    graph.add_node("collect_sources", collect_sources_node)
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

    # Interface 2 → Interface 3 (Parallel Execution)
    graph.add_conditional_edges(
        "validate_interface2",
        check_error,
        {"continue": "run_theme", "end": END},
    )
    graph.add_edge("run_theme", "run_pages")

    # Branch 1. Hallucination Check -> Glossary -> HallCheck Glossary
    graph.add_edge("run_pages", "run_hallcheck_pages")
    graph.add_edge("run_hallcheck_pages", "run_glossary")
    graph.add_edge("run_glossary", "run_hallcheck_glossary")

    # Branch 2. Chart Generation -> HallCheck Chart
    graph.add_edge("run_pages", "run_chart_agent")
    graph.add_edge("run_chart_agent", "run_hallcheck_chart")

    # Convergence: Branch 1 & 2가 모두 끝나면 Tone Final로 모임 (Join Pattern)
    # 두 브랜치 중 마지막에 끝나는 쪽만 run_tone_final을 호출하도록 함.
    graph.add_conditional_edges(
        "run_hallcheck_glossary",
        check_join_readiness,
        {"ready": "run_tone_final", "wait": END}
    )
    graph.add_conditional_edges(
        "run_hallcheck_chart",
        check_join_readiness,
        {"ready": "run_tone_final", "wait": END}
    )

    graph.add_edge("run_tone_final", "collect_sources")
    graph.add_edge("collect_sources", "assemble_output")
    graph.add_edge("assemble_output", END)

    return graph.compile()
