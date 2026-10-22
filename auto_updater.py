import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict

REPO_DIR = Path(__file__).resolve().parent


def _run_git(args: list[str], timeout: int = 15) -> tuple[int, str]:
    try:
        creation_flags = 0x08000000 if os.name == "nt" else 0
        proc = subprocess.run(
            ["git", *args],
            cwd=str(REPO_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=timeout,
            creationflags=creation_flags,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode, out.strip()
    except Exception as e:
        return 1, str(e)


def get_git_status() -> Dict[str, Any]:
    """Devolve versão atual (commit SHA), branch, remote e se existem updates no GitHub."""
    if not (REPO_DIR / ".git").exists():
        return {
            "is_git_repo": False,
            "local_sha": "local",
            "branch": "main",
            "behind_count": 0,
            "auto_update_enabled": True,
        }

    _, sha = _run_git(["rev-parse", "--short", "HEAD"])
    _, branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    _, remote_url = _run_git(["remote", "get-url", "origin"])
    if not remote_url or "unknown" in remote_url.lower():
        _, remote_url = _run_git(["config", "--get", "remote.origin.url"])
    _, last_msg = _run_git(["log", "-1", "--pretty=%s (%cr)"])

    return {
        "is_git_repo": True,
        "local_sha": sha or "main",
        "branch": branch or "main",
        "remote_url": remote_url,
        "last_commit": last_msg,
        "auto_update_enabled": True,
    }


def check_and_apply_update(force_fetch: bool = True) -> Dict[str, Any]:
    """
    Verifica no GitHub (origin/main) se há novos commits.
    Se houver, faz git pull automático e re-sincroniza os hooks via install.py.
    """
    status = get_git_status()
    if not status.get("is_git_repo"):
        return {**status, "updated": False, "message": "Diretório ainda não ligado a Git."}

    branch = status.get("branch") or "main"
    if force_fetch:
        _run_git(["fetch", "origin", branch, "--quiet"], timeout=20)

    rc_b, behind_str = _run_git(["rev-list", f"HEAD..origin/{branch}", "--count"])
    behind = int(behind_str) if (rc_b == 0 and behind_str.isdigit()) else 0

    if behind <= 0:
        return {
            **status,
            "behind_count": 0,
            "updated": False,
            "message": f"Já estás na versão mais recente ({status.get('local_sha')}).",
        }

    # Aplicar git pull preservando brain.db local
    old_sha = status.get("local_sha")
    rc_pull, pull_out = _run_git(["pull", "--ff-only", "origin", branch], timeout=25)
    if rc_pull != 0:
        # Fallback seguro com autostash se o utilizador editou algum ficheiro
        rc_pull, pull_out = _run_git(
            ["pull", "--rebase", "--autostash", "origin", branch], timeout=25
        )

    # Re-executar configuração silenciosa de hooks para aplicar novidades
    try:
        from install import configure_hooks_and_plugin

        configure_hooks_and_plugin(silent=True)
    except Exception:
        pass

    new_status = get_git_status()
    return {
        **new_status,
        "behind_count": 0,
        "updated": rc_pull == 0,
        "old_sha": old_sha,
        "new_sha": new_status.get("local_sha"),
        "commits_pulled": behind,
        "message": (
            f"Atualizado com sucesso de {old_sha} para {new_status.get('local_sha')} (+{behind} commits)!"
            if rc_pull == 0
            else f"Erro ao atualizar: {pull_out}"
        ),
    }


def start_auto_update_daemon(interval_seconds: int = 1800) -> None:
    """
    Daemon silencioso que corre dentro do web_dashboard.py:
    Verifica se existem updates no GitHub ao arrancar (após 8s) e a cada 30 minutos.
    """

    def _loop() -> None:
        time.sleep(8)
        while True:
            try:
                check_and_apply_update(force_fetch=True)
            except Exception:
                pass
            time.sleep(interval_seconds)

    t = threading.Thread(target=_loop, daemon=True)
    t.start()


if __name__ == "__main__":
    if getattr(sys, "stdout", None) is not None and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    res = check_and_apply_update(force_fetch=True)
    print(res.get("message", res))
