"""
API request/response schemas.

프론트엔드-백엔드 간 계약(contract)을 명확히 정의한다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)


class SourceInfo(BaseModel):
    title: str = ""
    journal: str = ""
    year: str = ""
    pmid: str = ""
    source_type: str = ""
    url: str = ""


class MatchedTermInfo(BaseModel):
    alias: str
    description: str = ""
    expansions: list[str] = Field(default_factory=list)
    query_type: str = "general"


class AskResponse(BaseModel):
    answer: str
    category: str | None = None
    query_type: str = "general"
    matched_terms: list[MatchedTermInfo] = Field(default_factory=list)
    paper_sources: list[SourceInfo] = Field(default_factory=list)
    aux_sources: list[SourceInfo] = Field(default_factory=list)
    has_paper_evidence: bool = True
    weak_evidence: bool = False
    paper_score: float = 0.0
    needs_web: bool = False
    expanded_query: str = ""


class HealthResponse(BaseModel):
    status: str = "ok"
    collections: dict[str, int] = Field(default_factory=dict)
