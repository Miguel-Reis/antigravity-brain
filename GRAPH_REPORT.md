# 🕸️ GRAPH_REPORT.md — Antigravity Brain Multi-Modal Knowledge Graph

> **Gerado automaticamente por `graphify_engine.py`** (Zero-LLM Deterministic AST + SQL + HTTP + MCP Graph)

## 1. Telemetria Executiva & Eficiência de Tokens
- **Total de Nós Multi-Modais**: `562` (`FILE`: 15, `CLASS`: 8, `FUNCTION`: 202, `JS_FUNCTION`: 253, `API_ROUTE`: 40, `MCP_TOOL`: 18, `SQL_TABLE`: 25)
- **Total de Arestas Tipadas**: `1821`
  - 🟢 **EXTRACTED (1.00)**: `1183` arestas (AST / DDL / Rota literal 100% determinística)
  - 🔵 **INFERRED (0.85)**: `576` arestas (Resolução cruzada de métodos e handlers)
  - 🟡 **AMBIGUOUS (0.55)**: `62` arestas (Despacho polimórfico / múltiplos candidatos)
- **Compressão de Contexto (Graphify Token Diet)**: `387,303` tokens brutos ➔ `360` tokens de índice (**`1075.8x` menos tokens**)

## 2. Top God Nodes (Centros de Gravidade Arquitetónica)
| # | Entidade | Tipo | Ficheiro | Grau (In/Out) | Alcance Ficheiros | Score Centralidade | Comunidade |
|---|---|---|---|---|---|---|---|
| 1 | **`BrainDB`** | `CLASS` | `db_engine.py:L91` | 81 (41↙ / 40↗) | 11 files | **224.54** | Core Memory & SQLite FTS5 Engine |
| 2 | **`BrainDB._connect`** | `FUNCTION` | `db_engine.py:L162` | 88 (88↙ / 0↗) | 8 files | **210.07** | Core Memory & SQLite FTS5 Engine |
| 3 | **`SwarmEngine`** | `CLASS` | `swarm_engine.py:L54` | 75 (37↙ / 38↗) | 8 files | **201.02** | Asymmetric Swarm & CoW Sandbox |
| 4 | **`BrainDashboardHandler.do_POST`** | `FUNCTION` | `web_dashboard.py:L1018` | 89 (23↙ / 66↗) | 9 files | **175.48** | HTTP Gateway, MCP Server & Token Diet |
| 5 | **`/api/orbit/action`** | `API_ROUTE` | `web_dashboard.py:L13168` | 52 (24↙ / 28↗) | 3 files | **155.81** | HTTP Gateway, MCP Server & Token Diet |
| 6 | **`run_all_tests`** | `FUNCTION` | `test_brain.py:L10` | 85 (1↙ / 84↗) | 10 files | **152.76** | HTTP Gateway, MCP Server & Token Diet |
| 7 | **`test_suite:run_all_tests`** | `TEST_CASE` | `test_brain.py:L10` | 85 (1↙ / 84↗) | 10 files | **152.76** | HTTP Gateway, MCP Server & Token Diet |
| 8 | **`OrbitEngine`** | `CLASS` | `orbit_engine.py:L17` | 53 (11↙ / 42↗) | 6 files | **135.42** | HTTP Gateway, MCP Server & Token Diet |
| 9 | **`memories`** | `SQL_TABLE` | `db_engine.py:L215` | 31 (31↙ / 0↗) | 6 files | **111.36** | Core Memory & SQLite FTS5 Engine |
| 10 | **`BrainDashboardHandler.do_GET`** | `FUNCTION` | `web_dashboard.py:L759` | 47 (18↙ / 29↗) | 9 files | **109.16** | HTTP Gateway, MCP Server & Token Diet |

## 3. Comunidades Topológicas Detetadas
- **Core Memory & SQLite FTS5 Engine** (`78` nós) — Exemplos: `memories`, `memory_edges`, `brain_branches`, `memory_revisions`, `memories_fts`, `checkpoints`
- **Asymmetric Swarm & CoW Sandbox** (`47` nós) — Exemplos: `swarm_runs`, `swarm_tasks`, `swarm_logs`, `swarm_sandboxes`, `swarm_scout`, `swarm_start`
- **AST Inspector, Graphify & Save Watcher** (`45` nós) — Exemplos: `ast_save_audits`, `ast_file_hashes`, `ast_symbol_snapshots`, `ast_impact_alerts`, `orbit_broadcasts`, `AstImpactWatcher`
- **HTTP Gateway, MCP Server & Token Diet** (`125` nós) — Exemplos: `_run_git`, `get_git_status`, `check_and_apply_update`, `kill_other_dashboard_processes`, `_schedule_server_hot_reload`, `start_auto_update_daemon`
- **Obsidian 2D Graph & 3D Agent Office UI** (`267` nós) — Exemplos: `office_agents`, `SwarmEngine._ensure_core_office_agents`, `SwarmEngine._sync_live_conversations_to_office`, `SwarmEngine.get_office_state`, `SwarmEngine.assign_office_agent_directive`, `SwarmEngine.spawn_custom_office_agent`

## 4. Cadeias Causais Full-Stack Verificadas (BFS Shortest Paths)
- **triggerAstSaveAuditUI ➔ ast_save_audits** (3 saltos, poupança `2104.9x`):  
  `triggerAstSaveAuditUI` (JS_FUNCTION) ➔ `/api/ast/watch` (API_ROUTE) ➔ `AstImpactWatcher.get_watcher_status` (FUNCTION) ➔ `ast_save_audits` (SQL_TABLE)
- **swarm_watch_audit ➔ BrainDB** (2 saltos, poupança `2934.1x`):  
  `swarm_watch_audit` (MCP_TOOL) ➔ `server.py` (FILE) ➔ `BrainDB` (CLASS)
- **createAndVerifySandboxUI ➔ swarm_sandboxes** (3 saltos, poupança `2104.9x`):  
  `createAndVerifySandboxUI` (JS_FUNCTION) ➔ `/api/swarm/sandbox` (API_ROUTE) ➔ `SwarmEngine.manage_subagent_sandbox` (FUNCTION) ➔ `swarm_sandboxes` (SQL_TABLE)
