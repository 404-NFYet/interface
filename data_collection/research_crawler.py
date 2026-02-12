"""Naver Finance 리포트 크롤링 + PDF OpenAI 요약.

KR 전용: 산업/경제 리포트 목록 스크래핑 → PDF 다운로드 → OpenAI Responses API 요약.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from ..config import (
    OPENAI_API_KEY,
    OPENAI_RESEARCH_MAX_OUTPUT_TOKENS,
    OPENAI_RESEARCH_MODEL,
    RESEARCH_DATA_DIR,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://finance.naver.com/research/"
INDUSTRY_LIST_URL = urljoin(BASE_URL, "industry_list.naver")
ECONOMY_LIST_URL = urljoin(BASE_URL, "economy_list.naver")

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 20
OPENAI_API_URL = "https://api.openai.com/v1/responses"
MAX_PDF_MB = 50
DEFAULT_MAX_WORKERS = 4

# ── PDF 요약 프롬프트 (인라인) ──
_RESEARCH_SUMMARY_PROMPT = """\
You are a Korean financial research analyst. Read the attached PDF report and return ONLY JSON.

**Output JSON keys:** `title`, `summary`, `key_points`, `metrics`, `topics`, `entities`, `risks`, `recommendations`, `language`

- `summary`: 5-8 sentences in Korean
- `key_points`: list of 3-8 bullet strings
- `metrics`: list of objects `{name, value, unit, context}`
- `topics`, `entities`, `risks`, `recommendations`: lists of strings
- Keep the JSON compact and valid. Do not include markdown/code fences.
- `language`: must be `"ko"`

**Report metadata:** {metadata}"""


def _parse_yy_mm_dd(text: str) -> Optional[dt.date]:
    m = re.search(r"(\d{2,4})\.(\d{2})\.(\d{2})", text.strip())
    if not m:
        return None
    year = int(m.group(1))
    if year < 100:
        year += 2000
    try:
        return dt.date(year, int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _fetch_html(url: str) -> str:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "euc-kr"
    return resp.text


def _extract_rows(
    html: str, source: str, base_url: str, target_date: dt.date,
) -> tuple[list[dict], Optional[dt.date]]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table.type_1")
    if not table:
        return [], None

    items: list[dict] = []
    seen_dates: list[dt.date] = []

    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if not tds:
            continue

        if source == "industry":
            if len(tds) < 6:
                continue
            category = tds[0].get_text(strip=True)
            title_td, firm, file_td, date_td = tds[1], tds[2].get_text(strip=True), tds[3], tds[4]
        else:
            if len(tds) < 5:
                continue
            category = None
            title_td, firm, file_td, date_td = tds[0], tds[1].get_text(strip=True), tds[2], tds[3]

        a = title_td.find("a")
        if not a or not a.get("href"):
            continue

        item_date = _parse_yy_mm_dd(date_td.get_text("", strip=True))
        if not item_date:
            continue
        seen_dates.append(item_date)

        if item_date != target_date:
            continue

        pdf_a = file_td.find("a") if file_td else None
        items.append({
            "source": source,
            "category": category,
            "title": a.get_text(strip=True),
            "firm": firm,
            "date": item_date.isoformat(),
            "read_url": urljoin(base_url, a["href"]),
            "pdf_url": pdf_a["href"] if pdf_a and pdf_a.get("href") else None,
        })

    min_date = min(seen_dates) if seen_dates else None
    return items, min_date


def _iter_pages(list_url: str, source: str, target_date: dt.date, max_pages: int = 5) -> list[dict]:
    all_items: list[dict] = []
    for page in range(1, max_pages + 1):
        html = _fetch_html(f"{list_url}?page={page}")
        page_items, min_date = _extract_rows(html, source, BASE_URL, target_date)
        all_items.extend(page_items)
        if min_date is None or min_date < target_date:
            break
    return all_items


def _extract_output_text(response_json: dict) -> str:
    texts: list[str] = []
    for item in response_json.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                texts.append(content["text"])
    return "\n".join(texts).strip()


def _normalize_json_text(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return text
    match = re.search(r"\{[\s\S]*\}", text)
    return match.group(0) if match else text


def _summarize_pdf_bytes(
    pdf_bytes: bytes,
    filename: str,
    metadata: dict,
    api_key: str,
    model: str,
    max_output_tokens: int,
) -> dict:
    file_size_mb = len(pdf_bytes) / (1024 * 1024)
    if file_size_mb > MAX_PDF_MB:
        raise ValueError(f"PDF too large: {file_size_mb:.2f} MB")

    b64 = base64.b64encode(pdf_bytes).decode("utf-8")
    prompt = _RESEARCH_SUMMARY_PROMPT.format(metadata=json.dumps(metadata, ensure_ascii=False))

    payload: dict[str, Any] = {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_file", "filename": filename, "file_data": f"data:application/pdf;base64,{b64}"},
                    {"type": "input_text", "text": prompt},
                ],
            }
        ],
        "text": {"format": {"type": "json_object"}},
        "max_output_tokens": max_output_tokens,
    }

    resp = requests.post(
        OPENAI_API_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=120,
    )
    resp.raise_for_status()
    output_text = _extract_output_text(resp.json())

    normalized = _normalize_json_text(output_text)
    if normalized:
        try:
            parsed = json.loads(normalized)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    preview = (output_text or "").strip()
    return {
        "title": metadata.get("title", ""),
        "summary": preview[:4000] or "(요약 텍스트 없음)",
        "key_points": [],
        "parse_fallback": True,
    }


def crawl_research(
    target_date: dt.date,
    summarize: bool = True,
    api_key: str = "",
    model: str = "",
    max_workers: int = DEFAULT_MAX_WORKERS,
) -> list[dict]:
    """Naver Finance 리포트 크롤링 + PDF 요약.

    Returns:
        요약된 리포트 리스트 [{title, source, summary, date, ...}]
    """
    api_key = api_key or OPENAI_API_KEY
    model = model or OPENAI_RESEARCH_MODEL
    max_output_tokens = OPENAI_RESEARCH_MAX_OUTPUT_TOKENS

    logger.info("[리포트 크롤러] 날짜: %s, 병렬 %d개", target_date, max_workers)

    with ThreadPoolExecutor(max_workers=2) as ex:
        f_ind = ex.submit(_iter_pages, INDUSTRY_LIST_URL, "industry", target_date)
        f_eco = ex.submit(_iter_pages, ECONOMY_LIST_URL, "economy", target_date)
        industry_items = f_ind.result()
        economy_items = f_eco.result()
    all_items = industry_items + economy_items
    logger.info("[리포트 크롤러] 산업 %d건, 경제 %d건", len(industry_items), len(economy_items))

    if not summarize or not api_key:
        return all_items

    summary_dir = RESEARCH_DATA_DIR / target_date.isoformat()
    summary_dir.mkdir(parents=True, exist_ok=True)

    def _summarize_one(item: dict) -> dict:
        if not item.get("pdf_url"):
            return {**item, "summary": "", "summary_status": "skipped_no_pdf"}
        try:
            pdf_resp = requests.get(
                item["pdf_url"], headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT, stream=True,
            )
            pdf_resp.raise_for_status()
            pdf_bytes = pdf_resp.content
            filename = os.path.basename(urlparse(item["pdf_url"]).path) or "report.pdf"
            meta = {k: item[k] for k in ("source", "category", "title", "firm", "date") if k in item}
            summary = _summarize_pdf_bytes(pdf_bytes, filename, meta, api_key, model, max_output_tokens)
            return {**item, **summary, "summary_status": "ok"}
        except Exception as e:
            return {**item, "summary": "", "summary_status": "error", "summary_error": str(e)}

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_summarize_one, item): item for item in all_items}
        for fut in as_completed(futures):
            results.append(fut.result())

    # JSON 저장
    out_path = summary_dir / "all.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("[리포트 크롤러] 완료: %d건 → %s", len(results), out_path)

    return results


def to_report_items(raw_items: list[dict]) -> list[dict]:
    """크롤링 원본을 reports 스키마로 변환."""
    result = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        summary = item.get("summary", "")
        if summary is None:
            summary = ""
        elif isinstance(summary, dict):
            summary = str(summary)
        result.append({
            "title": item.get("title", ""),
            "source": item.get("firm", item.get("source", "")),
            "summary": str(summary),
            "date": item.get("date", ""),
        })
    return result


def load_research(date: str, base_dir: Optional[Path] = None) -> list[dict]:
    """저장된 리포트 JSON 로드 → reports 스키마."""
    base = base_dir or RESEARCH_DATA_DIR
    path = Path(base) / date / "all.json"
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    items = raw if isinstance(raw, list) else raw.get("items", [])
    return to_report_items(items)
