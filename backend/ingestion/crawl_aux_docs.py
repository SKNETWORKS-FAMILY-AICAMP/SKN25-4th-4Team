"""
MedlinePlus + glossary 보조문서 수집기.

MedlinePlus XML에서 도메인 범위에 해당하는 건강 토픽을 수집하고,
glossary 항목도 문서화하여 aux_docs.jsonl로 저장한다.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import requests

from app.settings import DATA_DIR, load_domain_scope, load_glossary

MEDLINEPLUS_INDEX_URL = "https://medlineplus.gov/xml.html"


def _latest_xml_url() -> str:
    resp = requests.get(MEDLINEPLUS_INDEX_URL, timeout=30)
    resp.raise_for_status()
    matches = re.findall(r"/xml/mplus_topics_\d{4}-\d{2}-\d{2}\.xml", resp.text)
    if not matches:
        raise RuntimeError("MedlinePlus 최신 XML 링크를 찾지 못했습니다.")
    latest = sorted(set(matches), reverse=True)[0]
    return f"https://medlineplus.gov{latest}"


def _match_category(text: str, scope: dict[str, Any]) -> str | None:
    lowered = text.lower()
    best, best_score = None, 0
    for cat, info in scope.items():
        score = sum(1 for kw in info["keywords"] if kw.lower() in lowered)
        if score > best_score:
            best, best_score = cat, score
    return best if best_score > 0 else None


def fetch_medlineplus_docs(scope: dict[str, Any]) -> list[dict[str, Any]]:
    xml_url = _latest_xml_url()
    print(f"[MedlinePlus] Fetching {xml_url}")
    resp = requests.get(xml_url, timeout=90)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    for topic in root.findall(".//health-topic"):
        title = topic.attrib.get("title", "").strip()
        url = topic.attrib.get("url", "").strip()
        lang = topic.attrib.get("language", "").strip()
        if lang.lower() != "english" or not title or not url or url in seen:
            continue

        also_called = [x.text.strip() for x in topic.findall("also-called") if x.text]
        groups = [x.text.strip() for x in topic.findall("group") if x.text]
        mesh = [x.text.strip() for x in topic.findall(".//mesh-heading/descriptor") if x.text]
        summary = " ".join(
            "".join(n.itertext()).strip() for n in topic.findall("full-summary")
        ).strip()

        joined = " ".join([title, summary, " ".join(also_called), " ".join(groups), " ".join(mesh)])
        category = _match_category(joined, scope)
        if not category:
            continue

        seen.add(url)
        rows.append({
            "doc_id": f"medlineplus-{topic.attrib.get('id', title).strip()}",
            "title": title,
            "content": summary,
            "also_called": also_called,
            "groups": groups,
            "mesh_terms": mesh,
            "category": category,
            "source_type": "medlineplus",
            "source_name": "MedlinePlus",
            "source_url": url,
            "retrieved_at": now,
        })
    return rows


def build_glossary_docs(glossary: dict[str, Any]) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows: list[dict[str, Any]] = []
    for alias, info in glossary.items():
        rows.append({
            "doc_id": f"glossary-{alias}",
            "title": alias,
            "content": info.get("description", ""),
            "expansions": info.get("expansions", []),
            "category": info.get("category_hint", ""),
            "source_type": "glossary",
            "source_name": "local_glossary",
            "source_url": "",
            "retrieved_at": now,
        })
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def crawl_aux_docs(output: Path | None = None) -> Path:
    if output is None:
        output = DATA_DIR / "raw" / "aux_docs.jsonl"

    scope = load_domain_scope()
    glossary = load_glossary()

    medlineplus_rows = fetch_medlineplus_docs(scope)
    glossary_rows = build_glossary_docs(glossary)
    rows = medlineplus_rows + glossary_rows

    write_jsonl(output, rows)
    print(f"MedlinePlus: {len(medlineplus_rows)}개")
    print(f"Glossary: {len(glossary_rows)}개")
    print(f"총 저장: {len(rows)}개 → {output}")
    return output


if __name__ == "__main__":
    crawl_aux_docs()
