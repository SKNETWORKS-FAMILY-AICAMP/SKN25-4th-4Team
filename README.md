# BioRAG Unified

**논문 기반 건강 팩트체커**.

## 아키텍처

```
Frontend (Streamlit :8501)
    ↕ HTTP
Backend (FastAPI :8000)
    ├── pipeline/
    │   ├── glossary_matcher   — 신조어 감지 + 쿼리 확장
    │   ├── category_router    — 4개 카테고리 라우팅
    │   ├── retriever          — ChromaDB paper/aux 병렬 MMR 검색
    │   ├── external_search    — Tavily 웹검색 fallback
    │   ├── korean_rewriter    — 한국어 재작성 파이프라인
    │   └── rag_service        — 전체 조합 서비스
    └── ingestion/
        ├── crawl_pubmed       — PubMed Entrez 크롤러
        ├── crawl_aux_docs     — MedlinePlus + glossary 수집
        └── build_vectorstores — ChromaDB 벡터스토어 빌드
```

## 통합된 기능

| 출처 | 기능 | 위치 |
|------|------|------|
| 김찬영 | 카드형 HTML UI, 한국어 재작성, supplement 필터 | frontend/, korean_rewriter |
| 조민서 | 파이프라인 분리 구조, 섹션별 관리, 신조어 사전 | pipeline/, configs/ |
| biorag_hybrid | Hybrid RAG, MMR, MedlinePlus, paper/aux 병렬검색 | retriever, rag_service |

## 빠른 시작

### 1. 환경 설정

```bash
cp .env.example .env
# .env 파일에 OPENAI_API_KEY, NCBI_EMAIL 입력
```

### 2. 의존성 설치

```bash
# backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# frontend (별도 터미널)
cd frontend
pip install -r requirements.txt
```

### 3. 데이터 수집 + 벡터스토어 빌드

```bash
cd backend
bash ../scripts/ingest.sh --reset
```

### 4. 서버 실행

```bash
# 터미널 1: Backend
cd backend
uvicorn app.main:app --reload

# 터미널 2: Frontend
cd frontend
BACKEND_URL=http://localhost:8000 streamlit run app.py
```

### Docker Compose

```bash
docker compose up --build
```

## 카테고리

| 카테고리 | 예시 질문 |
|----------|-----------|
| diet_glp1 | 마운자로 부작용, 간헐적 단식 효과 |
| skin_beauty_regeneration | 콜라겐 보충제, 레티놀 효과 |
| supplement_trends | 오메가3, 비타민D, 유산균 |
| morning_fasted_routines | 올레샷, 애사비, 방탄커피 |

## 환경변수

`.env.example` 참고. 필수: `OPENAI_API_KEY`, `NCBI_EMAIL`.
