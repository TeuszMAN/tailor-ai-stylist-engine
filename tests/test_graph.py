from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from app.agent.graph import (
    NODE_INTAKE,
    NODE_MATCHER,
    NODE_MEASUREMENT,
    NODE_OUTPUT,
    NODE_TOOLS,
    StylistEngine,
)
from app.agent.llm import LLMBundle
from app.catalog import DEMO_CATALOG_PATH, JsonFileCatalogRepository
from app.schemas import (
    CatalogSource,
    Category,
    ColorFamily,
    Formality,
    Product,
    StylistPreferences,
    StylistRecommendRequest,
    UserMeasurements,
)

MEASUREMENTS = UserMeasurements(height_cm=180, weight_kg=85, chest_type="medio", belly_type="medio", shoe_size=41)


def engine(llm: LLMBundle | None = None) -> StylistEngine:
    return StylistEngine(JsonFileCatalogRepository(DEMO_CATALOG_PATH, CatalogSource.DEMO), llm)


class ScriptedChatModel(BaseChatModel):
    """Deterministic chat model that replays scripted AIMessages (or raises)."""

    responses: list[AIMessage] = Field(default_factory=list)
    error: str | None = None
    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> ScriptedChatModel:  # type: ignore[override]
        return self

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None, **kwargs: Any) -> ChatResult:
        if self.error:
            raise RuntimeError(self.error)
        message = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return ChatResult(generations=[ChatGeneration(message=message)])


def bundle(model: ScriptedChatModel) -> LLMBundle:
    return LLMBundle(model=model, provider="scripted", model_name="scripted-1")


def test_rule_based_best_man_flow() -> None:
    response = engine().recommend(
        StylistRecommendRequest(message="Sou padrinho de casamento à tarde", measurements=MEASUREMENTS)
    )
    assert response.engine.mode == "rule_based"
    assert response.engine.graph_path[:3] == [NODE_INTAKE, NODE_MEASUREMENT, NODE_MATCHER]
    assert response.engine.graph_path[-1] == NODE_OUTPUT
    assert NODE_TOOLS in response.engine.graph_path
    assert response.engine.tool_calls[0].tool == "calculate_tailoring_size"
    assert len(response.recommended_looks) == 3
    for look in response.recommended_looks:
        assert look.is_valid
        suit = look.items[0].product
        assert suit.color_family is not ColorFamily.BLACK  # afternoon: no black suit
        for item in look.items:
            assert item.selected_size is not None
            assert item.selected_size in item.product.available_sizes
    assert response.size_profile is not None and response.size_profile.suit_size == 52
    assert "padrinho" in response.reply.lower()
    assert response.quick_replies


def test_black_tie_only_returns_gala_looks() -> None:
    response = engine().recommend(
        StylistRecommendRequest(message="Vou a um baile black tie à noite", measurements=MEASUREMENTS)
    )
    assert response.context.target_formality is Formality.BLACK_TIE
    assert response.recommended_looks
    for look in response.recommended_looks:
        roles = {item.role: item.product for item in look.items}
        assert roles[Category.SUIT].color_family is ColorFamily.BLACK
        assert roles[Category.SHIRT].color_family is ColorFamily.WHITE
        assert roles[Category.SHOES].style == "oxford"


def test_versatile_request_reuses_one_suit_and_suggests_pants() -> None:
    response = engine().recommend(
        StylistRecommendRequest(
            message="Preciso de um terno versátil para trabalho e eventos", measurements=MEASUREMENTS
        )
    )
    suits = {look.items[0].product.id for look in response.recommended_looks}
    assert len(suits) == 1
    assert len({look.look_id for look in response.recommended_looks}) == len(response.recommended_looks)
    assert any(p.category is Category.PANTS for p in response.suggested_products)


def test_without_measurements_asks_for_fit_finder() -> None:
    response = engine().recommend(StylistRecommendRequest(message="Tenho uma entrevista de emprego"))
    assert response.size_profile is None
    assert response.recommended_looks
    assert all(item.selected_size is None for look in response.recommended_looks for item in look.items)
    assert "Ainda não tenho suas medidas" in response.reply


def test_measurements_written_in_the_message_are_used() -> None:
    response = engine().recommend(StylistRecommendRequest(message="Casamento à noite, tenho 1,80m e 85kg, calço 41"))
    assert response.size_profile is not None
    assert response.size_profile.summary.startswith("Terno 52")


def test_payload_catalog_and_missing_categories(catalog: list[Product]) -> None:
    suits_only = [p for p in catalog if p.category is Category.SUIT]
    response = engine().recommend(StylistRecommendRequest(message="Casamento", catalog=suits_only))
    assert response.engine.catalog_source is CatalogSource.PAYLOAD
    assert response.recommended_looks == []
    assert "camisas" in response.reply


def test_budget_warning() -> None:
    response = engine().recommend(
        StylistRecommendRequest(
            message="Casamento à noite",
            measurements=MEASUREMENTS,
            preferences=StylistPreferences(budget_max_cents=200_000),
        )
    )
    assert response.recommended_looks
    assert all(any("orçamento" in w for w in look.warnings) for look in response.recommended_looks)
    assert "acima do orçamento" in response.reply


def _call(name: str, args: dict[str, Any], call_id: str) -> dict[str, Any]:
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}


def test_llm_tool_calling_path_with_size_guardrail() -> None:
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    _call("search_inventory", {"category": "suit", "formality": "formal"}, "c1"),
                    _call("search_inventory", {"category": "shirt", "size": "4"}, "c2"),
                    _call("search_inventory", {"category": "tie"}, "c3"),
                    _call("search_inventory", {"category": "shoes", "size": "41"}, "c4"),
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    _call(
                        "compose_complete_look",
                        {
                            "suit_id": "terno-azul-marinho-super-120",
                            "shirt_id": "camisa-branca-algodao-egipcio",
                            "tie_id": "gravata-seda-bordo",
                            "shoe_id": "sapato-oxford-preto",
                        },
                        "c5",
                    )
                ],
            ),
            AIMessage(content="Montei um look clássico em azul-marinho com gravata bordô. Prefere outra cor?"),
        ]
    )
    response = engine(bundle(model)).recommend(
        StylistRecommendRequest(message="Casamento à noite", measurements=MEASUREMENTS)
    )
    assert response.engine.mode == "llm"
    assert response.engine.provider == "scripted"
    assert response.engine.fallback_reason is None
    assert response.reply.startswith("Montei um look clássico")
    assert [look.name for look in response.recommended_looks] == ["Cerimônia Azul Marinho · Gravata Bordô"]
    suit_search = next(t for t in response.engine.tool_calls if t.tool == "search_inventory")
    assert suit_search.arguments["size"] == "52"  # injected by the executor guardrail
    assert response.engine.graph_path.count(NODE_MATCHER) == 3


def test_llm_error_falls_back_to_rule_based() -> None:
    response = engine(bundle(ScriptedChatModel(error="provider down"))).recommend(
        StylistRecommendRequest(message="Sou padrinho de casamento à tarde", measurements=MEASUREMENTS)
    )
    assert response.engine.mode == "rule_based"
    assert response.engine.fallback_reason == "llm_error:RuntimeError"
    assert len(response.recommended_looks) == 3


def test_llm_without_valid_looks_falls_back() -> None:
    model = ScriptedChatModel(responses=[AIMessage(content="Claro! Recomendo um terno azul.")])
    response = engine(bundle(model)).recommend(StylistRecommendRequest(message="Entrevista", measurements=MEASUREMENTS))
    assert response.engine.fallback_reason == "llm_returned_no_valid_look"
    assert response.recommended_looks
    assert "Recomendo um terno azul" not in response.reply


def test_mermaid_export_contains_all_nodes() -> None:
    diagram = engine().mermaid()
    for node in (NODE_INTAKE, NODE_MEASUREMENT, NODE_MATCHER, NODE_TOOLS, NODE_OUTPUT):
        assert node in diagram
