type PipelineRunCreateResponse = {
  pipeline_run_id: number
  status: string
  stage_order: string[]
}

type PipelineStageRun = {
  stage_name: string
  status: string
  started_at: string
  finished_at: string | null
  error_summary: string | null
}

type PipelineRunStatusResponse = {
  pipeline_run_id: number
  pipeline_name: string
  status: string
  started_at: string
  finished_at: string | null
  error_summary: string | null
  artifacts: Record<string, unknown>
  stage_runs: PipelineStageRun[]
}

type ReportViewModel = {
  riskAnalytics: Record<string, unknown> | null
  recommendation: Record<string, unknown> | null
  evidence: Array<Record<string, unknown>>
}

const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
const pollIntervalMs = 2500

const runButtonEl = document.getElementById('run-pipeline') as HTMLButtonElement | null
const statusPanelEl = document.getElementById('status-panel')
const reportPanelEl = document.getElementById('report-panel')

if (!runButtonEl || !statusPanelEl || !reportPanelEl) {
  throw new Error('Missing dashboard elements')
}
const runButton = runButtonEl
const statusPanel = statusPanelEl
const reportPanel = reportPanelEl

let activeRunId: number | null = null
let pollTimerId: number | null = null

function createIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `dashboard-${crypto.randomUUID()}`
  }
  return `dashboard-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function setStatusMarkup(markup: string): void {
  statusPanel.innerHTML = markup
}

function setReportMarkup(markup: string): void {
  reportPanel.innerHTML = markup
}

function renderInitialState(): void {
  setStatusMarkup('<p class="status-line">No run started yet.</p>')
  setReportMarkup('<p>Run the pipeline to generate a report.</p>')
}

function toJsonBlock(value: unknown): string {
  return `<pre>${JSON.stringify(value, null, 2)}</pre>`
}

function deriveReportViewModel(status: PipelineRunStatusResponse): ReportViewModel {
  const reportPayload = status.artifacts.report
  if (reportPayload && typeof reportPayload === 'object') {
    const report = reportPayload as Record<string, unknown>
    const evidence = Array.isArray(report.evidence) ? (report.evidence as Array<Record<string, unknown>>) : []
    return {
      riskAnalytics:
        report.risk_analytics && typeof report.risk_analytics === 'object'
          ? (report.risk_analytics as Record<string, unknown>)
          : null,
      recommendation:
        report.recommendation && typeof report.recommendation === 'object'
          ? (report.recommendation as Record<string, unknown>)
          : null,
      evidence
    }
  }

  const fallbackEvidence = Array.isArray(status.artifacts.citations)
    ? (status.artifacts.citations as Array<Record<string, unknown>>)
    : []
  return {
    riskAnalytics: null,
    recommendation: null,
    evidence: fallbackEvidence
  }
}

function renderStatus(status: PipelineRunStatusResponse): void {
  const stageRows = status.stage_runs
    .map(
      (item) =>
        `<tr>
          <td>${item.stage_name}</td>
          <td>${item.status}</td>
          <td>${item.started_at ?? '-'}</td>
          <td>${item.finished_at ?? '-'}</td>
          <td>${item.error_summary ?? '-'}</td>
        </tr>`
    )
    .join('')
  const statusClass = status.status === 'failed' ? 'error' : status.status === 'completed' ? 'ok' : ''
  setStatusMarkup(`
    <p class="status-line ${statusClass}">Run #${status.pipeline_run_id} - ${status.status}</p>
    <p>Started: ${status.started_at} | Finished: ${status.finished_at ?? '-'}</p>
    <p class="${status.error_summary ? 'error' : ''}">Error: ${status.error_summary ?? 'None'}</p>
    <table>
      <thead>
        <tr><th>Stage</th><th>Status</th><th>Started</th><th>Finished</th><th>Error</th></tr>
      </thead>
      <tbody>${stageRows}</tbody>
    </table>
  `)
}

function renderReport(status: PipelineRunStatusResponse): void {
  const reportVm = deriveReportViewModel(status)
  const evidenceRows = reportVm.evidence
    .map((item, index) => {
      const citationId = String(item.citation_id ?? `E${index + 1}`)
      const path = String(item.path ?? item.snapshot_path ?? '-')
      const value = item.value === undefined ? '-' : JSON.stringify(item.value)
      return `<tr><td>${citationId}</td><td>${path}</td><td>${value}</td></tr>`
    })
    .join('')
  setReportMarkup(`
    <h2>Consolidated Report</h2>
    <h3>Risk Analytics</h3>
    ${reportVm.riskAnalytics ? toJsonBlock(reportVm.riskAnalytics) : '<p>Not available yet.</p>'}
    <h3>Recommendation</h3>
    ${reportVm.recommendation ? toJsonBlock(reportVm.recommendation) : '<p>Not available yet.</p>'}
    <h3>Expanded Evidence</h3>
    <table>
      <thead>
        <tr><th>Citation ID</th><th>Snapshot Path</th><th>Value</th></tr>
      </thead>
      <tbody>${evidenceRows || '<tr><td colspan="3">No evidence available.</td></tr>'}</tbody>
    </table>
  `)
}

function stopPolling(): void {
  if (pollTimerId !== null) {
    window.clearTimeout(pollTimerId)
    pollTimerId = null
  }
  runButton.disabled = false
}

async function pollRunStatus(runId: number): Promise<void> {
  try {
    const response = await fetch(`${apiBase}/pipeline/runs/${runId}`)
    const payload = (await response.json()) as PipelineRunStatusResponse
    renderStatus(payload)
    renderReport(payload)
    if (payload.status === 'completed' || payload.status === 'failed') {
      stopPolling()
      return
    }
    pollTimerId = window.setTimeout(() => {
      void pollRunStatus(runId)
    }, pollIntervalMs)
  } catch (err) {
    setStatusMarkup(`<p class="error">Polling failed: ${String(err)}</p>`)
    stopPolling()
  }
}

async function runPipeline(): Promise<void> {
  stopPolling()
  runButton.disabled = true
  setStatusMarkup('<p class="status-line">Triggering pipeline...</p>')
  setReportMarkup('<p>Waiting for first status update...</p>')
  try {
    const response = await fetch(`${apiBase}/pipeline/run`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({idempotency_key: createIdempotencyKey()})
    })
    const payload = (await response.json()) as PipelineRunCreateResponse
    activeRunId = payload.pipeline_run_id
    setStatusMarkup(
      `<p class="status-line">Run #${activeRunId} queued. Polling every ${pollIntervalMs / 1000}s.</p>`
    )
    void pollRunStatus(activeRunId)
  } catch (err) {
    runButton.disabled = false
    setStatusMarkup(`<p class="error">Failed to start run: ${String(err)}</p>`)
  }
}

runButton.addEventListener('click', () => {
  void runPipeline()
})

void (async () => {
  renderInitialState()
  if (activeRunId !== null) {
    await pollRunStatus(activeRunId)
  }
})()
