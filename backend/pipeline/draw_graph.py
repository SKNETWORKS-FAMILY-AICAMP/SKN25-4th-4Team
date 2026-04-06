"""
그래프 시각화 — LangGraph 그래프를 Mermaid 다이어그램으로 출력.

사용법:
    cd backend
    python -m pipeline.draw_graph           # Mermaid 출력
    python -m pipeline.draw_graph --png     # graph.png 저장
"""
from __future__ import annotations

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="LangGraph 그래프 시각화")
    parser.add_argument("--png", action="store_true", help="PNG 파일로 저장")
    args = parser.parse_args()

    from pipeline.graph import rag_graph

    mermaid = rag_graph.get_graph().draw_mermaid()
    print(mermaid)

    if args.png:
        try:
            png_bytes = rag_graph.get_graph().draw_mermaid_png()
            with open("graph.png", "wb") as f:
                f.write(png_bytes)
            print("\ngraph.png 저장 완료")
        except Exception as e:
            print(f"\nPNG 생성 실패 (pyppeteer 필요): {e}", file=sys.stderr)
            print("Mermaid 코드를 https://mermaid.live 에 붙여넣어 확인하세요.")


if __name__ == "__main__":
    main()