"""
FastAPI 백엔드 엔트리포인트.

POST /api/ask     — RAG 질의응답
GET  /api/health  — 헬스체크 + 컬렉션 상태
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.schemas import AskRequest, AskResponse, HealthResponse
from app.settings import get_settings
from pipeline.rag_service import HybridRAGService

load_dotenv()

logger = logging.getLogger(__name__)

# ── Lifespan — 서비스 초기화/종료 ──

_rag: HybridRAGService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _rag
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper())
    logger.info("Initializing HybridRAGService...")
    _rag = HybridRAGService()
    counts = _rag.get_collection_counts()
    logger.info("Collections ready: %s", counts)
    yield
    logger.info("Shutting down.")


# ── App ──

app = FastAPI(
    title="BioRAG Unified API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Endpoints ──

@app.post("/api/ask", response_model=AskResponse)
async def ask(req: AskRequest) -> AskResponse:
    """RAG 파이프라인을 실행하고 답변을 반환한다."""
    assert _rag is not None, "Service not initialized"
    return _rag.ask(req.question)


@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """서버 상태 + 컬렉션 문서 수를 반환한다."""
    if _rag is None:
        return HealthResponse(status="initializing")
    counts = _rag.get_collection_counts()
    return HealthResponse(status="ok", collections=counts)
