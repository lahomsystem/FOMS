"""반품 **승인** 계약 (T8-S2 · 2026-08-31).

배경: 접수만 있는 버튼은 사람 일을 안 줄인다. 접수 기능 실호출은 운영에서 **0회**인데,
같은 기간 사람은 판매자센터에서 **9건을 접수+승인 한 번에** 처리했다(22~60초). 그래서
접수 모달에 `승인까지 한 번에` 를 두고 한 번에 끝낸다(사용자 결정 2026-08-31).

**승인은 환불 확정이고 되돌리는 엔드포인트가 없다.** 그래서 고정하는 계약:

1. 체크를 안 켜면 **승인을 아예 부르지 않는다**(기본 꺼짐).
2. **접수에 성공한 건만** 승인한다 — 실패한 건은 네이버에 반품 요청 자체가 없다.
3. 승인 전에 상세를 **다시 읽고**, 보류가 걸려 있으면 **승인하지 않는다**. 보류 해제는
   FOMS 가 하지 않는다(반품안심케어 건은 해제 자체가 금지).
4. 승인 가능 상태가 아니면 승인하지 않는다 — **기다리지 않고** 사유를 남긴다.
5. 승인 실패·건너뜀은 `approve_skipped_reason` 으로 남아 화면이 "승인 남음"을 말한다.
6. 승인 body 는 **없다**(공식 문서). 클라이언트가 body 를 만들어 보내면 안 된다.
"""

from __future__ import annotations

import pytest

from db import db_session
from foms.services.integrations.naver_commerce import fulfillment as svc
from models import ExternalOrderLink
from tests.services.integrations.test_naver_return_send import _link  # noqa: F401


class _ApproveClient:
    """접수는 늘 성공. 승인 쪽 동작만 갈아 끼운다."""

    def __init__(self, *, detail_by_pid: dict | None = None,
                 approve_fail: dict | None = None,
                 approve_raises: Exception | None = None,
                 detail_raises: Exception | None = None):
        self.calls: list[str] = []
        self.approved: list[str] = []
        self._details = dict(detail_by_pid or {})
        self._approve_fail = dict(approve_fail or {})
        self._approve_raises = approve_raises
        self._detail_raises = detail_raises

    def request_return_product_order(self, product_order_id, *, reason,
                                     collect_method, detail=None, quantity=None):
        self.calls.append(product_order_id)
        return {"data": {"successProductOrderIds": [product_order_id],
                         "failProductOrderInfos": []}}

    def get_product_orders(self, ids):
        if self._detail_raises is not None:
            raise self._detail_raises
        out = []
        for pid in ids:
            block = dict(self._details.get(pid) or {"claimStatus": "RETURN_REQUEST"})
            out.append({"order": {"orderId": "N-APV"},
                        "productOrder": {"productOrderId": pid},
                        "return": block})
        return out

    def approve_return_product_order(self, product_order_id):
        self.approved.append(product_order_id)
        if self._approve_raises is not None:
            raise self._approve_raises
        if product_order_id in self._approve_fail:
            return {"data": {"successProductOrderIds": [],
                             "failProductOrderInfos": [
                                 {"productOrderId": product_order_id,
                                  "message": self._approve_fail[product_order_id]}]}}
        return {"data": {"successProductOrderIds": [product_order_id],
                         "failProductOrderInfos": []}}


def _return_state(link_id: int) -> dict:
    db_session.expire_all()
    link = db_session.get(ExternalOrderLink, link_id)
    return ((link.triage_state or {}).get("return") or {})


def _run(link_id: int, client, *, approve: bool):
    return svc.request_return(db_session, client, link_id=link_id,
                              reason="COLOR_AND_SIZE", actor_user_id=7, approve=approve)


def _run_expecting_unapproved(link_id: int, client):
    """승인이 하나도 안 나간 실행 — **예외가 오르는 것이 계약이다**(2026-09-02 개정).

    예전에는 접수만 성공하면 승인 0건이어도 조용히 성공으로 끝났다. 그 자리가
    "부분 실패는 실패다" 를 못 지킨 다섯 번째 지점이었고, 보류·상태 미도달처럼
    **환불이 안 나간 채 잊히는** 갈래가 정확히 여기로 빠졌다. 독립 경로
    ``approve_return`` 은 이미 예외를 올린다 — 두 경로의 완료 판정을 맞춘다.

    사유 기록은 예외와 **함께** 남아야 한다(워커가 이 예외에서 commit 한다).
    """
    with pytest.raises(svc.FulfillmentError) as err:
        _run(link_id, client, approve=True)
    assert "승인 안 됨" in str(err.value), str(err.value)
    return err.value


# --------------------------------------------------------------------------- #
# 1~2. 켠 사람만, 성공분만
# --------------------------------------------------------------------------- #

def test_without_flag_approve_is_never_called(app):
    """체크를 안 켜면 승인을 **아예 부르지 않는다** — 기본이 안전이다."""
    link_id = _link("PO-APV-OFF", dispatched=True)
    client = _ApproveClient()
    out = _run(link_id, client, approve=False)

    assert client.approved == []
    assert out["approved"] == []
    assert not _return_state(link_id).get("approved_at")


def test_flag_approves_and_marks_state(app):
    """켜면 접수 뒤 승인까지 나가고 표식이 남는다."""
    link_id = _link("PO-APV-ON", dispatched=True)
    client = _ApproveClient()
    out = _run(link_id, client, approve=True)

    assert client.approved == ["PO-APV-ON"]
    assert out["approved"] == ["PO-APV-ON"]
    state = _return_state(link_id)
    assert state.get("approved_at") and state.get("approved_by") == 7


# --------------------------------------------------------------------------- #
# 3. 보류 가드 — 이 기능의 핵심 안전장치
# --------------------------------------------------------------------------- #

def test_holdback_blocks_approval_and_we_do_not_release_it(app):
    """보류가 걸린 건은 **승인하지 않고 해제도 하지 않는다**.

    네이버는 보류가 걸린 건의 승인을 막는다. 그리고 반품안심케어 건은 **보류해제 자체가
    금지**다(공식). 해제가 반품비를 0원으로 초기화하는 갈래도 있다. 사람이 판매자센터에서
    판단할 일이라 FOMS 는 손대지 않는다.
    """
    link_id = _link("PO-APV-HOLD", dispatched=True)
    client = _ApproveClient(detail_by_pid={
        "PO-APV-HOLD": {"claimStatus": "RETURN_REQUEST",
                        "holdbackStatus": "HOLDBACK_REQUEST"}})
    _run_expecting_unapproved(link_id, client)

    assert client.approved == [], "보류 건에 승인을 불렀다"
    state = _return_state(link_id)
    assert "보류" in (state.get("approve_skipped_reason") or "")
    assert state.get("holdback_status") == "HOLDBACK_REQUEST"
    # 접수 자체는 성공했다 — 그 사실을 지우면 안 된다.
    assert state.get("requested_at")


def test_no_holdback_release_call_exists_anywhere(app):
    """보류 해제는 **코드에 존재조차 시키지 않는다**(회수방법 상수와 같은 규율).

    목록이나 함수가 있으면 언젠가 누가 부른다.
    """
    import inspect

    from foms.services.integrations.naver_commerce import client as client_mod

    source = inspect.getsource(client_mod) + inspect.getsource(svc)
    assert "holdback/release" not in source
    assert "claim/return/holdback" not in source


# --------------------------------------------------------------------------- #
# 4. 상태 가드 — 기다리지 않는다
# --------------------------------------------------------------------------- #

def test_status_not_approvable_is_skipped_without_waiting(app):
    """승인 가능 상태가 아니면 부르지 않고 사유를 남긴다 — sleep 루프를 돌지 않는다."""
    link_id = _link("PO-APV-EARLY", dispatched=True)
    client = _ApproveClient(detail_by_pid={
        "PO-APV-EARLY": {"claimStatus": "PAYED"}})
    _run_expecting_unapproved(link_id, client)

    assert client.approved == []
    assert "상태가 아닙니다" in (_return_state(link_id).get("approve_skipped_reason") or "")


def test_collect_done_is_approvable(app):
    """수거완료도 승인 대상이다 — 실물이 없는 우리 반품은 그 상태를 즉시 지나간다."""
    link_id = _link("PO-APV-COLLECT", dispatched=True)
    client = _ApproveClient(detail_by_pid={
        "PO-APV-COLLECT": {"claimStatus": "COLLECT_DONE"}})
    _run(link_id, client, approve=True)
    assert client.approved == ["PO-APV-COLLECT"]


# --------------------------------------------------------------------------- #
# 5. 실패 갈래는 사유를 남긴다
# --------------------------------------------------------------------------- #

def test_detail_read_failure_skips_approval_with_reason(app):
    """상태를 못 읽으면 승인하지 않는다 — 모르면 안 건다."""
    link_id = _link("PO-APV-NOREAD", dispatched=True)
    client = _ApproveClient(detail_raises=RuntimeError("HTTP 500"))
    _run_expecting_unapproved(link_id, client)

    assert client.approved == []
    assert "다시 읽지 못했습니다" in (_return_state(link_id).get("approve_skipped_reason") or "")


def test_approve_call_failure_leaves_reason(app):
    """승인 호출이 실패하면 사유가 남아 화면이 '승인 남음'을 말한다."""
    link_id = _link("PO-APV-FAIL", dispatched=True)
    client = _ApproveClient(approve_raises=RuntimeError("HTTP 400 상품 주문 상태 확인 필요"))
    _run_expecting_unapproved(link_id, client)

    assert "승인 실패" in (_return_state(link_id).get("approve_skipped_reason") or "")


def test_body_less_approve_contract(app):
    """승인은 **body 를 만들지 않는다** — 공식 문서에 Request Body 항목이 없다.

    2026-08-27 원장이 `approvalData` 를 넣어야 한다고 적었으나 그 출처에 그 문장이 없었다.
    없는 필드를 지어내 불가역 API 에 보내지 않는다.
    """
    import ast
    import inspect

    from foms.services.integrations.naver_commerce.client import NaverCommerceClient

    source = inspect.getsource(NaverCommerceClient.approve_return_product_order)
    tree = ast.parse(source.lstrip())
    func = tree.body[0]
    # docstring 은 왜 안 보내는지를 **설명**하느라 그 낱말을 쓴다 — 판정은 코드 본문으로.
    body = func.body[1:] if ast.get_docstring(func) else func.body
    code = "\n".join(ast.unparse(node) for node in body)
    assert "json_body" not in code, code
    assert "approvalData" not in code, code
    assert "claim/return/approve" in code
