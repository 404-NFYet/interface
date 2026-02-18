
import sys
import unittest.mock as mock
import json
import logging
import os

# Add project root to sys.path
project_root = "c:/Users/myhom/JIHOON/bootcamp/Project3"
if project_root not in sys.path:
    sys.path.append(project_root)

# Import nodes
from interface.nodes import interface3
from interface.nodes.interface3 import run_glossary_node
from interface.nodes.chart_agent import run_chart_agent_node
from interface.config import SECTION_MAP

# Config logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("verify_pipeline")

# Create full mock narrative based on SECTION_MAP
# Strong hint for 'background'
narrative_mock = {}
for step, title, key in SECTION_MAP:
    if key == "background":
        content = "2024년 1분기 삼성전자 영업이익은 6.6조원, SK하이닉스는 2.8조원입니다. 작년 동기 대비 각각 931% 증가, 흑자전환하였습니다."
        viz_hint = "삼성전자와 SK하이닉스 2024년 1분기 영업이익을 비교하는 세로형 막대 그래프를 그려주세요. (Bar Chart)"
    else:
        content = f"{title}에 대한 일반적인 설명입니다."
        viz_hint = ""

    narrative_mock[key] = {
        "purpose": f"{title} 섹션입니다.",
        "content": content,
        "bullets": ["핵심 내용 1"],
        "viz_hint": viz_hint
    }

# Mock state
mock_state = {
    "raw_narrative": {
        "theme": "반도체 슈퍼사이클",
        "one_liner": "메모리 반도체, 다시 뛴다!",
        "narrative": narrative_mock
    },
    "i3_validated": {
        "validated_pages": [
            {
                "step": step,
                "title": title,
                "content": narrative_mock[key]["content"],
                "bullets": ["불렛1"]
            }
            for step, title, key in SECTION_MAP
        ]
    },
    "i3_pages": [],
    "backend": "live", 
    "curated_context": {
        "filtered_stocks": [{"name": "삼성전자", "code": "005930"}, {"name": "SK하이닉스", "code": "000660"}]
    }
}

# Hybrid Mock & Interceptor
original_call_llm = interface3.call_llm_with_prompt

def hybrid_call_llm(prompt_name, variables, **kwargs):
    if "chart" in prompt_name:
        # Live call for Chart Agent
        from interface.ai.llm_utils import call_llm_with_prompt as real_call_llm
        result = real_call_llm(prompt_name, variables, **kwargs)
        
        # INTERCEPT: Print reasoning result
        if prompt_name == "3_chart_reasoning":
            print(f"\n[INTERCEPTED REASONING RESULT for {variables.get('section_title', 'Unknown Section')}]")
            print(json.dumps(result, ensure_ascii=False, indent=2))
        
        return result
    else:
        # Mock other prompts
        return {} 

interface3.call_llm_with_prompt = hybrid_call_llm
from interface.nodes import chart_agent
chart_agent.call_llm_with_prompt = hybrid_call_llm

print("--- Running Chart Agent (LIVE OpenAI Intercepted) ---")
try:
    run_chart_agent_node(mock_state)
except Exception as e:
    print(f"Chart Agent Failed: {e}")
    # traceback.print_exc()

print("\n--- Pipeline Emulation Complete ---")
