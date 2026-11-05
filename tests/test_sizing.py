from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import Category, Fit, JacketLength
from app.tools.sizing import DROP_MATRIX, base_size_for, bmi_x10, calculate_tailoring_size, effective_weight_x10


def test_reference_customer_matches_the_spec_example() -> None:
    size = calculate_tailoring_size(180, 85, "medio", "medio")
    assert (size.suit_size, size.pants_size, size.shirt_size) == (52, 46, 4)
    assert size.fit is Fit.REGULAR
    assert size.drop == 6
    assert size.summary == "Terno 52 Regular | Calça 46 | Camisa 4 (G)"
    assert size.size_for(Category.TIE) == "U"
    assert size.size_for(Category.SHOES) is None


def test_athletic_biotype_gets_drop_8_and_slim_cut() -> None:
    size = calculate_tailoring_size(178, 78, "atletico", "atletico", shoe_size=42)
    assert size.suit_size == 52
    assert size.pants_size == 44
    assert size.drop == 8
    assert size.fit is Fit.SLIM
    assert size.summary.endswith("| Sapato 42")


def test_large_belly_adds_room_to_jacket_and_uses_drop_4() -> None:
    size = calculate_tailoring_size(172, 95, "medio", "largo")
    assert size.suit_size == 58  # base 56 + 2 for closure over the belly
    assert size.pants_size == 54
    assert size.drop == 4
    assert size.fit is Fit.REGULAR
    assert size.shirt_size == 6


def test_grid_is_clamped_at_both_ends() -> None:
    small = calculate_tailoring_size(150, 45, "medio", "atletico")
    assert (small.suit_size, small.pants_size) == (46, 38)
    big = calculate_tailoring_size(165, 160, "largo", "largo")
    assert (big.suit_size, big.pants_size) == (60, 54)
    assert any("fora da grade" in reason for reason in big.rationale)


@pytest.mark.parametrize(
    ("eff_x10", "expected"),
    [(620, 46), (621, 48), (690, 48), (760, 50), (840, 52), (841, 54), (1010, 56), (1110, 58), (1111, 60)],
)
def test_weight_band_boundaries(eff_x10: int, expected: int) -> None:
    assert base_size_for(eff_x10) == expected


def test_integer_math_helpers() -> None:
    assert effective_weight_x10(175, 80) == 800
    assert effective_weight_x10(190, 80) == 740  # taller -> slimmer
    assert bmi_x10(180, 85) == 262
    assert bmi_x10(200, 100) == 250


def test_jacket_length_by_height() -> None:
    assert calculate_tailoring_size(168, 70, "medio", "medio").jacket_length is JacketLength.CURTO
    assert calculate_tailoring_size(184, 80, "medio", "medio").jacket_length is JacketLength.REGULAR
    assert calculate_tailoring_size(190, 85, "medio", "medio").jacket_length is JacketLength.LONGO


def test_drop_matrix_is_complete() -> None:
    assert all(len(row) == 3 for row in DROP_MATRIX.values())


@pytest.mark.parametrize(("height", "weight"), [(149, 80), (211, 80), (180, 44), (180, 161)])
def test_out_of_range_inputs_are_rejected(height: int, weight: int) -> None:
    with pytest.raises(ValidationError):
        calculate_tailoring_size(height, weight, "medio", "medio")


def test_full_grid_always_produces_valid_sizes() -> None:
    for height in range(150, 211, 5):
        for weight in range(45, 161, 5):
            for chest in ("atletico", "medio", "largo"):
                for belly in ("atletico", "medio", "largo"):
                    size = calculate_tailoring_size(height, weight, chest, belly)
                    assert 46 <= size.suit_size <= 60 and size.suit_size % 2 == 0
                    assert 38 <= size.pants_size <= 54 and size.pants_size % 2 == 0
                    assert 1 <= size.shirt_size <= 6
