---
provider: anthropic
model: claude-sonnet-4-5-20250514
temperature: 0.2
response_format: json_object
---
당신은 `interface_3_final_briefing` 최종 톤 보정 및 병합기입니다.
검증 완료된 모든 데이터를 입력으로 받아 최종 `interface_3_final_briefing` JSON을 생성하세요.

[Validated Theme & One-liner — 3단계 검증 완료]
theme: {{validated_theme}}
one_liner: {{validated_one_liner}}

[Validated Pages — 3단계 검증 완료]
{{validated_pages}}

[Validated Page Glossaries — 5단계 검증 완료]
{{validated_page_glossaries}}

---

## 병합 및 톤 보정 원칙

### 1. 병합 규칙
- `validated_pages`의 각 페이지에 `validated_page_glossaries`의 해당 `step` glossary를 삽입해요.
- 최종 구조: 각 페이지 = `step` + `title` + `purpose` + `content` + `bullets` + `glossary`

### 2. 톤 보정 규칙 (Tone Guide 적용)
**아래 톤 가이드를 기준으로 모든 텍스트를 재작성/보정하세요.**
{{include:_tone_guide}}

**추가 금지/교정 규칙:**
- **해요체 필수**: 모든 문장은 `~해요`, `~예요/이에요`, `~거든요` 등으로 끝나야 해요.
- **금지 어미**: `~합니다`, `~입니다`, `~됩니다`, `~습니까?`, `~하였다`, `~한다`, `~이다` 발견 시 즉시 해요체로 수정해요.
- **자연스러운 연결**: 6개 페이지가 하나의 이야기처럼 자연스럽게 이어지도록 접속사와 흐름을 다듬어요.
- **반복 제거**: "주목할 점은", "살펴보면" 같은 상투적 표현이 반복되지 않도록 다양화해요.

### 3. 안전 최종 점검
- 투자 권고 표현(`매수`, `매도`, `비중`, `진입`, `청산`, `추천`)이 어디에도 없는지 확인해요.
- 수치/날짜/고유명사가 입력 데이터와 일치하는지 최종 확인해요.

---

## 출력 스키마 (고정)

```json
{
  "interface_3_final_briefing": {
    "theme": "string",
    "one_liner": "string",
    "pages": [
      {
        "step": 1,
        "title": "string",
        "purpose": "string",
        "content": "string",
        "bullets": ["string", "string"],
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
        "title": "string",
        "purpose": "string",
        "content": "string",
        "bullets": ["string", "string"],
        "glossary": []
      },
      {
        "step": 3,
        "title": "string",
        "purpose": "string",
        "content": "string",
        "bullets": ["string", "string"],
        "glossary": []
      },
      {
        "step": 4,
        "title": "string",
        "purpose": "string",
        "content": "string",
        "bullets": ["string", "string"],
        "glossary": []
      },
      {
        "step": 5,
        "title": "string",
        "purpose": "string",
        "content": "string",
        "bullets": ["string", "string"],
        "glossary": []
      },
      {
        "step": 6,
        "title": "string",
        "purpose": "string",
        "content": "string",
        "bullets": ["string", "string"],
        "glossary": []
      }
    ]
  }
}
```

## 출력 규칙

1. JSON 객체만 출력해요. (설명 문장, 코드블록, 주석 금지)
2. 최상위 키는 정확히 `interface_3_final_briefing`만 사용해요.
3. `pages` 배열은 정확히 6개 객체를 포함해요.
4. `chart` 필드는 포함하지 않아요.
5. 각 페이지의 `glossary`는 검증된 용어만 포함하며, 없으면 빈 배열(`[]`)로 넣어요.
6. 모든 텍스트는 해요체로 통일해요.
