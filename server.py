# /// script
# dependencies = [
#   "mcp",
# ]
# ///
import inspect
import json
import os
import sys
import traceback
from typing import Any, Callable, Dict, List, Optional, Tuple

# Guardar o stdout original exclusivamente para o protocolo JSON-RPC MCP
_MCP_RAW_STDOUT = sys.stdout
# Redirecionar qualquer print acidental de bibliotecas/imports para stderr
sys.stdout = sys.stderr

# Garantir que o diretório local está no sys.path para importar db_engine
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)


class StdioMCPServer:
    """
    Servidor MCP JSON-RPC 2.0 (stdio) ultra-rápido e zero-dependências.
    Compatível com todas as versões do Antigravity IDE / Claude / Cursor no Windows, macOS e Linux,
    sem depender de 'mcp.server.mcpserver' ou versões específicas do pacote 'mcp'.
    """

    def __init__(self, name: str, version: str = "8.1.0") -> None:
        self.name = name
        self.version = version
        self.db: Any = None
        self._tools: Dict[str, Dict[str, Any]] = {}

    READ_ONLY_TOOLS = {
        "search_brain",
        "brain_stats",
        "swarm_status",
        "swarm_symbol_lookup",
        "swarm_impact_graph",
        "brain_prune_tools",
        "swarm_watch_audit",
        "swarm_graph_path",
        "orbit_briefing_roi",
    }
    DESTRUCTIVE_TOOLS = {"forget_fact"}

    def tool(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
        annotations: Optional[Dict[str, Any]] = None,
    ) -> Callable:
        def decorator(fn: Callable) -> Callable:
            tool_name = name or fn.__name__
            doc = inspect.getdoc(fn) or description or f"Executes {tool_name}"
            doc_lines = [line.strip() for line in doc.splitlines() if line.strip()]
            short_desc = doc_lines[0] if doc_lines else f"Executes {tool_name}"

            # Extrair descrições de parâmetros do bloco Args: na docstring
            param_docs: Dict[str, str] = {}
            in_args = False
            for line in doc.splitlines():
                stripped = line.strip()
                if stripped.lower().startswith("args:"):
                    in_args = True
                    continue
                if in_args:
                    if stripped.endswith(":") and " " not in stripped:
                        in_args = False
                        continue
                    if ":" in stripped:
                        p_name, p_desc = stripped.split(":", 1)
                        p_name = p_name.strip()
                        if p_name.isidentifier():
                            param_docs[p_name] = p_desc.strip()

            sig = inspect.signature(fn)
            properties: Dict[str, Any] = {}
            required: List[str] = []

            type_map = {
                str: "string",
                int: "integer",
                float: "number",
                bool: "boolean",
                list: "array",
                dict: "object",
            }

            for param_name, param in sig.parameters.items():
                if param_name == "self":
                    continue
                ann = param.annotation
                json_type = type_map.get(ann, "string")
                prop_schema: Dict[str, Any] = {"type": json_type}
                if param_name in param_docs:
                    prop_schema["description"] = param_docs[param_name]
                if param.default is inspect.Parameter.empty:
                    required.append(param_name)
                else:
                    prop_schema["default"] = param.default
                properties[param_name] = prop_schema

            input_schema: Dict[str, Any] = {
                "type": "object",
                "properties": properties,
            }
            if required:
                input_schema["required"] = required

            is_ro = tool_name in self.READ_ONLY_TOOLS
            is_destr = tool_name in self.DESTRUCTIVE_TOOLS
            tool_annotations: Dict[str, Any] = {
                "readOnlyHint": is_ro,
                "idempotentHint": True if (is_ro or is_destr or tool_name in ("store_fact", "save_checkpoint", "swarm_scout")) else False,
                "destructiveHint": is_destr,
            }
            if annotations:
                tool_annotations.update(annotations)

            self._tools[tool_name] = {
                "fn": fn,
                "signature": sig,
                "schema": {
                    "name": tool_name,
                    "description": short_desc[:115],
                    "inputSchema": input_schema,
                    "annotations": tool_annotations,
                },
            }
            return fn

        return decorator

    def _coerce_args(self, sig: inspect.Signature, arguments: Dict[str, Any]) -> Dict[str, Any]:
        coerced: Dict[str, Any] = {}
        for k, v in (arguments or {}).items():
            if k in sig.parameters:
                ann = sig.parameters[k].annotation
                try:
                    if ann is int and not isinstance(v, int):
                        v = int(v)
                    elif ann is float and not isinstance(v, (int, float)):
                        v = float(v)
                    elif ann is bool and isinstance(v, str):
                        v = v.strip().lower() in ("1", "true", "yes", "sim")
                    elif ann is str and v is not None and not isinstance(v, str):
                        v = str(v)
                except Exception:
                    pass
                coerced[k] = v
        return coerced

    def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Any:
        args = arguments or {}
        tool_entry = self._tools.get(name)
        if not tool_entry:
            raise ValueError(f"Unknown tool: {name}")
        call_args = self._coerce_args(tool_entry["signature"], args)
        return tool_entry["fn"](**call_args)

    def handle_request(self, req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        method = req.get("method", "")
        req_id = req.get("id")
        params = req.get("params") or {}

        # Notificações JSON-RPC (sem id) não têm resposta
        if req_id is None:
            return None

        if method == "initialize":
            client_proto = params.get("protocolVersion") if isinstance(params, dict) else None
            proto_ver = client_proto if isinstance(client_proto, str) and client_proto else "2024-11-05"
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": proto_ver,
                    "capabilities": {
                        "tools": {"listChanged": False},
                        "resources": {"subscribe": False, "listChanged": False},
                        "prompts": {"listChanged": False},
                    },
                    "serverInfo": {
                        "name": self.name,
                        "version": self.version,
                    },
                },
            }

        if method == "ping":
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}

        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": [t["schema"] for t in self._tools.values()],
                },
            }

        if method == "tools/call":
            tool_name = params.get("name", "") if isinstance(params, dict) else ""
            raw_args = params.get("arguments") or {} if isinstance(params, dict) else {}
            tool_entry = self._tools.get(tool_name)
            if not tool_entry:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32601,
                        "message": f"Unknown tool: {tool_name}",
                    },
                }
            try:
                call_args = self._coerce_args(tool_entry["signature"], raw_args)
                output = tool_entry["fn"](**call_args)
                text_out = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False, indent=2)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": text_out}],
                        "isError": False,
                    },
                }
            except Exception as exc:
                err_msg = f"Error executing {tool_name}: {exc}\n{traceback.format_exc()}"
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": err_msg}],
                        "isError": True,
                    },
                }

        if method == "resources/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "resources": [
                        {
                            "uri": "brain://memories/pinned",
                            "name": "Pinned Directives & Global Rules",
                            "description": "High-priority pinned memories, human-locked directives, and distilled Self-Learn rules",
                            "mimeType": "text/markdown",
                        },
                        {
                            "uri": "brain://scout/map",
                            "name": "Scout Shared Codebase Map",
                            "description": "Single-pass AST codebase map ([SCOUT_SHARED_MAP]) with surgical :Lstart-end pointers",
                            "mimeType": "text/markdown",
                        },
                        {
                            "uri": "brain://graph/report",
                            "name": "Graphify Architecture Report & God Nodes",
                            "description": "Multi-modal knowledge graph report with God Nodes, PageRank, and topological communities",
                            "mimeType": "text/markdown",
                        },
                        {
                            "uri": "brain://orbit/briefing",
                            "name": "Orbit Morning Briefing & ROI",
                            "description": "Executive morning briefing, 5h quota radar, and engineering ROI metrics",
                            "mimeType": "text/markdown",
                        },
                        {
                            "uri": "brain://voice/protocol",
                            "name": "Voice-Aware Zero-Call Protocol & Phonetic AST Guide",
                            "description": "Active voice token-saving rules, phonetic AST resolution patterns, and zero-call pre-execution status",
                            "mimeType": "text/markdown",
                        },
                    ]
                },
            }

        if method == "resources/templates/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "resourceTemplates": [
                        {
                            "uriTemplate": "brain://workspace/{workspace}/checkpoint",
                            "name": "Workspace Checkpoint",
                            "description": "Active project checkpoint, goal, next tasks, and key files for a workspace",
                            "mimeType": "text/markdown",
                        },
                        {
                            "uriTemplate": "brain://symbol/{symbol_name}",
                            "name": "AST Symbol Slice",
                            "description": "Surgical AST symbol lookup with [start_line, end_line] and code snippet",
                            "mimeType": "text/markdown",
                        },
                    ]
                },
            }

        if method == "resources/read":
            uri = str((params or {}).get("uri") or "").strip()
            text_out = self._resolve_resource_uri(uri)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "contents": [
                        {
                            "uri": uri,
                            "mimeType": "text/markdown",
                            "text": text_out,
                        }
                    ]
                },
            }

        if method == "prompts/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "prompts": [
                        {
                            "name": "ultraplan-scout",
                            "description": "Deep architectural planning workflow grounded in [SCOUT_SHARED_MAP] and Graphify God Nodes",
                            "arguments": [
                                {"name": "goal", "description": "Architectural feature or refactoring goal", "required": True},
                                {"name": "workspace", "description": "Target workspace name", "required": False},
                            ],
                        },
                        {
                            "name": "bugfix-lineage",
                            "description": "Deterministic root-cause debugging prompt using AST slices, blast radius, and regression tests",
                            "arguments": [
                                {"name": "issue", "description": "Bug symptom or stack trace", "required": True},
                                {"name": "target_file", "description": "Suspected file or symbol", "required": False},
                            ],
                        },
                        {
                            "name": "swarm-dispatch",
                            "description": "Asymmetric Swarm 4-lane decomposition (UI, API, TESTS, DOCS) with surgical file ownership",
                            "arguments": [
                                {"name": "mission", "description": "Multi-file engineering mission to parallelize", "required": True},
                                {"name": "workspace", "description": "Target workspace name", "required": False},
                            ],
                        },
                    ]
                },
            }

        if method == "prompts/get":
            prompt_name = str((params or {}).get("name") or "").strip()
            prompt_args = (params or {}).get("arguments") or {}
            prompt_payload = self._build_prompt_payload(prompt_name, prompt_args)
            if prompt_payload is None:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32602,
                        "message": f"Unknown prompt: {prompt_name}",
                    },
                }
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": prompt_payload,
            }

        if method == "logging/setLevel":
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32601,
                "message": f"Method not found: {method}",
            },
        }

    def _resolve_resource_uri(self, uri: str) -> str:
        try:
            if uri == "brain://memories/pinned":
                mems = db.search_memories("", workspace="all", n_results=12, update_stats=False)
                lines = ["# 📌 Pinned Directives & Global Rules\n"]
                for m in mems:
                    lines.append(f"- **[{m.get('workspace', 'global')}] {m.get('topic')}**: {m.get('fact')}")
                return "\n".join(lines)
            if uri == "brain://scout/map":
                scout_res = swarm.run_codebase_scout(CURRENT_DIR)
                return str(scout_res.get("shared_map") or "# Scout Shared Map\n")
            if uri == "brain://graph/report":
                rep = swarm.generate_architecture_report(workspace_path=CURRENT_DIR, write_to_disk=False)
                return str(rep.get("markdown") or "# Graphify Architecture Report\n")
            if uri == "brain://orbit/briefing":
                brief = orbit.get_executive_briefing_and_roi()
                return f"# 🪐 Orbit Morning Briefing & ROI\n\n```json\n{json.dumps(brief, indent=2, ensure_ascii=False)}\n```"
            if uri == "brain://voice/protocol":
                return (
                    "# 🎙️ Voice-Aware Zero-Call Protocol & Phonetic AST Guide\n\n"
                    "## 5 Voice Compatibility Mechanisms\n\n"
                    "1. **VoiceSttDenoiser**: Filters speech recognition filler words, repeated tokens, conversational stuttering, and STT transcription artifacts.\n"
                    "2. **SpokenCodePhoneticResolver**: Maps spoken camelCase, snake_case, dot-notation, and phonetically ambiguous filenames/symbols to real AST `:Lstart-end` pointers.\n"
                    "3. **VoiceZeroCallPreExecutor**: Pre-executes unambiguous voice intent operations (e.g., `store_fact`, `swarm_symbol_lookup`, `swarm_impact_graph`) directly in local SQLite/AST before LLM invocation.\n"
                    "4. **MultimodalAudioTurnSupport**: Detects spoken/audio-turn contexts and applies conversational formatting suitable for rapid voice synthesis and concise listening.\n"
                    "5. **VoiceToolPruningRouter**: Dynamically prunes irrelevant MCP tool schemas for voice turns, cutting overhead by up to 68% tokens.\n"
                )
            if uri.startswith("brain://workspace/") and uri.endswith("/checkpoint"):
                ws_part = uri[len("brain://workspace/") : -len("/checkpoint")].strip("/") or "brain_mcp"
                chk = db.get_checkpoint(ws_part) or {}
                return (
                    f"# 🏁 Checkpoint — `{ws_part}`\n\n"
                    f"- **Project**: {chk.get('project', ws_part)}\n"
                    f"- **Goal**: {chk.get('goal', 'N/A')}\n"
                    f"- **Status**: {chk.get('status', 'Active')}\n"
                    f"- **Key Files**: {chk.get('key_files', 'N/A')}\n"
                )
            if uri.startswith("brain://symbol/"):
                sym_name = uri[len("brain://symbol/") :].strip("/")
                lookup = swarm.lookup_symbol(sym_name, workspace_path=CURRENT_DIR)
                return f"# 🔍 AST Symbol Slice: `{sym_name}`\n\n```json\n{json.dumps(lookup, indent=2, ensure_ascii=False)}\n```"
        except Exception as exc:
            return f"# Resource Error (`{uri}`)\n\n{exc}"
        return f"# Resource `{uri}`\n\nNo content found for `{uri}`."

    def _build_prompt_payload(self, prompt_name: str, args: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if prompt_name == "ultraplan-scout":
            goal = str(args.get("goal") or "Design and implement architectural upgrade").strip()
            ws = str(args.get("workspace") or "brain_mcp").strip()
            text = (
                f"# 📐 Ultraplan Scout Protocol — `{ws}`\n\n"
                f"**Goal**: {goal}\n\n"
                f"1. Read `[SCOUT_SHARED_MAP]` and `brain://graph/report` once to identify God Nodes and target `:Lstart-end` slices.\n"
                f"2. Formulate a bounded multi-phase plan with explicit interface contracts and zero blind overwrites.\n"
                f"3. Verify all changes via AST compilation and automated tests before completion."
            )
            return {
                "description": f"Ultraplan architectural specification for {ws}",
                "messages": [{"role": "user", "content": {"type": "text", "text": text}}],
            }
        if prompt_name == "bugfix-lineage":
            issue = str(args.get("issue") or "Investigate and fix reported regression").strip()
            target_file = str(args.get("target_file") or "workspace").strip()
            text = (
                f"# 🐛 Bugfix Lineage & Root-Cause Protocol\n\n"
                f"**Issue**: {issue}\n"
                f"**Target**: `{target_file}`\n\n"
                f"1. Use `swarm_symbol_lookup` and `swarm_impact_graph` on `{target_file}` to isolate exact `:Lstart-end` lines and callers.\n"
                f"2. Apply a surgical `edit_file` fix preserving existing contracts and docstrings.\n"
                f"3. Run regression tests and append `<!-- brain: Bugfix | Root cause and fix -->`."
            )
            return {
                "description": f"Root-cause bugfix workflow for {target_file}",
                "messages": [{"role": "user", "content": {"type": "text", "text": text}}],
            }
        if prompt_name == "swarm-dispatch":
            mission = str(args.get("mission") or "Execute parallel multi-lane sprint").strip()
            ws = str(args.get("workspace") or "brain_mcp").strip()
            text = (
                f"# 🐝 Asymmetric Swarm 4-Lane Dispatch (`SCOUT ➔ PLAN ➔ SWARM ➔ VERIFY`) — `{ws}`\n\n"
                f"**Mission**: {mission}\n\n"
                f"- **Lane 1 (`DB-HOOKS`)**: Core storage, schema, and hooks.\n"
                f"- **Lane 2 (`API-ENGINES`)**: Backend engines, AST graph, and MCP protocol.\n"
                f"- **Lane 3 (`UI-GATEWAY`)**: HTTP routes and 60 FPS frontend UI.\n"
                f"- **Lane 4 (`QA-VERIFY`)**: End-to-end test suite and transactional sandbox verification."
            )
            return {
                "description": f"Asymmetric Swarm 4-lane dispatch plan for {ws}",
                "messages": [{"role": "user", "content": {"type": "text", "text": text}}],
            }
        return None

    def _read_message(self, in_stream: Any) -> Tuple[Optional[Any], bool]:
        """
        Reads a single JSON-RPC message supporting both Content-Length (exact UTF-8 byte framing)
        and newline-delimited JSON-RPC, while remaining 100% compatible with both binary-backed
        streams (`sys.stdin.buffer`) and `io.StringIO` in unit tests.
        """
        use_buffer = hasattr(in_stream, "buffer") and getattr(in_stream, "buffer", None) is not None
        raw_stream = in_stream.buffer if use_buffer else in_stream

        while True:
            line = raw_stream.readline()
            if not line:
                return None, False

            line_str = line.decode("utf-8", errors="replace") if isinstance(line, (bytes, bytearray)) else str(line)
            stripped = line_str.strip()
            if not stripped:
                continue

            if stripped.lower().startswith("content-length:"):
                length = int(stripped.split(":", 1)[1].strip())
                while True:
                    hdr_line = raw_stream.readline()
                    if not hdr_line:
                        break
                    hdr_str = (
                        hdr_line.decode("utf-8", errors="replace")
                        if isinstance(hdr_line, (bytes, bytearray))
                        else str(hdr_line)
                    )
                    if hdr_str.strip() == "":
                        break

                if isinstance(line, (bytes, bytearray)):
                    raw_bytes = raw_stream.read(length)
                    if not raw_bytes:
                        return None, True
                    raw_body = raw_bytes.decode("utf-8", errors="replace")
                else:
                    # io.StringIO compatibility with exact UTF-8 byte length framing
                    chunks: List[str] = []
                    bytes_read = 0
                    while bytes_read < length:
                        ch = raw_stream.read(1)
                        if not ch:
                            break
                        chunks.append(ch)
                        bytes_read += len(ch.encode("utf-8"))
                    raw_body = "".join(chunks)
                    if not raw_body:
                        return None, True
                return json.loads(raw_body), True

            return json.loads(stripped), False

    def _write_message(self, out_stream: Any, payload: Dict[str, Any], use_content_length: bool = False) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if use_content_length:
            body_bytes = body.encode("utf-8")
            header = f"Content-Length: {len(body_bytes)}\r\n\r\n"
            out_stream.write(header)
            out_stream.write(body)
        else:
            out_stream.write(body + "\n")
        out_stream.flush()

    def run(self, transport: str = "stdio") -> None:
        in_stream = sys.stdin
        out_stream = _MCP_RAW_STDOUT

        for stream in (in_stream, out_stream, sys.stderr):
            if stream is not None and hasattr(stream, "reconfigure"):
                try:
                    stream.reconfigure(encoding="utf-8", errors="replace")
                except Exception:
                    pass

        use_content_length = False
        while True:
            try:
                msg, is_cl = self._read_message(in_stream)
                if msg is None:
                    break
                if is_cl:
                    use_content_length = True

                if isinstance(msg, list):
                    responses = []
                    for item in msg:
                        if isinstance(item, dict):
                            resp = self.handle_request(item)
                            if resp is not None:
                                responses.append(resp)
                    if responses:
                        self._write_message(out_stream, responses, use_content_length=use_content_length)
                elif isinstance(msg, dict):
                    resp = self.handle_request(msg)
                    if resp is not None:
                        self._write_message(out_stream, resp, use_content_length=use_content_length)
            except json.JSONDecodeError:
                continue
            except (EOFError, KeyboardInterrupt):
                break
            except Exception as exc:
                try:
                    sys.stderr.write(f"[antigravity-brain MCP error] {exc}\n")
                    sys.stderr.flush()
                except Exception:
                    pass


MCPServer = StdioMCPServer

from ast_impact_watcher import get_global_watcher
from db_engine import BrainDB, ensure_dashboard_running
from orbit_engine import OrbitEngine
from swarm_engine import SwarmEngine
from token_diet import prune_tools_for_intent

db = BrainDB()
swarm = SwarmEngine(db)
orbit = OrbitEngine(db)
try:
    ensure_dashboard_running()
except Exception:
    pass

# Create the MCP server
mcp = MCPServer("antigravity-brain", version="8.1.0")
mcp.db = db



@mcp.tool()
def store_fact(
    topic: str,
    fact: str,
    workspace: str = "global",
    category: str = "general",
    tags: str = "",
    importance: int = 4,
) -> str:
    """Stores a new fact in the brain using hybrid SQLite FTS5 BM25 indexing.

    Args:
        topic: The general topic or category of the fact
        fact: The detailed information to remember
        workspace: Optional project/workspace name (default 'global')
        category: Category such as 'architecture', 'bugfix', 'infra', 'preference'
        tags: Space-separated keywords for fast retrieval
        importance: Priority from 1 (low) to 5 (critical)
    """
    row_id, is_new = db.store_fact(
        topic=topic,
        fact=fact,
        workspace=workspace,
        category=category,
        tags=tags,
        importance=importance,
    )
    status = "stored" if is_new else "updated (deduplicated)"
    return f"Fact {status} successfully with ID {row_id}."


@mcp.tool()
def search_brain(query: str, n_results: int = 5, workspace: str = "global") -> str:
    """Searches for relevant facts in the brain using hybrid BM25 + lexical similarity.

    Args:
        query: The question or context to search for. Natural language or keywords.
        n_results: Maximum number of results to return (default 5)
        workspace: Optional workspace filter boost
    """
    results = db.search_memories(query=query, workspace=workspace, n_results=n_results)
    if not results:
        return f"No relevant memories found for '{query}'."

    formatted_results = []
    for item in results:
        doc_id = item["id"]
        ws_label = f"[{item.get('workspace', 'global')}] " if item.get("workspace") else ""
        formatted_results.append(
            f"- [ID: {doc_id}] {ws_label}{item['topic']}: {item['fact']}"
        )

    return "Found the following relevant memories:\n" + "\n".join(formatted_results)


@mcp.tool()
def forget_fact(fact_id: str) -> str:
    """Deletes a fact from the brain using its ID.

    Args:
        fact_id: The ID of the fact to delete
    """
    if db.forget_fact(fact_id):
        return f"Successfully deleted fact ID {fact_id}."
    return f"Fact ID {fact_id} not found or could not be deleted."


@mcp.tool()
def save_checkpoint(
    workspace: str,
    project: str,
    goal: str = "",
    status: str = "",
    stack: str = "",
    last_completed: str = "",
    next_tasks: str = "",
    key_files: str = "",
) -> str:
    """Saves an ultra-compact project checkpoint for instant session resume.

    Args:
        workspace: Workspace identifier
        project: Project name
        goal: Current 1-line goal
        status: Current progress status
        stack: Tech stack summary
        last_completed: Recently completed tasks
        next_tasks: Next immediate tasks
        key_files: Comma-separated critical file paths
    """
    db.save_checkpoint(
        workspace=workspace,
        project=project,
        goal=goal,
        status=status,
        stack=stack,
        last_completed=last_completed,
        next_tasks=next_tasks,
        key_files=key_files,
    )
    return f"Checkpoint saved for workspace '{workspace}'."


@mcp.tool()
def brain_stats() -> str:
    """Returns Brain memory counts, injection latency, and estimated token savings."""
    return json.dumps(db.get_stats(), indent=2, ensure_ascii=False)


@mcp.tool()
def swarm_scout(workspace_path: str = "") -> str:
    """Runs the Scout-01 single-pass codebase indexer and stores the Shared Codebase Map in brain.db so subagents do not need to re-read files."""
    res = swarm.run_codebase_scout(workspace_path or CURRENT_DIR)
    return json.dumps(res, indent=2, ensure_ascii=False)


@mcp.tool()
def swarm_start(
    goal: str,
    workspace_path: str = "",
    animate_live: bool = True,
) -> str:
    """Starts an Asymmetric Swarm Run (0. Scout Shared Map -> 1. Architect Plan -> 2. 4 Parallel Lanes [UI, API, TESTS, DOCS] -> 3. Verify 48/48)."""
    res = swarm.start_live_swarm_run(
        goal=goal, workspace_path=workspace_path or CURRENT_DIR, animate_live=animate_live
    )
    return json.dumps(res["run"], indent=2, ensure_ascii=False)


@mcp.tool()
def swarm_update_task(
    task_code: str,
    status: str = "done",
    progress: int = 100,
    summary: str = "",
) -> str:
    """Updates the live status of a Swarm worker task (e.g., ui-01, api-02, test-01, docs-01) on the Swarm Monitor dashboard."""
    res = swarm.update_task_status(
        task_code=task_code, status=status, progress=progress, summary=summary
    )
    return json.dumps(res["run"], indent=2, ensure_ascii=False)


@mcp.tool()
def swarm_status() -> str:
    """Returns the current Asymmetric Swarm dashboard state, lane progress, and Scout Shared Map."""
    return json.dumps(swarm.get_swarm_dashboard(), indent=2, ensure_ascii=False)


@mcp.tool()
def swarm_symbol_lookup(symbol_query: str, workspace_path: str = "") -> str:
    """Locates a Python/JS/TS/HTML class or function by name using AST parsing and returns its exact file path, [start_line, end_line] range, and snippet so agents can edit surgically without reading full files."""
    res = swarm.lookup_symbol(symbol_query=symbol_query, workspace_path=workspace_path or CURRENT_DIR)
    return json.dumps(res, indent=2, ensure_ascii=False)


@mcp.tool()
def swarm_impact_graph(target: str, workspace_path: str = "") -> str:
    """Computes the reverse call & import dependency graph (blast radius) and recommended tests for a symbol or file before making code modifications."""
    res = swarm.analyze_impact_graph(target=target, workspace_path=workspace_path or CURRENT_DIR)
    return json.dumps(res, indent=2, ensure_ascii=False)


@mcp.tool()
def brain_prune_tools(query: str, workspace: str = "global") -> str:
    """Dynamic Intent-Based Tool Pruning: selects only the 3-4 essential MCP tools and servers for the given prompt intent, saving ~65% tool schema tokens."""
    res = prune_tools_for_intent(user_query=query, workspace=workspace)
    return json.dumps(res, indent=2, ensure_ascii=False)


@mcp.tool()
def swarm_sandbox(
    action: str = "create",
    lane: str = "API",
    task_code: str = "api-01",
    target_files: str = "",
    sandbox_id: int = 0,
    workspace_path: str = "",
) -> str:
    """Manages transactional Copy-on-Write subagent sandboxes with SHA-256 pre/post snapshots, AST syntax gate, and AI-Defence secret scanner before merge."""
    files_list = [f.strip() for f in target_files.split(",") if f.strip()] if target_files else []
    res = swarm.manage_subagent_sandbox(
        action=action,
        lane=lane,
        task_code=task_code,
        target_files=files_list,
        sandbox_id=sandbox_id or None,
        workspace_path=workspace_path or CURRENT_DIR,
    )
    return json.dumps(res, indent=2, ensure_ascii=False)


@mcp.tool()
def swarm_watch_audit(
    target_file: str = "",
    workspace_path: str = "",
    force: bool = True,
) -> str:
    """Runs the automated AST & Impact Radius file-save analyzer on a specific file or workspace to preemptively flag high-risk changes."""
    watcher = get_global_watcher(workspace_path or CURRENT_DIR)
    if target_file.strip():
        res = watcher.audit_file_save(
            file_path=target_file.strip(),
            workspace_path=workspace_path or CURRENT_DIR,
            force=force,
        )
    else:
        res = watcher.scan_workspace_saves(
            workspace_path=workspace_path or CURRENT_DIR,
            force_all=force,
        )
    return json.dumps(res, indent=2, ensure_ascii=False)


@mcp.tool()
def swarm_graph_path(
    source: str,
    target: str,
    max_hops: int = 6,
    workspace_path: str = "",
) -> str:
    """Graphify Multi-Modal BFS Shortest Path Finder: finds the exact relational path (JS Function -> HTTP Route -> Python AST -> SQLite Table) with confidence-labeled edges (EXTRACTED/INFERRED/AMBIGUOUS) and 70x+ token savings."""
    res = swarm.find_graph_path(
        source_query=source,
        target_query=target,
        max_hops=max_hops,
        workspace_path=workspace_path or CURRENT_DIR,
    )
    return json.dumps(res, indent=2, ensure_ascii=False)


@mcp.tool()
def swarm_architecture_report(
    workspace_path: str = "",
    write_to_disk: bool = True,
) -> str:
    """Generates the Graphify GRAPH_REPORT.md with Topological Communities, God Nodes centrality, confidence breakdown, and full-stack causal chains."""
    res = swarm.generate_architecture_report(
        workspace_path=workspace_path or CURRENT_DIR,
        write_to_disk=write_to_disk,
    )
    return json.dumps(res, indent=2, ensure_ascii=False)


@mcp.tool()
def orbit_mission_control(
    action: str = "inbox",
    target_scope: str = "all_fleet",
    directive: str = "",
    item_id: int = 0,
    workspace: str = "brain_mcp",
) -> str:
    """Orbit Agent OS Mission Control: manage human-in-the-loop Inbox approvals ('inbox', 'approve_all', 'approve_item', 'redirect_item'), send multi-scope fleet broadcasts ('broadcast'), or connect all AI IDEs ('connect_mcp_bridge').

    Args:
        action: Action to perform: 'inbox', 'approve_all', 'approve_item', 'redirect_item', 'broadcast', or 'connect_mcp_bridge'
        target_scope: Scope for broadcast: 'all_fleet', 'dept:UI', 'dept:API', 'dept:TESTS', 'dept:DOCS', or 'ws:<workspace>'
        directive: Directive or redirect note text
        item_id: Inbox item ID for approve_item or redirect_item
        workspace: Workspace identifier
    """
    if action == "approve_all":
        res = orbit.approve_all_inbox(workspace_path=CURRENT_DIR)
    elif action == "approve_item":
        res = orbit.approve_inbox_item(item_id=item_id, workspace_path=CURRENT_DIR)
    elif action == "redirect_item":
        res = orbit.redirect_inbox_item(item_id=item_id, redirect_note=directive)
    elif action == "broadcast":
        res = orbit.send_broadcast(target_scope=target_scope, directive=directive, workspace=workspace)
    elif action == "connect_mcp_bridge":
        res = orbit.connect_all_ai_tools()
    elif action in ("dot_ready", "dot_claim", "dot_complete", "dot_sync_md"):
        res = orbit.manage_dot_task(
            action=action.replace("dot_", ""),
            dot_id=directive or target_scope,
            workspace=workspace,
        )
    elif action == "self_learn_status":
        res = orbit.get_self_learn_status(workspace=workspace)
    elif action == "self_learn_toggle":
        en_arg = None
        if directive.lower() in ("on", "true", "1", "enable"):
            en_arg = True
        elif directive.lower() in ("off", "false", "0", "disable"):
            en_arg = False
        res = orbit.toggle_project_self_learn(workspace=workspace, enabled=en_arg)
    elif action == "self_learn_evolve":
        res = orbit.run_self_learn_evolution_cycle(workspace=workspace, force=True)
    elif action == "forge_prompt":
        res = orbit.generate_optimized_prompt(raw_request=directive, workspace=workspace, task_mode=target_scope or "feature")
    else:
        res = orbit.get_mission_control_inbox()
    return json.dumps(res, indent=2, ensure_ascii=False)


@mcp.tool()
def orbit_briefing_roi() -> str:
    """Returns the Orbit Agent OS Morning Brief, Engineering Savings / ROI Calculator (Hours + USD saved), Memory Trust Hierarchy stats, Agent Chaining Hand-offs, and Cross-IDE MCP Bridge status."""
    return json.dumps(orbit.get_executive_briefing_and_roi(), indent=2, ensure_ascii=False)


@mcp.tool()
def brain_voice_optimize(
    query: str,
    workspace: str = "brain_mcp",
    allow_write: bool = False,
) -> str:
    """Denoises spoken/STT voice queries, resolves spoken file/symbol names to :Lstart-end AST pointers, and optionally pre-executes Brain intents (store_fact, swarm_impact_graph, swarm_symbol_lookup).

    Args:
        query: Spoken/STT voice query or natural language audio transcript
        workspace: Target workspace identifier (default 'brain_mcp')
        allow_write: Whether to execute write operations (e.g. store_fact) or only simulate
    """
    try:
        from voice_brain_engine import process_voice_turn

        scout_map = ""
        try:
            scout_map = swarm.get_latest_scout_map(workspace)
        except Exception:
            pass
        res = process_voice_turn(
            db=mcp.db or db,
            raw_query=query,
            workspace=workspace,
            workspace_root=CURRENT_DIR,
            scout_map=scout_map,
            has_audio_media=False,
            allow_write=allow_write,
        )
    except Exception as e:
        res = {
            "ok": False,
            "error": str(e),
            "raw_query": query,
            "denoised_query": query,
        }
    return json.dumps(res, indent=2, ensure_ascii=False)


TOOLS: List[Dict[str, Any]] = [t["schema"] for t in mcp._tools.values()]


if __name__ == "__main__":
    if getattr(sys, "stdout", None) is not None and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    mcp.run(transport="stdio")


