"""`calculate_tailoring_size` — deterministic anthropometric sizing (algorithm "drop6-v1").

All arithmetic is integer-based (tenths of kg, BMI x10) so the TypeScript port in the
storefront produces bit-identical results. Specification: docs/SDD.md §5.

Pipeline
1. Effective weight: weight adjusted to a 175 cm reference body
   (0.4 kg per cm of height difference) -> taller people at the same weight are slimmer.
2. Base chest size from effective-weight bands (46..60).
3. Jacket: +2 when the torso needs room (broad chest or large belly).
4. Pants: jacket minus the drop from the biotype matrix (Drop 6 is the neutral case).
5. Shirt number (1..6) follows the jacket; cut (Slim/Regular) follows biotype and BMI.
"""

from __future__ import annotations

from app.schemas import (
    BellyType,
    ChestType,
    Fit,
    JacketLength,
    ShirtLetter,
    SizeRecommendation,
    UserMeasurements,
)

REFERENCE_HEIGHT_CM = 175
HEIGHT_FACTOR_X10 = 4  # 0.4 kg per cm, expressed in tenths of kg

# (upper bound of effective weight in tenths of kg, base size). Above the last bound -> 60.
WEIGHT_BANDS_X10: tuple[tuple[int, int], ...] = (
    (620, 46),
    (690, 48),
    (760, 50),
    (840, 52),
    (920, 54),
    (1010, 56),
    (1110, 58),
)
MAX_SUIT_SIZE = 60
MIN_SUIT_SIZE = 46
MIN_PANTS_SIZE = 38
MAX_PANTS_SIZE = 54

# Drop (jacket - pants) by chest x belly biotype.
DROP_MATRIX: dict[ChestType, dict[BellyType, int]] = {
    ChestType.ATLETICO: {BellyType.ATLETICO: 8, BellyType.MEDIO: 8, BellyType.LARGO: 6},
    ChestType.MEDIO: {BellyType.ATLETICO: 8, BellyType.MEDIO: 6, BellyType.LARGO: 4},
    ChestType.LARGO: {BellyType.ATLETICO: 8, BellyType.MEDIO: 6, BellyType.LARGO: 4},
}

SHIRT_LETTERS: dict[int, ShirtLetter] = {1: "PP", 2: "P", 3: "M", 4: "G", 5: "GG", 6: "XG"}
COLLAR_CM: dict[int, str] = {1: "37", 2: "38", 3: "39-40", 4: "41-42", 5: "43-44", 6: "45-46"}

BIOTYPE_LABEL: dict[str, str] = {"atletico": "atlético", "medio": "médio", "largo": "largo"}
FIT_LABEL: dict[Fit, str] = {Fit.SLIM: "Slim", Fit.REGULAR: "Regular"}

SLIM_BMI_X10 = 220  # BMI < 22.0 favors Slim
REGULAR_BMI_X10 = 280  # BMI >= 28.0 forces Regular


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def _format_decimal(value_x10: int) -> str:
    sign = "-" if value_x10 < 0 else ""
    whole, tenth = divmod(abs(value_x10), 10)
    return f"{sign}{whole},{tenth}"


def effective_weight_x10(height_cm: int, weight_kg: int) -> int:
    return weight_kg * 10 - HEIGHT_FACTOR_X10 * (height_cm - REFERENCE_HEIGHT_CM)


def bmi_x10(height_cm: int, weight_kg: int) -> int:
    """BMI x10 rounded half-up with integer math: w / (h/100)^2 * 10."""
    denominator = height_cm * height_cm
    return (weight_kg * 200_000 + denominator) // (2 * denominator)


def base_size_for(eff_x10: int) -> int:
    for upper, size in WEIGHT_BANDS_X10:
        if eff_x10 <= upper:
            return size
    return MAX_SUIT_SIZE


def jacket_length_for(height_cm: int) -> JacketLength:
    if height_cm < 170:
        return JacketLength.CURTO
    if height_cm < 185:
        return JacketLength.REGULAR
    return JacketLength.LONGO


def fit_for(chest: ChestType, belly: BellyType, bmi: int) -> tuple[Fit, str]:
    if belly is BellyType.LARGO:
        return Fit.REGULAR, "Abdômen largo pede corte Regular, com mais folga na cintura."
    if bmi >= REGULAR_BMI_X10:
        return Fit.REGULAR, "IMC acima de 28 favorece o corte Regular para conforto e caimento."
    if chest is ChestType.ATLETICO or belly is BellyType.ATLETICO:
        return Fit.SLIM, "Biotipo atlético valoriza o corte Slim, acinturado."
    if bmi < SLIM_BMI_X10:
        return Fit.SLIM, "Silhueta esguia (IMC abaixo de 22) fica mais elegante no corte Slim."
    return Fit.REGULAR, "Biotipo médio: o corte Regular garante caimento clássico."


def calculate_tailoring_size(
    height_cm: int,
    weight_kg: int,
    chest_type: str | ChestType,
    belly_type: str | BellyType,
    shoe_size: int | None = None,
) -> SizeRecommendation:
    """Return suit (46-60), pants (38-54), shirt (1-6) sizes and the ideal cut.

    Raises `pydantic.ValidationError` when inputs are outside the supported range.
    """
    m = UserMeasurements(
        height_cm=height_cm,
        weight_kg=weight_kg,
        chest_type=ChestType(chest_type),
        belly_type=BellyType(belly_type),
        shoe_size=shoe_size,
    )
    chest, belly = m.chest_type, m.belly_type
    eff = effective_weight_x10(m.height_cm, m.weight_kg)
    bmi = bmi_x10(m.height_cm, m.weight_kg)
    base = base_size_for(eff)
    rationale = [
        f"Peso efetivo de {_format_decimal(eff)} kg (peso ajustado à altura de referência de "
        f"{REFERENCE_HEIGHT_CM} cm) indica o tamanho base {base}."
    ]

    needs_room = chest is ChestType.LARGO or belly is BellyType.LARGO
    raw_jacket = base + (2 if needs_room else 0)
    if chest is ChestType.LARGO:
        rationale.append("Tórax largo pede um número acima no paletó para folga em ombros e peito.")
    elif belly is BellyType.LARGO:
        rationale.append("Abdômen largo pede um número acima no paletó para que ele feche sem repuxar.")
    jacket = _clamp(raw_jacket, MIN_SUIT_SIZE, MAX_SUIT_SIZE)
    if jacket != raw_jacket:
        rationale.append(f"Tamanho {raw_jacket} está fora da grade; usamos {jacket} e recomendamos ajuste sob medida.")

    drop = DROP_MATRIX[chest][belly]
    raw_pants = jacket - drop
    pants = _clamp(raw_pants, MIN_PANTS_SIZE, MAX_PANTS_SIZE)
    rationale.append(
        f"Biotipo tórax {BIOTYPE_LABEL[chest.value]} / abdômen {BIOTYPE_LABEL[belly.value]} aplica "
        f"Drop {drop}: calça {pants} para o paletó {jacket}."
    )
    if pants != raw_pants:
        rationale.append(f"Calça {raw_pants} está fora da grade; usamos {pants} com ajuste de barra e cós.")

    fit, fit_reason = fit_for(chest, belly, bmi)
    rationale.append(fit_reason)

    length = jacket_length_for(m.height_cm)
    rationale.append(f"Altura de {m.height_cm} cm indica paletó de comprimento {length.value}.")

    shirt = _clamp((jacket - MIN_SUIT_SIZE) // 2 + 1, 1, 6)
    letter = SHIRT_LETTERS[shirt]
    summary = f"Terno {jacket} {FIT_LABEL[fit]} | Calça {pants} | Camisa {shirt} ({letter})"
    if m.shoe_size is not None:
        summary += f" | Sapato {m.shoe_size}"

    return SizeRecommendation(
        suit_size=jacket,
        pants_size=pants,
        shirt_size=shirt,
        shirt_letter=letter,
        collar_cm=COLLAR_CM[shirt],
        fit=fit,
        drop=jacket - pants,
        jacket_length=length,
        shoe_size=m.shoe_size,
        estimated_chest_cm=jacket * 2,
        estimated_waist_cm=pants * 2,
        bmi=bmi / 10,
        effective_weight_kg=eff / 10,
        summary=summary,
        rationale=rationale,
    )


def size_from_measurements(measurements: UserMeasurements) -> SizeRecommendation:
    return calculate_tailoring_size(
        height_cm=measurements.height_cm,
        weight_kg=measurements.weight_kg,
        chest_type=measurements.chest_type,
        belly_type=measurements.belly_type,
        shoe_size=measurements.shoe_size,
    )
