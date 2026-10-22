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


def build_ephemeral_context(
    memories: List[Dict[str, Any]],
    checkpoint: Optional[Dict[str, Any]],
    workspace: str,
    scout_map: str = "",
) -> str:
    """Formata um bloco ultra-compacto (<320 tokens) para injeção efémera + Scout Shared Map."""
    parts: List[str] = [
        f"[BRAIN_MEMORY | ws={workspace} | Use estes factos e o SCOUT_MAP para evitar buscas/leituras redundantes]"
    ]

    if checkpoint:
        chk_line = (
            f"CHECKPOINT ({checkpoint.get('project', workspace)}): "
            f"Goal={checkpoint.get('goal', 'N/A')} | "
            f"Status={checkpoint.get('status', 'N/A')} | "
            f"Files={checkpoint.get('key_files', 'N/A')}"
        )
        parts.append(chk_line[:280])

    if scout_map:
        parts.append(scout_map[:420])

    for m in memories:
        topic = m.get("topic", "Fact")
        if topic.startswith("Scout Shared Codebase Map") and scout_map:
            continue
        fact = m.get("fact", "")
        ws_tag = f"[{m.get('workspace', 'global')}]" if m.get("workspace") != "global" else ""
        entry = f"- {ws_tag}{topic}: {fact}"
        if sum(len(p) for p in parts) + len(entry) + 2 > MAX_EPHEMERAL_CHARS:
            break
        parts.append(entry)

    return "\n".join(parts)


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

    # Evita injetar novamente nos sub-passos de tool loop do mesmo pedido do utilizador
    if not db.mark_turn_injected(conv_id, user_query):
        return {}

    memories = db.search_memories(query=user_query, workspace=ws, n_results=5)
    checkpoint = db.get_checkpoint(ws)
    scout_map = ""
    try:
        scout_map = SwarmEngine(db).get_latest_scout_map(ws)
    except Exception:
        scout_map = ""

    if not memories and not checkpoint and not scout_map:
        return {}

    ephemeral_msg = build_ephemeral_context(memories, checkpoint, ws, scout_map=scout_map)
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
