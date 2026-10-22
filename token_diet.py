import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List

from db_engine import BrainDB, seed_initial_memories

CONFIG_DIR = os.path.expanduser("~/.gemini/config")
MCP_CONFIG_PATH = os.path.join(CONFIG_DIR, "mcp_config.json")
MCP_FULL_BACKUP = os.path.join(CONFIG_DIR, "mcp_config.full.json")
MAIN_CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
MAIN_CONFIG_BACKUP = os.path.join(CONFIG_DIR, "config.full.json")
MCP_SCHEMAS_DIR = os.path.expanduser("~/.gemini/antigravity/mcp")
PLUGINS_DIR = os.path.join(CONFIG_DIR, "plugins")
BRAIN_CONV_DIR = os.path.expanduser("~/.gemini/antigravity/brain")

LEAN_MCP_SERVERS = {"antigravity-brain", "codebase-memory", "context7"}
CORE_PLUGINS = {"antigravity-brain", "claude-architect-coder", "context7", "strix"}


def audit_mcp_servers() -> List[Dict[str, Any]]:
    if not os.path.isfile(MCP_CONFIG_PATH):
        return []
    with open(MCP_CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    servers = cfg.get("mcpServers", {})
    report = []
    for s_name in servers:
        s_dir = os.path.join(MCP_SCHEMAS_DIR, s_name)
        tool_count = 0
        schema_bytes = 0
        if os.path.isdir(s_dir):
            for fname in os.listdir(s_dir):
                if fname.endswith(".json"):
                    tool_count += 1
                    schema_bytes += os.path.getsize(os.path.join(s_dir, fname))
        header_tokens = tool_count * 7 + 15
        report.append(
            {
                "server": s_name,
                "tools": tool_count,
                "schema_kb": round(schema_bytes / 1024.0, 1),
                "header_tokens_per_step": header_tokens,
                "in_lean_profile": s_name in LEAN_MCP_SERVERS,
            }
        )
    report.sort(key=lambda x: x["tools"], reverse=True)
    return report


def audit_plugins() -> Dict[str, Any]:
    if not os.path.isdir(PLUGINS_DIR):
        return {"plugin_count": 0, "enabled_plugins": 0, "skill_count": 0, "estimated_tokens_per_step": 0}

    disabled_in_cfg = set()
    if os.path.isfile(MAIN_CONFIG_PATH):
        try:
            with open(MAIN_CONFIG_PATH, "r", encoding="utf-8") as f:
                mcfg = json.load(f)
            for k, v in (mcfg.get("plugins") or {}).items():
                if isinstance(v, dict) and v.get("enabled") is False:
                    disabled_in_cfg.add(k)
        except Exception:
            pass

    plugins = os.listdir(PLUGINS_DIR)
    enabled_plugins = 0
    skill_count = 0
    total_desc_chars = 0
    for p in plugins:
        if p in disabled_in_cfg:
            continue
        enabled_plugins += 1
        skills_dir = os.path.join(PLUGINS_DIR, p, "skills")
        if os.path.isdir(skills_dir):
            for s in os.listdir(skills_dir):
                skill_md = os.path.join(skills_dir, s, "SKILL.md")
                if os.path.isfile(skill_md):
                    skill_count += 1
                    total_desc_chars += 320

    return {
        "plugin_count": len(plugins),
        "enabled_plugins": enabled_plugins,
        "skill_count": skill_count,
        "estimated_tokens_per_step": total_desc_chars // 4,
    }


def switch_mcp_profile(mode: str) -> str:
    if not os.path.isfile(MCP_CONFIG_PATH):
        return "Ficheiro mcp_config.json não encontrado."

    with open(MCP_CONFIG_PATH, "r", encoding="utf-8") as f:
        current_cfg = json.load(f)

    if mode == "lean":
        curr_servers = current_cfg.get("mcpServers", {})
        if len(curr_servers) > len(LEAN_MCP_SERVERS):
            shutil.copy2(MCP_CONFIG_PATH, MCP_FULL_BACKUP)

        source_servers = curr_servers
        if os.path.isfile(MCP_FULL_BACKUP):
            with open(MCP_FULL_BACKUP, "r", encoding="utf-8") as fb:
                source_servers = json.load(fb).get("mcpServers", curr_servers)

        lean_servers = {
            k: v for k, v in source_servers.items() if k in LEAN_MCP_SERVERS
        }
        with open(MCP_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"mcpServers": lean_servers}, f, indent=2)

        # Desativar plugins secundários em config.json mantendo CORE_PLUGINS
        disabled_count = 0
        if os.path.isfile(MAIN_CONFIG_PATH) and os.path.isdir(PLUGINS_DIR):
            with open(MAIN_CONFIG_PATH, "r", encoding="utf-8") as f:
                main_cfg = json.load(f)
            if "plugins" not in main_cfg:
                shutil.copy2(MAIN_CONFIG_PATH, MAIN_CONFIG_BACKUP)
            plugins_map: Dict[str, Any] = {}
            for p_name in os.listdir(PLUGINS_DIR):
                if p_name in CORE_PLUGINS:
                    plugins_map[p_name] = {"enabled": True}
                else:
                    plugins_map[p_name] = {"enabled": False}
                    disabled_count += 1
            main_cfg["plugins"] = plugins_map
            with open(MAIN_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(main_cfg, f, indent=2)

        removed_mcps = set(source_servers.keys()) - set(lean_servers.keys())
        return (
            f"Perfil 'lean' ATIVADO!\n"
            f"  - MCPs ativos: {sorted(lean_servers.keys())} (Pausados: {sorted(removed_mcps)})\n"
            f"  - Plugins ativos: {sorted(CORE_PLUGINS)} ({disabled_count} plugins secundários pausados em config.json)"
        )

    elif mode == "full":
        msg_parts = []
        if os.path.isfile(MCP_FULL_BACKUP):
            shutil.copy2(MCP_FULL_BACKUP, MCP_CONFIG_PATH)
            msg_parts.append("MCPs restaurados de mcp_config.full.json")
        if os.path.isfile(MAIN_CONFIG_BACKUP):
            shutil.copy2(MAIN_CONFIG_BACKUP, MAIN_CONFIG_PATH)
            msg_parts.append("Plugins restaurados de config.full.json")
        elif os.path.isfile(MAIN_CONFIG_PATH):
            with open(MAIN_CONFIG_PATH, "r", encoding="utf-8") as f:
                main_cfg = json.load(f)
            if "plugins" in main_cfg:
                del main_cfg["plugins"]
                with open(MAIN_CONFIG_PATH, "w", encoding="utf-8") as f:
                    json.dump(main_cfg, f, indent=2)
                msg_parts.append("Todos os plugins reativados em config.json")
        return "Perfil 'full' RESTAURADO: " + (", ".join(msg_parts) if msg_parts else "Já estava no modo full.")

    return f"Modo desconhecido: {mode}"


def print_status() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    db = BrainDB()
    stats = db.get_stats()
    mcp_report = audit_mcp_servers()
    plug_report = audit_plugins()

    print("=" * 72)
    print(" 🧠 ANTIGRAVITY BRAIN v2 & AUDITORIA DE QUOTA (5h / TOKENS)")
    print("=" * 72)

    print("\n[1] ESTADO DA BASE DE DADOS (brain.db - SQLite FTS5 BM25)")
    print(f"  • Memórias guardadas      : {stats['total_memories']} (Categorias: {stats['categories']})")
    print(f"  • Checkpoints de projeto  : {stats['total_checkpoints']}")
    print(f"  • Injeções PreInvocation  : {stats['injections_count']} (Latência média: {stats['avg_inject_latency_ms']} ms)")
    print(f"  • Auto-Harvests (Stop)    : {stats['harvests_count']}")
    print(f"  • Tokens injetados        : {stats['total_injected_tokens']:,}")
    print(f"  • Economia est. acumulada : {stats['estimated_saved_tokens']:,} tokens (Líquido: +{stats['net_tokens_saved']:,} tokens)")

    print("\n[2] AUDITORIA DE SERVIDORES MCP ATIVOS (mcp_config.json)")
    total_mcp_tools = 0
    total_mcp_tokens = 0
    for item in mcp_report:
        total_mcp_tools += item["tools"]
        total_mcp_tokens += item["header_tokens_per_step"]
        tag = "✅ [LEAN]" if item["in_lean_profile"] else "⚠️ [PESADO]"
        print(
            f"  • {item['server']:<20} : {item['tools']:>3} tools | ~{item['header_tokens_per_step']:>4} tokens/passo | {tag}"
        )
    print(f"  -> TOTAL MCPs: {total_mcp_tools} tools (~{total_mcp_tokens:,} tokens estáticos por passo)")

    print("\n[3] AUDITORIA DE PLUGINS & SKILLS GLOBAIS")
    print(
        f"  • Plugins instalados      : {plug_report['plugin_count']} pastas ({plug_report['skill_count']} skills)"
    )
    print(
        f"  • Custo de cabeçalho      : ~{plug_report['estimated_tokens_per_step']:,} tokens estáticos por passo"
    )
    print("  • Nota: O limite de orçamento do sistema já está a cortar skills excedentes.")

    print("\n[4] COMANDOS RÁPIDOS DISPONÍVEIS")
    print("  • Ativar modo económico (Lean) : python token_diet.py profile lean")
    print("  • Restaurar todos os MCPs      : python token_diet.py profile full")
    print("  • Pesquisar no Brain via CLI   : python token_diet.py search \"sua pergunta\"")
    print("=" * 72)


def main() -> None:
    parser = argparse.ArgumentParser(description="Antigravity Brain v2 & Token Diet CLI")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("status", help="Exibe relatório completo do Brain e auditoria de tokens")

    p_prof = sub.add_parser("profile", help="Alterna entre perfil 'lean' e 'full' no mcp_config.json")
    p_prof.add_argument("mode", choices=["lean", "full"])

    p_search = sub.add_parser("search", help="Testa pesquisa híbrida FTS5 BM25 no Brain")
    p_search.add_argument("query", type=str)
    p_search.add_argument("--ws", type=str, default="global")

    sub.add_parser("seed", help="Popula o Brain com memórias iniciais do ambiente")

    args = parser.parse_args()
    if args.cmd == "profile":
        print(switch_mcp_profile(args.mode))
    elif args.cmd == "search":
        sys.stdout.reconfigure(encoding="utf-8")
        db = BrainDB()
        res = db.search_memories(args.query, workspace=args.ws, n_results=5, update_stats=False)
        for r in res:
            print(f"[{r['id']}] ({r['workspace']}/{r['category']}) score={r['final_score']:.2f} | {r['topic']}: {r['fact']}")
    elif args.cmd == "seed":
        db = BrainDB()
        c = seed_initial_memories(db)
        print(f"Seeding concluído ({c} novos factos adicionados).")
    else:
        print_status()


if __name__ == "__main__":
    main()
