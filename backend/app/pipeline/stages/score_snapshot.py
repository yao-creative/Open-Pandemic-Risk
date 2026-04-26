from __future__ import annotations

from datetime import UTC, datetime
import json
import math
import pickle
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.models import IndicatorSnapshot, MlRiskSnapshot, PipelineRunScore

from .contracts import PipelineStage, StageContext, StageResult


class ScoreSnapshotStage(PipelineStage):
    name = "score_snapshot"
    required_inputs = ("snapshot_ref_id", "enrichment_pipeline_run_id")

    def _resolve_path(self, raw: str) -> Path:
        path = Path(raw)
        if path.is_absolute():
            return path
        repo_root = Path(__file__).resolve().parents[4]
        return repo_root / path

    def _load_model_bundle(self, context: StageContext) -> dict[str, Any]:
        model_path = self._resolve_path(context.settings.ml_model_pickle_path)
        with model_path.open("rb") as f:
            model_bundle = pickle.load(f)

        scaler_path = self._resolve_path(context.settings.ml_scaler_pickle_path)
        scaler_bundle: dict[str, Any] | None = None
        if scaler_path.exists():
            with scaler_path.open("rb") as f:
                scaler_bundle = pickle.load(f)

        manifest_path = self._resolve_path(context.settings.ml_model_manifest_path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}

        return {
            "model": model_bundle,
            "scaler": scaler_bundle,
            "manifest": manifest,
        }

    def _collect_snapshot_rows(self, context: StageContext, *, snapshot_ref_id: int, sample_limit: int) -> list[tuple[float, str, datetime | None]]:
        rows = context.db.execute(
            select(IndicatorSnapshot.value, IndicatorSnapshot.country_code, IndicatorSnapshot.period_date, IndicatorSnapshot.dim_json)
            .where(IndicatorSnapshot.value.is_not(None))
            .limit(sample_limit * 20)
        ).all()
        scoped: list[tuple[float, str, datetime | None]] = []
        for value, country_code, period_date, dim_json in rows:
            row_snapshot_ref = None
            if isinstance(dim_json, dict):
                row_snapshot_ref = dim_json.get("_snapshot_ref_id")
            if row_snapshot_ref == snapshot_ref_id:
                scoped.append((float(value), str(country_code or "UNK"), period_date))
            if len(scoped) >= sample_limit:
                break
        return scoped

    def _derive_features(self, scoped_rows: list[tuple[float, str, datetime | None]]) -> dict[str, float]:
        if not scoped_rows:
            return {
                "f_title_topic_code": 5.0,
                "f_title_has_outbreak_kw": 0.0,
                "f_title_word_count": 1.0,
                "f_pub_quarter": float(((datetime.now(tz=UTC).month - 1) // 3) + 1),
                "f_title_has_us_kw": 0.0,
                "f_case_accel": 0.0,
            }

        values = [item[0] for item in scoped_rows]
        countries = [item[1] for item in scoped_rows]
        period_dates = [item[2] for item in scoped_rows if item[2] is not None]

        signal_count = len(values)
        mean_value = sum(values) / signal_count
        max_value = max(values)
        has_us = 1.0 if any(code.upper() in {"USA", "US", "UNITED STATES"} for code in countries) else 0.0

        if max_value >= 80:
            topic_code = 1.0
        elif max_value >= 40:
            topic_code = 2.0
        elif max_value >= 15:
            topic_code = 3.0
        else:
            topic_code = 5.0

        title_word_count = float(max(1, min(20, int(round(math.log1p(max(signal_count, 1)) * 5)))))

        if period_dates:
            latest = max(period_dates)
            quarter = float(((latest.month - 1) // 3) + 1)
        else:
            quarter = float(((datetime.now(tz=UTC).month - 1) // 3) + 1)

        sorted_vals = sorted(values)
        if len(sorted_vals) >= 2:
            case_accel = sorted_vals[-1] - sorted_vals[-2]
        else:
            case_accel = 0.0

        return {
            "f_title_topic_code": topic_code,
            "f_title_has_outbreak_kw": 1.0,
            "f_title_word_count": title_word_count,
            "f_pub_quarter": quarter,
            "f_title_has_us_kw": has_us,
            "f_case_accel": float(case_accel),
        }

    def _predict_risk(self, features: dict[str, float], model_bundle: dict[str, Any], scaler_bundle: dict[str, Any] | None) -> tuple[float, str, float, str]:
        intercept = float(model_bundle.get("intercept", 0.0))
        coefficients = model_bundle.get("coefficients") or {}
        feature_order = model_bundle.get("feature_order") or list(coefficients.keys())

        feature_vector = {name: float(features.get(name, 0.0)) for name in feature_order}
        if scaler_bundle:
            means = scaler_bundle.get("means") or {}
            scales = scaler_bundle.get("scales") or {}
            for name in feature_vector:
                mean = float(means.get(name, 0.0))
                scale = float(scales.get(name, 1.0))
                feature_vector[name] = (feature_vector[name] - mean) / (scale if scale else 1.0)

        raw = intercept
        for name, coef in coefficients.items():
            raw += float(coef) * float(feature_vector.get(name, 0.0))

        risk_value = 1.0 / (1.0 + math.exp(-raw))

        if risk_value >= 0.75:
            risk_band = "critical"
            confidence_band = "high"
        elif risk_value >= 0.5:
            risk_band = "high"
            confidence_band = "medium"
        elif risk_value >= 0.25:
            risk_band = "medium"
            confidence_band = "medium"
        else:
            risk_band = "low"
            confidence_band = "low"

        confidence_score = min(0.99, max(0.05, abs(risk_value - 0.5) * 2.0))
        return risk_value, risk_band, confidence_score, confidence_band

    def run(self, context: StageContext) -> StageResult:
        snapshot_ref_id = int(context.artifacts["snapshot_ref_id"])
        target_pipeline_run_id = int(context.artifacts["enrichment_pipeline_run_id"])
        sample_limit = int(context.params.get("sample_limit") or 100)

        model_artifacts = self._load_model_bundle(context)
        scoped_rows = self._collect_snapshot_rows(context, snapshot_ref_id=snapshot_ref_id, sample_limit=sample_limit)
        features = self._derive_features(scoped_rows)
        risk_value, risk_band, confidence_score, confidence_band = self._predict_risk(
            features,
            model_bundle=model_artifacts["model"],
            scaler_bundle=model_artifacts["scaler"],
        )

        model_name = str(model_artifacts["model"].get("model_name") or "double_lasso_pickle")
        model_version = str(model_artifacts["model"].get("model_version") or "v1")

        now = datetime.now(tz=UTC)

        existing = context.db.execute(
            select(MlRiskSnapshot).where(MlRiskSnapshot.snapshot_ref_id == snapshot_ref_id)
        ).scalar_one_or_none()

        payload = {
            "model_output": {"risk_value": risk_value, "risk_band": risk_band},
            "confidence": {"band": confidence_band, "score": confidence_score},
            "ates": {},
            "features": features,
        }

        if existing is None:
            row = MlRiskSnapshot(
                snapshot_ref_id=snapshot_ref_id,
                model_name=model_name,
                model_version=model_version,
                payload_json=payload,
                created_at=now,
                updated_at=now,
            )
            context.db.add(row)
            context.db.flush()
            ml_snapshot_id = row.id
        else:
            existing.model_name = model_name
            existing.model_version = model_version
            existing.payload_json = payload
            existing.updated_at = now
            ml_snapshot_id = existing.id

        factors = {
            "snapshot_ref_id": snapshot_ref_id,
            "model_name": model_name,
            "model_version": model_version,
            "feature_order": model_artifacts["model"].get("feature_order") or [],
            "features": features,
        }
        context.db.add(
            PipelineRunScore(
                pipeline_run_id=target_pipeline_run_id,
                scored_at=now,
                risk_value=risk_value,
                risk_band=risk_band,
                factors_json=factors,
                model_version=model_version,
            )
        )
        context.db.commit()

        return StageResult(
            status="ok",
            metrics={"records_in": len(scoped_rows), "records_ok": 1, "records_failed": 0},
            artifacts={
                "ml_snapshot_id": ml_snapshot_id,
                "risk_value": risk_value,
                "risk_band": risk_band,
                "model_name": model_name,
                "model_version": model_version,
            },
        )
