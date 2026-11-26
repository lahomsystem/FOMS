"""30초 받아 오기의 주문 막힘 캐시(검토 고침 — 운영 생산 단계 53건 · 주문 JSON 평균 19KB · 최대 93KB 를 태블릿마다 30초마다 읽던 길).

* 평소(캐시 찬 뒤) 받아 오기 = 막힘을 싣기 전과 같은 쿼리 수, 주문 JSON(``structured_data``) 읽기 0.
* 주문 하나가 바뀌면(쓰기 엔진이 ``mutation_version`` 을 올림) 다음 받아 오기 = +1 쿼리, 그 쿼리의 ``IN`` 에 그 주문만 — 막힘이 새 값.
* 막힘을 바꾸는 쓰기 길마다 "쓰기 전 버전 < 쓰기 뒤 버전"이고 받아 오기 막힘이 따라 바뀐다: 보류 켜기 · 풀기, 도면팀 [수정 시작] · 취소,
  영업 수정 요청, 제작 완료(생산 → 시공) · 완료 취소 · 제작 취소, 도면 재전달(바로 반영 · 교체).
* 버전을 안 올리는 쓰기(시험은 주문 JSON 을 직접 고쳐 흉내)는 수명 5분이 지나면 맞춰진다 · 칸 수는 LRU 상한.
* 협력사 계정은 403, 표시 줄이 여럿 바뀐 주문 하나 = 표시 줄 전부 · 막힘 하나.

이름은 모두 지어낸 값이다. 시험마다 캐시는 ``tests/conftest.py`` 가 비운다(주문 번호가 시험마다 1 부터).
"""
from __future__ import annotations

import datetime

import pytest
from sqlalchemy import event

import foms.services.production.sync_blocks as sb
from db import db_session, engine
from foms.services.datetime_kst import now_utc_naive
from foms.services.production.part_mark_gates import HOLD_MESSAGE, REVISING_MESSAGE
from models import Order, PartnerOrg, ProductionPartMark, ProductionRun
from tests.domains.test_drawing_production_hotfix import _order as hotfix_order, _send, _user as hotfix_user
from tests.support.drawing_fix_workbench_seed import key, login, make_order, make_user, patch

SYNC = "/api/production/part-marks"
SINCE = "2000-01-01T00:00:00"


@pytest.fixture
def quiet(monkeypatch):
    """폰 알림 · 실시간 알림을 끈다(발송 없음)."""
    monkeypatch.setattr("foms.services.notifications.push_sender.enqueue_push_for_notification", lambda *a, **k: None)
    monkeypatch.setattr("foms.api.drawing.erp_orders_revision.emit_erp_notification_to_users", lambda *a, **k: None)
    monkeypatch.setattr("foms.api.drawing.erp_orders_drawing.emit_erp_notification_to_users", lambda *a, **k: None)
    monkeypatch.setattr("foms.services.notifications.realtime_notifications.emit_erp_notification_to_users",
                        lambda *a, **k: None)


def _run(oid: int) -> None:
    db_session.add(ProductionRun(order_id=oid, status="IN_PROGRESS", steps=[], defects=[], is_current=True))
    db_session.commit()


def _version(oid: int) -> int:
    db_session.expire_all()
    return int(db_session.get(Order, oid).mutation_version or 0)


def _sync(client, *oids: int) -> dict:
    resp = client.get(SYNC, query_string={"order_ids": ",".join(map(str, oids)), "since": SINCE})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()["data"]


def _counted(client, *oids: int) -> tuple[dict, list[tuple[str, tuple]]]:
    seen: list[tuple[str, tuple]] = []

    def _before(conn, cursor, statement, params, context, executemany):
        seen.append((statement, tuple(params) if isinstance(params, (list, tuple)) else ()))

    event.listen(engine, "before_cursor_execute", _before)
    try:
        data = _sync(client, *oids)
    finally:
        event.remove(engine, "before_cursor_execute", _before)
    return data, seen


def _json_reads(seen: list[tuple[str, tuple]]) -> list[tuple[str, tuple]]:
    return [(st, params) for st, params in seen if "orders.structured_data AS" in st]  # 주문 JSON 을 싣는 읽기(초안 거르개 서브쿼리 말고)


# --------------------------------------------------------------------------- #
# 쿼리 모양
# --------------------------------------------------------------------------- #
def test_warm_sync_reads_no_order_json_and_one_changed_order_adds_one_read_of_it_only(client, quiet):
    admin = make_user("한관리", team=None, role="ADMIN")
    oids = [make_order(2) for _ in range(5)]
    for oid in oids:
        _run(oid)
    login(client, admin)
    _sync(client, *oids)  # 세션 첫 요청 치우기 + 캐시 채우기(주문 JSON 은 이때 한 번)
    _sync(client, *oids)
    warm, seen = _counted(client, *oids)
    assert len(seen) == 2 and not _json_reads(seen)  # 로그인 사용자 · 주문 ⟕ 표시 줄 — 막힘 싣기 전과 같은 수, JSON 0
    assert all(warm["blocks"][str(oid)] == {"all": None, "keys": {}} for oid in oids)
    assert "orders.mutation_version" in seen[-1][0] and "LEFT OUTER JOIN production_part_marks" in seen[-1][0]
    target = oids[2]
    before = _version(target)
    assert client.post(f"/api/orders/{target}/production/hold", json={"active": True, "reason": "자재 기다림"}).status_code == 200
    assert _version(target) > before
    changed, seen = _counted(client, *oids)
    reads = _json_reads(seen)
    assert len(seen) == 3 and len(reads) == 1 and reads[0][1] == (target,)  # +1 이고 IN 에 그 주문만
    assert changed["blocks"][str(target)]["all"] == {"kind": "hold", "text": "보류 · 자재 기다림", "why": HOLD_MESSAGE,
                                                     "code": "HOLD_ACTIVE"}
    again, seen = _counted(client, *oids)
    assert len(seen) == 2 and not _json_reads(seen) and again["blocks"] == changed["blocks"]  # 다시 캐시에서


def test_cold_cache_reads_each_order_json_once_even_with_many_changed_marks(client):
    """표시 줄이 여럿 바뀐 주문 하나: 표시 줄은 전부, 막힘은 주문 하나에 하나, 주문 JSON 은 주문마다 한 번(SQLite)."""
    admin = make_user("한관리", team=None, role="ADMIN")
    busy, other = make_order(3), make_order(2)
    now = now_utc_naive()
    for j in range(3):
        for part in ("cut", "edge"):
            db_session.add(ProductionPartMark(order_id=busy, drawing_key=key(busy, f"s{j}"), part=part, state="BASIC" if part == "cut" else "NONE",
                                              updated_at=now))
    db_session.commit()
    login(client, admin)
    data, seen = _counted(client, busy, other)
    assert len(data["marks"]) == 6 and sorted(data["blocks"]) == sorted([str(busy), str(other)])
    reads = _json_reads(seen)
    assert len(reads) == 1 and sorted(reads[0][1]) == sorted([busy, other])


def test_partner_account_is_refused_403(client):
    oid = make_order(1)
    db_session.add(ProductionPartMark(order_id=oid, drawing_key=key(oid, "s0"), part="cut", state="BASIC", updated_at=now_utc_naive()))
    org = PartnerOrg(name="가짜협력")
    db_session.add(org)
    db_session.commit()
    login(client, make_user("협력직원", team=None, role="PARTNER", partner_org_id=org.id))
    resp = client.get(SYNC, query_string={"order_ids": str(oid), "since": SINCE})
    body = resp.get_json()
    assert resp.status_code == 403 and body["success"] is False and not (body.get("data") or {}).get("marks")
    assert "blocks" not in (body.get("data") or {})


# --------------------------------------------------------------------------- #
# 수명 · 칸 수
# --------------------------------------------------------------------------- #
def test_a_write_that_skips_the_version_is_caught_after_five_minutes(client, monkeypatch):
    admin = make_user("한관리", team=None, role="ADMIN")
    oid = make_order(2)
    login(client, admin)
    clock = [1000.0]
    monkeypatch.setattr(sb, "_clock", lambda: clock[0])
    assert _sync(client, oid)["blocks"][str(oid)]["all"] is None
    patch(oid, production={"steps": [], "hold": {"active": True, "reason": "자재 기다림"}})  # 버전 안 올리는 쓰기 흉내
    clock[0] += sb.CACHE_TTL_SECONDS - 1
    assert _sync(client, oid)["blocks"][str(oid)]["all"] is None  # 수명 안 = 캐시 그대로
    clock[0] += 2
    assert _sync(client, oid)["blocks"][str(oid)]["all"]["kind"] == "hold"  # 수명 지남 = 다시 읽음


def test_cache_keeps_at_most_its_size_and_drops_the_least_recent(monkeypatch):
    monkeypatch.setattr(sb, "CACHE_SIZE", 3)
    sb.clear_sync_cache()
    loads: list[list[int]] = []

    def load(ids):
        loads.append(sorted(ids))
        return {i: {"workflow": {"stage": "PRODUCTION"}} for i in ids}

    heads = {i: (1, "PRODUCTION", "PRODUCTION") for i in (1, 2, 3)}
    sb.cached_blocks(heads, load)
    sb.cached_blocks({1: heads[1]}, load)  # 1 을 최근으로
    sb.cached_blocks({4: (1, "PRODUCTION", "PRODUCTION")}, load)  # 넘침 → 가장 오래 안 쓴 2 를 버림
    sb.cached_blocks({i: (1, "PRODUCTION", "PRODUCTION") for i in (1, 2, 3, 4)}, load)
    assert loads == [[1, 2, 3], [4], [2]] and len(sb._cache) == 3
    sb.cached_blocks({1: (2, "PRODUCTION", "PRODUCTION")}, load)  # 버전이 오르면 새 열쇠
    assert loads[-1] == [1]
    sb.clear_sync_cache()


# --------------------------------------------------------------------------- #
# 쓰기 길마다 버전이 오르고 받아 오기 막힘이 따라 바뀐다
# --------------------------------------------------------------------------- #
def _bumps(client, oid: int, write, want) -> None:
    """쓰기 전 막힘을 캐시에 채운 뒤 쓰기 → 버전이 오르고, 받아 오기가 그 주문 JSON 을 다시 읽어 막힘이 바뀐 ``want(blocks)``."""
    was = _sync(client, oid)["blocks"][str(oid)]
    before = _version(oid)
    resp = write()
    assert resp.status_code == 200, resp.get_json()
    assert _version(oid) > before, "쓰기 길이 mutation_version 을 안 올림"
    data, seen = _counted(client, oid)
    assert [p for _st, p in _json_reads(seen)] == [(oid,)]
    assert want(data["blocks"][str(oid)]) and data["blocks"][str(oid)] != was, (was, data["blocks"][str(oid)])


def test_hold_on_and_off_bump_the_version(client, quiet):
    oid = make_order(2)
    _run(oid)
    login(client, make_user("한관리", team=None, role="ADMIN"))
    hold = lambda on: client.post(f"/api/orders/{oid}/production/hold", json={"active": on, "reason": "자재 기다림"})  # noqa: E731
    _bumps(client, oid, lambda: hold(True), lambda b: b["all"]["text"] == "보류 · 자재 기다림")
    _bumps(client, oid, lambda: hold(False), lambda b: b["all"] is None)


def test_drawing_team_fix_start_and_stop_bump_the_version(client, quiet):
    oid = make_order(3)
    login(client, make_user("김도면", team="DRAWING"))
    body = {"targets": [{"sheet_id": "s1"}]}
    _bumps(client, oid, lambda: client.post(f"/api/orders/{oid}/drawing/fix/start", json=body),
           lambda b: b["all"] is None and list(b["keys"]) == [key(oid, "s1")] and b["keys"][key(oid, "s1")]["why"] == REVISING_MESSAGE)
    _bumps(client, oid, lambda: client.post(f"/api/orders/{oid}/drawing/fix/stop", json=body), lambda b: b == {"all": None, "keys": {}})


def test_sales_revision_request_bumps_the_version(client, quiet):
    oid = make_order(3)
    login(client, make_user("한관리", team="CS", role="ADMIN"))
    _bumps(client, oid, lambda: client.post(f"/api/orders/{oid}/request-revision",
                                            json={"note": "측판 길이", "target_drawing_keys": [key(oid, "s2")]}),
           lambda b: list(b["keys"]) == [key(oid, "s2")])


def test_complete_uncomplete_and_production_cancel_bump_the_version(client, quiet):
    oid = make_order(2)
    _run(oid)
    login(client, make_user("한관리", team=None, role="ADMIN"))
    _bumps(client, oid, lambda: client.post(f"/api/orders/{oid}/production/complete", json={}),
           lambda b: b["all"] is not None and b["all"]["text"] == "제작 완료" and b["all"]["code"] == "NOT_IN_PRODUCTION")
    _bumps(client, oid, lambda: client.post(f"/api/orders/{oid}/production/uncomplete", json={}), lambda b: b["all"] is None)
    assert client.post(f"/api/orders/{oid}/production/hold", json={"active": True, "reason": "자재"}).status_code == 200
    _bumps(client, oid, lambda: client.post(f"/api/orders/{oid}/production/cancel", json={}),
           lambda b: b["all"] is None)  # 제작 취소는 보류를 정리한다(F-1) — 막힘이 풀린다


def test_drawing_resend_in_production_bumps_the_version(client, quiet):
    drawer, sales = hotfix_user("cache_drawer", team="DRAWING"), hotfix_user("cache_sales", team="SALES")
    oid = hotfix_order(drawer.id, sales.id)
    patch(oid, drawing_status="RETURNED")  # 영업 요청으로 통째 고치는 중(대상 없음) — 다시 보내면 풀린다
    login(client, drawer)
    _bumps(client, oid, lambda: _send(client, oid), lambda b: b["all"] is None)
