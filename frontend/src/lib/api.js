const JSON_HEADERS = { 'Content-Type': 'application/json' }

async function parse(res) {
  let data = {}
  try {
    data = await res.json()
  } catch {
    data = {}
  }
  if (!res.ok) {
    const detail = typeof data.detail === 'string' ? data.detail : `HTTP ${res.status}`
    const err = new Error(detail)
    err.status = res.status
    throw err
  }
  return data
}

export function fetchInfo(url) {
  return fetch('/api/info', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ url }),
  }).then(parse)
}

export function startDownload(payload) {
  return fetch('/api/download', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(payload),
  }).then(parse)
}

export function startDownloadAll(payload) {
  return fetch('/api/download-all', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(payload),
  }).then(parse)
}

export function fetchJob(jobId) {
  return fetch(`/api/download/${jobId}`).then(parse)
}

export function abortJob(jobId) {
  return fetch(`/api/download/${jobId}`, { method: 'DELETE' }).then(parse)
}

export function fetchBatch(batchId) {
  return fetch(`/api/download-all/${batchId}`).then(parse)
}

export function abortBatch(batchId) {
  return fetch(`/api/batch/${batchId}`, { method: 'DELETE' }).then(parse)
}

export function fetchHealth() {
  return fetch('/api/health').then(parse)
}

export function fileUrl(jobId) {
  return `/api/file/${jobId}`
}

export function batchFileUrl(batchId) {
  return `/api/batch/${batchId}/file`
}

export function wsUrl(jobId) {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${window.location.host}/ws/download/${jobId}`
}

export function wsBatchUrl(batchId) {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${window.location.host}/ws/batch/${batchId}`
}
