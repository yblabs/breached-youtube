import { formatBytes } from '../lib/format'
import { batchFileUrl } from '../lib/api'

const SEGMENTS = 44

const STATUS_LABEL = {
  queued: 'QUEUED',
  downloading: 'ACTIVE',
  processing: 'MERGING',
  finished: 'COMPLETE',
  error: 'FAILED',
  cancelled: 'ABORTED',
}

function Meter({ percent, status }) {
  const filled = Math.round((Math.min(100, Math.max(0, percent)) / 100) * SEGMENTS)
  const cls = [
    'meter',
    status === 'finished' ? 'is-done' : '',
    status === 'error' || status === 'cancelled' ? 'is-error' : '',
  ]
    .filter(Boolean)
    .join(' ')
  return (
    <div className={cls} role="progressbar" aria-valuenow={Math.round(percent)} aria-valuemin="0" aria-valuemax="100">
      {Array.from({ length: SEGMENTS }).map((_, i) => (
        <span
          key={i}
          className={`seg ${i < filled ? 'on' : ''} ${i === filled - 1 && status === 'downloading' ? 'head' : ''}`}
        />
      ))}
    </div>
  )
}

function ItemRow({ item }) {
  const pct = item.status === 'finished' ? 100 : Math.round(item.percent || 0)
  const tone =
    item.status === 'finished' ? '#39ff14' : item.status === 'error' || item.status === 'cancelled' ? '#ff003c' : '#00f3ff'
  const label = STATUS_LABEL[item.status] || String(item.status || '').toUpperCase()
  return (
    <div className="flex flex-col gap-1.5 border border-[rgba(0,243,255,0.14)] px-3 py-2">
      <div className="flex items-center justify-between gap-3">
        <span className="flex items-center gap-2 text-[11.5px] tracking-[0.12em] text-[#c6d6db]">
          <span className="dot" style={{ color: tone }} />
          {item.label}
          <span className="text-[10px] tracking-[0.16em] text-[#4d5b62]">{item.mode === 'audio' ? 'MP3' : 'MP4'}</span>
        </span>
        <span className="text-[10.5px] tracking-[0.16em]" style={{ color: tone }}>
          {label}
          {item.size ? ` · ${formatBytes(item.size)}` : ''}
        </span>
      </div>
      <div className="h-1 w-full bg-[rgba(0,243,255,0.12)]">
        <div className="h-full" style={{ width: `${pct}%`, background: tone }} />
      </div>
      {item.error && <span className="text-[10px] tracking-[0.08em] text-[#ff8fa6]">{item.error}</span>}
    </div>
  )
}

export default function BatchPanel({ batch, state, onAbort, onReset }) {
  const status = state.status || 'queued'
  const percent = status === 'finished' ? 100 : state.percent || 0
  const items = state.items || []
  const finishedCount = state.finishedCount ?? items.filter((i) => i.status === 'finished').length
  const totalCount = state.totalCount ?? items.length
  const terminal = ['finished', 'partial', 'error', 'cancelled'].includes(status)

  const headline =
    {
      queued: 'QUEUEING SWARM...',
      downloading: `DOWNLOADING ${finishedCount}/${totalCount} PAYLOADS... ${Math.round(percent)}%`,
      processing: 'FFMPEG MERGE IN PROGRESS...',
      finished: 'SWEEP COMPLETE',
      partial: 'SWEEP PARTIAL // SOME PAYLOADS FAILED',
      error: 'SWEEP FAILED',
      cancelled: 'SWEEP ABORTED',
    }[status] || 'STANDBY...'

  const headlineClass =
    status === 'finished'
      ? 'glow-toxic text-[#39ff14]'
      : status === 'error' || status === 'cancelled'
        ? 'glow-hot text-[#ff003c]'
        : status === 'partial'
          ? 'glow-hot text-[#ff8fa6]'
          : 'glow-neon text-[#00f3ff]'

  return (
    <section className="slide-in mt-10 flex flex-col gap-4" aria-label="batch transfer progress">
      <div className="section-rule">
        <span>// BATCH TRANSFER IN PROGRESS</span>
        <span className="text-[10px] tracking-[0.2em] text-[#4d5b62]">BATCH {batch.batchId}</span>
      </div>

      <div className="hud-box relative p-5 sm:p-6" style={{ '--tick-color': status === 'finished' ? '#39ff14' : '#00f3ff' }}>
        <span className="hud-ticks" aria-hidden="true" />
        <div className="mb-4 flex flex-wrap items-end justify-between gap-4">
          <div className="flex flex-col gap-1">
            <span className="kicker">DOWNLOAD ALL // {totalCount} PAYLOADS // BUNDLE</span>
            <span className={`text-xl font-bold tracking-[0.1em] sm:text-2xl ${headlineClass}`}>{headline}</span>
          </div>
          <div className={`text-5xl font-bold sm:text-6xl ${headlineClass}`} style={{ fontFamily: 'var(--font-hud)' }}>
            {Math.round(percent)}
            <span className="text-2xl">%</span>
          </div>
        </div>

        <Meter percent={percent} status={status} />

        <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-[11px] tracking-[0.16em] text-[#84969e]">
          <span>
            ITEMS <span className="text-[#00f3ff]">{finishedCount}</span> / {totalCount} COMPLETE
          </span>
          <span>
            BYTES <span className="text-[#00f3ff]">{formatBytes(state.downloaded)}</span> / {formatBytes(state.total)}
          </span>
          <span>
            STATE <span className={terminal ? 'text-[#39ff14]' : 'text-[#ff003c]'}>{status.toUpperCase()}</span>
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {items.map((item, i) => (
          <ItemRow key={item.job_id || `${item.label}-${i}`} item={item} />
        ))}
      </div>

      <div className="flex flex-wrap gap-3">
        {finishedCount > 0 && (
          <a className="hud-btn hud-btn--toxic" href={batchFileUrl(batch.batchId)} download>
            <span className="hud-btn__face">
              <span className="hud-btn__label glow-toxic px-6 py-3 text-[13px] font-bold tracking-[0.2em] text-[#39ff14]">
                &#9660; EXECUTE BUNDLE ({finishedCount} FILES · ZIP)
              </span>
            </span>
          </a>
        )}
        {!terminal && (
          <button className="hud-btn hud-btn--hot" onClick={onAbort}>
            <span className="hud-btn__face">
              <span className="hud-btn__label px-6 py-3 text-[13px] font-bold tracking-[0.2em] text-[#ff8fa6]">
                &#9632; ABORT SWEEP
              </span>
            </span>
          </button>
        )}
        <button className="hud-btn hud-btn--ghost" onClick={onReset}>
          <span className="hud-btn__face">
            <span className="hud-btn__label px-6 py-3 text-[13px] tracking-[0.2em] text-[#84969e]">
              &#8634; NEW TARGET
            </span>
          </span>
        </button>
      </div>
    </section>
  )
}
