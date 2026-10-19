import { useCallback, useEffect, useRef, useState } from 'react'
import Backdrop from './components/Backdrop'
import Header from './components/Header'
import UrlInput from './components/UrlInput'
import MetaCard from './components/MetaCard'
import FormatGrid from './components/FormatGrid'
import DownloadPanel from './components/DownloadPanel'
import BatchPanel from './components/BatchPanel'
import {
  abortBatch,
  abortJob,
  fetchBatch,
  fetchHealth,
  fetchInfo,
  fetchJob,
  fileUrl,
  startDownload,
  startDownloadAll,
  wsBatchUrl,
  wsUrl,
} from './lib/api'

const TERMINAL = ['finished', 'error', 'cancelled']
const BATCH_TERMINAL = ['finished', 'partial', 'error', 'cancelled']

export default function App() {
  const [health, setHealth] = useState(null)
  const [url, setUrl] = useState('')
  const [phase, setPhase] = useState('idle') // idle | scanning | ready
  const [info, setInfo] = useState(null)
  const [infoError, setInfoError] = useState(null)
  const [selected, setSelected] = useState(null)

  const [job, setJob] = useState(null)
  const [progress, setProgress] = useState({ status: 'queued', percent: 0, downloaded: 0, total: 0 })
  const [logs, setLogs] = useState([])

  const [batch, setBatch] = useState(null)
  const [batchState, setBatchState] = useState({ status: 'queued', percent: 0, items: [], total: 0, downloaded: 0 })

  const autoFired = useRef(false)
  const terminalRef = useRef(false)
  const batchTerminalRef = useRef(false)

  // ---- system health -------------------------------------------------
  useEffect(() => {
    fetchHealth()
      .then(setHealth)
      .catch(() => setHealth({ ffmpeg: false, node: false, yt_dlp: '--' }))
  }, [])

  // ---- metadata scan -------------------------------------------------
  const scan = useCallback(async () => {
    const target = url.trim()
    if (!target) {
      setInfoError('[ERR] EMPTY TARGET // PASTE A YOUTUBE LINK')
      return
    }
    setPhase('scanning')
    setInfoError(null)
    setInfo(null)
    setSelected(null)
    setJob(null)
    setBatch(null)
    terminalRef.current = false
    batchTerminalRef.current = false
    try {
      const data = await fetchInfo(target)
      setInfo(data)
      setUrl(data.resolved_url || target)
      const firstVideo = data.formats?.video?.[0]
      if (firstVideo) setSelected(firstVideo)
      setPhase('ready')
    } catch (err) {
      setPhase('idle')
      setInfoError(`[ERR] ${err.message}`)
    }
  }, [url])

  // ---- download job --------------------------------------------------
  const launch = useCallback(
    async (option) => {
      if (!option) return
      setSelected(option)
      setInfoError(null)
      try {
        const res = await startDownload({
          url: info?.resolved_url || url,
          format_id: option.format_id,
          mode: option.mode,
          bitrate: option.bitrate,
        })
        autoFired.current = false
        terminalRef.current = false
        setLogs([])
        setProgress({ status: 'queued', percent: 0, downloaded: 0, total: res.estimated_bytes || 0 })
        setJob({ jobId: res.job_id, label: res.label, mode: option.mode })
      } catch (err) {
        setInfoError(`[ERR] ${err.message}`)
      }
    },
    [info, url],
  )

  // ---- DOWNLOAD ALL: one job per payload, bundled into a batch --------
  const launchAll = useCallback(async () => {
    setInfoError(null)
    try {
      const res = await startDownloadAll({
        url: info?.resolved_url || url,
        video: true,
        audio: true,
      })
      setJob(null)
      batchTerminalRef.current = false
      setBatch({ batchId: res.batch_id, itemCount: res.item_count })
      setBatchState({
        status: res.status,
        percent: 0,
        items: res.items || [],
        total: res.estimated_bytes || 0,
        downloaded: 0,
        finishedCount: (res.items || []).filter((i) => i.status === 'finished').length,
        totalCount: res.item_count,
      })
    } catch (err) {
      setInfoError(`[ERR] ${err.message}`)
    }
  }, [info, url])

  // ---- realtime stream: websocket with long-poll fallback ------------
  useEffect(() => {
    const jobId = job?.jobId
    if (!jobId) return undefined

    let socket = null
    let pollTimer = null
    let stopped = false

    const apply = (ev) => {
      if (!ev || stopped) return
      switch (ev.type) {
        case 'snapshot': {
          const finished = ev.status === 'finished'
          setProgress({
            status: ev.status,
            percent: ev.percent,
            downloaded: finished ? ev.filesize || ev.downloaded : ev.downloaded,
            total: finished ? ev.filesize || ev.total : ev.total,
            speed: finished ? null : ev.speed,
            eta: finished ? null : ev.eta,
            filename: ev.filename,
            size: ev.filesize,
            error: ev.error,
          })
          setLogs(ev.logs || [])
          if (TERMINAL.includes(ev.status)) terminalRef.current = true
          break
        }
        case 'progress':
          setProgress((prev) => ({ ...prev, ...ev, type: undefined }))
          break
        case 'status':
          setProgress((prev) => ({ ...prev, status: ev.status }))
          break
        case 'log':
          setLogs((prev) => [...prev, ev.text])
          break
        case 'done':
          terminalRef.current = true
          setProgress((prev) => ({
            ...prev,
            status: 'finished',
            percent: 100,
            downloaded: ev.size,
            total: ev.size,
            filename: ev.filename,
            size: ev.size,
            speed: null,
            eta: null,
          }))
          setLogs((prev) => [...prev, `[OK] HANDOFF READY // ${ev.filename}`])
          break
        case 'error':
          terminalRef.current = true
          setProgress((prev) => ({ ...prev, status: 'error', error: ev.error }))
          break
        case 'cancelled':
          terminalRef.current = true
          setProgress((prev) => ({ ...prev, status: 'cancelled' }))
          break
        default:
          break
      }
    }

    const startPolling = () => {
      if (pollTimer || terminalRef.current || stopped) return
      pollTimer = setInterval(async () => {
        if (terminalRef.current) {
          clearInterval(pollTimer)
          return
        }
        try {
          const snap = await fetchJob(jobId)
          apply(snap)
        } catch {
          /* keep polling */
        }
      }, 500)
    }

    try {
      socket = new WebSocket(wsUrl(jobId))
      socket.onmessage = (event) => {
        try {
          apply(JSON.parse(event.data))
        } catch {
          /* malformed frame */
        }
      }
      socket.onerror = () => startPolling()
      socket.onclose = () => {
        if (!terminalRef.current) startPolling()
      }
    } catch {
      startPolling()
    }

    // safety net: if the socket never opens, fall back to long polling
    const fallback = setTimeout(() => {
      if (!socket || socket.readyState !== 1) startPolling()
    }, 1500)

    return () => {
      stopped = true
      clearTimeout(fallback)
      if (pollTimer) clearInterval(pollTimer)
      if (socket) {
        socket.onclose = null
        socket.close()
      }
    }
  }, [job?.jobId])

  // ---- batch stream: websocket pushed from the server-side poller ----
  useEffect(() => {
    const batchId = batch?.batchId
    if (!batchId) return undefined

    let socket = null
    let pollTimer = null
    let stopped = false

    const apply = (snap) => {
      if (!snap || stopped || snap.type !== 'batch') return
      const finishedCount = (snap.items || []).filter((i) => i.status === 'finished').length
      setBatchState({
        status: snap.status,
        percent: snap.percent || 0,
        items: snap.items || [],
        total: snap.total || 0,
        downloaded: snap.downloaded || 0,
        finishedCount,
        totalCount: snap.total_count,
        zipUrl: snap.zip_url,
      })
      if (BATCH_TERMINAL.includes(snap.status)) batchTerminalRef.current = true
    }

    const startPolling = () => {
      if (pollTimer || batchTerminalRef.current || stopped) return
      pollTimer = setInterval(async () => {
        if (batchTerminalRef.current) {
          clearInterval(pollTimer)
          return
        }
        try {
          apply(await fetchBatch(batchId))
        } catch {
          /* keep polling */
        }
      }, 700)
    }

    try {
      socket = new WebSocket(wsBatchUrl(batchId))
      socket.onmessage = (event) => {
        try {
          apply(JSON.parse(event.data))
        } catch {
          /* malformed frame */
        }
      }
      socket.onerror = () => startPolling()
      socket.onclose = () => {
        if (!batchTerminalRef.current) startPolling()
      }
    } catch {
      startPolling()
    }

    const fallback = setTimeout(() => {
      if (!socket || socket.readyState !== 1) startPolling()
    }, 1800)

    return () => {
      stopped = true
      clearTimeout(fallback)
      if (pollTimer) clearInterval(pollTimer)
      if (socket) {
        socket.onclose = null
        socket.close()
      }
    }
  }, [batch?.batchId])

  // ---- auto-handoff of the finished artifact -------------------------
  useEffect(() => {
    if (progress.status !== 'finished' || !job?.jobId || autoFired.current) return
    autoFired.current = true
    const anchor = document.createElement('a')
    anchor.href = fileUrl(job.jobId)
    anchor.download = progress.filename || ''
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
  }, [progress.status, job?.jobId, progress.filename])

  // ---- actions --------------------------------------------------------
  const abort = async () => {
    if (!job?.jobId) return
    try {
      await abortJob(job.jobId)
    } catch {
      /* ignore */
    }
    terminalRef.current = true
    setProgress((prev) => ({ ...prev, status: 'cancelled' }))
  }

  const abortAll = async () => {
    if (!batch?.batchId) return
    try {
      await abortBatch(batch.batchId)
    } catch {
      /* ignore */
    }
    batchTerminalRef.current = true
    setBatchState((prev) => ({ ...prev, status: 'cancelled' }))
  }

  const reset = async () => {
    if (job?.jobId && !terminalRef.current) {
      try {
        await abortJob(job.jobId)
      } catch {
        /* ignore */
      }
    }
    if (batch?.batchId && !batchTerminalRef.current) {
      try {
        await abortBatch(batch.batchId)
      } catch {
        /* ignore */
      }
    }
    terminalRef.current = true
    batchTerminalRef.current = true
    setJob(null)
    setBatch(null)
    setBatchState({ status: 'queued', percent: 0, items: [], total: 0, downloaded: 0 })
    setInfo(null)
    setSelected(null)
    setLogs([])
    setProgress({ status: 'queued', percent: 0, downloaded: 0, total: 0 })
    setInfoError(null)
    setUrl('')
    setPhase('idle')
  }

  const retry = () => {
    if (selected) launch(selected)
  }

  return (
    <div className="relative min-h-screen">
      <Backdrop />

      <div className="relative z-10 flex min-h-screen flex-col">
        <Header health={health} />

        <main className="mx-auto w-full max-w-6xl flex-1 px-5 pt-10 pb-20 sm:px-8 sm:pt-14">
          {/* hero */}
          <div className="flex flex-col gap-3">
            <span className="kicker">// YOUTUBE STREAM EXTRACTION PROTOCOL</span>
            <h1 className="glow-neon text-3xl leading-[1.05] font-bold tracking-[0.06em] text-[#e6f8fb] sm:text-5xl">
              RIP THE STREAM <span className="glow-hot text-[#ff003c]">OUT OF THE VOID.</span>
            </h1>
            <p className="max-w-2xl text-[13px] leading-relaxed tracking-[0.08em] text-[#84969e]">
              2160P MP4 MUXING · 320KBPS MP3 TRANSCODE · FFMPEG MERGE PIPELINE. Paste a target,
              lock a payload, watch the packets land.
            </p>
          </div>

          <div className="mt-8">
            <UrlInput
              value={url}
              onChange={setUrl}
              onSubmit={scan}
              busy={phase === 'scanning'}
              error={infoError && !job && !batch ? infoError : null}
              locked={
                (!!job && !TERMINAL.includes(progress.status)) ||
                (!!batch && !BATCH_TERMINAL.includes(batchState.status))
              }
            />
          </div>

          {infoError && (job || batch) && (
            <div className="stripe-bg mt-6 border border-[rgba(255,0,60,0.6)] px-4 py-3 text-[12px] text-[#ff8fa6]">
              {infoError}
            </div>
          )}

          {phase === 'scanning' && (
            <div className="mt-8 flex items-center gap-3 text-[12px] tracking-[0.24em] text-[#00f3ff]">
              <span className="dot" style={{ color: '#00f3ff' }} />
              RESOLVING STREAM MANIFEST...
            </div>
          )}

          {info && <MetaCard info={info} onReset={reset} />}

          {info && !job && !batch && (
            <FormatGrid
              info={info}
              selected={selected}
              onSelect={launch}
              onSelectAll={launchAll}
              disabled={phase === 'scanning'}
            />
          )}

          {job && (
            <DownloadPanel
              job={job}
              progress={progress}
              logs={logs}
              onAbort={abort}
              onRetry={retry}
              onReset={reset}
            />
          )}

          {batch && (
            <BatchPanel batch={batch} state={batchState} onAbort={abortAll} onReset={reset} />
          )}

          {/* footer */}
          <footer className="mt-16 border-t border-[rgba(0,243,255,0.16)] pt-5 text-[10.5px] tracking-[0.2em] text-[#4d5b62]">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <span>BREACHED YOUTUBE :: LOCALHOST EXTRACTION NODE // NO TELEMETRY</span>
              <span className="text-[#3a464c]">
                MADE BY <span className="text-[#00f3ff]">YASH</span> &amp;{' '}
                <span className="text-[#ff003c]">BHUPESH</span>
              </span>
            </div>
            <div className="mt-2 text-[#334046]">
              {health?.ffmpeg
                ? `FFMPEG ${health.ffmpeg_version || ''} ARMED`
                : 'FFMPEG OFFLINE // 4K MERGE + MP3 WILL FAIL'}{' '}
              · YT-DLP {health?.yt_dlp || '--'} · PYTHON API 127.0.0.1:8000
            </div>
          </footer>
        </main>
      </div>
    </div>
  )
}
