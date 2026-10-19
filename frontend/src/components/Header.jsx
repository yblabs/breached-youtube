const HEALTH_DEFAULT = { ffmpeg: false, node: false, yt_dlp: '--', ffmpeg_version: null }

function StatusChip({ label, ok, value }) {
  return (
    <span className={`chip ${ok ? '' : 'chip--hot'}`} title={`${label}: ${value}`}>
      <span className="dot" style={{ color: ok ? '#39ff14' : '#ff003c' }} />
      {label} {ok ? 'ONLINE' : 'OFFLINE'}
    </span>
  )
}

export default function Header({ health }) {
  const h = health || HEALTH_DEFAULT
  return (
    <header className="sticky top-0 z-30 border-b border-[rgba(0,243,255,0.22)] bg-[rgba(5,5,5,0.86)] backdrop-blur-[3px]">
      <div className="mx-auto flex w-full max-w-6xl flex-wrap items-center justify-between gap-4 px-5 py-4 sm:px-8">
        <div className="flex flex-col gap-1">
          <div className="flex items-baseline gap-3">
            <span className="glow-neon flicker text-2xl font-bold tracking-[0.18em] text-[#00f3ff] sm:text-3xl">
              BREACHED <span className="text-[#ff003c]">YOUTUBE</span>
            </span>
            <span className="hidden text-[10px] tracking-[0.3em] text-[#4d5b62] sm:inline">v1.0.4</span>
          </div>
          <span className="text-[10px] tracking-[0.26em] text-[#4d5b62]">
            MADE BY <span className="glow-neon text-[#00f3ff]">YASH</span>
            <span className="text-[#ff003c]"> &amp; </span>
            <span className="glow-hot text-[#ff003c]">BHUPESH</span>
          </span>
        </div>

        <nav className="flex flex-wrap items-center gap-2" aria-label="system status">
          <StatusChip label="FFMPEG" ok={h.ffmpeg} value={h.ffmpeg_version || 'NOT FOUND'} />
          <StatusChip label="NODE RT" ok={h.node} value="JS RUNTIME" />
          <span className="chip">
            <span className="dot" style={{ color: '#00f3ff' }} />
            YT-DLP {h.yt_dlp}
          </span>
          <span className="chip chip--toxic hidden md:inline-flex">
            <span className="dot" style={{ color: '#39ff14' }} />
            LINK SECURE
          </span>
        </nav>
      </div>
      <div className="h-px w-full bg-gradient-to-r from-transparent via-[rgba(255,0,60,0.55)] to-transparent" />
    </header>
  )
}
