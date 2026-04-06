"""
LangGraph 기반 RAG 서비스.
graph.py의 컴파일된 그래프를 호출하고,
GraphState → AskResponse 변환을 담당하는 얇은 래퍼.
"""
from __future__ import annotations

import logging

from app.schemas import AskResponse, MatchedTermInfo, SourceInfo
from pipeline.graph import rag_graph
from pipeline.nodes import get_collection_counts
from pipeline.retriever import docs_to_source_info

logger = logging.getLogger(__name__)


class HybridRAGService:
    """Hybrid RAG 서비스. 앱 시작 시 한 번 생성하여 재사용한다."""

    def get_collection_counts(self) -> dict[str, int]:
        return get_collection_counts()

    def ask(self, question: str) -> AskResponse:
        """LangGraph 파이프라인을 실행하고 AskResponse를 반환한다."""
        result = rag_graph.invoke({"question": question})

        matched = result.get("matched_terms", {})
        matched_term_infos = [
            MatchedTermInfo(
                alias=alias,
                description=info.get("description", ""),
                expansions=info.get("expansions", []),
                query_type=info.get("query_type", "general"),
            )
            for alias, info in matched.items()
        ]

        paper_docs = result.get("paper_docs", [])
        aux_docs = result.get("aux_docs", [])

        return AskResponse(
            answer=result.get("answer", "응답을 생성하지 못했습니다."),
            category=result.get("category"),
            query_type=result.get("query_type", "general"),
            matched_terms=matched_term_infos,
            paper_sources=[SourceInfo(**s) for s in docs_to_source_info(paper_docs)],
            aux_sources=[SourceInfo(**s) for s in docs_to_source_info(aux_docs)],
            has_paper_evidence=result.get("has_paper_evidence", False),
            weak_evidence=result.get("weak_evidence", False),
            paper_score=result.get("paper_score", 0.0),
            needs_web=result.get("needs_web", False),
            expanded_query=result.get("translated_query", result.get("expanded_query", "")),
        )