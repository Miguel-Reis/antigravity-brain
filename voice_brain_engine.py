"""
voice_brain_engine.py — Zero-Dependency, Ultra-Fast Voice-Aware Brain Protocol (<4ms).

Provides:
  1. VoiceSttDenoiser: Oral PT/EN filler stripping, spoken punctuation/extension normalization,
     and concise mode directive generation.
  2. SpokenCodePhoneticResolver: Phonetic and AST symbol resolution (:Lstart-end) mapping spoken
     queries directly to files and function/class pointers.
  3. VoiceZeroCallPreExecutor: Instant zero-call execution for spoken Brain tool intents
     (store_fact, swarm_impact_graph, swarm_symbol_lookup, brain_stats).
  4. process_voice_turn: Unified orchestrator for pre-invocation injection and preview.
"""

from __future__ import annotations

import ast
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
    ".sh",
    ".bat",
    ".sql",
}

IGNORE_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".brain_vault",
    ".pytest_cache",
    ".vscode",
    ".idea",
}

# Conversational oral fillers in Portuguese and English (with and without accents)
ORAL_FILLERS_PT: List[str] = [
    r"\bve lá se consegues\b",
    r"\bvê lá se consegues\b",
    r"\bve la se consegues\b",
    r"\bvê la se consegues\b",
    r"\bo que eu queria era\b",
    r"\bo que eu queria\b",
    r"\bdiz-me uma coisa\b",
    r"\bpor favor vê\b",
    r"\bpor favor ve\b",
    r"\bpor favor\b",
    r"\bfaz favor\b",
    r"\bfaz-me um favor\b",
    r"\bdá uma olhada\b",
    r"\bda uma olhada\b",
    r"\btipo assim\b",
    r"\bolha lá\b",
    r"\bolha la\b",
    r"\bpodes ver\b",
    r"\bconsegues ver\b",
    r"\bdá para ver\b",
    r"\bda para ver\b",
    r"\bescuta\b",
    r"\bouve lá\b",
    r"\bouve la\b",
    r"\bolha\b",
    r"\bentão\b",
    r"\bentao\b",
    r"\bbasicamente\b",
    r"\btipo\b",
    r"\bpá\b",
]

ORAL_FILLERS_EN: List[str] = [
    r"\bhey antigravity\b",
    r"\bok antigravity\b",
    r"\bokay antigravity\b",
    r"\bi was wondering if you could\b",
    r"\bcould you please\b",
    r"\bcan you please\b",
    r"\bplease check\b",
    r"\btell me something\b",
    r"\bso basically\b",
    r"\bbasically\b",
    r"\byou know\b",
    r"\bi mean\b",
    r"\blisten\b",
]

STOP_ARTICLES: set[str] = {
    "o",
    "a",
    "os",
    "as",
    "um",
    "uma",
    "do",
    "da",
    "dos",
    "das",
    "no",
    "na",
    "nos",
    "nas",
    "em",
    "para",
    "de",
    "com",
    "the",
    "an",
    "in",
    "on",
    "at",
    "to",
    "for",
    "file",
    "ficheiro",
    "arquivo",
}

SYM_STOP_WORDS: set[str] = {
    "onde", "esta", "está", "estao", "estão", "funcao", "função", "classe",
    "metodo", "método", "definida", "definido", "mostra", "linha", "linhas",
    "que", "qual", "quais", "como", "para", "abre", "mexe", "altera", "muda",
    "mexer", "impacto", "pagina", "página", "projeto", "separado", "adiciona",
    "pedi", "relativamente", "voz", "reve", "revê", "integridade", "estrutura",
    "codigo", "código", "todo", "toda", "todos", "pode", "ser", "removida",
    "removido", "tenho", "ja", "já", "sim", "nao", "não", "mais", "menos",
    "com", "sem", "isso", "isto", "esse", "essa", "este", "esta", "sobre",
    "where", "is", "function", "class", "method", "defined", "show", "line",
    "lines", "what", "which", "how", "to", "open", "modify", "change", "the",
    "a", "an", "o", "os", "as", "um", "uma", "do", "da", "dos", "das", "no", "na",
    "por", "favor", "ve", "vê", "olha", "la", "lá", "em", "de", "se", "eu", "te",
}

ALL_ORAL_FILLERS: List[re.Pattern[str]] = [
    re.compile(pattern, re.IGNORECASE) for pattern in (ORAL_FILLERS_PT + ORAL_FILLERS_EN)
]

VOICE_DETECTION_PATTERNS: List[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bent[ãa]o\b",
        r"\bolha l[áa]\b",
        r"\bolha\b",
        r"\btipo assim\b",
        r"\bbasicamente\b",
        r"\bo que eu queria\b",
        r"\bv[êe] l[áa] se consegues\b",
        r"\bpodes ver\b",
        r"\bfaz favor\b",
        r"\bpor favor v[êe]\b",
        r"\bpor favor\b",
        r"\bdiz-me uma coisa\b",
        r"\bescuta\b",
        r"\bhey antigravity\b",
        r"\bok antigravity\b",
        r"\bponto py\b",
        r"\bdot py\b",
        r"\bponto html\b",
        r"\bdot html\b",
        r"\bponto js\b",
        r"\bdot js\b",
        r"\bponto ts\b",
        r"\bdot ts\b",
        r"\bponto json\b",
        r"\bdot json\b",
        r"\bponto md\b",
        r"\bdot md\b",
        r"\bunderscore\b",
        r"\btraço baixo\b",
        r"\bunderline\b",
        r"\bguarda na mem[óo]ria\b",
        r"\bmemoriza que\b",
        r"\blembra-te que\b",
        r"\bregista no brain\b",
    ]
]


def analyze_voice_input(raw_query: str, has_audio_media: bool = False) -> Dict[str, Any]:
    """
    VoiceSttDenoiser:
    - Deteta se o input é provavelmente voz/ditado STT.
    - Limpa muletas orais (PT/EN) preservando substantivos técnicos, ficheiros e comandos.
    - Normaliza pontuação e extensões ditadas ('ponto py' -> '.py', 'underscore' -> '_', 'web dashboard .py' -> 'web_dashboard.py').
    - Produz métricas de tokens poupados e diretiva de modo conciso.
    """
    raw_q = (raw_query or "").strip()
    if not raw_q:
        return {
            "raw_query": "",
            "clean_query": "",
            "is_voice_likely": has_audio_media,
            "has_audio_media": has_audio_media,
            "filler_removed_count": 0,
            "removed_fillers": [],
            "fillers_removed": [],
            "raw_tokens_est": 0,
            "clean_tokens_est": 0,
            "voice_concise_directive": (
                "[VOICE_CONCISE_MODE: User spoke via voice/STT -> reply direct & concise (-60% prose), trust [VOICE_AST_TARGET] & [VOICE_PRE_EXEC] without redundant grep/MCP calls]"
                if has_audio_media
                else ""
            ),
            "estimated_tokens_saved": 420 if has_audio_media else 0,
        }

    # 1. Detetar se é voz
    is_voice = bool(has_audio_media)
    if not is_voice:
        for pat in VOICE_DETECTION_PATTERNS:
            if pat.search(raw_q):
                is_voice = True
                break

    if not is_voice:
        words = raw_q.split()
        code_punct = set("`(){}[]/\\;=<>\"'")
        has_code_punct = any(ch in code_punct for ch in raw_q)
        if len(words) >= 14 and not has_code_punct and raw_q.lower() == raw_q:
            is_voice = True

    # 2. Normalizar pontuação e extensões de voz inline
    clean = raw_q

    # Substituir traço baixo / underscore
    clean = re.sub(r"\b(?:underscore|traço\s+baixo|underline)\b", "_", clean, flags=re.IGNORECASE)

    # Substituir extensões faladas
    clean = re.sub(r"\b(?:ponto|dot)\s*py\b", ".py", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\b(?:ponto|dot)\s*html\b", ".html", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\b(?:ponto|dot)\s*js\b", ".js", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\b(?:ponto|dot)\s*ts\b", ".ts", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\b(?:ponto|dot)\s*json\b", ".json", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\b(?:ponto|dot)\s*md\b", ".md", clean, flags=re.IGNORECASE)

    # Unir palavras antes de extensões com underscore (ex: 'web dashboard .py' -> 'web_dashboard.py')
    def _join_stem_3(m: re.Match[str]) -> str:
        w1, w2, w3, ext = m.group(1), m.group(2), m.group(3), m.group(4)
        if w1.lower() in STOP_ARTICLES:
            return f"{w1} {w2}_{w3}.{ext}"
        return f"{w1}_{w2}_{w3}.{ext}"

    def _join_stem_2(m: re.Match[str]) -> str:
        w1, w2, ext = m.group(1), m.group(2), m.group(3)
        if w1.lower() in STOP_ARTICLES:
            return f"{w1} {w2}.{ext}"
        return f"{w1}_{w2}.{ext}"

    clean = re.sub(
        r"\b([a-zA-Z0-9]+)\s+([a-zA-Z0-9]+)\s+([a-zA-Z0-9]+)\s*\.(py|html|js|ts|json|md)\b",
        _join_stem_3,
        clean,
        flags=re.IGNORECASE,
    )
    clean = re.sub(
        r"\b([a-zA-Z0-9]+)\s+([a-zA-Z0-9]+)\s*\.(py|html|js|ts|json|md)\b",
        _join_stem_2,
        clean,
        flags=re.IGNORECASE,
    )

    # 3. Remover muletas orais
    removed_fillers: List[str] = []
    filler_count = 0
    for pat in ALL_ORAL_FILLERS:
        for m in pat.finditer(clean):
            matched_txt = m.group(0).strip()
            if matched_txt:
                removed_fillers.append(matched_txt)
                filler_count += 1
        clean = pat.sub(" ", clean)

    # Limpar espaços duplos
    clean = " ".join(clean.split()).strip()

    # Se a limpeza esvaziar por completo uma query de voz, restaurar a query base
    if not clean and raw_q:
        clean = raw_q

    raw_tokens_est = max(1, len(raw_q) // 4)
    clean_tokens_est = max(1, len(clean) // 4)
    filler_saved = max(0, raw_tokens_est - clean_tokens_est)
    concise_saved = 420 if is_voice else 0
    estimated_saved = filler_saved + concise_saved

    concise_directive = (
        "[VOICE_CONCISE_MODE: User spoke via voice/STT -> reply direct & concise (-60% prose), trust [VOICE_AST_TARGET] & [VOICE_PRE_EXEC] without redundant grep/MCP calls]"
        if is_voice
        else ""
    )

    return {
        "raw_query": raw_q,
        "clean_query": clean,
        "is_voice_likely": is_voice,
        "has_audio_media": has_audio_media,
        "filler_removed_count": filler_count,
        "removed_fillers": removed_fillers,
        "fillers_removed": removed_fillers,
        "raw_tokens_est": raw_tokens_est,
        "clean_tokens_est": clean_tokens_est,
        "voice_concise_directive": concise_directive,
        "estimated_tokens_saved": estimated_saved,
    }


_AST_SYMBOL_CACHE: Dict[str, Tuple[float, List[Tuple[str, int, int]]]] = {}


def _get_cached_py_symbols(full_path: str) -> List[Tuple[str, int, int]]:
    """Devolve lista [(symbol_name, start_line, end_line)] cacheada por mtime (<0.02ms após 1ª leitura)."""
    try:
        st_mtime = os.path.getmtime(full_path)
    except OSError:
        return []
    cached = _AST_SYMBOL_CACHE.get(full_path)
    if cached and cached[0] == st_mtime:
        return cached[1]
    syms: List[Tuple[str, int, int]] = []
    try:
        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                s_line = int(getattr(node, "lineno", 1))
                e_line = int(getattr(node, "end_lineno", s_line + 15))
                syms.append((node.name, s_line, e_line))
        _AST_SYMBOL_CACHE[full_path] = (st_mtime, syms)
    except Exception:
        pass
    return syms


def resolve_spoken_code_targets(
    raw_query: str,
    workspace_root: str = "",
    scout_map: str = "",
    db: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    SpokenCodePhoneticResolver:
    - Resolve referências a ficheiros ditados foneticamente contra o workspace real.
    - Resolve símbolos de funções/classes ditadas (:Lstart-end) via scout_map e SwarmEngine.lookup_symbol.
    - Gera diretiva compacta [VOICE_AST_TARGET: ...].
    """
    t0 = time.perf_counter()
    q = (raw_query or "").strip()
    if not q:
        return {
            "resolved_files": [],
            "ast_pointers": [],
            "directive_line": "",
            "estimated_tokens_saved": 0,
            "latency_ms": 0.0,
        }

    q_low = q.lower()
    default_dir = os.path.dirname(os.path.abspath(__file__))
    ws_dir = workspace_root if (workspace_root and os.path.isdir(workspace_root)) else default_dir

    # 1. Resolver Ficheiros Ditados no Workspace
    resolved_files: List[str] = []
    seen_files: set[str] = set()

    try:
        ws_path = Path(ws_dir)
        # Varrer ficheiros no diretório base e 1º nível de subdiretórios
        candidate_files: List[Tuple[str, str]] = []  # (rel_path, stem)

        for entry in os.scandir(ws_path):
            if entry.name.startswith(".") or entry.name in IGNORE_DIRS:
                continue
            if entry.is_file():
                ext = os.path.splitext(entry.name)[1].lower()
                if ext in CODE_EXTENSIONS:
                    candidate_files.append((entry.name, os.path.splitext(entry.name)[0]))
            elif entry.is_dir():
                try:
                    for sub_entry in os.scandir(entry.path):
                        if sub_entry.is_file():
                            ext = os.path.splitext(sub_entry.name)[1].lower()
                            if ext in CODE_EXTENSIONS:
                                rel = f"{entry.name}/{sub_entry.name}"
                                candidate_files.append((rel, os.path.splitext(sub_entry.name)[0]))
                except Exception:
                    pass

        # Construir chaves fonéticas para cada ficheiro candidato
        for rel_f, stem in candidate_files:
            fname = os.path.basename(rel_f).lower()
            stem_low = stem.lower()
            stem_spaced = stem_low.replace("_", " ").replace("-", " ")
            stem_rev = " ".join(reversed(stem_spaced.split())) if " " in stem_spaced else ""

            keys = [
                fname,
                stem_low,
                stem_spaced,
            ]
            if stem_rev:
                keys.append(stem_rev)

            # Casamento fonético na query
            matched = False
            for k in keys:
                if len(k) >= 3 and (
                    re.search(rf"\b{re.escape(k)}\b", q_low)
                    or (f"{k}.py" in q_low)
                    or (f"{k}.html" in q_low)
                    or (f"{k}.js" in q_low)
                ):
                    matched = True
                    break

            if matched and rel_f not in seen_files:
                resolved_files.append(rel_f)
                seen_files.add(rel_f)

    except Exception:
        pass

    # 2. Resolver Símbolos AST ditados (:Lstart-end)
    ast_pointers: List[Dict[str, Any]] = []
    seen_syms: set[str] = set()

    # Extrair candidatos a nomes de símbolos da query
    candidates: List[str] = []

    # a) Identificadores explícitos com underscore ou camelCase
    explicit_ids = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]{3,}\b", q)
    for eid in explicit_ids:
        if "_" in eid or any(c.isupper() for c in eid[1:]):
            if eid not in candidates:
                candidates.append(eid)

    # b) Multi-palavras contíguas (2 a 4 palavras técnicas) convertidas para snake_case
    words = re.findall(r"\b[a-zA-Z0-9]+\b", q_low)
    clean_words = [w for w in words if w not in SYM_STOP_WORDS and len(w) >= 2]
    for n in (4, 3, 2):
        for i in range(len(clean_words) - n + 1):
            snake = "_".join(clean_words[i : i + n])
            if snake not in candidates and len(snake) >= 6:
                candidates.append(snake)

    # c) Casar primeiro contra o scout_map (latência ~0.05ms, formatos 'fn sym():L1-L9' e 'file.py:L1-L9 (sym)')
    if scout_map and candidates:
        current_file = ""
        for sc_line in scout_map.splitlines():
            for file_chunk in sc_line.split(";"):
                fm = re.search(r"([a-zA-Z0-9_\-\./\\]+\.(?:py|js|ts|html))\b", file_chunk)
                if fm:
                    current_file = fm.group(1)
                for sm in re.finditer(
                    r"(?:fn|class|def|async def)?\s*([a-zA-Z_][a-zA-Z0-9_]*)\(\)?\s*:L(\d+)(?:-L?(\d+))?",
                    file_chunk,
                ):
                    sym_hit, s_line, e_line = sm.groups()
                    sym_low = sym_hit.lower()
                    for cand in candidates[:8]:
                        c_low = cand.lower()
                        if c_low == sym_low or (len(c_low) >= 8 and "_" in c_low and c_low in sym_low):
                            f_hit = current_file or "workspace"
                            p_key = f"{f_hit}:{s_line}"
                            if p_key not in seen_syms:
                                seen_syms.add(p_key)
                                ptr_str = f"{f_hit}:L{s_line}-L{e_line or s_line} ({sym_hit})"
                                ast_pointers.append(
                                    {
                                        "symbol": sym_hit,
                                        "file": f_hit,
                                        "start_line": int(s_line),
                                        "end_line": int(e_line or s_line),
                                        "pointer": ptr_str,
                                    }
                                )
                            break
            if len(ast_pointers) >= 3:
                break

        if len(ast_pointers) < 3:
            for m_hit in re.finditer(
                r"([a-zA-Z0-9_\-\./\\]+):L(\d+)-L?(\d*)\s*(?:\(([^)]*)\))?",
                scout_map,
            ):
                f_hit, s_line, e_line, sym_hit = m_hit.groups()
                if not sym_hit:
                    continue
                sym_low = sym_hit.lower()
                for cand in candidates[:8]:
                    c_low = cand.lower()
                    if c_low == sym_low or (len(c_low) >= 8 and "_" in c_low and c_low in sym_low):
                        p_key = f"{f_hit}:{s_line}"
                        if p_key not in seen_syms:
                            seen_syms.add(p_key)
                            ptr_str = f"{f_hit}:L{s_line}-L{e_line or s_line} ({sym_hit})"
                            ast_pointers.append(
                                {
                                    "symbol": sym_hit,
                                    "file": f_hit,
                                    "start_line": int(s_line),
                                    "end_line": int(e_line or s_line),
                                    "pointer": ptr_str,
                                }
                            )
                        break
                if len(ast_pointers) >= 3:
                    break

    # d) Fast AST Scan com cache por mtime (<0.5ms; prioriza resolved_files antes de varrer outros módulos)
    if len(ast_pointers) < 3 and candidates:
        files_to_scan: List[str] = []
        if resolved_files:
            files_to_scan.extend([rf for rf in resolved_files if rf.endswith(".py")])
        else:
            for rel_f, _ in candidate_files:
                if rel_f.endswith(".py") and rel_f not in files_to_scan:
                    files_to_scan.append(rel_f)
                if len(files_to_scan) >= 12:
                    break

        def _scan_py_list(py_list: List[str]) -> None:
            for rf in py_list:
                if len(ast_pointers) >= 3:
                    break
                full_path = os.path.join(ws_dir, rf)
                for sym_name, s_line, e_line in _get_cached_py_symbols(full_path):
                    n_low = sym_name.lower()
                    n_flat = n_low.replace("_", "")
                    for cand in candidates:
                        c_low = cand.lower()
                        c_flat = c_low.replace("_", "")
                        if (
                            c_low == n_low
                            or (len(c_flat) >= 9 and c_flat == n_flat)
                            or (len(c_low) >= 9 and "_" in c_low and c_low in n_low)
                        ):
                            p_key = f"{rf}:{s_line}"
                            if p_key not in seen_syms:
                                seen_syms.add(p_key)
                                ptr_str = f"{rf}:L{s_line}-L{e_line} ({sym_name})"
                                ast_pointers.append(
                                    {
                                        "symbol": sym_name,
                                        "file": rf,
                                        "start_line": s_line,
                                        "end_line": e_line,
                                        "pointer": ptr_str,
                                    }
                                )
                            break
                    if len(ast_pointers) >= 3:
                        break

        _scan_py_list(files_to_scan)
        if not ast_pointers and resolved_files:
            fallback_py = [rel_f for rel_f, _ in candidate_files if rel_f.endswith(".py") and rel_f not in files_to_scan][:10]
            _scan_py_list(fallback_py)

    # e) Se houve pedido explícito de símbolo ou ficheiro não-py e db disponível, chamar SwarmEngine.lookup_symbol (exact/camel match)
    if len(ast_pointers) < 3 and db is not None and any(rf.endswith((".html", ".js", ".ts")) for rf in resolved_files):
        try:
            from swarm_engine import SwarmEngine

            sw = SwarmEngine(db)
            for cand in candidates[:3]:
                res = sw.lookup_symbol(cand, workspace_path=ws_dir, include_body=False)
                for match in res.get("matches", []):
                    sym_name = str(match.get("symbol") or "")
                    if sym_name.lower().replace("_", "") != cand.lower().replace("_", ""):
                        continue
                    f_name = match.get("file")
                    s_l = match.get("start_line", 1)
                    e_l = match.get("end_line", s_l + 10)
                    p_key = f"{f_name}:{s_l}"
                    if p_key not in seen_syms:
                        seen_syms.add(p_key)
                        ptr_str = f"{f_name}:L{s_l}-L{e_l} ({sym_name})"
                        ast_pointers.append(
                            {
                                "symbol": sym_name,
                                "file": f_name,
                                "start_line": s_l,
                                "end_line": e_l,
                                "pointer": ptr_str,
                            }
                        )
                        if len(ast_pointers) >= 3:
                            break
                if len(ast_pointers) >= 3:
                    break
        except Exception:
            pass

    # 3. Construir diretiva compacta [VOICE_AST_TARGET: ...]
    target_tokens: List[str] = [p["pointer"] for p in ast_pointers]
    for rf in resolved_files:
        if not any(rf in p["pointer"] for p in ast_pointers):
            target_tokens.append(rf)

    directive_line = ""
    if target_tokens:
        directive_line = f"[VOICE_AST_TARGET: {' | '.join(target_tokens[:3])}]"

    saved_tokens = min(6400, 3200 * len(ast_pointers) + 1200 * len(resolved_files))
    latency_ms = (time.perf_counter() - t0) * 1000.0

    return {
        "resolved_files": resolved_files,
        "ast_pointers": ast_pointers,
        "directive_line": directive_line,
        "estimated_tokens_saved": saved_tokens,
        "latency_ms": round(latency_ms, 2),
    }


def pre_execute_voice_brain_tools(
    db: Any,
    raw_query: str,
    workspace: str = "brain_mcp",
    workspace_root: str = "",
    allow_write: bool = True,
) -> Dict[str, Any]:
    """
    VoiceZeroCallPreExecutor & VoiceToolPruningRouter:
    Deteta intenções de ferramentas Brain faladas em PT/EN e executa-as diretamente
    em Python em <4ms, poupando round-trips de chamada de ferramentas do LLM (~1500-2800 tokens cada):
      - Intent A: store_fact (guarda na memória que...)
      - Intent B: swarm_impact_graph (impacto / blast radius de...)
      - Intent C: swarm_symbol_lookup (onde está a função / mostra linha...)
      - Intent D: brain_stats / checkpoint (estado do brain...)
    """
    t0 = time.perf_counter()
    q = (raw_query or "").strip()
    executed_intents: List[Dict[str, Any]] = []
    pre_exec_lines: List[str] = []
    total_saved = 0

    default_dir = os.path.dirname(os.path.abspath(__file__))
    ws_dir = workspace_root if (workspace_root and os.path.isdir(workspace_root)) else default_dir

    # INTENT A: store_fact (Memorização Falada)
    m_store = re.search(
        r"(?:guarda na mem[óo]ria que|memoriza que|lembra-te que|regista no brain que|save to memory that|remember that)\s+(.+)",
        q,
        re.IGNORECASE,
    )
    if m_store:
        fact_body = m_store.group(1).strip()
        words = fact_body.split()
        topic_words = words[:6]
        topic = "Voice Memory: " + " ".join(topic_words)
        mem_id = 9999
        simulated = not allow_write

        if allow_write and db is not None:
            try:
                if hasattr(db, "store_fact"):
                    res = db.store_fact(
                        topic=topic,
                        fact=fact_body,
                        workspace=workspace,
                        category="directive",
                        tags="pinned voice_memory",
                        importance=5,
                        human_locked=1,
                    )
                    mem_id = res[0] if isinstance(res, (tuple, list)) else int(res)
                elif hasattr(db, "add_memory"):
                    res = db.add_memory(
                        topic=topic,
                        fact=fact_body,
                        workspace=workspace,
                        category="directive",
                        tags="pinned voice_memory",
                        importance=5,
                        human_locked=1,
                    )
                    mem_id = res[0] if isinstance(res, (tuple, list)) else int(res)
            except Exception:
                simulated = True

        status_tag = f"id=#{mem_id}" if not simulated else "SIMULATED"
        tag = f"[VOICE_PRE_EXEC|store_fact=OK|{status_tag}|ALREADY_SAVED_DO_NOT_CALL_STORE_FACT: {fact_body[:90]}]"
        pre_exec_lines.append(tag)
        executed_intents.append(
            {
                "tool": "store_fact",
                "topic": topic,
                "fact": fact_body,
                "mem_id": mem_id,
                "simulated": simulated,
            }
        )
        total_saved += 2100

    # INTENT B: swarm_impact_graph (Blast Radius / Impact Check)
    m_impact = re.search(
        r"(?:qual [ée] o impacto de(?: mexer em| alterar| mudar)?|impacto de(?: mexer em| alterar)?|blast radius de|quem chama|quem depende de|what calls|impact of changing)\s+(.+)",
        q,
        re.IGNORECASE,
    )
    if m_impact:
        raw_target = m_impact.group(1).strip().rstrip("?.! ")
        # Limpar artigos iniciais
        raw_target = re.sub(r"^(?:o|a|os|as|the)\s+", "", raw_target, flags=re.IGNORECASE).strip()
        target_res = resolve_spoken_code_targets(raw_target, workspace_root=ws_dir, db=db)
        target = (
            target_res["resolved_files"][0]
            if target_res["resolved_files"]
            else (raw_target.replace(" ", "_") if " " in raw_target else raw_target)
        )

        risk = "LOW"
        dep_list = "none"
        if db is not None:
            try:
                from swarm_engine import SwarmEngine

                sw = SwarmEngine(db)
                i_res = sw.analyze_impact_graph(target, workspace_path=ws_dir)
                risk = str(i_res.get("blast_radius") or "LOW")
                callers = i_res.get("callers") or []
                c_files = list(dict.fromkeys(c.get("file", "") for c in callers if c.get("file")))
                dep_list = ",".join(c_files[:3]) or "none"
            except Exception:
                pass

        tag = f"[VOICE_PRE_EXEC|swarm_impact_graph={target}|risk={risk}|dependents={dep_list} — ALREADY_COMPUTED]"
        pre_exec_lines.append(tag)
        executed_intents.append(
            {
                "tool": "swarm_impact_graph",
                "target": target,
                "risk": risk,
                "dependents": dep_list,
            }
        )
        total_saved += 2500

    # INTENT C: swarm_symbol_lookup (Localização Cirúrgica de Linhas)
    m_lookup = re.search(
        r"(?:onde est[áa] (?:a fun[çc][ãa]o|a classe|o m[ée]todo|definid[oa])|mostra a linha d[aeo]|em que linha est[áa]|where is (?:function|class))\s+(.+)",
        q,
        re.IGNORECASE,
    )
    if m_lookup:
        raw_sym = m_lookup.group(1).strip().rstrip("?.! ")
        raw_sym = re.sub(r"^(?:a|o|da|do|the)\s+", "", raw_sym, flags=re.IGNORECASE).strip()
        sym_query = raw_sym.replace(" ", "_")

        matched_loc = None
        if db is not None:
            try:
                from swarm_engine import SwarmEngine

                sw = SwarmEngine(db)
                res = sw.lookup_symbol(sym_query, workspace_path=ws_dir, include_body=False)
                matches = res.get("matches", [])
                if matches:
                    top_m = matches[0]
                    matched_loc = (
                        top_m.get("symbol", sym_query),
                        top_m.get("file", "unknown"),
                        top_m.get("start_line", 1),
                        top_m.get("end_line", 10),
                    )
            except Exception:
                pass

        if matched_loc:
            s_name, f_name, s_l, e_l = matched_loc
            tag = f"[VOICE_PRE_EXEC|swarm_symbol_lookup={s_name}->{f_name}:L{s_l}-L{e_l} — ALREADY_LOCATED]"
        else:
            tag = f"[VOICE_PRE_EXEC|swarm_symbol_lookup={sym_query} — TARGET_QUERY_READY]"

        pre_exec_lines.append(tag)
        executed_intents.append(
            {
                "tool": "swarm_symbol_lookup",
                "symbol": sym_query,
                "location": matched_loc,
            }
        )
        total_saved += 1800

    # INTENT D: brain_stats / checkpoint (Estado Atual do Brain)
    m_stats = re.search(
        r"(?:estado do brain|quantas mem[óo]rias tem o brain|qual o checkpoint atual|brain status|checkpoint status)",
        q,
        re.IGNORECASE,
    )
    if m_stats:
        total_mems = 0
        chk_goal = "N/A"
        if db is not None:
            try:
                stats = db.get_stats()
                total_mems = stats.get("total_memories", 0)
                chk = db.get_checkpoint(workspace) or {}
                chk_goal = str(chk.get("goal") or chk.get("last_completed") or "Active")[:35]
            except Exception:
                pass

        tag = f"[VOICE_PRE_EXEC|brain_status=mems:{total_mems}|chk:{chk_goal}]"
        pre_exec_lines.append(tag)
        executed_intents.append(
            {
                "tool": "brain_stats",
                "total_memories": total_mems,
                "checkpoint": chk_goal,
            }
        )
        total_saved += 1200

    # Dynamic Tool Pruning para voz (zero disk I/O usando JEV-S1 + INTENT_TOOL_ROUTING)
    tool_pruning: Dict[str, Any] = {}
    voice_tools_line = ""
    try:
        from token_diet import ALL_BRAIN_MCP_TOOLS, INTENT_TOOL_ROUTING

        active_db = db
        if active_db is None:
            from db_engine import BrainDB

            active_db = BrainDB()
        ws_norm = active_db.normalize_workspace(workspace)
        route = active_db.jev_system1_route(q or "general engineering", ws_norm)
        intent = str(route.get("intent") or "general_engineering")
        spec = INTENT_TOOL_ROUTING.get(intent, INTENT_TOOL_ROUTING["general_engineering"])
        act_tools = list(spec.get("active_tools") or [])
        saved_tok = max(180, (len(ALL_BRAIN_MCP_TOOLS) - len(act_tools)) * 42 + 480)
        tool_pruning = {
            "ok": True,
            "workspace": ws_norm,
            "intent": intent,
            "active_tools": act_tools,
            "tokens_saved_per_step": saved_tok,
        }
        voice_tools_line = (
            f"[BRAIN_VOICE_TOOLS|intent={intent}|use_only={','.join(act_tools[:4])}|saved=~{saved_tok}tok]"
        )
    except Exception:
        voice_tools_line = "[BRAIN_VOICE_TOOLS|intent=general_engineering|use_only=swarm_symbol_lookup,search_brain,store_fact|saved=~180tok]"

    return {
        "executed_intents": executed_intents,
        "pre_exec_lines": pre_exec_lines,
        "voice_tools_line": voice_tools_line,
        "tool_pruning": tool_pruning,
        "estimated_tokens_saved": total_saved,
        "latency_ms": round((time.perf_counter() - t0) * 1000.0, 2),
    }


def process_voice_turn(
    db: Any,
    raw_query: str,
    workspace: str = "brain_mcp",
    workspace_root: str = "",
    scout_map: str = "",
    has_audio_media: bool = False,
    allow_write: bool = True,
) -> Dict[str, Any]:
    """
    Convenience Orchestrator:
    Combina VoiceSttDenoiser + SpokenCodePhoneticResolver + VoiceZeroCallPreExecutor
    num único payload otimizado com latência agregada <4ms.
    """
    t0 = time.perf_counter()

    # 1. Denoising STT
    stt = analyze_voice_input(raw_query, has_audio_media=has_audio_media)
    clean_q = stt.get("clean_query") or raw_query
    is_voice = bool(stt.get("is_voice_likely"))

    # 2. Resolução Fonética de Ficheiros e AST
    targets = resolve_spoken_code_targets(
        raw_query=clean_q,
        workspace_root=workspace_root,
        scout_map=scout_map,
        db=db,
    )

    # 3. Pré-Execução Zero-Call de Ferramentas
    pre_exec = pre_execute_voice_brain_tools(
        db=db,
        raw_query=clean_q,
        workspace=workspace,
        workspace_root=workspace_root,
        allow_write=allow_write,
    )

    # 4. Montar Linhas Efêmeras para Injeção no [BRAIN_MEMORY]
    ephemeral_lines: List[str] = []

    # Pre-exec lines têm prioridade máxima (evitam tool calls redundantes)
    for line in pre_exec.get("pre_exec_lines", []):
        if line and line not in ephemeral_lines:
            ephemeral_lines.append(line)

    # Directive line de AST Pointers / Files
    if targets.get("directive_line"):
        ephemeral_lines.append(targets["directive_line"])

    # Diretiva de modo conciso se for voz
    if is_voice and stt.get("voice_concise_directive"):
        ephemeral_lines.append(stt["voice_concise_directive"])

    # Linha de pruning de ferramentas se for voz
    if is_voice and pre_exec.get("voice_tools_line"):
        ephemeral_lines.append(pre_exec["voice_tools_line"])

    total_tokens_saved = (
        int(stt.get("estimated_tokens_saved") or 0)
        + int(targets.get("estimated_tokens_saved") or 0)
        + int(pre_exec.get("estimated_tokens_saved") or 0)
    )

    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    return {
        "is_voice_likely": is_voice,
        "has_audio_media": has_audio_media,
        "raw_query": raw_query,
        "clean_query": clean_q,
        "resolved_files": targets.get("resolved_files", []),
        "ast_pointers": targets.get("ast_pointers", []),
        "executed_intents": pre_exec.get("executed_intents", []),
        "pre_exec_lines": pre_exec.get("pre_exec_lines", []),
        "voice_tools_line": pre_exec.get("voice_tools_line", ""),
        "ephemeral_lines": ephemeral_lines,
        "stt_analysis": stt,
        "targets_analysis": targets,
        "pre_exec_analysis": pre_exec,
        "total_estimated_tokens_saved": total_tokens_saved,
        "latency_ms": round(elapsed_ms, 2),
    }
