"""git post-rewrite 훅 — rebase/amend로 재작성된 커밋을 세션 ledger에 승계한다.

stdin으로 `old_sha new_sha [extra-info]` 쌍(줄당 1쌍, git post-rewrite 규격)을
읽어, old_sha를 보유한 세션을 찾아 그 세션에 new_sha를 append한다(ledger의
`append_commit` 재사용). old_sha가 어느 세션에도 없으면 그 줄은 조용히
건너뛴다(다른 워크트리/외부 커밋 등 정상 케이스).

이 스크립트는 훅에서 `|| exit 0`로 감싸 실행되므로 항상 fail-open이지만,
원인 없는 swallow는 FOMS 규칙 위반이다 — 예상 못 한 실패는 harness 런타임
로그에 남긴다.

설계 정본: docs/plans/2026-07-27-session-worktree-isolation-phase1.md
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import session_commit_ledger as scl  # noqa: E402  (harness 디렉터리 sys.path 주입 후 임포트)

REWRITE_LOG = os.path.join("docs", "harness", "runtime", "record_rewrite_ledger.log")


def _project_root() -> str:
    """훅이 실행되는 워크트리(cwd)의 최상위 경로. 조회 실패 시 cwd로 대체."""
    proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True,
        text=True, encoding="utf-8", errors="replace",
    )
    top = (proc.stdout or "").strip()
    return top if proc.returncode == 0 and top else os.getcwd()


def _owning_session(ledger: dict, old_sha: str) -> str | None:
    """old_sha를 보유한 세션 id를 찾는다. 없으면 None.

    파라미터:
        ledger: `session_commit_ledger.load_ledger`가 반환한 원본 dict.
        old_sha: post-rewrite가 알려준 재작성 전 SHA.
    반환:
        세션 id, 또는 어느 세션도 보유하지 않으면 None.
    """
    for sid, entry in ledger.get("sessions", {}).items():
        if not isinstance(entry, dict):
            continue
        shas = [str(s) for s in (entry.get("shas") or []) if s]
        if scl.sha_in_list(old_sha, shas):
            return sid
    return None


def _log_failure(project_root: str, msg: str) -> None:
    """예상 못 한 실패를 harness 런타임 로그에 남긴다. 로그 자체 실패는 무시(훅 안정성 우선)."""
    try:
        path = os.path.join(project_root, REWRITE_LOG)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except OSError:
        pass


def process_rewrite(project_root: str, lines: list[str]) -> int:
    """post-rewrite stdin 라인들을 처리해 ledger를 승계한다.

    파라미터:
        project_root: ledger가 위치한 저장소(워크트리) 루트.
        lines: `old_sha new_sha [extra-info]` 형식의 줄 목록.
    반환:
        실제로 승계(append)한 줄 수.
    """
    ledger = scl.load_ledger(project_root)
    handled = 0
    for line in lines:
        parts = line.split()
        if len(parts) < 2:
            continue
        old_sha, new_sha = parts[0], parts[1]
        sid = _owning_session(ledger, old_sha)
        if sid is None:
            continue
        scl.append_commit(project_root, sid, new_sha)
        handled += 1
    return handled


def main() -> int:
    """훅 엔트리포인트: stdin 전체를 읽어 처리. 항상 0을 반환한다(fail-open)."""
    project_root = _project_root()
    try:
        lines = sys.stdin.read().splitlines()
        process_rewrite(project_root, lines)
    except Exception as exc:  # noqa: BLE001 - 훅 fail-open, 단 원인은 반드시 로그로 남긴다
        _log_failure(project_root, f"[error] record_rewrite_ledger 실패: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
