"""열린 AS 가 본 흐름 목표 status 쓰기를 이기는 계약 (설계서 2026-11-20-multi-item-split-schedule §4.3, M6 · M7).

손으로 단계를 바꾸는 여섯 길이 ``order.status`` 를 본 흐름 글로 직접 덮으면, AS 건은 열려 있는데 주문 화면 ·
출고판의 AS 표시만 사라졌다(운영 5687). 이제 열린 AS(접수 · 처리 중)면 단계만 옮기고 상태 글은 그대로 둔다.

여섯 길: ① 강제 단계 변경(test_as_bulk_status_guard · test_as_overlay_stage_preserve 가 잰다) ② 단건 상태 쓰기
③ 일괄 상태 쓰기 ④ 칸 고치기 ⑤ 수정 제작 시작 ⑥ 옛 목록 일괄 · 옛 수정 폼.
대조군은 길마다 같은 자료로 둔다: 닫힌 AS(완료)는 지금처럼 덮이고, AS 아닌 주문은 그대로 바뀐다.
물류 · 보류 목표는 test_as_overlay_status_write_guard 가 따로 지킨다(건드리지 않는다).
"""
from __future__ import annotations

import itertools
from types import SimpleNamespace

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.orders import as_axis_read
from foms.services.orders.state_axes import (
    LEGACY_STATUS_ALIAS,
    AXIS_AS,
    open_as_outranks_main_status_write,
    read_as_status,
)
from models import Order, User
from tests.support.production_steps_seed import with_inspected_steps

_seq = itertools.count(1)


def _cycle(status: str) -> dict:
    cid = f"c{next(_seq)}"
    transitions = [{"seq": 1, "from": "NONE", "to": "RECEIVED", "command": "AS_REGISTER", "at": "2026-11-01T00:00:00"}]
    if status != "RECEIVED":
        transitions.append({"seq": 2, "from": "RECEIVED", "to": status, "command": "AS_X", "at": "2026-11-02T00:00:00"})
    return {"current_cycle_id": cid, "cycles": [{"cycle_id": cid, "opened_at": "2026-11-01T00:00:00",
                                                 "transitions": transitions}]}


def _order(*, status: str, stage: str = "PRODUCTION", is_erp: bool = True, lifecycle: dict | None = None) -> int:
    sd = {"workflow": {"stage": stage}, "parties": {"customer": {"name": "가짜고객"}}}
    if lifecycle is not None:
        sd["as_lifecycle"] = lifecycle
    if stage == "PRODUCTION":
        # 생산 → 시공 쓰기는 검수까지(공정 4칸) 끝나야 한다(2026-11-21) — 이 시험은 AS 표시만 보므로 공정은 끝으로 둔다.
        sd = with_inspected_steps(sd)
    order = Order(received_date="2026-11-01", customer_name="가짜고객", phone="010-0000-0000", address="가짜시 가짜로 1",
                  product="가짜장", status=status, is_erp_order=is_erp, erp_stage_code=stage if is_erp else None,
                  as_received_date="2026-11-01" if status.startswith("AS") else None,
                  structured_data=sd if is_erp else None)
    db_session.add(order)
    db_session.commit()
    return order.id


def _login(client, role: str = "ADMIN", team: str | None = "CS") -> User:
    n = next(_seq)
    user = User(username=f"as_main_guard_{n}", password=generate_password_hash("pw"), role=role, team=team,
                name=f"가짜사람{n}", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = user.id, user.username, user.role
    return user


def _saved(order_id: int) -> tuple[str, str]:
    db_session.expire_all()
    order = db_session.get(Order, order_id)
    return order.status, ((order.structured_data or {}).get("workflow") or {}).get("stage")


# ── 판정 ────────────────────────────────────────────────────────────────────

def test_leaf_reader_matches_the_state_axes_alias_table() -> None:
    """잎 모듈이 다시 적은 옛 상태 글 표는 state_axes 의 AS 갈래와 같다."""
    from_alias = {k: v[1] for k, v in LEGACY_STATUS_ALIAS.items() if v[0] == AXIS_AS}
    assert as_axis_read.LEGACY_AS_STATUS_TO_AXIS == from_alias
    assert read_as_status is as_axis_read.read_as_status


@pytest.mark.parametrize("status,lifecycle,erp,target,kept", [
    ("AS_RECEIVED", None, True, "CONSTRUCTION", "AS_RECEIVED"),          # 건 기록 없는 옛 AS 접수
    ("AS", None, True, "PRODUCTION", "AS"),                              # 처리 중
    ("AS_RECEIVED", "RECEIVED", True, "시공", "AS_RECEIVED"),             # 한글 단계 글 목표
    ("AS", "IN_PROGRESS", True, "COMPLETED", "AS"),
    ("AS_COMPLETED", None, True, "CONSTRUCTION", ""),                    # 닫힌 AS = 덮인다
    ("AS_RECEIVED", "COMPLETED", True, "CONSTRUCTION", ""),              # 건이 완료면 상태 글이 접수여도 닫힌 AS
    ("PRODUCTION", "RECEIVED", True, "CONSTRUCTION", ""),                # 지킬 AS 표시가 상태 글에 없다(5687 꼴)
    ("AS_RECEIVED", None, False, "COMPLETED", ""),                       # 비 ERP = 상태 글이 곧 단계
    ("AS_RECEIVED", "RECEIVED", True, "SCHEDULED", ""),                  # 물류 목표는 이 문지기 몫이 아니다
    ("AS_RECEIVED", "RECEIVED", True, "ON_HOLD", ""),                    # 보류
    ("AS_RECEIVED", "RECEIVED", True, "AS_COMPLETED", ""),               # AS 목표
])
def test_open_as_outranks_main_status_write_table(status, lifecycle, erp, target, kept) -> None:
    sd = {"workflow": {"stage": "PRODUCTION"}}
    if lifecycle:
        sd["as_lifecycle"] = _cycle(lifecycle)
    order = SimpleNamespace(status=status, is_erp_order=erp, structured_data=sd if erp else None)
    assert open_as_outranks_main_status_write(order, target) == kept


# ── ② 단건 상태 쓰기 ─────────────────────────────────────────────────────────

def test_single_status_write_moves_stage_and_keeps_open_as_status(client) -> None:
    _login(client)
    open_as = _order(status="AS_RECEIVED", lifecycle=_cycle("RECEIVED"))
    closed_as = _order(status="AS_COMPLETED", lifecycle=_cycle("COMPLETED"))
    plain = _order(status="PRODUCTION")

    resp = client.post("/api/update_order_status", json={"order_id": open_as, "status": "CONSTRUCTION"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["as_overlay_kept"] == "AS_RECEIVED" and body["new_status"] == "AS_RECEIVED"
    assert body["stage"] == "CONSTRUCTION" and "AS 표시는 그대로 남습니다" in body["message"]
    assert _saved(open_as) == ("AS_RECEIVED", "CONSTRUCTION")

    resp = client.post("/api/update_order_status", json={"order_id": closed_as, "status": "CONSTRUCTION"})
    assert resp.status_code == 200 and "as_overlay_kept" not in resp.get_json()
    assert _saved(closed_as) == ("CONSTRUCTION", "CONSTRUCTION")  # 대조군: 닫힌 AS 는 덮인다

    resp = client.post("/api/update_order_status", json={"order_id": plain, "status": "CONSTRUCTION"})
    assert resp.status_code == 200 and "as_overlay_kept" not in resp.get_json()
    assert _saved(plain) == ("CONSTRUCTION", "CONSTRUCTION")      # 대조군: AS 아님


# ── ③ 일괄 상태 쓰기 ─────────────────────────────────────────────────────────

def test_bulk_status_write_with_include_as_keeps_open_as_status(client) -> None:
    _login(client)
    open_as = _order(status="AS", lifecycle=_cycle("IN_PROGRESS"))
    closed_as = _order(status="AS_COMPLETED")
    plain = _order(status="PRODUCTION")

    resp = client.post("/api/bulk_update_order_status",
                       json={"order_ids": [open_as, closed_as, plain], "status": "CONSTRUCTION", "include_as": True})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["updated"] == 3 and body["as_overlay_kept"] == [open_as]
    assert "AS 표시는 그대로 남습니다" in body["message"]
    assert _saved(open_as) == ("AS", "CONSTRUCTION")
    assert _saved(closed_as) == ("CONSTRUCTION", "CONSTRUCTION")
    assert _saved(plain) == ("CONSTRUCTION", "CONSTRUCTION")


# ── ④ 칸 고치기 ─────────────────────────────────────────────────────────────

def test_field_update_status_moves_stage_and_keeps_open_as_status(client) -> None:
    _login(client)
    open_as = _order(status="AS_RECEIVED")                       # 건 기록 없는 옛 AS 접수도 지킨다
    closed_as = _order(status="AS_COMPLETED", lifecycle=_cycle("COMPLETED"))

    resp = client.post("/api/update_order_field", json={"order_id": open_as, "field": "status", "value": "CONSTRUCTION"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["status"] == "AS_RECEIVED", "응답이 저장되지 않은 값을 사실처럼 알린다"
    assert _saved(open_as) == ("AS_RECEIVED", "CONSTRUCTION")
    assert db_session.get(Order, open_as).erp_stage_code == "CONSTRUCTION"

    resp = client.post("/api/update_order_field", json={"order_id": closed_as, "field": "status", "value": "CONSTRUCTION"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _saved(closed_as) == ("CONSTRUCTION", "CONSTRUCTION")  # 대조군


# ── ⑤ 수정 제작 시작 ─────────────────────────────────────────────────────────

def test_production_rework_keeps_open_as_status(client) -> None:
    _login(client, team=None)
    open_as = _order(status="AS_RECEIVED", stage="CONSTRUCTION", lifecycle=_cycle("RECEIVED"))
    closed_as = _order(status="AS_COMPLETED", stage="CONSTRUCTION", lifecycle=_cycle("COMPLETED"))
    plain = _order(status="CONSTRUCTION", stage="CONSTRUCTION")
    punch = {"reason": "문짝 다시 제작", "admin_override": True, "override_reason": "시험 — 게이트 건너뜀"}

    for oid, saved_status in ((open_as, "AS_RECEIVED"), (closed_as, "PRODUCTION"), (plain, "PRODUCTION")):
        resp = client.post(f"/api/orders/{oid}/production/rework", json=dict(punch))
        assert resp.status_code == 200, (oid, resp.get_data(as_text=True))
        assert resp.get_json()["new_status"] == saved_status, "응답이 저장되지 않은 값을 사실처럼 알린다"

    assert _saved(open_as) == ("AS_RECEIVED", "PRODUCTION")
    assert _saved(closed_as) == ("PRODUCTION", "PRODUCTION")  # 대조군
    assert _saved(plain) == ("PRODUCTION", "PRODUCTION")      # 대조군


# ── ⑥ 옛 목록 일괄 · 옛 수정 폼 ──────────────────────────────────────────────

def test_legacy_list_bulk_action_skips_open_as_orders(client) -> None:
    _login(client)
    open_as = _order(status="AS_RECEIVED", lifecycle=_cycle("RECEIVED"))
    closed_as = _order(status="AS_COMPLETED")
    plain = _order(status="PRODUCTION")
    resp = client.post("/bulk_action", data={"action": "status_CONSTRUCTION",
                                             "selected_order": [str(open_as), str(closed_as), str(plain)]},
                       follow_redirects=False)
    assert resp.status_code in (302, 303), resp.status_code
    assert _saved(open_as)[0] == "AS_RECEIVED"       # 이 길은 단계를 안 옮긴다 — 열린 AS 는 건너뛴다
    assert _saved(closed_as)[0] == "CONSTRUCTION"    # 대조군
    assert _saved(plain)[0] == "CONSTRUCTION"
    with client.session_transaction() as sess:
        flashes = [msg for _cat, msg in sess.get("_flashes", [])]
    assert any("AS 접수 중인 주문 1건" in m and "AS 표시는 그대로 남습니다" in m for m in flashes), flashes


def test_legacy_edit_form_keeps_open_as_status(client) -> None:
    _login(client)
    open_as = _order(status="AS_RECEIVED", lifecycle=_cycle("RECEIVED"))
    closed_as = _order(status="AS_COMPLETED")
    for oid in (open_as, closed_as):
        resp = client.post(f"/edit/{oid}", data={"status": "CONSTRUCTION"}, follow_redirects=False)
        assert resp.status_code in (200, 302, 303), (oid, resp.status_code)
    assert _saved(open_as)[0] == "AS_RECEIVED"
    assert _saved(closed_as)[0] == "CONSTRUCTION"    # 대조군


# ── 화면 글(M8) ─────────────────────────────────────────────────────────────

_ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]
_KEPT_TEXT = "AS 표시는 그대로 남습니다. 잘못 접수한 AS 는 [AS 접수 취소]로 지워 주세요."


def test_override_modal_and_js_say_the_as_mark_stays() -> None:
    modal = (_ROOT / "templates/orders/partials/erp_stage_override_modal.html").read_text(encoding="utf-8")
    assert f'data-warning-as-kept="{_KEPT_TEXT}"' in modal
    js = (_ROOT / "static/js/orders/erp-stage-override.js").read_text(encoding="utf-8")
    assert _KEPT_TEXT in js and "as_overlay_kept" in js and "as_overlay_cleared" not in js
    assert "data-warning-as-kept" in js and "openAsInScope" in js


@pytest.mark.skipif(__import__("shutil").which("node") is None, reason="node 없음")
def test_override_js_builds_kept_text_for_single_and_bulk() -> None:
    import json
    import subprocess

    script = (
        "global.window={};"
        "global.document={readyState:'complete',addEventListener(){},querySelectorAll(){return []},"
        "getElementById(){return null},querySelector(){return null}};"
        f"require({json.dumps(str(_ROOT / 'static/js/orders/erp-stage-override.js'))});"
        "var f=window.FOMS_STAGE_OVERRIDE.asOverlayKeptText;"
        "process.stdout.write(JSON.stringify([f({as_overlay_kept:'AS_RECEIVED'}),f({as_overlay_kept:null}),"
        "f({results:[{as_overlay_kept:'AS'},{as_overlay_kept:'AS_RECEIVED'},{}]}),f(null)]));"
    )
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, encoding="utf-8",
                         timeout=60, check=True).stdout
    single, none, bulk, empty = json.loads(out)
    assert single == _KEPT_TEXT and none == "" and empty == ""
    assert bulk == "AS 접수 중인 주문 2건: " + _KEPT_TEXT
