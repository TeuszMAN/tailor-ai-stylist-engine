"""Typed LangGraph state (Pydantic v2) with explicit reducers."""

from __future__ import annotations

import operator
from typing import Annotated, Literal

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, ConfigDict, Field

from app.schemas import (
    CatalogSource,
    EngineMode,
    OutfitRecommendation,
    Product,
    SizeRecommendation,
    StylingContext,
    StylistRecommendRequest,
    StylistRecommendResponse,
    ToolCallTrace,
    UserMeasurements,
)

PlannerPhase = Literal["search", "relax", "compose", "done"]


def merge_inventory(left: dict[str, list[Product]], right: dict[str, list[Product]]) -> dict[str, list[Product]]:
    """Reducer: append search results per category, de-duplicated by product id, order preserved."""
    merged = {category: list(items) for category, items in left.items()}
    for category, items in right.items():
        bucket = merged.setdefault(category, [])
        seen = {p.id for p in bucket}
        for product in items:
            if product.id not in seen:
                bucket.append(product)
                seen.add(product.id)
    return merged


class AgentState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Inputs
    request: StylistRecommendRequest
    catalog: list[Product]
    catalog_source: CatalogSource

    # Engine mode (may switch from "llm" to "rule_based" at runtime — self-healing fallback)
    mode: EngineMode = "rule_based"
    provider: str | None = None
    model: str | None = None
    fallback_reason: str | None = None

    # Produced by intake_node / measurement_tool_node
    context: StylingContext | None = None
    measurements: UserMeasurements | None = None
    size_profile: SizeRecommendation | None = None

    # Tool-calling loop (stylist_matcher_node <-> tool_executor_node)
    messages: Annotated[list[AnyMessage], add_messages] = Field(default_factory=list)
    inventory: Annotated[dict[str, list[Product]], merge_inventory] = Field(default_factory=dict)
    looks: Annotated[list[OutfitRecommendation], operator.add] = Field(default_factory=list)
    tool_traces: Annotated[list[ToolCallTrace], operator.add] = Field(default_factory=list)
    graph_path: Annotated[list[str], operator.add] = Field(default_factory=list)
    matcher_iterations: int = 0
    planner_phase: PlannerPhase = "search"
    llm_final_text: str | None = None

    # Produced by output_structurer_node
    response: StylistRecommendResponse | None = None
