export function formatBytes(value) {
  const bytes = Number(value) || 0
  if (bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let size = bytes
  let i = 0
  while (size >= 1024 && i < units.length - 1) {
    size /= 1024
    i += 1
  }
  return `${size.toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

export function formatEta(seconds) {
  if (seconds === null || seconds === undefined) return '--:--'
  const total = Math.max(0, Math.floor(Number(seconds)))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const pad = (n) => String(n).padStart(2, '0')
  return h > 0 ? `${pad(h)}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`
}

export function formatCount(value) {
  const n = Number(value)
  if (!Number.isFinite(n)) return '--'
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(1)}B`
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(n)
}

export function formatSpeed(value) {
  if (!value) return '--'
  return `${(Number(value) / 1048576).toFixed(1)} MB/S`
}

const TAG_CLASS = {
  'SYS.BOOT': 'tag-sys',
  'SYS.MSG': 'tag-sys',
  'SYS.CACHE': 'tag-sys',
  'NET.OK': 'tag-net',
  'NET.CACHE': 'tag-net',
  FFMPEG: 'tag-ffmpeg',
  OK: 'tag-ok',
  ERR: 'tag-err',
  WARN: 'tag-warn',
}

export function parseLog(line) {
  const match = /^\[([A-Z0-9.]+)\]\s?([\s\S]*)$/.exec(line || '')
  if (!match) return { tag: null, tagClass: 'tag-sys', body: line || '' }
  return { tag: match[0].slice(0, match[0].indexOf(']') + 1), tagClass: TAG_CLASS[match[1]] || 'tag-sys', body: match[2] }
}

export function tierOf(height) {
  if (height >= 2160) return '4k'
  if (height >= 1440) return 'qhd'
  if (height >= 1080) return 'fhd'
  if (height >= 720) return 'hd'
  return 'sd'
}
