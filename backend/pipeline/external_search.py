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


def tavily_resolve_neologism(query: str) -> dict[str, str]:
    """glossary에 없는 신조어를 Tavily로 조회해 정의 + 검색 키워드를 반환한다."""
    settings = get_settings()
    api_key = settings.tavily_api_key.strip()
    if not api_key:
        return {"context": "", "search_keywords": ""}

    try:
        from langchain_community.tools.tavily_search import TavilySearchResults
    except ImportError:
        return {"context": "", "search_keywords": ""}

    try:
        tavily = TavilySearchResults(max_results=3)
        results = tavily.invoke(f"{query} 성분 정의 건강 효과")
        if not isinstance(results, list) or not results:
            return {"context": "", "search_keywords": ""}

        contents = " ".join(
            r.get("content", "") if isinstance(r, dict) else str(r) for r in results[:3]
        )
        context = contents[:800]

        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model=settings.llm_model,
            temperature=0,
            openai_api_key=settings.openai_api_key,
        )
        search_keywords = llm.invoke(
            f"다음 웹 검색 결과를 바탕으로 '{query}'의 핵심 성분/시술을 "
            f"PubMed에서 검색할 수 있는 영어 키워드 3~5개로만 변환해줘. "
            f"키워드만 공백으로 구분해서 출력:\n{context[:500]}"
        ).content.strip()

        return {"context": context, "search_keywords": search_keywords}

    except Exception as e:
        logger.warning("Tavily neologism resolve failed: %s", e)
        return {"context": "", "search_keywords": ""}
