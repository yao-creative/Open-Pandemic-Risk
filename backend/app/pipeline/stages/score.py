from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from statistics import fmean

from dataclasses import dataclass, field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import CountryRiskResult, WhoObservation

MODEL_VERSION = "country-risk-v1"
FACTOR_WEIGHTS = {
    "disease_burden": 0.65,
    "surveillance_readiness": 0.35,
}


@dataclass(frozen=True)
class CountryIndicatorPoint:
    country_code: str
    indicator_code: str
    indicator_label: str
    factor_group: str
    risk_direction: str
    numeric_value: float
    low_value: float | None
    high_value: float | None
    period_date: datetime | None
    source_date: datetime | None


@dataclass
class ScoreStageResult:
    status: str
    records_in: int
    records_ok: int
    records_failed: int
    countries_ranked: int = 0
    top_countries: list[dict[str, object]] = field(default_factory=list)
    error: str | None = None


def _safe_mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return float(fmean(values))


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _as_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime(1970, 1, 1, tzinfo=UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def classify_risk_band(risk_value: float) -> str:
    if risk_value >= 0.75:
        return "critical"
    if risk_value >= 0.5:
        return "high"
    if risk_value >= 0.25:
        return "medium"
    return "low"


def _effective_date(point: CountryIndicatorPoint) -> datetime:
    return _as_utc(point.period_date or point.source_date)


def _uncertainty_penalty(point: CountryIndicatorPoint) -> float:
    if point.low_value is None or point.high_value is None:
        return 0.0
    denominator = max(abs(point.numeric_value), 1.0)
    ratio = (point.high_value - point.low_value) / denominator
    return clamp(ratio / 2.0)


def _collapse_latest_points(rows: list[WhoObservation]) -> list[CountryIndicatorPoint]:
    grouped: dict[tuple[str, str], list[WhoObservation]] = defaultdict(list)
    for row in rows:
        grouped[(row.country_code, row.indicator_code)].append(row)

    points: list[CountryIndicatorPoint] = []
    for items in grouped.values():
        latest_timestamp = max(_as_utc(item.period_date or item.source_date) for item in items)
        latest_items = [item for item in items if _as_utc(item.period_date or item.source_date) == latest_timestamp]
        numeric_values = [float(item.numeric_value) for item in latest_items if item.numeric_value is not None]
        if not numeric_values:
            continue
        low_values = [float(item.low_value) for item in latest_items if item.low_value is not None]
        high_values = [float(item.high_value) for item in latest_items if item.high_value is not None]
        exemplar = latest_items[0]
        points.append(
            CountryIndicatorPoint(
                country_code=exemplar.country_code,
                indicator_code=exemplar.indicator_code,
                indicator_label=exemplar.indicator_label,
                factor_group=exemplar.factor_group,
                risk_direction=exemplar.risk_direction,
                numeric_value=_safe_mean(numeric_values),
                low_value=_safe_mean(low_values) if low_values else None,
                high_value=_safe_mean(high_values) if high_values else None,
                period_date=exemplar.period_date,
                source_date=exemplar.source_date,
            )
        )
    return points


def _normalized_indicator_risk(point: CountryIndicatorPoint, indicator_values: list[float]) -> float:
    minimum = min(indicator_values)
    maximum = max(indicator_values)
    if maximum <= minimum:
        baseline = 0.5
    else:
        baseline = (point.numeric_value - minimum) / (maximum - minimum)
    if point.risk_direction == "higher_is_better":
        return clamp(1.0 - baseline)
    return clamp(baseline)


def _recency_weight(point: CountryIndicatorPoint, latest_per_indicator: dict[str, datetime]) -> float:
    latest = latest_per_indicator[point.indicator_code]
    age_years = max((latest - _effective_date(point)).days, 0) / 365.25
    return clamp(1.0 - (0.15 * age_years), low=0.4, high=1.0)


def _weighted_average(values: list[tuple[float, float]]) -> float:
    weighted_sum = sum(value * weight for value, weight in values if weight > 0)
    weight_sum = sum(weight for _, weight in values if weight > 0)
    if weight_sum <= 0:
        return 0.0
    return clamp(weighted_sum / weight_sum)


def _calculate_country_results(points: list[CountryIndicatorPoint]) -> list[dict[str, object]]:
    if not points:
        return []

    by_indicator: dict[str, list[CountryIndicatorPoint]] = defaultdict(list)
    expected_by_factor: dict[str, set[str]] = defaultdict(set)
    latest_per_indicator: dict[str, datetime] = {}

    for point in points:
        by_indicator[point.indicator_code].append(point)
        expected_by_factor[point.factor_group].add(point.indicator_code)
        latest_per_indicator[point.indicator_code] = max(
            latest_per_indicator.get(point.indicator_code, datetime(1970, 1, 1, tzinfo=UTC)),
            _effective_date(point),
        )

    country_contributors: dict[str, list[dict[str, object]]] = defaultdict(list)
    country_factor_scores: dict[str, dict[str, list[tuple[float, float]]]] = defaultdict(lambda: defaultdict(list))
    country_recency: dict[str, list[float]] = defaultdict(list)
    country_uncertainty_quality: dict[str, list[float]] = defaultdict(list)
    country_indicator_codes: dict[str, set[str]] = defaultdict(set)

    for point in points:
        indicator_values = [item.numeric_value for item in by_indicator[point.indicator_code]]
        normalized_risk = _normalized_indicator_risk(point, indicator_values)
        uncertainty_penalty = _uncertainty_penalty(point)
        recency_weight = _recency_weight(point, latest_per_indicator)
        contribution_weight = max(0.2, recency_weight * (1.0 - (0.5 * uncertainty_penalty)))
        factor_weight = FACTOR_WEIGHTS.get(point.factor_group, 0.5)
        contribution_score = normalized_risk * contribution_weight * factor_weight

        country_factor_scores[point.country_code][point.factor_group].append((normalized_risk, contribution_weight))
        country_recency[point.country_code].append(recency_weight)
        country_uncertainty_quality[point.country_code].append(1.0 - uncertainty_penalty)
        country_indicator_codes[point.country_code].add(point.indicator_code)
        country_contributors[point.country_code].append(
            {
                "indicator_code": point.indicator_code,
                "indicator_label": point.indicator_label,
                "factor_group": point.factor_group,
                "risk_direction": point.risk_direction,
                "raw_value": point.numeric_value,
                "period_date": point.period_date.isoformat() if point.period_date is not None else None,
                "source_date": point.source_date.isoformat() if point.source_date is not None else None,
                "normalized_risk": round(normalized_risk, 4),
                "uncertainty_penalty": round(uncertainty_penalty, 4),
                "recency_weight": round(recency_weight, 4),
                "contribution_weight": round(contribution_weight, 4),
                "contribution_score": round(contribution_score, 4),
            }
        )

    total_expected_indicators = len({point.indicator_code for point in points})
    results: list[dict[str, object]] = []

    for country_code, factor_scores in country_factor_scores.items():
        disease_burden_score = _weighted_average(factor_scores.get("disease_burden", []))
        surveillance_readiness_score = _weighted_average(factor_scores.get("surveillance_readiness", []))
        available_factor_weights = [
            (disease_burden_score, FACTOR_WEIGHTS["disease_burden"]) if factor_scores.get("disease_burden") else None,
            (surveillance_readiness_score, FACTOR_WEIGHTS["surveillance_readiness"]) if factor_scores.get("surveillance_readiness") else None,
        ]
        base_risk = _weighted_average([item for item in available_factor_weights if item is not None])

        indicator_coverage = len(country_indicator_codes[country_code]) / max(total_expected_indicators, 1)
        freshness_score = _safe_mean(country_recency[country_code])
        uncertainty_quality = _safe_mean(country_uncertainty_quality[country_code])
        confidence_score = clamp((0.45 * indicator_coverage) + (0.35 * freshness_score) + (0.20 * uncertainty_quality))
        risk_score = clamp(base_risk * (0.55 + (0.45 * confidence_score)))
        risk_band = classify_risk_band(risk_score)

        factor_payload = {
            "disease_burden": {
                "score": round(disease_burden_score, 4),
                "indicator_count": len(factor_scores.get("disease_burden", [])),
                "expected_indicator_count": len(expected_by_factor.get("disease_burden", set())),
            },
            "surveillance_readiness": {
                "score": round(surveillance_readiness_score, 4),
                "indicator_count": len(factor_scores.get("surveillance_readiness", [])),
                "expected_indicator_count": len(expected_by_factor.get("surveillance_readiness", set())),
            },
            "confidence": {
                "score": round(confidence_score, 4),
                "indicator_coverage": round(indicator_coverage, 4),
                "freshness_score": round(freshness_score, 4),
                "uncertainty_quality": round(uncertainty_quality, 4),
            },
        }

        contributors = sorted(
            country_contributors[country_code],
            key=lambda item: float(item["contribution_score"]),
            reverse=True,
        )
        results.append(
            {
                "country_code": country_code,
                "risk_score": round(risk_score, 4),
                "risk_band": risk_band,
                "disease_burden_score": round(disease_burden_score, 4),
                "surveillance_readiness_score": round(surveillance_readiness_score, 4),
                "confidence_score": round(confidence_score, 4),
                "factors_json": {
                    "factors": factor_payload,
                    "top_contributors": contributors[:5],
                    "indicator_details": contributors,
                    "model_version": MODEL_VERSION,
                },
            }
        )

    return sorted(results, key=lambda item: (float(item["risk_score"]), float(item["confidence_score"])), reverse=True)


def score_pipeline_run(
    db: Session,
    *,
    pipeline_run_id: int,
    snapshot_ref_id: int | None = None,
    sample_limit: int = 10,
) -> ScoreStageResult:
    source_run_id = snapshot_ref_id or pipeline_run_id
    rows = db.execute(
        select(WhoObservation)
        .where(WhoObservation.pipeline_run_id == source_run_id)
        .where(WhoObservation.numeric_value.is_not(None))
        .order_by(WhoObservation.id.asc())
    ).scalars().all()
    points = _collapse_latest_points(rows)
    ranked = _calculate_country_results(points)

    db.execute(delete(CountryRiskResult).where(CountryRiskResult.pipeline_run_id == pipeline_run_id))
    for item in ranked:
        db.add(
            CountryRiskResult(
                pipeline_run_id=pipeline_run_id,
                country_code=str(item["country_code"]),
                scored_at=datetime.now(tz=UTC),
                risk_score=float(item["risk_score"]),
                risk_band=str(item["risk_band"]),
                disease_burden_score=float(item["disease_burden_score"]),
                surveillance_readiness_score=float(item["surveillance_readiness_score"]),
                confidence_score=float(item["confidence_score"]),
                factors_json=dict(item["factors_json"]),
                model_version=MODEL_VERSION,
            )
        )

    return ScoreStageResult(
        status="ok",
        records_in=len(points),
        records_ok=len(ranked),
        records_failed=0,
        countries_ranked=len(ranked),
        top_countries=[
            {
                "country_code": item["country_code"],
                "risk_score": item["risk_score"],
                "risk_band": item["risk_band"],
                "disease_burden_score": item["disease_burden_score"],
                "surveillance_readiness_score": item["surveillance_readiness_score"],
                "confidence_score": item["confidence_score"],
            }
            for item in ranked[:sample_limit]
        ],
    )
