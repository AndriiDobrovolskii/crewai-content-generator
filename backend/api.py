"""
FastAPI adapter layer — bridges React frontend ↔ existing pipeline_runner.

Design principle: crew.py and pipeline_runner.py are NEVER modified.
This module is a thin HTTP wrapper only.

Routes:
  GET  /api/config              → site list + categories for UI dropdowns
  POST /api/generate            → start full pipeline, returns job_id
  POST /api/discover            → start URL discovery, returns job_id
  GET  /api/jobs/{id}           → job status + result
  GET  /api/jobs/{id}/stream    → SSE real-time log stream
"""
from __future__ import annotations

import asyncio
import os
import queue
import sys
import threading
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

# ── Path setup (mirrors pipeline_runner.py pattern) ──────────────────────────
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
_SRC_DIR = os.path.join(_PROJECT_ROOT, "content_generator", "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(_PROJECT_ROOT, "content_generator", ".env"))
load_dotenv()

from content_generator.crew import SITES_CONFIG

# ── Local imports ─────────────────────────────────────────────────────────────
from backend.job_manager import job_manager
from backend.models import (
    ConfigResponse,
    DiscoverRequest,
    GenerateRequest,
    JobCreatedResponse,
    JobStateResponse,
    SiteInfo,
)

# ── Categories (mirrors knowledge_base.py) ────────────────────────────────────
CATEGORIES: list[str] = [
    "fdm_printer",
    "resin_printer",
    "sls_printer",
    "metal_printer",
    "3d_scanner",
    "filament",
    "resin",
    "print_farm",
    "software",
    "accessories",
    "post_processing",
    "metrology",
    "bioprinting",
    "other",
]

SOURCE_TYPES = [
    {"value": "text",               "label": "📝 Вставити текст"},
    {"value": "urls",               "label": "🌐 URL-адреси"},
    {"value": "pdf",                "label": "📄 PDF файл(и)"},
    {"value": "markdown",           "label": "📑 Markdown файл(и)"},
    {"value": "markdown_dir",       "label": "📁 Директорія Markdown"},
    {"value": "auto_search",        "label": "🔍 Auto-search (авто)"},
    {"value": "auto_search_review", "label": "🔎 Auto-search (HITL)"},
]


# ── App factory ───────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield  # Nothing to teardown for now


app = FastAPI(
    title="GEO Content Generator API",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/api/config", response_model=ConfigResponse)
async def get_config():
    """Returns all dropdown data needed to populate the UI."""
    sites = [
        SiteInfo(
            key=key,
            label=f"{key} ({cfg['country']})",
            country=cfg["country"],
            languages=cfg["languages"],
            ua_is_production=cfg["ua_is_production"],
        )
        for key, cfg in SITES_CONFIG.items()
    ]
    return ConfigResponse(
        sites=sites,
        categories=CATEGORIES,
        source_types=SOURCE_TYPES,
    )


@app.post("/api/generate", response_model=JobCreatedResponse)
async def start_generate(req: GenerateRequest):
    """Starts the full content generation pipeline in a background thread."""
    job = job_manager.create()
    job.status = "running"

    def _run():
        from content_generator.pipeline_runner import run_pipeline_headless

        result = run_pipeline_headless(
            product_name=req.product_name,
            site=req.site,
            source_type=req.source_type,
            raw_input=req.raw_input,
            log_callback=lambda msg: job_manager.push_log(job.id, msg),
        )
        job_manager.finish(job.id, result)

    threading.Thread(target=_run, daemon=True).start()
    return JobCreatedResponse(job_id=job.id)


@app.post("/api/discover", response_model=JobCreatedResponse)
async def start_discover(req: DiscoverRequest):
    """Starts URL discovery only (HITL path)."""
    job = job_manager.create()
    job.status = "running"

    def _run():
        from content_generator.pipeline_runner import run_discovery_headless

        result = run_discovery_headless(
            product_name=req.product_name,
            site=req.site,
            log_callback=lambda msg: job_manager.push_log(job.id, msg),
        )
        job_manager.finish_discovery(job.id, result)

    threading.Thread(target=_run, daemon=True).start()
    return JobCreatedResponse(job_id=job.id)


@app.get("/api/jobs/{job_id}", response_model=JobStateResponse)
async def get_job(job_id: str):
    """Poll endpoint — returns current job state without streaming."""
    job = job_manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStateResponse(
        job_id=job.id,
        status=job.status,
        files=job.files,
        zip_path=job.zip_path,
        error=job.error,
        discovered_urls=job.discovered_urls,
    )


@app.get("/api/jobs/{job_id}/stream")
async def stream_logs(job_id: str):
    """
    Server-Sent Events stream for real-time log output.

    Protocol:
      data: <log line>\\n\\n   — normal log message
      data: [DONE]\\n\\n       — pipeline finished (success or error)
    """
    job = job_manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    async def generate():
        # If job already done before client connected, drain queue then exit
        while True:
            try:
                msg = job.log_queue.get_nowait()
            except queue.Empty:
                if job.status in ("done", "error"):
                    yield "data: [DONE]\n\n"
                    return
                await asyncio.sleep(0.05)
                continue

            if msg is None:  # sentinel from job_manager.finish()
                yield "data: [DONE]\n\n"
                return

            # Escape newlines within a single SSE event
            escaped = msg.replace("\n", "↵")
            yield f"data: {escaped}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/jobs/{job_id}/download")
async def download_zip(job_id: str):
    """Returns the output ZIP file for download."""
    job = job_manager.get(job_id)
    if not job or not job.zip_path:
        raise HTTPException(status_code=404, detail="No output file available")
    if not os.path.exists(job.zip_path):
        raise HTTPException(status_code=404, detail="File no longer on disk")
    return FileResponse(
        path=job.zip_path,
        media_type="application/zip",
        filename=os.path.basename(job.zip_path),
    )


# ── Static files (production build) ──────────────────────────────────────────
_DIST = os.path.join(_PROJECT_ROOT, "frontend", "dist")
if os.path.isdir(_DIST):
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="static")


# ── Dev entry point ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run("backend.api:app", host="0.0.0.0", port=8000, reload=True)
