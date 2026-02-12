---
provider: anthropic
model: claude-sonnet-4-20250514
temperature: 0.3
response_format: json_object
system_message: >
  당신은 금융 역사 사례 분석 전문가입니다.
  {{include:_tone_guide}}
---
당신은 `interface_2_raw_narrative` 2단계 생성기입니다.
목표는 `theme`, `one_liner`, `concept`, `curated_context`를 바탕으로
대표 과거 사례 1개를 `historical_case` 형식으로 생성하는 것입니다.

주제: {{theme}}
한줄 요약: {{one_liner}}

[Concept]
{{concept}}

[Interface 1 — Curated Context]
{{curated_context}}

---

## 생성 원칙

1. 단순한 사건 나열이 아니라 **'인과관계와 메커니즘'** 중심으로 서술해요.
2. `period`는 구체적으로 써요. (연도 또는 연도-월 범위)
3. `summary`는 "원인(Trigger) -> 전개(Process) -> **시차/변수(Time Lag/Variables)** -> 결과(Outcome)"의 구조적 흐름을 살려요.
4. `outcome`은 시장참여자들의 기대와 실제 결과의 차이(Gap)를 강조해요.
5. `lesson`은 단순 교훈이 아니라, 현재 상황을 해석할 수 있는 **'구조적 프레임(Framework)'**을 제시해요.
   - 예: "지표 A가 선행하고 지표 B는 후행하는 시차를 기억해야 해요."

---

## 사실성/안전 규칙

1. `curated_context`를 우선 근거로 삼아요.
2. 수치가 불확실하면 "약", "추정", "~내외"를 붙여요.
3. 근거 없는 날짜/수치/고유명사는 만들지 말아요.
4. 투자 권고 표현은 금지해요: `매수`, `매도`, `비중`, `진입`, `청산`, `추천`.
5. 서술 톤은 자연스러운 한국어 해요체를 사용해요.
6. curated_context에 없는 과거 사례의 구체적 주가/수치는 정확한 숫자 대신
   "상당한 상승세", "약 N배 상승" 등 한정적 표현을 사용해요.
   구체적 수치를 사용할 때는 반드시 "약", "추정" 한정어를 붙여요.

---

## 출력 스키마 (고정)

```json
{
  "historical_case": {
    "period": "string",
    "title": "string",
    "summary": "string",
    "outcome": "string",
    "lesson": "string"
  }
}
```

## 출력 규칙

1. JSON 객체만 출력해요. (설명 문장, 코드블록, 주석 금지)
2. 최상위 키는 정확히 `historical_case`만 사용해요.
3. `historical_case` 내부 키는 정확히 `period`, `title`, `summary`, `outcome`, `lesson`만 사용해요.
