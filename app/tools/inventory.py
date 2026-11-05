"""`search_inventory` — hybrid lexical-semantic catalog search.

Works on *any* catalog (the demo repository, a JSON/SQLite repository or a catalog
sent in the request payload). Free text is interpreted deterministically:

* category words ("gravata", "mocassim") infer the category filter;
* color synonyms ("vinho", "chumbo", "areia") resolve to color families;
* occasion / dress-code words boost products tagged accordingly;
* remaining tokens are scored against product text (strong fields x3, weak x1).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.schemas import (
    FORMALITY_LABEL,
    CatalogSource,
    Category,
    ColorFamily,
    Formality,
    InventorySearchResult,
    Occasion,
    Product,
)
from app.tools.vocabulary import (
    CATEGORY_SYNONYMS,
    COLOR_SYNONYMS,
    FORMALITY_KEYWORDS,
    OCCASION_KEYWORDS,
    OCCASION_LABEL,
    find_phrases,
    normalize,
    resolve_colors,
    tokenize,
)

STRONG_WEIGHT = 3
WEAK_WEIGHT = 1
TAG_BOOST = 2


class ToolInputError(ValueError):
    """Raised when a tool receives arguments it cannot interpret."""


def _stem(token: str) -> str:
    return token[:-1] if len(token) > 3 and token.endswith("s") else token


def _terms(text: str) -> set[str]:
    return {_stem(t) for t in tokenize(text)}


@dataclass(frozen=True)
class _ProductDocument:
    strong: frozenset[str]
    weak: frozenset[str]


def _document(product: Product) -> _ProductDocument:
    strong = _terms(product.name) | _terms(product.color)
    for phrase in COLOR_SYNONYMS.get(product.color_family, ()):
        strong |= _terms(phrase)
    for phrase in CATEGORY_SYNONYMS[product.category]:
        strong |= _terms(phrase)
    weak = _terms(product.description) | _terms(product.fabric) | _terms(product.style or "")
    for occasion in product.occasion_tags:
        weak |= _terms(OCCASION_LABEL[occasion])
        for phrase in OCCASION_KEYWORDS[occasion]:
            weak |= _terms(phrase)
    for formality in product.formality_tags:
        weak |= _terms(FORMALITY_LABEL[formality])
    return _ProductDocument(strong=frozenset(strong), weak=frozenset(weak))


def _coerce_category(category: str | Category | None) -> Category | None:
    if category is None or category == "":
        return None
    try:
        return Category(category)
    except ValueError as exc:
        raise ToolInputError(f"Categoria inválida: {category!r}. Use uma de {[c.value for c in Category]}.") from exc


def _coerce_formality(formality: str | Formality | None) -> Formality | None:
    if formality is None or formality == "":
        return None
    try:
        return Formality(formality)
    except ValueError as exc:
        raise ToolInputError(
            f"Formalidade inválida: {formality!r}. Use uma de {[f.value for f in Formality]}."
        ) from exc


def search_inventory(
    category: str | Category | None,
    size: str | None,
    formality: str | Formality | None,
    color_query: str | None,
    query: str | None = None,
    *,
    catalog: Sequence[Product],
    in_stock_only: bool = True,
    limit: int = 20,
    source: CatalogSource = CatalogSource.DEMO,
) -> InventorySearchResult:
    """Filter the catalog returning only pieces available in the customer's size.

    Args:
        category: suit | shirt | pants | tie | shoes (optional, may be inferred from `query`).
        size: Brazilian size label, e.g. "52" (suit), "46" (pants), "4" (shirt), "U" (tie), "41" (shoes).
        formality: smart_casual | business | formal | black_tie.
        color_query: color in natural language ("azul marinho", "vinho", "chumbo").
        query: optional free text used for semantic ranking.
    """
    wanted_category = _coerce_category(category)
    wanted_formality = _coerce_formality(formality)
    wanted_size = (size or "").strip() or None

    text = normalize(query or "")
    inferred_category: Category | None = None
    if wanted_category is None and text:
        category_hits = find_phrases(text, CATEGORY_SYNONYMS)
        if category_hits:
            inferred_category = category_hits[0].key
            wanted_category = inferred_category

    colors: list[ColorFamily] = resolve_colors(color_query or "")
    soft_terms: set[str] = set()
    if color_query and not colors:
        soft_terms |= _terms(color_query)
    query_colors = resolve_colors(query or "")
    if not colors:
        colors = query_colors

    occasion_hits: set[Occasion] = {m.key for m in find_phrases(text, OCCASION_KEYWORDS)} if text else set()
    formality_hits: set[Formality] = {m.key for m in find_phrases(text, FORMALITY_KEYWORDS)} if text else set()
    query_terms = _terms(query or "") | soft_terms

    query_derived_filter = bool(inferred_category or (query_colors and colors == query_colors))
    scored: list[tuple[int, int, Product]] = []
    for position, product in enumerate(catalog):
        if wanted_category is not None and product.category is not wanted_category:
            continue
        if wanted_formality is not None and wanted_formality not in product.formality_tags:
            continue
        if colors and product.color_family not in colors:
            continue
        if wanted_size is not None:
            sizes = product.available_sizes if in_stock_only else [s.size for s in product.sizes]
            if wanted_size not in sizes:
                continue
        elif in_stock_only and not product.in_stock:
            continue

        doc = _document(product)
        score = STRONG_WEIGHT * len(query_terms & doc.strong) + WEAK_WEIGHT * len(query_terms & doc.weak)
        score += TAG_BOOST * len(occasion_hits & set(product.occasion_tags))
        score += TAG_BOOST * len(formality_hits & set(product.formality_tags))
        if text and score == 0 and not query_derived_filter:
            continue
        scored.append((score, position, product))

    scored.sort(key=lambda item: (-item[0], item[1]))
    items = [product for _, _, product in scored[:limit]]

    applied: dict[str, str] = {"in_stock_only": "true" if in_stock_only else "false"}
    if wanted_category is not None:
        applied["category"] = wanted_category.value
    if wanted_size is not None:
        applied["size"] = wanted_size
    if wanted_formality is not None:
        applied["formality"] = wanted_formality.value
    if colors:
        applied["colors"] = ",".join(c.value for c in colors)
    if query:
        applied["query"] = query

    return InventorySearchResult(
        source=source,
        total_matches=len(scored),
        items=items,
        resolved_colors=colors,
        inferred_category=inferred_category,
        applied_filters=applied,
    )
