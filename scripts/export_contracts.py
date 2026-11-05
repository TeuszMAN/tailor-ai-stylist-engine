"""Export the public contracts consumed by clients (run: `python -m scripts.export_contracts`).

Writes to docs/contracts/:
* openapi.json              — full OpenAPI 3.1 document of the FastAPI app
* schemas/<Model>.schema.json — JSON Schema of every request/response model
* langgraph.mmd             — Mermaid diagram rendered from the *compiled* StateGraph
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel
from pydantic.json_schema import JsonSchemaMode

from app.agent.graph import StylistEngine
from app.catalog import DEMO_CATALOG_PATH, JsonFileCatalogRepository
from app.config import Settings
from app.main import create_app
from app.schemas import (
    CatalogSource,
    ComposeLookRequest,
    InventorySearchRequest,
    InventorySearchResult,
    OutfitRecommendation,
    Product,
    SizeRecommendation,
    StylistRecommendRequest,
    StylistRecommendResponse,
    SuitCombination,
    UserMeasurements,
)

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS_DIR = ROOT / "docs" / "contracts"

SCHEMA_MODELS: tuple[type[BaseModel], ...] = (
    Product,
    UserMeasurements,
    SizeRecommendation,
    SuitCombination,
    ComposeLookRequest,
    OutfitRecommendation,
    InventorySearchRequest,
    InventorySearchResult,
    StylistRecommendRequest,
    StylistRecommendResponse,
)


def dumps(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def build_contracts() -> dict[str, str]:
    """Return {relative_path: file_content} for every exported contract file."""
    app = create_app(Settings(llm_provider="none", _env_file=None))
    files: dict[str, str] = {"openapi.json": dumps(app.openapi())}
    for model in SCHEMA_MODELS:
        mode: JsonSchemaMode = (
            "serialization" if model in (Product, OutfitRecommendation, StylistRecommendResponse) else "validation"
        )
        files[f"schemas/{model.__name__}.schema.json"] = dumps(model.model_json_schema(mode=mode))
    engine = StylistEngine(JsonFileCatalogRepository(DEMO_CATALOG_PATH, CatalogSource.DEMO))
    files["langgraph.mmd"] = engine.mermaid().rstrip() + "\n"
    return files


def main() -> None:
    for relative, content in build_contracts().items():
        target = CONTRACTS_DIR / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        print(f"wrote {target.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
