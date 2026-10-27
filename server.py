# /// script
# dependencies = [
#   "mcp",
# ]
# ///
import json
import os
import sys
from mcp.server.mcpserver import MCPServer

# Garantir que o diretório local está no sys.path para importar db_engine
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from ast_impact_watcher import get_global_watcher
from db_engine import BrainDB, ensure_dashboard_running
from swarm_engine import SwarmEngine
from token_diet import prune_tools_for_intent

db = BrainDB()
swarm = SwarmEngine(db)
ensure_dashboard_running()

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


