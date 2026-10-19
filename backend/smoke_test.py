"""Smoke test for the BREACHED YOUTUBE API: info -> download (mp3) -> file fetch."""

import sys
import time

import requests

BASE = "http://127.0.0.1:8000"
TARGET = "https://www.youtube.com/watch?v=jNQXAC9IVRw"  # short clip, fast turnaround


def wait_for(job_id: str, timeout: float = 300.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        snap = requests.get(f"{BASE}/api/download/{job_id}", timeout=30).json()
        print(f"  {snap['status']:<12} {snap['percent']:>5.1f}%  {snap['logs'][-1] if snap['logs'] else ''}")
        if snap["status"] in {"finished", "error", "cancelled"}:
            return snap
        time.sleep(1.5)
    raise SystemExit("TIMEOUT waiting for job")


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "audio"

    print("[1] GET /api/health")
    health = requests.get(f"{BASE}/api/health", timeout=30).json()
    assert health["ffmpeg"], "ffmpeg missing"
    print(f"    ffmpeg={health['ffmpeg_version']} node={health['node']} yt-dlp={health['yt_dlp']}")

    print("[2] POST /api/info")
    info = requests.post(f"{BASE}/api/info", json={"url": TARGET}, timeout=180).json()
    if "detail" in info:
        raise SystemExit(f"info failed: {info}")
    print(f"    {info['title']} // {info['duration_text']}")
    videos = info["formats"]["video"]
    audios = info["formats"]["audio"]
    print(f"    video options: {[v['label'] for v in videos]}")
    print(f"    audio options: {[a['label'] for a in audios]}")

    if mode == "audio":
        payload = {"url": TARGET, "format_id": audios[0]["format_id"], "mode": "audio", "bitrate": "320"}
        expected_ext = "mp3"
    else:
        wanted = int(sys.argv[2]) if len(sys.argv) > 2 else 360
        option = next((v for v in videos if v["height"] == wanted), videos[0])
        payload = {"url": TARGET, "format_id": option["format_id"], "mode": "video", "bitrate": None}
        expected_ext = "mp4"
        print(f"    selected: {option['label']} ({option['format_id']}) {option['note']}")

    print("[3] POST /api/download")
    started = requests.post(f"{BASE}/api/download", json=payload, timeout=180).json()
    if "detail" in started:
        raise SystemExit(f"download refused: {started}")
    print(f"    job={started['job_id']} ws={started['ws_url']} est={started['estimated_bytes']}")

    print("[4] websocket progress stream")
    import asyncio

    import websockets

    async def stream(job_id: str) -> dict:
        last = {}
        async with websockets.connect(f"ws://127.0.0.1:8000/ws/download/{job_id}", max_size=4 * 1024 * 1024) as ws:
            async for raw in ws:
                event = __import__("json").loads(raw)
                etype = event.get("type")
                if etype == "log":
                    print(f"    {event['text']}")
                elif etype == "progress":
                    print(f"    ... {event['percent']}% {event.get('speed')}")
                elif etype == "snapshot":
                    last = event
                elif etype in {"done", "error", "cancelled"}:
                    last.update(event)
                    print(f"    [{etype}] received")
                    break
        return last

    events = asyncio.run(stream(started["job_id"]))

    print("[5] poll status (long-poll fallback)")
    final = wait_for(started["job_id"])
    if final["status"] != "finished":
        raise SystemExit(f"job ended {final['status']}: {final['error']}")
    print(f"    file={final['filename']} size={final['filesize']}")
    assert final["filename"].lower().endswith(expected_ext), f"expected .{expected_ext}"

    print("[6] GET /api/file")
    with requests.get(f"{BASE}/api/file/{final['job_id']}", timeout=120, stream=True) as res:
        res.raise_for_status()
        disposition = res.headers.get("content-disposition", "")
        first = next(res.iter_content(64), b"")
        print(f"    status={res.status_code} disposition={disposition[:80]} head={first[:12]!r}")

    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
