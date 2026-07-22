"""세션별 커밋 SHA 레저 (deploy push 격리용).

여러 에이전트 창이 동일 워킹트리를 공유할 때, 어떤 session_id 가 어떤
커밋을 만들었는지 기록한다. gitignore 런타임 JSON 에 저장한다.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from paths import HARNESS_RUNTIME_DIR

LEDGER_FILENAME = "session_commit_ledger.json"


def ledger_path(project_root: str) -> str:
    """레저 JSON 절대 경로를 반환한다."""
    return os.path.join(project_root, HARNESS_RUNTIME_DIR, LEDGER_FILENAME)


def _now_iso() -> str:
    """UTC ISO-8601 타임스탬프."""
    return datetime.now(timezone.utc).isoformat()


def _empty() -> dict[str, Any]:
    """빈 레저 구조."""
    return {"sessions": {}}


def load_ledger(project_root: str) -> dict[str, Any]:
    """레저를 로드한다. 없거나 손상 시 빈 구조."""
    path = ledger_path(project_root)
    if not os.path.isfile(path):
        return _empty()
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError, TypeError):
        return _empty()
    if not isinstance(data, dict):
        return _empty()
    sessions = data.get("sessions")
    if not isinstance(sessions, dict):
        return _empty()
    return {"sessions": sessions}


def save_ledger(project_root: str, data: dict[str, Any]) -> None:
    """레저를 원자적으로 저장한다."""
    path = ledger_path(project_root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(tmp, path)


def normalize_session_id(session_id: str | None) -> str:
    """세션 ID를 정규화한다. 없으면 unknown."""
    sid = (session_id or "").strip()
    return sid if sid else "unknown"


def append_commit(project_root: str, session_id: str | None, sha: str) -> None:
    """세션 레저에 커밋 SHA 를 append 한다(중복 무시).

    파라미터:
        project_root: 저장소 루트.
        session_id: 훅 session/conversation id.
        sha: 커밋 해시(abbrev 허용).
    """
    sha = (sha or "").strip().lower()
    if not sha or not all(c in "0123456789abcdef" for c in sha):
        return
    sid = normalize_session_id(session_id)
    data = load_ledger(project_root)
    entry = data["sessions"].setdefault(sid, {"shas": [], "updated_at": _now_iso()})
    shas: list[str] = list(entry.get("shas") or [])
    if not any(_sha_match(existing, sha) for existing in shas):
        shas.append(sha)
    entry["shas"] = shas
    entry["updated_at"] = _now_iso()
    data["sessions"][sid] = entry
    save_ledger(project_root, data)


def session_shas(project_root: str, session_id: str | None) -> list[str]:
    """세션에 기록된 SHA 목록을 반환한다."""
    sid = normalize_session_id(session_id)
    data = load_ledger(project_root)
    entry = data["sessions"].get(sid) or {}
    raw = entry.get("shas") or []
    return [str(s).lower() for s in raw if s]


def _sha_match(a: str, b: str) -> bool:
    """두 SHA 가 동일 커밋을 가리키면 True(짧은 쪽이 prefix)."""
    a = a.lower()
    b = b.lower()
    if a == b:
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    return len(shorter) >= 7 and longer.startswith(shorter)


def sha_in_list(sha: str, known: list[str]) -> bool:
    """sha 가 known 목록에 매칭되면 True."""
    return any(_sha_match(sha, k) for k in known)
