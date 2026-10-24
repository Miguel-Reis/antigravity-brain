# ⚡ Antigravity Brain v4.0 — Tech Revolution

Motor local de memória persistente (**SQLite WAL + FTS5 BM25**), planeamento cognitivo **JEV-Mem System-1 (`<0.05ms`)**, grafo causal **Ruflo** e interface **Tech Revolution HUD** (`http://127.0.0.1:8765`) para o **Antigravity**.

---

## 🧠 Como Funciona (100% Automático em Cada Mensagem)

| Fase | Hook / Script | O que executa automaticamente |
| :--- | :--- | :--- |
| **Antes da Resposta** | `PreInvocation` ➔ [`brain_inject.py`](./brain_inject.py) | • **JEV-S1 Router**: classifica a intenção em `<0.05ms` e pondera as 3 camadas (`[W] Working`, `[S] Semantic`, `[E] Episodic`).<br>• **Adaptive Stopping**: injeta apenas memórias com ganho marginal real + arestas causais (`fixed_by`, `evolves`, `supersedes`).<br>• **Scout Shared Map**: injeta a árvore AST (`[SCOUT_SHARED_MAP]`) para evitar leituras repetidas da codebase. |
| **Durante a Execução** | `Tool Loop` ➔ [`swarm_engine.py`](./swarm_engine.py) | • Sincroniza em tempo real as ferramentas usadas (`edit_file`, `run_command`, subagentes) com o **Swarm Matrix** e move os agentes ativos para as secretárias no **Escritório 3D**. |
| **Fim da Resposta** | `Stop` ➔ [`brain_harvest.py`](./brain_harvest.py) | • Extrai notas `<!-- brain: Tópico \| Facto -->` e ficheiros editados a **custo zero de tokens**.<br>• **AI-Defence**: filtra chaves/segredos (`AIza...`, `ghp_...`, `sk-...`) antes de gravar.<br>• **Memory Doctor**: funde duplicados, cria ligações causais e atualiza o checkpoint. |

---

## 🖥️ Vistas do Dashboard (`http://127.0.0.1:8765`)

1. **`01 // NEURAL CORTEX` (`/#graph`)**
   - Grafo de memória com anéis de sonar quântico, nós holográficos por camada (`[HUB]`, `[W]`, `[S]`, `[E]`, `[CP]`) e arestas causais direcionadas.
   - Lâminas laterais **JEV-S1 Neural Router**, **5h Quota Reactor**, **Causal Lineage Inspector** e stream ao vivo do bloco `[BRAIN_MEMORY]`.
2. **`02 // SWARM MATRIX` (`/#swarm`)**
   - Pipeline **Scout-First Asymmetric Swarm** (`STAGE 01 SCOUT` ➔ `STAGE 02 ARCHITECT` ➔ `STAGE 03 24 WORKERS` ➔ `STAGE 04 48/48 VERIFY`).
   - 4 Lanes paralelas (`UI`, `API`, `TESTS`, `DOCS`) com fitness **Ruflo Pheromone EMA** e Work-Stealing automático.
3. **`03 // HOLOGRAPHIC 3D` (`/#office`)**
   - Escritório isométrico 3D a 60 FPS com 6 zonas dedicadas (Portal Quântico, Servidores MCP, Ponte de Comando Argon, Ala Swarm, Subagentes e Lounge), minimapa radar orbital e consola de ordens diretas (`[CONSOLE] NEURAL DIRECTIVE`).

> **Atalho Global**: Pressiona **`Ctrl+K`** em qualquer vista para abrir a **Command Palette**.

---

## 🚀 Instalação Rápida (PowerShell)

```powershell
git clone https://github.com/Miguel-Reis/antigravity-brain.git "$HOME\.gemini\antigravity\scratch\brain_mcp"; python "$HOME\.gemini\antigravity\scratch\brain_mcp\install.py"
```

O instalador [`install.py`](./install.py) regista automaticamente:
- Hooks globais em `~/.gemini/config/hooks.json`
- Plugin e regras em `~/.gemini/config/plugins/antigravity-brain`
- Servidor MCP `antigravity-brain` em `~/.gemini/config/mcp_config.json`
- Arranque em background de [`web_dashboard.py`](./web_dashboard.py) em `http://127.0.0.1:8765`

---

## 🔄 Atualização

O serviço verifica atualizações automaticamente em `origin/main`. Para atualizar manualmente:
- Clica em **`📦 Git`** no topo do dashboard (`http://127.0.0.1:8765`), ou executa:
  ```powershell
  python "$HOME\.gemini\antigravity\scratch\brain_mcp\auto_updater.py"
  ```

---

## 🔒 Privacidade

A base de dados local (`brain.db*`) e o mapeamento privado de projetos (`.brain_workspaces.json`) estão bloqueados no [`.gitignore`](./.gitignore) e **nunca** são enviados para o GitHub.
