"""LangGraph StateGraph 정의: 3개 인터페이스를 연결하는 브리핑 파이프라인.

datapipeline/scripts/keyword_pipeline_graph.py 패턴을 따른다.

노드 흐름:
  START → load_curated_context
    → run_page_purpose → run_historical_case → run_narrative_body
    → validate_interface2
    → [병렬] build_charts + build_glossary
    → assemble_pages → collect_sources → run_final_check
    → assemble_output → END
"""

from __future__ import annotations

from typing import Annotated, Any, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

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


# ── State 정의 ──

class BriefingPipelineState(TypedDict):
    """파이프라인 전체 상태."""

    # 입력
    input_path: Optional[str]
    topic_index: int
    backend: str  # "live" | "mock"

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

def check_error(state: BriefingPipelineState) -> str:
    """에러가 있으면 END로 라우팅."""
    if state.get("error"):
        return "end"
    return "continue"


# ── 그래프 빌더 ──

def build_graph() -> Any:
    """브리핑 파이프라인 LangGraph 컴파일."""
    graph = StateGraph(BriefingPipelineState)

    # Interface 1
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

    # START → Interface 1
    graph.add_edge(START, "load_curated_context")
    graph.add_conditional_edges(
        "load_curated_context",
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

    # Interface 2 → Interface 3: 순차 실행 (charts → glossary → assemble)
    # NOTE: LangGraph 병렬 실행은 fan-out 패턴이 필요.
    #       단순화를 위해 순차 실행으로 구현. 향후 병렬화 가능.
    graph.add_conditional_edges(
        "validate_interface2",
        check_error,
        {"continue": "build_charts", "end": END},
    )
    graph.add_edge("build_charts", "build_glossary")
    graph.add_edge("build_glossary", "assemble_pages")

    # assemble_pages → collect_sources → run_final_check → assemble_output
    graph.add_edge("assemble_pages", "collect_sources")
    graph.add_edge("collect_sources", "run_final_check")
    graph.add_edge("run_final_check", "assemble_output")
    graph.add_edge("assemble_output", END)

    return graph.compile()
