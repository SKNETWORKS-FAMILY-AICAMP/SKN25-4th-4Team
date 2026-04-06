"""
LangGraph nodes — 파이프라인의 각 단계를 독립된 함수로 분리.

각 노드는 GraphState를 받아서, 자기 담당 필드만 업데이트한 dict를 반환한다.

추가된 기능:
- retrieve: 한글→영어 번역 + similarity score 계산
- build_context: weak_evidence 판정
- postprocess: 서론/본론/결론 후처리 + 환각 검증
"""
from __future__ import annotations

import logging
from typing import Any

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.settings import get_settings
from pipeline.category_router import route_category
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
from pipeline.state import GraphState

logger = logging.getLogger(__name__)


# ── 싱글톤 리소스 ──

_vs: VectorStoreManager | None = None
_llm: ChatOpenAI | None = None


def get_vs() -> VectorStoreManager:
    global _vs
    if _vs is None:
        _vs = VectorStoreManager(get_settings())
    return _vs


def get_llm() -> ChatOpenAI:
    global _llm
    if _llm is None:
        s = get_settings()
        _llm = ChatOpenAI(model=s.llm_model, temperature=0, openai_api_key=s.openai_api_key)
    return _llm


def get_collection_counts() -> dict[str, int]:
    return get_vs().get_collection_counts()


# ═══════════════════════════════════════════════════════
# Node 1: 질문 분석
# ═══════════════════════════════════════════════════════

def analyze_query(state: GraphState) -> dict:
    """glossary 매칭, 쿼리 타입 분류, 확장 키워드 생성."""
    question = state["question"]
    matched = match_terms(question)

    return {
        "matched_terms": matched,
        "query_type": detect_query_type(matched),
        "expanded_query": expand_query(question, matched),
        "components": get_components(matched),
        "is_combo": is_combo_query(question, matched),
        "is_supplement": is_supplement_query(question),
        "is_neologism": is_neologism(question, matched),
    }


# ═══════════════════════════════════════════════════════
# Node 2: 카테고리 라우팅
# ═══════════════════════════════════════════════════════

def route(state: GraphState) -> dict:
    """질문을 카테고리로 라우팅. needs_web은 assess_retrieval에서 결정."""
    return {
        "category": route_category(state["question"], state["matched_terms"]),
    }


# ═══════════════════════════════════════════════════════
# Node 3: 1차 검색 (한글→영어 번역 + score 계산 추가)
# ═══════════════════════════════════════════════════════

def _translate_to_english(text: str) -> str:
    """한글 질문을 PubMed 검색용 영어로 번역한다."""
    try:
        result = get_llm().invoke(
            "Translate the following Korean health question into English "
            "for searching PubMed academic papers.\n"
            "Rules:\n"
            "1. Use scientific/ingredient names instead of brand names. "
            "Examples: 마운자로 → tirzepatide, 위고비 → semaglutide, "
            "오젬픽 → semaglutide, 삭센다 → liraglutide.\n"
            "2. If the input contains '검색 확장 키워드:', "
            "prioritize those keywords in the translation.\n"
            "3. Return only the translated text, no explanation.\n\n"
            f"Korean: {text}"
        )
        translated = result.content.strip()
        logger.info("번역 완료 | KO: %s → EN: %s", text[:30], translated[:60])
        return translated
    except Exception as e:
        logger.warning("번역 실패, 원문 사용: %s", e)
        return text


def retrieve(state: GraphState) -> dict:
    """ChromaDB에서 paper/aux를 병렬 MMR 검색 + 한글→영어 번역 + score 계산."""
    # 한글 → 영어 번역
    translated_query = _translate_to_english(state["expanded_query"])

    try:
        result = get_vs().retrieve(
            query=translated_query,
            category=state.get("category"),
            is_supplement=state.get("is_supplement", False),
        )
    except Exception as e:
        logger.error("Retrieval failed: %s", e)
        result = {"paper_docs": [], "aux_docs": [], "paper_score": 0.0}

    paper_score = result.get("paper_score", 0.0)
    paper_docs = result["paper_docs"]

    return {
        "paper_docs": paper_docs,
        "aux_docs": result["aux_docs"],
        "paper_score": paper_score,
        "translated_query": translated_query,
    }


# ═══════════════════════════════════════════════════════
# Node 4: 신조어 해석
# ═══════════════════════════════════════════════════════

def resolve_neologism(state: GraphState) -> dict:
    """신조어를 Tavily로 조회하고 PubMed 검색용 키워드를 추출."""
    resolved = tavily_resolve_neologism(state["question"])
    return {
        "neo_context": resolved.get("context", ""),
        "neo_search_keywords": resolved.get("search_keywords", ""),
    }


# ═══════════════════════════════════════════════════════
# Node 5: 재검색
# ═══════════════════════════════════════════════════════

def re_retrieve(state: GraphState) -> dict:
    """신조어 키워드로 논문 재검색 후 기존 결과와 합산."""
    keywords = state.get("neo_search_keywords", "")
    if not keywords:
        return {}

    logger.info("Neologism re-search: '%s' → '%s'", state["question"], keywords)

    try:
        result = get_vs().retrieve(
            query=keywords,
            category=None,
            is_supplement=state.get("is_supplement", False),
        )
    except Exception as e:
        logger.warning("Re-retrieval failed: %s", e)
        return {}

    existing = state.get("paper_docs", [])
    seen_ids = {d.metadata.get("doc_id", d.page_content[:50]) for d in existing}
    merged = list(existing)

    for doc in result.get("paper_docs", []):
        doc_id = doc.metadata.get("doc_id", doc.page_content[:50])
        if doc_id not in seen_ids:
            merged.append(doc)
            seen_ids.add(doc_id)

    aux = state.get("aux_docs", [])
    if not aux and result.get("aux_docs"):
        aux = result["aux_docs"]

    return {"paper_docs": merged, "aux_docs": aux}


# ═══════════════════════════════════════════════════════
# Node 5.5: LLM 기반 검색 품질 평가 (웹 검색 필요 여부 결정)
# ═══════════════════════════════════════════════════════

from pydantic import BaseModel, Field as PydanticField


class _RetrievalAssessment(BaseModel):
    needs_web: bool = PydanticField(description="Tavily 웹 검색이 필요한지 여부")
    weak_evidence: bool = PydanticField(description="논문 근거가 약한지 여부 (질문과 직접 관련 없거나 유사도 낮음)")
    reasoning: str = PydanticField(description="판단 근거 1~2문장")


_ASSESS_SYSTEM = """\
당신은 RAG 검색 품질 평가자입니다. 사용자 질문에 대해 검색된 논문이 충분한 근거가 되는지 평가하세요.

[needs_web=true 조건 — 하나라도 해당하면 true]
- 검색된 논문이 없거나 질문과 직접 관련이 없음
- 유사도 점수가 0.5 미만으로 낮음
- 최신 트렌드/제품/커뮤니티 정보가 더 적합한 질문
- 신조어·슬랭으로 논문 검색이 어려운 경우

[weak_evidence=true 조건]
- 논문은 있지만 질문에 직접 답하기 어려운 경우 (간접 근거만 존재)

[질문]
{question}

[검색된 논문 ({n_docs}개)]
{paper_summaries}

[평균 유사도 점수] {paper_score:.4f}  (0=완전 불일치, 1=완전 일치)
"""

_assess_llm: Any = None


def _get_assess_llm() -> Any:
    global _assess_llm
    if _assess_llm is None:
        s = get_settings()
        _assess_llm = ChatOpenAI(
            model=s.llm_model,
            temperature=0,
            openai_api_key=s.openai_api_key,
        ).with_structured_output(_RetrievalAssessment)
    return _assess_llm


def assess_retrieval(state: GraphState) -> dict:
    """LLM으로 검색 품질을 평가해 needs_web·weak_evidence를 결정한다.

    하드코딩 threshold 대신 LLM이 실제 논문 내용과 점수를 함께 보고 판단.
    실패 시 score < 0.5 기준으로 안전하게 fallback.
    """
    question = state["question"]
    paper_docs = state.get("paper_docs", [])
    paper_score = state.get("paper_score", 0.0)

    # 상위 3개 논문 요약
    summaries = []
    for i, doc in enumerate(paper_docs[:3], 1):
        title = doc.metadata.get("title", "제목 없음")
        snippet = doc.page_content[:120].replace("\n", " ")
        summaries.append(f"{i}. {title} — {snippet}…")
    paper_summaries = "\n".join(summaries) if summaries else "검색된 논문 없음"

    try:
        prompt = ChatPromptTemplate.from_messages([
            ("system", _ASSESS_SYSTEM),
            ("human", "웹 검색 필요 여부를 평가하세요."),
        ])
        chain = prompt | _get_assess_llm()
        result: _RetrievalAssessment = chain.invoke({
            "question": question,
            "n_docs": len(paper_docs),
            "paper_summaries": paper_summaries,
            "paper_score": paper_score,
        })
        logger.info(
            "검색 품질 평가 | needs_web=%s weak_evidence=%s score=%.4f | %s",
            result.needs_web, result.weak_evidence, paper_score, result.reasoning,
        )
        return {"needs_web": result.needs_web, "weak_evidence": result.weak_evidence}
    except Exception as e:
        logger.warning("검색 품질 평가 실패, score 기반 fallback: %s", e)
        weak = bool(paper_docs) and paper_score < 0.5
        return {"needs_web": weak or not paper_docs, "weak_evidence": weak}


# ═══════════════════════════════════════════════════════
# Node 6: 웹검색 fallback
# ═══════════════════════════════════════════════════════

def web_search(state: GraphState) -> dict:
    """Tavily 웹검색으로 트렌드 컨텍스트를 가져온다."""
    web_ctx = tavily_search_context(state["question"], mode="trend")
    neo_ctx = state.get("neo_context", "")
    if neo_ctx:
        web_ctx = (web_ctx + "\n\n" + neo_ctx).strip()

    # weak_evidence이면 공식기관 검색으로 보완
    if state.get("weak_evidence") and not web_ctx:
        web_ctx = tavily_search_context(state["question"], mode="official")

    return {"web_context": web_ctx}


# ═══════════════════════════════════════════════════════
# Node 7: 컨텍스트 조립 + valid_pmids 수집
# ═══════════════════════════════════════════════════════

def build_context(state: GraphState) -> dict:
    """검색 결과를 포맷하고, 환각 검증용 PMID 목록을 수집한다."""
    paper_docs = state.get("paper_docs", [])
    aux_docs = state.get("aux_docs", [])
    matched = state.get("matched_terms", {})

    term_lines = [
        f"- {alias}: {info.get('description', '')}"
        for alias, info in matched.items()
    ]

    web_context = state.get("web_context", "")
    if not web_context:
        neo_ctx = state.get("neo_context", "")
        if neo_ctx:
            web_context = neo_ctx

    # 환각 방지: 실제 검색된 PMID 수집
    valid_pmids: set[str] = set()
    for doc in paper_docs:
        pmid = doc.metadata.get("pmid", "")
        if pmid:
            valid_pmids.add(str(pmid))

    return {
        "paper_context": format_docs(paper_docs),
        "aux_context": format_docs(aux_docs),
        "web_context": web_context,
        "has_paper_evidence": bool(paper_docs),
        "term_descriptions": "\n".join(term_lines) if term_lines else "없음",
        "valid_pmids": valid_pmids,
    }


# ═══════════════════════════════════════════════════════
# Node 8: LLM 답변 생성
# ═══════════════════════════════════════════════════════

SYSTEM_PROMPT = """\
당신은 BioRAG — 논문 기반 건강 팩트체커입니다.

═══ 절대 규칙 (환각 방지) ═══
- [논문 컨텍스트]에 있는 내용만 근거로 사용하세요.
- 컨텍스트에 없는 논문, 저널명, 수치를 절대 지어내지 마세요.
- 출처 표기 시 반드시 컨텍스트에 있는 논문 제목을 그대로 사용하세요.

═══ 답변 구조 (반드시 준수) ═══

[서론] 질문한 용어/성분이 무엇인지 1~2문장. 출처 붙이지 않습니다.

[본론] 근거가 있는 내용을 문장 단위로 씁니다.
- 각 문장 끝에 반드시 출처를 붙입니다: (출처: 논문 제목, 연도)
- 논문 제목은 [논문 컨텍스트]의 "제목:" 필드에 있는 원문 그대로 사용하세요.
- 문장마다 줄바꿈합니다. 한 줄에 여러 문장 쓰지 마세요.
- 수치가 있으면 반드시 포함하세요.

[결론] 출처 없이 종합 의견 1~2문장 + "자세한 내용은 아래 논문을 확인하세요."

═══ 예시 (논문 있는 경우) ═══

티르제파타이드는 비만 및 제2형 당뇨 치료에 사용되는 주사제입니다.

72주 투여 시 체중이 평균 15~21% 감소했습니다. (출처: Tirzepatide Once Weekly for the Treatment of Obesity, 2022)
3년간 투여 시 제2형 당뇨 진행 위험이 크게 줄었습니다. (출처: Tirzepatide for the Prevention of Type 2 Diabetes, 2025)

개인 건강 상태에 따라 효과가 다를 수 있으므로 전문가 상담이 필요합니다.
자세한 내용은 아래 논문을 확인하세요.

═══ 예시 (논문 없는 경우) ═══

올레샷에 대한 직접적인 논문 근거는 없습니다. 올레샷은 올리브오일과 레몬즙을 공복에 마시는 건강법입니다.

올리브오일은 폴리페놀 성분이 항산화·항염 효과를 가집니다. (출처: Olive oil polyphenols and their implications in cardiovascular disease, 2018)
레몬즙은 헤스페리딘 등 플라보노이드가 항산화·항균 효과를 가집니다. (출처: Citrus flavonoids as therapeutics in human diseases, 2022)

각 성분의 효과는 입증되어 있으나 조합 자체를 검증한 연구는 없습니다.
자세한 내용은 아래 논문을 확인하세요.

═══ 웹검색 결과 사용 시 ═══
웹검색 내용 인용 시 문장 끝에 [웹 검색] 표시를 붙이세요.

═══ 모드별 지침 ═══
- SUPPLEMENT_MODE={supplement_mode}: ON이면 먹는 영양제만 추천. 주사제/시술은 "영양제로는 비권장"으로 분리.
- COMBO_MODE={combo_mode}: ON이면 성분별로 나눠서 각각의 근거만 제시.
- QUERY_TYPE={query_type}

[용어 정보]
{term_descriptions}

[논문 컨텍스트]
{paper_context}

[보조 문서 컨텍스트]
{aux_context}

[웹검색 보조 컨텍스트]
{web_context}
"""


def generate_answer(state: GraphState) -> dict:
    """LLM으로 최종 답변을 생성한다."""
    has_evidence = state.get("has_paper_evidence", False)
    web_context = state.get("web_context", "")

    if not has_evidence and not web_context:
        return {
            "raw_answer": (
                "현재 보유한 논문 데이터에서 관련 근거를 찾지 못했습니다. "
                "데이터를 업데이트하거나 전문의와 상담하세요."
            )
        }

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", "질문: {question}"),
    ])

    chain = prompt | get_llm() | StrOutputParser()
    answer = chain.invoke({
        "question": state["question"],
        "paper_context": state.get("paper_context") or "관련 논문 없음",
        "aux_context": state.get("aux_context") or "보조 문서 없음",
        "web_context": web_context or "웹 검색 결과 없음",
        "supplement_mode": "ON" if state.get("is_supplement") else "OFF",
        "combo_mode": "ON" if state.get("is_combo") else "OFF",
        "query_type": state.get("query_type", "general"),
        "term_descriptions": state.get("term_descriptions", "없음"),
    })

    return {"raw_answer": answer}


# ═══════════════════════════════════════════════════════
# Node 9: 후처리
# ═══════════════════════════════════════════════════════

def _verify_citations(answer: str) -> str:
    """출처 형식이 (출처: 논문 제목, 연도)로 변경되어 PMID 검증은 생략한다."""
    return answer


def _structure_paragraphs(answer: str) -> str:
    """서론/본론/결론 문단 구조화."""
    lines = answer.strip().split("\n")
    intro, body, outro = [], [], []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if "(출처:" in line:
            body.append(line)
        elif body:
            outro.append(line)
        else:
            intro.append(line)

    parts = []
    if intro:
        parts.append("\n".join(intro))
    if body:
        parts.append("\n".join(body))
    if outro:
        parts.append("\n".join(outro))

    return "\n\n".join(parts)


def postprocess(state: GraphState) -> dict:
    """환각 검증 + 한국어 재작성 + 안전 문구 + 서론/본론/결론 구조화."""
    raw = state.get("raw_answer", "")

    # 1. 환각 검증 (PMID 기반 → 논문 제목 기반 출처로 변경되어 pass-through)
    verified = _verify_citations(raw)

    # 2. 한국어 재작성
    answer = rewrite_answer(
        state["question"],
        verified,
        use_llm_rewrite=state.get("is_neologism", False),
    )

    # 3. 안전 문구 적용
    is_indirect = state.get("is_neologism", False) and not state.get("matched_terms")
    answer = apply_safety_notes(
        answer,
        state["question"],
        is_combo=state.get("is_combo", False),
        is_indirect=is_indirect,
    )

    # 4. 서론/본론/결론 문단 구조화
    answer = _structure_paragraphs(answer)

    # 5. 근거 유무 — paper_docs 기준으로만 판단 (score 바 표시 보장)
    has_paper_evidence = state.get("has_paper_evidence", False)

    return {"answer": answer, "has_paper_evidence": has_paper_evidence}