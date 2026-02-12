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
    def test_assemble_pages(self, golden_data: dict):
        from interface.nodes.interface3 import assemble_pages_node

        raw_narrative = golden_data["interface_2_raw_narrative"]
        state = {
            "raw_narrative": raw_narrative,
            "charts": {},
            "glossaries": {},
            "backend": "mock",
            "metrics": {},
        }
        result = assemble_pages_node(state)

        assert "error" not in result or result.get("error") is None
        assert len(result["pages"]) == 6
        assert result["pages"][0]["step"] == 1

    def test_collect_sources(self, golden_data: dict):
        from interface.nodes.interface3 import assemble_pages_node, collect_sources_node

        raw_narrative = golden_data["interface_2_raw_narrative"]
        curated_context = golden_data["interface_1_curated_context"]

        # 먼저 pages 조립
        pages_result = assemble_pages_node({
            "raw_narrative": raw_narrative,
            "charts": {},
            "glossaries": {},
            "metrics": {},
        })

        state = {
            "curated_context": curated_context,
            "pages": pages_result["pages"],
            "backend": "mock",
            "metrics": {},
        }
        result = collect_sources_node(state)

        assert "error" not in result or result.get("error") is None
        assert len(result["sources"]) > 0
