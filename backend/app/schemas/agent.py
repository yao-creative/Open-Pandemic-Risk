from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AgentQueryRequest(BaseModel):
    tool: str = Field(pattern="^(read_run_results|explore_db_readonly|search_exa)$")
    args: dict[str, Any] = Field(default_factory=dict)


class AgentQueryResponse(BaseModel):
    tool: str
    result: dict[str, Any]
