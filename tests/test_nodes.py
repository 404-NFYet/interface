"""노드 단위 테스트 — mock 백엔드 사용."""

import json
from pathlib import Path

import pytest

from interface.schemas import CuratedContext, RawNarrative

GOLDEN_CASE = Path(__file__).resolve().parent.parent.parent / "golden_case" / "03_k_defense.json"


@pytest.fixture
def golden_data() -> dict:
    return json.loads(GOLDEN_CASE.read_text("utf-8"))


@pytest.fixture
def curated_context(golden_data: dict) -> dict:
    return golden_data["interface_1_curated_context"]


class TestInterface1Node:
    def test_load_curated_context(self, golden_data: dict, tmp_path: Path):
        from interface.nodes.interface1 import load_curated_context_node

        # golden case를 임시 파일로 저장
        input_file = tmp_path / "test_input.json"
        input_file.write_text(json.dumps(golden_data, ensure_ascii=False), encoding="utf-8")

        state = {
            "input_path": str(input_file),
            "topic_index": 0,
            "backend": "mock",
            "metrics": {},
        }
        result = load_curated_context_node(state)

        assert "error" not in result or result.get("error") is None
        assert result["curated_context"]["theme"]
        CuratedContext.model_validate(result["curated_context"])

    def test_load_missing_path(self):
        from interface.nodes.interface1 import load_curated_context_node

        state = {"input_path": None, "metrics": {}}
        result = load_curated_context_node(state)
        assert result.get("error")


class TestInterface2Nodes:
    def test_page_purpose_mock(self, curated_context: dict):
        from interface.nodes.interface2 import run_page_purpose_node

        state = {
            "curated_context": curated_context,
            "backend": "mock",
            "metrics": {},
        }
        result = run_page_purpose_node(state)

        assert "error" not in result or result.get("error") is None
        assert "page_purpose" in result
        assert result["page_purpose"]["theme"]

    def test_historical_case_mock(self, curated_context: dict):
        from interface.nodes.interface2 import run_historical_case_node, _mock_page_purpose

        pp = _mock_page_purpose(curated_context)
        state = {
            "curated_context": curated_context,
            "page_purpose": pp,
            "backend": "mock",
            "metrics": {},
        }
        result = run_historical_case_node(state)

        assert "error" not in result or result.get("error") is None
        assert "historical_case" in result

    def test_narrative_body_mock(self, curated_context: dict):
        from interface.nodes.interface2 import (
            _mock_historical_case,
            _mock_page_purpose,
            run_narrative_body_node,
        )

        pp = _mock_page_purpose(curated_context)
        hc = _mock_historical_case(curated_context, pp)
        state = {
            "curated_context": curated_context,
            "page_purpose": pp,
            "historical_case": hc,
            "backend": "mock",
            "metrics": {},
        }
        result = run_narrative_body_node(state)

        assert "error" not in result or result.get("error") is None
        assert "narrative" in result

    def test_validate_interface2_mock(self, curated_context: dict):
        from interface.nodes.interface2 import (
            _mock_historical_case,
            _mock_narrative,
            _mock_page_purpose,
            validate_interface2_node,
        )

        pp = _mock_page_purpose(curated_context)
        hc = _mock_historical_case(curated_context, pp)
        narr = _mock_narrative(curated_context, pp, hc)
        state = {
            "curated_context": curated_context,
            "page_purpose": pp,
            "historical_case": hc,
            "narrative": narr,
            "backend": "mock",
            "metrics": {},
        }
        result = validate_interface2_node(state)

        assert "error" not in result or result.get("error") is None
        assert "raw_narrative" in result
        RawNarrative.model_validate(result["raw_narrative"])


class TestInterface3Nodes:
    """Interface 3 — 10노드 순차 파이프라인 (mock)."""

    @pytest.fixture
    def raw_narrative(self, golden_data: dict) -> dict:
        return golden_data["interface_2_raw_narrative"]

    def test_run_theme_mock(self, raw_narrative: dict):
        from interface.nodes.interface3 import run_theme_node

        state = {"raw_narrative": raw_narrative, "backend": "mock", "metrics": {}}
        result = run_theme_node(state)

        assert "error" not in result or result.get("error") is None
        assert "i3_theme" in result
        assert result["i3_theme"]["theme"]
        assert result["i3_theme"]["one_liner"]

    def test_run_pages_mock(self, raw_narrative: dict):
        from interface.nodes.interface3 import run_pages_node

        state = {"raw_narrative": raw_narrative, "backend": "mock", "metrics": {}}
        result = run_pages_node(state)

        assert "error" not in result or result.get("error") is None
        assert "i3_pages" in result
        assert len(result["i3_pages"]) == 6
        assert result["i3_pages"][0]["step"] == 1

    def test_run_hallcheck_pages_mock(self, raw_narrative: dict):
        from interface.nodes.interface3 import run_theme_node, run_pages_node, run_hallcheck_pages_node

        # build up state
        theme_result = run_theme_node({"raw_narrative": raw_narrative, "backend": "mock", "metrics": {}})
        pages_result = run_pages_node({"raw_narrative": raw_narrative, "backend": "mock", "metrics": {}})

        state = {
            "raw_narrative": raw_narrative,
            "i3_theme": theme_result["i3_theme"],
            "i3_pages": pages_result["i3_pages"],
            "backend": "mock",
            "metrics": {},
        }
        result = run_hallcheck_pages_node(state)

        assert "error" not in result or result.get("error") is None
        assert "i3_validated" in result
        assert result["i3_validated"]["validated_theme"]
        assert len(result["i3_validated"]["validated_pages"]) == 6

    def test_run_glossary_mock(self, raw_narrative: dict):
        from interface.nodes.interface3 import run_theme_node, run_pages_node, run_hallcheck_pages_node, run_glossary_node

        theme_r = run_theme_node({"raw_narrative": raw_narrative, "backend": "mock", "metrics": {}})
        pages_r = run_pages_node({"raw_narrative": raw_narrative, "backend": "mock", "metrics": {}})
        hallcheck_r = run_hallcheck_pages_node({
            "raw_narrative": raw_narrative,
            "i3_theme": theme_r["i3_theme"],
            "i3_pages": pages_r["i3_pages"],
            "backend": "mock", "metrics": {},
        })

        state = {
            "raw_narrative": raw_narrative,
            "i3_validated": hallcheck_r["i3_validated"],
            "backend": "mock",
            "metrics": {},
        }
        result = run_glossary_node(state)

        assert "error" not in result or result.get("error") is None
        assert "i3_glossaries" in result
        assert len(result["i3_glossaries"]) == 6

    def test_run_tone_final_mock(self, raw_narrative: dict):
        from interface.nodes.interface3 import (
            run_theme_node, run_pages_node, run_hallcheck_pages_node,
            run_glossary_node, run_hallcheck_glossary_node, run_tone_final_node,
        )

        theme_r = run_theme_node({"raw_narrative": raw_narrative, "backend": "mock", "metrics": {}})
        pages_r = run_pages_node({"raw_narrative": raw_narrative, "backend": "mock", "metrics": {}})
        hallcheck_r = run_hallcheck_pages_node({
            "raw_narrative": raw_narrative,
            "i3_theme": theme_r["i3_theme"],
            "i3_pages": pages_r["i3_pages"],
            "backend": "mock", "metrics": {},
        })
        glossary_r = run_glossary_node({
            "raw_narrative": raw_narrative,
            "i3_validated": hallcheck_r["i3_validated"],
            "backend": "mock", "metrics": {},
        })
        hallcheck_g = run_hallcheck_glossary_node({
            "raw_narrative": raw_narrative,
            "i3_validated": hallcheck_r["i3_validated"],
            "i3_glossaries": glossary_r["i3_glossaries"],
            "backend": "mock", "metrics": {},
        })

        state = {
            "i3_validated": hallcheck_r["i3_validated"],
            "i3_validated_glossaries": hallcheck_g["i3_validated_glossaries"],
            "backend": "mock",
            "metrics": {},
        }
        result = run_tone_final_node(state)

        assert "error" not in result or result.get("error") is None
        assert "pages" in result
        assert len(result["pages"]) == 6
        # glossary merged
        assert "glossary" in result["pages"][0]

    def test_collect_sources(self, golden_data: dict, raw_narrative: dict):
        from interface.nodes.interface3 import run_pages_node, collect_sources_node

        curated_context = golden_data["interface_1_curated_context"]
        pages_r = run_pages_node({"raw_narrative": raw_narrative, "backend": "mock", "metrics": {}})

        state = {
            "curated_context": curated_context,
            "pages": pages_r["i3_pages"],
            "sources": None,
            "backend": "mock",
            "metrics": {},
        }
        result = collect_sources_node(state)

        assert "error" not in result or result.get("error") is None
        assert len(result["sources"]) > 0
