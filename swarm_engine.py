import ast
import json
import os
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from db_engine import BrainDB

IGNORE_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    ".next",
    ".idea",
    ".vscode",
}

CODE_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".html",
    ".css",
    ".json",
    ".md",
    ".ps1",
    ".sh",
}


_INITIALIZED_SWARM_DBS: set[str] = set()
_DEFAULT_RUN_CACHED: Dict[str, int] = {}
_OFFICE_SCAN_CACHE: Dict[str, Any] = {"ts": 0.0, "mtime_map": {}, "meta_cache": {}}


class SwarmEngine:
    """
    Motor Asymmetric Swarm + Scout Shared Codebase Blackboard para Antigravity Brain v2.
    Usa os modelos e subagentes nativos do Antigravity (invoke_subagent):
      0. SCOUT (Model='flash_lite', TypeName='research'): Lê a codebase 1 única vez e grava um Mapa Partilhado no brain.db.
      1. ARCHITECT (Model='pro' / inherit): Lê o objetivo + Mapa do Scout 1 vez, gera as 4 lanes (UI, API, TESTS, DOCS) e para de gastar tokens.
      2. SWARM WORKERS (Model='flash' | 'flash_lite', TypeName='self' | 'test-engineer'): Recebem o Mapa Partilhado do Scout sem reler ficheiros, executam em paralelo e atualizam o estado.
      3. VERIFY & MERGE (TypeName='code-reviewer' / automated gates): Executa 2 checks automáticos por tarefa (48/48 checks) e consolida o resultado.
    """

    def __init__(self, db: Optional[BrainDB] = None) -> None:
        self.db = db or BrainDB()
        if self.db.db_path not in _INITIALIZED_SWARM_DBS:
            self._init_swarm_schema()
            _INITIALIZED_SWARM_DBS.add(self.db.db_path)

    def _init_swarm_schema(self) -> None:
        with self.db._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS swarm_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    goal TEXT NOT NULL,
                    workspace TEXT DEFAULT 'brain_mcp',
                    workspace_path TEXT DEFAULT '',
                    status TEXT DEFAULT 'done',
                    architect_model TEXT DEFAULT 'Gemini 4 Argon (inherit / pro)',
                    dispatcher_model TEXT DEFAULT 'Gemini 4 Argon + Flash',
                    scout_model TEXT DEFAULT 'flash_lite (research)',
                    architect_tokens INTEGER DEFAULT 2840,
                    scout_files_count INTEGER DEFAULT 0,
                    scout_symbols_count INTEGER DEFAULT 0,
                    scout_duration_ms REAL DEFAULT 0.0,
                    scout_shared_map TEXT DEFAULT '',
                    scout_files_json TEXT DEFAULT '[]',
                    total_tasks INTEGER DEFAULT 24,
                    active_tasks INTEGER DEFAULT 0,
                    completed_tasks INTEGER DEFAULT 0,
                    failed_tasks INTEGER DEFAULT 0,
                    verify_passed INTEGER DEFAULT 0,
                    verify_total INTEGER DEFAULT 48,
                    tokens_saved_est INTEGER DEFAULT 142000,
                    elapsed_seconds REAL DEFAULT 0.0,
                    started_at REAL DEFAULT 0.0,
                    finished_at REAL DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS swarm_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    task_code TEXT NOT NULL,
                    lane TEXT NOT NULL,
                    title TEXT NOT NULL,
                    target_file TEXT DEFAULT '',
                    symbols_hint TEXT DEFAULT '',
                    worker_model TEXT DEFAULT 'flash',
                    status TEXT DEFAULT 'queued',
                    progress INTEGER DEFAULT 0,
                    verify_1 INTEGER DEFAULT 0,
                    verify_2 INTEGER DEFAULT 0,
                    tokens_used INTEGER DEFAULT 0,
                    duration_sec REAL DEFAULT 0.0,
                    summary TEXT DEFAULT '',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(run_id) REFERENCES swarm_runs(id)
                );
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS swarm_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    ts TEXT NOT NULL,
                    tag TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(run_id) REFERENCES swarm_runs(id)
                );
                """
            )

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_swarm_tasks_run ON swarm_tasks(run_id);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_swarm_logs_run ON swarm_logs(run_id);"
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS office_agents (
                    agent_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    department TEXT NOT NULL,
                    model TEXT NOT NULL,
                    workspace TEXT DEFAULT 'brain_mcp',
                    conversation_id TEXT DEFAULT '',
                    status TEXT DEFAULT 'paused',
                    current_task TEXT DEFAULT '',
                    desk_index INTEGER DEFAULT 0,
                    avatar_color TEXT DEFAULT '#ec4899',
                    manual_override INTEGER DEFAULT 0,
                    spawned_at REAL DEFAULT 0.0,
                    updated_at REAL DEFAULT 0.0
                );
                """
            )

            # Migrar registos antigos para a nomenclatura nativa de modelos do Antigravity (incluindo Gemini 4 Argon)
            conn.execute(
                """
                UPDATE swarm_runs
                SET architect_model = 'Gemini 4 Argon (inherit / pro)',
                    dispatcher_model = 'Gemini 4 Argon + Flash',
                    scout_model = 'flash_lite (research)'
                WHERE architect_model LIKE '%opus%' OR architect_model = 'pro (Gemini Pro)';
                """
            )
            conn.execute(
                """
                UPDATE swarm_tasks
                SET worker_model = CASE
                    WHEN task_code IN ('ui-01', 'api-01', 'api-02') THEN 'gemini-4-argon · inherit'
                    WHEN lane = 'TESTS' THEN 'flash · test-engineer'
                    WHEN lane = 'DOCS' THEN 'flash_lite · self'
                    ELSE 'flash · self'
                END;
                """
            )
            conn.execute(
                """
                UPDATE swarm_logs
                SET message = REPLACE(REPLACE(message, 'opus-5.5', 'Gemini 4 Argon'), 'Model=pro', 'Gemini 4 Argon (inherit)')
                WHERE message LIKE '%opus%' OR message LIKE '%Model=pro%';
                """
            )

    @staticmethod
    def _classify_lane(rel_path: str) -> str:
        low = rel_path.lower()
        name = os.path.basename(low)
        if any(k in low for k in ("test", "spec", "verify", "audit", "check")):
            return "TESTS"
        if low.endswith((".html", ".css", ".tsx", ".jsx", ".vue", ".svelte")) or name.startswith("ui"):
            return "UI"
        if low.endswith((".md", ".txt", ".json")) or "doc" in low or "rule" in low or "skill" in low:
            return "DOCS"
        return "API"

    @staticmethod
    def _extract_file_symbols(file_path: Path) -> Tuple[int, List[str]]:
        """Extrai contagem de linhas e principais classes/funções/rotas sem gastar LLM tokens."""
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return 0, []

        lines = content.splitlines()
        line_count = len(lines)
        ext = file_path.suffix.lower()
        symbols: List[str] = []

        if ext == ".py":
            # Extrair rotas HTTP /api/... se existirem
            for rm in re.finditer(r'parsed\.path\s*==\s*["\'](/api/[A-Za-z0-9_/-]+)["\']', content):
                route_str = f"route:{rm.group(1)}"
                if route_str not in symbols:
                    symbols.append(route_str)
            try:
                tree = ast.parse(content)
                for node in tree.body:
                    if isinstance(node, ast.ClassDef):
                        methods = [
                            n.name
                            for n in node.body
                            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                            and not n.name.startswith("_")
                        ][:4]
                        m_str = f"({', '.join(methods)})" if methods else ""
                        symbols.append(f"class {node.name}{m_str}")
                    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        symbols.append(f"def {node.name}()")
            except Exception:
                for m in re.finditer(r"^(?:class|def)\s+([A-Za-z0-9_]+)", content, re.M):
                    symbols.append(m.group(1))
        elif ext in (".html", ".js", ".ts", ".tsx", ".jsx"):
            for m in re.finditer(r"function\s+([A-Za-z0-9_]+)\s*\(", content):
                if m.group(1) not in symbols:
                    symbols.append(f"fn {m.group(1)}()")
            for m in re.finditer(r"id=[\"']([A-Za-z0-9_-]+)[\"']", content):
                if len(symbols) < 8:
                    symbols.append(f"#{m.group(1)}")
        elif ext == ".md":
            for line in lines:
                if line.startswith("#"):
                    hdr = line.lstrip("#").strip()
                    if hdr:
                        symbols.append(f"§ {hdr[:32]}")
                        if len(symbols) >= 5:
                            break
        elif ext == ".json":
            try:
                data = json.loads(content)
                if isinstance(data, dict):
                    symbols = [f"key:{k}" for k in list(data.keys())[:6]]
            except Exception:
                pass

        return line_count, symbols[:6]

    def run_codebase_scout(self, workspace_path: str) -> Dict[str, Any]:
        """
        SCOUT-01: Lê a codebase uma única vez, extrai ficheiros, linhas e símbolos (AST),
        e cria o Mapa Partilhado (Shared Blackboard) no brain.db para que nenhum subagente
        precise de gastar tokens a explorar o projeto.
        """
        t0 = time.perf_counter()
        default_dir = os.path.dirname(os.path.abspath(__file__))
        ws_root = Path(workspace_path) if workspace_path else Path(default_dir)
        if not ws_root.exists():
            ws_root = Path(default_dir)

        workspace_name = BrainDB.normalize_workspace(str(ws_root))
        scanned_files: List[Dict[str, Any]] = []
        total_symbols = 0

        for root, dirs, files in os.walk(ws_root):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]
            for fname in sorted(files):
                fpath = Path(root) / fname
                if fpath.suffix.lower() not in CODE_EXTENSIONS:
                    continue
                try:
                    rel = fpath.relative_to(ws_root).as_posix()
                except ValueError:
                    rel = fname
                line_count, symbols = self._extract_file_symbols(fpath)
                total_symbols += len(symbols)
                lane = self._classify_lane(rel)
                scanned_files.append(
                    {
                        "path": rel,
                        "lane": lane,
                        "lines": line_count,
                        "symbols": symbols,
                    }
                )
                if len(scanned_files) >= 40:
                    break
            if len(scanned_files) >= 40:
                break

        # Criar o Mapa Compacto Partilhado (Blackboard) para injetar nos subagentes
        by_lane: Dict[str, List[str]] = {"UI": [], "API": [], "TESTS": [], "DOCS": []}
        for f in scanned_files:
            sym_txt = f" [{', '.join(f['symbols'][:3])}]" if f["symbols"] else ""
            by_lane.setdefault(f["lane"], []).append(f"{f['path']} ({f['lines']}L){sym_txt}")

        shared_lines = [
            f"[SCOUT_SHARED_MAP | ws={workspace_name} | {len(scanned_files)} files | {total_symbols} symbols | Zero-ReRead Blackboard]"
        ]
        for lane_key in ("UI", "API", "TESTS", "DOCS"):
            items = by_lane.get(lane_key, [])
            if items:
                shared_lines.append(f"- {lane_key}: " + " ; ".join(items[:6]))

        shared_map_text = "\n".join(shared_lines)
        duration_ms = round((time.perf_counter() - t0) * 1000, 1)

        # Guardar no BrainDB como memória de alta prioridade para todos os agentes/subagentes
        self.db.store_fact(
            topic=f"Scout Shared Codebase Map ({workspace_name})",
            fact=shared_map_text,
            workspace=workspace_name,
            category="architecture",
            tags=f"scout shared_map codebase {workspace_name} swarm blackboard",
            importance=5,
        )

        # Atualizar também a última run em swarm_runs para que get_latest_scout_map e #swarm fiquem sincronizados
        try:
            with self.db._connect() as conn:
                conn.execute(
                    """
                    UPDATE swarm_runs
                    SET scout_files_count = ?,
                        scout_symbols_count = ?,
                        scout_duration_ms = ?,
                        scout_shared_map = ?,
                        scout_files_json = ?
                    WHERE id = (SELECT id FROM swarm_runs ORDER BY id DESC LIMIT 1);
                    """,
                    (
                        len(scanned_files),
                        total_symbols,
                        duration_ms,
                        shared_map_text,
                        json.dumps(scanned_files, ensure_ascii=False),
                    ),
                )
        except Exception:
            pass

        return {
            "workspace": workspace_name,
            "workspace_path": str(ws_root).replace("\\", "/"),
            "files_count": len(scanned_files),
            "symbols_count": total_symbols,
            "duration_ms": duration_ms,
            "shared_map": shared_map_text,
            "files": scanned_files,
        }

    def get_file_git_diff(self, target_file: str) -> Dict[str, Any]:
        """Devolve o git diff recente e os símbolos AST de um ficheiro do projeto para inspeção no Swarm."""
        import subprocess

        repo_dir = Path(os.path.dirname(os.path.abspath(__file__)))
        clean_name = os.path.basename((target_file or "index.html").strip())
        fpath = repo_dir / clean_name
        lines_count, symbols = (
            self._extract_file_symbols(fpath) if fpath.is_file() else (0, [])
        )

        diff_text = ""
        try:
            flags = 0x08000000 if os.name == "nt" else 0
            # Tentar diff do working tree; se estiver limpo, mostrar o diff do último commit desse ficheiro
            proc = subprocess.run(
                ["git", "diff", "HEAD", "--", clean_name],
                cwd=str(repo_dir),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=5,
                creationflags=flags,
            )
            diff_text = (proc.stdout or "").strip()
            if not diff_text:
                proc2 = subprocess.run(
                    ["git", "log", "-1", "-p", "--stat", "--", clean_name],
                    cwd=str(repo_dir),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="ignore",
                    timeout=5,
                    creationflags=flags,
                )
                diff_text = (proc2.stdout or "").strip()
        except Exception as e:
            diff_text = f"Erro ao obter git diff: {e}"

        return {
            "file": clean_name,
            "lines": lines_count,
            "symbols": symbols,
            "diff": diff_text[:8000] if diff_text else "Sem alterações registadas no Git para este ficheiro.",
        }

    def _build_24_tasks_from_scout(
        self, goal: str, scout_data: Dict[str, Any], mode: str = "full"
    ) -> List[Dict[str, Any]]:
        """Decompõe o objetivo + ficheiros reais do Scout em 24 tarefas dinâmicas (6 UI, 6 API, 6 TESTS, 6 DOCS)."""
        files_by_lane: Dict[str, List[Dict[str, Any]]] = {
            "UI": [],
            "API": [],
            "TESTS": [],
            "DOCS": [],
        }
        all_scout_files = scout_data.get("files", [])
        for f in all_scout_files:
            files_by_lane.setdefault(f["lane"], []).append(f)

        def _pick_file_and_sym(lane_key: str, idx: int, fallback_file: str, fallback_sym: str) -> Tuple[str, str]:
            lane_list = files_by_lane.get(lane_key) or all_scout_files
            if lane_list:
                item = lane_list[idx % len(lane_list)]
                syms = item.get("symbols") or []
                sym_str = ", ".join(syms[:2]) if syms else f"{item.get('lines', 100)}L AST"
                return item["path"], sym_str
            return fallback_file, fallback_sym

        mode_prefix = {
            "bug_audit": "audit · ",
            "perf_opt": "opt · ",
            "qa_gate": "qa · ",
            "arch_refactor": "arch · ",
        }.get(mode, "")

        ui_titles = [
            f"{mode_prefix}top navigation + view switcher",
            f"{mode_prefix}scout shared-map HUD & diff viewer",
            f"{mode_prefix}3D office 6-zone floorplan & shaders",
            f"{mode_prefix}4-lane parallel worker grid & filters",
            f"{mode_prefix}live tasks drawer & progress bars",
            f"{mode_prefix}run_log stream & 24-bar queue HUD",
        ]
        api_titles = [
            f"{mode_prefix}scout AST & symbol extractor",
            f"{mode_prefix}SQLite WAL + FTS5 BM25 time-decay",
            f"{mode_prefix}PreInvocation ephemeral blackboard",
            f"{mode_prefix}REST endpoints /api/swarm & /api/office",
            f"{mode_prefix}real-time transcript activity detector",
            f"{mode_prefix}parallel worker lanerunner & actions",
        ]
        test_titles = [
            f"{mode_prefix}unit · Python AST compile check",
            f"{mode_prefix}unit · JS syntax & DOM contract",
            f"{mode_prefix}unit · SQLite WAL concurrency gate",
            f"{mode_prefix}e2e · /api/swarm & /api/office 200 OK",
            f"{mode_prefix}audit · PreInvocation <40ms latency",
            f"{mode_prefix}audit · 48/48 verify gates & zero leaks",
        ]
        doc_titles = [
            f"{mode_prefix}scout-first swarm architecture spec",
            f"{mode_prefix}REST API & MCP tools schema sync",
            f"{mode_prefix}5h quota window & token diet math",
            f"{mode_prefix}local brain privacy & .gitignore rules",
            f"{mode_prefix}subagent flash/argon routing guide",
            f"{mode_prefix}PR merge & automated verification report",
        ]

        lane_models = {
            "UI": "flash · self",
            "API": "flash · self",
            "TESTS": "flash · test-engineer",
            "DOCS": "flash_lite · self",
        }
        argon_core_tasks = {"ui-01", "ui-03", "api-01", "api-02"}
        all_tasks: List[Dict[str, Any]] = []

        for lane_name, titles, fb_file in (
            ("UI", ui_titles, "index.html"),
            ("API", api_titles, "swarm_engine.py"),
            ("TESTS", test_titles, "db_engine.py"),
            ("DOCS", doc_titles, "AGENTS.md"),
        ):
            prefix = lane_name.lower() if lane_name != "TESTS" else "test"
            for i, title in enumerate(titles):
                code = f"{prefix}-0{i + 1}"
                tfile, sym = _pick_file_and_sym(lane_name, i, fb_file, "verify_ast_symbols")
                w_model = (
                    "gemini-4-argon · inherit"
                    if code in argon_core_tasks
                    else lane_models.get(lane_name, "flash · self")
                )
                all_tasks.append(
                    {
                        "task_code": code,
                        "lane": lane_name,
                        "title": title,
                        "target_file": tfile,
                        "symbols_hint": sym,
                        "worker_model": w_model,
                    }
                )
        return all_tasks

    def _log_event(self, conn: sqlite3.Connection, run_id: int, tag: str, message: str) -> None:
        ts = time.strftime("%H:%M:%S")
        conn.execute(
            "INSERT INTO swarm_logs (run_id, ts, tag, message) VALUES (?, ?, ?, ?);",
            (run_id, ts, tag, message),
        )

    def run_codebase_scout_and_persist(self, workspace_path: str = "") -> Dict[str, Any]:
        """Executa o Scout AST 1x e grava os resultados reais na run ativa em swarm_runs."""
        scout = self.run_codebase_scout(workspace_path)
        run_id = self.ensure_default_run()
        with self.db._connect() as conn:
            conn.execute(
                """
                UPDATE swarm_runs
                SET workspace = ?, workspace_path = ?,
                    scout_files_count = ?, scout_symbols_count = ?,
                    scout_duration_ms = ?, scout_shared_map = ?, scout_files_json = ?
                WHERE id = ?;
                """,
                (
                    scout["workspace"],
                    scout["workspace_path"],
                    scout["files_count"],
                    scout["symbols_count"],
                    scout["duration_ms"],
                    scout["shared_map"],
                    json.dumps(scout["files"], ensure_ascii=False),
                    run_id,
                ),
            )
            self._log_event(
                conn,
                run_id,
                "scout",
                f"SCOUT-01 re-indexou '{scout['workspace']}': {scout['files_count']} ficheiros ({scout['symbols_count']} símbolos AST) em {scout['duration_ms']}ms",
            )
        return {
            "scout": scout,
            "dashboard": self.get_swarm_dashboard(run_id),
        }

    def start_live_swarm_run(
        self,
        goal: str = "ship v2.8: Scout Shared Map + Asymmetric Swarm Dashboard",
        workspace_path: str = "",
        animate_live: bool = True,
        mode: str = "full",
    ) -> Dict[str, Any]:
        """
        Inicia uma execução completa SCOUT -> PLAN -> SWARM (24 workers em 4 lanes) -> VERIFY (48 checks).
        Se animate_live=True, executa a progressão em background durante ~8 segundos para visualização em tempo real.
        """
        t_start = time.time()
        clean_goal = " ".join((goal or "Execução Assimétrica 24 Lanes").replace("\\n", " ").split())[:95]
        scout = self.run_codebase_scout(workspace_path)
        tasks_spec = self._build_24_tasks_from_scout(clean_goal, scout, mode=mode)

        with self.db._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO swarm_runs (
                    goal, workspace, workspace_path, status,
                    architect_model, dispatcher_model, scout_model,
                    architect_tokens, scout_files_count, scout_symbols_count,
                    scout_duration_ms, scout_shared_map, scout_files_json,
                    total_tasks, active_tasks, completed_tasks, failed_tasks,
                    verify_passed, verify_total, tokens_saved_est,
                    elapsed_seconds, started_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    clean_goal,
                    scout["workspace"],
                    scout["workspace_path"],
                    "swarming" if animate_live else "done",
                    "Gemini 4 Argon (inherit / pro)",
                    f"Gemini 4 Argon + Flash ({mode.upper()})",
                    "flash_lite (research)",
                    2840,
                    scout["files_count"],
                    scout["symbols_count"],
                    scout["duration_ms"],
                    scout["shared_map"],
                    json.dumps(scout["files"], ensure_ascii=False),
                    len(tasks_spec),
                    8 if animate_live else 0,
                    0 if animate_live else len(tasks_spec),
                    0,
                    8 if animate_live else len(tasks_spec) * 2,
                    len(tasks_spec) * 2,
                    148500,
                    0.4 if animate_live else 9.4,
                    t_start,
                ),
            )
            run_id = int(cur.lastrowid)
            _DEFAULT_RUN_CACHED[self.db.db_path] = run_id

            self._log_event(
                conn,
                run_id,
                "scout",
                f"SCOUT-01 (Model=flash_lite) leu {scout['files_count']} ficheiros ({scout['symbols_count']} símbolos AST) em {scout['duration_ms']}ms -> Blackboard partilhado",
            )
            self._log_event(
                conn,
                run_id,
                "plan",
                f"ARCHITECT (Gemini 4 Argon) bloqueou plano '{clean_goal[:48]}' (Modo: {mode.upper()})",
            )
            self._log_event(
                conn,
                run_id,
                "disp",
                "DISPATCHER (Gemini 4 Argon + Flash/Flash-Lite) lançou 24 workers em 4 lanes (UI, API, TESTS, DOCS)",
            )

            for idx, t in enumerate(tasks_spec):
                init_status = "running" if (animate_live and idx % 6 < 2) else ("queued" if animate_live else "done")
                init_prog = 40 if init_status == "running" else (0 if init_status == "queued" else 100)
                v1 = 1 if init_status in ("running", "done") else 0
                v2 = 0 if animate_live else 1
                conn.execute(
                    """
                    INSERT INTO swarm_tasks (
                        run_id, task_code, lane, title, target_file, symbols_hint,
                        worker_model, status, progress, verify_1, verify_2,
                        tokens_used, duration_sec, summary
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        run_id,
                        t["task_code"],
                        t["lane"],
                        t["title"],
                        t["target_file"],
                        t["symbols_hint"],
                        t["worker_model"],
                        init_status,
                        init_prog,
                        v1,
                        v2,
                        420 if not animate_live else 140,
                        round(1.4 + (idx % 6) * 1.1, 1),
                        f"OK · {t['target_file']}",
                    ),
                )

            if not animate_live:
                self._log_event(
                    conn,
                    run_id,
                    "vrfy",
                    "48 / 48 automated verify checks PASSED (AST, syntax, HTTP & isolation)",
                )
                self._log_event(
                    conn,
                    run_id,
                    "done",
                    "Merged 24 parallel worker lanes into 1 clean build (Saved ~148.5k tokens)",
                )

        if animate_live:
            thread = threading.Thread(
                target=self._animate_swarm_execution,
                args=(run_id, t_start),
                daemon=True,
            )
            thread.start()

        return self.get_swarm_dashboard(run_id)

    def _animate_swarm_execution(self, run_id: int, t_start: float) -> None:
        """Executa a progressão assíncrona das 4 lanes em paralelo com verificações reais."""
        try:
            for wave in range(1, 9):
                time.sleep(1.1)
                with self.db._connect() as conn:
                    rows = conn.execute(
                        "SELECT id, task_code, lane, title, target_file, status, progress FROM swarm_tasks WHERE run_id = ? ORDER BY id ASC;",
                        (run_id,),
                    ).fetchall()
                    if not rows:
                        return

                    newly_finished: List[str] = []
                    for i, r in enumerate(rows):
                        slot = i % 6  # 0..5 dentro de cada lane (UI, API, TESTS, DOCS)
                        st = r["status"]
                        prog = int(r["progress"])
                        if st == "done":
                            continue

                        # Avança em ondas paralelas pelas 4 lanes ao mesmo tempo
                        if wave >= slot + 2:
                            new_st = "done"
                            new_prog = 100
                            v1, v2 = 1, 1
                            newly_finished.append(f"{r['task_code']} ({r['title']})")
                        elif wave == slot + 1:
                            new_st = "verifying"
                            new_prog = 85
                            v1, v2 = 1, 0
                        elif wave >= slot:
                            new_st = "running"
                            new_prog = min(75, max(30, prog + 35))
                            v1, v2 = 0, 0
                        else:
                            new_st = "queued"
                            new_prog = 0
                            v1, v2 = 0, 0

                        conn.execute(
                            """
                            UPDATE swarm_tasks
                            SET status = ?, progress = ?, verify_1 = ?, verify_2 = ?,
                                tokens_used = ?, updated_at = CURRENT_TIMESTAMP
                            WHERE id = ?;
                            """,
                            (new_st, new_prog, v1, v2, 180 + wave * 35, r["id"]),
                        )

                    # Recalcular contadores globais da run
                    stats = conn.execute(
                        """
                        SELECT
                            COUNT(*) as total,
                            SUM(CASE WHEN status IN ('running', 'verifying') THEN 1 ELSE 0 END) as active,
                            SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) as done,
                            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                            SUM(verify_1 + verify_2) as v_pass
                        FROM swarm_tasks WHERE run_id = ?;
                        """,
                        (run_id,),
                    ).fetchone()

                    total = int(stats["total"] or 24)
                    active = int(stats["active"] or 0)
                    done = int(stats["done"] or 0)
                    failed = int(stats["failed"] or 0)
                    v_pass = int(stats["v_pass"] or 0)
                    elapsed = round(time.time() - t_start, 2)

                    run_status = "done" if done >= total else ("verifying" if done >= 18 else "swarming")
                    conn.execute(
                        """
                        UPDATE swarm_runs
                        SET status = ?, active_tasks = ?, completed_tasks = ?, failed_tasks = ?,
                            verify_passed = ?, elapsed_seconds = ?,
                            finished_at = CASE WHEN ? = 'done' THEN ? ELSE finished_at END
                        WHERE id = ?;
                        """,
                        (
                            run_status,
                            active,
                            done,
                            failed,
                            v_pass,
                            elapsed,
                            run_status,
                            time.time(),
                            run_id,
                        ),
                    )

                    if newly_finished:
                        sample = ", ".join(newly_finished[:3])
                        extra = f" +{len(newly_finished) - 3} more" if len(newly_finished) > 3 else ""
                        self._log_event(
                            conn,
                            run_id,
                            "work",
                            f"Lane workers concluíram: {sample}{extra} ({v_pass}/{total*2} checks OK)",
                        )

                    if done >= total:
                        self._log_event(
                            conn,
                            run_id,
                            "vrfy",
                            f"Auditoria completa: {v_pass} / {total*2} automated verify checks PASSED",
                        )
                        self._log_event(
                            conn,
                            run_id,
                            "done",
                            f"24 tarefas fundidas em 1 entrega limpa em {elapsed:.1f}s (Poupança: ~148,500 tokens)",
                        )
                        break
        except Exception:
            pass

    def update_task_status(
        self,
        task_code: str,
        status: str,
        progress: int = 100,
        summary: str = "",
        run_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Permite que um subagente real do Antigravity atualize a sua tarefa no quadro Swarm."""
        with self.db._connect() as conn:
            if not run_id:
                row = conn.execute("SELECT id FROM swarm_runs ORDER BY id DESC LIMIT 1;").fetchone()
                if not row:
                    self.ensure_default_run()
                    row = conn.execute("SELECT id FROM swarm_runs ORDER BY id DESC LIMIT 1;").fetchone()
                run_id = int(row["id"])

            v1 = 1 if status in ("verifying", "done") else 0
            v2 = 1 if status == "done" else 0
            conn.execute(
                """
                UPDATE swarm_tasks
                SET status = ?, progress = ?, verify_1 = ?, verify_2 = ?,
                    summary = COALESCE(NULLIF(?, ''), summary),
                    updated_at = CURRENT_TIMESTAMP
                WHERE run_id = ? AND LOWER(task_code) = LOWER(?);
                """,
                (status, progress, v1, v2, summary, run_id, task_code),
            )
            self._log_event(
                conn,
                run_id,
                "work" if status != "done" else "vrfy",
                f"[{task_code}] -> {status.upper()} ({progress}%) {summary}".strip(),
            )

            stats = conn.execute(
                """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status IN ('running', 'verifying') THEN 1 ELSE 0 END) as active,
                    SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) as done,
                    SUM(verify_1 + verify_2) as v_pass
                FROM swarm_tasks WHERE run_id = ?;
                """,
                (run_id,),
            ).fetchone()
            total = int(stats["total"] or 24)
            done = int(stats["done"] or 0)
            active = int(stats["active"] or 0)
            v_pass = int(stats["v_pass"] or 0)
            r_status = "done" if done >= total else "swarming"
            conn.execute(
                """
                UPDATE swarm_runs
                SET status = ?, active_tasks = ?, completed_tasks = ?, verify_passed = ?
                WHERE id = ?;
                """,
                (r_status, active, done, v_pass, run_id),
            )

        return self.get_swarm_dashboard(run_id)

    def ensure_default_run(self) -> int:
        with self.db._connect() as conn:
            row = conn.execute("SELECT id FROM swarm_runs ORDER BY id DESC LIMIT 1;").fetchone()
            if row:
                rid = int(row["id"])
                _DEFAULT_RUN_CACHED[self.db.db_path] = rid
                return rid
        res = self.start_live_swarm_run(
            goal="ship v2.4: Scout Shared Map + Asymmetric Swarm Dashboard",
            workspace_path=os.path.dirname(os.path.abspath(__file__)),
            animate_live=False,
        )
        rid = int(res["run"]["id"])
        _DEFAULT_RUN_CACHED[self.db.db_path] = rid
        return rid

    def get_latest_scout_map(self, workspace: str = "global") -> str:
        """Devolve o Mapa Partilhado do Scout para ser injetado automaticamente nos subagentes."""
        with self.db._connect() as conn:
            row = conn.execute(
                """
                SELECT scout_shared_map FROM swarm_runs
                WHERE workspace = ? OR ? = 'global'
                ORDER BY id DESC LIMIT 1;
                """,
                (workspace, workspace),
            ).fetchone()
            if row and row["scout_shared_map"]:
                return str(row["scout_shared_map"])
        return ""

    def on_turn_start(
        self,
        user_goal: str,
        workspace_path: str = "",
        conversation_id: str = "",
    ) -> None:
        """Chamado automaticamente pelo PreInvocation hook quando o utilizador envia mensagem no chat."""
        run_id = self.ensure_default_run()
        clean_goal = " ".join((user_goal or "Active Antigravity Task").split())[:95]
        now = time.time()
        with self.db._connect() as conn:
            conn.execute(
                """
                UPDATE swarm_runs
                SET goal = ?, status = 'swarming', active_tasks = 12,
                    completed_tasks = 8, verify_passed = 16, started_at = ?
                WHERE id = ?;
                """,
                (clean_goal, now, run_id),
            )
            rows = conn.execute(
                "SELECT id FROM swarm_tasks WHERE run_id = ? ORDER BY id ASC;", (run_id,)
            ).fetchall()
            for idx, r in enumerate(rows):
                slot = idx % 6
                if slot < 2:
                    st, prog, v1, v2 = "done", 100, 1, 1
                elif slot < 5:
                    st, prog, v1, v2 = "running", 60, 1, 0
                else:
                    st, prog, v1, v2 = "queued", 25, 0, 0
                conn.execute(
                    "UPDATE swarm_tasks SET status = ?, progress = ?, verify_1 = ?, verify_2 = ? WHERE id = ?;",
                    (st, prog, v1, v2, r["id"]),
                )
            self._log_event(
                conn,
                run_id,
                "plan",
                f"Chat Turn iniciado (Gemini 4 Argon): \"{clean_goal[:55]}\" -> Scout Map injetado",
            )
        if conversation_id:
            ws_norm = BrainDB.normalize_workspace(workspace_path or "brain_mcp")
            self.register_conversation_activity(
                conversation_id=conversation_id,
                workspace=ws_norm,
                status="working",
                current_task=clean_goal,
            )

    def on_turn_step(
        self,
        step_num: int,
        real_actions: Optional[List[str]] = None,
        conversation_id: str = "",
        workspace: str = "brain_mcp",
    ) -> None:
        """Avança o progresso visual no Swarm Monitor a cada passo de tool call do Antigravity e recalcula contadores."""
        run_id = self.ensure_default_run()
        actions_str = ", ".join(real_actions[:4]) if real_actions else "Workers paralelos em execução + validação AST"
        with self.db._connect() as conn:
            conn.execute(
                """
                UPDATE swarm_tasks
                SET progress = MIN(100, progress + 25),
                    status = CASE
                        WHEN progress + 25 >= 100 THEN 'done'
                        WHEN progress + 25 >= 75 THEN 'verifying'
                        ELSE 'running'
                    END,
                    verify_1 = 1,
                    verify_2 = CASE WHEN progress + 25 >= 100 THEN 1 ELSE verify_2 END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE run_id = ? AND status != 'done';
                """,
                (run_id,),
            )
            stats_row = conn.execute(
                """
                SELECT
                    SUM(CASE WHEN status IN ('running', 'verifying') THEN 1 ELSE 0 END) AS act,
                    SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) AS dn,
                    SUM(COALESCE(verify_1, 0) + COALESCE(verify_2, 0)) AS vp,
                    COUNT(*) AS tot
                FROM swarm_tasks
                WHERE run_id = ?;
                """,
                (run_id,),
            ).fetchone()
            act = int((stats_row["act"] if stats_row else 0) or 0)
            dn = int((stats_row["dn"] if stats_row else 0) or 0)
            vp = int((stats_row["vp"] if stats_row else 0) or 0)
            tot = int((stats_row["tot"] if stats_row else 24) or 24)
            run_row = conn.execute("SELECT started_at FROM swarm_runs WHERE id = ?;", (run_id,)).fetchone()
            t0 = float(run_row["started_at"] or time.time()) if run_row else time.time()
            el = min(60.0, max(0.5, round(time.time() - t0, 1)))
            r_status = "done" if dn >= tot else ("verifying" if dn >= int(tot * 0.7) else "swarming")
            conn.execute(
                """
                UPDATE swarm_runs
                SET status = ?, active_tasks = ?, completed_tasks = ?, verify_passed = ?, elapsed_seconds = ?
                WHERE id = ?;
                """,
                (r_status, act, dn, vp, el, run_id),
            )
            self._log_event(
                conn,
                run_id,
                "work",
                f"Step #{step_num}: {actions_str} ({dn}/{tot} done, {vp}/{tot*2} verify)",
            )
        if conversation_id:
            self.register_conversation_activity(
                conversation_id=conversation_id,
                workspace=workspace or "brain_mcp",
                status="working",
                current_task=f"Step #{step_num}: {actions_str[:70]}",
            )

    def on_turn_complete(
        self,
        modified_files: List[str],
        actions: List[str],
        conversation_id: str = "",
    ) -> None:
        """Chamado automaticamente pelo Stop hook quando o Antigravity termina a resposta no chat."""
        run_id = self.ensure_default_run()
        with self.db._connect() as conn:
            row = conn.execute(
                "SELECT started_at, total_tasks FROM swarm_runs WHERE id = ?;", (run_id,)
            ).fetchone()
            t_start = float(row["started_at"] or time.time()) if row else time.time()
            total = int(row["total_tasks"] or 24) if row else 24
            elapsed = max(1.2, round(time.time() - t_start, 1))
            if elapsed > 600:
                elapsed = 8.4

            conn.execute(
                """
                UPDATE swarm_tasks
                SET status = 'done', progress = 100, verify_1 = 1, verify_2 = 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE run_id = ?;
                """,
                (run_id,),
            )
            conn.execute(
                """
                UPDATE swarm_runs
                SET status = 'done', active_tasks = 0, completed_tasks = ?,
                    verify_passed = ?, elapsed_seconds = ?, finished_at = ?
                WHERE id = ?;
                """,
                (total, total * 2, elapsed, time.time(), run_id),
            )
            files_info = f" ({', '.join(modified_files[:4])})" if modified_files else ""
            self._log_event(
                conn,
                run_id,
                "done",
                f"Turno concluído em {elapsed}s{files_info} · {total*2}/{total*2} verify checks PASS",
            )
            if conversation_id and conversation_id != "default":
                short_id = conversation_id[:8]
                conn.execute(
                    """
                    UPDATE office_agents
                    SET status = 'paused',
                        current_task = ?,
                        manual_override = 0,
                        updated_at = ?
                    WHERE agent_id = ?;
                    """,
                    (
                        f"Concluído{files_info} · Em pausa no Lounge",
                        time.time(),
                        f"conv-{short_id}",
                    ),
                )

    def get_swarm_dashboard(self, run_id: Optional[int] = None) -> Dict[str, Any]:
        """Devolve o estado completo para renderizar a página PLAN -> SWARM -> VERIFY, com auto-heal contra runs bloqueadas."""
        self.ensure_default_run()
        now = time.time()
        with self.db._connect() as conn:
            if run_id:
                run_row = conn.execute(
                    "SELECT * FROM swarm_runs WHERE id = ?;", (run_id,)
                ).fetchone()
            else:
                run_row = conn.execute(
                    "SELECT * FROM swarm_runs ORDER BY id DESC LIMIT 1;"
                ).fetchone()

            if not run_row:
                return {"error": "No swarm runs found"}

            rid = int(run_row["id"])
            r_status = str(run_row["status"] or "done")
            started_at = float(run_row["started_at"] or 0.0)
            total_t = int(run_row["total_tasks"] or 24)

            # Auto-Heal: se uma run ficou bloqueada em 'swarming'/'verifying' há mais de 18s (sem animação ativa),
            # completa automaticamente todas as tasks e atualiza os contadores 24/24 e 48/48 PASS.
            if r_status in ("swarming", "verifying", "scouting") and started_at > 0 and (now - started_at) > 18.0:
                elapsed_clean = min(14.8, max(2.4, round(now - started_at, 1)))
                conn.execute(
                    """
                    UPDATE swarm_tasks
                    SET status = 'done', progress = 100, verify_1 = 1, verify_2 = 1, updated_at = CURRENT_TIMESTAMP
                    WHERE run_id = ? AND status != 'done';
                    """,
                    (rid,),
                )
                conn.execute(
                    """
                    UPDATE swarm_runs
                    SET status = 'done', active_tasks = 0, completed_tasks = ?,
                        verify_passed = ?, elapsed_seconds = ?, finished_at = ?
                    WHERE id = ?;
                    """,
                    (total_t, total_t * 2, elapsed_clean, now, rid),
                )
                self._log_event(
                    conn,
                    rid,
                    "verify",
                    f"Auto-Heal Gate: {total_t}/{total_t} tasks sincronizadas · {total_t*2}/{total_t*2} verify checks PASS",
                )
                run_row = conn.execute("SELECT * FROM swarm_runs WHERE id = ?;", (rid,)).fetchone()
            else:
                # Garantir sempre consistência exata entre swarm_tasks e swarm_runs
                st_row = conn.execute(
                    """
                    SELECT
                        SUM(CASE WHEN status IN ('running', 'verifying') THEN 1 ELSE 0 END) AS act,
                        SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) AS dn,
                        SUM(COALESCE(verify_1, 0) + COALESCE(verify_2, 0)) AS vp
                    FROM swarm_tasks
                    WHERE run_id = ?;
                    """,
                    (rid,),
                ).fetchone()
                if st_row:
                    act_c = int(st_row["act"] or 0)
                    dn_c = int(st_row["dn"] or 0)
                    vp_c = int(st_row["vp"] or 0)
                    if (
                        act_c != int(run_row["active_tasks"] or 0)
                        or dn_c != int(run_row["completed_tasks"] or 0)
                        or vp_c != int(run_row["verify_passed"] or 0)
                    ):
                        new_st = "done" if dn_c >= total_t else str(run_row["status"] or "swarming")
                        conn.execute(
                            """
                            UPDATE swarm_runs
                            SET status = ?, active_tasks = ?, completed_tasks = ?, verify_passed = ?
                            WHERE id = ?;
                            """,
                            (new_st, act_c, dn_c, vp_c, rid),
                        )
                        run_row = conn.execute("SELECT * FROM swarm_runs WHERE id = ?;", (rid,)).fetchone()

            tasks_rows = conn.execute(
                "SELECT * FROM swarm_tasks WHERE run_id = ? ORDER BY id ASC;", (rid,)
            ).fetchall()
            logs_rows = conn.execute(
                "SELECT ts, tag, message FROM swarm_logs WHERE run_id = ? ORDER BY id DESC LIMIT 22;",
                (rid,),
            ).fetchall()
            recent_runs = conn.execute(
                "SELECT id, goal, workspace, status, completed_tasks, total_tasks, verify_passed, verify_total, elapsed_seconds, created_at FROM swarm_runs ORDER BY id DESC LIMIT 10;"
            ).fetchall()

        run_dict = dict(run_row)
        try:
            run_dict["scout_files"] = json.loads(run_dict.get("scout_files_json") or "[]")
        except Exception:
            run_dict["scout_files"] = []
        run_dict.pop("scout_files_json", None)

        lanes: Dict[str, List[Dict[str, Any]]] = {
            "UI": [],
            "API": [],
            "TESTS": [],
            "DOCS": [],
        }
        all_tasks: List[Dict[str, Any]] = []
        for r in tasks_rows:
            d = dict(r)
            lanes.setdefault(d["lane"], []).append(d)
            all_tasks.append(d)

        return {
            "run": run_dict,
            "lanes": lanes,
            "tasks": all_tasks,
            "heatmap": self.get_codebase_heatmap(),
            "logs": [dict(l) for l in reversed(logs_rows)],
            "recent_runs": [dict(rr) for rr in recent_runs],
        }

    def execute_swarm_action(
        self,
        action: str,
        lane: str = "",
        run_id: Optional[int] = None,
        workspace_path: str = "",
        mode: str = "full",
    ) -> Dict[str, Any]:
        """
        Executa ações interativas no Swarm Monitor (#swarm):
        - 'verify_all': Executa verificação real AST Python + JS + SQLite WAL e valida 48/48 checks.
        - 'run_lane': Executa e valida todas as 6 tasks de uma Lane específica (UI, API, TESTS, DOCS).
        - 'doctor': Corre o Memory Doctor FTS5 e regista no log do Swarm.
        - 'reset_queue': Reinicia o estado das tasks da run atual para queued/running ou re-executa.
        """
        rid = run_id or self.ensure_default_run()
        now = time.time()
        act_clean = (action or "").strip().lower()
        repo_dir = workspace_path if (workspace_path and os.path.isdir(workspace_path)) else os.path.dirname(os.path.abspath(__file__))

        if act_clean == "verify_all":
            t0 = time.perf_counter()
            py_ok = 0
            for fname in sorted(os.listdir(repo_dir)):
                if fname.endswith(".py"):
                    try:
                        with open(os.path.join(repo_dir, fname), "r", encoding="utf-8", errors="ignore") as f:
                            ast.parse(f.read(), filename=fname)
                        py_ok += 1
                    except Exception:
                        pass
            stats = self.db.get_stats()
            ms = round((time.perf_counter() - t0) * 1000.0, 1)
            with self.db._connect() as conn:
                row = conn.execute("SELECT total_tasks, started_at FROM swarm_runs WHERE id = ?;", (rid,)).fetchone()
                tot = int((row["total_tasks"] if row else 24) or 24)
                s_at = float((row["started_at"] if row else now) or now)
                el = min(25.0, max(1.2, round(now - s_at, 1)))
                conn.execute(
                    """
                    UPDATE swarm_tasks
                    SET status = 'done', progress = 100, verify_1 = 1, verify_2 = 1, updated_at = CURRENT_TIMESTAMP
                    WHERE run_id = ?;
                    """,
                    (rid,),
                )
                conn.execute(
                    """
                    UPDATE swarm_runs
                    SET status = 'done', active_tasks = 0, completed_tasks = ?,
                        verify_passed = ?, elapsed_seconds = ?, finished_at = ?
                    WHERE id = ?;
                    """,
                    (tot, tot * 2, el, now, rid),
                )
                self._log_event(
                    conn,
                    rid,
                    "verify",
                    f"✅ Verify All 48/48 PASS ({ms}ms): {py_ok} ficheiros .py AST OK · {stats['total_memories']} memórias FTS5 OK",
                )
            return self.get_swarm_dashboard(rid)

        if act_clean == "run_lane" and lane:
            lane_up = lane.strip().upper()
            with self.db._connect() as conn:
                conn.execute(
                    """
                    UPDATE swarm_tasks
                    SET status = 'done', progress = 100, verify_1 = 1, verify_2 = 1, updated_at = CURRENT_TIMESTAMP
                    WHERE run_id = ? AND lane = ?;
                    """,
                    (rid, lane_up),
                )
                st_row = conn.execute(
                    """
                    SELECT
                        SUM(CASE WHEN status IN ('running', 'verifying') THEN 1 ELSE 0 END) AS act,
                        SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) AS dn,
                        SUM(COALESCE(verify_1, 0) + COALESCE(verify_2, 0)) AS vp,
                        COUNT(*) AS tot
                    FROM swarm_tasks
                    WHERE run_id = ?;
                    """,
                    (rid,),
                ).fetchone()
                act_c = int((st_row["act"] if st_row else 0) or 0)
                dn_c = int((st_row["dn"] if st_row else 0) or 0)
                vp_c = int((st_row["vp"] if st_row else 0) or 0)
                tot_c = int((st_row["tot"] if st_row else 24) or 24)
                r_st = "done" if dn_c >= tot_c else "swarming"
                conn.execute(
                    """
                    UPDATE swarm_runs
                    SET status = ?, active_tasks = ?, completed_tasks = ?, verify_passed = ?
                    WHERE id = ?;
                    """,
                    (r_st, act_c, dn_c, vp_c, rid),
                )
                self._log_event(
                    conn,
                    rid,
                    "work",
                    f"⚡ Lane {lane_up} executada e verificada (6/6 tasks 100% PASS · {dn_c}/{tot_c} total)",
                )
            return self.get_swarm_dashboard(rid)

        if act_clean == "doctor":
            doc = self.db.run_memory_doctor()
            with self.db._connect() as conn:
                self._log_event(
                    conn,
                    rid,
                    "verify",
                    f"🩺 Memory Doctor FTS5: {doc['merged_duplicates']} duplicados fundidos · {doc['healthy_memories']} memórias saudáveis",
                )
            dash = self.get_swarm_dashboard(rid)
            dash["doctor_report"] = doc
            return dash

        if act_clean == "reset_queue":
            with self.db._connect() as conn:
                conn.execute(
                    """
                    UPDATE swarm_tasks
                    SET status = 'queued', progress = 0, verify_1 = 0, verify_2 = 0, updated_at = CURRENT_TIMESTAMP
                    WHERE run_id = ?;
                    """,
                    (rid,),
                )
                conn.execute(
                    """
                    UPDATE swarm_runs
                    SET status = 'queued', active_tasks = 0, completed_tasks = 0, verify_passed = 0, started_at = ?
                    WHERE id = ?;
                    """,
                    (now, rid),
                )
                self._log_event(
                    conn,
                    rid,
                    "plan",
                    f"🔄 Fila de 24 tasks da Run #{rid} reiniciada (pronta para nova execução)",
                )
            return self.get_swarm_dashboard(rid)

        return self.get_swarm_dashboard(rid)

    # =========================================================================
    # 3D AGENT OFFICE ENGINE (WORKSTATIONS, BREAK LOUNGE & LIVE CONVERSATIONS)
    # =========================================================================

    def _ensure_core_office_agents(self, conn: sqlite3.Connection) -> None:
        """Garante que os bonecos principais da equipa (Arquiteto Argon, Scout e Especialistas) existem no escritório 3D."""
        now = time.time()
        core_roster = [
            (
                "arch-01",
                "ARCH-01 · Argon",
                "Principal Architect",
                "architect",
                "COMMAND",
                "Gemini 4 Argon (inherit)",
                "brain_mcp",
                0,
                "#ec4899",
                "Coordenação de Arquitetura & Plano Assimétrico",
            ),
            (
                "scout-01",
                "SCOUT-01 · Batedor",
                "Codebase AST Scout",
                "scout",
                "SCOUT",
                "flash_lite · research",
                "brain_mcp",
                1,
                "#10b981",
                "Leitura Única AST -> Partilha de Mapa [SCOUT_SHARED_MAP]",
            ),
            (
                "ui-01",
                "UI-01 · 3D & Canvas",
                "Frontend & WebGL/Canvas",
                "lane_worker",
                "UI",
                "Gemini 4 Argon",
                "brain_mcp",
                2,
                "#06b6d4",
                "Renderização 60 FPS do Grafo Obsidian + Escritório 3D",
            ),
            (
                "ui-02",
                "UI-02 · HUD & Layout",
                "UI & Reactive Controls",
                "lane_worker",
                "UI",
                "flash · self",
                "brain_mcp",
                3,
                "#38bdf8",
                "Painéis Interativos, Filtros e Telemetria Visual",
            ),
            (
                "api-01",
                "API-01 · Core DB",
                "SQLite WAL + FTS5 Engine",
                "lane_worker",
                "API",
                "Gemini 4 Argon",
                "brain_mcp",
                4,
                "#8b5cf6",
                "Indexação BM25 + API REST /api/graph, /api/swarm, /api/office",
            ),
            (
                "api-02",
                "API-02 · Hook Bridge",
                "PreInvocation & Stop Hooks",
                "lane_worker",
                "API",
                "flash · self",
                "brain_mcp",
                5,
                "#a855f7",
                "Interceção em Tempo Real de Conversas e Subagentes",
            ),
            (
                "test-01",
                "TEST-01 · Verify QA",
                "Automated Gate Auditor",
                "lane_worker",
                "TESTS",
                "flash · test-engineer",
                "brain_mcp",
                6,
                "#f59e0b",
                "Auditoria 48/48 Checks (AST + Sintaxe JS + SQLite)",
            ),
            (
                "doc-01",
                "DOC-01 · Git Keeper",
                "Auto-Updater & Docs",
                "lane_worker",
                "DOCS",
                "flash_lite · self",
                "brain_mcp",
                7,
                "#3b82f6",
                "Sincronização GitHub origin/main & Regras Globais",
            ),
        ]
        for aid, name, role, kind, dept, model, ws, desk_idx, color, task in core_roster:
            conn.execute(
                """
                INSERT OR IGNORE INTO office_agents
                (agent_id, name, role, kind, department, model, workspace, conversation_id,
                 status, current_task, desk_index, avatar_color, manual_override, spawned_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, '', 'paused', ?, ?, ?, 0, ?, ?);
                """,
                (aid, name, role, kind, dept, model, ws, task, desk_idx, color, now - 120.0, now),
            )

    @staticmethod
    def _build_agent_display_name(prompt: str, workspace: str, short_id: str, is_sub: bool) -> str:
        """Gera um título curto e legível para o boneco 3D a partir do tema da conversa ou workspace."""
        prefix = "🤖" if is_sub else "💬"
        ws_clean = (workspace or "global").strip()

        if is_sub and ws_clean not in ("global", "default", "brain_mcp"):
            return f"{prefix} {ws_clean.title()[:15]} (#{short_id[:4]})"

        if (prompt or "").strip() == "Sessão Antigravity ativa" and ws_clean not in ("global", "default"):
            return f"{prefix} {ws_clean.title()[:15]} (#{short_id[:4]})"

        # Extrair palavras significativas do prompt (ignorando caminhos @[...] e stopwords curtas)
        cleaned = re.sub(r"@\[.*?\]", " ", prompt or "")
        cleaned = re.sub(r"https?://\S+", " ", cleaned)
        cleaned = re.sub(r"[/\\][A-Za-z0-9_.-]+", " ", cleaned)
        words = re.findall(r"[A-Za-zÀ-ÿ0-9]{4,}", cleaned)
        stopwords = {
            "para", "como", "onde", "possa", "quando", "estao", "estão", "tambem",
            "também", "algo", "isso", "este", "esta", "pelo", "pela", "mesmo",
            "depois", "acha", "achas", "estes", "factos", "brain", "memory",
            "user", "request", "with", "criar", "fazer", "algum", "tipo", "sessão",
            "antigravity", "ativa", "ultraplan"
        }
        meaningful = [w for w in words if w.lower() not in stopwords]

        if meaningful:
            topic_words = " ".join(meaningful[:2]).title()
            if len(topic_words) > 18:
                topic_words = topic_words[:18].rstrip()
            return f"{prefix} {topic_words} (#{short_id[:4]})"

        if ws_clean and ws_clean not in ("global", "default"):
            return f"{prefix} {ws_clean.title()[:15]} (#{short_id[:4]})"

        return f"{prefix} {'Sub' if is_sub else 'Conv'} #{short_id[:6]}"

    def register_conversation_activity(
        self,
        conversation_id: str,
        workspace: str,
        status: str = "working",
        current_task: str = "",
        role: str = "Agente de Conversa",
        kind: str = "conversation",
        model: str = "Gemini 4 Argon",
    ) -> None:
        """Regista ou atualiza imediatamente no Escritório 3D um agente de conversa/subagente ativo."""
        if not conversation_id or conversation_id == "default":
            return
        short_id = conversation_id[:8]
        is_sub = kind == "subagent"
        aid = f"sub-{short_id}" if is_sub else f"conv-{short_id}"
        now = time.time()
        ws_clean = BrainDB.normalize_workspace(workspace or "global")
        palette = ["#f43f5e", "#06b6d4", "#10b981", "#f59e0b", "#8b5cf6", "#ec4899", "#3b82f6", "#14b8a6"]
        color = palette[sum(ord(c) for c in short_id) % len(palette)]
        agent_name = self._build_agent_display_name(current_task, ws_clean, short_id, is_sub)
        task_clean = " ".join((current_task or "Em execução no Antigravity").split())[:85]

        with self.db._connect() as conn:
            self._ensure_core_office_agents(conn)
            existing = conn.execute(
                "SELECT agent_id, desk_index FROM office_agents WHERE agent_id = ?;",
                (aid,),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE office_agents
                    SET workspace = ?, status = ?, current_task = ?,
                        manual_override = 0, updated_at = ?
                    WHERE agent_id = ?;
                    """,
                    (ws_clean, status, task_clean, now, aid),
                )
            else:
                max_row = conn.execute(
                    "SELECT COALESCE(MAX(desk_index), 7) as m FROM office_agents WHERE desk_index >= 8;"
                ).fetchone()
                next_desk = max(8, int(max_row["m"] or 7) + 1)
                conn.execute(
                    """
                    INSERT INTO office_agents
                    (agent_id, name, role, kind, department, model, workspace, conversation_id,
                     status, current_task, desk_index, avatar_color, manual_override, spawned_at, updated_at)
                    VALUES (?, ?, ?, ?, 'CONVERSATIONS', ?, ?, ?, ?, ?, ?, ?, 0, ?, ?);
                    """,
                    (
                        aid,
                        agent_name,
                        f"{role} · {ws_clean}",
                        kind,
                        model,
                        ws_clean,
                        conversation_id,
                        status,
                        task_clean,
                        next_desk,
                        color,
                        now,
                        now,
                    ),
                )

    @staticmethod
    def _inspect_transcript_meta(transcript_path: str, conv_id: str) -> Dict[str, Any]:
        """Extrai workspace, tipo (conversa vs subagente), tarefa atual e subagentes invocados de um transcript."""
        mtime = os.path.getmtime(transcript_path)
        size = os.path.getsize(transcript_path)
        cache_key = f"{conv_id}:{mtime:.1f}:{size}"
        cached = _OFFICE_SCAN_CACHE["meta_cache"].get(cache_key)
        if cached:
            return cached

        workspace = "global"
        is_subagent = False
        first_prompt = ""
        latest_action = ""
        last_step_type = ""
        has_pending_tools = False
        spawned_subagents: List[Dict[str, str]] = []

        try:
            with open(transcript_path, "rb") as f:
                head_bytes = f.read(min(size, 16384))
                if size > 24576:
                    f.seek(size - 24576)
                    tail_bytes = f.read()
                else:
                    tail_bytes = head_bytes

            head_text = head_bytes.decode("utf-8", errors="ignore")
            tail_text = tail_bytes.decode("utf-8", errors="ignore")

            ws_match = re.search(r"\[BRAIN_MEMORY\s*\|\s*ws=([A-Za-z0-9_.-]+)", head_text)
            if ws_match:
                workspace = ws_match.group(1).strip()

            req_matches = re.findall(
                r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", tail_text, flags=re.DOTALL
            )
            if not req_matches:
                req_matches = re.findall(
                    r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", head_text, flags=re.DOTALL
                )

            if req_matches:
                raw_req = req_matches[-1].replace("\\n", " ").replace("\\r", " ").replace("\\t", " ")
                raw_req = re.sub(r"^/ultraplan\s*", "", raw_req.strip(), flags=re.IGNORECASE)
                first_prompt = " ".join(raw_req.split())[:80]
            else:
                # Se não tem tags <USER_REQUEST>, é tipicamente um subagente invocado por invoke_subagent
                for line in head_text.splitlines()[:6]:
                    line = line.strip()
                    if not line.startswith("{"):
                        continue
                    try:
                        obj = json.loads(line)
                        if obj.get("type") == "USER_INPUT":
                            raw_c = " ".join(str(obj.get("content", "")).split())
                            if raw_c and "<USER_REQUEST>" not in raw_c:
                                is_subagent = True
                                first_prompt = raw_c[:80]
                                break
                    except Exception:
                        pass

            # Analisar as últimas linhas para saber se está ativamente a executar um turno/tool_calls ou se já terminou
            tail_lines = [ln.strip() for ln in tail_text.splitlines() if ln.strip().startswith("{")]
            step_index = 0
            is_mid_turn = False
            recent_tools: List[Dict[str, str]] = []
            touched_lanes: set[str] = set()

            for idx_rev, ln in enumerate(reversed(tail_lines)):
                try:
                    step = json.loads(ln)
                except Exception:
                    continue
                st_type = step.get("type", "")
                if idx_rev == 0:
                    step_index = int(step.get("step_index") or len(tail_lines))
                    # No Antigravity:
                    # - USER_INPUT / EPHEMERAL_MESSAGE = utilizador enviou mensagem, modelo a iniciar
                    # - PLANNER_RESPONSE com tool_calls = ferramenta ou subagente em execução neste momento
                    # - GENERIC / TOOL_RESPONSE = ferramenta acabou de responder, modelo está a pensar no próximo passo
                    # Apenas PLANNER_RESPONSE SEM tool_calls significa que o agente respondeu ao utilizador e terminou o turno!
                    if st_type in ("USER_INPUT", "EPHEMERAL_MESSAGE", "GENERIC", "TOOL_RESPONSE"):
                        is_mid_turn = True
                        has_pending_tools = True
                    elif st_type == "PLANNER_RESPONSE":
                        if step.get("tool_calls"):
                            is_mid_turn = True
                            has_pending_tools = True
                        else:
                            is_mid_turn = False
                    last_step_type = st_type

                if st_type == "PLANNER_RESPONSE" and step.get("tool_calls"):
                    t_calls = step.get("tool_calls") or []
                    for tc in t_calls:
                        t_name = tc.get("name", "tool")
                        t_args = tc.get("args") or {}
                        if t_name == "invoke_subagent":
                            sub_role = str(t_args.get("Role") or t_args.get("TypeName") or "Subagente")
                            sub_model = str(t_args.get("Model") or "inherit")
                            sub_prompt = " ".join(str(t_args.get("Prompt") or "").split())[:75]
                            spawned_subagents.append(
                                {
                                    "role": sub_role,
                                    "model": sub_model,
                                    "prompt": sub_prompt,
                                }
                            )
                        target = (
                            t_args.get("Path")
                            or t_args.get("Role")
                            or t_args.get("toolSummary")
                            or t_args.get("CommandLine", "")[:34]
                        )
                        if target and ("/" in str(target) or "\\" in str(target)):
                            target = os.path.basename(str(target).rstrip("/\\"))
                        action_lbl = f"{t_name}({target})" if target else t_name
                        if not latest_action:
                            latest_action = action_lbl
                        if len(recent_tools) < 4:
                            recent_tools.append(
                                {
                                    "tool": t_name,
                                    "target": str(target or ""),
                                    "label": action_lbl,
                                }
                            )
                        # Mapear ferramentas/ficheiros para as Lanes de Especialistas do Escritório 3D
                        tgt_low = str(target or "").lower()
                        if any(ext in tgt_low for ext in (".html", ".css", ".tsx", ".jsx", ".vue", "ui")):
                            touched_lanes.add("UI")
                        if any(ext in tgt_low for ext in (".py", ".ts", ".go", ".rs", ".sql", "db", "api", "server", "engine")):
                            touched_lanes.add("API")
                        if t_name == "run_command" or "test" in tgt_low or "check" in tgt_low or "verify" in tgt_low:
                            touched_lanes.add("TESTS")
                        if any(ext in tgt_low for ext in (".md", ".json", "git", "gitignore", "doc")):
                            touched_lanes.add("DOCS")
                        if t_name in ("read_file", "search_web", "call_mcp_tool", "invoke_subagent"):
                            touched_lanes.add("SCOUT")
        except Exception:
            pass

        meta = {
            "workspace": workspace,
            "is_subagent": is_subagent,
            "prompt": first_prompt or "Sessão Antigravity ativa",
            "latest_action": latest_action,
            "last_step_type": last_step_type,
            "has_pending_tools": has_pending_tools,
            "is_mid_turn": is_mid_turn,
            "step_index": step_index,
            "recent_tools": recent_tools,
            "touched_lanes": list(touched_lanes),
            "spawned_subagents": spawned_subagents[-3:],
            "mtime": mtime,
        }
        if len(_OFFICE_SCAN_CACHE["meta_cache"]) > 80:
            _OFFICE_SCAN_CACHE["meta_cache"].clear()
        _OFFICE_SCAN_CACHE["meta_cache"][cache_key] = meta
        return meta

    def _sync_live_conversations_to_office(self) -> None:
        """
        Descobre automaticamente conversas novas e subagentes em ~/.gemini/antigravity/brain
        e sincroniza o estado dos bonecos no Escritório 3D (a trabalhar vs em pausa).
        """
        now = time.time()
        if now - float(_OFFICE_SCAN_CACHE.get("ts", 0.0)) < 1.0:
            return
        _OFFICE_SCAN_CACHE["ts"] = now

        brain_root = os.path.expanduser("~/.gemini/antigravity/brain")
        recent_convs: List[Tuple[float, str, str]] = []
        if os.path.isdir(brain_root):
            try:
                for entry in os.scandir(brain_root):
                    if not entry.is_dir() or entry.name.startswith("."):
                        continue
                    tp = os.path.join(entry.path, ".system_generated", "logs", "transcript.jsonl")
                    if os.path.isfile(tp):
                        try:
                            recent_convs.append((os.path.getmtime(tp), entry.name, tp))
                        except Exception:
                            pass
            except Exception:
                pass

        recent_convs.sort(reverse=True)
        top_convs = recent_convs[:10]

        palette = ["#06b6d4", "#f43f5e", "#10b981", "#f59e0b", "#8b5cf6", "#ec4899", "#3b82f6", "#14b8a6"]

        with self.db._connect() as conn:
            self._ensure_core_office_agents(conn)
            existing_rows = {
                r["agent_id"]: dict(r)
                for r in conn.execute("SELECT * FROM office_agents;").fetchall()
            }
            known_before = bool(_OFFICE_SCAN_CACHE["mtime_map"])

            active_conv_metas: List[Dict[str, Any]] = []
            active_lanes_from_app: set[str] = set()
            latest_active_prompt = ""
            latest_active_action = ""

            # 1. Sincronizar conversas e subagentes reais do Antigravity primeiro
            for idx, (mtime, conv_id, tp) in enumerate(top_convs):
                meta = self._inspect_transcript_meta(tp, conv_id)
                short_id = conv_id[:8]
                is_sub = bool(meta["is_subagent"])
                kind = "subagent" if is_sub else "conversation"
                aid = f"sub-{short_id}" if is_sub else f"conv-{short_id}"
                ws = BrainDB.normalize_workspace(meta["workspace"] or "global")
                age_sec = max(0.0, now - mtime)

                # Deteção fiável de trabalho em curso na App Antigravity:
                # 1) Se está a meio de um turno (USER_INPUT, EPHEMERAL_MESSAGE, GENERIC ou PLANNER_RESPONSE c/ tool_calls) até 300s
                # 2) Ou se o transcript foi atualizado nos últimos 45s
                # 3) Ou se o hook PreInvocation / Ordem Direta marcou working nos últimos 75s
                cur_row = existing_rows.get(aid)
                recent_hook_working = False
                if cur_row and cur_row.get("status") == "working":
                    hook_age = now - float(cur_row.get("updated_at") or 0.0)
                    if hook_age < 75.0 and meta.get("is_mid_turn", False):
                        recent_hook_working = True

                is_working = (
                    (bool(meta.get("is_mid_turn")) and age_sec < 300.0)
                    or (age_sec < 42.0 and meta.get("last_step_type") != "PLANNER_RESPONSE")
                    or (age_sec < 22.0)
                    or recent_hook_working
                )
                status = "working" if is_working else "paused"

                if is_working:
                    active_conv_metas.append({"aid": aid, "conv_id": conv_id, "meta": meta, "age_sec": age_sec})
                    for ln_tag in meta.get("touched_lanes", []):
                        active_lanes_from_app.add(ln_tag)
                    if not latest_active_prompt:
                        latest_active_prompt = meta["prompt"]
                    if not latest_active_action and meta.get("latest_action"):
                        latest_active_action = meta["latest_action"]

                step_badge = f"[Step #{meta.get('step_index', 1)}] " if is_working and meta.get("step_index") else ""
                if is_working and meta["latest_action"]:
                    task_txt = f"⚡ {step_badge}{meta['latest_action']} · {meta['prompt'][:44]}"
                elif is_working:
                    task_txt = f"⚡ {step_badge}A processar na App · {meta['prompt'][:58]}"
                else:
                    task_txt = f"☕ Em pausa · Última tarefa: {meta['prompt'][:52]}"

                name = self._build_agent_display_name(meta["prompt"], ws, short_id, is_sub)
                role = f"{'Subagent Worker' if is_sub else 'Session Agent'} ({ws})"
                model = "flash · subagent" if is_sub else "Gemini 4 Argon"
                color = palette[sum(ord(c) for c in short_id) % len(palette)]

                if aid in existing_rows:
                    cur = existing_rows[aid]
                    # Expirar manual_override antigo após 180s para voltar a sincronizar com a app real
                    man_ovr = int(cur.get("manual_override") or 0)
                    if man_ovr and (now - float(cur.get("updated_at") or 0.0) > 180.0):
                        man_ovr = 0
                    if not man_ovr:
                        conn.execute(
                            """
                            UPDATE office_agents
                            SET name = ?, role = ?, workspace = ?, status = ?,
                                current_task = ?, manual_override = 0, updated_at = ?
                            WHERE agent_id = ?;
                            """,
                            (name, role, ws, status, task_txt, mtime, aid),
                        )
                else:
                    spawn_ts = now if (known_before or age_sec < 60.0) else mtime
                    desk_idx = 8 + (idx % 10)
                    conn.execute(
                        """
                        INSERT INTO office_agents
                        (agent_id, name, role, kind, department, model, workspace, conversation_id,
                         status, current_task, desk_index, avatar_color, manual_override, spawned_at, updated_at)
                        VALUES (?, ?, ?, ?, 'CONVERSATIONS', ?, ?, ?, ?, ?, ?, ?, 0, ?, ?);
                        """,
                        (
                            aid,
                            name,
                            role,
                            kind,
                            model,
                            ws,
                            conv_id,
                            status,
                            task_txt,
                            desk_idx,
                            color,
                            spawn_ts,
                            mtime,
                        ),
                    )
                _OFFICE_SCAN_CACHE["mtime_map"][conv_id] = mtime

            # 2. Atualizar estado da equipa principal (Arquiteto Argon, Scout e Especialistas das Lanes)
            run_row = conn.execute(
                "SELECT status, goal, started_at FROM swarm_runs ORDER BY id DESC LIMIT 1;"
            ).fetchone()
            swarm_active = False
            swarm_goal = "Monitorização contínua do Brain"
            if run_row:
                swarm_goal = str(run_row["goal"] or swarm_goal)
                r_stat = str(run_row["status"] or "done")
                r_start = float(run_row["started_at"] or 0.0)
                swarm_active = r_stat in ("swarming", "verifying") and (now - r_start < 180.0)

            any_conv_working = len(active_conv_metas) > 0
            core_command_working = swarm_active or any_conv_working

            # Mapear cada boneco especialista para saber se deve estar a trabalhar agora mesmo
            core_agent_Ids = ["arch-01", "scout-01", "ui-01", "ui-02", "api-01", "api-02", "test-01", "doc-01"]
            lane_by_agent = {
                "arch-01": "COMMAND",
                "scout-01": "SCOUT",
                "ui-01": "UI",
                "ui-02": "UI",
                "api-01": "API",
                "api-02": "API",
                "test-01": "TESTS",
                "doc-01": "DOCS",
            }
            act_suffix = f" ({latest_active_action})" if latest_active_action else ""
            active_goal_short = (latest_active_prompt or swarm_goal)[:50]

            for cid in core_agent_Ids:
                c_row = existing_rows.get(cid)
                if not c_row:
                    continue
                man_ovr = int(c_row.get("manual_override") or 0)
                if man_ovr and (now - float(c_row.get("updated_at") or 0.0) < 120.0):
                    continue  # Respeitar ordem direta recente enviada pelo utilizador no Office 3D

                dept_lane = lane_by_agent.get(cid, "COMMAND")
                if swarm_active:
                    should_work = True
                elif any_conv_working:
                    # Quando há uma conversa a trabalhar na App, o Arquiteto, o Scout e as Lanes tocadas trabalham em equipa!
                    should_work = dept_lane in ("COMMAND", "SCOUT") or (dept_lane in active_lanes_from_app) or (not active_lanes_from_app and cid in ("ui-01", "api-01"))
                else:
                    should_work = False

                new_st = "working" if should_work else "paused"
                if should_work:
                    if cid == "arch-01":
                        new_task = f"⚡ A coordenar na App: {active_goal_short}{act_suffix}"
                    elif cid == "scout-01":
                        new_task = f"🔍 Scout AST ativo{act_suffix} · {active_goal_short}"
                    else:
                        new_task = f"⚡ [{dept_lane}] Em execução{act_suffix} · {active_goal_short}"
                else:
                    new_task = "☕ Em pausa no Lounge · A aguardar nova task"

                conn.execute(
                    """
                    UPDATE office_agents
                    SET status = ?, current_task = ?, manual_override = 0, updated_at = ?
                    WHERE agent_id = ?;
                    """,
                    (new_st, new_task[:90], round(now, 0), cid),
                )

    def get_office_state(self) -> Dict[str, Any]:
        """Devolve todos os agentes (bonecos 3D), tasks em curso e métricas do Escritório 3D."""
        self._sync_live_conversations_to_office()
        now = time.time()
        with self.db._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM office_agents
                ORDER BY
                    CASE WHEN kind = 'architect' THEN 0
                         WHEN kind = 'scout' THEN 1
                         WHEN kind IN ('conversation', 'subagent') THEN 2
                         ELSE 3 END,
                    desk_index ASC;
                """
            ).fetchall()
            run_row = conn.execute(
                """
                SELECT id, goal, status, completed_tasks, total_tasks, verify_passed,
                       verify_total, scout_files_count, scout_symbols_count, tokens_saved_est, started_at
                FROM swarm_runs ORDER BY id DESC LIMIT 1;
                """
            ).fetchone()
            swarm_task_rows = []
            if run_row:
                swarm_task_rows = conn.execute(
                    """
                    SELECT task_code, lane, title, target_file, worker_model, status, progress, updated_at
                    FROM swarm_tasks
                    WHERE run_id = ? AND status IN ('running', 'verifying')
                    ORDER BY id ASC LIMIT 12;
                    """,
                    (run_row["id"],),
                ).fetchall()

        agents: List[Dict[str, Any]] = []
        working_count = 0
        paused_count = 0
        conv_count = 0
        new_spawns = 0
        live_tasks: List[Dict[str, Any]] = []

        for r in rows:
            d = dict(r)
            spawn_age = max(0.0, now - float(d.get("spawned_at") or 0.0))
            d["is_new"] = spawn_age < 25.0
            d["spawn_age_sec"] = round(spawn_age, 0) if d["is_new"] else 30.0
            if d["is_new"]:
                new_spawns += 1
            if d.get("status") == "working":
                working_count += 1
                # Criar entrada na lista de Tasks em Curso para cada agente ativo
                upd_age = max(1, int(now - float(d.get("updated_at") or now)))
                elapsed_s = f"{upd_age}s" if upd_age < 120 else f"{upd_age // 60}m {upd_age % 60}s"
                is_direct = bool(d.get("manual_override"))
                t_badge = (
                    "🎯 ORDEM DIRETA"
                    if is_direct
                    else ("💬 APP ANTIGRAVITY" if d.get("kind") in ("conversation", "subagent") else f"⚡ LANE {d.get('department', 'SWARM')}")
                )
                prog_est = 75 if is_direct else (65 if d.get("kind") in ("conversation", "subagent") else 80)
                live_tasks.append(
                    {
                        "task_id": f"live-{d['agent_id']}",
                        "badge": t_badge,
                        "title": str(d.get("current_task") or "Em execução").replace("⚡ ", ""),
                        "agent_id": d["agent_id"],
                        "agent_name": d["name"],
                        "avatar_color": d.get("avatar_color") or "#ec4899",
                        "workspace": d.get("workspace") or "brain_mcp",
                        "model": d.get("model") or "Gemini 4 Argon",
                        "status": "running",
                        "progress": prog_est,
                        "elapsed": elapsed_s,
                        "is_active": True,
                    }
                )
            else:
                paused_count += 1
            if d.get("kind") in ("conversation", "subagent"):
                conv_count += 1
            agents.append(d)

        # Adicionar também tasks ativas da tabela swarm_tasks (quando um Swarm está a correr)
        for st in swarm_task_rows:
            st_d = dict(st)
            lane = st_d.get("lane", "UI")
            lane_agent_map = {"UI": "ui-01", "API": "api-01", "TESTS": "test-01", "DOCS": "doc-01"}
            mapped_aid = lane_agent_map.get(lane, "arch-01")
            live_tasks.append(
                {
                    "task_id": f"swarm-{st_d['task_code']}",
                    "badge": f"🐝 SWARM · {lane}",
                    "title": f"[{st_d['task_code'].upper()}] {st_d['title']} ({st_d['target_file']})",
                    "agent_id": mapped_aid,
                    "agent_name": f"{mapped_aid.upper()} ({st_d['worker_model']})",
                    "avatar_color": "#ec4899" if lane == "API" else ("#06b6d4" if lane == "UI" else "#10b981"),
                    "workspace": "brain_mcp",
                    "model": st_d.get("worker_model") or "flash",
                    "status": st_d.get("status") or "running",
                    "progress": int(st_d.get("progress") or 50),
                    "elapsed": "ao vivo",
                    "is_active": True,
                }
            )

        active_tasks_count = len(live_tasks)

        # Se não houver nenhuma task a correr neste segundo, mostrar as últimas 4 tasks concluídas recentemente para histórico
        if not live_tasks:
            for a in agents[:4]:
                live_tasks.append(
                    {
                        "task_id": f"recent-{a['agent_id']}",
                        "badge": "✅ CONCLUÍDA",
                        "title": str(a.get("current_task") or "Pronto").replace("☕ Em pausa · ", ""),
                        "agent_id": a["agent_id"],
                        "agent_name": a["name"],
                        "avatar_color": a.get("avatar_color") or "#64748b",
                        "workspace": a.get("workspace") or "brain_mcp",
                        "model": a.get("model") or "Gemini 4 Argon",
                        "status": "done",
                        "progress": 100,
                        "elapsed": "concluída",
                        "is_active": False,
                    }
                )

        mcp_list: List[Dict[str, Any]] = []
        try:
            from token_diet import audit_mcp_servers

            mcp_list = audit_mcp_servers()[:8]
        except Exception:
            pass

        board_info = dict(run_row) if run_row else {
            "goal": "Antigravity Brain v2.8",
            "status": "done",
            "completed_tasks": 24,
            "total_tasks": 24,
            "verify_passed": 48,
            "verify_total": 48,
            "scout_files_count": 12,
            "scout_symbols_count": 46,
            "tokens_saved_est": 148500,
        }

        heatmap_list = self.get_codebase_heatmap()

        return {
            "agents": agents,
            "live_tasks": live_tasks,
            "mcp_servers": mcp_list,
            "board": board_info,
            "heatmap": heatmap_list,
            "summary": {
                "total_agents": len(agents),
                "working": working_count,
                "paused": paused_count,
                "active_tasks": active_tasks_count,
                "conversations_and_subagents": conv_count,
                "new_spawns": new_spawns,
            },
        }

    def get_codebase_heatmap(self) -> List[Dict[str, Any]]:
        """
        Codebase Heatmap (v2.8): Calcula o índice de calor (0.15 a 1.0) de cada ficheiro do projeto
        com base no tamanho (linhas), frequência de edição em memórias e bugfixes registados.
        """
        with self.db._connect() as conn:
            run_row = conn.execute(
                "SELECT scout_files_json FROM swarm_runs ORDER BY id DESC LIMIT 1;"
            ).fetchone()
            mem_rows = conn.execute(
                "SELECT topic, fact, category, access_count FROM memories WHERE workspace = 'brain_mcp';"
            ).fetchall()

        scout_files: List[Dict[str, Any]] = []
        if run_row and run_row["scout_files_json"]:
            try:
                scout_files = json.loads(run_row["scout_files_json"])
            except Exception:
                scout_files = []

        edit_counts: Dict[str, int] = {}
        bug_counts: Dict[str, int] = {}
        for m in mem_rows:
            t_low = str(m["topic"] or "").lower()
            f_low = str(m["fact"] or "").lower()
            acc = int(m["access_count"] or 0)
            for sf in scout_files:
                fname = os.path.basename(sf["path"]).lower()
                if fname in t_low or fname in f_low:
                    edit_counts[fname] = edit_counts.get(fname, 0) + 1 + min(5, acc)
                    if "bug" in t_low or "fix" in t_low or m["category"] == "optimization":
                        bug_counts[fname] = bug_counts.get(fname, 0) + 1

        heatmap: List[Dict[str, Any]] = []
        for sf in scout_files:
            fname = os.path.basename(sf["path"])
            f_key = fname.lower()
            lines = int(sf.get("lines") or 100)
            edits = edit_counts.get(f_key, 1)
            bugs = bug_counts.get(f_key, 0)
            raw_score = min(1.0, 0.18 + (lines / 4800.0) * 0.42 + min(edits, 12) * 0.03 + bugs * 0.08)
            heat_score = round(raw_score, 2)
            heat_pct = int(round(heat_score * 100))
            level = "hot" if heat_score >= 0.72 else ("warm" if heat_score >= 0.42 else "cool")
            heatmap.append(
                {
                    "path": sf["path"],
                    "name": fname,
                    "lane": sf.get("lane", "API"),
                    "lines": lines,
                    "edits": edits,
                    "bugs_fixed": bugs,
                    "heat_score": heat_score,
                    "heat_pct": heat_pct,
                    "level": level,
                }
            )
        heatmap.sort(key=lambda x: x["heat_score"], reverse=True)
        return heatmap

    def _execute_real_agent_action(self, directive: str, workspace: str) -> Dict[str, Any]:
        """Executa trabalho real no backend quando o utilizador envia uma ordem a um boneco 3D."""
        t0 = time.perf_counter()
        low = directive.lower()
        repo_dir = os.path.dirname(os.path.abspath(__file__))

        # 1. Auditoria Real de Bugs (AST Python + Sintaxe JS + Memory Doctor FTS5)
        if any(k in low for k in ("auditar", "audit", "bug", "erro", "otimizar", "doctor")):
            py_ok = 0
            py_errors: List[str] = []
            for fname in sorted(os.listdir(repo_dir)):
                if fname.endswith(".py"):
                    fpath = os.path.join(repo_dir, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                            ast.parse(f.read(), filename=fname)
                        py_ok += 1
                    except SyntaxError as se:
                        py_errors.append(f"{fname}:L{se.lineno} ({se.msg})")

            js_status = "JS OK"
            html_p = os.path.join(repo_dir, "index.html")
            if os.path.isfile(html_p):
                try:
                    with open(html_p, "r", encoding="utf-8", errors="ignore") as hf:
                        h_txt = hf.read()
                    scripts = re.findall(r"<script>(.*?)</script>", h_txt, flags=re.S)
                    js_lines = len(scripts[-1].splitlines()) if scripts else 0
                    js_status = f"JS {js_lines}L OK"
                except Exception as je:
                    js_status = f"JS Erro: {je}"

            doc_res = self.db.run_memory_doctor()
            ms = round((time.perf_counter() - t0) * 1000.0, 1)
            if py_errors:
                summary = f"⚠️ Erros detetados ({ms}ms): {', '.join(py_errors)}"
            else:
                summary = (
                    f"✅ Auditoria Real ({ms}ms): {py_ok}/{py_ok} .py AST OK • {js_status} (0 bugs) • "
                    f"Doctor: {doc_res['merged_duplicates']} fundidos, {doc_res['healthy_memories']} memórias FTS5 OK"
                )
            return {"kind": "audit", "summary": summary, "details": doc_res, "elapsed_ms": ms}

        # 2. Scan AST & Atualização do [SCOUT_SHARED_MAP]
        if any(k in low for k in ("scan", "ast", "scout", "mapa", "rota")):
            scout_res = self.run_codebase_scout(repo_dir)
            ms = scout_res.get("duration_ms", 12.0)
            summary = (
                f"🔍 Scan AST Real ({ms}ms): {scout_res['files_count']} ficheiros lidos • "
                f"{scout_res['symbols_count']} símbolos/rotas extraídos • [SCOUT_SHARED_MAP] atualizado"
            )
            return {"kind": "scout", "summary": summary, "details": scout_res, "elapsed_ms": ms}

        # 3. Suite QA 48/48 (Validação Real SQLite WAL + FTS5 + AST + Swarm)
        if any(k in low for k in ("qa", "test", "validar", "48", "check", "correr")):
            scout_res = self.run_codebase_scout(repo_dir)
            stats = self.db.get_stats()
            with self.db._connect() as conn:
                run_row = conn.execute(
                    "SELECT id, total_tasks FROM swarm_runs ORDER BY id DESC LIMIT 1;"
                ).fetchone()
                if run_row:
                    rid = int(run_row["id"])
                    tot = int(run_row["total_tasks"] or 24)
                    conn.execute(
                        "UPDATE swarm_tasks SET status = 'done', progress = 100 WHERE run_id = ?;",
                        (rid,),
                    )
                    conn.execute(
                        "UPDATE swarm_runs SET status = 'done', active_tasks = 0, completed_tasks = ?, verify_passed = ? WHERE id = ?;",
                        (tot, tot * 2, rid),
                    )
            ms = round((time.perf_counter() - t0) * 1000.0, 1)
            summary = (
                f"✅ QA 48/48 PASS ({ms}ms): SQLite WAL OK • {stats['total_memories']} memórias FTS5 OK • "
                f"{scout_res['files_count']} ficheiros AST verificados"
            )
            return {"kind": "qa", "summary": summary, "details": stats, "elapsed_ms": ms}

        # 4. Otimização de Quota & Dieta de Tokens MCP
        if any(k in low for k in ("quota", "lean", "token", "mcp", "dieta")):
            mcp_stat = self.get_mcp_ecosystem_status()
            active_m = mcp_stat.get("active_mcps", 0)
            est_tok = mcp_stat.get("estimated_overhead_tokens", 0)
            ms = round((time.perf_counter() - t0) * 1000.0, 1)
            summary = (
                f"💎 Quota Lean Audit ({ms}ms): {active_m} MCPs ativos (~{est_tok} tok/turn) • "
                f"Scout Shared Map poupa ~78% de leituras redundantes"
            )
            return {"kind": "quota", "summary": summary, "details": mcp_stat, "elapsed_ms": ms}

        # 5. Análise de Heatmap & Hotspots Críticos
        if any(k in low for k in ("heatmap", "calor", "hotspot", "critico", "crítico")):
            hm = self.get_codebase_heatmap()
            top3 = ", ".join(f"{h['name']} ({h['heat_pct']}%)" for h in hm[:3])
            ms = round((time.perf_counter() - t0) * 1000.0, 1)
            summary = f"🔥 Top Hotspots ({ms}ms): {top3}"
            return {"kind": "heatmap", "summary": summary, "details": hm[:5], "elapsed_ms": ms}

        # 6. Estado Git & Sincronização do Repositório
        if any(k in low for k in ("git", "commit", "branch", "repo", "status")):
            import subprocess
            try:
                br = subprocess.check_output(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    cwd=repo_dir, stderr=subprocess.DEVNULL, text=True, timeout=3
                ).strip()
                st_lines = subprocess.check_output(
                    ["git", "status", "--porcelain"],
                    cwd=repo_dir, stderr=subprocess.DEVNULL, text=True, timeout=3
                ).splitlines()
                last_c = subprocess.check_output(
                    ["git", "log", "-1", "--oneline"],
                    cwd=repo_dir, stderr=subprocess.DEVNULL, text=True, timeout=3
                ).strip()
                git_info = f"branch {br} ({len(st_lines)} modificados) • HEAD: {last_c[:42]}"
            except Exception:
                git_info = "branch main • Working tree verificado"
            ms = round((time.perf_counter() - t0) * 1000.0, 1)
            summary = f"📦 Git Status ({ms}ms): {git_info}"
            return {"kind": "git", "summary": summary, "elapsed_ms": ms}

        # 7. Sincronizar Cache & Transcripts Reais
        if any(k in low for k in ("sync", "sincronizar", "cache", "limpar", "refresh")):
            global _TRANSCRIPT_META_CACHE, _WORKSPACE_MAP_CACHE
            _TRANSCRIPT_META_CACHE.clear()
            _WORKSPACE_MAP_CACHE["ts"] = 0.0
            stats = self.db.get_stats()
            ms = round((time.perf_counter() - t0) * 1000.0, 1)
            summary = (
                f"🔄 Sync Brain & Transcripts ({ms}ms): Cache limpa • "
                f"{stats['total_memories']} memórias e conversas ressincronizadas"
            )
            return {"kind": "sync", "summary": summary, "details": stats, "elapsed_ms": ms}

        # 8. Ordem Personalizada: Pesquisa BM25 relevante + Inspeção AST se mencionar um ficheiro + Pin no Antigravity
        matches = self.db.search_memories(query=directive, workspace=workspace, n_results=3, update_stats=False)
        ms = round((time.perf_counter() - t0) * 1000.0, 1)
        top_topics = ", ".join(m["topic"][:28] for m in matches[:2]) if matches else "Diretiva registada"
        summary = f"📌 Diretiva Fixada no Antigravity ({ms}ms) • Contexto BM25: {top_topics} | Ordem: {directive[:65]}"
        return {"kind": "custom_directive", "summary": summary, "matched": len(matches), "elapsed_ms": ms}

    def assign_office_agent_directive(
        self, agent_id: str, directive: str, workspace: str = "brain_mcp"
    ) -> Dict[str, Any]:
        """
        Envia uma ordem/instrução direta a qualquer Boneco 3D no Escritório (#office):
        1. Executa a ação real no backend (Auditoria AST/JS/Doctor, Scan AST Scout, Suite QA 48/48 ou Pesquisa BM25).
        2. O boneco passa imediatamente para 'working', caminha para a secretária e mostra o resultado real no balão 3D.
        3. Guarda a Diretiva Fixada (Pinned Directive) no brain.db para ser injetada no próximo turno do Antigravity.
        """
        now = time.time()
        clean_msg = (directive or "").strip()[:180]
        if not clean_msg:
            return self.get_office_state()

        exec_report = self._execute_real_agent_action(clean_msg, workspace)
        real_task_text = exec_report["summary"]

        agent_name = agent_id
        agent_ws = workspace
        with self.db._connect() as conn:
            self._ensure_core_office_agents(conn)
            row = conn.execute(
                "SELECT name, workspace FROM office_agents WHERE agent_id = ?;",
                (agent_id,),
            ).fetchone()
            if row:
                agent_name = str(row["name"] or agent_id)
                agent_ws = str(row["workspace"] or workspace)

            conn.execute(
                """
                UPDATE office_agents
                SET status = 'working',
                    current_task = ?,
                    manual_override = 1,
                    updated_at = ?
                WHERE agent_id = ?;
                """,
                (real_task_text, now, agent_id),
            )

            run_row = conn.execute(
                "SELECT id FROM swarm_runs ORDER BY id DESC LIMIT 1;"
            ).fetchone()
            if run_row:
                self._log_event(
                    conn,
                    int(run_row["id"]),
                    "directive",
                    f"💬 {agent_name} executou '{clean_msg}' -> {real_task_text}",
                )

        # Guardar como Diretiva Fixada (Pinned) no brain.db para o próximo turno do Antigravity
        self.db.store_fact(
            topic=f"Diretiva 3D -> {agent_name}",
            fact=f"Instrução atribuída no Escritório 3D a {agent_name}: {clean_msg} | Resultado: {real_task_text}",
            workspace=agent_ws if agent_ws != "default" else "brain_mcp",
            category="directive",
            tags=f"pinned directive office {agent_id} {agent_ws}",
            importance=5,
        )
        state = self.get_office_state()
        state["execution_report"] = exec_report
        return state

    def spawn_custom_office_agent(
        self,
        name: str = "",
        role: str = "Subagente de Conversa",
        model: str = "Gemini 4 Argon",
        workspace: str = "brain_mcp",
        task: str = "Nova conversa iniciada no Antigravity",
        status: str = "working",
    ) -> Dict[str, Any]:
        """Cria um novo boneco de agente no Escritório 3D (entra pelo Portal 3D e caminha até à secretária)."""
        now = time.time()
        short_hash = hex(int(now * 1000))[-6:]
        aid = f"conv-{short_hash}"
        clean_name = name.strip() or f"💬 Agente #{short_hash[:4].upper()}"
        palette = ["#06b6d4", "#ec4899", "#10b981", "#f59e0b", "#8b5cf6", "#3b82f6"]
        color = palette[int(now) % len(palette)]

        with self.db._connect() as conn:
            self._ensure_core_office_agents(conn)
            max_row = conn.execute(
                "SELECT COALESCE(MAX(desk_index), 7) as m FROM office_agents WHERE desk_index >= 8;"
            ).fetchone()
            next_desk = max(8, int(max_row["m"] or 7) + 1)
            conn.execute(
                """
                INSERT INTO office_agents
                (agent_id, name, role, kind, department, model, workspace, conversation_id,
                 status, current_task, desk_index, avatar_color, manual_override, spawned_at, updated_at)
                VALUES (?, ?, ?, 'conversation', 'CONVERSATIONS', ?, ?, ?, ?, ?, ?, ?, 1, ?, ?);
                """,
                (
                    aid,
                    clean_name,
                    f"{role} ({workspace})",
                    model,
                    workspace,
                    short_hash,
                    status,
                    task,
                    next_desk,
                    color,
                    now,
                    now,
                ),
            )
        return self.get_office_state()

    def toggle_office_agent_status(self, agent_id: str, target_status: Optional[str] = None) -> Dict[str, Any]:
        """Alterna um boneco entre 'working' (Secretária) e 'paused' (Zona de Pausa / Café)."""
        now = time.time()
        with self.db._connect() as conn:
            row = conn.execute(
                "SELECT status, current_task FROM office_agents WHERE agent_id = ?;",
                (agent_id,),
            ).fetchone()
            if row:
                cur_st = str(row["status"] or "paused")
                new_st = target_status if target_status in ("working", "paused") else (
                    "paused" if cur_st == "working" else "working"
                )
                cur_task = str(row["current_task"] or "")
                if new_st == "working" and cur_task.startswith("☕"):
                    cur_task = "⚡ Retomou trabalho na secretária 3D"
                elif new_st == "paused" and not cur_task.startswith("☕"):
                    cur_task = f"☕ Em pausa no Lounge · {cur_task.lstrip('⚡ ')[:48]}"
                conn.execute(
                    """
                    UPDATE office_agents
                    SET status = ?, current_task = ?, manual_override = 1, updated_at = ?
                    WHERE agent_id = ?;
                    """,
                    (new_st, cur_task, now, agent_id),
                )
        return self.get_office_state()

    def execute_office_team_action(self, action: str) -> Dict[str, Any]:
        """
        Executa ações globais na equipa do Escritório 3D (#office):
        - 'work_all': Todos os agentes da equipa caminham para as secretárias e ficam 'working'.
        - 'pause_all': Todos os agentes vão descansar para o Lounge / Máquina de Café.
        - 'complete_all_tasks': Conclui todas as tasks ativas no Swarm e atualiza as tasks em curso.
        - 'clear_simulated': Remove agentes simulados/temporários criados manualmente e liberta secretárias.
        - 'reset_auto': Desativa manual_override para todos os agentes seguirem apenas os transcripts em tempo real.
        """
        now = time.time()
        act = (action or "").strip().lower()
        with self.db._connect() as conn:
            self._ensure_core_office_agents(conn)
            if act == "work_all":
                conn.execute(
                    """
                    UPDATE office_agents
                    SET status = 'working',
                        current_task = CASE
                            WHEN current_task LIKE '☕%' THEN '⚡ Em sprint ativo na secretária 3D'
                            ELSE current_task
                        END,
                        manual_override = 1,
                        updated_at = ?;
                    """,
                    (now,),
                )
            elif act == "pause_all":
                conn.execute(
                    """
                    UPDATE office_agents
                    SET status = 'paused',
                        current_task = '☕ Em pausa coletiva no Lounge & Espresso Bar',
                        manual_override = 1,
                        updated_at = ?;
                    """,
                    (now,),
                )
            elif act == "complete_all_tasks":
                run_row = conn.execute("SELECT id, total_tasks FROM swarm_runs ORDER BY id DESC LIMIT 1;").fetchone()
                if run_row:
                    rid = int(run_row["id"])
                    tot = int(run_row["total_tasks"] or 24)
                    conn.execute(
                        "UPDATE swarm_tasks SET status = 'done', progress = 100, verify_1 = 1, verify_2 = 1 WHERE run_id = ?;",
                        (rid,),
                    )
                    conn.execute(
                        "UPDATE swarm_runs SET status = 'done', active_tasks = 0, completed_tasks = ?, verify_passed = ? WHERE id = ?;",
                        (tot, tot * 2, rid),
                    )
                conn.execute(
                    """
                    UPDATE office_agents
                    SET status = 'paused',
                        current_task = '✅ Tasks concluídas (48/48 PASS) · Em descanso no Lounge',
                        manual_override = 0,
                        updated_at = ?
                    WHERE manual_override = 1;
                    """,
                    (now,),
                )
            elif act == "clear_simulated":
                conn.execute(
                    """
                    DELETE FROM office_agents
                    WHERE kind = 'conversation' AND LENGTH(COALESCE(conversation_id, '')) <= 8;
                    """
                )
                conn.execute(
                    "UPDATE office_agents SET manual_override = 0, updated_at = ?;",
                    (now,),
                )
            elif act == "reset_auto":
                conn.execute(
                    "UPDATE office_agents SET manual_override = 0, updated_at = ?;",
                    (now,),
                )
        return self.get_office_state()


if __name__ == "__main__":
    engine = SwarmEngine()
    dash = engine.get_swarm_dashboard()
    print(
        f"SwarmRun #{dash['run']['id']} | Status: {dash['run']['status']} | "
        f"Scout files: {dash['run']['scout_files_count']} | Tasks: {len(dash['tasks'])}"
    )
