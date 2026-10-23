import contextlib
import datetime
import hashlib
import json
import math
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "brain.db"
)

# Mapa de Sinónimos Técnicos PT/EN para expansão semântica a custo zero no FTS5 BM25
SYNONYM_MAP: Dict[str, List[str]] = {
    "db": ["sqlite", "database", "fts5"],
    "database": ["sqlite", "db", "fts5"],
    "base": ["sqlite", "database", "db"],
    "ui": ["frontend", "html", "canvas", "interface"],
    "interface": ["ui", "frontend", "dashboard"],
    "escritorio": ["office", "3d", "bonecos"],
    "office": ["escritorio", "3d", "avatars"],
    "bonecos": ["office", "3d", "avatars"],
    "quota": ["tokens", "diet", "lean", "5h"],
    "tokens": ["quota", "diet", "lean"],
    "vps": ["server", "ssh", "cloud", "infra"],
    "servidor": ["server", "vps", "http", "port"],
    "git": ["github", "repo", "update", "commit"],
    "github": ["git", "repo", "update"],
    "swarm": ["scout", "lanes", "argon", "workers"],
    "scout": ["swarm", "ast", "map"],
}

# Stopwords PT + EN para limpar queries em linguagem natural antes do FTS5 BM25
STOPWORDS = {
    "a", "ao", "aos", "aquela", "aquelas", "aquele", "aqueles", "aquilo", "as",
    "ate", "com", "como", "da", "das", "de", "dela", "delas", "dele", "deles",
    "depois", "do", "dos", "e", "ela", "elas", "ele", "eles", "em", "entre",
    "era", "eram", "essa", "essas", "esse", "esses", "esta", "estamos", "estao",
    "estar", "estas", "estava", "estavam", "este", "estes", "estou", "eu", "foi",
    "for", "foram", "fosse", "fossem", "ha", "isso", "isto", "ja", "la", "lhe",
    "lhes", "mais", "mas", "me", "mesmo", "meu", "meus", "minha", "minhas",
    "muito", "na", "nao", "nas", "nem", "no", "nos", "nossa", "nossas", "nosso",
    "nossos", "num", "numa", "o", "os", "ou", "para", "pela", "pelas", "pelo",
    "pelos", "por", "qual", "quando", "que", "quem", "se", "seja", "sejam",
    "sem", "sera", "serao", "seu", "seus", "so", "sua", "suas", "tambem", "te",
    "tem", "tendo", "tenha", "tenham", "tenho", "ter", "teu", "teus", "teve",
    "tinha", "tinham", "tive", "tivemos", "tiver", "tivera", "tiveram", "tivesse",
    "tivessem", "tu", "tua", "tuas", "um", "uma", "umas", "uns", "vai", "vao",
    "voce", "voces", "vos", "fazer", "criar", "usar", "ver", "qual", "onde",
    # English stopwords
    "the", "and", "is", "in", "to", "of", "it", "with", "as", "be", "on", "at",
    "by", "this", "that", "from", "or", "an", "are", "was", "were", "what",
    "which", "who", "whom", "how", "when", "where", "why", "can", "could",
    "should", "would", "will", "do", "does", "did", "have", "has", "had",
}


_INITIALIZED_DBS: set[str] = set()


class BrainDB:
    """Motor Híbrido SQLite (WAL) + FTS5 (BM25) + Checkpoints + Telemetria."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH) -> None:
        self.db_path = db_path
        if self.db_path not in _INITIALIZED_DBS:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            self._init_schema()
            _INITIALIZED_DBS.add(self.db_path)

    @contextlib.contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA temp_store=MEMORY;")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            # 1. Tabela principal de memórias
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT NOT NULL,
                    fact TEXT NOT NULL,
                    workspace TEXT DEFAULT 'global',
                    category TEXT DEFAULT 'general',
                    tags TEXT DEFAULT '',
                    importance INTEGER DEFAULT 3,
                    fact_hash TEXT UNIQUE,
                    access_count INTEGER DEFAULT 0,
                    last_accessed TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

            # Migração suave caso a tabela antiga só tivesse (id, topic, fact, created_at)
            existing_cols = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(memories);").fetchall()
            }
            migrations = [
                ("workspace", "TEXT DEFAULT 'global'"),
                ("category", "TEXT DEFAULT 'general'"),
                ("tags", "TEXT DEFAULT ''"),
                ("importance", "INTEGER DEFAULT 3"),
                ("fact_hash", "TEXT"),
                ("access_count", "INTEGER DEFAULT 0"),
                ("last_accessed", "TIMESTAMP"),
            ]
            for col_name, col_def in migrations:
                if col_name not in existing_cols:
                    conn.execute(
                        f"ALTER TABLE memories ADD COLUMN {col_name} {col_def};"
                    )

            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_hash ON memories(fact_hash) WHERE fact_hash IS NOT NULL;"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_workspace ON memories(workspace);"
            )

            # 2. Tabela FTS5 para pesquisa ultrarrápida BM25
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                    topic,
                    fact,
                    tags,
                    workspace,
                    content='memories',
                    content_rowid='id',
                    tokenize='unicode61 remove_diacritics 2'
                );
                """
            )

            # Triggers de sincronização automática entre memories e memories_fts
            conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
                    INSERT INTO memories_fts(rowid, topic, fact, tags, workspace)
                    VALUES (new.id, new.topic, new.fact, new.tags, new.workspace);
                END;
                """
            )
            conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
                    INSERT INTO memories_fts(memories_fts, rowid, topic, fact, tags, workspace)
                    VALUES ('delete', old.id, old.topic, old.fact, old.tags, old.workspace);
                END;
                """
            )
            conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE OF topic, fact, tags, workspace ON memories BEGIN
                    INSERT INTO memories_fts(memories_fts, rowid, topic, fact, tags, workspace)
                    VALUES ('delete', old.id, old.topic, old.fact, old.tags, old.workspace);
                    INSERT INTO memories_fts(rowid, topic, fact, tags, workspace)
                    VALUES (new.id, new.topic, new.fact, new.tags, new.workspace);
                END;
                """
            )

            # 3. Tabela de Checkpoints Ultra-Compactos por Workspace
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS checkpoints (
                    workspace TEXT PRIMARY KEY,
                    project TEXT NOT NULL,
                    goal TEXT DEFAULT '',
                    status TEXT DEFAULT '',
                    stack TEXT DEFAULT '',
                    last_completed TEXT DEFAULT '',
                    next_tasks TEXT DEFAULT '',
                    key_files TEXT DEFAULT '',
                    notes TEXT DEFAULT '',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

            # 4. Tabela de Controlo de Injeção por Turno (Evita duplicar injeções no mesmo passo)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS injected_turns (
                    conversation_id TEXT NOT NULL,
                    prompt_hash TEXT NOT NULL,
                    injected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (conversation_id, prompt_hash)
                );
                """
            )

            # 5. Tabela de Telemetria de Economia de Tokens / Quota
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS telemetry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    conversation_id TEXT DEFAULT '',
                    workspace TEXT DEFAULT 'global',
                    latency_ms REAL DEFAULT 0.0,
                    injected_tokens INTEGER DEFAULT 0,
                    estimated_saved_tokens INTEGER DEFAULT 0,
                    details TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

            # 6. Limpeza automática de entradas duplicadas de ficheiros ou regex corrompido
            conn.execute(
                """
                DELETE FROM memories
                WHERE LENGTH(fact) > 650
                   OR topic LIKE '%\\s*%'
                   OR topic LIKE '%Topico%'
                   OR topic LIKE '%Short Topic%';
                """
            )
            conn.execute(
                """
                DELETE FROM memories
                WHERE category = 'code_change'
                  AND id NOT IN (
                      SELECT MAX(id) FROM memories
                      WHERE category = 'code_change'
                      GROUP BY workspace, topic
                  );
                """
            )
            conn.execute(
                """
                DELETE FROM telemetry
                WHERE id NOT IN (
                    SELECT id FROM telemetry ORDER BY id DESC LIMIT 2500
                );
                """
            )

    @staticmethod
    def _compute_hash(topic: str, fact: str, workspace: str = "global") -> str:
        norm = f"{workspace.strip().lower()}::{topic.strip().lower()}::{fact.strip().lower()}"
        return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:32]

    @staticmethod
    def normalize_workspace(workspace_path: Optional[str]) -> str:
        if not workspace_path:
            return "global"
        clean = workspace_path.replace("\\", "/").rstrip("/")
        return os.path.basename(clean).lower() or "global"

    def store_fact(
        self,
        topic: str,
        fact: str,
        workspace: str = "global",
        category: str = "general",
        tags: str = "",
        importance: int = 3,
    ) -> Tuple[int, bool]:
        """Guarda ou atualiza um facto sem duplicar. Retorna (row_id, is_new)."""
        topic = topic.strip()
        fact = fact.strip()
        ws = self.normalize_workspace(workspace) if ("/" in workspace or "\\" in workspace) else (workspace.strip().lower() or "global")
        importance = max(1, min(5, int(importance)))
        f_hash = self._compute_hash(topic, fact, ws)

        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM memories WHERE fact_hash = ?;", (f_hash,)
            ).fetchone()
            if existing:
                row_id = int(existing["id"])
                conn.execute(
                    """
                    UPDATE memories
                    SET importance = MAX(importance, ?),
                        tags = CASE WHEN ? != '' THEN ? ELSE tags END,
                        last_accessed = CURRENT_TIMESTAMP
                    WHERE id = ?;
                    """,
                    (importance, tags, tags, row_id),
                )
                return row_id, False

            cur = conn.execute(
                """
                INSERT INTO memories (topic, fact, workspace, category, tags, importance, fact_hash, last_accessed)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP);
                """,
                (topic, fact, ws, category, tags, importance, f_hash),
            )
            return int(cur.lastrowid), True

    def forget_fact(self, fact_id: str | int) -> bool:
        """Remove um facto pelo ID."""
        try:
            fid = int(fact_id)
        except ValueError:
            return False
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM memories WHERE id = ?;", (fid,))
            return cur.rowcount > 0

    @staticmethod
    def extract_search_tokens(query: str) -> List[str]:
        # Extrai palavras alfanuméricas, IPs, nomes de ficheiros e expande sinónimos técnicos PT/EN
        raw_tokens = re.findall(r"[a-zA-Z0-9_\-\.]{2,}", query.lower())
        tokens: List[str] = []
        seen = set()
        for t in raw_tokens:
            clean = t.strip(".-_")
            if len(clean) < 2 or clean in STOPWORDS:
                continue
            if clean not in seen:
                seen.add(clean)
                tokens.append(clean)
                for syn in SYNONYM_MAP.get(clean, []):
                    if syn not in seen:
                        seen.add(syn)
                        tokens.append(syn)
        return tokens[:18]

    def search_memories(
        self,
        query: str,
        workspace: Optional[str] = None,
        n_results: int = 5,
        update_stats: bool = True,
    ) -> List[Dict[str, Any]]:
        """Pesquisa híbrida: FTS5 BM25 + Token Overlap + Afinidade de Workspace + Importância."""
        ws = self.normalize_workspace(workspace)
        tokens = self.extract_search_tokens(query)

        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) as c FROM memories;").fetchone()["c"]
            if total == 0:
                return []

            candidates: Dict[int, Dict[str, Any]] = {}

            # 1. Pesquisa FTS5 BM25 se tivermos tokens válidos
            if tokens:
                fts_terms = []
                for tok in tokens:
                    safe_tok = re.sub(r"[^a-zA-Z0-9_]", "", tok)
                    if len(safe_tok) >= 2:
                        fts_terms.append(f'"{safe_tok}"*')
                if fts_terms:
                    fts_query = " OR ".join(fts_terms)
                    try:
                        rows = conn.execute(
                            """
                            SELECT m.*,
                                   bm25(memories_fts, 3.0, 1.5, 2.5, 1.0) AS bm25_raw
                            FROM memories_fts
                            JOIN memories m ON m.id = memories_fts.rowid
                            WHERE memories_fts MATCH ?
                            ORDER BY bm25_raw ASC
                            LIMIT ?;
                            """,
                            (fts_query, max(n_results * 4, 20)),
                        ).fetchall()
                        for r in rows:
                            d = dict(r)
                            # bm25() em SQLite FTS5 retorna valores negativos (mais negativo = melhor)
                            d["score"] = abs(float(d.get("bm25_raw", 0.0))) * 2.0
                            candidates[d["id"]] = d
                    except sqlite3.OperationalError:
                        pass

            # 2. Fallback / Complemento: Memórias de alta importância do workspace atual ou global
            fallback_rows = conn.execute(
                """
                SELECT * FROM memories
                WHERE workspace IN (?, 'global')
                ORDER BY importance DESC, id DESC
                LIMIT 30;
                """,
                (ws,),
            ).fetchall()

            query_lower = query.lower()
            for r in fallback_rows:
                rid = r["id"]
                if rid not in candidates:
                    d = dict(r)
                    d["score"] = 0.0
                    candidates[rid] = d

            # 3. Re-ranking Híbrido (Overlap léxico + Workspace Boost + Importância)
            scored_list: List[Dict[str, Any]] = []
            for rid, item in candidates.items():
                text_blob = f"{item['topic']} {item['fact']} {item.get('tags', '')}".lower()
                overlap = sum(1 for tok in tokens if tok in text_blob)

                # Se a query tinha tokens específicos e este candidato não teve FTS match nem overlap,
                # só entra se for do mesmo workspace específico (não global genérico)
                if tokens and item["score"] == 0.0 and overlap == 0:
                    if item["workspace"] != ws or ws == "global":
                        continue

                ws_boost = 2.5 if (ws != "global" and item["workspace"] == ws) else 0.0
                imp_boost = float(item.get("importance", 3)) * 0.4
                overlap_boost = overlap * 1.8

                # Substring exata para IPs ou identificadores técnicos
                exact_tech_boost = 0.0
                for tok in tokens:
                    if ("." in tok or "_" in tok or any(c.isdigit() for c in tok)) and tok in text_blob:
                        exact_tech_boost += 3.0

                # Recency Time-Decay: privilegia memórias criadas ou acedidas recentemente
                recency_mult = 1.0
                ts_str = str(item.get("last_accessed") or item.get("created_at") or "")
                if ts_str:
                    try:
                        dt = datetime.datetime.fromisoformat(ts_str.replace("Z", ""))
                        now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                        age_days = max(0.0, (now_utc - dt).total_seconds() / 86400.0)
                        recency_mult = 1.0 + 0.35 * math.exp(-age_days / 14.0)
                    except Exception:
                        recency_mult = 1.1

                raw_final = (
                    item["score"] + overlap_boost + ws_boost + imp_boost + exact_tech_boost
                )
                item["final_score"] = round(raw_final * recency_mult, 3)
                scored_list.append(item)

            if not scored_list:
                for item in candidates.values():
                    if int(item.get("importance", 3)) >= 5:
                        item["final_score"] = float(item.get("importance", 5)) * 0.4
                        scored_list.append(item)

            scored_list.sort(key=lambda x: x["final_score"], reverse=True)
            top_results = scored_list[:n_results]

            if update_stats and top_results:
                ids = [r["id"] for r in top_results]
                placeholders = ",".join("?" for _ in ids)
                conn.execute(
                    f"""
                    UPDATE memories
                    SET access_count = access_count + 1,
                        last_accessed = CURRENT_TIMESTAMP
                    WHERE id IN ({placeholders});
                    """,
                    ids,
                )

            return top_results

    def save_checkpoint(
        self,
        workspace: str,
        project: str,
        goal: str = "",
        status: str = "",
        stack: str = "",
        last_completed: str = "",
        next_tasks: str = "",
        key_files: str = "",
        notes: str = "",
    ) -> None:
        ws = self.normalize_workspace(workspace) if ("/" in workspace or "\\" in workspace) else (workspace.strip().lower() or "global")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO checkpoints (workspace, project, goal, status, stack, last_completed, next_tasks, key_files, notes, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(workspace) DO UPDATE SET
                    project = excluded.project,
                    goal = CASE WHEN excluded.goal != '' THEN excluded.goal ELSE checkpoints.goal END,
                    status = CASE WHEN excluded.status != '' THEN excluded.status ELSE checkpoints.status END,
                    stack = CASE WHEN excluded.stack != '' THEN excluded.stack ELSE checkpoints.stack END,
                    last_completed = CASE WHEN excluded.last_completed != '' THEN excluded.last_completed ELSE checkpoints.last_completed END,
                    next_tasks = CASE WHEN excluded.next_tasks != '' THEN excluded.next_tasks ELSE checkpoints.next_tasks END,
                    key_files = CASE WHEN excluded.key_files != '' THEN excluded.key_files ELSE checkpoints.key_files END,
                    notes = CASE WHEN excluded.notes != '' THEN excluded.notes ELSE checkpoints.notes END,
                    updated_at = CURRENT_TIMESTAMP;
                """,
                (ws, project, goal, status, stack, last_completed, next_tasks, key_files, notes),
            )

    def get_checkpoint(self, workspace: Optional[str]) -> Optional[Dict[str, Any]]:
        ws = self.normalize_workspace(workspace)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM checkpoints WHERE workspace = ?;", (ws,)
            ).fetchone()
            return dict(row) if row else None

    def mark_turn_injected(self, conversation_id: str, prompt_text: str) -> bool:
        """Retorna True se este prompt neste conversation_id AINDA NÃO foi injetado."""
        p_hash = hashlib.sha256(prompt_text.strip().encode("utf-8")).hexdigest()[:24]
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT 1 FROM injected_turns WHERE conversation_id = ? AND prompt_hash = ?;",
                (conversation_id, p_hash),
            ).fetchone()
            if existing:
                return False
            conn.execute(
                "INSERT INTO injected_turns (conversation_id, prompt_hash) VALUES (?, ?);",
                (conversation_id, p_hash),
            )
            return True

    def log_telemetry(
        self,
        event_type: str,
        conversation_id: str = "",
        workspace: str = "global",
        latency_ms: float = 0.0,
        injected_tokens: int = 0,
        estimated_saved_tokens: int = 0,
        details: str = "",
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO telemetry (event_type, conversation_id, workspace, latency_ms, injected_tokens, estimated_saved_tokens, details)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    event_type,
                    conversation_id,
                    workspace,
                    round(latency_ms, 2),
                    injected_tokens,
                    estimated_saved_tokens,
                    details,
                ),
            )

    def get_stats(self) -> Dict[str, Any]:
        with self._connect() as conn:
            mem_count = conn.execute("SELECT COUNT(*) as c FROM memories;").fetchone()["c"]
            chk_count = conn.execute("SELECT COUNT(*) as c FROM checkpoints;").fetchone()["c"]
            tel = conn.execute(
                """
                SELECT COUNT(*) as total_events,
                       COALESCE(AVG(latency_ms), 0.0) as avg_latency_ms,
                       COALESCE(SUM(injected_tokens), 0) as total_injected_tokens,
                       COALESCE(SUM(estimated_saved_tokens), 0) as total_saved_tokens
                FROM telemetry
                WHERE event_type = 'pre_invocation_inject';
                """
            ).fetchone()
            harvest_count = conn.execute(
                "SELECT COUNT(*) as c FROM telemetry WHERE event_type = 'stop_harvest';"
            ).fetchone()["c"]
            by_cat = conn.execute(
                "SELECT category, COUNT(*) as c FROM memories GROUP BY category ORDER BY c DESC;"
            ).fetchall()

            # Métricas da Janela Deslizante de 5 Horas (5h Quota Window)
            w5 = conn.execute(
                """
                SELECT COUNT(*) as turns_5h,
                       COALESCE(SUM(injected_tokens), 0) as inj_5h,
                       COALESCE(SUM(estimated_saved_tokens), 0) as sav_5h,
                       MIN(created_at) as oldest_ts
                FROM telemetry
                WHERE created_at >= datetime('now', '-5 hours')
                  AND event_type = 'pre_invocation_inject';
                """
            ).fetchone()

            turns_5h = int(w5["turns_5h"] or 0) if w5 else 0
            saved_5h = int(w5["sav_5h"] or 0) if w5 else 0
            inj_5h = int(w5["inj_5h"] or 0) if w5 else 0
            reset_mins = 300
            if w5 and w5["oldest_ts"]:
                try:
                    dt_old = datetime.datetime.fromisoformat(str(w5["oldest_ts"]).replace("Z", ""))
                    now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                    elapsed_m = (now_utc - dt_old).total_seconds() / 60.0
                    reset_mins = max(1, min(300, int(300 - elapsed_m)))
                except Exception:
                    reset_mins = 240
            rh = reset_mins // 60
            rm = reset_mins % 60
            reset_lbl = f"{rh}h {rm:02d}m" if rh > 0 else f"{rm}m"

            return {
                "total_memories": mem_count,
                "total_checkpoints": chk_count,
                "injections_count": tel["total_events"],
                "harvests_count": harvest_count,
                "avg_inject_latency_ms": round(float(tel["avg_latency_ms"]), 2),
                "total_injected_tokens": int(tel["total_injected_tokens"]),
                "estimated_saved_tokens": int(tel["total_saved_tokens"]),
                "net_tokens_saved": int(tel["total_saved_tokens"]) - int(tel["total_injected_tokens"]),
                "categories": {r["category"]: r["c"] for r in by_cat},
                "quota_5h": {
                    "turns_5h": turns_5h,
                    "saved_5h": saved_5h,
                    "injected_5h": inj_5h,
                    "reset_in_minutes": reset_mins,
                    "reset_label": reset_lbl,
                },
            }

    def toggle_pin_memory(self, mem_id: int) -> Dict[str, Any]:
        """Fixa (Pin) ou desafixa uma memória no topo do bloco [BRAIN_MEMORY]."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, topic, tags, importance FROM memories WHERE id = ?;",
                (int(mem_id),),
            ).fetchone()
            if not row:
                return {"ok": False, "error": "Memória não encontrada"}
            cur_tags = str(row["tags"] or "").split()
            is_pinned = "pinned" in [t.lower() for t in cur_tags]
            if is_pinned:
                new_tags = " ".join(t for t in cur_tags if t.lower() != "pinned")
                new_imp = 4
            else:
                new_tags = " ".join(cur_tags + ["pinned"]).strip()
                new_imp = 5
            conn.execute(
                "UPDATE memories SET tags = ?, importance = ?, last_accessed = CURRENT_TIMESTAMP WHERE id = ?;",
                (new_tags, new_imp, int(mem_id)),
            )
            return {
                "ok": True,
                "id": int(mem_id),
                "topic": row["topic"],
                "pinned": not is_pinned,
                "importance": new_imp,
                "tags": new_tags,
            }

    def run_memory_doctor(self) -> Dict[str, Any]:
        """
        Memory Doctor (v2.8): Analisa todas as memórias para fundir tópicos duplicados,
        remover referências a ficheiros apagados e otimizar o índice FTS5 BM25.
        """
        repo_dir = os.path.dirname(os.path.abspath(__file__))
        merged_count = 0
        stale_removed = 0
        upgraded_pins = 0

        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, workspace, category, topic, fact, tags, importance, access_count FROM memories ORDER BY id ASC;"
            ).fetchall()

            by_key: Dict[Tuple[str, str], Dict[str, Any]] = {}
            to_delete: List[int] = []

            for r in rows:
                d = dict(r)
                mid = int(d["id"])
                ws = str(d["workspace"] or "global").strip().lower()
                topic = str(d["topic"] or "").strip()
                norm_topic = re.sub(r"\s+", " ", topic.lower())

                # 1. Verificar se é uma memória de ficheiro cujo caminho em disco já foi apagado
                if norm_topic.startswith("ficheiro "):
                    m_path = re.search(r"([A-Za-z]:[/\\][^\s\"']+)", str(d.get("fact") or ""))
                    if m_path:
                        disk_p = m_path.group(1).rstrip(".,;)")
                        if not os.path.exists(disk_p):
                            to_delete.append(mid)
                            stale_removed += 1
                            continue

                key = (ws, norm_topic)
                if key in by_key:
                    primary = by_key[key]
                    # Fundir tags, access_count e importância na memória principal
                    p_tags = set(str(primary["tags"] or "").split()) | set(str(d["tags"] or "").split())
                    new_tags = " ".join(sorted(p_tags))
                    new_imp = max(int(primary["importance"] or 3), int(d["importance"] or 3))
                    new_acc = int(primary["access_count"] or 0) + int(d["access_count"] or 0)
                    new_fact = d["fact"] if len(str(d["fact"])) >= len(str(primary["fact"])) else primary["fact"]

                    conn.execute(
                        "UPDATE memories SET fact = ?, tags = ?, importance = ?, access_count = ? WHERE id = ?;",
                        (new_fact, new_tags, new_imp, new_acc, int(primary["id"])),
                    )
                    primary["fact"] = new_fact
                    primary["tags"] = new_tags
                    primary["importance"] = new_imp
                    primary["access_count"] = new_acc
                    to_delete.append(mid)
                    merged_count += 1
                else:
                    by_key[key] = d

                # Garantir que memórias com tag 'pinned' ou 'directive' têm importância 5
                if ("pinned" in str(d["tags"]).lower() or d["category"] == "directive") and int(d["importance"] or 3) < 5:
                    conn.execute("UPDATE memories SET importance = 5 WHERE id = ?;", (mid,))
                    upgraded_pins += 1

            if to_delete:
                placeholders = ",".join("?" for _ in to_delete)
                conn.execute(f"DELETE FROM memories WHERE id IN ({placeholders});", to_delete)

            # Otimizar índice FTS5 BM25
            try:
                conn.execute("INSERT INTO memories_fts(memories_fts) VALUES('optimize');")
            except Exception:
                pass

            healthy_total = conn.execute("SELECT COUNT(*) as c FROM memories;").fetchone()["c"]

        return {
            "ok": True,
            "merged_duplicates": merged_count,
            "stale_removed": stale_removed,
            "upgraded_pins": upgraded_pins,
            "healthy_memories": int(healthy_total),
            "fts5_optimized": True,
        }

    def export_brain_pack(self, workspace_filter: str = "all") -> Dict[str, Any]:
        """Exporta o cérebro em formato .brainpack.json e em formato Markdown Obsidian Vault com [[WikiLinks]]."""
        ws_clean = (workspace_filter or "all").strip().lower()
        with self._connect() as conn:
            if ws_clean != "all":
                mems = [
                    dict(r)
                    for r in conn.execute(
                        "SELECT * FROM memories WHERE workspace = ? ORDER BY importance DESC, id ASC;",
                        (ws_clean,),
                    ).fetchall()
                ]
                chks = [
                    dict(r)
                    for r in conn.execute(
                        "SELECT * FROM checkpoints WHERE workspace = ?;", (ws_clean,)
                    ).fetchall()
                ]
            else:
                mems = [
                    dict(r)
                    for r in conn.execute(
                        "SELECT * FROM memories ORDER BY workspace ASC, importance DESC, id ASC;"
                    ).fetchall()
                ]
                chks = [
                    dict(r)
                    for r in conn.execute("SELECT * FROM checkpoints ORDER BY workspace ASC;").fetchall()
                ]

        # Construir documento Markdown compatível com Obsidian Vault (com [[WikiLinks]] entre notas)
        md_lines = [
            "---",
            f"title: Antigravity Brain Vault ({ws_clean.upper()})",
            "version: 2.8",
            f"memories_count: {len(mems)}",
            f"checkpoints_count: {len(chks)}",
            "---",
            "",
            f"# 🧠 Antigravity Brain Vault — `{ws_clean.upper()}`",
            "",
            "## 🏁 Checkpoints de Projeto",
        ]
        for c in chks:
            md_lines.extend(
                [
                    f"### 📂 [[Workspace {c['workspace']}]] — {c.get('project', c['workspace'])}",
                    f"- **Status**: `{c.get('status', '')}`",
                    f"- **Objetivo**: {c.get('goal', '')}",
                    f"- **Ficheiros-Chave**: `{c.get('key_files', '')}`",
                    f"- **Última Ação**: {c.get('last_completed', '')}",
                    "",
                ]
            )

        md_lines.append("## ⚡ Memórias & Sinapses (`[[WikiLinks]]`)")
        # Mapear tags para criar [[WikiLinks]] automáticos
        tag_map: Dict[str, List[str]] = {}
        for m in mems:
            for t in str(m.get("tags", "")).split():
                if len(t) >= 3 and t not in ("file", "edit", "explicit", "global"):
                    tag_map.setdefault(t.lower(), []).append(m["topic"])

        for m in mems:
            pin_icon = "📌 " if "pinned" in str(m.get("tags", "")).lower() else ""
            tags_formatted = " ".join(f"#{t}" for t in str(m.get("tags", "")).split() if t)
            related: List[str] = []
            for t in str(m.get("tags", "")).split():
                for other_topic in tag_map.get(t.lower(), []):
                    if other_topic != m["topic"] and other_topic not in related:
                        related.append(other_topic)
            wikilinks = ", ".join(f"[[{rt}]]" for rt in related[:4])

            md_lines.extend(
                [
                    f"### {pin_icon}{m['topic']}",
                    f"- **Workspace**: [[Workspace {m['workspace']}]] | **Categoria**: `{m.get('category', 'general')}` | **Importância**: {'⭐' * int(m.get('importance', 3))}",
                    f"- **Facto**: {m['fact']}",
                    f"- **Tags**: {tags_formatted or '#general'}",
                    f"- **Ligações Sinápticas**: {wikilinks or '*(Nó Independente)*'}",
                    "",
                ]
            )

        return {
            "version": "2.8",
            "workspace_filter": ws_clean,
            "exported_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "memories_count": len(mems),
            "checkpoints_count": len(chks),
            "brainpack": {
                "version": "2.8",
                "memories": mems,
                "checkpoints": chks,
            },
            "obsidian_markdown": "\n".join(md_lines),
        }

    def import_brain_pack(self, pack_data: Dict[str, Any]) -> Dict[str, Any]:
        """Importa um ficheiro .brainpack.json para o brain.db sem duplicar factos existentes."""
        inner = pack_data.get("brainpack") if isinstance(pack_data.get("brainpack"), dict) else pack_data
        mems = inner.get("memories") or []
        chks = inner.get("checkpoints") or []
        imported_mems = 0
        updated_mems = 0
        imported_chks = 0

        for m in mems:
            topic = str(m.get("topic", "")).strip()
            fact = str(m.get("fact", "")).strip()
            if not topic or not fact:
                continue
            _, is_new = self.store_fact(
                topic=topic,
                fact=fact,
                workspace=str(m.get("workspace", "global")),
                category=str(m.get("category", "general")),
                tags=str(m.get("tags", "")),
                importance=int(m.get("importance", 4) or 4),
            )
            if is_new:
                imported_mems += 1
            else:
                updated_mems += 1

        for c in chks:
            ws = str(c.get("workspace", "")).strip()
            if not ws:
                continue
            self.save_checkpoint(
                workspace=ws,
                project=str(c.get("project", ws)),
                goal=str(c.get("goal", "")),
                status=str(c.get("status", "")),
                stack=str(c.get("stack", "")),
                last_completed=str(c.get("last_completed", "")),
                next_tasks=str(c.get("next_tasks", "")),
                key_files=str(c.get("key_files", "")),
                notes=str(c.get("notes", "")),
            )
            imported_chks += 1

        return {
            "ok": True,
            "imported_memories": imported_mems,
            "updated_memories": updated_mems,
            "imported_checkpoints": imported_chks,
        }


def seed_initial_memories(db: BrainDB) -> int:
    """Popula o Brain com o contexto base da arquitetura Antigravity Brain v2."""
    repo_dir = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
    scratch_dir = os.path.expanduser("~/.gemini/antigravity/scratch").replace("\\", "/")
    config_dir = os.path.expanduser("~/.gemini/config").replace("\\", "/")

    initial_facts = [
        (
            "Ambiente & Antigravity Paths",
            f"Pasta scratch padrão para projetos: {scratch_dir}. Config global: {config_dir}. Diretório do Brain v2: {repo_dir}.",
            "global",
            "environment",
            "windows scratch uv python config paths",
            5,
        ),
        (
            "Arquitetura Antigravity Brain v2 (Zero-Round-Trip)",
            f"O Brain v2 usa hooks nativos em {config_dir}/hooks.json (PreInvocation -> brain_inject.py e Stop -> brain_harvest.py) ligados a brain.db (SQLite FTS5 BM25). Injeta ephemeralMessage antes da resposta em <40ms sem gastar chamadas extra de tool.",
            "brain_mcp",
            "architecture",
            "brain hooks preinvocation stop sqlite fts5 ephemeralmessage tokens",
            5,
        ),
        (
            "Otimização de Quota 5h (Token Diet)",
            f"Para reduzir o gasto de tokens por passo na janela de 5h, usar token_diet.py em {repo_dir}/token_diet.py para alternar entre o perfil 'lean' (desativa MCPs pesados) e 'full'.",
            "global",
            "optimization",
            "quota 5h tokens token_diet mcp plugins lean full",
            5,
        ),
        (
            "Scout-First Asymmetric Swarm Engine",
            f"Implementado em {repo_dir}/swarm_engine.py e visualizado em http://127.0.0.1:8765/#swarm. O SCOUT-01 lê a codebase 1 única vez via AST e partilha o [SCOUT_SHARED_MAP] com todos os subagentes (UI, API, TESTS, DOCS).",
            "brain_mcp",
            "architecture",
            "swarm scout blackboard lanes flash opus verify",
            5,
        ),
    ]
    added = 0
    for topic, fact, ws, cat, tags, imp in initial_facts:
        _, is_new = db.store_fact(
            topic=topic,
            fact=fact,
            workspace=ws,
            category=cat,
            tags=tags,
            importance=imp,
        )
        if is_new:
            added += 1
    return added


def ensure_dashboard_running(port: int = 8765) -> bool:
    """Garante que o servidor web Obsidian Brain (porta 8765) está ativo em background sem janela."""
    import socket
    import subprocess
    import sys

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.05)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True

        script_dir = os.path.dirname(os.path.abspath(__file__))
        dashboard_script = os.path.join(script_dir, "web_dashboard.py")
        if not os.path.isfile(dashboard_script):
            return False

        python_exe = sys.executable
        if os.name == "nt":
            pw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
            if os.path.isfile(pw):
                python_exe = pw

        # DETACHED_PROCESS (0x00000008) | CREATE_NEW_PROCESS_GROUP (0x00000200) | CREATE_NO_WINDOW (0x08000000)
        # Try with CREATE_BREAKAWAY_FROM_JOB (0x01000000) first so hook termination doesn't kill child
        if os.name == "nt":
            for flags in (0x01000000 | 0x08000000 | 0x00000200 | 0x00000008, 0x08000000 | 0x00000200):
                try:
                    subprocess.Popen(
                        [python_exe, dashboard_script],
                        cwd=script_dir,
                        creationflags=flags,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        close_fds=True,
                    )
                    return True
                except OSError:
                    continue
        else:
            subprocess.Popen(
                [python_exe, dashboard_script],
                cwd=script_dir,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                start_new_session=True,
            )
            return True
        return False
    except Exception:
        return False



if __name__ == "__main__":
    t0 = time.perf_counter()
    db = BrainDB()
    seeded = seed_initial_memories(db)
    elapsed = (time.perf_counter() - t0) * 1000
    print(f"BrainDB inicializado em {elapsed:.1f}ms (Novos factos semeados: {seeded})")
    print("Stats:", json.dumps(db.get_stats(), indent=2, ensure_ascii=False))
