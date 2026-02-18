"""Interface 3 노드: theme → pages → hallcheck → glossary → hallcheck → tone_final → sources → output.

viz 브랜치 아키텍처 + jihoon v11 프롬프트 기반 10노드 순차 파이프라인.
(chart_agent 2노드는 nodes/chart_agent.py에 별도 정의)
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
from ..config import COLOR_PALETTE, OUTPUT_DIR, SECTION_MAP
from ..schemas import (
    CuratedContext,
    FinalBriefing,
    FullBriefingOutput,
    RawNarrative,
)

logger = logging.getLogger(__name__)


def _update_metrics(state: dict, node_name: str, elapsed: float, status: str = "success") -> dict:
    """메트릭 업데이트 (Partial Update for Reducer)."""
    return {
        node_name: {
            "elapsed_s": round(elapsed, 2),
            "status": status
        }
    }


# ────────────────────────────────────────────
# 1. run_theme — refined theme + one_liner
# ────────────────────────────────────────────

@traceable(name="run_theme", run_type="llm",
           metadata={"phase": "interface_3", "phase_name": "테마 생성", "step": 1})
def run_theme_node(state: dict) -> dict:
    """validated_interface_2 → refined theme/one_liner."""
    if state.get("error"):
        return {"error": state["error"]}

    node_start = time.time()
    logger.info("[Node] run_theme")

    try:
        raw = state["raw_narrative"]
        backend = state.get("backend", "live")

        if backend == "mock":
            result = {"theme": raw["theme"], "one_liner": raw["one_liner"]}
        else:
            result = call_llm_with_prompt("3_theme", {
                "validated_interface_2": json.dumps(raw, ensure_ascii=False),
            })

        logger.info("  run_theme done: theme=%s", result.get("theme", "")[:50])
        return {
            "i3_theme": result,
            "metrics": _update_metrics(state, "run_theme", time.time() - node_start),
        }

    except Exception as e:
        logger.error("  run_theme failed: %s", e, exc_info=True)
        return {
            "error": f"run_theme failed: {e}",
            "metrics": _update_metrics(state, "run_theme", time.time() - node_start, "failed"),
        }


# ────────────────────────────────────────────
# 2. run_pages — 6 pages (no chart)
# ────────────────────────────────────────────

@traceable(name="run_pages", run_type="llm",
           metadata={"phase": "interface_3", "phase_name": "페이지 생성", "step": 2})
def run_pages_node(state: dict) -> dict:
    """validated_interface_2 → 6 pages."""
    if state.get("error"):
        return {"error": state["error"]}

    node_start = time.time()
    logger.info("[Node] run_pages")

    try:
        raw = state["raw_narrative"]
        backend = state.get("backend", "live")

        if backend == "mock":
            narrative = raw["narrative"]
            pages = []
            for step, title, section_key in SECTION_MAP:
                section = narrative[section_key]
                pages.append({
                    "step": step,
                    "title": title,
                    "purpose": section["purpose"],
                    "content": section["content"],
                    "bullets": section["bullets"][:2],
                })
            result = {"pages": pages}
        else:
            result = call_llm_with_prompt("3_pages", {
                "validated_interface_2": json.dumps(raw, ensure_ascii=False),
            })

        page_count = len(result.get("pages", []))
        logger.info("  run_pages done: %d pages", page_count)
        return {
            "i3_pages": result.get("pages", []),
            "metrics": _update_metrics(state, "run_pages", time.time() - node_start),
        }

    except Exception as e:
        logger.error("  run_pages failed: %s", e, exc_info=True)
        return {
            "error": f"run_pages failed: {e}",
            "metrics": _update_metrics(state, "run_pages", time.time() - node_start, "failed"),
        }


# ────────────────────────────────────────────
# 3. run_hallcheck_pages — corrective hallcheck
# ────────────────────────────────────────────

@traceable(name="run_hallcheck_pages", run_type="llm",
           metadata={"phase": "interface_3", "phase_name": "페이지 검증", "step": 3})
def run_hallcheck_pages_node(state: dict) -> dict:
    """theme + pages 검증 → validated_theme/one_liner/pages 반환."""
    if state.get("error"):
        return {"error": state["error"]}

    node_start = time.time()
    logger.info("[Node] run_hallcheck_pages")

    try:
        raw = state["raw_narrative"]
        i3_theme = state["i3_theme"]
        i3_pages = state["i3_pages"]
        backend = state.get("backend", "live")

        if backend == "mock":
            result = {
                "overall_risk": "low",
                "summary": "mock — 검증 미수행",
                "issues": [],
                "consistency_checks": [],
                "validated_theme": i3_theme.get("theme", raw["theme"]),
                "validated_one_liner": i3_theme.get("one_liner", raw["one_liner"]),
                "validated_pages": i3_pages,
            }
        else:
            result = call_llm_with_prompt("3_hallcheck_pages", {
                "validated_interface_2": json.dumps(raw, ensure_ascii=False),
                "theme_output": json.dumps(i3_theme, ensure_ascii=False),
                "pages_output": json.dumps(i3_pages, ensure_ascii=False),
            })

        risk = result.get("overall_risk", "unknown")
        issue_count = len(result.get("issues", []))
        logger.info("  run_hallcheck_pages done: risk=%s, issues=%d", risk, issue_count)

        return {
            "i3_validated": result,
            "metrics": _update_metrics(state, "run_hallcheck_pages", time.time() - node_start),
        }

    except Exception as e:
        logger.error("  run_hallcheck_pages failed: %s", e, exc_info=True)
        return {
            "error": f"run_hallcheck_pages failed: {e}",
            "metrics": _update_metrics(state, "run_hallcheck_pages", time.time() - node_start, "failed"),
        }


# ────────────────────────────────────────────
# 4. run_glossary — page_glossaries (with Search)
# ────────────────────────────────────────────

@traceable(name="run_glossary", run_type="chain",
           metadata={"phase": "interface_3", "phase_name": "용어 생성", "step": 4})
def run_glossary_node(state: dict) -> dict:
    """validated_pages → term extraction → search → page_glossaries."""
    if state.get("error"):
        return {"error": state["error"]}

    node_start = time.time()
    logger.info("[Node] run_glossary")

    try:
        raw = state["raw_narrative"]
        validated = state.get("i3_validated")
        if not validated:
            logger.warning("  run_glossary: i3_validated is None. Using raw i3_pages.")
            validated_pages = state.get("i3_pages", [])
        else:
            validated_pages = validated.get("validated_pages", [])
        backend = state.get("backend", "live")

        if backend == "mock":
            page_glossaries = []
            for step, _, section_key in SECTION_MAP:
                page_glossaries.append({
                    "step": step,
                    "glossary": [
                        {"term": f"용어-{section_key}", "definition": "mock 정의예요.", "domain": "일반"}
                    ],
                })
            return {
                "i3_glossaries": page_glossaries,
                "i3_glossary_search_context": "[Mock Search Results]",
                "metrics": _update_metrics(state, "run_glossary", time.time() - node_start),
            }

        # 1. Term Extraction
        extraction_result = call_llm_with_prompt("3_glossary_term_extraction", {
            "validated_pages": json.dumps(validated_pages, ensure_ascii=False),
        })
        terms_to_search = extraction_result.get("terms_to_search", [])
        logger.info(f"  Extracted {len(terms_to_search)} terms to search.")

        # 2. Web Search
        from ..ai.tools import search_web_for_chart_data
        
        search_results_text = ""
        if terms_to_search:
            # Deduplicate by term, keeping the first context found
            unique_terms_map = {}
            for item in terms_to_search:
                term = item.get("term")
                context = item.get("context_sentence", "")
                if term and term not in unique_terms_map:
                    unique_terms_map[term] = context

            logger.info(f"  Searching for: {list(unique_terms_map.keys())}")
            
            search_docs = []
            for term, context in unique_terms_map.items():
                try:
                    if context:
                        query = f"주식 용어 {term} 뜻 의미 (문맥: {context})"
                    else:
                        query = f"주식 용어 {term} 뜻 의미"
                    
                    search_output = search_web_for_chart_data.invoke(query)
                    search_docs.append(f"[{term}]\n(문맥: {context})\n{search_output}\n")
                except Exception as e:
                    logger.warning(f"  Search failed for {term}: {e}")
            
            search_results_text = "\n".join(search_docs)
        
        if not search_results_text:
            search_results_text = "(검색 결과 없음)"

        # 3. Glossary Generation
        result = call_llm_with_prompt("3_glossary", {
            "validated_interface_2": json.dumps(raw, ensure_ascii=False),
            "validated_pages": json.dumps(validated_pages, ensure_ascii=False),
            "search_results": search_results_text,
        })

        glossary_count = sum(
            len(pg.get("glossary", []))
            for pg in result.get("page_glossaries", [])
        )
        logger.info("  run_glossary done: %d terms across 6 pages", glossary_count)

        return {
            "i3_glossaries": result.get("page_glossaries", []),
            "i3_glossary_search_context": search_results_text,
            "metrics": _update_metrics(state, "run_glossary", time.time() - node_start),
        }

    except Exception as e:
        logger.error("  run_glossary failed: %s", e, exc_info=True)
        return {
            "error": f"run_glossary failed: {e}",
            "metrics": _update_metrics(state, "run_glossary", time.time() - node_start, "failed"),
        }


# ────────────────────────────────────────────
# 5. run_hallcheck_glossary — validated_page_glossaries
# ────────────────────────────────────────────

@traceable(name="run_hallcheck_glossary", run_type="llm",
           metadata={"phase": "interface_3", "phase_name": "용어 검증", "step": 5})
def run_hallcheck_glossary_node(state: dict) -> dict:
    """page_glossaries 검증 → validated_page_glossaries 반환."""
    if state.get("error"):
        return {"error": state["error"]}

    node_start = time.time()
    logger.info("[Node] run_hallcheck_glossary")

    try:
        raw = state["raw_narrative"]
        validated = state["i3_validated"]
        validated_pages = validated.get("validated_pages", [])
        i3_glossaries = state["i3_glossaries"]
        backend = state.get("backend", "live")

        if backend == "mock":
            result = {
                "overall_risk": "low",
                "summary": "mock — 검증 미수행",
                "issues": [],
                "validated_page_glossaries": i3_glossaries,
            }
        else:
            search_context = state.get("i3_glossary_search_context", "(검색 결과 없음)")
            result = call_llm_with_prompt("3_hallcheck_glossary", {
                "validated_interface_2": json.dumps(raw, ensure_ascii=False),
                "validated_pages": json.dumps(validated_pages, ensure_ascii=False),
                "page_glossaries": json.dumps(i3_glossaries, ensure_ascii=False),
                "search_results": search_context,
            })

        risk = result.get("overall_risk", "unknown")
        logger.info("  run_hallcheck_glossary done: risk=%s", risk)

        return {
            "i3_validated_glossaries": result.get("validated_page_glossaries", i3_glossaries),
            "metrics": _update_metrics(state, "run_hallcheck_glossary", time.time() - node_start),
        }

    except Exception as e:
        logger.error("  run_hallcheck_glossary failed: %s", e, exc_info=True)
        return {
            "error": f"run_hallcheck_glossary failed: {e}",
            "metrics": _update_metrics(state, "run_hallcheck_glossary", time.time() - node_start, "failed"),
        }


# ────────────────────────────────────────────
# 6. run_tone_final — merge pages + glossaries, tone correction
# ────────────────────────────────────────────

@traceable(name="run_tone_final", run_type="llm",
           metadata={"phase": "interface_3", "phase_name": "톤 보정", "step": 6})
def run_tone_final_node(state: dict) -> dict:
    """validated pages + glossaries → final merged pages with tone correction."""
    if state.get("error"):
        return {"error": state["error"]}

    node_start = time.time()
    logger.info("[Node] run_tone_final")

    try:
        validated = state["i3_validated"]
        validated_pages = validated.get("validated_pages", [])
        validated_theme = validated.get("validated_theme", "")
        validated_one_liner = validated.get("validated_one_liner", "")
        validated_glossaries = state["i3_validated_glossaries"]
        backend = state.get("backend", "live")

        if backend == "mock":
            # Simple merge without LLM
            glossary_map = {
                pg["step"]: pg.get("glossary", [])
                for pg in validated_glossaries
            }
            merged_pages = []
            for page in validated_pages:
                merged_page = dict(page)
                merged_page["glossary"] = glossary_map.get(page["step"], [])
                merged_pages.append(merged_page)

            result = {
                "interface_3_final_briefing": {
                    "theme": validated_theme,
                    "one_liner": validated_one_liner,
                    "pages": merged_pages,
                }
            }
        else:
            result = call_llm_with_prompt("3_tone_final", {
                "validated_theme": validated_theme,
                "validated_one_liner": validated_one_liner,
                "validated_pages": json.dumps(validated_pages, ensure_ascii=False),
                "validated_page_glossaries": json.dumps(validated_glossaries, ensure_ascii=False),
            })

        briefing = result.get("interface_3_final_briefing", {})
        page_count = len(briefing.get("pages", []))
        logger.info("  run_tone_final done: %d pages merged", page_count)

        return {
            "pages": briefing.get("pages", []),
            "theme": briefing.get("theme", validated_theme),
            "one_liner": briefing.get("one_liner", validated_one_liner),
            "metrics": _update_metrics(state, "run_tone_final", time.time() - node_start),
        }

    except Exception as e:
        logger.error("  run_tone_final failed: %s", e, exc_info=True)
        return {
            "error": f"run_tone_final failed: {e}",
            "metrics": _update_metrics(state, "run_tone_final", time.time() - node_start, "failed"),
        }


# ────────────────────────────────────────────
# 9. collect_sources — deterministic
# ────────────────────────────────────────────

_STOPWORDS = frozenset({
    "하는", "있는", "이는", "했다", "한다", "되는", "이다", "에서", "으로", "부터",
    "까지", "하고", "그리고", "또한", "하며", "위해", "대한", "통해", "따르", "관련",
    "지난", "오전", "오후", "현재", "기준", "대비", "전날", "거래", "거래일",
})


def _extract_keywords(text: str) -> list[str]:
    """텍스트에서 핵심 키워드(2글자 이상 한글 단어) 추출."""
    words = re.findall(r"[가-힣]{2,}", text)
    return [w for w in words if w not in _STOPWORDS and len(w) >= 2]


@traceable(name="collect_sources", run_type="tool",
           metadata={"phase": "interface_3", "phase_name": "출처 수집", "step": 9})
def collect_sources_node(state: dict) -> dict:
    """출처 수집 (결정론적). chart_agent가 추가한 sources도 병합."""
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

        # 소스별 키워드 추출
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
            page_text = page.get("content", "") + " " + " ".join(page.get("bullets", []))
            for sname, sinfo in source_map.items():
                keywords = source_keywords.get(sname, [])
                match_count = sum(1 for kw in keywords if kw in page_text)
                if match_count >= 2 and page["step"] not in sinfo["used_in_pages"]:
                    sinfo["used_in_pages"].append(page["step"])

        # used_in_pages가 비어있으면 1페이지 배정
        sources = list(source_map.values())
        for s in sources:
            if not s["used_in_pages"]:
                s["used_in_pages"] = [1]

        # chart_agent가 추가한 sources 병합
        chart_sources = state.get("sources") or []
        for cs in chart_sources:
            existing = next((s for s in sources if s["name"] == cs.get("name")), None)
            if existing:
                for pg in cs.get("used_in_pages", []):
                    if pg not in existing["used_in_pages"]:
                        existing["used_in_pages"].append(pg)
            else:
                sources.append(cs)

        logger.info("  collect_sources done: %d sources", len(sources))
        return {
            "sources": sources,
            "metrics": _update_metrics(state, "collect_sources", time.time() - node_start),
        }

    except Exception as e:
        logger.error("  collect_sources failed: %s", e, exc_info=True)
        return {
            "error": f"collect_sources failed: {e}",
            "metrics": _update_metrics(state, "collect_sources", time.time() - node_start, "failed"),
        }


# ────────────────────────────────────────────
# 10. assemble_output — Pydantic validation + JSON save
# ────────────────────────────────────────────

@traceable(name="assemble_output", run_type="tool",
           metadata={"phase": "interface_3", "phase_name": "최종 조립", "step": 10})
def assemble_output_node(state: dict) -> dict:
    """tone_final pages + charts 병합 → Pydantic 검증 → JSON 저장."""
    if state.get("error"):
        return {"error": state["error"]}

    node_start = time.time()
    logger.info("[Node] assemble_output")

    try:
        raw_narrative = state["raw_narrative"]
        curated = state["curated_context"]
        pages = state["pages"]
        charts = state.get("charts") or {}
        sources = state.get("sources", [])
        checklist = state.get("hallucination_checklist", [])
        theme = state.get("theme", raw_narrative["theme"])
        one_liner = state.get("one_liner", raw_narrative["one_liner"])

        # charts를 pages에 병합
        for page in pages:
            step = page["step"]
            section_key = next(
                (sk for s, _, sk in SECTION_MAP if s == step), None
            )
            if section_key and charts.get(section_key):
                page["chart"] = charts[section_key]
            elif "chart" not in page:
                page["chart"] = None

        # FinalBriefing 조립
        final_briefing_data = {
            "theme": theme,
            "one_liner": one_liner,
            "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "pages": pages,
            "sources": sources,
            "hallucination_checklist": checklist,
        }

        # Pydantic 검증
        output = FullBriefingOutput(
            topic=theme,
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

        logger.info("  assemble_output done: %s", output_path)
        return {
            "full_output": output.model_dump(),
            "output_path": str(output_path),
            "metrics": _update_metrics(state, "assemble_output", time.time() - node_start),
        }

    except Exception as e:
        logger.error("  assemble_output failed: %s", e, exc_info=True)
        return {
            "error": f"assemble_output failed: {e}",
            "metrics": _update_metrics(state, "assemble_output", time.time() - node_start, "failed"),
        }
