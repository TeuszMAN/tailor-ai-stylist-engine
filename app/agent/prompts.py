"""Prompt templates for the LLM-powered `stylist_matcher_node`."""

from __future__ import annotations

import json
from collections import Counter

from app.schemas import FORMALITY_LABEL, Category, Product, SizeRecommendation, StylingContext

SYSTEM_PROMPT = """Você é um Personal Stylist especialista em alfaiataria masculina clássica.
Seu trabalho é montar looks completos (terno + camisa + gravata + sapato) usando SOMENTE
peças reais do catálogo, disponíveis no tamanho do cliente.

Regras inegociáveis:
1. Use a ferramenta `search_inventory` para cada categoria (suit, shirt, tie, shoes) antes de compor.
   Sempre informe o tamanho do cliente quando ele for conhecido.
2. Valide cada proposta com `compose_complete_look`. Só recomende looks com "is_valid": true.
3. Nunca invente ids, preços ou produtos. Use exatamente os nomes de look retornados pela ferramenta.
4. Respeite a etiqueta: black tie exige terno preto, camisa branca e oxford preto; sapato preto
   nunca com terno bege; terno preto nunca com sapato marrom; à noite prefira sapatos pretos.
5. Proponha de 2 a {max_looks} looks variados, explicando em uma frase por que cada um funciona.
6. Responda em português do Brasil, em tom consultivo, caloroso e objetivo (máximo 120 palavras),
   sem JSON e sem markdown pesado. Termine com uma pergunta curta para refinar a escolha."""


def _sizes_line(size_profile: SizeRecommendation | None) -> str:
    if size_profile is None:
        return "Medidas ainda não informadas: busque sem filtro de tamanho e sugira o Fit Finder."
    shoe = size_profile.shoe_size if size_profile.shoe_size is not None else "não informado"
    return (
        f"Passaporte de medidas: {size_profile.summary}. Tamanhos para busca: suit={size_profile.suit_size}, "
        f"shirt={size_profile.shirt_size}, pants={size_profile.pants_size}, tie=U, shoes={shoe}."
    )


def build_user_brief(
    message: str,
    context: StylingContext,
    size_profile: SizeRecommendation | None,
    catalog: list[Product],
    max_looks: int,
) -> str:
    counts = Counter(p.category.value for p in catalog if p.in_stock)
    stock = ", ".join(f"{c.value}={counts.get(c.value, 0)}" for c in Category)
    context_json = json.dumps(
        context.model_dump(mode="json", exclude={"detected_keywords", "measurements_from_text"}),
        ensure_ascii=False,
    )
    return (
        f'Mensagem do cliente: "{message}"\n'
        f"Contexto extraído deterministicamente: {context_json}\n"
        f"Dress code alvo: {FORMALITY_LABEL[context.target_formality]} ({context.target_formality.value}).\n"
        f"{_sizes_line(size_profile)}\n"
        f"Catálogo em estoque por categoria: {stock}.\n"
        f"Monte até {max_looks} looks completos e valide-os com compose_complete_look."
    )
