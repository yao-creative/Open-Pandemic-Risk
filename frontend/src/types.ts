export type RiskBand = 'low' | 'medium' | 'high' | 'critical'

export type Contributor = {
  indicator_code: string
  indicator_label: string | null
  factor_group: string
  risk_direction: string | null
  raw_value: number | null
  normalized_risk: number | null
  contribution_score: number | null
  period_date: string | null
  source_date: string | null
}

export type FactorScore = {
  score: number
  indicator_count?: number | null
  expected_indicator_count?: number | null
  indicator_coverage?: number | null
  freshness_score?: number | null
  uncertainty_quality?: number | null
}

export type CountryRiskRow = {
  country_code: string
  risk_score: number
  risk_band: RiskBand
  disease_burden_score: number
  surveillance_readiness_score: number
  confidence_score: number
  top_contributors: Contributor[]
}

export type CountryRiskDetail = {
  country_code: string
  risk_score: number
  risk_band: RiskBand
  disease_burden_score: number
  surveillance_readiness_score: number
  confidence_score: number
  factors: Record<string, FactorScore>
  top_contributors: Contributor[]
  indicator_details: Contributor[]
  model_version: string
}

export type PipelineCountryResultsResponse = {
  pipeline_run_id: number
  pipeline_name: string
  status: string
  finished_at: string | null
  countries_ranked: number
  model_version: string | null
  countries: CountryRiskRow[]
}

export type PipelineCountryDetailResponse = {
  pipeline_run_id: number
  pipeline_name: string
  status: string
  finished_at: string | null
  country: CountryRiskDetail
}

export type PipelineStageRun = {
  id: number
  stage_name: string
  status: string
  started_at: string
  finished_at: string | null
  metrics?: Record<string, unknown> | null
  artifacts?: Record<string, unknown> | null
  error_summary?: string | null
}

export type PipelineRunStatusResponse = {
  pipeline_run_id: number
  pipeline_name: string
  status: string
  started_at: string
  finished_at: string | null
  error_summary: string | null
  artifacts: Record<string, unknown>
  stage_runs: PipelineStageRun[]
}

export type PipelineRunCreateResponse = {
  pipeline_run_id: number
  status: string
  stage_order: string[]
}
