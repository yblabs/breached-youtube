import { useRef, useState } from 'react'

export default function UrlInput({ value, onChange, onSubmit, busy, error, locked }) {
  const [focused, setFocused] = useState(false)
  const inputRef = useRef(null)

  const paste = async () => {
    try {
      const text = await navigator.clipboard.readText()
      if (text) {
        onChange(text.trim())
        inputRef.current?.focus()
      }
    } catch {
      inputRef.current?.focus()
    }
  }

  const wrapClass = [
    'target-wrap',
    focused ? 'is-focus' : '',
    error ? 'is-error' : '',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        if (!busy) onSubmit()
      }}
      className="relative"
      aria-label="target url"
    >
      <div className={wrapClass}>
        <div className="hud-box relative" style={{ '--tick-color': error ? '#ff003c' : '#00f3ff' }}>
          <span className="hud-ticks" aria-hidden="true" />
          <span className="target-prompt" aria-hidden="true">
            &gt;<span className="caret" />
          </span>
          <input
            ref={inputRef}
            className="target-input"
            type="text"
            inputMode="url"
            autoComplete="off"
            spellCheck={false}
            disabled={locked}
            value={value}
            placeholder="INITIALIZE TARGET URL..."
            aria-label="Initialize target URL"
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            onChange={(e) => onChange(e.target.value)}
          />
          <div className="target-actions">
            <button
              type="button"
              className="hud-btn hud-btn--ghost hidden sm:block"
              onClick={paste}
              disabled={locked}
              aria-label="Paste from clipboard"
            >
              <span className="hud-btn__face">
                <span className="hud-btn__label px-4 py-2 text-[11px] tracking-[0.22em] text-[#84969e]">
                  PASTE
                </span>
              </span>
            </button>
            <button type="submit" className="hud-btn" disabled={busy || locked}>
              <span className="hud-btn__face">
                <span className="hud-btn__label glow-neon px-5 py-2 text-[13px] font-bold tracking-[0.2em] text-[#00f3ff]">
                  {busy ? 'RESOLVING...' : 'EXECUTE'}
                </span>
              </span>
            </button>
          </div>
        </div>
      </div>

      {busy && <div className="scanning-strip mt-3" aria-hidden="true" />}

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-[11px] tracking-[0.14em] text-[#4d5b62]">
        <span>ACCEPTS: youtube.com/watch?v=... · youtu.be/... · 11-CHAR VIDEO ID</span>
        {error && <span className="glow-hot text-[#ff003c]">{error}</span>}
      </div>
    </form>
  )
}
