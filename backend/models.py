"""
API Pydantic contracts — Hard input/output schemas.
Never mutate these without versioning the API.
"""
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field


# ── Enums / Literals ──────────────────────────────────────────────────────────

SourceType = Literal[
    "text",
    "urls",
    "pdf",
    "markdown",
    "markdown_dir",
    "auto_search",
    "auto_search_review",
]

JobStatus = Literal["pending", "running", "done", "error"]


# ── Requests ──────────────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    product_name: str = Field(..., min_length=1, max_length=300)
    site: str = Field(..., description="Key from SITES_CONFIG")
    category: str = Field(..., description="Product category key")
    source_type: SourceType
    raw_input: str = Field(default="", description="Text / URLs / file paths")


class DiscoverRequest(BaseModel):
    product_name: str = Field(..., min_length=1, max_length=300)
    site: str = Field(..., description="Key from SITES_CONFIG")


# ── Responses ─────────────────────────────────────────────────────────────────

class JobCreatedResponse(BaseModel):
    job_id: str


class SiteInfo(BaseModel):
    key: str
    label: str
    country: str
    languages: list[str]
    ua_is_production: bool


class ConfigResponse(BaseModel):
    sites: list[SiteInfo]
    categories: list[str]
    source_types: list[dict]


class JobStateResponse(BaseModel):
    job_id: str
    status: JobStatus
    files: dict[str, str] = Field(default_factory=dict)  # lang → html
    zip_path: Optional[str] = None
    error: Optional[str] = None
    discovered_urls: list[str] = Field(default_factory=list)
