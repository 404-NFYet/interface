"""인터페이스 파이프라인 Pydantic v2 스키마.

golden_case/03_k_defense.json 구조를 정확히 반영한다.
3개 인터페이스(CuratedContext, RawNarrative, FinalBriefing)의 계약을 정의한다.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ────────────────────────────────────────────
# Interface 1: Curated Context
# ────────────────────────────────────────────

class StockItem(BaseModel):
    ticker: str
    name: str
    momentum: str  # 급등|급락|상승|하락|횡보
    change_pct: float
    period_days: int


class NewsItem(BaseModel):
    title: str
    url: str
    source: str
    summary: str
    published_date: str


class ReportItem(BaseModel):
    title: str
    source: str
    summary: str
    date: str


class Concept(BaseModel):
    name: str
    definition: str
    relevance: str


class CuratedContext(BaseModel):
    """Interface 1 출력 스키마."""
    date: str
    theme: str
    one_liner: str
    selected_stocks: list[StockItem]
    verified_news: list[NewsItem]
    reports: list[ReportItem]
    concept: Concept


# ────────────────────────────────────────────
# Interface 2: Raw Narrative
# ────────────────────────────────────────────

class HistoricalCase(BaseModel):
    period: str
    title: str
    summary: str
    outcome: str
    lesson: str


class NarrativeSection(BaseModel):
    purpose: str
    content: str
    bullets: list[str]
    viz_hint: Optional[str] = None


class NarrativeBody(BaseModel):
    background: NarrativeSection
    concept_explain: NarrativeSection
    history: NarrativeSection
    application: NarrativeSection
    caution: NarrativeSection
    summary: NarrativeSection


class RawNarrative(BaseModel):
    """Interface 2 출력 스키마."""
    theme: str
    one_liner: str
    concept: Concept
    historical_case: HistoricalCase
    narrative: NarrativeBody


# ────────────────────────────────────────────
# Interface 3: Final Briefing
# ────────────────────────────────────────────

class PlotlyChart(BaseModel):
    data: list[dict[str, Any]]
    layout: dict[str, Any]


class GlossaryItem(BaseModel):
    term: str
    definition: str
    domain: str


class Page(BaseModel):
    step: int
    title: str
    purpose: str
    content: str
    bullets: list[str]
    chart: Optional[PlotlyChart] = None
    glossary: list[GlossaryItem] = Field(default_factory=list)


class SourceItem(BaseModel):
    name: str
    url_domain: str
    used_in_pages: list[int]


class HallucinationItem(BaseModel):
    claim: str
    source: str
    risk: str  # 낮음|중간|높음
    note: str


class FinalBriefing(BaseModel):
    """Interface 3 출력 스키마."""
    theme: str
    one_liner: str
    generated_at: str
    pages: list[Page]
    sources: list[SourceItem]
    hallucination_checklist: list[HallucinationItem]


# ────────────────────────────────────────────
# 최종 통합 출력
# ────────────────────────────────────────────

class FullBriefingOutput(BaseModel):
    """최종 출력: 03_k_defense.json과 동일 구조."""
    topic: str
    interface_1_curated_context: CuratedContext
    interface_2_raw_narrative: RawNarrative
    interface_3_final_briefing: FinalBriefing
