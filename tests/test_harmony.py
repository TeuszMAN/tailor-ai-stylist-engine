from __future__ import annotations

import pytest

from app.schemas import Formality, Product
from app.tools import LookCompositionError, compose_complete_look
from app.tools.harmony import fnv1a32, load_ruleset

NAVY = "terno-azul-marinho-super-120"
SAND = "terno-bege-areia-linho"
BLACK = "terno-preto-cerimonia"
WHITE = "camisa-branca-algodao-egipcio"
BLUE = "camisa-azul-celeste-tricoline"
STRIPED = "camisa-listrada-azul-branca"
BURGUNDY = "gravata-seda-bordo"
SILVER = "gravata-seda-prata"
PAISLEY = "gravata-lavanda-paisley"
OXFORD = "sapato-oxford-preto"
BROGUE = "sapato-brogue-cafe"
MONK = "sapato-monk-strap-cafe"


def test_classic_navy_look_scores_100(catalog: list[Product]) -> None:
    look = compose_complete_look(NAVY, WHITE, BURGUNDY, OXFORD, Formality.FORMAL, "noite", catalog=catalog)
    assert look.is_valid
    assert look.harmony_score == 100
    assert look.formality is Formality.FORMAL
    assert look.total_price_cents == sum(item.product.price_cents for item in look.items)
    assert look.name == "Cerimônia Azul Marinho · Gravata Bordô"
    assert look.ruleset_version == load_ruleset().version


def test_black_suit_with_brown_shoes_is_forbidden(catalog: list[Product]) -> None:
    look = compose_complete_look(BLACK, WHITE, SILVER, MONK, catalog=catalog)
    assert not look.is_valid
    assert any("marrom com preto" in v for v in look.violations)


def test_sand_suit_with_black_shoes_is_forbidden(catalog: list[Product]) -> None:
    look = compose_complete_look(SAND, WHITE, BURGUNDY, OXFORD, catalog=catalog)
    assert not look.is_valid


def test_black_tie_requirements(catalog: list[Product]) -> None:
    gala = compose_complete_look(BLACK, WHITE, SILVER, OXFORD, Formality.BLACK_TIE, "noite", catalog=catalog)
    assert gala.is_valid and gala.formality is Formality.BLACK_TIE
    assert gala.name.startswith("Gala ")
    navy = compose_complete_look(NAVY, BLUE, SILVER, OXFORD, Formality.BLACK_TIE, "noite", catalog=catalog)
    assert not navy.is_valid
    assert len(navy.violations) >= 2  # suit + shirt


def test_night_penalizes_brown_shoes_and_day_penalizes_black_suit(catalog: list[Product]) -> None:
    night = compose_complete_look(NAVY, WHITE, BURGUNDY, MONK, Formality.FORMAL, "noite", catalog=catalog)
    assert night.is_valid and any("18h" in w for w in night.warnings)
    day = compose_complete_look(BLACK, WHITE, SILVER, OXFORD, Formality.FORMAL, "tarde", catalog=catalog)
    assert any("noturnos" in w for w in day.warnings)


def test_pattern_clash_and_formality_gap(catalog: list[Product]) -> None:
    look = compose_complete_look(NAVY, STRIPED, PAISLEY, BROGUE, Formality.FORMAL, None, catalog=catalog)
    assert any("estampadas" in w for w in look.warnings)
    assert any("degrau abaixo" in w for w in look.warnings)
    assert look.harmony_score < 80


def test_wrong_category_and_unknown_ids(catalog: list[Product]) -> None:
    with pytest.raises(LookCompositionError, match="não é um terno"):
        compose_complete_look(WHITE, WHITE, BURGUNDY, OXFORD, catalog=catalog)
    with pytest.raises(LookCompositionError, match="não encontrado"):
        compose_complete_look("missing", WHITE, BURGUNDY, OXFORD, catalog=catalog)


def test_fnv1a32_is_stable() -> None:
    assert fnv1a32("") == "811c9dc5"
    assert fnv1a32("a") == "e40c292c"
