"""
LangGraph state schema.
"""
from __future__ import annotations

from typing import Any, TypedDict
from langchain_core.documents import Document


class GraphState(TypedDict, total=False):
    """RAG 파이프라인 전체 공유 상태."""
    # 입력
    question: str
    # glossary 매칭 결과
    matched_terms: dict[str, Any]
    query_type: str
    expanded_query: str
    components: list[str]
    is_combo: bool
    is_supplement: bool
    is_neologism: bool
    # 라우팅
    category: str | None
    needs_web: bool
    # 검색 결과
    paper_docs: list[Document]
    aux_docs: list[Document]
    paper_context: str
    aux_context: str
    web_context: str
    # 번역 + score
    translated_query: str
    paper_score: float
    weak_evidence: bool
    # 신조어 처리
    neo_search_keywords: str
    neo_context: str
    # LLM 출력
    raw_answer: str
    answer: str
    # 최종 메타
    has_paper_evidence: bool
    term_descriptions: str
    # 환각 검증
    valid_pmids: set[str]