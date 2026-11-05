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

- [x] Rate limiting por cliente (429 + `Retry-After`), limite de tamanho do corpo (413) e CORS restrito por padrão — owner: Claude Code · since: 2026-11-05
- [x] Orçamento global de requisições ao LLM por minuto, degradando para `rule_based` sem erro — owner: Claude Code · since: 2026-11-05
- [x] CI no GitHub Actions: ruff, mypy, pytest (Python 3.11–3.13) e smoke test da imagem Docker — owner: Claude Code · since: 2026-11-05
- [x] Export de contratos idêntico em Python 3.11–3.13 (descrição explícita do 422) — owner: Claude Code · since: 2026-11-05

## Backlog (registrado na análise de 2026-11-05)

Prioridade: **P0** = antes de produção · **P1** = engenharia de alto valor · **P2** = evolução de produto/portfólio.

- [ ] **P0** · Renomear o branch padrão `claude/alfaiataria-delivery-stylist-3ki4wz` para `main` e mesclar via PR — owner: _livre_
- [ ] **P1** · Validar o modo LLM com chave real e criar uma suíte de evals (prompts de referência → asserções, ex.: black tie ⇒ só terno preto; LLM-as-judge para a justificativa) — owner: _livre_
- [ ] **P1** · Reconciliar o texto final do LLM com os looks que sobreviveram ao filtro de tamanho (hoje o texto pode citar um look removido) — owner: _livre_
- [ ] **P1** · Catálogo por tenant para não reenviar o catálogo inteiro a cada mensagem (`CATALOG_DATABASE_URL`, cache com versão/ETag) — owner: _livre_
- [ ] **P1** · NLU: reconhecer "1m80", "1 metro e 80" e variações; extração de contexto opcional via LLM com fallback para as regras — owner: _livre_
- [ ] **P2** · Looks com blazer + calça avulsa e regras de acessórios (cinto acompanha o sapato, lenço, meias) em `harmony_rules.json` — owner: _livre_
- [ ] **P2** · Endpoint/dataset de feedback "tamanho recomendado × tamanho que ficou" para calibrar as faixas do Drop 6 — owner: _livre_
- [ ] **P2** · Observabilidade de LLM: tokens, custo e latência por requisição no `EngineInfo` + tracing (LangSmith/OpenTelemetry) — owner: _livre_
- [ ] **P2** · Streaming SSE da resposta do stylist e memória de sessão com checkpointer LangGraph (Postgres/Redis) — owner: _livre_
- [ ] **P2** · Demo pública da engine (Render/Fly/Railway via Docker) com GIF no README — owner: _livre_
- [ ] **P2** · API keys por tenant e limites distribuídos (gateway/Redis) para várias réplicas — owner: _livre_
- [ ] **P2** · Busca vetorial opcional (embeddings) atrás da interface de `search_inventory` — owner: _livre_

## Log

| Data | Agente | Resumo |
|---|---|---|
| 2026-11-05 | Claude Code | Bootstrap completo: contratos, tools, grafo LangGraph, API, Docker, testes, SDD e vetores de paridade. |
| 2026-11-05 | Claude Code | Validação cruzada com o storefront: 51 testes de paridade TS e 7 testes de contrato ao vivo verdes. |
| 2026-11-05 | Claude Code | Hardening pós-análise: rate limiting, 413, CORS restrito, orçamento de LLM, CI 3.11–3.13 + Docker; backlog priorizado registrado. |
