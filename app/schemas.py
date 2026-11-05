"""Public data contracts (Pydantic v2) of the Tailor AI Engine.

Every payload that crosses a boundary (HTTP, LangGraph state, tool I/O) is declared
here. `scripts/export_contracts.py` exports these models (and the FastAPI OpenAPI
document) to `docs/contracts/`. Changing a field here is a *contract change*:
update `docs/SDD.md`, re-export the contracts and bump `API_VERSION`.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    computed_field,
    model_validator,
)

API_VERSION = "1.0.0"


class Contract(BaseModel):
    """Base model: rejects unknown fields so contract drift fails loudly."""

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class Category(StrEnum):
    SUIT = "suit"
    SHIRT = "shirt"
    PANTS = "pants"
    TIE = "tie"
    SHOES = "shoes"


class Formality(StrEnum):
    """Dress-code ladder, ordered from least to most formal."""

    SMART_CASUAL = "smart_casual"
    BUSINESS = "business"
    FORMAL = "formal"
    BLACK_TIE = "black_tie"


FORMALITY_RANK: dict[Formality, int] = {
    Formality.SMART_CASUAL: 1,
    Formality.BUSINESS: 2,
    Formality.FORMAL: 3,
    Formality.BLACK_TIE: 4,
}

FORMALITY_LABEL: dict[Formality, str] = {
    Formality.SMART_CASUAL: "esporte fino",
    Formality.BUSINESS: "social executivo",
    Formality.FORMAL: "passeio completo",
    Formality.BLACK_TIE: "black tie (traje a rigor)",
}


class ColorFamily(StrEnum):
    NAVY = "navy"
    CHARCOAL = "charcoal"
    GREY = "grey"
    SAND = "sand"
    BLACK = "black"
    WHITE = "white"
    LIGHT_BLUE = "light_blue"
    BLUE_STRIPE = "blue_stripe"
    PINK = "pink"
    BURGUNDY = "burgundy"
    SILVER = "silver"
    EMERALD = "emerald"
    LAVENDER = "lavender"
    BROWN = "brown"
    COGNAC = "cognac"
    KHAKI = "khaki"


SUIT_COLOR_FAMILIES: tuple[ColorFamily, ...] = (
    ColorFamily.NAVY,
    ColorFamily.CHARCOAL,
    ColorFamily.GREY,
    ColorFamily.SAND,
    ColorFamily.BLACK,
)


class Pattern(StrEnum):
    SOLID = "solid"
    STRIPED = "striped"
    CHECKED = "checked"
    TEXTURED = "textured"
    PAISLEY = "paisley"


class ChestType(StrEnum):
    ATLETICO = "atletico"
    MEDIO = "medio"
    LARGO = "largo"


class BellyType(StrEnum):
    ATLETICO = "atletico"
    MEDIO = "medio"
    LARGO = "largo"


class Fit(StrEnum):
    SLIM = "slim"
    REGULAR = "regular"


class JacketLength(StrEnum):
    CURTO = "curto"
    REGULAR = "regular"
    LONGO = "longo"


class Occasion(StrEnum):
    CASAMENTO = "casamento"
    TRABALHO = "trabalho"
    ENTREVISTA = "entrevista"
    FORMATURA = "formatura"
    GALA = "gala"
    EVENTO_DIURNO = "evento_diurno"
    VERSATIL = "versatil"


class Season(StrEnum):
    ALL_YEAR = "all_year"
    SUMMER = "summer"
    WINTER = "winter"


class CatalogSource(StrEnum):
    DEMO = "demo"
    FILE = "file"
    SQLITE = "sqlite"
    PAYLOAD = "payload"


TimeOfDay = Literal["dia", "tarde", "noite"]
GuestRole = Literal["noivo", "padrinho", "convidado", "formando", "candidato", "anfitriao"]
EngineMode = Literal["llm", "rule_based"]
ShirtLetter = Literal["PP", "P", "M", "G", "GG", "XG"]


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


class SizeStock(Contract):
    size: str = Field(
        min_length=1,
        max_length=8,
        description="Brazilian size label: suits 46-60, pants 38-54, shirts 1-6, ties U, shoes 37-46.",
    )
    stock: int = Field(ge=0, description="Units available for try-on.")


class Product(BaseModel):
    """A catalog item. Tolerant to extra fields so white-label clients can send richer records."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.:-]+$")
    sku: str = Field(min_length=3, max_length=32, pattern=r"^[A-Z0-9][A-Z0-9-]+$")
    name: str = Field(min_length=1, max_length=120)
    category: Category
    description: str = Field(default="", max_length=600)
    price_cents: int = Field(gt=0, description="Price in minor units (integer money).")
    currency: str = Field(default="BRL", pattern=r"^[A-Z]{3}$")
    color: str = Field(min_length=1, max_length=40, description="Human color name, e.g. 'Azul Marinho'.")
    color_family: ColorFamily
    pattern: Pattern = Pattern.SOLID
    fabric: str = Field(default="", max_length=80)
    style: str | None = Field(default=None, max_length=40, description="e.g. 'oxford', 'brogue', 'loafer'.")
    fit_options: list[Fit] = Field(default_factory=list)
    formality_tags: list[Formality] = Field(min_length=1)
    occasion_tags: list[Occasion] = Field(default_factory=list)
    seasons: list[Season] = Field(default_factory=lambda: [Season.ALL_YEAR])
    sizes: list[SizeStock] = Field(min_length=1)
    image_url: str | None = None
    highlight: str | None = Field(default=None, max_length=40)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def available_sizes(self) -> list[str]:
        return [s.size for s in self.sizes if s.stock > 0]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def in_stock(self) -> bool:
        return any(s.stock > 0 for s in self.sizes)

    @property
    def max_formality_rank(self) -> int:
        return max(FORMALITY_RANK[f] for f in self.formality_tags)


def _ensure_unique_ids(products: list[Product] | None) -> None:
    if not products:
        return
    seen: set[str] = set()
    for product in products:
        if product.id in seen:
            raise ValueError(f"Duplicate product id in catalog: {product.id}")
        seen.add(product.id)


class CatalogResponse(Contract):
    source: CatalogSource
    total: int
    items: list[Product]


# ---------------------------------------------------------------------------
# Anthropometric sizing (Drop 6 algorithm)
# ---------------------------------------------------------------------------


class UserMeasurements(Contract):
    height_cm: int = Field(ge=150, le=210, description="Height in centimeters.")
    weight_kg: int = Field(ge=45, le=160, description="Weight in kilograms.")
    chest_type: ChestType = ChestType.MEDIO
    belly_type: BellyType = BellyType.MEDIO
    shoe_size: int | None = Field(default=None, ge=37, le=46, description="Optional Brazilian shoe size.")


class SizeRecommendation(Contract):
    suit_size: int = Field(ge=46, le=60)
    pants_size: int = Field(ge=38, le=54)
    shirt_size: int = Field(ge=1, le=6)
    shirt_letter: ShirtLetter
    collar_cm: str
    fit: Fit
    drop: int = Field(description="Jacket size minus pants size after clamping.")
    jacket_length: JacketLength
    shoe_size: int | None = None
    estimated_chest_cm: int
    estimated_waist_cm: int
    bmi: float
    effective_weight_kg: float
    summary: str = Field(description="Passport line, e.g. 'Terno 52 Regular | Calça 46 | Camisa 4 (G)'.")
    rationale: list[str]
    algorithm_version: Literal["drop6-v1"] = "drop6-v1"

    def size_for(self, category: Category) -> str | None:
        match category:
            case Category.SUIT:
                return str(self.suit_size)
            case Category.PANTS:
                return str(self.pants_size)
            case Category.SHIRT:
                return str(self.shirt_size)
            case Category.TIE:
                return "U"
            case Category.SHOES:
                return str(self.shoe_size) if self.shoe_size is not None else None


# ---------------------------------------------------------------------------
# Inventory search
# ---------------------------------------------------------------------------


class InventorySearchRequest(Contract):
    category: Category | None = None
    size: str | None = Field(default=None, max_length=8)
    formality: Formality | None = None
    color_query: str | None = Field(default=None, max_length=80)
    query: str | None = Field(
        default=None, max_length=200, description="Free text, e.g. 'gravata vinho para casamento'."
    )
    in_stock_only: bool = True
    limit: int = Field(default=20, ge=1, le=100)
    catalog: list[Product] | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _unique_catalog(self) -> InventorySearchRequest:
        _ensure_unique_ids(self.catalog)
        return self


class InventorySearchResult(Contract):
    source: CatalogSource = CatalogSource.DEMO
    total_matches: int
    items: list[Product]
    resolved_colors: list[ColorFamily] = Field(default_factory=list)
    inferred_category: Category | None = None
    applied_filters: dict[str, str]


# ---------------------------------------------------------------------------
# Looks
# ---------------------------------------------------------------------------


class SuitCombination(Contract):
    """Input of `compose_complete_look`: one suit, shirt, tie and pair of shoes."""

    suit_id: str
    shirt_id: str
    tie_id: str
    shoe_id: str
    target_formality: Formality | None = None
    time_of_day: TimeOfDay | None = None


class ComposeLookRequest(SuitCombination):
    measurements: UserMeasurements | None = Field(
        default=None, description="When present, each item gets the customer's size and stock is checked."
    )
    catalog: list[Product] | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _unique_catalog(self) -> ComposeLookRequest:
        _ensure_unique_ids(self.catalog)
        return self


class LookItem(Contract):
    role: Category
    product: Product
    selected_size: str | None = Field(default=None, description="Customer size for this piece, when known.")


class OutfitRecommendation(Contract):
    look_id: str
    name: str
    items: list[LookItem]
    total_price_cents: int
    harmony_score: int = Field(ge=0, le=100)
    is_valid: bool
    formality: Formality
    occasions: list[Occasion]
    style_rationale: list[str]
    warnings: list[str] = Field(default_factory=list)
    violations: list[str] = Field(default_factory=list)
    ruleset_version: str


# ---------------------------------------------------------------------------
# Stylist recommendation (agentic endpoint)
# ---------------------------------------------------------------------------


class ChatTurn(Contract):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class StylistPreferences(Contract):
    budget_max_cents: int | None = Field(default=None, gt=0)
    preferred_colors: list[ColorFamily] = Field(default_factory=list, description="Suit color families to favor.")
    avoid_colors: list[ColorFamily] = Field(default_factory=list, description="Suit color families to avoid.")


class StylistRecommendRequest(Contract):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)
    measurements: UserMeasurements | None = None
    preferences: StylistPreferences | None = None
    catalog: list[Product] | None = Field(
        default=None,
        max_length=500,
        description="Optional white-label catalog. When omitted the engine uses its configured repository.",
    )
    max_looks: int = Field(default=3, ge=1, le=5)

    @model_validator(mode="after")
    def _unique_catalog(self) -> StylistRecommendRequest:
        _ensure_unique_ids(self.catalog)
        return self


class ExtractedMeasurements(Contract):
    height_cm: int | None = None
    weight_kg: int | None = None
    chest_type: ChestType | None = None
    belly_type: BellyType | None = None
    shoe_size: int | None = None


class ColorIntent(Contract):
    """Colors the customer asked for (prefer) or rejected (avoid) for one category."""

    prefer: list[ColorFamily] = Field(default_factory=list)
    avoid: list[ColorFamily] = Field(default_factory=list)


class StylingContext(Contract):
    occasion: Occasion
    occasion_label: str
    time_of_day: TimeOfDay | None = None
    role: GuestRole | None = None
    target_formality: Formality
    season: Season | None = None
    suit_colors: ColorIntent = Field(default_factory=ColorIntent, description="prefer = ranked palette for suits.")
    shirt_colors: ColorIntent = Field(default_factory=ColorIntent)
    tie_colors: ColorIntent = Field(default_factory=ColorIntent)
    shoe_colors: ColorIntent = Field(default_factory=ColorIntent)
    budget_max_cents: int | None = None
    wants_versatility: bool = False
    measurements_from_text: ExtractedMeasurements | None = None
    detected_keywords: list[str] = Field(default_factory=list)


class ToolCallTrace(Contract):
    tool: str
    arguments: dict[str, JsonValue]
    duration_ms: float
    ok: bool
    result_summary: str


class EngineInfo(Contract):
    mode: EngineMode
    provider: str | None = None
    model: str | None = None
    fallback_reason: str | None = None
    catalog_source: CatalogSource
    graph_path: list[str]
    tool_calls: list[ToolCallTrace]
    latency_ms: float


class StylistRecommendResponse(Contract):
    session_id: str
    reply: str
    recommended_looks: list[OutfitRecommendation]
    suggested_products: list[Product]
    size_profile: SizeRecommendation | None = None
    context: StylingContext
    quick_replies: list[str]
    engine: EngineInfo


# ---------------------------------------------------------------------------
# Operational
# ---------------------------------------------------------------------------


class HealthResponse(Contract):
    status: Literal["ok"]
    service: str
    version: str
    llm_mode: EngineMode
    llm_provider: str | None
    llm_model: str | None
    catalog_source: CatalogSource
    catalog_size: int


class ErrorResponse(Contract):
    detail: str
