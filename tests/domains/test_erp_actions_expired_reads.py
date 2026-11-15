"""기간이 지난 제안을 읽는 길(점검 2차 w6-12 · w5-02 — F-13 남은 반쪽).

완료 기준:
- 기간이 지났지만 밤 정리 전이라 아직 ``open`` 인 제안은 수 배지 · 주문 칩(PC · 태블릿 상자)에서 빠지고, 승인 대기 읽기(되맞추기를
  먼저 돌린다)는 그 줄을 ``expired`` 로 닫고 카드에 싣지 않는다 — '보이는데 누르면 막히는' 카드가 없다. 대조군: 기간이 남은 제안 ·
  나중에 접은 제안은 지금과 같다.
- 승인은 막히고 그 까닭은 '기간이 지난 제안이에요'(실제 까닭 — '이미 처리된 제안이에요'가 아니다).
- 밤 단계 차례('끝남 닫기' → '훑기'): 훑기 제안의 7일은 7일째 0시(한국)에 끝나 그 밤 '끝남 닫기'가 닫고 이어 도는 훑기가 같은 밤 다시
  만든다(만든 때 + 7일이면 그 밤을 몇 분 차이로 비껴가 하루 동안 아무 제안도 없거나, 고치기 전에는 보이는데 못 누르는 카드가 남았다).
합성 계정 · 합성 주문만. 바깥 호출 없음.
"""

from __future__ import annotations

import datetime

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.persistence.graft.models import ErpActionProposal
from foms.services.ai_staff import sweeps
from foms.services.datetime_kst import get_today_kst, now_utc_naive
from foms.services.erp_actions import views
from foms.services.erp_actions.lifecycle import ActionError, approve, expire_due, propose
from foms.services.erp_actions.runners import SERVICE_RUNNERS
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.graft_flags import FLAGS
from models import Order, User

BASE = "/api/erp-actions"
_KST = datetime.timedelta(hours=9)


def _day(offset: int) -> str:
    return (get_today_kst() + datetime.timedelta(days=offset)).isoformat()


@pytest.fixture
def world(app, monkeypatch):
    """접목판 스위치를 끈 뒤 화면 · 할 일 · 훑기만 켠다 — 관리자 하나 · 로그인한 시험 손님."""
    for env in FLAGS.values():
        monkeypatch.delenv(f"{env}_ENABLED", raising=False)
        monkeypatch.delenv(f"{env}_COHORT", raising=False)
    for env in ("FOMS_GRAFT_BRAIN_UI", "FOMS_GRAFT_ACTIONS"):
        monkeypatch.setenv(f"{env}_ENABLED", "1")
        monkeypatch.setenv(f"{env}_COHORT", "all")
    monkeypatch.setenv("FOMS_GRAFT_PROPOSERS_ENABLED", "1")
    admin = User(username="ex_admin", password=generate_password_hash("pw"), role="ADMIN", name="합성 관리자",
                 is_active=True)
    db_session.add(admin)
    db_session.commit()
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = admin.id
    yield {"admin": admin, "client": client}
    db_session.rollback()


def _order(stage: str = "RECEIVED", stage_days: float = 0) -> Order:
    sd = {"workflow": {"stage": stage,
                       "stage_updated_at": (now_utc_naive() - datetime.timedelta(days=stage_days)).isoformat()}}
    order = Order(received_date="2030-01-01", customer_name="합성손님", phone="010-0000-0000", address="합성 주소",
                  product="합성 품목", status=stage, is_erp_order=True, structured_data=sd)
    sync_erp_flat_columns(order, sd)
    db_session.add(order)
    db_session.commit()
    return order


def _propose(order: Order, days: int = 9) -> ErpActionProposal:
    row = propose(db_session, action="schedule_construction", proposed_by="agent:schedule", order=order,
                  params={"date": _day(days), "time": "오전"}, reason="합성 이유", evidence=[], source_kind="sweep",
                  source_ref="1", level=2, now=now_utc_naive())
    db_session.commit()
    return row


def _expire(row: ErpActionProposal) -> None:
    row.expires_at = now_utc_naive() - datetime.timedelta(minutes=5)  # 밤 정리 전 — 상태는 open 그대로
    db_session.commit()


def test_badge_and_order_chips_leave_out_an_expired_open_proposal(world):
    admin = world["admin"]
    alive, gone, folded = _order(), _order(), _order()
    keep, old, nap = _propose(alive), _propose(gone, 10), _propose(folded, 11)
    _expire(old)
    nap.snoozed_until = now_utc_naive() + datetime.timedelta(hours=3)
    db_session.commit()
    assert views.badge(db_session, admin)["actions"] == 1  # 기간이 남은 것만 — 나중에 접은 것은 예전처럼 빠진다
    chips = views.open_for_orders(db_session, admin, [alive.id, gone.id, folded.id])
    assert set(chips) == {alive.id} and chips[alive.id]["id"] == keep.id
    db_session.expire_all()
    assert db_session.get(ErpActionProposal, old.id).status == "open"  # 읽기만 — 닫는 것은 되맞추기 · 밤 정리


def test_the_inbox_read_closes_an_expired_card_before_listing(world):
    alive, gone = _order(), _order()
    keep, old = _propose(alive), _propose(gone, 10)
    _expire(old)
    keep_id, old_id = keep.id, old.id  # 요청이 끝나면 세션이 닫혀 줄이 떨어진다 — 번호만 들고 간다
    resp = world["client"].get(f"{BASE}/inbox")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    cards = resp.get_json()["data"]["cards"]
    assert [card["id"] for card in cards] == [keep_id]
    assert db_session.get(ErpActionProposal, old_id).status == "expired"


def test_approving_an_expired_proposal_names_the_real_reason(world):
    row = _propose(_order())
    _expire(row)
    with pytest.raises(ActionError) as late:
        approve(db_session, row.id, actor=world["admin"], runners=SERVICE_RUNNERS, base_version=row.base_version,
                now=now_utc_naive())
    assert late.value.code == "ACTION_NOT_OPEN" and late.value.message == "기간이 지난 제안이에요 — 새로 불러와 주세요."


def _night(day: datetime.date, minute: int) -> datetime.datetime:
    """그 날 한국 02:MM(밤 단계 시각)을 UTC naive 로."""
    return datetime.datetime.combine(day, datetime.time(2, minute)) - _KST


def test_the_night_after_seven_days_closes_and_remakes_in_the_same_run(world):
    """훑기가 만든 줄의 7일은 7일째 0시(한국)에 끝난다 — 그 밤 '끝남 닫기'가 닫고 이어 도는 훑기가 같은 밤 다시 만든다."""
    today = get_today_kst()
    order = _order("DRAWING", stage_days=3)
    first_night = _night(today, 10)
    assert sweeps.run_sweep(db_session, now=first_night, today=today).by_rule["O3"] == 1
    db_session.commit()
    (row,) = db_session.query(ErpActionProposal).filter(ErpActionProposal.order_id == order.id).all()
    week_end = datetime.datetime.combine(today + datetime.timedelta(days=7), datetime.time()) - _KST
    assert row.expires_at == week_end < first_night + datetime.timedelta(days=7)
    assert views.badge(db_session, world["admin"], now=week_end + datetime.timedelta(hours=1))["actions"] == 0  # 보이지 않음
    later = _night(today + datetime.timedelta(days=7), 5)  # 지난주보다 5분 이른 밤 단계
    assert expire_due(db_session, later) == 1
    assert sweeps.run_sweep(db_session, now=later, today=today + datetime.timedelta(days=7)).by_rule["O3"] == 1
    db_session.commit()
    db_session.expire_all()
    rows = db_session.query(ErpActionProposal).filter(ErpActionProposal.order_id == order.id).order_by(
        ErpActionProposal.id).all()
    assert [r.status for r in rows] == ["expired", "open"]
