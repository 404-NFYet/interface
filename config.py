"""Interface 파이프라인 설정.

환경변수 기반으로 API 키, 모델, 경로를 관리한다.
"""

import os
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

INTERFACE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = INTERFACE_DIR.parent

# interface/.env 우선, 없으면 프로젝트 루트 .env
load_dotenv(INTERFACE_DIR / ".env", override=True)
load_dotenv(PROJECT_ROOT / ".env", override=False)

# ── API Keys ──
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("CLAUDE_API_KEY", "")
DART_API_KEY = os.getenv("DART_API_KEY", "")
ECOS_API_KEY = os.getenv("ECOS_API_KEY", "")

# ── 기본 모델 (Interface 2/3 내러티브 생성) ──
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "claude-sonnet-4-20250514")
CHART_MODEL = os.getenv("CHART_MODEL", "gpt-4o-mini")
CHART_AGENT_MODEL = os.getenv("CHART_AGENT_MODEL", "gpt-5-mini")

# ── 경로 ──
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", str(Path(__file__).parent / "output")))
PROMPTS_DIR = Path(__file__).parent / "prompts" / "templates"

# ── 색상 팔레트 ──
COLOR_PALETTE = ["#FF6B35", "#004E89", "#1A936F", "#C5D86D", "#8B95A1"]

# ── Interface 3 섹션 매핑 (interface3.py + chart_agent.py 공유) ──
SECTION_MAP = [
    (1, "현재 배경", "background"),
    (2, "금융 개념 설명", "concept_explain"),
    (3, "과거 비슷한 사례", "history"),
    (4, "현재 상황에 적용", "application"),
    (5, "주의해야 할 점", "caution"),
    (6, "최종 정리", "summary"),
]

# ═══════════════════════════════════════════
# Data Collection 설정
# ═══════════════════════════════════════════

# ── 시장 ──
MARKET = os.getenv("MARKET", "KR")

# ── 가격 변동 스크리닝 ──
SHORT_TERM_DAYS = int(os.getenv("SHORT_TERM_DAYS", "5"))
SHORT_TERM_RETURN_MIN = float(os.getenv("SHORT_TERM_RETURN_MIN", "5"))
TRADING_DAYS_PER_MONTH = 21
MID_TERM_FORMATION_MONTHS = int(os.getenv("MID_TERM_FORMATION_MONTHS", "6"))
MID_TERM_SKIP_MONTHS = int(os.getenv("MID_TERM_SKIP_MONTHS", "1"))
MID_TERM_FORMATION_DAYS = MID_TERM_FORMATION_MONTHS * TRADING_DAYS_PER_MONTH
MID_TERM_SKIP_DAYS = MID_TERM_SKIP_MONTHS * TRADING_DAYS_PER_MONTH
MID_TERM_TOTAL_DAYS = MID_TERM_FORMATION_DAYS + MID_TERM_SKIP_DAYS
MID_TERM_RETURN_MIN = float(os.getenv("MID_TERM_RETURN_MIN", "5"))
VOLUME_RATIO_MIN = float(os.getenv("VOLUME_RATIO_MIN", "1.5"))
TOP_N = int(os.getenv("TOP_N", "20"))
SCAN_LIMIT = int(os.getenv("SCAN_LIMIT", "500"))

# ── Phase 1: GPT-5 mini Map/Reduce 요약 ──
OPENAI_PHASE1_MODEL = os.getenv("OPENAI_PHASE1_MODEL", "gpt-5-mini")
OPENAI_PHASE1_TEMPERATURE = float(os.getenv("OPENAI_PHASE1_TEMPERATURE", "0.3"))
OPENAI_PHASE1_MAX_COMPLETION_TOKENS = int(os.getenv("OPENAI_PHASE1_MAX_COMPLETION_TOKENS", "3000"))
OPENAI_PHASE1_CHUNK_TARGET_INPUT_TOKENS = int(os.getenv("OPENAI_PHASE1_CHUNK_TARGET_INPUT_TOKENS", "3200"))
OPENAI_PHASE1_SUMMARY_MAX_RETRIES = int(os.getenv("OPENAI_PHASE1_SUMMARY_MAX_RETRIES", "1"))

# ── Phase 2: GPT-5.2 Web Search 큐레이션 ──
OPENAI_PHASE2_MODEL = os.getenv("OPENAI_PHASE2_MODEL", "gpt-5.2")
OPENAI_PHASE2_TEMPERATURE = float(os.getenv("OPENAI_PHASE2_TEMPERATURE", "0.2"))
OPENAI_PHASE2_MAX_OUTPUT_TOKENS = int(os.getenv("OPENAI_PHASE2_MAX_OUTPUT_TOKENS", "10000"))

# ── Research PDF 요약 ──
OPENAI_RESEARCH_MODEL = os.getenv("OPENAI_RESEARCH_MODEL", "gpt-5-mini")
OPENAI_RESEARCH_TEMPERATURE = float(os.getenv("OPENAI_RESEARCH_TEMPERATURE", "0.3"))
OPENAI_RESEARCH_MAX_OUTPUT_TOKENS = int(os.getenv("OPENAI_RESEARCH_MAX_OUTPUT_TOKENS", "2400"))

# ── Curation ──
CURATED_TOPICS_MAX = int(os.getenv("CURATED_TOPICS_MAX", "5"))
SELECTED_STOCKS_MAX = int(os.getenv("SELECTED_STOCKS_MAX", "10"))

# ── 데이터 경로 ──
NEWS_DATA_DIR = Path(os.getenv("NEWS_DATA_DIR", str(INTERFACE_DIR / "data" / "news")))
RESEARCH_DATA_DIR = Path(os.getenv("RESEARCH_DATA_DIR", str(INTERFACE_DIR / "data" / "research")))


def get_price_period() -> tuple[str, str]:
    """가격 데이터 수집에 필요한 기간 (start, end) 반환."""
    end = datetime.now()
    cal_days_needed = int(MID_TERM_TOTAL_DAYS / 0.7) + 30
    start = end - timedelta(days=cal_days_needed)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
