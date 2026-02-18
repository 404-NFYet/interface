"""Chart Agent Node: Reasoning -> Tool Execution -> Generation -> Verification.

Handles the creation of financial charts by actively fetching data.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable

from langsmith import traceable

from ..ai.llm_utils import call_llm_with_prompt
from ..config import COLOR_PALETTE, SECTION_MAP
from ..ai.tools import get_corp_financials, get_exchange_rate, search_web_for_chart_data

logger = logging.getLogger(__name__)

# Available tools map
AVAILABLE_TOOLS: dict[str, Callable] = {
    "get_corp_financials": get_corp_financials,
    "get_exchange_rate": get_exchange_rate,
    "search_web_for_chart_data": search_web_for_chart_data,
}


def _update_metrics(state: dict, node_name: str, elapsed: float, status: str = "success") -> dict:
    """메트릭 업데이트 (Partial Update for Reducer)."""
    return {
        node_name: {
            "elapsed_s": round(elapsed, 2),
            "status": status
        }
    }


@traceable(name="run_chart_agent", run_type="chain",
           metadata={"phase": "interface_3", "phase_name": "차트 생성", "step": 7})
def run_chart_agent_node(state: dict) -> dict:
    """viz_hint -> Reasoning -> Tool Use -> Chart Generation."""
    if state.get("error"):
        return {"error": state["error"]}

    node_start = time.time()
    logger.info("[Node] run_chart_agent")

    try:
        raw = state["raw_narrative"]
        curated = state["curated_context"]
        narrative = raw["narrative"]
        backend = state.get("backend", "live")

        charts: dict[str, Any] = {}
        all_sources: list[dict] = list(state.get("sources") or [])

        internal_context_summary = json.dumps(curated, ensure_ascii=False)[:3000]

        for step, title, section_key in SECTION_MAP:
            section = narrative[section_key]
            viz_hint = section.get("viz_hint")

            if not viz_hint:
                charts[section_key] = None
                continue

            logger.info(f"  Processing chart for {section_key}: {viz_hint[:50]}...")

            if backend == "mock":
                charts[section_key] = {
                    "data": [{"type": "bar", "x": ["Mock A", "Mock B"], "y": [10, 20], "name": "Mock Data"}],
                    "layout": {"title": f"[Mock] {viz_hint}"},
                }
                all_sources.append({
                    "name": "Mock Source",
                    "url_domain": "mock.com",
                    "used_in_pages": [step],
                })
                continue

            # 1. Reasoning
            reasoning_result = call_llm_with_prompt("3_chart_reasoning", {
                "section_title": title,
                "content": section["content"],
                "viz_hint": viz_hint,
                "curated_context": internal_context_summary,
            })

            tool_calls = reasoning_result.get("tool_calls", [])
            chart_type = reasoning_result.get("chart_type", "Unknown")
            logger.info(f"    Reasoning: Type={chart_type}, Tools={len(tool_calls)}")

            # 2. Tool Execution
            tool_outputs = []
            for call in tool_calls:
                tool_name = call.get("tool")
                args = call.get("args", {})

                if tool_name in AVAILABLE_TOOLS:
                    try:
                        logger.info(f"    Executing {tool_name} with {args}")
                        output = AVAILABLE_TOOLS[tool_name].invoke(args)
                        tool_outputs.append({
                            "tool": tool_name,
                            "args": args,
                            "output": output,
                        })
                    except Exception as e:
                        logger.error(f"    Tool {tool_name} failed: {e}")
                        tool_outputs.append({
                            "tool": tool_name,
                            "error": str(e),
                        })
                else:
                    logger.warning(f"    Unknown tool: {tool_name}")

            # 3. Generation
            generation_result = call_llm_with_prompt("3_chart_generation", {
                "section_title": title,
                "step": step,
                "viz_hint": viz_hint,
                "chart_type": chart_type,
                "internal_context_summary": internal_context_summary,
                "tool_outputs": json.dumps(tool_outputs, ensure_ascii=False),
                "color_palette": COLOR_PALETTE,
            })

            generated_chart = generation_result.get("chart")
            generated_sources = generation_result.get("sources", [])

            if generated_chart:
                charts[section_key] = generated_chart

                for src in generated_sources:
                    if "used_in_pages" not in src or not src["used_in_pages"]:
                        src["used_in_pages"] = [step]

                    existing = next((s for s in all_sources if s["name"] == src["name"]), None)
                    if existing:
                        if step not in existing["used_in_pages"]:
                            existing["used_in_pages"].append(step)
                    else:
                        all_sources.append(src)
            else:
                logger.warning(f"    Chart generation returned empty for {section_key}")
                charts[section_key] = None

        generated_count = len([k for k, v in charts.items() if v])
        logger.info(f"  run_chart_agent done. Generated {generated_count} charts.")

        return {
            "charts": charts,
            "sources": all_sources,
            "metrics": _update_metrics(state, "run_chart_agent", time.time() - node_start),
        }

    except Exception as e:
        logger.error(f"  run_chart_agent failed: {e}", exc_info=True)
        return {
            "error": f"run_chart_agent failed: {e}",
            "metrics": _update_metrics(state, "run_chart_agent", time.time() - node_start, "failed"),
        }


@traceable(name="run_hallcheck_chart", run_type="llm",
           metadata={"phase": "interface_3", "phase_name": "차트 검증", "step": 8})
def run_hallcheck_chart_node(state: dict) -> dict:
    """Generated Chart Hallucination Check."""
    if state.get("error"):
        return {"error": state["error"]}

    node_start = time.time()
    logger.info("[Node] run_hallcheck_chart")

    try:
        charts = state.get("charts", {})
        checklist = list(state.get("hallucination_checklist") or [])

        backend = state.get("backend", "live")
        if backend == "mock":
            return {
                "hallucination_checklist": checklist,
                "metrics": _update_metrics(state, "run_hallcheck_chart", time.time() - node_start),
            }

        curated = state["curated_context"]

        for step, title, section_key in SECTION_MAP:
            chart = charts.get(section_key)
            if not chart:
                continue

            result = call_llm_with_prompt("3_hallcheck_chart", {
                "chart_json": json.dumps(chart, ensure_ascii=False),
                "source_context": json.dumps(curated, ensure_ascii=False)[:2000],
                "sources_metadata": json.dumps(state.get("sources", []), ensure_ascii=False),
            })

            new_items = result.get("hallucination_checklist", [])
            logger.info(f"  {section_key}: Found {len(new_items)} verification items.")
            checklist.extend(new_items)

        return {
            "hallucination_checklist": checklist,
            "metrics": _update_metrics(state, "run_hallcheck_chart", time.time() - node_start),
        }

    except Exception as e:
        logger.error(f"  run_hallcheck_chart failed: {e}", exc_info=True)
        return {
            "error": f"run_hallcheck_chart failed: {e}",
            "metrics": _update_metrics(state, "run_hallcheck_chart", time.time() - node_start, "failed"),
        }
