import json
import os
import re
import sys
import time
from typing import Any, Dict, List

from brain_inject import resolve_transcript_path
from db_engine import BrainDB


def harvest_latest_turn(transcript_path: str, workspace: str, conv_id: str, db: BrainDB) -> int:
    """Analisa os passos do último turno no transcript.jsonl e extrai memórias a custo 0 de tokens."""
    if not transcript_path or not os.path.isfile(transcript_path):
        return 0

    file_size = os.path.getsize(transcript_path)
    read_size = min(file_size, 131072)  # Últimos 128KB
    with open(transcript_path, "rb") as f:
        if file_size > read_size:
            f.seek(file_size - read_size)
        tail_bytes = f.read()

    lines = tail_bytes.decode("utf-8", errors="ignore").splitlines()
    steps: List[Dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            steps.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    if not steps:
        return 0

    # Isola apenas os passos após o último USER_INPUT
    last_user_idx = 0
    for idx in range(len(steps) - 1, -1, -1):
        if steps[idx].get("type") == "USER_INPUT":
            last_user_idx = idx
            break

    turn_steps = steps[last_user_idx:]
    harvested_count = 0
    modified_files: List[str] = []
    completed_actions: List[str] = []
    turn_input_tokens = 0
    turn_cached_tokens = 0
    turn_output_tokens = 0

    for step in turn_steps:
        if step.get("type") != "PLANNER_RESPONSE":
            continue

        turn_input_tokens += int(step.get("input_tokens", 0) or 0)
        turn_cached_tokens += int(step.get("cache_read_tokens", 0) or 0)
        turn_output_tokens += int(step.get("output_tokens", 0) or 0)

        # 1. Extrai marcadores explícitos <!-- brain: Topico | Facto --> no texto da resposta
        content = step.get("content", "") or ""
        explicit_matches = re.findall(
            r"<!--\s*brain:\s*([^|\n]+?)\s*\|\s*(.*?)\s*-->",
            content,
            flags=re.DOTALL,
        )
        for topic, fact in explicit_matches:
            _, is_new = db.store_fact(
                topic=topic.strip(),
                fact=fact.strip(),
                workspace=workspace,
                category="explicit_note",
                tags="auto_harvested explicit",
                importance=4,
            )
            if is_new:
                harvested_count += 1

        # 2. Extrai edições de ficheiros (write_to_file / replace_file_content)
        tool_calls = step.get("tool_calls") or []
        for tc in tool_calls:
            t_name = tc.get("name", "")
            args = tc.get("args") or {}
            if t_name in ("write_to_file", "replace_file_content"):
                target_file = str(args.get("TargetFile", "")).strip('"').replace("\\\\", "/")
                desc = str(args.get("Description", "")).strip('"')
                if target_file and "/brain/" not in target_file:
                    bname = os.path.basename(target_file)
                    if bname not in modified_files:
                        modified_files.append(bname)
                    if desc:
                        completed_actions.append(f"{bname}: {desc}")
                        _, is_new = db.store_fact(
                            topic=f"Ficheiro {bname} ({workspace})",
                            fact=f"Path: {target_file} — {desc}",
                            workspace=workspace,
                            category="code_change",
                            tags=f"{bname} {workspace} file edit",
                            importance=3,
                        )
                        if is_new:
                            harvested_count += 1

    # 3. Atualiza o Checkpoint automático do workspace se houve alterações de código
    if modified_files or completed_actions:
        db.save_checkpoint(
            workspace=workspace,
            project=workspace,
            last_completed="; ".join(completed_actions[-3:])[:300],
            key_files=", ".join(modified_files[-6:])[:200],
        )

    # 4. Regista telemetria real do turno
    db.log_telemetry(
        event_type="stop_harvest",
        conversation_id=conv_id,
        workspace=workspace,
        latency_ms=0.0,
        injected_tokens=0,
        estimated_saved_tokens=harvested_count * 1200,
        details=(
            f"harvested={harvested_count} "
            f"in_tok={turn_input_tokens} "
            f"cache_tok={turn_cached_tokens} "
            f"out_tok={turn_output_tokens}"
        ),
    )
    return harvested_count


def handle_stop(raw_stdin: str) -> Dict[str, Any]:
    t0 = time.perf_counter()
    if raw_stdin.strip():
        payload = json.loads(raw_stdin)
        conv_id = str(payload.get("conversationId", "default"))
        workspaces = payload.get("workspacePaths") or []
        raw_ws = workspaces[0] if workspaces else "global"

        db = BrainDB()
        ws = db.normalize_workspace(raw_ws)
        transcript_path = resolve_transcript_path(payload)
        if transcript_path:
            harvest_latest_turn(transcript_path, ws, conv_id, db)

    # Devolve "allow" (qualquer valor diferente de "continue" permite terminar normalmente)
    return {"decision": "allow"}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        raw_in = sys.stdin.read()
        result = handle_stop(raw_in)
        print(json.dumps(result, ensure_ascii=False))
    except Exception:
        print('{"decision": "allow"}')


if __name__ == "__main__":
    main()
