from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import polars as pl


def build_panel(raw_json: Path) -> pl.DataFrame:
    payload = json.loads(raw_json.read_text())
    rows = payload.get("value", [])

    base = pl.DataFrame(
        {
            "country_code": [str(r.get("SpatialDim") or "UNK") for r in rows],
            "year": [int(r.get("TimeDim")) if r.get("TimeDim") is not None else None for r in rows],
            "cases": [float(r.get("NumericValue")) if r.get("NumericValue") is not None else None for r in rows],
            "region_code": [str(r.get("ParentLocationCode") or "UNK") for r in rows],
        }
    ).filter(pl.col("year").is_not_null() & pl.col("cases").is_not_null())

    base = base.sort(["country_code", "year"]).with_columns(
        pl.col("cases").log1p().alias("f_case_count_log"),
        pl.col("cases").shift(1).over("country_code").alias("f_prev_year_cases"),
        pl.col("cases").rolling_mean(window_size=3, min_samples=1).over("country_code").alias("f_country_3yr_mean"),
        (pl.col("cases") - pl.col("cases").shift(1).over("country_code")).alias("f_case_accel"),
        (pl.col("country_code") == "USA").cast(pl.Int64).alias("f_is_usa"),
        pl.col("cases").shift(-1).over("country_code").alias("next_year_cases"),
    )

    # Future spike target from next-year measles reported cases.
    panel = base.with_columns(
        pl.when(pl.col("next_year_cases").is_null())
        .then(0)
        .when(pl.col("next_year_cases") >= pl.col("cases") * 1.25)
        .then(1)
        .otherwise(0)
        .cast(pl.Int64)
        .alias("target_t72h")
    )

    panel = panel.with_columns(
        (pl.col("cases") > 0).cast(pl.Int64).alias("f_title_has_outbreak_kw"),
        pl.col("f_is_usa").alias("f_title_has_us_kw"),
    ).with_columns(
        (
            pl.col("target_t72h") * 3
            + pl.col("f_title_has_outbreak_kw") * 2
            + pl.col("f_title_has_us_kw")
        ).cast(pl.Int64).alias("intervention_priority_score")
    )

    slim = panel.select(
        [
            (pl.col("country_code") + pl.lit("_") + pl.col("year").cast(pl.Utf8)).alias("record_id"),
            pl.datetime(pl.col("year"), pl.lit(1), pl.lit(1), time_zone="UTC").alias("publication_ts"),
            (pl.lit("Measles reported cases signal ") + pl.col("country_code")).alias("title"),
            pl.when(pl.col("region_code") == "AMR").then(1).otherwise(2).alias("f_title_topic_code"),
            pl.col("f_title_has_outbreak_kw"),
            pl.col("f_case_count_log").round(6).alias("f_title_word_count"),
            ((pl.col("year") - 1) % 4 + 1).cast(pl.Int64).alias("f_pub_quarter"),
            pl.col("f_title_has_us_kw"),
            pl.col("target_t72h"),
            pl.col("intervention_priority_score"),
            pl.col("f_case_count_log"),
            pl.col("f_prev_year_cases").fill_null(0.0),
            pl.col("f_country_3yr_mean").fill_null(0.0),
            pl.col("f_case_accel").fill_null(0.0),
            pl.col("f_is_usa"),
            pl.col("country_code"),
            pl.col("year"),
            pl.col("cases"),
        ]
    )
    return slim


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("ml/data/processed/ml_ready_slim_us_large.parquet"))
    args = parser.parse_args()

    df = build_panel(args.raw)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(args.out)
    print(f"wrote {df.height} rows to {args.out}")
    print(df.select(pl.col("target_t72h").mean().alias("target_rate")))


if __name__ == "__main__":
    main()
