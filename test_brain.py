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


if __name__ == "__main__":
    run_all_tests()
