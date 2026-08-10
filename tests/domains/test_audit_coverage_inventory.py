"""AUDIT-LOG P4 C2: 쓰기 라우트 감사 커버리지 드리프트 게이트.

배선(C1)은 한 번 채우면 끝나는 일이 아니다. 새 쓰기 라우트가 기록 없이 들어오면 커버리지는
조용히 다시 떨어진다(운영 실측: 172개 중 102개가 그렇게 쌓였다). 그래서 인벤토리를 커밋해
두고 **UNAUDITED 집합이 커지면 red** 로 만든다 — 줄어드는 것은 언제나 허용한다.

새 라우트를 추가하는 사람에게 남는 선택지는 둘뿐이다:

1. 감사 writer 를 호출한다(``log_access`` — 문장은 표시 SSOT 로).
2. 기록할 가치가 없다면 allowlist 에 **사유를 적어** 올린다.

선례: ``test_failopen_inventory.py`` · ``test_rev_99.py``.
"""

from __future__ import annotations

import ast
import json
import pathlib

import pytest

from tools.harness import audit_coverage_scan as scanner

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_INVENTORY_PATH = _REPO_ROOT / "docs" / "harness" / "foms_audit_coverage_inventory.json"
_ALLOWLIST_PATH = _REPO_ROOT / "docs" / "harness" / "foms_audit_coverage_allowlist.json"


@pytest.fixture(scope="module")
def inventory() -> dict:
    """커밋된 커버리지 인벤토리."""
    return json.loads(_INVENTORY_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def fresh_scan() -> list[dict]:
    """현재 코드 기준 재스캔 결과."""
    return scanner.scan()


def _keys(records) -> set[tuple[str, str]]:
    """``(path, endpoint)`` 집합 — lineno 는 보지 않는다(줄 밀림으로 red 금지)."""
    return {(r["path"], r["endpoint"]) for r in records}


def _lineno_free(records) -> list[dict]:
    """lineno 를 뺀 정렬된 레코드(순수 줄 이동이 게이트를 흔들지 않게)."""
    stripped = [{k: v for k, v in r.items() if k != "lineno"} for r in records]
    return sorted(stripped, key=lambda r: (r["path"], r["endpoint"]))


def test_inventory_matches_fresh_scan(inventory, fresh_scan):
    """커밋된 인벤토리 == 현재 코드 스캔(줄 번호 무관).

    새 쓰기 라우트·분류 변경이 있으면 red 다. 해소는
    ``python tools/harness/audit_coverage_scan.py`` 재생성.
    """
    assert _lineno_free(inventory["routes"]) == _lineno_free(fresh_scan), (
        "커버리지 인벤토리 드리프트 — tools/harness/audit_coverage_scan.py 로 재생성하라"
    )


def test_unaudited_set_does_not_grow(inventory, fresh_scan):
    """기록 없는 쓰기 라우트가 baseline 밖으로 늘지 않는다(핵심 게이트)."""
    fresh_unaudited = _keys(r for r in fresh_scan if r["classification"] == "UNAUDITED")
    pinned = _keys(inventory["unaudited_sites"])
    added = sorted(fresh_unaudited - pinned)
    assert not added, (
        "감사 기록 없는 쓰기 라우트가 새로 생겼다: "
        f"{added}. log_access(...) 로 행위자·대상을 남기거나, 기록할 가치가 없다면 "
        "docs/harness/foms_audit_coverage_allowlist.json 에 사유와 함께 올려라."
    )


def test_audited_routes_never_regress(inventory, fresh_scan):
    """이미 기록하던 라우트가 기록을 잃지 않는다(배선 제거 감지)."""
    pinned_audited = _keys(r for r in inventory["routes"] if r["classification"] == "AUDITED")
    fresh_audited = _keys(r for r in fresh_scan if r["classification"] == "AUDITED")
    lost = sorted(pinned_audited - fresh_audited)
    assert not lost, f"감사 기록을 잃은 라우트: {lost}"


def test_every_exemption_has_a_reason():
    """면제는 사유 없이 통과할 수 없다(조용한 커버리지 하락 방지)."""
    allow = json.loads(_ALLOWLIST_PATH.read_text(encoding="utf-8"))
    entries = allow.get("exempt", [])
    assert entries, "allowlist 가 비었다"
    for entry in entries:
        assert entry.get("key") and "::" in entry["key"], f"잘못된 key: {entry}"
        assert len((entry.get("reason") or "").strip()) >= 10, f"사유가 부실하다: {entry}"


def test_exemptions_point_at_real_routes(fresh_scan):
    """존재하지 않는 라우트를 면제해 두고 잊지 않는다(사문 방지)."""
    allow = json.loads(_ALLOWLIST_PATH.read_text(encoding="utf-8"))
    known = {f"{r['path']}::{r['endpoint']}" for r in fresh_scan}
    stale = sorted(e["key"] for e in allow.get("exempt", []) if e["key"] not in known)
    assert not stale, f"사라진 라우트를 가리키는 면제: {stale}"


def test_baselines_and_counts_are_consistent(inventory):
    """인벤토리 자체가 자기모순이 없다(손으로 고친 흔적 감지)."""
    routes = inventory["routes"]
    assert inventory["baselines"]["total"] == len(routes)
    assert inventory["baselines"]["unaudited"] == len(inventory["unaudited_sites"])
    counts = inventory["classification_counts"]
    for classification in scanner.CLASSIFICATIONS:
        actual = sum(1 for r in routes if r["classification"] == classification)
        assert counts[classification] == actual, f"{classification} 카운트 불일치"


def test_a_new_unrecorded_write_route_turns_the_gate_red(tmp_path):
    """인위적 red 실증 — 기록 없는 새 쓰기 라우트를 넣으면 UNAUDITED 로 잡힌다.

    게이트가 실제로 작동하는지 확인한다(스캐너가 항상 green 이면 게이트가 아니다).
    """
    module = tmp_path / "fake_routes.py"
    module.write_text(
        "from flask import Blueprint\n"
        "bp = Blueprint('fake', __name__)\n\n"
        "@bp.route('/danger', methods=['POST'])\n"
        "def api_delete_everything():\n"
        "    return {'success': True}\n",
        encoding="utf-8",
    )
    records = scanner._scan_file(module, {}, scanner._ModuleIndex())
    assert [r["classification"] for r in records] == ["UNAUDITED"]
    assert records[0]["methods"] == ["POST"]


def test_a_route_that_records_is_classified_audited(tmp_path):
    """반대 방향 실증 — ``log_access`` 를 부르면 AUDITED 로 분류된다."""
    module = tmp_path / "audited_routes.py"
    module.write_text(
        "from flask import Blueprint\n"
        "from foms.web.auth import log_access\n"
        "bp = Blueprint('ok', __name__)\n\n"
        "@bp.route('/ok', methods=['POST'])\n"
        "def api_do_something():\n"
        "    log_access('했다', 1, action='DID', target_type='order', target_id=1)\n"
        "    return {'success': True}\n",
        encoding="utf-8",
    )
    records = scanner._scan_file(module, {}, scanner._ModuleIndex())
    assert [r["classification"] for r in records] == ["AUDITED"]


def test_scanner_follows_thin_delegating_wrappers(tmp_path):
    """얇은 위임 래퍼를 기록 없음으로 오판하지 않는다(``foms/api/orders/__init__.py`` 구조)."""
    package = tmp_path / "foms" / "api" / "fake"
    package.mkdir(parents=True)
    (package / "worker.py").write_text(
        "from foms.web.auth import log_access\n\n"
        "def do_response():\n"
        "    log_access('했다', 1, action='DID')\n"
        "    return {'success': True}\n",
        encoding="utf-8",
    )
    (package / "__init__.py").write_text(
        "from flask import Blueprint\n"
        "from .worker import do_response\n"
        "bp = Blueprint('fake', __name__)\n\n"
        "@bp.route('/x', methods=['POST'])\n"
        "def api_x():\n"
        "    return do_response()\n",
        encoding="utf-8",
    )
    records = scanner._scan_file(package / "__init__.py", {}, scanner._ModuleIndex())
    assert [r["classification"] for r in records] == ["AUDITED"]


def test_get_only_routes_are_out_of_scope(tmp_path):
    """GET 전용 라우트는 대상이 아니다(열람 기록은 P4 D 단계 소관)."""
    module = tmp_path / "read_routes.py"
    module.write_text(
        "from flask import Blueprint\n"
        "bp = Blueprint('read', __name__)\n\n"
        "@bp.route('/list', methods=['GET'])\n"
        "def api_list():\n"
        "    return {'success': True}\n",
        encoding="utf-8",
    )
    assert scanner._scan_file(module, {}, scanner._ModuleIndex()) == []


def test_scanner_source_is_valid_python():
    """스캐너 자체가 파싱 가능한지(자기 도구 회귀 방지)."""
    source = (_REPO_ROOT / "tools" / "harness" / "audit_coverage_scan.py").read_text(encoding="utf-8")
    ast.parse(source)
