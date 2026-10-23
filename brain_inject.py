import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional

from db_engine import BrainDB, ensure_dashboard_running
from swarm_engine import SwarmEngine

MAX_EPHEMERAL_CHARS = 1350  # ~320 tokens max budget (inclui Scout Shared Map)


def resolve_transcript_path(payload: Dict[str, Any]) -> Optional[str]:
    """Localiza o ficheiro transcript.jsonl da conversa atual."""
    candidates: List[str] = []

    t_path = payload.get("transcriptPath")
    if t_path:
        candidates.append(t_path)

    art_dir = payload.get("artifactDirectoryPath")
    if art_dir:
        candidates.append(os.path.join(art_dir, ".system_generated", "logs", "transcript.jsonl"))

    conv_id = payload.get("conversationId")
    if conv_id:
        app_data = os.path.expanduser("~/.gemini/antigravity")
        candidates.append(
            os.path.join(app_data, "brain", conv_id, ".system_generated", "logs", "transcript.jsonl")
        )

    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def extract_latest_user_request(transcript_path: Optional[str]) -> Optional[str]:
    """Lê o último USER_INPUT do transcript.jsonl de forma eficiente."""
    if not transcript_path or not os.path.isfile(transcript_path):
        return None

    try:
        # Lê apenas os últimos 64KB para ser instantâneo mesmo em conversas grandes
        file_size = os.path.getsize(transcript_path)
        read_size = min(file_size, 65536)
        with open(transcript_path, "rb") as f:
            if file_size > read_size:
                f.seek(file_size - read_size)
            tail_bytes = f.read()

        lines = tail_bytes.decode("utf-8", errors="ignore").splitlines()
        for line in reversed(lines):
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                step = json.loads(line)
            except json.JSONDecodeError:
                continue

            if step.get("type") == "USER_INPUT":
                content = step.get("content", "")
                match = re.search(
                    r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>",
                    content,
                     flags=re.DOTALL,
                )
                if match:
                    return match.group(1).strip()
                return content.strip()[:1000]
    except Exception:
        return None
    return None


def extract_latest_tool_actions(transcript_path: Optional[str]) -> List[str]:
    """Extrai as ferramentas/ficheiros reais que o Antigravity acabou de executar neste passo."""
    if not transcript_path or not os.path.isfile(transcript_path):
        return []
    try:
        file_size = os.path.getsize(transcript_path)
        read_size = min(file_size, 32768)
        with open(transcript_path, "rb") as f:
            if file_size > read_size:
                f.seek(file_size - read_size)
            tail_bytes = f.read()
        lines = tail_bytes.decode("utf-8", errors="ignore").splitlines()
        for line in reversed(lines):
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                step = json.loads(line)
            except json.JSONDecodeError:
                continue
            if step.get("type") == "PLANNER_RESPONSE" and step.get("tool_calls"):
                actions: List[str] = []
                for tc in step.get("tool_calls") or []:
                    name = tc.get("name", "tool")
                    args = tc.get("args") or {}
                    target = (
                        args.get("Path")
                        or args.get("TargetFile")
                        or args.get("AbsolutePath")
                        or args.get("Role")
                        or args.get("toolSummary")
                        or args.get("CommandLine", "")[:35]
                    )
                    if target and ("/" in str(target) or "\\" in str(target)):
                        target = os.path.basename(str(target).rstrip("/\\"))
                    actions.append(f"{name}({target})" if target else name)
                return actions
            if step.get("type") == "USER_INPUT":
                break
    except Exception:
        pass
    return []


def compute_adaptive_budget(user_query: str) -> int:
    """Ajusta dinamicamente o orçamento de caracteres conforme a complexidade do pedido."""
    q = (user_query or "").strip().lower()
    deep_keywords = ("analise", "arquitetura", "bug", "erro", "refactor", "todos", "melhoria", "ultraplan", "implement")
    if len(q) > 85 or any(k in q for k in deep_keywords):
        return 1680  # ~420 tokens para tarefas complexas
    if len(q) < 22:
        return 1020  # ~255 tokens para confirmações rápidas
    return MAX_EPHEMERAL_CHARS


def build_ephemeral_context(
    memories: List[Dict[str, Any]],
    checkpoint: Optional[Dict[str, Any]],
    workspace: str,
    scout_map: str = "",
    max_chars: int = MAX_EPHEMERAL_CHARS,
) -> str:
    """Formata um bloco ultra-compacto para injeção efémera + Scout Shared Map."""
    parts: List[str] = [
        f"[BRAIN_MEMORY | ws={workspace} | Use estes factos e o SCOUT_MAP para evitar buscas/leituras redundantes]"
    ]

    if checkpoint:
        c_goal = (checkpoint.get("goal") or checkpoint.get("last_completed") or "Sessão ativa").strip()
        c_status = (checkpoint.get("status") or "Ativo • Auto-Synced").strip()
        c_files = (checkpoint.get("key_files") or "N/A").strip()
        chk_line = (
            f"CHECKPOINT ({checkpoint.get('project') or workspace}): "
            f"Goal={c_goal[:90]} | "
            f"Status={c_status[:45]} | "
            f"Files={c_files[:95]}"
        )
        parts.append(chk_line[:280])

    if scout_map:
        parts.append(scout_map[:480])

    seen_topics: set[str] = set()
    # Priorizar memórias Fixadas (Pinned) ou Diretivas Diretas do Escritório 3D no topo!
    sorted_memories = sorted(
        memories,
        key=lambda x: (
            1
            if ("pinned" in str(x.get("tags", "")).lower() or x.get("category") == "directive")
            else 0
        ),
        reverse=True,
    )
    for m in sorted_memories:
        topic = (m.get("topic") or "Fact").strip()
        if topic.startswith("Scout Shared Codebase Map") and scout_map:
            continue
        norm_topic = re.sub(r"\s+", " ", topic.lower())
        if norm_topic in seen_topics:
            continue
        seen_topics.add(norm_topic)
        fact = (m.get("fact") or "").strip()
        is_pin = "pinned" in str(m.get("tags", "")).lower() or m.get("category") == "directive"
        pin_prefix = "📌[PIN] " if is_pin else ""
        ws_tag = f"[{m.get('workspace', 'global')}]" if m.get("workspace") != "global" else ""
        entry = f"- {pin_prefix}{ws_tag}{topic}: {fact}"
        if sum(len(p) for p in parts) + len(entry) + 2 > max_chars:
            break
        parts.append(entry)

    return "\n".join(parts)


def generate_inspector_preview(
    db: BrainDB, workspace: str = "brain_mcp", query: str = ""
) -> Dict[str, Any]:
    """Gera a pré-visualização exata do bloco [BRAIN_MEMORY] + [SCOUT_SHARED_MAP] para o Prompt Inspector."""
    ws = db.normalize_workspace(workspace) if workspace and workspace != "all" else "brain_mcp"
    effective_query = (query or "").strip() or f"workspace {ws} architecture environment"
    budget_chars = compute_adaptive_budget(effective_query)

    # Garantir que memórias Pinned/Diretivas entram sempre mesmo que não façam match léxico
    with db._connect() as conn:
        pinned_rows = [
            dict(r)
            for r in conn.execute(
                """
                SELECT * FROM memories
                WHERE (tags LIKE '%pinned%' OR category = 'directive')
                  AND (workspace = ? OR workspace = 'global')
                ORDER BY id DESC LIMIT 6;
                """,
                (ws,),
            ).fetchall()
        ]

    searched = db.search_memories(
        query=effective_query, workspace=ws, n_results=8, update_stats=False
    )
    combined = pinned_rows + searched
    checkpoint = db.get_checkpoint(ws)
    scout_map = ""
    try:
        scout_map = SwarmEngine(db).get_latest_scout_map(ws)
    except Exception:
        scout_map = ""

    ephemeral_text = build_ephemeral_context(
        combined, checkpoint, ws, scout_map=scout_map, max_chars=budget_chars
    )
    est_tokens = max(1, len(ephemeral_text) // 4)
    return {
        "workspace": ws,
        "query": effective_query,
        "budget_chars": budget_chars,
        "actual_chars": len(ephemeral_text),
        "estimated_tokens": est_tokens,
        "pinned_count": len(pinned_rows),
        "matched_count": len(searched),
        "ephemeral_block": ephemeral_text,
        "pinned_memories": [
            {"id": p["id"], "topic": p["topic"], "fact": p["fact"], "workspace": p["workspace"]}
            for p in pinned_rows
        ],
    }


def handle_pre_invocation(raw_stdin: str) -> Dict[str, Any]:
    t0 = time.perf_counter()
    ensure_dashboard_running()
    if not raw_stdin.strip():
        return {}

    payload = json.loads(raw_stdin)
    conv_id = str(payload.get("conversationId", "default"))
    workspaces = payload.get("workspacePaths") or []
    raw_ws = workspaces[0] if workspaces else "global"

    db = BrainDB()
    ws = db.normalize_workspace(raw_ws)

    transcript_path = resolve_transcript_path(payload)
    user_query = extract_latest_user_request(transcript_path)

    # Se não conseguirmos ler o transcript (ex.: primeiro passo absoluto ainda não gravado em disco),
    # apenas injetamos se invocationNum <= 1 usando o contexto do workspace.
    inv_num = int(payload.get("invocationNum", 1))
    if not user_query:
        if inv_num > 1:
            return {}
        user_query = f"workspace {ws} architecture environment"

    # Evita injetar novamente nos sub-passos de tool loop do mesmo pedido do utilizador,
    # mas atualiza o progresso em tempo real no Swarm Monitor com as tools reais!
    swarm_eng = SwarmEngine(db)
    if not db.mark_turn_injected(conv_id, user_query):
        try:
            real_actions = extract_latest_tool_actions(transcript_path)
            swarm_eng.on_turn_step(inv_num, real_actions, conversation_id=conv_id, workspace=ws)
        except Exception:
            pass
        return {}

    try:
        swarm_eng.on_turn_start(user_query, raw_ws, conversation_id=conv_id)
    except Exception:
        pass

    with db._connect() as conn:
        pinned_rows = [
            dict(r)
            for r in conn.execute(
                """
                SELECT * FROM memories
                WHERE (tags LIKE '%pinned%' OR category = 'directive')
                  AND (workspace = ? OR workspace = 'global')
                ORDER BY id DESC LIMIT 4;
                """,
                (ws,),
            ).fetchall()
        ]
    memories = pinned_rows + db.search_memories(query=user_query, workspace=ws, n_results=8)
    checkpoint = db.get_checkpoint(ws)
    scout_map = ""
    try:
        scout_map = swarm_eng.get_latest_scout_map(ws)
    except Exception:
        scout_map = ""

    if not memories and not checkpoint and not scout_map:
        return {}

    budget_chars = compute_adaptive_budget(user_query)
    ephemeral_msg = build_ephemeral_context(
        memories, checkpoint, ws, scout_map=scout_map, max_chars=budget_chars
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    injected_tokens = max(1, len(ephemeral_msg) // 4)
    # Estimativa conservadora: evitar 1 round-trip de busca/view_file poupa ~4.500 tokens
    estimated_saved = 4500 if memories else 1500

    db.log_telemetry(
        event_type="pre_invocation_inject",
        conversation_id=conv_id,
        workspace=ws,
        latency_ms=elapsed_ms,
        injected_tokens=injected_tokens,
        estimated_saved_tokens=estimated_saved,
        details=f"matched={len(memories)} query={user_query[:60]}",
    )

    return {
        "injectSteps": [
            {
                "ephemeralMessage": ephemeral_msg
            }
        ]
    }


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        raw_in = sys.stdin.read()
        result = handle_pre_invocation(raw_in)
        print(json.dumps(result, ensure_ascii=False))
    except Exception:
        # Fail-open: nunca bloquear o loop do Antigravity
        print("{}")


if __name__ == "__main__":
    main()
