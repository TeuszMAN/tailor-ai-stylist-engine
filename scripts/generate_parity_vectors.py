"""Golden vectors that any port of the deterministic engine must reproduce bit-for-bit.

Run: `python -m scripts.generate_parity_vectors` (writes docs/contracts/parity/*.json).

The storefront's TypeScript Local Fallback Adapter copies these files into its test
fixtures, so Python and TypeScript are cross-validated on:
* drop6_vectors.json      — anthropometric sizing over a grid of bodies
* harmony_vectors.json    — every suit/shirt/tie/shoe combination of the demo catalog x 5 contexts
* intake_vectors.json     — PT-BR context extraction
* search_vectors.json     — hybrid lexical-semantic search
* recommend_vectors.json  — full rule-based recommendations (looks, reply, suggestions)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.agent.graph import StylistEngine
from app.agent.intake import run_intake
from app.catalog import DEMO_CATALOG_PATH, JsonFileCatalogRepository
from app.schemas import (
    CatalogSource,
    Category,
    Formality,
    Product,
    StylistPreferences,
    StylistRecommendRequest,
    TimeOfDay,
    UserMeasurements,
)
from app.tools import calculate_tailoring_size, search_inventory
from app.tools.harmony import evaluate_combination, fnv1a32, load_ruleset

ROOT = Path(__file__).resolve().parents[1]
PARITY_DIR = ROOT / "docs" / "contracts" / "parity"

HEIGHTS = (150, 168, 175, 180, 190, 210)
WEIGHTS = (45, 62, 70, 85, 95, 110, 160)
BIOTYPES = ("atletico", "medio", "largo")
CONTEXTS: tuple[tuple[Formality | None, TimeOfDay | None], ...] = (
    (None, None),
    (Formality.FORMAL, "noite"),
    (Formality.FORMAL, "tarde"),
    (Formality.BLACK_TIE, "noite"),
    (Formality.BUSINESS, "dia"),
)

INTAKE_MESSAGES = (
    "Sou padrinho de casamento à tarde",
    "Preciso de um terno versátil para trabalho e eventos",
    "Casamento black tie às 20h",
    "Vou me formar mês que vem, a formatura é à noite",
    "Tenho uma entrevista de emprego num banco",
    "Quero terno cinza com gravata verde, sem sapato preto, até R$ 4.500",
    "Tenho 1,80 m e 85kg, calço 42 e tenho barriga",
    "Meço 175 cm, peso 78 kg, sou atlético e sem barriga",
    "Casamento na praia no verão, de manhã",
    "Batizado do meu sobrinho num almoço de domingo",
    "Reuniões no escritório todos os dias, orçamento de 3 mil",
    "Nada de preto, prefiro azul marinho",
    "Evento de gala com traje a rigor",
    "Vou casar! Sou o noivo e a cerimônia é às 17h",
    "Fui convidado para um casamento esporte fino ao ar livre",
    "Quero uma camisa rosa e gravata lavanda",
    "Preciso de algo para o inverno na serra, traje social",
    "Olá!",
    "Tenho ombros largos e barriguinha, 1.72 e 90 kg",
    "Passeio completo para formatura do meu filho",
)

SEARCH_QUERIES: tuple[dict[str, Any], ...] = (
    {"category": "suit", "size": "52"},
    {"category": "suit", "size": "52", "formality": "formal"},
    {"category": "suit", "color_query": "cinza"},
    {"category": "tie", "color_query": "vinho"},
    {"category": "shoes", "size": "44"},
    {"query": "gravata verde para casamento"},
    {"query": "sapato para casamento"},
    {"query": "terno azul marinho"},
    {"query": "camisa branca"},
    {"query": "linho verão"},
    {"query": "black tie"},
    {"query": "mocassim conhaque"},
    {"query": "calça para trabalho", "size": "46"},
    {"query": "xyzzy"},
    {"category": "shirt", "size": "6", "formality": "black_tie"},
    {"in_stock_only": False, "category": "suit", "size": "60"},
)

MEASUREMENTS = {"height_cm": 180, "weight_kg": 85, "chest_type": "medio", "belly_type": "medio", "shoe_size": 41}
RECOMMEND_SCENARIOS: tuple[dict[str, Any], ...] = (
    {"message": "Sou padrinho de casamento à tarde", "measurements": MEASUREMENTS},
    {"message": "Preciso de um terno versátil para trabalho e eventos", "measurements": MEASUREMENTS},
    {"message": "Casamento black tie às 20h", "measurements": MEASUREMENTS},
    {"message": "Tenho uma entrevista de emprego"},
    {"message": "Casamento à noite, tenho 1,80m e 85kg, calço 41"},
    {"message": "Casamento na praia de manhã", "measurements": {**MEASUREMENTS, "shoe_size": None}},
    {"message": "Quero uma opção com gravata verde esmeralda", "measurements": MEASUREMENTS},
    {"message": "Formatura à noite, sem preto", "measurements": MEASUREMENTS},
    {
        "message": "Casamento à noite",
        "measurements": MEASUREMENTS,
        "preferences": {"budget_max_cents": 400000},
        "max_looks": 2,
    },
    {
        "message": "Trabalho no escritório",
        "measurements": {"height_cm": 172, "weight_kg": 95, "chest_type": "medio", "belly_type": "largo"},
    },
    {"message": "Evento diurno esporte fino", "measurements": {**MEASUREMENTS, "chest_type": "atletico"}},
    {
        "message": "E se for à noite?",
        "history": [{"role": "user", "content": "Sou padrinho de casamento"}],
        "measurements": MEASUREMENTS,
    },
)


def _catalog() -> list[Product]:
    return JsonFileCatalogRepository(DEMO_CATALOG_PATH, CatalogSource.DEMO).list_products()


def drop6_vectors() -> dict[str, Any]:
    cases = []
    for height in HEIGHTS:
        for weight in WEIGHTS:
            for chest in BIOTYPES:
                for belly in BIOTYPES:
                    shoe = 41 if (height + weight) % 2 == 0 else None
                    result = calculate_tailoring_size(height, weight, chest, belly, shoe)
                    cases.append(
                        {
                            "input": {
                                "height_cm": height,
                                "weight_kg": weight,
                                "chest_type": chest,
                                "belly_type": belly,
                                "shoe_size": shoe,
                            },
                            "expected": result.model_dump(mode="json"),
                        }
                    )
    return {"algorithm_version": "drop6-v1", "cases": cases}


def harmony_vectors(catalog: list[Product]) -> dict[str, Any]:
    by_category = {c: [p for p in catalog if p.category is c] for c in Category}
    ids = [p.id for p in catalog]
    rows = []
    for target, time_of_day in CONTEXTS:
        for suit in by_category[Category.SUIT]:
            for shirt in by_category[Category.SHIRT]:
                for tie in by_category[Category.TIE]:
                    for shoes in by_category[Category.SHOES]:
                        ev = evaluate_combination(suit, shirt, tie, shoes, target, time_of_day)
                        messages = "|".join((*ev.rationale, "#", *ev.warnings, "#", *ev.violations))
                        rows.append(
                            [
                                ids.index(suit.id),
                                ids.index(shirt.id),
                                ids.index(tie.id),
                                ids.index(shoes.id),
                                target.value if target else None,
                                time_of_day,
                                ev.score,
                                ev.is_valid,
                                ev.formality.value,
                                fnv1a32(messages),
                            ]
                        )
    return {
        "ruleset_version": load_ruleset().version,
        "columns": ["suit", "shirt", "tie", "shoes", "target", "time", "score", "valid", "formality", "messages_fnv"],
        "product_ids": ids,
        "rows": rows,
    }


def intake_vectors() -> dict[str, Any]:
    cases = []
    for message in INTAKE_MESSAGES:
        context = run_intake(StylistRecommendRequest(message=message))
        cases.append({"message": message, "expected": context.model_dump(mode="json")})
    return {"cases": cases}


def search_vectors(catalog: list[Product]) -> dict[str, Any]:
    cases = []
    for query in SEARCH_QUERIES:
        result = search_inventory(
            query.get("category"),
            query.get("size"),
            query.get("formality"),
            query.get("color_query"),
            query.get("query"),
            catalog=catalog,
            in_stock_only=query.get("in_stock_only", True),
        )
        cases.append(
            {
                "input": query,
                "expected": {
                    "ids": [p.id for p in result.items],
                    "total_matches": result.total_matches,
                    "resolved_colors": [c.value for c in result.resolved_colors],
                    "inferred_category": result.inferred_category.value if result.inferred_category else None,
                },
            }
        )
    return {"cases": cases}


def recommend_vectors() -> dict[str, Any]:
    engine = StylistEngine(JsonFileCatalogRepository(DEMO_CATALOG_PATH, CatalogSource.DEMO))
    cases = []
    for scenario in RECOMMEND_SCENARIOS:
        payload = dict(scenario)
        if payload.get("measurements"):
            payload["measurements"] = UserMeasurements.model_validate(payload["measurements"])
        if payload.get("preferences"):
            payload["preferences"] = StylistPreferences.model_validate(payload["preferences"])
        request = StylistRecommendRequest.model_validate({**payload, "session_id": "parity"})
        response = engine.recommend(request)
        cases.append(
            {
                "input": scenario,
                "expected": {
                    "reply": response.reply,
                    "context": response.context.model_dump(mode="json"),
                    "size_summary": response.size_profile.summary if response.size_profile else None,
                    "looks": [
                        {
                            "look_id": look.look_id,
                            "name": look.name,
                            "item_ids": [item.product.id for item in look.items],
                            "selected_sizes": [item.selected_size for item in look.items],
                            "harmony_score": look.harmony_score,
                            "total_price_cents": look.total_price_cents,
                            "warnings": look.warnings,
                        }
                        for look in response.recommended_looks
                    ],
                    "suggested_ids": [p.id for p in response.suggested_products],
                    "quick_replies": response.quick_replies,
                },
            }
        )
    return {"cases": cases}


def build_vectors() -> dict[str, str]:
    catalog = _catalog()
    data = {
        "drop6_vectors.json": drop6_vectors(),
        "harmony_vectors.json": harmony_vectors(catalog),
        "intake_vectors.json": intake_vectors(),
        "search_vectors.json": search_vectors(catalog),
        "recommend_vectors.json": recommend_vectors(),
    }
    return {
        name: json.dumps(content, ensure_ascii=False, separators=(",", ":")) + "\n" for name, content in data.items()
    }


def main() -> None:
    PARITY_DIR.mkdir(parents=True, exist_ok=True)
    for name, content in build_vectors().items():
        (PARITY_DIR / name).write_text(content, encoding="utf-8")
        print(f"wrote docs/contracts/parity/{name} ({len(content) // 1024} KiB)")


if __name__ == "__main__":
    main()
