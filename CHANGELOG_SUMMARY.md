# Interface 변경 사항 요약

본 문서는 최근 작업 기간 동안 `interface` 폴더 내에서 이루어진 주요 변경 사항을 정리한 것입니다.

## 1. 파이프라인 아키텍처 (`graph.py`)

LangGraph를 기반으로 한 브리핑 파이프라인의 구조를 정의하고 안정화했습니다.

*   **상태 정의 (`BriefingPipelineState`)**:
    *   `metrics`, `error` 등 공통 상태 관리를 위한 `TypedDict` 정의.
    *   병렬 실행 시 상태 충돌 방지를 위한 Reducer 함수 구현 (`merge_metrics`, `merge_list`, `merge_last`).
    *   **주요 수정**: `INVALID_CONCURRENT_GRAPH_UPDATE` 오류 해결을 위해 `Annotated`와 Reducer를 적용하여 동시성 문제 해결.

*   **그래프 구성**:
    *   **데이터 수집 (Data Collection)**: News/Research 크롤링 및 요약, 토픽 큐레이션 노드 연결.
    *   **Interface 2**: `Page Purpose` → `Historical Case` → `Narrative Body` → `Validation`의 순차적 흐름 구성.
    *   **Interface 3**:
        *   `Theme` 및 `Pages` 생성 후 **병렬 브랜치**로 분기:
            1.  **Glossary Branch**: 용어 추출 → 검증 (Hallucination Check).
            2.  **Chart Branch**: 차트 생성 → 검증.
        *   **Join Pattern**: 두 브랜치가 모두 완료(`check_join_readiness`)되어야 `Tone Final`로 진행되도록 로직 구현. (초기 실행 오류 수정 포함)

*   **에러 핸들링 및 라우팅**:
    *   각 단계별 에러 발생 시 즉시 종료(`END`)하거나 로그를 남기는 조건부 엣지(`check_error`) 추가.
    *   입력 소스(`input_path`) 유무에 따라 파일 로드 모드와 실시간 수집 모드를 자동 전환하는 라우터 구현.

## 2. 실행 스크립트 및 CLI (`run.py`)

파이프라인 실행을 유연하게 제어하기 위한 CLI 환경을 구축했습니다.

*   **명령어 인수 (Generic Arguments)**:
    *   `--input`: 로컬 JSON 파일 기반 실행 지원.
    *   `--backend`: `live` (실제 LLM/툴), `mock` (테스트), `auto` (API 키 감지) 모드 지원.
    *   `--market`: `KR`, `US`, `ALL` 등 대상 시장 지정.
    *   `--topic-index`: 특정 토픽만 선택적으로 처리할 수 있는 기능 추가.
*   **로깅 및 모니터링**:
    *   실행 시간 측정 및 각 노드별 상태(`metrics`)를 로그로 출력하여 병목 구간 파악 용이.

## 3. 프롬프트 엔지니어링 (`prompts/templates/`)

LLM의 출력 품질을 높이고 최신 모델을 적용하기 위해 프롬프트를 대대적으로 수정했습니다.

*   **모델 버전 업데이트**:
    *   `claude-3-5-sonnet-20240620` 등의 구버전 모델명을 최신 `claude-sonnet-4-20250514` (가상/예시 버전) 등으로 일괄 변경하여 `NotFoundError` 해결.
*   **Interface 2 내러티브 개선**:
    *   `page_purpose.md`, `historical_case.md`, `narrative_body.md` 등을 수정하여 "Golden Sample"에 가까운 톤앤매너와 구조를 갖추도록 개선.
    *   단순 사실 나열이 아닌, 독자의 흥미를 유발하는 내러티브 구조 강화.
*   **Interface 3 신규 프롬프트**:
    *   `3_pages.md`, `3_chart_generation.md`, `3_glossary.md` 등 최종 아웃풋 생성을 위한 상세 프롬프트 추가 및 최적화.
    *   검증(Hallucination Check)을 위한 별도 프롬프트 (`3_hallcheck_*.md`) 세분화.
    *   **Markdown 포맷 및 분량 제어**:
        *   최종 아웃풋(`3_pages.md` 등)의 `content` 필드를 **Markdown** 문법(Bold, 리스트, 인용문 등)으로 작성하도록 지시하여 가독성 강화.
        *   각 페이지별 **글자수 제한**(예: 공백 포함 최대 700자)을 명시하여, 불필요한 미사여구를 줄이고 핵심 내용 위주로 작성되도록 제어.


## 4. 데이터 수집 및 MCP 통합

*   **MCP (Model Context Protocol) 도입**:
    *   외부 데이터 소스와의 연동을 위해 MCP 클라이언트/서버 구조 도입 (관련 파일: `mcp_client.py`, `mcp_server.py`).
    *   데이터 수집 단계의 병렬 처리 및 효율성 증대.

## 5. 기타 유틸리티

*   **검증 스크립트**: `verify_glossary_v2.py`, `verify_pipeline_hybrid.py` 등을 통해 전체 파이프라인을 돌리지 않고도 특정 모듈(용어집, 파이프라인 일부)만 빠르게 검증할 수 있는 환경 마련.
