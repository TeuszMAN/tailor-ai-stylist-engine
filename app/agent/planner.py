"""Deterministic Rule-Based planner — the zero-key fallback of `stylist_matcher_node`.

It speaks the same protocol as an LLM: it emits tool calls (`search_inventory`,
`compose_complete_look`) that are executed by `tool_executor_node`. Therefore the graph
path, the traces and the response shape are identical with or without an API key.

The storefront's TypeScript Local Fallback Adapter ports `rank_suits` and
`choose_combinations` 1:1 (verified by `docs/contracts/parity/recommend_vectors.json`).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import JsonValue

from app.schemas import (
    Category,
    ColorFamily,
    Formality,
    Occasion,
    Product,
    Season,
    SizeRecommendation,
    StylingContext,
)
from app.tools.harmony import evaluate_combination

REQUIRED_CATEGORIES: tuple[Category, ...] = (Category.SUIT, Category.SHIRT, Category.TIE, Category.SHOES)

COLOR_PREFERENCE_WEIGHTS: tuple[int, ...] = (30, 20, 10)
FORMALITY_MATCH_BONUS = 10
SEASON_BONUS = 5
REUSE_PENALTY = 4
ACCENT_PREFERENCE_BONUS = 12
OVER_BUDGET_PENALTY = 25


@dataclass(frozen=True)
class PlannedCall:
    name: str
    args: dict[str, JsonValue]


@dataclass(frozen=True)
class Combination:
    suit: Product
    shirt: Product
    tie: Product
    shoes: Product
    score: int
    total_price_cents: int

    @property
    def key(self) -> tuple[str, str, str, str]:
        return (self.suit.id, self.shirt.id, self.tie.id, self.shoes.id)


def search_call(category: Category, size: str | None, formality: Formality | None) -> PlannedCall:
    return PlannedCall(
        name="search_inventory",
        args={
            "category": category.value,
            "size": size,
            "formality": formality.value if formality else None,
            "color_query": None,
            "query": None,
        },
    )


def size_for(profile: SizeRecommendation | None, category: Category) -> str | None:
    return profile.size_for(category) if profile is not None else None


def initial_searches(context: StylingContext, profile: SizeRecommendation | None) -> list[PlannedCall]:
    calls = [search_call(c, size_for(profile, c), context.target_formality) for c in REQUIRED_CATEGORIES]
    if context.wants_versatility or context.occasion in (Occasion.TRABALHO, Occasion.VERSATIL):
        calls.append(search_call(Category.PANTS, size_for(profile, Category.PANTS), None))
    return calls


def avoided_colors(context: StylingContext, category: Category) -> list[ColorFamily]:
    intents = {
        Category.SUIT: context.suit_colors,
        Category.SHIRT: context.shirt_colors,
        Category.TIE: context.tie_colors,
        Category.SHOES: context.shoe_colors,
    }
    intent = intents.get(category)
    return intent.avoid if intent is not None else []


def candidates(
    inventory: dict[str, list[Product]],
    category: Category,
    context: StylingContext,
    profile: SizeRecommendation | None,
) -> list[Product]:
    """Re-apply the hard constraints (size, stock, avoided colors) to whatever was searched."""
    size = size_for(profile, category)
    mandated = context.target_formality is Formality.BLACK_TIE and category in (Category.SHIRT, Category.SHOES)
    result: list[Product] = []
    for product in inventory.get(category.value, []):
        if product.category is not category:
            continue
        if size is not None and size not in product.available_sizes:
            continue
        if size is None and not product.in_stock:
            continue
        if not mandated and product.color_family in avoided_colors(context, category):
            continue
        result.append(product)
    return result


def relax_searches(
    inventory: dict[str, list[Product]], context: StylingContext, profile: SizeRecommendation | None
) -> list[PlannedCall]:
    """Drop the dress-code filter for categories that came back empty (size is never relaxed)."""
    return [
        search_call(c, size_for(profile, c), None)
        for c in REQUIRED_CATEGORIES
        if not candidates(inventory, c, context, profile)
    ]


def suit_score(product: Product, context: StylingContext) -> int:
    score = 0
    prefs = context.suit_colors.prefer
    if product.color_family in prefs:
        index = prefs.index(product.color_family)
        score += COLOR_PREFERENCE_WEIGHTS[index] if index < len(COLOR_PREFERENCE_WEIGHTS) else 0
    if context.target_formality in product.formality_tags:
        score += FORMALITY_MATCH_BONUS
    if context.season is Season.SUMMER and Season.SUMMER in product.seasons:
        score += SEASON_BONUS
    if context.season is Season.WINTER and Season.SUMMER in product.seasons:
        score -= SEASON_BONUS
    return score


def rank_suits(suits: Sequence[Product], context: StylingContext) -> list[Product]:
    return sorted(suits, key=lambda p: (-suit_score(p, context), p.price_cents, p.id))


def _accent_bonus(product: Product, preferences: list[ColorFamily]) -> int:
    return ACCENT_PREFERENCE_BONUS if product.color_family in preferences else 0


def best_combination(
    suit: Product,
    shirts: Sequence[Product],
    ties: Sequence[Product],
    shoes: Sequence[Product],
    context: StylingContext,
    used: Counter[str],
    taken: set[tuple[str, str, str, str]],
) -> Combination | None:
    best: tuple[tuple[int, int, str, str, str], Combination] | None = None
    for shirt in shirts:
        for tie in ties:
            for shoe in shoes:
                key = (suit.id, shirt.id, tie.id, shoe.id)
                if key in taken:
                    continue
                evaluation = evaluate_combination(suit, shirt, tie, shoe, context.target_formality, context.time_of_day)
                if not evaluation.is_valid:
                    continue
                total = suit.price_cents + shirt.price_cents + tie.price_cents + shoe.price_cents
                adjusted = evaluation.score
                adjusted -= REUSE_PENALTY * (used[shirt.id] + used[tie.id] + used[shoe.id])
                adjusted += _accent_bonus(shirt, context.shirt_colors.prefer)
                adjusted += _accent_bonus(tie, context.tie_colors.prefer)
                adjusted += _accent_bonus(shoe, context.shoe_colors.prefer)
                if context.budget_max_cents is not None and total > context.budget_max_cents:
                    adjusted -= OVER_BUDGET_PENALTY
                rank_key = (-adjusted, total, shirt.id, tie.id, shoe.id)
                if best is None or rank_key < best[0]:
                    best = (rank_key, Combination(suit, shirt, tie, shoe, evaluation.score, total))
    return best[1] if best else None


def choose_combinations(
    inventory: dict[str, list[Product]],
    context: StylingContext,
    profile: SizeRecommendation | None,
    max_looks: int,
) -> list[Combination]:
    ranked = rank_suits(candidates(inventory, Category.SUIT, context, profile), context)
    shirts = candidates(inventory, Category.SHIRT, context, profile)
    ties = candidates(inventory, Category.TIE, context, profile)
    shoes = candidates(inventory, Category.SHOES, context, profile)
    if not (ranked and shirts and ties and shoes):
        return []

    # Suits in the context palette come first; other colors only when the palette is out of stock.
    preferred = [s for s in ranked if s.color_family in context.suit_colors.prefer]
    pool = preferred or ranked
    if context.wants_versatility:
        plan = [pool[0]] * max_looks
    else:
        plan = pool[:max_looks]
        plan += [pool[index % len(pool)] for index in range(max_looks - len(plan))]

    used: Counter[str] = Counter()
    taken: set[tuple[str, str, str, str]] = set()
    chosen: list[Combination] = []
    for suit in plan:
        combo = best_combination(suit, shirts, ties, shoes, context, used, taken)
        if combo is None:
            continue
        chosen.append(combo)
        taken.add(combo.key)
        used.update([combo.shirt.id, combo.tie.id, combo.shoes.id])
    return chosen


def compose_call(combo: Combination, context: StylingContext) -> PlannedCall:
    return PlannedCall(
        name="compose_complete_look",
        args={
            "suit_id": combo.suit.id,
            "shirt_id": combo.shirt.id,
            "tie_id": combo.tie.id,
            "shoe_id": combo.shoes.id,
            "target_formality": context.target_formality.value,
            "time_of_day": context.time_of_day,
        },
    )


def missing_categories(
    inventory: dict[str, list[Product]], context: StylingContext, profile: SizeRecommendation | None
) -> list[Category]:
    return [c for c in REQUIRED_CATEGORIES if not candidates(inventory, c, context, profile)]
