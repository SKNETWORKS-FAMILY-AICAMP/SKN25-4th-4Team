"""
External search — Tavily 웹검색 fallback.

glossary에 없는 최신 트렌드 표현이 들어왔을 때만 사용한다.
최종 의학 근거로 쓰지 않고 용어 해석/최신성 보조용이다.
"""
from __future__ import annotations

import logging
from typing import Any

from app.settings import get_settings, load_trusted_domains

logger = logging.getLogger(__name__)


def tavily_search_context(query: str, mode: str = "trend") -> str:
    """Tavily로 웹검색을 수행하고 결과를 컨텍스트 문자열로 반환한다."""
    settings = get_settings()
    api_key = settings.tavily_api_key.strip()
    if not api_key:
        return ""

    try:
        from tavily import TavilyClient
    except ImportError:
        logger.warning("tavily-python not installed, skipping web search")
        return ""

    domains = load_trusted_domains()
    include_domains = (
        domains.get("trend_domains", [])
        if mode == "trend"
        else domains.get("official_domains", [])
    )

    try:
        client = TavilyClient(api_key=api_key)
        response: dict[str, Any] = client.search(
            query=query,
            max_results=3,
            search_depth="basic",
            include_raw_content=True,
            include_domains=include_domains or None,
        )
    except Exception as e:
        logger.warning("Tavily search failed: %s", e)
        return ""

    results = response.get("results", [])
    if not results:
        return ""

    parts: list[str] = []
    for idx, item in enumerate(results, start=1):
        content = item.get("raw_content") or item.get("content", "")
        # 길이 제한
        if len(content) > 1000:
            content = content[:1000] + "..."
        parts.append(
            f"[웹 {idx}]\n"
            f"제목: {item.get('title', '')}\n"
            f"URL: {item.get('url', '')}\n"
            f"내용: {content}"
        )
    return "\n\n---\n\n".join(parts)


def tavily_resolve_neologism(query: str) -> str:
    """glossary에 없는 신조어를 Tavily로 조회해 정의를 반환한다."""
    settings = get_settings()
    api_key = settings.tavily_api_key.strip()
    if not api_key:
        return ""

    try:
        from langchain_community.tools.tavily_search import TavilySearchResults
    except ImportError:
        return ""

    try:
        tavily = TavilySearchResults(max_results=2)
        results = tavily.invoke(f"{query} 성분 정의 건강")
        if isinstance(results, list):
            contents = " ".join(
                r.get("content", "") if isinstance(r, dict) else str(r)
                for r in results[:2]
            )
            return contents[:500]
    except Exception as e:
        logger.warning("Tavily neologism resolve failed: %s", e)

    return ""
