from __future__ import annotations

import argparse
import json
import pickle
from pathlib import Path

import polars as pl


def _extract_feature_names(summary: dict) -> list[str]:
    coef = summary.get("coefficients") or {}
    names: list[str] = []
    for key in coef.keys():
        if key == "const":
            continue
        if key.startswith("treatment_"):
            names.append(key.replace("treatment_", "", 1))
        elif key.startswith("control_"):
            names.append(key.replace("control_", "", 1))
    seen: set[str] = set()
    out: list[str] = []
    for name in names:
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path, default=Path("ml/models/double_lasso_summary.json"))
    parser.add_argument("--train-data", type=Path, default=Path("ml/data/processed/ml_ready_slim_us_large.parquet"))
    parser.add_argument("--model-out", type=Path, default=Path("ml/models/double_lasso_model.pkl"))
    parser.add_argument("--scaler-out", type=Path, default=Path("ml/models/double_lasso_scaler.pkl"))
    parser.add_argument("--manifest-out", type=Path, default=Path("ml/models/double_lasso_manifest.json"))
    parser.add_argument("--model-version", type=str, default="v1")
    args = parser.parse_args()

    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    feature_order = _extract_feature_names(summary)

    coefficients_raw = summary.get("coefficients") or {}
    intercept = float(coefficients_raw.get("const", 0.0))
    coefficients: dict[str, float] = {}
    for name in feature_order:
        if name == "f_title_has_us_kw":
            coefficients[name] = float(coefficients_raw.get("treatment_f_title_has_us_kw", 0.0))
        else:
            coefficients[name] = float(coefficients_raw.get(f"control_{name}", 0.0))

    train_df = pl.read_parquet(args.train_data)
    means = {
        name: float(train_df.select(pl.col(name).cast(pl.Float64).mean()).item()) if name in train_df.columns else 0.0
        for name in feature_order
    }
    stds = {
        name: float(train_df.select(pl.col(name).cast(pl.Float64).std()).item()) if name in train_df.columns else 1.0
        for name in feature_order
    }
    scales = {name: (std if std and std > 0 else 1.0) for name, std in stds.items()}

    model_bundle = {
        "model_name": "double_lasso_linear",
        "model_version": args.model_version,
        "feature_order": feature_order,
        "intercept": intercept,
        "coefficients": coefficients,
        "link": "sigmoid",
    }
    scaler_bundle = {
        "feature_order": feature_order,
        "means": means,
        "scales": scales,
    }
    manifest = {
        "model_name": model_bundle["model_name"],
        "model_version": model_bundle["model_version"],
        "target_name": "target_t72h",
        "feature_order": feature_order,
        "artifact_paths": {
            "model_pickle": str(args.model_out),
            "scaler_pickle": str(args.scaler_out),
        },
    }

    args.model_out.parent.mkdir(parents=True, exist_ok=True)
    with args.model_out.open("wb") as f:
        pickle.dump(model_bundle, f)

    args.scaler_out.parent.mkdir(parents=True, exist_ok=True)
    with args.scaler_out.open("wb") as f:
        pickle.dump(scaler_bundle, f)

    args.manifest_out.parent.mkdir(parents=True, exist_ok=True)
    args.manifest_out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"wrote model bundle to {args.model_out}")
    print(f"wrote scaler bundle to {args.scaler_out}")
    print(f"wrote manifest to {args.manifest_out}")


if __name__ == "__main__":
    main()
