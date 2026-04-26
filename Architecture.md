# Edit 1 Pandemic Early Warning Ingestion + Schema Proposal 2026-04-25 17:40 Branch: proposal/pandemic-early-warning-schema-ingestion

## Source Fit Analysis

- `WHO GHO OData API` and `Athena API` are high-quality, structured, country-level epidemiology sources with stable semantics and historical depth. They are best used as a baseline truth layer and calibration backbone, not as first detection signals.
- `ProMED` (RSS + web posts) provides expert-curated but narrative early outbreak signals with weaker structure and noisier timing. It is the primary lead generator for early warning.
- High-ROI architecture: run low-cost frequent ProMED ingestion for speed, then fuse with slower WHO indicator snapshots for context, confidence correction, and risk-score calibration.

## Pandemic Signal Ingestion Sequence (Mermaid)

```mermaid
sequenceDiagram
    autonumber
    participant Cron as scheduler/runner
    participant PromedIngest as backend/app/ingest/promed.py
    participant WhoIngest as backend/app/ingest/who.py
    participant Extractor as backend/app/pipeline/extract_llm.py
    participant Resolve as backend/app/pipeline/entity_resolution.py
    participant Score as backend/app/pipeline/risk_scoring.py
    participant DB as backend/app/db.py (Postgres)
    participant API as backend/app/main.py

    Cron->>PromedIngest: poll RSS + fetch new posts (5-15 min)
    PromedIngest->>DB: upsert raw_ingest_event(source=promed)
    PromedIngest->>Extractor: send narrative text payload
    Extractor-->>PromedIngest: pathogen/location/date/case/death/confidence JSON
    PromedIngest->>Resolve: canonicalize pathogen + geo entities
    Resolve-->>PromedIngest: canonical ids + dedupe keys
    PromedIngest->>DB: upsert canonical_event + event_observation

    Cron->>WhoIngest: pull OData/Athena indicators (daily)
    WhoIngest->>DB: upsert indicator_snapshot(source=who)

    Cron->>Score: recompute affected country/pathogen risk scores
    Score->>DB: read canonical_event + indicator_snapshot
    Score->>DB: upsert risk_score + alert

    API->>DB: query /signals /signals/map /stats
    DB-->>API: filtered events + scores + alerts
```

## Failure Path Sequence (Mermaid)

```mermaid
sequenceDiagram
    autonumber
    participant Cron as scheduler/runner
    participant PromedIngest as backend/app/ingest/promed.py
    participant Extractor as backend/app/pipeline/extract_llm.py
    participant DLQ as backend/app/pipeline/dead_letter.py
    participant DB as backend/app/db.py (Postgres)

    Cron->>PromedIngest: ingest batch
    PromedIngest->>Extractor: parse report
    Extractor-->>PromedIngest: low-confidence or schema-invalid output
    PromedIngest->>DB: persist parse_error with payload hash
    PromedIngest->>DLQ: enqueue raw record for retry/manual review
    DLQ->>DB: update processing_status=needs_review
```

## Data Schema Proposal

### Design Goals

- Separate immutable raw data from normalized facts.
- Permit multiple observations (sources, updates, corrections) per canonical event.
- Track extraction confidence and provenance for human-auditable early warning.
- Keep schema simple enough for a hackathon MVP, but extensible to production.

### Core Tables

| Table | Purpose | Key Columns |
| --- | --- | --- |
| `source_registry` | Source metadata and polling policy | `id`, `name`, `kind` (`rss`,`api`), `base_url`, `poll_interval_minutes`, `enabled` |
| `raw_ingest_event` | Immutable fetched payloads | `id`, `source_id`, `external_id`, `fetched_at`, `published_at`, `url`, `title`, `raw_text`, `raw_json`, `content_hash` |
| `canonical_event` | De-duplicated outbreak event entity | `id`, `event_key`, `pathogen_id`, `location_id`, `event_start_date`, `status` (`suspected`,`confirmed`,`monitoring`,`closed`) |
| `event_observation` | Source-specific claim about an event | `id`, `canonical_event_id`, `raw_ingest_event_id`, `observed_at`, `case_count`, `death_count`, `transmission_mode`, `novelty_flag`, `extract_confidence`, `verification_state` |
| `indicator_snapshot` | WHO country-level baseline indicators over time | `id`, `source_id`, `indicator_code`, `country_code`, `period_date`, `value`, `unit`, `dim_json` |
| `risk_score` | Computed risk outputs for triage and map views | `id`, `canonical_event_id`, `country_code`, `scored_at`, `risk_value`, `risk_band`, `score_factors_json`, `model_version` |
| `alert` | Actionable notifications generated from thresholds | `id`, `canonical_event_id`, `risk_score_id`, `alert_level`, `trigger_reason`, `created_at`, `acknowledged_at` |
| `pipeline_run` | Operational observability per ingestion/scoring run | `id`, `pipeline_name`, `started_at`, `finished_at`, `status`, `records_in`, `records_ok`, `records_failed`, `error_summary` |

### Minimal SQLAlchemy-Oriented Constraints

- Unique indexes:
  - `raw_ingest_event(source_id, external_id)`
  - `raw_ingest_event(source_id, content_hash)`
  - `canonical_event(event_key)`
  - `indicator_snapshot(source_id, indicator_code, country_code, period_date)`
- Foreign keys:
  - `event_observation.canonical_event_id -> canonical_event.id`
  - `event_observation.raw_ingest_event_id -> raw_ingest_event.id`
  - `risk_score.canonical_event_id -> canonical_event.id`
  - `alert.risk_score_id -> risk_score.id`
- Retention:
  - Keep `raw_ingest_event` immutable and append-only for replay/debug.
  - Use soft deletes only on user-facing entities (`alert` acknowledgements), not ingest logs.

## Current Database Schema (Mermaid ERD)

```mermaid
erDiagram
    SOURCE_REGISTRY ||--o{ RAW_INGEST_EVENT : has
    SOURCE_REGISTRY ||--o{ INDICATOR_SNAPSHOT : has
    CANONICAL_EVENT ||--o{ EVENT_OBSERVATION : has
    RAW_INGEST_EVENT ||--o{ EVENT_OBSERVATION : derived_from
    CANONICAL_EVENT ||--o{ RISK_SCORE : has
    CANONICAL_EVENT ||--o{ ALERT : has
    RISK_SCORE ||--o{ ALERT : triggers

    SOURCE_REGISTRY {
        int id PK
        string name UK
        string kind
        string base_url
        int poll_interval_minutes
        bool enabled
    }

    RAW_INGEST_EVENT {
        int id PK
        int source_id FK
        string external_id
        datetime fetched_at
        datetime published_at
        string url
        string title
        string raw_text
        json raw_json
        string content_hash
    }

    CANONICAL_EVENT {
        int id PK
        string event_key UK
        string pathogen_id
        string location_id
        datetime event_start_date
        string status
    }

    EVENT_OBSERVATION {
        int id PK
        int canonical_event_id FK
        int raw_ingest_event_id FK
        datetime observed_at
        int case_count
        int death_count
        string transmission_mode
        bool novelty_flag
        float extract_confidence
        string verification_state
    }

    INDICATOR_SNAPSHOT {
        int id PK
        int source_id FK
        string indicator_code
        string country_code
        datetime period_date
        float value
        string unit
        json dim_json
    }

    RISK_SCORE {
        int id PK
        int canonical_event_id FK
        string country_code
        datetime scored_at
        float risk_value
        string risk_band
        json score_factors_json
        string model_version
    }

    ALERT {
        int id PK
        int canonical_event_id FK
        int risk_score_id FK
        string alert_level
        string trigger_reason
        datetime created_at
        datetime acknowledged_at
    }

    PIPELINE_RUN {
        int id PK
        string pipeline_name
        datetime started_at
        datetime finished_at
        string status
        int records_in
        int records_ok
        int records_failed
        string error_summary
    }
```

## Ingestion and Scoring Proposal (High ROI)

- Polling cadence:
  - `ProMED RSS`: every 10 minutes.
  - `WHO indicators`: daily refresh, with backfill jobs for missing periods.
- Two-stage extraction:
  - Stage 1 deterministic parsing (RSS metadata, date normalization, URL canonicalization).
  - Stage 2 LLM extraction into strict JSON schema with confidence + rationale fields.
- Entity resolution:
  - Normalize pathogen and country using controlled dictionaries (`iso3`, pathogen aliases).
  - Compute `event_key = hash(pathogen_id + location_id + week_bucket + signal_type)` for dedupe.
- Risk scoring v1 (interpretable):
  - `risk = w1*signal_strength + w2*growth_proxy + w3*severity_proxy + w4*baseline_vulnerability_adjustment`
  - `baseline_vulnerability_adjustment` sourced from WHO indicators (e.g., historical burden, health-system proxies).
- Alerting:
  - Emit alert only when both threshold and minimum confidence are met.
  - Enforce cooldown windows to prevent duplicate alert spam for the same `canonical_event`.

## Implementation Notes

- Proposed module layout:
  - `backend/app/ingest/promed.py`
  - `backend/app/ingest/who.py`
  - `backend/app/pipeline/extract_llm.py`
  - `backend/app/pipeline/entity_resolution.py`
  - `backend/app/pipeline/risk_scoring.py`
  - `backend/app/models/*.py` (SQLAlchemy models for the tables above)
- API endpoints aligned to existing project plan:
  - `GET /signals`
  - `GET /signals/{id}`
  - `GET /signals/map`
  - `POST /ingest/run`
  - `GET /stats`
- Fast win for demo quality:
  - Seed with last 14 days of ProMED posts.
  - Pull 2-4 WHO indicators across 15-30 countries to avoid over-scope.
  - Show before/after calibration: raw narrative score vs WHO-calibrated score.

## Rollout Notes

- Phase 1 (Hackathon MVP): single worker, synchronous ingestion command, SQLite acceptable.
- Phase 2 (Productionizable): move to Postgres + job queue, partition `raw_ingest_event` by month, add idempotent retry semantics.
- Phase 3 (Operational): analyst review queue for low-confidence extractions, feedback loop into extraction prompts and scoring weights.

# Edit 2 Async Orchestration With Celery RabbitMQ 2026-04-25 21:49 Branch: proposal/pandemic-early-warning-schema-ingestion

## Celery Pipeline Sequence (Mermaid)

```mermaid
sequenceDiagram
    autonumber
    participant API as backend/app/api/routes/ingest.py
    participant Orchestrator as backend/app/workers/tasks/orchestrator.py
    participant Queue as RabbitMQ (ingest queue)
    participant PromedTask as backend/app/workers/tasks/source_promed.py
    participant WhoTask as backend/app/workers/tasks/source_who.py
    participant Finalizer as backend/app/workers/tasks/finalize_run.py
    participant DB as backend/app/db.py (Postgres)

    API->>DB: insert pipeline_run(state=queued)
    API->>Queue: enqueue orchestrate_run(pipeline_run_id)
    API-->>API: 202 Accepted + run_id

    Queue->>Orchestrator: execute orchestrate_run
    Orchestrator->>DB: set pipeline_run.state=running, started_at
    Orchestrator->>Queue: fan-out group(source_promed, source_who)

    Queue->>PromedTask: execute source ingestion
    PromedTask->>DB: upsert source_run(state, counters, error_code)
    PromedTask->>DB: upsert raw_ingest_event rows

    Queue->>WhoTask: execute WHO ingestion
    WhoTask->>DB: upsert source_run(state, counters, error_code)
    WhoTask->>DB: upsert indicator_snapshot rows

    Queue->>Finalizer: chord callback finalize_run
    Finalizer->>DB: aggregate source_run rows
    Finalizer->>DB: set pipeline_run.state=(succeeded|partial|failed), finished_at
```

## State Check Sequence (Mermaid)

```mermaid
sequenceDiagram
    autonumber
    participant UI as frontend polling client
    participant API as backend/app/api/routes/ingest.py
    participant DB as backend/app/db.py

    UI->>API: GET /ingest/runs/{id}
    API->>DB: read pipeline_run + source_run ordered by source
    DB-->>API: current states, counters, errors, timestamps
    API-->>UI: run summary + source-level progress

    UI->>API: GET /ingest/runs/{id}/events (optional)
    API->>DB: read pipeline_event logs for timeline
    API-->>UI: transition timeline (queued->running->partial/succeeded/failed)
```

## Proposed Runtime State Machine

- `pipeline_run.state`:
  - `queued`: accepted by API, waiting in queue.
  - `running`: orchestrator started and at least one source task scheduled.
  - `partial`: at least one source failed, at least one source succeeded.
  - `succeeded`: all enabled source tasks succeeded.
  - `failed`: all source tasks failed or orchestration failed before any success.
  - `canceled` (optional): manual cancellation before finalization.
- `source_run.state`:
  - `queued`, `running`, `succeeded`, `failed`, `skipped`.
- Transition guardrails:
  - only finalizer may set terminal `pipeline_run.state`.
  - source tasks are idempotent by `(pipeline_run_id, source_name, shard_key)`.
  - retries update `attempt` and keep latest terminal state per source.

## Schema Additions For Async Control

- Add columns to `pipeline_run`:
  - `state` (replace current overloaded `status`), `queued_at`, `started_at`, `finished_at`, `progress_pct`, `request_id`, `celery_root_task_id`.
- Add new `source_run` table:
  - `id`, `pipeline_run_id`, `source_name`, `state`, `attempt`, `queued_at`, `started_at`, `finished_at`, `records_in`, `records_ok`, `records_failed`, `error_code`, `error_summary`, `task_id`.
- Add optional `pipeline_event` table:
  - append-only transition and warning log (`event_type`, `payload_json`, `created_at`) for UI timeline and incident debugging.
- Recommended indexes:
  - `pipeline_run(state, queued_at desc)`
  - `source_run(pipeline_run_id, source_name)` unique
  - `source_run(state, started_at desc)`

## Proposed Advancement Database Schema (Mermaid ERD)

```mermaid
erDiagram
    SOURCE_REGISTRY ||--o{ RAW_INGEST_EVENT : has
    SOURCE_REGISTRY ||--o{ INDICATOR_SNAPSHOT : has
    CANONICAL_EVENT ||--o{ EVENT_OBSERVATION : has
    RAW_INGEST_EVENT ||--o{ EVENT_OBSERVATION : derived_from
    CANONICAL_EVENT ||--o{ RISK_SCORE : has
    CANONICAL_EVENT ||--o{ ALERT : has
    RISK_SCORE ||--o{ ALERT : triggers

    PIPELINE_RUN ||--o{ SOURCE_RUN : tracks
    PIPELINE_RUN ||--o{ PIPELINE_EVENT : emits
    SOURCE_RUN ||--o{ PIPELINE_EVENT : emits

    SOURCE_REGISTRY {
        int id PK
        string name UK
        string kind
        string base_url
        int poll_interval_minutes
        bool enabled
    }

    RAW_INGEST_EVENT {
        int id PK
        int source_id FK
        string external_id
        datetime fetched_at
        datetime published_at
        string url
        string title
        string raw_text
        json raw_json
        string content_hash
    }

    CANONICAL_EVENT {
        int id PK
        string event_key UK
        string pathogen_id
        string location_id
        datetime event_start_date
        string status
    }

    EVENT_OBSERVATION {
        int id PK
        int canonical_event_id FK
        int raw_ingest_event_id FK
        datetime observed_at
        int case_count
        int death_count
        string transmission_mode
        bool novelty_flag
        float extract_confidence
        string verification_state
    }

    INDICATOR_SNAPSHOT {
        int id PK
        int source_id FK
        string indicator_code
        string country_code
        datetime period_date
        float value
        string unit
        json dim_json
    }

    RISK_SCORE {
        int id PK
        int canonical_event_id FK
        string country_code
        datetime scored_at
        float risk_value
        string risk_band
        json score_factors_json
        string model_version
    }

    ALERT {
        int id PK
        int canonical_event_id FK
        int risk_score_id FK
        string alert_level
        string trigger_reason
        datetime created_at
        datetime acknowledged_at
    }

    PIPELINE_RUN {
        int id PK
        string pipeline_name
        string state
        datetime queued_at
        datetime started_at
        datetime finished_at
        float progress_pct
        string request_id
        string celery_root_task_id
        int records_in
        int records_ok
        int records_failed
        string error_summary
    }

    SOURCE_RUN {
        int id PK
        int pipeline_run_id FK
        string source_name
        string state
        int attempt
        datetime queued_at
        datetime started_at
        datetime finished_at
        int records_in
        int records_ok
        int records_failed
        string error_code
        string error_summary
        string task_id
    }

    PIPELINE_EVENT {
        int id PK
        int pipeline_run_id FK
        int source_run_id FK
        string event_type
        json payload_json
        datetime created_at
    }
```

## Folder Organization And Refactor Plan

- `backend/app/api/routes/`
  - `ingest.py` (`POST /ingest/run`, `GET /ingest/runs/{id}`, `GET /ingest/runs`)
- `backend/app/core/`
  - `config.py`, `celery_app.py`, `logging.py`
- `backend/app/models/`
  - `pipeline.py` (`PipelineRun`, `SourceRun`, `PipelineEvent`)
  - `signal.py` (`RawIngestEvent`, `IndicatorSnapshot`, etc.)
- `backend/app/schemas/`
  - `ingest_run.py` (`RunCreateResponse`, `RunStatusResponse`, `SourceRunResponse`)
- `backend/app/services/`
  - `run_state_machine.py` (transition rules + validators)
  - `ingest_registry.py` (source registration and enabled/disabled controls)
- `backend/app/workers/tasks/`
  - `orchestrator.py`, `source_promed.py`, `source_who.py`, `finalize_run.py`
- `backend/app/ingest/adapters/`
  - `promed_adapter.py`, `who_odata_adapter.py` (pure fetch/parse, no orchestration)
- `backend/app/repos/`
  - `pipeline_repo.py`, `source_run_repo.py` (DB write patterns and transaction boundaries)

## Refactoring Steps (Low-Risk Sequence)

1. Extract synchronous `run_ingestion` logic into reusable source task functions with no FastAPI dependency.
2. Introduce `source_run` model and migration; keep current sync endpoint behavior untouched.
3. Add Celery app + RabbitMQ wiring; implement orchestrator and finalizer tasks.
4. Change `POST /ingest/run` to async trigger returning `202` and run id.
5. Add `GET /ingest/runs/{id}` polling endpoint backed by `pipeline_run` + `source_run`.
6. Deprecate old synchronous response shape after frontend poller is live.

## Polling And Operational Checks

- UI poll cadence:
  - every `2s` while `queued|running`, every `10s` after terminal state for summary refresh.
- Health endpoints:
  - `GET /healthz` for process liveness.
  - `GET /readyz` includes DB + broker reachability.
- Operator checks:
  - queue depth, worker concurrency, oldest queued run age, per-source failure rate over last N runs.
- Retry policy:
  - `autoretry_for` transient HTTP/network errors with bounded exponential backoff.
  - mark `source_run.failed` only after retry budget exhausted.

## Rollout Notes

- Stage A (hackathon-compatible): single Celery worker, one queue, one finalizer, SQLite still allowed for local demo.
- Stage B: move runtime to Postgres, enable multiple workers and source-specific queues.
- Stage C: add dead-letter queue, poison message handling, and alerting on stuck `running` state via heartbeat timeout.

# Edit 3 SQLAlchemy Flush Decision Points 2026-04-25 21:52 Branch: proposal/pandemic-early-warning-schema-ingestion

## Pipeline Run Create Flow With Explicit Flush (Mermaid)

```mermaid
sequenceDiagram
    autonumber
    participant API as backend/app/api/routes/ingest.py
    participant Session as SQLAlchemy Session (backend/app/db.py)
    participant DB as Postgres
    participant Repo as backend/app/repos/pipeline_repo.py

    API->>Repo: create PipelineRun(status=running, counters=0)
    Repo->>Session: db.add(pipeline_run)
    Note right of Session: Object is pending in Unit of Work only
    Repo->>Session: db.flush()
    Session->>DB: INSERT pipeline_run(...)
    DB-->>Session: generated id/defaults
    Session-->>Repo: pipeline_run.id available
    Repo-->>API: return run_id for downstream records/logs
    API->>Session: db.commit()
```

## Autoflush and Commit-Only Path (Mermaid)

```mermaid
sequenceDiagram
    autonumber
    participant Service as backend/app/services/run_service.py
    participant Session as SQLAlchemy Session
    participant DB as Postgres

    Service->>Session: db.add(pipeline_run)
    Note right of Session: No SQL yet unless flush/autoflush triggers
    Service->>Session: execute query OR db.commit()
    Session->>DB: implicit flush (INSERT/UPDATE pending rows)
    DB-->>Session: constraints/defaults evaluated
    Session-->>Service: query result or commit success/failure
```

## Implementation Notes

- `db.add()` stages the row in memory; it does not persist immediately.
- `db.flush()` is a transactional write checkpoint, not a durability boundary.
- Use explicit `flush()` when one of these is true:
  - subsequent writes need `pipeline_run.id` in the same transaction.
  - fail-fast behavior is needed before expensive downstream processing.
  - DB-side defaults/triggers must be materialized before building a response payload.
- Skip explicit `flush()` when the code can rely on implicit flush at query/commit and does not depend on generated values yet.
- Keep `commit()` at transaction boundaries so run creation plus related writes remain atomic and rollback-safe.

## Operational Guardrails

- Avoid `flush()` after every `add()`; it increases round trips with little value.
- Treat flush errors (unique/FK/check violations) as expected transactional failures and return deterministic API errors.
- For async orchestration, create `pipeline_run`, flush once to get run id, enqueue tasks, then commit once.

# Edit 6 WHO-Only Hard-Coded Integration (Pre-Implementation Baseline vs Target) 2026-04-26 10:07 Branch: who-surveillance-mvp-v1

## Old ERD (Current State) (Mermaid)

```mermaid
erDiagram
    SOURCE_REGISTRY ||--o{ INDICATOR_SNAPSHOT : has
    PIPELINE_RUN {
        int id PK
        string pipeline_name
        datetime started_at
        datetime finished_at
        string status
        int records_in
        int records_ok
        int records_failed
        string error_summary
    }
    SOURCE_REGISTRY {
        int id PK
        string name UK
        string kind
        string base_url
        int poll_interval_minutes
        bool enabled
    }
    INDICATOR_SNAPSHOT {
        int id PK
        int source_id FK
        string indicator_code
        string country_code
        datetime period_date
        float value
        string unit
        json dim_json
    }
```

## Old Flow (Current State) (Mermaid)

```mermaid
flowchart TD
    A[POST /ingest/run] --> B[run_ingestion]
    B --> C[Create pipeline_run running]
    C --> D[GET WHO endpoint from who_odata_url]
    D --> E[ingest_who_odata]
    E --> F[Upsert source_registry]
    E --> G[Insert indicator_snapshot rows]
    G --> H[Aggregate counters]
    H --> I[Finalize pipeline_run status]
    I --> J[Return ingest summary]
```

## Old Sequence (Current State) (Mermaid)

```mermaid
sequenceDiagram
    autonumber
    participant API as /ingest/run
    participant Orchestrator as run_ingestion
    participant WHO as WHO OData (single endpoint)
    participant DB as App DB

    API->>Orchestrator: run_ingestion(db, settings)
    Orchestrator->>DB: insert pipeline_run(status=running)
    Orchestrator->>WHO: GET settings.who_odata_url
    WHO-->>Orchestrator: payload.value[]
    Orchestrator->>DB: get/create source_registry(who_odata)
    loop each row
        Orchestrator->>DB: dedupe + insert indicator_snapshot
    end
    Orchestrator->>DB: update pipeline_run totals + status
    Orchestrator-->>API: IngestRunResponse
```

## New ERD (Target for This Implementation) (Mermaid)

```mermaid
erDiagram
    SOURCE_REGISTRY ||--o{ INDICATOR_SNAPSHOT : has
    PIPELINE_RUN {
        int id PK
        string pipeline_name
        datetime started_at
        datetime finished_at
        string status
        int records_in
        int records_ok
        int records_failed
        string error_summary
    }
    SOURCE_REGISTRY {
        int id PK
        string name UK
        string kind
        string base_url
        int poll_interval_minutes
        bool enabled
    }
    INDICATOR_SNAPSHOT {
        int id PK
        int source_id FK
        string indicator_code
        string country_code
        datetime period_date
        float value
        string unit
        json dim_json
    }
```

Notes:
- No new tables in this step.
- New WHO profile/category metadata is stored in `indicator_snapshot.dim_json`.

## New Flow (Target for This Implementation) (Mermaid)

```mermaid
flowchart TD
    A[POST /ingest/run] --> B[run_ingestion with fixed profile who_surveillance_mvp_v1]
    B --> C[Create pipeline_run running]
    C --> D[Loop hard-coded indicator codes]
    D --> E[GET WHO /api/{IndicatorCode}]
    E --> F[ingest_who_odata code-scoped ingest]
    F --> G[Insert indicator_snapshot with profile and category tags in dim_json]
    G --> H[Collect per-code status and counters]
    H --> I[Finalize pipeline_run aggregate status: ok/partial/error]
    I --> J[Return run summary plus code diagnostics]
    J --> K[GET /runs/{id} for operator readback]
```

## New Sequence (Target for This Implementation) (Mermaid)

```mermaid
sequenceDiagram
    autonumber
    participant API as /ingest/run
    participant Orchestrator as run_ingestion (fixed profile)
    participant WHO as WHO OData (/api/{IndicatorCode})
    participant DB as App DB
    participant RunsAPI as /runs/{id}

    API->>Orchestrator: run_ingestion(db, settings)
    Orchestrator->>DB: insert pipeline_run(status=running, profile=who_surveillance_mvp_v1 logical context)
    loop each hard-coded indicator code
        Orchestrator->>WHO: GET /api/{IndicatorCode}
        alt code success
            WHO-->>Orchestrator: payload rows
            Orchestrator->>DB: dedupe + insert indicator_snapshot rows
            Orchestrator->>Orchestrator: mark code_result ok
        else code failure
            WHO-->>Orchestrator: http/network/timeout error
            Orchestrator->>Orchestrator: mark code_result error
        end
    end
    Orchestrator->>DB: update pipeline_run totals + final status
    Orchestrator-->>API: run summary + code diagnostics
    RunsAPI->>DB: fetch pipeline_run + diagnostics
    RunsAPI-->>RunsAPI: return operator-readable run details
```
