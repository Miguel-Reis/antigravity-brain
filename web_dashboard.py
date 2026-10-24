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

from auto_updater import check_and_apply_update, get_git_status, start_auto_update_daemon
from brain_harvest import harvest_latest_turn
from db_engine import BrainDB, seed_initial_memories
from swarm_engine import SwarmEngine
from token_diet import (
    audit_mcp_servers,
    audit_plugins,
    switch_mcp_profile,
    toggle_single_mcp_server,
)

PORT = 8765
INDEX_HTML_PATH = os.path.join(CURRENT_DIR, "index.html")
BRAIN_LOGS_ROOT = os.path.expanduser("~/.gemini/antigravity/brain")
SCRATCH_ROOT = os.path.expanduser("~/.gemini/antigravity/scratch")


def harvest_all_workspace_context(db: BrainDB) -> Dict[str, int]:
    """Popula o Brain com memórias reais das conversas e projetos da máquina."""
    added_memories = seed_initial_memories(db)
    harvested_turns = 0

    # 1. Enriquecer memórias do motor Brain v2 + descobrir projetos em SCRATCH_ROOT
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
            "Servidor web local na porta 8765 (http://127.0.0.1:8765) com visualização de grafo interativo estilo Obsidian, monitor Asymmetric Swarm (#swarm), pesquisa FTS5 BM25 em tempo real e Auto-Updater Git.",
            "brain_mcp",
            "architecture",
            "obsidian graph web_dashboard ui swarm visualizacao fts5",
            5,
        ),
    ]
    for topic, fact, ws, cat, tags, imp in project_facts:
        _, is_new = db.store_fact(
            topic=topic, fact=fact, workspace=ws, category=cat, tags=tags, importance=imp
        )
        if is_new:
            added_memories += 1

    if os.path.isdir(SCRATCH_ROOT):
        for entry in sorted(os.listdir(SCRATCH_ROOT)):
            full_p = os.path.join(SCRATCH_ROOT, entry)
            if os.path.isdir(full_p) and not entry.startswith("."):
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
                                    target = (
                                        args.get("TargetFile")
                                        or args.get("Path")
                                        or args.get("AbsolutePath")
                                        or ""
                                    )
                                    if target and (".gemini/antigravity/brain" not in target.replace("\\", "/")):
                                        base_f = os.path.basename(target.rstrip("/\\"))
                                        if any(
                                            k in base_f.lower()
                                            for k in ("check_", "tmp_", "run_office_sim")
                                        ):
                                            continue
                                        file_ws = db.normalize_workspace(os.path.dirname(target))
                                        ext = os.path.splitext(base_f)[1].lstrip(".").lower() or "file"
                                        _, is_new = db.store_fact(
                                            topic=f"Ficheiro {base_f} ({file_ws})",
                                            fact=f"Ficheiro do projeto {file_ws} em {target.replace(chr(92), '/')} (modificado via {t_name}).",
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


def build_obsidian_graph_payload(
    db: BrainDB,
    query: str = "",
    workspace_filter: str = "all",
    category_filter: str = "all",
    include_tags: bool = True,
) -> Dict[str, Any]:
    """Constrói a estrutura de nós e ligações sinápticas (estilo Obsidian Graph View)."""
    with db._connect() as conn:
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

    # Se houver query de pesquisa FTS5, identificar os IDs com match e respetivos scores
    matched_scores: Dict[int, float] = {}
    if query.strip():
        search_res = db.search_memories(
            query=query.strip(), workspace="global", n_results=30, update_stats=False
        )
        for r in search_res:
            matched_scores[int(r["id"])] = round(float(r.get("final_score", 1.0)), 2)

    # Filtrar memórias
    filtered_memories: List[Dict[str, Any]] = []
    for m in all_memories:
        if workspace_filter != "all" and m.get("workspace") != workspace_filter:
            continue
        if category_filter != "all" and m.get("category") != category_filter:
            continue
        m["is_match"] = (int(m["id"]) in matched_scores) if query.strip() else False
        m["search_score"] = matched_scores.get(int(m["id"]), 0.0)
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

    all_ws = sorted({m.get("workspace", "global") or "global" for m in all_memories})
    all_cats = sorted({m.get("category", "general") or "general" for m in all_memories})

    return {
        "nodes": nodes,
        "links": links,
        "stats": db.get_stats(),
        "token_diet": {
            "is_lean": is_lean,
            "mcp_servers": mcp_audit,
            "plugins": plug_audit,
            "total_mcp_tokens_per_step": sum(x["header_tokens_per_step"] for x in mcp_audit),
        },
        "filters": {
            "workspaces": all_ws,
            "categories": all_cats,
        },
    }


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

    def _send_json(self, data: Any, status: int = 200) -> None:
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        etag = f'W/"{hashlib.md5(raw).hexdigest()[:16]}-{len(raw)}"'
        if status == 200 and self.command == "GET":
            inm = self.headers.get("If-None-Match", "")
            if inm and inm == etag:
                self.send_response(304)
                self.send_header("ETag", etag)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                return
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("ETag", etag)
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            if not os.path.isfile(INDEX_HTML_PATH):
                self._send_json({"error": "index.html not found"}, 404)
                return
            with open(INDEX_HTML_PATH, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
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

        if parsed.path == "/api/inspector":
            from brain_inject import generate_inspector_preview

            qs = urllib.parse.parse_qs(parsed.query)
            ws = qs.get("workspace", ["brain_mcp"])[0]
            q = qs.get("q", [""])[0]
            db = BrainDB()
            self._send_json(generate_inspector_preview(db=db, workspace=ws, query=q))
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

        self._send_json({"error": "Not found"}, 404)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0) or 0)
        body_raw = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        try:
            body = json.loads(body_raw) if body_raw else {}
        except json.JSONDecodeError:
            body = {}

        db = BrainDB()

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
                        SET topic = ?, fact = ?, workspace = ?, category = ?, tags = ?, importance = ?, last_accessed = CURRENT_TIMESTAMP
                        WHERE id = ?;
                        """,
                        (topic, fact, workspace.lower(), category.lower(), tags, importance, int(mem_id)),
                    )
                self._send_json({"ok": True, "id": int(mem_id), "updated": True})
            else:
                row_id, is_new = db.store_fact(
                    topic=topic,
                    fact=fact,
                    workspace=workspace,
                    category=category,
                    tags=tags,
                    importance=importance,
                )
                self._send_json({"ok": True, "id": row_id, "is_new": is_new})
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

        if parsed.path == "/api/doctor":
            res = db.run_memory_doctor()
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

        self._send_json({"error": "Endpoint desconhecido"}, 404)

    def do_DELETE(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith("/api/memories/"):
            mem_id = parsed.path.split("/")[-1]
            db = BrainDB()
            deleted = db.forget_fact(mem_id)
            self._send_json({"ok": deleted})
            return
        self._send_json({"error": "Not found"}, 404)


def run_server(port: int = PORT) -> None:
    import threading

    if getattr(sys, "stdout", None) is not None and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    db = BrainDB()
    server = ThreadingHTTPServer(("127.0.0.1", port), BrainDashboardHandler)

    def _bg_sync() -> None:
        try:
            sync_info = harvest_all_workspace_context(BrainDB())
            SwarmEngine(BrainDB()).ensure_default_run()
            if getattr(sys, "stdout", None) is not None:
                print(f"   Sincronizacao inicial concluida: {sync_info}")
        except Exception:
            pass

    threading.Thread(target=_bg_sync, daemon=True).start()
    start_auto_update_daemon(interval_seconds=1800)
    try:
        if getattr(sys, "stdout", None) is not None:
            print(f"Obsidian Brain Graph Web Server ativo em: http://127.0.0.1:{port}")
    except Exception:
        pass
    server.serve_forever()


if __name__ == "__main__":
    run_server()

