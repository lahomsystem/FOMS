"""채널톡 작은 창 할 일 제안 줄 — 기간이 지난 제안 · 이어진 FOMS 계정 없는 상담원(점검 2차 w5-02 · w6-12 · w5-08).

완료 기준:
- 기간이 지난 줄 제안(밤 정리 전이라 아직 ``open``)은 ``cs.draft.get`` 에 줄이 뜨지 않는다(승인 대기 수 · 칩과 같은 조건).
- 줄이 뜬 뒤 기간이 지나면 답 보내기는 그대로 나가고 결과 한 줄은 '할 일 제안은 기간이 지나 넣지 않았어요' — 주문은 안 바뀐다.
- 이어진 FOMS 계정이 없는 상담원이 창을 열면 줄에 '이어진 FOMS 계정이 없어 같이 넣을 수 없어요'(``blocked``)가 붙는다 — 이어진
  상담원에게는 없다(대조군). 작은 창 스크립트는 그 글을 보이고 [같이 넣기] · [빼기]를 고르지 못하게 한다(제안 번호를 싣지 않는다).
채널톡 · 보내기 · 알림은 가짜(네트워크 0), 합성 글만.
"""

from __future__ import annotations

import datetime
from pathlib import Path

from db import db_session
from foms.persistence.graft.models import ErpActionProposal
from foms.services.cs_agent import send_view, wam_functions
from foms.services.cs_agent.channel_read import naive_utc
from tests.domains.test_cs_drafting import channel  # noqa: F401 — channel 은 fixture
from tests.domains.test_cs_send import FakeSender, posted, ready  # noqa: F401 — ready 는 fixture
from tests.domains.test_cs_wam_graft import (  # noqa: F401 — 바깥 env 끄기 · 알림 가짜 fixture 도 같이
    fresh, graft, graft_env_off, lines_of, order, proposal, quiet_notifications, send, staff,
)
from tests.domains.test_cs_wam_send import NOW, call
from tests.support.cs_agent_fakes import keys  # noqa: F401 — keys 는 fixture

SCRIPT = Path(__file__).resolve().parents[2] / "static" / "js" / "cs-agent" / "wam-graft.js"


def _expire(proposal_id: int, minutes: int = 1) -> None:
    """작은 창 함수 시각(:data:`NOW`)보다 앞에 기간이 끝난 것으로 — 밤 정리 전이라 상태는 ``open`` 그대로."""
    row = db_session.get(ErpActionProposal, proposal_id)
    row.expires_at = naive_utc(NOW) - datetime.timedelta(minutes=minutes)
    db_session.commit()


def _get(app, ready, turn_id, manager="mgr-7"):
    return call(app, ready, "cs.draft.get", {"turn": turn_id, "chat": "uc-1"}, manager=manager)["result"]


def test_an_expired_line_does_not_show(app, ready):
    graft()
    staff()
    turn_id = posted(ready)
    pid = proposal(turn_id, order())
    assert _get(app, ready, turn_id)["action"]["id"] == pid  # 대조군 — 기간이 남은 줄은 뜬다
    _expire(pid)
    assert _get(app, ready, turn_id)["action"] is None
    assert send_view.inline_proposal(db_session, turn_id, now=naive_utc(NOW)) is None
    assert send_view.inline_proposal(db_session, turn_id).id == pid  # 기간을 보지 않는 판정(넣을 때 까닭 가르기)
    assert fresh(pid).status == "open"  # 읽기는 상태를 바꾸지 않는다(밤 정리 · 되맞추기 몫)


def test_a_line_that_expires_after_it_showed_keeps_the_reply_and_says_why(app, ready):
    graft()
    person = staff()
    turn_id = posted(ready)
    target = order()
    pid = proposal(turn_id, target)
    assert _get(app, ready, turn_id)["action"]["id"] == pid
    _expire(pid)  # 창이 뜬 뒤 기간이 끝났다
    result = send(app, ready, turn_id, FakeSender(ready), with_action=pid)
    assert result["code"] == "sent" and result["ok"] is True  # 답은 그대로 나간다
    assert result["action"] == {"code": "expired", "ok": False, "message": "할 일 제안은 기간이 지나 넣지 않았어요."}
    assert fresh(pid).status == "open" and fresh(pid).decided_by is None and lines_of(target) == []
    assert person is not None


def test_the_approve_step_itself_names_the_expiry_too(app, ready, monkeypatch):
    """확인과 승인 사이에 기간이 끝나도(승인 첫 걸음이 막음) 같은 한 줄 — '이미 처리된 제안이에요'가 아니다."""
    graft()
    staff()
    turn_id = posted(ready)
    target = order()
    pid = proposal(turn_id, target)
    real = send_view.inline_proposal
    monkeypatch.setattr(wam_functions, "inline_proposal", lambda session, turn, now=None: real(session, turn))
    _expire(pid)  # 줄 고르기는 기간을 못 본 채 지나간다(그 사이 끝남 흉내) — 승인 첫 걸음이 진짜 시각으로 막는다
    result = send(app, ready, turn_id, FakeSender(ready), with_action=pid)
    assert result["code"] == "sent" and result["action"]["code"] == "expired"
    assert lines_of(target) == []


def test_an_unlinked_agent_sees_the_line_blocked_when_the_window_opens(app, ready):
    graft()
    staff()  # mgr-7 은 이어져 있다(대조군)
    turn_id = posted(ready)
    pid = proposal(turn_id, order())
    linked = _get(app, ready, turn_id)["action"]
    assert linked["id"] == pid and "blocked" not in linked
    unlinked = _get(app, ready, turn_id, manager="mgr-unlinked")["action"]
    assert unlinked == {**linked, "blocked": "이어진 FOMS 계정이 없어 같이 넣을 수 없어요."}
    assert fresh(pid).status == "open"


def test_the_small_window_script_locks_the_choice_for_a_blocked_line():
    """작은 창 스크립트 — 막힘 글을 힌트 자리에 보이고 두 단추를 끄며, 보낼 값에 제안 번호를 싣지 않는다(구조 확인)."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "action.blocked" in text and "button.disabled = Boolean(blocked)" in text
    assert "state.id = null; // 같이 넣을 사람이 없다" in text and "if (!state.id) return {};" in text
    assert len(text.splitlines()) < 300  # 새 JS 300줄 래칫
