import argparse
import ast
import hashlib
import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from db_engine import BrainDB
from swarm_engine import CODE_EXTENSIONS, IGNORE_DIRS as IGNORED_DIRS, SwarmEngine

_WATCHER_DAEMON_STARTED = False
_WATCHER_LOCK = threading.Lock()
_WATCHER_RUNTIME_STATE: Dict[str, Any] = {
    "daemon_active": False,
    "started_at": 0,
    "last_scan_ts": 0,
    "files_monitored": 0,
    "saves_detected": 0,
    "high_risk_flagged": 0,
}


class AstImpactWatcher:
    """
    Automated File-Save AST & Blast Radius Analyzer:
    Detects file saves via mtime_ns + SHA-256 content hashing, diffs individual AST symbol
    bodies to pinpoint which functions/classes were modified, evaluates the reverse call/import
    blast radius, and preemptively flags HIGH/CRITICAL changes in SQLite & BrainDB.
    """

    def __init__(self, db: Optional[BrainDB] = None, workspace_path: str = "") -> None:
        self.db = db or BrainDB()
        self.swarm = SwarmEngine(self.db)
        self.workspace_root = Path(workspace_path).resolve() if workspace_path else Path(CURRENT_DIR).resolve()
        self._file_state_cache: Dict[str, Dict[str, Any]] = {}
        self._init_watcher_schema()

    def _init_watcher_schema(self) -> None:
        with self.db._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS ast_save_audits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT NOT NULL,
                    workspace TEXT NOT NULL DEFAULT 'global',
                    sha256 TEXT NOT NULL,
                    risk_level TEXT NOT NULL DEFAULT 'LOW',
                    blast_radius TEXT NOT NULL DEFAULT 'LOW',
                    affected_files_count INTEGER NOT NULL DEFAULT 0,
                    total_references INTEGER NOT NULL DEFAULT 0,
                    syntax_ok INTEGER NOT NULL DEFAULT 1,
                    secrets_ok INTEGER NOT NULL DEFAULT 1,
                    changed_symbols_json TEXT NOT NULL DEFAULT '[]',
                    recommended_tests_json TEXT NOT NULL DEFAULT '[]',
                    callers_json TEXT NOT NULL DEFAULT '[]',
                    summary TEXT NOT NULL DEFAULT '',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_ast_save_audits_file
                ON ast_save_audits(file_path, id DESC);

                CREATE TABLE IF NOT EXISTS ast_file_hashes (
                    file_path TEXT PRIMARY KEY,
                    workspace TEXT DEFAULT 'global',
                    sha256 TEXT NOT NULL,
                    mtime_ns INTEGER DEFAULT 0,
                    symbols_json TEXT DEFAULT '{}',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS ast_symbol_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT NOT NULL,
                    symbol_name TEXT NOT NULL,
                    symbol_kind TEXT DEFAULT 'function',
                    start_line INTEGER DEFAULT 1,
                    end_line INTEGER DEFAULT 1,
                    sha256 TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(file_path, symbol_name)
                );
                """
            )

    @staticmethod
    def _scan_brace_end_line(lines: List[str], start_idx: int, max_scan: int = 400) -> int:
        """
        Scans brace depth `{` / `}` from `start_idx` up to `max_scan` lines, ignoring braces
        inside string literals ('...', "...", `...`) and comments (//..., /*...*/).
        """
        brace_depth = 0
        started_brace = False
        in_Quote: Optional[str] = None
        in_block_comment = False
        limit_idx = min(len(lines), start_idx + max_scan)

        for idx in range(start_idx, limit_idx):
            ln = lines[idx]
            i = 0
            n = len(ln)
            while i < n:
                ch = ln[i]
                nxt = ln[i + 1] if i + 1 < n else ""
                if in_block_comment:
                    if ch == "*" and nxt == "/":
                        in_block_comment = False
                        i += 2
                        continue
                    i += 1
                    continue
                if in_Quote is not None:
                    if ch == "\\":
                        i += 2
                        continue
                    if ch == in_Quote:
                        in_Quote = None
                    i += 1
                    continue
                if ch == "/" and nxt == "/":
                    break
                if ch == "/" and nxt == "*":
                    in_block_comment = True
                    i += 2
                    continue
                if ch in ("'", '"', "`"):
                    in_Quote = ch
                    i += 1
                    continue
                if ch == "{":
                    brace_depth += 1
                    started_brace = True
                elif ch == "}":
                    brace_depth -= 1
                    if started_brace and brace_depth <= 0:
                        return idx + 1
                i += 1
            if not started_brace and idx > start_idx + 3:
                break

        return limit_idx if started_brace else min(len(lines), start_idx + 24)

    @staticmethod
    def extract_symbol_hashes(file_path: Path, content: str) -> Dict[str, Dict[str, Any]]:
        """
        Extracts functions/classes and computes a SHA-256 digest of each symbol's body
        so the watcher can pinpoint which exact symbols were modified on file save.
        """
        ext = file_path.suffix.lower()
        lines = content.splitlines()
        symbols: Dict[str, Dict[str, Any]] = {}

        if ext == ".py":
            try:
                tree = ast.parse(content)
                for node in tree.body:
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        s_line = int(getattr(node, "lineno", 1))
                        e_line = int(getattr(node, "end_lineno", s_line))
                        body_txt = "\n".join(lines[max(0, s_line - 1) : min(len(lines), e_line)])
                        body_sha = hashlib.sha256(body_txt.encode("utf-8")).hexdigest()[:12]
                        kind = "class" if isinstance(node, ast.ClassDef) else "function"
                        symbols[node.name] = {
                            "name": node.name,
                            "kind": kind,
                            "start_line": s_line,
                            "end_line": e_line,
                            "sha256": body_sha,
                        }
                        if isinstance(node, ast.ClassDef):
                            for sub in node.body:
                                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                    ms = int(getattr(sub, "lineno", s_line))
                                    me = int(getattr(sub, "end_lineno", ms))
                                    m_txt = "\n".join(lines[max(0, ms - 1) : min(len(lines), me)])
                                    m_sha = hashlib.sha256(m_txt.encode("utf-8")).hexdigest()[:12]
                                    m_key = f"{node.name}.{sub.name}"
                                    symbols[m_key] = {
                                        "name": m_key,
                                        "kind": "method",
                                        "start_line": ms,
                                        "end_line": me,
                                        "sha256": m_sha,
                                    }
            except SyntaxError:
                pass
        else:
            sym_re = re.compile(
                r"^\s*(?:export\s+)?(?:async\s+)?(?:function\s+([a-zA-Z0-9_]+)|class\s+([a-zA-Z0-9_]+)|(?:const|let|var)\s+([a-zA-Z0-9_]+)\s*=\s*(?:async\s*)?\(|func\s+(?:\([^)]+\)\s*)?([a-zA-Z0-9_]+)|(?:pub\s+)?(?:async\s+)?fn\s+([a-zA-Z0-9_]+)|(?:pub\s+)?struct\s+([a-zA-Z0-9_]+))"
            )
            for idx, line in enumerate(lines):
                m = sym_re.search(line)
                if not m:
                    continue
                sym_name = next((g for g in m.groups() if g), "")
                if not sym_name or len(sym_name) < 2:
                    continue
                s_line = idx + 1
                e_line = AstImpactWatcher._scan_brace_end_line(lines, idx, max_scan=400)
                chunk = "\n".join(lines[idx:e_line])
                c_sha = hashlib.sha256(chunk.encode("utf-8")).hexdigest()[:12]
                symbols[sym_name] = {
                    "name": sym_name,
                    "kind": "symbol",
                    "start_line": s_line,
                    "end_line": e_line,
                    "sha256": c_sha,
                }

        return symbols

    @staticmethod
    def check_syntax_and_secrets(file_path: Path, content: str) -> Tuple[bool, str, bool]:
        """Runs AST/structural syntax verification and AI-Defence secret detection."""
        ext = file_path.suffix.lower()
        syntax_ok = True
        syntax_err = ""

        if ext == ".py":
            try:
                ast.parse(content)
            except SyntaxError as exc:
                syntax_ok = False
                syntax_err = f"SyntaxError L{exc.lineno}: {exc.msg}"
        elif ext == ".html":
            low = content.lower()
            if "<script" in low and "</script>" not in low:
                syntax_ok = False
                syntax_err = "Unclosed <script> tag in HTML"

        secret_re = re.compile(
            r"(?:AIza[0-9A-Za-z\-_]{35}|ya29\.[0-9A-Za-z\-_]{20,}|gh[pousr]_[0-9A-Za-z]{36}|"
            r"github_pat_[0-9A-Za-z_]{50,}|sk-ant-[0-9A-Za-z_\-]{25,}|sk-(?:proj-|svcacct-)?[0-9A-Za-z_\-]{32,}|"
            r"(?:AKIA|ASIA|AROA)[0-9A-Z]{16}|eyJ[a-zA-Z0-9_\-]{10,}\.eyJ[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]+|"
            r"-----BEGIN (?:RSA|EC|DSA|OPENSSH|PGP)?\s?PRIVATE KEY-----|xox[baprs]-[0-9a-zA-Z\-]{10,}|hf_[0-9a-zA-Z]{30,})"
        )
        secrets_ok = not bool(secret_re.search(content))
        return syntax_ok, syntax_err, secrets_ok

    def audit_file_save(
        self,
        file_path: str,
        workspace_path: str = "",
        force: bool = False,
        persist_memory_on_high_risk: bool = True,
    ) -> Dict[str, Any]:
        """
        Audits a saved file:
        1. Validates AST syntax + scans for accidental secrets.
        2. Diffs symbol hashes against the previous snapshot to identify modified functions/classes.
        3. Computes the reverse call/import impact graph (blast radius) for the file and changed symbols.
        4. Preemptively flags HIGH/CRITICAL changes in SQLite and BrainDB.
        """
        t0 = time.perf_counter()
        ws_root = Path(workspace_path).resolve() if workspace_path else self.workspace_root.resolve()
        raw_p = Path(file_path)
        target_p = (ws_root / raw_p).resolve() if not raw_p.is_absolute() else raw_p.resolve()

        try:
            rel_path = str(target_p.relative_to(ws_root)).replace("\\", "/")
        except ValueError:
            return {"ok": False, "error": "Acesso negado: o ficheiro reside fora dos limites autorizados do workspace."}

        if not target_p.is_file():
            return {"ok": False, "error": f"Ficheiro não encontrado: {file_path}"}

        content = target_p.read_text(encoding="utf-8", errors="ignore")
        file_sha = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
        stat_info = target_p.stat()
        ws_name = BrainDB.normalize_workspace(str(ws_root))

        prev_state = self._file_state_cache.get(rel_path)
        if prev_state is None:
            try:
                with self.db._connect() as conn:
                    fh_row = conn.execute(
                        "SELECT sha256, mtime_ns, symbols_json FROM ast_file_hashes WHERE file_path = ?;",
                        (rel_path,),
                    ).fetchall()
                    sym_rows = conn.execute(
                        "SELECT symbol_name, symbol_kind, start_line, end_line, sha256 FROM ast_symbol_snapshots WHERE file_path = ?;",
                        (rel_path,),
                    ).fetchall()
                    if fh_row or sym_rows:
                        loaded_syms: Dict[str, Dict[str, Any]] = {}
                        if fh_row:
                            try:
                                loaded_syms = json.loads(fh_row[0]["symbols_json"] or "{}")
                            except Exception:
                                loaded_syms = {}
                        for sr in sym_rows:
                            s_nm = str(sr["symbol_name"])
                            loaded_syms[s_nm] = {
                                "name": s_nm,
                                "kind": str(sr["symbol_kind"] or "function"),
                                "start_line": int(sr["start_line"] or 1),
                                "end_line": int(sr["end_line"] or 1),
                                "sha256": str(sr["sha256"] or ""),
                            }
                        prev_state = {
                            "sha256": str(fh_row[0]["sha256"] or "") if fh_row else "",
                            "mtime_ns": int(fh_row[0]["mtime_ns"] or 0) if fh_row else 0,
                            "symbols": loaded_syms,
                        }
                        self._file_state_cache[rel_path] = prev_state
            except Exception:
                prev_state = None

        if prev_state and prev_state.get("sha256") == file_sha and not force:
            return {
                "ok": True,
                "skipped": True,
                "file": rel_path,
                "sha256": file_sha,
                "message": "Sem alterações de conteúdo desde a última verificação.",
            }

        syntax_ok, syntax_err, secrets_ok = self.check_syntax_and_secrets(target_p, content)
        curr_symbols = self.extract_symbol_hashes(target_p, content)

        changed_symbols: List[str] = []
        if prev_state and "symbols" in prev_state:
            prev_syms: Dict[str, Dict[str, Any]] = prev_state["symbols"]
            for s_name, s_meta in curr_symbols.items():
                if s_name not in prev_syms or prev_syms[s_name].get("sha256") != s_meta.get("sha256"):
                    changed_symbols.append(s_name)
            for old_name in prev_syms:
                if old_name not in curr_symbols:
                    changed_symbols.append(old_name)

        if not changed_symbols and (not prev_state or force):
            # First snapshot or forced audit on unchanged file: pick top exported symbols in the file
            top_syms = [
                k for k, v in curr_symbols.items() if v.get("kind") in ("class", "function", "symbol") and "." not in k
            ]
            changed_symbols = top_syms[:4]

        self._file_state_cache[rel_path] = {
            "mtime_ns": stat_info.st_mtime_ns,
            "sha256": file_sha,
            "symbols": curr_symbols,
        }
        try:
            with self.db._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO ast_file_hashes (file_path, workspace, sha256, mtime_ns, symbols_json, updated_at)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(file_path) DO UPDATE SET
                        workspace = excluded.workspace,
                        sha256 = excluded.sha256,
                        mtime_ns = excluded.mtime_ns,
                        symbols_json = excluded.symbols_json,
                        updated_at = CURRENT_TIMESTAMP;
                    """,
                    (
                        rel_path,
                        ws_name,
                        file_sha,
                        int(stat_info.st_mtime_ns),
                        json.dumps(curr_symbols),
                    ),
                )
                conn.execute("DELETE FROM ast_symbol_snapshots WHERE file_path = ?;", (rel_path,))
                for s_name, s_meta in curr_symbols.items():
                    conn.execute(
                        """
                        INSERT INTO ast_symbol_snapshots (file_path, symbol_name, symbol_kind, start_line, end_line, sha256, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                        ON CONFLICT(file_path, symbol_name) DO UPDATE SET
                            symbol_kind = excluded.symbol_kind,
                            start_line = excluded.start_line,
                            end_line = excluded.end_line,
                            sha256 = excluded.sha256,
                            updated_at = CURRENT_TIMESTAMP;
                        """,
                        (
                            rel_path,
                            s_name,
                            str(s_meta.get("kind") or "function"),
                            int(s_meta.get("start_line") or 1),
                            int(s_meta.get("end_line") or 1),
                            str(s_meta.get("sha256") or ""),
                        ),
                    )
        except Exception:
            pass

        # Run impact analysis on the file and the primary changed symbols
        file_stem = target_p.stem
        file_impact = self.swarm.analyze_impact_graph(target=file_stem, workspace_path=str(ws_root))
        merged_callers: Dict[str, Dict[str, Any]] = {
            c["file"]: dict(c) for c in file_impact.get("callers", [])
        }
        recommended_tests = set(file_impact.get("recommended_tests", ["test_brain.py"]))
        total_refs = int(file_impact.get("total_references", 0))

        for sym in changed_symbols[:3]:
            base_sym = sym.split(".")[-1]
            sym_imp = self.swarm.analyze_impact_graph(target=base_sym, workspace_path=str(ws_root))
            total_refs = max(total_refs, int(sym_imp.get("total_references", 0)))
            for t in sym_imp.get("recommended_tests", []):
                recommended_tests.add(t)
            for caller in sym_imp.get("callers", []):
                cf = caller["file"]
                if cf not in merged_callers:
                    merged_callers[cf] = dict(caller)
                else:
                    merged_callers[cf]["references_count"] = max(
                        int(merged_callers[cf].get("references_count", 0)),
                        int(caller.get("references_count", 0)),
                    )

        callers_list = sorted(
            merged_callers.values(), key=lambda x: int(x.get("references_count", 0)), reverse=True
        )[:10]
        affected_count = len(callers_list)
        blast_radius = (
            "HIGH"
            if (affected_count >= 5 or total_refs >= 25)
            else ("MEDIUM" if (affected_count >= 2 or total_refs >= 6) else "LOW")
        )

        if not syntax_ok or not secrets_ok:
            risk_level = "CRITICAL"
        elif blast_radius == "HIGH":
            risk_level = "HIGH"
        elif blast_radius == "MEDIUM":
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        tests_sorted = sorted(recommended_tests)
        syms_preview = ", ".join(changed_symbols[:4]) if changed_symbols else "file-level"
        if not syntax_ok:
            summary = f"[CRITICAL] {rel_path}: {syntax_err} (Blast Radius: {affected_count} ficheiros)"
        elif not secrets_ok:
            summary = f"[CRITICAL] {rel_path}: Segredo/API Key detetado pelo AI-Defence Scanner!"
        else:
            summary = (
                f"[{risk_level}] {rel_path} ({syms_preview}) -> "
                f"{affected_count} ficheiros dependentes ({total_refs} refs) | Testes: {', '.join(tests_sorted[:3])}"
            )

        ws_name = BrainDB.normalize_workspace(str(ws_root))
        with self.db._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO ast_save_audits (
                    file_path, workspace, sha256, risk_level, blast_radius,
                    affected_files_count, total_references, syntax_ok, secrets_ok,
                    changed_symbols_json, recommended_tests_json, callers_json, summary
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    rel_path,
                    ws_name,
                    file_sha,
                    risk_level,
                    blast_radius,
                    affected_count,
                    total_refs,
                    1 if syntax_ok else 0,
                    1 if secrets_ok else 0,
                    json.dumps(changed_symbols[:8]),
                    json.dumps(tests_sorted),
                    json.dumps(callers_list),
                    summary,
                ),
            )
            audit_id = int(cur.lastrowid)

        # Preemptively store/update a high-priority alert in BrainDB when risk is HIGH or CRITICAL
        if persist_memory_on_high_risk and risk_level in ("HIGH", "CRITICAL"):
            caller_names = ", ".join(c["file"] for c in callers_list[:5]) or "nenhum"
            self.db.store_fact(
                topic=f"Alerta Preemptivo AST Save [{risk_level}]: {rel_path}",
                fact=(
                    f"Alteração detetada em {rel_path} (símbolos: {syms_preview}, SHA:{file_sha[:8]}) "
                    f"com Blast Radius {blast_radius} ({affected_count} ficheiros dependentes: {caller_names}; "
                    f"{total_refs} referências). Sintaxe AST={'OK' if syntax_ok else syntax_err}. "
                    f"Correr testes antes de prosseguir: {', '.join(tests_sorted)}."
                ),
                workspace=ws_name,
                category="code_change",
                tags=f"ast_watcher high_risk_save_alert {rel_path.lower()} {risk_level.lower()}",
                importance=5,
            )

        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        _WATCHER_RUNTIME_STATE["saves_detected"] = int(_WATCHER_RUNTIME_STATE.get("saves_detected", 0)) + 1
        if risk_level in ("HIGH", "CRITICAL"):
            _WATCHER_RUNTIME_STATE["high_risk_flagged"] = int(_WATCHER_RUNTIME_STATE.get("high_risk_flagged", 0)) + 1

        return {
            "ok": True,
            "audit_id": audit_id,
            "file": rel_path,
            "workspace": ws_name,
            "sha256": file_sha,
            "risk_level": risk_level,
            "blast_radius": blast_radius,
            "syntax_ok": syntax_ok,
            "syntax_error": syntax_err,
            "secrets_ok": secrets_ok,
            "changed_symbols": changed_symbols[:8],
            "affected_files_count": affected_count,
            "total_references": total_refs,
            "recommended_tests": tests_sorted,
            "callers": callers_list,
            "summary": summary,
            "latency_ms": elapsed_ms,
        }

    def scan_workspace_saves(
        self,
        workspace_path: str = "",
        force_all: bool = False,
        persist_memory_on_high_risk: bool = True,
    ) -> Dict[str, Any]:
        """
        Scans all supported source files in the workspace, detects any files whose mtime_ns or
        SHA-256 changed since the last scan, and runs preemptive AST & Impact analysis on them.
        """
        t0 = time.perf_counter()
        ws_root = Path(workspace_path).resolve() if workspace_path else self.workspace_root
        audited: List[Dict[str, Any]] = []
        monitored_count = 0

        for root, dirs, files in os.walk(ws_root):
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]
            for fname in sorted(files):
                ext = os.path.splitext(fname)[1].lower()
                if ext not in CODE_EXTENSIONS:
                    continue
                fpath = Path(root) / fname
                try:
                    rel_path = str(fpath.relative_to(ws_root)).replace("\\", "/")
                    st = fpath.stat()
                except OSError:
                    continue
                monitored_count += 1
                prev = self._file_state_cache.get(rel_path)
                if not force_all and prev and prev.get("mtime_ns") == st.st_mtime_ns:
                    continue

                res = self.audit_file_save(
                    file_path=str(fpath),
                    workspace_path=str(ws_root),
                    force=force_all,
                    persist_memory_on_high_risk=persist_memory_on_high_risk,
                )
                if res.get("ok") and not res.get("skipped"):
                    audited.append(res)

        _WATCHER_RUNTIME_STATE["last_scan_ts"] = int(time.time() * 1000)
        _WATCHER_RUNTIME_STATE["files_monitored"] = monitored_count

        high_risk = [a for a in audited if a.get("risk_level") in ("HIGH", "CRITICAL")]
        return {
            "ok": True,
            "files_monitored": monitored_count,
            "saves_audited_count": len(audited),
            "high_risk_count": len(high_risk),
            "audits": audited,
            "high_risk_alerts": high_risk,
            "latency_ms": round((time.perf_counter() - t0) * 1000.0, 2),
        }

    def get_watcher_status(self, limit: int = 12) -> Dict[str, Any]:
        """Returns the live watcher daemon status and most recent file-save impact audits."""
        with self.db._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM ast_save_audits
                ORDER BY id DESC LIMIT ?;
                """,
                (int(limit),),
            ).fetchall()
            total_row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_audits,
                    SUM(CASE WHEN risk_level IN ('HIGH', 'CRITICAL') THEN 1 ELSE 0 END) AS high_risk_total
                FROM ast_save_audits;
                """
            ).fetchone()

        audits: List[Dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            d["changed_symbols"] = json.loads(d.get("changed_symbols_json") or "[]")
            d["recommended_tests"] = json.loads(d.get("recommended_tests_json") or "[]")
            d["callers"] = json.loads(d.get("callers_json") or "[]")
            d["syntax_ok"] = bool(d.get("syntax_ok", 1))
            d["secrets_ok"] = bool(d.get("secrets_ok", 1))
            audits.append(d)

        return {
            "ok": True,
            "daemon_active": bool(_WATCHER_RUNTIME_STATE.get("daemon_active", False)),
            "files_monitored": int(_WATCHER_RUNTIME_STATE.get("files_monitored", 0)),
            "last_scan_ts": int(_WATCHER_RUNTIME_STATE.get("last_scan_ts", 0)),
            "total_audits": int(total_row["total_audits"] or 0) if total_row else 0,
            "high_risk_total": int(total_row["high_risk_total"] or 0) if total_row else 0,
            "audits": audits,
        }

    def analyze_git_diff_blast_radius(self, workspace_path: str = "") -> Dict[str, Any]:
        """
        Parses `git diff HEAD -U0` (or compares against persisted AST symbol snapshots),
        maps modified line ranges to AST symbols, and resolves reverse callers,
        Git co-changed files (`CO_CHANGED`), and targeted test functions.
        """
        import subprocess
        from graphify_engine import get_graphify_engine

        t0 = time.perf_counter()
        ws_root = Path(workspace_path).resolve() if workspace_path else self.workspace_root.resolve()
        ws_name = BrainDB.normalize_workspace(str(ws_root))

        file_line_ranges: Dict[str, List[Tuple[int, int]]] = {}
        try:
            diff_out = subprocess.check_output(
                ["git", "diff", "HEAD", "-U0"],
                cwd=str(ws_root),
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=2.5,
            )
            curr_file = ""
            hunk_re = re.compile(r"^@@\s+-\d+(?:,\d+)?\s+\+(\d+)(?:,(\d+))?\s+@@")
            for raw_ln in diff_out.splitlines():
                if raw_ln.startswith("+++ b/"):
                    curr_file = raw_ln[6:].strip().replace("\\", "/")
                    file_line_ranges.setdefault(curr_file, [])
                elif curr_file and raw_ln.startswith("@@"):
                    hm = hunk_re.match(raw_ln)
                    if hm:
                        s_ln = int(hm.group(1))
                        cnt = int(hm.group(2)) if hm.group(2) is not None else 1
                        e_ln = max(s_ln, s_ln + max(1, cnt) - 1)
                        file_line_ranges[curr_file].append((s_ln, e_ln))
        except Exception:
            pass

        modified_files: List[str] = []
        modified_symbols: List[str] = []

        # Map diff hunks to AST symbols
        for rel_f, ranges in file_line_ranges.items():
            fp = ws_root / rel_f
            if not fp.is_file():
                continue
            modified_files.append(rel_f)
            content = fp.read_text(encoding="utf-8", errors="ignore")
            syms = self.extract_symbol_hashes(fp, content)
            for s_name, s_meta in syms.items():
                sym_s = int(s_meta.get("start_line", 1))
                sym_e = int(s_meta.get("end_line", sym_s))
                for h_s, h_e in ranges:
                    if not (h_e < sym_s or h_s > sym_e):
                        if s_name not in modified_symbols:
                            modified_symbols.append(s_name)
                        break

        # Fallback to persisted SQLite symbol snapshots if git diff had no uncommitted hunks
        if not modified_files:
            with self.db._connect() as conn:
                snap_files = conn.execute(
                    "SELECT DISTINCT file_path FROM ast_symbol_snapshots LIMIT 40;"
                ).fetchall()
                for sf in snap_files:
                    rel_f = str(sf["file_path"])
                    fp = ws_root / rel_f
                    if not fp.is_file():
                        continue
                    content = fp.read_text(encoding="utf-8", errors="ignore")
                    curr_syms = self.extract_symbol_hashes(fp, content)
                    sym_rows = conn.execute(
                        "SELECT symbol_name, sha256 FROM ast_symbol_snapshots WHERE file_path = ?;",
                        (rel_f,),
                    ).fetchall()
                    prev_map = {str(sr["symbol_name"]): str(sr["sha256"]) for sr in sym_rows}
                    file_mod = False
                    for s_name, s_meta in curr_syms.items():
                        if s_name not in prev_map or prev_map[s_name] != s_meta.get("sha256"):
                            file_mod = True
                            if s_name not in modified_symbols:
                                modified_symbols.append(s_name)
                    if file_mod and rel_f not in modified_files:
                        modified_files.append(rel_f)

        reverse_callers: List[str] = []
        targeted_tests: List[str] = []
        for sym in (modified_symbols[:5] or [Path(f).stem for f in modified_files[:3]]):
            base_s = sym.split(".")[-1]
            imp = self.swarm.analyze_impact_graph(target=base_s, workspace_path=str(ws_root))
            for c in imp.get("callers", []):
                if c["file"] not in reverse_callers:
                    reverse_callers.append(c["file"])
            for t in imp.get("recommended_tests", []):
                if t not in targeted_tests:
                    targeted_tests.append(t)

        g_eng = get_graphify_engine(str(ws_root))
        cochange_edges = g_eng._mine_git_cochange_edges(ws_root)
        co_changed_files: List[str] = []
        mod_set = set(modified_files)
        for ce in cochange_edges:
            if not mod_set or ce["file_a"] in mod_set or ce["file_b"] in mod_set:
                for cand_f in (ce["file_a"], ce["file_b"]):
                    if cand_f not in co_changed_files:
                        co_changed_files.append(cand_f)

        blast_radius = (
            "HIGH"
            if len(reverse_callers) >= 5 or len(modified_symbols) >= 4
            else ("MEDIUM" if (reverse_callers or modified_symbols) else "LOW")
        )
        return {
            "ok": True,
            "workspace": ws_name,
            "modified_files": modified_files,
            "modified_symbols": modified_symbols,
            "reverse_callers": reverse_callers[:12],
            "co_changed_files": co_changed_files[:10],
            "targeted_tests": targeted_tests or ["test_brain.py"],
            "blast_radius": blast_radius,
            "latency_ms": round((time.perf_counter() - t0) * 1000.0, 2),
        }


_GLOBAL_WATCHER: Optional[AstImpactWatcher] = None


def get_global_watcher(workspace_path: str = "") -> AstImpactWatcher:
    global _GLOBAL_WATCHER
    with _WATCHER_LOCK:
        if _GLOBAL_WATCHER is None:
            _GLOBAL_WATCHER = AstImpactWatcher(workspace_path=workspace_path or CURRENT_DIR)
        return _GLOBAL_WATCHER


def start_ast_impact_watcher_daemon(
    workspace_path: str = "",
    interval_seconds: float = 2.0,
) -> AstImpactWatcher:
    """
    Starts the background file-save watcher daemon thread that monitors code files
    and runs AST + Impact Radius analysis automatically whenever a file is saved.
    """
    global _WATCHER_DAEMON_STARTED
    watcher = get_global_watcher(workspace_path or CURRENT_DIR)
    if _WATCHER_DAEMON_STARTED:
        return watcher

    _WATCHER_DAEMON_STARTED = True
    _WATCHER_RUNTIME_STATE["daemon_active"] = True
    _WATCHER_RUNTIME_STATE["started_at"] = int(time.time() * 1000)

    def _daemon_loop() -> None:
        # Initial baseline scan (populates cache and audits core files without flooding memories)
        try:
            watcher.scan_workspace_saves(persist_memory_on_high_risk=False)
        except Exception:
            pass
        while True:
            time.sleep(max(0.5, float(interval_seconds)))
            try:
                watcher.scan_workspace_saves(persist_memory_on_high_risk=True)
            except Exception:
                pass

    t = threading.Thread(target=_daemon_loop, daemon=True, name="AstImpactSaveWatcher")
    t.start()
    return watcher


def _format_cli_report(report: Dict[str, Any]) -> str:
    lines = [
        "=" * 78,
        " 🛡️  ANTIGRAVITY AST & IMPACT RADIUS FILE-SAVE WATCHER",
        "=" * 78,
    ]
    audits = report.get("audits", [report] if "file" in report else [])
    if not audits:
        lines.append(" ✓ Nenhuma alteração de ficheiro pendente (0 saves novos detetados).")
        return "\n".join(lines)

    for a in audits:
        risk = a.get("risk_level", "LOW")
        badge = "🚨 CRITICAL" if risk == "CRITICAL" else ("⚠️ HIGH" if risk == "HIGH" else ("🔶 MEDIUM" if risk == "MEDIUM" else "✅ LOW"))
        syms = ", ".join(a.get("changed_symbols", [])) or "file-level"
        tests = ", ".join(a.get("recommended_tests", [])) or "test_brain.py"
        lines.append(
            f" {badge} | {a.get('file')} (SHA:{a.get('sha256', '')[:8]}) | Símbolos: {syms}"
        )
        lines.append(
            f"    ↳ Blast Radius: {a.get('blast_radius')} ({a.get('affected_files_count')} ficheiros / {a.get('total_references')} refs) "
            f"| AST: {'PASS' if a.get('syntax_ok') else a.get('syntax_error')} | Testes: {tests}"
        )
    lines.append("=" * 78)
    return "\n".join(lines)


def main() -> None:
    if getattr(sys, "stdout", None) is not None and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="Automated AST & Impact Radius Analyzer on File Save"
    )
    parser.add_argument("--file", "-f", type=str, default="", help="Audit a specific saved file immediately")
    parser.add_argument("--workspace", "-w", type=str, default=CURRENT_DIR, help="Workspace root directory")
    parser.add_argument("--once", action="store_true", help="Run a single workspace scan and exit")
    parser.add_argument("--watch", action="store_true", help="Continuously watch workspace for file saves")
    parser.add_argument("--interval", type=float, default=1.0, help="Polling interval in seconds for --watch mode")
    parser.add_argument("--json", action="store_true", help="Output raw JSON report")
    args = parser.parse_args()

    watcher = AstImpactWatcher(workspace_path=args.workspace)

    if args.file:
        res = watcher.audit_file_save(file_path=args.file, workspace_path=args.workspace, force=True)
        print(json.dumps(res, indent=2, ensure_ascii=False) if args.json else _format_cli_report(res))
        return

    if args.watch:
        print(f"👀 A monitorizar gravações de ficheiros em {args.workspace} (intervalo={args.interval}s)...")
        init_rep = watcher.scan_workspace_saves(workspace_path=args.workspace, persist_memory_on_high_risk=False)
        print(_format_cli_report(init_rep))
        try:
            while True:
                time.sleep(max(0.3, args.interval))
                scan_rep = watcher.scan_workspace_saves(workspace_path=args.workspace, persist_memory_on_high_risk=True)
                if scan_rep.get("saves_audited_count", 0) > 0:
                    print(
                        json.dumps(scan_rep, indent=2, ensure_ascii=False)
                        if args.json
                        else _format_cli_report(scan_rep)
                    )
        except KeyboardInterrupt:
            print("\nWatcher terminado.")
        return

    # Default or --once: run single scan across workspace
    rep = watcher.scan_workspace_saves(workspace_path=args.workspace, force_all=True)
    print(json.dumps(rep, indent=2, ensure_ascii=False) if args.json else _format_cli_report(rep))


if __name__ == "__main__":
    main()
