from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

import httpx
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.clients import ExaClient
from app.models import (
    AgentToolAudit,
    ContextDump,
    EnrichmentFinding,
    EnrichmentReport,
    EnrichmentRun,
    ExaCitation,
    IndicatorSnapshot,
    PipelineRun,
)
from app.settings import Settings


@dataclass
class AgentState:
    enrichment_run_id: int
    pipeline_run_id: int
    snapshot_ref_id: int | None
    max_steps: int
    max_targets: int
    max_exa_calls: int
    steps_used: int = 0
    exa_calls_used: int = 0


class BaseTool(ABC):
    name: str

    @abstractmethod
    def execute(self, db: Session, *, settings: Settings, state: AgentState, args: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


def _write_tool_audit(
    db: Session,
    *,
    tool_name: str,
    args: dict[str, Any],
    started: float,
    success: bool,
    error_summary: str | None,
) -> None:
    elapsed = int((perf_counter() - started) * 1000)
    db.add(
        AgentToolAudit(
            tool_name=tool_name,
            requested_at=datetime.now(tz=UTC),
            duration_ms=elapsed,
            success=success,
            args_json=args,
            error_summary=error_summary,
        )
    )


class ReadSnapshotContextTool(BaseTool):
    name = "read_snapshot_context"

    def execute(self, db: Session, *, settings: Settings, state: AgentState, args: dict[str, Any]) -> dict[str, Any]:
        snapshot_ref_id = state.snapshot_ref_id
        if snapshot_ref_id is None:
            snapshot_ref_id = db.execute(
                select(PipelineRun.id)
                .where(PipelineRun.pipeline_name == "phase1_sync_ingestion")
                .order_by(desc(PipelineRun.id))
                .limit(1)
            ).scalar_one_or_none()

        state.snapshot_ref_id = snapshot_ref_id

        rows = db.execute(
            select(IndicatorSnapshot.country_code, IndicatorSnapshot.indicator_code, IndicatorSnapshot.value)
            .where(IndicatorSnapshot.value.is_not(None))
            .order_by(desc(IndicatorSnapshot.id))
            .limit(settings.agent_snapshot_context_limit)
        ).all()
        indicators = [
            {
                "country_code": country_code,
                "indicator_code": indicator_code,
                "value": float(value) if value is not None else None,
            }
            for country_code, indicator_code, value in rows
        ]

        target_candidates: list[str] = []
        for item in indicators:
            country_code = item.get("country_code")
            if country_code and country_code not in target_candidates:
                target_candidates.append(country_code)

        if not target_candidates:
            target_candidates = ["global"]

        context = {
            "snapshot_ref_id": snapshot_ref_id,
            "generated_at": datetime.now(tz=UTC).isoformat(),
            "indicator_samples": indicators,
            "target_candidates": target_candidates,
        }

        existing = db.execute(select(ContextDump).where(ContextDump.enrichment_run_id == state.enrichment_run_id)).scalar_one_or_none()
        if existing is None:
            db.add(
                ContextDump(
                    enrichment_run_id=state.enrichment_run_id,
                    context_json=context,
                    created_at=datetime.now(tz=UTC),
                )
            )
        else:
            existing.context_json = context
        return context


class SelectEnrichmentTargetsTool(BaseTool):
    name = "select_enrichment_targets"

    def execute(self, db: Session, *, settings: Settings, state: AgentState, args: dict[str, Any]) -> dict[str, Any]:
        context = args["context"]
        targets = []
        for target_key in context.get("target_candidates", []):
            if len(targets) >= state.max_targets:
                break
            query = settings.exa_default_query if target_key == "global" else f"{settings.exa_default_query} {target_key}"
            targets.append({"target_key": target_key, "query": query})
        return {"targets": targets}


class SearchExaTool(BaseTool):
    name = "search_exa"

    def execute(self, db: Session, *, settings: Settings, state: AgentState, args: dict[str, Any]) -> dict[str, Any]:
        if not settings.exa_api_key:
            raise ValueError("exa_api_key is not configured")
        client = ExaClient(
            api_url=settings.exa_api_url,
            api_key=settings.exa_api_key,
            timeout_seconds=settings.agent_query_timeout_seconds,
        )
        requested_results = int(args.get("num_results") or settings.exa_num_results)
        bounded_results = min(max(requested_results, 1), settings.agent_row_limit)
        try:
            rows = client.search(query=str(args["query"]), num_results=bounded_results)
        except httpx.HTTPError as exc:
            raise RuntimeError(f"search_exa upstream error: {exc}") from exc
        return {
            "query": str(args["query"]),
            "results": [{"url": item.url, "title": item.title, "snippet": item.snippet} for item in rows],
        }


class PersistFindingTool(BaseTool):
    name = "persist_finding"

    def execute(self, db: Session, *, settings: Settings, state: AgentState, args: dict[str, Any]) -> dict[str, Any]:
        target_key = str(args["target_key"])
        exa_payload = args["exa_payload"]
        finding = EnrichmentFinding(
            enrichment_run_id=state.enrichment_run_id,
            target_key=target_key,
            query=str(exa_payload["query"]),
            finding_json=exa_payload,
            created_at=datetime.now(tz=UTC),
        )
        db.add(finding)
        citation_rows = 0
        for item in exa_payload["results"]:
            db.add(
                ExaCitation(
                    pipeline_run_id=state.pipeline_run_id,
                    url=item["url"],
                    title=item.get("title"),
                    snippet=item.get("snippet"),
                    query=str(exa_payload["query"]),
                    created_at=datetime.now(tz=UTC),
                )
            )
            citation_rows += 1
        return {"citation_rows": citation_rows}


class PersistReportTool(BaseTool):
    name = "persist_report"

    def execute(self, db: Session, *, settings: Settings, state: AgentState, args: dict[str, Any]) -> dict[str, Any]:
        findings = db.execute(
            select(EnrichmentFinding).where(EnrichmentFinding.enrichment_run_id == state.enrichment_run_id)
        ).scalars().all()
        target_keys = sorted({item.target_key for item in findings})
        summary = {
            "enrichment_run_id": state.enrichment_run_id,
            "snapshot_ref_id": state.snapshot_ref_id,
            "target_count": len(target_keys),
            "targets": target_keys,
            "finding_count": len(findings),
            "exa_calls_used": state.exa_calls_used,
            "steps_used": state.steps_used,
            "generated_at": datetime.now(tz=UTC).isoformat(),
        }
        existing = db.execute(
            select(EnrichmentReport).where(EnrichmentReport.enrichment_run_id == state.enrichment_run_id)
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                EnrichmentReport(
                    enrichment_run_id=state.enrichment_run_id,
                    summary_json=summary,
                    created_at=datetime.now(tz=UTC),
                )
            )
        else:
            existing.summary_json = summary
        return summary


class AgentRunner:
    def __init__(self, *, settings: Settings) -> None:
        self.settings = settings
        self.read_context_tool = ReadSnapshotContextTool()
        self.select_targets_tool = SelectEnrichmentTargetsTool()
        self.search_exa_tool = SearchExaTool()
        self.persist_finding_tool = PersistFindingTool()
        self.persist_report_tool = PersistReportTool()

    def _run_tool(self, db: Session, state: AgentState, tool: BaseTool, args: dict[str, Any]) -> dict[str, Any]:
        started = perf_counter()
        try:
            result = tool.execute(db, settings=self.settings, state=state, args=args)
            _write_tool_audit(
                db,
                tool_name=tool.name,
                args={"enrichment_run_id": state.enrichment_run_id, **args},
                started=started,
                success=True,
                error_summary=None,
            )
            return result
        except Exception as exc:
            _write_tool_audit(
                db,
                tool_name=tool.name,
                args={"enrichment_run_id": state.enrichment_run_id, **args},
                started=started,
                success=False,
                error_summary=str(exc),
            )
            raise

    def run(self, db: Session, *, enrichment_run_id: int) -> None:
        run = db.get(EnrichmentRun, enrichment_run_id)
        if run is None:
            return
        if run.status not in {"queued", "running"}:
            return

        state = AgentState(
            enrichment_run_id=run.id,
            pipeline_run_id=run.pipeline_run_id,
            snapshot_ref_id=run.snapshot_ref_id,
            max_steps=run.max_steps,
            max_targets=run.max_targets,
            max_exa_calls=run.max_exa_calls,
            steps_used=run.steps_used,
            exa_calls_used=run.exa_calls_used,
        )

        run.status = "running"
        run.started_at = run.started_at or datetime.now(tz=UTC)
        run.updated_at = datetime.now(tz=UTC)
        db.commit()

        try:
            context = self._run_tool(db, state, self.read_context_tool, {})
            state.steps_used += 1
            run.snapshot_ref_id = state.snapshot_ref_id
            run.steps_used = state.steps_used
            run.updated_at = datetime.now(tz=UTC)
            db.commit()

            target_payload = self._run_tool(db, state, self.select_targets_tool, {"context": context})
            state.steps_used += 1
            run.steps_used = state.steps_used
            run.updated_at = datetime.now(tz=UTC)
            db.commit()

            for target in target_payload["targets"]:
                if state.steps_used >= state.max_steps:
                    break
                if state.exa_calls_used >= state.max_exa_calls:
                    break
                exa_payload = self._run_tool(
                    db,
                    state,
                    self.search_exa_tool,
                    {"query": target["query"], "num_results": self.settings.exa_num_results},
                )
                state.steps_used += 1
                state.exa_calls_used += 1
                self._run_tool(
                    db,
                    state,
                    self.persist_finding_tool,
                    {"target_key": target["target_key"], "exa_payload": exa_payload},
                )
                state.steps_used += 1
                run.steps_used = state.steps_used
                run.exa_calls_used = state.exa_calls_used
                run.updated_at = datetime.now(tz=UTC)
                db.commit()

            self._run_tool(db, state, self.persist_report_tool, {})
            state.steps_used += 1
            run.steps_used = state.steps_used
            run.exa_calls_used = state.exa_calls_used
            run.status = "completed"
            run.finished_at = datetime.now(tz=UTC)
            run.updated_at = datetime.now(tz=UTC)
            run.error_summary = None
            db.commit()
        except Exception as exc:
            run.steps_used = state.steps_used
            run.exa_calls_used = state.exa_calls_used
            run.status = "failed"
            run.finished_at = datetime.now(tz=UTC)
            run.updated_at = datetime.now(tz=UTC)
            run.error_summary = str(exc)
            db.commit()
