"""Deterministic response composition used by `output_structurer_node`."""

from __future__ import annotations

from app.schemas import (
    FORMALITY_LABEL,
    Category,
    ColorFamily,
    Occasion,
    OutfitRecommendation,
    Product,
    SizeRecommendation,
    StylingContext,
)
from app.tools.vocabulary import format_brl

ROLE_INTRO: dict[str, str] = {
    "noivo": "Parabéns pelo casamento! Como noivo, você merece o look mais impecável da cerimônia.",
    "padrinho": "Que honra ser padrinho! O padrinho precisa estar elegante sem competir com o noivo.",
    "formando": "Parabéns pela formatura! É hora de um visual à altura da conquista.",
    "candidato": "Para entrevistas, a regra é transmitir credibilidade sem exageros.",
    "anfitriao": "Como anfitrião, o visual deve ser acolhedor e impecável.",
    "convidado": "Convidado bem-vestido honra o evento e os anfitriões.",
}

OCCASION_INTRO: dict[Occasion, str] = {
    Occasion.CASAMENTO: "Casamento pede elegância clássica e atenção aos detalhes.",
    Occasion.TRABALHO: "No dia a dia profissional, o segredo é sobriedade com versatilidade.",
    Occasion.ENTREVISTA: "Para entrevistas, a regra é transmitir credibilidade sem exageros.",
    Occasion.FORMATURA: "Formatura é celebração: vale um visual marcante e bem cortado.",
    Occasion.GALA: "Evento de gala pede o máximo de formalidade.",
    Occasion.EVENTO_DIURNO: "Eventos diurnos permitem tons mais claros e texturas leves.",
    Occasion.VERSATIL: "Um terno versátil é o investimento mais inteligente do guarda-roupa masculino.",
}

TIME_PHRASE: dict[str, str] = {"dia": " durante o dia", "tarde": " à tarde", "noite": " à noite"}

CATEGORY_LABEL_PT: dict[Category, str] = {
    Category.SUIT: "ternos",
    Category.SHIRT: "camisas",
    Category.PANTS: "calças",
    Category.TIE: "gravatas",
    Category.SHOES: "sapatos",
}

SUGGESTION_PRIORITY: tuple[Category, ...] = (
    Category.PANTS,
    Category.TIE,
    Category.SHIRT,
    Category.SHOES,
    Category.SUIT,
)


def compose_reply(
    context: StylingContext,
    size_profile: SizeRecommendation | None,
    looks: list[OutfitRecommendation],
    missing: list[Category],
) -> str:
    intro = ROLE_INTRO.get(context.role or "", OCCASION_INTRO[context.occasion])
    time_phrase = TIME_PHRASE.get(context.time_of_day or "", "")
    lines = [
        intro,
        f"Para {context.occasion_label}{time_phrase}, o dress code ideal é {FORMALITY_LABEL[context.target_formality]}.",
    ]
    if size_profile is not None:
        lines.append(
            f"Usei seu passaporte de medidas ({size_profile.summary}) e considerei apenas peças disponíveis no seu tamanho."
        )
    else:
        lines.append(
            "Ainda não tenho suas medidas: informe altura, peso e biotipo para eu filtrar só o que veste bem em você."
        )

    if looks:
        plural = "looks completos" if len(looks) > 1 else "look completo"
        lines.append(f"Montei {len(looks)} {plural}:")
        for index, look in enumerate(looks, start=1):
            reason = look.style_rationale[0] if look.style_rationale else "Combinação validada pelas regras clássicas."
            lines.append(f"{index}. {look.name} — {reason} Total: {format_brl(look.total_price_cents)}.")
        if context.budget_max_cents is not None and all(
            look.total_price_cents > context.budget_max_cents for look in looks
        ):
            lines.append(
                f"Os looks ficaram acima do orçamento de {format_brl(context.budget_max_cents)}; "
                "posso trocar peças por alternativas mais acessíveis."
            )
    else:
        missing_text = ", ".join(CATEGORY_LABEL_PT[c] for c in missing) or "algumas categorias"
        lines.append(
            f"Não encontrei combinações completas em estoque para {missing_text} no seu tamanho. "
            "Posso sugerir outras cores ou um ajuste sob medida."
        )
    lines.append("Quer que eu ajuste cores, orçamento ou formalidade?")
    return "\n".join(lines)


def quick_replies(context: StylingContext, size_profile: SizeRecommendation | None) -> list[str]:
    replies: list[str] = []
    replies.append(
        "Tenho 1,80 m e 85 kg, tórax e abdômen médios" if size_profile is None else "Quero opções até R$ 3.500"
    )
    if context.occasion is Occasion.CASAMENTO:
        replies.append(
            "E para um casamento de dia?" if context.time_of_day == "noite" else "E se o casamento for à noite?"
        )
    elif context.occasion in (Occasion.TRABALHO, Occasion.VERSATIL):
        replies.append("Agora um look para casamento à tarde")
    else:
        replies.append("Preciso de um terno versátil para trabalho e eventos")
    first_color = context.suit_colors.prefer[0] if context.suit_colors.prefer else None
    replies.append("Prefiro tons de cinza" if first_color is ColorFamily.NAVY else "Prefiro terno azul-marinho")
    return replies


def suggested_products(
    inventory: dict[str, list[Product]], looks: list[OutfitRecommendation], limit: int = 4
) -> list[Product]:
    """Complementary pieces not used in the looks: one per category first, then fill up to `limit`."""
    used = {item.product.id for look in looks for item in look.items}
    suggestions: list[Product] = []
    for per_category in (1, limit):
        for category in SUGGESTION_PRIORITY:
            taken = sum(1 for p in suggestions if p.category is category)
            for product in inventory.get(category.value, []):
                if len(suggestions) >= limit or taken >= per_category:
                    break
                if product.id in used or any(p.id == product.id for p in suggestions):
                    continue
                suggestions.append(product)
                taken += 1
    return suggestions


def message_text(content: object) -> str:
    """Extract plain text from LangChain message content (str or list of content blocks)."""
    if isinstance(content, str):
        return content.strip()
    parts: list[str] = []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
    return "".join(parts).strip()
