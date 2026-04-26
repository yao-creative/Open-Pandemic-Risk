from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import polars as pl
import statsmodels.api as sm
from sklearn.linear_model import LassoCV
from sklearn.preprocessing import StandardScaler


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("ml/data/processed/ml_ready_slim_us_large.parquet"))
    parser.add_argument("--out", type=Path, default=Path("ml/models/double_lasso_summary.json"))
    args = parser.parse_args()

    df = pl.read_parquet(args.data)

    # Treatment D and controls X for double lasso; outcome Y is target_t72h.
    y = df["target_t72h"].to_numpy()
    d = df["f_title_has_us_kw"].to_numpy().astype(float)
    x_cols = ["f_title_topic_code", "f_title_has_outbreak_kw", "f_title_word_count", "f_pub_quarter", "f_case_accel"]
    X = df.select(x_cols).to_numpy().astype(float)

    scaler_x = StandardScaler()
    Xs = scaler_x.fit_transform(X)

    # Lasso 1: D ~ X
    lasso_d = LassoCV(cv=5, random_state=42, n_alphas=100, max_iter=20000)
    lasso_d.fit(Xs, d)
    sel_d = {x_cols[i] for i, c in enumerate(lasso_d.coef_) if abs(c) > 1e-8}

    # Lasso 2: Y ~ X
    lasso_y = LassoCV(cv=5, random_state=42, n_alphas=100, max_iter=20000)
    lasso_y.fit(Xs, y)
    sel_y = {x_cols[i] for i, c in enumerate(lasso_y.coef_) if abs(c) > 1e-8}

    selected = sorted(sel_d.union(sel_y))
    X_ols = df.select(selected).to_numpy().astype(float) if selected else np.empty((len(df), 0))

    # Final OLS: Y ~ D + selected(X)
    design = np.column_stack([d, X_ols]) if selected else d.reshape(-1, 1)
    design = sm.add_constant(design)
    model = sm.OLS(y, design).fit(cov_type="HC3")

    coef_names = ["const", "treatment_f_title_has_us_kw"] + [f"control_{c}" for c in selected]
    coef_map = {name: float(val) for name, val in zip(coef_names, model.params)}
    pval_map = {name: float(val) for name, val in zip(coef_names, model.pvalues)}

    out = {
        "n_rows": int(len(df)),
        "target_rate": float(np.mean(y)),
        "treatment_rate": float(np.mean(d)),
        "selected_controls_union": selected,
        "lasso_alpha_d": float(lasso_d.alpha_),
        "lasso_alpha_y": float(lasso_y.alpha_),
        "r2": float(model.rsquared),
        "adj_r2": float(model.rsquared_adj),
        "coefficients": coef_map,
        "pvalues": pval_map,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2), encoding="utf-8")

    print(f"wrote double lasso summary to {args.out}")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
