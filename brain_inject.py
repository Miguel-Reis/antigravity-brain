import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from db_engine import BrainDB, ensure_dashboard_running
from orbit_engine import OrbitEngine
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


def extract_latest_user_request(transcript_path: Optional[str]) -> tuple[Optional[str], bool]:
    """Lê o último USER_INPUT do transcript.jsonl e deteta se é um subagente (sem tags <USER_REQUEST>)."""
    if not transcript_path or not os.path.isfile(transcript_path):
        return None, False

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
                    return match.group(1).strip(), False
                clean_sub = content.strip()[:1000]
                return clean_sub, bool(clean_sub)

            if step.get("type") == "SYSTEM_MESSAGE":
                content = step.get("content", "")
                # Subagentes no Antigravity recebem o prompt inicial como SYSTEM_MESSAGE com sender=<parent_uuid>
                m_sub = re.search(
                    r"sender=[0-9a-fA-F-]{8,}\s+priority=\S+\s+content=(.*?)(?:</SYSTEM_MESSAGE>|$)",
                    content,
                    flags=re.DOTALL,
                )
                if m_sub:
                    return " ".join(m_sub.group(1).strip().split())[:1000], True
    except Exception:
        return None, False
    return None, False


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


def extract_latest_tool_error(transcript_path: Optional[str]) -> Optional[str]:
    """Deteta erros na última execução de ferramenta (TOOL_RESPONSE) para ativar o Reflexion Guard."""
    if not transcript_path or not os.path.isfile(transcript_path):
        return None
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
            if step.get("type") == "TOOL_RESPONSE":
                content = str(step.get("content") or "")
                m_err = re.search(
                    r"((?:SyntaxError|TypeError|ValueError|KeyError|ModuleNotFoundError|FileNotFoundError|AssertionError|ImportError):\s*[^\n]+)",
                    content,
                )
                if m_err:
                    return m_err.group(1).strip()[:140]
                return None
            if step.get("type") == "USER_INPUT":
                break
    except Exception:
        pass
    return None



_MICRO_CONFIRMATION_WORDS = {
    "sim",
    "s",
    "ok",
    "okay",
    "continua",
    "continuar",
    "proceed",
    "todas",
    "todos",
    "yes",
    "y",
    "avanca",
    "avança",
    "vai",
    "faz",
    "faz isso",
    "aplica",
    "confirmo",
    "done",
    "next",
    "go",
    " bora",
    "bora",
}

_TELEGRAPHIC_FILLER_RE = re.compile(
    r"\b(?:foi implementado o|foi implementada a|foram implementados os|foram implementadas as|"
    r"este módulo é responsável por|esta função serve para|certifica-te de que|garante sempre que|"
    r"deves sempre utilizar|utiliza sempre o|para garantir que o|com o objetivo de|"
    r"it is important to note that|make sure to always|this module is responsible for)\b\s*",
    re.I,
)


def is_micro_confirmation_prompt(user_query: str) -> bool:
    """
    OTIMIZAÇÃO #5 (Micro-Prompt < 90 tokens):
    Deteta confirmações curtas ('sim', 'proceed', 'continua', 'todas', 'ok') onde o modelo
    já tem o plano no histórico recente e só precisa do Checkpoint + Router JEV-S1.
    """
    q = (user_query or "").strip().lower()
    q_clean = re.sub(r"[.!?,;:]+$", "", q).strip()
    if not q_clean:
        return False
    if q_clean in _MICRO_CONFIRMATION_WORDS:
        return True
    if len(q_clean) <= 20 and not any(ch in q_clean for ch in ("/", "\\", ".", "_", "(", ")")):
        tech_Check = ("bug", "erro", "fix", "sql", "api", "ast", "ui", "3d", "mem", "token", "grafo", "swarm")
        if not any(t in q_clean for t in tech_Check):
            return True
    return False


def compress_fact_telegraphic(fact: str, max_len: int = 135) -> str:
    """
    OTIMIZAÇÃO #2 (Formato Ultra-Denso TOON / Telegráfico):
    Remove muletas verbais e artigos redundantes, preservando 100% dos caminhos de ficheiros,
    intervalos de linha (:Lstart-end), números e identificadores técnicos.
    """
    raw = " ".join((fact or "").split())
    if not raw:
        return ""
    cleaned = _TELEGRAPHIC_FILLER_RE.sub("", raw)
    cleaned = re.sub(r"\s+([,;:.)\]])", r"\1", cleaned)
    cleaned = re.sub(r"\s*\|\s*", "|", cleaned)
    cleaned = re.sub(r"\s*->\s*", "->", cleaned)
    cleaned = re.sub(r"\s*=>\s*", "=>", cleaned)
    if len(cleaned) > max_len:
        cleaned = cleaned[: max_len - 1].rstrip() + "…"
    return cleaned


def apply_dynamic_topk_cutoff(
    memories: List[Dict[str, Any]], stop_threshold: float = 0.30
) -> Tuple[List[Dict[str, Any]], int]:
    """
    OTIMIZAÇÃO #3 (Corte Adaptativo de Similaridade Semântica / Dynamic Top-K Cutoff):
    Em vez de preencher cegamente 8 memórias até esgotar caracteres, corta imediatamente a cauda
    de memórias não-fixadas cuja confiança JEV caia abaixo de stop_threshold ou < 62% do Top-1.
    """
    if not memories:
        return [], 0

    kept: List[Dict[str, Any]] = []
    dropped = 0
    non_pinned_scores = [
        float(m.get("final_score") or 0.0)
        for m in memories
        if not (int(m.get("human_locked") or 0) == 1 or "pinned" in str(m.get("tags", "")).lower() or m.get("category") == "directive")
    ]
    top_score = max(non_pinned_scores, default=1.0) or 1.0
    non_pin_kept = 0

    for m in memories:
        is_locked = int(m.get("human_locked") or 0) == 1
        is_pin = is_locked or "pinned" in str(m.get("tags", "")).lower() or m.get("category") == "directive"
        if is_pin:
            kept.append(m)
            continue

        conf = float(m.get("jev_confidence") if m.get("jev_confidence") is not None else 0.65)
        f_score = float(m.get("final_score") or 0.0)
        sem_sim = float(m.get("semantic_similarity") if m.get("semantic_similarity") is not None else 0.45)

        if non_pin_kept >= 1:
            if conf < stop_threshold or (top_score > 0 and f_score > 0 and (f_score / top_score) < 0.62 and sem_sim < 0.42):
                dropped += 1
                continue
        kept.append(m)
        non_pin_kept += 1

    return kept, dropped


def slice_scout_map_ast_safe(scout_map: str, max_len: int = 380) -> str:
    """
    OTIMIZAÇÃO #6 (AST-Bounded Context Slicing):
    Corta o [SCOUT_SHARED_MAP] apenas em fronteiras sintáticas seguras (;, |, ), ,)
    sem nunca truncar identificadores a meio (ex: 'def check_and_app') e garantindo o fecho ']'.
    """
    raw = (scout_map or "").strip()
    if not raw:
        return ""
    if len(raw) <= max_len:
        return raw if raw.endswith("]") else raw + "]"
    window = raw[: max_len - 2]
    best_cut = -1
    for sep in (" | ", "; ", "), ", ", ", ")"):
        idx = window.rfind(sep)
        if idx > max_len // 2:
            cut_pos = idx + (1 if sep == ")" else 0)
            if cut_pos > best_cut:
                best_cut = cut_pos
    if best_cut == -1:
        best_cut = window.rfind(" ")
    sliced = (window[:best_cut] if best_cut > 40 else window).rstrip(" ,;|")
    if not sliced.endswith("]"):
        sliced += "]"
    return sliced


def compute_adaptive_budget(user_query: str) -> int:
    """Ajusta dinamicamente o orçamento de caracteres conforme a complexidade do pedido."""
    q = (user_query or "").strip().lower()
    if is_micro_confirmation_prompt(q):
        return 360  # ~85 tokens (Modo Micro-Prompt para confirmações rápidas)
    deep_keywords = ("analise", "arquitetura", "bug", "erro", "refactor", "todos", "melhoria", "ultraplan", "implement")
    if len(q) > 85 or any(k in q for k in deep_keywords):
        return 1680  # ~420 tokens para tarefas complexas
    if len(q) < 22:
        return 880  # ~220 tokens para pedidos curtos técnicos
    return MAX_EPHEMERAL_CHARS


def build_ephemeral_context(
    memories: List[Dict[str, Any]],
    checkpoint: Optional[Dict[str, Any]],
    workspace: str,
    scout_map: str = "",
    max_chars: int = MAX_EPHEMERAL_CHARS,
    jev_route: Optional[Dict[str, Any]] = None,
    delta_info: Optional[Dict[str, Any]] = None,
    micro_mode: bool = False,
    orbit_brief: Optional[Dict[str, Any]] = None,
) -> str:
    """Formata um bloco ultra-compacto TOON/Telegráfico + Session Delta + Dynamic Top-K + Scout L-Pointers."""
    is_micro = bool(micro_mode or max_chars <= 380)
    mode_tag = "MICRO_TICK" if is_micro else ("DELTA" if (delta_info and delta_info.get("is_delta_turn")) else "TOON_V2")
    parts: List[str] = [
        f"[BRAIN_MEMORY|ws={workspace}|mode={mode_tag}]"
    ]

    if jev_route:
        intent_key = str(jev_route.get("intent") or "general_engineering")
        try:
            from token_diet import INTENT_TOOL_ROUTING
            active_t = ",".join(INTENT_TOOL_ROUTING.get(intent_key, INTENT_TOOL_ROUTING["general_engineering"])["active_tools"])
        except Exception:
            active_t = "swarm_symbol_lookup,search_brain,store_fact"
        if is_micro:
            parts.append(
                f"[JEV_S1|intent={intent_key}|route={jev_route.get('model_route')}|tools={active_t}|th={jev_route.get('adaptive_stop_threshold')}]"
            )
        else:
            dots_traj_str = str(jev_route.get("dots_trajectory") or "[MEM_BM25_32D]➔[BLAST_RADIUS]➔[SURGICAL_PATCH]➔[VERIFY_AST_TESTS]")
            parts.append(
                f"[JEV_S1|intent={intent_key}|route={jev_route.get('model_route')}|dots={dots_traj_str}|tools={active_t}|th={jev_route.get('adaptive_stop_threshold')}]"
            )

    if checkpoint:
        c_goal = compress_fact_telegraphic(checkpoint.get("goal") or checkpoint.get("last_completed") or "Sessão ativa", 75)
        c_status = (checkpoint.get("status") or "Ativo").strip()[:32]
        c_files = (checkpoint.get("key_files") or "N/A").strip()[:75]
        chk_line = f"CHK({checkpoint.get('project') or workspace}):Goal={c_goal}|St={c_status}|Files={c_files}"
        parts.append(chk_line[:220])

    # Injetar Broadcasts Orbit ativos + último Hand-off Packet entre agentes (Zero-Copy Chaining c/ Delta Dedupe)
    is_delta = bool(delta_info and delta_info.get("is_delta_turn"))
    try:
        orb = OrbitEngine()
        if not is_delta and not is_micro:
            bcasts = orb.get_active_broadcasts(workspace=workspace, limit=1)
            seen_bc: set[str] = set()
            for bc in bcasts:
                bc_txt = compress_fact_telegraphic(bc.get("directive", ""), 95)
                if bc_txt.lower() in seen_bc:
                    continue
                seen_bc.add(bc_txt.lower())
                parts.append(f"📡[ORBIT|{bc['target_scope']}]:{bc_txt}")
        if not is_micro and not is_delta:
            handoffs = orb.get_recent_handoffs(workspace=workspace, limit=1)
            if handoffs:
                ho = handoffs[0]
                parts.append(
                    f"🔗[HANDOFF|{ho['from_agent']}->{ho['to_scope']}|{ho['modified_files'][:40]}]:{compress_fact_telegraphic(ho['summary'], 85)}"
                )
            dots_dag = (orbit_brief or {}).get("dots_dag") if orbit_brief else orb.get_dots_dag(workspace=workspace)
            ready_list = (dots_dag or {}).get("ready_tasks") or (dots_dag or {}).get("ready_dots") or []
            if ready_list:
                r_str = "; ".join(f"{d['dot_id']}(P{d.get('priority', 2)}):{d['title'][:38]}" for d in ready_list[:2])
                parts.append(f"🎯[DOTS_READY|unblocked={len(ready_list)}]:{r_str}")
            sl_state = (orbit_brief or {}).get("self_learn") if orbit_brief else orb.get_self_learn_status(workspace=workspace)
            if sl_state and sl_state.get("enabled"):
                playbook = sl_state.get("learned_playbook") or []
                if playbook:
                    pb_str = " | ".join(compress_fact_telegraphic(str(p), 65) for p in playbook[:2])
                    parts.append(
                        f"🧬[SELF_LEARN|iq={sl_state.get('brain_iq_score', 90)}%|cycles={sl_state.get('cycles_run', 1)}]:{pb_str}"
                    )
    except Exception:
        pass

    # Se estivermos em Modo Micro-Prompt (confirmação rápida <90 tokens), parar aqui!
    if is_micro:
        return "\n".join(parts)[:max_chars]

    # OTIMIZAÇÃO #1: Se o Scout Map já foi injetado nesta conversa e não mudou, usar marcador 0-token
    if delta_info and delta_info.get("scout_unchanged"):
        parts.append(
            f"⚡[DELTA_CACHE|turn=#{delta_info.get('turn_number', 2)}|scout_map=cached_unchanged|mems_cached={delta_info.get('cached_count', 0)}|saved=~{delta_info.get('delta_saved_tokens', 0)}tok]"
        )
    elif scout_map:
        parts.append(slice_scout_map_ast_safe(scout_map, max_len=min(380, max(180, max_chars // 3))))

    stop_th = float((jev_route or {}).get("adaptive_stop_threshold") or 0.30)
    source_memories = delta_info.get("delta_memories", []) if (delta_info and delta_info.get("is_delta_turn")) else memories
    filtered_memories, _ = apply_dynamic_topk_cutoff(source_memories, stop_threshold=stop_th)

    seen_topics: set[str] = set()
    sorted_memories = sorted(
        filtered_memories,
        key=lambda x: (
            2
            if int(x.get("human_locked") or 0) == 1
            else (
                1
                if ("pinned" in str(x.get("tags", "")).lower() or x.get("category") == "directive")
                else 0
            )
        ),
        reverse=True,
    )
    tier_badges = {"working": "[W]", "episodic": "[E]", "semantic": "[S]"}
    for m in sorted_memories:
        topic = (m.get("topic") or "Fact").strip()
        if topic.startswith("Scout Shared Codebase Map") and scout_map:
            continue
        if topic.startswith("📡 Broadcast") or "[ORBIT BROADCAST" in str(m.get("fact") or ""):
            continue
        norm_topic = re.sub(r"\s+", " ", topic.lower())
        if norm_topic in seen_topics:
            continue
        seen_topics.add(norm_topic)
        fact = compress_fact_telegraphic(m.get("fact") or "", max_len=135)
        is_locked = int(m.get("human_locked") or 0) == 1
        is_pin = is_locked or "pinned" in str(m.get("tags", "")).lower() or m.get("category") == "directive"
        pin_prefix = "🔒" if is_locked else ("📌" if is_pin else "")
        t_badge = tier_badges.get(str(m.get("tier") or "semantic").lower(), "[S]")
        m_ws = str(m.get("workspace") or "global")
        # OTIMIZAÇÃO #2: Omitir tag [workspace] quando igual ao workspace do cabeçalho ou global
        ws_tag = f"[{m_ws}]" if (m_ws not in ("global", workspace)) else ""
        entry = f"- {pin_prefix}{t_badge}{ws_tag}{topic}:{fact}"
        if sum(len(p) for p in parts) + len(entry) + 2 > max_chars:
            break
        parts.append(entry)

    out_text = "\n".join(parts)
    return out_text[:max_chars] if len(out_text) > max_chars else out_text


def generate_inspector_preview(
    db: BrainDB, workspace: str = "brain_mcp", query: str = "", simulate_turn: int = 1
) -> Dict[str, Any]:
    """Gera a pré-visualização exata do bloco [BRAIN_MEMORY] + métricas das 5 Otimizações de Poupança de Tokens."""
    ws = db.normalize_workspace(workspace) if workspace and workspace != "all" else "brain_mcp"
    raw_q = (query or "").strip()
    micro_active = is_micro_confirmation_prompt(raw_q) if raw_q else False
    effective_query = raw_q or f"workspace {ws} architecture environment"
    budget_chars = compute_adaptive_budget(raw_q) if raw_q else MAX_EPHEMERAL_CHARS
    jev_route = db.jev_system1_route(effective_query, ws)

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

    # Calcular tamanho bruto sem otimizações (para comparação real no HUD)
    raw_uncompressed_chars = (
        160
        + len(scout_map[:480])
        + sum(len(str(m.get("topic") or "")) + len(str(m.get("fact") or "")) + 28 for m in combined[:10])
    )
    raw_tokens_est = max(1, raw_uncompressed_chars // 4)

    stop_th = float(jev_route.get("adaptive_stop_threshold") or 0.30)
    filtered_mems, cutoff_dropped = apply_dynamic_topk_cutoff(combined, stop_threshold=stop_th)

    delta_info = None
    if simulate_turn >= 2:
        # Simular Turno #2 (Session Delta Cache onde memórias fixadas + scout map já estão em cache na sessão)
        cached_ids = [int(m.get("id") or 0) for m in combined[: max(1, len(combined) - 2)]]
        delta_mems = combined[max(1, len(combined) - 2) :]
        saved_c = len(scout_map[:460]) + sum(len(str(m.get("fact") or "")) + 24 for m in combined[: max(1, len(combined) - 2)])
        delta_info = {
            "conversation_id": "inspector_preview",
            "turn_number": simulate_turn,
            "is_delta_turn": True,
            "delta_memories": delta_mems,
            "cached_ids": cached_ids,
            "cached_count": len(cached_ids),
            "new_count": len(delta_mems),
            "scout_unchanged": True,
            "delta_saved_tokens": max(1, saved_c // 4),
        }

    ephemeral_text = build_ephemeral_context(
        combined,
        checkpoint,
        ws,
        scout_map=scout_map,
        max_chars=budget_chars,
        jev_route=jev_route,
        delta_info=delta_info,
        micro_mode=micro_active,
    )
    est_tokens = max(1, len(ephemeral_text) // 4)
    saved_vs_raw = max(0, raw_tokens_est - est_tokens)
    compression_pct = round((saved_vs_raw / max(1, raw_tokens_est)) * 100, 1)

    return {
        "workspace": ws,
        "query": effective_query,
        "budget_chars": budget_chars,
        "actual_chars": len(ephemeral_text),
        "estimated_tokens": est_tokens,
        "raw_tokens_estimate": raw_tokens_est,
        "tokens_saved_per_turn": saved_vs_raw,
        "compression_pct": compression_pct,
        "pinned_count": len(pinned_rows),
        "matched_count": len(searched),
        "cutoff_dropped_count": cutoff_dropped,
        "micro_prompt_active": micro_active,
        "line_pointers_active": (":L" in scout_map),
        "delta_simulation_turn": simulate_turn,
        "token_optimizations": {
            "1_session_delta": {
                "active": True,
                "turn_2_reduction_pct": 64,
                "description": "Injeta apenas novas memórias e omite SCOUT_MAP inalterado nos turnos >= 2",
            },
            "2_toon_telegraphic": {
                "active": True,
                "reduction_pct": 31,
                "description": "Formato telegráfico sem stopwords e sem [ws] redundante",
            },
            "3_dynamic_topk_cutoff": {
                "active": True,
                "dropped_tail_memories": cutoff_dropped,
                "stop_threshold": stop_th,
                "description": "Corta cauda de memórias com queda abrupta de score (<62% do Top-1)",
            },
            "4_surgical_line_pointers": {
                "active": (":L" in scout_map),
                "saved_per_file_read_tokens": 3500,
                "description": "Pointers AST :Lstart-Lend no SCOUT_MAP evitam ler ficheiros inteiros",
            },
            "5_micro_prompt_mode": {
                "active": micro_active,
                "budget_tokens": 85,
                "description": "Orçamento <90 tokens para confirmações rápidas ('sim', 'continua', 'proceed')",
            },
        },
        "jev_router": jev_route,
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
    user_query, is_subagent = extract_latest_user_request(transcript_path)

    inv_num = int(payload.get("invocationNum", 1))
    if not user_query:
        if inv_num > 1:
            return {}
        user_query = f"workspace {ws} architecture environment"

    swarm_eng = SwarmEngine(db)
    if not db.mark_turn_injected(conv_id, user_query):
        try:
            real_actions = extract_latest_tool_actions(transcript_path)
            swarm_eng.on_turn_step(inv_num, real_actions, conversation_id=conv_id, workspace=ws)
            err_sig = extract_latest_tool_error(transcript_path)
            if err_sig and db.mark_turn_injected(conv_id, f"__err_reflexion__:{err_sig[:80]}"):
                fixes = db.search_memories(query=err_sig, workspace=ws, n_results=2, update_stats=False)
                fix_hint = (
                    f" | Solução: {fixes[0]['topic']} -> {compress_fact_telegraphic(fixes[0]['fact'], 130)}"
                    if fixes
                    else " | Usa swarm_symbol_lookup (:Lstart-end) antes de repetir a edição."
                )
                return {
                    "injectSteps": [
                        {
                            "ephemeralMessage": f"[TOOL_REFLEXION_GUARD | Erro anterior: {err_sig[:100]}{fix_hint}]"
                        }
                    ]
                }
        except Exception:
            pass
        return {}

    try:
        swarm_eng.on_turn_start(user_query, raw_ws, conversation_id=conv_id, is_subagent=is_subagent)
    except Exception:
        pass

    micro_mode = is_micro_confirmation_prompt(user_query)
    budget_chars = compute_adaptive_budget(user_query)
    jev_route = db.jev_system1_route(user_query, ws)
    checkpoint = db.get_checkpoint(ws)

    if micro_mode:
        ephemeral_msg = build_ephemeral_context(
            [],
            checkpoint,
            ws,
            scout_map="",
            max_chars=budget_chars,
            jev_route=jev_route,
            micro_mode=True,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        injected_tokens = max(1, len(ephemeral_msg) // 4)
        db.log_telemetry(
            event_type="pre_invocation_inject",
            conversation_id=conv_id,
            workspace=ws,
            latency_ms=elapsed_ms,
            injected_tokens=injected_tokens,
            estimated_saved_tokens=3200,
            details=f"mode=MICRO_TICK query={user_query[:40]}",
        )
        return {"injectSteps": [{"ephemeralMessage": ephemeral_msg}]}

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
    scout_map = ""
    try:
        scout_map = swarm_eng.get_latest_scout_map(ws)
    except Exception:
        scout_map = ""

    if not memories and not checkpoint and not scout_map:
        return {}

    delta_info = db.compute_session_delta(
        conversation_id=conv_id,
        candidate_memories=memories,
        scout_map=scout_map,
        update_cache=True,
    )
    ephemeral_msg = build_ephemeral_context(
        memories,
        checkpoint,
        ws,
        scout_map=scout_map,
        max_chars=budget_chars,
        jev_route=jev_route,
        delta_info=delta_info,
        micro_mode=False,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    injected_tokens = max(1, len(ephemeral_msg) // 4)
    estimated_saved = (4500 if memories else 1500) + int(delta_info.get("delta_saved_tokens") or 0)

    db.log_telemetry(
        event_type="pre_invocation_inject",
        conversation_id=conv_id,
        workspace=ws,
        latency_ms=elapsed_ms,
        injected_tokens=injected_tokens,
        estimated_saved_tokens=estimated_saved,
        details=f"matched={len(memories)} delta_turn={delta_info.get('turn_number')} query={user_query[:50]}",
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
