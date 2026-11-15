"""실측 예약 알림톡 제안(훑기 규칙 O1 · 할 일 ``send_measure_alimtalk``) — 점검 2차 w6-01.

완료 기준(시공일 안내 ``construction_notice`` 와 같은 수준):
- ① 제안 기간은 실측일(한국 날짜 — 여러 날이면 마지막 날)이 끝나는 때에 끝난다(넣을 값이 비어도 7일이 아니다).
- ② 승인 첫 걸음 · 실행기가 지금 주문을 다시 읽어 실측일이 지났으면 '실측일이 지났어요', 지금 일정으로 이미 나간 기록이 있으면
  '이 실측 예약 안내는 이미 보냈어요'로 막는다 — 보내는 함수는 불리지 않는다. 대조군: 옛 일정의 자동 발송 · 실패 기록은 막지 않는다.
- ③ 실측 일정이 바뀌면 옛 제안은 되맞추기(승인 대기 읽기 · 밤 단계)와 승인 첫 걸음에서 낡은 것(``superseded``)으로 닫힌다.
  훑기가 만든 제안은 만든 그 자리에서 낡은 것이 아니다(겹침 열쇠 상황이 같은 값).
- 주문 화면 손 발송('누른 만큼 나간다')과 자동 발송 계약(``kakao_alimtalk``)은 건드리지 않는다.
**알림톡은 보내지 않는다** — 보내는 함수는 모든 시험에서 가짜(불리면 기록). 합성 주문 · 합성 글만.
"""

from __future__ import annotations

import datetime

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.persistence.graft.models import ErpActionProposal
from foms.services import kakao_alimtalk as kakao
from foms.services.datetime_kst import get_today_kst, now_utc_naive
from foms.services.erp_actions import construction_notice, lifecycle, measure_notice, preview
from foms.services.erp_actions.lifecycle import ActionError, approve, propose, reconcile
from foms.services.erp_actions.runners import SERVICE_RUNNERS, RunRequest
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.graft_flags import FLAGS
from models import Order, User

NOW = now_utc_naive()
_KST = datetime.timedelta(hours=9)


def _day(offset: int) -> str:
    return (get_today_kst() + datetime.timedelta(days=offset)).isoformat()


def _kst_midnight_after(day: str) -> datetime.datetime:
    """그 날이 끝나는 때(한국 자정)를 UTC naive 로."""
    return datetime.datetime.combine(datetime.date.fromisoformat(day) + datetime.timedelta(days=1), datetime.time()) - _KST


@pytest.fixture(autouse=True)
def world(app, monkeypatch):
    """접목판 env 를 끄고 알림톡 설정은 '있음'으로 — 보내는 함수는 가짜(불린 주문 번호만 모은다)."""
    for env in FLAGS.values():
        monkeypatch.delenv(f"{env}_ENABLED", raising=False)
        monkeypatch.delenv(f"{env}_COHORT", raising=False)
    monkeypatch.setattr(kakao, "is_configured", lambda brand=None: True)
    monkeypatch.setattr(kakao, "brand_config", lambda brand=None: {"pf_id": "PF-X", "template_id": "TPL-X"})
    sent: list[int] = []
    monkeypatch.setattr(kakao, "send_alimtalk", lambda order_id, **kw: (sent.append(order_id),
                                                                         {"sent": True, "error": None})[1])
    monkeypatch.setattr(kakao, "_solapi_send", lambda **kw: pytest.fail("Solapi 를 부르면 안 된다"))
    yield sent
    db_session.rollback()


def _sd(days: str, time: str = "오전", **extra) -> dict:
    return {"workflow": {"stage": "MEASURE"}, "parties": {"customer": {"name": "합성손님", "phone": "010-0000-0003"}},
            "schedule": {"measurement": {"date": days, "time": time}}, **extra}


def _order(days: str, time: str = "오전", **extra) -> Order:
    sd = _sd(days, time, **extra)
    order = Order(received_date="2030-01-01", customer_name="합성손님", phone="010-0000-0000", address="합성 주소",
                  product="합성 품목", status="MEASURE", is_erp_order=True, structured_data=sd)
    sync_erp_flat_columns(order, sd)
    db_session.add(order)
    db_session.commit()
    return order


def _admin() -> User:
    user = User(username="mn_admin", password=generate_password_hash("pw"), role="ADMIN", name="합성 관리자",
                is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _propose(order: Order) -> ErpActionProposal | None:
    row = propose(db_session, action="send_measure_alimtalk", proposed_by="agent:ops", order=order, params={},
                  reason="합성 이유", evidence=[], source_kind="sweep", source_ref="1", level=1, now=NOW)
    db_session.commit()
    return row


def _set(order: Order, **changes) -> None:
    sd = dict(order.structured_data)
    sd.update(changes)
    order.structured_data = sd
    sync_erp_flat_columns(order, sd)
    db_session.commit()


def _approve(row: ErpActionProposal, actor: User):
    return approve(db_session, row.id, actor=actor, runners=SERVICE_RUNNERS, base_version=row.base_version, now=NOW)


# ── ① 기간 끝 ────────────────────────────────────────────────────────────
def test_the_proposal_ends_when_the_measurement_day_ends(world):
    tomorrow = _order(_day(1))
    row = _propose(tomorrow)
    assert row.expires_at == _kst_midnight_after(_day(1)) < NOW + datetime.timedelta(days=7)
    two_days = _order(f"{_day(1)}, {_day(3)}")  # 여러 날이면 마지막 날
    assert _propose(two_days).expires_at == _kst_midnight_after(_day(3))
    assert lifecycle._expiry(NOW, {}) == NOW + datetime.timedelta(days=7)  # 날짜가 없는 할 일은 그대로 7일


# ── ② 막는 조건(지금 주문을 다시 읽는다) ─────────────────────────────────────
def test_check_blocks_a_past_measurement_like_the_construction_notice(world, monkeypatch):
    assert preview.check("send_measure_alimtalk", _order(_day(-3)), {}) == "실측일이 지났어요."
    assert preview.check("send_measure_alimtalk", _order(f"{_day(-3)}, {_day(2)}"), {}) is None  # 남은 날이 있다
    assert preview.check("send_measure_alimtalk", _order(_day(0)), {}) is None  # 오늘은 아직 지나지 않았다
    monkeypatch.setattr(construction_notice.notice, "block_reason", lambda order: None)
    site = Order(received_date="2030-01-01", customer_name="합성손님", phone="010-0000-0000", address="합성 주소",
                 product="합성 품목", status="CONSTRUCTION", is_erp_order=True,
                 structured_data={"workflow": {"stage": "CONSTRUCTION"},
                                  "schedule": {"construction": {"date": _day(-2), "time": "오전"}}})
    db_session.add(site)
    db_session.commit()
    assert construction_notice.check(site, {}) == "시공일이 지났어요."  # 대조군 — 시공일 안내도 같은 말


@pytest.mark.parametrize("key, sent_for_now", [
    ("auto_now", True), ("manual", True), ("action", True), ("auto_old_date", False), ("failed", False)])
def test_check_blocks_a_notice_already_sent_for_this_schedule(world, key, sent_for_now):
    order = _order(_day(1))
    keys = {"auto_now": kakao.build_dedupe_key(order.id, order.structured_data),
            "manual": f"alimtalk:measure:{order.id}:manual:abc", "action": f"alimtalk:measure:{order.id}:action:9",
            "auto_old_date": f"alimtalk:measure:{order.id}:{_day(4)}:오전", "failed": None}
    record = {"sent_at": NOW.isoformat(), "message_id": "m-1", "error": None, "dedupe_key": keys[key]}
    if key == "failed":
        record.update(sent_at=None, message_id=None, error="network",
                      dedupe_key=kakao.build_dedupe_key(order.id, order.structured_data))
    _set(order, alimtalk_measurement=record)
    expected = "이 실측 예약 안내는 이미 보냈어요." if sent_for_now else None
    assert preview.check("send_measure_alimtalk", order, {}) == expected


def test_approving_after_the_measurement_day_never_sends(world, monkeypatch):
    admin, order = _admin(), _order(_day(1))
    row = _propose(order)
    later = get_today_kst() + datetime.timedelta(days=3)  # 실측 뒤 — 제안 기간 시계는 그대로 두고 오늘만 옮긴다
    monkeypatch.setattr(measure_notice, "get_today_kst", lambda: later)
    with pytest.raises(ActionError) as blocked:
        _approve(row, admin)
    assert blocked.value.code == "ACTION_PRECONDITION" and blocked.value.message == "실측일이 지났어요."
    assert world == []
    db_session.expire_all()
    assert db_session.get(ErpActionProposal, row.id).status == "open"


def test_approving_after_an_auto_send_for_the_same_schedule_never_sends_twice(world):
    admin, order = _admin(), _order(_day(1))
    row = _propose(order)
    _set(order, alimtalk_measurement={"sent_at": NOW.isoformat(), "message_id": "m-auto", "error": None,
                                      "dedupe_key": kakao.build_dedupe_key(order.id, order.structured_data)})
    with pytest.raises(ActionError) as blocked:
        _approve(row, admin)
    assert blocked.value.message == "이 실측 예약 안내는 이미 보냈어요." and world == []


def test_the_runner_rechecks_under_the_order_before_sending(world, monkeypatch):
    admin, order = _admin(), _order(_day(1))
    request = RunRequest(proposal_id=41, action="send_measure_alimtalk", order_id=order.id, params={}, actor=admin,
                         now=NOW)
    later = get_today_kst() + datetime.timedelta(days=2)
    monkeypatch.setattr(measure_notice, "get_today_kst", lambda: later)
    out = SERVICE_RUNNERS["send_measure_alimtalk"](db_session, request)
    assert out.status == "blocked" and out.message == "실측일이 지났어요." and world == []


def test_a_fresh_proposal_still_runs_once(world):
    """대조군 — 내일 실측 · 보낸 기록 없음이면 승인하면 한 번 나간다(막이가 정상 길을 막지 않는다)."""
    admin, order = _admin(), _order(_day(1))
    row = _propose(order)
    assert _approve(row, admin)["status"] == "executed" and world == [order.id]


# ── ③ 실측 일정이 바뀌면 옛 제안은 낡은 것 ─────────────────────────────────
def test_a_schedule_change_closes_the_old_proposal_on_reconcile(world):
    order = _order(_day(1))
    row, same = _propose(order), _propose(_order(_day(1)))
    assert reconcile(db_session, NOW) == 0  # 만든 그 자리에서는 낡지 않았다
    _set(order, schedule={"measurement": {"date": _day(3), "time": "오전"}})
    assert reconcile(db_session, NOW) == 1
    db_session.commit()
    db_session.expire_all()
    assert db_session.get(ErpActionProposal, row.id).status == "superseded"
    assert db_session.get(ErpActionProposal, same.id).status == "open"  # 일정이 그대로인 제안은 그대로


def test_a_time_change_also_makes_it_stale_and_approve_closes_it(world):
    admin, order = _admin(), _order(_day(1), "오전")
    row = _propose(order)
    _set(order, schedule={"measurement": {"date": _day(1), "time": "오후"}})
    with pytest.raises(ActionError) as stale:
        _approve(row, admin)
    assert stale.value.code == "ACTION_NOT_OPEN" and "실측 일정이 바뀌었어요" in stale.value.message
    assert world == []
    db_session.expire_all()
    assert db_session.get(ErpActionProposal, row.id).status == "superseded"
    assert _propose(db_session.get(Order, order.id)) is not None  # 새 일정으로는 다시 제안할 수 있다


def test_the_manual_button_contract_is_untouched(world):
    """주문 화면 손 발송은 일정 서명으로 막지 않는다(누른 만큼 나간다) — 막이는 제안 쪽에만 있다."""
    order = _order(_day(1))
    _set(order, alimtalk_measurement={"sent_at": NOW.isoformat(), "message_id": "m-d", "error": None,
                                      "dedupe_key": "alimtalk:measure:draft:k:manual:x",
                                      "draft_schedule": kakao.build_draft_schedule_signature(order.structured_data)})
    assert kakao._already_sent(order, f"alimtalk:measure:{order.id}:manual:new", manual=True) is False
    assert kakao._already_sent(order, kakao.build_dedupe_key(order.id, order.structured_data)) is True
    assert preview.check("send_measure_alimtalk", order, {}) == "이 실측 예약 안내는 이미 보냈어요."
