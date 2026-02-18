
import json
import logging
from nodes.interface3 import run_glossary_node, run_hallcheck_glossary_node

# logger setup
logging.basicConfig(level=logging.INFO)

# Mock state
mock_state = {
    "raw_narrative": {
        "theme": "Test Theme",
        "one_liner": "Test One Liner",
        "narrative": {
            "section1": {"purpose": "p", "content": "c", "bullets": ["b"]}
        }
    },
    "i3_validated": {
        "validated_pages": [
            {
                "step": 1,
                "title": "테스트 페이지",
                "content": "이 페이지는 주가수익비율(PER)과 주당순이익(EPS)에 대해 설명합니다. 초보 투자자(주린이)가 이해하기 쉬워야 합니다. 캔들 차트 분석도 포함됩니다.",
                "bullets": ["PER는 중요하다.", "EPS도 중요하다."]
            }
        ]
    },
    "backend": "live" # Use live to trigger LLM and Search
}

print("--- 1. Testing run_glossary_node ---")
glossary_result = run_glossary_node(mock_state)
print("Glossary Result Keys:", glossary_result.keys())
if "i3_glossaries" in glossary_result:
    print(f"Generated Terms: {len(glossary_result['i3_glossaries'])}")
    for page in glossary_result['i3_glossaries']:
        for term in page.get('glossary', []):
            print(f" - {term['term']}: {term['definition']}")

if "i3_glossary_search_context" in glossary_result:
    print("\nSearch Context Preview:")
    print(glossary_result["i3_glossary_search_context"][:200] + "...")

print("\n--- 2. Testing run_hallcheck_glossary_node ---")
# Update state with result from previous step
mock_state.update(glossary_result)
hallcheck_result = run_hallcheck_glossary_node(mock_state)
print("Hallcheck Result Keys:", hallcheck_result.keys())
if "i3_validated_glossaries" in hallcheck_result:
    print(f"Validated Terms: {len(hallcheck_result['i3_validated_glossaries'])}")
