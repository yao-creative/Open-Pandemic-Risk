import { api } from './api'
import { getApproximatePoint, hasCountryPoint } from './atlas'
import { COUNTRY_LABELS } from './countries'
import type {
  Contributor,
  CountryRiskDetail,
  CountryRiskRow,
  PipelineCountryResultsResponse,
  PipelineRunStatusResponse,
  RiskBand
} from './types'

type ViewMode = 'booting' | 'empty' | 'loading' | 'ready' | 'error'

type AppState = {
  mode: ViewMode
  results: PipelineCountryResultsResponse | null
  runStatus: PipelineRunStatusResponse | null
  selectedCountryCode: string | null
  selectedCountry: CountryRiskDetail | null
  errorMessage: string | null
  detailError: string | null
  detailLoading: boolean
  isLaunching: boolean
}

const MAX_MAP_COUNTRIES = 40

const appEl = document.getElementById('app')

if (!appEl) {
  throw new Error('Missing #app root')
}

const state: AppState = {
  mode: 'booting',
  results: null,
  runStatus: null,
  selectedCountryCode: null,
  selectedCountry: null,
  errorMessage: null,
  detailError: null,
  detailLoading: false,
  isLaunching: false
}

let detailRequestVersion = 0

void init()

async function init(): Promise<void> {
  state.mode = state.results ? 'loading' : 'booting'
  state.errorMessage = null
  render()

  try {
    const results = await api.getLatestResults()
    await presentResults(results, { keepSelection: false, revealSelection: false })
  } catch (error) {
    const message = String(error)
    if (message.includes('no pipeline results found') || message.includes('pipeline results not found')) {
      state.mode = 'empty'
      state.errorMessage = null
      render()
      return
    }
    state.mode = 'error'
    state.errorMessage = message
    render()
  }
}

async function launchRun(): Promise<void> {
  if (state.isLaunching) return
  state.isLaunching = true
  state.mode = 'loading'
  state.errorMessage = null
  render()

  try {
    const created = await api.createPipelineRun(`demo-${Date.now()}`)
    await pollRun(created.pipeline_run_id)
  } catch (error) {
    state.mode = 'error'
    state.errorMessage = String(error)
    state.isLaunching = false
    render()
  }
}

async function pollRun(pipelineRunId: number): Promise<void> {
  while (true) {
    let runStatus: PipelineRunStatusResponse
    try {
      runStatus = await api.getPipelineRun(pipelineRunId)
    } catch (error) {
      if (isTransientRunStatusError(error)) {
        await sleep(1200)
        continue
      }
      throw error
    }
    state.runStatus = runStatus
    render()

    if (runStatus.status === 'completed') {
      const results = await api.getResults(pipelineRunId)
      await presentResults(results, { keepSelection: false, revealSelection: false })
      state.isLaunching = false
      return
    }

    if (runStatus.status === 'failed') {
      state.mode = 'error'
      state.isLaunching = false
      state.errorMessage = runStatus.error_summary || 'Pipeline run failed.'
      render()
      return
    }

    await sleep(1400)
  }
}

async function presentResults(
  results: PipelineCountryResultsResponse,
  options: { keepSelection: boolean; revealSelection: boolean }
): Promise<void> {
  const nextSelection =
    options.keepSelection && state.selectedCountryCode && results.countries.some((row) => row.country_code === state.selectedCountryCode)
      ? state.selectedCountryCode
      : results.countries[0]?.country_code || null

  state.results = results
  state.mode = 'ready'
  state.errorMessage = null
  state.selectedCountryCode = nextSelection
  state.selectedCountry = null
  state.detailError = null
  state.detailLoading = Boolean(nextSelection)
  render()

  await hydrateRunStatus(results.pipeline_run_id)

  if (nextSelection) {
    await selectCountry(results.pipeline_run_id, nextSelection, { revealSelection: options.revealSelection })
  }
}

async function hydrateRunStatus(pipelineRunId: number): Promise<void> {
  try {
    state.runStatus = await api.getPipelineRun(pipelineRunId)
    render()
  } catch {
    // The dashboard still works with results only; stage telemetry is additive.
  }
}

async function selectCountry(
  pipelineRunId: number,
  countryCode: string,
  options: { revealSelection: boolean }
): Promise<void> {
  detailRequestVersion += 1
  const requestVersion = detailRequestVersion
  state.selectedCountryCode = countryCode
  state.selectedCountry = null
  state.detailError = null
  state.detailLoading = true
  render()

  if (options.revealSelection) {
    revealSelectedCountryPanel()
  }

  try {
    const detail = await api.getCountryDetail(pipelineRunId, countryCode)
    if (requestVersion !== detailRequestVersion) return
    state.selectedCountry = detail.country
    state.detailLoading = false
    state.detailError = null
    render()
  } catch (error) {
    if (requestVersion !== detailRequestVersion) return
    state.detailLoading = false
    state.detailError = String(error)
    render()
  }
}

function isTransientRunStatusError(error: unknown): boolean {
  const message = String(error).toLowerCase()
  return message.includes('database busy') || message.includes('database is locked')
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

function countryName(countryCode: string): string {
  return COUNTRY_LABELS[countryCode] || countryCode
}

function formatScore(score: number): string {
  return `${Math.round(score * 100)}`
}

function formatBand(band: RiskBand): string {
  if (band === 'critical') return 'Critical'
  if (band === 'high') return 'High'
  if (band === 'medium') return 'Medium'
  return 'Low'
}

function formatFactorName(value: string): string {
  return value
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

function formatTimestamp(value: string | null): string {
  if (!value) return 'in progress'
  return new Date(value).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit'
  })
}

function formatMetric(value: number | null): string {
  if (value == null || Number.isNaN(value)) return '-'
  const abs = Math.abs(value)
  if (abs >= 1000) {
    return value.toLocaleString(undefined, { maximumFractionDigits: 0 })
  }
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 })
}

function riskClass(band: RiskBand): string {
  return `risk-${band}`
}

function selectedRow(results: PipelineCountryResultsResponse | null): CountryRiskRow | null {
  if (!results) return null
  if (state.selectedCountryCode) {
    const match = results.countries.find((row) => row.country_code === state.selectedCountryCode)
    if (match) return match
  }
  return results.countries[0] || null
}

function selectedRank(results: PipelineCountryResultsResponse | null, countryCode: string | null): number | null {
  if (!results || !countryCode) return null
  const index = results.countries.findIndex((row) => row.country_code === countryCode)
  return index >= 0 ? index + 1 : null
}

function visibleMapCountries(results: PipelineCountryResultsResponse): CountryRiskRow[] {
  return results.countries.filter((row) => hasCountryPoint(row.country_code)).slice(0, MAX_MAP_COUNTRIES)
}

function isCountryVisibleOnMap(results: PipelineCountryResultsResponse | null, countryCode: string | null): boolean {
  if (!results || !countryCode) return false
  return visibleMapCountries(results).some((row) => row.country_code === countryCode)
}

function buildFocusContext(
  row: CountryRiskRow,
  rank: number | null,
  leader: CountryRiskRow,
  totalCountries: number,
  selectedOnMap: boolean
): string {
  if (row.country_code === leader.country_code) {
    return `Rank #1 of ${totalCountries}. This is the current run leader and it is pinned on the map.`
  }

  const mapNote = selectedOnMap
    ? 'It is also visible on the top-risk map.'
    : `It sits outside the top ${MAX_MAP_COUNTRIES} map cut, but the inspector still updates.`

  return `Rank #${rank ?? '?'} of ${totalCountries}. The run leader is ${countryName(leader.country_code)}. ${mapNote}`
}

function buildDetailNarrative(
  country: CountryRiskDetail,
  rank: number | null,
  leader: CountryRiskRow,
  totalCountries: number
): string {
  const signals = country.top_contributors
    .slice(0, 3)
    .map((item) => item.indicator_label || item.indicator_code)
    .filter(Boolean)
    .join(', ')

  if (country.country_code === leader.country_code) {
    return `This country currently leads the run. The biggest pressure comes from ${signals || 'the available WHO indicators'}.`
  }

  return `This country ranks #${rank ?? '?'} of ${totalCountries}. The run leader is ${countryName(leader.country_code)}, while this profile is being pushed by ${signals || 'the available WHO indicators'}.`
}

function render(): void {
  appEl!.innerHTML = renderApp()
  bindEvents()
}

function renderApp(): string {
  if (state.mode === 'booting' || state.mode === 'loading') {
    return renderLoading()
  }
  if (state.mode === 'empty') {
    return renderEmpty()
  }
  if (state.mode === 'error') {
    return renderError()
  }
  return renderDashboard()
}

function renderLoading(): string {
  const stages = state.runStatus?.stage_runs || []
  return `
    <div class="page-shell">
      <section class="hero panel">
        <span class="eyebrow">Pipeline running</span>
        <h1>Building the WHO risk ranking.</h1>
        <p class="muted">The app is ingesting WHO indicators, shaping country observations, and preparing ranked outputs.</p>
        <div class="hero-actions">
          <button class="button button-primary" type="button" disabled>Run in progress</button>
        </div>
      </section>
      <section class="panel stage-panel">
        <div class="section-head">
          <div>
            <p class="section-kicker">Live status</p>
            <h2>Pipeline stages</h2>
          </div>
          <p class="muted mono">${state.runStatus ? `run ${state.runStatus.pipeline_run_id}` : 'waiting for first response'}</p>
        </div>
        <div class="stage-grid">
          ${stages.length ? stages.map(renderStageCard).join('') : '<div class="empty-state">Waiting for stage updates...</div>'}
        </div>
      </section>
    </div>
  `
}

function renderEmpty(): string {
  return `
    <div class="page-shell">
      <section class="hero panel">
        <span class="eyebrow">WHO-first outbreak ranking</span>
        <h1>Run the pipeline to generate the first country risk dashboard.</h1>
        <p class="muted">This MVP ranks countries by disease burden, surveillance readiness, and confidence, then shows exactly what drove the score.</p>
        <div class="hero-actions">
          <button id="launch-run" class="button button-primary" type="button">Run WHO pipeline</button>
          <a class="button button-secondary" href="${api.apiBase}/docs" target="_blank" rel="noreferrer">Open API docs</a>
        </div>
      </section>
    </div>
  `
}

function renderError(): string {
  return `
    <div class="page-shell">
      <section class="hero panel">
        <span class="eyebrow">Run issue</span>
        <h1>The app could not load usable country results.</h1>
        <p class="muted">${escapeHtml(state.errorMessage || 'Unknown error')}</p>
        <div class="hero-actions">
          <button id="launch-run" class="button button-primary" type="button">Retry with fresh run</button>
          <button id="reload-latest" class="button button-secondary" type="button">Reload latest results</button>
        </div>
      </section>
    </div>
  `
}

function renderDashboard(): string {
  const results = state.results
  if (!results) return renderEmpty()

  const focusRow = selectedRow(results)
  if (!focusRow) return renderEmpty()

  const focusRank = selectedRank(results, focusRow.country_code)
  const leader = results.countries[0]
  const selectedOnMap = isCountryVisibleOnMap(results, focusRow.country_code)

  return `
    <div class="page-shell">
      <section class="hero panel">
        <div class="hero-grid">
          <div class="hero-copy">
            <span class="eyebrow">WHO-first dashboard</span>
            <h1>See where to look first, then inspect why.</h1>
            <p class="muted">
              The map highlights the highest-risk countries. The table and inspector stay in sync so every click answers one question: why does this country rank here?
            </p>
            <div class="hero-actions">
              <button id="launch-run" class="button button-primary" type="button">${state.isLaunching ? 'Running...' : 'Run fresh pipeline'}</button>
              <button id="reload-latest" class="button button-secondary" type="button">Reload latest results</button>
            </div>
          </div>
          <div class="hero-metrics">
            <div class="stat-card">
              <span class="stat-label">Run ID</span>
              <strong class="stat-value mono">${results.pipeline_run_id}</strong>
            </div>
            <div class="stat-card">
              <span class="stat-label">Countries ranked</span>
              <strong class="stat-value">${results.countries_ranked}</strong>
            </div>
            <div class="stat-card">
              <span class="stat-label">Finished</span>
              <strong class="stat-value hero-small">${escapeHtml(formatTimestamp(results.finished_at))}</strong>
            </div>
            <div class="stat-card">
              <span class="stat-label">Model</span>
              <strong class="stat-value hero-small mono">${escapeHtml(results.model_version || 'unknown')}</strong>
            </div>
          </div>
        </div>
      </section>

      <section class="overview-grid">
        <article class="panel map-panel">
          <div class="section-head">
            <div>
              <p class="section-kicker">Geographic view</p>
              <h2>Highest-risk map</h2>
            </div>
            <p class="muted">Showing the top ${MAX_MAP_COUNTRIES} ranked countries with reliable map positions.</p>
          </div>
          <div class="map-status-row">
            <div class="status-card">
              <span class="status-label">Run leader</span>
              <strong>${escapeHtml(countryName(leader.country_code))}</strong>
              <span class="muted mono">#1 · ${formatBand(leader.risk_band)}</span>
            </div>
            <div class="status-card ${selectedOnMap ? 'active' : 'quiet'}">
              <span class="status-label">Focus</span>
              <strong>${escapeHtml(countryName(focusRow.country_code))}</strong>
              <span class="muted mono">${focusRank ? `#${focusRank}` : 'not ranked'}${selectedOnMap ? ' · on map' : ' · off map'}</span>
            </div>
          </div>
          <div class="map-legend">
            <span class="risk-pill risk-high">High risk</span>
            <span class="risk-pill risk-medium">Medium risk</span>
            <span class="risk-pill risk-low">Low risk</span>
            <span class="legend-note">Numbers inside markers match the rank table.</span>
          </div>
          <div class="world-map">
            ${renderWorldBackdrop()}
            <div class="world-grid"></div>
            <div class="map-region-label map-region-americas">Americas</div>
            <div class="map-region-label map-region-emea">Europe + Africa</div>
            <div class="map-region-label map-region-apac">Asia + Pacific</div>
            ${visibleMapCountries(results).map((row, index) => renderMapMarker(row, index + 1)).join('')}
          </div>
          <p class="map-note">
            ${
              selectedOnMap
                ? `${escapeHtml(countryName(focusRow.country_code))} is highlighted on the map and in the table.`
                : `${escapeHtml(countryName(focusRow.country_code))} is below the top-${MAX_MAP_COUNTRIES} map cut, so the inspector updates without adding a fake marker.`
            }
          </p>
        </article>

        <article class="panel focus-panel">
          ${renderFocusPanel(focusRow, focusRank, leader, results.countries_ranked, selectedOnMap)}
        </article>
      </section>

      <section class="panel detail-panel" data-detail-panel>
        ${renderSelectedCountryPanel(focusRow, focusRank, leader, results.countries_ranked)}
      </section>

      <section class="panel ranking-panel">
        <div class="section-head">
          <div>
            <p class="section-kicker">Ranked comparison</p>
            <h2>Country risk table</h2>
          </div>
          <p class="muted">Click any row to move the same focus country used by the map and the inspector.</p>
        </div>
        <div class="table-header">
          <span>Rank</span>
          <span>Country</span>
          <span>Band</span>
          <span>Risk</span>
          <span>Confidence</span>
          <span>Lead signal</span>
        </div>
        <div class="table-shell">
          ${results.countries.map((row, index) => renderRankingRow(row, index + 1)).join('')}
        </div>
      </section>

      <section class="panel stage-panel">
        <div class="section-head">
          <div>
            <p class="section-kicker">Run telemetry</p>
            <h2>Stage status</h2>
          </div>
          <p class="muted mono">status ${escapeHtml(results.status)}</p>
        </div>
        <div class="stage-grid">
          ${(state.runStatus?.stage_runs || []).map(renderStageCard).join('') || '<div class="empty-state">Stage telemetry is unavailable for this run.</div>'}
        </div>
      </section>
    </div>
  `
}

function renderFocusPanel(
  row: CountryRiskRow,
  rank: number | null,
  leader: CountryRiskRow,
  totalCountries: number,
  selectedOnMap: boolean
): string {
  const topContributors = row.top_contributors.slice(0, 3)

  return `
    <div class="section-head">
      <div>
        <p class="section-kicker">Focus country</p>
        <h2>${escapeHtml(countryName(row.country_code))}</h2>
        <p class="muted mono">${escapeHtml(row.country_code)}${rank ? ` · rank #${rank} of ${totalCountries}` : ''}</p>
      </div>
      <div class="focus-score-block">
        <span class="risk-pill ${riskClass(row.risk_band)}">${formatBand(row.risk_band)}</span>
        <strong class="detail-score">${formatScore(row.risk_score)}</strong>
      </div>
    </div>
    <p class="focus-context">${escapeHtml(buildFocusContext(row, rank, leader, totalCountries, selectedOnMap))}</p>
    <div class="focus-metric-grid">
      <div class="stat-card compact">
        <span class="stat-label">Risk score</span>
        <strong class="stat-value">${formatScore(row.risk_score)}</strong>
      </div>
      <div class="stat-card compact">
        <span class="stat-label">Disease burden</span>
        <strong class="stat-value">${formatScore(row.disease_burden_score)}</strong>
      </div>
      <div class="stat-card compact">
        <span class="stat-label">Readiness gap</span>
        <strong class="stat-value">${formatScore(row.surveillance_readiness_score)}</strong>
      </div>
      <div class="stat-card compact">
        <span class="stat-label">Confidence</span>
        <strong class="stat-value">${formatScore(row.confidence_score)}</strong>
      </div>
    </div>
    <div class="detail-card">
      <span class="status-label">Strongest signals</span>
      <div class="signal-pill-row">
        ${topContributors.length ? topContributors.map(renderSignalPill).join('') : '<span class="muted">No signal evidence available.</span>'}
      </div>
    </div>
  `
}

function renderWorldBackdrop(): string {
  return `
    <svg class="world-backdrop" viewBox="0 0 1000 520" preserveAspectRatio="none" aria-hidden="true">
      <path d="M83 128c38-31 98-45 157-33 52 10 85 35 106 64 11 15 6 31-12 39-35 17-61 33-73 58-9 18-28 22-45 10-26-19-51-18-77-2-27 16-70 13-101-10-28-20-43-47-35-68 10-25 30-42 80-58Z" />
      <path d="M268 268c25-8 55 4 74 27 19 23 20 45 5 61-13 13-19 31-17 52 2 22-8 39-25 44-19 6-38-8-46-36-8-25-22-45-42-61-21-16-24-37-8-57 13-16 30-24 59-30Z" />
      <path d="M438 135c39-20 84-18 122 5 19 12 37 15 54 10 29-9 62 0 81 21 14 15 12 31-4 46-18 16-26 37-24 63 3 34-8 61-29 72-24 13-54 5-80-22-18-18-32-41-41-68-7-21-24-35-51-42-34-9-54-24-61-45-8-24 4-40 33-52Z" />
      <path d="M596 116c56-25 124-29 182-9 43 14 80 41 100 73 10 16 5 32-14 42-29 16-53 34-70 55-17 21-43 28-66 18-30-13-59-15-87-6-30 10-63 1-90-25-22-22-41-31-58-28-27 4-49-11-49-33 0-27 16-48 45-58 19-7 61-20 107-29Z" />
      <path d="M824 372c20-15 50-23 78-19 24 4 45 17 57 35 10 16 7 31-8 41-15 10-26 24-33 43-7 17-20 24-38 21-19-3-32-16-39-36-7-18-23-32-47-42-18-7-22-21-12-41 8-15 20-27 42-36Z" />
    </svg>
  `
}

function renderSelectedCountryPanel(
  row: CountryRiskRow,
  rank: number | null,
  leader: CountryRiskRow,
  totalCountries: number
): string {
  if (state.detailLoading) {
    return `
      <div class="section-head">
        <div>
          <p class="section-kicker">Country detail</p>
          <h2>${escapeHtml(countryName(row.country_code))}</h2>
          <p class="muted mono">${escapeHtml(row.country_code)}${rank ? ` · rank #${rank} of ${totalCountries}` : ''}</p>
        </div>
        <div class="focus-score-block">
          <span class="risk-pill ${riskClass(row.risk_band)}">${formatBand(row.risk_band)}</span>
          <strong class="detail-score">${formatScore(row.risk_score)}</strong>
        </div>
      </div>
      <p class="detail-intro">${escapeHtml(buildFocusContext(row, rank, leader, totalCountries, isCountryVisibleOnMap(state.results, row.country_code)))}</p>
      <div class="empty-state">Loading the factor breakdown and indicator evidence for this country.</div>
    `
  }

  if (state.detailError || !state.selectedCountry) {
    return `
      <div class="section-head">
        <div>
          <p class="section-kicker">Country detail</p>
          <h2>${escapeHtml(countryName(row.country_code))}</h2>
          <p class="muted mono">${escapeHtml(row.country_code)}${rank ? ` · rank #${rank} of ${totalCountries}` : ''}</p>
        </div>
        <div class="focus-score-block">
          <span class="risk-pill ${riskClass(row.risk_band)}">${formatBand(row.risk_band)}</span>
          <strong class="detail-score">${formatScore(row.risk_score)}</strong>
        </div>
      </div>
      <p class="detail-intro">${escapeHtml(buildFocusContext(row, rank, leader, totalCountries, isCountryVisibleOnMap(state.results, row.country_code)))}</p>
      <div class="empty-state">${escapeHtml(state.detailError || 'Country detail is unavailable for this selection.')}</div>
    `
  }

  return renderCountryDetail(state.selectedCountry, rank, leader, totalCountries)
}

function renderStageCard(stage: PipelineRunStatusResponse['stage_runs'][number]): string {
  const statusClass = stage.status === 'completed' ? 'ok' : stage.status === 'running' ? 'active' : 'warn'
  return `
    <div class="stage-card ${statusClass}">
      <div class="stage-top">
        <strong>${escapeHtml(stage.stage_name)}</strong>
        <span class="stage-badge">${escapeHtml(stage.status)}</span>
      </div>
      <p class="muted mono">${stage.finished_at ? formatTimestamp(stage.finished_at) : 'in progress'}</p>
      ${
        stage.metrics
          ? `<pre class="stage-metrics">${escapeHtml(JSON.stringify(stage.metrics, null, 2))}</pre>`
          : '<p class="muted">No metrics yet.</p>'
      }
    </div>
  `
}

function renderMapMarker(row: CountryRiskRow, rank: number): string {
  const point = getApproximatePoint(row.country_code)
  const selected = state.selectedCountryCode === row.country_code
  const size = selected ? 34 : rank <= 5 ? 28 : 16 + Math.round(row.risk_score * 18)
  const label = selected ? countryName(row.country_code) : rank <= 6 ? `${row.country_code} · #${rank}` : row.country_code

  return `
    <button
      class="map-marker ${riskClass(row.risk_band)} ${selected ? 'selected' : ''} ${rank === 1 ? 'leader' : ''}"
      data-country-select="${row.country_code}"
      type="button"
      style="left:${point.x}%; top:${point.y}%; width:${size}px; height:${size}px;"
      title="${escapeHtml(countryName(row.country_code))}"
      aria-label="Select ${escapeHtml(countryName(row.country_code))}"
    >
      ${rank <= 9 ? `<span class="marker-rank">${rank}</span>` : ''}
      <span class="map-label" style="transform: translate(-50%, ${selected ? 22 : 18}px);">${escapeHtml(label)}</span>
    </button>
  `
}

function renderRankingRow(row: CountryRiskRow, rank: number): string {
  const topContributor = row.top_contributors[0]
  return `
    <button class="ranking-row ${state.selectedCountryCode === row.country_code ? 'selected' : ''}" data-country-select="${row.country_code}" type="button">
      <div class="ranking-rank">${rank}</div>
      <div class="ranking-country">
        <strong>${escapeHtml(countryName(row.country_code))}</strong>
        <span class="muted mono">${escapeHtml(row.country_code)}</span>
      </div>
      <div class="ranking-band"><span class="risk-pill ${riskClass(row.risk_band)}">${formatBand(row.risk_band)}</span></div>
      <div class="ranking-score">
        <strong>${formatScore(row.risk_score)}</strong>
        <span class="muted">risk</span>
      </div>
      <div class="ranking-score">
        <strong>${formatScore(row.confidence_score)}</strong>
        <span class="muted">confidence</span>
      </div>
      <div class="ranking-factor">
        <strong>${topContributor ? escapeHtml(topContributor.indicator_label || topContributor.indicator_code) : 'No contributor'}</strong>
        <span class="muted">${topContributor ? escapeHtml(formatFactorName(topContributor.factor_group)) : 'No factor group'}</span>
      </div>
    </button>
  `
}

function renderCountryDetail(
  country: CountryRiskDetail,
  rank: number | null,
  leader: CountryRiskRow,
  totalCountries: number
): string {
  const factorCards = [
    {
      label: 'Disease burden',
      score: country.disease_burden_score,
      note: `${country.factors.disease_burden?.indicator_count ?? 0} indicators used`
    },
    {
      label: 'Readiness gap',
      score: country.surveillance_readiness_score,
      note: `${country.factors.surveillance_readiness?.indicator_count ?? 0} indicators used`
    },
    {
      label: 'Confidence',
      score: country.confidence_score,
      note: `Coverage ${Math.round((country.factors.confidence?.indicator_coverage ?? 0) * 100)}`
    }
  ]

  return `
    <div class="section-head">
      <div>
        <p class="section-kicker">Country detail</p>
        <h2>${escapeHtml(countryName(country.country_code))}</h2>
        <p class="muted mono">${escapeHtml(country.country_code)}${rank ? ` · rank #${rank} of ${totalCountries}` : ''}</p>
      </div>
      <div class="focus-score-block">
        <span class="risk-pill ${riskClass(country.risk_band)}">${formatBand(country.risk_band)}</span>
        <strong class="detail-score">${formatScore(country.risk_score)}</strong>
      </div>
    </div>
    <p class="detail-intro">${escapeHtml(buildDetailNarrative(country, rank, leader, totalCountries))}</p>
    <div class="signal-pill-row detail-signals">
      ${country.top_contributors.slice(0, 3).map(renderSignalPill).join('')}
    </div>
    <div class="factor-grid">
      ${factorCards
        .map(
          (factor) => `
            <div class="factor-card">
              <span class="stat-label">${escapeHtml(factor.label)}</span>
              <strong class="factor-score">${formatScore(factor.score)}</strong>
              <div class="factor-bar"><span style="width:${Math.round(factor.score * 100)}%"></span></div>
              <span class="muted">${escapeHtml(factor.note)}</span>
            </div>
          `
        )
        .join('')}
    </div>
    <div class="detail-columns">
      <div class="detail-card">
        <h3>Top drivers</h3>
        <div class="detail-list">
          ${country.top_contributors.map(renderContributor).join('')}
        </div>
      </div>
      <div class="detail-card">
        <h3>Indicator evidence</h3>
        <div class="detail-list detail-list-scroll">
          ${country.indicator_details.map(renderContributor).join('')}
        </div>
      </div>
    </div>
  `
}

function renderSignalPill(item: Contributor): string {
  return `<span class="signal-pill">${escapeHtml(item.indicator_label || item.indicator_code)}</span>`
}

function renderContributor(item: Contributor): string {
  const meta = [
    formatFactorName(item.factor_group),
    item.source_date ? `Source ${formatTimestamp(item.source_date)}` : null
  ]
    .filter(Boolean)
    .join(' · ')

  return `
    <div class="contributor-row">
      <div class="contributor-copy">
        <strong>${escapeHtml(item.indicator_label || item.indicator_code)}</strong>
        <p class="muted contributor-meta">${escapeHtml(meta)}</p>
      </div>
      <div class="contributor-metrics">
        <span class="mono">raw ${formatMetric(item.raw_value)}</span>
        <span class="mono">impact ${formatMetric(item.contribution_score)}</span>
      </div>
    </div>
  `
}

function bindEvents(): void {
  document.getElementById('launch-run')?.addEventListener('click', () => {
    void launchRun()
  })
  document.getElementById('reload-latest')?.addEventListener('click', () => {
    void init()
  })
  document.querySelectorAll<HTMLElement>('[data-country-select]').forEach((element) => {
    element.addEventListener('click', () => {
      const countryCode = element.dataset.countrySelect
      if (!countryCode || !state.results) return
      void selectCountry(state.results.pipeline_run_id, countryCode, { revealSelection: true })
    })
  })
}

function revealSelectedCountryPanel(): void {
  const panel = document.querySelector<HTMLElement>('[data-detail-panel]')
  if (!panel) return
  panel.classList.remove('flash')
  void panel.offsetWidth
  panel.classList.add('flash')
  if (window.innerWidth <= 1100) {
    panel.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
  window.setTimeout(() => {
    panel.classList.remove('flash')
  }, 900)
}

function escapeHtml(value: string): string {
  return value
    .split('&').join('&amp;')
    .split('<').join('&lt;')
    .split('>').join('&gt;')
    .split('"').join('&quot;')
    .split("'").join('&#039;')
}
