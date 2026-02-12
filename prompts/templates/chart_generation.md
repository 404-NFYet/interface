---
provider: openai
model: gpt-4o-mini
temperature: 0.3
response_format: json_object
system_message: >
  당신은 Plotly.js 차트 전문가입니다. viz_hint와 콘텐츠를 분석하여
  모바일 친화적인 Plotly JSON을 생성합니다.
  {{include:_chart_skeletons}}
---
아래 정보를 바탕으로 Plotly.js 차트 JSON을 생성하세요.

## 입력

섹션: {{section_key}}
시각화 힌트: {{viz_hint}}
콘텐츠: {{content}}
불렛 포인트: {{bullets}}

관련 주식: {{stocks}}
관련 뉴스: {{news}}

색상 팔레트: {{color_palette}}

---

## 차트 생성 규칙

1. **캔들스틱 차트 금지**: 절대 "type": "candlestick"을 사용하지 마세요. line+markers 또는 area(fill: tozeroy) scatter를 대신 사용하세요.
2. **type-title 일치**: viz_hint에 "bar"라고 했으면 반드시 bar 차트를, "line"이라고 했으면 scatter(lines+markers)를 사용하세요.
3. **x, y 길이 동일**: data 내 모든 trace에서 x와 y 배열 길이가 반드시 같아야 해요.
4. **y축 단위 명시**: layout.yaxis.title에 반드시 단위를 포함하세요 (예: "원 (KRW)", "조원", "PER (배)", "%").
5. **annotation 활용**: 핵심 수치에 annotation을 달아 독자가 바로 의미를 파악할 수 있게 하세요.
6. **색상 팔레트 사용**: 제공된 color_palette의 색상을 사용하세요.
7. **모바일 최적화**: 데이터 포인트는 5~8개, 텍스트는 짧게 유지하세요.
8. **trace가 1개면 showlegend 생략**, 2개 이상이면 "showlegend": true, "legend": {"orientation": "h", "y": -0.25} 추가.

---

## 데이터 규칙

1. curated_context의 실제 데이터를 최대한 활용하세요.
2. 정확한 수치가 없으면 콘텐츠와 뉴스에서 언급된 수치를 합리적으로 추정하세요.
3. 추정 수치는 annotation에 "추정" 표시를 하세요.
4. 날짜는 "YYYY" 또는 "YYYY.MM" 형식을 사용하세요.

---

## 데이터 안전 규칙

1. **가상 데이터 절대 금지**: curated_context에 없는 기업명/수치를 만들지 마세요.
   - "기타 A", "기타 B", "가상 기업" 같은 이름을 절대 사용하지 마세요.
   - 비교 대상이 부족하면 데이터 포인트 수를 줄이세요 (2~3개도 괜찮아요).
2. **섹션별 스켈레톤의 chart type을 반드시 따르세요.** (system_message의 섹션별 골격 참조)
3. **이전 차트와 차별화**: 아래 정보를 보고 동일한 차트 유형/데이터 조합을 피하세요.

## 이전 차트 정보

{{previous_charts}}

---

## 출력 스키마 (고정)

```json
{
  "data": [
    {
      "x": ["string", ...],
      "y": [number, ...],
      "type": "string",
      ...
    }
  ],
  "layout": {
    "title": "string",
    "yaxis": {"title": "string"},
    ...
  }
}
```

## 출력 규칙

1. JSON 객체만 출력해요. (설명 문장, 코드블록, 주석 금지)
2. 최상위 키는 정확히 `data`와 `layout`만 사용해요.
