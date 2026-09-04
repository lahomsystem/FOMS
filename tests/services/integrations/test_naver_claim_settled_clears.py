"""클레임 승인이 성공하면 **같은 축의** 실패 기록을 내린다 (2026-09-04 사용자 2차 신고).

운영 실화면: 담당자가 취소 승인을 눌러 환불까지 끝났는데도 빨간 띠가 그대로 남았다.
실측(운영 링크 2122~2126): `fulfillment.last_error = "주문상태 확인 필요(취소 불가능
주문상태)"`(10:05) 뒤에 `cancel.approved_at`(10:12) 이 찍히고 클레임이 `CANCEL_DONE` 이
됐는데, 승인 성공 경로가 `last_error` 를 손대지 않아 통지가 사실보다 오래 살아남았다.

여기서 못박는 것:

* 승인 성공은 **그 상품주문의** ``cancel``·``cancel-approve`` 축 실패만 내린다.
* 축 밖(발주확인·반품)은 **안 건드린다** — 반품 축 ``last_error`` 는 "이 본품은 환불되지
  않았다"는 유일한 DB 흔적이다(황민철 집 ERP 5026). 집 전체·전 축을 지우던 옛 동작은
  RC5 에서 이미 되돌려졌다.
* 증거는 지우지 않고 **내린다**(``last_error_cleared`` + ``failure_cleared_reason``) —
  사람이 ``확인함`` 으로 닫는 자리와 같은 모양이라, 나중에 "무엇을 무엇이 닫았나"를 DB 가
  답할 수 있다.
* 반품 승인은 반품 축만 내린다(축 표가 갈라 놓는다).
"""

from __future__ import annotations

import pytest

from db import db_session
from foms.services.integrations.naver_commerce import fulfillment
from models import ExternalOrderLink

from tests.services.integrations.test_naver_claim_approve import (  # noqa: F401
    _CancelClient,
    _ReturnClient,
    _link,
    _uid,
    workbench_on,
)


def _failed_state(action: str, reason: str = "주문상태 확인 필요(취소 불가능 주문상태)") -> dict:
    """그 축으로 실패한 링크의 ``triage_state``."""
    return {"fulfillment": {"last_error": reason,
                            "last_error_at": "2026-09-04T01:05:17.881734",
                            "last_error_action": action}}


def _state(link_id: int) -> dict:
    db_session.expire_all()
    row = db_session.get(ExternalOrderLink, int(link_id))
    return (row.triage_state or {}).get("fulfillment") or {}


# --------------------------------------------------------------------------- #
# 양성 — 승인이 같은 축 실패를 내린다
# --------------------------------------------------------------------------- #

def test_cancel_approval_clears_the_cancel_failure(app, workbench_on):
    """운영 재현: 취소 실패가 있는 집에 취소 승인이 성공하면 띠가 닫힌다."""
    link = _link(state=_failed_state("cancel"))

    out = fulfillment.approve_cancel(db_session, _CancelClient(), link_id=int(link.id),
                                     actor_user_id=38)
    db_session.commit()

    state = _state(link.id)
    assert state.get("last_error", "") == ""
    # 증거는 내려서 남는다 — 무엇을 왜 닫았는지 DB 가 답해야 한다.
    assert "주문상태 확인 필요" in state.get("last_error_cleared", "")
    assert state.get("last_error_cleared_action") == "cancel"
    assert state.get("failure_cleared_reason") == "cancel-approved"
    assert state.get("failure_cleared_by") is None, "사람이 닫은 게 아니다"
    assert int(link.id) in out["cleared_link_ids"]


def test_cancel_approval_also_clears_its_own_axis_failure(app, workbench_on):
    """앞선 승인 시도 실패(`cancel-approve`)도 승인이 성공하면 함께 내린다."""
    link = _link(state=_failed_state("cancel-approve", "승인 실패: 일시 오류"))

    fulfillment.approve_cancel(db_session, _CancelClient(), link_id=int(link.id),
                               actor_user_id=38)
    db_session.commit()

    assert _state(link.id).get("last_error", "") == ""
    assert _state(link.id).get("last_error_cleared_action") == "cancel-approve"


# --------------------------------------------------------------------------- #
# 음성 대조군 — 전부 "승인이 성공한 집" 안에서 고른다
# --------------------------------------------------------------------------- #

def test_confirm_failure_survives_a_cancel_approval(app, workbench_on):
    """발주확인 실패는 취소가 확정돼도 **여전히 사실**이다 — 안 지운다."""
    link = _link(state=_failed_state("confirm", "발주확인 실패: 일시 오류"))

    fulfillment.approve_cancel(db_session, _CancelClient(), link_id=int(link.id),
                               actor_user_id=38)
    db_session.commit()

    state = _state(link.id)
    assert "발주확인 실패" in state.get("last_error", "")
    assert state.get("last_error_action") == "confirm"


def test_return_failure_survives_a_cancel_approval(app, workbench_on):
    """반품 접수 실패는 '이 본품은 환불되지 않았다'는 유일한 흔적이다 — 안 지운다."""
    link = _link(state=_failed_state("return", "반품 접수 실패: 400"))

    fulfillment.approve_cancel(db_session, _CancelClient(), link_id=int(link.id),
                               actor_user_id=38)
    db_session.commit()

    assert "반품 접수 실패" in _state(link.id).get("last_error", "")


def test_a_failed_approval_does_not_clear_anything(app, workbench_on):
    """승인이 실패하면 옛 실패도 그대로다 — 성공만 닫을 자격이 있다."""
    link = _link(state=_failed_state("cancel"))
    client = _CancelClient(fail_row="네이버 거절")

    with pytest.raises(fulfillment.FulfillmentError):
        fulfillment.approve_cancel(db_session, client, link_id=int(link.id),
                                   actor_user_id=38)
    db_session.commit()

    state = _state(link.id)
    assert state.get("last_error"), "실패한 승인이 통지를 지우면 할 일이 사라진다"
    assert state.get("last_error_action") == "cancel-approve"


def test_only_the_approved_sibling_is_cleared(app, workbench_on):
    """승인 대상이 아닌 형제의 실패는 그대로다 — 집이 아니라 상품주문 단위다."""
    order_no = f"N-CLR-{_uid()}"
    approved = _link(order_no=order_no, state=_failed_state("cancel"))
    # 클레임이 없는 형제 — 승인 대상 밖이다(같은 집).
    other = _link(order_no=order_no, claim="", state=_failed_state("cancel"))

    fulfillment.approve_cancel(db_session, _CancelClient(), link_id=int(approved.id),
                               actor_user_id=38)
    db_session.commit()

    assert _state(approved.id).get("last_error", "") == ""
    assert _state(other.id).get("last_error"), "승인 안 된 형제까지 닫으면 할 일이 사라진다"


def test_return_approval_does_not_clear_a_cancel_failure(app, workbench_on):
    """반품 승인은 취소 축을 안 닫는다 — 축 표가 갈라 놓는다."""
    link = _link(claim="RETURN_REQUEST", state=_failed_state("cancel"))

    fulfillment.approve_return(db_session, _ReturnClient(), link_id=int(link.id),
                               actor_user_id=38)
    db_session.commit()

    assert "주문상태 확인 필요" in _state(link.id).get("last_error", "")


def test_the_axis_table_is_the_single_source(app):
    """축 표가 코드 안에 하나뿐이다 — 두 벌이 되면 한쪽만 고쳐진다."""
    assert fulfillment.CLAIM_SETTLED_CLEARS == {
        "cancel-approve": ("cancel", "cancel-approve"),
        "return-approve": ("return", "return-approve"),
    }
    # 반품 **거부**는 없다: 거부는 클레임을 끝내지만 우리 접수 실패를 무효로 만들지 않는다.
    assert "return-reject" not in fulfillment.CLAIM_SETTLED_CLEARS
