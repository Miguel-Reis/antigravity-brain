import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Set, Tuple

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

import importlib
from ast_impact_watcher import get_global_watcher, start_ast_impact_watcher_daemon
from auto_updater import (
    _schedule_server_hot_reload,
    check_and_apply_update,
    get_git_status,
    kill_other_dashboard_processes,
    start_auto_update_daemon,
)
from brain_harvest import harvest_latest_turn
from db_engine import BrainDB, seed_initial_memories
import orbit_engine as _orbit_engine_mod
from orbit_engine import OrbitEngine
from swarm_engine import SwarmEngine
from token_diet import (
    audit_mcp_servers,
    audit_plugins,
    prune_tools_for_intent,
    switch_mcp_profile,
    toggle_single_mcp_server,
)

PORT = 8765
INDEX_HTML_PATH = os.path.join(CURRENT_DIR, "index.html")
BRAIN_LOGS_ROOT = os.path.expanduser("~/.gemini/antigravity/brain")
SCRATCH_ROOT = os.path.expanduser("~/.gemini/antigravity/scratch")

_ORBIT_MTIME: float = (
    os.path.getmtime(os.path.join(CURRENT_DIR, "orbit_engine.py"))
    if os.path.isfile(os.path.join(CURRENT_DIR, "orbit_engine.py"))
    else 0.0
)


def _get_fresh_orbit_engine(db: BrainDB) -> Any:
    """Recarrega orbit_engine.py automaticamente em memória se o ficheiro mudou no disco (ex: após git pull)."""
    global _ORBIT_MTIME, OrbitEngine, _orbit_engine_mod
    try:
        orb_path = os.path.join(CURRENT_DIR, "orbit_engine.py")
        if os.path.isfile(orb_path):
            cur_m = os.path.getmtime(orb_path)
            if cur_m > _ORBIT_MTIME:
                _ORBIT_MTIME = cur_m
                _orbit_engine_mod = importlib.reload(_orbit_engine_mod)
                OrbitEngine = _orbit_engine_mod.OrbitEngine
    except Exception:
        pass
    return OrbitEngine(db)


def harvest_all_workspace_context(db: BrainDB) -> Dict[str, int]:
    """Popula o Brain com memórias reais das conversas e projetos da máquina."""
    added_memories = seed_initial_memories(db)
    harvested_turns = 0

    # 1. Enriquecer memórias do motor Brain v4.5 em 6 Clusters Planetários ("Îlots")
    project_facts = [
        (
            "Injetor Efémero PreInvocation (brain_inject.py)",
            "Interceta o evento PreInvocation antes da chamada ao modelo, lê o último USER_INPUT do transcript.jsonl e injeta até 320 tokens via ephemeralMessage + Scout Map em ~15-35ms sem round-trip extra.",
            "brain_mcp",
            "optimization",
            "brain_inject preinvocation ephemeralmessage hooks latency sqlite",
            5,
        ),
        (
            "Auto-Harvester Pós-Resposta (brain_harvest.py)",
            "Dispara no evento Stop do Antigravity. Extrai edições de ficheiros (write_to_file/replace_file_content), comentários <!-- brain: Topico | Facto --> e estatísticas de tokens a custo 0.",
            "brain_mcp",
            "optimization",
            "brain_harvest stop hook transcript tokens checkpoint",
            5,
        ),
        (
            "Interface Visual Obsidian Brain Graph & Swarm (web_dashboard.py)",
            "Servidor web local com visualização de grafo planetário estilo Obsidian + Jev-S1, monitor Asymmetric Swarm (#swarm), pesquisa FTS5 BM25 em tempo real e Auto-Updater Git.",
            "brain_mcp",
            "architecture",
            "obsidian graph web_dashboard ui swarm visualizacao fts5",
            5,
        ),
        (
            "Jev-Mem System-1 Neural Router & Adaptive Stopping",
            "Classifica memórias em Working [W], Semantic [S] e Episodic [E] com corte adaptativo (TH=0.28) e vetor semântico bilingue de 32 dimensões.",
            "brain_mcp",
            "architecture",
            "jev_s1 router semantic working episodic fts5 sqlite",
            5,
        ),
        (
            "Asymmetric Swarm 24 Lanes & Ruflo Pheromone EMA",
            "Orquestra 4 Lanes paralelas (UI, API, TESTS, DOCS × 6 workers) com Work-Stealing automático e fitness de feromonas EMA em tempo real.",
            "brain_mcp",
            "architecture",
            "swarm_24x swarm lanes ruflo pheromone work_steal verify",
            5,
        ),
        (
            "Subagent Transactional Sandbox (Copy-on-Write)",
            "Isola subagentes em sandboxes transacionais com snapshots SHA-256, AST syntax gate e scanner AI-Defence antes do merge.",
            "brain_mcp",
            "infra",
            "swarm_24x swarm sandbox cow verify ast security",
            4,
        ),
        (
            "Verify Gate 48/48 (AST + HTTP + SQLite WAL)",
            "Auditoria determinística de 48 verificações automáticas garantindo zero colisões de ficheiros e integridade transacional.",
            "brain_mcp",
            "optimization",
            "swarm_24x verify qa ast sqlite swarm check",
            4,
        ),
        (
            "Graphify Multi-Modal Knowledge Graph (325 Nodes)",
            "Constrói o grafo multi-modal da codebase (JS Functions ➔ HTTP Routes ➔ Python AST ➔ SQLite Tables) com arestas EXTRACTED, INFERRED e AMBIGUOUS.",
            "brain_mcp",
            "architecture",
            "graphify_ast graphify ast bfs sqlite routes symbols",
            5,
        ),
        (
            "Automated File-Save AST & Impact Radius Watcher",
            "Daemon que deteta alterações em ficheiros, calcula o diff de símbolos AST e sinaliza automaticamente mudanças HIGH/CRITICAL no blast radius.",
            "brain_mcp",
            "optimization",
            "graphify_ast ast watcher impact blast_radius symbols hooks",
            5,
        ),
        (
            "Graphify BFS Shortest Path & 70x Token Compression",
            "Pesquisa o caminho relacional mais curto entre qualquer função JS e tabela SQLite em <2ms, poupando mais de 70x em tokens de contexto.",
            "brain_mcp",
            "optimization",
            "graphify_ast graphify bfs tokens compression ast",
            4,
        ),
        (
            "Ponte de Comando 3D & Bonecos Articulados 60 FPS",
            "Motor isométrico 3D a 60 FPS com 6 zonas arquitetónicas, câmara Follow & Zoom-to-Cursor no rato, Radar Orbital 2D e sintetizador WebAudio.",
            "brain_mcp",
            "architecture",
            "office_3d webgl canvas camera zoom radar",
            5,
        ),
        (
            "Torres Holográficas 3D do Mapa de Calor por Secretária",
            "Renderiza prismas holográficos 3D interativos sobre as secretárias dos agentes com base na intensidade de edição e calor dos ficheiros.",
            "brain_mcp",
            "optimization",
            "office_3d heatmap holo_towers ast ui",
            5,
        ),
        (
            "Sala de Servidores MCP 3D & Portal Quântico",
            "Controlo interativo 3D dos servidores MCP ativos e chegada cronológica de novos agentes pelo Portal Quântico Noroeste.",
            "brain_mcp",
            "infra",
            "office_3d mcp portal servers tokens",
            4,
        ),
        (
            "Dynamic Intent-Based Tool Pruning (-66.7% Tokens)",
            "Seleciona dinamicamente apenas as 3-4 ferramentas MCP essenciais para a intenção do prompt, cortando 66.7% do overhead de schemas.",
            "brain_mcp",
            "optimization",
            "token_diet quota 5h mcp prune tokens",
            5,
        ),
        (
            "5h Quota Reactor & Perfil Lean vs Full",
            "Monitoriza a janela de 5h do Antigravity e comuta instantaneamente servidores MCP pesados para maximizar turnos disponíveis.",
            "brain_mcp",
            "preference",
            "token_diet quota 5h lean full mcp",
            4,
        ),
    ]
    for topic, fact, ws, cat, tags, imp in project_facts:
        _, is_new = db.store_fact(
            topic=topic, fact=fact, workspace=ws, category=cat, tags=tags, importance=imp
        )
        if is_new:
            added_memories += 1

    try:
        db.discover_causal_links()
    except Exception:
        pass

    if os.path.isdir(SCRATCH_ROOT):
        for entry in sorted(os.listdir(SCRATCH_ROOT)):
            full_p = os.path.join(SCRATCH_ROOT, entry)
            if os.path.isdir(full_p) and not entry.startswith(".") and entry.lower() not in ("antigravity-backup",):
                try:
                    sample_files = [
                        f for f in os.listdir(full_p) if not f.startswith(".")
                    ][:8]
                    if sample_files:
                        ws_slug = entry.lower()
                        _, is_new = db.store_fact(
                            topic=f"Projeto Local: {entry}",
                            fact=f"Localizado em {full_p.replace(chr(92), '/')}. Ficheiros principais: {', '.join(sample_files)}.",
                            workspace=ws_slug,
                            category="architecture",
                            tags=f"projeto scratch {ws_slug}",
                            importance=4,
                        )
                        if is_new:
                            added_memories += 1
                except Exception:
                    pass

    # 2. Analisar profundamente todos os transcripts e artefactos .md em ~/.gemini/antigravity/brain
    if os.path.isdir(BRAIN_LOGS_ROOT):
        for conv_id in os.listdir(BRAIN_LOGS_ROOT):
            conv_dir = os.path.join(BRAIN_LOGS_ROOT, conv_id)
            if not os.path.isdir(conv_dir) or conv_id.startswith("."):
                continue

            # 2a. Extrair artefactos Markdown (.md) da conversa (planos, walkthroughs, ultraplan)
            for fname in os.listdir(conv_dir):
                if fname.endswith(".md"):
                    md_path = os.path.join(conv_dir, fname)
                    try:
                        with open(md_path, "r", encoding="utf-8", errors="ignore") as mf:
                            md_text = mf.read(6000)
                        first_hdr = ""
                        for ln in md_text.splitlines():
                            if ln.startswith("#"):
                                first_hdr = ln.lstrip("#").strip()[:70]
                                break
                        summary_snippet = " ".join(md_text.split())[:260]
                        if summary_snippet:
                            _, is_new = db.store_fact(
                                topic=f"Artefacto: {first_hdr or fname} ({conv_id[:6]})",
                                fact=f"Documento {fname} na conversa {conv_id[:8]}: {summary_snippet}",
                                workspace="global",
                                category="architecture",
                                tags=f"artifact {fname.replace('.md', '')} plan doc",
                                importance=4,
                            )
                            if is_new:
                                added_memories += 1
                    except Exception:
                        pass

            # 2b. Extrair todos os turnos, edições de ficheiros e comentários <!-- brain: ... --> do transcript.jsonl
            t_path = os.path.join(conv_dir, ".system_generated", "logs", "transcript.jsonl")
            if os.path.isfile(t_path):
                try:
                    c = harvest_latest_turn(t_path, "brain_mcp", conv_id, db)
                    harvested_turns += 1
                    added_memories += c

                    with open(t_path, "r", encoding="utf-8", errors="ignore") as tf:
                        for raw_ln in tf:
                            raw_ln = raw_ln.strip()
                            if not raw_ln.startswith("{"):
                                continue
                            try:
                                step = json.loads(raw_ln)
                            except Exception:
                                continue
                            if step.get("type") != "PLANNER_RESPONSE":
                                continue

                            content_txt = str(step.get("content") or "")
                            for b_match in re.finditer(
                                r"<!--\s*brain:\s*([^|\n]+?)\s*\|\s*(.*?)\s*-->",
                                content_txt,
                                flags=re.DOTALL,
                            ):
                                b_topic = b_match.group(1).strip()[:120]
                                b_fact = " ".join(b_match.group(2).strip().split())[:450]
                                if b_topic and b_fact:
                                    _, is_new = db.store_fact(
                                        topic=b_topic,
                                        fact=b_fact,
                                        workspace="brain_mcp",
                                        category="explicit_note",
                                        tags="explicit brain_comment architecture",
                                        importance=5,
                                    )
                                    if is_new:
                                        added_memories += 1

                            for tc in step.get("tool_calls") or []:
                                t_name = tc.get("name", "")
                                args = tc.get("args") or {}
                                if t_name in (
                                    "write_to_file",
                                    "replace_file_content",
                                    "multi_replace_file_content",
                                    "write_file",
                                    "edit_file",
                                ):
                                    target_raw = (
                                        args.get("TargetFile")
                                        or args.get("Path")
                                        or args.get("AbsolutePath")
                                        or ""
                                    )
                                    target = re.sub(
                                        r"/+",
                                        "/",
                                        str(target_raw).strip().strip('"').strip("'").replace("\\", "/"),
                                    )
                                    if (
                                        target
                                        and ".gemini/antigravity/brain" not in target.lower()
                                        and ".gemini/config" not in target.lower()
                                    ):
                                        base_f = os.path.basename(target.rstrip("/"))
                                        if any(
                                            k in base_f.lower()
                                            for k in ("check_", "tmp_", "run_office_sim")
                                        ):
                                            continue
                                        file_ws = db.normalize_workspace(os.path.dirname(target))
                                        if file_ws in ("global", "all", "brain", "scratch"):
                                            continue
                                        ext = os.path.splitext(base_f)[1].lstrip(".").lower() or "file"
                                        _, is_new = db.store_fact(
                                            topic=f"Ficheiro {base_f} ({file_ws})",
                                            fact=f"Ficheiro do projeto {file_ws} em {target} (modificado via {t_name}).",
                                            workspace=file_ws,
                                            category="code_change",
                                            tags=f"file edit {ext} {base_f.lower()} {file_ws}",
                                            importance=3,
                                        )
                                        if is_new:
                                            added_memories += 1
                except Exception:
                    pass

    return {"added_memories": added_memories, "scanned_conversations": harvested_turns}


_GRAPH_PAYLOAD_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}


def build_obsidian_graph_payload(
    db: BrainDB,
    query: str = "",
    workspace_filter: str = "all",
    category_filter: str = "all",
    include_tags: bool = True,
) -> Dict[str, Any]:
    """Constrói a estrutura de nós e ligações sinápticas (estilo Obsidian Graph View)."""
    cache_key = f"{db.db_path}|{query.strip()}|{workspace_filter}|{category_filter}|{int(include_tags)}"
    now_ts = time.time()
    cached_entry = _GRAPH_PAYLOAD_CACHE.get(cache_key)
    if cached_entry and (now_ts - cached_entry[0] < 2.5):
        return cached_entry[1]

    with db._connect() as conn:
        all_memories = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM memories ORDER BY importance DESC, id DESC LIMIT 650;"
            ).fetchall()
        ]
        if len(all_memories) < 12:
            harvest_all_workspace_context(db)
            all_memories = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM memories ORDER BY importance DESC, id DESC LIMIT 650;"
                ).fetchall()
            ]
        all_checkpoints = [
            dict(r)
            for r in conn.execute("SELECT * FROM checkpoints;").fetchall()
        ]

    # Se houver query de pesquisa FTS5 + Semântica 32-D, identificar os IDs com match e respetivos scores
    matched_scores: Dict[int, float] = {}
    matched_sem_sim: Dict[int, float] = {}
    q_vec = BrainDB.compute_semantic_vector(query.strip()) if query.strip() else []
    if query.strip():
        search_res = db.search_memories(
            query=query.strip(), workspace="global", n_results=30, update_stats=False
        )
        for r in search_res:
            rid = int(r["id"])
            matched_scores[rid] = round(float(r.get("final_score", 1.0)), 2)
            matched_sem_sim[rid] = round(float(r.get("semantic_similarity", 0.0)), 3)

    # Filtrar memórias
    filtered_memories: List[Dict[str, Any]] = []
    for m in all_memories:
        if workspace_filter != "all" and m.get("workspace") != workspace_filter:
            continue
        if category_filter != "all" and m.get("category") != category_filter:
            continue
        mid_int = int(m["id"])
        m["is_match"] = (mid_int in matched_scores) if query.strip() else False
        m["search_score"] = matched_scores.get(mid_int, 0.0)
        if mid_int in matched_sem_sim:
            m["semantic_similarity"] = matched_sem_sim[mid_int]
        elif q_vec:
            raw_emb = m.get("embedding_json")
            m_vec = json.loads(raw_emb) if raw_emb else BrainDB.compute_semantic_vector(f"{m.get('topic','')} {m.get('fact','')} {m.get('tags','')}")
            m["semantic_similarity"] = round(BrainDB.cosine_similarity(q_vec, m_vec), 3)
        else:
            m["semantic_similarity"] = round(min(0.99, 0.72 + int(m.get("importance", 3) or 3) * 0.05), 2)
        filtered_memories.append(m)

    nodes: List[Dict[str, Any]] = []
    links: List[Dict[str, Any]] = []
    node_ids: Set[str] = set()

    # 1. Criar Nós de Workspace (Hubs Centrais)
    workspaces = sorted({m.get("workspace", "global") or "global" for m in filtered_memories})
    for ws in workspaces:
        ws_node_id = f"ws:{ws}"
        node_ids.add(ws_node_id)
        nodes.append(
            {
                "id": ws_node_id,
                "label": f"📂 {ws}",
                "node_type": "workspace",
                "workspace": ws,
                "category": "workspace",
                "importance": 5,
                "val": 22,
                "fact": f"Workspace / Projeto '{ws}' no Antigravity Brain.",
                "tags": ws,
            }
        )

    # 2. Criar Nós de Checkpoints
    for chk in all_checkpoints:
        ws = chk.get("workspace", "global")
        if workspace_filter != "all" and ws != workspace_filter:
            continue
        chk_id = f"chk:{ws}"
        node_ids.add(chk_id)
        nodes.append(
            {
                "id": chk_id,
                "label": f"🏁 Checkpoint: {chk.get('project', ws)}",
                "node_type": "checkpoint",
                "workspace": ws,
                "category": "checkpoint",
                "importance": 5,
                "val": 16,
                "fact": (
                    f"Goal: {chk.get('goal', '')}\n"
                    f"Status: {chk.get('status', '')}\n"
                    f"Stack: {chk.get('stack', '')}\n"
                    f"Key Files: {chk.get('key_files', '')}\n"
                    f"Last Completed: {chk.get('last_completed', '')}"
                ),
                "tags": "checkpoint status milestone",
                "updated_at": chk.get("updated_at", ""),
            }
        )
        if f"ws:{ws}" in node_ids:
            links.append(
                {
                    "source": f"ws:{ws}",
                    "target": chk_id,
                    "kind": "checkpoint_link",
                    "weight": 2.5,
                }
            )

    # 3. Criar Nós de Memórias e mapear Tags para Ligações Sinápticas
    tag_to_mem_ids: Dict[str, List[str]] = {}
    for m in filtered_memories:
        m_id = f"mem:{m['id']}"
        ws = m.get("workspace", "global") or "global"
        imp = int(m.get("importance", 3) or 3)
        acc = int(m.get("access_count", 0) or 0)
        raw_tags = [
            t.strip().lower()
            for t in re.split(r"[\s,;]+", m.get("tags", "") or "")
            if len(t.strip()) >= 2
        ]

        node_ids.add(m_id)
        nodes.append(
            {
                "id": m_id,
                "db_id": m["id"],
                "label": m["topic"],
                "node_type": "memory",
                "workspace": ws,
                "category": m.get("category", "general") or "general",
                "tier": m.get("tier") or db.classify_memory_tier(
                    str(m.get("category", "")), str(m.get("topic", "")), str(m.get("fact", "")), str(m.get("tags", ""))
                ),
                "importance": imp,
                "access_count": acc,
                "val": 8 + imp * 2.2 + min(acc, 10) * 0.6,
                "fact": m["fact"],
                "tags": " ".join(raw_tags),
                "tag_list": raw_tags,
                "created_at": m.get("created_at", ""),
                "last_accessed": m.get("last_accessed", ""),
                "is_match": m["is_match"],
                "search_score": m["search_score"],
                "semantic_similarity": m.get("semantic_similarity", 0.85),
                "source_agent": m.get("source_agent", "system"),
                "trust_score": float(m.get("trust_score") or 0.85),
                "human_locked": int(m.get("human_locked") or 0),
            }
        )

        # Ligação ao Workspace Hub
        ws_node_id = f"ws:{ws}"
        if ws_node_id in node_ids:
            links.append(
                {
                    "source": ws_node_id,
                    "target": m_id,
                    "kind": "workspace_link",
                    "weight": 1.5,
                }
            )

        for t in raw_tags:
            tag_to_mem_ids.setdefault(t, []).append(m_id)

    # 3b. Ligações Causais Explícitas (Ruflo CausalMemoryGraph: fixed_by, evolves, supersedes)
    for ce in db.get_causal_edges():
        s_node = f"mem:{ce['source_id']}"
        t_node = f"mem:{ce['target_id']}"
        if s_node in node_ids and t_node in node_ids:
            links.append(
                {
                    "source": s_node,
                    "target": t_node,
                    "kind": "causal_link",
                    "relation": ce.get("relation", "evolves"),
                    "weight": float(ce.get("weight", 0.9)) * 2.4,
                }
            )

    # 4. Criar Ligações Sinápticas entre Memórias que partilham Tags/Conceitos específicos
    ignored_synapse_tags = {"file", "edit", "explicit", "auto_harvested", "global", "scratch", "brain_mcp"} | set(workspaces)
    pair_weights: Dict[Tuple[str, str], List[str]] = {}
    for tag, mem_list in tag_to_mem_ids.items():
        if len(mem_list) < 2 or len(mem_list) > 35 or tag in ignored_synapse_tags:
            continue
        for i in range(len(mem_list)):
            for j in range(i + 1, len(mem_list)):
                a, b = sorted((mem_list[i], mem_list[j]))
                pair_weights.setdefault((a, b), []).append(tag)

    # Ordenar pelas sinapses mais fortes e limitar grau sináptico por nó para evitar "hairball"
    sorted_pairs = sorted(pair_weights.items(), key=lambda kv: len(kv[1]), reverse=True)
    synapse_degree: Dict[str, int] = {}
    for (a, b), shared_tags in sorted_pairs:
        if synapse_degree.get(a, 0) >= 6 or synapse_degree.get(b, 0) >= 6:
            continue
        synapse_degree[a] = synapse_degree.get(a, 0) + 1
        synapse_degree[b] = synapse_degree.get(b, 0) + 1
        links.append(
            {
                "source": a,
                "target": b,
                "kind": "synaptic_link",
                "shared_tags": shared_tags,
                "weight": min(3.0, 0.8 + 0.5 * len(shared_tags)),
            }
        )

    # 5. Nós de #Tags (como no Obsidian Graph View quando "Tags" está ativo)
    if include_tags:
        for tag, mem_list in tag_to_mem_ids.items():
            if tag in ignored_synapse_tags:
                continue
            if 2 <= len(mem_list) <= 45:
                tag_node_id = f"tag:{tag}"
                node_ids.add(tag_node_id)
                nodes.append(
                    {
                        "id": tag_node_id,
                        "label": f"#{tag}",
                        "node_type": "tag",
                        "workspace": "global",
                        "category": "tag",
                        "importance": len(mem_list),
                        "val": 5 + min(len(mem_list) * 1.5, 8),
                        "fact": f"Tag semântica #{tag} associada a {len(mem_list)} memórias no Brain.",
                        "tags": tag,
                    }
                )
                for m_id in mem_list:
                    links.append(
                        {
                            "source": m_id,
                            "target": tag_node_id,
                            "kind": "tag_link",
                            "weight": 0.7,
                        }
                    )

    mcp_audit, plug_audit, is_lean = _get_cached_diet_audit()

    ws_counts: Dict[str, int] = {}
    for m in all_memories:
        w_key = m.get("workspace", "global") or "global"
        ws_counts[w_key] = ws_counts.get(w_key, 0) + 1
    all_ws = sorted(ws_counts.keys(), key=lambda k: (-ws_counts[k], k))
    all_cats = sorted({m.get("category", "general") or "general" for m in all_memories})

    result_payload = {
        "nodes": nodes,
        "links": links,
        "stats": db.get_stats(),
        "jev_router": db.jev_system1_route(query or "architecture", workspace_filter),
        "cow_branches": db.list_cow_branches(),
        "token_diet": {
            "is_lean": is_lean,
            "mcp_servers": mcp_audit,
            "plugins": plug_audit,
            "total_mcp_tokens_per_step": sum(x["header_tokens_per_step"] for x in mcp_audit),
        },
        "filters": {
            "workspaces": all_ws,
            "workspace_counts": ws_counts,
            "categories": all_cats,
        },
    }
    if len(_GRAPH_PAYLOAD_CACHE) > 24:
        _GRAPH_PAYLOAD_CACHE.clear()
    _GRAPH_PAYLOAD_CACHE[cache_key] = (now_ts, result_payload)
    return result_payload


_DIET_CACHE: Dict[str, Any] = {"ts": 0.0, "mcp": [], "plug": {}, "is_lean": False}


def _get_cached_diet_audit(force: bool = False) -> Tuple[List[Dict[str, Any]], Dict[str, Any], bool]:
    now = time.time()
    if force or not _DIET_CACHE["mcp"] or (now - _DIET_CACHE["ts"] > 120.0):
        mcp_audit = audit_mcp_servers()
        plug_audit = audit_plugins()
        enabled_mcps = [item for item in mcp_audit if item.get("enabled", True)]
        is_lean = all(item["in_lean_profile"] for item in enabled_mcps) and len(enabled_mcps) <= 3
        _DIET_CACHE["ts"] = now
        _DIET_CACHE["mcp"] = mcp_audit
        _DIET_CACHE["plug"] = plug_audit
        _DIET_CACHE["is_lean"] = is_lean
    return _DIET_CACHE["mcp"], _DIET_CACHE["plug"], _DIET_CACHE["is_lean"]


class BrainDashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        # Silenciar logs HTTP verbosos
        pass

    def _allowed_origin(self) -> str:
        origin = str(self.headers.get("Origin") or "").strip()
        if origin in ("http://127.0.0.1:8765", "http://localhost:8765", "http://127.0.0.1:3000", "http://localhost:3000"):
            return origin
        return "http://127.0.0.1:8765"

    def _is_trusted_local_origin(self) -> bool:
        origin = str(self.headers.get("Origin") or "").strip()
        if not origin:
            sec_site = str(self.headers.get("Sec-Fetch-Site") or "").strip().lower()
            return sec_site in ("", "same-origin", "none")
        return origin in ("http://127.0.0.1:8765", "http://localhost:8765", "http://127.0.0.1:3000", "http://localhost:3000")

    def _send_json(self, data: Any, status: int = 200) -> None:
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        etag = f'W/"{hashlib.md5(raw).hexdigest()[:16]}-{len(raw)}"'
        cors_origin = self._allowed_origin()
        if status == 200 and self.command in ("GET", "HEAD"):
            inm = self.headers.get("If-None-Match", "")
            if inm and inm == etag:
                self.send_response(304)
                self.send_header("ETag", etag)
                self.send_header("Access-Control-Allow-Origin", cors_origin)
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("X-Frame-Options", "DENY")
                self.end_headers()
                return
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("ETag", etag)
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", cors_origin)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(raw)

    def do_HEAD(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        cors_origin = self._allowed_origin()
        if parsed.path in ("/", "/index.html"):
            size = os.path.getsize(INDEX_HTML_PATH) if os.path.isfile(INDEX_HTML_PATH) else 0
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(size))
            self.send_header("Access-Control-Allow-Origin", cors_origin)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", cors_origin)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/health", "/api/health"):
            self._send_json({"status": "ok", "service": "antigravity-brain-v4.5"})
            return

        if parsed.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return

        if parsed.path in ("/", "/index.html"):
            if not os.path.isfile(INDEX_HTML_PATH):
                self._send_json({"error": "index.html not found"}, 404)
                return
            st = os.stat(INDEX_HTML_PATH)
            html_etag = f'W/"v7.1-carbon-{int(st.st_mtime)}-{st.st_size}"'
            if self.headers.get("If-None-Match", "") == html_etag:
                self.send_response(304)
                self.send_header("ETag", html_etag)
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("X-Frame-Options", "DENY")
                self.end_headers()
                return
            with open(INDEX_HTML_PATH, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("ETag", html_etag)
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(content)
            return

        if parsed.path in ("/favicon.ico", "/brain_app.ico", "/brain_app.png"):
            from brain_app import ensure_app_icons

            icons = ensure_app_icons()
            is_png = parsed.path.endswith(".png")
            f_path = icons["png"] if is_png else icons["ico"]
            if os.path.isfile(f_path):
                with open(f_path, "rb") as fh:
                    raw_bytes = fh.read()
                self.send_response(200)
                self.send_header("Content-Type", "image/png" if is_png else "image/x-icon")
                self.send_header("Cache-Control", "public, max-age=86400")
                self.send_header("Content-Length", str(len(raw_bytes)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(raw_bytes)
                return

        if parsed.path == "/manifest.json":
            manifest = {
                "name": "Antigravity Brain v5.0 — Neural OS & Prompt Forge",
                "short_name": "Brain OS",
                "start_url": "/?app=1#graph",
                "display": "standalone",
                "background_color": "#070a14",
                "theme_color": "#070a14",
                "icons": [
                    {"src": "/brain_app.png", "sizes": "256x256", "type": "image/png"},
                    {"src": "/favicon.ico", "sizes": "64x64 32x32 16x16", "type": "image/x-icon"},
                ],
            }
            self._send_json(manifest)
            return

        if parsed.path == "/api/graph":
            qs = urllib.parse.parse_qs(parsed.query)
            q = qs.get("q", [""])[0]
            ws = qs.get("workspace", ["all"])[0]
            cat = qs.get("category", ["all"])[0]
            inc_tags = qs.get("tags", ["1"])[0] != "0"
            db = BrainDB()
            payload = build_obsidian_graph_payload(
                db=db,
                query=q,
                workspace_filter=ws,
                category_filter=cat,
                include_tags=inc_tags,
            )
            self._send_json(payload)
            return

        if parsed.path == "/api/swarm":
            qs = urllib.parse.parse_qs(parsed.query)
            run_id_raw = qs.get("run_id", [""])[0]
            run_id = int(run_id_raw) if run_id_raw.isdigit() else None
            db = BrainDB()
            swarm = SwarmEngine(db)
            self._send_json(swarm.get_swarm_dashboard(run_id))
            return

        if parsed.path == "/api/swarm/diff":
            qs = urllib.parse.parse_qs(parsed.query)
            target_file = qs.get("file", ["index.html"])[0]
            db = BrainDB()
            swarm = SwarmEngine(db)
            self._send_json(swarm.get_file_git_diff(target_file))
            return

        if parsed.path == "/api/office":
            db = BrainDB()
            swarm = SwarmEngine(db)
            self._send_json(swarm.get_office_state())
            return

        if parsed.path in ("/api/inspector", "/api/inspector_preview"):
            from brain_inject import generate_inspector_preview

            qs = urllib.parse.parse_qs(parsed.query)
            ws = qs.get("workspace", ["brain_mcp"])[0]
            q = qs.get("q", [""])[0]
            sim_turn = int(qs.get("turn", ["1"])[0] or 1)
            db = BrainDB()
            self._send_json(generate_inspector_preview(db=db, workspace=ws, query=q, simulate_turn=sim_turn))
            return

        if parsed.path == "/api/export":
            qs = urllib.parse.parse_qs(parsed.query)
            ws = qs.get("workspace", ["all"])[0]
            db = BrainDB()
            self._send_json(db.export_brain_pack(workspace_filter=ws))
            return

        if parsed.path == "/api/update":
            self._send_json(get_git_status())
            return

        if parsed.path == "/api/symbol":
            qs = urllib.parse.parse_qs(parsed.query)
            q = qs.get("q", [""])[0]
            swarm = SwarmEngine(BrainDB())
            self._send_json(swarm.lookup_symbol(symbol_query=q, workspace_path=CURRENT_DIR))
            return

        if parsed.path == "/api/impact":
            qs = urllib.parse.parse_qs(parsed.query)
            target = qs.get("target", [""])[0]
            swarm = SwarmEngine(BrainDB())
            self._send_json(swarm.analyze_impact_graph(target=target, workspace_path=CURRENT_DIR))
            return

        if parsed.path == "/api/diet/prune":
            qs = urllib.parse.parse_qs(parsed.query)
            q = qs.get("q", ["otimizar codigo python"])[0]
            ws = qs.get("workspace", ["global"])[0]
            self._send_json(prune_tools_for_intent(user_query=q, workspace=ws))
            return

        if parsed.path == "/api/swarm/sandbox":
            swarm = SwarmEngine(BrainDB())
            self._send_json(swarm.manage_subagent_sandbox(action="list", workspace_path=CURRENT_DIR))
            return

        if parsed.path == "/api/ast/watch":
            qs = urllib.parse.parse_qs(parsed.query)
            limit = int(qs.get("limit", ["10"])[0] or 10)
            watcher = get_global_watcher(CURRENT_DIR)
            self._send_json(watcher.get_watcher_status(limit=limit))
            return

        if parsed.path == "/api/ast/graphify":
            qs = urllib.parse.parse_qs(parsed.query)
            force = qs.get("force", ["0"])[0] == "1"
            swarm = SwarmEngine(BrainDB())
            kg = swarm.build_codebase_knowledge_graph(workspace_path=CURRENT_DIR, force_rebuild=force)
            self._send_json(
                {
                    "ok": True,
                    "build_latency_ms": kg["build_latency_ms"],
                    "total_nodes": kg["total_nodes"],
                    "total_edges": kg["total_edges"],
                    "node_type_counts": kg["node_type_counts"],
                    "confidence_counts": kg["confidence_counts"],
                    "god_nodes": kg["god_nodes"],
                    "communities": kg["communities"],
                    "token_telemetry": kg["token_telemetry"],
                }
            )
            return

        if parsed.path == "/api/ast/path":
            qs = urllib.parse.parse_qs(parsed.query)
            src = qs.get("source", ["triggerAstSaveAuditUI"])[0]
            tgt = qs.get("target", ["ast_save_audits"])[0]
            hops = int(qs.get("max_hops", ["6"])[0] or 6)
            swarm = SwarmEngine(BrainDB())
            self._send_json(
                swarm.find_graph_path(
                    source_query=src,
                    target_query=tgt,
                    max_hops=hops,
                    workspace_path=CURRENT_DIR,
                )
            )
            return

        if parsed.path == "/api/orbit/overview":
            qs = urllib.parse.parse_qs(parsed.query)
            ws_param = qs.get("workspace", ["all"])[0] or "all"
            orbit = _get_fresh_orbit_engine(BrainDB())
            self._send_json(orbit.get_executive_briefing_and_roi(workspace=ws_param))
            return

        if parsed.path == "/api/orbit/inbox":
            orbit = _get_fresh_orbit_engine(BrainDB())
            self._send_json(orbit.get_mission_control_inbox())
            return

        if parsed.path == "/api/memories/revisions":
            qs = urllib.parse.parse_qs(parsed.query)
            mid_raw = qs.get("memory_id", [""])[0]
            mid = int(mid_raw) if mid_raw.isdigit() else None
            db = BrainDB()
            self._send_json({"ok": True, "revisions": db.get_memory_revisions(memory_id=mid, limit=25)})
            return

        if parsed.path == "/api/events":
            db = BrainDB()
            stats = db.get_stats()
            with db._connect() as conn:
                try:
                    ag_cnt = conn.execute("SELECT COUNT(*) as c FROM office_agents;").fetchone()["c"]
                except Exception:
                    ag_cnt = 8
            payload = json.dumps(
                {
                    "type": "brain_sse_heartbeat",
                    "timestamp": int(time.time() * 1000),
                    "total_memories": stats.get("total_memories", 0),
                    "tokens_saved": stats.get("estimated_saved_tokens", 0),
                    "active_agents": int(ag_cnt or 8),
                },
                ensure_ascii=False,
            )
            body_bytes = f"retry: 25000\nevent: brain_state\ndata: {payload}\n\n".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.send_header("Access-Control-Allow-Origin", self._allowed_origin())
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(body_bytes)))
            self.end_headers()
            self.wfile.write(body_bytes)
            return

        self._send_json({"error": "Not found"}, 404)

    def do_POST(self) -> None:
        if not self._is_trusted_local_origin():
            self._send_json({"error": "Origem cruzada não autorizada (CSRF Protection)"}, 403)
            return
        parsed = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0) or 0)
        body_raw = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        try:
            body = json.loads(body_raw) if body_raw else {}
        except json.JSONDecodeError:
            body = {}

        db = BrainDB()
        _GRAPH_PAYLOAD_CACHE.clear()

        if parsed.path == "/api/memories":
            topic = str(body.get("topic", "")).strip()
            fact = str(body.get("fact", "")).strip()
            workspace = str(body.get("workspace", "global")).strip() or "global"
            category = str(body.get("category", "general")).strip() or "general"
            tags = str(body.get("tags", "")).strip()
            importance = int(body.get("importance", 4) or 4)
            mem_id = body.get("id")

            if not topic or not fact:
                self._send_json({"error": "Tópico e facto são obrigatórios."}, 400)
                return

            if mem_id:
                with db._connect() as conn:
                    conn.execute(
                        """
                        UPDATE memories
                        SET topic = ?, fact = ?, workspace = ?, category = ?, tags = ?, importance = ?,
                            source_agent = 'human_ui', trust_score = 1.0, human_locked = 1,
                            last_accessed = CURRENT_TIMESTAMP
                        WHERE id = ?;
                        """,
                        (topic, fact, workspace.lower(), category.lower(), tags, importance, int(mem_id)),
                    )
                self._send_json({"ok": True, "id": int(mem_id), "updated": True, "human_locked": 1})
            else:
                row_id, is_new = db.store_fact(
                    topic=topic,
                    fact=fact,
                    workspace=workspace,
                    category=category,
                    tags=tags,
                    importance=importance,
                    source_agent="human_ui",
                    trust_score=1.0,
                    human_locked=1,
                )
                self._send_json({"ok": True, "id": row_id, "is_new": is_new, "human_locked": 1})
            return

        if parsed.path == "/api/sync":
            res = harvest_all_workspace_context(db)
            self._send_json({"ok": True, **res})
            return

        if parsed.path == "/api/profile":
            mode = str(body.get("mode", "lean")).strip()
            if mode not in ("lean", "full"):
                self._send_json({"error": "Modo inválido"}, 400)
                return
            msg = switch_mcp_profile(mode)
            _get_cached_diet_audit(force=True)
            self._send_json({"ok": True, "message": msg, "mode": mode})
            return

        if parsed.path == "/api/swarm/start":
            goal = str(body.get("goal", "")).strip() or "ship v2.4: Scout Shared Map + Asymmetric Swarm Run"
            ws_path = str(body.get("workspace_path", "")).strip() or CURRENT_DIR
            animate = bool(body.get("animate_live", True))
            mode = str(body.get("mode", "full")).strip() or "full"
            swarm = SwarmEngine(db)
            dash = swarm.start_live_swarm_run(
                goal=goal, workspace_path=ws_path, animate_live=animate, mode=mode
            )
            self._send_json({"ok": True, **dash})
            return

        if parsed.path == "/api/swarm/scout":
            ws_path = str(body.get("workspace_path", "")).strip() or CURRENT_DIR
            swarm = SwarmEngine(db)
            scout_res = swarm.run_codebase_scout_and_persist(ws_path)
            self._send_json({"ok": True, "scout": scout_res, "dashboard": swarm.get_swarm_dashboard()})
            return

        if parsed.path == "/api/swarm/action":
            action = str(body.get("action", "verify_all")).strip()
            lane = str(body.get("lane", "")).strip()
            run_id_raw = body.get("run_id")
            run_id = int(run_id_raw) if str(run_id_raw or "").isdigit() else None
            ws_path = str(body.get("workspace_path", "")).strip() or CURRENT_DIR
            mode = str(body.get("mode", "full")).strip()
            swarm = SwarmEngine(db)
            dash = swarm.execute_swarm_action(
                action=action, lane=lane, run_id=run_id, workspace_path=ws_path, mode=mode
            )
            self._send_json({"ok": True, **dash})
            return

        if parsed.path == "/api/swarm/task":
            task_code = str(body.get("task_code", "")).strip()
            status = str(body.get("status", "done")).strip()
            progress = int(body.get("progress", 100))
            summary = str(body.get("summary", "")).strip()
            swarm = SwarmEngine(db)
            dash = swarm.update_task_status(task_code=task_code, status=status, progress=progress, summary=summary)
            self._send_json({"ok": True, **dash})
            return

        if parsed.path == "/api/office/team_action":
            action = str(body.get("action", "work_all")).strip()
            swarm = SwarmEngine(db)
            state = swarm.execute_office_team_action(action=action)
            self._send_json({"ok": True, **state})
            return

        if parsed.path == "/api/office/spawn":
            name = str(body.get("name", "")).strip()
            role = str(body.get("role", "Agente de Conversa")).strip()
            model = str(body.get("model", "Gemini 4 Argon")).strip()
            workspace = str(body.get("workspace", "brain_mcp")).strip()
            task = str(body.get("task", "Nova conversa iniciada no Antigravity")).strip()
            status = str(body.get("status", "working")).strip()
            swarm = SwarmEngine(db)
            state = swarm.spawn_custom_office_agent(
                name=name,
                role=role,
                model=model,
                workspace=workspace,
                task=task,
                status=status,
            )
            self._send_json({"ok": True, **state})
            return

        if parsed.path == "/api/office/toggle":
            agent_id = str(body.get("agent_id", "")).strip()
            target_status = body.get("status")
            swarm = SwarmEngine(db)
            state = swarm.toggle_office_agent_status(agent_id=agent_id, target_status=target_status)
            self._send_json({"ok": True, **state})
            return

        if parsed.path == "/api/office/command":
            agent_id = str(body.get("agent_id", "")).strip()
            directive = str(body.get("directive", "")).strip()
            workspace = str(body.get("workspace", "brain_mcp")).strip()
            swarm = SwarmEngine(db)
            state = swarm.assign_office_agent_directive(
                agent_id=agent_id, directive=directive, workspace=workspace
            )
            self._send_json({"ok": True, **state})
            return

        if parsed.path == "/api/memories/pin":
            mem_id = int(body.get("id", 0) or 0)
            res = db.toggle_pin_memory(mem_id)
            self._send_json(res)
            return

        if parsed.path in ("/api/doctor", "/api/memories/doctor"):
            res = db.run_memory_doctor()
            self._send_json(res)
            return

        if parsed.path == "/api/memories/bulk":
            action = str(body.get("action", "")).strip()
            ids = body.get("memory_ids") or body.get("ids") or []
            target_ws = str(body.get("target_workspace") or body.get("workspace") or "global").strip() or "global"
            res = db.bulk_manage_memories(action=action, memory_ids=ids, target_workspace=target_ws)
            self._send_json(res)
            return

        if parsed.path == "/api/memories/rollback":
            rev_id = int(body.get("revision_id") or body.get("id") or 0)
            res = db.rollback_memory(revision_id=rev_id)
            self._send_json(res, 200 if res.get("ok") else 400)
            return

        if parsed.path == "/api/cow_branch":
            lbl = str(body.get("label", "")).strip()
            ws_b = str(body.get("workspace", "all")).strip() or "all"
            res = db.create_cow_branch(label=lbl, workspace=ws_b)
            self._send_json(res)
            return

        if parsed.path == "/api/import":
            res = db.import_brain_pack(body)
            self._send_json(res)
            return

        if parsed.path == "/api/mcp/toggle":
            srv = str(body.get("server", "")).strip()
            res = toggle_single_mcp_server(srv)
            _get_cached_diet_audit(force=True)
            swarm = SwarmEngine(db)
            self._send_json({**res, "office": swarm.get_office_state()})
            return

        if parsed.path == "/api/update":
            res = check_and_apply_update(force_fetch=True)
            self._send_json({"ok": True, **res})
            return

        if parsed.path == "/api/swarm/sandbox":
            action = str(body.get("action", "create")).strip()
            lane = str(body.get("lane", "API")).strip()
            task_code = str(body.get("task_code", "api-01")).strip()
            raw_files = body.get("target_files", [])
            if isinstance(raw_files, str):
                target_files = [f.strip() for f in raw_files.split(",") if f.strip()]
            elif isinstance(raw_files, list):
                target_files = [str(f).strip() for f in raw_files if str(f).strip()]
            else:
                target_files = []
            sandbox_id_raw = body.get("sandbox_id")
            sandbox_id = int(sandbox_id_raw) if str(sandbox_id_raw or "").isdigit() else None
            swarm = SwarmEngine(db)
            res = swarm.manage_subagent_sandbox(
                action=action,
                lane=lane,
                task_code=task_code,
                target_files=target_files,
                sandbox_id=sandbox_id,
                workspace_path=CURRENT_DIR,
            )
            self._send_json(res)
            return

        if parsed.path == "/api/ast/watch":
            target_file = str(body.get("file", "")).strip()
            force_flag = bool(body.get("force", True))
            watcher = get_global_watcher(CURRENT_DIR)
            if target_file:
                res = watcher.audit_file_save(
                    file_path=target_file,
                    workspace_path=CURRENT_DIR,
                    force=force_flag,
                )
            else:
                res = watcher.scan_workspace_saves(
                    workspace_path=CURRENT_DIR,
                    force_all=force_flag,
                )
            self._send_json({**res, "status": watcher.get_watcher_status(limit=10)})
            return

        if parsed.path == "/api/ast/report":
            write_disk = bool(body.get("write_to_disk", True))
            swarm = SwarmEngine(db)
            rep = swarm.generate_architecture_report(
                workspace_path=CURRENT_DIR, write_to_disk=write_disk
            )
            self._send_json(rep)
            return

        if parsed.path == "/api/orbit/action":
            action = str(body.get("action", "")).strip()
            orbit = _get_fresh_orbit_engine(db)
            if action == "approve_item":
                item_id = int(body.get("id", 0) or 0)
                res = orbit.approve_inbox_item(item_id=item_id, workspace_path=CURRENT_DIR)
            elif action == "approve_all":
                res = orbit.approve_all_inbox(workspace_path=CURRENT_DIR)
            elif action == "redirect_item":
                item_id = int(body.get("id", 0) or 0)
                note = str(body.get("redirect_note", "")).strip()
                res = orbit.redirect_inbox_item(item_id=item_id, redirect_note=note)
            elif action == "broadcast":
                scope = str(body.get("target_scope", "all_fleet")).strip() or "all_fleet"
                directive = str(body.get("directive", "")).strip()
                ws = str(body.get("workspace", "brain_mcp")).strip() or "brain_mcp"
                res = orbit.send_broadcast(target_scope=scope, directive=directive, workspace=ws)
            elif action == "record_handoff":
                res = orbit.record_handoff(
                    from_agent=str(body.get("from_agent", "Arquiteto (Brain)")),
                    to_agent=str(body.get("to_agent", "Worker UI (Flash)")),
                    task_code=str(body.get("task_code", "orbit-01")),
                    workspace=str(body.get("workspace", "brain_mcp")),
                    summary=str(body.get("summary", "")),
                    files_touched=body.get("files_touched", []),
                    next_action=str(body.get("next_action", "")),
                )
            elif action == "connect_mcp_bridge":
                targets = body.get("targets")
                res = orbit.connect_all_ai_tools(target_ids=targets if isinstance(targets, list) else None)
            elif action in ("dot_ready", "dot_create", "dot_claim", "dot_complete", "dot_reopen", "dot_sync_md"):
                sub_act = action.replace("dot_", "")
                deps_raw = body.get("depends_on") or []
                if isinstance(deps_raw, str):
                    deps_list = [x.strip() for x in deps_raw.split(",") if x.strip()]
                elif isinstance(deps_raw, list):
                    deps_list = [str(x).strip() for x in deps_raw if str(x).strip()]
                else:
                    deps_list = []
                dot_res = orbit.manage_dot_task(
                    action=sub_act,
                    dot_id=str(body.get("dot_id", "")),
                    title=str(body.get("title", "")),
                    workspace=str(body.get("workspace", "brain_mcp")),
                    lane=str(body.get("lane", "API")),
                    depends_on=deps_list,
                    agent_id=str(body.get("agent_id", "arch-01")),
                    assignee=str(body.get("assignee", "")),
                    close_reason=str(body.get("close_reason", "")),
                    priority=int(body.get("priority", 4) or 4),
                    summary=str(body.get("summary", "")),
                )
                res = {**dot_res, "dot": dot_res}
            elif action == "self_learn_status":
                ws = str(body.get("workspace", "brain_mcp"))
                sl_res = orbit.get_self_learn_status(workspace=ws)
                res = {**sl_res, "self_learn": sl_res}
            elif action == "self_learn_toggle":
                ws = str(body.get("workspace", "brain_mcp"))
                en_val = body.get("enabled")
                pro_val = body.get("proactive_enabled")
                sl_res = orbit.toggle_project_self_learn(
                    workspace=ws,
                    enabled=bool(en_val) if en_val is not None else None,
                    proactive_enabled=bool(pro_val) if pro_val is not None else None,
                )
                res = {**sl_res, "self_learn": sl_res}
            elif action == "self_learn_evolve":
                ws = str(body.get("workspace", "brain_mcp"))
                force_flag = bool(body.get("force", False))
                sl_res = orbit.run_self_learn_evolution_cycle(workspace=ws, force=force_flag)
                res = {**sl_res, "self_learn": sl_res.get("self_learn")}
            elif action in ("self_learn_enable_all", "self_learn_evolve_all"):
                ws = str(body.get("workspace", "brain_mcp"))
                sl_res = orbit.enable_and_evolve_all_projects(workspace=ws)
                res = {**sl_res, "self_learn": sl_res.get("self_learn")}
            elif action == "forge_prompt":
                ws = str(body.get("workspace", "brain_mcp"))
                raw_req = str(body.get("raw_request", ""))
                t_mode = str(body.get("task_mode", "feature"))
                lang_val = str(body.get("lang", "pt-PT"))
                sel_sk = body.get("selected_skills")
                sel_list = [str(x).strip() for x in sel_sk if str(x).strip()] if isinstance(sel_sk, list) else None
                pf_res = orbit.generate_optimized_prompt(
                    raw_request=raw_req,
                    workspace=ws,
                    task_mode=t_mode,
                    selected_skills=sel_list,
                    lang=lang_val,
                )
                res = {**pf_res, "prompt_forge": pf_res}
            elif action == "prompt_history":
                ws = str(body.get("workspace", "all"))
                hist = orbit.get_prompt_forge_history(workspace=ws, limit=10)
                res = {"ok": True, "history": hist}
            elif action == "vault_overview":
                ws = str(body.get("workspace", "brain_mcp"))
                res = orbit.get_vault_studio_overview(workspace=ws)
            elif action == "vault_defuddle":
                ws = str(body.get("workspace", "brain_mcp"))
                raw_in = str(body.get("raw_input", ""))
                title_in = str(body.get("title", ""))
                save_flag = bool(body.get("save_to_vault", True))
                df_res = orbit.defuddle_content(
                    raw_input=raw_in,
                    workspace=ws,
                    title=title_in,
                    save_to_vault=save_flag,
                )
                res = {**df_res, "vault_studio": orbit.get_vault_studio_overview(workspace=ws)}
            elif action == "vault_sync":
                ws = str(body.get("workspace", "brain_mcp"))
                vs_res = orbit.sync_markdown_vault(workspace=ws)
                res = {**vs_res, "vault_studio": vs_res}
            elif action == "vault_read_note":
                ws = str(body.get("workspace", "brain_mcp"))
                fn = str(body.get("filename", "atlas.md"))
                res = orbit.read_vault_note(workspace=ws, filename=fn)
            elif action == "vault_save_note":
                ws = str(body.get("workspace", "brain_mcp"))
                fn = str(body.get("filename", "atlas.md"))
                cnt = str(body.get("content", ""))
                res = orbit.save_vault_note(workspace=ws, filename=fn, content=cnt, sync_to_db=True)
            elif action == "global_brain_synthesize":
                ws = str(body.get("workspace", "brain_mcp"))
                scan_tr = bool(body.get("scan_transcripts", True))
                gb_res = orbit.synthesize_global_meta_brain(scan_transcripts=scan_tr)
                res = {**gb_res, "global_brain": gb_res, "self_learn": orbit.get_self_learn_status(workspace=ws)}
            elif action == "self_learn_resolve_conflicts":
                ws = str(body.get("workspace", "global"))
                rc_res = orbit.resolve_global_rule_conflicts(workspace=ws)
                res = {**rc_res, "self_learn": orbit.get_self_learn_status(workspace=ws)}
            elif action == "file_edit_gc":
                max_pw = int(body.get("max_per_workspace", 2) or 2)
                res = orbit.compact_redundant_file_edits(max_per_workspace=max_pw)
            elif action == "quota_5h_radar":
                res = orbit.get_5h_quota_radar()
            elif action == "vault_inject_repo_agents":
                ws = str(body.get("workspace", "brain_mcp"))
                repo_p = str(body.get("repo_path", ""))
                res = orbit.inject_rules_into_repo_agents_md(workspace=ws, repo_path=repo_p)
            elif action == "synthesize_bug_tests":
                ws = str(body.get("workspace", "brain_mcp"))
                res = orbit.synthesize_regression_tests_from_bugs(workspace=ws)
            else:
                self._send_json({"ok": False, "error": f"Ação Orbit desconhecida: {action}"}, 400)
                return
            req_ws = str(body.get("workspace", "all"))
            self._send_json({**res, "overview": orbit.get_executive_briefing_and_roi(workspace=req_ws)})
            return

        if parsed.path == "/api/app/launch":
            from brain_app import ensure_desktop_shortcuts, launch_native_app_window

            act = str(body.get("action", "open_window")).strip().lower()
            sec = str(body.get("section", "graph")).strip().lower()
            if act == "open_spotlight":
                pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
                if not os.path.isfile(pyw):
                    pyw = sys.executable
                subprocess.Popen(
                    [pyw, os.path.join(CURRENT_DIR, "brain_app.py"), "--spotlight"],
                    cwd=CURRENT_DIR,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=0x08000000 if os.name == "nt" else 0,
                )
                self._send_json({"ok": True, "action": "open_spotlight"})
                return
            if act == "create_shortcut":
                sc_res = ensure_desktop_shortcuts()
                self._send_json(sc_res)
                return
            win_res = launch_native_app_window(section=sec)
            self._send_json(win_res)
            return

        self._send_json({"error": "Endpoint desconhecido"}, 404)

    def do_DELETE(self) -> None:
        _GRAPH_PAYLOAD_CACHE.clear()
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith("/api/memories/"):
            mem_id = parsed.path.split("/")[-1]
            db = BrainDB()
            deleted = db.forget_fact(mem_id)
            self._send_json({"ok": deleted})
            return
        self._send_json({"error": "Not found"}, 404)


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def start_self_learn_sentinel_daemon(interval_seconds: float = 90.0) -> None:
    """
    Task de Auto-Aprendizagem Recursiva & Sentinel Proativo em background ('1 task running'):
    Ronda periodicamente todos os projetos onde o utilizador ativou 'enabled = 1' e executa
    consolidação de Meta-Regras, reforço sináptico Hebbiano e deteção proativa a 0 tokens LLM.
    """
    import threading

    def _sentinel_worker() -> None:
        first_boot = True
        while True:
            time.sleep(3.0 if first_boot else max(15.0, float(interval_seconds)))
            first_boot = False
            try:
                orb = _get_fresh_orbit_engine(BrainDB())
                st = orb.get_self_learn_status("brain_mcp")
                for proj in st.get("projects", []):
                    if proj.get("enabled"):
                        orb.run_self_learn_evolution_cycle(workspace=str(proj["workspace"]), force=False)
            except Exception:
                pass

    t = threading.Thread(target=_sentinel_worker, name="BrainSelfLearnSentinel", daemon=True)
    t.start()


def start_code_mtime_watchdog_daemon(interval_seconds: float = 4.0) -> None:
    """
    Deteta automaticamente quando ficheiros .py são atualizados no disco (ex: git pull externo num PC remoto)
    e reinicia o processo web_dashboard.py em memória para evitar 'Ação Orbit desconhecida'.
    """
    import threading

    this_file = os.path.abspath(__file__)
    initial_mtime = os.path.getmtime(this_file) if os.path.isfile(this_file) else 0.0

    def _watchdog() -> None:
        while True:
            time.sleep(max(2.5, float(interval_seconds)))
            try:
                if os.path.isfile(this_file):
                    cur_m = os.path.getmtime(this_file)
                    if initial_mtime > 0 and cur_m > initial_mtime + 0.5:
                        _schedule_server_hot_reload()
                        return
            except Exception:
                pass

    t = threading.Thread(target=_watchdog, name="BrainCodeMtimeWatchdog", daemon=True)
    t.start()


def run_server(port: int = PORT, host: str = "127.0.0.1") -> None:
    import threading

    if getattr(sys, "stdout", None) is not None and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    # Bind socket immediately so the dev server port is ready in <10ms
    server = ReusableThreadingHTTPServer((host, port), BrainDashboardHandler)

    def _bg_sync() -> None:
        try:
            kill_other_dashboard_processes(exclude_pid=os.getpid())
            db = BrainDB()
            sync_info = harvest_all_workspace_context(db)
            SwarmEngine(db).ensure_default_run()
            start_auto_update_daemon(interval_seconds=300)
            start_code_mtime_watchdog_daemon(interval_seconds=4.0)
            start_ast_impact_watcher_daemon(workspace_path=CURRENT_DIR, interval_seconds=2.0)
            start_self_learn_sentinel_daemon(interval_seconds=90.0)
            if getattr(sys, "stdout", None) is not None:
                print(f"   Sincronizacao inicial concluida: {sync_info}", flush=True)
        except Exception:
            pass

    threading.Thread(target=_bg_sync, daemon=True).start()
    try:
        if getattr(sys, "stdout", None) is not None:
            print(f"Obsidian Brain Graph Web Server ativo em: http://{host}:{port}", flush=True)
    except Exception:
        pass
    server.serve_forever()


if __name__ == "__main__":
    env_port = int(os.environ.get("PORT", PORT))
    env_host = os.environ.get("HOST", "127.0.0.1")
    run_server(port=env_port, host=env_host)


