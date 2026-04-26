from __future__ import annotations

from app.pipeline.stages.contracts import PipelineStage
from app.pipeline.stages.enrich_snapshot_agent import EnrichSnapshotAgentStage
from app.pipeline.stages.ingest_snapshot import IngestSnapshotStage
from app.pipeline.stages.recommend_response_agent import RecommendResponseAgentStage


class StageRegistry:
    def __init__(self) -> None:
        self._stages: dict[str, PipelineStage] = {
            "ingest_snapshot": IngestSnapshotStage(),
            "enrich_snapshot_agent": EnrichSnapshotAgentStage(),
            "recommend_response_agent": RecommendResponseAgentStage(),
        }

    def list_stages(self) -> list[PipelineStage]:
        return list(self._stages.values())

    def get(self, stage_name: str) -> PipelineStage | None:
        return self._stages.get(stage_name)
