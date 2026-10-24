# ⚡ Antigravity Brain v4.0 — Tech Revolution

Local persistent memory engine (**SQLite WAL + FTS5 BM25**), **JEV-Mem System-1 cognitive router (`<0.05ms`)**, **Ruflo causal graph**, and **Tech Revolution HUD** (`http://127.0.0.1:8765`) for **Antigravity**.

---

## 🧠 How It Works (100% Automatic on Every Chat Message)

| Stage | Hook / Script | What Runs Automatically |
| :--- | :--- | :--- |
| **Before Response** | `PreInvocation` ➔ [`brain_inject.py`](./brain_inject.py) | • **JEV-S1 Router**: classifies intent in `<0.05ms` and weights the 3 memory tiers (`[W] Working`, `[S] Semantic`, `[E] Episodic`).<br>• **Adaptive Stopping**: injects only high-gain memories + causal edges (`fixed_by`, `evolves`, `supersedes`).<br>• **Scout Shared Map**: injects the AST symbol map (`[SCOUT_SHARED_MAP]`) to eliminate redundant codebase reads. |
| **During Execution** | `Tool Loop` ➔ [`swarm_engine.py`](./swarm_engine.py) | • Syncs live tool calls (`edit_file`, `run_command`, subagents) with the **Swarm Matrix** and moves active agents to their workstations in the **3D Office**. |
| **After Response** | `Stop` ➔ [`brain_harvest.py`](./brain_harvest.py) | • Harvests `<!-- brain: Topic \| Fact -->` notes and edited files at **zero LLM token cost**.<br>• **AI-Defence**: redacts secrets/tokens (`AIza...`, `ghp_...`, `sk-...`) before SQLite storage.<br>• **Memory Doctor**: merges duplicates, builds causal links, and updates the workspace checkpoint. |

---

## 🖥️ Dashboard Views (`http://127.0.0.1:8765`)

1. **`01 // NEURAL CORTEX` (`/#graph`)**
   - Quantum sonar memory graph with double-ring holographic nodes by tier (`[HUB]`, `[W]`, `[S]`, `[E]`, `[CP]`) and directed causal edges.
   - Side blades for **JEV-S1 Neural Router**, **5h Quota Reactor**, **Causal Lineage Inspector**, and live `[BRAIN_MEMORY]` stream.
2. **`02 // SWARM MATRIX` (`/#swarm`)**
   - **Scout-First Asymmetric Swarm** pipeline (`STAGE 01 SCOUT` ➔ `STAGE 02 ARCHITECT` ➔ `STAGE 03 24 WORKERS` ➔ `STAGE 04 48/48 VERIFY`).
   - 4 parallel lanes (`UI`, `API`, `TESTS`, `DOCS`) with **Ruflo Pheromone EMA** fitness and automatic Work-Stealing.
3. **`03 // HOLOGRAPHIC 3D` (`/#office`)**
   - 60 FPS isometric 3D office with 6 dedicated zones (Quantum Portal, MCP Server Room, Argon Command Bridge, Swarm Engineering Wing, Subagents Wing, and Espresso & Arcade Lounge), orbital radar minimap, and direct `[CONSOLE] NEURAL DIRECTIVE` bar.

> **Global Shortcut**: Press **`Ctrl+K`** in any view to open the **Command Palette**.

---

## 🚀 Quick Install (PowerShell)

```powershell
git clone https://github.com/Miguel-Reis/antigravity-brain.git "$HOME\.gemini\antigravity\scratch\brain_mcp"; python "$HOME\.gemini\antigravity\scratch\brain_mcp\install.py"
```

[`install.py`](./install.py) automatically configures:
- Global hooks in `~/.gemini/config/hooks.json`
- Plugin and rules in `~/.gemini/config/plugins/antigravity-brain`
- `antigravity-brain` MCP server in `~/.gemini/config/mcp_config.json`
- Background dashboard service ([`web_dashboard.py`](./web_dashboard.py)) at `http://127.0.0.1:8765`

---

## 🔄 Updating

The background service automatically checks `origin/main` for updates. To update manually:
- Click **`📦 Git`** in the top bar of `http://127.0.0.1:8765`, or run:
  ```powershell
  python "$HOME\.gemini\antigravity\scratch\brain_mcp\auto_updater.py"
  ```

