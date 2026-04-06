"""
Hybrid RAG service — 모든 파이프라인 컴포넌트를 조합하는 메인 서비스.

전체 흐름:
1. glossary 매칭 → 신조어 감지 + 쿼리 확장
2. 카테고리 라우팅
3. paper/aux 병렬 검색 (MMR)
4. 필요 시 Tavily fallback
5. LLM 답변 생성
6. 한국어 재작성 + 안전 문구 적용
"""
from __future__ import annotations

import logging
from typing import Any

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.schemas import (
    AskResponse,
    MatchedTermInfo,
    SourceInfo,
)
from app.settings import get_settings
from pipeline.category_router import needs_web_fallback, route_category
from pipeline.external_search import tavily_resolve_neologism, tavily_search_context
from pipeline.glossary_matcher import (
    detect_query_type,
    expand_query,
    get_components,
    is_combo_query,
    is_neologism,
    is_supplement_query,
    match_terms,
)
from pipeline.korean_rewriter import apply_safety_notes, rewrite_answer
from pipeline.retriever import (
    VectorStoreManager,
    docs_to_source_info,
    format_docs,
)

logger = logging.getLogger(__name__)

# ── System prompt ──

SYSTEM_PROMPT = """\
당신은 근거 기반 건강 QA 어시스턴트입니다.
다음 규칙을 반드시 지키세요.

1. 논문 컨텍스트(paper_context)가 최우선 근거입니다.
2. 보조 문서(aux_context)는 용어 설명, 소비자 친화 설명, 동의어 보조용으로만 사용하세요.
3. 웹검색(web_context)은 최신 용어/트렌드 해석 보조용으로만 사용하고, 논문 근거처럼 단정하지 마세요.
4. 직접적인 논문 근거가 없으면 반드시 "현재 보유한 논문 데이터에서 직접적인 근거를 찾지 못했습니다."로 시작하세요.
5. 핵심 주장 뒤에는 반드시 (출처: 저널명, 연도, PMID) 형식으로 표기하세요.
6. 개인 진단, 처방, 복용량 결정은 하지 마세요.
7. 한국어로 답변하세요.
8. 마크다운 헤더(###, **) 사용을 최소화하세요.
9. SUPPLEMENT_MODE가 ON이면 먹는 영양제/섭취 가능한 성분만 추천하세요. 주사제나 시술은 "영양제로는 비권장"으로 분리 표기하세요.
10. COMBO_MODE가 ON이면 조합 자체가 효과적이라고 단정하지 말고, 성분별로 나눠 각각의 논문 근거만 제시하세요.

[모드]
- SUPPLEMENT_MODE: {supplement_mode}
- COMBO_MODE: {combo_mode}
- QUERY_TYPE: {query_type}

[용어 정보]
{term_descriptions}

[논문 컨텍스트]
{paper_context}

[보조 문서 컨텍스트]
{aux_context}

[웹검색 보조 컨텍스트]
{web_context}
"""


class HybridRAGService:
    """Hybrid RAG 서비스. 앱 시작 시 한 번 생성하여 재사용한다."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._vs = VectorStoreManager(self._settings)
        self._llm = ChatOpenAI(
            model=self._settings.llm_model,
            temperature=0,
            openai_api_key=self._settings.openai_api_key,
        )
        self._prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            ("human", "질문: {question}"),
        ])
        self._parser = StrOutputParser()

    def get_collection_counts(self) -> dict[str, int]:
        return self._vs.get_collection_counts()

    def ask(self, question: str) -> AskResponse:
        """전체 RAG 파이프라인을 실행하고 AskResponse를 반환한다."""

        # 1. glossary 매칭
        matched = match_terms(question)
        query_type = detect_query_type(matched)
        expanded = expand_query(question, matched)
        components = get_components(matched)
        is_combo = is_combo_query(question, matched)
        is_supplement = is_supplement_query(question)
        is_neo = is_neologism(question, matched)

        # 신조어인데 glossary에 없으면 Tavily로 조회
        neo_context = ""
        if is_neo:
            neo_context = tavily_resolve_neologism(question)

        # 2. 카테고리 라우팅
        category = route_category(question, matched)

        # 3. 웹 검색 필요 여부
        needs_web = needs_web_fallback(question, matched)

        # 4. 검색
        try:
            retrieved = self._vs.retrieve(
                query=expanded,
                category=category,
                is_supplement=is_supplement,
            )
        except Exception as e:
            logger.error("Retrieval failed: %s", e)
            retrieved = {"paper_docs": [], "aux_docs": []}

        paper_docs = retrieved["paper_docs"]
        aux_docs = retrieved["aux_docs"]

        paper_context = format_docs(paper_docs)
        aux_context = format_docs(aux_docs)

        # 5. 웹검색 fallback
        web_context = ""
        if needs_web:
            web_context = tavily_search_context(question, mode="trend")
        if neo_context:
            web_context = (web_context + "\n\n" + neo_context).strip()

        # 6. 논문 없음 판별
        has_paper_evidence = bool(paper_docs)

        # 7. 용어 설명 텍스트 생성
        term_descriptions = ""
        if matched:
            lines = []
            for alias, info in matched.items():
                lines.append(f"- {alias}: {info.get('description', '')}")
            term_descriptions = "\n".join(lines)

        # 8. LLM 답변 생성
        if not has_paper_evidence and not web_context:
            answer = (
                "현재 보유한 논문 데이터에서 관련 근거를 찾지 못했습니다. "
                "데이터를 업데이트하거나 전문의와 상담하세요."
            )
        else:
            chain = self._prompt | self._llm | self._parser
            answer = chain.invoke({
                "question": question,
                "paper_context": paper_context or "관련 논문 없음",
                "aux_context": aux_context or "보조 문서 없음",
                "web_context": web_context or "웹 검색 결과 없음",
                "supplement_mode": "ON" if is_supplement else "OFF",
                "combo_mode": "ON" if is_combo else "OFF",
                "query_type": query_type,
                "term_descriptions": term_descriptions or "없음",
            })

        # 9. 한국어 재작성
        answer = rewrite_answer(
            question,
            answer,
            use_llm_rewrite=is_neo,
        )

        # 10. 안전 문구 적용
        is_indirect = is_neo and not matched
        answer = apply_safety_notes(
            answer,
            question,
            is_combo=is_combo,
            is_indirect=is_indirect,
        )

        # 11. 응답 조립
        matched_term_infos = [
            MatchedTermInfo(
                alias=alias,
                description=info.get("description", ""),
                expansions=info.get("expansions", []),
                query_type=info.get("query_type", "general"),
            )
            for alias, info in matched.items()
        ]

        return AskResponse(
            answer=answer,
            category=category,
            query_type=query_type,
            matched_terms=matched_term_infos,
            paper_sources=[SourceInfo(**s) for s in docs_to_source_info(paper_docs)],
            aux_sources=[SourceInfo(**s) for s in docs_to_source_info(aux_docs)],
            has_paper_evidence=has_paper_evidence,
            needs_web=needs_web,
            expanded_query=expanded,
        )
