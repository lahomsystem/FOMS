"""CS · 완료 문지기 — 엔진 밖 옛 쓰기 · 지난 주문 일괄 도구 · 협력사 AS · 화면 (제품마다 '시공 끝' 2단계 7절 · N7 · N10).

설계: ``docs/specs/2026-11-21-item-construction-done_SPEC.md``. 단건 · 일괄 상태 쓰기, 칸 고치기, 옛 수정 폼 ·
옛 목록 일괄은 막고(일괄은 건너뛰고 알린다), 스위치를 끄면 지금과 같다. 지난 주문 일괄 완료 도구는 스위치와
상관없이 자료로만 뺀다. 판정 · 엔진 · 강제 변경은 ``test_items_construction_gate.py``.
"""
from __future__ import annotations

import datetime
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from foms.services.orders import item_construction_done as icd
from foms.services.orders.items_construction_gate import ITEMS_CONSTRUCTION_OPEN
from tests.support.item_construction_seed import (
    BLOCKED, FLAG, UID_A, UID_B, flashes, login, mark, saved, seed_order, seed_sd,
)


# ── 4. 엔진 밖 옛 쓰기 ───────────────────────────────────────────────────────

@pytest.mark.parametrize("target", ["CS", "COMPLETED"])
def test_single_status_route_blocks_all_branches(client, target) -> None:
    login(client)
    canonical, overlay = seed_order("CONSTRUCTION"), seed_order("CONSTRUCTION", hold=True)   # 보류 = 엔진 밖 옛 길
    for oid in (canonical, overlay):
        for extra in ({}, {"admin_override": True, "override_reason": "관리자 뚫기"}):
            resp = client.post("/api/update_order_status", json={"order_id": oid, "status": target, **extra})
            assert resp.status_code == 409, (oid, extra, resp.get_data(as_text=True))
            body = resp.get_json()
            assert (body["code"], body["message"]) == (ITEMS_CONSTRUCTION_OPEN, BLOCKED)
        assert saved(oid)[:2] == ("CONSTRUCTION", "CONSTRUCTION")


@pytest.mark.parametrize("kind,flag,hold", [("plain", "1", False), ("partial", "0", False),
                                            ("plain", "1", True), ("partial", "0", True)])
def test_single_status_route_controls(client, monkeypatch, kind, flag, hold) -> None:
    monkeypatch.setenv(FLAG, flag)
    login(client)
    oid = seed_order("CONSTRUCTION", kind, hold=hold)
    resp = client.post("/api/update_order_status", json={"order_id": oid, "status": "CS"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert saved(oid)[1] == "CS"


def test_bulk_status_route_skips_and_reports(client) -> None:
    login(client)
    partial, overlay, plain = seed_order("CONSTRUCTION"), seed_order("CONSTRUCTION", hold=True), seed_order("CONSTRUCTION", "plain")
    resp = client.post("/api/bulk_update_order_status", json={"order_ids": [partial, overlay, plain], "status": "CS"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["updated"] == 1 and sorted(body["blocked_items_construction_open"]) == sorted([partial, overlay])
    assert "2건은 남은 제품 시공이 있어 바꾸지 않았습니다." in body["message"]
    assert saved(partial)[1] == "CONSTRUCTION" and saved(overlay)[1] == "CONSTRUCTION"
    assert saved(plain)[1] == "CS"

    only = client.post("/api/bulk_update_order_status", json={"order_ids": [partial], "status": "COMPLETED",
                                                                "admin_override": True, "override_reason": "뚫기"})
    assert only.status_code == 409 and only.get_json()["success"] is False
    assert only.get_json()["blocked_items_construction_open"] == [partial]


def test_bulk_status_route_flag_off_is_unchanged(client, monkeypatch) -> None:
    monkeypatch.setenv(FLAG, "0")
    login(client)
    partial = seed_order("CONSTRUCTION")
    resp = client.post("/api/bulk_update_order_status", json={"order_ids": [partial], "status": "CS"})
    assert resp.status_code == 200 and resp.get_json()["blocked_items_construction_open"] == []
    assert saved(partial)[1] == "CS"


@pytest.mark.parametrize("target", ["CS", "COMPLETED"])
def test_field_update_status_blocks(client, target) -> None:
    login(client)
    for oid in (seed_order("CONSTRUCTION"), seed_order("CONSTRUCTION", hold=True)):
        resp = client.post("/api/update_order_field", json={"order_id": oid, "field": "status", "value": target})
        assert resp.status_code == 409, resp.get_data(as_text=True)
        assert resp.get_json()["code"] == ITEMS_CONSTRUCTION_OPEN
        assert saved(oid)[:2] == ("CONSTRUCTION", "CONSTRUCTION")


@pytest.mark.parametrize("kind,flag", [("plain", "1"), ("partial", "0")])
def test_field_update_status_controls(client, monkeypatch, kind, flag) -> None:
    monkeypatch.setenv(FLAG, flag)
    login(client)
    oid = seed_order("CONSTRUCTION", kind, hold=True)                           # 엔진 밖 옛 길 대조군
    resp = client.post("/api/update_order_field", json={"order_id": oid, "field": "status", "value": "CS"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert saved(oid)[1] == "CS"


def test_legacy_edit_form_keeps_status_and_says_why(client) -> None:
    login(client)
    partial, plain = seed_order("CONSTRUCTION"), seed_order("CONSTRUCTION", "plain")
    for oid in (partial, plain):
        resp = client.post(f"/edit/{oid}", data={"status": "CS"}, follow_redirects=False)
        assert resp.status_code in (200, 302, 303), (oid, resp.status_code)
    assert saved(partial)[0] == "CONSTRUCTION"
    assert saved(plain)[0] == "CS"                                         # 대조군
    assert any(BLOCKED in m and "주문 상태는 그대로" in m for m in flashes(client))


def test_legacy_list_bulk_action_skips_partial_open(client, monkeypatch) -> None:
    login(client)
    partial, plain = seed_order("CONSTRUCTION"), seed_order("CONSTRUCTION", "plain")
    resp = client.post("/bulk_action", data={"action": "status_COMPLETED",
                                             "selected_order": [str(partial), str(plain)]})
    assert resp.status_code in (302, 303), resp.status_code
    assert saved(partial)[0] == "CONSTRUCTION" and saved(plain)[0] == "COMPLETED"
    assert any("남은 제품 시공이 있는 주문 1건" in m for m in flashes(client))

    monkeypatch.setenv(FLAG, "0")                                           # 스위치를 끄면 지금과 같다
    client.post("/bulk_action", data={"action": "status_COMPLETED", "selected_order": [str(partial)]})
    assert saved(partial)[0] == "COMPLETED"


# ── 5. 지난 주문 일괄 완료 도구 — 스위치와 상관없이 자료로 뺀다 ───────────────

_TOOL_PATH = Path(__file__).resolve().parents[2] / "tools" / "ops" / "bulk_complete_past_construction.py"


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("bulk_complete_past_construction_items_gate", _TOOL_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _row(sd: dict, **over) -> dict:
    """후보 행 — 제품 칸 날짜는 기준일 앞으로 옮긴다(뒤 시공일 사유와 섞이지 않게)."""
    for item in sd.get("items") or []:
        if item.get("construction_date"):
            item["construction_date"] = "2026-08-19"
    base = {"id": 7, "customer_name": "가", "status": "CONSTRUCTION", "is_erp_order": True,
            "erp_stage_code": "CONSTRUCTION", "erp_construction_date": "2026-08-20", "as_axis_status": None,
            "meta_draft": False, "open_quests": 0, "naver_claim_open": False, "later_construction_date": None,
            "construction_text": "2026-08-20", "items": sd.get("items"), "item_construction_done": sd.get(icd.DONE_KEY)}
    base.update(over)
    return base


@pytest.mark.parametrize("flag", ["1", "0"])
def test_bulk_tool_excludes_partial_open_by_data_only(tool, monkeypatch, flag) -> None:
    monkeypatch.setenv(FLAG, flag)
    cutoff = "2026-09-15"
    partial = _row(seed_sd("CONSTRUCTION", "partial"))                          # 남은 날이 모두 기준일 앞이어도 뺀다
    assert tool.later_construction_date(partial, cutoff) is None
    assert tool.classify_row(partial, cutoff=cutoff) == (None, "items_construction_open", [])
    assert tool.classify_row(_row(seed_sd("CONSTRUCTION", "plain")), cutoff=cutoff)[0] == "main"
    assert tool.classify_row(_row(seed_sd("CONSTRUCTION", "all_done")), cutoff=cutoff)[0] == "main"
    plan = tool.build_plan([partial, _row(seed_sd("CS", "plain"), id=8)], cutoff=cutoff, today="2026-09-22", cutoff_days=7)
    assert [i["order_id"] for i in plan["items"]] == [8]
    assert plan["skipped"][0]["reason"] == "items_construction_open"
    assert plan["summary"]["skipped"] == {"items_construction_open": 1}


def test_bulk_tool_rule_matches_app_helper(tool) -> None:
    """도구의 부분 시공 판정은 앱 ``is_partial_open`` 과 같은 값을 낸다(규칙 두 벌 드리프트 방지)."""
    samples = [seed_sd("CS", "partial"), seed_sd("CS", "plain"), seed_sd("CS", "all_done"), {}, {"items": "x"},
               {"items": [{"uid": UID_A}], icd.DONE_KEY: {UID_A: mark()}},
               {"items": [{"uid": UID_A}, {"product_name": "이름표 없음"}], icd.DONE_KEY: {UID_A: mark()}},
               {"items": [{"uid": UID_A}, {"uid": UID_B, "cancel": {"at": "x"}}], icd.DONE_KEY: {UID_A: mark()}},
               {"items": [{"uid": UID_A}, {"uid": UID_B}], icd.DONE_KEY: {UID_A: "망가진 값"}},
               {"items": [{"uid": " " + UID_A + " "}, {"uid": UID_B}], icd.DONE_KEY: {UID_A: mark()}},
               {"items": [{"uid": "짧은-uid"}, {"uid": UID_B}], icd.DONE_KEY: {"짧은-uid": mark()}},
               {"items": [{"uid": UID_A}, {"uid": UID_B}], icd.DONE_KEY: ["x"]}]
    for sd in samples:
        assert tool.items_construction_open(sd) is icd.is_partial_open(sd), sd


class _FakeCursor:
    """apply_one 의 잠금 조회 한 번만 답하는 커서 — 쓰기(UPDATE · INSERT)가 오면 실패한다."""

    def __init__(self, row: dict):
        self.row, self.sql = row, []

    def execute(self, sql, params=None):
        assert not sql.lstrip().upper().startswith(("UPDATE", "INSERT")), sql
        self.sql.append(sql)

    def fetchone(self):
        return self.row


def test_bulk_tool_apply_rechecks_under_lock(tool) -> None:
    """plan 뒤에 '시공 끝'이 찍힌 주문은 잠근 뒤 다시 보고 건너뛴다(쓰기 0)."""
    sd = seed_sd("CONSTRUCTION", "partial")
    cur = _FakeCursor({"status": "CONSTRUCTION", "erp_stage_code": "CONSTRUCTION", "as_axis_status": None,
                       "structured_data": sd})
    item = {"order_id": 7, "observed_status": "CONSTRUCTION", "observed_stage": "CONSTRUCTION",
            "observed_as_axis": None, "mode": "main", "customer_name": "가"}
    out = tool.apply_one(cur, item, actor_user_id=1, now=datetime.datetime(2026, 9, 22), reason="시험")
    assert out == "skipped:items_construction_open" and len(cur.sql) == 1


# ── 6. 협력사 AS 접수(N10) ───────────────────────────────────────────────────

@pytest.mark.parametrize("stage,kind,flag,expected", [
    ("PRODUCTION", "partial", "1", "new"),       # 먼저 끝낸 제품이 있으면 생산 단계도 AS 를 받는다
    ("PRODUCTION", "all_done", "1", "new"),
    ("CONSTRUCTION", "partial", "1", "new"),
    ("PRODUCTION", "plain", "1", None),          # 대조군 — '시공 끝' 없음
    ("PRODUCTION", "partial", "0", None),        # 스위치 끔 = 지금과 같다
    ("CONFIRM", "partial", "1", None),           # 생산 · 시공 단계에서만
    ("CONSTRUCTION", "plain", "0", "new"),       # 지금 규칙 그대로
])
def test_partner_as_intake_mode(monkeypatch, stage, kind, flag, expected) -> None:
    from foms.services.partners import as_intake

    monkeypatch.setenv(FLAG, flag)
    order = SimpleNamespace(erp_stage_code=stage, structured_data=seed_sd(stage, kind))
    assert as_intake.as_mode(order) == expected


# ── 화면: 강제 변경 창의 확인 · 다시 보내기 ──────────────────────────────────

_ROOT = Path(__file__).resolve().parents[2]


def test_override_js_asks_and_resends_with_close_remaining_items() -> None:
    js = (_ROOT / "static/js/orders/erp-stage-override.js").read_text(encoding="utf-8")
    assert "'ITEMS_CONSTRUCTION_OPEN'" in js and "close_remaining_items = true" in js
    assert "남은 제품도 시공 끝으로 찍고 넘길까요?" in js and "resendClosingItems" in js
    assert "!body.close_remaining_items" in js                                # 두 번째로는 묻지 않는다
    for rel in ("templates/orders/partials/dashboard_main.html", "templates/measurement/metropolitan_dashboard.html",
                "templates/measurement/regional_dashboard.html"):
        assert "erp-stage-override.js') }}?v=20261121b" in (_ROOT / rel).read_text(encoding="utf-8"), rel


def test_tool_module_has_no_foms_import() -> None:
    """도구 두 모듈은 foms 를 import 하지 않는다(psycopg 만으로 도는 운영 도구)."""
    for name in ("bulk_complete_past_construction_core.py", "bulk_complete_past_construction_remaining.py"):
        text = (_ROOT / "tools" / "ops" / name).read_text(encoding="utf-8")
        assert "from foms" not in text and "import foms" not in text, name
