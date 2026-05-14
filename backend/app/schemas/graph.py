"""
Graph-related schemas for knowledge graph visualization.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class NoteLinkResponse(BaseModel):
    """Response for a note link connection."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    source_note_id: int
    target_note_id: int
    link_type: str  # related | referenced | parent | child
    description: Optional[str] = None
    created_at: datetime


class GraphNodeResponse(BaseModel):
    """Response for a single node in the knowledge graph."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    content_preview: Optional[str] = None
    is_favorite: bool
    is_archived: bool
    is_pinned: bool
    color: Optional[str] = None
    emoji: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class GraphResponse(BaseModel):
    """Response for a knowledge graph with nodes and edges."""

    nodes: list[GraphNodeResponse]
    edges: list[NoteLinkResponse]
    center_node_id: Optional[int] = None  # For focused graph views


class GraphAllResponse(BaseModel):
    """Response for full knowledge graph with pagination."""

    nodes: list[GraphNodeResponse]
    edges: list[NoteLinkResponse]
    cursor: Optional[str] = None
    has_more: bool
