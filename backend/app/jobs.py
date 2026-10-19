"""Download job bookkeeping: worker threads, event bus, snapshots."""

from __future__ import annotations

import asyncio
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from . import engine

TERMINAL_STATUSES = {"finished", "error", "cancelled"}

# DOWNLOAD ALL runs one job per payload; keep the swarm civil so YouTube does not
# throttle the whole sweep. Extra jobs wait in "queued" until a slot frees up.
MAX_PARALLEL_DOWNLOADS = 3


class Job:
    def __init__(self, *, job_id: str, url: str, title: str, mode: str, plan: dict, loop: asyncio.AbstractEventLoop) -> None:
        self.id = job_id
        self.url = url
        self.title = title or "UNTITLED TARGET"
        self.mode = mode
        self.plan = plan
        self.status = "queued"
        self.percent = 0.0
        self.downloaded = 0
        self.total = int(plan.get("est_bytes") or 0)
        self.speed: float | None = None
        self.eta: int | None = None
        self.logs: list[str] = []
        self.filename: str | None = None
        self.filepath: str | None = None
        self.filesize: int = 0
        self.error: str | None = None
        self.label = plan.get("label") or ""
        self.created = time.time()
        self.cancel = threading.Event()
        self._loop = loop
        self._queues: list[asyncio.Queue] = []

    # -- pub/sub ------------------------------------------------------
    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=2000)
        self._queues.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        if queue in self._queues:
            self._queues.remove(queue)

    def publish(self, event: dict) -> None:
        """Thread safe: called from the yt-dlp worker thread."""
        if event.get("type") == "log":
            self.logs.append(str(event.get("text") or ""))
            if len(self.logs) > 400:
                del self.logs[:150]
        for queue in list(self._queues):
            try:
                asyncio.run_coroutine_threadsafe(queue.put(event), self._loop)
            except RuntimeError:
                continue

    def log(self, text: str) -> None:
        self.publish({"type": "log", "text": text})

    def snapshot(self) -> dict:
        return {
            "type": "snapshot",
            "job_id": self.id,
            "status": self.status,
            "percent": round(self.percent, 1),
            "downloaded": self.downloaded,
            "total": self.total,
            "speed": self.speed,
            "eta": self.eta,
            "mode": self.mode,
            "label": self.label,
            "title": self.title,
            "logs": list(self.logs),
            "filename": self.filename,
            "filesize": self.filesize,
            "error": self.error,
            "download_url": f"/api/file/{self.id}" if self.status == "finished" else None,
        }


class Batch:
    """Groups the individual jobs of a DOWNLOAD ALL sweep into one aggregate view."""

    def __init__(self, *, batch_id: str, url: str, title: str, jobs: list[Job], loop: asyncio.AbstractEventLoop) -> None:
        self.id = batch_id
        self.url = url
        self.title = title
        self.jobs: list[Job] = list(jobs)
        self.errors: list[dict] = []
        self.created = time.time()

    @property
    def status(self) -> str:
        statuses = [job.status for job in self.jobs]
        if not statuses:
            return "error"
        active = [s for s in statuses if s not in TERMINAL_STATUSES]
        if active:
            return "downloading" if any(s in ("downloading", "processing") for s in active) else "queued"
        finished = statuses.count("finished")
        if finished == len(statuses):
            return "finished"
        if finished:
            return "partial"
        if statuses.count("cancelled") == len(statuses):
            return "cancelled"
        return "error"

    def snapshot(self) -> dict:
        jobs = self.jobs
        status = self.status
        percent = round(sum(job.percent for job in jobs) / len(jobs), 1) if jobs else 0.0
        if status == "finished":
            percent = 100.0
        total = sum(int(job.total or 0) for job in jobs)
        downloaded = sum(int(job.filesize if job.status == "finished" else job.downloaded) or 0 for job in jobs)
        finished_count = sum(1 for job in jobs if job.status == "finished")

        items = [
            {
                "job_id": job.id,
                "label": job.label or job.mode.upper(),
                "mode": job.mode,
                "status": job.status,
                "percent": round(job.percent, 1),
                "filename": job.filename,
                "size": job.filesize,
                "error": job.error,
                "download_url": f"/api/file/{job.id}" if job.status == "finished" else None,
                "skipped": False,
            }
            for job in jobs
        ]
        for entry in self.errors:
            items.append(
                {
                    "job_id": None,
                    "label": entry.get("label") or "UNKNOWN PAYLOAD",
                    "mode": entry.get("mode"),
                    "status": "error",
                    "percent": 0.0,
                    "filename": None,
                    "size": 0,
                    "error": entry.get("error"),
                    "download_url": None,
                    "skipped": True,
                }
            )

        return {
            "type": "batch",
            "batch_id": self.id,
            "status": status,
            "percent": percent,
            "total": total,
            "downloaded": downloaded,
            "finished_count": finished_count,
            "total_count": len(jobs) + len(self.errors),
            "items": items,
            "zip_url": f"/api/batch/{self.id}/file" if finished_count else None,
            "title": self.title,
        }


class JobManager:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._jobs: dict[str, Job] = {}
        self._batches: dict[str, Batch] = {}
        self._slots = threading.Semaphore(MAX_PARALLEL_DOWNLOADS)
        self._task: asyncio.Task | None = None

    # -- lifecycle ----------------------------------------------------
    def start(self) -> None:
        self.purge(max_age=0)
        self._task = asyncio.create_task(self._cleanup_loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(300)
            self.purge(max_age=1800)

    def purge(self, max_age: int = 1800) -> None:
        now = time.time()
        stale = [jid for jid, job in self._jobs.items() if now - job.created > max_age and job.status in TERMINAL_STATUSES]
        for jid in stale:
            self._jobs.pop(jid, None)
        stale_batches = [
            bid
            for bid, batch in self._batches.items()
            if now - batch.created > max_age and all(job.status in TERMINAL_STATUSES for job in batch.jobs)
        ]
        for bid in stale_batches:
            self._batches.pop(bid, None)
            try:
                (self.base_dir / f"{bid}.zip").unlink()
            except OSError:
                pass
        for entry in self.base_dir.iterdir() if self.base_dir.exists() else []:
            if not entry.is_dir():
                continue
            try:
                age = now - entry.stat().st_mtime
            except OSError:
                continue
            if age > max_age:
                shutil.rmtree(entry, ignore_errors=True)

    # -- jobs ---------------------------------------------------------
    def create(self, *, url: str, title: str, mode: str, plan: dict, loop: asyncio.AbstractEventLoop) -> Job:
        job_id = uuid.uuid4().hex[:10].upper()
        job = Job(job_id=job_id, url=url, title=title, mode=mode, plan=plan, loop=loop)
        self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    # -- batches (DOWNLOAD ALL) --------------------------------------
    def create_batch(self, *, url: str, title: str, jobs: list[Job], loop: asyncio.AbstractEventLoop, errors: list[dict] | None = None) -> Batch:
        batch_id = "B" + uuid.uuid4().hex[:9].upper()
        batch = Batch(batch_id=batch_id, url=url, title=title, jobs=jobs, loop=loop)
        if errors:
            batch.errors = errors
        self._batches[batch_id] = batch
        return batch

    def get_batch(self, batch_id: str) -> Batch | None:
        return self._batches.get(batch_id)

    def count_active(self) -> int:
        return sum(1 for job in self._jobs.values() if job.status not in TERMINAL_STATUSES)

    def workdir(self, job_id: str) -> Path:
        path = self.base_dir / job_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def start_worker(self, job: Job) -> None:
        workdir = str(self.workdir(job.id))
        thread = threading.Thread(
            target=_worker,
            args=(job, workdir, self._slots),
            daemon=True,
            name=f"grab-{job.id}",
        )
        thread.start()


def _worker(job: Job, workdir: str, slots: threading.Semaphore | None = None) -> None:
    if slots is not None:
        slots.acquire()
    try:
        if job.cancel.is_set():
            job.status = "cancelled"
            job.publish({"type": "cancelled", "status": "cancelled"})
            return
        engine_path_note = engine.FFMPEG_DIR or "NOT FOUND"
        job.log("[SYS.BOOT] BREACHED YOUTUBE EXTRACTION NODE ONLINE")
        job.log(f"[SYS.MSG] TARGET LOCKED // {job.title[:120]}")
        job.log(f"[SYS.MSG] MODE={job.mode.upper()} // CONTAINER={job.plan.get('container', '?').upper()} // FFMPEG={engine_path_note}")
        for stream in job.plan.get("streams", []):
            job.log(f"[NET.OK] {stream['role'].upper()} STREAM RESOLVED // {stream['label']} // ID={stream['id']}")
        job.log("[SYS.MSG] DOWNLOADING PACKETS... 0%")
        job.status = "downloading"
        job.publish({"type": "status", "status": "downloading"})

        path, filename, size = engine.run_download(
            job.url,
            job.plan,
            workdir,
            job.publish,
            should_cancel=job.cancel.is_set,
        )

        job.status = "finished"
        job.percent = 100.0
        job.filepath = path
        job.filename = filename
        job.filesize = size
        job.speed = None
        job.eta = None
        job.log(f"[OK] TRANSFER COMPLETE // {filename} // {engine.human_size(size)}")
        job.publish(
            {
                "type": "done",
                "status": "finished",
                "filename": filename,
                "size": size,
                "download_url": f"/api/file/{job.id}",
                "percent": 100.0,
            }
        )
    except engine.DownloadAborted:
        job.status = "cancelled"
        job.log("[WARN] TRANSFER ABORTED BY OPERATOR")
        job.publish({"type": "cancelled", "status": "cancelled"})
    except engine.EngineError as exc:
        job.status = "error"
        job.error = str(exc)
        job.log(f"[ERR] {exc}")
        job.publish({"type": "error", "status": "error", "error": str(exc)})
    except Exception as exc:  # pragma: no cover - safety net
        job.status = "error"
        job.error = f"UNEXPECTED FAULT // {exc}"
        job.log(f"[ERR] UNEXPECTED FAULT // {exc}")
        job.publish({"type": "error", "status": "error", "error": job.error})
    finally:
        if slots is not None:
            slots.release()
