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


def test_set_session_shas_roundtrip(tmp_path: Path) -> None:
    """set → 회수, 공백·빈 문자열·비 hex 필터, 타 세션 보존."""
    ledger = _load()
    root = str(tmp_path)
    ledger.append_commit(root, "sess-keep", "cccccccccccccccccccccccccccccccccccccccc")

    ledger.set_session_shas(
        root,
        "sess-a",
        ["  AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA  ", "", "   ", "zzzz-not-hex", "bbbbbbbb"],
    )

    assert ledger.session_shas(root, "sess-a") == [
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "bbbbbbbb",
    ]
    # 기존 세션은 보존되고 union 에 함께 잡힌다
    assert ledger.session_shas(root, "sess-keep") == [
        "cccccccccccccccccccccccccccccccccccccccc",
    ]
    assert set(ledger.all_known_shas(root)) == {
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "bbbbbbbb",
        "cccccccccccccccccccccccccccccccccccccccc",
    }


def test_set_session_shas_replaces_not_appends(tmp_path: Path) -> None:
    """rebase 후 갱신 용도: 기존 목록을 통째로 교체한다(append 아님)."""
    ledger = _load()
    root = str(tmp_path)
    ledger.append_commit(root, "sess-a", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    ledger.set_session_shas(root, "sess-a", ["dddddddddddddddddddddddddddddddddddddddd"])
    assert ledger.session_shas(root, "sess-a") == [
        "dddddddddddddddddddddddddddddddddddddddd",
    ]
    assert ledger.latest_session_id(root) == "sess-a"


def test_all_known_shas_survives_corrupt_entries(tmp_path: Path) -> None:
    """손상 ledger(비-dict 엔트리·shas=null·비문자열)에도 예외 없이 union 반환."""
    ledger = _load()
    root = str(tmp_path)
    ledger.save_ledger(
        root,
        {
            "sessions": {
                "broken-type": "not-a-dict",
                "null-shas": {"shas": None, "updated_at": "2026-01-01T00:00:00+00:00"},
                "mixed": {"shas": ["eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee", 123, None]},
                "dup": {"shas": ["EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE"]},
            }
        },
    )
    assert ledger.all_known_shas(root) == [
        "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
    ]
    assert ledger.latest_session_id(root) is not None


def test_sha_in_list_prefix() -> None:
    """abbrev prefix 매칭."""
    ledger = _load()
    known = ["aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]
    assert ledger.sha_in_list("aaaaaaaa", known)
    assert not ledger.sha_in_list("bbbbbbbb", known)
