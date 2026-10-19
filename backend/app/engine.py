"""yt-dlp engine: environment discovery, metadata extraction, format intelligence."""

from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import time
from collections import OrderedDict
from typing import Any
from urllib.parse import urlparse

import yt_dlp
from yt_dlp.utils import DownloadError

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


class EngineError(Exception):
    """Raised with a client-safe, human readable message."""


class DownloadAborted(Exception):
    """Raised from progress hooks when the operator cancels the job."""


def _registry_path() -> str:
    """Read the live Machine+User PATH (os.environ can be stale in a long lived shell)."""
    if os.name != "nt":
        return ""
    try:
        import winreg
    except Exception:
        return ""
    chunks: list[str] = []
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(hive, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment") as key:
                value, _ = winreg.QueryValueEx(key, "Path")
                chunks.append(str(value))
        except Exception:
            continue
    return ";".join(chunks)


def _prepend_path(directory: str) -> None:
    if not directory:
        return
    current = os.environ.get("PATH", "")
    parts = [p.strip(os.pathsep).strip() for p in current.split(os.pathsep)]
    if directory not in parts:
        os.environ["PATH"] = directory + os.pathsep + current


def discover_ffmpeg() -> str | None:
    """Locate the directory holding the ffmpeg binary."""
    exe = shutil.which("ffmpeg")
    if exe:
        return os.path.dirname(os.path.abspath(exe))
    binary = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    for raw in _registry_path().split(";"):
        raw = raw.strip().strip('"')
        if raw and os.path.isfile(os.path.join(raw, binary)):
            return raw
    local = os.environ.get("LOCALAPPDATA", "")
    for pattern in (
        os.path.join(local, "Microsoft", "WinGet", "Packages", "Gyan.FFmpeg_*", "*", "bin"),
        r"C:\ffmpeg\bin",
        "/opt/homebrew/bin",
        "/usr/local/bin",
        "/usr/bin",
    ):
        for candidate in glob.glob(pattern):
            if os.path.isfile(os.path.join(candidate, binary)):
                return candidate
    return None


def discover_node() -> str | None:
    exe = shutil.which("node")
    if exe:
        return os.path.dirname(os.path.abspath(exe))
    for candidate in (
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "nodejs", "node.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "nodejs", "node.exe"),
    ):
        if os.path.isfile(candidate):
            return os.path.dirname(candidate)
    return None


FFMPEG_DIR = discover_ffmpeg()
FFMPEG_AVAILABLE = FFMPEG_DIR is not None
NODE_DIR = discover_node()
NODE_AVAILABLE = NODE_DIR is not None

# Make sure child tooling (yt-dlp -> ffmpeg merge, JS runtime) resolves on this process PATH.
_prepend_path(FFMPEG_DIR or "")
_prepend_path(NODE_DIR or "")


def ffmpeg_version() -> str | None:
    if not FFMPEG_DIR:
        return None
    binary = os.path.join(FFMPEG_DIR, "ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        out = subprocess.run([binary, "-version"], capture_output=True, text=True, timeout=8, creationflags=flags)
        first = (out.stdout or "").splitlines()[0]
        match = re.search(r"ffmpeg version (\S+)", first)
        return match.group(1) if match else (first or None)
    except Exception:
        return None


FFMPEG_VERSION = ffmpeg_version()

BASE_OPTS: dict[str, Any] = {
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "playlist_items": "1",
    "socket_timeout": 30,
    "retries": 3,
    "fragment_retries": 5,
    "concurrent_fragment_downloads": 4,
    "noprogress": True,
}
if NODE_AVAILABLE:
    BASE_OPTS["js_runtimes"] = {"node": {}}

ALLOWED_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
}


def normalize_url(raw: str | None) -> str | None:
    """Accept a full URL, a bare youtu.be/youtube link, or a bare 11 char video id."""
    url = (raw or "").strip()
    if not url or len(url) > 400:
        return None
    if re.fullmatch(r"[\w-]{11}", url):
        return f"https://www.youtube.com/watch?v={url}"
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return None
    host = (parsed.hostname or "").lower().rstrip(".")
    if host not in ALLOWED_HOSTS and not host.endswith(".youtube.com"):
        return None
    return url


def clean_error(message: str) -> str:
    text = ANSI_RE.sub("", str(message)).strip()
    text = re.sub(r"^ERROR:\s*", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text)
    return text[:400] if text else "EXTRACTION FAILED"


class _CaptureLogger:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def debug(self, msg: str) -> None:  # noqa: D102
        return None

    def info(self, msg: str) -> None:  # noqa: D102
        return None

    def warning(self, msg: str) -> None:  # noqa: D102
        self.lines.append(clean_error(msg))

    def error(self, msg: str) -> None:  # noqa: D102
        self.lines.append(clean_error(msg))


class InfoCache:
    """Small TTL cache so /api/info and /api/download share one extraction."""

    def __init__(self, ttl: float = 900.0, maxsize: int = 48) -> None:
        self.ttl = ttl
        self.maxsize = maxsize
        self._data: OrderedDict[str, tuple[float, dict]] = OrderedDict()
        self._lock = __import__("threading").Lock()

    def get(self, key: str) -> dict | None:
        with self._lock:
            hit = self._data.get(key)
            if not hit:
                return None
            stamp, info = hit
            if time.time() - stamp > self.ttl:
                self._data.pop(key, None)
                return None
            self._data.move_to_end(key)
            return info

    def set(self, key: str, info: dict) -> None:
        with self._lock:
            self._data[key] = (time.time(), info)
            self._data.move_to_end(key)
            while len(self._data) > self.maxsize:
                self._data.popitem(last=False)


CACHE = InfoCache()

def extract(url: str, _depth: int = 0) -> tuple[dict, list[str]]:
    """Return (info_dict, warnings). Cached per URL for 15 minutes."""
    cached = CACHE.get(url)
    if cached is not None:
        return cached, []

    logger = _CaptureLogger()
    opts = dict(BASE_OPTS)
    opts["logger"] = logger
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError as exc:
        raise EngineError(clean_error(str(exc))) from exc
    except EngineError:
        raise
    except Exception as exc:  # network, geo block, extractor bug
        raise EngineError(f"EXTRACTOR FAULT // {clean_error(exc)}") from exc

    if not info:
        raise EngineError("EXTRACTOR RETURNED NO DATA FOR THIS TARGET")

    if info.get("_type") in ("playlist", "multi_video"):
        entries = [e for e in (info.get("entries") or []) if e]
        if not entries:
            raise EngineError("PLAYLIST EMPTY // NO EXTRACTABLE VIDEO ENTRY")
        if _depth >= 2:
            raise EngineError("PLAYLIST NESTING TOO DEEP // PICK A SINGLE VIDEO")
        first = entries[0]
        if first.get("formats"):
            info = first
        else:
            target = first.get("url") or first.get("webpage_url")
            if not target:
                raise EngineError("PLAYLIST ENTRY HAS NO RESOLVABLE URL")
            return extract(target, _depth + 1)

    if info.get("is_live"):
        raise EngineError("LIVE TRANSMISSION DETECTED // VOD REPLAY REQUIRED")

    CACHE.set(url, info)
    warnings = [w for w in logger.lines if w][:6]
    return info, warnings


def _duration(info: dict) -> float | None:
    value = info.get("duration")
    return float(value) if value else None


def human_size(num: float | None) -> str:
    if not num:
        return "0 B"
    step = 1024.0
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(num)
    for unit in units:
        if value < step:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= step
    return f"{value:.1f} PB"


def hms(seconds: float | None) -> str:
    total = int(seconds or 0)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _fmt_size(fmt: dict, duration: float | None) -> int:
    size = fmt.get("filesize") or fmt.get("filesize_approx")
    if size:
        return int(size)
    tbr = fmt.get("tbr")
    if tbr and duration:
        return int(float(tbr) * 1000 / 8 * duration)
    return 0


def _audio_pool(formats: list[dict]) -> list[dict]:
    return [
        f
        for f in formats
        if f.get("vcodec") in (None, "none")
        and f.get("acodec") not in (None, "none")
        and f.get("acodec") != "unknown"
        and f.get("ext") not in ("m3u8", "mpd")
    ]


def pick_best_audio(formats: list[dict], prefer_ext: str | None = None) -> dict | None:
    pool = _audio_pool(formats)
    if not pool:
        return None
    # DRC (compressed dynamic range) variants are near-identical in bitrate but
    # flatter the master — only use them when nothing else exists.
    plain = [f for f in pool if not str(f.get("format_id", "")).endswith("-drc")]
    if plain:
        pool = plain
    if prefer_ext:
        preferred = [f for f in pool if f.get("ext") == prefer_ext]
        if preferred:
            pool = preferred
    return max(pool, key=lambda f: (float(f.get("abr") or 0), float(f.get("tbr") or 0)))


def _video_score(fmt: dict) -> tuple:
    """mp4 first, SDR first, audio-free stream first, then raw quality."""
    return (
        1 if fmt.get("ext") == "mp4" else 0,
        1 if str(fmt.get("dynamic_range") or "SDR").upper() == "SDR" else 0,
        1 if not (fmt.get("acodec") and fmt.get("acodec") != "none") else 0,
        float(fmt.get("tbr") or 0),
        float(fmt.get("fps") or 0),
    )


BADGES = {
    4320: "8K UHD",
    2160: "4K UHD",
    1440: "QHD 2K",
    1080: "FULL HD",
    720: "HD READY",
    480: "STANDARD",
    360: "MOBILE",
    240: "COMPACT",
    144: "MINIMAL",
}

AUDIO_BITRATES = (320, 192, 128)


def build_options(info: dict) -> dict:
    """Group raw yt-dlp formats into a UI friendly video/audio matrix."""
    formats = info.get("formats") or []
    duration = _duration(info)

    groups: dict[int, list[dict]] = {}
    for fmt in formats:
        height = fmt.get("height")
        vcodec = fmt.get("vcodec")
        if not height or not vcodec or vcodec == "none":
            continue
        if fmt.get("ext") in ("m3u8", "mpd"):
            continue
        groups.setdefault(int(height), []).append(fmt)

    best_audio = pick_best_audio(formats)
    video: list[dict] = []
    for height in sorted(groups, reverse=True):
        best = max(groups[height], key=_video_score)
        has_audio = bool(best.get("acodec") and best.get("acodec") != "none")
        video_size = _fmt_size(best, duration)
        height_audio = None if has_audio else (
            pick_best_audio(formats, prefer_ext="m4a" if best.get("ext") == "mp4" else None) or best_audio
        )
        audio_size = _fmt_size(height_audio, duration) if height_audio else 0
        fps = int(best.get("fps") or 0)
        codec = str(best.get("vcodec") or "").split(".")[0].upper()
        notes = [f"{fps}FPS" if fps else "", str(best.get("ext") or "").upper(), codec]
        notes.append("MUXED" if has_audio else "MERGE")
        video.append(
            {
                "mode": "video",
                "format_id": str(best.get("format_id")),
                "height": height,
                "label": f"{height}P",
                "badge": BADGES.get(height, "RAW"),
                "fps": fps,
                "ext": str(best.get("ext") or ""),
                "vcodec": codec,
                "has_audio": has_audio,
                "est_size": video_size + audio_size,
                "note": " · ".join(n for n in notes if n),
            }
        )

    audio: list[dict] = []
    if best_audio:
        abr = int(float(best_audio.get("abr") or best_audio.get("tbr") or 0))
        codec = str(best_audio.get("acodec") or "").split(".")[0].upper()
        source = f"{abr or '?'}KBPS {codec} SRC"
        for quality in AUDIO_BITRATES:
            audio.append(
                {
                    "mode": "audio",
                    "format_id": str(best_audio.get("format_id")),
                    "bitrate": str(quality),
                    "label": f"MP3 {quality}",
                    "sublabel": f"{quality} KBPS",
                    "source": source,
                    "ext": "mp3",
                    "est_size": int(quality * 1000 / 8 * duration) if duration else 0,
                }
            )

    return {"video": video, "audio": audio}


def describe(info: dict, warnings: list[str] | None = None) -> dict:
    options = build_options(info)
    duration = int(info.get("duration") or 0)
    return {
        "id": info.get("id"),
        "title": info.get("title") or "UNTITLED TARGET",
        "thumbnail": info.get("thumbnail"),
        "duration": duration,
        "duration_text": hms(duration),
        "uploader": info.get("uploader") or info.get("channel") or "UNKNOWN OPERATOR",
        "channel": info.get("channel") or info.get("uploader") or "UNKNOWN",
        "view_count": info.get("view_count"),
        "like_count": info.get("like_count"),
        "webpage_url": info.get("webpage_url"),
        "is_live": bool(info.get("is_live")),
        "warnings": warnings or [],
        "formats": options,
    }


def resolve_plan(info: dict, mode: str, format_id: str, bitrate: str | None = None) -> dict:
    """Turn a chosen format id into a concrete yt-dlp format spec + merge strategy."""
    formats = info.get("formats") or []
    target = next((f for f in formats if str(f.get("format_id")) == str(format_id)), None)
    if target is None:
        raise EngineError(f"FORMAT {format_id} NOT OFFERED FOR THIS TARGET // RE-SCAN")

    duration = _duration(info)
    streams: list[dict] = []

    if mode == "video":
        has_audio = bool(target.get("acodec") and target.get("acodec") != "none")
        height = int(target.get("height") or 0)
        codec = str(target.get("vcodec") or "").split(".")[0].upper()
        audio_src = None
        if has_audio:
            spec = str(format_id)
            est = _fmt_size(target, duration)
            merge_to = None
        else:
            if not FFMPEG_AVAILABLE:
                raise EngineError("FFMPEG OFFLINE // 1080P+ MERGE REQUIRES FFMPEG ON PATH")
            # YouTube serves 1080p+ video and audio as separate streams: force a mux.
            # mp4 video muxes far more safely with AAC than with opus.
            prefer = "m4a" if target.get("ext") == "mp4" else None
            audio_src = pick_best_audio(formats, prefer_ext=prefer)
            audio_src = audio_src or pick_best_audio(formats)
            if audio_src:
                spec = f"{format_id}+{audio_src.get('format_id')}/{format_id}+bestaudio/{format_id}"
                est = _fmt_size(target, duration) + _fmt_size(audio_src, duration)
            else:
                spec = str(format_id)
                est = _fmt_size(target, duration)
            merge_to = "mp4"
        streams.append({"role": "video", "id": format_id, "label": f"{height}P {codec}"})
        if audio_src:
            abr = int(float(audio_src.get("abr") or audio_src.get("tbr") or 0))
            streams.append(
                {
                    "role": "audio",
                    "id": str(audio_src.get("format_id")),
                    "label": f"{abr}KBPS {str(audio_src.get('acodec') or '').split('.')[0].upper()}",
                }
            )
        container = "mp4"
        label = f"{height}P"
    elif mode == "audio":
        if not FFMPEG_AVAILABLE:
            raise EngineError("FFMPEG OFFLINE // MP3 EXTRACTION REQUIRES FFMPEG ON PATH")
        quality = str(bitrate or "320")
        if not quality.isdigit() or not 64 <= int(quality) <= 320:
            quality = "320"
        spec = f"{format_id}/bestaudio/best"
        est = int(int(quality) * 1000 / 8 * duration) if duration else _fmt_size(target, duration)
        abr = int(float(target.get("abr") or target.get("tbr") or 0))
        streams.append(
            {
                "role": "audio",
                "id": str(format_id),
                "label": f"{abr}KBPS {str(target.get('acodec') or '').split('.')[0].upper()} SOURCE",
            }
        )
        merge_to = None
        container = "mp3"
        label = f"MP3 {quality}"
    else:
        raise EngineError("UNKNOWN MODE // EXPECTED video|audio")

    return {
        "mode": mode,
        "format": spec,
        "est_bytes": int(est or 0),
        "merge_output_format": merge_to,
        "postprocessors": (
            []
            if mode == "video"
            else [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": str(bitrate or "320"),
                }
            ]
        ),
        "bitrate": str(bitrate or "320") if mode == "audio" else None,
        "container": container,
        "label": label,
        "streams": streams,
    }


class _RunState:
    """Tracks byte counts across multi-file downloads (video track + audio track)."""

    def __init__(self) -> None:
        self.base = 0
        self.stage_id: str | None = None
        self.stage_total = 0
        self.stage_done = 0
        self.percent = 0.0
        self.last_push = 0.0
        self.last_logged_pct = -1


def _mmss(value: Any) -> str:
    try:
        return hms(int(value))
    except Exception:
        return "--:--"


def _make_progress_hook(plan: dict, state: _RunState, emit, should_cancel=None):
    est_total = int(plan.get("est_bytes") or 0)

    def hook(d: dict) -> None:
        if should_cancel is not None and should_cancel():
            raise DownloadAborted("TRANSFER ABORTED BY OPERATOR")

        status = d.get("status")
        info = d.get("info_dict") or {}
        stage = str(info.get("format_id") or "") or None

        if status == "downloading":
            total = int(d.get("total_bytes") or d.get("total_bytes_estimate") or 0)
            done = int(d.get("downloaded_bytes") or 0)
            if stage and stage != state.stage_id:
                state.stage_id = stage
                state.stage_total = 0
                state.stage_done = 0
            if total:
                state.stage_total = total
            state.stage_done = done

            absolute = state.base + done
            if est_total:
                pct = min(99.0, 100.0 * absolute / est_total)
            elif state.stage_total:
                pct = 100.0 * done / state.stage_total
            else:
                pct = state.percent
            state.percent = max(state.percent, pct)

            speed = d.get("speed")
            eta = d.get("eta")
            now = time.monotonic()
            if now - state.last_push >= 0.15:
                state.last_push = now
                emit(
                    {
                        "type": "progress",
                        "percent": round(state.percent, 1),
                        "downloaded": int(absolute),
                        "total": int(est_total or state.stage_total),
                        "speed": float(speed) if speed else None,
                        "eta": int(eta) if eta is not None else None,
                    }
                )
            whole = int(state.percent)
            if whole > state.last_logged_pct:
                state.last_logged_pct = whole
                rate = f"{speed / 1048576:.1f}MB/S" if speed else "CALC..."
                emit(
                    {
                        "type": "log",
                        "text": f"[SYS.MSG] DOWNLOADING PACKETS... {whole}% // {rate} // ETA {_mmss(eta)}",
                    }
                )

        elif status == "finished":
            total = int(d.get("total_bytes") or d.get("downloaded_bytes") or state.stage_total or 0)
            state.base += total
            state.stage_total = 0
            state.stage_done = 0
            name = os.path.basename(str(d.get("filename") or "STREAM"))
            emit(
                {
                    "type": "progress",
                    "percent": round(min(99.0, state.percent), 1),
                    "downloaded": int(state.base),
                    "total": int(est_total or state.base),
                    "speed": None,
                    "eta": None,
                }
            )
            emit({"type": "log", "text": f"[NET.CACHE] {name} SEALED // {human_size(total)} CACHED"})

    return hook


def _make_postprocessor_hook(plan: dict, state: _RunState, emit):
    """Log only the meaningful ffmpeg passes (merge / mp3 transcode) and push
    the meter into the 90s while ffmpeg is crunching, since ffmpeg reports no
    byte-level progress of its own."""
    tracked = {"active": False}

    def hook(d: dict) -> None:
        status = d.get("status")
        raw = d.get("postprocessor")
        name = raw if isinstance(raw, str) else (type(raw).__name__ if raw is not None else "")

        if status == "started":
            if "Merger" in name:
                text = "[FFMPEG] MERGE PROTOCOL ENGAGED // MUXING VIDEO + AUDIO TRACKS"
            elif "ExtractAudio" in name:
                text = f"[FFMPEG] TRANSCODING AUDIO CORE -> MP3 @ {plan.get('bitrate') or '320'}KBPS"
            else:
                return  # metadata/fixup passes are noise
            if tracked["active"]:
                return  # same pass announced twice by the extractor
            tracked["active"] = True
            if state.percent < 92.0:
                state.percent = 92.0
                emit({"type": "progress", "percent": 92.0})
            emit({"type": "status", "status": "processing"})
            emit({"type": "log", "text": text})
        elif status == "finished" and tracked["active"]:
            tracked["active"] = False
            emit({"type": "log", "text": "[FFMPEG] PASS COMPLETE // CONTAINER FINALIZED"})

    return hook


def _pick_final_file(workdir: str) -> tuple[str, str, int] | None:
    candidates = []
    for entry in os.listdir(workdir):
        if entry.endswith((".part", ".ytdl", ".temp", ".json", ".description")):
            continue
        path = os.path.join(workdir, entry)
        if os.path.isfile(path):
            candidates.append(path)
    if not candidates:
        return None
    chosen = max(candidates, key=lambda p: os.path.getsize(p))
    return chosen, os.path.basename(chosen), os.path.getsize(chosen)


def run_download(url: str, plan: dict, workdir: str, emit, should_cancel=None) -> tuple[str, str, int]:
    """Execute the yt-dlp download (runs inside a worker thread)."""
    os.makedirs(workdir, exist_ok=True)
    state = _RunState()

    opts = dict(BASE_OPTS)
    opts.update(
        {
            "format": plan["format"],
            "outtmpl": os.path.join(workdir, "%(title).140B [%(id)s].%(ext)s"),
            "progress_hooks": [_make_progress_hook(plan, state, emit, should_cancel)],
            "postprocessor_hooks": [_make_postprocessor_hook(plan, state, emit)],
            "postprocessors": plan.get("postprocessors") or [],
        }
    )
    if plan.get("merge_output_format"):
        opts["merge_output_format"] = plan["merge_output_format"]

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
    except DownloadAborted:
        raise
    except DownloadError as exc:
        raise EngineError(clean_error(str(exc))) from exc
    except EngineError:
        raise
    except Exception as exc:
        raise EngineError(f"UNEXPECTED FAULT // {clean_error(exc)}") from exc

    found = _pick_final_file(workdir)
    if not found:
        raise EngineError("OUTPUT FILE MISSING // EXTRACTION PRODUCED NO ARTIFACT")
    return found


ENGINE_READY = True
