"""LangGraph orchestration of the Tailor AI Stylist.

    START -> intake_node -> measurement_tool_node -> stylist_matcher_node
                                                       |  ^
                                         (tool calls)  v  |  (results)
                                                tool_executor_node
                                                       |
                                  (no tool calls) -> output_structurer_node -> END

* `intake_node`            deterministic PT-BR NLU -> StylingContext
* `measurement_tool_node`  calls `calculate_tailoring_size` (Drop 6) when measurements are known
* `stylist_matcher_node`   LLM with tool calling, or the deterministic Rule-Based planner
                           (same tool-call protocol). Self-heals: any LLM error, or an LLM
                           that ends without a valid look, switches the run to rule-based.
* `tool_executor_node`     runs `search_inventory` / `compose_complete_look` with guardrails
                           (customer size injection, typed args, error capture)
* `output_structurer_node` builds the typed `StylistRecommendResponse`
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.messages.tool import ToolCall
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import JsonValue, ValidationError

from app.agent import planner
from app.agent.formatter import compose_reply, message_text, quick_replies, suggested_products
from app.agent.intake import resolve_measurements, run_intake
from app.agent.llm import LLMBundle
from app.agent.prompts import SYSTEM_PROMPT, build_user_brief
from app.agent.state import AgentState, PlannerPhase
from app.agent.tool_specs import (
    COMPOSE_COMPLETE_LOOK,
    SEARCH_INVENTORY,
    ComposeLookArgs,
    SearchInventoryArgs,
    tool_specs,
)
from app.catalog import CatalogRepository, resolve_catalog
from app.ratelimit import RateLimitRule, SlidingWindowRateLimiter
from app.schemas import (
    EngineInfo,
    InventorySearchResult,
    OutfitRecommendation,
    Product,
    StylingContext,
    StylistRecommendRequest,
    StylistRecommendResponse,
    ToolCallTrace,
)
from app.tools import (
    LookCompositionError,
    ToolInputError,
    attach_sizes,
    compose_complete_look,
    search_inventory,
    size_from_measurements,
)
from app.tools.vocabulary import format_brl

logger = logging.getLogger(__name__)

NODE_INTAKE = "intake_node"
NODE_MEASUREMENT = "measurement_tool_node"
NODE_MATCHER = "stylist_matcher_node"
NODE_TOOLS = "tool_executor_node"
NODE_OUTPUT = "output_structurer_node"

RECURSION_LIMIT = 40
HISTORY_TURNS_FOR_LLM = 6
TOOL_RESULT_ITEMS = 12


def _context(state: AgentState) -> StylingContext:
    if state.context is None:
        raise RuntimeError("intake_node must run before this node")
    return state.context


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


def intake_node(state: AgentState) -> dict[str, Any]:
    return {"context": run_intake(state.request), "graph_path": [NODE_INTAKE]}


def measurement_tool_node(state: AgentState) -> dict[str, Any]:
    measurements = resolve_measurements(state.request, _context(state))
    update: dict[str, Any] = {"measurements": measurements, "graph_path": [NODE_MEASUREMENT]}
    if measurements is None:
        return update
    started = time.perf_counter()
    profile = size_from_measurements(measurements)
    update["size_profile"] = profile
    update["tool_traces"] = [
        ToolCallTrace(
            tool="calculate_tailoring_size",
            arguments=measurements.model_dump(mode="json"),
            duration_ms=_elapsed_ms(started),
            ok=True,
            result_summary=profile.summary,
        )
    ]
    return update


@dataclass
class _LLMTurn:
    update: dict[str, Any] = field(default_factory=dict)
    fallback_reason: str | None = None


def _history_messages(state: AgentState) -> list[BaseMessage]:
    turns = state.request.history[-HISTORY_TURNS_FOR_LLM:]
    return [HumanMessage(t.content) if t.role == "user" else AIMessage(t.content) for t in turns]


def _llm_turn(state: AgentState, llm: LLMBundle, iteration: int, max_tool_rounds: int) -> _LLMTurn:
    context = _context(state)
    prefix: list[BaseMessage] = []
    if not state.messages:
        prefix = [
            SystemMessage(SYSTEM_PROMPT.format(max_looks=state.request.max_looks)),
            *_history_messages(state),
            HumanMessage(
                build_user_brief(
                    state.request.message, context, state.size_profile, state.catalog, state.request.max_looks
                )
            ),
        ]
    try:
        reply = llm.model.bind_tools(tool_specs()).invoke([*state.messages, *prefix])
    except Exception as exc:  # provider/network/auth errors must never break the endpoint
        logger.warning("LLM call failed, switching to rule-based planner: %s", exc)
        return _LLMTurn(fallback_reason=f"llm_error:{type(exc).__name__}")

    has_valid_look = any(look.is_valid for look in state.looks)
    if not isinstance(reply, AIMessage):
        return _LLMTurn(fallback_reason="llm_invalid_message")
    if reply.tool_calls:
        if iteration <= max_tool_rounds:
            return _LLMTurn(update={"messages": [*prefix, reply]})
        if has_valid_look:
            return _LLMTurn(update={"planner_phase": "done"})
        return _LLMTurn(fallback_reason="llm_tool_round_limit")
    if not has_valid_look:
        return _LLMTurn(fallback_reason="llm_returned_no_valid_look")
    return _LLMTurn(
        update={"messages": [*prefix, reply], "llm_final_text": message_text(reply.content), "planner_phase": "done"}
    )


def _rule_based_turn(state: AgentState, iteration: int) -> tuple[AIMessage, PlannerPhase]:
    context = _context(state)
    profile = state.size_profile
    phase: PlannerPhase = state.planner_phase
    calls: list[planner.PlannedCall] = []
    next_phase: PlannerPhase = "done"

    if phase == "search":
        calls = planner.initial_searches(context, profile)
        next_phase = "relax"
    elif phase == "relax":
        calls = planner.relax_searches(state.inventory, context, profile)
        next_phase = "compose"
        if not calls:
            phase = "compose"
    if phase == "compose":
        combos = planner.choose_combinations(state.inventory, context, profile, state.request.max_looks)
        calls = [planner.compose_call(combo, context) for combo in combos]
        next_phase = "done"

    tool_calls = [
        ToolCall(name=call.name, args=call.args, id=f"rb-{iteration}-{index}", type="tool_call")
        for index, call in enumerate(calls)
    ]
    return AIMessage(content="", tool_calls=tool_calls), next_phase


class StylistMatcherNode:
    """`stylist_matcher_node`: LLM tool calling with a self-healing rule-based fallback."""

    def __init__(self, llm: LLMBundle | None, max_tool_rounds: int) -> None:
        self.llm = llm
        self.max_tool_rounds = max_tool_rounds

    def __call__(self, state: AgentState) -> dict[str, Any]:
        iteration = state.matcher_iterations + 1
        update: dict[str, Any] = {"graph_path": [NODE_MATCHER], "matcher_iterations": iteration}
        if state.mode == "llm" and self.llm is not None:
            turn = _llm_turn(state, self.llm, iteration, self.max_tool_rounds)
            if turn.fallback_reason is None:
                update.update(turn.update)
                return update
            update["mode"] = "rule_based"
            update["fallback_reason"] = turn.fallback_reason
        message, next_phase = _rule_based_turn(state, iteration)
        update["messages"] = [message]
        update["planner_phase"] = next_phase
        return update


def _strings(values: Iterable[str]) -> list[JsonValue]:
    return [str(value) for value in values]


def _product_payload(product: Product) -> dict[str, JsonValue]:
    return {
        "id": product.id,
        "name": product.name,
        "color": product.color,
        "color_family": product.color_family.value,
        "pattern": product.pattern.value,
        "style": product.style,
        "price": format_brl(product.price_cents),
        "available_sizes": _strings(product.available_sizes),
        "formality": _strings(f.value for f in product.formality_tags),
    }


def _search_payload(result: InventorySearchResult) -> dict[str, JsonValue]:
    items: list[JsonValue] = [_product_payload(p) for p in result.items[:TOOL_RESULT_ITEMS]]
    return {"total_matches": result.total_matches, "items": items}


def _look_payload(look: OutfitRecommendation) -> dict[str, JsonValue]:
    return {
        "look_id": look.look_id,
        "name": look.name,
        "is_valid": look.is_valid,
        "harmony_score": look.harmony_score,
        "formality": look.formality.value,
        "total": format_brl(look.total_price_cents),
        "rationale": _strings(look.style_rationale[:3]),
        "warnings": _strings(look.warnings),
        "violations": _strings(look.violations),
    }


def tool_executor_node(state: AgentState) -> dict[str, Any]:
    last = state.messages[-1] if state.messages else None
    if not isinstance(last, AIMessage):
        raise RuntimeError("tool_executor_node expects an AIMessage with tool calls")
    context = _context(state)
    profile = state.size_profile

    tool_messages: list[ToolMessage] = []
    traces: list[ToolCallTrace] = []
    inventory: dict[str, list[Product]] = {}
    looks: list[OutfitRecommendation] = []

    for call in last.tool_calls:
        started = time.perf_counter()
        name = call["name"]
        raw_args: dict[str, Any] = dict(call.get("args") or {})
        effective_args: dict[str, JsonValue] = {
            k: v for k, v in raw_args.items() if v is None or isinstance(v, (str, int, float, bool))
        }
        payload: dict[str, JsonValue]
        try:
            if name == SEARCH_INVENTORY:
                search = SearchInventoryArgs.model_validate(raw_args)
                size = search.size or planner.size_for(profile, search.category)  # guardrail: customer size
                result = search_inventory(
                    search.category,
                    size,
                    search.formality,
                    search.color_query,
                    search.query,
                    catalog=state.catalog,
                    source=state.catalog_source,
                )
                inventory.setdefault(search.category.value, []).extend(result.items)
                effective_args = {**search.model_dump(mode="json"), "size": size}
                payload = _search_payload(result)
                summary = f"{result.total_matches} peça(s) de {search.category.value} (tam. {size or 'qualquer'})"
            elif name == COMPOSE_COMPLETE_LOOK:
                combo = ComposeLookArgs.model_validate(raw_args)
                target = combo.target_formality or context.target_formality
                time_of_day = combo.time_of_day or context.time_of_day
                look = compose_complete_look(
                    combo.suit_id,
                    combo.shirt_id,
                    combo.tie_id,
                    combo.shoe_id,
                    target,
                    time_of_day,
                    catalog=state.catalog,
                )
                looks.append(look)
                effective_args = {
                    **combo.model_dump(mode="json"),
                    "target_formality": target.value,
                    "time_of_day": time_of_day,
                }
                payload = _look_payload(look)
                verdict = "válido" if look.is_valid else "inválido"
                summary = f"{look.name}: nota {look.harmony_score}, {verdict}"
            else:
                raise ToolInputError(f"Ferramenta desconhecida: {name}")
            ok = True
        except (ValidationError, ToolInputError, LookCompositionError) as exc:
            ok = False
            payload = {"error": str(exc)}
            summary = f"erro: {exc}"[:240]

        traces.append(
            ToolCallTrace(
                tool=name,
                arguments=effective_args,
                duration_ms=_elapsed_ms(started),
                ok=ok,
                result_summary=summary,
            )
        )
        tool_messages.append(
            ToolMessage(content=json.dumps(payload, ensure_ascii=False), tool_call_id=call.get("id") or name, name=name)
        )

    return {
        "messages": tool_messages,
        "tool_traces": traces,
        "inventory": inventory,
        "looks": looks,
        "graph_path": [NODE_TOOLS],
    }


def output_structurer_node(state: AgentState) -> dict[str, Any]:
    context = _context(state)
    profile = state.size_profile
    budget = context.budget_max_cents

    final_looks: list[OutfitRecommendation] = []
    seen: set[str] = set()
    for look in state.looks:
        if look.look_id in seen or not look.is_valid:
            continue
        sized, unavailable = attach_sizes(look, profile)
        if unavailable:  # never recommend what is not in stock in the customer's size
            continue
        if budget is not None and sized.total_price_cents > budget:
            sized = sized.model_copy(
                update={"warnings": [*sized.warnings, f"Acima do orçamento de {format_brl(budget)}."]}
            )
        final_looks.append(sized)
        seen.add(look.look_id)
        if len(final_looks) >= state.request.max_looks:
            break

    missing = planner.missing_categories(state.inventory, context, profile)
    llm_text = state.llm_final_text if state.mode == "llm" else None
    reply = llm_text or compose_reply(context, profile, final_looks, missing)
    response = StylistRecommendResponse(
        session_id=state.request.session_id or uuid.uuid4().hex[:16],
        reply=reply,
        recommended_looks=final_looks,
        suggested_products=suggested_products(state.inventory, final_looks),
        size_profile=profile,
        context=context,
        quick_replies=quick_replies(context, profile),
        engine=EngineInfo(
            mode=state.mode,
            provider=state.provider,
            model=state.model,
            fallback_reason=state.fallback_reason,
            catalog_source=state.catalog_source,
            graph_path=[*state.graph_path, NODE_OUTPUT],
            tool_calls=state.tool_traces,
            latency_ms=0.0,
        ),
    )
    return {"response": response, "graph_path": [NODE_OUTPUT]}


def route_after_matcher(state: AgentState) -> str:
    last = state.messages[-1] if state.messages else None
    if isinstance(last, AIMessage) and last.tool_calls:
        return NODE_TOOLS
    return NODE_OUTPUT


# ---------------------------------------------------------------------------
# Graph & engine
# ---------------------------------------------------------------------------


def build_graph(llm: LLMBundle | None, max_tool_rounds: int = 4) -> CompiledStateGraph[Any, Any, Any, Any]:
    graph = StateGraph(AgentState)
    graph.add_node(NODE_INTAKE, intake_node)
    graph.add_node(NODE_MEASUREMENT, measurement_tool_node)
    graph.add_node(NODE_MATCHER, StylistMatcherNode(llm, max_tool_rounds))
    graph.add_node(NODE_TOOLS, tool_executor_node)
    graph.add_node(NODE_OUTPUT, output_structurer_node)

    graph.add_edge(START, NODE_INTAKE)
    graph.add_edge(NODE_INTAKE, NODE_MEASUREMENT)
    graph.add_edge(NODE_MEASUREMENT, NODE_MATCHER)
    graph.add_conditional_edges(NODE_MATCHER, route_after_matcher, {NODE_TOOLS: NODE_TOOLS, NODE_OUTPUT: NODE_OUTPUT})
    graph.add_edge(NODE_TOOLS, NODE_MATCHER)
    graph.add_edge(NODE_OUTPUT, END)
    return graph.compile()


LLM_BUDGET_EXHAUSTED = "llm_budget_exhausted"


class StylistEngine:
    """Facade used by the API: resolves the catalog, runs the graph, stamps latency.

    `llm_requests_per_minute` is a global spend guard: when the budget is exhausted the request
    runs on the deterministic planner (same response contract) with `fallback_reason` set.
    """

    def __init__(
        self,
        repository: CatalogRepository,
        llm: LLMBundle | None = None,
        max_tool_rounds: int = 4,
        *,
        llm_requests_per_minute: int | None = None,
        limiter: SlidingWindowRateLimiter | None = None,
    ) -> None:
        self.repository = repository
        self.llm = llm
        self.graph = build_graph(llm, max_tool_rounds)
        self._llm_rule = RateLimitRule("llm", llm_requests_per_minute) if llm_requests_per_minute is not None else None
        self._limiter = limiter or SlidingWindowRateLimiter()

    @property
    def mode(self) -> str:
        return "llm" if self.llm is not None else "rule_based"

    def _llm_allowed(self) -> bool:
        if self.llm is None:
            return False
        if self._llm_rule is None:
            return True
        return self._limiter.hit("llm:global", self._llm_rule).allowed

    def recommend(self, request: StylistRecommendRequest) -> StylistRecommendResponse:
        started = time.perf_counter()
        catalog, source = resolve_catalog(request.catalog, self.repository)
        use_llm = self._llm_allowed()
        initial = AgentState(
            request=request,
            catalog=catalog,
            catalog_source=source,
            mode="llm" if use_llm else "rule_based",
            provider=self.llm.provider if self.llm else None,
            model=self.llm.model_name if self.llm else None,
            fallback_reason=LLM_BUDGET_EXHAUSTED if self.llm is not None and not use_llm else None,
        )
        raw = self.graph.invoke(initial, config={"recursion_limit": RECURSION_LIMIT})
        final = raw if isinstance(raw, AgentState) else AgentState.model_validate(raw)
        if final.response is None:
            raise RuntimeError("Graph finished without a response")
        engine = final.response.engine.model_copy(
            update={"latency_ms": round((time.perf_counter() - started) * 1000, 2)}
        )
        logger.info(
            "stylist.recommend mode=%s looks=%d tools=%d latency_ms=%.1f fallback=%s",
            engine.mode,
            len(final.response.recommended_looks),
            len(engine.tool_calls),
            engine.latency_ms,
            engine.fallback_reason,
        )
        return final.response.model_copy(update={"engine": engine})

    def mermaid(self) -> str:
        return self.graph.get_graph().draw_mermaid()
