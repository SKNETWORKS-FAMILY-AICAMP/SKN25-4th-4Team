"""
BioRAG 데이터 전처리 & 청킹
- 수집된 논문 데이터 정제
- 텍스트 청킹 (800자 단위)
- 용어사전 처리
- 전처리된 데이터 저장
"""

import json
import os
import re
from datetime import datetime



# 1. 청킹 설정

CHUNK_SIZE = 800        # 청크 최대 글자 수
CHUNK_OVERLAP = 100     # 청크 간 겹치는 글자 수 (문맥 유지)



# 2. 텍스트 정제 함수

def clean_text(text: str) -> str:
    """
    텍스트 정제
    - 특수문자 제거
    - 공백 정리
    - 불필요한 태그 제거
    """
    if not text:
        return ""

    # HTML 태그 제거
    text = re.sub(r"<[^>]+>", " ", text)

    # 특수문자 정리 (논문에서 흔히 나오는 것들 유지)
    text = re.sub(r"[^\w\s.,;:()\-/%°αβγδ]", " ", text)

    # 연속 공백 → 단일 공백
    text = re.sub(r"\s+", " ", text)

    # 앞뒤 공백 제거
    text = text.strip()

    return text



# 3. 청킹 함수

def split_into_chunks(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """
    텍스트를 청크로 분할
    - 문장 단위로 자르기 (단어 중간에 안 잘림)
    - overlap으로 문맥 이어짐
    """
    if not text:
        return []

    # 텍스트가 chunk_size보다 짧으면 그냥 반환
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        if end >= len(text):
            # 마지막 청크
            chunks.append(text[start:].strip())
            break

        # 문장 끝(. ! ?)에서 자르기
        cut = text.rfind(". ", start, end)
        if cut == -1:
            cut = text.rfind(" ", start, end)  
        if cut == -1:
            cut = end

        chunk = text[start:cut + 1].strip()
        if chunk:
            chunks.append(chunk)

        # overlap 적용
        start = max(start + 1, cut + 1 - overlap)

    return chunks



# 4. 논문 데이터 전처리

def process_papers(papers: list) -> list:
    """
    논문 데이터 전처리 및 청킹
    """
    print("논문 데이터 전처리 중...")

    all_chunks = []
    chunk_id = 0

    for i, paper in enumerate(papers):
        if (i + 1) % 50 == 0:
            print(f"  처리 완료: {i + 1}/{len(papers)} 논문")

        # 제목 + 초록 합치기
        title = clean_text(paper.get("title", ""))
        abstract = clean_text(paper.get("abstract", ""))

        if not abstract:
            continue

        # 제목은 모든 청크에 포함 (검색 품질 향상)
        full_text = f"Title: {title}\n\nAbstract: {abstract}" if title else abstract

        # 청킹
        chunks = split_into_chunks(full_text)

        for j, chunk_text in enumerate(chunks):
            chunk = {
                "chunk_id": f"paper_{chunk_id:05d}",
                "text": chunk_text,
                "metadata": {
                    "source_type": "paper",
                    "pmid": paper.get("pmid", ""),
                    "title": title,
                    "journal": paper.get("journal", ""),
                    "year": paper.get("year", ""),
                    "first_author": paper.get("first_author", ""),
                    "doi": paper.get("doi", ""),
                    "keyword": paper.get("keyword", ""),
                    "source": paper.get("source", ""),
                    "chunk_index": j,
                    "total_chunks": len(chunks),
                }
            }
            all_chunks.append(chunk)
            chunk_id += 1

    print(f"\n 논문 {len(papers)}개 → 청크 {len(all_chunks)}개 생성\n")
    return all_chunks



# 5. 용어사전 전처리

def process_glossary(glossary: list) -> list:
    """
    용어사전 전처리
    - 각 용어를 하나의 청크로 처리
    """
    print("📖 용어사전 전처리 중...")

    all_chunks = []

    for i, term_data in enumerate(glossary):
        term = term_data.get("term", "")
        definition = term_data.get("definition", "")
        keywords = term_data.get("keywords", [])
        category = term_data.get("category", "")

        if not term or not definition:
            continue

        # 용어사전 텍스트 구성
        keywords_str = ", ".join(keywords) if keywords else ""
        text = (
            f"용어: {term}\n"
            f"정의: {definition}\n"
            f"분류: {category}\n"
            f"관련 키워드: {keywords_str}"
        )

        chunk = {
            "chunk_id": f"glossary_{i:04d}",
            "text": text,
            "metadata": {
                "source_type": "glossary",
                "term": term,
                "category": category,
                "source": f"건강 용어사전: {term}",
                "chunk_index": 0,
                "total_chunks": 1,
            }
        }
        all_chunks.append(chunk)

    print(f" 용어 {len(all_chunks)}개 처리 완료\n")
    return all_chunks



# 6. 통계 출력

def print_stats(chunks: list):
    """
    전처리 결과 통계 출력
    """
    paper_chunks = [c for c in chunks if c["metadata"]["source_type"] == "paper"]
    glossary_chunks = [c for c in chunks if c["metadata"]["source_type"] == "glossary"]

    avg_len = sum(len(c["text"]) for c in chunks) / len(chunks) if chunks else 0

    print(" 전처리 결과 통계")
    print(f"  전체 청크 수     : {len(chunks)}개")
    print(f"  논문 청크        : {len(paper_chunks)}개")
    print(f"  용어사전 청크    : {len(glossary_chunks)}개")
    print(f"  평균 청크 길이   : {avg_len:.0f}자")
    print(f"  최대 청크 길이   : {max(len(c['text']) for c in chunks)}자")
    print(f"  최소 청크 길이   : {min(len(c['text']) for c in chunks)}자")
    print()



# 7. 메인 실행

def main():
    print("BioRAG 데이터 전처리 시작")

    print(" 데이터 로딩 중...")

    papers = []
    glossary = []

    # 논문 데이터
    papers_path = "data/raw/papers.json"
    if os.path.exists(papers_path):
        with open(papers_path, "r", encoding="utf-8") as f:
            papers = json.load(f)
        print(f"   논문 {len(papers)}개 로드")
    else:
        print(f"   {papers_path} 파일 없음 → crawler.py 먼저 실행하세요")

    # 용어사전
    glossary_path = "data/raw/glossary.json"
    if os.path.exists(glossary_path):
        with open(glossary_path, "r", encoding="utf-8") as f:
            glossary = json.load(f)
        print(f"  용어 {len(glossary)}개 로드")
    else:
        print(f"   {glossary_path} 파일 없음")

    if not papers and not glossary:
        print("\n 처리할 데이터가 없습니다. crawler.py를 먼저 실행하세요.")
        return

    print()

    # ── 전처리 ───────────────────────────────────────────────
    all_chunks = []

    if papers:
        paper_chunks = process_papers(papers)
        all_chunks.extend(paper_chunks)

    if glossary:
        glossary_chunks = process_glossary(glossary)
        all_chunks.extend(glossary_chunks)

    # ── 통계 출력 ────────────────────────────────────────────
    print_stats(all_chunks)

    # ── 저장 ─────────────────────────────────────────────────
    os.makedirs("data/processed", exist_ok=True)
    output_path = "data/processed/chunks.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=2)

    print(f" 저장 완료: {output_path}")
    print(f"   총 {len(all_chunks)}개 청크\n")
    print(" 전처리 완료!")
    print("\n 다음 단계: python pipeline/embed_store.py\n")


if __name__ == "__main__":
    main()