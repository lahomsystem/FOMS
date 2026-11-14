"""시공일 안내 알림톡(설계서 2026-11-14-foms-graft 3.13 · D208 · D211 · D213) — 나가는 조건 · 한 번만 · 이력 · 감사 · 승인 창 줄 ·
실행기 셋(시공 잡기 · 방문 옮기기의 ``notify_customer`` 와 할 일 ``send_construction_alimtalk``).

완료 기준:
- 스위치 · Solapi 설정 · 서식 번호 가운데 하나라도 없으면 보내는 함수(가짜)가 **0 번** 불린다 — 셋 다 있으면 한 번.
- 같은 주문 · 같은 시공일 두 번째는 안 보냄(시공일이 바뀌면 다시) · 협력사 · 삭제 · 초안 · 전화 없음 · 시공일 없음은 안 보냄.
- 서식 변수는 넷뿐 — 시공 팀 · 인원 글 없음(D211). 이력 칸 꼴 · 감사 줄(본문 · 손님 정보 없음).
- ``notify_customer`` 참이면 시공일이 커밋된 **뒤** 한 통 · 거짓이면 0 · 보내기 실패는 시공일을 되돌리지 않는다(결과에 코드 한 줄).
- 스위치가 꺼졌을 때 승인 창 '바뀌는 칸' · '승인하면 차례로' · 실행 결과가 지금과 같다.

**바깥으로는 절대 보내지 않는다** — Solapi 호출부(``kakao_alimtalk._solapi_send``)는 모든 시험에서 가짜다. 합성 주문 · 합성 값만.
"""

from __future__ import annotations

import datetime

import pytest
from werkzeug.security import generate_password_hash

import foms.services.kakao_alimtalk as kakao
import foms.services.kakao_alimtalk_construction as kc
import foms.services.orders.construction_schedule as schedule_mod
from db import db_session
from foms.services.datetime_kst import get_today_kst, now_utc_naive
from foms.services.erp_actions import construction_notice as cn
from foms.services.erp_actions import preview, runners
from foms.services.erp_actions.registry import parse_params
from foms.services.erp_actions.runners import SERVICE_RUNNERS, RunRequest
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.graft_flags import FLAGS
from models import Order, PartnerOrg, SecurityLog, User

CUSTOMER = "합성손님"
PHONE = "010-0000-0001"
_SOLAPI_ENVS = ("SOLAPI_API_KEY", "SOLAPI_API_SECRET", "SOLAPI_SENDER_PHONE", "SOLAPI_SENDER_PHONE_HAUD",
                "SOLAPI_SENDER_PHONE_LAHOM", "SOLAPI_PF_ID_HAUD", "SOLAPI_PF_ID_LAHOM",
                "SOLAPI_TEMPLATE_CONSTRUCTION_ID_HAUD", "SOLAPI_TEMPLATE_CONSTRUCTION_ID_LAHOM")


def _day(offset: int) -> str:
    return (get_today_kst() + datetime.timedelta(days=offset)).isoformat()


@pytest.fixture(autouse=True)
def quiet(app, monkeypatch):
    """접목판 스위치 · Solapi env 를 모두 지우고, 바깥으로 나가는 것은 가짜로. 호출을 센다(진짜 Solapi 는 절대 안 부른다)."""
    for env in FLAGS.values():
        monkeypatch.delenv(f"{env}_ENABLED", raising=False)
        monkeypatch.delenv(f"{env}_COHORT", raising=False)
    for name in _SOLAPI_ENVS:
        monkeypatch.delenv(name, raising=False)
    calls: list[dict] = []

    def _fake_send(**kwargs):
        calls.append(kwargs)
        return f"MSG-{len(calls)}"

    monkeypatch.setattr(kakao, "_solapi_send", _fake_send)
    monkeypatch.setattr(kakao, "_solapi_send_text", lambda **kw: pytest.fail("문자는 보내지 않는다"))
    monkeypatch.setattr(runners, "finalize_schedule_notifications", lambda db, result: None)
    monkeypatch.setattr(schedule_mod, "apply_drawing_order_change_alert", lambda *a, **k: (None, False))
    monkeypatch.setattr(schedule_mod, "apply_production_change_alert", lambda *a, **k: ([], False))
    return calls


def _ready(mp) -> None:
    """쓸 수 있는 상태 — 스위치 + Solapi 설정 + 하우드 발신 프로필 · 서식 번호(합성 값)."""
    mp.setenv("FOMS_GRAFT_CONSTRUCTION_ALIMTALK_ENABLED", "1")
    for name, value in (("SOLAPI_API_KEY", "k"), ("SOLAPI_API_SECRET", "s"), ("SOLAPI_SENDER_PHONE", "0200000000"),
                        ("SOLAPI_PF_ID_HAUD", "PF-H"), ("SOLAPI_TEMPLATE_CONSTRUCTION_ID_HAUD", "TPL-C-H")):
        mp.setenv(name, value)


def _order(*, construction: str | None = None, time: str = "오전", phone: str | None = PHONE, status: str = "PRODUCTION",
           partner: bool = False, **sd_extra) -> Order:
    sd = {"workflow": {"stage": status}, "parties": {"customer": {"name": CUSTOMER, "phone": phone},
                                                     "orderer": {"name": "합성 주문처"}}, **sd_extra}
    if construction:
        sd["schedule"] = {"construction": {"date": construction, "time": time}}
    order = Order(received_date="2030-01-01", customer_name=CUSTOMER, phone="010-0000-0000", address="합성 주소",
                  product="합성 품목", status=status, is_erp_order=True, structured_data=sd)
    if partner:
        org = PartnerOrg(name="합성 협력사")
        db_session.add(org)
        db_session.flush()
        order.partner_org_id = org.id
    sync_erp_flat_columns(order, sd)
    db_session.add(order)
    db_session.commit()
    return order


def _admin() -> User:
    user = User(username="ca_admin", password=generate_password_hash("pw"), role="ADMIN", name="합성 관리자",
                is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _fresh(order_id: int) -> Order:
    db_session.expire_all()
    return db_session.get(Order, order_id)


def _send(order: Order, key: str = "alimtalk:construction:t:manual") -> dict:
    return kc.send_construction_alimtalk(order.id, manual_by=None, dedupe_key=key, source="erp_action:9")


def _audits() -> list[SecurityLog]:
    db_session.expire_all()
    return db_session.query(SecurityLog).filter(SecurityLog.action == kc.AUDIT_SENT).all()


# ── 서식 글 · 변수 ──────────────────────────────────────────────────────
def test_template_draft_has_four_variables_and_no_team_or_crew_words():
    import re

    assert set(re.findall(r"#\{[^}]+\}", kc.ALIMTALK_TEMPLATE_CONSTRUCTION)) == {
        "#{고객명}", "#{시공일}", "#{시간대}", "#{주문처}"}
    for word in ("팀", "인원", "명이", "300", "폭"):
        assert word not in kc.ALIMTALK_TEMPLATE_CONSTRUCTION, word
    sd = {"parties": {"customer": {"name": "가짜손님"}, "orderer": {"name": "가짜 주문처"}},
          "schedule": {"construction": {"date": "2030-11-20", "time": "오후", "team": "가짜 시공팀",
                                        "workers": 3, "crew": ["가짜 기사"]}}}
    variables = kc.build_construction_variables(sd)
    assert variables == {"#{고객명}": "가짜손님", "#{시공일}": "11월 20일", "#{시간대}": "오후", "#{주문처}": "가짜 주문처"}
    text = kc.render_construction_preview(sd)
    assert "#{" not in text and "11월 20일" in text and "가짜 시공팀" not in text and "가짜 기사" not in text
    empty = kc.build_construction_variables({})
    assert empty["#{시간대}"] == kakao.UNDECIDED_FALLBACK and empty["#{주문처}"] == kakao.DEFAULT_ORDERER


# ── 나가는 조건 ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("missing, code", [
    ("FOMS_GRAFT_CONSTRUCTION_ALIMTALK_ENABLED", "disabled"),
    ("SOLAPI_API_KEY", "not_configured"),
    ("SOLAPI_TEMPLATE_CONSTRUCTION_ID_HAUD", "brand_profile_missing"),
])
def test_any_missing_gate_never_calls_the_sender(quiet, monkeypatch, missing, code):
    _ready(monkeypatch)
    monkeypatch.delenv(missing)
    order = _order(construction=_day(3))
    assert kc.is_construction_ready("HAUD") is False and kc.readiness_code("HAUD") == code
    assert _send(order) == {"sent": False, "error": code}
    assert quiet == [] and kc.HISTORY_KEY not in _fresh(order.id).structured_data and _audits() == []


def test_all_three_send_once_with_history_and_audit(quiet, monkeypatch):
    _ready(monkeypatch)
    order = _order(construction=_day(3), time="오후")
    assert kc.is_construction_ready("HAUD") and kc.block_reason(order) is None
    assert _send(order, key=f"alimtalk:construction:{order.id}:{_day(3)}:action:9") == {"sent": True, "error": None}
    (call,) = quiet
    assert (call["to"], call["from_"], call["pf_id"], call["template_id"]) == ("01000000001", "0200000000", "PF-H",
                                                                               "TPL-C-H")
    assert set(call["variables"]) == {"#{고객명}", "#{시공일}", "#{시간대}", "#{주문처}"}
    record = _fresh(order.id).structured_data[kc.HISTORY_KEY]
    assert set(record) == {"sent_at", "message_id", "dedupe_key", "error", "sent_by", "sent_by_name",
                           "construction_date", "channel", "channel_checked_at"}
    assert (record["construction_date"], record["message_id"], record["error"]) == (_day(3), "MSG-1", None)
    assert record["dedupe_key"] == f"alimtalk:construction:{order.id}:{_day(3)}:action:9" and record["sent_at"]
    (log,) = _audits()
    assert log.detail == {"sent": True, "error": None, "template": "construction", "source": "erp_action:9"}
    assert log.target_id == order.id and CUSTOMER not in log.message and "0001" not in log.message


def test_same_date_twice_sends_once_and_a_new_date_sends_again(quiet, monkeypatch):
    _ready(monkeypatch)
    order = _order(construction=_day(3))
    assert _send(order)["sent"] and _send(order) == {"sent": True, "error": None}
    assert len(quiet) == 1 and len(_audits()) == 1
    moved = _fresh(order.id)
    moved.structured_data = {**moved.structured_data, "schedule": {"construction": {"date": _day(5), "time": ""}}}
    db_session.commit()
    assert _send(moved)["sent"] and len(quiet) == 2
    assert _fresh(order.id).structured_data[kc.HISTORY_KEY]["construction_date"] == _day(5)


@pytest.mark.parametrize("kind, code", [("partner", "partner_order"), ("deleted", "order_not_found"),
                                        ("draft", "not_eligible"), ("no_phone", "no_valid_phone"),
                                        ("no_date", "no_construction_date")])
def test_orders_we_never_send_to(quiet, monkeypatch, kind, code):
    _ready(monkeypatch)
    order = _order(construction=None if kind == "no_date" else _day(3), partner=kind == "partner",
                   phone=None if kind == "no_phone" else PHONE, status="DRAFT" if kind == "draft" else "PRODUCTION")
    if kind == "deleted":
        order.status = "DELETED"
        db_session.commit()
    assert kc.block_reason(order) == code and code in kc.GATE_CODES
    assert _send(order) == {"sent": False, "error": code}
    assert quiet == [] and kc.HISTORY_KEY not in (_fresh(order.id).structured_data or {}) and _audits() == []


def test_vendor_failure_is_recorded_with_its_code(quiet, monkeypatch):
    _ready(monkeypatch)

    def _boom(**kwargs):
        raise TimeoutError("합성 시간 초과")

    monkeypatch.setattr(kakao, "_solapi_send", _boom)
    order = _order(construction=_day(3))
    assert _send(order) == {"sent": False, "error": "network"}
    record = _fresh(order.id).structured_data[kc.HISTORY_KEY]
    assert (record["sent_at"], record["message_id"], record["error"]) == (None, None, "network")
    assert not kc.sent_for(_fresh(order.id).structured_data, _day(3))
    (log,) = _audits()
    assert log.detail["sent"] is False and log.detail["error"] == "network"


# ── 승인 창 줄(notify_customer) · 할 일 함수 ─────────────────────────────
def test_notify_rows_and_steps_only_when_usable(quiet, monkeypatch):
    order = _order(construction=None)
    params = parse_params("schedule_construction", {"date": _day(4), "time": "오전"})
    assert params["notify_customer"] is True
    off_rows, off_steps = preview.preview("schedule_construction", order, params), preview.steps(
        "schedule_construction", order, params)
    assert [row["field"] for row in off_rows] == ["시공 날짜"] and cn.STEP not in off_steps  # 스위치 끔 — 지금과 같다
    assert cn.param_shown("schedule_construction", "notify_customer", order) is False
    _ready(monkeypatch)
    rows = preview.preview("schedule_construction", order, params)
    assert rows[1:] == [{"field": cn.FIELD, "before": "보낸 적 없음", "after": "1건 보냄"}]
    assert preview.steps("schedule_construction", order, params)[-1] == cn.STEP == "손님 알림톡 1건 — 시공일 안내"
    assert cn.param_shown("schedule_construction", "notify_customer", order) is True
    no = {**params, "notify_customer": False}
    assert len(preview.preview("schedule_construction", order, no)) == 1
    assert cn.STEP not in preview.steps("schedule_construction", order, no)
    lines = preview.steps("schedule_construction", order, params) + [str(r) for r in rows]
    assert not any(word in line for line in lines for word in ("시공 팀", "시공팀", "인원", "300"))  # D211


def test_send_action_check_preview_verify_and_ran(quiet, monkeypatch):
    order = _order(construction=_day(2))
    assert preview.check("send_construction_alimtalk", order, {}) == "시공일 안내 알림톡이 아직 꺼져 있어요."
    _ready(monkeypatch)
    assert preview.check("send_construction_alimtalk", order, {}) is None
    assert preview.preview("send_construction_alimtalk", order, {}) == [
        {"field": cn.FIELD, "before": "보낸 적 없음", "after": "1건 보냄"}]
    assert not preview.verify("send_construction_alimtalk", order, {})
    key = cn.action_key(order.id, _day(2), 77)
    assert key == f"alimtalk:construction:{order.id}:{_day(2)}:action:77"
    _send(order, key=key)
    sent = _fresh(order.id)
    assert preview.check("send_construction_alimtalk", sent, {}) == "이 시공일 안내는 이미 보냈어요."
    assert preview.verify("send_construction_alimtalk", sent, {})
    assert preview.ran("send_construction_alimtalk", sent, {}, 77) and not preview.ran(
        "send_construction_alimtalk", sent, {}, 78)
    past = _order(construction=_day(-1))
    assert preview.check("send_construction_alimtalk", past, {}) == "시공일이 지났어요."


# ── 실행기 ───────────────────────────────────────────────────────────────
def _req(order: Order, action: str, params: dict, actor: User) -> RunRequest:
    return RunRequest(proposal_id=41, action=action, order_id=order.id, params=params, actor=actor, now=now_utc_naive())


def test_schedule_with_notify_sends_once_after_the_date_is_committed(quiet, monkeypatch):
    _ready(monkeypatch)
    admin, order = _admin(), _order(construction=None)
    seen_dates: list = []

    def _fake_send(**kwargs):
        reader = kakao.open_session()  # 다른 세션 — 커밋된 값만 보인다
        try:
            saved = reader.get(Order, order.id).structured_data["schedule"]["construction"]["date"]
        finally:
            reader.close()
        seen_dates.append(saved)
        quiet.append(kwargs)
        return "MSG-S"

    monkeypatch.setattr(kakao, "_solapi_send", _fake_send)
    params = parse_params("schedule_construction", {"date": _day(6), "time": "오후"})
    out = SERVICE_RUNNERS["schedule_construction"](db_session, _req(order, "schedule_construction", params, admin))
    assert out.status == "executed" and out.result["customer_notice"] == {"sent": True, "error": None}
    assert seen_dates == [_day(6)] and len(quiet) == 1  # 시공일 커밋 뒤 한 통
    assert out.message == "시공일을 정했어요. 손님 알림톡도 보냈어요."
    record = _fresh(order.id).structured_data[kc.HISTORY_KEY]
    assert record["dedupe_key"] == f"alimtalk:construction:{order.id}:{_day(6)}:action:41"
    assert record["sent_by"] == admin.id and _audits()[0].detail["source"] == "erp_action:41"


@pytest.mark.parametrize("switch_on", [True, False])
def test_notify_off_or_switch_off_is_the_same_as_now(quiet, monkeypatch, switch_on):
    if switch_on:
        _ready(monkeypatch)
    admin, order = _admin(), _order(construction=_day(3))
    params = parse_params("move_construction", {"date": _day(8), "notify_customer": not switch_on})
    out = SERVICE_RUNNERS["move_construction"](db_session, _req(order, "move_construction", params, admin))
    assert out.status == "executed" and "customer_notice" not in out.result and out.message == "시공일을 옮겼어요."
    assert quiet == [] and _audits() == [] and kc.HISTORY_KEY not in _fresh(order.id).structured_data
    assert set(out.result) == {"change_set", "change_count", "before_date", "date", "time", "reason_required",
                               "reason_attached"}  # 지금 결과 칸 그대로


def test_send_failure_keeps_the_new_date(quiet, monkeypatch):
    _ready(monkeypatch)
    admin = _admin()

    def _refused(**kwargs):
        raise RuntimeError("template variable mismatch")

    monkeypatch.setattr(kakao, "_solapi_send", _refused)
    order = _order(construction=_day(3))
    params = parse_params("move_construction", {"date": _day(9)})
    out = SERVICE_RUNNERS["move_construction"](db_session, _req(order, "move_construction", params, admin))
    assert out.status == "executed" and out.result["customer_notice"] == {"sent": False, "error": "template_mismatch"}
    assert out.message == "시공일을 옮겼어요. 손님 알림톡은 못 보냈어요."
    assert _fresh(order.id).structured_data["schedule"]["construction"]["date"] == _day(9)


def test_unexpected_send_error_is_one_code_and_the_date_stays(quiet, monkeypatch):
    _ready(monkeypatch)
    admin, order = _admin(), _order(construction=None)

    def _crash(*args, **kwargs):
        raise RuntimeError("합성 오류")

    monkeypatch.setattr(kc, "send_construction_alimtalk", _crash)
    params = parse_params("schedule_construction", {"date": _day(5)})
    out = SERVICE_RUNNERS["schedule_construction"](db_session, _req(order, "schedule_construction", params, admin))
    assert out.status == "executed" and out.result["customer_notice"] == {"sent": False, "error": "ACTION_FAILED"}
    assert _fresh(order.id).structured_data["schedule"]["construction"]["date"] == _day(5)


def test_send_construction_alimtalk_runner(quiet, monkeypatch):
    admin, order = _admin(), _order(construction=_day(2))
    blocked = SERVICE_RUNNERS["send_construction_alimtalk"](db_session, _req(order, "send_construction_alimtalk", {}, admin))
    assert blocked.status == "blocked" and quiet == []  # 스위치 끔 — 보내지 않는다
    _ready(monkeypatch)
    out = SERVICE_RUNNERS["send_construction_alimtalk"](db_session, _req(order, "send_construction_alimtalk", {}, admin))
    assert out.status == "executed" and out.result == {"sent": True} and len(quiet) == 1
    record = _fresh(order.id).structured_data[kc.HISTORY_KEY]
    assert record["dedupe_key"] == f"alimtalk:construction:{order.id}:{_day(2)}:action:41"
    again = SERVICE_RUNNERS["send_construction_alimtalk"](db_session, _req(order, "send_construction_alimtalk", {}, admin))
    assert again.status == "blocked" and "이미 보냈어요" in again.message and len(quiet) == 1


def test_send_construction_alimtalk_runner_vendor_failure_is_failed(quiet, monkeypatch):
    _ready(monkeypatch)
    monkeypatch.setattr(kakao, "_solapi_send", lambda **kw: (_ for _ in ()).throw(ConnectionError("합성")))
    admin, order = _admin(), _order(construction=_day(2))
    out = SERVICE_RUNNERS["send_construction_alimtalk"](db_session, _req(order, "send_construction_alimtalk", {}, admin))
    assert out.status == "failed" and out.result == {"sent": False, "error": "network"}


# ── 검수 R1 고침(R-12 · R-02) ────────────────────────────────────────────
def test_sent_check_runs_under_the_order_row_lock(quiet, monkeypatch):
    """R-12 — 겹친 두 보내기(할 일 · ``notify_customer``)가 같은 시공일로 두 통을 내지 않게, '이미 보냄' 판정보다 주문 줄
    ``FOR UPDATE`` 잠금이 먼저다(뒤에 온 쪽은 앞쪽 이력이 커밋된 뒤 판정한다). 진짜 겹침은 PostgreSQL 잠금이 줄 세운다."""
    from sqlalchemy.orm import Query

    _ready(monkeypatch)
    order = _order(construction=_day(3))
    events: list[str] = []
    real_lock, real_sent = Query.with_for_update, kc.sent_for

    def lock(self, *args, **kwargs):
        events.append("lock:" + ",".join(str(d.get("name")) for d in self.column_descriptions))
        return real_lock(self, *args, **kwargs)

    monkeypatch.setattr(Query, "with_for_update", lock)
    monkeypatch.setattr(kc, "sent_for", lambda sd, day: events.append("judge") or real_sent(sd, day))
    monkeypatch.setattr(kakao, "_solapi_send", lambda **kw: events.append("send") or "MSG-L")
    assert _send(order) == {"sent": True, "error": None}
    assert events == ["lock:Order", "judge", "send"]  # 잠금 → 판정 → 보내기(이력은 같은 잠금 아래)
    events.clear()
    assert _send(order) == {"sent": True, "error": None}  # 두 번째는 잠근 최신 이력으로 '이미 나감'
    assert events == ["lock:Order", "judge"] and len(_audits()) == 1


def test_a_send_committed_after_the_callers_check_is_not_sent_again(quiet, monkeypatch):
    """R-12 — 부르는 쪽이 '아직 안 나감'을 본 뒤 다른 승인이 먼저 보내고 커밋했으면, 잠근 다시 읽기가 그 이력을 보고 안 보낸다."""
    _ready(monkeypatch)
    admin, order = _admin(), _order(construction=_day(3))
    real = kc.send_construction_alimtalk

    def other_wins_first(order_id, **kwargs):
        real(order_id, manual_by=None, dedupe_key="alimtalk:construction:other", source="erp_action:7")
        return real(order_id, **kwargs)

    monkeypatch.setattr(kc, "send_construction_alimtalk", other_wins_first)
    out = SERVICE_RUNNERS["send_construction_alimtalk"](db_session, _req(order, "send_construction_alimtalk", {}, admin))
    assert out.status == "executed" and len(quiet) == 1 and len(_audits()) == 1


def test_hidden_notice_line_only_when_the_construction_notice_goes_out(quiet, monkeypatch):
    """R-02 — 빠른 승인 자리에 보일 손님 알림톡 줄: 시공일 할 일 + 쓸 수 있는 상태 + 넣을 값 참일 때만. 알림톡 보내기 할 일은
    카드 칸이 곧 알림톡이라 빈 글 · 스위치 끔이면 빈 글(지금과 같다)."""
    from foms.persistence.graft.models import ErpActionProposal
    from foms.services.erp_actions.views import hidden_notice, quick_view

    order = _order(construction=None, status="RECEIVED")
    params = parse_params("schedule_construction", {"date": _day(6), "time": "오전"})

    def row(action: str, values: dict) -> ErpActionProposal:
        return ErpActionProposal(action=action, params=values, preview=preview.preview(action, order, values))

    assert hidden_notice(row("schedule_construction", params), order) == ""  # 스위치 끔
    assert quick_view(row("schedule_construction", params), order) == {"needs_input": False, "notice": ""}
    _ready(monkeypatch)
    assert hidden_notice(row("schedule_construction", params), order) == cn.STEP
    assert quick_view(row("schedule_construction", params), order)["notice"] == cn.STEP
    assert hidden_notice(row("schedule_construction", {**params, "notify_customer": False}), order) == ""
    dated = _order(construction=_day(2), status="RECEIVED")
    send_row = ErpActionProposal(action="send_construction_alimtalk", params={},
                                 preview=preview.preview("send_construction_alimtalk", dated, {}))
    assert hidden_notice(send_row, dated) == ""  # 카드 칸 '손님 알림톡(시공일 안내)' 이 곧 그 줄
    assert quick_view(send_row, dated) == {"needs_input": False, "notice": ""}


def test_quick_view_needs_input_when_the_change_asks_for_a_reason(quiet, monkeypatch):
    """R-01 — 사유를 묻는 변경(고객 컨펌 뒤 시공일 옮기기)이면 빠른 승인 자리는 [고쳐서]만(``needs_input``)."""
    from foms.persistence.graft.models import ErpActionProposal
    from foms.services.erp_actions.views import quick_view

    confirmed, early = _order(construction=_day(3), status="CONFIRM"), _order(construction=_day(3), status="MEASURE")
    params = parse_params("move_construction", {"date": _day(9), "time": ""})
    for order, needs in ((confirmed, True), (early, False)):
        row = ErpActionProposal(action="move_construction", params=params,
                                preview=preview.preview("move_construction", order, params))
        assert quick_view(row, order)["needs_input"] is needs
