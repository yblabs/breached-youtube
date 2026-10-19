# BREACHED YOUTUBE — Cyberpunk YouTube Extraction Protocol

High-performance YouTube downloader with a heavy cyberpunk HUD.
**Made by Yash & Bhupesh.**
Paste a link → scan available qualities (4K MP4 / 1080p / 720p / 320kbps MP3) →
watch packets land over a live WebSocket stream → pull the file.

```
backend/    FastAPI + yt-dlp + ffmpeg      (127.0.0.1:8000)
frontend/   React 19 + Vite + Tailwind 4   (127.0.0.1:5173)
start.ps1   diagnostics + dual launcher
```

---

## 1. System dependencies (do this first)

| Requirement | Why | Check |
| --- | --- | --- |
| **ffmpeg** | merges 1080p+ video/audio streams, transcodes MP3 | `ffmpeg -version` |
| **Python 3.11+** | FastAPI engine | `python --version` |
| **Node 18+** | Vite build **and** yt-dlp's JS runtime for format decryption | `node -v` |

Install ffmpeg (Windows):

```powershell
winget install Gyan.FFmpeg
```

Linux / macOS: `apt install ffmpeg` · `brew install ffmpeg`.

> ffmpeg is **mandatory**: without it 4K/1080p muxing and MP3 extraction fail.
> The API reports `ffmpeg: true/false` at `/api/health`, and the HUD header shows it live.

## 2. Run

```powershell
.\start.ps1
```

The launcher verifies ffmpeg/python/node, installs dependencies on first run, then opens two consoles:

- HUD → http://127.0.0.1:5173
- API → http://127.0.0.1:8000/api/health (docs at `/docs`)

Manual alternative:

```powershell
# terminal 1
cd backend
pip install -r requirements.txt
python run_server.py

# terminal 2
cd frontend
npm install
npm run dev
```

Production-style single process (serves the built HUD from FastAPI):

```powershell
cd frontend && npm run build
cd ../backend && python run_server.py     # open http://127.0.0.1:8000
```

## 3. API

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/api/info` | POST `{url}` / GET `?url=` | title, thumbnail, duration, grouped format matrix |
| `/api/download` | POST `{url, format_id, mode, bitrate}` | starts a job → `{job_id, ws_url, ...}` |
| `/ws/download/{job_id}` | WS | live progress + terminal log lines |
| `/api/download/{job_id}` | GET | snapshot (long-poll fallback, 500ms) |
| `/api/download/{job_id}` | DELETE | abort + purge |
| `/api/file/{job_id}` | GET | streams the finished artifact |
| `/api/health` | GET | ffmpeg / node / yt-dlp diagnostics |

**Merge logic:** YouTube stores 1080p+ video and audio as separate streams.
The backend resolves the chosen video `format_id`, picks the best compatible audio
(`m4a` for mp4 containers, `opus` for webm) and asks yt-dlp for
`<video>+<audio>`, with `merge_output_format="mp4"` so ffmpeg muxes both tracks
into one file. MP3 jobs run yt-dlp's `FFmpegExtractAudio` post-processor at
320/192/128 kbps.

## 4. Smoke test

```powershell
cd backend
python smoke_test.py audio      # MP3 320 path
python smoke_test.py video 480  # video + ffmpeg merge path (any height you like)
```

Exercises: health → info → download → WebSocket progress → long-poll snapshot → file fetch.

## 5. Design system

- Void black `#050505`, neon cyan `#00f3ff`, hot magenta `#ff003c`, toxic green `#39ff14`
- Monospace only (Space Mono / Fira Code / VT323 via Google Fonts)
- Zero border radius anywhere (global `border-radius: 0`), angular `clip-path` notches
- Glow via `filter: drop-shadow()` on wrappers (clip-path clips box-shadows)
- CRT scanlines, drifting grid, vignette, glitch sweep overlay
- Grayscale + RGB-split glitch treatment on the thumbnail
- Segmented block meter (44 blocks) instead of a smooth bar
- Terminal log with colour-coded tags: `[SYS.MSG]` `[NET.OK]` `[FFMPEG]` `[OK]` `[ERR]`

## 6. Project layout

```
backend/
  app/engine.py     yt-dlp discovery, format intelligence, ffmpeg merge planning, progress hooks
  app/jobs.py       job registry, worker threads, event bus
  app/main.py       REST + WebSocket surface
  smoke_test.py     end-to-end checks
frontend/
  src/App.jsx                 state machine, WS + long-poll fallback, auto file handoff
  src/index.css               the cyberpunk design system (Tailwind v4 @theme)
  src/components/             Backdrop · Header · UrlInput · MetaCard · FormatGrid · DownloadPanel
```

## 7. Notes

- Only `youtube.com` / `youtu.be` (and bare 11-char video IDs) are accepted.
- Extracted metadata is cached for 15 minutes so scan + download share one request.
- Finished artifacts live in `backend/downloads/<JOB_ID>/` and are purged after 30 minutes.
- Respect YouTube's Terms of Service and copyright law — download only content you own
  or have rights to.
