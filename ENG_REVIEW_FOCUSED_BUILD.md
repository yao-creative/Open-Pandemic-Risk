# Engineering Review: Focused Build

Date: 2026-04-26
Branch: `focused-build`

This review reconciles:

- the current repo implementation
- `Architecture.md`
- `HACKATHON_MVP.md`
- Linear issues `AIX-33`, `AIX-35`, `AIX-37`
- Yi Yao's latest chat guidance

## Executive Summary

The project should be built as an app demo plus a submission PDF.

The app should do one thing clearly:

- rank countries by outbreak risk using WHO data
- show why each country ranks where it does

The PDF is the packaging of that app, not the product itself.

The current repo already has a usable pipeline skeleton:

- WHO ingestion
- stage-based orchestration
- optional Exa enrichment
- run telemetry

But the current pipeline does **not** yet produce the correct hackathon output.

Right now it produces:

- a pipeline run
- one aggregate score for a run

What the demo needs is:

- one score per country
- factor breakdown per country
- a UI that shows ranking + explanation

## What Yi Yao's Message Means

Translated into engineering terms:

- he has already built the ingestion and enrichment scaffolding
- he has **not** locked the risk/response scope yet
- he wants WHO data understanding to drive the scoring model
- he is unsure whether to target local ministries, domestic use, or international coordination
- time is extremely constrained, so scope has to collapse hard

The correct interpretation is:

- do **not** invent a big new platform
- do **not** build subnational domestic outbreak ops unless WHO data makes it trivial
- do **not** keep chat or generic "response agent" ideas on the critical path
- do build a narrow country-prioritization app for a public-health analyst or ministry analyst

## Step 0: Scope Challenge

### What already exists

Existing code already solves part of the problem:

- `backend/app/pipeline/runner/pipeline_runner.py`
  - ordered stage runner
  - run status
  - stage status
  - event log
- `backend/app/pipeline/run_ingest.py`
  - WHO profile-based ingestion
  - per-code run stats
- `backend/app/ingest/who.py`
  - fetches WHO OData rows
  - stores raw-ish row JSON in `dim_json`
- `backend/app/pipeline/stages/enrich_snapshot_agent.py`
  - optional Exa-based enrichment stage
- `backend/app/api/routes/pipeline.py`
  - `POST /pipeline/run`
  - `GET /pipeline/runs/{id}`
  - `GET /pipeline/runs/{id}/events`
- tests and CI
  - backend tests
  - compose health
  - live E2E workflow

### Minimum change set that hits the real goal

Minimum viable hackathon build:

1. keep the current stage runner
2. keep WHO as the primary source
3. change scoring output from run-level to country-level
4. add an explainable factor payload per country
5. add a simple UI: map + ranked table + country detail
6. keep Exa optional or non-blocking

### Scope ruling

Recommendation: reduce scope.

Do not build:

- subnational domestic analytics
- generalized response planning engine
- chat-first interface
- ProMED-first early-warning ingestion
- fully canonical WHO warehouse before the demo

Instead build:

- WHO-first country ranking
- explainable factor breakdown
- one clean demo screen

### WHO API reality check

A live probe of the WHO API confirms:

- the natural shape is country-level and year/time-sliced
- indicator dimensions vary by indicator
- uncertainty fields like `Low` and `High` exist for some indicators

Example observations:

- `MDG_0000000020` exposes `COUNTRY`, `REGION`, `YEAR`, `PUBLISHSTATE`
- row payloads contain `SpatialDim`, `TimeDim`, `NumericValue`, `Low`, `High`, `Date`
- `SDGIHR2021` is also country/year-shaped

This means:

- "domestic" is only realistic if you mean "usable by a domestic ministry"
- it is **not** a strong fit for subnational district-level operational tooling

## Architecture Review

### Finding 1

`[P1] (confidence: 10/10) backend/app/pipeline/stages/score_snapshot.py:17-60 — the score stage produces one aggregate run score, not one country risk result.`

Why it matters:

- the chosen product is country ranking
- judges need a ranked table and explainability by country
- a single run score cannot drive that UI

Recommendation:

- replace `PipelineRunScore` as the demo-facing output with `country_risk_result`
- keep run-level score rows only if they are useful as telemetry

### Finding 2

`[P1] (confidence: 9/10) backend/app/pipeline/runner/pipeline_runner.py:15 and backend/app/pipeline/stages/enrich_snapshot_agent.py:78-89 — Exa enrichment is on the critical path and can fail the whole pipeline.`

Why it matters:

- the core demo is WHO ranking
- Exa needs an API key and agent stability
- a failed enrichment stage should not block a demoable country ranking

Recommendation:

- move Exa after scoring, or mark it optional and fail-open

### Finding 3

`[P1] (confidence: 9/10) backend/app/models/entities.py:67-86 and backend/app/ingest/who.py:117-132 — WHO observations are stored in a thin snapshot table with opaque `dim_json`, but the project needs explicit country/time/factor derivation.`

Why it matters:

- current storage is enough for raw capture
- it is not enough for stable explainable scoring contracts
- every downstream consumer would need to reverse-engineer the WHO row shape again

Recommendation:

- for the hackathon, add a typed projection stage or table for canonical scoring input
- minimum typed fields:
  - `indicator_code`
  - `country_code`
  - `period_date`
  - `numeric_value`
  - `low_value`
  - `high_value`
  - `source_date`
  - `category`
  - `pipeline_run_id`

### Finding 4

`[P2] (confidence: 8/10) backend/app/pipeline/run_ingest.py:141-223 plus backend/app/pipeline/runner/pipeline_runner.py:116-147 — the top-level pipeline run points at nested ingest/enrichment run ids, which adds lineage indirection during a time-constrained hackathon.`

Why it matters:

- the model is understandable
- but it makes debugging and UI data loading harder than needed

Recommendation:

- keep nested runs only if you reuse them directly
- otherwise bind country results to the top-level `pipeline_run_id` and treat stage artifacts as implementation detail

## Code Quality Review

### Finding 1

`[P1] (confidence: 10/10) backend/app/pipeline/stages/score.py:54-77 and backend/app/pipeline/stages/score_snapshot.py:22-55 — scoring averages mixed indicators with incompatible semantics.`

Why it matters:

- counts, rates, prevalence, readiness scores, and bounded percentages are not directly comparable
- this makes the current score scientifically weak and hard to defend

Recommendation:

- normalize inside indicator families first
- aggregate second
- preserve factor-level contributions in output

### Finding 2

`[P1] (confidence: 9/10) backend/app/ingest/who.py:21-29 — `_parse_period_date()` falls back to `Dim1`, even though `Dim1` is indicator-specific and may not represent time.`

Why it matters:

- this can silently mis-date rows
- the WHO model explicitly treats `Dim1` as a generic dimension slot

Recommendation:

- only derive time from WHO time fields
- keep indicator-specific dimensions separate from time parsing

### Finding 3

`[P1] (confidence: 9/10) backend/app/ingest/who.py:101-103 — `DisplayValue` is stored as `unit`, but WHO `DisplayValue` is often a human-readable value string, not a measurement unit.`

Why it matters:

- example WHO rows include display strings like `168 [70-308]`
- storing that as `unit` corrupts semantics and hurts explainability

Recommendation:

- store unit separately only when an actual unit exists
- preserve `Value`/display text as display text

### Finding 4

`[P2] (confidence: 8/10) backend/app/agents/react_agent.py:84-97 — snapshot context reads recent indicator rows globally rather than clearly constraining to the intended snapshot.`

Why it matters:

- enrichment target selection can drift away from the current run
- citations can attach to stale or unrelated countries

Recommendation:

- if Exa remains, hard-scope all enrichment context to the current snapshot or top-level run

### Finding 5

`[P2] (confidence: 8/10) backend/app/models/entities.py:89-110 and :180-189 — both `RiskScore` and `PipelineRunScore` exist, while the focused plan wants `country_risk_result`.`

Why it matters:

- there are three competing score concepts
- naming drift will slow implementation and produce avoidable bugs

Recommendation:

- standardize now:
  - `who_observation` for typed WHO fact rows
  - `country_risk_result` for country output
  - `pipeline_run` for execution lineage

## Test Review

### Coverage diagram

```text
CODE PATHS                                                     USER FLOWS
[+] /pipeline/run                                              [+] Analyst starts a run
  ├── create_or_get_run()                                        ├── [★★ TESTED] route returns run id/status
  ├── background runner launch                                   ├── [GAP] pipeline reaches country ranking result
  └── [GAP] idempotent rerun returns same useful output          └── [GAP] failed optional enrichment still shows ranking

[+] ingest_snapshot stage                                       [+] WHO ingest behavior
  ├── run_ingestion()                                             ├── [★★ TESTED] WHO payload can be parsed
  ├── per-code savepoint isolation                                ├── [GAP] mixed success across codes shows partial run
  ├── [GAP] year parsing avoids Dim1 misuse                       ├── [GAP] Low/High uncertainty fields preserved
  └── [GAP] display text not mislabeled as unit                   └── [GAP] same country across multiple indicators is grouped correctly

[+] enrich_snapshot_agent stage                                 [+] Enrichment behavior
  ├── validate snapshot_ref_id                                    ├── [★★ TESTED] stage validation fails with missing inputs
  ├── run agent + persist findings                                ├── [GAP] no Exa key does not kill core demo
  ├── [GAP] snapshot scoping for context selection                └── [GAP] enrichment citations stay attached to current run only
  └── [GAP] fail-open optional path

[+] score_snapshot stage                                        [+] Ranking and explanation
  ├── select rows for current snapshot                            ├── [★★ TESTED] score stage can scope rows by snapshot ref
  ├── derive features                                             ├── [GAP] one country per output row
  ├── [GAP] indicator-aware normalization                         ├── [GAP] factor breakdown visible for burden/readiness/confidence
  ├── [GAP] uncertainty penalty from Low/High                     ├── [GAP] countries are rank-sorted deterministically
  ├── [GAP] recency weighting                                     ├── [GAP] missing data lowers confidence instead of inflating risk
  ├── [GAP] idempotent one-result-per-country-per-run             └── [GAP] stale older runs do not contaminate current ranking
  └── [GAP] country_risk_result persistence

[+] frontend                                                    [+] Demo UI
  └── [GAP] current frontend only shows /readyz                  ├── [GAP] map + ranked table render pipeline results
                                                                 └── [GAP] country detail explains why a country ranks high

COVERAGE: 4/24 meaningful paths tested (~17%)
Critical gaps: country-level result contract, indicator-aware scoring, optional enrichment failure path, demo UI
```

### Missing tests to add to the plan

- `backend/tests/test_who_projection.py`
  - assert time parsing uses only WHO time fields
  - assert `Low` and `High` are preserved
  - assert display text is not stored as unit
- `backend/tests/test_country_risk_scoring.py`
  - assert one result per country
  - assert burden/readiness/confidence factors are emitted
  - assert mixed indicator families are normalized before aggregation
  - assert missingness reduces confidence
  - assert recency weighting changes result ordering when dates differ
- `backend/tests/test_pipeline_optional_enrichment.py`
  - assert WHO scoring succeeds even when Exa is unavailable
- `backend/tests/test_pipeline_run_isolation.py`
  - assert old runs do not contaminate a new run's ranking
- `frontend` integration/E2E
  - map renders ranked countries
  - clicking a country shows factor breakdown
  - empty state and failed-enrichment state still present a usable UI

## Performance Review

### Finding 1

`[P2] (confidence: 8/10) backend/app/pipeline/stages/score_snapshot.py:22-35 — score stage scans rows, filters snapshot lineage in Python, and stops after `sample_limit`.`

Why it matters:

- this becomes slower as snapshots grow
- it is unnecessary once run lineage is modeled explicitly

Recommendation:

- persist run lineage as a first-class indexed column
- query only rows for the active run in SQL

### Finding 2

`[P2] (confidence: 7/10) backend/app/pipeline/runner/pipeline_runner.py:23-35 — idempotency lookup scans the last 200 runs and inspects JSON in application code.`

Why it matters:

- acceptable for very small hackathon volume
- weak if reused beyond the demo

Recommendation:

- if kept, move idempotency key to a dedicated indexed column

### Finding 3

`[P2] (confidence: 7/10) backend/app/agents/react_agent.py:84-89 — enrichment context reads latest rows globally and limits in app code rather than targeted SQL by run/country.`

Why it matters:

- more rows than needed are read
- stale data risk and unnecessary DB work are coupled

Recommendation:

- scope by active run and selected countries before loading

## Failure Modes

| Codepath | Real failure mode | Test exists | Error handling exists | User sees clear error? |
|---|---|---:|---:|---:|
| WHO ingest | indicator endpoint returns 404/500 | partial | yes | partly |
| WHO ingest | time parsed from wrong field | no | no | no |
| Exa enrichment | missing key or upstream error | no | partial | no |
| Score stage | mixed indicators inflate/deflate risk incorrectly | no | no | no |
| Score stage | older run contaminates new score | partial | no | no |
| Score stage | one global score returned instead of country ranking | no | no | yes, via bad demo output |
| Frontend | backend healthy but no ranking UI exists | yes, indirectly | no | yes |

Critical silent gaps:

- time parsing ambiguity
- indicator-family mixing
- optional enrichment blocking the core pipeline

## NOT in Scope

- subnational local ministry ops
  - WHO data shape does not justify this for MVP
- generalized response recommendation engine
  - too open-ended and hard to defend in a short demo
- chat interface
  - explicitly killed already and not needed for the strongest story
- ProMED-first narrative ingestion
  - conflicts with the WHO-first focused build
- fully generalized canonical metadata warehouse
  - useful later, but too large if it blocks the demo UI and country ranking output

## Recommended Build Target

Build this:

```text
POST /pipeline/run
  -> ingest WHO indicators for a fixed profile
  -> transform rows into typed scoring inputs
  -> compute country_risk_result rows
  -> optionally enrich top N countries with Exa
  -> GET results for map + ranked table + detail panel
```

Product sentence:

- "We rank countries by outbreak risk using WHO burden and readiness data, then show exactly why."

Primary user:

- public health analyst
- secondarily, a ministry analyst needing prioritization

## Implementation Order

### Lane A

- scoring contract
- country result schema
- typed WHO projection

Modules touched:

- `backend/app/models`
- `backend/app/ingest`
- `backend/app/pipeline/stages`

### Lane B

- pipeline API response for country results
- result retrieval endpoint

Modules touched:

- `backend/app/api/routes`
- `backend/app/schemas`

Depends on:

- Lane A

### Lane C

- frontend demo screen

Modules touched:

- `frontend/src`

Depends on:

- Lane B

### Lane D

- optional Exa enrichment polish

Modules touched:

- `backend/app/agents`
- `backend/app/pipeline/stages`

Depends on:

- Lane A

Execution order:

- do Lane A first
- then launch Lane B + Lane D in parallel if there are two builders
- then do Lane C once backend result shape is stable

## Final Recommendation

The right build is an app, not just a PDF.

But it is not a broad bio-intel platform either.

It should be:

- a WHO-first country ranking app
- with explainable country-level outputs
- with optional enrichment
- packaged by a PDF report for submission

If there is only enough time for one decisive backend change, do this:

- replace run-level scoring with `country_risk_result` and make Exa non-blocking

That is the shortest path from the current repo to a demo judges can understand in under 10 seconds.
