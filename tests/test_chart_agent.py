"""Chart Agent 노드 테스트 — mock 백엔드 사용."""

import json
from pathlib import Path

import pytest

GOLDEN_CASE = Path(__file__).resolve().parent.parent.parent / "golden_case" / "03_k_defense.json"


@pytest.fixture
def golden_data() -> dict:
    return json.loads(GOLDEN_CASE.read_text("utf-8"))


class TestChartAgentNodes:
    def test_chart_agent_mock(self, golden_data: dict):
        from interface.nodes.chart_agent import run_chart_agent_node

        raw_narrative = golden_data["interface_2_raw_narrative"]
        curated_context = golden_data["interface_1_curated_context"]

        state = {
            "raw_narrative": raw_narrative,
            "curated_context": curated_context,
            "sources": [],
            "backend": "mock",
            "error": None,
            "metrics": {},
        }
        result = run_chart_agent_node(state)

        assert "error" not in result or result.get("error") is None
        assert "charts" in result
        assert isinstance(result["charts"], dict)

    def test_hallcheck_chart_mock(self, golden_data: dict):
        from interface.nodes.chart_agent import run_chart_agent_node, run_hallcheck_chart_node

        raw_narrative = golden_data["interface_2_raw_narrative"]
        curated_context = golden_data["interface_1_curated_context"]

        # 먼저 chart_agent 실행
        chart_result = run_chart_agent_node({
            "raw_narrative": raw_narrative,
            "curated_context": curated_context,
            "sources": [],
            "backend": "mock",
            "error": None,
            "metrics": {},
        })

        state = {
            "charts": chart_result["charts"],
            "curated_context": curated_context,
            "sources": chart_result.get("sources", []),
            "hallucination_checklist": [],
            "backend": "mock",
            "error": None,
            "metrics": {},
        }
        result = run_hallcheck_chart_node(state)

        assert "error" not in result or result.get("error") is None
        assert "hallucination_checklist" in result

    def test_chart_agent_skips_on_error(self):
        from interface.nodes.chart_agent import run_chart_agent_node

        state = {"error": "previous error", "metrics": {}}
        result = run_chart_agent_node(state)
        assert "error" in result
