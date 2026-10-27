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


if __name__ == "__main__":
    run_all_tests()




