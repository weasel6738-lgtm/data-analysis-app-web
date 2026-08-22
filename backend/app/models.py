"""API request models."""

from typing import Any, Literal

from pydantic import BaseModel, Field

WorkflowKind = Literal["yield-trend", "issue-triage", "spc-fdc", "root-cause", "report"]


class WorkflowRequest(BaseModel):
    kind: WorkflowKind
    context: dict[str, Any] = Field(default_factory=dict)
    question: str = Field(default="", max_length=2000)

