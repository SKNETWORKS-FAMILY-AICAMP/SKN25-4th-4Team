"""
Korean rewriter — 답변을 한국 사용자 친화적 표현으로 재작성한다.

김찬영의 rewrite_answer_for_korean_users + normalize_common_korean_terms +
build_term_guide를 모듈화하고 개선한 버전.
"""
from __future__ import annotations

import logging
import re

from langchain_openai import ChatOpenAI

from app.settings import get_settings

logger = logging.getLogger(__name__)

# ── 고정 용어 치환 테이블 ──

_REPLACEMENTS = {
    "Tirzepatide": "티르제파타이드(마운자로 성분명)",
    "Semaglutide": "세마글루타이드(위고비/오젬픽 성분명)",
    "GLP-1RA": "GLP-1 계열 주사약",
    "GLP-1 receptor agonist": "GLP-1 계열 주사약",
    "retinoic acid": "레티노산(비타민A 계열 성분)",
    "Retinoic acid": "레티노산(비타민A 계열 성분)",
    "polynucleotide": "폴리뉴클레오타이드(PN, 피부주사 성분)",
    "Polynucleotide": "폴리뉴클레오타이드(PN, 피부주사 성분)",
    "PN Injection": "PN 피부주사",
    "HIFU": "고강도 집속 초음파 시술(HIFU)",
    "Ultherapy": "울쎄라(HIFU 리프팅 시술)",
    "Fasting-mimicking diet": "단식 모방 식단",
    "fasting-mimicking diet": "단식 모방 식단",
}


def _normalize_terms(text: str) -> str:
    """고정 치환 테이블로 영어 의학용어를 한국어로 바꾼다."""
    for src, dst in _REPLACEMENTS.items():
        text = text.replace(src, dst)

    # 마크다운 강조 제거
    text = text.replace("**", "")
    # placeholder 제거
    text = re.sub(r"\(쉬운말:\s*[^)]*\)", "", text)
    text = text.replace("쉬운말:", "")
    # 다중 공백 정리
    text = re.sub(r"\s{2,}", " ", text)
    return text


def rewrite_answer(
    question: str,
    answer: str,
    *,
    use_llm_rewrite: bool = False,
) -> str:
    """답변을 한국 사용자 친화적 표현으로 재작성한다.

    Args:
        question: 원본 질문
        answer: LLM이 생성한 원본 답변
        use_llm_rewrite: True면 LLM을 한 번 더 호출해서 전체 재작성
    """
    if not answer.strip():
        return answer

    normalized = _normalize_terms(answer)

    if not use_llm_rewrite:
        return normalized

    # 영어가 많이 남아있는 경우에만 LLM 재작성 수행
    has_english = bool(re.search(r"[A-Za-z]{4,}", normalized))
    if not has_english:
        return normalized

    try:
        settings = get_settings()
        llm = ChatOpenAI(
            model=settings.llm_model,
            temperature=0,
            openai_api_key=settings.openai_api_key,
        )

        rewritten = llm.invoke(
            "아래 답변을 한국 일반 사용자가 바로 이해할 수 있게 다시 써줘.\n"
            "규칙:\n"
            "1. 영어 의학용어는 꼭 필요한 고유명사 외에는 한국어로 바꿔라.\n"
            "2. '쉬운말:' 같은 꼬리표는 아예 쓰지 마라.\n"
            "3. 한국에서 이미 통용되는 말이 있으면 그 말만 간단히 써라.\n"
            "4. [출처: ...] 또는 (출처: ...) 줄은 그대로 유지하라.\n"
            "5. 논문 근거 내용은 추가/삭제하지 말고 표현만 바꿔라.\n"
            "6. 설명형 괄호를 남발하지 마라.\n"
            "7. 과한 강조 표식 없이 평문으로 자연스럽게 설명해라.\n\n"
            f"질문: {question}\n\n"
            f"원본 답변:\n{normalized}"
        ).content.strip()

        return _normalize_terms(rewritten)

    except Exception as e:
        logger.warning("LLM rewrite failed: %s", e)
        return normalized


def apply_safety_notes(
    answer: str,
    question: str,
    *,
    is_combo: bool = False,
    is_indirect: bool = False,
) -> str:
    """조합/간접 근거 안전 문구를 답변에 추가한다."""
    text = answer.strip()

    if is_combo:
        combo_header = (
            f"⚠️ '{question}'의 조합 자체를 직접 평가한 임상 논문 근거는 현재 확인되지 않았습니다. "
            "아래 내용은 개별 성분에 대한 논문 근거입니다."
        )
        combo_footer = (
            "⚠️ 개별 성분 효과는 입증되었으나, 직접 혼합 복용에 대한 임상 데이터는 부족합니다. "
            "복용 전 의사 또는 약사와 상담하는 것이 좋습니다."
        )
        if combo_header not in text:
            text = combo_header + "\n\n" + text
        if combo_footer not in text:
            text = text + "\n\n" + combo_footer

    elif is_indirect:
        indirect_header = (
            f"'{question}' 자체를 직접 평가한 임상 논문 근거는 현재 확인되지 않았습니다. "
            "아래 내용은 관련 성분 또는 유사 주제의 논문 근거입니다."
        )
        indirect_footer = (
            "질문한 표현이 실제 제품명·복용법·속칭일 수 있으므로, "
            "복용 전 의사 또는 약사와 상담하는 것이 좋습니다."
        )
        if indirect_header not in text:
            text = indirect_header + "\n\n" + text
        if indirect_footer not in text:
            text = text + "\n\n" + indirect_footer

    return text
