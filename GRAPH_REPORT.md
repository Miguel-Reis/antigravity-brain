# 🕸️ GRAPH_REPORT.md — Antigravity Brain Multi-Modal Knowledge Graph

> **Gerado automaticamente por `graphify_engine.py`** (Zero-LLM Deterministic AST + SQL + HTTP + MCP Graph)

## 1. Telemetria Executiva & Eficiência de Tokens
- **Total de Nós Multi-Modais**: `549` (`FILE`: 16, `CLASS`: 12, `FUNCTION`: 193, `JS_FUNCTION`: 248, `API_ROUTE`: 40, `MCP_TOOL`: 18, `SQL_TABLE`: 22)
- **Total de Arestas Tipadas**: `1684`
  - 🟢 **EXTRACTED (1.00)**: `1155` arestas (AST / DDL / Rota literal 100% determinística)
  - 🔵 **INFERRED (0.85)**: `473` arestas (Resolução cruzada de métodos e handlers)
  - 🟡 **AMBIGUOUS (0.55)**: `56` arestas (Despacho polimórfico / múltiplos candidatos)
- **Compressão de Contexto (Graphify Token Diet)**: `370,168` tokens brutos ➔ `360` tokens de índice (**`1028.2x` menos tokens**)

## 2. Top God Nodes (Centros de Gravidade Arquitetónica)
| # | Entidade | Tipo | Ficheiro | Grau (In/Out) | Alcance Ficheiros | Score Centralidade | Comunidade |
|---|---|---|---|---|---|---|---|
| 1 | **`BrainDB`** | `CLASS` | `db_engine.py:L80` | 74 (42↙ / 32↗) | 12 files | **191.7** | Core Memory & SQLite FTS5 Engine |
| 2 | **`SwarmEngine`** | `CLASS` | `swarm_engine.py:L54` | 74 (36↙ / 38↗) | 8 files | **174.42** | Asymmetric Swarm & CoW Sandbox |
| 3 | **`BrainDashboardHandler.do_POST`** | `FUNCTION` | `web_dashboard.py:L986` | 88 (24↙ / 64↗) | 10 files | **155.2** | HTTP Gateway, MCP Server & Token Diet |
| 4 | **`run_all_tests`** | `FUNCTION` | `test_brain.py:L10` | 80 (1↙ / 79↗) | 11 files | **147.2** | HTTP Gateway, MCP Server & Token Diet |
| 5 | **`BrainDB._connect`** | `FUNCTION` | `db_engine.py:L101` | 84 (84↙ / 0↗) | 8 files | **143.2** | Core Memory & SQLite FTS5 Engine |
| 6 | **`OrbitEngine`** | `CLASS` | `orbit_engine.py:L17` | 54 (13↙ / 41↗) | 7 files | **132.3** | HTTP Gateway, MCP Server & Token Diet |
| 7 | **`/api/orbit/action`** | `API_ROUTE` | `web_dashboard.py:L12539` | 51 (24↙ / 27↗) | 3 files | **109.35** | HTTP Gateway, MCP Server & Token Diet |
| 8 | **`BrainDashboardHandler.do_GET`** | `FUNCTION` | `web_dashboard.py:L731` | 47 (18↙ / 29↗) | 10 files | **97.8** | HTTP Gateway, MCP Server & Token Diet |
| 9 | **`memories`** | `SQL_TABLE` | `db_engine.py:L124` | 29 (29↙ / 0↗) | 6 files | **80.73** | Core Memory & SQLite FTS5 Engine |
| 10 | **`store_fact`** | `MCP_TOOL` | `server.py:L318` | 17 (15↙ / 2↗) | 9 files | **71.01** | HTTP Gateway, MCP Server & Token Diet |

## 3. Comunidades Topológicas Detetadas
- **Core Memory & SQLite FTS5 Engine** (`67` nós) — Exemplos: `memories`, `memory_edges`, `brain_branches`, `memory_revisions`, `memories_fts`, `checkpoints`
- **Asymmetric Swarm & CoW Sandbox** (`47` nós) — Exemplos: `swarm_runs`, `swarm_tasks`, `swarm_logs`, `swarm_sandboxes`, `swarm_scout`, `swarm_start`
- **AST Inspector, Graphify & Save Watcher** (`39` nós) — Exemplos: `ast_save_audits`, `orbit_broadcasts`, `AstImpactWatcher`, `AstImpactWatcher.__init__`, `AstImpactWatcher._init_watcher_schema`, `AstImpactWatcher.extract_symbol_hashes`
- **HTTP Gateway, MCP Server & Token Diet** (`134` nós) — Exemplos: `_run_git`, `get_git_status`, `check_and_apply_update`, `kill_other_dashboard_processes`, `_schedule_server_hot_reload`, `start_auto_update_daemon`
- **Obsidian 2D Graph & 3D Agent Office UI** (`262` nós) — Exemplos: `office_agents`, `SwarmEngine._ensure_core_office_agents`, `SwarmEngine._sync_live_conversations_to_office`, `SwarmEngine.get_office_state`, `SwarmEngine.assign_office_agent_directive`, `SwarmEngine.spawn_custom_office_agent`

## 4. Cadeias Causais Full-Stack Verificadas (BFS Shortest Paths)
- **triggerAstSaveAuditUI ➔ ast_save_audits** (3 saltos, poupança `2011.8x`):  
  `triggerAstSaveAuditUI` (JS_FUNCTION) ➔ `/api/ast/watch` (API_ROUTE) ➔ `AstImpactWatcher.get_watcher_status` (FUNCTION) ➔ `ast_save_audits` (SQL_TABLE)
- **swarm_watch_audit ➔ BrainDB** (2 saltos, poupança `2804.3x`):  
  `swarm_watch_audit` (MCP_TOOL) ➔ `server.py` (FILE) ➔ `BrainDB` (CLASS)
- **createAndVerifySandboxUI ➔ swarm_sandboxes** (3 saltos, poupança `2011.8x`):  
  `createAndVerifySandboxUI` (JS_FUNCTION) ➔ `/api/swarm/sandbox` (API_ROUTE) ➔ `SwarmEngine.manage_subagent_sandbox` (FUNCTION) ➔ `swarm_sandboxes` (SQL_TABLE)
