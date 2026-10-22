import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

REPO_DIR = Path(__file__).resolve().parent
HOME_DIR = Path.home()
GEMINI_DIR = HOME_DIR / ".gemini"
CONFIG_DIR = GEMINI_DIR / "config"
PLUGINS_DIR = CONFIG_DIR / "plugins" / "antigravity-brain"
RULES_DIR = PLUGINS_DIR / "rules"


def configure_hooks_and_plugin(silent: bool = False) -> Dict[str, Any]:
    """Configura automaticamente os hooks globais, plugin e MCP para qualquer utilizador."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    RULES_DIR.mkdir(parents=True, exist_ok=True)

    python_cmd = "python"
    inject_script = (REPO_DIR / "brain_inject.py").as_posix()
    harvest_script = (REPO_DIR / "brain_harvest.py").as_posix()
    server_script = (REPO_DIR / "server.py").as_posix()

    hooks_payload = {
        "hooks": {
            "PreInvocation": [
                {
                    "command": f'{python_cmd} "{inject_script}"',
                    "timeout": 5000,
                }
            ],
            "Stop": [
                {
                    "command": f'{python_cmd} "{harvest_script}"',
                    "timeout": 8000,
                }
            ],
        }
    }

    # 1. Atualizar ~/.gemini/config/hooks.json preservando outros hooks se existirem
    global_hooks_path = CONFIG_DIR / "hooks.json"
    existing_hooks: Dict[str, Any] = {}
    if global_hooks_path.is_file():
        try:
            existing_hooks = json.loads(global_hooks_path.read_text(encoding="utf-8"))
        except Exception:
            existing_hooks = {}

    merged_hooks = existing_hooks.get("hooks", {})
    merged_hooks["PreInvocation"] = hooks_payload["hooks"]["PreInvocation"]
    merged_hooks["Stop"] = hooks_payload["hooks"]["Stop"]
    existing_hooks["hooks"] = merged_hooks
    global_hooks_path.write_text(
        json.dumps(existing_hooks, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # 2. Atualizar ~/.gemini/config/plugins/antigravity-brain/
    plugin_json_path = PLUGINS_DIR / "plugin.json"
    plugin_manifest = {
        "name": "antigravity-brain",
        "version": "2.4.0",
        "description": "Zero-Round-Trip SQLite FTS5 Memory Engine, Obsidian Graph View & Scout-First Asymmetric Swarm",
        "hooks": "./hooks.json",
        "rules": ["./rules/AGENTS.md"],
    }
    plugin_json_path.write_text(
        json.dumps(plugin_manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (PLUGINS_DIR / "hooks.json").write_text(
        json.dumps(hooks_payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    agents_md_content = """# Antigravity Brain v2 — Zero-Round-Trip Memory Protocol

1. **Pre-Injected Context (`[BRAIN_MEMORY]`)**: Prior to responding, check if an ephemeral `[BRAIN_MEMORY]` block was injected. Trust its file paths, checkpoints, and environment facts so you do not waste tool calls re-discovering project structure.
2. **Zero-Token Memory Harvesting (`<!-- brain: Topic | Fact -->`)**: Whenever you solve a non-trivial bug, discover a critical IP/config/path, or make an architectural decision, append a hidden HTML comment at the very end of your response:
   `<!-- brain: Short Topic | Concise actionable fact with exact paths/values -->`
   The `Stop` hook (`brain_harvest.py`) automatically indexes these comments and any edited files into `brain.db` at zero LLM token cost.
3. **Explicit Search**: Only call the `antigravity-brain` MCP tool (`search_brain`) if you need a deep query that was not covered by the automatic `[BRAIN_MEMORY]` injection.
4. **Scout-First Asymmetric Swarm Protocol (`SCOUT ➔ PLAN ➔ SWARM ➔ VERIFY`)**:
   - **Shared Codebase Map (`[SCOUT_SHARED_MAP]`)**: Before launching multi-file work, run `SwarmEngine.run_codebase_scout()` (or `swarm_scout` / `swarm_start`) so the codebase is indexed **1 time** and shared in `brain.db` across all agents via `PreInvocation`.
   - **Decoupled Architect & Lightweight Lanes**: Read the goal and `[SCOUT_SHARED_MAP]` once as the Architect, decompose into isolated lanes (`UI`, `API`, `TESTS`, `DOCS`), and delegate parallel execution via `invoke_subagent` with `Model="flash"` or `"flash_lite"`, passing the exact target file and symbols so workers never re-read the codebase.
"""
    (RULES_DIR / "AGENTS.md").write_text(agents_md_content, encoding="utf-8")

    # 3. Registar o servidor MCP em ~/.gemini/config/mcp_config.json
    mcp_cfg_path = CONFIG_DIR / "mcp_config.json"
    mcp_cfg: Dict[str, Any] = {"mcpServers": {}}
    if mcp_cfg_path.is_file():
        try:
            mcp_cfg = json.loads(mcp_cfg_path.read_text(encoding="utf-8"))
        except Exception:
            mcp_cfg = {"mcpServers": {}}

    servers = mcp_cfg.setdefault("mcpServers", {})
    servers["antigravity-brain"] = {
        "command": "python",
        "args": [server_script],
    }
    mcp_cfg_path.write_text(
        json.dumps(mcp_cfg, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # 4. Registar Auto-Start no arranque do Windows (HKCU\...\Run\AntigravityBrain)
    startup_registered = False
    if os.name == "nt":
        try:
            import winreg

            pythonw_exe = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
            if not os.path.isfile(pythonw_exe):
                pythonw_exe = sys.executable
            dashboard_script = str(REPO_DIR / "web_dashboard.py")
            cmd_val = f'"{pythonw_exe}" "{dashboard_script}"'
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                winreg.SetValueEx(key, "AntigravityBrain", 0, winreg.REG_SZ, cmd_val)
            startup_registered = True
        except Exception:
            startup_registered = False

    if not silent:
        print("✅ Hooks globais configurados em:", global_hooks_path)
        print("✅ Plugin Antigravity Brain v2.4 instalado em:", PLUGINS_DIR)
        print("✅ Servidor MCP registado em:", mcp_cfg_path)
        if startup_registered:
            print("✅ Auto-Start no arranque do Windows (HKCU Run) ativado!")

    return {
        "hooks_path": str(global_hooks_path),
        "plugin_dir": str(PLUGINS_DIR),
        "mcp_config": str(mcp_cfg_path),
        "startup_registered": startup_registered,
    }


def main() -> None:
    if getattr(sys, "stdout", None) is not None and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    silent = "--silent" in sys.argv
    if not silent:
        print("=" * 68)
        print(" 🧠 INSTALADOR & AUTO-CONFIGURADOR — ANTIGRAVITY BRAIN v2.4")
        print("=" * 68)

    configure_hooks_and_plugin(silent=silent)

    # Inicializar base de dados + Scout + Servidor Web
    if str(REPO_DIR) not in sys.path:
        sys.path.insert(0, str(REPO_DIR))

    from db_engine import BrainDB, ensure_dashboard_running, seed_initial_memories
    from swarm_engine import SwarmEngine

    db = BrainDB()
    seed_initial_memories(db)
    SwarmEngine(db).ensure_default_run()
    started = ensure_dashboard_running()

    if not silent:
        print(f"✅ Base de dados SQLite FTS5 pronta: {REPO_DIR / 'brain.db'}")
        print(f"✅ Dashboard Web & Swarm Monitor ativo ({started}): http://127.0.0.1:8765")
        print("   -> Vista Grafo Obsidian : http://127.0.0.1:8765/#graph")
        print("   -> Vista Swarm Monitor  : http://127.0.0.1:8765/#swarm")
        print("=" * 68)


if __name__ == "__main__":
    main()
