# Interface 파이프라인

실시간 데이터 수집(뉴스 크롤링, 주가 스크리닝, GPT-5.2 웹서치 큐레이션)부터 최종 브리핑 생성까지 22개 노드로 구성된 LangGraph 파이프라인.

## 목차

- [아키텍처 개요](#아키텍처-개요)
- [디렉토리 구조](#디렉토리-구조)
- [실행 방법](#실행-방법)
- [파이프라인 흐름 상세](#파이프라인-흐름-상세)
- [수정 가이드: 데이터 수집](#수정-가이드-데이터-수집)
- [수정 가이드: Interface 2 (내러티브 생성)](#수정-가이드-interface-2-내러티브-생성)
- [수정 가이드: Interface 3 (최종 조립)](#수정-가이드-interface-3-최종-조립)
- [Pydantic 스키마 계약](#pydantic-스키마-계약)
- [테스트](#테스트)
- [환경 설정](#환경-설정)

---

## 아키텍처 개요

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                          LangGraph StateGraph (22 nodes)                      │
│                                                                              │
│  START → [라우터: --input 유무?]                                              │
│            │                          │                                       │
│          YES (파일 로드)             NO (실시간 데이터 수집, 기본)               │
│            │                          │                                       │
│   ┌────────────────┐    ┌─────────────────────────────────────────┐          │
│   │ load_curated   │    │ crawl_news → crawl_research             │          │
│   │ _context       │    │   → screen_stocks                       │          │
│   └───────┬────────┘    │   → summarize_news → summarize_research │          │
│           │              │   → curate_topics → build_curated_ctx  │          │
│           │              └──────────────┬──────────────────────────┘          │
│           │                             │                                     │
│           └──────── merge point ────────┘                                     │
│                         │                                                     │
│  ┌──────────────────────────────────────────────────────────┐                │
│  │                    Interface 2 (4 nodes)                   │                │
│  │  page_purpose → historical_case → narrative_body           │                │
│  │    → validate_interface2                                    │                │
│  └───────────────────────┬──────────────────────────────────┘                │
│                          │                                                    │
│  ┌───────────────────────────────────────────────────────────────────┐       │
│  │                    Interface 3 (10 nodes)                          │       │
│  │  run_theme → run_pages → hallcheck_pages                           │       │
│  │    → run_glossary → hallcheck_glossary → tone_final                │       │
│  │    → chart_agent → hallcheck_chart                                 │       │
│  │    → collect_sources → assemble_output                             │       │
│  └───────────────────────┬───────────────────────────────────────────┘       │
│                          │                                                    │
│                  briefing_YYYYMMDD.json                                       │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 핵심 설계 원칙

1. **데이터 수집 내장**: `--input` 없이 실행하면 RSS 크롤링 → 주가 스크리닝 → GPT-5.2 웹서치 큐레이션을 자동 수행
2. **2-Phase 요약**: GPT-5 mini Map/Reduce (Phase 1) + GPT-5.2 Web Search (Phase 2) 아키텍처
3. **Pydantic 계약**: 각 인터페이스의 입출력은 `schemas.py`의 Pydantic v2 모델로 강제 검증
4. **LangSmith 트레이싱**: 모든 노드에 `@traceable(metadata={"phase": "...", "step": N})`으로 계층적 추적
5. **mock 백엔드**: API 호출 없이 전체 22노드 파이프라인 구조를 테스트 가능
6. **하위 호환**: `--input`으로 기존 JSON 파일을 전달하면 파일 로드 경로로 동작 (기존 11노드)

---

## 디렉토리 구조

```
interface/
├── __init__.py
├── config.py                      # 환경변수, API 키, 스크리닝/모델 설정
├── schemas.py                     # Pydantic 모델 (데이터 수집 + 3개 인터페이스 계약)
├── graph.py                       # LangGraph StateGraph 정의 (22노드, 라우터)
├── run.py                         # CLI 진입점
│
├── data_collection/               # 데이터 수집 유틸리티 (v2)
│   ├── __init__.py
│   ├── news_crawler.py            # RSS 크롤링 (KR 12 + US 6 피드)
│   ├── research_crawler.py        # Naver Finance 리포트 + PDF 요약
│   ├── screener.py                # FinanceDataReader OHLCV 스크리닝
│   ├── intersection.py            # screened → matched 변환 (v2: narrative 없음)
│   ├── news_summarizer.py         # GPT-5 mini Map/Reduce 요약
│   └── openai_curator.py          # GPT-5.2 Responses API + web_search 큐레이션
│
├── ai/
│   ├── multi_provider_client.py   # OpenAI/Perplexity/Anthropic 통합 클라이언트
│   ├── llm_utils.py              # prompt_loader 연동 + JSON 추출 헬퍼
│   └── tools.py                  # Chart Agent 도구 (DART/ECOS/웹검색)
│
├── prompts/
│   ├── prompt_loader.py           # .md 프롬프트 파싱 (frontmatter + 변수 치환)
│   └── templates/
│       ├── _tone_guide.md         # [공유] 해요체 톤 가이드
│       ├── _chart_skeletons.md    # [공유] Plotly 차트 골격 템플릿
│       ├── page_purpose.md        # [I2-1] theme, one_liner, concept 추출
│       ├── historical_case.md     # [I2-2] 과거 사례 매칭
│       ├── narrative_body.md      # [I2-3] 6단계 내러티브 본문
│       ├── hallucination_check.md # [I2-4] 팩트체크 + validated_interface_2
│       ├── chart_generation.md    # [I3-legacy] viz_hint → Plotly JSON
│       ├── glossary_generation.md # [I3-legacy] 페이지별 용어사전
│       ├── final_hallucination.md # [I3-legacy] 최종 팩트체크 리스트
│       ├── 3_theme.md            # [I3-1] theme + one_liner 정제
│       ├── 3_pages.md            # [I3-2] 6페이지 생성
│       ├── 3_hallcheck_pages.md  # [I3-3] 페이지 팩트체크 (교정형)
│       ├── 3_glossary.md         # [I3-4] 페이지별 용어사전
│       ├── 3_hallcheck_glossary.md # [I3-5] 용어 팩트체크
│       ├── 3_tone_final.md       # [I3-6] 톤 보정 + 병합
│       ├── 3_chart_reasoning.md  # [I3-7] Chart Agent 추론
│       ├── 3_chart_generation.md # [I3-7] Chart Agent 생성
│       └── 3_hallcheck_chart.md  # [I3-8] 차트 팩트체크
│
├── nodes/
│   ├── crawlers.py                # 뉴스/리포트 크롤링 노드 (2개)
│   ├── screening.py               # 주가 스크리닝 노드 (1개)
│   ├── curation.py                # 요약 + 큐레이션 + context 빌드 (4개)
│   ├── interface1.py              # load_curated_context 노드
│   ├── interface2.py              # 4개 노드 + mock 함수
│   ├── interface3.py              # 8개 노드 (theme/pages/hallcheck/glossary/tone/sources/output)
│   └── chart_agent.py             # 2개 노드 (chart_agent + hallcheck_chart)
│
├── output/                        # 생성된 브리핑 JSON
└── tests/
    ├── test_schemas.py            # Pydantic 스키마 검증 (10개 테스트)
    ├── test_nodes.py              # Interface 2/3 노드 테스트 (12개 테스트)
    ├── test_chart_agent.py        # Chart Agent 노드 테스트 (3개 테스트)
    ├── test_data_collection.py    # 데이터 수집 노드 + E2E 테스트 (13개 테스트)
    └── test_data_collection_utils.py  # 유틸리티 단위 테스트 (15개 테스트)
```

---

## 실행 방법

### 사전 요구사항

```bash
pip install pydantic python-dotenv openai anthropic langgraph langsmith \
    FinanceDataReader feedparser beautifulsoup4 tqdm requests
```

### 기본 실행 (실시간 데이터 수집)

```bash
# mock 모드 (API 호출 없이 전체 18노드 구조 검증)
python -m interface.run --backend mock

# live 모드 (실시간 데이터 수집 + LLM 호출)
python -m interface.run --backend live --market KR

# US 시장
python -m interface.run --backend live --market US

# KR + US 통합
python -m interface.run --backend live --market ALL
```

### 파일 로드 모드 (기존 호환)

```bash
# 기존 curated context JSON 파일 사용
python -m interface.run --input path/to/curated.json --backend live

# topics[] 배열이 있는 입력에서 특정 토픽 선택
python -m interface.run --input output/curated_ALL.json --topic-index 2
```

### CLI 옵션

| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `--input` | curated context JSON 경로. **생략하면 실시간 데이터 수집** | `None` |
| `--backend` | `live` / `mock` / `auto` | `auto` |
| `--market` | `KR` / `US` / `ALL` (데이터 수집 모드) | `KR` |
| `--topic-index` | topics[] 배열에서 처리할 인덱스 | `0` |

### 출력

실행 결과는 `interface/output/briefing_YYYYMMDD_HHMMSS.json`에 저장된다.

---

## 파이프라인 흐름 상세

### 22개 노드 실행 순서

```
START
  │
  ├─── [input_path 있음] ──────────────────────────────────────┐
  │                                                              │
  │    [1] load_curated_context  ← JSON 로드 + Pydantic 검증   │
  │         │                                                    │
  │         └───────────────────────────────┐                    │
  │                                         │                    │
  └─── [input_path 없음] ──────────┐       │                    │
                                    │       │                    │
  [1] crawl_news        ← RSS 피드 크롤링 (비치명적)             │
    │                                                            │
  [2] crawl_research    ← Naver Finance 리포트 + PDF 요약        │
    │                                                            │
  [3] screen_stocks     ← FinanceDataReader OHLCV 스크리닝       │
    │                                                            │
  [4] summarize_news    ← GPT-5 mini Map/Reduce 뉴스 요약        │
    │                                                            │
  [5] summarize_research ← GPT-5 mini Map/Reduce 리포트 요약     │
    │                                                            │
  [6] curate_topics     ← GPT-5.2 Web Search 큐레이션            │
    │                                                            │
  [7] build_curated_context ← topics[0] → CuratedContext 변환    │
       │                                                         │
       └───────────── merge point ──────────────────────────────┘
                          │
                          ▼
  [8]  run_page_purpose        ← LLM: theme, one_liner, concept 추출
  [9]  run_historical_case     ← LLM: 과거 사례 매칭
  [10] run_narrative_body      ← LLM: 6단계 내러티브 본문 생성
  [11] validate_interface2     ← LLM: 할루시네이션 체크 + RawNarrative 조립
  [12] run_theme               ← LLM: theme/one_liner 정제
  [13] run_pages               ← LLM: 6페이지 생성 (chart 없음)
  [14] run_hallcheck_pages     ← LLM: 교정형 팩트체크 (validated 반환)
  [15] run_glossary            ← LLM: 페이지별 용어사전
  [16] run_hallcheck_glossary  ← LLM: 용어 팩트체크
  [17] run_tone_final          ← LLM: pages + glossary 병합, 톤 보정
  [18] run_chart_agent         ← LLM: Reasoning → Tool → Plotly 생성
  [19] run_hallcheck_chart     ← LLM: 차트 데이터 팩트체크
  [20] collect_sources         ← 결정론적: 출처 수집 + 차트 소스 병합
  [21] assemble_output         ← 결정론적: Pydantic 검증 + JSON 저장
                          │
                          ▼
                         END
```

### 노드별 상세

| # | 노드 | Phase | LLM | 모델 | 설명 |
|---|------|-------|-----|------|------|
| 1 | crawl_news | data_collection | - | - | RSS 12+6 피드 크롤링, 본문 추출 |
| 2 | crawl_research | data_collection | O | GPT-5 mini | Naver Finance 리포트 PDF 요약 |
| 3 | screen_stocks | data_collection | - | - | FinanceDataReader 4시그널 스크리닝 |
| 4 | summarize_news | data_collection | O | GPT-5 mini | Map/Reduce 뉴스 청크 요약 |
| 5 | summarize_research | data_collection | O | GPT-5 mini | Map/Reduce 리포트 청크 요약 |
| 6 | curate_topics | data_collection | O | GPT-5.2 | Web Search + strict JSON schema |
| 7 | build_curated_context | data_collection | - | - | topics → CuratedContext 변환 |
| 8 | run_page_purpose | interface_2 | O | Claude Sonnet | theme, one_liner, concept |
| 9 | run_historical_case | interface_2 | O | Claude Sonnet | 과거 사례 매칭 |
| 10 | run_narrative_body | interface_2 | O | Claude Sonnet | 6단계 내러티브 |
| 11 | validate_interface2 | interface_2 | O | Claude Sonnet | 팩트체크 + 조립 |
| 12 | run_theme | interface_3 | O | Claude Sonnet | theme/one_liner 정제 |
| 13 | run_pages | interface_3 | O | Claude Sonnet | 6페이지 생성 |
| 14 | run_hallcheck_pages | interface_3 | O | Claude Sonnet | 교정형 팩트체크 |
| 15 | run_glossary | interface_3 | O | Claude Sonnet | 페이지별 용어사전 |
| 16 | run_hallcheck_glossary | interface_3 | O | Claude Sonnet | 용어 팩트체크 |
| 17 | run_tone_final | interface_3 | O | Claude Sonnet | 톤 보정 + 병합 |
| 18 | run_chart_agent | interface_3 | O | GPT-5 mini | Reasoning → Tool → Plotly |
| 19 | run_hallcheck_chart | interface_3 | O | GPT-5 mini | 차트 데이터 검증 |
| 20 | collect_sources | interface_3 | - | - | 출처 매칭 + 차트 소스 병합 |
| 21 | assemble_output | interface_3 | - | - | Pydantic 검증 + JSON 저장 |

### LangSmith 트레이싱 구조

모든 노드에 `metadata={"phase": "...", "phase_name": "...", "step": N}`이 설정되어 있어 LangSmith UI에서 phase별 필터링이 가능하다:

```
Pipeline Run
├── [phase: data_collection] 데이터 수집 (step 1~7)
├── [phase: interface_2] 내러티브 생성 (step 1~4)
└── [phase: interface_3] 최종 조립 (step 1~10)
```

---

## 수정 가이드: 데이터 수집

데이터 수집은 `data_collection/` 모듈과 `nodes/crawlers.py`, `nodes/screening.py`, `nodes/curation.py`로 구성된다.

### 주가 스크리닝 파라미터

**수정 파일**: `config.py` 또는 `.env`

| 환경변수 | 설명 | 기본값 |
|----------|------|--------|
| `MARKET` | 스크리닝 대상 시장 | `KR` |
| `SHORT_TERM_DAYS` | 단기 급등/급락 판별 기간 | `5` |
| `SHORT_TERM_RETURN_MIN` | 단기 수익률 임계치 (%) | `5` |
| `MID_TERM_FORMATION_MONTHS` | 중장기 형성 기간 | `6` |
| `VOLUME_RATIO_MIN` | 비정상 거래량 비율 | `1.5` |
| `TOP_N` | 최대 스크리닝 종목 수 | `20` |
| `SCAN_LIMIT` | 스캔 대상 종목 수 | `500` |

### 뉴스 소스 추가/변경

**수정 파일**: `data_collection/news_crawler.py`

- `FEEDS_KR` / `FEEDS_US`: RSS 피드 목록 수정
- `_SELECTORS_BY_DOMAIN`: 본문 추출 CSS 셀렉터 추가

### Phase 1 모델 설정 (요약)

| 환경변수 | 설명 | 기본값 |
|----------|------|--------|
| `OPENAI_PHASE1_MODEL` | Map/Reduce 요약 모델 | `gpt-5-mini` |
| `OPENAI_PHASE1_TEMPERATURE` | 요약 temperature | `0.3` |
| `OPENAI_PHASE1_MAX_COMPLETION_TOKENS` | 청크당 최대 토큰 | `3000` |
| `OPENAI_PHASE1_CHUNK_TARGET_INPUT_TOKENS` | 청크 타겟 입력 토큰 | `3200` |

> GPT-5 모델은 temperature 커스텀을 지원하지 않을 수 있음. 코드에서 자동으로 fallback 처리.

### Phase 2 모델 설정 (큐레이션)

| 환경변수 | 설명 | 기본값 |
|----------|------|--------|
| `OPENAI_PHASE2_MODEL` | 웹서치 큐레이션 모델 | `gpt-5.2` |
| `OPENAI_PHASE2_TEMPERATURE` | 큐레이션 temperature | `0.2` |
| `OPENAI_PHASE2_MAX_OUTPUT_TOKENS` | 큐레이션 최대 출력 토큰 | `10000` |

### 큐레이션 출력 v2 필드

`CuratedContext`에 v2 전용 필드가 추가됨:

```python
source_ids: list[str]              # 웹서치 출처 ID (ws1_s1 형식)
evidence_source_urls: list[str]    # 근거 URL 목록
```

→ `default_factory=list`로 하위 호환 유지 (v1 JSON에 없어도 OK)

---

## 수정 가이드: Interface 2 (내러티브 생성)

Interface 2는 4단계 LLM 파이프라인이다. 각 단계의 출력이 다음 단계의 입력이 된다.

```
curated_context
    │
    ▼
[Stage 1] page_purpose.md  → { theme, one_liner, concept }
    │
    ▼
[Stage 2] historical_case.md  → { historical_case: { period, title, summary, outcome, lesson } }
    │
    ▼
[Stage 3] narrative_body.md  → { narrative: { background, concept_explain, history, application, caution, summary } }
    │
    ▼
[Stage 4] hallucination_check.md  → { validated_interface_2: { theme, one_liner, concept, historical_case, narrative } }
```

### Stage별 수정 방법

| Stage | 수정 파일 | 주요 수정 포인트 |
|-------|----------|-----------------|
| 1 | `page_purpose.md` | theme 스타일, one_liner 형식, concept 선정 기준 |
| 2 | `historical_case.md` | 사례 시기 범위, summary 구조, lesson 포맷 |
| 3 | `narrative_body.md` | 섹션별 분량, bullets 개수, viz_hint 스타일 |
| 4 | `hallucination_check.md` | 검증 강도, 투자 표현 필터, overall_risk 기준 |

### 6단계 구조 변경 시 파급 범위

6단계를 7단계나 5단계로 바꾸려면 아래 **모든 파일**을 수정해야 한다:

```
prompts/templates/narrative_body.md   ← 프롬프트 섹션 목록 + 출력 스키마
schemas.py → NarrativeBody            ← 필드 추가/삭제
nodes/interface3.py → SECTION_MAP     ← (step, title, section_key) 매핑
```

---

## 수정 가이드: Interface 3 (최종 조립)

Interface 3은 10노드 순차 파이프라인이다:

```
validated_interface_2
  → run_theme → run_pages → hallcheck_pages
  → run_glossary → hallcheck_glossary → tone_final
  → chart_agent → hallcheck_chart
  → collect_sources → assemble_output → END
```

### 프롬프트 수정

| 노드 | 프롬프트 | 주요 수정 포인트 |
|------|---------|-----------------|
| run_theme | `3_theme.md` | theme 형식, one_liner 훅 스타일 |
| run_pages | `3_pages.md` | 페이지별 작성 원칙, 톤 규칙 |
| hallcheck_pages | `3_hallcheck_pages.md` | 검증 강도, overall_risk 기준 |
| run_glossary | `3_glossary.md` | 용어 선별 기준, 난이도 수준 |
| hallcheck_glossary | `3_hallcheck_glossary.md` | 정의 검증 기준 |
| tone_final | `3_tone_final.md` | 톤 보정 규칙, 병합 구조 |

### Chart Agent

Chart Agent는 3단계 에이전트 루프를 실행한다:

1. **Reasoning** (`3_chart_reasoning.md`): viz_hint 분석 → 차트 유형 선택 → 도구 호출 계획
2. **Tool Execution**: DART 재무제표 / ECOS 환율 / 웹검색 도구 실행
3. **Generation** (`3_chart_generation.md`): 도구 결과 + 문맥 → Plotly JSON 생성

도구 수정: `ai/tools.py`
노드 수정: `nodes/chart_agent.py`

| 수정 목적 | 수정 위치 |
|-----------|----------|
| 차트 유형 가이드 | `3_chart_reasoning.md` |
| Plotly 스타일/색상 | `3_chart_generation.md`, `config.py` → `COLOR_PALETTE` |
| 도구 추가 | `ai/tools.py` + `chart_agent.py` → `AVAILABLE_TOOLS` |
| Chart Agent 모델 | `3_chart_*.md` frontmatter 또는 `CHART_AGENT_MODEL` |

### 출처(sources) 수집

**수정 파일**: `nodes/interface3.py` → `collect_sources_node`

결정론적 노드. 키워드 기반 매칭 알고리즘 + chart_agent 소스 병합.

---

## Pydantic 스키마 계약

### 전체 구조

```
FullBriefingOutput
├── topic: str
├── interface_1_curated_context: CuratedContext
│   ├── date, theme, one_liner
│   ├── selected_stocks: list[StockItem]
│   ├── verified_news: list[NewsItem]
│   ├── reports: list[ReportItem]
│   ├── concept: Concept
│   ├── source_ids: list[str]              ← v2
│   └── evidence_source_urls: list[str]    ← v2
├── interface_2_raw_narrative: RawNarrative
│   ├── theme, one_liner
│   ├── concept: Concept
│   ├── historical_case: HistoricalCase
│   └── narrative: NarrativeBody (6 sections)
└── interface_3_final_briefing: FinalBriefing
    ├── theme, one_liner, generated_at
    ├── pages: list[Page]
    ├── sources: list[SourceItem]
    └── hallucination_checklist: list[HallucinationItem]
```

### 데이터 수집 중간 타입

```
ScreenedStockItem    # 스크리너 출력 (symbol, signal, return_pct, volume_ratio)
MatchedStockItem     # 교집합 출력 (v2: narrative 없음, has_narrative=False)
```

### 스키마 변경 시 체크리스트

1. `schemas.py`에서 Pydantic 모델 수정
2. 관련 프롬프트의 `## 출력 스키마` 섹션 업데이트
3. 관련 노드의 mock 함수 업데이트
4. `tests/` 실행하여 검증
5. 하위 호환 필요 시 `Optional` 또는 `Field(default_factory=...)` 사용

---

## 테스트

```bash
# 전체 테스트 (53개)
python -m pytest interface/tests/ -v

# 데이터 수집 노드 테스트
python -m pytest interface/tests/test_data_collection.py -v

# 유틸리티 단위 테스트
python -m pytest interface/tests/test_data_collection_utils.py -v

# 기존 스키마/노드 테스트
python -m pytest interface/tests/test_schemas.py interface/tests/test_nodes.py -v

# Chart Agent 테스트
python -m pytest interface/tests/test_chart_agent.py -v

# E2E mock 테스트 (22노드 파이프라인)
python -m interface.run --backend mock

# E2E mock 테스트 (파일 로드 모드)
python -m interface.run --input path/to/curated.json --backend mock
```

### 테스트 구성 (53개)

| 테스트 파일 | 테스트 수 | 검증 대상 |
|------------|----------|----------|
| `test_schemas.py` | 10 | Pydantic 스키마 검증 + Quiz + roundtrip |
| `test_nodes.py` | 12 | Interface 2/3 노드 mock 테스트 (10노드) |
| `test_chart_agent.py` | 3 | Chart Agent + hallcheck 노드 |
| `test_data_collection.py` | 13 | 크롤러/스크리닝/큐레이션 노드 + E2E |
| `test_data_collection_utils.py` | 15 | intersection, summarizer, crawler 유틸 |

---

## 환경 설정

### 초기 설정

```bash
cp .env.example .env
# .env 파일에 실제 API 키 입력
```

### 필수 환경변수

| 변수 | 설명 | 용도 |
|------|------|------|
| `OPENAI_API_KEY` | OpenAI API 키 | 데이터 수집 (Phase 1/2), 차트/용어 생성 |
| `CLAUDE_API_KEY` | Anthropic API 키 | 내러티브 생성, 팩트체크 |

### 선택 환경변수 (Chart Agent)

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `DART_API_KEY` | DART 재무제표 API 키 | (미설정 시 mock) |
| `ECOS_API_KEY` | 한국은행 ECOS 환율 API 키 | (미설정 시 mock) |
| `CHART_AGENT_MODEL` | Chart Agent 추론/생성 모델 | `gpt-5-mini` |

### 기타 선택 환경변수

<details>
<summary>LangSmith (관측성)</summary>

| 변수 | 기본값 |
|------|--------|
| `LANGCHAIN_TRACING_V2` | `true` |
| `LANGCHAIN_API_KEY` | - |
| `LANGCHAIN_PROJECT` | `adelie-pipeline` |

</details>

<details>
<summary>모델 설정</summary>

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `DEFAULT_MODEL` | `claude-sonnet-4-20250514` | Interface 2/3 내러티브 |
| `CHART_MODEL` | `gpt-4o-mini` | 차트/용어 생성 |
| `OPENAI_PHASE1_MODEL` | `gpt-5-mini` | Map/Reduce 요약 |
| `OPENAI_PHASE2_MODEL` | `gpt-5.2` | 웹서치 큐레이션 |
| `OPENAI_RESEARCH_MODEL` | `gpt-5-mini` | PDF 요약 |

</details>

<details>
<summary>스크리닝 파라미터</summary>

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `MARKET` | `KR` | 스크리닝 시장 |
| `SHORT_TERM_DAYS` | `5` | 단기 판별 기간 |
| `SHORT_TERM_RETURN_MIN` | `5` | 단기 수익률 임계치 (%) |
| `MID_TERM_FORMATION_MONTHS` | `6` | 중장기 형성 기간 |
| `VOLUME_RATIO_MIN` | `1.5` | 비정상 거래량 비율 |
| `TOP_N` | `20` | 최대 스크리닝 종목 수 |
| `SCAN_LIMIT` | `500` | 스캔 대상 종목 수 |

</details>

전체 환경변수 목록은 `.env.example` 참조.

### 프롬프트 모델/프로바이더 오버라이드

각 프롬프트의 frontmatter에서 개별 설정 가능:

```yaml
---
provider: anthropic
model: claude-sonnet-4-20250514
temperature: 0.3
response_format: json_object
---
```
