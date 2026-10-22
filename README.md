# 🧠 Antigravity Brain v2.4 — Obsidian Graph + Scout-First Asymmetric Swarm

Motor local de memória persistente (**SQLite WAL + FTS5 BM25**), otimização da quota de **5 horas / tokens** e monitor em tempo real **Scout-First Asymmetric Swarm** para o **Antigravity**.

---

## ✨ Funcionalidades Principais

1. **Injeção Efémera Zero-Round-Trip (`PreInvocation` Hook — ~15ms)**:
   - Antes de cada resposta do modelo, [`brain_inject.py`](./brain_inject.py) pesquisa na base de dados local (`brain.db`) e injeta apenas os factos relevantes + o mapa partilhado da codebase (`<320 tokens`), poupando milhares de tokens em buscas repetidas.
2. **Auto-Harvester a Custo Zero (`Stop` Hook)**:
   - No fim de cada resposta, [`brain_harvest.py`](./brain_harvest.py) extrai automaticamente os ficheiros editados, checkpoints e notas `<!-- brain: Tópico | Facto -->` sem gastar 1 único token de LLM.
3. **Obsidian Neural Graph View (`http://127.0.0.1:8765/#graph`)**:
   - Grafo interativo com formas geométricas vetoriais por categoria, física pré-aquecida sem *jitter* no `F5`, pesquisa FTS5 em tempo real e inspetor de ligações sinápticas.
4. **Scout-First Asymmetric Swarm Monitor (`http://127.0.0.1:8765/#swarm`)**:
   - **0. `SCOUT-01` (Leitura Única AST)**: Lê a codebase **1 única vez** e partilha o `[SCOUT_SHARED_MAP]` com todos os subagentes para nenhum worker gastar tokens a reler ficheiros.
   - **1. `ARCHITECT` ➔ 2. `SWARM (4 Lanes: UI, API, TESTS, DOCS)` ➔ 3. `VERIFY (48/48 Checks)`**: Painel visual em tempo real para acompanhar o progresso dos subagentes.
5. **Token Diet (`Lean` vs `Full`) & Auto-Updater Git**:
   - Alterna entre perfil económico (`lean`) e completo (`full`) com 1 clique.
   - **Auto-Update Integrado**: Verifica automaticamente no GitHub (`origin/main`) ao iniciar e a cada 30 minutos (ou através do botão **`📦 Git`** no topo do dashboard).

---

## 🚀 Instalação Rápida num Novo PC (1 Comando no PowerShell)

Basta abrir o **PowerShell** e colar este comando:

```powershell
git clone https://github.com/Miguel-Reis/antigravity-brain.git "$HOME\.gemini\antigravity\scratch\brain_mcp"; python "$HOME\.gemini\antigravity\scratch\brain_mcp\install.py"
```

*(Ou fazer duplo-clique em `install.bat` depois de clonar!)*

O instalador [`install.py`](./install.py) configura tudo sozinho para o utilizador atual:
- Regista os hooks globais em `~/.gemini/config/hooks.json`
- Instala o plugin global em `~/.gemini/config/plugins/antigravity-brain`
- Regista o servidor MCP `antigravity-brain` em `~/.gemini/config/mcp_config.json`
- Adiciona o arranque silencioso (`pythonw.exe`) ao iniciar o Windows
- Abre o servidor local em **`http://127.0.0.1:8765`**

---

## 🔄 Como Atualizar (Auto-Update ou Manual)

O projeto já inclui **Auto-Update automático** em background (verifica novos commits em `origin/main` sempre que o servidor inicia e a cada 30 minutos).

Se quiseres forçar uma atualização imediata a qualquer momento, tens 3 opções:
1. **No Browser (`http://127.0.0.1:8765`)**: Clica no botão **`📦 Git: <sha> (Auto)`** no canto superior direito.
2. **Duplo-clique**: Executa o ficheiro `update.bat`.
3. **Via Terminal**:
   ```powershell
   python "$HOME\.gemini\antigravity\scratch\brain_mcp\auto_updater.py"
   ```
