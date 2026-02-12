"""Interface 파이프라인 설정.

환경변수 기반으로 API 키, 모델, 경로를 관리한다.
"""

import os
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

# ── 기본 모델 ──
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "claude-sonnet-4-20250514")
CHART_MODEL = os.getenv("CHART_MODEL", "gpt-4o-mini")

# ── 경로 ──
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", str(Path(__file__).parent / "output")))
PROMPTS_DIR = Path(__file__).parent / "prompts" / "templates"

# ── 색상 팔레트 ──
COLOR_PALETTE = ["#FF6B35", "#004E89", "#1A936F", "#C5D86D", "#8B95A1"]
