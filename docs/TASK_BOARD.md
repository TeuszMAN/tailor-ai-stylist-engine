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
  - ↳ 2026-11-07: incluir nos evals os casos do P0 "Guarda-corpos de saída do modo LLM" (override de formalidade, texto com preço inventado e casos de injeção de prompt).
- [ ] **P1** · Reconciliar o texto final do LLM com os looks que sobreviveram ao filtro de tamanho (hoje o texto pode citar um look removido) — owner: _livre_
  - ↳ 2026-11-07: incorporado ao P0 "Guarda-corpos de saída do modo LLM" abaixo; nada impede o texto de citar preço ou desconto que não existem (num teste com LLM roteirizado, um texto assim passou sem conferência).
- [ ] **P1** · Catálogo por tenant para não reenviar o catálogo inteiro a cada mensagem (`CATALOG_DATABASE_URL`, cache com versão/ETag) — owner: _livre_
  - ↳ 2026-11-07: o storefront envia o catálogo inteiro no recommend e na busca; com mais de 500 produtos, ou com um produto que viole o schema daqui, os dois dão 422 e ele fica no motor local sem aviso.
- [ ] **P1** · NLU: reconhecer "1m80", "1 metro e 80" e variações; extração de contexto opcional via LLM com fallback para as regras — owner: _livre_
  - ↳ 2026-11-07: ver o P1 [Ambos] "NLU do intake" abaixo, com a lista verificada de frases que falham hoje.
- [ ] **P2** · Looks com blazer + calça avulsa e regras de acessórios (cinto acompanha o sapato, lenço, meias) em `harmony_rules.json` — owner: _livre_
- [ ] **P2** · Endpoint/dataset de feedback "tamanho recomendado × tamanho que ficou" para calibrar as faixas do Drop 6 — owner: _livre_
- [ ] **P2** · Observabilidade de LLM: tokens, custo e latência por requisição no `EngineInfo` + tracing (LangSmith/OpenTelemetry) — owner: _livre_
- [ ] **P2** · Streaming SSE da resposta do stylist e memória de sessão com checkpointer LangGraph (Postgres/Redis) — owner: _livre_
- [ ] **P2** · Demo pública da engine (Render/Fly/Railway via Docker) com GIF no README — owner: _livre_
- [ ] **P2** · API keys por tenant e limites distribuídos (gateway/Redis) para várias réplicas — owner: _livre_
- [ ] **P2** · Busca vetorial opcional (embeddings) atrás da interface de `search_inventory` — owner: _livre_

## Backlog (registrado na revisão verificada de 2026-11-07)

Revisão de 2026-11-07 com Claude Code, Gemini e OpenCode: 115 pontos conferidos por reprodução ou leitura de código, com
arquivo e linha. Mesma escala de prioridade do backlog acima. **[Ambos]** = o porte TypeScript do storefront
(`src/lib/engine/local/`) tem o mesmo bug: corrigir aqui, regenerar os vetores de paridade e espelhar lá. O modo LLM foi
exercitado só com um LLM roteirizado, sem provedor real. Achados de segurança ainda abertos aparecem aqui só de forma
genérica; os detalhes ficam no board privado do storefront, sob o mesmo nome do item.

- [ ] **P0** · [Ambos] Tamanho errado por descrição do corpo: frases negadas ou neutras ("não tenho barriga", "barriga normal", "não sou barrigudo", "sem ombros largos") viram abdômen ou tórax largo, e qualquer "forte" ("calor forte", "não quero cor forte") vira tórax atlético. Ex.: com 1,80 m e 85 kg, "não tenho barriga" dá Terno 54 / Calça 50 / Camisa GG e "calor forte" dá Terno 52 Slim / Calça 44, em vez de 52 Regular / 46 / G. Checar a negação por termo, tirar o "barriga" genérico do largo e tirar o "forte" (e o "academia" isolado) do atlético: aceitar só frases corporais inequívocas ("sou atlético", "faço academia", "peito forte") e tratar "sou forte" e "fortinho" como ambíguos, nunca como atlético — `app/agent/intake.py:145`, `app/tools/vocabulary.py:257` e `:277` — owner: _livre_
- [ ] **P0** · Hardening de abuso e custo da API pública — owner: _livre_
  - Deploy atrás de proxy: definir `FORWARDED_ALLOW_IPS` só com o IP ou a faixa do proxy, nunca `*`.
  - Limites de entrada e de saída: fazer o limite de corpo (413) contar os bytes de fato recebidos, pôr `max_length` nas listas de `Product` e de `StylistPreferences` e responder ao 422 sem ecoar o `input`.
  - Rate limit e orçamento de LLM: agrupar endereços IPv6 por prefixo na chave do cliente, dar ao limitador um teto rígido de chaves (ex.: LRU) e contar o orçamento de LLM por tokens e por cliente.
  - [Ambos] Custo de CPU do intake: na extração de cores, olhar só um trecho curto antes de cada cor e limitar o histórico que o intake junta, com teste de desempenho.
  - [Ambos] Custo de CPU do planner: limitar as combinações avaliadas por requisição, com teste de desempenho.
- [ ] **P0** · Guarda-corpos de saída do modo LLM, antes de ligá-lo em produção (amplia o P1 "Reconciliar o texto final do LLM") — owner: _livre_
  - Fixar `target_formality`, `time_of_day` e tamanho a partir do contexto, ignorando os valores que o LLM passa ao `compose_complete_look` (hoje um look "business, dia" passa como válido num pedido black tie).
  - O tamanho do LLM vence o do cliente (`app/agent/graph.py:279`): usar `planner.size_for(profile, category) or search.size`. Validar o estoque no `compose` (look inválido, com violação) em vez de descartar no fim sem fallback: hoje a resposta sai sem looks e com modo "llm".
  - [Ambos] Sem passaporte (ou sem `shoe_size`), o `attach_sizes` não confere `in_stock` (`app/tools/harmony.py:272`): um look do LLM com peça esgotada em todos os tamanhos passa sem aviso, e o `POST /api/v1/looks/compose` também não confere o estoque (sem `measurements`, nem chama o `attach_sizes`). No modo por regras o planner já filtra.
  - Gerar ou conferir o `reply` a partir dos looks finais, com limite de tamanho: num teste com LLM roteirizado, um texto com "R$ 1.990 com 20% de desconto e frete grátis" saiu como `reply` sem nenhuma conferência com o look devolvido (R$ 4.437).
  - Injeção de prompt: tratar como dados não confiáveis tudo o que vem do cliente (catálogo, histórico e mensagem), não aceitar turnos `assistant` do cliente como falas do modelo e cobrir com evals adversariais.
  - Ao cair para `rule_based` no meio do laço, limpar o estado do LLM (`inventory` e looks parciais): já saiu um look "Executivo" numa resposta black tie.
- [ ] **P1** · [Ambos] NLU do intake (amplia o P1 "NLU: reconhecer 1m80") — owner: _livre_
  - Negação: "não é black tie" força black tie; "nada formal, é um almoço" vira formal; o `NEGATION_BEFORE` olha só até 2 palavras antes da cor ("não gosto de terno preto" vira preferência por preto).
  - Horário, ocasião e papel: "Boa noite!" vence "às 11h da manhã"; "em 2 horas" vira noite; "19:30" não é lido; "padrinho de batizado" e "padrinho de formatura" viram casamento; "padrinho do noivo" e "o noivo é meu primo" tratam o cliente como o noivo.
  - Números: o peso pega o primeiro número ("pesava 100, hoje 85") e ignora "peso 85", "85kgs" e "85,5 kg"; "dia 2.10" vira 2,10 m; "sapato tamanho 42" não extrai o calçado; "terno número 46" vira sapato 46 (0 looks); "até 200 convidados" e "peso até 105 kg" viram orçamento, e "3,5 mil" não é lido.
  - Cores e histórico: "camisa branca ou azul" põe a 2ª cor no terno; no histórico, o turno mais antigo vence o mais recente.
- [ ] **P1** · [Ambos] Decisão de contrato: com `measurements` no request, as medidas digitadas na mensagem ("agora estou com 90 kg") são ignoradas sem aviso, porque o `resolve_measurements` dá precedência às explícitas por desenho. Definir qual vence (o passaporte ou a mensagem atual) ou ao menos devolver um aviso, e espelhar no porte — owner: _livre_
- [ ] **P1** · [Ambos] Planner devolve 0 ou 1 look com estoque disponível — owner: _livre_
  - Com sapato 44, "Casamento à tarde, quero terno bege" volta com 0 looks e "Sou padrinho de casamento à tarde" com 1 (com sapato 41 vêm 3): o relaxamento só ocorre com a busca totalmente vazia, e o pool fica preso aos ternos preferidos.
  - Só as 20 primeiras peças de cada categoria entram, na ordem do catálogo: num catálogo de 400 itens o terno bege pedido nem é avaliado. Ranquear antes de truncar.
- [ ] **P1** · [Ambos] Busca e cores — owner: _livre_
  - `color_query` não reconhecido é ignorado: "gravata vermelha" devolve as 5 gravatas, e `GET /catalog?color=vermelho` devolve os 21 itens.
  - Plurais falham (`COLOR_SYNONYMS`, `_stem`): "sapatos marrons" põe o preto em 1º, e "sem sapatos pretos" não evita o preto.
  - "azul" resolve só para navy e faltam as formas femininas: "camisa azul", "camisa azul clara" e "camisa off white" voltam vazias.
  - "gravata borboleta" devolve gravatas comuns; itens fora do catálogo (cinto, meia, abotoadura, lenço, colete) são ignorados, e a cor devolve peças de outra categoria.
  - Em busca com duas peças, a cor da peça de referência filtra a buscada ("gravata para terno cinza" volta vazio).
  - Tamanho comparado como texto exato: "u", "M" ou "G" para camisa e "41.0" voltam vazios. Normalizar.
- [ ] **P1** · [Ambos] Regras de harmonia (`harmony_rules.json`, `app/tools/harmony.py`) — owner: _livre_
  - O black tie exige `style == "oxford"` exato: "Oxford Verniz" e "oxford cap-toe" invalidam o look de gala.
  - Pares de cor fora da tabela valem "acceptable" em silêncio: camisa preta com terno marinho (84 pts), sapato branco à noite (92 pts), terno marrom com sapato preto.
  - O black tie aceita gravata comum e nunca orienta para a gravata-borboleta.
  - Em `BLACK_TIE`, o `evaluate_combination` pula a checagem de distância de formalidade (`app/tools/harmony.py:170`): uma gravata smart casual passa com 92 pts.
- [ ] **P1** · Testes que protejam as garantias centrais — owner: _livre_
  - Mutação: desligar o filtro "só peças com estoque no tamanho do cliente" ou afrouxar a checagem de formalidade mantém os 103 testes verdes.
  - Caminho LLM: o fake devolve sempre a mesma mensagem e mascara bugs de várias rodadas; faltam black tie com override, falha no meio do laço, limite de rodadas e texto não ancorado.
  - `LLM_MAX_TOOL_ROUNDS` ≥ 16 estoura o limite de recursão do grafo e vira HTTP 500 em vez de fallback: limitar a configuração.
  - Contrato: mudanças incompatíveis passam sem bump de `API_VERSION` ou `ruleset_version` (o SDD §8.4 não é verificado). `oasdiff` no CI e um lock com os hashes das versões.
  - [Ambos] Os vetores de paridade não pegam mudanças plausíveis no NLU e no planner (hoje são 0 divergências em 10.400 casos): gerar vetores a partir dos léxicos (negação, plural, números de borda) e de um corpus com seed fixa.
- [ ] **P1** · Latência e custo do LLM (complementa o P2 "Observabilidade de LLM") — owner: _livre_
  - Prazo total por requisição no modo LLM, configurável e com padrão abaixo do timeout do cliente (hoje 12 s no storefront): guardar o prazo no estado, limitar o `timeout` de cada chamada ao tempo restante, usar `max_retries=0` e cair para o fallback `llm_deadline` ao estourar.
  - Concorrência: todas as rotas de `app/main.py` são `def` síncronas e dividem o mesmo threadpool, inclusive o `/health`. Servir o `/health` fora desse pool e sem I/O bloqueante no event loop, e limitar a concorrência do stylist, com teste de carga.
  - Modelo padrão Opus para um tool calling estreito, prompt reenviado inteiro a cada rodada e sem prompt caching. Rodar antes as buscas determinísticas e deixar o LLM só com o compose e o texto.
  - Limite explícito de tokens de saída em todos os provedores de LLM.
  - Depois do limite de rodadas, o `_llm_turn` (`app/agent/graph.py`) ainda chama o modelo com as tools oferecidas e só então descarta as tool calls: nessa última chamada, pedir só o texto final, sem permitir tool calls, e pulá-la quando não houver look válido (direto para o fallback `llm_tool_round_limit`).
- [ ] **P2** · Grade de tamanhos satura em silêncio: 165 cm com 150 kg recebe "Terno 60" sem aviso de sob medida (com tórax e abdômen médios, 2.864 combinações fora da faixa e nenhuma com aviso); com abdômen largo e a calça cortada (ex.: 175 cm e 160 kg), a frase "aplica Drop 4: calça 54 para o paletó 60" contradiz o `drop` 6 da resposta. Campo opcional de "fora da grade" e sugestão de sob medida — owner: _livre_
- [ ] **P2** · [Ambos] O ranking ignora `seasons` ("terno para o verão" põe o de linho em 3º) e vaza palavras soltas das frases de ocasião; palavras de cor em outro sentido viram filtro ("bodas de prata", "café da manhã", "black friday") — owner: _livre_
- [ ] **P2** · Operação — owner: _livre_
  - `CORS_ALLOW_ORIGINS` com barra final ou caminho bloqueia todo o tráfego do browser, e o storefront cai para o motor local sem ninguém perceber: normalizar e validar no boot.
  - Com `ENVIRONMENT=production`, desligar `/docs`, `/redoc` e `/openapi.json` e devolver `null` no provedor e no modelo, tanto no `/health` quanto no `engine` das respostas do stylist (o contrato já aceita `null`).
  - Dependabot ou Renovate e `pip-audit` no CI, imagem base fixada por digest e código da aplicação somente leitura para o usuário do runtime no contêiner.
  - `SqliteCatalogRepository`: cachear o catálogo validado, com invalidação, e falhar no boot se o arquivo do banco não existir.
- [ ] **P2** · [Ambos] Sem medidas e sem looks, o `compose_reply` junta duas frases contraditórias (idem quando há estoque mas a harmonia falha) — owner: _livre_
- [ ] **P2** · O `calculate_tailoring_size` lança `ValueError` cru para `chest_type` ou `belly_type` inválidos, em vez de um erro de validação — owner: _livre_
- [ ] **P2** · Expor `ruleset_version`, `algorithm_version` e o hash dos vetores no `/health`, para o storefront comparar em runtime com o fallback empacotado — owner: _livre_
- [ ] **P2** · [Ambos] Divergências residuais de paridade: remover só os diacríticos latinos (U+0300–U+036F), e não toda a categoria Mn (o Python 3.11 usa Unicode 14 e o Node usa 16), e limitar os dígitos do orçamento (acima de 15 dígitos diverge) — owner: _livre_
- [ ] **P2** · SDD §8.2: o exemplo de "resposta real" não sai do request de exemplo, e o §10 exagera a cobertura dos fallbacks. Gerar os exemplos por script — owner: _livre_

## Log

| Data | Agente | Resumo |
|---|---|---|
| 2026-11-05 | Claude Code | Bootstrap completo: contratos, tools, grafo LangGraph, API, Docker, testes, SDD e vetores de paridade. |
| 2026-11-05 | Claude Code | Validação cruzada com o storefront: 51 testes de paridade TS e 7 testes de contrato ao vivo verdes. |
| 2026-11-05 | Claude Code | Hardening pós-análise: rate limiting, 413, CORS restrito, orçamento de LLM, CI 3.11–3.13 + Docker; backlog priorizado registrado. |
| 2026-11-07 | Claude Code | Revisão verificada (115 pontos, com Gemini e OpenCode): tarefas novas no backlog, de P0 a P2, e notas nos itens existentes. |
