"""
LangGraph 기반 RAG 서비스.
graph.py의 컴파일된 그래프를 호출하고,
GraphState → AskResponse 변환을 담당하는 얇은 래퍼.
"""

from __future__ import annotations

import logging
from typing import AsyncGenerator

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
            expanded_query=result.get(
                "translated_query", result.get("expanded_query", "")
            ),
        )

    async def ask_stream(self, question: str) -> AsyncGenerator[dict, None]:
        """스트리밍 버전 — 파이프라인을 순차 실행하고 LLM 토큰을 yield한다.

        이벤트 형식:
          {"type": "chunk", "text": "토큰..."}      — LLM 생성 중
          {"type": "done",  ...AskResponse 필드...} — 후처리 완료
        """
        from langchain_core.output_parsers import StrOutputParser
        from langchain_core.prompts import ChatPromptTemplate

        from pipeline.nodes import (
            SYSTEM_PROMPT,
            analyze_query,
            assess_retrieval,
            build_context,
            get_llm,
            postprocess,
            re_retrieve,
            resolve_neologism,
            retrieve,
            route,
            web_search,
        )

        state: dict = {"question": question}

        # ── 파이프라인 노드 순차 실행 ──
        for node_fn in [analyze_query, route, retrieve]:
            state.update(node_fn(state))

        needs_neo = state.get("is_neologism") or (
            not state.get("paper_docs") and not state.get("matched_terms")
        )
        if needs_neo:
            state.update(resolve_neologism(state))
            state.update(re_retrieve(state))

        state.update(assess_retrieval(state))

        if state.get("needs_web"):
            state.update(web_search(state))

        state.update(build_context(state))

        yield {"type": "status", "text": "답변 생성 중..."}

        # ── LLM 스트리밍 ──
        has_evidence = state.get("has_paper_evidence", False)
        web_context = state.get("web_context", "")

        if not has_evidence and not web_context:
            full_answer = (
                "현재 보유한 논문 데이터에서 관련 근거를 찾지 못했습니다. "
                "데이터를 업데이트하거나 전문의와 상담하세요."
            )
            yield {"type": "chunk", "text": full_answer}
        else:
            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", SYSTEM_PROMPT),
                    ("human", "질문: {question}"),
                ]
            )
            chain = prompt | get_llm() | StrOutputParser()
            full_answer = ""

            async for chunk in chain.astream(
                {
                    "question": state["question"],
                    "paper_context": state.get("paper_context") or "관련 논문 없음",
                    "aux_context": state.get("aux_context") or "보조 문서 없음",
                    "web_context": web_context or "웹 검색 결과 없음",
                    "supplement_mode": "ON" if state.get("is_supplement") else "OFF",
                    "combo_mode": "ON" if state.get("is_combo") else "OFF",
                    "query_type": state.get("query_type", "general"),
                    "term_descriptions": state.get("term_descriptions", "없음"),
                }
            ):
                full_answer += chunk
                yield {"type": "chunk", "text": chunk}

        # ── 후처리 ──
        state["raw_answer"] = full_answer
        state.update(postprocess(state))

        paper_docs = state.get("paper_docs", [])
        aux_docs = state.get("aux_docs", [])

        yield {
            "type": "done",
            "answer": state.get("answer", full_answer),
            "category": state.get("category"),
            "query_type": state.get("query_type", "general"),
            "matched_terms": [],
            "paper_sources": docs_to_source_info(paper_docs),
            "aux_sources": docs_to_source_info(aux_docs),
            "has_paper_evidence": state.get("has_paper_evidence", False),
            "weak_evidence": state.get("weak_evidence", False),
            "paper_score": state.get("paper_score", 0.0),
            "needs_web": state.get("needs_web", False),
            "expanded_query": state.get(
                "translated_query", state.get("expanded_query", "")
            ),
        }
