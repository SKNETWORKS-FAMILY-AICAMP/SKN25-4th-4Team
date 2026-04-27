"""
PubMed 논문 수집기.

Biopython Entrez API로 논문 초록 + 메타데이터를 수집한다.
configs/pubmed_topics.json의 토픽 설정을 기반으로 카테고리별 논문을 가져온다.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from Bio import Entrez

from app.settings import DATA_DIR, get_settings, load_pubmed_topics


def configure_entrez() -> None:
    settings = get_settings()
    Entrez.email = settings.ncbi_email
    Entrez.tool = "BioRAGUnified"
    if settings.ncbi_api_key:
        Entrez.api_key = settings.ncbi_api_key


def search_pmids(query: str, max_results: int) -> list[str]:
    with Entrez.esearch(
        db="pubmed",
        term=query,
        retmax=max_results,
        sort="relevance",
        retmode="xml",
    ) as handle:
        result = Entrez.read(handle)
    return result.get("IdList", [])


def fetch_pubmed_xml(pmids: list[str]) -> str:
    if not pmids:
        return ""
    with Entrez.efetch(
        db="pubmed",
        id=",".join(pmids),
        rettype="abstract",
        retmode="xml",
    ) as handle:
        return handle.read()


def _first_text(el: ET.Element | None, xpath: str, default: str = "") -> str:
    if el is None:
        return default
    found = el.find(xpath)
    if found is None or found.text is None:
        return default
    return found.text.strip()


def _extract_year(article: ET.Element) -> str:
    year = _first_text(article, ".//PubDate/Year")
    if year:
        return year
    medline_date = _first_text(article, ".//PubDate/MedlineDate")
    match = re.search(r"(19|20)\d{2}", medline_date)
    if match:
        return match.group(0)
    return _first_text(article, ".//ArticleDate/Year")


def _extract_doi(article: ET.Element) -> str:
    for aid in article.findall(".//ArticleId"):
        if aid.attrib.get("IdType") == "doi" and aid.text:
            return aid.text.strip()
    return ""


def _extract_pub_types(article: ET.Element) -> list[str]:
    return [
        item.text.strip() for item in article.findall(".//PublicationType") if item.text
    ]


def _extract_mesh(article: ET.Element) -> list[str]:
    return [
        item.text.strip()
        for item in article.findall(".//MeshHeading/DescriptorName")
        if item.text
    ]


def _evidence_priority(pub_types: list[str]) -> str:
    lowered = {p.lower() for p in pub_types}
    for label, key in [
        ("systematic-review", "systematic review"),
        ("meta-analysis", "meta-analysis"),
        ("rct", "randomized controlled trial"),
        ("clinical-trial", "clinical trial"),
        ("review", "review"),
    ]:
        if key in lowered:
            return label
    return "other"


def parse_pubmed_xml(
    xml_text: str,
    topic_id: str,
    category: str,
) -> list[dict[str, Any]]:
    if not xml_text:
        return []

    root = ET.fromstring(xml_text)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows: list[dict[str, Any]] = []

    for article in root.findall(".//PubmedArticle"):
        pmid = _first_text(article, ".//PMID")
        title = _first_text(article, ".//ArticleTitle")
        journal = _first_text(article, ".//Journal/Title")
        year = _extract_year(article)
        doi = _extract_doi(article)
        pub_types = _extract_pub_types(article)
        mesh = _extract_mesh(article)

        parts: list[str] = []
        for node in article.findall(".//AbstractText"):
            label = node.attrib.get("Label", "").strip()
            text = "".join(node.itertext()).strip()
            if text:
                parts.append(f"{label}: {text}" if label else text)
        abstract = "\n".join(parts).strip()

        if not (pmid and title and abstract):
            continue

        rows.append(
            {
                "doc_id": f"pmid-{pmid}",
                "pmid": pmid,
                "title": title,
                "abstract": abstract,
                "journal": journal,
                "year": year,
                "doi": doi,
                "topic_id": topic_id,
                "category": category,
                "source_type": "paper",
                "publication_types": pub_types,
                "mesh_terms": mesh,
                "evidence_priority": _evidence_priority(pub_types),
                "source_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "retrieved_at": now,
            }
        )
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def crawl_pubmed(
    output: Path | None = None,
    sleep: float = 0.35,
) -> Path:
    """PubMed 논문을 수집하여 JSONL로 저장한다."""
    if output is None:
        output = DATA_DIR / "raw" / "papers.jsonl"

    configure_entrez()
    topics = load_pubmed_topics()

    all_rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in topics:
        topic_id = item["topic_id"]
        category = item["category"]
        query = item["query"]
        max_results = int(item.get("max_results", 10))

        print(f"[PubMed] {topic_id} | max={max_results}")
        pmids = search_pmids(query, max_results)
        xml_text = fetch_pubmed_xml(pmids)
        rows = parse_pubmed_xml(xml_text, topic_id, category)

        added = 0
        for row in rows:
            if row["pmid"] not in seen:
                seen.add(row["pmid"])
                all_rows.append(row)
                added += 1
        print(f"  → PMID: {len(pmids)} / 저장: {added}")
        time.sleep(sleep)

    write_jsonl(output, all_rows)
    print(f"\n완료: {len(all_rows)}개 논문 → {output}")
    return output


if __name__ == "__main__":
    crawl_pubmed()
