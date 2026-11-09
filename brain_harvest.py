import json
import os
import re
import sys
import time
from typing import Any, Dict, List

from brain_inject import resolve_smart_active_workspace, resolve_transcript_path
from db_engine import BrainDB
from orbit_engine import OrbitEngine
from swarm_engine import SwarmEngine


def clean_system_envelope(text: str) -> str:
    """Remove cabeçalhos e tags de sistema (<SYSTEM_MESSAGE>, [Message] timestamp=..., <USER_REQUEST>, [BRAIN_MEMORY])."""
    if not text:
        return ""
    s = str(text)
    s = re.sub(
        r"The following is a <SYSTEM_MESSAGE>.*?(?=<SYSTEM_MESSAGE>|$)",
        "",
        s,
        flags=re.DOTALL | re.I,
    )
    s = re.sub(
        r"</?(?:SYSTEM_MESSAGE|USER_REQUEST|EPHEMERAL_MESSAGE)>",
        "",
        s,
        flags=re.I,
    )
    s = re.sub(
        r"\[Message\]\s*timestamp=\S+\s+sender=\S+\s+priority=\S+\s+content=",
        "",
        s,
        flags=re.I,
    )
    s = re.sub(r"\[BRAIN_MEMORY[^\]]*\]", "", s)
    return " ".join(s.split()).strip()


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

    # Isola apenas os passos após o último USER_INPUT (ou SYSTEM_MESSAGE inicial em subagentes)
    last_user_idx = 0
    turn_user_goal = ""
    is_subagent = False
    for idx in range(len(steps) - 1, -1, -1):
        st_type = steps[idx].get("type")
        if st_type == "USER_INPUT":
            last_user_idx = idx
            raw_u = str(steps[idx].get("content") or "")
            m_req = re.search(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", raw_u, flags=re.DOTALL)
            if m_req:
                turn_user_goal = clean_system_envelope(m_req.group(1))[:110]
            elif "<SYSTEM_MESSAGE>" in raw_u or "sender=" in raw_u:
                is_subagent = True
                turn_user_goal = clean_system_envelope(raw_u)[:110]
            else:
                turn_user_goal = clean_system_envelope(raw_u)[:110]
            break
        if st_type == "SYSTEM_MESSAGE" and last_user_idx == 0:
            raw_sys = str(steps[idx].get("content") or "")
            if "sender=" in raw_sys and "sender=system" not in raw_sys:
                last_user_idx = idx
                is_subagent = True
                turn_user_goal = clean_system_envelope(raw_sys)[:110]
                break

    turn_steps = steps[last_user_idx:]
    harvested_count = 0
    modified_files: List[str] = []
    completed_actions: List[str] = []
    detected_errors: List[str] = []
    turn_input_tokens = 0
    turn_cached_tokens = 0
    turn_output_tokens = 0

    for step in turn_steps:
        if step.get("type") == "TOOL_RESPONSE":
            t_out = str(step.get("content") or "")
            err_match = re.search(
                r"((?:SyntaxError|TypeError|ValueError|KeyError|ModuleNotFoundError|ImportError|FileNotFoundError|AssertionError|AttributeError|OperationalError): [^\n]+)",
                t_out,
            )
            if err_match:
                err_txt = err_match.group(1).strip()[:120]
                if err_txt not in detected_errors:
                    detected_errors.append(err_txt)
            continue

        if step.get("type") != "PLANNER_RESPONSE":
            continue

        turn_input_tokens += int(step.get("input_tokens", 0) or 0)
        turn_cached_tokens += int(step.get("cache_read_tokens", 0) or 0)
        turn_output_tokens += int(step.get("output_tokens", 0) or 0)

        # 1. Extrai marcadores explícitos <!-- brain: Topico | Facto --> (suporta setas ->, =>, <, >)
        content = step.get("content", "") or ""
        explicit_matches = re.findall(
            r"<!--\s*brain:\s*([^|\n`{}]{3,85}?)\s*\|\s*(.{6,450}?)\s*-->",
            content,
        )
        for topic, fact in explicit_matches:
            t_clean = topic.strip()
            f_clean = " ".join(fact.strip().split())
            if any(x in t_clean.lower() for x in ("topico", "short topic", "\\s*")):
                continue
            _, is_new = db.store_fact(
                topic=t_clean,
                fact=f_clean,
                workspace=workspace,
                category="explicit_note",
                tags="auto_harvested explicit",
                importance=4,
            )
            if is_new:
                harvested_count += 1

        # 2. Extrai edições de ficheiros (1 memória consolidada por ficheiro para não poluir o grafo)
        tool_calls = step.get("tool_calls") or []
        for tc in tool_calls:
            t_name = tc.get("name", "")
            args = tc.get("args") or {}
            if t_name in ("write_to_file", "replace_file_content", "multi_replace_file_content", "write_file", "edit_file"):
                target_file = str(
                    args.get("TargetFile")
                    or args.get("Path")
                    or args.get("AbsolutePath")
                    or args.get("filePath")
                    or args.get("file_path")
                    or ""
                ).strip('"').replace("\\\\", "/")
                desc = str(args.get("Description") or args.get("Instruction") or "Atualização de código").strip('"')[:160]
                if target_file and "/brain/" not in target_file:
                    bname = os.path.basename(target_file)
                    if bname not in modified_files:
                        modified_files.append(bname)
                    if desc:
                        completed_actions.append(f"{bname}: {desc}")
                        topic_key = f"Ficheiro {bname} ({workspace})"
                        fact_val = f"Path: {target_file} — Última edição: {desc}"
                        with db._connect() as conn:
                            existing = conn.execute(
                                "SELECT id FROM memories WHERE workspace = ? AND topic = ? LIMIT 1;",
                                (workspace.lower(), topic_key),
                            ).fetchone()
                            if existing:
                                conn.execute(
                                    "UPDATE memories SET fact = ?, last_accessed = CURRENT_TIMESTAMP WHERE id = ?;",
                                    (fact_val, existing["id"]),
                                )
                            else:
                                db.store_fact(
                                    topic=topic_key,
                                    fact=fact_val,
                                    workspace=workspace,
                                    category="code_change",
                                    tags=f"{bname} {workspace} file edit",
                                    importance=3,
                                )
                                harvested_count += 1

    # 3. Atualiza o Checkpoint automático do workspace + Auto-Refresh do Scout Map se houve alterações de código
    if detected_errors and modified_files:
        bug_target = modified_files[-1]
        db.store_fact(
            topic=f"Auto-Bugfix: {bug_target} ({workspace})",
            fact=f"Erro resolvido no turno: {detected_errors[-1]} -> Corrigido em {', '.join(modified_files[:3])}.",
            workspace=workspace,
            category="optimization",
            tags=f"bugfix {bug_target} {workspace} erro",
            importance=4,
        )

    if modified_files or completed_actions:
        checkpoint_goal = "" if is_subagent else (turn_user_goal or f"Desenvolvimento ativo em {workspace}")
        db.save_checkpoint(
            workspace=workspace,
            project=workspace,
            goal=checkpoint_goal,
            status="Ativo • Auto-Synced",
            last_completed="; ".join(completed_actions[-3:])[:300],
            key_files=", ".join(modified_files[-6:])[:200],
        )
        try:
            SwarmEngine(db).run_codebase_scout(os.path.dirname(os.path.abspath(__file__)))
        except Exception:
            pass

    if harvested_count > 0:
        try:
            db.run_memory_doctor()
        except Exception:
            pass

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
    try:
        SwarmEngine(db).on_turn_complete(modified_files, completed_actions, conversation_id=conv_id)
        if modified_files or completed_actions or harvested_count > 0:
            OrbitEngine(db).record_handoff(
                from_agent=f"conv:{conv_id[:8]}",
                workspace=workspace,
                summary=turn_user_goal or ("; ".join(completed_actions[-2:]) if completed_actions else "Turno concluído com memória colhida"),
                modified_files=", ".join(modified_files[:5]),
                key_findings="; ".join(completed_actions[-3:])[:240],
                to_scope="next_agent",
            )
    except Exception:
        pass
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
        if ws == "global":
            resolved_ws = resolve_smart_active_workspace(db, "", conv_id)
            if resolved_ws and resolved_ws != "global":
                ws = resolved_ws
        transcript_path = resolve_transcript_path(payload)
        if transcript_path:
            harvest_latest_turn(transcript_path, ws, conv_id, db)
        else:
            try:
                SwarmEngine(db).on_turn_complete([], [], conversation_id=conv_id)
            except Exception:
                pass

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
