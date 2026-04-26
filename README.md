# AI x Bio Hackathon Notes

## Hackathon

- Event: [AI x Bio Hackathon](https://apartresearch.com/research)
- Dates mentioned in chat: April 24-26, 2026
- Focus: how AI changes biological risk, and what can be built to stay ahead

## Tracks

1. DNA synthesis screening and guardrails for AI-powered bio design tools
2. Pandemic early warning systems: wastewater, metagenomic sequencing, disease intelligence
3. Practitioner tools: dashboards, risk assessment, policy trackers, and communications tools for under-resourced institutions
4. Benchtop DNA synthesizer security: phone-home screening, tamper-proof hardware, split-order detection

## Funding Angle

- [Coefficient Giving](https://www.coefficientgiving.org/) biosecurity RFP mentioned in chat
- Deadline mentioned in chat: May 11
- Chat claim: possible follow-on 500-word Expression of Interest

## Judge Context

### People Mentioned

- Judges named in chat:
  - Jasper Goetting, SecureBio
  - Jason Hoelscher-Obermaier, Apart Research
- Influential speakers mentioned in chat:
  - Kevin Esvelt
  - Jaime Yassif
  - Conor McGurk
  - Steph Guerra
  - Jonas Sandbrink

### What Judges Likely Reward

- Open-source tool
- Real practitioner gap
- Technical substance
- Clear bio-risk reduction story
- Usable by under-resourced institutions

## Project Direction

### Goal

Bio threat intel aggregator.

### Analogs

- Recorded Future
- Mandiant
- CrowdStrike
- HealthMap
- ProMED
- Sormas
- GoData

### Build Concept

Aggregate data to provide exact information, a fresh alert feed, and response decisions with rationale.

### Chat Rank

1

### Judge Preferences

- Novelty
- Approach
- Solution
- Clarity of problem addressed

## Core Problems to Solve

- Convert messy global signals into actionable early warnings with clear importance.

## Ingestion (Ranked Notes)

- WHO:
  - https://www.who.int/data/gho/info/gho-odata-api
  - GHO Indicator Metadata Registry
  - GHO Data Portal
- CDC NWSS API (wastewater API)
- ProMED:
  - https://www.google.com/search?q=https://promedmail.org/promed-posts/
  - https://www.google.com/search?q=https://promedmail.org/rss-feeds/
  - Notes: RSS; ISID directly (bulk/high frequency)
- HealthMap:
  - HealthMap API Information
  - Interactive Map
  - HealthMap GitHub repositories

## Additional Data Signals

- News
- OpenFlights
- WorldPop
- GLEAM
- ProMED

## User Features

- Feed: low-latency, fresh signals
- Evaluation: signal confidence and importance
- Response: actionable recommendations

## Core Technical Features

- Ingestion and normalization
- Event extraction
- Anomaly detection
- Fusion
- Risk scoring
- Recommended response based on analytics

## Audience

- Public health: primary
- Global organizations: coordination
- Hospitals: preparedness
- Enterprises: risk
- Researchers: analysis

## ML Experiment (Ingestion-Only)

A manual first-pass dataset builder now exists under `ml/`:

- X: pull WHO fixed-profile rows from `indicator_snapshot`
- Y: pull WHO DON labels, with fallback to WHO Emergencies when DON is empty
- preprocess with Polars into `ml/data/ml_ready.parquet`

See `ml/README.md` for command sequence and notebook usage.
