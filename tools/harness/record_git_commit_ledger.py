"""git commit 성공 시 세션 레저에 HEAD SHA 를 기록하는 공용 헬퍼."""
from __future__ import annotations

import os
import re
import subprocess
import sys


def looks_like_git_commit(command: str) -> bool:
    """명령이 git commit 실행으로 보이면 True."""
    lowered = (command or "").lower()
    if "git commit" not in lowered:
        return False
    # 도움말/드라이런성 제외
    if re.search(r"\bgit\s+commit\b.*\s(-h|--help)\b", lowered):
        return False
    return True


def commit_succeeded(output: str) -> bool:
    """커밋 성공 출력 휴리스틱."""
    text = output or ""
    low = text.lower()
    if "files changed" in low or "file changed" in low:
        return True
    if re.search(r"\[[\w/.\-]+\s+[0-9a-f]{7,}\]", text):
        return True
    if "nothing to commit" in low or "clean working tree" in low:
        return False
    if "error:" in low or "fatal:" in low:
        return False
    return False


def record_head_commit(
    project_root: str,
    session_id: str | None,
    command: str,
    output: str,
) -> bool:
    """성공한 git commit 이면 HEAD 를 레저에 기록. 기록 시 True."""
    if not looks_like_git_commit(command) or not commit_succeeded(output):
        return False
    harness = os.path.join(project_root, "tools", "harness")
    if harness not in sys.path:
        sys.path.insert(0, harness)
    from session_commit_ledger import append_commit  # type: ignore[import-not-found]

    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=project_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )
    if proc.returncode != 0:
        return False
    sha = (proc.stdout or "").strip()
    if not sha:
        return False
    append_commit(project_root, session_id, sha)
    return True
