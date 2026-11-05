# TASK BOARD — Tailor AI Engine

Quadro de coordenação entre agentes (**Claude Code**, **Antigravity**, **OpenCode**, **Hermes Agent**) e humanos.

## Protocolo

1. **Reivindique** antes de começar: preencha `owner` e `since` na tarefa (uma tarefa = um dono).
2. **Trave arquivos sensíveis** listando-os em *Locks* enquanto trabalha (`app/schemas.py`, `harmony_rules.json`).
3. **Conclua** somente com a *Definition of Done* verde (ruff, mypy strict, pytest) e marque `[x]`.
4. **Registre** no *Log* (data, agente, resumo). Conflitos: o SDD é a fonte da verdade; proponha mudança no SDD primeiro.

## Locks ativos

| Arquivo | Agente | Desde | Motivo |
|---|---|---|---|
| — | — | — | — |

## Fase 1 — Governança & contratos

- [x] `AGENTS.md`, `CLAUDE.md`, `.gitignore`, `README.md` (EN/PT) — owner: Claude Code
- [x] `docs/SDD.md` com C4, grafo LangGraph, sequência, Drop 6 e contrato OpenAPI/JSON — owner: Claude Code
- [x] Contratos Pydantic v2 em `app/schemas.py` (`API_VERSION = 1.0.0`) — owner: Claude Code
- [x] Export automático: `docs/contracts/openapi.json`, `schemas/*.schema.json`, `langgraph.mmd` — owner: Claude Code

## Fase 2 — Motor agêntico

- [x] `calculate_tailoring_size` (Drop 6, aritmética inteira, 46–60 / 38–54 / 1–6, Slim/Regular) — owner: Claude Code
- [x] `search_inventory` léxico-semântico (sinônimos PT-BR, inferência de categoria, tamanho em estoque) — owner: Claude Code
- [x] `compose_complete_look` + `harmony_rules.json` (`classic-etiquette-v1`) — owner: Claude Code
- [x] Repositórios de catálogo: demo, arquivo JSON, SQLite e payload — owner: Claude Code
- [x] `mock_catalog.json` genérico com 21 produtos (6 ternos, 4 camisas, 2 calças, 5 gravatas, 4 sapatos) — owner: Claude Code
- [x] `StateGraph`: `intake_node` → `measurement_tool_node` → `stylist_matcher_node` ⇄ `tool_executor_node` → `output_structurer_node` — owner: Claude Code
- [x] LLM tool calling (Anthropic/OpenAI) com fallback auto-curável para o planner rule-based — owner: Claude Code
- [x] Endpoints `GET /health`, `POST /api/v1/fit-finder`, `POST /api/v1/stylist/recommend` (+ catalog, inventory/search, looks/compose) — owner: Claude Code
- [x] `Dockerfile` (non-root, healthcheck, CA corporativa opcional) e `requirements*.txt` / `pyproject.toml` — owner: Claude Code

## Fase 3 — Qualidade & paridade

- [x] Testes: sizing, inventory, harmony, intake, grafo (incl. LLM roteirizado e fallbacks), API, contratos — owner: Claude Code
- [x] Vetores de paridade (`docs/contracts/parity/`) para portes do motor determinístico — owner: Claude Code
- [x] `ruff check` + `ruff format --check` + `mypy --strict` verdes — owner: Claude Code
- [x] Imagem Docker construída e `/health` saudável no contêiner — owner: Claude Code

## Fase 4 — Validação cruzada

- [x] Storefront (`storefront-web`) consome `/api/v1/fit-finder` e `/api/v1/stylist/recommend` com catálogo via payload — owner: Claude Code
- [x] Local Fallback Adapter (TypeScript) reproduz os vetores de paridade — owner: Claude Code
- [x] Teste de contrato ao vivo: resposta da API (rule-based) = adapter local para o catálogo da loja — owner: Claude Code

## Fase 5 — Hardening pós-análise (2026-11-05)

- [ ] Rate limiting por cliente (429 + `Retry-After`), limite de tamanho do corpo (413) e CORS restrito por padrão — owner: Claude Code · since: 2026-11-05
- [ ] Orçamento global de requisições ao LLM por minuto, degradando para `rule_based` sem erro — owner: Claude Code · since: 2026-11-05
- [ ] CI no GitHub Actions: ruff, mypy, pytest (Python 3.11–3.13) e smoke test da imagem Docker — owner: Claude Code · since: 2026-11-05

## Backlog (próximos)

- [ ] Busca vetorial opcional (embeddings) atrás da interface de `search_inventory` — owner: _livre_
- [ ] Memória de sessão com checkpointer LangGraph (Postgres/Redis) — owner: _livre_
- [ ] Streaming SSE da resposta do stylist — owner: _livre_
- [ ] Avaliação offline de looks (LLM-as-judge) e dataset de regressão — owner: _livre_
- [ ] Rate limiting e API keys por tenant no gateway — owner: _livre_

## Log

| Data | Agente | Resumo |
|---|---|---|
| 2026-11-05 | Claude Code | Bootstrap completo: contratos, tools, grafo LangGraph, API, Docker, testes, SDD e vetores de paridade. |
| 2026-11-05 | Claude Code | Validação cruzada com o storefront: 51 testes de paridade TS e 7 testes de contrato ao vivo verdes. |
