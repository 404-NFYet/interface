"""Pydantic 스키마 검증 테스트.

golden_case/03_k_defense.json을 FullBriefingOutput으로 검증한다.
"""

import json
from pathlib import Path

import pytest

from interface.schemas import (
    CuratedContext,
    FinalBriefing,
    FullBriefingOutput,
    RawNarrative,
)

GOLDEN_CASE = Path(__file__).resolve().parent.parent.parent / "golden_case" / "03_k_defense.json"


@pytest.fixture
def golden_data() -> dict:
    """golden_case/03_k_defense.json 로드."""
    return json.loads(GOLDEN_CASE.read_text("utf-8"))


class TestCuratedContext:
    def test_validate(self, golden_data: dict):
        raw = golden_data["interface_1_curated_context"]
        ctx = CuratedContext.model_validate(raw)
        assert ctx.theme
        assert len(ctx.selected_stocks) > 0
        assert len(ctx.verified_news) > 0
        assert ctx.concept.name

    def test_roundtrip(self, golden_data: dict):
        raw = golden_data["interface_1_curated_context"]
        ctx = CuratedContext.model_validate(raw)
        dumped = ctx.model_dump()
        ctx2 = CuratedContext.model_validate(dumped)
        assert ctx == ctx2


class TestRawNarrative:
    def test_validate(self, golden_data: dict):
        raw = golden_data["interface_2_raw_narrative"]
        narr = RawNarrative.model_validate(raw)
        assert narr.theme
        assert narr.historical_case.period
        assert narr.narrative.background.purpose

    def test_all_sections_present(self, golden_data: dict):
        raw = golden_data["interface_2_raw_narrative"]
        narr = RawNarrative.model_validate(raw)
        for section_name in ["background", "concept_explain", "history", "application", "caution", "summary"]:
            section = getattr(narr.narrative, section_name)
            assert section.purpose
            assert section.content
            assert len(section.bullets) >= 2


class TestFinalBriefing:
    def test_validate(self, golden_data: dict):
        raw = golden_data["interface_3_final_briefing"]
        fb = FinalBriefing.model_validate(raw)
        assert fb.theme
        assert len(fb.pages) == 6
        assert len(fb.sources) > 0
        assert len(fb.hallucination_checklist) > 0

    def test_pages_structure(self, golden_data: dict):
        raw = golden_data["interface_3_final_briefing"]
        fb = FinalBriefing.model_validate(raw)
        for i, page in enumerate(fb.pages):
            assert page.step == i + 1
            assert page.title
            assert page.content


class TestFullBriefingOutput:
    def test_validate_golden_case(self, golden_data: dict):
        output = FullBriefingOutput.model_validate(golden_data)
        assert output.topic
        assert output.interface_1_curated_context.theme
        assert output.interface_2_raw_narrative.theme
        assert output.interface_3_final_briefing.theme

    def test_json_roundtrip(self, golden_data: dict):
        output = FullBriefingOutput.model_validate(golden_data)
        json_str = output.model_dump_json(ensure_ascii=False)
        parsed = json.loads(json_str)
        output2 = FullBriefingOutput.model_validate(parsed)
        assert output.topic == output2.topic
        assert len(output.interface_3_final_briefing.pages) == len(output2.interface_3_final_briefing.pages)
