"""session_commit_ledger 단위 테스트."""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load():
    path = REPO_ROOT / "tools" / "harness" / "session_commit_ledger.py"
    name = "session_commit_ledger_ut"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    # paths.py 가 같은 디렉터리에 있어야 함
    import sys

    harness = str(REPO_ROOT / "tools" / "harness")
    if harness not in sys.path:
        sys.path.insert(0, harness)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_append_and_query(tmp_path: Path) -> None:
    """세션별 SHA append·조회·중복 무시."""
    ledger = _load()
    root = str(tmp_path)
    ledger.append_commit(root, "sess-a", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    ledger.append_commit(root, "sess-a", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    ledger.append_commit(root, "sess-a", "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")
    ledger.append_commit(root, "sess-b", "cccccccccccccccccccccccccccccccccccccccc")

    assert ledger.session_shas(root, "sess-a") == [
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    ]
    assert ledger.session_shas(root, "sess-b") == [
        "cccccccccccccccccccccccccccccccccccccccc",
    ]
    assert ledger.session_shas(root, "missing") == []


def test_unknown_session_id(tmp_path: Path) -> None:
    """빈 session_id 는 unknown 버킷."""
    ledger = _load()
    root = str(tmp_path)
    ledger.append_commit(root, None, "dddddddddddddddddddddddddddddddddddddddd")
    assert ledger.session_shas(root, "unknown") == [
        "dddddddddddddddddddddddddddddddddddddddd",
    ]


def test_sha_in_list_prefix() -> None:
    """abbrev prefix 매칭."""
    ledger = _load()
    known = ["aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]
    assert ledger.sha_in_list("aaaaaaaa", known)
    assert not ledger.sha_in_list("bbbbbbbb", known)
