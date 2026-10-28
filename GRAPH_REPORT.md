# 🕸️ GRAPH_REPORT.md — Antigravity Brain Multi-Modal Knowledge Graph

> **Gerado automaticamente por `graphify_engine.py`** (Zero-LLM Deterministic AST + SQL + HTTP + MCP Graph)

## 1. Telemetria Executiva & Eficiência de Tokens
- **Total de Nós Multi-Modais**: `323` (`FILE`: 14, `CLASS`: 5, `FUNCTION`: 114, `JS_FUNCTION`: 129, `API_ROUTE`: 32, `MCP_TOOL`: 16, `SQL_TABLE`: 13)
- **Total de Arestas Tipadas**: `958`
  - 🟢 **EXTRACTED (1.00)**: `684` arestas (AST / DDL / Rota literal 100% determinística)
  - 🔵 **INFERRED (0.85)**: `240` arestas (Resolução cruzada de métodos e handlers)
  - 🟡 **AMBIGUOUS (0.55)**: `34` arestas (Despacho polimórfico / múltiplos candidatos)
- **Compressão de Contexto (Graphify Token Diet)**: `188,103` tokens brutos ➔ `360` tokens de índice (**`522.5x` menos tokens**)

## 2. Top God Nodes (Centros de Gravidade Arquitetónica)
| # | Entidade | Tipo | Ficheiro | Grau (In/Out) | Alcance Ficheiros | Score Centralidade | Comunidade |
|---|---|---|---|---|---|---|---|
| 1 | **`SwarmEngine`** | `CLASS` | `swarm_engine.py:L53` | 73 (36↙ / 37↗) | 8 files | **172.53** | Asymmetric Swarm & CoW Sandbox |
| 2 | **`BrainDB`** | `CLASS` | `db_engine.py:L65` | 60 (34↙ / 26↗) | 10 files | **156.6** | Core Memory & SQLite FTS5 Engine |
| 3 | **`BrainDashboardHandler.do_POST`** | `FUNCTION` | `web_dashboard.py:L709` | 54 (21↙ / 33↗) | 8 files | **101.2** | HTTP Gateway, MCP Server & Token Diet |
| 4 | **`BrainDB._connect`** | `FUNCTION` | `db_engine.py:L76` | 52 (52↙ / 0↗) | 7 files | **95.2** | Core Memory & SQLite FTS5 Engine |
| 5 | **`BrainDashboardHandler.do_GET`** | `FUNCTION` | `web_dashboard.py:L532` | 39 (16↙ / 23↗) | 8 files | **80.2** | HTTP Gateway, MCP Server & Token Diet |
| 6 | **`run_all_tests`** | `FUNCTION` | `test_brain.py:L10` | 28 (1↙ / 27↗) | 9 files | **68.0** | HTTP Gateway, MCP Server & Token Diet |
| 7 | **`memories`** | `SQL_TABLE` | `db_engine.py:L96` | 16 (16↙ / 0↗) | 5 files | **51.84** | Core Memory & SQLite FTS5 Engine |
| 8 | **`main`** | `FUNCTION` | `ast_impact_watcher.py:L527` | 21 (5↙ / 16↗) | 7 files | **51.8** | AST Inspector, Graphify & Save Watcher |
| 9 | **`handle_pre_invocation`** | `FUNCTION` | `brain_inject.py:L310` | 24 (4↙ / 20↗) | 5 files | **49.6** | Core Memory & SQLite FTS5 Engine |
| 10 | **`BrainDB.search_memories`** | `FUNCTION` | `db_engine.py:L671` | 18 (8↙ / 10↗) | 7 files | **47.6** | Core Memory & SQLite FTS5 Engine |

## 3. Comunidades Topológicas Detetadas
- **Core Memory & SQLite FTS5 Engine** (`49` nós) — Exemplos: `memories`, `memory_edges`, `brain_branches`, `memories_fts`, `checkpoints`, `injected_turns`
- **Asymmetric Swarm & CoW Sandbox** (`46` nós) — Exemplos: `swarm_runs`, `swarm_tasks`, `swarm_logs`, `swarm_sandboxes`, `swarm_scout`, `swarm_start`
- **AST Inspector, Graphify & Save Watcher** (`35` nós) — Exemplos: `ast_save_audits`, `AstImpactWatcher`, `AstImpactWatcher.__init__`, `AstImpactWatcher._init_watcher_schema`, `AstImpactWatcher.extract_symbol_hashes`, `AstImpactWatcher.check_syntax_and_secrets`
- **HTTP Gateway, MCP Server & Token Diet** (`50` nós) — Exemplos: `_run_git`, `get_git_status`, `check_and_apply_update`, `_schedule_server_hot_reload`, `start_auto_update_daemon`, `configure_hooks_and_plugin`
- **Obsidian 2D Graph & 3D Agent Office UI** (`143` nós) — Exemplos: `office_agents`, `SwarmEngine._ensure_core_office_agents`, `SwarmEngine._sync_live_conversations_to_office`, `SwarmEngine.get_office_state`, `SwarmEngine.assign_office_agent_directive`, `SwarmEngine.spawn_custom_office_agent`

## 4. Cadeias Causais Full-Stack Verificadas (BFS Shortest Paths)
- **triggerAstSaveAuditUI ➔ ast_save_audits** (3 saltos, poupança `1022.3x`):  
  `triggerAstSaveAuditUI` (JS_FUNCTION) ➔ `/api/ast/watch` (API_ROUTE) ➔ `AstImpactWatcher.get_watcher_status` (FUNCTION) ➔ `ast_save_audits` (SQL_TABLE)
- **swarm_watch_audit ➔ BrainDB** (2 saltos, poupança `1425.0x`):  
  `swarm_watch_audit` (MCP_TOOL) ➔ `server.py` (FILE) ➔ `BrainDB` (CLASS)
- **createAndVerifySandboxUI ➔ swarm_sandboxes** (3 saltos, poupança `1022.3x`):  
  `createAndVerifySandboxUI` (JS_FUNCTION) ➔ `/api/swarm/sandbox` (API_ROUTE) ➔ `SwarmEngine.manage_subagent_sandbox` (FUNCTION) ➔ `swarm_sandboxes` (SQL_TABLE)
