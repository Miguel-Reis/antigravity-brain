# 🕸️ GRAPH_REPORT.md — Antigravity Brain Multi-Modal Knowledge Graph

> **Gerado automaticamente por `graphify_engine.py`** (Zero-LLM Deterministic AST + SQL + HTTP + MCP Graph)

## 1. Telemetria Executiva & Eficiência de Tokens
- **Total de Nós Multi-Modais**: `454` (`FILE`: 15, `CLASS`: 8, `FUNCTION`: 155, `JS_FUNCTION`: 198, `API_ROUTE`: 38, `MCP_TOOL`: 18, `SQL_TABLE`: 22)
- **Total de Arestas Tipadas**: `1369`
  - 🟢 **EXTRACTED (1.00)**: `949` arestas (AST / DDL / Rota literal 100% determinística)
  - 🔵 **INFERRED (0.85)**: `378` arestas (Resolução cruzada de métodos e handlers)
  - 🟡 **AMBIGUOUS (0.55)**: `42` arestas (Despacho polimórfico / múltiplos candidatos)
- **Compressão de Contexto (Graphify Token Diet)**: `287,484` tokens brutos ➔ `360` tokens de índice (**`798.6x` menos tokens**)

## 2. Top God Nodes (Centros de Gravidade Arquitetónica)
| # | Entidade | Tipo | Ficheiro | Grau (In/Out) | Alcance Ficheiros | Score Centralidade | Comunidade |
|---|---|---|---|---|---|---|---|
| 1 | **`BrainDB`** | `CLASS` | `db_engine.py:L75` | 71 (39↙ / 32↗) | 11 files | **181.71** | Core Memory & SQLite FTS5 Engine |
| 2 | **`SwarmEngine`** | `CLASS` | `swarm_engine.py:L54` | 73 (36↙ / 37↗) | 8 files | **172.53** | Asymmetric Swarm & CoW Sandbox |
| 3 | **`BrainDashboardHandler.do_POST`** | `FUNCTION` | `web_dashboard.py:L911` | 73 (23↙ / 50↗) | 9 files | **131.0** | HTTP Gateway, MCP Server & Token Diet |
| 4 | **`BrainDB._connect`** | `FUNCTION` | `db_engine.py:L88` | 74 (74↙ / 0↗) | 8 files | **129.2** | Core Memory & SQLite FTS5 Engine |
| 5 | **`run_all_tests`** | `FUNCTION` | `test_brain.py:L10` | 61 (1↙ / 60↗) | 10 files | **117.4** | HTTP Gateway, MCP Server & Token Diet |
| 6 | **`OrbitEngine`** | `CLASS` | `orbit_engine.py:L17` | 36 (15↙ / 21↗) | 6 files | **93.96** | HTTP Gateway, MCP Server & Token Diet |
| 7 | **`BrainDashboardHandler.do_GET`** | `FUNCTION` | `web_dashboard.py:L690` | 46 (18↙ / 28↗) | 9 files | **93.2** | HTTP Gateway, MCP Server & Token Diet |
| 8 | **`memories`** | `SQL_TABLE` | `db_engine.py:L111` | 21 (21↙ / 0↗) | 6 files | **65.61** | Core Memory & SQLite FTS5 Engine |
| 9 | **`/api/orbit/action`** | `API_ROUTE` | `web_dashboard.py:L11628` | 26 (11↙ / 15↗) | 3 files | **62.1** | HTTP Gateway, MCP Server & Token Diet |
| 10 | **`store_fact`** | `MCP_TOOL` | `server.py:L318` | 14 (12↙ / 2↗) | 8 files | **61.02** | HTTP Gateway, MCP Server & Token Diet |

## 3. Comunidades Topológicas Detetadas
- **Core Memory & SQLite FTS5 Engine** (`66` nós) — Exemplos: `memories`, `memory_edges`, `brain_branches`, `memory_revisions`, `memories_fts`, `checkpoints`
- **Asymmetric Swarm & CoW Sandbox** (`46` nós) — Exemplos: `swarm_runs`, `swarm_tasks`, `swarm_logs`, `swarm_sandboxes`, `swarm_scout`, `swarm_start`
- **AST Inspector, Graphify & Save Watcher** (`39` nós) — Exemplos: `ast_save_audits`, `orbit_broadcasts`, `AstImpactWatcher`, `AstImpactWatcher.__init__`, `AstImpactWatcher._init_watcher_schema`, `AstImpactWatcher.extract_symbol_hashes`
- **HTTP Gateway, MCP Server & Token Diet** (`91` nós) — Exemplos: `_run_git`, `get_git_status`, `check_and_apply_update`, `_schedule_server_hot_reload`, `start_auto_update_daemon`, `configure_hooks_and_plugin`
- **Obsidian 2D Graph & 3D Agent Office UI** (`212` nós) — Exemplos: `office_agents`, `SwarmEngine._ensure_core_office_agents`, `SwarmEngine._sync_live_conversations_to_office`, `SwarmEngine.get_office_state`, `SwarmEngine.assign_office_agent_directive`, `SwarmEngine.spawn_custom_office_agent`

## 4. Cadeias Causais Full-Stack Verificadas (BFS Shortest Paths)
- **triggerAstSaveAuditUI ➔ ast_save_audits** (3 saltos, poupança `1562.4x`):  
  `triggerAstSaveAuditUI` (JS_FUNCTION) ➔ `/api/ast/watch` (API_ROUTE) ➔ `AstImpactWatcher.get_watcher_status` (FUNCTION) ➔ `ast_save_audits` (SQL_TABLE)
- **swarm_watch_audit ➔ BrainDB** (2 saltos, poupança `2177.9x`):  
  `swarm_watch_audit` (MCP_TOOL) ➔ `server.py` (FILE) ➔ `BrainDB` (CLASS)
- **createAndVerifySandboxUI ➔ swarm_sandboxes** (3 saltos, poupança `1562.4x`):  
  `createAndVerifySandboxUI` (JS_FUNCTION) ➔ `/api/swarm/sandbox` (API_ROUTE) ➔ `SwarmEngine.manage_subagent_sandbox` (FUNCTION) ➔ `swarm_sandboxes` (SQL_TABLE)
