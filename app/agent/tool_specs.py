"""Tool schemas exposed to the LLM (OpenAI function format, accepted by every LangChain chat model).

The tools are *executed* by `tool_executor_node` with the request's catalog — the LLM
only decides which tool to call and with which arguments.
"""

from __future__ import annotations

from typing import Any

from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import BaseModel, ConfigDict, Field

from app.schemas import Category, Formality, TimeOfDay

SEARCH_INVENTORY = "search_inventory"
COMPOSE_COMPLETE_LOOK = "compose_complete_look"


class SearchInventoryArgs(BaseModel):
    """Busca peças em estoque no catálogo, filtrando por categoria, tamanho, formalidade e cor."""

    model_config = ConfigDict(extra="ignore")

    category: Category = Field(description="Categoria: suit, shirt, pants, tie ou shoes.")
    size: str | None = Field(
        default=None,
        description="Tamanho do cliente nessa categoria (terno '52', camisa '4', calça '46', gravata 'U', sapato '41').",
    )
    formality: Formality | None = Field(
        default=None, description="Dress code: smart_casual, business, formal, black_tie."
    )
    color_query: str | None = Field(default=None, description="Cor em linguagem natural, ex.: 'azul marinho', 'vinho'.")
    query: str | None = Field(default=None, description="Texto livre opcional para ranqueamento semântico.")


class ComposeLookArgs(BaseModel):
    """Valida um look completo (terno + camisa + gravata + sapato) pela etiqueta clássica e calcula o preço."""

    model_config = ConfigDict(extra="ignore")

    suit_id: str = Field(description="id do terno retornado por search_inventory.")
    shirt_id: str = Field(description="id da camisa retornada por search_inventory.")
    tie_id: str = Field(description="id da gravata retornada por search_inventory.")
    shoe_id: str = Field(description="id do sapato retornado por search_inventory.")
    target_formality: Formality | None = Field(default=None, description="Dress code do evento.")
    time_of_day: TimeOfDay | None = Field(default=None, description="dia, tarde ou noite.")


def _spec(name: str, model: type[BaseModel]) -> dict[str, Any]:
    spec = convert_to_openai_tool(model)
    spec["function"]["name"] = name
    return spec


def tool_specs() -> list[dict[str, Any]]:
    return [_spec(SEARCH_INVENTORY, SearchInventoryArgs), _spec(COMPOSE_COMPLETE_LOOK, ComposeLookArgs)]
