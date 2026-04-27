"""
Glossary matcher — 신조어/브랜드명 감지 및 쿼리 확장.

김찬영의 detect_terms + 조민서의 KNOWN_TERMS + biorag의 _match_glossary를 통합.
glossary.json을 읽어 한국어 질문에서 신조어를 감지하고,
영어 확장 키워드 + 카테고리 힌트 + 쿼리 타입을 반환한다.
"""

from __future__ import annotations

from typing import Any

from app.settings import load_glossary


def match_terms(question: str) -> dict[str, Any]:
    """질문에 포함된 glossary 용어를 모두 찾아 반환한다."""
    glossary = load_glossary()
    matched: dict[str, Any] = {}
    lowered = question.lower()

    for alias, info in glossary.items():
        if alias.lower() in lowered:
            matched[alias] = info

    return matched


def expand_query(question: str, matched_terms: dict[str, Any]) -> str:
    """매칭된 용어의 영어 확장 키워드를 질문에 덧붙인다."""
    expansions: list[str] = []
    for info in matched_terms.values():
        expansions.extend(info.get("expansions", []))

    if not expansions:
        return question

    unique = list(dict.fromkeys(expansions))
    return question + "\n검색 확장 키워드: " + ", ".join(unique)


def get_components(matched_terms: dict[str, Any]) -> list[str]:
    """매칭된 용어에서 성분 리스트를 추출한다."""
    components: list[str] = []
    for info in matched_terms.values():
        components.extend(info.get("components", []))
    return list(dict.fromkeys(components))


def detect_query_type(matched_terms: dict[str, Any]) -> str:
    """매칭된 용어의 query_type 중 우선순위가 높은 것을 반환한다."""
    priority = {"combo": 0, "medicine": 1, "diet": 2, "general": 3}
    best_type = "general"
    best_priority = 999

    for info in matched_terms.values():
        qt = info.get("query_type", "general")
        p = priority.get(qt, 3)
        if p < best_priority:
            best_priority = p
            best_type = qt

    return best_type


def is_combo_query(question: str, matched_terms: dict[str, Any]) -> bool:
    """조합 질문인지 판별한다."""
    if detect_query_type(matched_terms) == "combo":
        return True

    combo_indicators = ["조합", "섞어", "함께", "같이", "and", "+"]
    lowered = question.lower()
    return any(x in lowered for x in combo_indicators)


def is_supplement_query(question: str) -> bool:
    """영양제/건강기능식품 질문인지 판별한다."""
    keywords = ["영양제", "건강기능식품", "보충제", "섭취", "먹", "추천", "supplement"]
    lowered = question.lower()
    return any(k in lowered for k in keywords)


def is_neologism(question: str, matched_terms: dict[str, Any]) -> bool:
    """glossary에 없는 짧은 신조어/브랜드명 질문인지 판별한다."""
    if matched_terms:
        return False
    stripped = question.replace(" ", "")
    return len(stripped) <= 20 and len(question.split()) <= 3
