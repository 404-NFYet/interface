"""뉴스 RSS 크롤링 + JSON 로딩.

KR: 한경, 매경, 아시아경제, MBN
US: MarketWatch, Yahoo Finance, CNBC
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import re
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import feedparser
import requests
from bs4 import BeautifulSoup

from ..config import MARKET, NEWS_DATA_DIR

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 20

FEEDS_KR = [
    {"id": "hankyung_economy", "name": "Hankyung Economy", "category": "economy", "url": "https://www.hankyung.com/feed/economy"},
    {"id": "hankyung_finance", "name": "Hankyung Finance", "category": "finance", "url": "https://www.hankyung.com/feed/finance"},
    {"id": "hankyung_all", "name": "Hankyung All", "category": "all", "url": "https://www.hankyung.com/feed/all-news"},
    {"id": "mk_economy", "name": "MK Economy", "category": "economy", "url": "https://www.mk.co.kr/rss/30100041/"},
    {"id": "mk_stock", "name": "MK Stock", "category": "stock", "url": "https://www.mk.co.kr/rss/50200011/"},
    {"id": "mk_economy_all", "name": "MK Economy All", "category": "economy_all", "url": "https://www.mk.co.kr/rss/50000001/"},
    {"id": "mk_headline", "name": "MK Headline", "category": "headline", "url": "https://www.mk.co.kr/rss/30000001/"},
    {"id": "asiae_economy", "name": "Asiae Economy", "category": "economy", "url": "http://www.asiae.co.kr/rss/economy.htm"},
    {"id": "asiae_stock", "name": "Asiae Stock", "category": "stock", "url": "http://www.asiae.co.kr/rss/stock.htm"},
    {"id": "asiae_all", "name": "Asiae All", "category": "all", "url": "http://www.asiae.co.kr/rss/all.htm"},
    {"id": "mbn_economy", "name": "MBN Money Economy", "category": "economy", "url": "https://mbnmoney.mbn.co.kr/rss/news/economy"},
    {"id": "mbn_finance", "name": "MBN Money Finance", "category": "finance", "url": "https://mbnmoney.mbn.co.kr/rss/news/finance"},
]

FEEDS_US = [
    {"id": "marketwatch_topstories", "name": "MarketWatch Top Stories", "category": "markets", "url": "https://feeds.content.dowjones.io/public/rss/mw_topstories"},
    {"id": "marketwatch_marketpulse", "name": "MarketWatch Market Pulse", "category": "markets", "url": "https://feeds.content.dowjones.io/public/rss/mw_marketpulse"},
    {"id": "marketwatch_realtime", "name": "MarketWatch Real-time Headlines", "category": "markets", "url": "https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines"},
    {"id": "yahoo_finance_rss", "name": "Yahoo Finance", "category": "finance", "url": "https://finance.yahoo.com/rss/"},
    {"id": "cnbc_markets", "name": "CNBC Markets", "category": "markets", "url": "https://www.cnbc.com/id/100003114/device/rss/rss.html"},
    {"id": "cnbc_technology", "name": "CNBC Technology", "category": "tech", "url": "https://www.cnbc.com/id/19854910/device/rss/rss.html"},
]

# 도메인별 본문 추출 셀렉터
_SELECTORS_BY_DOMAIN: dict[str, list[str]] = {
    "www.hankyung.com": ["div#articletxt", "div.article-body", "div#contents"],
    "hankyung.com": ["div#articletxt", "div.article-body", "div#contents"],
    "www.mk.co.kr": ["div#article_body", "div.article_body", "div#articleBody", "div#content"],
    "mk.co.kr": ["div#article_body", "div.article_body", "div#articleBody", "div#content"],
    "www.asiae.co.kr": ["div#txt_area", "div.news_area", "div#articleBody"],
    "asiae.co.kr": ["div#txt_area", "div.news_area", "div#articleBody"],
    "mbnmoney.mbn.co.kr": ["div#newsContent", "div#article_body", "div.view_cont"],
    "www.marketwatch.com": ["div.article__body", "article.article__body", "div#article-body"],
    "marketwatch.com": ["div.article__body", "article.article__body", "div#article-body"],
    "finance.yahoo.com": ["div.caas-body", "div#mrt-node-YDC-Stream", "article"],
    "www.cnbc.com": ["div.ArticleBody-articleBody", "div.group", "article"],
    "cnbc.com": ["div.ArticleBody-articleBody", "div.group", "article"],
}


def _get_feeds(market: str) -> list[dict]:
    market = market.upper()
    if market == "ALL":
        return FEEDS_KR + FEEDS_US
    return FEEDS_US if market == "US" else FEEDS_KR


def _soup_text(el: Any) -> str:
    if not el:
        return ""
    text = el.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def _clean_summary(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_article_text(url: str) -> str:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    netloc = urlparse(url).netloc.lower()
    for sel in _SELECTORS_BY_DOMAIN.get(netloc, []):
        text = _soup_text(soup.select_one(sel))
        if len(text) >= 200:
            return text

    article = soup.find("article")
    text = _soup_text(article)
    if len(text) >= 200:
        return text

    paragraphs = [_soup_text(p) for p in soup.find_all("p") if _soup_text(p)]
    if paragraphs:
        return _clean_summary(" ".join(paragraphs))

    og_desc = soup.find("meta", attrs={"property": "og:description"})
    if og_desc and og_desc.get("content"):
        return _clean_summary(og_desc["content"])
    return ""


def _entry_date(entry: Any) -> Optional[dt.date]:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    return dt.datetime(*parsed[:6]).date()


def crawl_news(target_date: dt.date, market: str = MARKET) -> list[dict]:
    """RSS 피드에서 target_date 기사를 수집하고 본문 추출.

    Returns:
        원본 뉴스 아이템 리스트 (source_id, title, link, summary, content 등)
    """
    feeds = _get_feeds(market)
    logger.info("[뉴스 수집] 시장: %s, 날짜: %s, 피드 %d개", market, target_date, len(feeds))

    all_items: list[dict] = []
    for feed in feeds:
        try:
            resp = requests.get(feed["url"], headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            parsed = feedparser.parse(resp.content)
        except Exception as e:
            logger.warning("피드 실패 %s: %s", feed["id"], e)
            continue

        for entry in parsed.entries:
            item_date = _entry_date(entry)
            if item_date != target_date:
                continue
            link = entry.get("link", "")
            content = ""
            content_status = "skipped"
            if link:
                try:
                    content = _extract_article_text(link)
                    content_status = "ok" if content else "empty"
                except Exception:
                    content_status = "error"

            all_items.append({
                "source_id": feed["id"],
                "source_name": feed["name"],
                "category": feed["category"],
                "title": entry.get("title", ""),
                "link": link,
                "published": item_date.isoformat() if item_date else None,
                "summary": _clean_summary(entry.get("summary", "")),
                "author": entry.get("author", ""),
                "content": content,
                "content_status": content_status,
            })

    logger.info("[뉴스 수집] 완료: %d건", len(all_items))

    # JSON 저장
    out_dir = NEWS_DATA_DIR / target_date.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "all.json"
    out_path.write_text(json.dumps(all_items, ensure_ascii=False, indent=2), encoding="utf-8")

    return all_items


# ── JSON 로더 (news/YYYY-MM-DD/all.json → NewsItem 스키마) ──

def to_news_items(raw_items: list[dict]) -> list[dict]:
    """크롤링 원본을 verified_news 스키마로 변환."""
    result = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        result.append({
            "title": item.get("title", ""),
            "url": item.get("link", ""),
            "source": item.get("source_name", ""),
            "summary": item.get("summary", ""),
            "published_date": item.get("published", "") or "",
        })
    return result


def load_news(date: str, base_dir: Optional[Path] = None) -> list[dict]:
    """저장된 뉴스 JSON 로드 → verified_news 스키마."""
    base = base_dir or NEWS_DATA_DIR
    path = Path(base) / date / "all.json"
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    items = raw if isinstance(raw, list) else raw.get("items", [])
    return to_news_items(items)
