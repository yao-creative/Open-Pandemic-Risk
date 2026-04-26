# Hackathon MVP Contract

This file is the source of truth for the hackathon MVP.

If this file conflicts with [Architecture.md](C:/Users/wbrya/OneDrive/Documents/GitHub/biohack-2026-april/Architecture.md), this file wins for demo scope and product framing.

`Architecture.md` contains historical architecture exploration.
This file contains the focused build.

## 1. Product Sentence

The product ranks countries by outbreak risk using WHO data, then shows exactly why each country is ranked where it is.

## 2. Primary User

Primary user:

- `public health analyst`

Secondary users:

- NGO / global health coordinator
- government response / policy analyst

## 3. What Judges Should See

The first screen should prove three things in under 10 seconds:

1. the system ranks countries
2. the ranking is explainable
3. the output feels actionable

Recommended main screen:

- split view
- left: world map with country risk coloring
- right: ranked country table

Recommended second screen:

- country detail panel
- top factors: `disease_burden`, `surveillance_readiness`, `confidence`
- supporting indicators and evidence

## 4. Core Job To Be Done

Help a public health analyst answer:

- where should I look first?
- why does this country matter?
- how much should I trust this ranking?

## 5. MVP Inputs

The MVP input is not "all outbreak data."
The MVP input is a narrow, defensible WHO-first dataset.

### Data inputs

- WHO indicator catalog
- WHO dimension catalog
- WHO dimension value catalog
- WHO observation rows for a selected set of indicators

### Selected factor groups

- `disease_burden`
- `surveillance_readiness`
- `confidence`

### Example indicator families

- burden:
  - TB
  - malaria
  - measles
  - cholera
- readiness:
  - IHR
  - SPAR
- confidence:
  - observation completeness
  - uncertainty width
  - source freshness

## 6. MVP Output

The MVP output is:

- a ranked list of countries
- one row per country
- one overall risk score per country
- one risk band per country
- one explainability payload per country

The output is not:

- a conversational chatbot
- a narrative outbreak feed
- a generalized global health data portal

## 7. Standard Vocabulary

Use these names consistently.

### `indicator`

A WHO metric being measured.

Examples:

- TB incidence
- measles reported cases
- IHR readiness score

### `dimension`

A slice used to break an indicator into rows.

Examples:

- country
- year
- sex
- region

### `dimension value`

A coded value inside a dimension.

Examples:

- `USA`
- `SEX_MLE`
- `EMR`

### `observation`

One WHO data row for one indicator at one slice.

Example:

- TB incidence for USA in 2024

### `grain`

The level of detail of a row or table.

Example:

- `who_observation` grain:
  - one `indicator_code`
  - one location
  - one time bucket
  - one combination of optional dims

Do not use `grain` to mean "dimension."
They are different.

### `pipeline_run`

One execution of the ingest -> score pipeline.

### `country_risk_result`

The final scored country output shown in the UI.

Use this instead of vague terms like:

- signal
- alert
- risk thing

### `factor`

A top-level scoring component used in the explanation layer.

The MVP factors are:

- `disease_burden`
- `surveillance_readiness`
- `confidence`

## 8. Standard Table Names

These are the canonical internal tables for the WHO-first MVP.

### `who_indicator`

One row per WHO indicator.

### `who_dimension`

One row per WHO dimension type.

### `who_dimension_value`

One row per WHO dimension value.

Primary key should be:

- `(dimension_code, value_code)`

Not just `value_code`.

### `who_indicator_dimension`

One row per allowed indicator-dimension relationship.

### `who_observation`

The canonical fact table for WHO observations.

### `country_risk_result`

One row per scored country per run.

### `pipeline_run`

One row per pipeline execution.

## 9. Standard Join Keys

Use these joins.

### Observation -> Indicator

- `who_observation.indicator_code`
- `who_indicator.indicator_code`

### Observation -> Spatial dimension value

- `who_observation.spatial_dim_type`
- `who_observation.spatial_dim_code`
- `who_dimension_value.dimension_code`
- `who_dimension_value.value_code`

### Observation -> Optional dim values

For `dim1`, `dim2`, `dim3`, and `datasource_dim`, always join using:

- dimension type/code pair
- value code

Never assume:

- `dim1` always means sex
- `dim2` always means age
- `dim3` always means region

### Indicator -> Allowed dimensions

- `who_indicator.indicator_code`
- `who_indicator_dimension.indicator_code`

## 10. How To Determine Which Dimensions To Use

Use this sequence every time.

1. Start with the user-facing question
2. Pick the indicator
3. Check `who_indicator_dimension`
4. Keep only the dimensions required for the MVP use case
5. Preserve the raw row JSON anyway

Rule:

- product question first
- indicator second
- dimensions third

Not the other way around.

Example:

If the user question is:

- which countries should I look at first?

Then the minimum important dimensions are usually:

- location
- time

If the question is:

- how does burden differ by sex?

Then sex becomes necessary.

## 11. Scoring Contract

The MVP score should answer:

- how severe is the burden?
- how weak is readiness?
- how trustworthy is the evidence?

### Factor definitions

#### `disease_burden`

How concerning the underlying health indicators are.

#### `surveillance_readiness`

How capable the country appears at detection and response.

#### `confidence`

How much trust we should place in the ranking given the observed data.

### Plain-English ranking logic

A country ranks higher when:

- burden is worse
- readiness is weaker
- confidence is high enough that we trust the ranking

### Explainability contract

Every `country_risk_result` should include:

- `risk_score`
- `risk_band`
- `top_factors`
- `factor_values`
- `factor_explanations`
- `model_version`
- `pipeline_run_id`

## 12. UI Contract

### Main screen

- map + ranked table

The table should show:

- country name
- risk band
- risk score
- top 3 factors

The map should show:

- same country-level ranking encoded visually

### Country detail screen

Should show:

- country name
- overall score and band
- burden, readiness, confidence breakdown
- supporting indicators
- supporting evidence / metadata

## 13. Enums To Define

### `RiskBand`

- `low`
- `medium`
- `high`
- `critical`

### `PipelineStageName`

- `ingest_who`
- `score_country_risk`

Optional later:

- `enrich_with_exa`

### `PipelineStageStatus`

- `queued`
- `running`
- `ok`
- `partial`
- `error`
- `skipped`

### `FactorName`

- `disease_burden`
- `surveillance_readiness`
- `confidence`

## 14. Configs To Define

### `indicators.yml`

Purpose:

- list the exact WHO indicators included in the MVP

Fields:

- `indicator_code`
- `factor_name`
- `enabled`
- `expected_dimensions`
- `notes`

### `scoring.yml`

Purpose:

- define the scoring behavior

Fields:

- `model_version`
- `factor_weights`
- `risk_band_thresholds`
- `uncertainty_penalty_enabled`
- `completeness_penalty_enabled`

### `app_config`

Fields:

- `who_base_url`
- `request_timeout_seconds`
- `country_limit`
- `indicator_limit`

## 15. Explicit Non-Goals

Not in scope for the focused hackathon MVP:

- ProMED-first event extraction
- generic chat interface
- full analyst workflow tooling
- generalized outbreak alerting engine
- production async orchestration
- large-scale historical backfill

## 16. Demo Script

The demo should feel like this:

1. open dashboard
2. see top-ranked countries immediately
3. click one country
4. see exactly why it ranked high
5. show the supporting WHO-based factors

The story is:

"This helps a public health analyst decide where to look first, and why."

## 17. Open Decisions To Lock Next

1. exact indicator list
2. exact factor weighting
3. whether Exa is in the demo path or only supporting material

## 18. Related Docs

- Historical architecture: [Architecture.md](C:/Users/wbrya/OneDrive/Documents/GitHub/biohack-2026-april/Architecture.md)
- WHO operating model: [OPERATING_MODEL.md](C:/Users/wbrya/OneDrive/Documents/GitHub/biohack-2026-april/research/who_gho_odata/OPERATING_MODEL.md)
- WHO notebook: [who_gho_odata_usage.ipynb](C:/Users/wbrya/OneDrive/Documents/GitHub/biohack-2026-april/research/who_gho_odata/who_gho_odata_usage.ipynb)
