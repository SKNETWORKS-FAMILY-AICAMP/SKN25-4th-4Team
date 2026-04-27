"""
Centralized application settings.

모든 환경변수와 경로를 한 곳에서 관리한다.
pydantic-settings를 사용해 .env 파일과 환경변수를 자동으로 로드한다.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[1]  # backend/
CONFIGS_DIR = BASE_DIR / "configs"
DATA_DIR = BASE_DIR / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── OpenAI ──
    openai_api_key: str = ""
    llm_model: str = "gpt-4o"
    embedding_model: str = "text-embedding-3-small"

    # ── NCBI / PubMed ──
    ncbi_email: str = ""
    ncbi_api_key: str = ""

    # ── Tavily (optional) ──
    tavily_api_key: str = ""

    # ── ChromaDB ──
    chroma_db_path: str = str(DATA_DIR / "chroma")
    paper_collection: str = "biorag_papers"
    aux_collection: str = "biorag_aux"

    # ── Retrieval ──
    paper_k: int = 5
    paper_fetch_k: int = 15
    aux_k: int = 3
    aux_fetch_k: int = 8
    mmr_lambda: float = 0.5

    # ── Backend ──
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    log_level: str = "info"

    # ── Frontend ──
    backend_url: str = "http://localhost:8000"


@lru_cache
def get_settings() -> Settings:
    return Settings()


# ── Config file loaders ──


@lru_cache
def load_glossary() -> dict[str, Any]:
    path = CONFIGS_DIR / "glossary.json"
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache
def load_domain_scope() -> dict[str, Any]:
    path = CONFIGS_DIR / "domain_scope.json"
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache
def load_pubmed_topics() -> list[dict[str, Any]]:
    path = CONFIGS_DIR / "pubmed_topics.json"
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache
def load_trusted_domains() -> dict[str, list[str]]:
    path = CONFIGS_DIR / "trusted_domains.json"
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)
