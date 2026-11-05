"""Deterministic PT-BR vocabulary shared by the intake node and the inventory search.

Everything here is pure and side-effect free. The storefront's TypeScript Local
Fallback Adapter ports this module 1:1 and is verified against the parity vectors
in `docs/contracts/parity/` — keep both sides in sync when editing phrases.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Generic, TypeVar

from app.schemas import BellyType, Category, ChestType, ColorFamily, Formality, GuestRole, Occasion, Season, TimeOfDay

K = TypeVar("K")

_NON_TEXT = re.compile(r"[^a-z0-9$,.]+")
_SPACES = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Lowercase, strip accents and punctuation (keeps digits, `$`, `,` and `.`)."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    without_marks = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return _SPACES.sub(" ", _NON_TEXT.sub(" ", without_marks)).strip()


@dataclass(frozen=True)
class PhraseMatch(Generic[K]):
    key: K
    phrase: str
    start: int
    end: int


def _phrase_pattern(phrase: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])")


def find_phrases(text: str, vocabulary: Mapping[K, Iterable[str]]) -> list[PhraseMatch[K]]:
    """Longest-phrase-first matching with consumed spans, ordered by position.

    `text` must already be normalized. A span consumed by a longer phrase
    ("azul celeste") can't be matched again by a shorter one ("azul").
    """
    entries = sorted(
        ((phrase, key) for key, phrases in vocabulary.items() for phrase in phrases),
        key=lambda item: (-len(item[0]), item[0]),
    )
    consumed = [False] * len(text)
    matches: list[PhraseMatch[K]] = []
    for phrase, key in entries:
        for found in _phrase_pattern(phrase).finditer(text):
            start, end = found.span()
            if any(consumed[start:end]):
                continue
            for i in range(start, end):
                consumed[i] = True
            matches.append(PhraseMatch(key=key, phrase=phrase, start=start, end=end))
    matches.sort(key=lambda m: m.start)
    return matches


def first_key(text: str, vocabulary: Mapping[K, Iterable[str]], priority: Iterable[K]) -> tuple[K, list[str]] | None:
    """Return the highest-priority key with at least one phrase in `text`, plus the matched phrases."""
    found = find_phrases(text, vocabulary)
    hits = {m.key for m in found}
    for key in priority:
        if key in hits:
            return key, [m.phrase for m in found if m.key == key]
    return None


def blank_phrases(text: str, phrases: Iterable[str]) -> str:
    """Replace phrases by spaces (keeps offsets stable for later matching)."""
    for phrase in sorted(phrases, key=len, reverse=True):
        text = _phrase_pattern(phrase).sub(lambda m: " " * len(m.group(0)), text)
    return text


# ---------------------------------------------------------------------------
# Lexicons
# ---------------------------------------------------------------------------

COLOR_SYNONYMS: dict[ColorFamily, tuple[str, ...]] = {
    ColorFamily.NAVY: ("azul marinho", "marinho", "azul escuro", "navy", "azul"),
    ColorFamily.CHARCOAL: ("cinza chumbo", "chumbo", "grafite", "cinza escuro", "charcoal"),
    ColorFamily.GREY: ("cinza claro", "cinza mescla", "mescla", "cinza", "grey", "gray"),
    ColorFamily.SAND: ("bege areia", "areia", "bege", "off white", "sand"),
    ColorFamily.BLACK: ("preto", "preta", "negro", "black"),
    ColorFamily.WHITE: ("branca", "branco", "white"),
    ColorFamily.LIGHT_BLUE: ("azul celeste", "celeste", "azul claro", "azul bebe", "light blue"),
    ColorFamily.BLUE_STRIPE: ("listrada", "listrado", "listras", "riscas"),
    ColorFamily.PINK: ("rosa antigo", "rosa", "rose", "pink"),
    ColorFamily.BURGUNDY: ("bordo", "vinho", "marsala", "burgundy"),
    ColorFamily.SILVER: ("prata", "prateada", "prateado", "silver"),
    ColorFamily.EMERALD: ("verde esmeralda", "esmeralda", "verde", "emerald"),
    ColorFamily.LAVENDER: ("lavanda", "lilas", "lavender"),
    ColorFamily.BROWN: ("cafe", "marrom", "chocolate", "tabaco", "brown"),
    ColorFamily.COGNAC: ("conhaque", "caramelo", "cognac", "whisky"),
    ColorFamily.KHAKI: ("caqui", "khaki"),
}

# Generic words that customers use for more than one family ("terno cinza" = light or charcoal grey).
COLOR_PHRASE_EXPANSION: dict[str, tuple[ColorFamily, ...]] = {
    "cinza": (ColorFamily.GREY, ColorFamily.CHARCOAL),
}


def families_for(match: PhraseMatch[ColorFamily]) -> tuple[ColorFamily, ...]:
    return COLOR_PHRASE_EXPANSION.get(match.phrase, (match.key,))


COLOR_LABEL: dict[ColorFamily, str] = {
    ColorFamily.NAVY: "azul-marinho",
    ColorFamily.CHARCOAL: "cinza-chumbo",
    ColorFamily.GREY: "cinza-claro",
    ColorFamily.SAND: "bege-areia",
    ColorFamily.BLACK: "preto",
    ColorFamily.WHITE: "branca",
    ColorFamily.LIGHT_BLUE: "azul-celeste",
    ColorFamily.BLUE_STRIPE: "listrada em azul",
    ColorFamily.PINK: "rosa",
    ColorFamily.BURGUNDY: "bordô",
    ColorFamily.SILVER: "prata",
    ColorFamily.EMERALD: "verde-esmeralda",
    ColorFamily.LAVENDER: "lavanda",
    ColorFamily.BROWN: "café",
    ColorFamily.COGNAC: "conhaque",
    ColorFamily.KHAKI: "cáqui",
}

CATEGORY_SYNONYMS: dict[Category, tuple[str, ...]] = {
    Category.SUIT: ("terno", "ternos", "paleto", "paletos", "blazer", "costume", "suit"),
    Category.SHIRT: ("camisa", "camisas", "shirt"),
    Category.PANTS: ("calca", "calcas", "pants"),
    Category.TIE: ("gravata", "gravatas", "necktie"),
    Category.SHOES: ("sapato", "sapatos", "calcado", "calcados", "oxford", "brogue", "mocassim", "loafer", "monk"),
}

OCCASION_KEYWORDS: dict[Occasion, tuple[str, ...]] = {
    Occasion.CASAMENTO: ("casamento", "casar", "casorio", "noivo", "padrinho", "bodas", "wedding"),
    Occasion.FORMATURA: ("formatura", "colacao", "graduacao", "formando", "baile de formatura"),
    Occasion.ENTREVISTA: ("entrevista", "processo seletivo", "dinamica de grupo"),
    Occasion.GALA: ("gala", "black tie", "traje a rigor", "rigor", "smoking", "baile"),
    Occasion.VERSATIL: (
        "versatil",
        "coringa",
        "varias ocasioes",
        "multiuso",
        "primeiro terno",
        "trabalho e eventos",
    ),
    Occasion.EVENTO_DIURNO: (
        "batizado",
        "almoco",
        "brunch",
        "evento diurno",
        "ao ar livre",
        "praia",
        "jardim",
        "festa de dia",
    ),
    Occasion.TRABALHO: (
        "trabalho",
        "escritorio",
        "reuniao",
        "reunioes",
        "corporativo",
        "executivo",
        "expediente",
        "negocios",
        "dia a dia",
        "business",
        "audiencia",
        "palestra",
    ),
}

OCCASION_PRIORITY: tuple[Occasion, ...] = (
    Occasion.CASAMENTO,
    Occasion.FORMATURA,
    Occasion.ENTREVISTA,
    Occasion.GALA,
    Occasion.VERSATIL,
    Occasion.EVENTO_DIURNO,
    Occasion.TRABALHO,
)

OCCASION_LABEL: dict[Occasion, str] = {
    Occasion.CASAMENTO: "casamento",
    Occasion.TRABALHO: "rotina de trabalho",
    Occasion.ENTREVISTA: "entrevista de emprego",
    Occasion.FORMATURA: "formatura",
    Occasion.GALA: "evento de gala",
    Occasion.EVENTO_DIURNO: "evento diurno",
    Occasion.VERSATIL: "guarda-roupa versátil",
}

OCCASION_FORMALITY: dict[Occasion, Formality] = {
    Occasion.CASAMENTO: Formality.FORMAL,
    Occasion.FORMATURA: Formality.FORMAL,
    Occasion.GALA: Formality.BLACK_TIE,
    Occasion.ENTREVISTA: Formality.BUSINESS,
    Occasion.TRABALHO: Formality.BUSINESS,
    Occasion.EVENTO_DIURNO: Formality.SMART_CASUAL,
    Occasion.VERSATIL: Formality.BUSINESS,
}

FORMALITY_KEYWORDS: dict[Formality, tuple[str, ...]] = {
    Formality.BLACK_TIE: ("black tie", "traje a rigor", "smoking", "gala", "rigor"),
    Formality.FORMAL: ("passeio completo", "formal", "cerimonia"),
    Formality.SMART_CASUAL: ("esporte fino", "smart casual", "despojado", "informal"),
    Formality.BUSINESS: ("traje social", "passeio"),
}

FORMALITY_PRIORITY: tuple[Formality, ...] = (
    Formality.BLACK_TIE,
    Formality.FORMAL,
    Formality.SMART_CASUAL,
    Formality.BUSINESS,
)

TIME_KEYWORDS: dict[TimeOfDay, tuple[str, ...]] = {
    "noite": ("a noite", "de noite", "noite", "noturno", "noturna", "jantar"),
    "tarde": ("a tarde", "de tarde", "fim de tarde", "tarde", "por do sol", "entardecer"),
    "dia": ("de manha", "manha", "de dia", "diurno", "diurna", "almoco", "brunch", "ao ar livre", "praia"),
}

TIME_PRIORITY: tuple[TimeOfDay, ...] = ("noite", "tarde", "dia")

SEASON_KEYWORDS: dict[Season, tuple[str, ...]] = {
    Season.SUMMER: ("verao", "calor", "praia", "quente", "calorento"),
    Season.WINTER: ("inverno", "frio", "serra", "gelado"),
}

SEASON_PRIORITY: tuple[Season, ...] = (Season.SUMMER, Season.WINTER)

ROLE_KEYWORDS: dict[GuestRole, tuple[str, ...]] = {
    "noivo": ("noivo", "vou casar", "meu casamento", "minha noiva"),
    "padrinho": ("padrinho",),
    "formando": ("formando", "minha formatura", "me formar", "vou me formar"),
    "candidato": ("entrevista",),
    "anfitriao": ("anfitriao", "vou receber", "minha festa"),
    "convidado": ("convidado", "fui convidado", "convite"),
}

ROLE_PRIORITY: tuple[GuestRole, ...] = ("noivo", "padrinho", "formando", "candidato", "anfitriao", "convidado")

VERSATILITY_KEYWORDS: tuple[str, ...] = OCCASION_KEYWORDS[Occasion.VERSATIL]

CHEST_KEYWORDS: dict[ChestType, tuple[str, ...]] = {
    ChestType.LARGO: ("ombros largos", "peito largo", "torax largo", "corpulento", "parrudo", "encorpado", "robusto"),
    ChestType.ATLETICO: ("atletico", "malho", "musculoso", "academia", "musculacao", "sarado", "forte"),
}

BELLY_KEYWORDS: dict[BellyType, tuple[str, ...]] = {
    BellyType.ATLETICO: (
        "sem barriga",
        "tanquinho",
        "abdomen definido",
        "abdomen atletico",
        "barriga chapada",
        "abdomen chapado",
    ),
    BellyType.MEDIO: ("barriguinha", "pouca barriga", "um pouco de barriga", "barriga pequena"),
    BellyType.LARGO: (
        "barriga saliente",
        "barriga grande",
        "abdomen saliente",
        "abdomen largo",
        "barrigudo",
        "panca",
        "barriga",
    ),
}

NEGATION_BEFORE = re.compile(
    r"(?:^|\s)(?:sem|nao|nada de|evitar|evito|evite|odeio|exceto|menos|tirando)\s+(?:[a-z0-9]+\s+){0,2}$"
)

STOPWORDS: frozenset[str] = frozenset(
    [
        "a",
        "o",
        "as",
        "os",
        "um",
        "uma",
        "de",
        "do",
        "da",
        "dos",
        "das",
        "e",
        "em",
        "no",
        "na",
        "nos",
        "nas",
        "para",
        "pra",
        "por",
        "com",
        "que",
        "me",
        "meu",
        "minha",
        "eu",
        "quero",
        "preciso",
        "algo",
        "tem",
        "tenho",
        "ser",
        "sou",
        "vou",
        "mais",
        "muito",
        "bem",
        "ao",
        "aos",
        "se",
        "como",
    ]
)


def tokenize(text: str) -> list[str]:
    """Normalized tokens without stopwords (used by the lexical-semantic search)."""
    return [t for t in re.split(r"[\s,.$]+", normalize(text)) if t and t not in STOPWORDS]


def resolve_colors(text: str) -> list[ColorFamily]:
    """Color families mentioned in free text, in order of appearance."""
    normalized = blank_phrases(normalize(text), FORMALITY_KEYWORDS[Formality.BLACK_TIE])
    ordered: list[ColorFamily] = []
    for match in find_phrases(normalized, COLOR_SYNONYMS):
        for family in families_for(match):
            if family not in ordered:
                ordered.append(family)
    return ordered


def format_brl(cents: int) -> str:
    """Integer-safe BRL formatting: 381700 -> 'R$ 3.817,00'."""
    reais, centavos = divmod(abs(cents), 100)
    digits = str(reais)
    groups: list[str] = []
    while len(digits) > 3:
        groups.insert(0, digits[-3:])
        digits = digits[:-3]
    groups.insert(0, digits)
    sign = "-" if cents < 0 else ""
    return f"{sign}R$ {'.'.join(groups)},{centavos:02d}"
