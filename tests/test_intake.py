from __future__ import annotations

from app.agent.intake import extract_signals, resolve_measurements, run_intake
from app.schemas import (
    BellyType,
    ChatTurn,
    ChestType,
    ColorFamily,
    Formality,
    Occasion,
    StylistPreferences,
    StylistRecommendRequest,
    UserMeasurements,
)
from app.tools.vocabulary import (
    CATEGORY_SYNONYMS,
    COLOR_SYNONYMS,
    FORMALITY_KEYWORDS,
    OCCASION_KEYWORDS,
    format_brl,
    normalize,
)


def context_for(message: str, **kwargs: object):
    return run_intake(StylistRecommendRequest(message=message, **kwargs))  # type: ignore[arg-type]


def test_best_man_at_an_afternoon_wedding() -> None:
    ctx = context_for("Sou padrinho de casamento à tarde")
    assert ctx.occasion is Occasion.CASAMENTO
    assert ctx.role == "padrinho"
    assert ctx.time_of_day == "tarde"
    assert ctx.target_formality is Formality.FORMAL
    assert ctx.suit_colors.prefer[0] is ColorFamily.SAND
    assert ColorFamily.BLACK not in ctx.suit_colors.prefer


def test_versatile_suit_for_work_and_events() -> None:
    ctx = context_for("Preciso de um terno versátil para trabalho e eventos")
    assert ctx.occasion is Occasion.VERSATIL
    assert ctx.wants_versatility
    assert ctx.target_formality is Formality.BUSINESS


def test_black_tie_wedding_keeps_occasion_and_forces_dress_code() -> None:
    ctx = context_for("Casamento black tie às 20h")
    assert ctx.occasion is Occasion.CASAMENTO
    assert ctx.target_formality is Formality.BLACK_TIE
    assert ctx.time_of_day == "noite"
    assert ctx.suit_colors.prefer == [ColorFamily.BLACK]


def test_colors_by_category_negation_and_budget() -> None:
    ctx = context_for("Quero terno cinza com gravata verde, sem sapato preto, até R$ 4.500")
    assert ctx.suit_colors.prefer == [ColorFamily.GREY, ColorFamily.CHARCOAL]
    assert ctx.tie_colors.prefer == [ColorFamily.EMERALD]
    assert ctx.shoe_colors.avoid == [ColorFamily.BLACK]
    assert ctx.suit_colors.avoid == []
    assert ctx.budget_max_cents == 450_000


def test_measurements_in_free_text() -> None:
    ctx = context_for("Tenho 1,80 m e 85kg, calço 42 e tenho barriga")
    m = ctx.measurements_from_text
    assert m is not None
    assert (m.height_cm, m.weight_kg, m.shoe_size, m.belly_type) == (180, 85, 42, BellyType.LARGO)
    request = StylistRecommendRequest(message="Tenho 1,80 m e 85kg, calço 42 e tenho barriga")
    resolved = resolve_measurements(request, ctx)
    assert resolved == UserMeasurements(height_cm=180, weight_kg=85, belly_type=BellyType.LARGO, shoe_size=42)


def test_explicit_measurements_win_but_text_fills_shoe_size() -> None:
    explicit = UserMeasurements(height_cm=170, weight_kg=70, chest_type=ChestType.ATLETICO)
    request = StylistRecommendRequest(message="sapato 41 por favor", measurements=explicit)
    resolved = resolve_measurements(request, run_intake(request))
    assert resolved is not None and resolved.height_cm == 170 and resolved.shoe_size == 41


def test_history_fills_missing_occasion() -> None:
    ctx = context_for(
        "E se for à noite?",
        history=[ChatTurn(role="user", content="Sou padrinho de casamento")],
    )
    assert ctx.occasion is Occasion.CASAMENTO
    assert ctx.time_of_day == "noite"
    assert ctx.role == "padrinho"


def test_explicit_preferences_override_defaults() -> None:
    ctx = context_for(
        "Formatura",
        preferences=StylistPreferences(preferred_colors=[ColorFamily.NAVY], avoid_colors=[ColorFamily.BLACK]),
    )
    assert ctx.suit_colors.prefer == [ColorFamily.NAVY]
    assert ctx.suit_colors.avoid == [ColorFamily.BLACK]


def test_social_shirt_does_not_downgrade_a_wedding() -> None:
    assert extract_signals("camisa social para casamento").formality is None


def test_default_occasion_is_versatile() -> None:
    ctx = context_for("Olá!")
    assert ctx.occasion is Occasion.VERSATIL
    assert ctx.target_formality is Formality.BUSINESS


def test_vocabulary_phrases_are_normalized() -> None:
    for vocabulary in (COLOR_SYNONYMS, CATEGORY_SYNONYMS, OCCASION_KEYWORDS, FORMALITY_KEYWORDS):
        for phrases in vocabulary.values():
            assert all(phrase == normalize(phrase) for phrase in phrases)


def test_format_brl() -> None:
    assert format_brl(381_700) == "R$ 3.817,00"
    assert format_brl(99) == "R$ 0,99"
    assert format_brl(123_456_789) == "R$ 1.234.567,89"
