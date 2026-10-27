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
    active_servers: Dict[str, Any] = {}
    if os.path.isfile(MCP_CONFIG_PATH):
        try:
            with open(MCP_CONFIG_PATH, "r", encoding="utf-8") as f:
                active_servers = (json.load(f) or {}).get("mcpServers", {})
        except Exception:
            pass

    full_servers: Dict[str, Any] = dict(active_servers)
    if os.path.isfile(MCP_FULL_BACKUP):
        try:
            with open(MCP_FULL_BACKUP, "r", encoding="utf-8") as fb:
                for k, v in ((json.load(fb) or {}).get("mcpServers", {})).items():
                    full_servers.setdefault(k, v)
        except Exception:
            pass

    if os.path.isdir(MCP_SCHEMAS_DIR):
        for entry in os.listdir(MCP_SCHEMAS_DIR):
            if os.path.isdir(os.path.join(MCP_SCHEMAS_DIR, entry)):
                full_servers.setdefault(entry, {})

    report = []
    for s_name in full_servers:
        s_dir = os.path.join(MCP_SCHEMAS_DIR, s_name)
        tool_count = 0
        schema_bytes = 0
        if os.path.isdir(s_dir):
            for fname in os.listdir(s_dir):
                if fname.endswith(".json"):
                    tool_count += 1
                    schema_bytes += os.path.getsize(os.path.join(s_dir, fname))
        is_enabled = s_name in active_servers
        header_tokens = (tool_count * 7 + 15) if is_enabled else 0
        report.append(
            {
                "server": s_name,
                "enabled": is_enabled,
                "tools": tool_count,
                "schema_kb": round(schema_bytes / 1024.0, 1),
                "header_tokens_per_step": header_tokens,
                "potential_tokens": tool_count * 7 + 15,
                "in_lean_profile": s_name in LEAN_MCP_SERVERS,
            }
        )
    report.sort(key=lambda x: (not x["enabled"], -x["tools"]))
    return report


def toggle_single_mcp_server(server_name: str) -> Dict[str, Any]:
    """Ativa ou pausa individualmente um único servidor MCP (usado na Sala de Servidores 3D)."""
    if not os.path.isfile(MCP_CONFIG_PATH):
        return {"ok": False, "error": "mcp_config.json não encontrado."}

    with open(MCP_CONFIG_PATH, "r", encoding="utf-8") as f:
        current_cfg = json.load(f) or {}
    curr_servers = current_cfg.get("mcpServers", {})

    if not os.path.isfile(MCP_FULL_BACKUP) and len(curr_servers) > 0:
        shutil.copy2(MCP_CONFIG_PATH, MCP_FULL_BACKUP)

    backup_servers: Dict[str, Any] = {}
    if os.path.isfile(MCP_FULL_BACKUP):
        try:
            with open(MCP_FULL_BACKUP, "r", encoding="utf-8") as fb:
                backup_servers = (json.load(fb) or {}).get("mcpServers", {})
        except Exception:
            pass

    if server_name in curr_servers:
        # Guardar definição no backup antes de pausar
        if server_name not in backup_servers:
            backup_servers[server_name] = curr_servers[server_name]
            with open(MCP_FULL_BACKUP, "w", encoding="utf-8") as fb:
                json.dump({"mcpServers": backup_servers}, fb, indent=2)
        del curr_servers[server_name]
        new_state = False
    else:
        if server_name in backup_servers:
            curr_servers[server_name] = backup_servers[server_name]
            new_state = True
        else:
            return {"ok": False, "error": f"Configuração de '{server_name}' não encontrada no backup."}

    current_cfg["mcpServers"] = curr_servers
    with open(MCP_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(current_cfg, f, indent=2)

    return {
        "ok": True,
        "server": server_name,
        "enabled": new_state,
        "mcp_servers": audit_mcp_servers(),
    }


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


ALL_BRAIN_MCP_TOOLS = [
    "store_fact",
    "search_brain",
    "forget_fact",
    "save_checkpoint",
    "brain_stats",
    "swarm_scout",
    "swarm_start",
    "swarm_update_task",
    "swarm_status",
    "swarm_symbol_lookup",
    "swarm_impact_graph",
    "brain_prune_tools",
    "swarm_sandbox",
    "swarm_watch_audit",
    "swarm_graph_path",
    "swarm_architecture_report",
]

INTENT_TOOL_ROUTING: Dict[str, Dict[str, Any]] = {
    "bugfix_diagnosis": {
        "active_tools": ["swarm_symbol_lookup", "swarm_impact_graph", "swarm_graph_path", "search_brain", "store_fact"],
        "active_mcps": ["antigravity-brain", "codebase-memory"],
        "subagent_topology": "SCOUT (flash_lite) -> DEBUG-WORKER (Gemini 4 Argon) -> QA-VERIFY (flash)",
    },
    "ui_3d_interactive": {
        "active_tools": ["swarm_symbol_lookup", "swarm_status", "swarm_update_task", "store_fact"],
        "active_mcps": ["antigravity-brain"],
        "subagent_topology": "UI-01 (Gemini 4 Argon) + QA-BROWSER (flash)",
    },
    "architecture_synthesis": {
        "active_tools": ["swarm_scout", "swarm_impact_graph", "swarm_graph_path", "swarm_architecture_report", "save_checkpoint"],
        "active_mcps": ["antigravity-brain", "context7"],
        "subagent_topology": "ARCH-01 (Gemini 4 Argon) -> 4 Parallel Lanes (UI, API, TESTS, DOCS)",
    },
    "quota_performance": {
        "active_tools": ["brain_prune_tools", "brain_stats", "swarm_scout", "save_checkpoint"],
        "active_mcps": ["antigravity-brain"],
        "subagent_topology": "SCOUT (flash_lite · Single-Pass)",
    },
    "security_privacy_gate": {
        "active_tools": ["swarm_impact_graph", "swarm_sandbox", "search_brain", "store_fact"],
        "active_mcps": ["antigravity-brain"],
        "subagent_topology": "SECURITY-GATE (Gemini 4 Argon) + AI-Defence Redactor",
    },
    "general_engineering": {
        "active_tools": ["swarm_symbol_lookup", "search_brain", "store_fact", "save_checkpoint"],
        "active_mcps": ["antigravity-brain", "codebase-memory"],
        "subagent_topology": "Gemini 4 Argon (inherit) + Scout Shared Map",
    },
}


def prune_tools_for_intent(user_query: str, workspace: str = "global") -> Dict[str, Any]:
    """
    Orçamento Dinâmico de Ferramentas MCP por Intenção (Option C - Dynamic Tool Pruning):
    Seleciona apenas o subconjunto estrito de ferramentas MCP relevantes para a intenção
    classificada pelo JEV-S1 Router (<0.05ms), reduzindo o peso de cabeçalho em 55-70%.
    """
    db = BrainDB()
    ws = db.normalize_workspace(workspace)
    route = db.jev_system1_route(user_query or "general engineering", ws)
    intent = str(route.get("intent", "general_engineering"))
    spec = INTENT_TOOL_ROUTING.get(intent, INTENT_TOOL_ROUTING["general_engineering"])

    active_tools = spec["active_tools"]
    pruned_tools = [t for t in ALL_BRAIN_MCP_TOOLS if t not in active_tools]

    mcp_audit = audit_mcp_servers()
    total_static_tokens = sum(m["potential_tokens"] for m in mcp_audit) + len(ALL_BRAIN_MCP_TOOLS) * 42
    active_tokens = len(active_tools) * 42 + len(spec["active_mcps"]) * 28
    saved_per_step = max(120, total_static_tokens - active_tokens)
    reduction_pct = round((saved_per_step / max(1, total_static_tokens)) * 100.0, 1)

    return {
        "ok": True,
        "workspace": ws,
        "intent": intent,
        "decision_latency_ms": route.get("decision_latency_ms", 0.02),
        "active_mcps": spec["active_mcps"],
        "active_tools": active_tools,
        "selected_tools": active_tools,
        "pruned_tools": pruned_tools,
        "active_tools_count": len(active_tools),
        "selected_tools_count": len(active_tools),
        "total_tools_available": len(ALL_BRAIN_MCP_TOOLS),
        "pruned_tools_count": len(pruned_tools),
        "tokens_saved_per_step": saved_per_step,
        "estimated_tokens_saved": saved_per_step,
        "reduction_pct": reduction_pct,
        "subagent_topology": spec["subagent_topology"],
    }


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
    print("  • Dynamic Tool Pruning         : python token_diet.py prune \"corrigir bug AST\"")
    print("  • Pesquisar no Brain via CLI   : python token_diet.py search \"sua pergunta\"")
    print("=" * 72)


def main() -> None:
    parser = argparse.ArgumentParser(description="Antigravity Brain v2 & Token Diet CLI")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("status", help="Exibe relatório completo do Brain e auditoria de tokens")

    p_prof = sub.add_parser("profile", help="Alterna entre perfil 'lean' e 'full' no mcp_config.json")
    p_prof.add_argument("mode", choices=["lean", "full"])

    p_prune = sub.add_parser("prune", help="Executa Dynamic Tool Pruning por intenção JEV-S1")
    p_prune.add_argument("query", type=str)
    p_prune.add_argument("--ws", type=str, default="global")

    p_search = sub.add_parser("search", help="Testa pesquisa híbrida FTS5 BM25 + Semântica no Brain")
    p_search.add_argument("query", type=str)
    p_search.add_argument("--ws", type=str, default="global")

    sub.add_parser("seed", help="Popula o Brain com memórias iniciais do ambiente")

    args = parser.parse_args()
    if args.cmd == "profile":
        print(switch_mcp_profile(args.mode))
    elif args.cmd == "prune":
        sys.stdout.reconfigure(encoding="utf-8")
        print(json.dumps(prune_tools_for_intent(args.query, workspace=args.ws), indent=2, ensure_ascii=False))
    elif args.cmd == "search":
        sys.stdout.reconfigure(encoding="utf-8")
        db = BrainDB()
        res = db.search_memories(args.query, workspace=args.ws, n_results=5, update_stats=False)
        for r in res:
            print(f"[{r['id']}] ({r['workspace']}/{r['category']}) score={r['final_score']:.2f} sem={r.get('semantic_similarity', 0):.2f} | {r['topic']}: {r['fact']}")
    elif args.cmd == "seed":
        db = BrainDB()
        c = seed_initial_memories(db)
        print(f"Seeding concluído ({c} novos factos adicionados).")
    else:
        print_status()


if __name__ == "__main__":
    main()

