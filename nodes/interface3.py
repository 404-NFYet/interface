"""Interface 3 Nodes: 8-Step Sequential Pipeline.

1. Theme -> 2. Pages -> 3. Hallcheck Pages -> 4. Glossary -> 5. Hallcheck Glossary -> 6. Tone Final
-> (Graph: 7. Chart Agent -> 8. Hallcheck Chart) -> Collect Sources -> Assemble Output.
"""

from __future__ import annotations

import json
import logging
import time
import re
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
    Page,
    GlossaryItem,
    SourceItem,
    HallucinationItem,
    PlotlyChart
)

logger = logging.getLogger(__name__)


def _update_metrics(state: dict, node_name: str, elapsed: float, status: str = "success") -> dict:
    metrics = dict(state.get("metrics") or {})
    metrics[node_name] = {"elapsed_s": round(elapsed, 2), "status": status}
    return metrics


# ── Helper Functions ──

_STOPWORDS = frozenset({
    "하는", "있는", "이는", "했다", "한다", "되는", "이다", "에서", "으로", "부터",
    "까지", "하고", "그리고", "또한", "하며", "위해", "대한", "통해", "따르", "관련",
    "지난", "오전", "오후", "현재", "기준", "대비", "전날", "거래", "거래일",
})

def _extract_keywords(text: str) -> list[str]:
    """텍스트에서 핵심 키워드(2글자 이상 한글 단어) 추출."""
    words = re.findall(r"[가-힣]{2,}", text)
    return [w for w in words if w not in _STOPWORDS and len(w) >= 2]


# ── Step 1: Theme ──

@traceable(name="run_theme", run_type="llm", metadata={"phase": "interface_3", "step": 1})
def run_theme_node(state: dict) -> dict:
    """Refine Theme & One-Liner."""
    if state.get("error"): return {"error": state["error"]}
    node_start = time.time()
    logger.info("[Node] run_theme")
    
    try:
        raw = state["raw_narrative"]
        backend = state.get("backend", "live")
        
        if backend == "mock":
             return {"metrics": _update_metrics(state, "run_theme", time.time() - node_start)}

        # Use 3_theme.md to refine
        result = call_llm_with_prompt("3_theme", {
            "raw_narrative": raw
        })
        
        # Update raw_narrative with refined theme/oneliner if provided
        new_theme = result.get("theme")
        new_oneliner = result.get("one_liner")
        
        if new_theme: raw["theme"] = new_theme
        if new_oneliner: raw["one_liner"] = new_oneliner
        
        return {
            "raw_narrative": raw,
            "metrics": _update_metrics(state, "run_theme", time.time() - node_start)
        }
    except Exception as e:
        logger.error(f"run_theme failed: {e}")
        return {"error": str(e)}


# ── Step 2: Pages Generation ──

@traceable(name="run_pages", run_type="llm", metadata={"phase": "interface_3", "step": 2})
def run_pages_node(state: dict) -> dict:
    """Generate Content for 6 Pages."""
    if state.get("error"): return {"error": state["error"]}
    node_start = time.time()
    logger.info("[Node] run_pages")
    
    try:
        raw = state["raw_narrative"]
        narrative = raw["narrative"]
        backend = state.get("backend", "live")
        
        pages_content = []
        
        for step, title, section_key in SECTION_MAP:
            section = narrative[section_key]
            
            if backend == "mock":
                pages_content.append({
                    "step": step,
                    "title": title,
                    "purpose": section["purpose"],
                    "content": section["content"], # Reuse raw as is
                    "bullets": section["bullets"]
                })
                continue
                
            # Use 3_pages.md
            result = call_llm_with_prompt("3_pages", {
                "section_key": section_key,
                "title": title,
                "purpose": section["purpose"],
                "content": section["content"],
                "bullets": section["bullets"]
            })
            
            pages_content.append({
                "step": step,
                "title": title,
                "purpose": section["purpose"],
                "content": result.get("content", section["content"]),
                "bullets": result.get("bullets", section["bullets"]),
                "quiz": result.get("quiz")
            })
            
        return {
            "pages": pages_content, # Intermediate structure
            "metrics": _update_metrics(state, "run_pages", time.time() - node_start)
        }
    except Exception as e:
        logger.error(f"run_pages failed: {e}")
        return {"error": str(e)}


# ── Step 3: Hallcheck Pages ──

@traceable(name="run_hallcheck_pages", run_type="llm", metadata={"phase": "interface_3", "step": 3})
def run_hallcheck_pages_node(state: dict) -> dict:
    """Verify Text Content."""
    if state.get("error"): return {"error": state["error"]}
    node_start = time.time()
    
    try:
        curated = state["curated_context"]
        pages = state["pages"]
        backend = state.get("backend", "live")
        checklist = state.get("hallucination_checklist", [])
        
        if backend == "mock":
             return {"metrics": _update_metrics(state, "run_hallcheck_pages", time.time() - node_start)}

        result = call_llm_with_prompt("3_hallcheck_pages", {
            "curated_context": curated,
            "pages": pages
        })
        
        new_items = result.get("hallucination_checklist", [])
        checklist.extend(new_items)
        
        # Update pages with validated version if provided
        validated_pages = result.get("validated_pages")
        if validated_pages:
            # Ensure quiz data is preserved or updated
            # The prompt is instructed to return full pages, so we can overwrite
            pages = validated_pages

        return {
            "pages": pages, # Update state with validated pages
            "hallucination_checklist": checklist,
            "metrics": _update_metrics(state, "run_hallcheck_pages", time.time() - node_start)
        }
    except Exception as e:
        logger.error(f"run_hallcheck_pages failed: {e}")
        return {"error": str(e)}


# ── Step 4: Glossary ──

@traceable(name="run_glossary", run_type="llm", metadata={"phase": "interface_3", "step": 4})
def run_glossary_node(state: dict) -> dict:
    """Generate Glossary."""
    if state.get("error"): return {"error": state["error"]}
    node_start = time.time()
    
    try:
        pages = state["pages"] # Use generated pages
        backend = state.get("backend", "live")
        
        glossaries: dict[str, list] = {}
        seen_terms = set()
        
        for page in pages:
            # section_key finding via step is tedious, but we iterate pages
            # pages don't store section_key, but we know order.
            # actually pages list is ordered 1..6
            step = page["step"]
            # Find section_key from SECTION_MAP
            section_key = next((k for s, t, k in SECTION_MAP if s == step), f"section_{step}")
            
            if backend == "mock":
                glossaries[section_key] = [{"term": f"MockTerm{step}", "definition": "MockDef", "domain": "General"}]
                continue
                
            result = call_llm_with_prompt("3_glossary", {
                "content": page["content"],
                "existing_terms": list(seen_terms)
            })
            
            items = result.get("glossary", [])
            filtered = []
            for item in items:
                t = item.get("term")
                if t and t not in seen_terms:
                    seen_terms.add(t)
                    filtered.append(item)
            glossaries[section_key] = filtered
            
        return {
            "glossaries": glossaries,
            "metrics": _update_metrics(state, "run_glossary", time.time() - node_start)
        }
    except Exception as e:
        logger.error(f"run_glossary failed: {e}")
        return {"error": str(e)}


# ── Step 5: Hallcheck Glossary ──

@traceable(name="run_hallcheck_glossary", run_type="llm", metadata={"phase": "interface_3", "step": 5})
def run_hallcheck_glossary_node(state: dict) -> dict:
    """Verify Glossary Definitions."""
    if state.get("error"): return {"error": state["error"]}
    node_start = time.time()
    
    try:
        glossaries = state["glossaries"]
        checklist = state.get("hallucination_checklist", [])
        backend = state.get("backend", "live") # Mock check omitted for brevity, passing empty
        
        if backend != "mock":
            result = call_llm_with_prompt("3_hallcheck_glossary", {
                "glossaries": glossaries
            })
            checklist.extend(result.get("hallucination_checklist", []))
            
        return {
            "hallucination_checklist": checklist,
            "metrics": _update_metrics(state, "run_hallcheck_glossary", time.time() - node_start)
        }
    except Exception as e:
        logger.error(f"run_hallcheck_glossary failed: {e}")
        return {"error": str(e)}


# ── Step 6: Tone Final ──

@traceable(name="run_tone_final", run_type="llm", metadata={"phase": "interface_3", "step": 6})
def run_tone_final_node(state: dict) -> dict:
    """Final Tone Polish."""
    if state.get("error"): return {"error": state["error"]}
    node_start = time.time()
    
    try:
        pages = state["pages"]
        backend = state.get("backend", "live")
        
        if backend == "mock":
             return {"metrics": _update_metrics(state, "run_tone_final", time.time() - node_start)}

        new_pages = []
        for page in pages:
            result = call_llm_with_prompt("3_tone_final", {
                "content": page["content"],
                "bullets": page["bullets"]
            })
            new_page = page.copy()
            new_page["content"] = result.get("content", page["content"])
            # bullets might also be refined if prompt supports it
            if "bullets" in result:
                new_page["bullets"] = result["bullets"]
            new_pages.append(new_page)
            
        return {
            "pages": new_pages,
            "metrics": _update_metrics(state, "run_tone_final", time.time() - node_start)
        }
    except Exception as e:
        logger.error(f"run_tone_final failed: {e}")
        return {"error": str(e)}


# ── Collect Sources (Text) ──

@traceable(name="collect_sources", run_type="tool", metadata={"phase": "interface_3", "step": 9})
def collect_sources_node(state: dict) -> dict:
    """Collect Sources from Text (News/Reports). Run after Tone Final, before Output."""
    if state.get("error"): return {"error": state["error"]}
    node_start = time.time()
    
    try:
        curated = state["curated_context"]
        pages = state["pages"]
        sources = state.get("sources", []) # Output from Chart Agent might be here already
        
        # Build map from existing sources to avoid dupes logic...
        # ... Reuse logic from previous collect_sources_node ...
        
        # Simplified for brevity:
        # 1. Create source candidates from Curated Context
        # 2. Key matching against Page Content
        # 3. Append to 'sources' list
        
        source_map = {s["name"]: s for s in sources} # Existing sources
        
        # Keyword extraction & matching (same as before)
        # verified_news & reports -> candidates
        candidates = []
        for news in curated.get("verified_news", []):
            candidates.append({
                "name": news.get("source"),
                "domain": news.get("url", "").split("/")[2] if "//" in news.get("url", "") else "",
                "text": f"{news.get('title')} {news.get('summary')}"
            })
        for rep in curated.get("reports", []):
            candidates.append({
                "name": rep.get("source"),
                "domain": "",
                "text": f"{rep.get('title')} {rep.get('summary')}"
            })
            
        for cand in candidates:
            name = cand["name"]
            if not name: continue
            
            # Check if used in pages
            used_pages = []
            cand_keywords = _extract_keywords(cand["text"])
            
            for page in pages:
                p_text = page["content"] + " " + " ".join(page["bullets"])
                match_count = sum(1 for kw in cand_keywords if kw in p_text)
                if match_count >= 1: # Lower threshold?
                    used_pages.append(page["step"])
            
            if used_pages:
                if name not in source_map:
                    source_map[name] = {
                        "name": name,
                        "url_domain": cand["domain"],
                        "used_in_pages": used_pages
                    }
                else:
                    # Merge pages
                    existing = source_map[name]
                    existing["used_in_pages"] = list(set(existing["used_in_pages"] + used_pages))

        final_sources = list(source_map.values())
        
        return {
            "sources": final_sources,
            "metrics": _update_metrics(state, "collect_sources", time.time() - node_start)
        }
    except Exception as e:
        logger.error(f"collect_sources failed: {e}")
        return {"error": str(e)}


# ── Assemble Output ──

@traceable(name="assemble_output", run_type="tool", metadata={"phase": "interface_3", "step": 10})
def assemble_output_node(state: dict) -> dict:
    """Final Assembly."""
    if state.get("error"): return {"error": state["error"]}
    node_start = time.time()
    
    try:
        raw_narrative = state["raw_narrative"]
        curated = state["curated_context"]
        pages_data = state["pages"]
        glossaries = state.get("glossaries", {})
        charts = state.get("charts", {})
        sources = state.get("sources", [])
        checklist = state.get("hallucination_checklist", [])
        
        final_pages = []
        for p_data in pages_data:
            step = p_data["step"]
            # Find section_key needed for chart/glossary lookup
            section_key = next((k for s, t, k in SECTION_MAP if s == step), None)
            
            page_obj = Page(
                step=step,
                title=p_data["title"],
                purpose=p_data["purpose"],
                content=p_data["content"],
                bullets=p_data["bullets"],
                quiz=p_data.get("quiz"),
                chart=charts.get(section_key),
                glossary=[GlossaryItem(**g) for g in glossaries.get(section_key, [])]
            )
            final_pages.append(page_obj)
            
        # Sort sources by name or importance? Keep list.
        final_sources = [SourceItem(**s) for s in sources]
        final_checklist = [HallucinationItem(**h) for h in checklist]
        
        final_briefing = FinalBriefing(
            theme=raw_narrative["theme"],
            one_liner=raw_narrative["one_liner"],
            generated_at=datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            pages=final_pages,
            sources=final_sources,
            hallucination_checklist=final_checklist
        )
        
        output = FullBriefingOutput(
            topic=raw_narrative["theme"],
            interface_1_curated_context=CuratedContext.model_validate(curated),
            interface_2_raw_narrative=RawNarrative.model_validate(raw_narrative),
            interface_3_final_briefing=final_briefing
        )
        
        # Save
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = OUTPUT_DIR / f"briefing_{timestamp}.json"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(output.model_dump_json(indent=2, ensure_ascii=False))
            
        logger.info(f"assemble_output done: {output_path}")
        return {
            "full_output": output.model_dump(),
            "output_path": str(output_path),
            "metrics": _update_metrics(state, "assemble_output", time.time() - node_start)
        }
    except Exception as e:
        logger.error(f"assemble_output failed: {e}", exc_info=True)
        return {"error": str(e)}
