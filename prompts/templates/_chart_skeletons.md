**섹션별 차트 골격 템플릿** (아래 구조를 그대로 따르되, 주석 자리에 실제 데이터를 채우세요):

공통 규칙:
- trace가 1개면 showlegend 생략. trace가 2개 이상이면 "showlegend": true, "legend": {"orientation": "h", "y": -0.25} 추가.
- annotations로 핵심 수치(피크, 최종 수익률 등)를 표기하면 좋음.
- x와 y의 길이는 반드시 동일해야 함.
- 날짜는 "YYYY" 또는 "YYYY.MM" 형식.
- curated_context에 없는 기업명/수치를 절대 만들지 마세요. ("기타 A", "가상 기업" 금지)

### background (시계열 scatter — 주가/지표 추이)
대표 종목이나 핵심 지표의 시계열 변화를 보여줘요.
```
"chart": {
  "data": [
    {"x": [/* 날짜 5~8개 */], "y": [/* 지표 수치 */], "type": "scatter", "mode": "lines+markers", "name": "/* 지표명 */", "line": {"width": 3}}
  ],
  "layout": {"title": "/* 차트 제목 */", "xaxis": {"title": "기간"}, "yaxis": {"title": "/* 단위 */"}}
}
```

### concept_explain (bar 또는 grouped-bar — 개념 비교)
핵심 개념을 시각적으로 비교해요. (예: PER, 수익률, 기업별 수치)
```
"chart": {
  "data": [
    {"x": [/* 비교 항목 3~5개 */], "y": [/* 수치 */], "type": "bar", "name": "/* 지표명 */", "marker": {"color": [/* 팔레트 색상 */]}}
  ],
  "layout": {"title": "/* 차트 제목 */", "xaxis": {"title": "항목"}, "yaxis": {"title": "/* 단위 */"}}
}
```

### history (area scatter — 과거 추이 + 마일스톤 annotation)
과거 사례의 시계열 추이와 주요 전환점을 보여줘요.
```
"chart": {
  "data": [
    {"x": [/* 과거 시점 5~8개 */], "y": [/* 수치 */], "type": "scatter", "mode": "lines+markers", "fill": "tozeroy", "name": "/* 지표명 */", "line": {"width": 2}}
  ],
  "layout": {"title": "/* 차트 제목 */", "xaxis": {"title": "기간"}, "yaxis": {"title": "/* 단위 */"}, "annotations": [/* 주요 마일스톤 annotation */]}
}
```

### application (grouped-bar — 과거 vs 현재 대조)
과거 사례와 현재 상황의 핵심 수치를 비교해요.
```
"chart": {
  "data": [
    {"x": [/* 비교 항목 2~4개 */], "y": [/* 과거 수치 */], "type": "bar", "name": "/* 과거 시기 */"},
    {"x": [/* 비교 항목 2~4개 */], "y": [/* 현재 수치 */], "type": "bar", "name": "/* 현재 시기 */"}
  ],
  "layout": {"title": "/* 차트 제목 */", "xaxis": {"title": "항목"}, "yaxis": {"title": "/* 단위 */"}, "barmode": "group", "showlegend": true, "legend": {"orientation": "h", "y": -0.25}}
}
```

### caution (차트 없음 권장, 필요시 시나리오 bar)
caution 섹션은 차트 없이 텍스트만으로 충분해요. viz_hint가 null이면 차트를 생성하지 마세요.
만약 viz_hint가 있다면 리스크 시나리오를 bar로 보여줘요.
```
"chart": {
  "data": [
    {"x": [/* 시나리오명 3개 */], "y": [/* 영향도(%) */], "type": "bar", "name": "영향도 (%)", "text": [/* 확률 텍스트 3개 */], "textposition": "outside"}
  ],
  "layout": {"title": "/* 차트 제목 */", "xaxis": {"title": "시나리오"}, "yaxis": {"title": "영향도 (%)"}}
}
```

### summary (horizontal-bar — 핵심 관찰 지표 우선순위)
독자가 체크해야 할 핵심 지표/이벤트를 중요도순으로 보여줘요.
```
"chart": {
  "data": [
    {"x": [/* 중요도 점수 3개 */], "y": [/* 관찰 지표명 3개 */], "type": "bar", "orientation": "h", "marker": {"color": [/* 팔레트 색상 */]}, "text": [/* 점수 텍스트 */], "textposition": "auto"}
  ],
  "layout": {"title": "핵심 관찰 지표 우선순위", "xaxis": {"title": "중요도 (1-10)"}, "yaxis": {"title": "관찰 지표"}}
}
```
