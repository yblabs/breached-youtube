import { useEffect, useRef } from 'react'
import { formatBytes, formatEta, formatSpeed, parseLog } from '../lib/format'
import { fileUrl } from '../lib/api'

const SEGMENTS = 44

function Meter({ percent, phase }) {
  const filled = Math.round((Math.min(100, Math.max(0, percent)) / 100) * SEGMENTS)
  const cls = ['meter', phase === 'processing' ? 'is-merge' : '', phase === 'finished' ? 'is-done' : '', phase === 'error' ? 'is-error' : '']
    .filter(Boolean)
    .join(' ')
  return (
    <div className={cls} role="progressbar" aria-valuenow={Math.round(percent)} aria-valuemin="0" aria-valuemax="100">
      {Array.from({ length: SEGMENTS }).map((_, i) => (
        <span key={i} className={`seg ${i < filled ? 'on' : ''} ${i === filled - 1 && phase === 'downloading' ? 'head' : ''}`} />
      ))}
    </div>
  )
}

function Terminal({ logs }) {
  const bodyRef = useRef(null)
  useEffect(() => {
    const node = bodyRef.current
    if (node) node.scrollTop = node.scrollHeight
  }, [logs])

  return (
    <div className="terminal hud-box hud-box--sm" style={{ '--hud-edge': 'rgba(0,243,255,0.35)' }}>
      <div className="flex items-center justify-between border-b border-[rgba(0,243,255,0.22)] px-4 py-2">
        <span className="flex items-center gap-2 text-[10.5px] tracking-[0.26em] text-[#00f3ff]">
          <span className="dot" style={{ color: '#00f3ff' }} />
          SYS.LOG // STREAM://
        </span>
        <span className="text-[10px] tracking-[0.2em] text-[#4d5b62]">{logs.length} LINES</span>
      </div>
      <div className="terminal__body" ref={bodyRef}>
        {logs.length === 0 && <div className="text-[#4d5b62]">[SYS.BOOT] AWAITING TELEMETRY...</div>}
        {logs.map((line, i) => {
          const { tag, tagClass, body } = parseLog(line)
          return (
            <div className="log-line" key={`${i}-${line.slice(0, 12)}`}>
              {tag && <span className={tagClass}>{tag} </span>}
              <span className="text-[#9fb1b8]">{body}</span>
              {i === logs.length - 1 && <span className="caret ml-1 inline-block !h-[0.9em] !w-[0.5em] translate-y-[1px]" />}
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function DownloadPanel({ job, progress, logs, onAbort, onRetry, onReset }) {
  const status = progress.status || job.status || 'queued'
  const percent = status === 'finished' ? 100 : progress.percent || 0
  const phase = status === 'finished' ? 'finished' : status === 'error' ? 'error' : status === 'processing' ? 'processing' : 'downloading'

  const headline = {
    queued: 'QUEUEING EXTRACTION...',
    downloading: `DOWNLOADING PACKETS... ${Math.round(percent)}%`,
    processing: 'FFMPEG MERGE IN PROGRESS...',
    finished: 'TRANSFER COMPLETE',
    error: 'EXTRACTION FAILED',
    cancelled: 'TRANSFER ABORTED',
  }[status] || 'STANDBY...'

  const headlineClass =
    status === 'finished' ? 'glow-toxic text-[#39ff14]' : status === 'error' || status === 'cancelled' ? 'glow-hot text-[#ff003c]' : 'glow-neon text-[#00f3ff]'

  const terminal = status === 'finished' || status === 'error' || status === 'cancelled'

  return (
    <section className="slide-in mt-10 flex flex-col gap-4" aria-label="transfer progress">
      <div className="section-rule">
        <span>// TRANSFER IN PROGRESS</span>
        <span className="text-[10px] tracking-[0.2em] text-[#4d5b62]">JOB {job.jobId}</span>
      </div>

      <div className="hud-box relative p-5 sm:p-6" style={{ '--tick-color': status === 'finished' ? '#39ff14' : '#00f3ff' }}>
        <span className="hud-ticks" aria-hidden="true" />
        <div className="mb-4 flex flex-wrap items-end justify-between gap-4">
          <div className="flex flex-col gap-1">
            <span className="kicker">{job.label} // {job.mode.toUpperCase()} PAYLOAD</span>
            <span className={`text-xl font-bold tracking-[0.1em] sm:text-2xl ${headlineClass}`}>{headline}</span>
          </div>
          <div className={`font-[var(--font-hud)] text-5xl font-bold sm:text-6xl ${headlineClass}`} style={{ fontFamily: 'var(--font-hud)' }}>
            {Math.round(percent)}
            <span className="text-2xl">%</span>
          </div>
        </div>

        <Meter percent={percent} phase={phase} />

        <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-[11px] tracking-[0.16em] text-[#84969e]">
          <span>
            BYTES <span className="text-[#00f3ff]">{formatBytes(progress.downloaded)}</span> / {formatBytes(progress.total)}
          </span>
          <span>
            RATE <span className="text-[#00f3ff]">{formatSpeed(progress.speed)}</span>
          </span>
          <span>
            ETA <span className="text-[#00f3ff]">{formatEta(progress.eta)}</span>
          </span>
          <span>
            STATE <span className={terminal ? 'text-[#39ff14]' : 'text-[#ff003c]'}>{status.toUpperCase()}</span>
          </span>
        </div>

        {status === 'error' && progress.error && (
          <div className="stripe-bg mt-4 border border-[rgba(255,0,60,0.6)] px-4 py-3 text-[12px] tracking-[0.1em] text-[#ff8fa6]">
            <span className="glow-hot font-bold text-[#ff003c]">[ERR] </span>
            {progress.error}
          </div>
        )}
      </div>

      <Terminal logs={logs} />

      <div className="flex flex-wrap gap-3">
        {status === 'finished' && (
          <a className="hud-btn hud-btn--toxic" href={fileUrl(job.jobId)} download={progress.filename || undefined}>
            <span className="hud-btn__face">
              <span className="hud-btn__label glow-toxic px-6 py-3 text-[13px] font-bold tracking-[0.2em] text-[#39ff14]">
                ▼ EXECUTE FILE TRANSFER{progress.filename ? ` // ${formatBytes(progress.size || 0)}` : ''}
              </span>
            </span>
          </a>
        )}
        {(status === 'error' || status === 'cancelled') && (
          <button className="hud-btn" onClick={onRetry}>
            <span className="hud-btn__face">
              <span className="hud-btn__label glow-neon px-6 py-3 text-[13px] font-bold tracking-[0.2em] text-[#00f3ff]">
                ↻ RETRY EXTRACTION
              </span>
            </span>
          </button>
        )}
        {!terminal && (
          <button className="hud-btn hud-btn--hot" onClick={onAbort}>
            <span className="hud-btn__face">
              <span className="hud-btn__label px-6 py-3 text-[13px] font-bold tracking-[0.2em] text-[#ff8fa6]">
                ■ ABORT TRANSFER
              </span>
            </span>
          </button>
        )}
        <button className="hud-btn hud-btn--ghost" onClick={onReset}>
          <span className="hud-btn__face">
            <span className="hud-btn__label px-6 py-3 text-[13px] tracking-[0.2em] text-[#84969e]">
              ⟲ NEW TARGET
            </span>
          </span>
        </button>
      </div>
    </section>
  )
}
