# AGENTS.md — Tailor AI Engine

Instruções para **qualquer agente de código** (Claude Code, Antigravity, OpenCode, Hermes Agent) e humanos.

## 0. Antes de tocar no código

1. Leia [`docs/SDD.md`](docs/SDD.md) (arquitetura, contratos, algoritmo Drop 6, regras de harmonia).
2. Leia [`docs/TASK_BOARD.md`](docs/TASK_BOARD.md) e **reivindique** a tarefa (campo `owner` + data) antes de começar.
3. Este repositório é **PÚBLICO**: nunca adicione nomes reais de lojas, telefones/WhatsApp, e-mails, chaves de API
   ou dados de clientes. Tudo que é específico de negócio entra por variável de ambiente ou payload.

## 1. Comandos

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt          # runtime + pytest, httpx, ruff, mypy
uvicorn app.main:app --reload --port 8000    # http://localhost:8000/docs
```

| Tarefa | Comando |
|---|---|
| Lint | `ruff check app tests scripts` |
| Formatação | `ruff format app tests scripts` |
| Tipagem (strict) | `mypy app scripts` |
| Testes | `pytest` |
| Exportar contratos (OpenAPI, JSON Schema, Mermaid) | `python -m scripts.export_contracts` |
| Regenerar vetores de paridade | `python -m scripts.generate_parity_vectors` |
| Catálogo em SQLite | `python -m scripts.seed_sqlite app/catalog/mock_catalog.json catalog.db` |
| Docker | `docker build -t tailor-ai-engine . && docker run -p 8000:8000 tailor-ai-engine` |

**Definition of Done:** `ruff check`, `ruff format --check`, `mypy app scripts` e `pytest` verdes — os mesmos gates
rodam no CI (`.github/workflows/ci.yml`, Python 3.11–3.13 + smoke test Docker), que também precisa ficar verde.

## 2. Regras de arquitetura

* **Pydantic v2 é obrigatório** para todo dado que cruza fronteira (HTTP, estado do grafo, I/O de tools).
  Contratos vivem em `app/schemas.py`; nada de `dict` solto em assinaturas públicas.
* **Tipagem estrita:** `mypy --strict` deve passar; evite `Any` (permitido só na borda com LangChain/LangGraph).
* **Tools são determinísticas e puras** (`app/tools/`): sem I/O de rede, sem aleatoriedade, sem relógio.
* **Regras de harmonia são dados** (`app/tools/harmony_rules.json`). Mudou regra ⇒ atualize SDD §6 e os vetores de paridade.
* **Isolamento de responsabilidades:**
  `schemas` (contratos) → `tools` (domínio) → `agent` (orquestração) → `main` (HTTP). Dependências só nessa direção.
* O fallback rule-based deve continuar falando o **mesmo protocolo de tool calling** do LLM.
* Dinheiro sempre em **centavos inteiros**. Tamanhos são `str` nos produtos (`"52"`, `"4"`, `"U"`).

## 3. Mudança de contrato (checklist)

1. Edite `app/schemas.py` (campos novos devem ser opcionais para manter compatibilidade em `/api/v1`).
2. `python -m scripts.export_contracts && python -m scripts.generate_parity_vectors`.
3. Atualize `docs/SDD.md` §8 e avise os clientes (o storefront copia `docs/contracts/` para seus fixtures).
4. Breaking change ⇒ nova rota `/api/v2` e incremento de `API_VERSION`.

## 4. Convenções

* Commits: Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`).
* Código e identificadores em inglês; textos voltados ao cliente final em PT-BR.
* Ao concluir uma tarefa, marque `[x]` no `docs/TASK_BOARD.md` e registre o agente no log.
