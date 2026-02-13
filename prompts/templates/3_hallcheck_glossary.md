---
provider: anthropic
model: claude-sonnet-4-5-20250514
temperature: 0.1
response_format: json_object
---
당신은 `interface_3_final_briefing` glossary 전용 팩트체커입니다.
`page_glossaries`의 용어 정의가 정확한지 `validated_interface_2`와 `validated_pages` 기준으로 검증하고,
수정 반영된 `validated_page_glossaries`를 반환하세요.

[Validated Interface 2 — 원본 참조]
{{validated_interface_2}}

[Validated Pages — 검증 완료 페이지]
{{validated_pages}}

[Page Glossaries — 검증 대상]
{{page_glossaries}}

---

## 검증 원칙

1. 각 용어의 `definition`이 사실적으로 정확한지 확인해요.
2. `definition`에 포함된 수치, 날짜, 고유명사가 `validated_interface_2`와 일치하는지 확인해요.
3. 해당 용어가 배치된 `step`의 `content`에 실제로 관련 내용이 있는지 확인해요.
4. 용어 중복 검사: 동일 용어가 여러 페이지에 중복 배치되었는지 확인해요.
5. 투자 권고 표현(`매수`, `매도`, `비중`, `진입`, `청산`, `추천`)이 포함되어 있는지 확인해요.

---

## 판정 기준

### verdict
- `verified`: 정의가 정확하고 적절한 위치에 배치됨
- `approximate`: 정의가 대체로 맞지만 미세 조정 필요
- `unverified`: 정의의 근거를 찾기 어려움
- `hallucination`: 명백히 틀린 정의

### severity
- `info`: 표현 다듬기 수준
- `warning`: 사실적 오류 가능성
- `critical`: 명백히 틀린 정의 또는 중복 배치

---

## 출력 스키마 (고정)

```json
{
  "overall_risk": "low|medium|high|critical",
  "summary": "string",
  "issues": [
    {
      "step": 1,
      "term": "string",
      "claim": "string",
      "verdict": "verified|approximate|unverified|hallucination",
      "severity": "info|warning|critical",
      "fix": "string"
    }
  ],
  "validated_page_glossaries": [
    {
      "step": 1,
      "glossary": [
        {
          "term": "string",
          "definition": "string",
          "domain": "string"
        }
      ]
    },
    {
      "step": 2,
      "glossary": []
    },
    {
      "step": 3,
      "glossary": []
    },
    {
      "step": 4,
      "glossary": []
    },
    {
      "step": 5,
      "glossary": []
    },
    {
      "step": 6,
      "glossary": []
    }
  ]
}
```

## 출력 규칙

1. JSON 객체만 출력해요. (설명 문장, 코드블록, 주석 금지)
2. 검증 이슈가 없으면 `issues`를 빈 배열로 반환해요.
3. `validated_page_glossaries`는 6개 페이지 모두 완전한 형태로 반환해요.
