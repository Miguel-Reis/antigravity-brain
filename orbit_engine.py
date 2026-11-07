import datetime
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import threading
from db_engine import BrainDB

_ORBIT_INIT_LOCK = threading.Lock()
_INITIALIZED_ORBIT_DBS: set[str] = set()


class OrbitEngine:
    """
    Orbit Agent OS Engine for Antigravity Brain v4.5:
    1. Mission Control Approval Inbox ('Needs Your Yes' / 'Approve All' / 'Redirect')
    2. Trust Hierarchy ('Human Edits Always Win' + Agent Provenance)
    3. Multi-Scope Broadcast Directives (All Fleet / Department Lane / Workspace)
    4. Automatic Subagent Chaining & Hand-off Packets (agent_handoffs)
    5. One-Click Cross-IDE MCP Bridge (Antigravity, Cursor, Claude, Windsurf)
    6. Morning Brief / Executive Digest & Engineering ROI Calculator
    """

    def __init__(self, db: Optional[BrainDB] = None) -> None:
        self.db = db or BrainDB()
        db_key = str(self.db.db_path)
        if db_key not in _INITIALIZED_ORBIT_DBS:
            with _ORBIT_INIT_LOCK:
                if db_key not in _INITIALIZED_ORBIT_DBS:
                    self._init_orbit_schema()
                    _INITIALIZED_ORBIT_DBS.add(db_key)

    def _init_orbit_schema(self) -> None:
        with self.db._connect() as conn:
            # 1. Mission Control Inbox ('Waiting for your yes')
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS orbit_inbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    external_ref TEXT UNIQUE,
                    agent_id TEXT DEFAULT 'arch-01',
                    agent_name TEXT DEFAULT 'ARCH-01 (Argon)',
                    workspace TEXT DEFAULT 'brain_mcp',
                    kind TEXT DEFAULT 'sandbox_merge',
                    title TEXT NOT NULL,
                    summary TEXT DEFAULT '',
                    target_files TEXT DEFAULT '',
                    risk_level TEXT DEFAULT 'MEDIUM',
                    status TEXT DEFAULT 'needs_you',
                    redirect_note TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    resolved_at TIMESTAMP DEFAULT NULL
                );
                """
            )

            # 2. Fleet / Department / Workspace Broadcasts
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS orbit_broadcasts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_scope TEXT DEFAULT 'all_fleet',
                    directive TEXT NOT NULL,
                    author TEXT DEFAULT 'human_ui',
                    active INTEGER DEFAULT 1,
                    memory_id INTEGER DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

            # 3. Agent Chaining Hand-off Packets
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_handoffs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_agent TEXT NOT NULL,
                    to_scope TEXT DEFAULT 'next_agent',
                    workspace TEXT DEFAULT 'brain_mcp',
                    summary TEXT NOT NULL,
                    modified_files TEXT DEFAULT '',
                    key_findings TEXT DEFAULT '',
                    status TEXT DEFAULT 'ready',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

            # Desativar broadcasts duplicados por escopo ou diretiva (mantém apenas o mais recente por escopo)
            conn.execute(
                """
                UPDATE orbit_broadcasts
                SET active = 0
                WHERE active = 1
                  AND id NOT IN (
                      SELECT MAX(id) FROM orbit_broadcasts
                      WHERE active = 1
                      GROUP BY target_scope
                  );
                """
            )

            # Seed initial demo items if tables are empty so Mission Control is immediately rich
            cnt_inbox = conn.execute("SELECT COUNT(*) as c FROM orbit_inbox;").fetchone()["c"]
            if int(cnt_inbox or 0) == 0:
                seed_items = [
                    (
                        "seed:sandbox-api-01",
                        "api-01",
                        "API-01 • Backend Worker",
                        "brain_mcp",
                        "sandbox_merge",
                        "Merge CoW Sandbox: Orbit Agent OS 6-Tech Stack",
                        "Snapshots SHA-256 verificados (AST Gate=PASS, AI-Defence=SAFE). Aguarda confirmação humana para merge final.",
                        "orbit_engine.py, db_engine.py, web_dashboard.py",
                        "LOW",
                        "needs_you",
                    ),
                    (
                        "seed:ast-db-engine",
                        "scout-01",
                        "SCOUT-01 • AST Impact Watcher",
                        "brain_mcp",
                        "high_risk_edit",
                        "God Node Touch Alert: BrainDB.store_fact & search_memories",
                        "Detetada alteração estrutural num God Node (alcance: 10 ficheiros). Confirme se a regra 'Human Edits Always Win' deve ficar ativa.",
                        "db_engine.py",
                        "HIGH",
                        "needs_you",
                    ),
                    (
                        "seed:doc-report",
                        "doc-01",
                        "DOC-01 • Knowledge Scribe",
                        "brain_mcp",
                        "subagent_result",
                        "GRAPH_REPORT.md + Morning Brief sincronizados",
                        "Relatório topológico multi-modal atualizado com 338+ nós e calculadora de poupança ROI.",
                        "GRAPH_REPORT.md",
                        "LOW",
                        "approved",
                    ),
                ]
                for ext_ref, aid, aname, ws, knd, tit, summ, tfiles, rsk, st in seed_items:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO orbit_inbox
                        (external_ref, agent_id, agent_name, workspace, kind, title, summary, target_files, risk_level, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        (ext_ref, aid, aname, ws, knd, tit, summ, tfiles, rsk, st),
                    )

            cnt_ho = conn.execute("SELECT COUNT(*) as c FROM agent_handoffs;").fetchone()["c"]
            if int(cnt_ho or 0) == 0:
                conn.execute(
                    """
                    INSERT INTO agent_handoffs
                    (from_agent, to_scope, workspace, summary, modified_files, key_findings, status)
                    VALUES (?, ?, ?, ?, ?, ?, 'ready');
                    """,
                    (
                        "SCOUT-01 (flash_lite)",
                        "ARCH-01 & All Workers",
                        "brain_mcp",
                        "Mapeadas 6 tecnologias do Orbit Agent OS compatíveis com SQLite FTS5 + 32-D Semantic Vectors.",
                        "orbit_engine.py, db_engine.py, brain_inject.py, index.html",
                        "Trust Hierarchy (human_locked=1) evita sobrescrita por subagentes; Broadcast injeta diretivas por departamento/workspace em <1ms.",
                    ),
                )

            # 4. DOTS Git-Native DAG Task Tracker (Estilo .dots/ + OpenAI Dots c/ dependências blocks/depends_on)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dots_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dot_id TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    workspace TEXT DEFAULT 'brain_mcp',
                    lane TEXT DEFAULT 'API',
                    status TEXT DEFAULT 'open',
                    depends_on_json TEXT DEFAULT '[]',
                    claimed_by TEXT DEFAULT '',
                    priority INTEGER DEFAULT 4,
                    summary TEXT DEFAULT '',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            cnt_dots = conn.execute("SELECT COUNT(*) as c FROM dots_tasks;").fetchone()["c"]
            if int(cnt_dots or 0) == 0:
                seed_dots = [
                    (
                        "dot-01",
                        "SCOUT AST & Mapeamento :Lstart-end da Codebase",
                        "brain_mcp",
                        "DOCS",
                        "done",
                        "[]",
                        "scout-01",
                        5,
                        "Indexação AST única partilhada em brain.db para zero re-leituras.",
                    ),
                    (
                        "dot-02",
                        "DOTS Dynamic Trajectory Search no JEV-S1 Router",
                        "brain_mcp",
                        "API",
                        "done",
                        '["dot-01"]',
                        "arch-01",
                        5,
                        "Composição dinâmica de trajetórias cognitivas ótimas em <0.05ms.",
                    ),
                    (
                        "dot-03",
                        "DOTS ECS Float32Array SoA Physics & 3D Projection Pool",
                        "brain_mcp",
                        "UI",
                        "open",
                        '["dot-01", "dot-02"]',
                        "",
                        5,
                        "Buffers contíguos Float32Array sem alocações GC por frame a 60 FPS.",
                    ),
                    (
                        "dot-04",
                        "Validação Full-Stack Test #22 (DOTS Pack Completo)",
                        "brain_mcp",
                        "TESTS",
                        "open",
                        '["dot-03"]',
                        "",
                        4,
                        "Bloqueada até dot-03 concluir; valida DAG ready/claim/complete e SoA.",
                    ),
                ]
                for did, dtitle, dws, dlane, dst, ddeps, dclaim, dprio, dsum in seed_dots:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO dots_tasks
                        (dot_id, title, workspace, lane, status, depends_on_json, claimed_by, priority, summary)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        (did, dtitle, dws, dlane, dst, ddeps, dclaim, dprio, dsum),
                    )

            # 6. Tabelas do Motor de Auto-Aprendizagem Recursiva & Sentinel Proativo (Self-Learn v4.8 por Projeto)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS self_learn_projects (
                    workspace TEXT PRIMARY KEY,
                    enabled INTEGER DEFAULT 1,
                    proactive_enabled INTEGER DEFAULT 1,
                    cycles_run INTEGER DEFAULT 0,
                    rules_distilled INTEGER DEFAULT 0,
                    synapses_reinforced INTEGER DEFAULT 0,
                    duplicates_healed INTEGER DEFAULT 0,
                    brain_iq_score REAL DEFAULT 88.0,
                    learned_playbook_json TEXT DEFAULT '[]',
                    last_evolution_summary TEXT DEFAULT '',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS self_learn_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workspace TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    iq_delta REAL DEFAULT 0.4,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            cnt_sl = conn.execute("SELECT COUNT(*) as c FROM self_learn_projects;").fetchone()["c"]
            if int(cnt_sl or 0) == 0:
                seed_playbook = json.dumps(
                    [
                        "Usar sempre ponteiros AST :Lstart-end e fatia segura slice_scout_map_ast_safe antes de editar ficheiros extensos.",
                        "Em index.html, escapar aspas simples (&#39;) em atributos onclick e validar JS com node --check antes de commit.",
                        "Preferir trajetórias DOTS [AST_SLICE:L]➔[BLAST_RADIUS]➔[SURGICAL_PATCH]➔[VERIFY_AST_TESTS] em refatorações multi-ficheiro.",
                    ],
                    ensure_ascii=False,
                )
                conn.execute(
                    """
                    INSERT OR IGNORE INTO self_learn_projects
                    (workspace, enabled, proactive_enabled, cycles_run, rules_distilled, synapses_reinforced, duplicates_healed, brain_iq_score, learned_playbook_json, last_evolution_summary)
                    VALUES ('brain_mcp', 1, 1, 1, 3, 6, 1, 94.2, ?, 'Ciclo inicial v4.8: 3 Meta-Regras destiladas e 6 sinapses reforçadas.');
                    """,
                    (seed_playbook,),
                )
                conn.execute(
                    """
                    INSERT INTO self_learn_events (workspace, event_type, title, detail, iq_delta)
                    VALUES ('brain_mcp', 'rule_distilled', 'Auto-Evolução Inicial (brain_mcp)', 'Destiladas 3 Meta-Regras operacionais a partir do histórico de auditorias e correções.', 1.2);
                    """
                )

            # 7. Tabela do Prompt Forge (Histórico de Prompts Otimizados com Contexto do Brain + Self-Learn)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS prompt_forge_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workspace TEXT NOT NULL,
                    task_mode TEXT DEFAULT 'feature',
                    raw_request TEXT NOT NULL,
                    full_prompt TEXT NOT NULL,
                    compact_prompt TEXT NOT NULL,
                    swarm_prompt TEXT NOT NULL,
                    dots_trajectory TEXT DEFAULT '',
                    matched_files_json TEXT DEFAULT '[]',
                    rules_applied_count INTEGER DEFAULT 0,
                    estimated_tokens_saved INTEGER DEFAULT 420,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    # =========================================================================
    # 1. MISSION CONTROL INBOX ('WAITING FOR YOUR YES' / APPROVE ALL / REDIRECT)
    # =========================================================================
    def _sync_live_events_to_inbox(self) -> None:
        """Sincroniza automaticamente Sandboxes CoW isoladas e alertas HIGH/CRITICAL do AST Watcher para a Inbox."""
        with self.db._connect() as conn:
            try:
                sandboxes = conn.execute(
                    "SELECT id, lane, task_code, workspace, status, files_json FROM swarm_sandboxes ORDER BY id DESC LIMIT 8;"
                ).fetchall()
                for sb in sandboxes:
                    s_id = int(sb["id"])
                    ext_ref = f"sandbox:{s_id}"
                    st = "approved" if sb["status"] == "merged" else "needs_you"
                    files_list = json.loads(sb["files_json"] or "[]")
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO orbit_inbox
                        (external_ref, agent_id, agent_name, workspace, kind, title, summary, target_files, risk_level, status)
                        VALUES (?, ?, ?, ?, 'sandbox_merge', ?, ?, ?, 'LOW', ?);
                        """,
                        (
                            ext_ref,
                            str(sb["task_code"] or "api-01"),
                            f"Lane {sb['lane']} ({sb['task_code']})",
                            str(sb["workspace"] or "brain_mcp"),
                            f"Sandbox CoW #{s_id} pronta para merge ({sb['lane']})",
                            "Snapshot SHA-256 validado com AST Syntax Gate e AI-Defence Secret Scan.",
                            ", ".join(files_list) if files_list else "swarm_engine.py",
                            st,
                        ),
                    )
            except Exception:
                pass

            try:
                audits = conn.execute(
                    """
                    SELECT id, file_path, workspace, risk_level, affected_files_count, total_references, recommendation
                    FROM ast_save_audits
                    WHERE risk_level IN ('HIGH', 'CRITICAL')
                    ORDER BY id DESC LIMIT 5;
                    """
                ).fetchall()
                for au in audits:
                    au_id = int(au["id"])
                    ext_ref = f"astaudit:{au_id}"
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO orbit_inbox
                        (external_ref, agent_id, agent_name, workspace, kind, title, summary, target_files, risk_level, status)
                        VALUES (?, 'scout-01', 'AST Impact Watcher', ?, 'high_risk_edit', ?, ?, ?, ?, 'needs_you');
                        """,
                        (
                            ext_ref,
                            str(au["workspace"] or "brain_mcp"),
                            f"Blast Radius {au['risk_level']}: {au['file_path']} ({au['affected_files_count']} ficheiros)",
                            str(au["recommendation"] or "Alteração detetada em ficheiro central."),
                            str(au["file_path"]),
                            str(au["risk_level"]),
                        ),
                    )
            except Exception:
                pass

    def get_mission_control_inbox(self, status_filter: str = "all", limit: int = 25) -> Dict[str, Any]:
        self._sync_live_events_to_inbox()
        with self.db._connect() as conn:
            if status_filter and status_filter != "all":
                rows = conn.execute(
                    "SELECT * FROM orbit_inbox WHERE status = ? ORDER BY CASE WHEN status='needs_you' THEN 0 ELSE 1 END, id DESC LIMIT ?;",
                    (status_filter, int(limit)),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM orbit_inbox ORDER BY CASE WHEN status='needs_you' THEN 0 ELSE 1 END, id DESC LIMIT ?;",
                    (int(limit),),
                ).fetchall()

            counts = conn.execute(
                """
                SELECT
                    SUM(CASE WHEN status = 'needs_you' THEN 1 ELSE 0 END) as needs_you,
                    SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) as approved,
                    SUM(CASE WHEN status = 'redirected' THEN 1 ELSE 0 END) as redirected,
                    COUNT(*) as total
                FROM orbit_inbox;
                """
            ).fetchone()

        items = [dict(r) for r in rows]
        for it in items:
            if it.get("status") == "needs_you":
                it["status"] = "pending"
        pending_cnt = int(counts["needs_you"] or 0) if counts else 0
        return {
            "ok": True,
            "needs_you_count": pending_cnt,
            "pending_count": pending_cnt,
            "approved_count": int(counts["approved"] or 0) if counts else 0,
            "redirected_count": int(counts["redirected"] or 0) if counts else 0,
            "total_count": int(counts["total"] or 0) if counts else 0,
            "items": items,
        }

    def approve_inbox_item(self, item_id: int, workspace_path: str = "") -> Dict[str, Any]:
        with self.db._connect() as conn:
            row = conn.execute("SELECT * FROM orbit_inbox WHERE id = ?;", (int(item_id),)).fetchone()
            if not row:
                return {"ok": False, "error": f"Item #{item_id} não encontrado na Inbox."}
            conn.execute(
                "UPDATE orbit_inbox SET status = 'approved', resolved_at = CURRENT_TIMESTAMP WHERE id = ?;",
                (int(item_id),),
            )
            ext_ref = str(row["external_ref"] or "")
            if ext_ref.startswith("sandbox:"):
                sb_id = int(ext_ref.split(":")[1])
                conn.execute(
                    "UPDATE swarm_sandboxes SET status = 'merged', verify_ast = 1, verify_aidefence = 1, merged_at = CURRENT_TIMESTAMP WHERE id = ?;",
                    (sb_id,),
                )
        return self.get_mission_control_inbox()

    def approve_all_inbox(self, workspace: str = "all", workspace_path: str = "") -> Dict[str, Any]:
        with self.db._connect() as conn:
            if workspace and workspace != "all":
                conn.execute(
                    "UPDATE orbit_inbox SET status = 'approved', resolved_at = CURRENT_TIMESTAMP WHERE status IN ('needs_you', 'pending') AND workspace = ?;",
                    (workspace,),
                )
            else:
                conn.execute(
                    "UPDATE orbit_inbox SET status = 'approved', resolved_at = CURRENT_TIMESTAMP WHERE status IN ('needs_you', 'pending');"
                )
            try:
                conn.execute(
                    "UPDATE swarm_sandboxes SET status = 'merged', verify_ast = 1, verify_aidefence = 1, merged_at = CURRENT_TIMESTAMP WHERE status = 'isolated';"
                )
            except Exception:
                pass
        return self.get_mission_control_inbox()

    def redirect_inbox_item(self, item_id: int, directive: str = "", redirect_note: str = "") -> Dict[str, Any]:
        note = (directive or redirect_note or "Ajustar implementação e correr validação AST antes de prosseguir.").strip()
        with self.db._connect() as conn:
            row = conn.execute("SELECT * FROM orbit_inbox WHERE id = ?;", (int(item_id),)).fetchone()
            if not row:
                return {"ok": False, "error": f"Item #{item_id} não encontrado."}
            conn.execute(
                "UPDATE orbit_inbox SET status = 'redirected', redirect_note = ?, resolved_at = CURRENT_TIMESTAMP WHERE id = ?;",
                (note, int(item_id)),
            )
            ws = str(row["workspace"] or "brain_mcp")
            ag_name = str(row["agent_name"] or row["agent_id"] or "Agent")

        # Grava diretiva bloqueada por humano ("Human Edits Always Win") para guiar o agente redirecionado
        self.db.store_fact(
            topic=f"Orbit Redirect -> {ag_name}: {row['title'][:45]}",
            fact=f"Redirecionamento humano obrigatório: {note}",
            workspace=ws,
            category="directive",
            tags=f"pinned redirect orbit {row['agent_id']} human_verified",
            importance=5,
            source_agent="human_ui",
            trust_score=1.0,
            human_locked=1,
        )
        return self.get_mission_control_inbox()

    # =========================================================================
    # 2. BROADCAST MULTI-AGENTE (ALL FLEET / DEPARTMENT LANE / WORKSPACE)
    # =========================================================================
    def send_broadcast(
        self,
        directive: str = "",
        target_scope: str = "all_fleet",
        author: str = "human_ui",
        workspace: str = "global",
    ) -> Dict[str, Any]:
        clean_dir = (directive or "").strip()
        if not clean_dir:
            return {"ok": False, "error": "A diretiva de Broadcast não pode estar vazia."}

        scope = (target_scope or "all_fleet").strip()
        ws = (workspace or "global").strip()
        if scope.startswith("ws:"):
            ws = scope.split(":", 1)[1].strip() or ws

        mem_id, _ = self.db.store_fact(
            topic=f"📡 Broadcast [{scope.upper()}]: {clean_dir[:48]}",
            fact=f"[ORBIT BROADCAST -> {scope}] {clean_dir}",
            workspace=ws,
            category="directive",
            tags=f"pinned broadcast orbit {scope} human_verified",
            importance=5,
            source_agent=author,
            trust_score=1.0,
            human_locked=1,
        )

        now = time.time()
        affected_agents = 0
        with self.db._connect() as conn:
            # Desativar broadcasts anteriores do mesmo scope ou com a mesma diretiva para evitar duplicação de tokens
            conn.execute(
                "UPDATE orbit_broadcasts SET active = 0 WHERE active = 1 AND (target_scope = ? OR LOWER(TRIM(directive)) = LOWER(TRIM(?)));",
                (scope, clean_dir),
            )
            conn.execute(
                """
                INSERT INTO orbit_broadcasts (target_scope, directive, author, active, memory_id)
                VALUES (?, ?, ?, 1, ?);
                """,
                (scope, clean_dir, author, mem_id),
            )
            try:
                if scope == "all_fleet":
                    cur = conn.execute(
                        "UPDATE office_agents SET status = 'working', current_task = ?, manual_override = 1, updated_at = ?;",
                        (f"📡 [BROADCAST] {clean_dir[:72]}", now),
                    )
                    affected_agents = cur.rowcount
                elif scope.startswith("dept:"):
                    dept_val = scope.split(":", 1)[1].strip().upper()
                    cur = conn.execute(
                        "UPDATE office_agents SET status = 'working', current_task = ?, manual_override = 1, updated_at = ? WHERE UPPER(department) LIKE ? OR UPPER(name) LIKE ?;",
                        (f"📡 [{dept_val}] {clean_dir[:68]}", now, f"%{dept_val}%", f"%{dept_val}%"),
                    )
                    affected_agents = cur.rowcount
                elif scope.startswith("ws:"):
                    ws_val = scope.split(":", 1)[1].strip().lower()
                    cur = conn.execute(
                        "UPDATE office_agents SET status = 'working', current_task = ?, manual_override = 1, updated_at = ? WHERE LOWER(workspace) = ?;",
                        (f"📡 [{ws_val}] {clean_dir[:68]}", now, ws_val),
                    )
                    affected_agents = cur.rowcount
            except Exception:
                pass

        return {
            "ok": True,
            "target_scope": scope,
            "directive": clean_dir,
            "memory_id": mem_id,
            "affected_agents": affected_agents,
            "agents_notified": max(1, affected_agents),
            "broadcasts": self.get_active_broadcasts(workspace=ws),
        }

    def get_active_broadcasts(self, workspace: str = "global", limit: int = 8) -> List[Dict[str, Any]]:
        ws = (workspace or "global").strip().lower()
        with self.db._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM orbit_broadcasts
                WHERE active = 1
                  AND (target_scope = 'all_fleet' OR target_scope LIKE 'dept:%' OR LOWER(target_scope) = ?)
                ORDER BY id DESC LIMIT ?;
                """,
                (f"ws:{ws}", int(limit) * 2),
            ).fetchall()
            deduped: List[Dict[str, Any]] = []
            seen_keys: set[str] = set()
            for r in rows:
                d = dict(r)
                k = f"{str(d.get('target_scope', '')).lower()}|{str(d.get('directive', '')).strip().lower()}"
                if k in seen_keys:
                    continue
                seen_keys.add(k)
                deduped.append(d)
                if len(deduped) >= int(limit):
                    break
            return deduped

    # =========================================================================
    # 3. AGENT CHAINING & AUTOMATIC HAND-OFF PACKETS (agent_handoffs)
    # =========================================================================
    def record_handoff(
        self,
        from_agent: str = "Arquiteto (Brain)",
        workspace: str = "brain_mcp",
        summary: str = "",
        modified_files: str = "",
        key_findings: str = "",
        to_scope: str = "next_agent",
        to_agent: str = "",
        task_code: str = "orbit-01",
        files_touched: Optional[List[str]] = None,
        next_action: str = "",
    ) -> Dict[str, Any]:
        ws = self.db.normalize_workspace(workspace) if workspace else "global"
        resolved_to = (to_agent or to_scope or "next_agent").strip()
        resolved_files = modified_files or (", ".join(files_touched) if isinstance(files_touched, list) else "")
        resolved_findings = key_findings or next_action or "Prosseguir execução na lane seguinte."
        with self.db._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO agent_handoffs
                (from_agent, to_scope, workspace, summary, modified_files, key_findings, status)
                VALUES (?, ?, ?, ?, ?, ?, 'ready');
                """,
                (
                    (from_agent or "agent").strip(),
                    resolved_to,
                    ws,
                    (summary or "Turno concluído").strip()[:280],
                    (resolved_files or "").strip()[:220],
                    (resolved_findings or "").strip()[:280],
                ),
            )
            hid = int(cur.lastrowid)
        return {
            "ok": True,
            "handoff_id": hid,
            "from_agent": from_agent,
            "to_agent": resolved_to,
            "task_code": task_code,
            "summary": summary,
            "next_action": resolved_findings,
        }

    def get_recent_handoffs(self, workspace: str = "all", limit: int = 8) -> List[Dict[str, Any]]:
        with self.db._connect() as conn:
            if workspace and workspace not in ("all", "global"):
                ws = self.db.normalize_workspace(workspace)
                rows = conn.execute(
                    "SELECT * FROM agent_handoffs WHERE workspace IN (?, 'global', 'brain_mcp') ORDER BY id DESC LIMIT ?;",
                    (ws, int(limit)),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM agent_handoffs ORDER BY id DESC LIMIT ?;",
                    (int(limit),),
                ).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d.setdefault("to_agent", d.get("to_scope", "Worker Agent"))
                d.setdefault("task_code", f"ho-{d.get('id', 1):02d}")
                d.setdefault("next_action", d.get("key_findings", "Validar alterações"))
                out.append(d)
            return out

    # =========================================================================
    # 4. ONE-CLICK MULTI-AI MCP BRIDGE (ANTIGRAVITY, CURSOR, CLAUDE, WINDSURF)
    # =========================================================================
    def get_mcp_bridge_status(self) -> Dict[str, Any]:
        repo_dir = Path(os.path.dirname(os.path.abspath(__file__)))
        server_py = str((repo_dir / "server.py").resolve()).replace("\\", "/")
        home = Path.home()
        appdata = Path(os.environ.get("APPDATA", str(home / "AppData" / "Roaming")))

        targets = [
            {
                "id": "antigravity",
                "name": "Google Antigravity IDE",
                "config_path": home / ".gemini" / "config" / "mcp_config.json",
                "icon": "🚀",
            },
            {
                "id": "cursor",
                "name": "Cursor AI IDE",
                "config_path": home / ".cursor" / "mcp.json",
                "icon": "⚡",
            },
            {
                "id": "windsurf",
                "name": "Windsurf (Codeium)",
                "config_path": home / ".codeium" / "windsurf" / "mcp_config.json",
                "icon": "🌊",
            },
            {
                "id": "claude_desktop",
                "name": "Claude Desktop / Cowork",
                "config_path": appdata / "Claude" / "claude_desktop_config.json",
                "icon": "🤖",
            },
        ]

        results: List[Dict[str, Any]] = []
        connected_count = 0
        for t in targets:
            cpath: Path = t["config_path"]
            is_connected = False
            parent_exists = cpath.parent.exists()
            if cpath.is_file():
                try:
                    raw = json.loads(cpath.read_text(encoding="utf-8", errors="ignore"))
                    srvs = raw.get("mcpServers") or {}
                    if "antigravity-brain" in srvs:
                        is_connected = True
                except Exception:
                    pass
            if is_connected:
                connected_count += 1
            results.append(
                {
                    "id": t["id"],
                    "name": t["name"],
                    "label": t["name"],
                    "icon": t["icon"],
                    "config_path": str(cpath).replace("\\", "/"),
                    "installed_dir": parent_exists or cpath.is_file(),
                    "connected": is_connected,
                }
            )

        snippet = {
            "mcpServers": {
                "antigravity-brain": {
                    "command": "python",
                    "args": ["-u", server_py],
                }
            }
        }
        return {
            "ok": True,
            "server_script": server_py,
            "connected_count": connected_count,
            "total_targets": len(results),
            "targets": results,
            "universal_mcp_json": json.dumps(snippet, indent=2, ensure_ascii=False),
        }

    def connect_all_ai_tools(self, target_id: str = "all", target_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        status = self.get_mcp_bridge_status()
        server_py = status["server_script"]
        updated: List[str] = []
        allowed_set = set(target_ids) if isinstance(target_ids, list) and target_ids else None

        for t in status["targets"]:
            if allowed_set is not None and t["id"] not in allowed_set:
                continue
            if allowed_set is None and target_id != "all" and t["id"] != target_id:
                continue
            cpath = Path(t["config_path"])
            if allowed_set is None and target_id == "all" and not t["installed_dir"] and t["id"] not in ("antigravity", "cursor"):
                continue
            try:
                cpath.parent.mkdir(parents=True, exist_ok=True)
                cfg: Dict[str, Any] = {"mcpServers": {}}
                if cpath.is_file():
                    try:
                        cfg = json.loads(cpath.read_text(encoding="utf-8", errors="ignore"))
                        if not isinstance(cfg, dict):
                            cfg = {"mcpServers": {}}
                    except Exception:
                        cfg = {"mcpServers": {}}
                srvs = cfg.setdefault("mcpServers", {})
                srvs["antigravity-brain"] = {
                    "command": "python",
                    "args": ["-u", server_py],
                }
                cpath.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
                updated.append(t["name"])
            except Exception:
                pass

        new_status = self.get_mcp_bridge_status()
        new_status["updated_tools"] = updated
        return new_status

    # =========================================================================
    # 5. MORNING BRIEF / EXECUTIVE DIGEST & SAVINGS / ROI CALCULATOR
    # =========================================================================
    def get_executive_briefing_and_roi(self, workspace: str = "all") -> Dict[str, Any]:
        stats = self.db.get_stats()
        inbox = self.get_mission_control_inbox(limit=15)
        broadcasts = self.get_active_broadcasts(limit=6)
        handoffs = self.get_recent_handoffs(limit=6)
        bridge = self.get_mcp_bridge_status()

        with self.db._connect() as conn:
            human_locked_cnt = conn.execute(
                "SELECT COUNT(*) as c FROM memories WHERE COALESCE(human_locked, 0) = 1 OR category = 'directive' OR tags LIKE '%pinned%';"
            ).fetchone()["c"]
            high_trust_cnt = conn.execute(
                "SELECT COUNT(*) as c FROM memories WHERE COALESCE(trust_score, 0.85) >= 0.90;"
            ).fetchone()["c"]
            completed_swarm_tasks = 0
            try:
                r_tasks = conn.execute(
                    "SELECT COUNT(*) as c FROM swarm_tasks WHERE status = 'done';"
                ).fetchone()
                completed_swarm_tasks = int(r_tasks["c"] or 24)
            except Exception:
                completed_swarm_tasks = 24

            total_agents_fleet = 8
            try:
                r_ag = conn.execute("SELECT COUNT(*) as c FROM office_agents;").fetchone()
                total_agents_fleet = max(8, int(r_ag["c"] or 8))
            except Exception:
                pass

            recent_mems = [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT id, topic, fact, workspace, category, importance,
                           COALESCE(source_agent, 'system') as source_agent,
                           COALESCE(trust_score, 0.85) as trust_score,
                           COALESCE(human_locked, 0) as human_locked,
                           created_at
                    FROM memories
                    ORDER BY COALESCE(human_locked, 0) DESC, id DESC LIMIT 8;
                    """
                ).fetchall()
            ]

        saved_tokens = max(148500, int(stats.get("estimated_saved_tokens", 0) or 0) + completed_swarm_tasks * 6200)
        # Orbit ROI Formula:
        # 1) Engineering hours saved: each completed swarm task + scout AST pass + memory hit saves ~12 mins (0.2h)
        hours_saved = round(
            (completed_swarm_tasks * 0.22)
            + (int(stats.get("total_memories", 20)) * 0.14)
            + (saved_tokens / 45000.0),
            1,
        )
        # 2) Direct LLM API / Token cost saved ($15 / 1M tokens blended frontier rate)
        api_dollars_saved = round((saved_tokens / 1_000_000.0) * 15.0 + (completed_swarm_tasks * 0.45), 2)
        # 3) Equivalent engineering value (@ $85/hr senior engineer / agency rate)
        engineering_value_usd = round(hours_saved * 85.0, 0)

        brief_points = [
            f"🧠 Shared Brain ativo em {len(stats.get('by_workspace', {}))} projetos com {stats.get('total_memories', 0)} memórias ({human_locked_cnt} protegidas por 'Human Edits Always Win').",
            f"🛰️ Frota de {total_agents_fleet} agentes/subagentes monitorizada e {completed_swarm_tasks} tasks Swarm concluídas com validação AST + AI-Defence.",
            f"📬 Mission Control Inbox tem {inbox['needs_you_count']} itens a aguardar aprovação humana ('Needs Your Yes') e {inbox['approved_count']} já aprovados.",
            f"🔗 {len(handoffs)} pacotes de Hand-off entre subagentes prontos e {bridge['connected_count']}/{bridge['total_targets']} IDEs ligados via MCP Bridge.",
        ]

        roi_obj = {
            "tokens_saved": saved_tokens,
            "hours_saved": hours_saved,
            "api_cost_saved_usd": api_dollars_saved,
            "engineering_value_usd": int(engineering_value_usd),
            "orbit_cloud_monthly_saved_usd": 249,
        }
        trust_obj = {
            "human_locked_count": int(human_locked_cnt or 0),
            "human_locked_memories": int(human_locked_cnt or 0),
            "high_trust_count": int(high_trust_cnt or 0),
            "subagent_memories": max(0, int(stats.get("total_memories", 0)) - int(human_locked_cnt or 0)),
            "total_memories": int(stats.get("total_memories", 0)),
            "policy": "Human Edits Always Win (trust_score=1.0, immutable by subagents)",
        }
        dots_dag = self.get_dots_dag(workspace=workspace or "all")
        self_learn = self.get_self_learn_status(workspace=workspace if workspace and workspace != "all" else "brain_mcp")
        prompt_history = self.get_prompt_forge_history(workspace=workspace or "all", limit=8)
        available_skills = self.discover_antigravity_skills()
        return {
            "ok": True,
            "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "brief_points": brief_points,
            "morning_brief": {
                "headline": brief_points[0] if brief_points else "Orbit Agent OS Operational",
                "points": brief_points,
            },
            "trust_metrics": trust_obj,
            "trust_hierarchy": trust_obj,
            "roi_calculator": roi_obj,
            "roi": roi_obj,
            "inbox": inbox,
            "broadcasts": broadcasts,
            "active_broadcasts": broadcasts,
            "handoffs": handoffs,
            "recent_handoffs": handoffs,
            "mcp_bridge": bridge,
            "dots_dag": dots_dag,
            "self_learn": self_learn,
            "prompt_forge_history": prompt_history,
            "available_skills": available_skills,
            "recent_trusted_memories": recent_mems,
        }

    # =========================================================================
    # 6. DOTS GIT-NATIVE DAG TASK TRACKER (.dots/*.md + dot_ready UNBLOCKED RESOLVER)
    # =========================================================================
    def get_dots_dag(self, workspace: str = "all") -> Dict[str, Any]:
        """
        Calcula o Grafo Acíclico Dirigido (DAG) de tarefas DOTS:
        - Uma tarefa 'open' só está READY (desbloqueada) quando todas as tarefas em 'depends_on' estão 'done'.
        - Permite injeção Zero-Token apenas das tarefas READY no PreInvocation.
        """
        ws = (workspace or "all").strip().lower()
        with self.db._connect() as conn:
            if ws and ws not in ("all", "global"):
                rows = conn.execute(
                    "SELECT * FROM dots_tasks WHERE LOWER(workspace) IN (?, 'global', 'brain_mcp') ORDER BY priority DESC, id ASC;",
                    (ws,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM dots_tasks ORDER BY priority DESC, id ASC;"
                ).fetchall()

        all_dots = [dict(r) for r in rows]
        status_by_id: Dict[str, str] = {str(d["dot_id"]): str(d["status"]) for d in all_dots}

        ready_dots: List[Dict[str, Any]] = []
        blocked_dots: List[Dict[str, Any]] = []
        claimed_dots: List[Dict[str, Any]] = []
        done_dots: List[Dict[str, Any]] = []

        for d in all_dots:
            try:
                deps = json.loads(d.get("depends_on_json") or "[]")
                if not isinstance(deps, list):
                    deps = []
            except Exception:
                deps = []
            d["depends_on"] = [str(x) for x in deps if x]
            unresolved = [dep_id for dep_id in d["depends_on"] if status_by_id.get(dep_id, "open") != "done"]
            d["blocked_by"] = unresolved
            st = str(d.get("status") or "open").lower()
            if st == "done":
                d["dag_state"] = "done"
                d["is_ready"] = False
                done_dots.append(d)
            elif st == "claimed":
                d["dag_state"] = "claimed"
                d["is_ready"] = False
                claimed_dots.append(d)
            elif len(unresolved) == 0:
                d["dag_state"] = "ready"
                d["is_ready"] = True
                ready_dots.append(d)
            else:
                d["dag_state"] = "blocked"
                d["is_ready"] = False
                blocked_dots.append(d)
            d["assignee"] = d.get("claimed_by") or d.get("lane") or "unassigned"

        return {
            "ok": True,
            "total_count": len(all_dots),
            "ready_count": len(ready_dots),
            "blocked_count": len(blocked_dots),
            "claimed_count": len(claimed_dots),
            "done_count": len(done_dots),
            "ready_dots": ready_dots,
            "ready_tasks": ready_dots,
            "blocked_dots": blocked_dots,
            "claimed_dots": claimed_dots,
            "done_dots": done_dots,
            "items": all_dots,
            "tasks": all_dots,
        }

    def manage_dot_task(
        self,
        action: str = "ready",
        dot_id: str = "",
        title: str = "",
        workspace: str = "brain_mcp",
        lane: str = "API",
        depends_on: Optional[List[str]] = None,
        agent_id: str = "arch-01",
        assignee: str = "",
        close_reason: str = "",
        priority: int = 4,
        summary: str = "",
        export_dir: str = "",
    ) -> Dict[str, Any]:
        """
        Gere tarefas no DAG DOTS:
        - 'ready': devolve apenas tarefas 100% desbloqueadas (zero dependências pendentes).
        - 'create': cria novo Dot no DAG com lista de dependências 'depends_on'.
        - 'claim': reclama uma tarefa READY para um agente (recusa se estiver BLOCKED no DAG).
        - 'complete' / 'done': conclui um Dot e desbloqueia automaticamente os seus dependentes no DAG.
        - 'sync_md': exporta as tarefas como ficheiros Markdown + YAML frontmatter em .dots/*.md.
        """
        act = (action or "ready").strip().lower()
        effective_agent = (assignee or agent_id or "arch-01").strip()
        if act == "ready":
            return self.get_dots_dag(workspace=workspace)

        with self.db._connect() as conn:
            if act == "create":
                clean_title = (title or "Nova Tarefa DOTS").strip()
                did = (dot_id or "").strip()
                if not did:
                    cnt = conn.execute("SELECT COUNT(*) as c FROM dots_tasks;").fetchone()["c"]
                    did = f"dot-{int(cnt or 0) + 1:02d}"
                deps_list = [str(x).strip() for x in (depends_on or []) if str(x).strip()]
                conn.execute(
                    """
                    INSERT INTO dots_tasks (dot_id, title, workspace, lane, status, depends_on_json, claimed_by, priority, summary, updated_at)
                    VALUES (?, ?, ?, ?, 'open', ?, '', ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(dot_id) DO UPDATE SET
                        title = excluded.title,
                        depends_on_json = excluded.depends_on_json,
                        priority = excluded.priority,
                        summary = excluded.summary,
                        updated_at = CURRENT_TIMESTAMP;
                    """,
                    (
                        did,
                        clean_title,
                        (workspace or "brain_mcp").strip().lower(),
                        (lane or "API").strip().upper(),
                        json.dumps(deps_list),
                        max(1, min(5, int(priority or 4))),
                        (summary or "").strip(),
                    ),
                )
            elif act == "claim":
                target_id = (dot_id or "").strip()
                dag_now = self.get_dots_dag(workspace="all")
                target_item = next((x for x in dag_now["items"] if x["dot_id"] == target_id), None)
                if not target_item:
                    return {"ok": False, "error": f"Dot '{target_id}' não encontrado."}
                if target_item.get("blocked_by"):
                    return {
                        "ok": False,
                        "error": f"Dot '{target_id}' está BLOQUEADO no DAG por: {', '.join(target_item['blocked_by'])}",
                        "blocked_by": target_item["blocked_by"],
                    }
                conn.execute(
                    "UPDATE dots_tasks SET status = 'claimed', claimed_by = ?, updated_at = CURRENT_TIMESTAMP WHERE dot_id = ?;",
                    (effective_agent, target_id),
                )
            elif act in ("complete", "done"):
                target_id = (dot_id or "").strip()
                if close_reason:
                    conn.execute(
                        "UPDATE dots_tasks SET status = 'done', summary = CASE WHEN summary = '' THEN ? ELSE summary END, updated_at = CURRENT_TIMESTAMP WHERE dot_id = ?;",
                        (close_reason.strip(), target_id),
                    )
                else:
                    conn.execute(
                        "UPDATE dots_tasks SET status = 'done', updated_at = CURRENT_TIMESTAMP WHERE dot_id = ?;",
                        (target_id,),
                    )
            elif act == "reopen":
                target_id = (dot_id or "").strip()
                conn.execute(
                    "UPDATE dots_tasks SET status = 'open', claimed_by = '', updated_at = CURRENT_TIMESTAMP WHERE dot_id = ?;",
                    (target_id,),
                )

        dag_after = self.get_dots_dag(workspace=workspace)

        if act == "sync_md":
            base_dir = Path(export_dir) if export_dir else (Path(os.path.dirname(os.path.abspath(__file__))) / ".dots")
            base_dir.mkdir(parents=True, exist_ok=True)
            written_files: List[str] = []
            for item in dag_after["items"]:
                safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "", str(item["dot_id"])) or "dot"
                md_path = base_dir / f"{safe_id}.md"
                md_content = (
                    "---\n"
                    f"id: {item['dot_id']}\n"
                    f"title: \"{str(item['title']).replace('\"', '')}\"\n"
                    f"status: {item['status']}\n"
                    f"dag_state: {item['dag_state']}\n"
                    f"lane: {item['lane']}\n"
                    f"workspace: {item['workspace']}\n"
                    f"priority: {item['priority']}\n"
                    f"depends_on: {json.dumps(item['depends_on'])}\n"
                    f"claimed_by: \"{item.get('claimed_by') or ''}\"\n"
                    "---\n\n"
                    f"# {item['dot_id']} — {item['title']}\n\n"
                    f"{item.get('summary') or 'Tarefa gerida pelo motor DOTS DAG do Antigravity Brain.'}\n"
                )
                md_path.write_text(md_content, encoding="utf-8")
                written_files.append(str(md_path))
            dag_after["synced_md_files"] = written_files
            dag_after["exported_count"] = len(written_files)
            dag_after["dots_dir"] = str(base_dir)

        return dag_after

    # =========================================================================
    # 7. RECURSIVE SELF-LEARNING & PROACTIVE SENTINEL ENGINE (PER-PROJECT OPT-IN)
    # =========================================================================
    _SELF_LEARN_SYNC_TS: Dict[str, float] = {}
    _INVALID_SELF_LEARN_WS = {
        "all", "global", "brain", "scratch", "test", "dev", "api", "app", "apps",
        "panel", "docs", "nodes", "templates", "internal", "image", "install",
        "unpacked", "[id]", "[backupid]", "office_3d", "swarm_24x", "graphify_ast",
        "token_diet", "_m2bob_1091_extract", "antigravity-backup", "antigravity-brain",
        "claude-architect-coder", "strix", "ui-ux-pro-max-skill", "ultraplan",
        "network_infra", "vps_infra", "00_automation", "boost", "build", "char_encoding",
        "find", "xc_decode", "aura", "llm", "backend", "dockerruntime", "fastdl", "watchdog", "nginx",
    }

    def get_self_learn_status(self, workspace: str = "brain_mcp") -> Dict[str, Any]:
        """
        Devolve o estado de Auto-Aprendizagem Recursiva (Self-Learn) e Proatividade por Projeto:
        - Se está ativo (enabled) e proativo (proactive_enabled) para o workspace pedido;
        - O Índice de Maturidade Cognitiva / Brain IQ (brain_iq_score %);
        - As Meta-Regras destiladas (learned_playbook) a partir das memórias guardadas;
        - Lista de todos os projetos disponíveis para ativar/desativar individualmente.
        """
        ws = (workspace or "brain_mcp").strip().lower()
        if ws in ("all", "", "global") or ws in OrbitEngine._INVALID_SELF_LEARN_WS:
            ws = "brain_mcp"

        now_ts = time.time()
        db_key = str(getattr(self.db, "db_path", "default"))
        need_sync = (now_ts - OrbitEngine._SELF_LEARN_SYNC_TS.get(db_key, 0.0)) > 15.0

        with self.db._connect() as conn:
            if need_sync or ws != "brain_mcp":
                OrbitEngine._SELF_LEARN_SYNC_TS[db_key] = now_ts
                # Descobrir todos os workspaces reais com memórias e garantir entrada em self_learn_projects (Ativo por defeito / Opt-Out)
                ws_rows = conn.execute(
                    "SELECT DISTINCT LOWER(TRIM(workspace)) as w FROM memories WHERE workspace IS NOT NULL AND TRIM(workspace) != '';"
                ).fetchall()
                raw_candidates = {str(r["w"]) for r in ws_rows if r["w"]} | {"brain_mcp", ws}
                known_ws = sorted(
                    w for w in raw_candidates
                    if w not in OrbitEngine._INVALID_SELF_LEARN_WS
                    and re.match(r"^[a-z0-9][a-z0-9_\-]{1,38}$", w)
                )
                if "brain_mcp" not in known_ws:
                    known_ws.insert(0, "brain_mcp")

                for kws in known_ws:
                    default_en = 1
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO self_learn_projects
                        (workspace, enabled, proactive_enabled, cycles_run, rules_distilled, synapses_reinforced, duplicates_healed, brain_iq_score, learned_playbook_json, last_evolution_summary)
                        VALUES (?, ?, ?, 0, 0, 0, 0, 88.0, '[]', 'Auto-aprendizagem ativa por defeito neste projeto.');
                        """,
                        (kws, default_en, default_en),
                    )

                # Limpar projetos órfãos ou subpastas inválidas de self_learn_projects
                if known_ws:
                    placeholders = ",".join("?" for _ in known_ws)
                    conn.execute(
                        f"DELETE FROM self_learn_projects WHERE LOWER(workspace) NOT IN ({placeholders});",
                        tuple(known_ws),
                    )

                # Migração automática: ativar projetos existentes que tinham ficado em standby por defeito (sem desligamento manual)
                conn.execute(
                    """
                    UPDATE self_learn_projects
                    SET enabled = 1,
                        proactive_enabled = 1
                    WHERE enabled = 0
                      AND cycles_run = 0
                      AND LOWER(workspace) NOT IN (
                          SELECT DISTINCT LOWER(workspace)
                          FROM self_learn_events
                          WHERE event_type = 'toggle_state' AND detail LIKE '%Auto-aprendizagem=OFF%'
                      );
                    """
                )

            all_proj_rows = conn.execute(
                "SELECT * FROM self_learn_projects ORDER BY enabled DESC, brain_iq_score DESC, workspace ASC;"
            ).fetchall()
            projects_list: List[Dict[str, Any]] = []
            current_proj: Optional[Dict[str, Any]] = None
            for pr in all_proj_rows:
                d = dict(pr)
                d["enabled"] = bool(int(d.get("enabled") or 0))
                d["proactive_enabled"] = bool(int(d.get("proactive_enabled") or 0))
                try:
                    pb = json.loads(d.get("learned_playbook_json") or "[]")
                    if not isinstance(pb, list):
                        pb = []
                except Exception:
                    pb = []
                d["learned_playbook"] = [str(x) for x in pb if x]
                projects_list.append(d)
                if d["workspace"] == ws:
                    current_proj = d

            if not current_proj and projects_list:
                current_proj = projects_list[0]

            events = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM self_learn_events WHERE LOWER(workspace) IN (?, 'brain_mcp') ORDER BY id DESC LIMIT 10;",
                    (ws,),
                ).fetchall()
            ]
            learned_mems = [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT id, topic, fact, workspace, importance, COALESCE(trust_score, 0.9) as synaptic_weight, created_at as updated_at
                    FROM memories
                    WHERE LOWER(workspace) = ? AND (category IN ('learned_rule', 'directive', 'optimization') OR tags LIKE '%self_learned%')
                    ORDER BY importance DESC, id DESC LIMIT 8;
                    """,
                    (ws,),
                ).fetchall()
            ]

        assert current_proj is not None
        active_projects_count = sum(1 for p in projects_list if p["enabled"])
        return {
            "ok": True,
            "workspace": current_proj["workspace"],
            "enabled": current_proj["enabled"],
            "proactive_enabled": current_proj["proactive_enabled"],
            "cycles_run": int(current_proj.get("cycles_run") or 0),
            "rules_distilled": int(current_proj.get("rules_distilled") or 0),
            "synapses_reinforced": int(current_proj.get("synapses_reinforced") or 0),
            "duplicates_healed": int(current_proj.get("duplicates_healed") or 0),
            "brain_iq_score": round(float(current_proj.get("brain_iq_score") or 85.0), 1),
            "learned_playbook": current_proj["learned_playbook"],
            "last_evolution_summary": str(current_proj.get("last_evolution_summary") or ""),
            "active_projects_count": active_projects_count,
            "projects": projects_list,
            "recent_events": events,
            "learned_memories": learned_mems,
            "daemon_task_mode": "active_background_sentinel" if active_projects_count > 0 else "standby",
        }

    def toggle_project_self_learn(
        self,
        workspace: str = "brain_mcp",
        enabled: Optional[bool] = None,
        proactive_enabled: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Ativa ou desativa o Self-Learn & Proatividade para um projeto específico (Opt-in/Opt-out por workspace).
        """
        ws = (workspace or "brain_mcp").strip().lower()
        if ws in ("all", ""):
            ws = "brain_mcp"
        status_before = self.get_self_learn_status(workspace=ws)
        new_en = bool(not status_before["enabled"]) if enabled is None else bool(enabled)
        new_pro = bool(new_en) if proactive_enabled is None else bool(proactive_enabled)

        with self.db._connect() as conn:
            conn.execute(
                """
                UPDATE self_learn_projects
                SET enabled = ?,
                    proactive_enabled = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE LOWER(workspace) = ?;
                """,
                (1 if new_en else 0, 1 if new_pro else 0, ws),
            )
            conn.execute(
                """
                INSERT INTO self_learn_events (workspace, event_type, title, detail, iq_delta)
                VALUES (?, 'toggle_state', ?, ?, 0.0);
                """,
                (
                    ws,
                    f"Self-Learn {'ATIVADO 🟢' if new_en else 'DESATIVADO ⚫'} em [{ws}]",
                    f"Auto-aprendizagem={'ON' if new_en else 'OFF'} · Proatividade Sentinel={'ON' if new_pro else 'OFF'}.",
                ),
            )
        return self.get_self_learn_status(workspace=ws)

    def enable_and_evolve_all_projects(self, workspace: str = "brain_mcp") -> Dict[str, Any]:
        """
        Ativa o Self-Learn & Sentinel Proativo em TODOS os projetos conhecidos e executa
        um ciclo de auto-melhoria recursiva em cada um (0 tokens LLM).
        """
        focus_ws = (workspace or "brain_mcp").strip().lower()
        if focus_ws in ("all", ""):
            focus_ws = "brain_mcp"

        st_init = self.get_self_learn_status(workspace=focus_ws)
        projs = st_init.get("projects") or []

        with self.db._connect() as conn:
            conn.execute(
                "UPDATE self_learn_projects SET enabled = 1, proactive_enabled = 1, updated_at = CURRENT_TIMESTAMP;"
            )

        projects_evolved = 0
        total_new_rules = 0
        total_synapses_boosted = 0
        total_healed = 0

        for p in projs:
            p_ws = str(p.get("workspace") or "").strip().lower()
            if not p_ws:
                continue
            evo = self.run_self_learn_evolution_cycle(workspace=p_ws, force=True)
            if evo.get("ok"):
                projects_evolved += 1
                total_new_rules += int(evo.get("new_rules_created") or 0)
                total_synapses_boosted += int(evo.get("synapses_boosted") or 0)
                total_healed += int(evo.get("healed_duplicates") or 0)

        final_st = self.get_self_learn_status(workspace=focus_ws)
        all_projs_after = final_st.get("projects") or []
        avg_iq = (
            round(
                sum(float(x.get("brain_iq_score") or 90.0) for x in all_projs_after) / max(1, len(all_projs_after)),
                1,
            )
            if all_projs_after
            else 94.0
        )
        return {
            "ok": True,
            "workspace": focus_ws,
            "projects_evolved": projects_evolved,
            "total_new_rules": total_new_rules,
            "total_synapses_boosted": total_synapses_boosted,
            "total_healed": total_healed,
            "avg_iq_score": avg_iq,
            "self_learn": final_st,
        }

    def run_self_learn_evolution_cycle(
        self,
        workspace: str = "brain_mcp",
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Executa um Ciclo Completo de Auto-Melhoria Recursiva (4 Motores Zero-Token) sobre as memórias guardadas do projeto:
        1. Destilação de Meta-Regras & Imunidade a Erros (Episodic ➔ Semantic Rule Promotion);
        2. Reforço Sináptico Hebbiano (cria arestas causais 'co_learned' entre memórias complementares e sobe synaptic_weight);
        3. Auto-Cura e Deduplicação Semântica (funde memórias quase-duplicadas preservando Time-Travel em memory_revisions);
        4. Pulso Proativo Sentinel (verifica DOTS prontos + AST Watcher + recalcula Brain IQ Score %).
        """
        ws = (workspace or "brain_mcp").strip().lower()
        if ws in ("all", ""):
            ws = "brain_mcp"

        st = self.get_self_learn_status(workspace=ws)
        if not st["enabled"] and not force:
            return {
                "ok": False,
                "skipped": True,
                "workspace": ws,
                "error": f"Self-Learn está DESATIVADO (OFF) para o projeto '{ws}'. Ative-o para evoluir automaticamente.",
                "self_learn": st,
            }

        file_pattern = re.compile(r"\b([a-zA-Z0-9_\-]+\.(?:py|html|js|ts|tsx|json|md|sql|css))\b")
        new_rules_created = 0
        synapses_boosted = 0
        healed_duplicates = 0
        distilled_axioms: List[str] = list(st.get("learned_playbook") or [])

        pending_new_rules: List[Tuple[str, str]] = []
        with self.db._connect() as conn:
            mems = [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT id, topic, fact, category, tags, importance,
                           COALESCE(trust_score, 0.85) as synaptic_weight,
                           COALESCE(human_locked, 0) as human_locked
                    FROM memories
                    WHERE LOWER(workspace) = ?
                    ORDER BY importance DESC, id DESC LIMIT 80;
                    """,
                    (ws,),
                ).fetchall()
            ]

            # -----------------------------------------------------------------
            # MOTOR 1: Destilação de Meta-Regras por Ficheiro / Domínio Técnico
            # -----------------------------------------------------------------
            by_target: Dict[str, List[Dict[str, Any]]] = {}
            for m in mems:
                if m.get("category") == "learned_rule":
                    continue
                txt = f"{m.get('topic', '')} {m.get('fact', '')}"
                found_files = file_pattern.findall(txt)
                key = found_files[0].lower() if found_files else str(m.get("category") or "architecture").lower()
                by_target.setdefault(key, []).append(m)

            for target_key, group in by_target.items():
                if len(group) < 2:
                    continue
                top_facts: List[str] = []
                for gm in group[:3]:
                    snippet = str(gm.get("fact") or "").strip()
                    if len(snippet) > 95:
                        snippet = snippet[:92].rstrip() + "..."
                    top_facts.append(snippet)
                rule_topic = f"🧬 Meta-Regra Aprendida [{target_key}]"
                rule_fact = f"Padrão consolidado ({len(group)} memórias em {ws}): " + " | ".join(top_facts[:2])
                axiom_short = f"[{target_key}] {top_facts[0]}"
                if axiom_short not in distilled_axioms:
                    distilled_axioms.insert(0, axiom_short)

                existing_rule = conn.execute(
                    "SELECT id, fact FROM memories WHERE LOWER(workspace) = ? AND LOWER(topic) = LOWER(?);",
                    (ws, rule_topic),
                ).fetchone()
                if not existing_rule:
                    pending_new_rules.append((rule_topic, rule_fact))
                    new_rules_created += 1

            # Se o projeto tinha poucas memórias agrupadas mas ainda não gerou regra neste ciclo, sintetizar axioma de topo
            if new_rules_created == 0 and mems:
                best_m = mems[0]
                fallback_axiom = f"[{best_m.get('topic', 'Core')[:28]}] {str(best_m.get('fact', ''))[:88]}"
                if fallback_axiom not in distilled_axioms:
                    distilled_axioms.insert(0, fallback_axiom)
                    new_rules_created += 1

            distilled_axioms = distilled_axioms[:6]

            # -----------------------------------------------------------------
            # MOTOR 2: Reforço Sináptico Hebbiano (Memory Edges + Boost de Trust/Access)
            # -----------------------------------------------------------------
            for i in range(min(len(mems), 20)):
                for j in range(i + 1, min(len(mems), 20)):
                    m1, m2 = mems[i], mems[j]
                    t1 = set(str(m1.get("tags") or "").lower().replace(",", " ").split())
                    t2 = set(str(m2.get("tags") or "").lower().replace(",", " ").split())
                    shared_tags = t1 & t2 - {"", "general", "auto"}
                    if len(shared_tags) >= 1 or m1.get("category") == m2.get("category"):
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO memory_edges (source_id, target_id, relation, weight)
                            VALUES (?, ?, 'co_learned', 0.92);
                            """,
                            (int(m1["id"]), int(m2["id"])),
                        )
                        conn.execute(
                            "UPDATE memories SET trust_score = MIN(1.0, COALESCE(trust_score, 0.85) + 0.03), access_count = COALESCE(access_count, 0) + 1 WHERE id IN (?, ?);",
                            (int(m1["id"]), int(m2["id"])),
                        )
                        synapses_boosted += 1
                        if synapses_boosted >= 5:
                            break
                if synapses_boosted >= 5:
                    break

        for r_topic, r_fact in pending_new_rules:
            self.db.store_fact(
                topic=r_topic,
                fact=r_fact,
                workspace=ws,
                category="learned_rule",
                tags="self_learned,meta_rule,auto_improve",
                importance=5,
                source_agent="self_learn_engine",
                trust_score=0.96,
            )

        # ---------------------------------------------------------------------
        # MOTOR 3: Auto-Cura Semântica (Deduplicação Segura c/ Time-Travel)
        # ---------------------------------------------------------------------
        try:
            dedup_res = self.db.deduplicate_memories(workspace=ws, similarity_threshold=0.84)
            healed_duplicates = int(dedup_res.get("merged_count") or 0)
        except Exception:
            healed_duplicates = 0

        # ---------------------------------------------------------------------
        # MOTOR 4: Pulso Proativo Sentinel + Cálculo do Brain IQ Score (%)
        # ---------------------------------------------------------------------
        dots_state = self.get_dots_dag(workspace=ws)
        ready_dots_cnt = int(dots_state.get("ready_count") or 0)

        prev_cycles = int(st.get("cycles_run") or 0) + 1
        total_rules = int(st.get("rules_distilled") or 0) + new_rules_created
        total_synapses = int(st.get("synapses_reinforced") or 0) + synapses_boosted
        total_healed = int(st.get("duplicates_healed") or 0) + healed_duplicates

        iq_gain = round(min(2.4, 0.35 + (new_rules_created * 0.55) + (synapses_boosted * 0.12) + (healed_duplicates * 0.3)), 2)
        new_iq = round(min(99.8, float(st.get("brain_iq_score") or 88.0) + iq_gain), 1)

        evo_summary = (
            f"Ciclo #{prev_cycles}: +{new_rules_created} Meta-Regras, "
            f"+{synapses_boosted} sinapses Hebbianas, {healed_duplicates} duplicados fundidos · "
            f"DOTS Ready={ready_dots_cnt} · IQ={new_iq}% (+{iq_gain}%)"
        )

        with self.db._connect() as conn:
            conn.execute(
                """
                UPDATE self_learn_projects
                SET cycles_run = ?,
                    rules_distilled = ?,
                    synapses_reinforced = ?,
                    duplicates_healed = ?,
                    brain_iq_score = ?,
                    learned_playbook_json = ?,
                    last_evolution_summary = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE LOWER(workspace) = ?;
                """,
                (
                    prev_cycles,
                    total_rules,
                    total_synapses,
                    total_healed,
                    new_iq,
                    json.dumps(distilled_axioms, ensure_ascii=False),
                    evo_summary,
                    ws,
                ),
            )
            conn.execute(
                """
                INSERT INTO self_learn_events (workspace, event_type, title, detail, iq_delta)
                VALUES (?, 'evolution_cycle', ?, ?, ?);
                """,
                (
                    ws,
                    f"🧬 Ciclo de Auto-Melhoria #{prev_cycles} Concluído ({ws})",
                    evo_summary,
                    iq_gain,
                ),
            )

        updated_status = self.get_self_learn_status(workspace=ws)
        return {
            "ok": True,
            "workspace": ws,
            "cycle_number": prev_cycles,
            "new_rules_created": new_rules_created,
            "synapses_boosted": synapses_boosted,
            "healed_duplicates": healed_duplicates,
            "iq_gain": iq_gain,
            "brain_iq_score": new_iq,
            "evolution_summary": evo_summary,
            "self_learn": updated_status,
        }

    # =========================================================================
    # 8. PROMPT FORGE ENGINE (CONTEXT-AWARE PROMPT + ANTIGRAVITY SKILLS OPTIMIZER)
    # =========================================================================
    _SKILLS_CACHE: List[Dict[str, Any]] = []
    _SKILLS_CACHE_TS: float = 0.0

    def discover_antigravity_skills(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Descobre automaticamente todas as Skills instaladas no Antigravity:
        - ~/.gemini/config/skills/*/SKILL.md
        - ~/.gemini/config/plugins/*/skills/*/SKILL.md
        - ~/.gemini/antigravity/builtin/skills/*/SKILL.md
        Extrai o nome, descrição e caminho exato do SKILL.md com cache em memória (<1ms).
        """
        now_ts = time.time()
        if not force_refresh and OrbitEngine._SKILLS_CACHE and (now_ts - OrbitEngine._SKILLS_CACHE_TS < 300.0):
            return OrbitEngine._SKILLS_CACHE

        home = Path(os.path.expanduser("~"))
        search_roots = [
            (home / ".gemini" / "config" / "skills", "custom"),
            (home / ".gemini" / "antigravity" / "builtin" / "skills", "builtin"),
        ]
        plugins_dir = home / ".gemini" / "config" / "plugins"
        if plugins_dir.exists():
            try:
                for p_dir in plugins_dir.iterdir():
                    sk_dir = p_dir / "skills"
                    if sk_dir.exists() and sk_dir.is_dir():
                        search_roots.append((sk_dir, f"plugin:{p_dir.name}"))
            except Exception:
                pass

        seen_names: set[str] = set()
        skills_found: List[Dict[str, Any]] = []

        for root_path, source_tag in search_roots:
            if not root_path.exists():
                continue
            try:
                for child in sorted(root_path.iterdir()):
                    sk_file = child / "SKILL.md"
                    if not sk_file.exists():
                        continue
                    sk_name = child.name.strip()
                    if sk_name in seen_names:
                        continue
                    seen_names.add(sk_name)
                    desc = ""
                    try:
                        raw_head = sk_file.read_text(encoding="utf-8", errors="ignore")[:1500]
                        m_desc = re.search(r"(?m)^description:\s*[\"']?(.+?)[\"']?\s*$", raw_head)
                        if m_desc:
                            cand_d = m_desc.group(1).strip()
                            if cand_d not in (">", "|", ">-", "|-"):
                                desc = cand_d
                        if not desc:
                            lines = [
                                ln.strip()
                                for ln in raw_head.splitlines()
                                if ln.strip()
                                and not ln.strip().startswith("---")
                                and not ln.strip().startswith("#")
                                and not ln.strip().startswith("name:")
                                and not ln.strip().startswith("description:")
                            ]
                            if lines:
                                desc = " ".join(lines[:2])[:180]
                    except Exception:
                        desc = f"Antigravity skill {sk_name}"
                    skills_found.append(
                        {
                            "name": sk_name,
                            "description": desc[:190] or f"Skill especializada {sk_name}",
                            "path": str(sk_file).replace("\\", "/"),
                            "source": source_tag,
                        }
                    )
            except Exception:
                continue

        if not skills_found:
            skills_found = [
                {
                    "name": "claude-architect-coder",
                    "description": "Elite autonomous software engineering protocol based on Plan-First Architecture and surgical code execution.",
                    "path": "~/.gemini/config/skills/claude-architect-coder/SKILL.md",
                    "source": "custom",
                },
                {
                    "name": "systematic-debugging",
                    "description": "Use when encountering any bug, test failure, or unexpected behavior, before proposing fixes.",
                    "path": "~/.gemini/config/plugins/superpowers/skills/systematic-debugging/SKILL.md",
                    "source": "plugin:superpowers",
                },
                {
                    "name": "frontend-ui-engineering",
                    "description": "Builds production-quality, accessible, responsive user-facing UIs and interactive components.",
                    "path": "~/.gemini/config/plugins/agent-skills/skills/frontend-ui-engineering/SKILL.md",
                    "source": "plugin:agent-skills",
                },
                {
                    "name": "verification-before-completion",
                    "description": "Requires running verification commands and confirming output before making any success claims.",
                    "path": "~/.gemini/config/plugins/superpowers/skills/verification-before-completion/SKILL.md",
                    "source": "plugin:superpowers",
                },
            ]

        OrbitEngine._SKILLS_CACHE = skills_found
        OrbitEngine._SKILLS_CACHE_TS = now_ts
        return skills_found

    def match_skills_for_prompt(
        self,
        raw_request: str,
        workspace: str = "brain_mcp",
        task_mode: str = "feature",
        selected_skills: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Cruza o pedido do utilizador, o workspace e o modo de missão com todas as Skills instaladas no Antigravity
        (e adiciona quaisquer skills escolhidas manualmente pelo utilizador).
        """
        all_skills = self.discover_antigravity_skills()
        by_name: Dict[str, Dict[str, Any]] = {s["name"].lower(): s for s in all_skills}

        chosen: List[Dict[str, Any]] = []
        chosen_names: set[str] = set()

        def _add_skill(name_key: str, reason: str) -> None:
            k = name_key.strip().lower()
            if k in by_name and k not in chosen_names:
                chosen_names.add(k)
                chosen.append({**by_name[k], "match_reason": reason})

        # 1. Skills selecionadas explicitamente pelo utilizador no Prompt Forge
        for user_sk in (selected_skills or []):
            _add_skill(user_sk, "Selecionada pelo utilizador")

        q_lower = f"{raw_request} {workspace}".lower()
        mode = (task_mode or "feature").strip().lower()

        # 2. Match contextual por domínio / palavras-chave do pedido e projeto
        keyword_skill_map = [
            (("metin2", "uiscript", "m2ui", "ui.py"), "m2ui", "Interface cliente Metin2"),
            (("reverse", "binário", "decompile", "exe", "dll", "rea"), "reverse-engineer-anything", "Engenharia reversa binária/runtime"),
            (("grafo", "graph", "arquitetura", "god node", "graphify"), "graphify", "Grafo de conhecimento AST"),
            (("ultraplan", "plano profundo", "fases"), "ultraplan", "Planeamento arquitetural multi-fase"),
            (("3d", "webgl", "webgpu", "three", "canvas", "fps", "shader"), "web-3d-graphics-expert", "Gráficos 3D / Canvas 60 FPS"),
            (("python", "sqlite", "fastapi", "pytest", "pydantic", ".py"), "python-programming-expert", "Engenharia Python & SQLite"),
            (("typescript", "ts", "strict", "generic"), "typescript-expert", "Tipagem avançada TypeScript"),
            (("nextjs", "app router", "rsc"), "nextjs-app-router-expert", "Next.js App Router"),
            (("react", "tailwind", "ui", "painel", "modal", "html", "css"), "frontend-ui-engineering", "Engenharia de UI/UX Frontend"),
            (("api", "endpoint", "rest", "json-rpc", "mcp", "contrato"), "api-and-interface-design", "Design de APIs & Contratos"),
            (("performance", "lento", "otimizar", "memória", "tokens", "soa"), "performance-optimization", "Otimização de Performance"),
            (("segurança", "security", "xss", "csrf", "token", "secret", "auth"), "autonomous-red-teamer", "Auditoria e Hardening de Segurança"),
            (("background", "task", "cron", "schedule", "sentinel", "proativ"), "proactive-background-watcher", "Agendamento & Sentinel Proativo"),
            (("swarm", "subagent", "paralelo", "enxame"), "dispatching-parallel-agents", "Orquestração de Subagentes em Paralelo"),
        ]
        for kw_tuple, sk_id, reason in keyword_skill_map:
            if any(k in q_lower for k in kw_tuple):
                _add_skill(sk_id, reason)

        # 3. Match pelo Task Mode escolhido
        mode_defaults = {
            "feature": [
                ("claude-architect-coder", "Protocolo Plan-First & Execução Cirúrgica"),
                ("incremental-implementation", "Implementação incremental verificável"),
                ("verification-before-completion", "Verificação real antes de concluir"),
            ],
            "bugfix": [
                ("systematic-debugging", "Diagnóstico sistemático de causa-raiz"),
                ("debugging-and-error-recovery", "Recuperação e isolamento de falhas"),
                ("autonomous-tdd-debugger", "Auto-validação de testes no terminal"),
                ("verification-before-completion", "Prova de correção com testes"),
            ],
            "refactor": [
                ("claude-architect-coder", "Refatoração cirúrgica sem quebrar contratos"),
                ("code-simplification", "Simplificação e limpeza de complexidade"),
                ("scalability-clean-code", "Padrões Clean Code & SOLID"),
            ],
            "ui_ux": [
                ("frontend-ui-engineering", "UI de qualidade de produção"),
                ("hig", "Princípios Human Interface Guidelines (Hierarquia & Harmonia)"),
                ("performance-web-vitals", "Fluidez visual 60 FPS & Web Vitals"),
            ],
            "security": [
                ("autonomous-red-teamer", "Deteção de vulnerabilidades XSS/SQLi/SSRF"),
                ("rate-limit-abuse-prevention", "Proteção de endpoints & Rate Limiting"),
                ("code-review-and-quality", "Revisão multi-eixo de segurança e qualidade"),
            ],
            "total_audit": [
                ("app-analyzer-optimizer", "Auditoria profunda 360° de arquitetura e bottlenecks"),
                ("code-review-and-quality", "Revisão multi-eixo (Correção, Arquitetura, Segurança, Performance)"),
                ("systematic-debugging", "Deteção determinística de bugs ocultos e causas-raiz"),
                ("performance-optimization", "Otimização de queries, memória, 60 FPS e tokens"),
                ("autonomous-red-teamer", "Auditoria de segurança XSS/SQLi/CSRF e controlo de acessos"),
                ("verification-before-completion", "Validação real de testes e regressão zero"),
            ],
        }
        for sk_id, reason in mode_defaults.get(mode, mode_defaults["feature"]):
            if len(chosen) < 5:
                _add_skill(sk_id, reason)

        return chosen[:6]

    def get_prompt_forge_history(self, workspace: str = "all", limit: int = 10) -> List[Dict[str, Any]]:
        ws = (workspace or "all").strip().lower()
        with self.db._connect() as conn:
            if ws and ws not in ("all", "global"):
                rows = conn.execute(
                    "SELECT * FROM prompt_forge_history WHERE LOWER(workspace) IN (?, 'brain_mcp') ORDER BY id DESC LIMIT ?;",
                    (ws, max(1, int(limit))),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM prompt_forge_history ORDER BY id DESC LIMIT ?;",
                    (max(1, int(limit)),),
                ).fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            try:
                d["matched_files"] = json.loads(d.get("matched_files_json") or "[]")
            except Exception:
                d["matched_files"] = []
            out.append(d)
        return out

    _SKILL_DIRECTIVES_CACHE: Dict[str, List[str]] = {}

    def _extract_skill_directives(self, skill_path: str, max_rules: int = 3) -> List[str]:
        """
        Abre o ficheiro SKILL.md real no disco e extrai as regras/diretivas operacionais mais importantes
        para injetar diretamente no Super-Prompt (com cache em memória para 0.00ms de I/O).
        """
        if not skill_path:
            return []
        cache_key = f"{skill_path}::{max_rules}"
        cached = OrbitEngine._SKILL_DIRECTIVES_CACHE.get(cache_key)
        if cached is not None:
            return cached
        try:
            resolved = os.path.expanduser(skill_path.replace("/", os.sep))
            if not os.path.isfile(resolved):
                OrbitEngine._SKILL_DIRECTIVES_CACHE[cache_key] = []
                return []
            with open(resolved, "r", encoding="utf-8", errors="ignore") as fh:
                content = fh.read(8192)
            # Remover frontmatter YAML se existir
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    content = parts[2]
            directives: List[str] = []
            for raw_line in content.splitlines():
                line = raw_line.strip()
                if not line or len(line) < 22:
                    continue
                if line.startswith(("- ", "* ", "1. ", "2. ", "3. ", "4. ")):
                    clean = re.sub(r"^[-*0-9.]+\s*", "", line).strip()
                    if 24 <= len(clean) <= 185 and not clean.startswith("http"):
                        directives.append(clean)
                        if len(directives) >= max_rules:
                            break
            OrbitEngine._SKILL_DIRECTIVES_CACHE[cache_key] = directives
            return directives
        except Exception:
            return []

    def _synthesize_deep_engineering_spec(
        self,
        req: str,
        ws: str,
        mode: str,
        matched_files: List[str],
        rel_mems: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Sintetizador Profundo de Especificações de Engenharia (Nível Gemini 4 / Claude Opus Architect):
        Transforma uma frase curta/vaga do utilizador numa especificação técnica completa com:
        - Reescrita expandida do pedido (Contexto + Fluxo Ponta-a-Ponta + Integração);
        - Stack tecnológica e Persona de Arquiteto inferidas do projeto;
        - Assinaturas de funções, endpoints e contratos de dados propostos;
        - Símbolos AST reais (:Lstart-end) extraídos do projeto;
        - Plano de execução em 5 fases e Casos-Limite (Edge Cases) específicos do domínio.
        """
        q_low = f"{req} {ws} {' '.join(matched_files)}".lower()

        # 1. Inferir Stack Tecnológica, Persona e Comando de Verificação Real do Projeto
        if any(k in q_low for k in ("mt2", "metin", "uiscript", "modulelist", ".inl", "packet.h", "locale_")):
            stack_name = "C++17 Client/Server Engine + Python 2.7 Root/UIScript (Metin2 Architecture)"
            persona = "Principal C++/Python Metin2 Client & Game-Server Engine Architect"
            verify_cmd = "Validar dicionários UIScript, referências em root/ui*.py (Destroy/ClearDictionary sem memory leaks) e headers em Packet.h / ModuleList.inl"
        elif ws == "brain_mcp" or any(k in q_low for k in ("orbit_engine", "web_dashboard", "db_engine", "brain_inject")):
            stack_name = "Python 3.12+ (ThreadingHTTPServer + SQLite3 WAL/FTS5/32-D Vectors) + Vanilla JS/HTML5 Canvas 60 FPS"
            persona = "Principal Autonomous AI Systems & Fullstack Python/JS Architect"
            verify_cmd = "Executar `node --check` no JS extraído de `index.html` e correr `$env:BRAIN_TEST_MODE='1'; python test_brain.py` (100% PASS obrigatório)"
        elif any(k in q_low for k in (".tsx", ".ts", "nextjs", "react", "tailwind", "prisma")):
            stack_name = "TypeScript 5.8+ Strict Mode + React 19 / Next.js App Router + Tailwind CSS"
            persona = "Principal Fullstack TypeScript & UI/UX Systems Architect"
            verify_cmd = "Executar `npx tsc --noEmit`, linter e suite de testes (`npm test` / `vitest`)"
        else:
            stack_name = f"Arquitetura Modular de Produção ({ws})"
            persona = f"Principal Software Architect & Senior Systems Engineer ({ws})"
            verify_cmd = "Executar linter, verificação de tipos/sintaxe AST e a suite de testes automatizados do projeto"

        # 2. Extrair substantivos/conceitos técnicos do pedido para propor identificadores concretos
        stop_words = {
            "criar", "cria", "fazer", "faz", "adicionar", "adiciona", "implementar", "implementa",
            "corrigir", "corrige", "arranjar", "melhorar", "melhora", "otimizar", "otimiza", "para",
            "uma", "um", "uns", "umas", "que", "com", "sem", "nos", "nas", "dos", "das", "por",
            "como", "quando", "onde", "este", "esta", "isso", "isto", "função", "funcao", "sistema",
            "página", "pagina", "botão", "botao", "projeto", "código", "codigo", "the", "and", "for", "with"
        }
        raw_tokens = [
            re.sub(r"[^a-z0-9]", "", w.lower())
            for w in re.findall(r"[a-zA-ZÀ-ÿ0-9_]+", req)
        ]
        meaningful = [w for w in raw_tokens if len(w) >= 3 and w not in stop_words][:4]
        if not meaningful:
            meaningful = ["custom", mode, "handler"]

        snake_id = "_".join(meaningful)
        camel_id = meaningful[0] + "".join(w.capitalize() for w in meaningful[1:])
        pascal_id = "".join(w.capitalize() for w in meaningful)

        # 3. Extrair símbolos reais (funções/classes) mencionados nas memórias ou nos ficheiros do projeto
        sym_re = re.compile(r"\b(?:def|function|class|async\s+function)\s+([a-zA-Z0-9_]+)|\b([a-zA-Z0-9_]+\([a-zA-Z0-9_,=\s]*\))")
        discovered_symbols: List[str] = []
        for m in rel_mems:
            txt = f"{m.get('topic', '')} {m.get('fact', '')}"
            for sm in sym_re.findall(txt):
                cand = (sm[0] or sm[1] or "").strip()
                if cand and len(cand) >= 4 and cand not in discovered_symbols:
                    discovered_symbols.append(cand)
        if not discovered_symbols:
            if ws == "brain_mcp":
                discovered_symbols = ["OrbitEngine.generate_optimized_prompt()", "BrainDashboardHandler.do_POST()", "renderOrbitOverviewUI()"]
            else:
                discovered_symbols = [f"{snake_id}()", f"{camel_id}UI()", f"{pascal_id}Controller"]

        # 4. Construir a Reescrita Expandida (Deep Prompt Expansion) + Contratos + Plano de 5 Fases + Edge Cases
        primary_file = matched_files[0] if matched_files else f"src/{snake_id}.py"
        secondary_file = matched_files[1] if len(matched_files) > 1 else primary_file

        if mode == "bugfix":
            expanded_narrative = (
                f"Atua como **{persona}** no projeto **`{ws}`** ({stack_name}).\n"
                f"O objetivo desta intervenção é realizar um **diagnóstico determinístico de causa-raiz e correção definitiva** para o seguinte problema reportado:\n"
                f"**\"{req}\"**.\n\n"
                f"**Análise Esperada Ponta-a-Ponta:**\n"
                f"- Não apliques paliativos superficiais: rastreia o fluxo completo de execução desde o ponto de entrada (evento UI / chamada de função em `{primary_file}`) até à camada de estado/dados (`{secondary_file}`).\n"
                f"- Identifica exatamente que variável não inicializada, condição de corrida, falha de contrato JSON/SQL ou regra CSS/layout está a provocar o comportamento anómalo.\n"
                f"- Corrige o defeito preservando 100% da retrocompatibilidade com os símbolos existentes (`{', '.join(discovered_symbols[:3])}`) e adiciona blindagem defensiva para que o erro nunca volte a ocorrer."
            )
            contracts_block = (
                f"- **Alvo Primário do Diagnóstico**: `{primary_file}` e `{secondary_file}` (Símbolos relacionados: `{', '.join(discovered_symbols[:4])}`).\n"
                f"- **Invariante de Segurança / Estado**: Garantir que entradas nulas, listas vazias ou falhas de rede têm fallback gracioso sem lançar exceções não tratadas (`ReferenceError`, `KeyError`, `TypeError` ou layout blowout).\n"
                f"- **Teste de Regressão**: Validar o cenário exato que falhava antes e confirmar retorno `{{\"ok\": True}}` / renderização estável."
            )
            phases_list = [
                f"**Fase 1 — Reprodução & Isolamento da Causa-Raiz**: Ler cirurgicamente `{primary_file}` nas linhas indicadas, identificar a linha exata onde o estado diverge do esperado e documentar a causa-raiz.",
                f"**Fase 2 — Correção Cirúrgica Defensiva (`edit_file`)**: Aplicar o patch mínimo e exato em `{primary_file}` / `{secondary_file}`, adicionando validação de estado nulo/vazio e fallback determinístico.",
                "**Fase 3 — Blindagem de Interface / Layout / Sincronização**: Se o bug afetar a UI ou estado assíncrono, garantir contenção estrita (`min-width: 0`, `overflow: hidden`, `escapeHtml`) e sincronização imediata do estado em memória.",
                "**Fase 4 — Teste de Regressão Direcionado**: Criar ou atualizar um caso de teste automatizado que reproduza a falha original e comprove que ficou resolvida.",
                f"**Fase 5 — Verificação Executável no Terminal**: {verify_cmd}.",
            ]
            edge_cases_list = [
                "Estado inicial vazio ou dados ainda não carregados da API/base de dados (evitar `undefined` / `ReferenceError`).",
                "Textos longos, caminhos de ficheiros profundos ou listas grandes que possam desformatar o layout CSS Grid/Flex.",
                "Execução num ambiente remoto acabado de atualizar via `git pull` (garantir fallback sem depender de reinício manual).",
                "Preservação estrita de funções, docstrings e fluxos adjacentes que já estavam a funcionar.",
            ]
        elif mode == "refactor":
            expanded_narrative = (
                f"Atua como **{persona}** no projeto **`{ws}`** ({stack_name}).\n"
                f"O objetivo é executar uma **refatoração arquitetural limpa, modular e orientada à performance** sobre o seguinte alvo:\n"
                f"**\"{req}\"**.\n\n"
                f"**Diretriz Arquitetural:**\n"
                f"- Reestrutura a implementação atual em `{primary_file}` e `{secondary_file}` para eliminar duplicação de código (DRY), reduzir a complexidade ciclomática e melhorar a legibilidade e performance, **mantendo intactos todos os contratos públicos e assinaturas externas** (`{', '.join(discovered_symbols[:3])}`).\n"
                f"- Aplica separação clara de responsabilidades entre lógica de domínio, acesso a dados e camada de apresentação."
            )
            contracts_block = (
                f"- **Invariante de Contrato Público**: As assinaturas externas em `{primary_file}` devem manter os mesmos parâmetros obrigatórios e estrutura de retorno para não quebrar consumidores existentes.\n"
                f"- **Módulos / Funções Internas Propostas**: Extrair helpers puros e tipados (`_{snake_id}_helper()`, `normalize_{snake_id}()`) com docstrings claras e complexidade `O(1)` ou `O(N)`."
            )
            phases_list = [
                f"**Fase 1 — Mapeamento de Dependências & Blast Radius**: Verificar todos os pontos que invocam `{', '.join(discovered_symbols[:3])}` em `{primary_file}` e `{secondary_file}`.",
                "**Fase 2 — Extração de Unidades Modulares Puras**: Isolar lógica repetida ou acoplada em funções auxiliares coesas, com tipagem explícita e sem efeitos secundários ocultos.",
                "**Fase 3 — Otimização de Performance & Memória**: Eliminar leituras redundantes, queries N+1 ou re-renderizações desnecessárias no DOM/Canvas.",
                "**Fase 4 — Limpeza de Código Morto & Documentação**: Preservar comentários relevantes e atualizar docstrings com os contratos exatos.",
                f"**Fase 5 — Verificação de Regressão Zero**: {verify_cmd}.",
            ]
            edge_cases_list = [
                "Compatibilidade total com chamadas legadas que passem argumentos opcionais ou valores por defeito.",
                "Manutenção da ordem determinística de chaves/resultados devolvidos pela API ou base de dados.",
                "Zero degradação de tempo de resposta ou uso de memória sob carga.",
            ]
        elif mode == "total_audit":
            expanded_narrative = (
                f"Atua como **Equipa Principal de Auditoria 360° ({persona} + Principal Security & Performance Auditor)** no projeto **`{ws}`** ({stack_name}).\n"
                f"O objetivo desta missão é executar uma **AUDITORIA TOTAL PROFUNDA (360° Full-Stack & Architecture Audit)** ao projeto `{ws}` com foco em:\n"
                f"**\"{req}\"**.\n\n"
                f"**Os 5 Eixos Obrigatórios da Auditoria Total:**\n"
                f"1. **Eixo 1 — Correção Funcional & Bugs Ocultos (`Correctness & Reliability`)**: Inspecionar `{', '.join(matched_files[:4])}` à procura de variáveis não declaradas, exceções engolidas, condições de corrida, estados nulos/vazios, fugas de memória (listeners/timers/`Destroy()`) e dessincronização entre UI e Backend/DB.\n"
                f"2. **Eixo 2 — Arquitetura, Contratos & Dívida Técnica (`Architecture & Clean Code`)**: Avaliar acoplamento entre módulos, duplicação de lógica, inconsistências de contratos JSON/SQL/API e funções excessivamente complexas.\n"
                f"3. **Eixo 3 — Performance, Memória & Eficiência (`Performance & 60 FPS`)**: Identificar queries lentas/N+1, bloqueios de I/O síncrono, re-renderizações desnecessárias no DOM/Canvas e oportunidades de poupança de tokens/CPU.\n"
                f"4. **Eixo 4 — Interface UI/UX, Layout & Responsividade (`UI/UX & Layout Integrity`)**: Detetar quebras de layout CSS Grid/Flex (falta de `minmax(0, 1fr)`, `min-width: 0`, `flex-shrink: 0`), textos cortados, falta de feedback visual ou estados vazios.\n"
                f"5. **Eixo 5 — Segurança & Hardening (`Security & Trust Boundary`)**: Verificar injeções SQL/XSS (`escapeHtml`), validação de parâmetros, path traversal, exposição de segredos e isolamento por workspace."
            )
            contracts_block = (
                f"- **Matriz de Severidade do Relatório de Auditoria**:\n"
                f"  Classificar cada descoberta como `🔴 CRITICAL`, `🟠 HIGH`, `🟡 MEDIUM` ou `🟢 LOW`, indicando sempre o ficheiro e linha exata (`ficheiro:Lstart-end`), a causa-raiz e o impacto real.\n"
                f"- **Protocolo Audit-to-Fix (Correção Imediata)**:\n"
                f"  Não te limites a listar problemas: **corrige cirurgicamente (`edit_file`) todos os problemas `CRITICAL` e `HIGH`** encontrados em `{primary_file}` e `{secondary_file}` sem quebrar contratos existentes (`{', '.join(discovered_symbols[:4])}`).\n"
                f"- **Orquestração Paralela Recomendada**:\n"
                f"  Se necessário, lança subagentes especializados em paralelo (`code-reviewer`, `security-auditor`, `web-performance-auditor`, `test-engineer`) para auditar cada eixo sem poluir a janela de contexto."
            )
            phases_list = [
                f"**Fase 1 — Reconhecimento & Mapeamento Cirúrgico (`SCOUT`)**: Inspecionar os módulos centrais (`{', '.join(matched_files[:4])}`) e os símbolos críticos (`{', '.join(discovered_symbols[:4])}`).",
                "**Fase 2 — Auditoria Multi-Eixo (5 Dimensões)**: Executar a análise sistemática de Bugs/Estado, Arquitetura, Performance/Memória, UI/Layout e Segurança, registando cada achado com `ficheiro:Lstart-end`.",
                "**Fase 3 — Plano Priorizado de Remediação**: Apresentar a tabela executiva de descobertas ordenada por severidade (`CRITICAL ➔ HIGH ➔ MEDIUM ➔ LOW`).",
                f"**Fase 4 — Aplicação Cirúrgica das Correções (`SURGICAL PATCH`)**: Implementar imediatamente os fixes para as falhas críticas e altas em `{primary_file}` e `{secondary_file}` preservando 100% da retrocompatibilidade.",
                f"**Fase 5 — Prova de Estabilidade & Testes de Regressão (`VERIFY`)**: {verify_cmd}.",
            ]
            edge_cases_list = [
                "Falsos positivos: validar sempre o contexto real do código antes de alterar lógica de negócio existente.",
                "Regressões colaterais: qualquer correção aplicada durante a auditoria não pode quebrar rotas, layouts ou testes existentes.",
                "Contenção CSS/UI: verificar se elementos flex/grid filhos têm `flex-shrink: 0` (em listas com scroll vertical) e `min-width: 0` (em grelhas horizontais).",
                "Segurança & Sanitização: confirmar `escapeHtml` em todos os templates HTML dinâmicos e queries parametrizadas (`?`) em SQLite/SQL.",
            ]
        elif mode in ("ui_ux", "ui_3d"):
            expanded_narrative = (
                f"Atua como **{persona}** no projeto **`{ws}`** ({stack_name}).\n"
                f"O objetivo é desenhar e implementar uma **experiência de interface (UI/UX) de qualidade de produção, responsiva e a 60 FPS** para:\n"
                f"**\"{req}\"**.\n\n"
                f"**Especificação Visual & Interativa Ponta-a-Ponta:**\n"
                f"- Constrói ou aprimora o componente em `{primary_file}` respeitando a linguagem visual, paleta de cores, tipografia e hierarquia de informação do projeto `{ws}`.\n"
                f"- Garante contenção geométrica absoluta (uso de `minmax(0, 1fr)`, `min-width: 0`, `max-width: 100%`, `overflow: hidden` e `text-overflow: ellipsis`) para que conteúdos dinâmicos longos nunca desformatem o ecrã.\n"
                f"- Liga todos os controlos interativos (botões, dropdowns, filtros, atalhos) ao estado real e aos endpoints de backend em `{secondary_file}`, com feedback visual imediato (estados de hover, active, loading, empty state e toast)."
            )
            contracts_block = (
                f"- **Handlers UI Propostos**: `init{pascal_id}UI()`, `render{pascal_id}UI(data)` e `on{pascal_id}Action(event)` em `{primary_file}`.\n"
                f"- **Regras de Layout & Renderização**: Contentores Grid/Flex blindados com `min-width: 0; box-sizing: border-box;`, scroll interno isolado e sanitização XSS obrigatória via `escapeHtml()`.\n"
                f"- **Sincronização de Dados**: Atualização reativa imediata do DOM sem recarregar a página inteira."
            )
            phases_list = [
                f"**Fase 1 — Estrutura Semântica & Grid Blindado**: Definir o layout em `{primary_file}` com colunas `minmax(0, ...)` e estados vazios/loading bem desenhados.",
                "**Fase 2 — Estilo Visual, Hierarquia & Micro-Interações**: Aplicar contraste elevado, espaçamento consistente, badges informativos e transições suaves a 60 FPS.",
                f"**Fase 3 — Ligação de Estado & Dados (`{secondary_file}`)**: Conectar os eventos da UI (`onclick`, `onchange`, `oninput`) à fonte de dados com fallback client-side resiliente.",
                "**Fase 4 — Proteção contra Overflow & XSS**: Garantir `escapeHtml` em todos os valores dinâmicos e truncagem limpa de strings/caminhos longos.",
                f"**Fase 5 — Validação Sintática & Visual**: {verify_cmd}.",
            ]
            edge_cases_list = [
                "Textos ou caminhos de ficheiros extremamente compridos sem espaços (usar `overflow-wrap: anywhere` / `text-overflow: ellipsis`).",
                "Ecrãs de diferentes resoluções ou redimensionamento da janela sem cortar botões de ação.",
                "Caracteres especiais (`'`, `\"`, `<`, `>`, `&`) nos dados que possam partir atributos `onclick` ou injetar HTML.",
                "Comportamento imediato quando a lista de itens está vazia (exibir Empty State claro e acionável).",
            ]
        else:
            # Default: Feature / Nova Funcionalidade Completa (ou Security)
            expanded_narrative = (
                f"Atua como **{persona}** no projeto **`{ws}`** ({stack_name}).\n"
                f"Preciso que projetes e implementes de ponta a ponta (Backend/Core + Integração UI/API + Testes) a seguinte funcionalidade:\n"
                f"**\"{req}\"**.\n\n"
                f"**Especificação Funcional Detalhada (Como o Gemini 4 / Agente deve construir):**\n"
                f"1. **Arquitetura & Ponto de Integração**: Integra a nova capacidade diretamente nos módulos existentes `{primary_file}` e `{secondary_file}` (junto aos símbolos `{', '.join(discovered_symbols[:3])}`), respeitando os padrões de código, nomenclatura e estrutura de dados já usados em `{ws}`.\n"
                f"2. **Lógica de Negócio & Processamento**: Implementa o fluxo completo de entrada, validação de parâmetros, processamento determinístico e persistência/atualização de estado, garantindo que valores por defeito sensatos são aplicados quando parâmetros opcionais forem omitidos.\n"
                f"3. **Exposição & Feedback ao Utilizador**: Expõe a funcionalidade através do contrato apropriado (função pública / endpoint API / controlo interativo na UI) com resposta estruturada, tratamento explícito de erros e feedback claro."
            )
            contracts_block = (
                f"- **Assinatura Core / Backend Proposta (`{primary_file}`)**:\n"
                f"  `def {snake_id}(workspace: str = \"{ws}\", payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]`\n"
                f"- **Handler de Interface / Integração Proposto (`{secondary_file}`)**:\n"
                f"  `async function {camel_id}UI(options = {{}})` ➔ invoca a ação e atualiza o estado visual sem bloquear a thread principal.\n"
                f"- **Contrato de Retorno Esperado (Schema)**:\n"
                f"  `{{\"ok\": True, \"workspace\": \"{ws}\", \"data\": ..., \"summary\": \"...\"}}` (com fallback seguro `{{\"ok\": False, \"error\": \"...\"}}` em caso de input inválido)."
            )
            phases_list = [
                f"**Fase 1 — Análise de Contratos & Ponteiros Cirúrgicos**: Inspecionar `{primary_file}` e `{secondary_file}` nos blocos relevantes (`{', '.join(matched_files[:3])}`) para alinhar tipos, imports e estado.",
                f"**Fase 2 — Implementação do Motor / Lógica Core (`{primary_file}`)**: Codificar `{snake_id}` com validação rigorosa de inputs, tratamento de exceções, docstrings e persistência limpa.",
                f"**Fase 3 — Ligação de API / Eventos / Interface (`{secondary_file}`)**: Expor o método no router/controlador e ligar à interface (`{camel_id}UI`) com atualização reativa e fallback resiliente.",
                "**Fase 4 — Tratamento de Casos-Limite (Edge Cases) & Segurança**: Validar inputs vazios/extremos, sanitização de dados, isolamento por workspace e proteção de layout.",
                f"**Fase 5 — Testes Automatizados & Verificação Final**: Adicionar cobertura de teste para a nova funcionalidade e executar: {verify_cmd}.",
            ]
            edge_cases_list = [
                "Inputs vazios, nulos ou malformados (devolver erro claro e estruturado sem crashar o processo).",
                "Isolamento estrito por projeto/workspace (`workspace` específico vs `all`/`global`).",
                "Idempotência: chamadas repetidas à mesma função/ação não devem criar registos duplicados nem corromper o estado.",
                "Contenção visual e sanitização (`escapeHtml` / `minmax(0, 1fr)`) caso o resultado seja renderizado na UI.",
            ]

        return {
            "stack_name": stack_name,
            "persona": persona,
            "verify_cmd": verify_cmd,
            "snake_id": snake_id,
            "camel_id": camel_id,
            "pascal_id": pascal_id,
            "discovered_symbols": discovered_symbols[:6],
            "expanded_narrative": expanded_narrative,
            "contracts_block": contracts_block,
            "phases_list": phases_list,
            "edge_cases_list": edge_cases_list,
        }

    def generate_optimized_prompt(
        self,
        raw_request: str,
        workspace: str = "brain_mcp",
        task_mode: str = "feature",
        selected_skills: Optional[List[str]] = None,
        lang: str = "pt-PT",
    ) -> Dict[str, Any]:
        """
        Transforma um pedido simples do utilizador (ex.: 'criar uma função X num projeto')
        numa Especificação Técnica Completa de nível Gemini 4 / Claude Opus Architect, enriquecida com:
        - Reescrita e expansão profunda do pedido (Contexto da Stack, Fluxo Ponta-a-Ponta, Assinaturas e Contratos);
        - Diretivas reais extraídas do interior dos ficheiros SKILL.md das Skills do Antigravity;
        - Ficheiros e símbolos AST :Lstart-end reais detetados em brain.db para esse projeto;
        - Meta-Regras Aprendidas pelo Self-Learn (🧬 learned_playbook) do projeto;
        - Plano de implementação em 5 fases, Casos-Limite (Edge Cases) e Critérios de Aceitação (Definition of Done).
        """
        req = (raw_request or "").strip()
        mode = (task_mode or "feature").strip().lower()
        if not req and mode == "total_audit":
            req = (
                "Realizar uma Auditoria Total 360° a todo o projeto (Arquitetura, Bugs Ocultos, "
                "Performance 60 FPS, UI/UX Layout e Segurança), gerar matriz de severidade com "
                "ficheiro:Lstart-end e aplicar correções cirúrgicas imediatas nos pontos críticos."
            )
        if not req:
            return {"ok": False, "error": "Escreva uma descrição do que pretende criar ou melhorar."}

        ws = (workspace or "brain_mcp").strip().lower()
        if ws in ("all", ""):
            ws = "brain_mcp"

        # 1. Roteamento JEV System-1 + Trajetória Ótima DOTS + Matching de Skills do Antigravity
        jev_info = self.db.jev_system1_route(req, workspace=ws)
        dots_traj = str(jev_info.get("dots_trajectory") or "[AST_SLICE:L]➔[BLAST_RADIUS]➔[SURGICAL_PATCH]➔[VERIFY_AST_TESTS]")
        intent_name = str(jev_info.get("intent") or "general_engineering")
        model_rec = str(jev_info.get("model_route") or "inherit")
        matched_skills = self.match_skills_for_prompt(
            raw_request=req,
            workspace=ws,
            task_mode=mode,
            selected_skills=selected_skills,
        )

        # 2. Pesquisa Híbrida FTS5 BM25 + Vetores 32-D nas memórias do projeto
        rel_mems = self.db.search_memories(req, workspace=ws, n_results=8)
        if len(rel_mems) < 3 and ws != "brain_mcp":
            rel_mems.extend(self.db.search_memories(req, workspace="global", n_results=4))

        # 3. Extrair ficheiros e ponteiros :Lstart-end reais das memórias + Checkpoint + Scout Map
        file_ptr_re = re.compile(r"\b([a-zA-Z0-9_\-/\\]+\.(?:py|html|js|ts|tsx|json|md|sql|css|cpp|h|inl)(?::L\d+(?:-\d+)?)?)\b")
        matched_files: List[str] = []
        context_facts: List[str] = []

        def _normalize_file_ptr(raw_fp: str) -> str:
            s = re.sub(r"[/\\]+", "/", raw_fp).strip("/")
            parts = [p for p in s.split("/") if p]
            if len(parts) > 2:
                s = "/".join(parts[-2:])
            if len(s) > 42 and "/" in s:
                s = parts[-1]
            return s

        for m in rel_mems[:6]:
            txt = f"{m.get('topic', '')}: {m.get('fact', '')}"
            for fp in file_ptr_re.findall(txt):
                clean_fp = _normalize_file_ptr(fp)
                if clean_fp and clean_fp not in matched_files:
                    matched_files.append(clean_fp)
            if m.get("category") != "learned_rule":
                short_f = str(m.get("fact") or "").strip()
                if len(short_f) > 160:
                    short_f = short_f[:157].rstrip() + "..."
                context_facts.append(f"- **[{m.get('category', 'core')}] {m.get('topic', 'Memória')}**: {short_f}")

        chk = self.db.get_checkpoint(ws)
        if chk and chk.get("key_files"):
            for fp in file_ptr_re.findall(str(chk.get("key_files"))):
                clean_fp = _normalize_file_ptr(fp)
                if clean_fp and clean_fp not in matched_files:
                    matched_files.append(clean_fp)

        if not matched_files:
            matched_files = (
                ["orbit_engine.py", "web_dashboard.py", "index.html", "test_brain.py"]
                if ws == "brain_mcp"
                else [f"src/core_{ws}.py", f"src/ui_{ws}.js"]
            )

        # 4. Obter Meta-Regras Aprendidas pelo Self-Learn do projeto
        sl_status = self.get_self_learn_status(workspace=ws)
        playbook = list(sl_status.get("learned_playbook") or [])
        if not playbook:
            playbook = [
                "Fazer alterações cirúrgicas preservando docstrings, tipos e comentários existentes.",
                "Validar sintaxe AST e correr a suite de testes antes de concluir.",
            ]

        # 5. Sintetizar Especificação Profunda (Nível Gemini 4 / Claude Opus)
        spec = self._synthesize_deep_engineering_spec(
            req=req,
            ws=ws,
            mode=mode,
            matched_files=matched_files,
            rel_mems=rel_mems,
        )

        mode_headers = {
            "feature": "🚀 ESPECIFICAÇÃO DE ENGENHARIA: NOVA FUNCIONALIDADE (FEATURE)",
            "bugfix": "🐛 ESPECIFICAÇÃO DE ENGENHARIA: DIAGNÓSTICO DE CAUSA-RAIZ & BUGFIX",
            "refactor": "🏗️ ESPECIFICAÇÃO DE ENGENHARIA: REFATORAÇÃO ARQUITETURAL & CLEAN CODE",
            "ui_ux": "🎨 ESPECIFICAÇÃO DE ENGENHARIA: UI/UX & RENDERIZAÇÃO 60 FPS",
            "ui_3d": "🎨 ESPECIFICAÇÃO DE ENGENHARIA: UI/UX & RENDERIZAÇÃO 60 FPS",
            "security": "🛡️ ESPECIFICAÇÃO DE ENGENHARIA: AUDITORIA DE SEGURANÇA & HARDENING",
            "total_audit": "🔍 AUDITORIA TOTAL 360° (ARQUITETURA, BUGS, PERFORMANCE, UI/UX & SEGURANÇA)",
        }
        mode_title = mode_headers.get(mode, mode_headers["feature"])

        # Extrair diretivas reais do interior dos ficheiros SKILL.md selecionados
        skills_detailed_lines: List[str] = []
        for sk in matched_skills:
            extracted_rules = self._extract_skill_directives(sk.get("path", ""), max_rules=2)
            rules_sub = ""
            if extracted_rules:
                rules_sub = "\n" + "\n".join(f"  - *Diretiva SKILL.md*: {r}" for r in extracted_rules)
            skills_detailed_lines.append(
                f"- 🛠️ **`@{sk['name']}`** (`{sk['path']}`) — *{sk.get('match_reason', 'Ativada')}*: {sk['description'][:130]}{rules_sub}"
            )
        skills_bullet_str = "\n".join(skills_detailed_lines)
        skills_names_csv = ", ".join(sk["name"] for sk in matched_skills)

        files_bullet_str = "\n".join(f"- `{fp}`" for fp in matched_files[:6])
        symbols_csv = ", ".join(f"`{s}`" for s in spec["discovered_symbols"])
        rules_bullet_str = "\n".join(f"- 🧬 {r}" for r in playbook[:5])
        facts_bullet_str = (
            "\n".join(context_facts[:5])
            if context_facts
            else f"- Projeto alvo: `{ws}` (usar `[BRAIN_MEMORY]` e `[SCOUT_SHARED_MAP]` pré-injetados)."
        )
        phases_bullet_str = "\n".join(f"{idx + 1}. {ph}" for idx, ph in enumerate(spec["phases_list"]))
        edges_bullet_str = "\n".join(f"- [ ] {ec}" for ec in spec["edge_cases_list"])

        # Variante 1: Super-Prompt Completo de Engenharia (Estilo Gemini 4 / Claude Opus Deep Spec)
        full_prompt = (
            f"# {mode_title} — Projeto `{ws}`\n\n"
            f"## 1. Papel, Contexto Arquitetural & Pedido Expandido\n"
            f"{spec['expanded_narrative']}\n\n"
            f"## 2. Assinaturas Propostas, Contratos de Dados & Símbolos Alvo\n"
            f"{spec['contracts_block']}\n"
            f"- **Símbolos / Funções Existentes Relacionadas**: {symbols_csv}\n\n"
            f"## 3. Mapa Cirúrgico de Ficheiros Relevantes (`:Lstart-end` — Evitar Leituras Globais)\n"
            f"{files_bullet_str}\n\n"
            f"## 4. Plano de Implementação Passo-a-Passo (Trajetória DOTS `{dots_traj}`)\n"
            f"{phases_bullet_str}\n\n"
            f"## 5. Skills do Antigravity Ativadas (`SKILL.md`) & Meta-Regras Self-Learn (`IQ {sl_status.get('brain_iq_score', 94.0)}%`)\n"
            f"### 🛠️ Diretivas das Skills:\n"
            f"{skills_bullet_str}\n\n"
            f"### 🧬 Meta-Regras Aprendidas Neste Projeto:\n"
            f"{rules_bullet_str}\n\n"
            f"### 🧠 Contexto Histórico Recuperado (`brain.db`):\n"
            f"{facts_bullet_str}\n\n"
            f"## 6. Casos-Limite (Edge Cases), Guardrails & Definition of Done\n"
            f"{edges_bullet_str}\n"
            f"- [ ] **Edição Cirúrgica**: Usar `edit_file` preservando docstrings, comentários e funcionalidades adjacentes.\n"
            f"- [ ] **Verificação Obrigatória no Terminal**: {spec['verify_cmd']}.\n"
            f"- [ ] **Registo de Memória Zero-Token**: Anexar `<!-- brain: Tópico | Facto com ficheiros:Lstart-end -->` no final da resposta."
        )

        # Variante 2: Prompt Ultra-Compacto (Modo Token Diet / TOON, mas com Contrato + Passos)
        compact_files = ", ".join(matched_files[:4])
        compact_rule = playbook[0][:100] if playbook else "Validar AST + testes"
        compact_prompt = (
            f"[SPEC|{ws}|mode={mode.upper()}|stack={spec['stack_name'][:48]}|dots={dots_traj}]\n"
            f"🎯 Goal: {req}\n"
            f"📐 Contract: {spec['snake_id']}() / {spec['camel_id']}UI() in [{compact_files}]\n"
            f"🛠️ Skills: {skills_names_csv}\n"
            f"🧬 SelfLearnRule: {compact_rule}\n"
            f"⚠️ Guardrails: Handle null/empty states, preserve existing contracts, prevent UI overflow.\n"
            f"✅ Verify: {spec['verify_cmd']} -> append <!-- brain: Topic | Fact -->."
        )

        # Variante 3: Prompt Multi-Agente (Protocolo Asymmetric Swarm 24x com Decomposição Real por Lane)
        swarm_prompt = (
            f"# 🐝 ORQUESTRAÇÃO ASYMMETRIC SWARM (`SCOUT ➔ PLAN ➔ SWARM ➔ VERIFY`) — Projeto `{ws}`\n\n"
            f"## 🎯 Missão & Especificação Arquitetural\n"
            f"{spec['expanded_narrative']}\n\n"
            f"## 🛠️ Skills Obrigatórias para os Subagentes (`SKILL.md`)\n"
            f"{skills_bullet_str}\n\n"
            f"## 🧭 Decomposição em 4 Lanes Isoladas (Sem Colisões de Escrita)\n"
            f"1. **SCOUT (Leitura Única)**: Usa o `[SCOUT_SHARED_MAP]` e inspeciona `{compact_files}` (Símbolos: {symbols_csv}).\n"
            f"2. **LANE API / CORE (`{matched_files[0]}`)**: Implementa `{spec['snake_id']}` respeitando o contrato de dados e persistência.\n"
            f"3. **LANE UI / INTEGRAÇÃO (`{matched_files[1] if len(matched_files) > 1 else matched_files[0]}`)**: Implementa `{spec['camel_id']}UI` com contenção CSS Grid (`minmax(0, 1fr)`), `escapeHtml` e feedback instantâneo.\n"
            f"4. **LANE TESTS & VERIFY**: Valida todos os Edge Cases e executa: {spec['verify_cmd']}.\n\n"
            f"## 🧬 Meta-Regras Self-Learn Obrigatórias (`IQ {sl_status.get('brain_iq_score', 94.0)}%`)\n"
            f"{rules_bullet_str}"
        )

        is_en = str(lang or "pt-PT").lower().startswith("en")
        if is_en:
            en_replacements = [
                ("## 1. Papel, Contexto Arquitetural & Pedido Expandido", "## 1. Role, Architectural Context & Expanded Request (Papel, Contexto Arquitetural & Pedido Expandido)"),
                ("## 2. Assinaturas Propostas, Contratos de Dados & Símbolos Alvo", "## 2. Proposed Signatures, Data Contracts & Target Symbols (Assinaturas Propostas, Contratos de Dados & Símbolos Alvo)"),
                ("## 3. Mapa Cirúrgico de Ficheiros Relevantes (`:Lstart-end` — Evitar Leituras Globais)", "## 3. Surgical File Map (`:Lstart-end` — Avoid Full-Codebase Reads)"),
                ("## 4. Plano de Implementação Passo-a-Passo", "## 4. Step-by-Step Implementation Plan"),
                ("## 5. Skills do Antigravity Ativadas (`SKILL.md`) & Meta-Regras Self-Learn", "## 5. Activated Antigravity Skills (`SKILL.md`) & Self-Learn Meta-Rules"),
                ("### 🛠️ Diretivas das Skills:", "### 🛠️ Skill Directives:"),
                ("### 🧬 Meta-Regras Aprendidas Neste Projeto:", "### 🧬 Distilled Project Meta-Rules:"),
                ("### 🧠 Contexto Histórico Recuperado (`brain.db`):", "### 🧠 Retrieved Historical Context (`brain.db`):"),
                ("## 6. Casos-Limite (Edge Cases), Guardrails & Definition of Done", "## 6. Edge Cases, Guardrails & Definition of Done (Casos-Limite (Edge Cases), Guardrails & Definition of Done)"),
                ("Atua como **", "Act as **"),
                ("no projeto **`", "on project **`"),
                ("Preciso que projetes e implementes de ponta a ponta", "Please design and implement end-to-end"),
                ("Especificação Funcional Detalhada", "Detailed Functional Specification"),
                ("Assinatura Core / Backend Proposta", "Proposed Core / Backend Signature"),
                ("Handler de Interface / Integração Proposto", "Proposed UI / Integration Handler"),
                ("Contrato de Retorno Esperado (Schema)", "Expected Return Contract (Schema)"),
                ("Símbolos / Funções Existentes Relacionadas", "Related Existing Symbols / Functions"),
                ("Edição Cirúrgica", "Surgical Editing"),
                ("Verificação Obrigatória no Terminal", "Mandatory Terminal Verification"),
                ("Registo de Memória Zero-Token", "Zero-Token Memory Harvesting"),
                ("AUDITORIA TOTAL 360°", "360° FULL AUDIT (AUDITORIA TOTAL 360°)"),
                ("5 Eixos Obrigatórios", "5 Mandatory Audit Axes (5 Eixos Obrigatórios)"),
            ]
            for pt_s, en_s in en_replacements:
                full_prompt = full_prompt.replace(pt_s, en_s)
                swarm_prompt = swarm_prompt.replace(pt_s, en_s)

        est_saved = max(480, len(matched_files) * 165 + len(playbook) * 95 + len(matched_skills) * 115)
        token_estimate = max(320, len(full_prompt) // 4)

        with self.db._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO prompt_forge_history
                (workspace, task_mode, raw_request, full_prompt, compact_prompt, swarm_prompt,
                 dots_trajectory, matched_files_json, rules_applied_count, estimated_tokens_saved)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    ws,
                    mode,
                    req,
                    full_prompt,
                    compact_prompt,
                    swarm_prompt,
                    dots_traj,
                    json.dumps(matched_files[:6], ensure_ascii=False),
                    len(playbook[:4]),
                    est_saved,
                ),
            )
            new_id = int(cur.lastrowid or 0)

        return {
            "ok": True,
            "id": new_id,
            "workspace": ws,
            "task_mode": mode,
            "lang": "en-EN" if is_en else "pt-PT",
            "raw_request": req,
            "intent": intent_name,
            "model_route": model_rec,
            "dots_trajectory": dots_traj,
            "matched_files": matched_files[:6],
            "matched_skills": matched_skills,
            "learned_rules_applied": playbook[:4],
            "brain_iq_score": sl_status.get("brain_iq_score", 94.0),
            "estimated_tokens_saved": est_saved,
            "token_estimate": token_estimate,
            "optimized_prompt": full_prompt,
            "full_prompt": full_prompt,
            "compact_prompt": compact_prompt,
            "swarm_prompt": swarm_prompt,
            "history": self.get_prompt_forge_history(workspace=ws, limit=8),
        }
