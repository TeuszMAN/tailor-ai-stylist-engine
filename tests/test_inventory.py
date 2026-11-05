from __future__ import annotations

import pytest

from app.schemas import Category, ColorFamily, Formality, Product
from app.tools import ToolInputError, search_inventory


def test_size_filter_excludes_sold_out_sizes(catalog: list[Product]) -> None:
    result = search_inventory("suit", "52", None, None, catalog=catalog)
    ids = {p.id for p in result.items}
    assert "terno-cinza-chumbo" not in ids  # size 52 is sold out in the demo catalog
    assert "terno-azul-marinho-super-120" in ids
    assert all("52" in p.available_sizes for p in result.items)


def test_formality_filter(catalog: list[Product]) -> None:
    result = search_inventory(Category.SUIT, None, Formality.BLACK_TIE, None, catalog=catalog)
    assert [p.id for p in result.items] == ["terno-preto-cerimonia"]


@pytest.mark.parametrize(
    ("color_query", "family"),
    [("vinho", ColorFamily.BURGUNDY), ("azul marinho", ColorFamily.NAVY), ("prateada", ColorFamily.SILVER)],
)
def test_color_synonyms(catalog: list[Product], color_query: str, family: ColorFamily) -> None:
    result = search_inventory("tie", "U", None, color_query, catalog=catalog)
    assert result.items
    assert {p.color_family for p in result.items} == {family}


def test_generic_grey_matches_light_and_charcoal(catalog: list[Product]) -> None:
    result = search_inventory("suit", None, None, "cinza", catalog=catalog)
    assert {p.color_family for p in result.items} == {ColorFamily.GREY, ColorFamily.CHARCOAL}


def test_free_text_infers_category_and_color(catalog: list[Product]) -> None:
    result = search_inventory(None, None, None, None, "gravata verde para casamento", catalog=catalog)
    assert result.inferred_category is Category.TIE
    assert [p.id for p in result.items] == ["gravata-seda-verde-esmeralda"]


def test_free_text_ranks_by_occasion(catalog: list[Product]) -> None:
    result = search_inventory(None, None, None, None, "sapato para casamento", catalog=catalog)
    assert result.items[0].category is Category.SHOES
    assert "casamento" in result.items[0].occasion_tags


def test_unknown_words_return_nothing(catalog: list[Product]) -> None:
    assert search_inventory(None, None, None, None, "xyzzy", catalog=catalog).total_matches == 0


def test_payload_catalog_is_respected(catalog: list[Product]) -> None:
    custom = [p for p in catalog if p.category is Category.SHOES]
    result = search_inventory(None, None, None, None, catalog=custom)
    assert {p.category for p in result.items} == {Category.SHOES}


def test_invalid_category_raises(catalog: list[Product]) -> None:
    with pytest.raises(ToolInputError):
        search_inventory("hat", None, None, None, catalog=catalog)
