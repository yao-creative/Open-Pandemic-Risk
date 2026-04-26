# ML Ingestion-Only Experiment (Manual v1)

This folder builds an initial supervised training dataset from:

- X candidates from DB (`indicator_snapshot`, fixed WHO profile rows)
- Y candidates from WHO news APIs
  - Primary: `/api/news/dons`
  - Fallback when DON is empty: `/api/news/emergencies`

No enrichment stage is used in this experiment.

## Setup

```bash
python3 -m venv .venv-ml
source .venv-ml/bin/activate
pip install -r ml/requirements.txt
```

## Run

```bash
python ml/scripts/probe_who_news_apis.py --out ml/data/raw/who_api_probe.json
python ml/scripts/load_x_from_db.py --db-path backend/app.db --out ml/data/processed/x_candidates.parquet
python ml/scripts/fetch_y_who_news.py --out-json ml/data/raw/y_who_news_raw.json --out-parquet ml/data/processed/y_candidates.parquet --top 100
python ml/scripts/preprocess_xy_polars.py --x ml/data/processed/x_candidates.parquet --y ml/data/processed/y_candidates.parquet --out ml/data/processed/ml_ready.parquet
```

## Outputs

- `ml/data/raw/who_api_probe.json`: endpoint counts/date ranges
- `ml/data/raw/y_who_news_raw.json`: raw normalized Y rows
- `ml/data/processed/x_candidates.parquet`: candidate X rows
- `ml/data/processed/y_candidates.parquet`: typed Y rows
- `ml/data/processed/ml_ready.parquet`: final train-ready frame
