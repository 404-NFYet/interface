"""Interface 2 노드: 4단계 내러티브 생성 파이프라인.

generate_interface2.py의 4단계 로직을 LangGraph 노드로 분리:
1. page_purpose → theme, one_liner, concept
2. historical_case → 과거 사례 매칭
3. narrative_body → 6단계 내러티브 본문
4. validate_interface2 → 할루시네이션 체크 + 조립
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from langsmith import traceable

from ..ai.llm_utils import call_llm_with_prompt
from ..schemas import RawNarrative

logger = logging.getLogger(__name__)


def _update_metrics(state: dict, node_name: str, elapsed: float, status: str = "success") -> dict:
    """메트릭 업데이트 (Partial Update for Reducer)."""
    return {
        node_name: {
            "elapsed_s": round(elapsed, 2),
            "status": status
        }
    }


# ── Mock 함수들 (테스트용) ──

def _mock_page_purpose(curated: dict) -> dict:
    return {
        "theme": curated.get("theme", "핵심 산업 내 구조적 전환 국면"),
        "one_liner": curated.get("one_liner", "핵심 지표가 개선되는데 왜 주가는 아직 반응하지 못할까요?"),
        "concept": curated.get("concept", {
            "name": "핵심 산업 사이클",
            "definition": "수요와 공급의 엇갈림으로 상승과 하락이 반복되는 주기예요.",
            "relevance": "현재는 기존 수요 둔화와 신수요 확장이 동시에 나타나는 전환점이에요.",
        }),
    }


def _mock_historical_case(curated: dict, pp: dict) -> dict:
    concept_name = pp.get("concept", {}).get("name", "사이클")
    return {
        "historical_case": {
            "period": "과거 유사 사이클 구간",
            "title": f"{concept_name} 조정기와 회복기 전환 사례",
            "summary": "수요 급증 이후 공급이 빠르게 늘며 재고가 쌓였고, 가격 하락이 이어졌어요.",
            "outcome": "바닥 신호가 먼저 나타나도 시장은 추가 확인을 요구해서 반등이 지연될 수 있었어요.",
            "lesson": "재고 감소는 선행 신호이고 가격 반등은 후행 신호라는 시차를 분리해서 봐야 해요.",
        }
    }


def _mock_narrative(curated: dict, pp: dict, hc: dict) -> dict:
    stock_names = [
        s.get("name") for s in curated.get("selected_stocks", [])
        if isinstance(s, dict) and s.get("name")
    ]
    stock_label = " vs ".join(stock_names[:2]) if stock_names else "관련 기업들"

    return {
        "narrative": {
            "background": {
                "purpose": "독자의 주의를 환기하고 지금 읽어야 하는 이유를 제시",
                "content": f"최근 {stock_label}의 흐름이 크게 엇갈리면서 시장의 혼란이 커졌어요.",
                "bullets": ["업황 개선 신호와 주가 반응 사이의 괴리", "기업별 수혜 강도 차이 확대"],
                "viz_hint": f"line - {stock_label} 최근 주가 추이",
            },
            "concept_explain": {
                "purpose": "핵심 개념을 쉽게 설명하고 현재 맥락과 연결",
                "content": f"{pp['concept']['definition']}",
                "bullets": ["사이클은 선행지표와 후행지표의 시간차가 커요", "동일 산업 내에서도 제품군별 국면이 다를 수 있어요"],
                "viz_hint": None,
            },
            "history": {
                "purpose": "과거 메커니즘을 통해 현재 패턴 해석",
                "content": "과거 사례에서도 재고 감소와 가격 반등 사이에 시차가 있었어요.",
                "bullets": ["재고 지표 개선이 먼저 나타났어요", "가격과 실적 확인 후 주가 반응이 본격화됐어요"],
                "viz_hint": "dual_line - 재고 지표 vs 가격/주가",
            },
            "application": {
                "purpose": "과거 교훈을 현재 상황에 적용",
                "content": "현재도 재고 조정의 진전이라는 닮은 점이 있지만, 고부가 제품 경쟁력이라는 변수가 더 크게 작동하고 있어요.",
                "bullets": ["닮은 점: 재고 조정 진행", "다른 점: 고부가 제품 주도권 경쟁"],
                "viz_hint": "grouped_bar - 제품군별 매출 비중 비교",
            },
            "caution": {
                "purpose": "반대 시나리오와 리스크 균형 제시",
                "content": "바닥 신호가 나와도 반등 시점은 늦어질 수 있어요.",
                "bullets": [
                    "재고 감소만으로 가격 반등을 단정하기 어려워요",
                    "핵심 제품 품질/고객 인증 일정이 변수예요",
                    "대외 규제 강화는 추가 하방 리스크예요",
                ],
                "viz_hint": None,
            },
            "summary": {
                "purpose": "핵심 요약과 관찰 포인트 제시",
                "content": "핵심은 재고, 가격, 경쟁력 지표의 순서를 구분해서 보는 거예요.",
                "bullets": ["재고 지표의 연속 개선 여부", "가격 반등의 지속성", "핵심 고객/제품 경쟁력 이벤트"],
                "viz_hint": "horizontal_bar - 관찰 지표 우선순위",
            },
        }
    }


def _mock_hallucination_check(pp: dict, hc: dict, narr: dict) -> dict:
    return {
        "overall_risk": "low",
        "summary": "mock 모드 결과예요. 실제 사실성 검증은 수행하지 않았어요.",
        "issues": [],
        "consistency_checks": [],
        "validated_interface_2": {
            "theme": pp["theme"],
            "one_liner": pp["one_liner"],
            "concept": pp["concept"],
            "historical_case": hc.get("historical_case", hc),
            "narrative": narr.get("narrative", narr),
        },
    }


# ── LangGraph 노드들 ──

@traceable(name="run_page_purpose", run_type="llm",
           metadata={"phase": "interface_2", "phase_name": "내러티브 생성", "step": 1})
def run_page_purpose_node(state: dict) -> dict:
    """Stage 1: theme, one_liner, concept 추출."""
    if state.get("error"):
        return {"error": state["error"]}

    node_start = time.time()
    logger.info("[Node] run_page_purpose")

    try:
        curated = state["curated_context"]
        backend = state.get("backend", "live")

        if backend == "mock":
            result = _mock_page_purpose(curated)
        else:
            result = call_llm_with_prompt("page_purpose", {
                "curated_context": curated,
            })

        logger.info("  page_purpose 완료: theme=%s", result.get("theme", "")[:50])
        return {
            "page_purpose": result,
            "metrics": _update_metrics(state, "run_page_purpose", time.time() - node_start),
        }

    except Exception as e:
        logger.error("  page_purpose 실패: %s", e)
        return {
            "error": f"page_purpose 실패: {e}",
            "metrics": _update_metrics(state, "run_page_purpose", time.time() - node_start, "failed"),
        }


@traceable(name="run_historical_case", run_type="llm",
           metadata={"phase": "interface_2", "phase_name": "내러티브 생성", "step": 2})
def run_historical_case_node(state: dict) -> dict:
    """Stage 2: 과거 사례 매칭."""
    if state.get("error"):
        return {"error": state["error"]}

    node_start = time.time()
    logger.info("[Node] run_historical_case")

    try:
        pp = state["page_purpose"]
        curated = state["curated_context"]
        backend = state.get("backend", "live")

        if backend == "mock":
            result = _mock_historical_case(curated, pp)
        else:
            result = call_llm_with_prompt("historical_case", {
                "theme": pp["theme"],
                "one_liner": pp["one_liner"],
                "concept": pp["concept"],
                "curated_context": curated,
            })

        logger.info("  historical_case 완료")
        return {
            "historical_case": result,
            "metrics": _update_metrics(state, "run_historical_case", time.time() - node_start),
        }

    except Exception as e:
        logger.error("  historical_case 실패: %s", e)
        return {
            "error": f"historical_case 실패: {e}",
            "metrics": _update_metrics(state, "run_historical_case", time.time() - node_start, "failed"),
        }


@traceable(name="run_narrative_body", run_type="llm",
           metadata={"phase": "interface_2", "phase_name": "내러티브 생성", "step": 3})
def run_narrative_body_node(state: dict) -> dict:
    """Stage 3: 6단계 내러티브 본문 생성."""
    if state.get("error"):
        return {"error": state["error"]}

    node_start = time.time()
    logger.info("[Node] run_narrative_body")

    try:
        pp = state["page_purpose"]
        hc = state["historical_case"]
        curated = state["curated_context"]
        backend = state.get("backend", "live")

        if backend == "mock":
            result = _mock_narrative(curated, pp, hc)
        else:
            result = call_llm_with_prompt("narrative_body", {
                "theme": pp["theme"],
                "one_liner": pp["one_liner"],
                "concept": pp["concept"],
                "historical_case": hc.get("historical_case", hc),
                "curated_context": curated,
            })

        logger.info("  narrative_body 완료")
        return {
            "narrative": result,
            "metrics": _update_metrics(state, "run_narrative_body", time.time() - node_start),
        }

    except Exception as e:
        logger.error("  narrative_body 실패: %s", e)
        return {
            "error": f"narrative_body 실패: {e}",
            "metrics": _update_metrics(state, "run_narrative_body", time.time() - node_start, "failed"),
        }


@traceable(name="validate_interface2", run_type="llm",
           metadata={"phase": "interface_2", "phase_name": "내러티브 생성", "step": 4})
def validate_interface2_node(state: dict) -> dict:
    """Stage 4: 할루시네이션 체크 + interface2 조립."""
    if state.get("error"):
        return {"error": state["error"]}

    node_start = time.time()
    logger.info("[Node] validate_interface2")

    try:
        pp = state["page_purpose"]
        hc = state["historical_case"]
        narr = state["narrative"]
        curated = state["curated_context"]
        backend = state.get("backend", "live")

        if backend == "mock":
            result = _mock_hallucination_check(pp, hc, narr)
        else:
            result = call_llm_with_prompt("hallucination_check", {
                "curated_context": curated,
                "page_purpose_output": pp,
                "historical_case_output": hc,
                "narrative_output": narr,
            })

        # validated_interface_2 추출
        validated = result.get("validated_interface_2", {
            "theme": pp["theme"],
            "one_liner": pp["one_liner"],
            "concept": pp["concept"],
            "historical_case": hc.get("historical_case", hc),
            "narrative": narr.get("narrative", narr),
        })

        # Pydantic 검증
        raw_narr = RawNarrative.model_validate(validated)
        logger.info("  validate_interface2 완료: overall_risk=%s", result.get("overall_risk"))

        return {
            "raw_narrative": raw_narr.model_dump(),
            "metrics": _update_metrics(state, "validate_interface2", time.time() - node_start),
        }

    except Exception as e:
        logger.error("  validate_interface2 실패: %s", e)
        return {
            "error": f"validate_interface2 실패: {e}",
            "metrics": _update_metrics(state, "validate_interface2", time.time() - node_start, "failed"),
        }
