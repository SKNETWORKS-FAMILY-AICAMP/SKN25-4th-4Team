"""
Retriever — ChromaDB paper/aux 병렬 검색.

biorag의 paper/aux parallel retrieval + MMR을 분리한 모듈.
김찬영의 supplement filter 로직도 통합.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.runnables import RunnableLambda, RunnableParallel
from langchain_openai import OpenAIEmbeddings

from app.settings import Settings, get_settings

logger = logging.getLogger(__name__)

# ── supplement filter (김찬영 코드 기반) ──

_SUPPLEMENT_BLOCKED = [
    "injection",
    "injectable",
    "intradermal",
    "ultherapy",
    "hifu",
    "laser",
    "procedure",
    "surgery",
    "device",
    "pn injection",
]
_SUPPLEMENT_PREFERRED = [
    "dietary",
    "supplement",
    "oral",
    "ingestion",
    "nutrient",
    "vitamin",
    "mineral",
    "omega",
    "collagen peptide",
    "probiotic",
    "food",
    "nutrition",
]


def _filter_supplement_docs(docs: list[Document]) -> list[Document]:
    """영양제 질문에서 주사/시술 맥락 문서를 제외한다."""
    selected = [
        d
        for d in docs
        if not any(b in (d.page_content or "").lower() for b in _SUPPLEMENT_BLOCKED)
    ]
    narrowed = [
        d
        for d in selected
        if any(p in (d.page_content or "").lower() for p in _SUPPLEMENT_PREFERRED)
    ]
    return narrowed or selected or docs


class VectorStoreManager:
    """ChromaDB 벡터스토어 연결을 관리한다."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._embeddings = OpenAIEmbeddings(
            model=self._settings.embedding_model,
            openai_api_key=self._settings.openai_api_key,
        )
        self._paper_store: Chroma | None = None
        self._aux_store: Chroma | None = None

    def _get_paper_store(self) -> Chroma:
        if self._paper_store is None:
            self._paper_store = Chroma(
                collection_name=self._settings.paper_collection,
                persist_directory=self._settings.chroma_db_path,
                embedding_function=self._embeddings,
            )
        return self._paper_store

    def _get_aux_store(self) -> Chroma:
        if self._aux_store is None:
            self._aux_store = Chroma(
                collection_name=self._settings.aux_collection,
                persist_directory=self._settings.chroma_db_path,
                embedding_function=self._embeddings,
            )
        return self._aux_store

    def get_collection_counts(self) -> dict[str, int]:
        """각 컬렉션의 문서 수를 반환한다."""
        counts = {}
        try:
            counts["papers"] = self._get_paper_store()._collection.count()
        except Exception:
            counts["papers"] = 0
        try:
            counts["aux"] = self._get_aux_store()._collection.count()
        except Exception:
            counts["aux"] = 0
        return counts

    def retrieve(
        self,
        query: str,
        category: str | None = None,
        is_supplement: bool = False,
    ) -> dict[str, Any]:
        """paper/aux를 병렬로 검색한다."""
        s = self._settings

        # paper retriever
        paper_kwargs: dict[str, Any] = {
            "k": s.paper_k,
            "fetch_k": s.paper_fetch_k,
            "lambda_mult": s.mmr_lambda,
        }
        if category:
            paper_kwargs["filter"] = {"category": category}

        paper_retriever = self._get_paper_store().as_retriever(
            search_type="mmr",
            search_kwargs=paper_kwargs,
        )

        # aux retriever
        aux_kwargs: dict[str, Any] = {
            "k": s.aux_k,
            "fetch_k": s.aux_fetch_k,
            "lambda_mult": s.mmr_lambda,
        }
        if category:
            aux_kwargs["filter"] = {"category": category}

        aux_retriever = self._get_aux_store().as_retriever(
            search_type="mmr",
            search_kwargs=aux_kwargs,
        )

        # 병렬 검색
        parallel = RunnableParallel(
            paper_docs=RunnableLambda(lambda q: paper_retriever.invoke(q)),
            aux_docs=RunnableLambda(lambda q: aux_retriever.invoke(q)),
        )

        try:
            result = parallel.invoke(query)
        except Exception as e:
            logger.warning("Retrieval failed, trying without category filter: %s", e)
            paper_kwargs.pop("filter", None)
            aux_kwargs.pop("filter", None)
            paper_retriever = self._get_paper_store().as_retriever(
                search_type="mmr",
                search_kwargs=paper_kwargs,
            )
            aux_retriever = self._get_aux_store().as_retriever(
                search_type="mmr",
                search_kwargs=aux_kwargs,
            )
            parallel = RunnableParallel(
                paper_docs=RunnableLambda(lambda q: paper_retriever.invoke(q)),
                aux_docs=RunnableLambda(lambda q: aux_retriever.invoke(q)),
            )
            result = parallel.invoke(query)

        paper_docs = result.get("paper_docs", [])
        aux_docs = result.get("aux_docs", [])

        if is_supplement:
            paper_docs = _filter_supplement_docs(paper_docs)

        # MMR 결과 기반 similarity score 계산
        paper_score = 0.0
        if paper_docs:
            try:
                scored = (
                    self._get_paper_store().similarity_search_with_relevance_scores(
                        query, k=s.paper_fetch_k
                    )
                )
                score_map = {
                    d.metadata.get("doc_id", d.page_content[:40]): sc
                    for d, sc in scored
                }
                scores = [
                    score_map[doc.metadata.get("doc_id", doc.page_content[:40])]
                    for doc in paper_docs
                    if doc.metadata.get("doc_id", doc.page_content[:40]) in score_map
                ]
                paper_score = (
                    max(0.0, min(sum(scores) / len(scores) * 1.7, 1.0))
                    if scores
                    else 0.0
                )
                logger.info("평균 similarity score: %.4f", paper_score)
            except Exception as e:
                logger.warning("Score 계산 실패: %s", e)

        return {
            "paper_docs": paper_docs,
            "aux_docs": aux_docs,
            "paper_score": paper_score,
        }


def format_docs(docs: list[Document]) -> str:
    """검색된 문서를 LLM 컨텍스트 문자열로 포매팅한다."""
    if not docs:
        return ""

    blocks: list[str] = []
    for idx, doc in enumerate(docs, start=1):
        meta = doc.metadata
        label = meta.get("source_type", "doc").upper()
        blocks.append(
            f"[{label} {idx}]\n"
            f"제목: {meta.get('title', '')}\n"
            f"저널/출처: {meta.get('journal', meta.get('source_name', ''))}\n"
            f"연도: {meta.get('year', '')}\n"
            f"PMID: {meta.get('pmid', '')}\n"
            f"본문: {doc.page_content}"
        )
    return "\n\n---\n\n".join(blocks)


def docs_to_source_info(docs: list[Document]) -> list[dict[str, str]]:
    """문서 리스트를 SourceInfo dict 리스트로 변환한다."""
    items = []
    for doc in docs:
        meta = doc.metadata
        items.append(
            {
                "title": meta.get("title", ""),
                "journal": meta.get("journal", meta.get("source_name", "")),
                "year": str(meta.get("year", "")),
                "pmid": meta.get("pmid", ""),
                "source_type": meta.get("source_type", ""),
                "url": meta.get("source_url", ""),
            }
        )
    return items
