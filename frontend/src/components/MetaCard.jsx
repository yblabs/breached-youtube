import { formatCount, formatBytes } from '../lib/format'

export default function MetaCard({ info, onReset }) {
  const video = info.formats?.video || []
  const audio = info.formats?.audio || []
  const top = video[0]
  const maxHeight = video.reduce((max, f) => Math.max(max, f.height || 0), 0)
  const estTop = video.find((f) => f.height === maxHeight)?.est_size || top?.est_size || 0

  return (
    <section className="slide-in hud-box hud-box--flat relative mt-8 p-4 sm:p-5" style={{ '--tick-color': '#00f3ff' }} aria-label="target metadata">
      <span className="hud-ticks" aria-hidden="true" />
      <div className="flex flex-col gap-5 md:flex-row md:items-stretch">
        {/* thumbnail with digital glitch treatment */}
        <div className="relative w-full shrink-0 md:w-[300px]">
          <div
            className="glitch h-[170px] w-full md:h-full md:min-h-[168px]"
            style={{ '--gsrc': info.thumbnail ? `url(${info.thumbnail})` : 'none' }}
          >
            {info.thumbnail ? (
              <img src={info.thumbnail} alt="" loading="lazy" />
            ) : (
              <div className="flex h-full w-full items-center justify-center text-[11px] tracking-[0.3em] text-[#4d5b62]">
                NO SIGNAL
              </div>
            )}
            <div className="glitch__lines" />
            <div className="glitch__sweep" />
            <div className="absolute bottom-2 left-2 z-[4] bg-[rgba(5,5,5,0.85)] px-2 py-1 text-[10px] tracking-[0.24em] text-[#00f3ff]">
              LIVE FEED // RGB SPLIT
            </div>
          </div>
          <div className="pointer-events-none absolute inset-0 border border-[rgba(0,243,255,0.35)]" />
        </div>

        {/* title + meta */}
        <div className="flex min-w-0 flex-1 flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="chip chip--toxic">
              <span className="dot" style={{ color: '#39ff14' }} />
              TARGET ACQUIRED
            </span>
            <span className="chip">{info.duration_text} RUNTIME</span>
            {maxHeight >= 2160 && <span className="chip chip--hot">4K AVAILABLE</span>}
            <span className="chip hidden sm:inline-flex">{audio.length} AUDIO ENCODERS</span>
          </div>

          <h2 className="glow-neon text-lg leading-snug font-bold break-words text-[#e6f8fb] sm:text-2xl">
            {info.title}
          </h2>

          <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-[12px] tracking-[0.1em] text-[#84969e]">
            <span className="text-[#00f3ff]">@{info.channel}</span>
            <span>{formatCount(info.view_count)} VIEWS</span>
            <span>{formatCount(info.like_count)} LIKES</span>
            <span>ID {info.id}</span>
          </div>

          <div className="mt-auto flex flex-wrap gap-2 pt-1">
            <span className="chip">MAX {maxHeight || '--'}P</span>
            <span className="chip">MAX EST {formatBytes(estTop)}</span>
            <span className="chip chip--hot">{(info.warnings || []).length} EXTRACTOR NOTES</span>
          </div>
        </div>

        <div className="flex shrink-0 flex-row md:flex-col">
          <button className="hud-btn hud-btn--ghost h-fit" onClick={onReset}>
            <span className="hud-btn__face">
              <span className="hud-btn__label px-4 py-2 text-[11px] tracking-[0.2em] text-[#84969e]">
                NEW TARGET
              </span>
            </span>
          </button>
        </div>
      </div>
    </section>
  )
}
