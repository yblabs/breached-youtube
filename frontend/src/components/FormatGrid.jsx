import { formatBytes, tierOf } from '../lib/format'

const TIERS = [
  { key: '4k', title: 'VIDEO // 4K ULTRA HD', accent: 'hot', hint: '2160P+ · FFMPEG MUX' },
  { key: 'qhd', title: 'VIDEO // QHD 1440P', accent: 'neon', hint: 'STREAM MERGE' },
  { key: 'fhd', title: 'VIDEO // FULL HD 1080P', accent: 'neon', hint: 'STREAM MERGE' },
  { key: 'hd', title: 'VIDEO // HD 720P', accent: 'neon', hint: 'PROGRESSIVE / MERGE' },
  { key: 'sd', title: 'VIDEO // STANDARD', accent: 'neon', hint: 'LOW-BANDWIDTH' },
]

function Payload({ option, selected, disabled, onSelect, accent }) {
  const isLocked = selected?.format_id === option.format_id && selected?.mode === option.mode && selected?.bitrate === option.bitrate
  const cls = [
    'hud-btn',
    'payload',
    accent === 'hot' ? 'hud-btn--hot' : '',
    isLocked ? 'is-locked' : '',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <button
      type="button"
      className={cls}
      disabled={disabled}
      aria-pressed={isLocked}
      onClick={() => onSelect(option)}
    >
      <span className="hud-btn__face">
        <span className="hud-btn__label flex items-center justify-between gap-3 px-4 py-3">
          <span className="flex flex-col items-start gap-1 text-left">
            <span className="flex items-baseline gap-2">
              <span className="text-lg font-bold tracking-[0.08em] text-[#e6f8fb]">{option.label}</span>
              {isLocked && (
                <span className="text-[10px] tracking-[0.2em] text-[#39ff14]">[LOCKED]</span>
              )}
            </span>
            <span className="text-[10.5px] tracking-[0.16em] text-[#84969e]">{option.note || option.source}</span>
          </span>
          <span className="flex flex-col items-end gap-1">
            <span
              className={`px-2 py-0.5 text-[10px] tracking-[0.18em] ${
                option.height >= 2160 || option.mode === 'audio'
                  ? 'bg-[rgba(255,0,60,0.16)] text-[#ff8fa6]'
                  : 'bg-[rgba(0,243,255,0.12)] text-[#00f3ff]'
              }`}
            >
              {option.height >= 2160 ? option.badge : option.mode === 'audio' ? 'MP3' : option.badge}
            </span>
            <span className="text-[10px] tracking-[0.14em] text-[#4d5b62]">
              ~{formatBytes(option.est_size)}
            </span>
          </span>
        </span>
      </span>
    </button>
  )
}

export default function FormatGrid({ info, selected, onSelect, onSelectAll, disabled }) {
  const video = info.formats?.video || []
  const audio = info.formats?.audio || []
  const total = video.length + audio.length

  const grouped = TIERS.map((tier) => ({
    ...tier,
    items: video.filter((f) => tierOf(f.height) === tier.key),
  })).filter((g) => g.items.length > 0)

  return (
    <section className="mt-10 flex flex-col gap-9" aria-label="payload selection">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="section-rule">
          <span>// SELECT PAYLOAD</span>
        </div>
        <span className="text-[11px] tracking-[0.2em] text-[#4d5b62]">
          {video.length} VIDEO STREAMS · {audio.length} ENCODERS
        </span>
      </div>

      {onSelectAll && total > 0 && (
        <div className="target-wrap slide-in hud-box hud-box--hot p-4 sm:p-5" style={{ '--tick-color': '#ff003c' }}>
          <span className="hud-ticks" aria-hidden="true" />
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex flex-col gap-1">
              <span className="kicker text-[#ff8fa6]">// BATCH EXTRACTION</span>
              <span className="text-[12.5px] tracking-[0.08em] text-[#84969e]">
                SWEEP EVERY PAYLOAD &mdash; {video.length} VIDEO TIER{video.length === 1 ? '' : 'S'} + {audio.length} MP3 ENCODER{audio.length === 1 ? '' : 'S'} &mdash; INTO ONE BUNDLE.
              </span>
            </div>
            <button type="button" className="hud-btn hud-btn--hot" disabled={disabled} onClick={onSelectAll}>
              <span className="hud-btn__face">
                <span className="hud-btn__label glow-hot px-6 py-3 text-[13px] font-bold tracking-[0.2em] text-[#ff8fa6]">
                  &#8681; DOWNLOAD ALL // {total} FILES
                </span>
              </span>
            </button>
          </div>
        </div>
      )}

      {grouped.map((group) => (
        <div key={group.key} className="flex flex-col gap-3">
          <div className={`section-rule ${group.accent === 'hot' ? 'section-rule--hot' : ''}`}>
            <span>{group.title}</span>
            <span className="text-[10px] tracking-[0.2em] text-[#4d5b62]">{group.hint}</span>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {group.items.map((option) => (
              <Payload
                key={`${option.mode}-${option.format_id}`}
                option={option}
                accent={group.accent}
                selected={selected}
                disabled={disabled}
                onSelect={onSelect}
              />
            ))}
          </div>
        </div>
      ))}

      {audio.length > 0 && (
        <div className="flex flex-col gap-3">
          <div className="section-rule section-rule--hot">
            <span>AUDIO // MP3 EXTRACTION</span>
            <span className="text-[10px] tracking-[0.2em] text-[#4d5b62]">FFMPEG TRANSCODE · {audio[0].source}</span>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {audio.map((option) => (
              <Payload
                key={`audio-${option.bitrate}`}
                option={option}
                accent="hot"
                selected={selected}
                disabled={disabled}
                onSelect={onSelect}
              />
            ))}
          </div>
        </div>
      )}
    </section>
  )
}
