# -*- coding: utf-8 -*-
"""NVCLAIM-PARTIAL-01 — 부분 취소·반품 계약 테스트의 공용 픽스처·헬퍼.

테스트 네 파일(``test_naver_partial_claim`` = 서비스 계약,
``test_naver_partial_claim_dispatch`` = 부분 취소 뒤 발송·벌크 pre-check,
``test_naver_partial_claim_routes`` = 큐·워커·라우트·미리보기·감사,
``test_naver_partial_claim_ui`` = 화면 pane·목록 줄·JS·핀)이 이 한 벌을 쓴다.
한 파일에 다 두면 500줄 파일 상한(``tests/harness/test_file_size_ratchet``)에 걸리는데,
헬퍼를 복사해 나누면 네 파일의 픽스처가 조용히 갈린다 — 그러면 같은 기준 집 #2354 를
파일마다 다르게 재현한다.

``test_`` 로 시작하지 않으므로 pytest 가 수집하지 않는다.
"""
from __future__ import annotations

import pathlib
from typing import Any, Optional

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.integrations.naver_commerce.constants import ADDON_PRODUCT_CLASS
from models import ExternalOrderLink, User

MAIN_PRODUCT_CLASS = "조합형옵션상품"
TRIAGE_PATH = "/admin/naver-ingest/triage"
PANE_PATH = "/admin/naver-ingest/triage/pane"
JS_PATH = pathlib.Path("static/js/admin/naver-workbench.js")
WORKBENCH_TEMPLATE = pathlib.Path("templates/admin/naver_workbench.html")

_SEQ = [0]


def _uid() -> str:
    """테스트 안에서 겹치지 않는 짧은 번호."""
    _SEQ[0] += 1
    return str(_SEQ[0])


# --------------------------------------------------------------------------- #
# 픽스처·헬퍼
# --------------------------------------------------------------------------- #

@pytest.fixture()
def workbench_on(monkeypatch):
    """취소·반품은 워크벤치 전용 기능이다 — 게이트가 켜져야 라우트가 열린다."""
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_ENABLED", "1")
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_COHORT", "all")
    yield


@pytest.fixture()
def partial_on(monkeypatch):
    """부분 선택 게이트(계약 §0, C8) — 끄면 옛 모달·옛 본문 그대로다."""
    monkeypatch.setenv("FOMS_NAVER_PARTIAL_CLAIM_ENABLED", "1")
    monkeypatch.setenv("FOMS_NAVER_PARTIAL_CLAIM_COHORT", "all")
    yield


def _partial_off(monkeypatch) -> None:
    """부분 선택 게이트를 확실히 끈다(환경에 남은 값에 속지 않게)."""
    monkeypatch.delenv("FOMS_NAVER_PARTIAL_CLAIM_ENABLED", raising=False)
    monkeypatch.delenv("FOMS_NAVER_PARTIAL_CLAIM_COHORT", raising=False)


def _login(client, *, role: str = "ADMIN") -> User:
    """세션에 사용자를 심는다(test_naver_workbench_v3_contract 와 같은 모양)."""
    user = User(username=f"wbpc_{role.lower()}_{_uid()}", password=generate_password_hash("pw"),
                role=role, team="CS", name=f"{role} 사용자", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


class _StubClient:
    """네이버 호출을 **기록만** 하는 스텁(test_naver_cancel.py 의 확장).

    ``calls`` 에 ``{"action", "pid", "kwargs"}`` 를 순서대로 남긴다. ``kwargs`` 를 그대로
    적는 이유는 결정 7 — 호출자가 ``quantity`` 를 넘기지 않는다는 계약을 단언하기 위해서다.
    ``fail_ids`` 에 든 상품주문은 커머스API 모양(HTTP 200 + failProductOrderInfos)으로 실패한다.
    """

    def __init__(self, *, fail_ids: set[str] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.confirm_calls: list[list[str]] = []
        self.dispatch_calls: list[list[dict]] = []
        self.fail_ids = set(fail_ids or ())

    def _answer(self, pid: str) -> dict:
        if pid in self.fail_ids:
            return {"data": {"failProductOrderInfos": [
                {"productOrderId": pid, "code": "9999", "message": "상품 주문 상태 확인 필요"}]}}
        return {"data": {"successProductOrderIds": [pid]}}

    def request_cancel_product_order(self, product_order_id, *, reason, detail=None, **kwargs):
        pid = str(product_order_id)
        self.calls.append({"action": "cancel", "pid": pid,
                           "kwargs": {"reason": reason, "detail": detail, **kwargs}})
        return self._answer(pid)

    def request_return_product_order(self, product_order_id, *, reason, collect_method,
                                     detail=None, **kwargs):
        pid = str(product_order_id)
        self.calls.append({"action": "return", "pid": pid,
                           "kwargs": {"reason": reason, "collect_method": collect_method,
                                      "detail": detail, **kwargs}})
        return self._answer(pid)

    def confirm_place_orders(self, ids):
        self.confirm_calls.append([str(i) for i in ids])
        return {"data": {"successProductOrderIds": [str(i) for i in ids]}}

    def dispatch_product_orders(self, rows):
        self.dispatch_calls.append(list(rows))
        return {"data": {"successProductOrderIds": [str(r["productOrderId"]) for r in rows]}}


def _pids(client: _StubClient, action: str | None = None) -> list[str]:
    """스텁이 기록한 호출의 상품주문번호를 순서대로."""
    return [c["pid"] for c in client.calls if action is None or c["action"] == action]


def _link(external_id: str, *, order_no: str, addon: bool, dispatched: bool = False,
          returned: bool = False, claim: str = "", claim_type: str = "",
          canceled: bool = False, cancel_scope: str = "", place: Optional[str] = "OK",
          amount: int = 0) -> int:
    """상품주문 1건(test_naver_addon_claim_order._link 의 확장).

    ``canceled`` 면 우리 취소 표식을 남기고, ``cancel_scope`` 가 있으면 함께 적는다(빈 값 =
    옛 표식 — 계약 §5 는 이를 household 로 읽는다). ``addon`` 이 ``productClass`` 를 가른다.
    """
    from foms.services.integrations.naver_commerce.mapping import group_key_text

    product_order: dict[str, Any] = {
        "productOrderId": external_id, "productName": f"제품 {external_id}",
        "productClass": ADDON_PRODUCT_CLASS if addon else MAIN_PRODUCT_CLASS,
        "totalPaymentAmount": amount, "placeOrderStatus": place,
        "shippingAddress": {"name": "이수취", "tel1": "010-3333-4444",
                            "baseAddress": "서울 강남구 1", "detailedAddress": "101호"},
    }
    if claim:
        product_order["claimStatus"] = claim
    if claim_type:
        product_order["claimType"] = claim_type
    snapshot = {"order": {"orderId": order_no, "ordererName": "김주문"},
                "productOrder": product_order}
    state: dict[str, Any] = {}
    if dispatched:
        state["fulfillment"] = {"dispatched_at": "2026-09-10T00:00:00"}
    if canceled:
        state["fulfillment"] = {"canceled_at": "2026-09-11T00:00:00",
                                **({"cancel_scope": cancel_scope} if cancel_scope else {})}
    if returned:
        state["return"] = {"requested_at": "2026-09-10T01:00:00"}
    link = ExternalOrderLink(
        channel="NAVER", external_id=external_id, external_order_no=order_no,
        sync_status="LINKED", place_order_status=place,
        raw_snapshot=snapshot, group_key=group_key_text(snapshot),
        triage_state=state or None,
    )
    db_session.add(link)
    db_session.commit()
    return int(link.id)


def _state(link_id: int) -> dict:
    """링크의 fulfillment 표식(없으면 빈 dict)."""
    db_session.expire_all()
    link = db_session.get(ExternalOrderLink, link_id)
    return (link.triage_state or {}).get("fulfillment") or {}


def _links(link_id: int) -> list[ExternalOrderLink]:
    """같은 집의 링크 전부(서비스와 같은 판정)."""
    from foms.services.integrations.naver_commerce.fulfillment import links_of_group

    db_session.expire_all()
    return links_of_group(db_session, link_id)


def _household_2354(order_no: str, *, dispatched: bool = False) -> dict[str, int]:
    """기준 집 #2354 의 모양(브리프 §2-1) — 외부 id → link id.

    본품 M + 추가구성 A1·A2·A3(PAYED, 0원) + 추가구성 C1~C4(판매자센터에서 이미 CANCEL_DONE).
    삽입 순서도 운영과 같게(M, A1, C1~C4, A2, A3) 둔다 — 순서 단언이 우연에 기대지 않게.
    """
    ids: dict[str, int] = {}
    ids["M"] = _link(f"{order_no}-M", order_no=order_no, addon=False, dispatched=dispatched,
                     amount=1233700)
    ids["A1"] = _link(f"{order_no}-A1", order_no=order_no, addon=True, dispatched=dispatched)
    for name, amount in (("C1", 50000), ("C2", 50000), ("C3", 100000), ("C4", 50000)):
        ids[name] = _link(f"{order_no}-{name}", order_no=order_no, addon=True, amount=amount,
                          claim="CANCEL_DONE", claim_type="CANCEL")
    ids["A2"] = _link(f"{order_no}-A2", order_no=order_no, addon=True, dispatched=dispatched)
    ids["A3"] = _link(f"{order_no}-A3", order_no=order_no, addon=True, dispatched=dispatched)
    return ids


def _ext(order_no: str, name: str) -> str:
    """``_household_2354`` 가 만든 외부 id."""
    return f"{order_no}-{name}"
