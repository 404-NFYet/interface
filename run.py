"""Interface 파이프라인 CLI 진입점.

사용법:
    # interface1 결과 파일 → 전체 실행
    python -m interface.run --input golden_case/03_k_defense.json --backend live

    # mock 테스트 (LLM 호출 없이 구조 검증)
    python -m interface.run --input golden_case/03_k_defense.json --backend mock

    # 특정 토픽 인덱스 지정 (topics[] 배열이 있는 입력)
    python -m interface.run --input data-gen/output/curated_ALL.json --topic-index 0
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("interface.run")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Interface 파이프라인: 3개 인터페이스를 연결하여 최종 브리핑 JSON 생성",
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Interface 1 결과 JSON 파일 경로",
    )
    parser.add_argument(
        "--backend",
        choices=["live", "mock", "auto"],
        default="auto",
        help="실행 백엔드. live=실제 LLM, mock=더미 응답, auto=API 키 유무로 결정",
    )
    parser.add_argument(
        "--topic-index",
        type=int,
        default=0,
        help="topics[] 배열이 있는 입력에서 처리할 토픽 인덱스 (기본: 0)",
    )
    return parser.parse_args()


def pick_backend(arg_backend: str) -> str:
    """auto 모드에서 API 키 유무로 백엔드 결정."""
    if arg_backend != "auto":
        return arg_backend

    from .config import ANTHROPIC_API_KEY, OPENAI_API_KEY
    if ANTHROPIC_API_KEY or OPENAI_API_KEY:
        return "live"
    return "mock"


def main() -> int:
    args = parse_args()
    backend = pick_backend(args.backend)

    if not args.input.exists():
        logger.error("입력 파일을 찾을 수 없습니다: %s", args.input)
        return 1

    logger.info("=== Interface Pipeline ===")
    logger.info("Input: %s", args.input)
    logger.info("Backend: %s", backend)
    logger.info("Topic Index: %d", args.topic_index)

    # LangGraph 빌드
    from .graph import build_graph

    graph = build_graph()

    # 초기 상태
    initial_state = {
        "input_path": str(args.input.resolve()),
        "topic_index": args.topic_index,
        "backend": backend,
        "curated_context": None,
        "page_purpose": None,
        "historical_case": None,
        "narrative": None,
        "raw_narrative": None,
        "charts": None,
        "glossaries": None,
        "pages": None,
        "sources": None,
        "hallucination_checklist": None,
        "full_output": None,
        "output_path": None,
        "error": None,
        "metrics": {},
    }

    # 실행
    started = time.time()
    final_state = graph.invoke(initial_state)
    elapsed = time.time() - started

    # 결과 출력
    if final_state.get("error"):
        logger.error("파이프라인 실패: %s", final_state["error"])
        return 1

    output_path = final_state.get("output_path", "")
    logger.info("=== 완료 ===")
    logger.info("출력 파일: %s", output_path)
    logger.info("총 소요시간: %.2fs", elapsed)

    # 메트릭 출력
    metrics = final_state.get("metrics", {})
    if metrics:
        logger.info("--- 노드별 실행 시간 ---")
        for node_name, info in metrics.items():
            logger.info("  %s: %.2fs (%s)", node_name, info["elapsed_s"], info["status"])

    return 0


if __name__ == "__main__":
    sys.exit(main())
