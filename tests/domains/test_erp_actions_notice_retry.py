"""시공일 승인 뒤 손님 시공일 안내가 못 나갔을 때 — 다시 보내기 제안(점검 2차 w6-08 · 설계서 3.13 · D213).

완료 기준:
- 시공 잡기 · 방문 옮기기(시공) 승인에서 시공일은 쓰였고 같이 보낸 안내만 실패하면 '알림톡 보내기(시공일 안내)' 제안 하나가 열린다
  (운영 AI · 출처 ``proposal`` · 수준 1 · 기간은 시공일이 끝날 때까지). 승인한 사람에게는 '시공일은 잡았고 안내는 못 보냈어요 —
  다시 보내기 제안을 남겼어요'.
- 자동으로 다시 보내지 않는다(Solapi 는 승인 한 번에 한 번). 그 제안을 사람이 승인하면 한 번 나간다(O4 처음 수준 0 이어도 — 사람이
  이미 승인한 일의 뒷일).
- 같은 실패로 제안이 여러 개 쌓이지 않는다(같은 시공일이면 이미 열린 것을 알린다). 스위치가 꺼져 있거나 안내를 끄고 승인하면 아무것도
  안 한다(결과 · 말이 지금과 같다).
**진짜 Solapi 는 부르지 않는다** — 보내기 함수는 가짜(부른 수만 센다). 합성 주문 · 합성 글만.
"""

from __future__ import annotations

import datetime

import pytest

from db import db_session
from foms.persistence.graft.models import ErpActionProposal
from foms.services import kakao_alimtalk as kakao
from foms.services.datetime_kst import get_today_kst, now_utc_naive
from foms.services.erp_actions.lifecycle import approve, propose
from foms.services.erp_actions.runners import SERVICE_RUNNERS
from tests.domains.test_construction_alimtalk import _admin, _order, _ready, quiet  # noqa: F401 — quiet 은 바깥 가짜 fixture

NOW = now_utc_naive()
RETRY = "send_construction_alimtalk"
_KST = datetime.timedelta(hours=9)


def _day(offset: int) -> str:
    return (get_today_kst() + datetime.timedelta(days=offset)).isoformat()


@pytest.fixture
def refused(quiet, monkeypatch):
    """Solapi 가 서식 변수 틀림으로 거절한다(부른 수는 센다)."""
    tries: list[dict] = []

    def _refuse(**kwargs):
        tries.append(kwargs)
        raise RuntimeError("template variable mismatch")

    monkeypatch.setattr(kakao, "_solapi_send", _refuse)
    return tries


def _schedule(order, action="schedule_construction", **params):
    agent = "agent:schedule" if action == "schedule_construction" else "agent:cs"  # 그 할 일을 제안하는 AI 직원
    row = propose(db_session, action=action, proposed_by=agent, order=order,
                  params={"date": _day(6), "time": "오후", **params}, reason="합성 이유", evidence=[],
                  source_kind="sweep", source_ref="1", level=2, now=NOW)
    db_session.commit()
    return row


def _approve(row, admin, **kw):
    return approve(db_session, row.id, actor=admin, runners=SERVICE_RUNNERS, base_version=row.base_version, now=NOW, **kw)


def _retries() -> list[ErpActionProposal]:
    db_session.expire_all()
    return db_session.query(ErpActionProposal).filter(ErpActionProposal.action == RETRY).all()


def test_a_failed_notice_leaves_one_resend_proposal_and_says_so(refused, monkeypatch):
    _ready(monkeypatch)
    admin, order = _admin(), _order(construction=None)
    row = _schedule(order)
    done = _approve(row, admin)
    assert done["status"] == "executed" and done["message"] == "시공일은 잡았고 안내는 못 보냈어요 — 다시 보내기 제안을 남겼어요."
    (retry,) = _retries()
    assert done["result"]["notice_retry"] == retry.id and done["result"]["customer_notice"]["sent"] is False
    assert (retry.proposed_by, retry.source_kind, retry.source_ref, retry.level, retry.status, retry.params) == (
        "agent:ops", "proposal", str(row.id), 1, "open", {})
    end = datetime.datetime.combine(datetime.date.fromisoformat(_day(6)) + datetime.timedelta(days=1), datetime.time())
    assert retry.expires_at == end - _KST  # 시공일이 끝나면 기간도 끝난다
    assert len(refused) == 1  # 자동으로 다시 보내지 않는다
    db_session.expire_all()
    assert db_session.get(ErpActionProposal, row.id).result["notice_retry"] == retry.id


def test_a_person_approves_the_resend_and_it_goes_once(refused, monkeypatch, quiet):
    _ready(monkeypatch)
    admin, order = _admin(), _order(construction=None)
    _approve(_schedule(order), admin)
    (retry,) = _retries()
    monkeypatch.setattr(kakao, "_solapi_send", lambda **kw: (quiet.append(kw), "MSG-R")[1])
    again = _approve(retry, admin)  # 운영 AI 의 시공일 안내 처음 수준은 0 — 그래도 사람이 남긴 뒷일이라 승인된다
    assert again["status"] == "executed" and again["message"] == "시공일 안내 알림톡을 보냈어요."
    assert len(quiet) == 1 and len(refused) == 1


def test_the_same_failure_never_piles_up(refused, monkeypatch):
    _ready(monkeypatch)
    admin, order = _admin(), _order(construction=None)
    first = _approve(_schedule(order), admin)
    db_session.expire_all()
    moved = _schedule(db_session.get(type(order), order.id), action="move_construction", time="오전")  # 같은 날 · 다른 시간대
    second = _approve(moved, admin, reason_code="customer_request")  # 사유를 물을 변경(검수 R-01)
    assert second["message"] == "시공일은 옮겼고 안내는 못 보냈어요 — 다시 보내기 제안을 남겼어요."
    assert [r.id for r in _retries()] == [first["result"]["notice_retry"]] == [second["result"]["notice_retry"]]
    assert len(refused) == 2  # 승인 두 번 — 한 번씩만


@pytest.mark.parametrize("case", ["switch_off", "notice_off"])
def test_nothing_happens_when_the_notice_is_off(refused, monkeypatch, case):
    if case == "notice_off":
        _ready(monkeypatch)
    admin, order = _admin(), _order(construction=None)
    row = _schedule(order, notify_customer=case != "notice_off")
    done = _approve(row, admin)
    assert done["status"] == "executed" and done["message"] == "시공일을 정했어요."
    assert "notice_retry" not in done["result"] and "customer_notice" not in done["result"]
    assert _retries() == [] and refused == []  # 보내 보지도 않는다
