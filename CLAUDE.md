# CLAUDE.md — Tailor AI Engine

Guia para o Claude Code neste repositório. As regras completas e compartilhadas por todos os agentes
estão em [`AGENTS.md`](AGENTS.md). Leia-o junto com este arquivo.

@AGENTS.md

## Fluxo obrigatório

1. Leia `docs/SDD.md` e `docs/TASK_BOARD.md` antes de modificar código; reivindique a tarefa no board.
2. Trabalhe em passos pequenos e rode, antes de cada commit:
   `ruff check app tests scripts && ruff format --check app tests scripts && mypy app scripts && pytest`
3. Alterou `app/schemas.py`, `harmony_rules.json`, `vocabulary.py`, `sizing.py` ou o planner? Rode
   `python -m scripts.export_contracts && python -m scripts.generate_parity_vectors` e commite os arquivos gerados.
4. Marque a tarefa como `[x]` no `docs/TASK_BOARD.md`.

## Lembretes

* Repositório **público**: zero dados de loja real, telefones ou segredos. Use `.env` (ignorado pelo Git).
* Pydantic v2 em todo contrato; `mypy --strict` sem `# type: ignore` novos sem justificativa.
* Sem API key o motor roda em `rule_based`: os testes nunca dependem de rede.
* Modelos padrão: `ANTHROPIC_MODEL=claude-opus-5-5`, `OPENAI_MODEL=gpt-4.1-mini` (configuráveis por env).
