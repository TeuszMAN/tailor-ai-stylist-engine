"""`compose_complete_look` — classic menswear harmony rules engine.

The rules live in `harmony_rules.json` (data, not code) so that the storefront's
TypeScript fallback evaluates *exactly* the same etiquette. Scoring:

    score = base_score
          + sum(points[rating] for the 4 color pairs)      # suit/shoes, suit/shirt, suit/tie, shirt/tie
          + formality_bonus (when the look matches the dress code)
          + context penalties (black tie, time of day, pattern clashes)
    clamped to [0, 100]; any "forbidden" pair or violation => is_valid = False
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas import (
    FORMALITY_LABEL,
    FORMALITY_RANK,
    Category,
    ColorFamily,
    Formality,
    LookItem,
    OutfitRecommendation,
    Pattern,
    Product,
    SizeRecommendation,
    TimeOfDay,
)
from app.tools.vocabulary import COLOR_LABEL, normalize

RULESET_PATH = Path(__file__).with_name("harmony_rules.json")

Relation = Literal["suit_shoes", "suit_shirt", "suit_tie", "shirt_tie"]
Severity = Literal["warning", "violation"]


class Rating(StrEnum):
    EXCELLENT = "excellent"
    GOOD = "good"
    ACCEPTABLE = "acceptable"
    WARNING = "warning"
    FORBIDDEN = "forbidden"


class ContextRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    severity: Severity
    text: str


class HarmonyRuleset(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str
    base_score: int
    formality_bonus: int
    points: dict[Rating, int]
    context_penalty: dict[Severity, int]
    pairs: dict[Relation, dict[ColorFamily, dict[ColorFamily, Rating]]]
    templates: dict[Relation, dict[Rating, str]]
    notes: dict[str, str]
    context_rules: dict[str, ContextRule]
    formality_match_text: str
    formality_coherent_text: str
    name_prefix: dict[Formality, str]


@lru_cache(maxsize=1)
def load_ruleset() -> HarmonyRuleset:
    return HarmonyRuleset.model_validate(json.loads(RULESET_PATH.read_text(encoding="utf-8")))


class LookCompositionError(ValueError):
    """Raised when the requested ids don't describe a suit + shirt + tie + shoes."""


RANK_TO_FORMALITY: dict[int, Formality] = {rank: formality for formality, rank in FORMALITY_RANK.items()}

CATEGORY_ARTICLE: dict[Category, str] = {
    Category.SUIT: "um terno",
    Category.SHIRT: "uma camisa",
    Category.PANTS: "uma calça",
    Category.TIE: "uma gravata",
    Category.SHOES: "um sapato",
}

PATTERNED_SHIRTS = frozenset({Pattern.STRIPED, Pattern.CHECKED})
PATTERNED_TIES = frozenset({Pattern.STRIPED, Pattern.CHECKED, Pattern.PAISLEY})


@dataclass(frozen=True)
class HarmonyEvaluation:
    score: int
    is_valid: bool
    formality: Formality
    rationale: tuple[str, ...]
    warnings: tuple[str, ...]
    violations: tuple[str, ...]


def fnv1a32(text: str) -> str:
    """Tiny, portable hash (also implemented in the storefront) for stable look ids."""
    value = 0x811C9DC5
    for byte in text.encode("utf-8"):
        value ^= byte
        value = (value * 0x01000193) & 0xFFFFFFFF
    return f"{value:08x}"


def look_id_for(suit_id: str, shirt_id: str, tie_id: str, shoe_id: str) -> str:
    return "look-" + fnv1a32(f"{suit_id}|{shirt_id}|{tie_id}|{shoe_id}")


def evaluate_combination(
    suit: Product,
    shirt: Product,
    tie: Product,
    shoes: Product,
    target_formality: Formality | None = None,
    time_of_day: TimeOfDay | None = None,
) -> HarmonyEvaluation:
    """Pure scoring function shared by the tool, the rule-based planner and the API."""
    rules = load_ruleset()
    score = rules.base_score
    rationale: list[str] = []
    warnings: list[str] = []
    violations: list[str] = []

    pairs: tuple[tuple[Relation, Product, Product], ...] = (
        ("suit_shoes", suit, shoes),
        ("suit_shirt", suit, shirt),
        ("suit_tie", suit, tie),
        ("shirt_tie", shirt, tie),
    )
    for relation, first, second in pairs:
        rating = rules.pairs[relation].get(first.color_family, {}).get(second.color_family, Rating.ACCEPTABLE)
        score += rules.points[rating]
        if rating is Rating.ACCEPTABLE:
            continue
        note_key = f"{relation}:{first.color_family.value}:{second.color_family.value}"
        text = rules.notes.get(note_key) or rules.templates[relation][rating].format(
            a=COLOR_LABEL[first.color_family], b=COLOR_LABEL[second.color_family]
        )
        if rating in (Rating.EXCELLENT, Rating.GOOD):
            rationale.append(text)
        elif rating is Rating.WARNING:
            warnings.append(text)
        else:
            violations.append(text)

    def apply(rule_key: str, **fmt: str) -> None:
        nonlocal score
        rule = rules.context_rules[rule_key]
        text = rule.text.format(**fmt)
        (violations if rule.severity == "violation" else warnings).append(text)
        score += rules.context_penalty[rule.severity]

    look_rank = min(p.max_formality_rank for p in (suit, shirt, tie, shoes))
    look_formality = RANK_TO_FORMALITY[look_rank]

    if target_formality is Formality.BLACK_TIE:
        if Formality.BLACK_TIE not in suit.formality_tags:
            apply("black_tie_suit")
        if shirt.color_family is not ColorFamily.WHITE:
            apply("black_tie_shirt")
        if shoes.color_family is not ColorFamily.BLACK or normalize(shoes.style or "") != "oxford":
            apply("black_tie_shoes")
        if look_rank == FORMALITY_RANK[Formality.BLACK_TIE]:
            score += rules.formality_bonus
            rationale.append(rules.formality_match_text.format(target=FORMALITY_LABEL[target_formality]))
    elif target_formality is not None:
        label = FORMALITY_LABEL[target_formality]
        gap = FORMALITY_RANK[target_formality] - look_rank
        if gap >= 2:
            apply("formality_below_many", target=label)
        elif gap == 1:
            apply("formality_below_one", target=label)
        elif gap <= -2:
            apply("formality_above", target=label)
        if -1 <= gap <= 0:
            score += rules.formality_bonus
            rationale.append(rules.formality_match_text.format(target=label))
    else:
        score += rules.formality_bonus
        rationale.append(rules.formality_coherent_text.format(target=FORMALITY_LABEL[look_formality]))

    if time_of_day == "noite":
        if suit.color_family is ColorFamily.SAND:
            apply("night_light_suit")
        if shoes.color_family in (ColorFamily.BROWN, ColorFamily.COGNAC):
            apply("night_brown_shoes")
    elif time_of_day in ("dia", "tarde") and suit.color_family is ColorFamily.BLACK:
        apply("day_black_suit")

    if shirt.pattern in PATTERNED_SHIRTS and tie.pattern in PATTERNED_TIES:
        apply("pattern_clash_shirt_tie")
    if suit.pattern is Pattern.CHECKED and shirt.pattern in PATTERNED_SHIRTS:
        apply("pattern_clash_suit_shirt")

    return HarmonyEvaluation(
        score=max(0, min(100, score)),
        is_valid=not violations,
        formality=look_formality,
        rationale=tuple(rationale),
        warnings=tuple(warnings),
        violations=tuple(violations),
    )


def _require(index: dict[str, Product], product_id: str, category: Category) -> Product:
    product = index.get(product_id)
    if product is None:
        raise LookCompositionError(f"Produto '{product_id}' não encontrado no catálogo.")
    if product.category is not category:
        raise LookCompositionError(
            f"Produto '{product_id}' não é {CATEGORY_ARTICLE[category]} (categoria: {product.category.value})."
        )
    return product


def compose_complete_look(
    suit_id: str,
    shirt_id: str,
    tie_id: str,
    shoe_id: str,
    target_formality: Formality | None = None,
    time_of_day: TimeOfDay | None = None,
    *,
    catalog: Sequence[Product],
) -> OutfitRecommendation:
    """Validate a full look against classic etiquette and price the combo."""
    index = {p.id: p for p in catalog}
    suit = _require(index, suit_id, Category.SUIT)
    shirt = _require(index, shirt_id, Category.SHIRT)
    tie = _require(index, tie_id, Category.TIE)
    shoes = _require(index, shoe_id, Category.SHOES)

    evaluation = evaluate_combination(suit, shirt, tie, shoes, target_formality, time_of_day)
    rules = load_ruleset()
    prefix = rules.name_prefix[target_formality or evaluation.formality]
    items = [
        LookItem(role=Category.SUIT, product=suit),
        LookItem(role=Category.SHIRT, product=shirt),
        LookItem(role=Category.TIE, product=tie),
        LookItem(role=Category.SHOES, product=shoes),
    ]
    return OutfitRecommendation(
        look_id=look_id_for(suit.id, shirt.id, tie.id, shoes.id),
        name=f"{prefix} {suit.color} · Gravata {tie.color}",
        items=items,
        total_price_cents=sum(item.product.price_cents for item in items),
        harmony_score=evaluation.score,
        is_valid=evaluation.is_valid,
        formality=evaluation.formality,
        occasions=list(suit.occasion_tags),
        style_rationale=list(evaluation.rationale),
        warnings=list(evaluation.warnings),
        violations=list(evaluation.violations),
        ruleset_version=rules.version,
    )


def attach_sizes(
    look: OutfitRecommendation, size_profile: SizeRecommendation | None
) -> tuple[OutfitRecommendation, list[str]]:
    """Set the customer's size on each item; return messages for pieces out of stock in that size."""
    if size_profile is None:
        return look, []
    unavailable: list[str] = []
    items: list[LookItem] = []
    for item in look.items:
        size = size_profile.size_for(item.role)
        if size is not None and size not in item.product.available_sizes:
            unavailable.append(f"{item.product.name} sem estoque no tamanho {size}.")
        items.append(item.model_copy(update={"selected_size": size}))
    return look.model_copy(update={"items": items}), unavailable
