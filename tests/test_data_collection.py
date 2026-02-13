"""데이터 수집 노드 테스트 — mock 백엔드 사용."""

import pytest


def _make_base_state(**overrides) -> dict:
    state = {
        "input_path": None,
        "topic_index": 0,
        "backend": "mock",
        "market": "KR",
        "raw_news": None,
        "raw_reports": None,
        "screened_stocks": None,
        "matched_stocks": None,
        "news_summary": None,
        "research_summary": None,
        "curated_topics": None,
        "websearch_log": None,
        "curated_context": None,
        "page_purpose": None,
        "historical_case": None,
        "narrative": None,
        "raw_narrative": None,
        "i3_theme": None,
        "i3_pages": None,
        "i3_validated": None,
        "i3_glossaries": None,
        "i3_validated_glossaries": None,
        "charts": None,
        "pages": None,
        "sources": None,
        "hallucination_checklist": None,
        "theme": None,
        "one_liner": None,
        "full_output": None,
        "output_path": None,
        "error": None,
        "metrics": {},
    }
    state.update(overrides)
    return state


class TestCrawlerNodes:
    def test_crawl_news_mock(self):
        from interface.nodes.crawlers import crawl_news_node
        state = _make_base_state()
        result = crawl_news_node(state)
        assert "raw_news" in result
        assert isinstance(result["raw_news"], list)
        assert len(result["raw_news"]) > 0
        assert result["raw_news"][0]["title"]

    def test_crawl_research_mock(self):
        from interface.nodes.crawlers import crawl_research_node
        state = _make_base_state()
        result = crawl_research_node(state)
        assert "raw_reports" in result
        assert isinstance(result["raw_reports"], list)
        assert len(result["raw_reports"]) > 0

    def test_crawl_news_skips_on_error(self):
        from interface.nodes.crawlers import crawl_news_node
        state = _make_base_state(error="previous error")
        result = crawl_news_node(state)
        assert "error" in result

    def test_crawl_research_skips_on_error(self):
        from interface.nodes.crawlers import crawl_research_node
        state = _make_base_state(error="previous error")
        result = crawl_research_node(state)
        assert "error" in result


class TestScreeningNode:
    def test_screen_stocks_mock(self):
        from interface.nodes.screening import screen_stocks_node
        state = _make_base_state()
        result = screen_stocks_node(state)
        assert "screened_stocks" in result
        assert "matched_stocks" in result
        assert len(result["screened_stocks"]) > 0
        assert len(result["matched_stocks"]) > 0
        # matched 구조 확인
        m = result["matched_stocks"][0]
        assert "symbol" in m
        assert "name" in m
        assert "signal" in m
        assert m["has_narrative"] is False

    def test_screen_stocks_skips_on_error(self):
        from interface.nodes.screening import screen_stocks_node
        state = _make_base_state(error="previous error")
        result = screen_stocks_node(state)
        assert "error" in result


class TestCurationNodes:
    def test_summarize_news_mock(self):
        from interface.nodes.curation import summarize_news_node
        state = _make_base_state(raw_news=[{"title": "test", "source": "src"}])
        result = summarize_news_node(state)
        assert "news_summary" in result
        assert isinstance(result["news_summary"], str)
        assert len(result["news_summary"]) > 0

    def test_summarize_research_mock(self):
        from interface.nodes.curation import summarize_research_node
        state = _make_base_state(raw_reports=[{"title": "test"}])
        result = summarize_research_node(state)
        assert "research_summary" in result
        assert isinstance(result["research_summary"], str)

    def test_curate_topics_mock(self):
        from interface.nodes.curation import curate_topics_node
        state = _make_base_state(
            news_summary="test summary",
            research_summary="test report",
            matched_stocks=[
                {"name": "삼성전자", "symbol": "005930", "signal": "short_surge",
                 "return_pct": 8.5, "volume_ratio": 2.1, "period_days": 5},
            ],
        )
        result = curate_topics_node(state)
        assert "curated_topics" in result
        assert isinstance(result["curated_topics"], list)
        assert len(result["curated_topics"]) > 0

    def test_build_curated_context_mock(self):
        from interface.nodes.curation import curate_topics_node, build_curated_context_node
        # 먼저 curate_topics mock으로 topics 생성
        state = _make_base_state()
        curate_result = curate_topics_node(state)
        state.update(curate_result)
        # build_curated_context
        result = build_curated_context_node(state)
        assert "curated_context" in result
        ctx = result["curated_context"]
        assert ctx["theme"]
        assert ctx["one_liner"]
        assert ctx["selected_stocks"]
        assert ctx["concept"]
        # v2 필드 확인
        assert "source_ids" in ctx
        assert "evidence_source_urls" in ctx

    def test_build_curated_context_empty_topics(self):
        from interface.nodes.curation import build_curated_context_node
        state = _make_base_state(curated_topics=[])
        result = build_curated_context_node(state)
        assert "error" in result


class TestDataCollectionE2E:
    """데이터 수집 → Interface 2/3 통합 mock E2E."""

    def test_full_pipeline_mock_no_input(self):
        """input_path=None, backend=mock으로 전체 22노드 파이프라인."""
        from interface.graph import build_graph

        graph = build_graph()
        state = _make_base_state()
        final = graph.invoke(state)

        # 에러 없이 완료
        assert final.get("error") is None, f"Pipeline error: {final.get('error')}"
        # 출력 파일 생성
        assert final.get("output_path")
        # 전체 출력 존재
        assert final.get("full_output")
        # 데이터 수집 결과 존재
        assert final.get("curated_context")
        # 메트릭 확인 (데이터 수집 노드 포함)
        metrics = final.get("metrics", {})
        assert "crawl_news" in metrics
        assert "screen_stocks" in metrics
        assert "curate_topics" in metrics
        assert "build_curated_context" in metrics
        assert "assemble_output" in metrics

    def test_file_load_still_works(self, tmp_path):
        """기존 파일 로드 경로가 여전히 동작하는지 확인."""
        import json
        from interface.graph import build_graph

        # 최소 curated context JSON 생성
        curated = {
            "date": "2026-01-01",
            "theme": "테스트 테마",
            "one_liner": "테스트 한줄 요약",
            "selected_stocks": [
                {"ticker": "005930", "name": "삼성전자", "momentum": "상승", "change_pct": 5.0, "period_days": 5},
            ],
            "verified_news": [
                {"title": "뉴스", "url": "https://test.com", "source": "테스트", "summary": "요약", "published_date": "2026-01-01"},
            ],
            "reports": [
                {"title": "리포트", "source": "증권사", "summary": "요약", "date": "2026-01-01"},
            ],
            "concept": {"name": "개념", "definition": "정의", "relevance": "관련성"},
        }
        input_file = tmp_path / "test_curated.json"
        input_file.write_text(json.dumps(curated, ensure_ascii=False), encoding="utf-8")

        graph = build_graph()
        state = _make_base_state(
            input_path=str(input_file),
            backend="mock",
        )
        final = graph.invoke(state)
        assert final.get("error") is None, f"Pipeline error: {final.get('error')}"
        assert final.get("output_path")
