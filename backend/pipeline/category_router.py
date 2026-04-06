"""
Category router — 질문을 도메인 카테고리로 라우팅한다.

biorag의 _route_category + 조민서의 get_section 로직을 통합.
glossary 힌트(가중치 3) + 키워드 매칭(가중치 1)으로 투표하여
가장 점수가 높은 카테고리를 반환한다.
"""
from __future__ import annotations

from typing import Any

from app.settings import load_domain_scope


def route_category(
    question: str,
    matched_terms: dict[str, Any],
) -> str | None:
    """질문을 가장 적합한 카테고리로 라우팅한다. 매칭이 없으면 None."""
    domain_scope = load_domain_scope()
    votes: dict[str, int] = {}
    lowered = question.lower()

    # glossary 힌트 (강한 신호)
    for info in matched_terms.values():
        hint = info.get("category_hint")
        if hint:
            votes[hint] = votes.get(hint, 0) + 3

    # domain_scope 키워드 매칭
    for category, info in domain_scope.items():
        for kw in info["keywords"]:
            if kw.lower() in lowered:
                votes[category] = votes.get(category, 0) + 1

    if not votes:
        return None

    return max(votes, key=votes.get)


