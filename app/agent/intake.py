"""`intake_node` logic — deterministic PT-BR context extraction.

Turns the customer's message (+ chat history + explicit preferences) into a typed
`StylingContext`: occasion, time of day, role, target dress code, color intents,
budget and any measurements written in free text ("tenho 1,80 m e 85 kg").
No LLM is needed for this step, which keeps the agent auditable and cheap.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.schemas import (
    SUIT_COLOR_FAMILIES,
    BellyType,
    Category,
    ChestType,
    ColorFamily,
    ColorIntent,
    ExtractedMeasurements,
    Formality,
    GuestRole,
    Occasion,
    Season,
    StylingContext,
    StylistPreferences,
    StylistRecommendRequest,
    TimeOfDay,
    UserMeasurements,
)
from app.tools.vocabulary import (
    BELLY_KEYWORDS,
    CHEST_KEYWORDS,
    COLOR_SYNONYMS,
    FORMALITY_KEYWORDS,
    FORMALITY_PRIORITY,
    NEGATION_BEFORE,
    OCCASION_FORMALITY,
    OCCASION_KEYWORDS,
    OCCASION_LABEL,
    OCCASION_PRIORITY,
    ROLE_KEYWORDS,
    ROLE_PRIORITY,
    SEASON_KEYWORDS,
    SEASON_PRIORITY,
    TIME_KEYWORDS,
    TIME_PRIORITY,
    VERSATILITY_KEYWORDS,
    blank_phrases,
    families_for,
    find_phrases,
    first_key,
    normalize,
)

HOUR_PATTERN = re.compile(r"(?<![0-9])([01]?[0-9]|2[0-3])\s*(?:h|horas?)(?![a-z])")
HEIGHT_METERS = re.compile(r"(?<![0-9])([12])[,.]([0-9]{2})(?![0-9])")
HEIGHT_CM = re.compile(r"(?<![0-9])(1[5-9][0-9]|20[0-9]|210)\s*cm(?![a-z])")
WEIGHT_KG = re.compile(r"(?<![0-9])(4[5-9]|[5-9][0-9]|1[0-5][0-9]|160)\s*(?:kg|quilos?|kilos?)(?![a-z])")
SHOE_SIZE = re.compile(r"(?:calco|calcado|sapato|numero|pe)\s+(?:n\s*)?(3[7-9]|4[0-6])(?![0-9])")
BUDGET = re.compile(
    r"(?:ate|orcamento(?:\s+de)?|maximo(?:\s+de)?|limite(?:\s+de)?|budget(?:\s+de)?|gastar(?:\s+ate)?)\s+"
    r"(?:r\$\s*)?(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{2}))?(?:\s*(mil|k))?(?![a-z0-9])"
)
CATEGORY_CUE = re.compile(
    r"(camisa|camisas|gravata|gravatas|sapato|sapatos|mocassim|calcado|calca|calcas|terno|ternos|paleto)\s+"
    r"(?:(?:de|em|na|no|cor)\s+){0,2}$"
)
CUE_CATEGORY: dict[str, Category] = {
    "camisa": Category.SHIRT,
    "camisas": Category.SHIRT,
    "gravata": Category.TIE,
    "gravatas": Category.TIE,
    "sapato": Category.SHOES,
    "sapatos": Category.SHOES,
    "mocassim": Category.SHOES,
    "calcado": Category.SHOES,
    "calca": Category.PANTS,
    "calcas": Category.PANTS,
    "terno": Category.SUIT,
    "ternos": Category.SUIT,
    "paleto": Category.SUIT,
}
MIN_BUDGET_REAIS = 100
ACCENT_ORDER: tuple[Category, ...] = (Category.SUIT, Category.SHIRT, Category.TIE, Category.SHOES)


@dataclass
class Signals:
    occasion: Occasion | None = None
    time_of_day: TimeOfDay | None = None
    role: GuestRole | None = None
    formality: Formality | None = None
    season: Season | None = None
    prefer: dict[Category, list[ColorFamily]] = field(default_factory=dict)
    avoid: dict[Category, list[ColorFamily]] = field(default_factory=dict)
    budget_cents: int | None = None
    versatility: bool = False
    height_cm: int | None = None
    weight_kg: int | None = None
    chest_type: ChestType | None = None
    belly_type: BellyType | None = None
    shoe_size: int | None = None
    keywords: list[str] = field(default_factory=list)


def _add_unique(target: list[ColorFamily], values: tuple[ColorFamily, ...] | list[ColorFamily]) -> None:
    for value in values:
        if value not in target:
            target.append(value)


def _extract_colors(text: str, signals: Signals) -> None:
    """Colors are attributed to the nearest category cue ("gravata verde"); no cue means the suit."""
    cleaned = blank_phrases(text, FORMALITY_KEYWORDS[Formality.BLACK_TIE])
    for match in find_phrases(cleaned, COLOR_SYNONYMS):
        families = families_for(match)
        before = cleaned[: match.start]
        signals.keywords.append(match.phrase)
        cue = CATEGORY_CUE.search(before)
        category = CUE_CATEGORY[cue.group(1)] if cue else Category.SUIT
        if category is Category.PANTS:
            continue
        if category is Category.SUIT:
            families = tuple(f for f in families if f in SUIT_COLOR_FAMILIES)
        bucket = signals.avoid if NEGATION_BEFORE.search(before) else signals.prefer
        _add_unique(bucket.setdefault(category, []), families)


def _extract_measurements(text: str, signals: Signals) -> None:
    for found in HEIGHT_METERS.finditer(text):
        if "$" in text[max(0, found.start() - 3) : found.start()]:
            continue
        height = int(found.group(1)) * 100 + int(found.group(2))
        if 150 <= height <= 210:
            signals.height_cm = height
            break
    if signals.height_cm is None and (cm := HEIGHT_CM.search(text)):
        signals.height_cm = int(cm.group(1))
    if weight := WEIGHT_KG.search(text):
        signals.weight_kg = int(weight.group(1))
    if shoe := SHOE_SIZE.search(text):
        signals.shoe_size = int(shoe.group(1))
    if chest := first_key(text, CHEST_KEYWORDS, (ChestType.LARGO, ChestType.ATLETICO)):
        signals.chest_type = chest[0]
        signals.keywords.extend(chest[1])
    if belly := first_key(text, BELLY_KEYWORDS, (BellyType.ATLETICO, BellyType.MEDIO, BellyType.LARGO)):
        signals.belly_type = belly[0]
        signals.keywords.extend(belly[1])


def _extract_budget(text: str) -> int | None:
    found = BUDGET.search(text)
    if not found:
        return None
    reais = int(found.group(1).replace(".", ""))
    if found.group(3):
        reais *= 1000
    if reais < MIN_BUDGET_REAIS:
        return None
    cents = int(found.group(2)) if found.group(2) else 0
    return reais * 100 + cents


def extract_signals(raw_text: str) -> Signals:
    text = normalize(raw_text)
    signals = Signals()
    if not text:
        return signals

    if occasion := first_key(text, OCCASION_KEYWORDS, OCCASION_PRIORITY):
        signals.occasion = occasion[0]
        signals.keywords.extend(occasion[1])
    if role := first_key(text, ROLE_KEYWORDS, ROLE_PRIORITY):
        signals.role = role[0]
        signals.keywords.extend(role[1])
    if formality := first_key(text, FORMALITY_KEYWORDS, FORMALITY_PRIORITY):
        signals.formality = formality[0]
        signals.keywords.extend(formality[1])
    if time_hit := first_key(text, TIME_KEYWORDS, TIME_PRIORITY):
        signals.time_of_day = time_hit[0]
        signals.keywords.extend(time_hit[1])
    elif hour := HOUR_PATTERN.search(text):
        value = int(hour.group(1))
        signals.time_of_day = "noite" if value >= 18 or value < 5 else "tarde" if value >= 12 else "dia"
        signals.keywords.append(hour.group(0))
    if season := first_key(text, SEASON_KEYWORDS, SEASON_PRIORITY):
        signals.season = season[0]
        signals.keywords.extend(season[1])

    versatility_hits = find_phrases(text, {"versatil": VERSATILITY_KEYWORDS})
    signals.versatility = signals.occasion is Occasion.VERSATIL or bool(versatility_hits)

    _extract_colors(text, signals)
    _extract_measurements(text, signals)
    signals.budget_cents = _extract_budget(text)
    signals.keywords = list(dict.fromkeys(signals.keywords))
    return signals


def merge_signals(primary: Signals, fallback: Signals) -> Signals:
    """Current message wins; history fills the gaps (e.g. 'e se for à noite?')."""
    return Signals(
        occasion=primary.occasion or fallback.occasion,
        time_of_day=primary.time_of_day or fallback.time_of_day,
        role=primary.role or fallback.role,
        formality=primary.formality or fallback.formality,
        season=primary.season or fallback.season,
        prefer={
            c: primary.prefer.get(c) or fallback.prefer.get(c, [])
            for c in ACCENT_ORDER
            if c in primary.prefer or c in fallback.prefer
        },
        avoid={
            c: list(dict.fromkeys(primary.avoid.get(c, []) + fallback.avoid.get(c, [])))
            for c in ACCENT_ORDER
            if c in primary.avoid or c in fallback.avoid
        },
        budget_cents=primary.budget_cents or fallback.budget_cents,
        versatility=primary.versatility or fallback.versatility,
        height_cm=primary.height_cm or fallback.height_cm,
        weight_kg=primary.weight_kg or fallback.weight_kg,
        chest_type=primary.chest_type or fallback.chest_type,
        belly_type=primary.belly_type or fallback.belly_type,
        shoe_size=primary.shoe_size or fallback.shoe_size,
        keywords=list(dict.fromkeys(primary.keywords + fallback.keywords)),
    )


DEFAULT_SUIT_COLORS: dict[Occasion, tuple[ColorFamily, ...]] = {
    Occasion.CASAMENTO: (ColorFamily.NAVY, ColorFamily.GREY, ColorFamily.CHARCOAL),
    Occasion.FORMATURA: (ColorFamily.BLACK, ColorFamily.NAVY, ColorFamily.CHARCOAL),
    Occasion.ENTREVISTA: (ColorFamily.NAVY, ColorFamily.CHARCOAL),
    Occasion.TRABALHO: (ColorFamily.NAVY, ColorFamily.CHARCOAL, ColorFamily.GREY),
    Occasion.EVENTO_DIURNO: (ColorFamily.SAND, ColorFamily.GREY, ColorFamily.NAVY),
    Occasion.VERSATIL: (ColorFamily.NAVY, ColorFamily.CHARCOAL, ColorFamily.GREY),
    Occasion.GALA: (ColorFamily.BLACK,),
}

WEDDING_BY_TIME: dict[str, tuple[ColorFamily, ...]] = {
    "dia": (ColorFamily.SAND, ColorFamily.GREY, ColorFamily.NAVY),
    "tarde": (ColorFamily.SAND, ColorFamily.NAVY, ColorFamily.GREY),
    "noite": (ColorFamily.NAVY, ColorFamily.CHARCOAL, ColorFamily.BLACK),
}


def default_suit_colors(
    occasion: Occasion, time_of_day: TimeOfDay | None, formality: Formality, season: Season | None
) -> list[ColorFamily]:
    if formality is Formality.BLACK_TIE:
        return [ColorFamily.BLACK]
    if occasion is Occasion.CASAMENTO and time_of_day is not None:
        colors = list(WEDDING_BY_TIME[time_of_day])
    else:
        colors = list(DEFAULT_SUIT_COLORS[occasion])
    if time_of_day == "noite":
        colors = [c for c in colors if c is not ColorFamily.SAND]
    elif time_of_day in ("dia", "tarde"):
        colors = [c for c in colors if c is not ColorFamily.BLACK]
    if season is Season.SUMMER and time_of_day != "noite":
        colors = [ColorFamily.SAND] + [c for c in colors if c is not ColorFamily.SAND]
    elif season is Season.WINTER:
        colors = [c for c in colors if c is not ColorFamily.SAND]
    return colors


def _intent(signals: Signals, category: Category) -> ColorIntent:
    avoid = signals.avoid.get(category, [])
    return ColorIntent(prefer=[c for c in signals.prefer.get(category, []) if c not in avoid], avoid=list(avoid))


def build_context(signals: Signals, preferences: StylistPreferences | None) -> StylingContext:
    occasion = signals.occasion or Occasion.VERSATIL
    formality = signals.formality or OCCASION_FORMALITY[occasion]

    suit_avoid = list(
        dict.fromkeys((preferences.avoid_colors if preferences else []) + signals.avoid.get(Category.SUIT, []))
    )
    explicit = list(
        dict.fromkeys((preferences.preferred_colors if preferences else []) + signals.prefer.get(Category.SUIT, []))
    )
    explicit = [c for c in explicit if c in SUIT_COLOR_FAMILIES]
    palette = explicit or default_suit_colors(occasion, signals.time_of_day, formality, signals.season)
    suit_colors = ColorIntent(prefer=[c for c in palette if c not in suit_avoid], avoid=suit_avoid)

    budget = preferences.budget_max_cents if preferences and preferences.budget_max_cents else signals.budget_cents

    extracted: ExtractedMeasurements | None = None
    if any(
        value is not None
        for value in (signals.height_cm, signals.weight_kg, signals.chest_type, signals.belly_type, signals.shoe_size)
    ):
        extracted = ExtractedMeasurements(
            height_cm=signals.height_cm,
            weight_kg=signals.weight_kg,
            chest_type=signals.chest_type,
            belly_type=signals.belly_type,
            shoe_size=signals.shoe_size,
        )

    return StylingContext(
        occasion=occasion,
        occasion_label=OCCASION_LABEL[occasion],
        time_of_day=signals.time_of_day,
        role=signals.role,
        target_formality=formality,
        season=signals.season,
        suit_colors=suit_colors,
        shirt_colors=_intent(signals, Category.SHIRT),
        tie_colors=_intent(signals, Category.TIE),
        shoe_colors=_intent(signals, Category.SHOES),
        budget_max_cents=budget,
        wants_versatility=signals.versatility or occasion is Occasion.VERSATIL,
        measurements_from_text=extracted,
        detected_keywords=signals.keywords,
    )


def resolve_measurements(request: StylistRecommendRequest, context: StylingContext) -> UserMeasurements | None:
    """Explicit measurements win; free-text measurements are used when height and weight are present."""
    extracted = context.measurements_from_text
    if request.measurements is not None:
        if request.measurements.shoe_size is None and extracted and extracted.shoe_size is not None:
            return request.measurements.model_copy(update={"shoe_size": extracted.shoe_size})
        return request.measurements
    if extracted and extracted.height_cm is not None and extracted.weight_kg is not None:
        return UserMeasurements(
            height_cm=extracted.height_cm,
            weight_kg=extracted.weight_kg,
            chest_type=extracted.chest_type or ChestType.MEDIO,
            belly_type=extracted.belly_type or BellyType.MEDIO,
            shoe_size=extracted.shoe_size,
        )
    return None


def run_intake(request: StylistRecommendRequest) -> StylingContext:
    current = extract_signals(request.message)
    history_text = " . ".join(turn.content for turn in request.history if turn.role == "user")
    merged = merge_signals(current, extract_signals(history_text)) if history_text else current
    return build_context(merged, request.preferences)
