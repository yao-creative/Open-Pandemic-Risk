# Focused Build Checklist

Date: 2026-04-26
Branch: `focused-build`

This is the smallest sane breakdown from the current repo to the hackathon demo.

## Product Target

Build:

- a WHO-first app that ranks countries by outbreak risk
- and shows exactly why each country ranks there

Do not build:

- a chat app
- a full response recommendation engine
- a subnational domestic operations platform
- a generalized global health data warehouse

## Main Output Contract

Input:

- selected WHO indicators
- country/time observation rows
- optional uncertainty fields

Output:

- one `country_risk_result` per country per run
- each result has:
  - `country_code`
  - `risk_score`
  - `risk_band`
  - `disease_burden`
  - `surveillance_readiness`
  - `confidence`
  - `top_contributors`
  - `pipeline_run_id`

## Work Breakdown

### 1. Lock the scoring contract

Goal:

- define exactly what one scored row looks like

Subproblems:

- choose final output table/schema name
- define score range and risk bands
- define factor names
- define explanation payload shape

Done when:

- there is one stable schema for `country_risk_result`
- frontend and backend can both code against it

## 2. Clean WHO projection

Goal:

- turn messy WHO rows into typed scoring inputs

Subproblems:

- extract `indicator_code`
- extract `country_code`
- extract `period_date`
- extract `numeric_value`
- extract `low_value` and `high_value` when present
- extract source/update date
- attach factor category from profile
- bind rows to `pipeline_run_id`

Done when:

- scoring code no longer has to reverse-engineer `dim_json`

## 3. Indicator catalog selection

Goal:

- reduce the WHO profile to a defensible small set

Subproblems:

- pick burden indicators
- pick readiness indicators
- decide whether confidence is fully derived or partly sourced
- remove codes that are noisy, sparse, or redundant

Recommended shape:

- 3 to 5 burden indicators
- 3 to 5 readiness indicators
- confidence mostly derived from freshness, coverage, and uncertainty

Done when:

- you can explain every chosen indicator in one sentence

## 4. Country-level scoring

Goal:

- produce one score per country, not one score per run

Subproblems:

- group typed rows by country
- normalize within indicator family before aggregation
- invert readiness so weak readiness increases risk
- derive confidence from missingness, uncertainty width, and recency
- combine factor scores into one overall risk score
- generate risk band

Done when:

- the pipeline outputs a ranked list of countries

## 5. Explainability payload

Goal:

- make the ranking defendable in demo language

Subproblems:

- store factor scores
- store top contributing indicators
- store freshness and uncertainty notes
- store a short machine-readable rationale payload

Done when:

- for any country, you can answer:
  - why is it high?
  - what drove the score?
  - how much should I trust it?

## 6. Make Exa optional

Goal:

- stop enrichment from blocking the core demo

Subproblems:

- fail open when Exa is unavailable
- make scoring independent from Exa
- if Exa runs, enrich only top N countries after scoring

Done when:

- WHO-only still gives a complete usable ranking

## 7. Backend result API

Goal:

- expose ranking results cleanly to the frontend

Subproblems:

- add result retrieval endpoint for a run
- return sorted countries
- return country detail payload
- keep stage telemetry separate from demo results

Done when:

- frontend can fetch one run and render ranking + detail

## 8. Demo frontend

Goal:

- show the story in under 10 seconds

Subproblems:

- main screen with map + ranked table
- click/select country for detail panel
- show 3 top factors
- show loading, empty, and partial-data states

Done when:

- a judge can immediately see:
  - it ranks countries
  - it is explainable
  - it feels actionable

## 9. Tests

Goal:

- cover the risky logic, not just route smoke tests

Subproblems:

- projection tests
- country scoring tests
- run isolation tests
- optional enrichment failure tests
- frontend render tests for ranking/detail

Done when:

- the core ranking contract is protected from regressions

## 10. Submission packaging

Goal:

- turn the app into a strong hackathon submission

Subproblems:

- screenshots
- architecture diagram
- method summary
- why this matters
- what is novel
- limitations and future work

Done when:

- the PDF clearly explains the app you actually built

## Best Execution Order

1. scoring contract
2. clean WHO projection
3. indicator selection
4. country-level scoring
5. explainability payload
6. backend result API
7. demo frontend
8. make Exa optional polish
9. tests
10. submission packaging

## If You Need To Cut Scope Harder

Cut in this order:

1. remove Exa from critical path
2. reduce indicator count
3. ship table first, map second
4. keep country detail simple

Do not cut:

- country-level output
- factor explainability
- run isolation

## Suggested Team Split

Person 1:

- WHO projection
- country scoring
- explainability payload

Person 2:

- result API
- frontend ranking screen
- submission screenshots and packaging

If only one person is available:

- do backend scoring first
- then render a simple ranked table
- then add the map only if time remains
