# WHO GHO Operating Model

This file is the plain-English operating model for the WHO-first AIX hackathon project.

It answers:

- what the project is actually building
- how WHO GHO data is shaped
- how to decide which dimensions matter
- what "canonical", "join key", and "typed projection" mean
- what tables, enums, and configs should exist
- what is still unclear and needs a decision

## 1. Project, ELI5

The team is building two things at once:

1. An app/prototype
2. A submission package

The app/prototype is:

- ingest structured WHO health indicators
- optionally enrich with Exa research context
- compute a simple risk score
- expose run results for a UI, agent, or report

The submission package is:

- PDF report
- title + abstract
- author list
- optional GitHub repo
- optional video demo

The PDF is not the whole project.
The PDF is the final explanation of the app.

## 2. Data Model, ELI5

Think of WHO GHO like a big warehouse of measurements.

- An `indicator` is the thing being measured.
  Examples: TB incidence, measles reported cases, cholera deaths.
- A `dimension` is how that measurement is sliced.
  Examples: country, year, sex, region.
- An `observation` is one row of data for one indicator at one specific slice.

Example:

- indicator: `MDG_0000000020`
- meaning: TB incidence per 100,000
- dimensions: country + year
- row: `USA`, `2024`, `3.2`

That one row is an observation.

## 3. Key Terms

### Canonical

`Canonical` means: the standard internal shape we choose and use everywhere.

Not the raw WHO shape.
Not whatever one endpoint happens to return.
Not whatever a teammate casually names it.

It is the normalized project-wide source of truth.

Example:

- raw WHO may say `SpatialDim`
- internal canonical column may be `country_code`

Canonical means we pick one stable internal name and keep it consistent.

### Join key

A `join key` is the field used to connect one table to another.

Examples:

- `indicator_code` joins observations to indicator metadata
- `dimension_code` joins dimension values to dimension definitions
- `country_code` joins observations to decoded country names

Simple mental model:

- one table has codes
- another table explains those codes
- join key is the shared code

### Typed projection

A `typed projection` means:

- take messy JSON
- pull out the fields we care about
- cast them into stable types like string / int / float / datetime

Example:

- raw JSON field `TimeDim` -> integer `time_dim`
- raw JSON field `NumericValue` -> float `numeric_value`
- raw JSON field `Date` -> datetime `published_at`

The raw row should still be stored too.

## 4. The Proper Way To Decide Dimensions

Do not guess dimensions from vibes.

Use this order:

1. Start with the product question
2. Pick candidate indicators
3. Check `IndicatorDimension` for each indicator
4. Keep only the dimensions needed for the MVP use case
5. Preserve all raw dimensions in JSON for replay

### Step 1. Start with the product question

Ask:

- what decision do we want the app to support?
- what comparison do we need to make?
- what grouping do we need in the UI or score?

For this project, likely questions are:

- what countries have concerning disease burden trends?
- where is surveillance capacity weak?
- which countries should rank higher in response attention?

Those questions imply dimensions like:

- country
- time
- sometimes sex or age
- sometimes region

### Step 2. Pick candidate indicators

Examples already surfaced in the Linear research:

- `IHR*` and `IHRSPAR*` for readiness / surveillance capacity
- `TB_*` for tuberculosis burden
- `MALARIA_*` for malaria burden
- `WHS3_62` for measles reported cases
- `CHOLERA_0000000001` for cholera reported cases

### Step 3. Check indicator-specific dimensions

This is the critical rule:

Not every indicator uses the same dimensions.

That is why `IndicatorDimension` exists.

If WHO says an indicator uses:

- `COUNTRY`
- `YEAR`
- `SEX`

then those are valid slices for that indicator.

If WHO does not list `SEX` for that indicator, do not invent sex-based analysis for it.

### Step 4. Keep only dimensions needed for the MVP

For the MVP, default to:

- location: `SpatialDim` / `SpatialDimType`
- time: `TimeDim`, `TimeDimensionBegin`, `TimeDimensionEnd`
- up to three extra dims: `Dim1`, `Dim2`, `Dim3`
- metadata dims if present: `DataSourceDim`

Do not explode every possible dimension into custom columns unless the scoring or UI needs it.

### Step 5. Preserve raw JSON

Even if the MVP only uses a few columns, keep the full raw row in JSON.

Reason:

- future scoring may need currently-unused fields
- debugging becomes possible
- replay becomes possible

## 5. What Is An Indicator-Specific Dimension

An indicator-specific dimension is:

- a dimension that applies to one indicator
- but may not apply to another

Example:

- indicator A might have `COUNTRY + YEAR + SEX`
- indicator B might have `COUNTRY + YEAR`
- indicator C might have `REGION + YEAR`

That means the dimensional shape depends on the indicator.

This is why the pipeline cannot assume:

- `Dim1` always means sex
- `Dim2` always means age
- `Dim3` always means region

`Dim1`, `Dim2`, and `Dim3` are slots.
You must decode what each slot means for that indicator.

## 6. How To Read A WHO Observation Row

Treat a WHO row like this:

- `IndicatorCode`: what is being measured
- `SpatialDimType`: what kind of location code this is
- `SpatialDim`: which place
- `TimeDimType`: what kind of time bucket this is
- `TimeDim`: the time bucket value
- `Dim1Type`, `Dim2Type`, `Dim3Type`: what each extra dimension means
- `Dim1`, `Dim2`, `Dim3`: the coded values for those dimensions
- `NumericValue`: the numeric measure
- `Low`, `High`: uncertainty interval when available
- `Date`: when WHO published/refreshed the row

## 7. Recommended Canonical Tables

These are the internal tables I would use.

### `who_indicator`

Purpose:

- one row per indicator

Columns:

- `indicator_code`
- `indicator_name`
- `language`
- `raw_json`

Primary key:

- `indicator_code`

### `who_dimension`

Purpose:

- one row per dimension type

Columns:

- `dimension_code`
- `title`
- `raw_json`

Primary key:

- `dimension_code`

### `who_dimension_value`

Purpose:

- decode coded values for each dimension

Columns:

- `dimension_code`
- `value_code`
- `value_title`
- `parent_dimension_code`
- `parent_value_code`
- `raw_json`

Primary key:

- `(dimension_code, value_code)`

Important:

Do not use only `value_code` as the project PK.
Codes may be reused in different dimensions.

### `who_indicator_dimension`

Purpose:

- record which dimensions apply to which indicator

Columns:

- `indicator_code`
- `dimension_code`
- `dimension_name`
- `language`
- `raw_json`

Primary key:

- `(indicator_code, dimension_code)`

### `who_observation`

Purpose:

- canonical fact table of WHO observations

Columns:

- `observation_id` if WHO provides one
- `indicator_code`
- `spatial_dim_type`
- `spatial_dim_code`
- `parent_location_code`
- `time_dim_type`
- `time_dim`
- `time_dimension_value`
- `time_dimension_begin`
- `time_dimension_end`
- `dim1_type`
- `dim1_code`
- `dim2_type`
- `dim2_code`
- `dim3_type`
- `dim3_code`
- `datasource_dim_type`
- `datasource_dim_code`
- `value_text`
- `numeric_value`
- `low_value`
- `high_value`
- `comments`
- `published_at`
- `raw_json`

Suggested uniqueness key:

- `indicator_code`
- `spatial_dim_code`
- `time_dimension_value`
- `dim1_code`
- `dim2_code`
- `dim3_code`
- `datasource_dim_code`

If WHO provides a globally stable row `Id`, keep it, but still define your own natural uniqueness rule.

## 8. Canonical Join Keys

Use these joins.

### Observation -> Indicator

- `who_observation.indicator_code`
- joins to `who_indicator.indicator_code`

### Observation -> Spatial dimension value

- `who_observation.spatial_dim_type`
- `who_observation.spatial_dim_code`
- joins to `who_dimension_value.dimension_code`
- joins to `who_dimension_value.value_code`

### Observation -> Dim1 value

- `who_observation.dim1_type`
- `who_observation.dim1_code`
- joins to `who_dimension_value.dimension_code`
- joins to `who_dimension_value.value_code`

Same pattern for `dim2`, `dim3`, and `datasource_dim`.

### Indicator -> Allowed dimensions

- `who_indicator.indicator_code`
- joins to `who_indicator_dimension.indicator_code`

### Dimension value -> Dimension definition

- `who_dimension_value.dimension_code`
- joins to `who_dimension.dimension_code`

## 9. Enums To Define In The App

These are application enums, not necessarily WHO enums.

### `SourceKind`

- `who_odata`
- `exa`

### `PipelineStageName`

- `ingest_who`
- `enrich_with_exa`
- `score`

### `PipelineStageStatus`

- `running`
- `ok`
- `partial`
- `error`
- `skipped`

### `RiskBand`

- `low`
- `medium`
- `high`
- `critical`

### `ObservationRole`

Use this only if needed for grouping indicators:

- `surveillance_capacity`
- `event_signal`
- `risk_modifier`

## 10. Configs To Define

These should live in config, not in random code constants.

### WHO ingest config

- `who_base_url`
- `who_indicator_catalog_url`
- `who_dimension_catalog_url`
- `who_request_timeout_seconds`
- `who_page_size`
- `who_retry_count`
- `who_backfill_enabled`

### Indicator selection config

Purpose:

- declare which indicators are in scope for the MVP

Fields per indicator:

- `indicator_code`
- `category`
- `enabled`
- `default_spatial_dimension`
- `default_time_grain`
- `expected_dimensions`
- `notes`

### Scoring config

- `model_version`
- `sample_limit`
- `recency_decay_half_life_days`
- `uncertainty_penalty_enabled`
- `coverage_penalty_enabled`
- `indicator_group_weights`

### Agent read-only config

- `allowed_tables`
- `max_row_limit`
- `query_timeout_seconds`

## 11. Data Definitions The Team Should Agree On

These are the minimum definitions to write down explicitly.

### What is a signal?

In this project, two meanings exist.

1. WHO observation row
2. downstream risk-worthy event or country-level concern

Pick one for the app vocabulary.

Recommendation:

- use `observation` for raw WHO rows
- use `risk output` or `country risk result` for scored outputs

Do not call both of them `signal`.

### What is a run?

A `run` is one execution of the pipeline.

Recommendation:

- one `/ingest/run` call = one `pipeline_run`
- all artifacts produced in that execution must reference `pipeline_run_id`

### What is run-scoped?

`Run-scoped` means:

- any stage should read only data from the current pipeline run
- not "latest rows from the whole database"

Without run scope:

- scoring may use stale data
- results are not reproducible

### What is explainable scoring?

It means the score output must say:

- what inputs contributed
- how much they contributed
- what lowered confidence
- what model version generated it

## 12. Why The Current Scoring Is Naive

Because it is too blunt.

It appears to:

- read recent numeric values
- compute mean / max / count
- convert that into a single score

Problems:

- mixes incomparable indicators
- is not clearly run-scoped
- ignores uncertainty intervals
- ignores missingness and coverage
- is hard to defend to judges or users

## 13. Proper MVP Scoring Approach

For the hackathon MVP:

1. Keep scoring simple
2. But make it defensible

Recommended MVP:

- normalize within indicator family first
- aggregate only after normalization
- penalize uncertainty when `High - Low` is wide
- penalize missing expected dimensions
- store top contributors in `factors_json`
- bind score to `pipeline_run_id`

## 14. Questions To Stop Guessing On

These are the real unresolved decisions.

### Product

- Is the primary output country-level ranking, indicator-level ranking, or event-style alerting?
- Is the frontend showing country cards, a feed, or a report-first experience?
- Is WHO-only enough for the final demo, or is Exa needed for the story?

### Data

- Which exact indicator list is in scope for the MVP?
- Which categories are mandatory: readiness, event signals, risk modifiers?
- Do we score countries, indicators, or runs?

### Submission

- Is the demo judged mainly on technical novelty, practical usefulness, or polished presentation?
- Does the report explain a working prototype, or mostly propose a design?

## 15. Proper Workflow For This Project

Use this order.

1. Lock product output
2. Lock data contract
3. Lock scoring contract
4. Implement pipeline
5. Generate demo artifacts
6. Package report

### 1. Lock product output

Write one sentence:

`The app takes WHO indicator data and produces ranked, explainable country risk outputs.`

If the team disagrees with that sentence, stop and resolve that first.

### 2. Lock data contract

Before more coding:

- finalize canonical tables
- finalize join keys
- finalize MVP indicator list
- finalize which dimensions are required per category

### 3. Lock scoring contract

Define:

- what gets scored
- score range
- score bands
- explainability fields

### 4. Implement pipeline

- ingest WHO
- enrich with Exa
- score run-scoped outputs

### 5. Generate demo artifacts

- one example run
- one example output table
- one example explanation panel

### 6. Package report

- architecture
- why WHO
- limitations
- dual-use considerations
- screenshots or tables from the prototype

## 16. What Bryan Should Do

Immediate high-value work:

1. Consolidate the WHO model research into one clean artifact
2. Convert that into a canonical schema decision
3. Make the team agree on the project sentence and output type
4. Push for one MVP scoring contract
5. Use the notebook to validate 3-5 real indicators end-to-end

## 17. File Links

- Notebook: [who_gho_odata_usage.ipynb](C:/Users/wbrya/OneDrive/Documents/GitHub/biohack-2026-april/research/who_gho_odata/who_gho_odata_usage.ipynb)
- This doc: [OPERATING_MODEL.md](C:/Users/wbrya/OneDrive/Documents/GitHub/biohack-2026-april/research/who_gho_odata/OPERATING_MODEL.md)
