
import sys
import unittest.mock as mock
import json
import logging

# Add project root to sys.path
project_root = "c:/Users/myhom/JIHOON/bootcamp/Project3"
if project_root not in sys.path:
    sys.path.append(project_root)

# Import nodes
from interface.nodes import interface3
from interface.nodes.interface3 import run_glossary_node, run_hallcheck_glossary_node

# Config logger
logging.basicConfig(level=logging.INFO)

# Mock state
mock_state = {
    "raw_narrative": {
        "theme": "반도체 슈퍼사이클",
        "one_liner": "메모리 반도체, 다시 뛴다!",
        "narrative": {
            "section1": {"purpose": "p", "content": "c", "bullets": ["b"]}
        }
    },
    "i3_validated": {
        "validated_pages": [
            {
                "step": 1,
                "title": "시장 분석",
                "content": "HBM 수요 폭증과 외국인 수급이 긍정적입니다.",
                "bullets": ["HBM", "외국인 수급"]
            }
        ]
    },
    "backend": "live" # Keep live to enter the logic block
}

# Mocking call_llm_with_prompt
def mock_call_llm(prompt_name, variables):
    print(f"\n[MockLLM] Called with prompt: {prompt_name}")
    
    if prompt_name == "3_glossary_term_extraction":
        print(" -> Returning mock extracted terms WITH CONTEXT")
        return {
            "terms_to_search": [
                {
                    "step": 1, 
                    "term": "HBM", 
                    "context_sentence": "삼성전자가 HBM 시장에서 점유율을 늘리고 있습니다."
                },
                {
                    "step": 1, 
                    "term": "외국인 수급", 
                    "context_sentence": "최근 코스피에서 외국인 수급이 개선세입니다."
                }
            ]
        }
    
    elif prompt_name == "3_glossary":
        print(" -> Returning mock glossary")
        return {
            "page_glossaries": [
                {
                    "step": 1,
                    "glossary": [
                        {"term": "HBM", "definition": "AI 두뇌에 들어가는 초고속 메모리예요.", "domain": "반도체"},
                        {"term": "외국인 수급", "definition": "외국인 투자자가 우리 증시에서 주식을 사들이는 것을 말해요.", "domain": "시장"}
                    ]
                }
            ]
        }
    
    elif prompt_name == "3_hallcheck_glossary":
        print(" -> Returning mock hallcheck result")
        return {
            "overall_risk": "low",
            "validated_page_glossaries": [
                {
                    "step": 1,
                    "glossary": [
                         {"term": "HBM", "definition": "AI 두뇌에 들어가는 초고속 메모리예요. (검증됨)", "domain": "반도체"},
                    ]
                }
            ]
        }
        
    return {}

# Mocking search tool
class MockSearchTool:
    def invoke(self, query):
        print(f"[MockSearch] Searching for: {query}")
        # Verify if context is in query
        if "(문맥:" in query:
             print("   -> [CHECK] Query contains context!")
        return f"Search result for {query}..."

# Apply mocks
interface3.call_llm_with_prompt = mock_call_llm
interface3.search_web_for_chart_data = MockSearchTool()

print("--- 1. Testing run_glossary_node (With Context) ---")
try:
    glossary_result = run_glossary_node(mock_state)
    
    # Verify Search Context was populated
    search_context = glossary_result.get("i3_glossary_search_context", "")
    print(f"\n[Verification] Search Context Length: {len(search_context)}")
    if "(문맥:" in search_context:
        print("[Verification] SUCCESS: Search context contains context sentences.")
    else:
        print("[Verification] FAILURE: Search context missing context sentences.")
    
    print(f"Context Sample: {search_context[:200]}...")

except Exception as e:
    print(f"Error: {e}")
