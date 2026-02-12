"""데이터 수집 유틸리티 단위 테스트."""

import pytest


class TestIntersection:
    def test_screened_to_matched(self):
        from interface.data_collection.intersection import screened_to_matched

        stock = {
            "symbol": "005930",
            "name": "삼성전자",
            "signal": "short_surge",
            "return_pct": 8.5,
            "volume_ratio": 2.1,
            "period_days": 5,
        }
        matched = screened_to_matched(stock)
        assert matched["symbol"] == "005930"
        assert matched["name"] == "삼성전자"
        assert matched["signal"] == "short_surge"
        assert matched["has_narrative"] is False
        assert matched["narrative_headlines"] == []
        assert matched["narrative_sources"] == []

    def test_screened_to_matched_preserves_fields(self):
        from interface.data_collection.intersection import screened_to_matched

        stock = {
            "symbol": "000660",
            "name": "SK하이닉스",
            "signal": "mid_term_up",
            "return_pct": 15.3,
            "volume_ratio": 1.8,
            "period_days": 126,
        }
        matched = screened_to_matched(stock)
        assert matched["return_pct"] == 15.3
        assert matched["volume_ratio"] == 1.8
        assert matched["period_days"] == 126


class TestNewsSummarizerUtils:
    def test_estimate_tokens(self):
        from interface.data_collection.news_summarizer import _estimate_tokens
        assert _estimate_tokens("") == 1
        assert _estimate_tokens("1234") == 1
        assert _estimate_tokens("12345678") == 2

    def test_chunk_blocks_single(self):
        from interface.data_collection.news_summarizer import _chunk_blocks
        blocks = [(1, "short text")]
        chunks = _chunk_blocks(blocks, 1000)
        assert len(chunks) == 1
        assert len(chunks[0]) == 1

    def test_chunk_blocks_split(self):
        from interface.data_collection.news_summarizer import _chunk_blocks
        blocks = [(i, "x" * 200) for i in range(10)]
        chunks = _chunk_blocks(blocks, 200)
        assert len(chunks) > 1

    def test_format_news_blocks(self):
        from interface.data_collection.news_summarizer import _format_news_blocks
        items = [
            {"title": "제목1", "source": "소스1", "summary": "요약1", "published_date": "2026-01-01"},
            {"title": "제목2", "source": "소스2", "summary": "요약2", "published_date": "2026-01-02"},
        ]
        blocks = _format_news_blocks(items)
        assert len(blocks) == 2
        assert blocks[0][0] == 1
        assert "제목1" in blocks[0][1]

    def test_format_report_blocks(self):
        from interface.data_collection.news_summarizer import _format_report_blocks
        items = [
            {"title": "리포트1", "source": "증권사1", "summary": "요약1", "date": "2026-01-01"},
        ]
        blocks = _format_report_blocks(items)
        assert len(blocks) == 1
        assert "리포트1" in blocks[0][1]


class TestNewsCrawlerUtils:
    def test_to_news_items(self):
        from interface.data_collection.news_crawler import to_news_items
        raw = [
            {"title": "뉴스", "link": "https://test.com", "source_name": "한경",
             "summary": "요약", "published": "2026-01-01"},
        ]
        items = to_news_items(raw)
        assert len(items) == 1
        assert items[0]["title"] == "뉴스"
        assert items[0]["url"] == "https://test.com"
        assert items[0]["source"] == "한경"

    def test_to_news_items_empty(self):
        from interface.data_collection.news_crawler import to_news_items
        assert to_news_items([]) == []


class TestResearchCrawlerUtils:
    def test_to_report_items(self):
        from interface.data_collection.research_crawler import to_report_items
        raw = [
            {"title": "리포트", "firm": "삼성증권", "summary": "요약", "date": "2026-01-01"},
        ]
        items = to_report_items(raw)
        assert len(items) == 1
        assert items[0]["title"] == "리포트"
        assert items[0]["source"] == "삼성증권"

    def test_to_report_items_none_summary(self):
        from interface.data_collection.research_crawler import to_report_items
        raw = [{"title": "리포트", "firm": "증권사", "summary": None, "date": "2026-01-01"}]
        items = to_report_items(raw)
        assert items[0]["summary"] == ""


class TestSchemaExtensions:
    def test_screened_stock_item(self):
        from interface.schemas import ScreenedStockItem
        s = ScreenedStockItem(
            symbol="005930", name="삼성전자", signal="short_surge",
            return_pct=8.5, volume_ratio=2.1, period_days=5,
        )
        assert s.symbol == "005930"

    def test_matched_stock_item_defaults(self):
        from interface.schemas import MatchedStockItem
        m = MatchedStockItem(
            symbol="005930", name="삼성전자", signal="short_surge",
            return_pct=8.5, volume_ratio=2.1, period_days=5,
        )
        assert m.narrative_headlines == []
        assert m.has_narrative is False

    def test_curated_context_v2_fields(self):
        from interface.schemas import CuratedContext
        ctx = CuratedContext(
            date="2026-01-01", theme="테마", one_liner="한줄",
            selected_stocks=[
                {"ticker": "005930", "name": "삼성전자", "momentum": "상승", "change_pct": 5, "period_days": 5}
            ],
            verified_news=[
                {"title": "뉴스", "url": "https://test.com", "source": "src", "summary": "sum", "published_date": "2026-01-01"}
            ],
            reports=[{"title": "리포트", "source": "src", "summary": "sum", "date": "2026-01-01"}],
            concept={"name": "n", "definition": "d", "relevance": "r"},
            source_ids=["ws1_s1"],
            evidence_source_urls=["https://evidence.com"],
        )
        assert ctx.source_ids == ["ws1_s1"]
        assert ctx.evidence_source_urls == ["https://evidence.com"]

    def test_curated_context_v2_fields_default(self):
        """v1 JSON에 v2 필드 없어도 하위 호환."""
        from interface.schemas import CuratedContext
        ctx = CuratedContext(
            date="2026-01-01", theme="테마", one_liner="한줄",
            selected_stocks=[
                {"ticker": "005930", "name": "삼성전자", "momentum": "상승", "change_pct": 5, "period_days": 5}
            ],
            verified_news=[
                {"title": "뉴스", "url": "https://test.com", "source": "src", "summary": "sum", "published_date": "2026-01-01"}
            ],
            reports=[{"title": "리포트", "source": "src", "summary": "sum", "date": "2026-01-01"}],
            concept={"name": "n", "definition": "d", "relevance": "r"},
        )
        assert ctx.source_ids == []
        assert ctx.evidence_source_urls == []
