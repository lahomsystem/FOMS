"""고객이 먼저 취소를 요청하면 우리 취소는 **실패가 아니다** (2026-09-04 운영 신고).

운영 실화면: 담당자가 취소처리를 눌렀는데 빨간 띠가 떴다 —
`박상우 2026090486868221 취소 주문상태 확인 필요(취소 불가능 주문상태)`.
실측: **고객의 취소 요청이 우리 클릭보다 32.6초 먼저** 접수돼 있었다. 네이버는 이미 취소
클레임이 열린 상품주문에 판매자 취소를 부르면 거절한다 — 주문은 우리가 원한 방향으로 가
있었고, 남은 일은 **승인 한 번**이었으며 그 버튼은 같은 화면에 이미 열려 있었다.

여기서 못박는 것:

* 실패를 적기 **전에** 한 번 다시 물어, 그 사이 고객 취소 클레임이 열린 건은 빨간 실패가
  아니라 **취소 축 안내**(`cancel.superseded_*`)로 적는다.
* **모르면 실패로 남긴다** — 재조회가 실패하면 전건 그대로 빨강이다(불가역 규율과 같은 방향).
* 취소 축이 아닌 클레임(반품 요청 등)은 재분류 대상이 아니다 — 취소가 안 된 건 여전히 사실이다.
* 성공 도장(`canceled_at`)은 찍지 않는다. 우리가 취소한 게 아니라 승인이 남아 있다.
* 실패가 하나도 없으면 재조회를 **부르지 않는다**(읽기 1회는 실패 경로 전용).
"""

from __future__ import annotations

import pytest

from db import db_session
from foms.services.integrations.naver_commerce.fulfillment import (
    FulfillmentError,
    cancel_order,
)
from models import ExternalOrderLink

from tests.services.integrations.test_naver_cancel import (  # noqa: F401
    _StubClient,
    _link,
    _state,
    workbench_on,
)


class _ClaimAwareClient(_StubClient):
    """재조회(`get_product_orders`)까지 흉내내는 스텁."""

    def __init__(self, *, fail_ids=None, fresh=None, blow_up: bool = False) -> None:
        super().__init__(fail_ids=fail_ids)
        self.fresh = dict(fresh or {})
        self.blow_up = blow_up
        self.lookup_calls: list[list[str]] = []

    def get_product_orders(self, pids):
        self.lookup_calls.append(list(pids))
        if self.blow_up:
            raise RuntimeError("네이버 조회 실패")
        return [{"productOrder": {"productOrderId": pid,
                                  "claimStatus": self.fresh.get(pid, "")}}
                for pid in pids]


def _cancel_axis(link_id: int) -> dict:
    db_session.expire_all()
    link = db_session.get(ExternalOrderLink, link_id)
    return (link.triage_state or {}).get("cancel") or {}


def _run(link_id: int, client) -> None:
    """취소를 부른다. 부분 실패는 예외로 오므로 삼켜서 상태만 본다."""
    try:
        cancel_order(db_session, client, link_id=link_id, reason="PRODUCT_UNSATISFIED",
                     detail="테스트", actor_user_id=1)
    except FulfillmentError:
        pass
    db_session.commit()


# --------------------------------------------------------------------------- #
# 양성 — 밀린 건은 빨강이 아니다
# --------------------------------------------------------------------------- #

def test_buyer_cancel_request_is_not_a_failure(app, workbench_on):
    """재조회가 `CANCEL_REQUEST` 라고 답하면 실패 기록을 남기지 않는다(운영 신고 재현)."""
    pid = "PO-SUP-1"
    link_id = _link(pid, order_no="N-SUP-1")
    client = _ClaimAwareClient(fail_ids={pid}, fresh={pid: "CANCEL_REQUEST"})

    _run(link_id, client)

    state = _state(link_id)
    assert state.get("last_error", "") == "", "빨간 실패 띠가 뜨면 화면이 거짓을 말한다"
    axis = _cancel_axis(link_id)
    assert axis.get("superseded_status") == "CANCEL_REQUEST"
    assert axis.get("superseded_at")
    # 네이버가 준 문장은 버리지 않는다 — 사람이 원문을 볼 수 있어야 한다.
    assert "상태 확인 필요" in str(axis.get("superseded_note", ""))
    # 우리가 고른 사유가 반영되지 않았다는 사실도 남긴다(귀책·제재가 사유에 걸린다).
    assert axis.get("superseded_our_reason") == "PRODUCT_UNSATISFIED"
    # 우리가 취소한 게 아니다 — 성공 도장을 찍으면 승인이 남은 걸 화면이 잊는다.
    assert not state.get("canceled_at")


def test_already_done_cancel_is_also_not_a_failure(app, workbench_on):
    """이미 취소 완료된 건도 실패가 아니다 — 할 일이 남지 않았다."""
    pid = "PO-SUP-2"
    link_id = _link(pid, order_no="N-SUP-2")
    client = _ClaimAwareClient(fail_ids={pid}, fresh={pid: "CANCEL_DONE"})

    _run(link_id, client)

    assert _state(link_id).get("last_error", "") == ""
    assert _cancel_axis(link_id).get("superseded_status") == "CANCEL_DONE"


# --------------------------------------------------------------------------- #
# 음성 대조군 — 전부 "실패를 들고 재분류 직전에 도달한 집" 안에서 고른다
# --------------------------------------------------------------------------- #

def test_plain_failure_stays_red(app, workbench_on):
    """클레임이 없는데 실패한 건은 그대로 빨강이다 — 원문도 보존."""
    pid = "PO-SUP-3"
    link_id = _link(pid, order_no="N-SUP-3")
    client = _ClaimAwareClient(fail_ids={pid}, fresh={pid: ""})

    _run(link_id, client)

    state = _state(link_id)
    assert "상태 확인 필요" in state.get("last_error", "")
    assert state.get("last_error_action") == "cancel"
    assert not _cancel_axis(link_id).get("superseded_at")


def test_lookup_failure_keeps_everything_red(app, workbench_on):
    """재조회가 죽으면 **모르는 것**이다 — 전건 그대로 실패로 남긴다."""
    pid = "PO-SUP-4"
    link_id = _link(pid, order_no="N-SUP-4")
    client = _ClaimAwareClient(fail_ids={pid}, blow_up=True)

    _run(link_id, client)

    assert "상태 확인 필요" in _state(link_id).get("last_error", "")
    assert not _cancel_axis(link_id).get("superseded_at")


def test_return_claim_is_not_a_cancel_supersede(app, workbench_on):
    """반품 요청은 취소 축이 아니다 — 취소가 안 된 건 여전히 사실이다."""
    pid = "PO-SUP-5"
    link_id = _link(pid, order_no="N-SUP-5")
    client = _ClaimAwareClient(fail_ids={pid}, fresh={pid: "RETURN_REQUEST"})

    _run(link_id, client)

    assert "상태 확인 필요" in _state(link_id).get("last_error", "")
    assert not _cancel_axis(link_id).get("superseded_at")


def test_siblings_are_judged_one_by_one(app, workbench_on):
    """한 집에서 밀린 건과 진짜 실패가 섞이면 **형제끼리 안 물든다**."""
    pid_a, pid_b = "PO-SUP-6A", "PO-SUP-6B"
    link_a = _link(pid_a, order_no="N-SUP-6")
    link_b = _link(pid_b, order_no="N-SUP-6")
    client = _ClaimAwareClient(fail_ids={pid_a, pid_b},
                               fresh={pid_a: "CANCEL_REQUEST", pid_b: ""})

    _run(link_a, client)

    assert _state(link_a).get("last_error", "") == ""
    assert _cancel_axis(link_a).get("superseded_status") == "CANCEL_REQUEST"
    assert "상태 확인 필요" in _state(link_b).get("last_error", "")
    assert not _cancel_axis(link_b).get("superseded_at")


def test_no_failure_means_no_extra_lookup(app, workbench_on):
    """다 성공하면 재조회를 **안 부른다** — 읽기 1회는 실패 경로 전용이다."""
    pid = "PO-SUP-7"
    link_id = _link(pid, order_no="N-SUP-7")
    client = _ClaimAwareClient()

    _run(link_id, client)

    assert client.lookup_calls == []
    assert _state(link_id).get("canceled_at"), "정상 취소는 그대로 성공해야 한다"
