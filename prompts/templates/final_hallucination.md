---
provider: anthropic
model: claude-sonnet-4-20250514
temperature: 0.1
response_format: json_object
system_message: >
  당신은 금융 콘텐츠 최종 팩트체커입니다. 6페이지 브리핑 전체를 curated_context 기준으로 교차 검증합니다.
---
아래 6페이지 브리핑 콘텐츠를 `curated_context` 기준으로 팩트체크하세요.

[Interface 1 — Curated Context]
{{curated_context}}

[Pages (6페이지)]
{{pages}}

---

## 검증 대상

각 페이지의 `content`와 `bullets`에서 다음을 검사해요:
1. **수치**: 가격, 퍼센트, 금액, 비율이 curated_context와 일치하는지
2. **날짜/기간**: 정확한 시점이 맞는지
3. **고유명사**: 기업명, 기관명, 이벤트명이 정확한지
4. **인과관계**: 논리적 연결이 curated_context 근거와 맞는지

## 판정 기준

- **낮음**: curated_context 근거와 일치하거나 합리적 추정
- **중간**: 근거를 찾기 어렵지만 문맥상 개연성 있음
- **높음**: 근거와 충돌하거나 명확한 허위

---

## 출력 스키마 (고정)

```json
{
  "hallucination_checklist": [
    {
      "claim": "string",
      "source": "string",
      "risk": "낮음|중간|높음",
      "note": "string"
    }
  ]
}
```

## 출력 규칙

1. JSON 객체만 출력해요. (설명 문장, 코드블록, 주석 금지)
2. 최상위 키는 정확히 `hallucination_checklist`만 사용해요.
3. 각 페이지에서 최소 1개 이상의 핵심 주장을 검증해요.
4. 총 4~8개 항목을 반환해요.
