import argparse
import json
import sys
import time
from urllib.request import Request, urlopen


BASE = "http://127.0.0.1:8000"


def _post(path, payload):
    req = Request(BASE + path, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def _get(path, timeout=120):
    with urlopen(BASE + path, timeout=timeout) as resp:
        return resp.read()


def test_audio():
    info = _post("/api/info", {"url": "https://www.youtube.com/watch?v=jNQXAC9IVRw"})
    assert info["ok"], info
    audio = next((a for a in info["formats"]["audio"] if a["bitrate"] == "192"), None) or info["formats"]["audio"][0]
    d = _post("/api/download", {"url": info["resolved_url"], "format_id": audio["format_id"], "mode": "audio", "bitrate": audio["bitrate"]})
    job = d["job_id"]
    for _ in range(60):
        try:
            st = json.loads(_get(f"/api/download/{job}").decode())
        except Exception:
            time.sleep(1); continue
        if st["status"] in ("finished","error","cancelled"):
            break
        time.sleep(1)
    assert st["status"] == "finished", st
    data = _get(f"/api/file/{job}", timeout=300)
    assert len(data) > 1000
    print("OK")


def test_video(height):
    info = _post("/api/info", {"url": "https://www.youtube.com/watch?v=jNQXAC9IVRw"})
    vids = info["formats"]["video"]
    target = next((v for v in vids if v["height"] == height), vids[0] if vids else None)
    assert target, info
    d = _post("/api/download", {"url": info["resolved_url"], "format_id": target["format_id"], "mode": "video"})
    job = d["job_id"]
    for _ in range(90):
        try:
            st = json.loads(_get(f"/api/download/{job}").decode())
        except Exception:
            time.sleep(1); continue
        if st["status"] in ("finished","error","cancelled"):
            break
        time.sleep(1)
    assert st["status"] == "finished", st
    data = _get(f"/api/file/{job}", timeout=600)
    assert len(data) > 10000
    print("OK")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=["audio","video"])
    p.add_argument("height", nargs="?", type=int, default=480)
    args = p.parse_args()
    if args.mode == "audio":
        test_audio()
    else:
        test_video(args.height)
    print("ALL CHECKS PASSED")
