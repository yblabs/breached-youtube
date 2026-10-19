"""BREACHED YOUTUBE — FastAPI surface: metadata, download jobs, websocket progress."""

from __future__ import annotations

import asyncio
import re
import shutil
import time
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import engine
from .jobs import TERMINAL_STATUSES, JobManager

BASE_DIR = Path(__file__).resolve().parent.parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"

manager = JobManager(DOWNLOAD_DIR)


@asynccontextmanager
async def lifespan(_: FastAPI):
    manager.start()
    yield
    await manager.stop()


app = FastAPI(
    title="BREACHED YOUTUBE API",
    description="Cyberpunk YouTube stream extraction pipeline (yt-dlp + ffmpeg). Made by Yash & Bhupesh.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------
# schemas
# --------------------------------------------------------------------------
class InfoRequest(BaseModel):
    url: str


class DownloadRequest(BaseModel):
    url: str
    format_id: str
    mode: Literal["video", "audio"]
    bitrate: str | None = None


class DownloadAllRequest(BaseModel):
    url: str
    video: bool = True
    audio: bool = True


# --------------------------------------------------------------------------
# metadata
# --------------------------------------------------------------------------
async def _extract(url: str) -> tuple[dict, list[str]]:
    try:
        return await asyncio.to_thread(engine.extract, url)
    except engine.EngineError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/info")
async def post_info(payload: InfoRequest):
    url = engine.normalize_url(payload.url)
    if not url:
        raise HTTPException(status_code=400, detail="INVALID TARGET // EXPECTED youtube.com | youtu.be | VIDEO ID")
    info, warnings = await _extract(url)
    body = engine.describe(info, warnings)
    body["resolved_url"] = url
    return body


@app.get("/api/info")
async def get_info(url: str = Query(...)):
    normalized = engine.normalize_url(url)
    if not normalized:
        raise HTTPException(status_code=400, detail="INVALID TARGET // EXPECTED youtube.com | youtu.be | VIDEO ID")
    info, warnings = await _extract(normalized)
    body = engine.describe(info, warnings)
    body["resolved_url"] = normalized
    return body


# --------------------------------------------------------------------------
# download jobs
# --------------------------------------------------------------------------
@app.post("/api/download")
async def post_download(payload: DownloadRequest):
    url = engine.normalize_url(payload.url)
    if not url:
        raise HTTPException(status_code=400, detail="INVALID TARGET // EXPECTED youtube.com | youtu.be | VIDEO ID")

    info, warnings = await _extract(url)
    try:
        plan = engine.resolve_plan(info, payload.mode, payload.format_id, payload.bitrate)
    except engine.EngineError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    job = manager.create(
        url=url,
        title=str(info.get("title") or "UNTITLED TARGET"),
        mode=payload.mode,
        plan=plan,
        loop=asyncio.get_running_loop(),
    )
    manager.start_worker(job)
    return {
        "job_id": job.id,
        "status": job.status,
        "ws_url": f"/ws/download/{job.id}",
        "status_url": f"/api/download/{job.id}",
        "file_url": f"/api/file/{job.id}",
        "label": plan.get("label"),
        "estimated_bytes": plan.get("est_bytes"),
        "warnings": warnings,
    }


@app.get("/api/download/{job_id}")
async def job_status(job_id: str):
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="UNKNOWN JOB ID // SESSION EXPIRED OR NEVER EXISTED")
    return JSONResponse(job.snapshot())


@app.delete("/api/download/{job_id}")
async def cancel_job(job_id: str):
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="UNKNOWN JOB ID")
    job.cancel.set()
    if job.status not in TERMINAL_STATUSES:
        job.status = "cancelled"
        job.publish({"type": "cancelled"})
    shutil.rmtree(manager.base_dir / job_id, ignore_errors=True)
    return {"ok": True, "job_id": job_id}


@app.get("/api/file/{job_id}")
async def download_file(job_id: str):
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="UNKNOWN JOB ID")
    if job.status != "finished" or not job.filepath:
        raise HTTPException(status_code=409, detail="ARTIFACT NOT READY // WAIT FOR TRANSFER COMPLETE")
    path = Path(job.filepath)
    if not path.is_file():
        raise HTTPException(status_code=410, detail="ARTIFACT PURGED // RE-RUN THE EXTRACTION")
    return FileResponse(path, filename=job.filename or path.name, media_type="application/octet-stream")


# --------------------------------------------------------------------------
# batch jobs (DOWNLOAD ALL)
# --------------------------------------------------------------------------
def _safe_stem(text: str) -> str:
    cleaned = re.sub(r"[^\w\-. ]+", "", str(text or "")).strip().strip(".")
    return (cleaned or "BREACHED_YOUTUBE")[:80]


@app.post("/api/download-all")
async def post_download_all(payload: DownloadAllRequest):
    url = engine.normalize_url(payload.url)
    if not url:
        raise HTTPException(status_code=400, detail="INVALID TARGET // EXPECTED youtube.com | youtu.be | VIDEO ID")

    info, warnings = await _extract(url)
    options = engine.build_options(info)

    selections: list[tuple[str, str, str | None, str]] = []
    if payload.video:
        for option in options.get("video", []):
            selections.append(("video", option["format_id"], None, option["label"]))
    if payload.audio:
        for option in options.get("audio", []):
            selections.append(("audio", option["format_id"], option.get("bitrate"), option["label"]))

    if not selections:
        raise HTTPException(status_code=422, detail="NO PAYLOADS AVAILABLE FOR THIS TARGET")

    loop = asyncio.get_running_loop()
    title = str(info.get("title") or "UNTITLED TARGET")
    jobs = []
    errors: list[dict] = []
    for mode, format_id, bitrate, label in selections:
        try:
            plan = engine.resolve_plan(info, mode, format_id, bitrate)
        except engine.EngineError as exc:
            errors.append({"label": label, "mode": mode, "error": str(exc)})
            continue
        jobs.append(manager.create(url=url, title=title, mode=mode, plan=plan, loop=loop))

    if not jobs:
        raise HTTPException(status_code=422, detail="NO PAYLOADS COULD BE RESOLVED // " + "; ".join(e["error"] for e in errors[:2]))

    batch = manager.create_batch(url=url, title=title, jobs=jobs, loop=loop, errors=errors)
    for job in jobs:
        manager.start_worker(job)

    snapshot = batch.snapshot()
    return {
        "batch_id": batch.id,
        "status": snapshot["status"],
        "item_count": snapshot["total_count"],
        "estimated_bytes": snapshot["total"],
        "items": snapshot["items"],
        "skipped": errors,
        "ws_url": f"/ws/batch/{batch.id}",
        "status_url": f"/api/download-all/{batch.id}",
        "zip_url": snapshot["zip_url"],
        "warnings": warnings,
    }


@app.get("/api/download-all/{batch_id}")
async def batch_status(batch_id: str):
    batch = manager.get_batch(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="UNKNOWN BATCH ID // SESSION EXPIRED OR NEVER EXISTED")
    return JSONResponse(batch.snapshot())


@app.delete("/api/batch/{batch_id}")
async def cancel_batch(batch_id: str):
    batch = manager.get_batch(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="UNKNOWN BATCH ID")
    for job in batch.jobs:
        job.cancel.set()
        if job.status not in TERMINAL_STATUSES:
            job.status = "cancelled"
            job.publish({"type": "cancelled"})
    return {"ok": True, "batch_id": batch_id}


def _build_batch_zip(batch) -> Path | None:
    entries = [
        (job.label or job.mode.upper(), job.filename, job.filepath)
        for job in batch.jobs
        if job.status == "finished" and job.filepath and Path(job.filepath).is_file()
    ]
    if not entries:
        return None
    dest = DOWNLOAD_DIR / f"{batch.id}.zip"
    dest.parent.mkdir(parents=True, exist_ok=True)
    used: set[str] = set()
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for label, filename, filepath in entries:
            name = filename or Path(filepath).name
            if name in used:
                stem, dot, ext = name.rpartition(".")
                name = f"{stem or name} [{label}]{dot}{ext}"
            used.add(name)
            archive.write(filepath, arcname=name)
    return dest


@app.get("/api/batch/{batch_id}/file")
async def download_batch(batch_id: str):
    batch = manager.get_batch(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="UNKNOWN BATCH ID")
    if not any(job.status == "finished" for job in batch.jobs):
        raise HTTPException(status_code=409, detail="NO ARTIFACTS READY // WAIT FOR TRANSFER COMPLETE")
    dest = await asyncio.to_thread(_build_batch_zip, batch)
    if dest is None or not dest.is_file():
        raise HTTPException(status_code=410, detail="ARTIFACTS PURGED // RE-RUN THE SWEEP")
    filename = f"{_safe_stem(batch.title)} [ALL].zip"
    return FileResponse(dest, filename=filename, media_type="application/zip")


# --------------------------------------------------------------------------
# websocket progress (long-poll fallback: GET /api/download/{id})
# --------------------------------------------------------------------------
@app.websocket("/ws/download/{job_id}")
async def ws_download(websocket: WebSocket, job_id: str):
    job = manager.get(job_id)
    if job is None:
        await websocket.close(code=4404)
        return
    await websocket.accept()
    queue = job.subscribe()
    try:
        snapshot = job.snapshot()
        await websocket.send_json(snapshot)
        if snapshot["status"] in TERMINAL_STATUSES:
            return
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping", "ts": time.time()})
                continue
            await websocket.send_json(event)
            if event.get("type") in ("done", "error", "cancelled"):
                break
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        job.unsubscribe(queue)


@app.websocket("/ws/batch/{batch_id}")
async def ws_batch(websocket: WebSocket, batch_id: str):
    batch = manager.get_batch(batch_id)
    if batch is None:
        await websocket.close(code=4404)
        return
    await websocket.accept()
    try:
        while True:
            snapshot = batch.snapshot()
            await websocket.send_json(snapshot)
            if snapshot["status"] in ("finished", "error", "cancelled", "partial"):
                break
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass


# --------------------------------------------------------------------------
# ops
# --------------------------------------------------------------------------
@app.get("/api/health")
async def health():
    return {
        "status": "online",
        "ffmpeg": engine.FFMPEG_AVAILABLE,
        "ffmpeg_version": engine.FFMPEG_VERSION,
        "ffmpeg_path": engine.FFMPEG_DIR,
        "node": engine.NODE_AVAILABLE,
        "yt_dlp": engine.yt_dlp.version.__version__,
        "engine_ready": engine.ENGINE_READY,
        "active_jobs": manager.count_active(),
    }


if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
