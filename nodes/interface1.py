"""Interface 1 노드: curated context 로드 및 검증.

interface1의 실제 실행(data-gen 파이프라인)은 이 모듈 밖에서 수행된다.
이 노드는 interface1 결과 파일을 입력으로 받아 Pydantic 검증만 수행한다.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from langsmith import traceable

from ..schemas import CuratedContext

logger = logging.getLogger(__name__)


def _update_metrics(state: dict, node_name: str, elapsed: float, status: str = "success") -> dict:
    metrics = dict(state.get("metrics") or {})
    metrics[node_name] = {"elapsed_s": round(elapsed, 2), "status": status}
    return metrics


@traceable(name="load_curated_context", run_type="tool",
           metadata={"phase": "data_collection", "phase_name": "데이터 수집/로드", "step": 0})
def load_curated_context_node(state: dict) -> dict:
    """interface1 결과를 파일에서 로드하고 Pydantic으로 검증."""
    if state.get("error"):
        return {"error": state["error"]}

    node_start = time.time()
    logger.info("[Node] load_curated_context")

    try:
        input_path = state.get("input_path")
        if not input_path:
            return {
                "error": "input_path가 지정되지 않았습니다.",
                "metrics": _update_metrics(state, "load_curated_context", time.time() - node_start, "failed"),
            }

        data = json.loads(Path(input_path).read_text("utf-8"))

        # 다양한 입력 형식 지원
        if "interface_1_curated_context" in data:
            raw = data["interface_1_curated_context"]
        elif "topics" in data:
            idx = state.get("topic_index", 0)
            raw = data["topics"][idx]["interface_1_curated_context"]
        else:
            raw = data

        # Pydantic 검증
        curated = CuratedContext.model_validate(raw)
        logger.info("  CuratedContext 검증 통과: theme=%s", curated.theme[:50])

        return {
            "curated_context": curated.model_dump(),
            "metrics": _update_metrics(state, "load_curated_context", time.time() - node_start),
        }

    except Exception as e:
        logger.error("  curated context 로드 실패: %s", e)
        return {
            "error": f"curated context 로드 실패: {e}",
            "metrics": _update_metrics(state, "load_curated_context", time.time() - node_start, "failed"),
        }
