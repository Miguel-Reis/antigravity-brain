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
from typing import Any, Callable, Dict, List, Optional

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

    def __init__(self, name: str, version: str = "2.4.0") -> None:
        self.name = name
        self.version = version
        self._tools: Dict[str, Dict[str, Any]] = {}

    def tool(self, name: Optional[str] = None, description: Optional[str] = None) -> Callable:
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

            self._tools[tool_name] = {
                "fn": fn,
                "signature": sig,
                "schema": {
                    "name": tool_name,
                    "description": doc,
                    "inputSchema": input_schema,
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
            return {"jsonrpc": "2.0", "id": req_id, "result": {"resources": []}}

        if method == "resources/templates/list":
            return {"jsonrpc": "2.0", "id": req_id, "result": {"resourceTemplates": []}}

        if method == "prompts/list":
            return {"jsonrpc": "2.0", "id": req_id, "result": {"prompts": []}}

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
                line = in_stream.readline()
                if not line:
                    break

                stripped = line.strip()
                if not stripped:
                    continue

                # Suporte híbrido: Content-Length (LSP-style) ou JSON-RPC por linha (MCP stdio standard)
                if stripped.lower().startswith("content-length:"):
                    use_content_length = True
                    length = int(stripped.split(":", 1)[1].strip())
                    while True:
                        hdr_line = in_stream.readline()
                        if not hdr_line or hdr_line.strip() == "":
                            break
                    raw_body = in_stream.read(length)
                    if not raw_body:
                        break
                    msg = json.loads(raw_body)
                else:
                    msg = json.loads(stripped)

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
from swarm_engine import SwarmEngine
from token_diet import prune_tools_for_intent

db = BrainDB()
swarm = SwarmEngine(db)
try:
    ensure_dashboard_running()
except Exception:
    pass

# Create the MCP server
mcp = MCPServer("antigravity-brain")



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


if __name__ == "__main__":
    if getattr(sys, "stdout", None) is not None and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    mcp.run(transport="stdio")


