# AGENTS.md — brain_mcp

# Antigravity Brain v8.1 — Zero-Round-Trip Memory & Voice Protocol

1. **Pre-Injected Context (`[BRAIN_MEMORY]`)**: Prior to responding, check if an ephemeral `[BRAIN_MEMORY]` block was injected. Trust its file paths, checkpoints, and environment facts so you do not waste tool calls re-discovering project structure.
2. **Zero-Token Memory Harvesting (`<!-- brain: Topic | Fact -->`)**: Whenever you solve a non-trivial bug, discover a critical IP/config/path, or make an architectural decision, append a hidden HTML comment at the very end of your response:
   `<!-- brain: Short Topic | Concise actionable fact with exact paths/values -->`
   The `Stop` hook (`brain_harvest.py`) automatically indexes these comments and any edited files into `brain.db` at zero LLM token cost.
3. **Explicit Search**: Only call the `antigravity-brain` MCP tool (`search_brain`) if you need a deep query that was not covered by the automatic `[BRAIN_MEMORY]` injection.
4. **Scout-First Asymmetric Swarm Protocol (`SCOUT ➔ PLAN ➔ SWARM ➔ VERIFY`)**:
   - **Shared Codebase Map (`[SCOUT_SHARED_MAP]`)**: Before launching multi-file work, run `SwarmEngine.run_codebase_scout()` (or `swarm_scout` / `swarm_start`) so the codebase is indexed **1 time** and shared in `brain.db` across all agents via `PreInvocation`.
   - **Decoupled Architect & Lightweight Lanes**: Read the goal and `[SCOUT_SHARED_MAP]` once as the Architect, decompose into isolated lanes (`UI`, `API`, `TESTS`, `DOCS`), and delegate parallel execution via `invoke_subagent` with `Model="flash"` or `"flash_lite"`, passing the exact target file and symbols so workers never re-read the codebase.
5. **Voice-Aware Zero-Call Protocol (`[VOICE_PRE_EXEC]` & `[VOICE_AST_TARGET]`)**:
   - **Spoken AST Resolution (`[VOICE_AST_TARGET]`)**: When the user speaks or query contains voice transcription markers, consult injected `[VOICE_AST_TARGET]` pointers (`:Lstart-end`) to edit or inspect code immediately without exploratory symbol lookups.
   - **Zero-Call Pre-Execution (`[VOICE_PRE_EXEC]`)**: When voice commands request memory storage, status queries, or symbol lookups, trust the pre-executed results injected under `[VOICE_PRE_EXEC]` instead of making redundant tool calls, saving up to 68% tokens.

<!-- BRAIN_AUTO_RULES_START -->
## 🧠 Antigravity Global Brain — Auto-Synced Rules (`brain_mcp`)
> Atualizado automaticamente pelo Universal Repo Rules Sync (v6.1).

### 🧬 Regras Destiladas (Self-Learn Playbook)
- [extrator_universal.py] Confirmed Aion 2 (PID 3540/14376) and Speeder Notepad host (PID 10212) active; fixed early-e...
- [relatorio_auditoria_shadow_meter_v2.md] Consolidated all 3 subagent audits for v2.0.127 (dfda128) into relatorio_auditoria_shadow_me...
- [conf.json] Found 14 issues across main.rs, win32/window.rs, updater/mod.rs, account/secret.rs, share/mo...
- [explicit_note] Mapped Zep/Graphiti bi-temporal invalidation, HippoRAG 2 PPR, Ebbinghaus spaced decay, 128-b...
- [db_engine.py] Implemented PRAGMA user_version=72 gate, 128-bit BQ + POPCNT Hamming, HippoRAG 2 PPR + 4-Way...

### 🌐 Top Regras & Factos Críticos
- **🧬 Meta-Regra Aprendida [brain_app.py]**: Padrão consolidado (2 memórias em brain_mcp): Removed brain_app.py/BrainApp.bat/HKCU Run registry key, upgraded ReusableThreadingHTTPServe... | Added brain_app.
- **🧬 Meta-Regra Aprendida [explicit_note]**: Padrão consolidado (28 memórias em brain_mcp): Removed all references to Easy-WI and .php filenames across all 19 files in c:/Users/guels/D... | Created isolate
- **🧬 Meta-Regra Aprendida [conf.json]**: Padrão consolidado (2 memórias em brain_mcp): Found 14 issues across main.rs, win32/window.rs, updater/mod.rs, account/secret.rs, share/mo... | CSP is null in s
- **🧬 Meta-Regra Aprendida [brain_inject.py]**: Padrão consolidado (2 memórias em brain_mcp): Smart Active-Repo Resolver (brain_inject.py:L622), Zero-Leak Secret Redactor (db_engine.py:L... | Implemented fore
- **🧬 Meta-Regra Aprendida [db_engine.py]**: Padrão consolidado (2 memórias em brain_mcp): Upgraded db_engine.py to 128-D Subword LSH + RRF (k=60), Unicode-safe accent tokenizer, Cros... | Remediated 91 bo
<!-- BRAIN_AUTO_RULES_END -->
