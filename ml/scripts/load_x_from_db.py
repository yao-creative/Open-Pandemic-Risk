from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import polars as pl


def load_x_rows(
    db_path: Path,
    *,
    profile_name: str,
    snapshot_ref_id: int | None,
) -> pl.DataFrame:
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, indicator_code, country_code, period_date, value, unit, dim_json
        FROM indicator_snapshot
        WHERE dim_json IS NOT NULL
        """
    )
    rows = cur.fetchall()
    conn.close()

    records = []
    for row in rows:
        dim_json = row[6]
        try:
            meta = json.loads(dim_json) if isinstance(dim_json, str) else dict(dim_json)
        except Exception:
            continue

        if str(meta.get("_profile_name")) != profile_name:
            continue

        row_snapshot_ref = meta.get("_snapshot_ref_id")
        if snapshot_ref_id is not None and int(row_snapshot_ref or -1) != snapshot_ref_id:
            continue

        records.append(
            {
                "snapshot_row_id": row[0],
                "indicator_code": row[1],
                "country_code": row[2],
                "period_date": row[3],
                "value": row[4],
                "unit": row[5],
                "profile_name": meta.get("_profile_name"),
                "profile_category": meta.get("_profile_category"),
                "snapshot_ref_id": row_snapshot_ref,
            }
        )

    if not records:
        return pl.DataFrame(
            schema={
                "snapshot_row_id": pl.Int64,
                "indicator_code": pl.Utf8,
                "country_code": pl.Utf8,
                "period_date": pl.Utf8,
                "value": pl.Float64,
                "unit": pl.Utf8,
                "profile_name": pl.Utf8,
                "profile_category": pl.Utf8,
                "snapshot_ref_id": pl.Int64,
            }
        )

    return pl.DataFrame(records)


def main() -> None:
    parser = argparse.ArgumentParser(description="Load X candidate rows from indicator_snapshot into parquet.")
    parser.add_argument("--db-path", type=Path, default=Path("backend/app.db"))
    parser.add_argument("--out", type=Path, default=Path("ml/data/processed/x_candidates.parquet"))
    parser.add_argument("--profile-name", type=str, default="who_surveillance_mvp_v1")
    parser.add_argument("--snapshot-ref-id", type=int, default=None)
    args = parser.parse_args()

    df = load_x_rows(
        args.db_path,
        profile_name=args.profile_name,
        snapshot_ref_id=args.snapshot_ref_id,
    )

    if df.height > 0:
        df = df.with_columns(
            pl.col("period_date").str.strptime(pl.Datetime, strict=False, exact=False),
            pl.col("value").cast(pl.Float64, strict=False),
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(args.out)
    print(f"wrote {df.height} rows to {args.out}")


if __name__ == "__main__":
    main()
