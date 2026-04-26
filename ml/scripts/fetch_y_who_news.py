from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from urllib.parse import urlencode

import polars as pl


def _fetch_json(url: str) -> dict:
    payload = subprocess.run(["curl", "-sS", url], check=True, capture_output=True, text=True).stdout
    return json.loads(payload)


def _fetch_news_rows(endpoint: str, *, top: int) -> list[dict]:
    query = urlencode({"$top": top})
    payload = _fetch_json(f"{endpoint}?{query}")
    return list(payload.get("value", []))


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Y candidate labels from WHO DON/Emergencies APIs.")
    parser.add_argument("--out-json", type=Path, default=Path("ml/data/raw/y_who_news_raw.json"))
    parser.add_argument("--out-parquet", type=Path, default=Path("ml/data/processed/y_candidates.parquet"))
    parser.add_argument("--top", type=int, default=100)
    args = parser.parse_args()

    dons_endpoint = "https://www.who.int/api/news/dons"
    emergencies_endpoint = "https://www.who.int/api/news/emergencies"

    dons_rows = _fetch_news_rows(dons_endpoint, top=args.top)
    source = "dons"
    rows = dons_rows
    if not rows:
        rows = _fetch_news_rows(emergencies_endpoint, top=args.top)
        source = "emergencies"

    normalized = []
    for row in rows:
        normalized.append(
            {
                "y_source": source,
                "record_id": row.get("Id") or row.get("id"),
                "title": row.get("Title"),
                "publication_ts": row.get("PublicationDateAndTime") or row.get("PublicationDate"),
                "new_outbreak": row.get("NewOutbreak"),
                "who_risk_assessment": row.get("WHORiskAssessment") or row.get("EmergencyRatingTextual"),
                "emergency_start_ts": row.get("EmergencyStartDate"),
                "emergency_end_ts": row.get("EmergencyEndDate"),
                "summary": row.get("Summary"),
                "overview": row.get("Overview"),
                "raw_json": row,
            }
        )

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(normalized, indent=2), encoding="utf-8")

    df = pl.DataFrame(normalized).with_columns(pl.col("new_outbreak").cast(pl.Boolean, strict=False))
    args.out_parquet.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(args.out_parquet)

    print(f"source={source} rows={df.height} out={args.out_parquet}")


if __name__ == "__main__":
    main()
