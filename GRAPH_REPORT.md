# 🕸️ GRAPH_REPORT.md — Antigravity Brain Multi-Modal Knowledge Graph

> **Gerado automaticamente por `graphify_engine.py`** (Zero-LLM Deterministic AST + SQL + HTTP + MCP Graph)

## 1. Telemetria Executiva & Eficiência de Tokens
- **Total de Nós Multi-Modais**: `411` (`FILE`: 15, `CLASS`: 8, `FUNCTION`: 140, `JS_FUNCTION`: 177, `API_ROUTE`: 36, `MCP_TOOL`: 18, `SQL_TABLE`: 17)
- **Total de Arestas Tipadas**: `1219`
  - 🟢 **EXTRACTED (1.00)**: `856` arestas (AST / DDL / Rota literal 100% determinística)
  - 🔵 **INFERRED (0.85)**: `323` arestas (Resolução cruzada de métodos e handlers)
  - 🟡 **AMBIGUOUS (0.55)**: `40` arestas (Despacho polimórfico / múltiplos candidatos)
- **Compressão de Contexto (Graphify Token Diet)**: `250,265` tokens brutos ➔ `360` tokens de índice (**`695.2x` menos tokens**)

## 2. Top God Nodes (Centros de Gravidade Arquitetónica)
| # | Entidade | Tipo | Ficheiro | Grau (In/Out) | Alcance Ficheiros | Score Centralidade | Comunidade |
|---|---|---|---|---|---|---|---|
| 1 | **`SwarmEngine`** | `CLASS` | `swarm_engine.py:L53` | 73 (36↙ / 37↗) | 8 files | **172.53** | Asymmetric Swarm & CoW Sandbox |
| 2 | **`BrainDB`** | `CLASS` | `db_engine.py:L65` | 65 (37↙ / 28↗) | 11 files | **170.37** | Core Memory & SQLite FTS5 Engine |
| 3 | **`BrainDashboardHandler.do_POST`** | `FUNCTION` | `web_dashboard.py:L865` | 64 (22↙ / 42↗) | 9 files | **118.4** | HTTP Gateway, MCP Server & Token Diet |
| 4 | **`BrainDB._connect`** | `FUNCTION` | `db_engine.py:L76` | 65 (65↙ / 0↗) | 8 files | **116.6** | Core Memory & SQLite FTS5 Engine |
| 5 | **`run_all_tests`** | `FUNCTION` | `test_brain.py:L10` | 46 (1↙ / 45↗) | 10 files | **96.4** | HTTP Gateway, MCP Server & Token Diet |
| 6 | **`BrainDashboardHandler.do_GET`** | `FUNCTION` | `web_dashboard.py:L667` | 43 (17↙ / 26↗) | 9 files | **89.0** | HTTP Gateway, MCP Server & Token Diet |
| 7 | **`OrbitEngine`** | `CLASS` | `orbit_engine.py:L14` | 28 (14↙ / 14↗) | 6 files | **78.84** | HTTP Gateway, MCP Server & Token Diet |
| 8 | **`memories`** | `SQL_TABLE` | `db_engine.py:L96` | 18 (18↙ / 0↗) | 6 files | **59.94** | Core Memory & SQLite FTS5 Engine |
| 9 | **`store_fact`** | `MCP_TOOL` | `server.py:L320` | 13 (11↙ / 2↗) | 8 files | **59.13** | HTTP Gateway, MCP Server & Token Diet |
| 10 | **`BrainDB.store_fact`** | `FUNCTION` | `db_engine.py:L491` | 21 (14↙ / 7↗) | 8 files | **55.0** | Core Memory & SQLite FTS5 Engine |

## 3. Comunidades Topológicas Detetadas
- **Core Memory & SQLite FTS5 Engine** (`57` nós) — Exemplos: `memories`, `memory_edges`, `brain_branches`, `memories_fts`, `checkpoints`, `injected_turns`
- **Asymmetric Swarm & CoW Sandbox** (`46` nós) — Exemplos: `swarm_runs`, `swarm_tasks`, `swarm_logs`, `swarm_sandboxes`, `swarm_scout`, `swarm_start`
- **AST Inspector, Graphify & Save Watcher** (`38` nós) — Exemplos: `ast_save_audits`, `orbit_broadcasts`, `AstImpactWatcher`, `AstImpactWatcher.__init__`, `AstImpactWatcher._init_watcher_schema`, `AstImpactWatcher.extract_symbol_hashes`
- **HTTP Gateway, MCP Server & Token Diet** (`79` nós) — Exemplos: `_run_git`, `get_git_status`, `check_and_apply_update`, `_schedule_server_hot_reload`, `start_auto_update_daemon`, `configure_hooks_and_plugin`
- **Obsidian 2D Graph & 3D Agent Office UI** (`191` nós) — Exemplos: `office_agents`, `SwarmEngine._ensure_core_office_agents`, `SwarmEngine._sync_live_conversations_to_office`, `SwarmEngine.get_office_state`, `SwarmEngine.assign_office_agent_directive`, `SwarmEngine.spawn_custom_office_agent`

## 4. Cadeias Causais Full-Stack Verificadas (BFS Shortest Paths)
- **triggerAstSaveAuditUI ➔ ast_save_audits** (3 saltos, poupança `1360.1x`):  
  `triggerAstSaveAuditUI` (JS_FUNCTION) ➔ `/api/ast/watch` (API_ROUTE) ➔ `AstImpactWatcher.get_watcher_status` (FUNCTION) ➔ `ast_save_audits` (SQL_TABLE)
- **swarm_watch_audit ➔ BrainDB** (2 saltos, poupança `1895.9x`):  
  `swarm_watch_audit` (MCP_TOOL) ➔ `server.py` (FILE) ➔ `BrainDB` (CLASS)
- **createAndVerifySandboxUI ➔ swarm_sandboxes** (3 saltos, poupança `1360.1x`):  
  `createAndVerifySandboxUI` (JS_FUNCTION) ➔ `/api/swarm/sandbox` (API_ROUTE) ➔ `SwarmEngine.manage_subagent_sandbox` (FUNCTION) ➔ `swarm_sandboxes` (SQL_TABLE)
