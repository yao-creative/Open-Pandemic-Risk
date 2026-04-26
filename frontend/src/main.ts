type HealthResponse = {
  status?: string
}

type ReadyzResponse = {
  ready: boolean
  checks?: Record<string, string>
  details?: string[]
}

type FetchResult<T> = {
  ok: boolean
  status: number | null
  data: T | null
  error: string | null
  url: string
}

const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

const statusLogEl = getElement('status-log')
const frontendUrlEl = getElement('frontend-url')
const apiBaseEl = getElement('api-base')
const frontendStatusPillEl = getElement('frontend-status-pill')
const healthPillEl = getElement('health-pill')
const healthSummaryEl = getElement('health-summary')
const readySummaryEl = getElement('ready-summary')
const readyDetailsEl = getElement('ready-details')
const refreshPillEl = getElement('refresh-pill')
const copyStatusEl = getElement('copy-status')

const linkMap = {
  health: getLink('health-link'),
  ready: getLink('ready-link'),
  pipeline: getLink('pipeline-link'),
  debug: getLink('debug-link')
}

const refreshButton = getButton('refresh-button')
const copyButton = getButton('copy-button')

refreshButton.addEventListener('click', () => {
  void refreshChecks()
})

copyButton.addEventListener('click', () => {
  void copySummary()
})

setText(frontendUrlEl, window.location.origin)
setText(apiBaseEl, apiBase)
setLinks()
appendLog(`frontend_url=${window.location.href}`)
appendLog(`api_base=${apiBase}`)

void refreshChecks()

function getElement(id: string): HTMLElement {
  const el = document.getElementById(id)
  if (!el) {
    throw new Error(`Missing element: ${id}`)
  }
  return el
}

function getLink(id: string): HTMLAnchorElement {
  const el = document.getElementById(id)
  if (!(el instanceof HTMLAnchorElement)) {
    throw new Error(`Missing anchor: ${id}`)
  }
  return el
}

function getButton(id: string): HTMLButtonElement {
  const el = document.getElementById(id)
  if (!(el instanceof HTMLButtonElement)) {
    throw new Error(`Missing button: ${id}`)
  }
  return el
}

function setText(el: HTMLElement, value: string): void {
  el.textContent = value
}

function setPill(el: HTMLElement, label: string, tone: 'ok' | 'warn' | 'neutral' = 'neutral'): void {
  el.textContent = label
  el.classList.remove('ok', 'warn')
  if (tone === 'ok') el.classList.add('ok')
  if (tone === 'warn') el.classList.add('warn')
}

function appendLog(line: string): void {
  const stamp = new Date().toLocaleTimeString()
  statusLogEl.textContent = `${statusLogEl.textContent}\n[${stamp}] ${line}`.trim()
}

async function fetchJson<T>(path: string): Promise<FetchResult<T>> {
  const url = `${apiBase}${path}`
  try {
    const res = await fetch(url)
    const text = await res.text()
    const data = text ? (JSON.parse(text) as T) : null
    return {
      ok: res.ok,
      status: res.status,
      data,
      error: null,
      url
    }
  } catch (error) {
    return {
      ok: false,
      status: null,
      data: null,
      error: String(error),
      url
    }
  }
}

async function refreshChecks(): Promise<void> {
  setPill(refreshPillEl, 'refreshing', 'neutral')
  appendLog('refresh_started')

  const [health, ready] = await Promise.all([
    fetchJson<HealthResponse>('/healthz'),
    fetchJson<ReadyzResponse>('/readyz')
  ])

  renderHealth(health)
  renderReady(ready)

  const frontendTone = health.ok ? 'ok' : 'warn'
  setPill(frontendStatusPillEl, health.ok ? 'frontend live' : 'api unreachable', frontendTone)
  setPill(refreshPillEl, 'fresh', health.ok && ready.ok ? 'ok' : 'warn')

  appendLog(`health status=${health.status ?? 'network_error'} ok=${health.ok}`)
  if (health.error) appendLog(`health error=${health.error}`)
  appendLog(`ready status=${ready.status ?? 'network_error'} ok=${ready.ok}`)
  if (ready.error) appendLog(`ready error=${ready.error}`)
  if (ready.data?.details?.length) appendLog(`ready details=${ready.data.details.join(' | ')}`)
}

function renderHealth(result: FetchResult<HealthResponse>): void {
  if (result.ok && result.data?.status) {
    setPill(healthPillEl, 'healthy', 'ok')
    setText(healthSummaryEl, `${result.status} ${result.data.status}`)
    return
  }

  setPill(healthPillEl, 'issue', 'warn')
  setText(healthSummaryEl, result.error ? `network_error ${result.error}` : `${result.status ?? 'unknown'} unhealthy`)
}

function renderReady(result: FetchResult<ReadyzResponse>): void {
  if (result.data) {
    const ready = Boolean(result.data.ready) && result.ok
    setText(
      readySummaryEl,
      JSON.stringify(
        {
          http_status: result.status,
          backend_ready: ready,
          checks: result.data.checks
        },
        null,
        2
      )
    )
    setText(readyDetailsEl, result.data.details?.join(' | ') || 'no extra details')
    setPill(healthPillEl, ready && healthPillEl.textContent === 'healthy' ? 'healthy' : 'degraded', ready ? 'ok' : 'warn')
    return
  }

  setText(
    readySummaryEl,
    JSON.stringify(
      {
        http_status: result.status,
        backend_ready: false,
        error: result.error
      },
      null,
      2
    )
  )
  setText(readyDetailsEl, result.error || 'readiness check failed')
  setPill(healthPillEl, 'degraded', 'warn')
}

function setLinks(): void {
  linkMap.health.href = `${apiBase}/healthz`
  linkMap.ready.href = `${apiBase}/readyz`
  linkMap.pipeline.href = `${apiBase}/docs#/pipeline/run_pipeline`
  linkMap.debug.href = `${apiBase}/debug/stages`
}

async function copySummary(): Promise<void> {
  const summary = [
    `frontend_url=${window.location.href}`,
    `api_base=${apiBase}`,
    `health=${healthSummaryEl.textContent}`,
    `ready=${readySummaryEl.textContent}`,
    `details=${readyDetailsEl.textContent}`
  ].join('\n')

  try {
    await navigator.clipboard.writeText(summary)
    setText(copyStatusEl, 'Debug summary copied to clipboard.')
    appendLog('copy_summary success=true')
  } catch (error) {
    setText(copyStatusEl, `Clipboard write failed: ${String(error)}`)
    appendLog(`copy_summary success=false error=${String(error)}`)
  }
}
