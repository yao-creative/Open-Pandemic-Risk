from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from ml.scripts.labeling import grade3_plus_flag, has_future_start_within, normalize_emergency_rating


TITLE_TOPIC_CODE = {
    "infectious_outbreak": 1,
    "humanitarian_conflict": 2,
    "natural_disaster": 3,
    "system_update": 4,
    "other": 5,
}


def _infer_title_topic(title: str) -> str:
    text = title.lower()
    infectious_terms = (
        "outbreak",
        "ebola",
        "cholera",
        "mpox",
        "covid",
        "influenza",
        "measles",
        "polio",
        "marburg",
        "dengue",
        "virus",
    )
    if any(term in text for term in infectious_terms):
        return "infectious_outbreak"

    humanitarian_terms = ("crisis", "conflict", "humanitarian", "violence")
    if any(term in text for term in humanitarian_terms):
        return "humanitarian_conflict"

    disaster_terms = ("earthquake", "flood", "cyclone", "hurricane", "storm")
    if any(term in text for term in disaster_terms):
        return "natural_disaster"

    system_terms = ("update", "situation", "brief", "response")
    if any(term in text for term in system_terms):
        return "system_update"

    return "other"


def _build_x_features(x_df: pl.DataFrame) -> pl.DataFrame:
    if x_df.height == 0:
        return pl.DataFrame(
            {
                "period_date": [],
                "x_value_mean": [],
                "x_value_std": [],
                "x_row_count": [],
                "x_indicator_nunique": [],
            },
            schema={
                "period_date": pl.Datetime,
                "x_value_mean": pl.Float64,
                "x_value_std": pl.Float64,
                "x_row_count": pl.Int64,
                "x_indicator_nunique": pl.Int64,
            },
        )

    x_norm = x_df.with_columns(
        pl.col("period_date").cast(pl.Datetime, strict=False).dt.replace_time_zone("UTC"),
        pl.col("value").cast(pl.Float64, strict=False),
    )

    x_clean = x_norm.filter(pl.col("period_date").is_not_null() & pl.col("value").is_not_null()).with_columns(
        pl.col("value").clip(
            pl.col("value").quantile(0.01),
            pl.col("value").quantile(0.99),
        )
    )
    return x_clean.group_by("period_date").agg(
        pl.col("value").mean().alias("x_value_mean"),
        pl.col("value").std().fill_null(0.0).alias("x_value_std"),
        pl.len().alias("x_row_count"),
        pl.col("indicator_code").n_unique().alias("x_indicator_nunique"),
    ).sort("period_date")


def _build_y_labels(y_df: pl.DataFrame) -> pl.DataFrame:
    y_norm = y_df.with_columns(
        pl.col("publication_ts").str.to_datetime(strict=False, time_zone="UTC"),
        pl.col("emergency_start_ts").str.to_datetime(strict=False, time_zone="UTC"),
        pl.col("emergency_end_ts").str.to_datetime(strict=False, time_zone="UTC"),
    )
    y_sorted = y_norm.filter(pl.col("publication_ts").is_not_null()).sort("publication_ts")
    start_times = [v for v in y_sorted.get_column("emergency_start_ts").to_list() if v is not None]

    rows = y_sorted.to_dicts()
    for row in rows:
        rating_norm = normalize_emergency_rating(row.get("who_risk_assessment"))
        pub_dt = row["publication_ts"]

        title_raw = str(row.get("title") or "")
        title_norm = re.sub(r"\s+", " ", title_raw.lower()).strip()
        title_word_count = len([w for w in title_norm.split(" ") if w])
        title_topic = _infer_title_topic(title_norm)

        row["risk_rating_norm"] = rating_norm
        row["y_grade3_plus"] = grade3_plus_flag(rating_norm)
        row["y_event_start_t24h"] = has_future_start_within(pub_dt, start_times, window_hours=24)
        row["y_event_start_t72h"] = has_future_start_within(pub_dt, start_times, window_hours=72)

        row["title_norm"] = title_norm
        row["title_char_len"] = len(title_norm)
        row["title_word_count"] = title_word_count
        row["title_has_outbreak_kw"] = int("outbreak" in title_norm or "upsurge" in title_norm)
        row["title_topic_cat"] = title_topic
        row["title_topic_code"] = TITLE_TOPIC_CODE[title_topic]

        # USA field-worker oriented binary relevance cues.
        us_terms = ("usa", "u.s.", "united states", "cdc", "hhs", "state health")
        row["title_has_us_kw"] = int(any(term in title_norm for term in us_terms))

        row["pub_year"] = pub_dt.year
        row["pub_month"] = pub_dt.month
        row["pub_weekday"] = pub_dt.weekday()
        row["pub_quarter"] = (pub_dt.month - 1) // 3 + 1

        start_dt = row.get("emergency_start_ts")
        row["event_lead_days"] = (start_dt - pub_dt).days if start_dt is not None else None

        # Simple intervention priority score for demo triage.
        row["intervention_priority_score"] = int(
            row["y_grade3_plus"] * 3 + row["title_has_outbreak_kw"] * 2 + row["title_has_us_kw"]
        )

    if not rows:
        return pl.DataFrame(schema=y_norm.schema)

    out = pl.DataFrame(rows).sort("publication_ts")
    title_freq = out.group_by("title_norm").len().rename({"len": "title_freq_count"})
    out = out.join(title_freq, on="title_norm", how="left").with_columns(
        (pl.col("title_freq_count") / pl.lit(out.height)).alias("title_freq_rate")
    )
    return out


def build_ml_ready_frame(x_df: pl.DataFrame, y_df: pl.DataFrame) -> pl.DataFrame:
    x_features = _build_x_features(x_df)
    y_labels = _build_y_labels(y_df)

    if y_labels.height == 0:
        return y_labels
    if x_features.height == 0:
        return y_labels.with_columns(
            pl.lit(None, dtype=pl.Float64).alias("x_value_mean"),
            pl.lit(None, dtype=pl.Float64).alias("x_value_std"),
            pl.lit(None, dtype=pl.Int64).alias("x_row_count"),
            pl.lit(None, dtype=pl.Int64).alias("x_indicator_nunique"),
        )

    return y_labels.join_asof(
        x_features,
        left_on="publication_ts",
        right_on="period_date",
        strategy="backward",
    )


def build_ml_ready_slim_frame(full_df: pl.DataFrame) -> pl.DataFrame:
    # Pruned demo frame: 5 simple features + target + triage field.
    return full_df.select(
        [
            "record_id",
            "publication_ts",
            "title",
            "f_title_topic_code",
            "f_title_has_outbreak_kw",
            "f_title_word_count",
            "f_pub_quarter",
            "f_title_has_us_kw",
            "target_t72h",
            "intervention_priority_score",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Preprocess X and Y candidate datasets into ML-ready frame.")
    parser.add_argument("--x", type=Path, default=Path("ml/data/processed/x_candidates.parquet"))
    parser.add_argument("--y", type=Path, default=Path("ml/data/processed/y_candidates.parquet"))
    parser.add_argument("--out", type=Path, default=Path("ml/data/processed/ml_ready.parquet"))
    parser.add_argument("--out-slim", type=Path, default=Path("ml/data/processed/ml_ready_slim_us.parquet"))
    args = parser.parse_args()

    x_df = pl.read_parquet(args.x)
    y_df = pl.read_parquet(args.y)
    out_df = build_ml_ready_frame(x_df, y_df).with_columns(
        pl.col("title_topic_code").alias("f_title_topic_code"),
        pl.col("title_has_outbreak_kw").alias("f_title_has_outbreak_kw"),
        pl.col("title_word_count").clip(1, 20).alias("f_title_word_count"),
        pl.col("pub_quarter").alias("f_pub_quarter"),
        pl.col("title_has_us_kw").alias("f_title_has_us_kw"),
        pl.col("y_event_start_t72h").alias("target_t72h"),
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    out_df.write_parquet(args.out)

    slim_df = build_ml_ready_slim_frame(out_df)
    args.out_slim.parent.mkdir(parents=True, exist_ok=True)
    slim_df.write_parquet(args.out_slim)

    print(f"wrote {out_df.height} rows to {args.out}")
    print(f"wrote {slim_df.height} rows to {args.out_slim}")


if __name__ == "__main__":
    main()
