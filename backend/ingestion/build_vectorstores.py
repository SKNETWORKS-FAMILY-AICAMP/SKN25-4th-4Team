"""
벡터스토어 빌더 — papers/aux JSONL → ChromaDB 적재.

papers.jsonl → biorag_papers 컬렉션 (청킹 포함)
aux_docs.jsonl → biorag_aux 컬렉션
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings

from app.settings import DATA_DIR, get_settings


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _split_text(text: str, max_chars: int = 1600, overlap: int = 200) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return chunks


def papers_to_documents(rows: list[dict[str, Any]]) -> tuple[list[Document], list[str]]:
    docs: list[Document] = []
    ids: list[str] = []
    for row in rows:
        text = (
            f"Title: {row['title']}\n"
            f"Abstract: {row['abstract']}\n"
            f"Publication Types: {', '.join(row.get('publication_types', []))}\n"
            f"MeSH Terms: {', '.join(row.get('mesh_terms', []))}"
        )
        for idx, chunk in enumerate(_split_text(text)):
            docs.append(
                Document(
                    page_content=chunk,
                    metadata={
                        "doc_id": row["doc_id"],
                        "pmid": row.get("pmid", ""),
                        "title": row.get("title", ""),
                        "journal": row.get("journal", ""),
                        "year": str(row.get("year", "")),
                        "category": row.get("category", ""),
                        "topic_id": row.get("topic_id", ""),
                        "source_type": row.get("source_type", "paper"),
                        "evidence_priority": row.get("evidence_priority", "other"),
                        "source_url": row.get("source_url", ""),
                    },
                )
            )
            ids.append(f"{row['doc_id']}-{idx}")
    return docs, ids


def aux_to_documents(rows: list[dict[str, Any]]) -> tuple[list[Document], list[str]]:
    docs: list[Document] = []
    ids: list[str] = []
    for row in rows:
        extra = []
        if row.get("also_called"):
            extra.append("Also called: " + ", ".join(row["also_called"]))
        if row.get("expansions"):
            extra.append("Expansions: " + ", ".join(row["expansions"]))
        if row.get("mesh_terms"):
            extra.append("MeSH Terms: " + ", ".join(row["mesh_terms"]))
        text = (
            f"Title: {row['title']}\nSummary: {row.get('content', '')}\n"
            + "\n".join(extra)
        )
        docs.append(
            Document(
                page_content=text,
                metadata={
                    "doc_id": row["doc_id"],
                    "title": row.get("title", ""),
                    "category": row.get("category", ""),
                    "source_type": row.get("source_type", "aux"),
                    "source_name": row.get("source_name", ""),
                    "source_url": row.get("source_url", ""),
                },
            )
        )
        ids.append(row["doc_id"])
    return docs, ids


def build_vectorstores(
    papers_path: Path | None = None,
    aux_path: Path | None = None,
    reset: bool = False,
) -> None:
    load_dotenv()
    settings = get_settings()

    if papers_path is None:
        papers_path = DATA_DIR / "raw" / "papers.jsonl"
    if aux_path is None:
        aux_path = DATA_DIR / "raw" / "aux_docs.jsonl"

    db_dir = Path(settings.chroma_db_path)

    if reset and db_dir.exists():
        shutil.rmtree(db_dir)
        print(f"[reset] {db_dir} 삭제 완료")

    paper_rows = read_jsonl(papers_path)
    aux_rows = read_jsonl(aux_path)

    paper_docs, paper_ids = papers_to_documents(paper_rows)
    aux_docs, aux_ids = aux_to_documents(aux_rows)

    embeddings = OpenAIEmbeddings(
        model=settings.embedding_model,
        openai_api_key=settings.openai_api_key,
    )

    if paper_docs:
        paper_store = Chroma(
            collection_name=settings.paper_collection,
            persist_directory=str(db_dir),
            embedding_function=embeddings,
        )
        paper_store.add_documents(documents=paper_docs, ids=paper_ids)
        print(f"Papers 적재: {len(paper_docs)}개 청크")

    if aux_docs:
        aux_store = Chroma(
            collection_name=settings.aux_collection,
            persist_directory=str(db_dir),
            embedding_function=embeddings,
        )
        aux_store.add_documents(documents=aux_docs, ids=aux_ids)
        print(f"Aux 적재: {len(aux_docs)}개")

    print(f"DB 위치: {db_dir}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    build_vectorstores(reset=args.reset)
