"""git post-rewrite 훅 — rebase/amend로 재작성된 커밋을 세션 ledger에 승계한다.

stdin으로 `old_sha new_sha [extra-info]` 쌍(줄당 1쌍, git post-rewrite 규격)을
읽어 **new_sha 기준으로 그룹핑**한 뒤, 그 그룹의 모든 old_sha가 **동일한 단일
세션 소유일 때만** new_sha를 그 세션에 append한다(ledger의 `append_commit`
재사용). squash/fixup은 `old1 new` / `old2 new`처럼 여러 old를 하나의 new로
접기 때문에, 줄 단위로 처리하면 소유한 첫 줄만 보고 승계해 나머지 old(타
세션·미보유)의 내용이 내 커밋으로 세탁된다 — 그룹 판정이 그 경로를 막는다.

승계하지 않은 그룹은 사유를 harness 런타임 로그에 남긴다. 조용히 무시하면
나중에 `sync`/push가 refuse했을 때 원인을 추적할 수 없다(FOMS 훅 규칙).

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


def _group_by_new_sha(lines: list[str]) -> list[tuple[str, list[str]]]:
    """post-rewrite stdin 라인을 new_sha 기준으로 묶는다(등장 순서 유지).

    파라미터:
        lines: `old_sha new_sha [extra-info]` 형식의 줄 목록. 토큰 2개 미만은 버린다.
    반환:
        `(new_sha, [old_sha, ...])` 목록. squash/fixup은 한 new_sha에 old가 여럿이다.
    """
    groups: dict[str, list[str]] = {}
    for line in lines:
        parts = line.split()
        if len(parts) < 2:
            continue
        groups.setdefault(parts[1], []).append(parts[0])
    return list(groups.items())


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

    new_sha 그룹의 old_sha가 **전부 같은 한 세션 소유**일 때만 승계한다.
    하나라도 미보유이거나 소유 세션이 갈리면 승계하지 않고 사유를 로그에 남긴다
    (squash 승계 세탁 차단).

    파라미터:
        project_root: ledger가 위치한 저장소(워크트리) 루트.
        lines: `old_sha new_sha [extra-info]` 형식의 줄 목록.
    반환:
        실제로 승계(append)한 new_sha 수.
    """
    ledger = scl.load_ledger(project_root)
    handled = 0
    for new_sha, olds in _group_by_new_sha(lines):
        owners = {_owning_session(ledger, old) for old in olds}
        if owners == {None}:
            _log_failure(
                project_root,
                f"[skip] {new_sha[:10]} 승계 안 함 — old {len(olds)}개 전부 ledger 미보유"
                " (타 워크트리/외부 커밋 재작성)",
            )
            continue
        if len(owners) > 1:
            preview = ", ".join(sorted(str(o) for o in owners))
            _log_failure(
                project_root,
                f"[refuse] {new_sha[:10]} 승계 거부 — old {len(olds)}개의 소유가 단일하지 않음"
                f" (squash 세탁 차단, 소유: {preview})",
            )
            continue
        scl.append_commit(project_root, owners.pop(), new_sha)
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
