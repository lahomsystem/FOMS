"""조작 뒤 **자동 다시읽기** 계약 (T3 · 2026-08-31).

배경: 발주확인·발송처리·취소·반품접수는 ``triage_state`` 만 쓰고 ``raw_snapshot`` 은
손대지 않는다. 그래서 발송처리를 하고 이력으로 가면 화면의 네이버 축이 **발송 전 사실**을
계속 말한다 — 사람이 `다시 읽기` 를 손으로 눌러야 최신화됐다(사용자 지적 2026-08-31).

고정하는 계약:

1. 네 조작 **모두** 성공 뒤 그 집을 다시 읽게 큐에 넣는다(사용자 결정: "네 가지 모두").
2. **부분 실패**(HTTP 200 + failProductOrderInfos)에서도 넣는다 — 성공분은 네이버에서
   이미 바뀌었고, 실패 띠를 보고 온 사람이 옛 상태를 보면 안 된다.
3. **실패해도** 넣는다 — 불가역 경로에서 재조회는 낭비가 아니라 확인이다(HTTP 오류가
   나도 네이버엔 반영됐을 수 있다).
4. 다시읽기 enqueue 가 실패해도 **원래 조작을 깨지 않는다**. 조용히 삼키지 않고 로그로 남긴다.
"""

from __future__ import annotations

import pytest

from db import db_session
from foms.services.jobs import tasks as tasks_mod
from tests.services.integrations.test_naver_fulfillment import (  # noqa: F401
    _StubClient,
    _link,
)


class _Recorder:
    """``enqueue_naver_refresh`` 대역 — 호출 인자만 적는다."""

    def __init__(self, *, ok: bool = True, boom: bool = False) -> None:
        self.calls: list[tuple[int, object]] = []
        self.ok = ok
        self.boom = boom

    def __call__(self, link_id, actor_user_id=None):
        if self.boom:
            raise RuntimeError("큐가 죽었다")
        self.calls.append((int(link_id), actor_user_id))
        return self.ok


@pytest.fixture()
def recorder(monkeypatch):
    """태스크가 함수 안에서 import 하므로 **원본 모듈 속성**을 갈아 끼운다."""
    from foms.services.jobs import queue as queue_mod

    rec = _Recorder()
    monkeypatch.setattr(queue_mod, "enqueue_naver_refresh", rec)
    return rec


def _run(link_id: int, action: str, monkeypatch, client=None):
    from foms.services.integrations.naver_commerce import client as client_mod

    stub = client or _StubClient()
    monkeypatch.setattr(client_mod, "NaverCommerceClient", lambda: stub)
    kwargs = {}
    if action in ("cancel", "return"):
        kwargs["reason"] = "COLOR_AND_SIZE"
    return tasks_mod.run_naver_fulfillment_task(link_id, action, None, **kwargs), stub


# --------------------------------------------------------------------------- #
# 1. 네 조작 모두
# --------------------------------------------------------------------------- #

def test_confirm_success_enqueues_refresh(app, monkeypatch, recorder):
    """발주확인 뒤 그 집을 다시 읽는다."""
    link_id = _link("PO-RF-CONFIRM", order_no="N-RF-1", place="NOT_YET")
    _run(link_id, "confirm", monkeypatch)
    assert recorder.calls == [(link_id, None)]


def test_dispatch_success_enqueues_refresh(app, monkeypatch, recorder):
    """**발송처리** 뒤 다시 읽는다 — 사용자가 지목한 바로 그 자리다.

    이게 없으면 발송처리를 하고 이력으로 갔을 때 네이버 축이 발송 전 사실을 말한다.
    """
    link_id = _link("PO-RF-DISPATCH", order_no="N-RF-2", place="OK")
    _run(link_id, "dispatch", monkeypatch)
    assert recorder.calls == [(link_id, None)]


def test_return_reject_enqueues_refresh(app, monkeypatch, recorder):
    """**반품 거부**(T8-S3) 뒤에도 다시 읽는다 — 네 조작과 같은 규율이다.

    거부는 네이버 쪽 클레임 상태를 바꾼다. 다시 읽지 않으면 화면이 계속 `반품 요청`이라
    말하고, 담당자는 거부가 안 나갔다고 읽어 한 번 더 누른다.
    """
    from foms.services.integrations.naver_commerce import client as client_mod
    from foms.services.integrations.naver_commerce.mapping import group_key_text
    from models import ExternalOrderLink

    snapshot = {"order": {"orderId": "N-RF-REJ"},
                "productOrder": {"productOrderId": "PO-RF-REJ",
                                 "claimStatus": "RETURN_REQUEST", "claimType": "RETURN"}}
    link = ExternalOrderLink(channel="NAVER", external_id="PO-RF-REJ",
                             external_order_no="N-RF-REJ", sync_status="LINKED",
                             raw_snapshot=snapshot, group_key=group_key_text(snapshot))
    db_session.add(link)
    db_session.commit()
    link_id = int(link.id)

    class _RejectStub:
        def reject_return_product_order(self, product_order_id, *, reason):
            return {"data": {"successProductOrderIds": [product_order_id],
                             "failProductOrderInfos": []}}

    monkeypatch.setattr(client_mod, "NaverCommerceClient", lambda: _RejectStub())
    tasks_mod.run_naver_fulfillment_task(link_id, "return-reject", None,
                                         reason="반품이 어렵습니다.")

    assert recorder.calls == [(link_id, None)]


def test_every_mutating_action_is_registered(app):
    """조작 목록이 조용히 줄어들면 그 조작만 옛 사실을 말하게 된다.

    ``return-reject`` 는 T8-S3 에서 **의도적으로** 더했다 — 이 집합은 손으로 늘려야
    하는 자리이고, 그래서 새 조작을 만든 사람이 여기 와서 한 번 더 생각하게 된다.
    """
    assert set(tasks_mod.REFRESH_AFTER_ACTIONS) == {
        "confirm", "dispatch", "cancel", "return", "return-reject",
        "cancel-approve", "return-approve"}


# --------------------------------------------------------------------------- #
# 2~3. 실패 갈래
# --------------------------------------------------------------------------- #

def test_failure_also_enqueues_refresh(app, monkeypatch, recorder):
    """실패해도 다시 읽는다 — 불가역 경로에서 **재조회는 낭비가 아니라 확인**이다.

    두 가지가 이 갈래로 온다: 부분 실패(HTTP 200 + failProductOrderInfos)의 성공분은
    네이버에서 **이미 바뀌었고**, 통째 실패도 HTTP 오류가 응답 도중에 났다면 네이버에는
    반영됐을 수 있다. 둘 다 "지금 진짜 상태가 무엇인가"를 다시 읽어야 답이 나온다.
    실패 띠를 보고 온 사람에게 옛 사실을 보여주는 것이 제일 나쁘다.
    """
    link_id = _link("PO-RF-FAIL", order_no="N-RF-3", place="NOT_YET")
    with pytest.raises(Exception):
        _run(link_id, "confirm", monkeypatch, client=_StubClient(fail=True))
    assert recorder.calls == [(link_id, None)]


# --------------------------------------------------------------------------- #
# 4. 다시읽기 실패가 조작을 깨지 않는다
# --------------------------------------------------------------------------- #

def test_refresh_enqueue_failure_does_not_break_the_action(app, monkeypatch):
    """큐가 죽어도 조작 결과는 그대로다 — 다시 읽기는 편의이지 정합성 조건이 아니다."""
    from foms.services.jobs import queue as queue_mod

    monkeypatch.setattr(queue_mod, "enqueue_naver_refresh", _Recorder(boom=True))
    link_id = _link("PO-RF-BOOM", order_no="N-RF-4", place="NOT_YET")
    result, _stub = _run(link_id, "confirm", monkeypatch)
    assert result is not None


def test_unknown_action_is_not_refreshed(app, monkeypatch, recorder):
    """목록 밖 조작 이름으로는 큐에 넣지 않는다(오타·신규 조작 대비)."""
    assert tasks_mod._enqueue_refresh_after("detach", 1, None) is False
    assert recorder.calls == []
