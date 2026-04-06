"""
LangGraph graph — 조건부 분기가 있는 RAG 파이프라인 그래프.

흐름:
  analyze_query → route → retrieve
    → [신조어?] → resolve_neologism → re_retrieve ─┐
                                                    ↓
                         → assess_retrieval (LLM 검색 품질 평가)
    → [웹필요?] → web_search
    → build_context → generate_answer → postprocess → END
"""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from pipeline.nodes import (
    analyze_query,
    assess_retrieval,
    build_context,
    generate_answer,
    postprocess,
    re_retrieve,
    resolve_neologism,
    retrieve,
    route,
    web_search,
)
from pipeline.state import GraphState


def _needs_neologism_resolution(state: GraphState) -> str:
    """신조어이거나 1차 검색 결과가 없으면 → resolve_neologism."""
    is_neo = state.get("is_neologism", False)
    no_results = not state.get("paper_docs") and not state.get("matched_terms")
    if is_neo or no_results:
        return "resolve_neologism"
    return "assess_retrieval"


def _needs_web_search(state: GraphState) -> str:
    """웹검색 필요 여부에 따라 분기."""
    if state.get("needs_web", False):
        return "web_search"
    return "build_context"


def build_graph() -> StateGraph:
    """RAG 파이프라인 그래프를 구성하고 컴파일한다."""
    g = StateGraph(GraphState)

    # ── 노드 등록 ──
    g.add_node("analyze_query", analyze_query)
    g.add_node("route", route)
    g.add_node("retrieve", retrieve)
    g.add_node("resolve_neologism", resolve_neologism)
    g.add_node("re_retrieve", re_retrieve)
    g.add_node("assess_retrieval", assess_retrieval)  # LLM 검색 품질 평가
    g.add_node("web_search", web_search)
    g.add_node("build_context", build_context)
    g.add_node("generate_answer", generate_answer)
    g.add_node("postprocess", postprocess)

    # ── 고정 엣지 ──
    g.set_entry_point("analyze_query")
    g.add_edge("analyze_query", "route")
    g.add_edge("route", "retrieve")

    # ── 조건부 분기 1: 신조어 처리 필요? ──
    g.add_conditional_edges(
        "retrieve",
        _needs_neologism_resolution,
        {
            "resolve_neologism": "resolve_neologism",
            "assess_retrieval": "assess_retrieval",
        },
    )
    g.add_edge("resolve_neologism", "re_retrieve")

    # re_retrieve 후 → LLM 품질 평가
    g.add_edge("re_retrieve", "assess_retrieval")

    # ── 조건부 분기 2: 웹검색 필요? (LLM이 결정한 needs_web 기준) ──
    g.add_conditional_edges(
        "assess_retrieval",
        _needs_web_search,
        {"web_search": "web_search", "build_context": "build_context"},
    )

    # ── 나머지 고정 흐름 ──
    g.add_edge("web_search", "build_context")
    g.add_edge("build_context", "generate_answer")
    g.add_edge("generate_answer", "postprocess")
    g.add_edge("postprocess", END)

    return g.compile()


# 모듈 로드 시 그래프 컴파일 (앱 시작 시 1회)
rag_graph = build_graph()