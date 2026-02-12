# Interface 파이프라인

3개 인터페이스를 LangGraph로 연결하여 `golden_case/03_k_defense.json`과 동일한 구조의 최종 브리핑 JSON을 생성한다.

## 목차

- [아키텍처 개요](#아키텍처-개요)
- [디렉토리 구조](#디렉토리-구조)
- [실행 방법](#실행-방법)
- [파이프라인 흐름 상세](#파이프라인-흐름-상세)
- [수정 가이드: Interface 1 (데이터 수집)](#수정-가이드-interface-1-데이터-수집)
- [수정 가이드: Interface 2 (내러티브 생성)](#수정-가이드-interface-2-내러티브-생성)
- [수정 가이드: Interface 3 (최종 조립)](#수정-가이드-interface-3-최종-조립)
- [Pydantic 스키마 계약](#pydantic-스키마-계약)
- [테스트](#테스트)
- [환경 설정](#환경-설정)

---

## 아키텍처 개요

```
┌─────────────────────────────────────────────────────────────────────┐
│                        LangGraph StateGraph                        │
│                                                                     │
│  ┌──────────┐   ┌──────────────────────────────────────────────┐   │
│  │Interface 1│   │              Interface 2                     │   │
│  │  (로드)   │──▶│ page_purpose → historical_case → narrative  │   │
│  │          │   │             → hallucination_check             │   │
│  └──────────┘   └──────────────────────┬───────────────────────┘   │
│                                        │                            │
│                                        ▼                            │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                      Interface 3                             │   │
│  │ build_charts → build_glossary → assemble_pages              │   │
│  │ → collect_sources → final_hallucination → assemble_output   │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                        │                            │
│                                        ▼                            │
│                              briefing_YYYYMMDD.json                 │
└─────────────────────────────────────────────────────────────────────┘
```

### 핵심 설계 원칙

1. **Pydantic 계약**: 각 인터페이스의 입출력은 `schemas.py`의 Pydantic v2 모델로 강제 검증된다
2. **LangGraph 노드**: 각 단계는 독립 노드이며 `@traceable`로 LangSmith 추적이 가능하다
3. **mock 백엔드**: LLM 호출 없이 전체 파이프라인 구조를 테스트할 수 있다
4. **prompt_loader**: frontmatter 메타데이터(provider/model/temperature)와 `{{variable}}` 치환을 지원한다

---

## 디렉토리 구조

```
interface/
├── __init__.py
├── config.py                      # 환경변수, API 키, 경로 설정
├── schemas.py                     # Pydantic 모델 (3개 인터페이스 계약)
├── graph.py                       # LangGraph StateGraph 정의
├── run.py                         # CLI 진입점
│
├── ai/
│   ├── multi_provider_client.py   # OpenAI/Perplexity/Anthropic 통합 클라이언트
│   └── llm_utils.py              # prompt_loader 연동 + JSON 추출 헬퍼
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
│       ├── chart_generation.md    # [I3] viz_hint → Plotly JSON
│       ├── glossary_generation.md # [I3] 페이지별 용어사전
│       └── final_hallucination.md # [I3] 최종 팩트체크 리스트
│
├── nodes/
│   ├── interface1.py              # load_curated_context 노드
│   ├── interface2.py              # 4개 노드 + mock 함수
│   └── interface3.py              # 6개 노드 + mock 함수
│
├── output/                        # 생성된 브리핑 JSON
└── tests/
    ├── test_schemas.py            # Pydantic 스키마 검증 (8개 테스트)
    └── test_nodes.py              # 노드 단위 테스트 (8개 테스트)
```

---

## 실행 방법

### 사전 요구사항

```bash
pip install pydantic python-dotenv openai anthropic langgraph langsmith
```

### 기본 실행

```bash
# mock 모드 (LLM 호출 없이 구조 검증)
python -m interface.run --input golden_case/03_k_defense.json --backend mock

# live 모드 (실제 LLM 호출)
python -m interface.run --input golden_case/03_k_defense.json --backend live

# auto 모드 (API 키 유무로 자동 결정, 기본값)
python -m interface.run --input golden_case/03_k_defense.json

# data-gen 출력 파일 사용 (topics[] 배열이 있는 경우)
python -m interface.run --input data-gen/output/curated_ALL_xxx.json --topic-index 0
```

### CLI 옵션

| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `--input` | Interface 1 결과 JSON 파일 경로 | (필수) |
| `--backend` | `live` / `mock` / `auto` | `auto` |
| `--topic-index` | topics[] 배열에서 처리할 인덱스 | `0` |

### 출력

실행 결과는 `interface/output/briefing_YYYYMMDD_HHMMSS.json`에 저장된다.

---

## 파이프라인 흐름 상세

### 11개 노드 실행 순서

```
START
  │
  ▼
[1] load_curated_context    ← Interface 1 JSON 로드 + Pydantic 검증
  │
  ▼
[2] run_page_purpose        ← LLM: theme, one_liner, concept 추출
  │
  ▼
[3] run_historical_case     ← LLM: 과거 사례 매칭
  │
  ▼
[4] run_narrative_body      ← LLM: 6단계 내러티브 본문 생성
  │
  ▼
[5] validate_interface2     ← LLM: 할루시네이션 체크 + RawNarrative 조립
  │
  ▼
[6] build_charts            ← LLM: viz_hint → Plotly JSON (섹션별)
  │
  ▼
[7] build_glossary          ← LLM: 페이지별 용어사전 (중복 제거)
  │
  ▼
[8] assemble_pages          ← 결정론적: 6페이지 조립 (chart + glossary 병합)
  │
  ▼
[9] collect_sources         ← 결정론적: verified_news + reports에서 출처 추출
  │
  ▼
[10] run_final_check        ← LLM: 최종 할루시네이션 체크리스트
  │
  ▼
[11] assemble_output        ← 결정론적: FullBriefingOutput 조립 + JSON 저장
  │
  ▼
END
```

### 노드별 LLM 사용 여부

| 노드 | 타입 | LLM 호출 | 프롬프트 |
|------|------|----------|----------|
| load_curated_context | tool | - | - |
| run_page_purpose | llm | O | `page_purpose.md` |
| run_historical_case | llm | O | `historical_case.md` |
| run_narrative_body | llm | O | `narrative_body.md` |
| validate_interface2 | llm | O | `hallucination_check.md` |
| build_charts | llm | O (섹션당 1회) | `chart_generation.md` |
| build_glossary | llm | O (섹션당 1회) | `glossary_generation.md` |
| assemble_pages | tool | - | - |
| collect_sources | tool | - | - |
| run_final_check | llm | O | `final_hallucination.md` |
| assemble_output | tool | - | - |

---

## 수정 가이드: Interface 1 (데이터 수집)

Interface 1은 파이프라인 **외부**에서 실행되며, 결과 JSON을 `--input`으로 전달받는다.

### 입력 JSON 스키마

Interface 1은 아래 `CuratedContext` 형태를 출력해야 한다:

```json
{
  "interface_1_curated_context": {
    "date": "2026-02-11",
    "theme": "핵심 주제 문장",
    "one_liner": "한줄 요약 (해요체)",
    "selected_stocks": [
      {"ticker": "012450", "name": "한화에어로스페이스", "momentum": "급등", "change_pct": 198.5, "period_days": 365}
    ],
    "verified_news": [
      {"title": "뉴스 제목", "url": "https://...", "source": "한국경제", "summary": "요약", "published_date": "2026-02-10"}
    ],
    "reports": [
      {"title": "리포트 제목", "source": "NH투자증권", "summary": "요약", "date": "2026-02-10"}
    ],
    "concept": {
      "name": "PER(주가수익비율)",
      "definition": "쉬운 정의",
      "relevance": "현재 이슈와의 연결"
    }
  }
}
```

### 데이터 수집 코드 수정 방법

| 수정 목적 | 수정 대상 | 설명 |
|-----------|----------|------|
| 주식 필터 기준 변경 | `data-gen/` | 거래대금, 등락률, 기간 등 필터 조건 수정 |
| 뉴스 소스 추가/변경 | `data-gen/` | RSS 피드 URL, 크롤링 대상 변경 |
| 리포트 소스 추가 | `data-gen/` | 증권사 리포트 수집 로직 변경 |
| concept 선택 로직 | `data-gen/` | 자동 개념 선택 알고리즘 변경 |
| **스키마 필드 추가** | `schemas.py` → `CuratedContext` | 필드 추가 후 `interface1.py` 노드도 수정 |

### 스키마 변경 시 파급 범위

`CuratedContext`에 필드를 추가하면 아래 파일을 확인해야 한다:

```
schemas.py              ← CuratedContext 모델 수정
nodes/interface1.py     ← 검증 로직 (자동으로 Pydantic이 처리)
nodes/interface2.py     ← curated_context를 프롬프트 변수로 전달하므로, LLM이 새 필드를 활용
nodes/interface3.py     ← collect_sources_node에서 curated_context 참조
```

**예시: `macro_indicators` 필드 추가**

```python
# schemas.py
class MacroIndicator(BaseModel):
    name: str
    value: float
    unit: str

class CuratedContext(BaseModel):
    ...
    macro_indicators: list[MacroIndicator] = Field(default_factory=list)  # 신규
```

→ 기존 JSON에 `macro_indicators`가 없어도 `default_factory=list` 덕분에 하위 호환된다.

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

#### Stage 1: theme / one_liner / concept 품질 개선

**수정 파일**: `prompts/templates/page_purpose.md`

| 수정 목적 | 수정 위치 | 방법 |
|-----------|----------|------|
| theme 문장 스타일 변경 | `## 생성 목표` → `1. theme` | "변화의 방향성" 대신 원하는 스타일 지시어 수정 |
| one_liner 질문형 강제 해제 | `## 생성 목표` → `2. one_liner` | "질문형 훅을 권장해요" 부분 수정 |
| concept 선정 기준 강화 | `## 생성 목표` → `3. concept` | "반드시 1개" 조건이나 난이도 기준 수정 |
| 모델 변경 | frontmatter `model:` | `claude-sonnet-4-20250514` → 원하는 모델 |
| temperature 조정 | frontmatter `temperature:` | 0.3 (보수적) ~ 0.7 (창의적) |

**예시: one_liner를 서술형으로 변경**

```markdown
2. `one_liner`
- 독자가 바로 이해할 수 있는 핵심 요약을 작성해요.
- 질문형보다는 서술형으로 작성해요.
- "A가 B를 바꾸고 있어요" 형식을 권장해요.
```

#### Stage 2: 과거 사례 매칭 정확도 개선

**수정 파일**: `prompts/templates/historical_case.md`

| 수정 목적 | 수정 위치 | 방법 |
|-----------|----------|------|
| 사례 시기 범위 제한 | `## 생성 원칙` | "최근 10년 이내 사례만" 등 조건 추가 |
| summary 구조 변경 | `## 생성 원칙` → `3` | "원인 → 전개 → 시차 → 결과" 흐름 커스텀 |
| lesson 포맷 강화 | `## 생성 원칙` → `5` | 프레임워크 대신 "현재 적용 가능한 지표" 등으로 변경 |

#### Stage 3: 6단계 내러티브 본문 개선

**수정 파일**: `prompts/templates/narrative_body.md`

이 프롬프트가 **최종 콘텐츠 품질에 가장 큰 영향**을 미친다.

| 수정 목적 | 수정 위치 | 방법 |
|-----------|----------|------|
| 섹션별 분량 조절 | `## 섹션별 작성 원칙` | 각 섹션 지시에 "300자 이내" 등 분량 제약 추가 |
| bullets 개수 변경 | `## 출력 규칙` → `4` | "2~3개" → "2~4개" 등 |
| viz_hint 스타일 지정 | `## 섹션별 작성 원칙` | "viz_hint는 'chart_type - 설명' 형태로" 등 |
| caution 톤 조절 | `### 5) caution` | "균형 있게" → "더 강하게 경고" 등 |
| summary 관찰 포인트 형식 | `### 6) summary` | "지표 3가지" → "질문 3가지" 등으로 변경 |
| **6단계 구조 자체를 변경** | `## 생성 대상` + `## 출력 스키마` | 섹션 추가/삭제 시 스키마도 함께 변경 필요 (아래 참고) |

**6단계 구조 변경 시 파급 범위** (중요):

6단계를 7단계나 5단계로 바꾸려면 아래 **모든 파일**을 수정해야 한다:

```
prompts/templates/narrative_body.md   ← 프롬프트 섹션 목록 + 출력 스키마
schemas.py → NarrativeBody            ← 필드 추가/삭제
nodes/interface3.py → SECTION_MAP     ← (step, title, section_key) 매핑
nodes/interface3.py → assemble_pages  ← 페이지 조립 로직
```

#### Stage 4: 할루시네이션 체크 강화

**수정 파일**: `prompts/templates/hallucination_check.md`

| 수정 목적 | 수정 위치 | 방법 |
|-----------|----------|------|
| 검증 강도 강화 | `## 검증 원칙` | "수치 오차 5% 이상이면 warning" 등 구체적 기준 추가 |
| 투자 표현 필터 강화 | `## 검증 원칙` → `4` | 금지 표현 리스트 확대 |
| overall_risk 기준 변경 | `## overall_risk 규칙` | critical 판정 기준 조정 |

#### Interface 2 전체에 영향을 주는 공통 수정

| 수정 목적 | 수정 파일 | 방법 |
|-----------|----------|------|
| 전체 모델 변경 | 4개 프롬프트의 frontmatter `model:` | 일괄 변경 |
| 톤/문체 변경 | `_tone_guide.md` | 해요체 규칙, 금지 어미 등 수정 |
| 프로바이더 변경 | 4개 프롬프트의 frontmatter `provider:` | `anthropic` → `openai` 등 |
| mock 응답 수정 | `nodes/interface2.py` | `_mock_*` 함수들 수정 |
| 노드 로직 변경 | `nodes/interface2.py` | 노드 함수에서 변수 전달 방식 커스텀 |

---

## 수정 가이드: Interface 3 (최종 조립)

Interface 3은 `interface_2_raw_narrative`를 받아 최종 6페이지 브리핑을 만든다.

```
raw_narrative
    │
    ├──▶ [build_charts]     viz_hint → Plotly JSON
    │
    ├──▶ [build_glossary]   content → 용어사전
    │
    ▼
[assemble_pages]     narrative + charts + glossary → 6 pages
    │
    ▼
[collect_sources]    verified_news + reports → sources
    │
    ▼
[run_final_check]    pages → hallucination_checklist
    │
    ▼
[assemble_output]    FullBriefingOutput JSON 저장
```

### 차트 생성 수정

**수정 파일**: `prompts/templates/chart_generation.md`

| 수정 목적 | 수정 위치 | 방법 |
|-----------|----------|------|
| 차트 스타일 변경 | `## 차트 생성 규칙` | line/bar/area 선호도, 색상 등 |
| annotation 규칙 | `## 차트 생성 규칙` → `5` | 핵심 수치 표기 스타일 변경 |
| 모바일 최적화 강화 | `## 차트 생성 규칙` → `7` | 데이터 포인트 수, 폰트 크기 등 |
| 차트 골격 템플릿 수정 | `_chart_skeletons.md` | 기본 Plotly 구조 변경 (system_message에 include됨) |
| 색상 팔레트 변경 | `config.py` → `COLOR_PALETTE` | 5색 팔레트 변경 |
| 차트 생성 모델 변경 | frontmatter `model:` | `gpt-4o-mini` → `gpt-4o` 등 (비용/품질 트레이드오프) |
| viz_hint가 없는 섹션에 강제 차트 | `nodes/interface3.py` → `build_charts_node` | `if not viz_hint:` 조건 수정 |

**예시: 차트 색상 팔레트 변경**

```python
# config.py
COLOR_PALETTE = ["#2563EB", "#DC2626", "#059669", "#D97706", "#7C3AED"]
```

### 용어사전 수정

**수정 파일**: `prompts/templates/glossary_generation.md`

| 수정 목적 | 수정 위치 | 방법 |
|-----------|----------|------|
| 용어 개수 조절 | `## 생성 규칙` → `1` | "0~3개" → "1~2개" 등 |
| domain 카테고리 변경 | `## 생성 규칙` → `4` | "금융, 산업, 국제..." 목록 수정 |
| 정의 스타일 변경 | `## 생성 규칙` → `3` | 해요체 외 다른 톤 지정 |
| 중복 방지 로직 수정 | `nodes/interface3.py` → `build_glossary_node` | `seen_terms` 관리 방식 변경 |

### 출처(sources) 수집 수정

**수정 파일**: `nodes/interface3.py` → `collect_sources_node`

이 노드는 **결정론적** (LLM 미사용)이므로 Python 코드를 직접 수정한다.

| 수정 목적 | 수정 위치 | 방법 |
|-----------|----------|------|
| 출처 매칭 알고리즘 | `collect_sources_node` | 콘텐츠-소스 매칭 로직 변경 |
| used_in_pages 배정 로직 | `collect_sources_node` | 페이지별 출처 매칭 기준 강화 |
| 외부 출처 추가 | `collect_sources_node` | 고정 출처 목록 추가 |

### 최종 할루시네이션 체크 수정

**수정 파일**: `prompts/templates/final_hallucination.md`

| 수정 목적 | 수정 위치 | 방법 |
|-----------|----------|------|
| 검증 항목 수 조절 | `## 출력 규칙` → `4` | "4~8개" → "6~10개" 등 |
| risk 판정 기준 | `## 판정 기준` | 낮음/중간/높음 기준 상세화 |
| 검증 대상 확대 | `## 검증 대상` | 차트 데이터도 검증 대상에 포함 등 |

### 6페이지 조립 수정

**수정 파일**: `nodes/interface3.py` → `SECTION_MAP` + `assemble_pages_node`

```python
# 현재 6페이지 매핑
SECTION_MAP = [
    (1, "현재 배경",        "background"),
    (2, "금융 개념 설명",    "concept_explain"),
    (3, "과거 비슷한 사례",  "history"),
    (4, "현재 상황에 적용",  "application"),
    (5, "주의해야 할 점",    "caution"),
    (6, "최종 정리",        "summary"),
]
```

| 수정 목적 | 수정 위치 | 방법 |
|-----------|----------|------|
| 페이지 제목 변경 | `SECTION_MAP` | 2번째 요소 (title) 수정 |
| 페이지 순서 변경 | `SECTION_MAP` | 튜플 순서 + step 번호 변경 |
| 페이지 추가/삭제 | `SECTION_MAP` + `schemas.py` + `narrative_body.md` | 3곳 동시 수정 필요 |

### 최종 출력 조립 수정

**수정 파일**: `nodes/interface3.py` → `assemble_output_node`

| 수정 목적 | 수정 위치 | 방법 |
|-----------|----------|------|
| 출력 파일명 형식 | `assemble_output_node` | `f"briefing_{timestamp}.json"` 패턴 변경 |
| 출력 디렉토리 변경 | `config.py` → `OUTPUT_DIR` | 환경변수 또는 기본값 변경 |
| 추가 메타데이터 삽입 | `assemble_output_node` | `FullBriefingOutput` 생성 전후에 필드 추가 |

---

## Pydantic 스키마 계약

### 전체 구조 (FullBriefingOutput)

```
FullBriefingOutput
├── topic: str
├── interface_1_curated_context: CuratedContext
│   ├── date, theme, one_liner
│   ├── selected_stocks: list[StockItem]
│   ├── verified_news: list[NewsItem]
│   ├── reports: list[ReportItem]
│   └── concept: Concept
├── interface_2_raw_narrative: RawNarrative
│   ├── theme, one_liner
│   ├── concept: Concept
│   ├── historical_case: HistoricalCase
│   └── narrative: NarrativeBody
│       ├── background: NarrativeSection
│       ├── concept_explain: NarrativeSection
│       ├── history: NarrativeSection
│       ├── application: NarrativeSection
│       ├── caution: NarrativeSection
│       └── summary: NarrativeSection
└── interface_3_final_briefing: FinalBriefing
    ├── theme, one_liner, generated_at
    ├── pages: list[Page]
    │   └── step, title, purpose, content, bullets, chart?, glossary[]
    ├── sources: list[SourceItem]
    └── hallucination_checklist: list[HallucinationItem]
```

### 스키마 변경 시 체크리스트

새 필드를 추가하거나 기존 필드를 변경할 때:

1. `schemas.py`에서 해당 Pydantic 모델 수정
2. 관련 프롬프트 `.md`의 `## 출력 스키마` 섹션 업데이트
3. 관련 노드의 mock 함수 업데이트 (`_mock_*`)
4. `tests/test_schemas.py`에서 golden case 검증이 여전히 통과하는지 확인
5. 하위 호환이 필요하면 `Optional` 또는 `Field(default_factory=...)` 사용

---

## 테스트

```bash
# 전체 테스트
python -m pytest interface/tests/ -v

# 스키마 검증만
python -m pytest interface/tests/test_schemas.py -v

# 노드 단위 테스트만
python -m pytest interface/tests/test_nodes.py -v

# E2E mock 테스트
python -m interface.run --input golden_case/03_k_defense.json --backend mock
```

### 테스트 구성

| 테스트 | 검증 대상 |
|--------|----------|
| `test_schemas.py::TestCuratedContext` | Interface 1 스키마 검증 + roundtrip |
| `test_schemas.py::TestRawNarrative` | Interface 2 스키마 검증 + 6섹션 존재 |
| `test_schemas.py::TestFinalBriefing` | Interface 3 스키마 검증 + 6페이지 구조 |
| `test_schemas.py::TestFullBriefingOutput` | golden case 전체 검증 + JSON roundtrip |
| `test_nodes.py::TestInterface1Node` | curated context 로드 + 에러 처리 |
| `test_nodes.py::TestInterface2Nodes` | 4단계 mock 노드 + Pydantic 검증 |
| `test_nodes.py::TestInterface3Nodes` | 페이지 조립 + 출처 수집 |

---

## 환경 설정

### .env 파일

프로젝트 루트(`data-integration/.env`)에 아래 키를 설정한다:

```env
# 필수 (live 모드)
CLAUDE_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...

# 선택
PERPLEXITY_API_KEY=pplx-...
DEFAULT_MODEL=claude-sonnet-4-20250514
CHART_MODEL=gpt-4o-mini
OUTPUT_DIR=interface/output
```

### 프롬프트 모델/프로바이더 오버라이드

각 프롬프트의 frontmatter에서 개별 설정 가능:

```yaml
---
provider: anthropic          # openai | anthropic | perplexity
model: claude-sonnet-4-20250514
temperature: 0.3
response_format: json_object
system_message: >
  커스텀 시스템 메시지
---
```

### 향후 datapipeline 통합

이 모듈은 `adelie-investment/datapipeline`에 통합될 예정이다. 통합 시:

1. `interface/` → `datapipeline/interface/`로 이동
2. `config.py` → `datapipeline/core/config.py`의 `get_settings()` 사용으로 전환
3. `ai/multi_provider_client.py` → `datapipeline/ai/multi_provider_client.py` 원본 사용
4. `prompts/prompt_loader.py` → `datapipeline/prompts/prompt_loader.py` 원본 사용
5. `graph.py`를 `datapipeline/scripts/`에서 keyword_pipeline_graph.py와 함께 관리
