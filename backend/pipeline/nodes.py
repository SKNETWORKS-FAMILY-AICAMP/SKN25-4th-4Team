"""
LangGraph nodes — 파이프라인의 각 단계를 독립된 함수로 분리.

각 노드는 GraphState를 받아서, 자기 담당 필드만 업데이트한 dict를 반환한다.

환각 방지:
- build_context에서 valid_pmids 목록을 수집
- postprocess에서 답변 속 PMID가 valid_pmids에 있는지 검증
- 없는 PMID 출처는 제거하고 경고 문구 삽입
"""
from __future__ import annotations

import logging
import re
from typing import Any

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

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
    """질문을 4개 카테고리 중 하나로 라우팅."""
    return {
        "category": route_category(state["question"], state["matched_terms"]),
        "needs_web": needs_web_fallback(state["question"], state["matched_terms"]),
    }


# ═══════════════════════════════════════════════════════
# Node 3: 1차 검색
# ═══════════════════════════════════════════════════════

def retrieve(state: GraphState) -> dict:
    """ChromaDB에서 paper/aux를 병렬 MMR 검색."""
    try:
        result = get_vs().retrieve(
            query=state["expanded_query"],
            category=state.get("category"),
            is_supplement=state.get("is_supplement", False),
        )
    except Exception as e:
        logger.error("Retrieval failed: %s", e)
        result = {"paper_docs": [], "aux_docs": []}

    return {
        "paper_docs": result["paper_docs"],
        "aux_docs": result["aux_docs"],
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
# Node 6: 웹검색 fallback
# ═══════════════════════════════════════════════════════

def web_search(state: GraphState) -> dict:
    """Tavily 웹검색으로 트렌드 컨텍스트를 가져온다."""
    web_ctx = tavily_search_context(state["question"], mode="trend")
    neo_ctx = state.get("neo_context", "")
    if neo_ctx:
        web_ctx = (web_ctx + "\n\n" + neo_ctx).strip()
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

    # ── 환각 방지: 실제 검색된 PMID 수집 ──
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
사용자가 건강 트렌드, 영양제, 시술, 식이요법에 대해 질문하면
아래 컨텍스트의 논문 근거를 기반으로 한국어로 답변합니다.

═══ 절대 규칙 (환각 방지) ═══

- 아래 [논문 컨텍스트]에 있는 내용만 근거로 사용하세요.
- 컨텍스트에 없는 논문, PMID, 저널명, 수치를 절대 지어내지 마세요.
- 컨텍스트에 없는 내용은 "확인되지 않았습니다"로 처리하세요.
- 출처 표기 시 반드시 컨텍스트에 있는 PMID만 사용하세요.

═══ 답변 규칙 ═══

1. 근거 우선순위: [논문 컨텍스트] > [보조 문서] > [웹검색]
   - 논문 컨텍스트가 최종 근거입니다.
   - 보조 문서는 용어 설명 보조용입니다.
   - 웹검색은 트렌드/신조어 해석 보조용이며 "~로 알려져 있습니다" 수준으로만 사용하세요.

2. 출처 표기: 주장마다 (출처: 저널명, 연도, PMID:숫자) 형식으로 반드시 붙이세요.

3. 논문 근거가 없으면: "현재 보유한 논문 데이터에서 직접적인 근거를 찾지 못했습니다."로 시작하세요.

4. 금지사항: 개인 진단, 처방, 복용량 결정, 마크다운 헤더(###), 볼드(**) 사용 금지.

5. 한국어: 영어 의학용어는 한국어로 바꾸되, 성분명은 한국에서 통용되는 이름을 쓰세요.
   예: Tirzepatide → 티르제파타이드(마운자로), Semaglutide → 세마글루타이드(위고비)

═══ 모드별 지침 ═══

- SUPPLEMENT_MODE={supplement_mode}: ON이면 먹는 영양제만 추천. 주사제/시술은 "영양제로는 비권장"으로 분리.
- COMBO_MODE={combo_mode}: ON이면 "조합 자체의 임상 근거는 없습니다"로 시작, 성분별로 나눠서 근거 제시.
- QUERY_TYPE={query_type}

═══ 답변 구조 ═══

아래 구조를 따르세요:

[정의] 질문한 용어/성분이 무엇인지 1-2문장 설명
[근거] 논문 컨텍스트에서 찾은 효과/부작용을 성분별로 정리 (각각 출처 표기)
[주의] 한계점, 상담 권고 등 (해당 시)

═══ 예시 ═══

질문: 올레샷 효과 있어?

[정의]
올레샷은 올리브오일과 레몬즙을 섞어 공복에 마시는 건강법입니다.
이 조합 자체를 직접 평가한 임상 논문 근거는 현재 확인되지 않았습니다.

[근거]
올리브오일: 폴리페놀 성분이 심혈관 건강에 도움이 될 수 있다는 연구가 있습니다. (출처: JAMA, 2022, PMID:12345678)
레몬: 비타민C와 플라보노이드가 항산화 작용을 한다는 보고가 있습니다. (출처: Nutrients, 2021, PMID:87654321)

[주의]
두 성분을 조합한 형태의 직접적인 임상 연구는 없으므로, 효과를 단정할 수 없습니다.

═══ 컨텍스트 ═══

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
# Node 9: 후처리 (한국어 재작성 + 안전 문구 + 환각 검증)
# ═══════════════════════════════════════════════════════

def _verify_citations(answer: str, valid_pmids: set[str]) -> str:
    """답변 속 PMID가 실제 검색 결과에 있는지 검증한다.

    - valid_pmids에 없는 PMID를 참조하는 출처 표기는 제거한다.
    - 환각으로 생성된 가짜 출처를 걸러낸다.
    """
    if not valid_pmids:
        # 논문이 아예 없었으면, 출처 표기 자체가 있으면 전부 환각
        citation_pattern = re.compile(
            r"\(출처:[^)]*PMID[:\s]*\d+[^)]*\)",
            re.IGNORECASE,
        )
        cleaned = citation_pattern.sub("", answer)
        if cleaned != answer:
            logger.warning("Hallucinated citations removed (no valid papers)")
            cleaned = cleaned.strip()
            if "출처를 확인할 수 없는 내용이 제거되었습니다" not in cleaned:
                cleaned += "\n\n(일부 출처를 확인할 수 없어 제거되었습니다.)"
            return cleaned
        return answer

    # PMID:숫자 패턴을 찾아서 valid_pmids에 없는 것 필터링
    citation_pattern = re.compile(
        r"\(출처:[^)]*PMID[:\s]*(\d+)[^)]*\)",
        re.IGNORECASE,
    )

    hallucinated_count = 0

    def _check_citation(match: re.Match) -> str:
        nonlocal hallucinated_count
        pmid = match.group(1)
        if pmid in valid_pmids:
            return match.group(0)  # 유효 → 유지
        else:
            hallucinated_count += 1
            logger.warning("Hallucinated PMID removed: %s", pmid)
            return ""  # 무효 → 제거

    cleaned = citation_pattern.sub(_check_citation, answer)

    if hallucinated_count > 0:
        cleaned = cleaned.strip()
        cleaned += f"\n\n(검증되지 않은 출처 {hallucinated_count}건이 제거되었습니다.)"

    return cleaned


def postprocess(state: GraphState) -> dict:
    """한국어 용어 정규화 + 환각 검증 + 안전 문구 적용 + 근거 유무 재판정."""
    raw = state.get("raw_answer", "")
    valid_pmids = state.get("valid_pmids", set())

    # 1. 환각 검증: 가짜 PMID 출처 제거
    verified = _verify_citations(raw, valid_pmids)

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

    # 4. 근거 유무 재판정
    #    검색 결과가 있어도 LLM이 "관련 근거 없다"고 판단했으면 False로 덮어쓴다.
    #    (MMR 검색은 관련 없는 문서도 k개를 채워서 반환하기 때문)
    has_paper_evidence = state.get("has_paper_evidence", False)
    if has_paper_evidence:
        no_evidence_signals = [
            "근거를 찾지 못했습니다",
            "직접적인 근거를 찾지 못",
            "관련 근거를 찾지 못",
            "직접적인 근거가 없",
            "논문 근거는 현재 확인되지 않았습니다",
        ]
        if any(signal in answer for signal in no_evidence_signals):
            has_paper_evidence = False
            logger.info("Evidence flag overridden to False (LLM found no relevant evidence)")

    return {"answer": answer, "has_paper_evidence": has_paper_evidence}