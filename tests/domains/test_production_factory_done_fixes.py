"""공장마다 제작 완료 고침 한 판(3단계 ⑥ 검토 뒤) — 막다른 길 둘 · 감사 길 · 공장 단추 다시 그리기 · 다시 보냄 · 문지기 동작 고정.

1. 섞인 주문 [완료 취소]를 누른 사람 공장 장이 주문에 없으면(장이 모두 2공장 · 1공장 계정) 다시 열린 공장이 없어 막다른 길이었다
   → 있는 공장을 모두 연다. 열린 뒤 2공장 사람이 다시 완료하면 시공 대기까지.
2. 관리자 강제 단계 되돌리기(시공 대기 → 생산)가 공장 완료 표지를 남겨 같은 막다른 길 → 생산 또는 그 앞으로 되돌리면 표지를 지운다.
3. factory-done 감사는 지금 [제작 완료]와 같은 길(log_access — 대신 로그인 ``impersonated_by``).
4. 공정 API 응답에 공장마다 준비 · 까닭(섞인 주문만) — 작업 시트 공장 단추가 손 체크 뒤 다시 그린다.
5. 같은 멱등 열쇠로 다시 온 공장 완료는 감사 줄을 더 안 쓰고 ``changed: false``.
6. 옮긴 제작 완료 본문 · 마지막 공장 길이 같은 검수까지 문지기를 실제로 지난다(소스 글이 아니라 동작으로).

되돌리면 실패: 1 · 2 막다른 길(작업 시트에 완료 단추 없음) · 대신 로그인 흔적 없음 · 공정 응답에 공장 값 없음 · 다시 보냄에 감사 둘 ·
문지기를 건너뜀. 대조군: 한 공장 주문 공정 응답 · 앞으로 가는 강제 변경은 그대로.
"""
from __future__ import annotations

from pathlib import Path

from flask import jsonify

import foms.services.production.order_write_helpers as helpers_mod
from db import db_session
from models import OrderEvent, SecurityLog
from tests.support.production_factory_seed import TABLET, factory_user, mixed_order, put_mark, set_cookies, set_factory_done
from tests.support.production_part_claim_seed import fresh, login

ROOT = Path(__file__).resolve().parents[2]
PARTS = ("cut", "edge", "assemble", "inspect")


def _done(seed, js, who) -> None:
    for j in js:
        for part in PARTS:
            put_mark(seed, j, part, "DONE", who)


def _factory(client, oid: int, factory: int, done: bool = True, **extra):
    return client.post(f"/api/orders/{oid}/production/factory-done", json={"factory": factory, "done": done, **extra})


def _marks(oid: int):
    return (fresh(oid).structured_data.get("production") or {}).get("factory_done")


def _sheet(client, oid: int) -> str:
    set_cookies(client, TABLET)
    res = client.get(f"/erp/production/sheet/{oid}")
    assert res.status_code == 200
    return res.get_data(as_text=True)


def test_uncomplete_by_account_whose_factory_is_absent_reopens_all(client):
    seed = mixed_order(2, f2=(0, 1))  # 장이 모두 2공장
    insp2 = factory_user("강검수", factory=2, part="inspect")
    _done(seed, (0, 1), insp2)
    login(client, factory_user("정관리", role="ADMIN", team="CS"))
    assert client.post(f"/api/orders/{seed.id}/production/complete", json={}).status_code == 200
    assert set(_marks(seed.id)) == {"2"}
    login(client, factory_user("박반장", lead=True))  # 1공장 반장 — 이 주문에 1공장 장이 없다
    assert client.post(f"/api/orders/{seed.id}/production/uncomplete", json={}).status_code == 200
    assert fresh(seed.id).erp_stage_code == "PRODUCTION" and not _marks(seed.id)  # 2공장도 다시 열림
    event = db_session.query(OrderEvent).filter_by(order_id=seed.id, event_type="PRODUCTION_COMPLETE_REVERTED").one()
    assert event.payload["factories_reopened"] == [2]
    login(client, factory_user("강반장", factory=2, lead=True))
    assert 'data-tablet-sheet-action="production-complete"' in _sheet(client, seed.id)  # 남은 공장 하나 = [제작 완료]
    login(client, insp2)
    res = _factory(client, seed.id, 2)
    assert res.status_code == 200 and res.get_json()["data"]["final"] is True and fresh(seed.id).erp_stage_code == "CONSTRUCTION"


def test_uncomplete_by_present_factory_still_reopens_only_that_one(client):
    seed = mixed_order(3, f2=(2,))  # 대조군: 누른 사람 공장이 주문에 있으면 지금처럼 그 공장만
    _done(seed, range(3), factory_user("윤검수", part="inspect"))
    login(client, factory_user("정관리", role="ADMIN", team="CS"))
    assert client.post(f"/api/orders/{seed.id}/production/complete", json={}).status_code == 200
    login(client, factory_user("강반장", factory=2, lead=True))
    assert client.post(f"/api/orders/{seed.id}/production/uncomplete", json={}).status_code == 200
    assert set(_marks(seed.id)) == {"1"}


def test_admin_regress_override_clears_marks_and_buttons_come_back(client):
    seed = mixed_order(3, f2=(2,))
    _done(seed, range(3), factory_user("윤검수", part="inspect"))
    admin = factory_user("정관리", role="ADMIN", team="CS")
    login(client, admin)
    assert client.post(f"/api/orders/{seed.id}/production/complete", json={}).status_code == 200
    res = client.post(f"/api/orders/{seed.id}/workflow/stage-override",
                      json={"to_stage": "PRODUCTION", "reason": "다시 만듦", "confirm": True})
    assert res.status_code == 200, res.get_data(as_text=True)
    assert fresh(seed.id).erp_stage_code == "PRODUCTION" and not _marks(seed.id)
    event = db_session.query(OrderEvent).filter_by(order_id=seed.id, event_type="STAGE_OVERRIDE").one()
    assert event.payload["factories_reopened"] == [1, 2]
    html = _sheet(client, seed.id)
    assert "1공장 제작 중 · 2공장 제작 중" in html  # 공장 줄이 다시 '제작 중'(회차는 닫혀 제작 대기 — [제작 시작] 길은 그대로)
    assert client.post(f"/api/orders/{seed.id}/production/start", json={}).status_code == 200
    html = _sheet(client, seed.id)
    assert "<b>1공장 제작 완료</b>" in html and "<b>2공장 제작 완료</b>" in html  # 공장 완료 단추가 다시 뜬다


def test_forward_override_keeps_marks():
    from foms.services.orders.stage_override import apply_stage_override
    seed = mixed_order(3, f2=(2,))
    set_factory_done(seed.id, 2, [seed.keys[2]])
    admin = factory_user("정관리", role="ADMIN", team="CS")
    order = fresh(seed.id)
    payload = apply_stage_override(order=order, to_stage="CONSTRUCTION", reason="정리", user_id=admin.id, db=db_session)
    db_session.commit()
    assert "factories_reopened" not in payload and set(_marks(seed.id)) == {"2"}  # 앞으로 가는 변경은 그대로


def test_factory_done_audit_goes_through_log_access_with_impersonator(client):
    seed = mixed_order(3, f2=(2,))
    insp1 = factory_user("윤검수", part="inspect")
    _done(seed, range(3), insp1)
    set_factory_done(seed.id, 1, list(seed.keys[:2]), by_name="윤검수")
    admin = factory_user("정관리", role="ADMIN", team="CS")
    insp2 = factory_user("강검수", factory=2, part="inspect")
    login(client, insp2)
    with client.session_transaction() as sess:
        sess["impersonating_from"] = admin.id  # 관리자가 강검수로 대신 로그인
    res = _factory(client, seed.id, 2)
    assert res.status_code == 200 and res.get_json()["data"]["final"] is True
    db_session.expire_all()
    row = db_session.query(SecurityLog).filter_by(target_id=seed.id, action="PRODUCTION_COMPLETED").one()
    assert row.user_id == insp2.id and row.detail["impersonated_by"] == admin.id


def test_steps_api_carries_factory_readiness_only_for_mixed_orders(client):
    seed = mixed_order(2, f2=(1,), steps_done=("cut", "edge", "assemble"))
    login(client, factory_user("강반장", factory=2, lead=True))
    html = _sheet(client, seed.id)
    assert 'data-foms-sheet-factory="2" data-done="1"' in html and "2공장에 아직 미완료가 있어요 — 검수 1장" in html  # 회색 + 까닭
    data = client.post(f"/api/orders/{seed.id}/production/steps", json={"key": "inspect", "done": True}).get_json()["data"]
    assert data["factories"]["2"] == {"ready": True, "why": "", "done": False}
    off = client.post(f"/api/orders/{seed.id}/production/steps", json={"key": "inspect", "done": False}).get_json()["data"]
    assert off["factories"]["2"]["ready"] is False and off["factories"]["2"]["why"] == "2공장에 아직 미완료가 있어요 — 검수 1장"
    plain = mixed_order(2, f2=())
    assert "factories" not in client.get(f"/api/orders/{plain.id}/production/steps").get_json()["data"]  # 한 공장 주문 그대로
    js = (ROOT / "static/js/production/foms-production-sheet-factory.js").read_text(encoding="utf-8")
    parts = (ROOT / "static/js/production/foms-production-sheet-parts.js").read_text(encoding="utf-8")
    assert "new CustomEvent('foms:sheet-steps'" in parts and "addEventListener('foms:sheet-steps'" in js


def test_same_idempotency_key_replay_writes_no_second_audit(client):
    seed = mixed_order(3, f2=(2,))
    _done(seed, range(3), factory_user("윤검수", part="inspect"))
    insp2 = factory_user("강검수", factory=2, part="inspect")
    login(client, insp2)
    first = _factory(client, seed.id, 2, idempotency_key="k-fac-1")
    assert first.status_code == 200 and first.get_json()["data"]["changed"] is True
    login(client, factory_user("정관리", role="ADMIN", team="CS"))
    assert _factory(client, seed.id, 2, done=False).status_code == 200  # 그사이 관리자가 완료 취소
    login(client, insp2)
    again = _factory(client, seed.id, 2, idempotency_key="k-fac-1")  # 같은 열쇠 다시 보냄(연결이 얼었다 풀림)
    assert again.status_code == 200 and again.get_json()["data"]["changed"] is False
    assert not _marks(seed.id)  # 쓰기 0
    db_session.expire_all()
    assert db_session.query(SecurityLog).filter_by(target_id=seed.id, action="PRODUCTION_FACTORY_COMPLETED").count() == 1


def test_complete_and_last_factory_both_pass_the_same_inspect_gate(client, monkeypatch):
    blocked = {"success": False, "code": "GATE_PROBE", "message": "문지기"}

    def _probe(sd, marks):
        return blocked

    monkeypatch.setattr(helpers_mod, "complete_block_body", _probe)  # 검수까지 문지기 한 곳을 막는다
    one = mixed_order(2, f2=())
    _done(one, range(2), factory_user("윤검수", part="inspect"))
    login(client, factory_user("정관리", role="ADMIN", team="CS"))
    res = client.post(f"/api/orders/{one.id}/production/complete", json={})
    assert res.status_code == 409 and res.get_json()["code"] == "GATE_PROBE"  # 옮긴 본문이 문지기를 부른다
    mixed = mixed_order(3, f2=(2,))
    _done(mixed, range(3), factory_user("윤검수", part="inspect"))
    set_factory_done(mixed.id, 1, list(mixed.keys[:2]))
    login(client, factory_user("강검수", factory=2, part="inspect"))
    res = _factory(client, mixed.id, 2)
    assert res.status_code == 409 and res.get_json()["code"] == "GATE_PROBE"  # 마지막 공장 길도 같은 문지기
    assert fresh(mixed.id).erp_stage_code == "PRODUCTION" and set(_marks(mixed.id)) == {"1"}
    monkeypatch.undo()
    assert _factory(client, mixed.id, 2).status_code == 200  # 문지기를 풀면 지나간다(대조군)
    assert jsonify  # flask 응답 꼴(문지기가 돌려주는 튜플)과 같은 길
