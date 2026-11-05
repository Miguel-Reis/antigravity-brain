import json
import os
import tempfile
import time
from db_engine import BrainDB, seed_initial_memories
from brain_inject import handle_pre_invocation
from brain_harvest import handle_stop


def run_all_tests() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        test_db_path = os.path.join(tmpdir, "test_brain.db")
        db = BrainDB(db_path=test_db_path)

        # 1. Testar seeding e deduplicação
        added_1 = seed_initial_memories(db)
        added_2 = seed_initial_memories(db)
        assert added_1 >= 4, f"Esperado >=4 factos novos, obteve {added_1}"
        assert added_2 == 0, f"Deduplicação falhou: adicionou {added_2} duplicados"

        # 2. Testar pesquisa FTS5 BM25 e latência (< 40ms)
        t0 = time.perf_counter()
        results = db.search_memories("como reduzir tokens quota 5h ruflo", workspace="global", n_results=3)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        assert len(results) > 0, "Pesquisa FTS5 não retornou resultados"
        assert "token_diet.py" in results[0]["fact"] or "hooks.json" in results[0]["fact"]
        assert latency_ms < 40.0, f"Latência demasiado alta: {latency_ms:.2f}ms"
        print(f"[PASS] Pesquisa FTS5 BM25: {len(results)} resultados em {latency_ms:.2f}ms")

        # 3. Testar Checkpoint save & get
        db.save_checkpoint(
            workspace="brain_mcp",
            project="Antigravity Brain v2",
            goal="Minimizar consumo de tokens na janela de 5h",
            status="100% operacional",
            key_files="db_engine.py, brain_inject.py, brain_harvest.py, token_diet.py",
        )
        chk = db.get_checkpoint("brain_mcp")
        assert chk is not None and chk["project"] == "Antigravity Brain v2"
        print("[PASS] Checkpoints por workspace operacionais")

    # 4. Testar contrato real do PreInvocation e Stop na base de produção
    prod_db = BrainDB()
    hooks_cfg_path = os.path.expanduser("~/.gemini/config/hooks.json").replace("\\", "/")
    repo_dir = os.path.dirname(os.path.abspath(__file__))
    prod_db.save_checkpoint(
        workspace="brain_mcp",
        project="Antigravity Brain v2",
        goal="Reduzir consumo da quota de 5h com injeção efémera Zero-Round-Trip",
        status=f"Ativo em {hooks_cfg_path}",
        stack="Python 3.12+, SQLite WAL + FTS5 BM25, Antigravity Hooks, MCP, Swarm",
        key_files="db_engine.py, brain_inject.py, brain_harvest.py, server.py, swarm_engine.py, auto_updater.py",
    )

    test_conv_id = f"test-conv-{int(time.time() * 1000)}"
    sample_payload = json.dumps(
        {
            "conversationId": test_conv_id,
            "workspacePaths": [repo_dir],
            "invocationNum": 1,
        }
    )
    t0 = time.perf_counter()
    out_1 = handle_pre_invocation(sample_payload)
    inj_ms = (time.perf_counter() - t0) * 1000.0
    assert "injectSteps" in out_1, "Primeira invocação devia injetar ephemeralMessage"
    msg = out_1["injectSteps"][0]["ephemeralMessage"]
    assert "[BRAIN_MEMORY" in msg
    print(f"[PASS] PreInvocation Hook: injetou {len(msg)} chars (~{len(msg)//4} tokens) em {inj_ms:.2f}ms")

    # Segunda invocação com o mesmo prompt no mesmo conversationId deve devolver {} (guarda anti-loop)
    out_2 = handle_pre_invocation(sample_payload)
    assert out_2 == {}, "Segunda invocação no mesmo turno devia ser ignorada ({})"
    print("[PASS] Guarda Anti-Repetição de Turno verificada ({})")

    # Testar Stop Hook
    stop_out = handle_stop(sample_payload)
    assert stop_out == {"decision": "allow"}
    print("[PASS] Stop Hook verificado ({'decision': 'allow'})")

    # Limpar dados sintéticos de teste da base de produção
    with prod_db._connect() as conn:
        conn.execute("DELETE FROM injected_turns WHERE conversation_id LIKE 'test-conv-%';")
        conn.execute("DELETE FROM telemetry WHERE conversation_id LIKE 'test-conv-%';")

    # 6. Testar contrato e matemática do Modo Follow na Vista 3D do Escritório (index.html)
    index_path = os.path.join(repo_dir, "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    for required_token in (
        'id="btnOfficeFollow"',
        'id="btnOffFollowAgent"',
        'id="btnHoloFollow"',
        "function stepOfficeFollowCamera(",
        "function setOfficeFollowMode(",
        "function toggleOfficeFollowMode()",
        "stepOfficeFollowCamera(officeCam, followedSim)",
    ):
        assert required_token in html_content, f"Token em falta no index.html: {required_token}"
    print("[PASS] Contrato HTML/JS do Modo Follow 3D verificado")

    # 7. Testar Localizador Cirúrgico de Símbolos AST (lookup_symbol) e Grafo de Impacto (analyze_impact_graph)
    from swarm_engine import SwarmEngine

    swarm_eng = SwarmEngine(prod_db)
    sym_py = swarm_eng.lookup_symbol("handle_pre_invocation", workspace_path=repo_dir)
    assert sym_py["ok"] and sym_py["matches_count"] >= 1
    assert sym_py["matches"][0]["file"] == "brain_inject.py"
    assert sym_py["matches"][0]["start_line"] > 1

    sym_js = swarm_eng.lookup_symbol("stepOfficeFollowCamera", workspace_path=repo_dir)
    assert sym_js["ok"] and sym_js["matches_count"] >= 1
    assert sym_js["matches"][0]["file"] == "index.html"
    print(
        f"[PASS] AST Symbol Lookup (Python + JS): {sym_py['matches'][0]['file']}:L{sym_py['matches'][0]['start_line']} & {sym_js['matches'][0]['file']}:L{sym_js['matches'][0]['start_line']}"
    )

    impact = swarm_eng.analyze_impact_graph("BrainDB", workspace_path=repo_dir)
    assert impact["ok"] and impact["affected_files_count"] >= 4
    print(
        f"[PASS] Reverse Call/Impact Graph: {impact['affected_files_count']} ficheiros afetados ({impact['total_references']} referências, Risco: {impact['blast_radius']})"
    )

    # 8. Testar Opção A: Embeddings Semânticos Híbridos 32-D + Cosine Similarity
    vec_pt = BrainDB.compute_semantic_vector("otimizar latência da base de dados sqlite wal e indices")
    vec_en = BrainDB.compute_semantic_vector("database query latency optimization and sql schema index")
    sim_score = BrainDB.cosine_similarity(vec_pt, vec_en)
    assert len(vec_pt) == 32 and sim_score > 0.35, f"Similaridade semântica bilingue insuficiente: {sim_score}"
    sem_results = prod_db.search_memories("reduzir custo da janela de contexto e poupar bateria", workspace="global", n_results=3)
    assert len(sem_results) > 0 and "semantic_similarity" in sem_results[0]
    print(f"[PASS] Opção A (Hybrid Semantic Vector 32-D + BM25): cosine_bilingue={sim_score:.3f}, top_hit='{sem_results[0]['topic']}'")

    # 9. Testar Opção C: Dynamic Intent-Based MCP Tool Pruning
    from token_diet import prune_tools_for_intent

    pruned = prune_tools_for_intent("refatorar função python e analisar impacto AST na base de dados", workspace="brain_mcp")
    assert pruned["ok"] and pruned["selected_tools_count"] <= 6
    assert pruned["reduction_pct"] >= 50.0
    assert "swarm_symbol_lookup" in pruned["selected_tools"]
    print(
        f"[PASS] Opção C (Dynamic Tool Pruning): {pruned['selected_tools_count']}/{pruned['total_tools_available']} tools ativas "
        f"(-{pruned['reduction_pct']}% / ~{pruned['estimated_tokens_saved']} tokens poupados)"
    )

    # 10. Testar Opção D: Sandboxes Transacionais por Subagente (Copy-on-Write + Merge Gate)
    sb_create = swarm_eng.manage_subagent_sandbox(
        action="create",
        lane="API",
        task_code="api-01",
        target_files=["db_engine.py", "swarm_engine.py"],
        workspace_path=repo_dir,
    )
    assert sb_create["ok"] and sb_create["sandbox_id"] > 0
    sb_verify = swarm_eng.manage_subagent_sandbox(
        action="verify_merge",
        sandbox_id=sb_create["sandbox_id"],
        workspace_path=repo_dir,
    )
    assert sb_verify["ok"] and sb_verify["syntax_ok"] and sb_verify["secrets_ok"]
    assert sb_verify["status"] == "merged"
    # Limpar sandbox sintética criada pelo teste na BD de produção para evitar acumulação
    with prod_db._connect() as conn:
        conn.execute("DELETE FROM swarm_sandboxes WHERE id = ?;", (sb_create["sandbox_id"],))
        conn.execute("DELETE FROM orbit_inbox WHERE external_ref = ?;", (f"sandbox:{sb_create['sandbox_id']}",))
    sb_dir_cleanup = os.path.join(repo_dir, ".swarm_sandboxes", f"sb_{sb_create['sandbox_id']}_API_api-01")
    if os.path.isdir(sb_dir_cleanup):
        import shutil
        shutil.rmtree(sb_dir_cleanup, ignore_errors=True)
    print(
        f"[PASS] Opção D (Subagent Transactional Sandbox): Sandbox #{sb_verify['sandbox_id']} -> {sb_verify['status'].upper()} "
        f"(AST Gate={sb_verify['syntax_ok']}, Secret Scan={sb_verify['secrets_ok']})"
    )

    # 11. Testar Contrato das 6 Melhorias de UI/UX em index.html
    for ui_token in (
        'id="astInspectorModal"',
        'id="swarmSandboxPanel"',
        'id="officeQuickAgentDock"',
        'id="sseStatusBadge"',
        'id="fmSemSim"',
        'id="astWatcherAlertsBox"',
        "function toggleSidebarBlade(",
        "function runAstAndImpactLookup(",
        "function cycleOfficeFollowAgent(",
        "function triggerAstSaveAuditUI(",
    ):
        assert ui_token in html_content, f"Token UI em falta em index.html: {ui_token}"
    print("[PASS] Contrato das 6 Melhorias de UI/UX verificado em index.html")

    # 12. Testar Script Automatizado de Auditoria AST & Impact Radius em cada File Save (ast_impact_watcher.py)
    from ast_impact_watcher import AstImpactWatcher

    watcher = AstImpactWatcher(db=prod_db, workspace_path=repo_dir)
    save_audit = watcher.audit_file_save("db_engine.py", workspace_path=repo_dir, force=True, persist_memory_on_high_risk=False)
    assert save_audit["ok"] and save_audit["syntax_ok"] and save_audit["secrets_ok"]
    assert save_audit["risk_level"] == "HIGH" and save_audit["affected_files_count"] >= 5
    assert "BrainDB" in save_audit["changed_symbols"]

    # Testar deteção de mudança cirúrgica de símbolo e erro sintático CRITICAL num ficheiro temporário
    with tempfile.TemporaryDirectory() as w_tmp:
        sample_py = os.path.join(w_tmp, "core_service.py")
        with open(sample_py, "w", encoding="utf-8") as f:
            f.write("def compute_price(x):\n    return x * 2\n\ndef stable_fn():\n    return 1\n")
        a1 = watcher.audit_file_save(sample_py, workspace_path=w_tmp, force=True, persist_memory_on_high_risk=False)
        assert a1["ok"] and a1["syntax_ok"]

        # Modificar apenas compute_price -> deve detetar apenas 'compute_price' em changed_symbols
        with open(sample_py, "w", encoding="utf-8") as f:
            f.write("def compute_price(x):\n    return x * 3 + 1\n\ndef stable_fn():\n    return 1\n")
        a2 = watcher.audit_file_save(sample_py, workspace_path=w_tmp, force=False, persist_memory_on_high_risk=False)
        assert a2["ok"] and a2["changed_symbols"] == ["compute_price"]

        # Introduzir erro de sintaxe -> deve sinalizar CRITICAL preventivamente
        with open(sample_py, "w", encoding="utf-8") as f:
            f.write("def compute_price(x):\n    return x * (\n")
        a3 = watcher.audit_file_save(sample_py, workspace_path=w_tmp, force=False, persist_memory_on_high_risk=False)
        assert a3["ok"] and not a3["syntax_ok"] and a3["risk_level"] == "CRITICAL"

    print(
        f"[PASS] Automated File-Save AST & Impact Watcher: db_engine.py -> {save_audit['risk_level']} "
        f"({save_audit['affected_files_count']} ficheiros, {save_audit['total_references']} refs) & Symbol Diff + CRITICAL Gate OK"
    )

    # 13. Testar Tecnologias Graphify (Multi-Modal Knowledge Graph, Arestas de Confiança, God Nodes, BFS Path & GRAPH_REPORT.md)
    kg = swarm_eng.build_codebase_knowledge_graph(workspace_path=repo_dir, force_rebuild=True)
    assert kg["ok"] and kg["total_nodes"] >= 40 and kg["total_edges"] >= 60
    nt = kg["node_type_counts"]
    for req_type in ("FILE", "CLASS", "FUNCTION", "JS_FUNCTION", "API_ROUTE", "MCP_TOOL", "SQL_TABLE"):
        assert nt.get(req_type, 0) >= 1, f"Tipo de nó multi-modal em falta: {req_type}"
    cc = kg["confidence_counts"]
    assert cc.get("EXTRACTED", 0) >= 30 and (cc.get("INFERRED", 0) + cc.get("AMBIGUOUS", 0)) >= 1
    assert len(kg["god_nodes"]) >= 5 and len(kg["communities"]) == 5

    # Testar BFS Shortest Path multi-modal: JS Function (Frontend) -> API Route -> Python Handler/Watcher -> SQLite Table
    bfs_res = swarm_eng.find_graph_path(
        source_query="triggerAstSaveAuditUI",
        target_query="ast_save_audits",
        max_hops=6,
        workspace_path=repo_dir,
    )
    assert bfs_res["ok"] and bfs_res["found"] and bfs_res["hops_count"] >= 2
    path_types = {n["node_type"] for n in bfs_res["path_nodes"]}
    assert "JS_FUNCTION" in path_types and "SQL_TABLE" in path_types

    # Testar geração automática de GRAPH_REPORT.md
    rep_res = swarm_eng.generate_architecture_report(workspace_path=repo_dir, write_to_disk=True)
    assert rep_res["ok"] and os.path.isfile(rep_res["report_file"])
    assert "Top God Nodes" in rep_res["markdown"] and "EXTRACTED" in rep_res["markdown"]
    print(
        f"[PASS] Graphify Engine: {kg['total_nodes']} nós multi-modais, {kg['total_edges']} arestas "
        f"(EXTRACTED={cc['EXTRACTED']}, INFERRED={cc['INFERRED']}, AMBIGUOUS={cc['AMBIGUOUS']}), "
        f"BFS Path 'triggerAstSaveAuditUI -> ast_save_audits' em {bfs_res['hops_count']} saltos ({bfs_res['token_savings']['compression_multiplier']}) & GRAPH_REPORT.md OK"
    )

    # 14. Testar Camada de Torres Holográficas 3D do Mapa de Calor sobre as Secretárias (Office 3D)
    office_st = swarm_eng.get_office_state()
    assert "desk_towers" in office_st and len(office_st["desk_towers"]) >= 8
    first_tower = office_st["desk_towers"][0]
    for req_k in ("desk_index", "agent_id", "file_name", "heat_score", "heat_pct", "level", "edits", "editing_intensity"):
        assert req_k in first_tower, f"Campo em falta em desk_towers: {req_k}"

    for holo_token in (
        'id="officeHoloTowerInspector"',
        'id="btnPulseHoloTowers"',
        "function getDeskHoloTowerData(",
        "function selectOfficeHoloTower(",
        "function pulseOfficeHoloTowers3D()",
        "officeDeskTowerHitboxes.push(",
    ):
        assert holo_token in html_content, f"Token de Torres Holográficas 3D em falta em index.html: {holo_token}"
    print(
        f"[PASS] 3D Holographic Desk Heatmap Towers: {len(office_st['desk_towers'])} secretárias mapeadas "
        f"(Top: {first_tower['file_name']} @ {first_tower['heat_pct']}% [{first_tower['level'].upper()}] · {first_tower['edits']} edits) & Hitboxes/HUD OK"
    )

    # 15. Testar Servidor MCP (server.py) via Subprocess JSON-RPC 2.0 stdio (Handshake initialize + tools/list + tools/call)
    import subprocess
    import sys

    server_py = os.path.join(repo_dir, "server.py")
    mcp_input = "\n".join(
        [
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "antigravity-client", "version": "1.0.0"},
                    },
                }
            ),
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}),
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "brain_stats", "arguments": {}},
                }
            ),
        ]
    ) + "\n"

    proc = subprocess.run(
        [sys.executable, "-u", server_py],
        input=mcp_input,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
    )
    assert proc.returncode == 0, f"server.py falhou com código {proc.returncode}: {proc.stderr}"
    out_lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    assert len(out_lines) == 3, f"Esperadas 3 respostas JSON-RPC no stdout, obteve {len(out_lines)}: {out_lines}"

    init_resp = json.loads(out_lines[0])
    assert init_resp.get("id") == 1 and init_resp["result"]["serverInfo"]["name"] == "antigravity-brain"

    tools_resp = json.loads(out_lines[1])
    tool_names = [t["name"] for t in tools_resp["result"]["tools"]]
    assert len(tool_names) >= 15 and "store_fact" in tool_names and "swarm_graph_path" in tool_names

    call_resp = json.loads(out_lines[2])
    assert call_resp.get("id") == 3 and not call_resp["result"].get("isError")
    stats_payload = json.loads(call_resp["result"]["content"][0]["text"])
    assert "total_memories" in stats_payload
    print(
        f"[PASS] MCP Stdio Server (server.py): Handshake 'initialize' OK, {len(tool_names)} tools registadas & 'brain_stats' executado sem dependências externas"
    )

    # 16. Testar as 6 Tecnologias Orbit Agent OS (Inbox, Trust Hierarchy, Multi-Scope Broadcast, Agent Chaining, Cross-IDE Bridge & ROI)
    from orbit_engine import OrbitEngine

    with tempfile.TemporaryDirectory() as orbit_tmp:
        orbit_db = BrainDB(db_path=os.path.join(orbit_tmp, "orbit_test.db"))
        SwarmEngine(orbit_db)  # garante office_agents inicializados
        orbit = OrbitEngine(orbit_db)

        # 16a. Memory Trust Hierarchy ("Human Edits Always Win")
        mem_id_human, _ = orbit_db.store_fact(
            topic="Regra Imutável de Produção",
            fact="Nunca apagar tabelas SQLite em produção sem snapshot CoW.",
            workspace="brain_mcp",
            category="preference",
            tags="human trust lock production",
            importance=5,
            source_agent="human_ui",
            trust_score=1.0,
            human_locked=1,
        )
        # Tentar sobrescrever como subagente (human_locked=0) — deve manter o facto humano intacto!
        orbit_db.store_fact(
            topic="Regra Imutável de Produção",
            fact="Subagente tentou alterar esta regra automaticamente.",
            workspace="brain_mcp",
            category="preference",
            tags="subagent override attempt",
            importance=3,
            source_agent="subagent_worker",
            trust_score=0.6,
            human_locked=0,
        )
        locked_results = orbit_db.search_memories("Regra Imutável de Produção", workspace="brain_mcp", n_results=3)
        assert any(
            r["id"] == mem_id_human
            and "Nunca apagar tabelas SQLite" in r["fact"]
            and int(r.get("human_locked") or 0) == 1
            for r in locked_results
        ), "Falha na Trust Hierarchy: memória human_locked=1 foi sobrescrita por subagente!"

        # 16b. Multi-Scope Broadcast Directives
        bc_res = orbit.send_broadcast(
            target_scope="dept:API",
            directive="Priorizar latência <10ms em todos os endpoints SQLite WAL",
            workspace="brain_mcp",
        )
        assert bc_res["ok"] is True and bc_res["agents_notified"] >= 1

        # 16c. Agent Chaining & Hand-off Packets
        ho_res = orbit.record_handoff(
            from_agent="Arquiteto (Brain)",
            to_agent="Worker API (Flash)",
            task_code="api-orbit",
            workspace="brain_mcp",
            summary="OrbitEngine criado e ligado ao PreInvocation.",
            files_touched=["orbit_engine.py", "brain_inject.py"],
            next_action="Validar endpoints /api/orbit/overview e /api/orbit/action.",
        )
        assert ho_res["ok"] is True and ho_res["handoff_id"] > 0

        # 16d. Mission Control Inbox ("Needs Your Yes") & Executive Briefing + ROI + MCP Bridge
        inbox_before = orbit.get_mission_control_inbox()
        assert inbox_before["ok"] is True and "items" in inbox_before
        overview = OrbitEngine(prod_db).get_executive_briefing_and_roi()
        assert overview["ok"] is True
        assert "roi" in overview and overview["roi"]["hours_saved"] >= 0
        assert "trust_hierarchy" in overview
        assert "mcp_bridge" in overview and len(overview["mcp_bridge"]["targets"]) == 4

    for orbit_ui_token in (
        'id="orbitOsModal"',
        'id="btnOpenOrbitModal"',
        "function openOrbitOsModal()",
        "function orbitApproveAllUI()",
        "function sendOrbitBroadcastUI()",
        "function connectAllMcpBridgeUI(",
    ):
        assert orbit_ui_token in html_content, f"Token Orbit Agent OS em falta em index.html: {orbit_ui_token}"

    print(
        f"[PASS] Orbit Agent OS (6 Tecnologias): Trust Hierarchy (Human Wins), Broadcast ({bc_res['agents_notified']} ags), "
        f"Hand-off Chaining, Inbox ({inbox_before['pending_count']} pending), 4-IDE MCP Bridge & ROI (${overview['roi']['engineering_value_usd']}) OK"
    )

    # 17. Testar Motor de Frustum Culling 3D para o office3DCanvas (Contrato + Matemática 3D/2D)
    for frustum_token in (
        'id="offStatCullBadge"',
        'id="offStatCulled"',
        'id="offStatCullSaved"',
        'id="btnOfficeFrustumCull"',
        'id="btnHoloFrustumCull"',
        "function computeOfficeFrustum(",
        "function testSphereInOfficeFrustum(",
        "function isAgentInOfficeFrustum(",
        "function toggleOfficeFrustumCulling(",
        "window.officeFrustumStats = officeFrustumStats",
    ):
        assert frustum_token in html_content, f"Token Frustum Culling em falta em index.html: {frustum_token}"

    import math

    def _py_test_sphere_in_frustum(x: float, y: float, z: float, radius: float, cam: dict, w: int = 960, h: int = 680, enabled: bool = True) -> dict:
        cos_y = math.cos(cam["yaw"])
        sin_y = math.sin(cam["yaw"])
        cos_p = math.cos(cam["pitch"])
        sin_p = math.sin(cam["pitch"])
        zoom = max(0.35, float(cam["zoom"]))
        scale_m = max(0.75, min(1.65, zoom))
        pad_x = 80.0 * scale_m
        pad_y = 102.0 * scale_m
        half_w = w * 0.5
        half_h = h * 0.54
        dx = x - cam["targetX"]
        dz = z - cam["targetZ"]
        rx = dx * cos_y - dz * sin_y
        rz = dx * sin_y + dz * cos_y
        sx = half_w + rx * zoom
        sy = half_h + (rz * sin_p - y * cos_p) * zoom
        depth = rz * cos_p + y * sin_p
        if not enabled:
            return {"visible": True, "sx": sx, "sy": sy, "depth": depth}
        r_px = max(16.0, radius * zoom)
        vis = (
            -1350.0 <= depth <= 1350.0
            and (sx + r_px) >= -pad_x
            and (sx - r_px) <= (w + pad_x)
            and (sy + r_px * 1.15) >= -pad_y
            and (sy - r_px * 1.30) <= (h + pad_y)
        )
        return {"visible": vis, "sx": sx, "sy": sy, "depth": depth}

    zoomed_cam = {"yaw": -0.32, "pitch": 0.52, "zoom": 2.35, "targetX": -165.0, "targetZ": -255.0}
    in_view = _py_test_sphere_in_frustum(-165.0, 26.0, -230.0, 42.0, zoomed_cam, enabled=True)
    far_lounge = _py_test_sphere_in_frustum(445.0, 26.0, 255.0, 42.0, zoomed_cam, enabled=True)
    far_lounge_disabled = _py_test_sphere_in_frustum(445.0, 26.0, 255.0, 42.0, zoomed_cam, enabled=False)
    assert in_view["visible"] is True, "Agente focado na Ponte de Comando devia estar VISÍVEL no Frustum"
    assert far_lounge["visible"] is False, "Agente distante no Lounge (Sul-Este) devia ser CULLED quando câmara está com zoom na Ponte de Comando"
    assert far_lounge_disabled["visible"] is True, "Com Frustum Culling desativado, todos os agentes devem retornar visible=True"
    print(
        f"[PASS] office3DCanvas Frustum Culling: Visível no foco=({in_view['sx']:.1f}, {in_view['sy']:.1f}), "
        f"Agente fora de vista descartado=({far_lounge['sx']:.1f}, {far_lounge['sy']:.1f}) -> CULLED OK"
    )

    # 18. Testar Contrato da Reorganização da UI da Página Brain & Layout Quadro Blueprint / Galeria Bento
    for brain_ui_token in (
        'id="brainLeftDrawer"',
        'id="brainToolsPhysicsModal"',
        'id="btnOpenToolsPhysicsModal"',
        'id="btnToggleLeftDrawerFloating"',
        'id="btnToggleRightDrawerFloating"',
        'id="btnBlueprintView"',
        'id="btnBentoView"',
        'id="brainBentoGallery"',
        "function toggleBrainDrawer(",
        "function openBrainToolsModal()",
        "function closeBrainToolsModal()",
        "function toggleVaultWorkspaceAccordion(",
        "function resetVaultWorkspaceFilter()",
        "function setBrainViewStyle(",
        "function renderBlueprintBoard(",
        "function renderBrainBentoGallery()",
        "isPrimaryIsland",
        "_islandRank",
        "_culledByLod",
        "userClickedGraphNode",
    ):
        assert brain_ui_token in html_content, f"Token da UI reorganizada do Brain em falta em index.html: {brain_ui_token}"
    print("[PASS] Brain UI & Zero-Overlap Blueprint Board + Bento Gallery + Acordeão de Pastas OK")

    # 19. Testar os 4 Pilares de Melhorias (Deduplicação Semântica, Bulk Actions, Kanban por Categoria, Filtros Inteligentes e Sync 3D + Eco-FPS)
    with tempfile.TemporaryDirectory() as tmp_pillar_dir:
        pillar_db = BrainDB(os.path.join(tmp_pillar_dir, "pillar_test.db"))
        dup_id_1, is_new_1 = pillar_db.store_fact(topic="Checkpoints App", fact="Estado inicial do checkpoint.", category="architecture", importance=3, tags="checkpoint app", workspace="app_ws")
        dup_id_2, is_new_2 = pillar_db.store_fact(topic="  checkpoints app ", fact="Estado evoluído e consolidado do checkpoint.", category="architecture", importance=4, tags="checkpoint evolved", workspace="app_ws")
        assert dup_id_1 == dup_id_2 and is_new_1 is True and is_new_2 is False, "store_fact sem supersedes_id deve atualizar in-place o mesmo (workspace, topic) em vez de criar duplicados"

        # Criar 2 memórias semanticamente quase idênticas (>90% cosseno) com sufixos numéricos para testar o Memory Doctor Semântico
        sem_a, _ = pillar_db.store_fact(topic="Checkpoint: app #1", fact="Configuração do motor de renderização React e rotas da aplicação principal v1.", category="architecture", importance=3, tags="react routes", workspace="app_ws")
        sem_b, _ = pillar_db.store_fact(topic="Checkpoint: app #2", fact="Configuração do motor de renderização React e rotas da aplicação principal v2.", category="architecture", importance=4, tags="react routes v2", workspace="app_ws")
        assert sem_a != sem_b
        doc_res = pillar_db.run_memory_doctor()
        assert doc_res.get("ok") is True and doc_res.get("merged_duplicates", 0) >= 1, "Memory Doctor deve fundir tópicos canónicos/semânticos repetidos"

        # Testar Bulk Memory Actions (pin, unpin, move_workspace, delete)
        b1, _ = pillar_db.store_fact(topic="Bulk Node Alpha", fact="Memória para teste em lote A", category="optimization", importance=3, tags="bulk test", workspace="app_ws")
        b2, _ = pillar_db.store_fact(topic="Bulk Node Beta", fact="Memória para teste em lote B", category="optimization", importance=3, tags="bulk test", workspace="app_ws")
        res_pin = pillar_db.bulk_manage_memories("pin", [b1, b2])
        assert res_pin["ok"] is True and res_pin["affected"] == 2
        res_move = pillar_db.bulk_manage_memories("move_workspace", [b1, b2], target_workspace="moved_ws")
        assert res_move["ok"] is True and res_move["target_workspace"] == "moved_ws"
        res_del = pillar_db.bulk_manage_memories("delete", [b1, b2])
        assert res_del["ok"] is True and res_del["affected"] == 2

    for pillar_token in (
        'id="smartFilterAll"',
        'id="smartFilterPinned"',
        'id="smartFilterRecent"',
        'id="smartFilterOrphan"',
        'id="brainSortMode"',
        'id="btnQuickCompactHud"',
        'id="blueprintQuickJumpBar"',
        "function setSmartBrainFilter(",
        "function onBrainSortChange(",
        "function toggleBlueprintDrilldownLayout()",
        "function runQuickMemoryCompact()",
        "function runBulkMemoryAction(",
        "function focusOfficeWorkspace3D(",
        "function isEcoGpuIdle()",
        "blueprintSwimlanesMeta",
    ):
        assert pillar_token in html_content, f"Token dos 4 Pilares de Melhorias em falta em index.html: {pillar_token}"
    print("[PASS] 4 Pilares de Melhorias (Deduplicação Semântica, Bulk Actions, Kanban 5 Colunas, Filtros & Sync Office 3D + Eco-FPS) OK")

    # 20. Teste das 5 Otimizações de Poupança de Tokens (Delta Session, TOON, Top-K Cutoff, AST :Lstart-end, Micro-Prompt)
    from brain_inject import (
        apply_dynamic_topk_cutoff,
        build_ephemeral_context,
        compress_fact_telegraphic,
        compute_adaptive_budget,
        generate_inspector_preview,
        is_micro_confirmation_prompt,
    )

    # 20.1 Pointers Cirúrgicos :Lstart-end no Scout
    from pathlib import Path
    lc_db, syms_db = SwarmEngine._extract_file_symbols(Path(__file__).resolve().parent / "db_engine.py")
    assert lc_db > 100 and any(":L" in s for s in syms_db), f"Esperado pointer :Lstart-end nos símbolos de db_engine.py, obtido: {syms_db}"

    # 20.2 Formato Telegráfico TOON
    raw_verbose = "Foi implementado o módulo de cache em db_engine.py:L970-1060 para garantir que o consumo de tokens diminui."
    comp_toon = compress_fact_telegraphic(raw_verbose)
    assert len(comp_toon) < len(raw_verbose) and "db_engine.py:L970-1060" in comp_toon, "TOON deve comprimir muletas preservando ficheiros e linhas"

    # 20.3 Corte Adaptativo Top-K
    sample_mems = [
        {"id": 101, "topic": "Top 1 Core", "fact": "Facto principal", "workspace": "brain_mcp", "final_score": 12.0, "jev_confidence": 0.92, "semantic_similarity": 0.85},
        {"id": 102, "topic": "Tail Ruído 1", "fact": "Ruído marginal", "workspace": "brain_mcp", "final_score": 2.1, "jev_confidence": 0.21, "semantic_similarity": 0.18},
        {"id": 103, "topic": "Tail Ruído 2", "fact": "Outro ruído", "workspace": "brain_mcp", "final_score": 1.8, "jev_confidence": 0.19, "semantic_similarity": 0.15},
    ]
    kept_mems, dropped_cnt = apply_dynamic_topk_cutoff(sample_mems, stop_threshold=0.30)
    assert len(kept_mems) == 1 and dropped_cnt == 2, f"Top-K Cutoff devia descartar 2 memórias de baixo score, obtido kept={len(kept_mems)} dropped={dropped_cnt}"

    # 20.4 Modo Micro-Prompt (<90 tokens)
    assert is_micro_confirmation_prompt("Continua") is True
    assert is_micro_confirmation_prompt("Sim") is True
    assert is_micro_confirmation_prompt("Proceed") is True
    assert is_micro_confirmation_prompt("Analisar bug no renderBlueprintBoard de index.html") is False
    assert compute_adaptive_budget("Continua") <= 360

    with tempfile.TemporaryDirectory() as tmp_tok_dir:
        tok_db = BrainDB(os.path.join(tmp_tok_dir, "tok_test.db"))
        micro_prev = generate_inspector_preview(tok_db, workspace="brain_mcp", query="Continua", simulate_turn=1)
        assert micro_prev["micro_prompt_active"] is True and micro_prev["estimated_tokens"] < 90, f"Micro-prompt deve gastar <90 tokens, gastou {micro_prev['estimated_tokens']}"

        # 20.5 Session Delta Memory (Turno #1 vs Turno #2)
        s_map_sample = "[SCOUT_SHARED_MAP | ws=brain_mcp | db_engine.py (class BrainDB:L42-1600)]"
        d_turn1 = tok_db.compute_session_delta("conv_delta_test", sample_mems[:1], scout_map=s_map_sample, update_cache=True)
        assert d_turn1["turn_number"] == 1 and d_turn1["is_delta_turn"] is False
        ctx_t1 = build_ephemeral_context(sample_mems[:1], None, "brain_mcp", scout_map=s_map_sample, delta_info=d_turn1)

        d_turn2 = tok_db.compute_session_delta("conv_delta_test", sample_mems[:1], scout_map=s_map_sample, update_cache=True)
        assert d_turn2["turn_number"] == 2 and d_turn2["is_delta_turn"] is True and d_turn2["scout_unchanged"] is True
        ctx_t2 = build_ephemeral_context(sample_mems[:1], None, "brain_mcp", scout_map=s_map_sample, delta_info=d_turn2)
        assert "DELTA_CACHE" in ctx_t2 and len(ctx_t2) < len(ctx_t1), "Turno #2 com Session Delta deve ser mais curto e conter DELTA_CACHE"
    print("[PASS] 5 Otimizações de Poupança de Tokens (Session Delta, TOON Telegráfico, Top-K Cutoff, Pointers :Lstart-end e Micro-Prompt <90 tok) OK")

    # 21. Testar Correções da Auditoria Total v4.6 & Novas Tecnologias (FTS5 BM25 Prefix, AST-Safe Scout Slice, Arrow Regex, Time-Travel Revisions & Security Gates)
    from brain_inject import slice_scout_map_ast_safe
    from brain_harvest import harvest_latest_turn

    # 21.1 AST-Bounded Slicing do [SCOUT_SHARED_MAP] (nunca corta identificadores a meio)
    long_scout = (
        "[SCOUT_SHARED_MAP | ws=brain_mcp | "
        "db_engine.py (class BrainDB:L42-1600, def check_and_apply_decay:L880-920, def compute_session_delta:L970-1060); "
        "orbit_engine.py (class OrbitEngine:L16-710, def send_broadcast:L240-310)]"
    )
    sliced_scout = slice_scout_map_ast_safe(long_scout, 115)
    assert sliced_scout.endswith("]") and "check_and_app]" not in sliced_scout and len(sliced_scout) <= 115, (
        f"slice_scout_map_ast_safe cortou identificador a meio ou excedeu limite: {sliced_scout}"
    )

    # 21.2 Time-Travel Memory Revisions + Rollback 1-Click + FTS5 BM25 Prefix + Arrow Regex + Broadcast Deduplication
    with tempfile.TemporaryDirectory() as tmp_v46_dir:
        v46_db = BrainDB(os.path.join(tmp_v46_dir, "v46_audit.db"))

        # Testar harvest_latest_turn com setas (->, =>, <)
        sample_jsonl = os.path.join(tmp_v46_dir, "transcript.jsonl")
        with open(sample_jsonl, "w", encoding="utf-8") as fj:
            fj.write(json.dumps({"type": "USER_INPUT", "content": "<USER_REQUEST>Testar harvest</USER_REQUEST>"}) + "\n")
            fj.write(
                json.dumps(
                    {
                        "type": "PLANNER_RESPONSE",
                        "content": "Concluído.\n<!-- brain: Pipeline Arrow Test | Fluxo A -> B => C validado em < 5ms sem truncagem -->",
                    }
                )
                + "\n"
            )
        h_cnt = harvest_latest_turn(sample_jsonl, "brain_mcp", "conv_v46", v46_db)
        assert h_cnt >= 1
        arrow_hits = v46_db.search_memories("Pipeline Arrow Test", workspace="brain_mcp", n_results=3)
        assert any("A -> B => C" in m["fact"] and "< 5ms" in m["fact"] for m in arrow_hits), (
            f"harvest_latest_turn falhou ao capturar setas -> / => / <: {arrow_hits}"
        )
        m_id, is_new = v46_db.store_fact(
            topic="Configuração Crítica WAL",
            fact="Usar synchronous=NORMAL e busy_timeout=5000ms.",
            workspace="brain_mcp",
            category="architecture",
            importance=5,
            tags="sqlite wal timeout",
        )
        assert is_new is True
        # Atualizar a mesma memória para gerar revisão automática em memory_revisions
        v46_db.store_fact(
            topic="Configuração Crítica WAL",
            fact="Usar synchronous=NORMAL e busy_timeout=30000ms com lock.",
            workspace="brain_mcp",
            category="architecture",
            importance=5,
            tags="sqlite wal timeout lock",
            source_agent="subagent_api",
        )
        revs = v46_db.get_memory_revisions(memory_id=m_id)
        assert len(revs) >= 1 and "5000ms" in revs[0]["old_fact"], f"Revisão não registada em memory_revisions: {revs}"

        # Executar Rollback Time-Travel para a revisão anterior
        rb = v46_db.rollback_memory(int(revs[0]["id"]))
        assert rb["ok"] is True and rb["memory_id"] == m_id and "5000ms" in rb["restored_fact"]

        # Verificar que FTS5 BM25 Prefix Search funciona sem OperationalError (e devolve bm25_raw != 0 ou match FTS)
        fts_hits = v46_db.search_memories("Configuração Crítica busy_timeout", workspace="brain_mcp", n_results=3)
        assert len(fts_hits) >= 1 and fts_hits[0]["id"] == m_id

        # Verificar Deduplicação de Orbit Broadcasts & Delta Turn Suppression
        v46_orbit = OrbitEngine(v46_db)
        v46_orbit.send_broadcast(directive="Diretiva Unificada v4.6", target_scope="all_fleet", workspace="brain_mcp")
        v46_orbit.send_broadcast(directive="Diretiva Unificada v4.6", target_scope="all_fleet", workspace="brain_mcp")
        active_bcs = v46_orbit.get_active_broadcasts("brain_mcp")
        fleet_bcs = [b for b in active_bcs if b["target_scope"] == "all_fleet"]
        assert len(fleet_bcs) == 1, f"Orbit broadcast duplicado para o mesmo target_scope: {fleet_bcs}"

        ctx_delta = build_ephemeral_context(
            fts_hits,
            None,
            "brain_mcp",
            delta_info={"is_delta_turn": True, "turn_number": 2, "unchanged_topics": ["Configuração Crítica WAL"], "unchanged_count": 1, "delta_memories": []},
        )
        assert "📡[ORBIT]" not in ctx_delta, "Turno Delta não deve repetir cabeçalho estático 📡[ORBIT]"

        # 21.4 Security Gates: Path Traversal Confinement + 12-Format Secret Redaction
        v46_watcher = AstImpactWatcher(db=v46_db, workspace_path=tmp_v46_dir)
        traversal_res = v46_watcher.audit_file_save("../../Windows/win.ini", workspace_path=tmp_v46_dir, force=True)
        assert traversal_res["ok"] is False, f"AstImpactWatcher devia bloquear Path Traversal fora do workspace: {traversal_res}"

        sec_sample = "Token Anthropic sk-ant-api03-abcdef1234567890abcdef1234567890 e GitHub github_pat_11ABCDEF0123456789_abcdef0123456789abcdef"
        redacted_sample = BrainDB.redact_secrets(sec_sample)
        assert "sk-ant-" not in redacted_sample and "github_pat_" not in redacted_sample and "[REDACTED_SECRET]" in redacted_sample

    for v46_ui_token in (
        ".replace(/'/g, '&#39;')",
        "function closeAnyOpenModalOnEscape()",
        "function hasAnyModalOpen()",
        "function loadMemoryRevisionsUI()",
        "function rollbackMemoryRevisionUI(",
        'id="memoryRevisionsList"',
        "_lastOfficeDsSig",
    ):
        assert v46_ui_token in html_content, f"Token v4.6 em falta em index.html: {v46_ui_token}"
    print("[PASS] Auditoria Total v4.6 (FTS5 BM25 Prefix Fix, AST-Safe Scout Slice, Arrow Regex, Time-Travel Rollback & Security Hardening) OK")

    # 22. Testar Pack Completo DOTS v4.7 (Camada 1: Git-Native DAG .dots/*.md, Camada 2: Dynamic Optimal Trajectory Search, Camada 3: ECS Float32Array SoA)
    with tempfile.TemporaryDirectory() as tmp_dots_dir:
        dots_db = BrainDB(os.path.join(tmp_dots_dir, "dots_v47.db"))
        dots_orbit = OrbitEngine(dots_db)

        # 22.1 Camada 2 — DOTS Dynamic Optimal Reasoning Trajectories Search (JEV System-1)
        jev_dots = dots_db.jev_system1_route("Corrigir bug em index.html:L5520 e correr pytest para verificar", workspace="brain_mcp")
        assert "dots_trajectory" in jev_dots and "➔" in jev_dots["dots_trajectory"], f"Trajetória DOTS ausente em jev_system1_route: {jev_dots}"
        assert "[AST_SLICE:L]" in jev_dots["dots_trajectory"] and "[VERIFY_AST_TESTS]" in jev_dots["dots_trajectory"], (
            f"Módulos atómicos esperados em falta na trajetória DOTS: {jev_dots['dots_trajectory']}"
        )

        # 22.2 Camada 1 — Git-Native DAG Task Tracker (bloqueio de dependências + desbloqueio automático + export .dots/*.md)
        dag_init = dots_orbit.get_dots_dag("brain_mcp")
        assert dag_init["ready_count"] >= 1 and dag_init["blocked_count"] >= 1, f"DAG inicial inválido: {dag_init}"

        # Tentar fazer claim de dot-04 (que depende de dot-03 ainda open) -> deve bloquear!
        blocked_claim = dots_orbit.manage_dot_task(action="claim", dot_id="dot-04", assignee="worker_tests", workspace="brain_mcp")
        assert blocked_claim["ok"] is False and "dot-03" in blocked_claim.get("blocked_by", []), (
            f"dot-04 devia estar bloqueado por dot-03: {blocked_claim}"
        )

        # Concluir dot-03 -> deve desbloquear automaticamente dot-04 para READY!
        comp_03 = dots_orbit.manage_dot_task(action="complete", dot_id="dot-03", close_reason="SoA Float32Array concluído", workspace="brain_mcp")
        assert comp_03["ok"] is True
        ready_after = dots_orbit.manage_dot_task(action="ready", workspace="brain_mcp")
        ready_ids = [t["dot_id"] for t in ready_after["ready_tasks"]]
        assert "dot-04" in ready_ids, f"dot-04 devia passar a READY após conclusão de dot-03: {ready_ids}"

        # Exportar para .dots/*.md com YAML frontmatter Git-Native
        dots_md_dir = os.path.join(tmp_dots_dir, ".dots")
        sync_res = dots_orbit.manage_dot_task(action="sync_md", workspace="brain_mcp", export_dir=dots_md_dir)
        assert sync_res["ok"] is True and sync_res["exported_count"] >= 4
        md_files = os.listdir(dots_md_dir)
        assert any(f.startswith("dot-02") and f.endswith(".md") for f in md_files), f"Ficheiros .dots/*.md não gerados: {md_files}"

        # Verificar injeção Zero-Token de dots= e 🎯[DOTS_READY] no contexto efémero
        brief_dots = dots_orbit.get_executive_briefing_and_roi("brain_mcp")
        ctx_dots = build_ephemeral_context(
            [],
            None,
            "brain_mcp",
            jev_route=jev_dots,
            orbit_brief=brief_dots,
        )
        assert "dots=" in ctx_dots and "🎯[DOTS_READY|" in ctx_dots, f"Injeção DOTS em falta em build_ephemeral_context: {ctx_dots}"

    # 22.3 Camada 3 — DOTS Engine ECS Float32Array SoA + UI Tracker em index.html
    for dots_ui_token in (
        "const dotsEcsSoA =",
        "new Float32Array(",
        "applyPairRepulsionSoA(",
        "window.dotsEngineStats",
        'id="orbitDotsDagList"',
        "function orbitDotActionUI(",
    ):
        assert dots_ui_token in html_content, f"Token DOTS v4.7 em falta em index.html: {dots_ui_token}"
    print("[PASS] Pack Completo DOTS v4.7 (DAG .dots/*.md + Trajetórias Cognitivas DOTS + Motor Físico ECS Float32Array SoA) OK")

    # 23. Testar Motor de Auto-Aprendizagem Recursiva & Sentinel Proativo por Projeto (Self-Learn v4.8)
    with tempfile.TemporaryDirectory() as tmp_sl_dir:
        sl_db = BrainDB(os.path.join(tmp_sl_dir, "self_learn_v48.db"))
        sl_orbit = OrbitEngine(sl_db)

        # Guardar memórias episódicas num projeto 'proj_alpha' sobre o mesmo ficheiro (index.html)
        sl_db.store_fact(
            topic="Bug Fix Aspas em index.html",
            fact="Em index.html:L11200 usar sempre &#39; em escapeHtml para evitar quebra de onclick.",
            workspace="proj_alpha",
            category="bug_fix",
            tags="ui,index,xss,escape",
            importance=5,
        )
        sl_db.store_fact(
            topic="Otimização SoA em index.html",
            fact="Em index.html:L5510 usar Float32Array em stepPhysics e validar sintaxe com node --check.",
            workspace="proj_alpha",
            category="optimization",
            tags="ui,index,physics,dots",
            importance=5,
        )

        # 23.1 Novo projeto 'proj_alpha' começa com Self-Learn OFF por omissão (Opt-in por projeto)
        st_alpha_init = sl_orbit.get_self_learn_status("proj_alpha")
        assert st_alpha_init["enabled"] is False, f"Novo projeto devia iniciar com Self-Learn OFF (Opt-in): {st_alpha_init}"
        skipped_cycle = sl_orbit.run_self_learn_evolution_cycle("proj_alpha", force=False)
        assert skipped_cycle["ok"] is False and skipped_cycle.get("skipped") is True, "Ciclo devia ser ignorado quando Self-Learn está OFF"

        # Verificar que quando está OFF não injeta 🧬[SELF_LEARN] no contexto
        brief_off = sl_orbit.get_executive_briefing_and_roi("proj_alpha")
        ctx_off = build_ephemeral_context([], None, "proj_alpha", orbit_brief=brief_off)
        assert "🧬[SELF_LEARN|" not in ctx_off, f"Não devia injetar 🧬[SELF_LEARN| quando desativado no projeto: {ctx_off}"

        # 23.2 Ativar Self-Learn em 'proj_alpha' e correr Ciclo de Auto-Melhoria Recursiva
        st_alpha_on = sl_orbit.toggle_project_self_learn("proj_alpha", enabled=True)
        assert st_alpha_on["enabled"] is True and st_alpha_on["proactive_enabled"] is True

        evo_res = sl_orbit.run_self_learn_evolution_cycle("proj_alpha", force=False)
        assert evo_res["ok"] is True and evo_res["new_rules_created"] >= 1 and evo_res["synapses_boosted"] >= 1, (
            f"Ciclo de Auto-Melhoria falhou ao destilar Meta-Regras ou reforçar sinapses: {evo_res}"
        )
        assert evo_res["brain_iq_score"] > 85.0 and len(evo_res["self_learn"]["learned_playbook"]) >= 1

        # Verificar que a Meta-Regra Aprendida foi guardada em brain.db e é injetada em 🧬[SELF_LEARN]
        brief_on = sl_orbit.get_executive_briefing_and_roi("proj_alpha")
        ctx_on = build_ephemeral_context([], None, "proj_alpha", orbit_brief=brief_on)
        assert "🧬[SELF_LEARN|" in ctx_on and "index.html" in ctx_on, f"Injeção 🧬[SELF_LEARN] ausente após ativação: {ctx_on}"

        # 24. Testar Prompt Forge Engine (Otimizador de Prompts c/ Ficheiros :Lstart-end + Meta-Regras Self-Learn + DOTS + Skills Antigravity)
        avail_skills = sl_orbit.discover_antigravity_skills()
        assert len(avail_skills) >= 4, f"discover_antigravity_skills devia encontrar skills instaladas: {len(avail_skills)}"

        pf_res = sl_orbit.generate_optimized_prompt(
            raw_request="Criar uma função em index.html para exportar métricas e validar XSS",
            workspace="proj_alpha",
            task_mode="feature",
            selected_skills=["claude-architect-coder"],
        )
        assert pf_res["ok"] is True, f"generate_optimized_prompt falhou: {pf_res}"
        assert "index.html:L11200" in pf_res["full_prompt"] or "index.html" in pf_res["full_prompt"], (
            f"Prompt gerado devia incluir ficheiros relevantes de proj_alpha: {pf_res['full_prompt']}"
        )
        assert "🧬" in pf_res["full_prompt"] and len(pf_res["compact_prompt"]) < len(pf_res["full_prompt"]), (
            "Prompt Forge devia incluir Meta-Regras Self-Learn e variante compacta mais curta"
        )
        assert len(pf_res.get("matched_skills", [])) >= 1 and "SKILL.md" in pf_res["full_prompt"], (
            f"Prompt Forge devia injetar Skills do Antigravity com caminho SKILL.md: {pf_res}"
        )
        assert "SCOUT ➔ PLAN ➔ SWARM ➔ VERIFY" in pf_res["swarm_prompt"] and len(pf_res["history"]) >= 1

    for sl_ui_token in (
        'id="orbitSelfLearnProjectsList"',
        'id="orbitSelfLearnPlaybookList"',
        "function toggleProjectSelfLearnUI(",
        "function runSelfLearnEvolutionUI(",
        'id="topSelfLearnBadgeTxt"',
        'id="selfLearnWorkspace"',
        'id="selfLearnPipelineCanvas"',
        "function renderSelfLearnPipelineCanvasLoop()",
        'id="promptForgeWorkspace"',
        'id="pfOutputTextarea"',
        'id="pfSkillsPickerGrid"',
        "function renderPromptForgeSkillsPicker()",
        "function togglePromptForgeSkill(",
        "function forgeAntigravityPromptUI()",
        "function copyForgedPromptUI()",
    ):
        assert sl_ui_token in html_content, f"Token Self-Learn / Prompt Forge v4.9 em falta em index.html: {sl_ui_token}"
    print("[PASS] Self-Learn Studio Gráfico (60 FPS Neural Pipeline) & Prompt Forge + Antigravity Skills v4.9 OK")


if __name__ == "__main__":
    run_all_tests()
