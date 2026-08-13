"""图谱契约 —— L0/L1 统一图数据结构。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

IndexStatus = Literal[
    "NONE",
    "QUEUED",
    "CLONING",
    "INDEXING",
    "READY",
    "STALE",
    "CLONE_FAILED",
    "INDEX_FAILED",
]
IndexMode = Literal["fast", "moderate", "full", "cross-repo-intelligence"]
GraphLevel = Literal["project", "code"]


class CodeGraphNode(BaseModel):
    id: str
    name: str
    kind: str
    level: GraphLevel = "code"
    x: Optional[float] = None
    y: Optional[float] = None
    z: Optional[float] = None
    file_path: Optional[str] = None
    qualified_name: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    size: Optional[float] = None
    color: Optional[str] = None
    status: Optional[str] = None
    in_calls: Optional[int] = None
    attrs: dict[str, Any] = Field(default_factory=dict)


class CodeGraphEdge(BaseModel):
    source: str
    target: str
    relation: str
    weight: Optional[float] = None
    reasons: list[str] = Field(default_factory=list)


class GraphStats(BaseModel):
    node_count: int = 0
    edge_count: int = 0
    total_nodes: Optional[int] = None
    avg_similarity: Optional[float] = None


class UnifiedGraphData(BaseModel):
    nodes: list[CodeGraphNode] = Field(default_factory=list)
    edges: list[CodeGraphEdge] = Field(default_factory=list)
    stats: GraphStats = Field(default_factory=GraphStats)


class GraphIndexStatusOut(BaseModel):
    project_id: UUID
    engine_project: str = ""
    local_path: Optional[str] = None
    head_sha: Optional[str] = None
    branch: Optional[str] = None
    status: IndexStatus = "NONE"
    index_mode: IndexMode = "fast"
    node_count: Optional[int] = None
    edge_count: Optional[int] = None
    indexed_at: Optional[datetime] = None
    error: Optional[str] = None


class IndexTriggerBody(BaseModel):
    mode: IndexMode = "fast"


class TraceBody(BaseModel):
    symbol: str = Field(..., min_length=1)
    direction: Literal["upstream", "downstream", "both"] = "both"
    depth: int = Field(3, ge=1, le=20)


class SearchBody(BaseModel):
    query: str = Field(..., min_length=1)
    label: Optional[str] = None
    limit: int = Field(20, ge=1, le=200)


class CrossEdgeOut(BaseModel):
    source_project_id: Optional[str] = None
    target_project_id: Optional[str] = None
    source_engine: str
    target_engine: str
    relation: str
    weight: float = 1.0
    reasons: list[str] = Field(default_factory=list)
    source_symbol: Optional[str] = None
    target_symbol: Optional[str] = None
