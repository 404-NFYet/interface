"""Interface 3 노드: 차트 생성, 용어사전, 페이지 조립, 출처 수집, 최종 검증.

viz_hint → Plotly JSON 변환, glossary 생성, 6페이지 조립, 출처 수집을 수행한다.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime
from typing import Any

from langsmith import traceable

from ..ai.llm_utils import call_llm_with_prompt
from ..config import COLOR_PALETTE, OUTPUT_DIR
from ..schemas import (
    CuratedContext,
    FinalBriefing,
    FullBriefingOutput,
    RawNarrative,
)

logger = logging.getLogger(__name__)

SECTION_MAP = [
    (1, "현재 배경", "background"),
    (2, "금융 개념 설명", "concept_explain"),
    (3, "과거 비슷한 사례", "history"),
    (4, "현재 상황에 적용", "application"),
    (5, "주의해야 할 점", "caution"),
    (6, "최종 정리", "summary"),
]


def _update_metrics(state: dict, node_name: str, elapsed: float, status: str = "success") -> dict:
    metrics = dict(state.get("metrics") or {})
    metrics[node_name] = {"elapsed_s": round(elapsed, 2), "status": status}
    return metrics


# ── Mock 함수들 ──

def _mock_chart(section_key: str, viz_hint: str | None) -> dict | None:
    """mock 모드 차트 — 최소한의 Plotly 구조."""
    if not viz_hint:
        return None
    return {
        "data": [{"x": ["A", "B", "C"], "y": [1, 2, 3], "type": "bar", "name": f"mock-{section_key}"}],
        "layout": {"title": f"[Mock] {viz_hint}"},
    }


_STOPWORDS = frozenset({
    "하는", "있는", "이는", "했다", "한다", "되는", "이다", "에서", "으로", "부터",
    "까지", "하고", "그리고", "또한", "하며", "위해", "대한", "통해", "따르", "관련",
    "지난", "오전", "오후", "현재", "기준", "대비", "전날", "거래", "거래일",
})


def _extract_keywords(text: str) -> list[str]:
    """텍스트에서 핵심 키워드(2글자 이상 한글 단어) 추출."""
    words = re.findall(r"[가-힣]{2,}", text)
    return [w for w in words if w not in _STOPWORDS and len(w) >= 2]


def _mock_glossary(section_key: str, content: str) -> list[dict]:
    """mock 모드 용어사전."""
    return [
        {"term": f"용어-{section_key}", "definition": "mock 모드 정의예요.", "domain": "일반"}
    ]


# ── LangGraph 노드들 ──

@traceable(name="build_charts", run_type="llm",
           metadata={"phase": "interface_3", "phase_name": "최종 조립", "step": 1})
def build_charts_node(state: dict) -> dict:
    """viz_hint → Plotly JSON 변환."""
    if state.get("error"):
        return {"error": state["error"]}

    node_start = time.time()
    logger.info("[Node] build_charts")

    try:
        raw = state["raw_narrative"]
        curated = state["curated_context"]
        narrative = raw["narrative"]
        backend = state.get("backend", "live")

        charts: dict[str, Any] = {}
        previous_charts_summary: list[str] = []

        for _, _, section_key in SECTION_MAP:
            section = narrative[section_key]
            viz_hint = section.get("viz_hint")

            if not viz_hint:
                charts[section_key] = None
                continue

            if backend == "mock":
                charts[section_key] = _mock_chart(section_key, viz_hint)
            else:
                result = call_llm_with_prompt("chart_generation", {
                    "viz_hint": viz_hint,
                    "section_key": section_key,
                    "content": section["content"],
                    "bullets": section["bullets"],
                    "stocks": curated.get("selected_stocks", []),
                    "news": curated.get("verified_news", []),
                    "color_palette": COLOR_PALETTE,
                    "previous_charts": "\n".join(previous_charts_summary) or "없음",
                })
                charts[section_key] = result

            # 이전 차트 요약 누적 (다음 차트 생성 시 중복 방지)
            if charts.get(section_key):
                chart = charts[section_key]
                chart_type = chart.get("data", [{}])[0].get("type", "unknown")
                chart_title = chart.get("layout", {}).get("title", "")
                previous_charts_summary.append(
                    f"- {section_key}: type={chart_type}, title={chart_title}"
                )

        logger.info("  build_charts 완료: %d 차트 생성", sum(1 for v in charts.values() if v))
        return {
            "charts": charts,
            "metrics": _update_metrics(state, "build_charts", time.time() - node_start),
        }

    except Exception as e:
        logger.error("  build_charts 실패: %s", e)
        return {
            "error": f"build_charts 실패: {e}",
            "metrics": _update_metrics(state, "build_charts", time.time() - node_start, "failed"),
        }


@traceable(name="build_glossary", run_type="llm",
           metadata={"phase": "interface_3", "phase_name": "최종 조립", "step": 2})
def build_glossary_node(state: dict) -> dict:
    """페이지별 용어사전 생성."""
    if state.get("error"):
        return {"error": state["error"]}

    node_start = time.time()
    logger.info("[Node] build_glossary")

    try:
        raw = state["raw_narrative"]
        narrative = raw["narrative"]
        backend = state.get("backend", "live")

        glossaries: dict[str, list] = {}
        seen_terms: set[str] = set()

        for _, _, section_key in SECTION_MAP:
            section = narrative[section_key]

            if backend == "mock":
                items = _mock_glossary(section_key, section["content"])
            else:
                result = call_llm_with_prompt("glossary_generation", {
                    "section_key": section_key,
                    "content": section["content"],
                    "bullets": section["bullets"],
                    "existing_terms": list(seen_terms),
                })
                items = result.get("glossary", [])

            # 중복 제거
            filtered = []
            for item in items:
                term = item.get("term", "")
                if term and term not in seen_terms:
                    seen_terms.add(term)
                    filtered.append(item)
            glossaries[section_key] = filtered

        logger.info("  build_glossary 완료: 총 %d 용어", len(seen_terms))
        return {
            "glossaries": glossaries,
            "metrics": _update_metrics(state, "build_glossary", time.time() - node_start),
        }

    except Exception as e:
        logger.error("  build_glossary 실패: %s", e)
        return {
            "error": f"build_glossary 실패: {e}",
            "metrics": _update_metrics(state, "build_glossary", time.time() - node_start, "failed"),
        }


@traceable(name="assemble_pages", run_type="tool",
           metadata={"phase": "interface_3", "phase_name": "최종 조립", "step": 3})
def assemble_pages_node(state: dict) -> dict:
    """6페이지 조립 (결정론적)."""
    if state.get("error"):
        return {"error": state["error"]}

    node_start = time.time()
    logger.info("[Node] assemble_pages")

    try:
        raw = state["raw_narrative"]
        narrative = raw["narrative"]
        charts = state.get("charts", {})
        glossaries = state.get("glossaries", {})

        pages = []
        for step, title, section_key in SECTION_MAP:
            section = narrative[section_key]
            page = {
                "step": step,
                "title": title,
                "purpose": section["purpose"],
                "content": section["content"],
                "bullets": section["bullets"],
                "chart": charts.get(section_key),
                "glossary": glossaries.get(section_key, []),
            }
            pages.append(page)

        logger.info("  assemble_pages 완료: %d pages", len(pages))
        return {
            "pages": pages,
            "metrics": _update_metrics(state, "assemble_pages", time.time() - node_start),
        }

    except Exception as e:
        logger.error("  assemble_pages 실패: %s", e)
        return {
            "error": f"assemble_pages 실패: {e}",
            "metrics": _update_metrics(state, "assemble_pages", time.time() - node_start, "failed"),
        }


@traceable(name="collect_sources", run_type="tool",
           metadata={"phase": "interface_3", "phase_name": "최종 조립", "step": 4})
def collect_sources_node(state: dict) -> dict:
    """출처 수집 (결정론적)."""
    if state.get("error"):
        return {"error": state["error"]}

    node_start = time.time()
    logger.info("[Node] collect_sources")

    try:
        curated = state["curated_context"]
        pages = state["pages"]

        # verified_news에서 출처 추출
        source_map: dict[str, dict] = {}
        for news in curated.get("verified_news", []):
            url = news.get("url", "")
            source_name = news.get("source", "")
            # 도메인 추출
            domain = url.split("//")[-1].split("/")[0] if "//" in url else url.split("/")[0]
            domain = domain.replace("www.", "")

            if source_name not in source_map:
                source_map[source_name] = {
                    "name": source_name,
                    "url_domain": domain,
                    "used_in_pages": [],
                }

        # 리포트에서 출처 추출
        for report in curated.get("reports", []):
            source_name = report.get("source", "")
            if source_name and source_name not in source_map:
                source_map[source_name] = {
                    "name": source_name,
                    "url_domain": "",
                    "used_in_pages": [],
                }

        # 소스별 키워드 추출 (뉴스 제목/요약에서)
        source_keywords: dict[str, list[str]] = {}
        for news in curated.get("verified_news", []):
            sname = news.get("source", "")
            text = f"{news.get('title', '')} {news.get('summary', '')}"
            kws = _extract_keywords(text)
            if sname not in source_keywords:
                source_keywords[sname] = []
            source_keywords[sname].extend(kws)

        for report in curated.get("reports", []):
            sname = report.get("source", "")
            text = f"{report.get('title', '')} {report.get('summary', '')}"
            kws = _extract_keywords(text)
            if sname not in source_keywords:
                source_keywords[sname] = []
            source_keywords[sname].extend(kws)

        # 페이지별 출처 매칭 (키워드 기반)
        for page in pages:
            page_text = (
                page.get("content", "") + " " + " ".join(page.get("bullets", []))
            )
            for sname, sinfo in source_map.items():
                keywords = source_keywords.get(sname, [])
                # 키워드 중 2개 이상이 페이지에 등장하면 매칭
                match_count = sum(1 for kw in keywords if kw in page_text)
                if match_count >= 2:
                    if page["step"] not in sinfo["used_in_pages"]:
                        sinfo["used_in_pages"].append(page["step"])

        # used_in_pages가 비어있는 것도 포함 (최소 1페이지 배정)
        sources = list(source_map.values())
        for s in sources:
            if not s["used_in_pages"]:
                s["used_in_pages"] = [1]

        logger.info("  collect_sources 완료: %d sources", len(sources))
        return {
            "sources": sources,
            "metrics": _update_metrics(state, "collect_sources", time.time() - node_start),
        }

    except Exception as e:
        logger.error("  collect_sources 실패: %s", e)
        return {
            "error": f"collect_sources 실패: {e}",
            "metrics": _update_metrics(state, "collect_sources", time.time() - node_start, "failed"),
        }


@traceable(name="run_final_check", run_type="llm",
           metadata={"phase": "interface_3", "phase_name": "최종 조립", "step": 5})
def run_final_check_node(state: dict) -> dict:
    """최종 할루시네이션 체크리스트 생성."""
    if state.get("error"):
        return {"error": state["error"]}

    node_start = time.time()
    logger.info("[Node] run_final_check")

    try:
        curated = state["curated_context"]
        pages = state["pages"]
        backend = state.get("backend", "live")

        if backend == "mock":
            checklist = [
                {
                    "claim": "mock 모드 — 실제 검증 미수행",
                    "source": "mock",
                    "risk": "낮음",
                    "note": "실제 LLM 호출 시 검증이 수행됩니다.",
                }
            ]
        else:
            result = call_llm_with_prompt("final_hallucination", {
                "curated_context": curated,
                "pages": pages,
            })
            checklist = result.get("hallucination_checklist", [])

        logger.info("  run_final_check 완료: %d items", len(checklist))
        return {
            "hallucination_checklist": checklist,
            "metrics": _update_metrics(state, "run_final_check", time.time() - node_start),
        }

    except Exception as e:
        logger.error("  run_final_check 실패: %s", e)
        return {
            "error": f"run_final_check 실패: {e}",
            "metrics": _update_metrics(state, "run_final_check", time.time() - node_start, "failed"),
        }


@traceable(name="assemble_output", run_type="tool",
           metadata={"phase": "interface_3", "phase_name": "최종 조립", "step": 6})
def assemble_output_node(state: dict) -> dict:
    """최종 JSON 조립 + Pydantic 검증 + 파일 저장."""
    if state.get("error"):
        return {"error": state["error"]}

    node_start = time.time()
    logger.info("[Node] assemble_output")

    try:
        raw_narrative = state["raw_narrative"]
        curated = state["curated_context"]
        pages = state["pages"]
        sources = state.get("sources", [])
        checklist = state.get("hallucination_checklist", [])

        # FinalBriefing 조립
        final_briefing_data = {
            "theme": raw_narrative["theme"],
            "one_liner": raw_narrative["one_liner"],
            "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "pages": pages,
            "sources": sources,
            "hallucination_checklist": checklist,
        }

        # Pydantic 검증
        output = FullBriefingOutput(
            topic=raw_narrative["theme"],
            interface_1_curated_context=CuratedContext.model_validate(curated),
            interface_2_raw_narrative=RawNarrative.model_validate(raw_narrative),
            interface_3_final_briefing=FinalBriefing.model_validate(final_briefing_data),
        )

        # 파일 저장
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = OUTPUT_DIR / f"briefing_{timestamp}.json"
        output_path.write_text(
            output.model_dump_json(indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        logger.info("  assemble_output 완료: %s", output_path)
        return {
            "full_output": output.model_dump(),
            "output_path": str(output_path),
            "metrics": _update_metrics(state, "assemble_output", time.time() - node_start),
        }

    except Exception as e:
        logger.error("  assemble_output 실패: %s", e)
        return {
            "error": f"assemble_output 실패: {e}",
            "metrics": _update_metrics(state, "assemble_output", time.time() - node_start, "failed"),
        }
