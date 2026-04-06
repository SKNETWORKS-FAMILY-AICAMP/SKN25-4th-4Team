#!/usr/bin/env bash
set -euo pipefail

# BioRAG 데이터 수집 + 벡터스토어 빌드 스크립트
# 사용법: cd backend && bash ../scripts/ingest.sh [--reset]

RESET_FLAG=""
if [[ "${1:-}" == "--reset" ]]; then
    RESET_FLAG="--reset"
fi

echo "=== [1/3] PubMed 논문 수집 ==="
python -m ingestion.crawl_pubmed

echo ""
echo "=== [2/3] MedlinePlus + Glossary 보조문서 수집 ==="
python -m ingestion.crawl_aux_docs

echo ""
echo "=== [3/3] ChromaDB 벡터스토어 빌드 ==="
python -m ingestion.build_vectorstores $RESET_FLAG

echo ""
echo "✅ 데이터 수집 + 벡터스토어 빌드 완료!"
echo "   다음 명령으로 서버를 시작하세요:"
echo "   uvicorn app.main:app --reload"
