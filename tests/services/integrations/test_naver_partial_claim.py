# -*- coding: utf-8 -*-
"""NVCLAIM-PARTIAL-01 — 취소·반품을 **상품주문 일부만 골라** 보내는 계약.

스펙 ``docs/specs/2026-09-11-naver-partial-claim_SPEC.md``, 계약 §0~§6(CEO 확정 2026-09-11).
기준 사례는 운영 #2354(브리프 §2-1): 본품 1 + 추가구성 7, 그중 4건은 판매자센터에서 이미
``CANCEL_DONE``. 사용자는 남은 라인 일부만 골라 취소·반품하고 싶다.

세 층을 한 파일에서 잠근다 — 서비스(``cancel_order``/``request_return``)·큐·워커·라우트·
미리보기(``claim-plan``)·화면(pane). **네이버 클레임은 불가역이다.** 어떤 테스트도 실제
``NaverCommerceClient`` 로 네트워크를 타지 않는다: 서비스는 :class:`_StubClient`, 라우트는
``enqueue_*`` monkeypatch, claim-plan 은 클라이언트 생성 자체를 raise 로 막아 0회를 증명한다.

``product_order_ids`` 의 뜻 3종(계약 §0)이 전 계층에서 같다:

* **None(키 부재)** = 집 전체(오늘 동작 그대로 — ★ 음성 대조군이 지킨다)
* **[]** = 거절(라우트 400, 서비스 ``FulfillmentError``, 네이버 0회)
* **[id…]** = 그 라인만 + 서버가 붙이는 자동 동반(본품을 고르면 남은 추가구성상품)

새 이름(``plan_claim_scope``·``cancel_sendable``·``CANCEL_SCOPE_*`` 등)은 **각 테스트 안에서
지역 import** 한다 — 구현이 아직 없어도 ``--collect-only`` 가 통과해야 워커 A·B·C 와 나란히
쓸 수 있다. ★ 표시 테스트는 구현 전에도 green 이어야 하는 음성 대조군이다.
"""
from __future__ import annotations

import copy
import pathlib
import re
from collections import Counter
from typing import Any, Optional

import pytest
from sqlalchemy.orm.attributes import flag_modified
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.integrations.naver_commerce.constants import ADDON_PRODUCT_CLASS
from models import ExternalOrderLink, SecurityLog, User
from tests.services.integrations._markup import has_attribute, is_disabled, open_tag

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


# --------------------------------------------------------------------------- #
# 서비스 — 취소 (계약 §1)
# --------------------------------------------------------------------------- #

def test_cancel_subset_calls_only_the_chosen_rows_in_claim_order(app):
    """고른 라인만 나간다 — 본품을 고르면 남은 추가구성상품이 **자동 동반**되고 순서는 추가구성 먼저.

    M+A1+A2 집에서 [M, A1] 을 고르면 A2 가 자동으로 붙어(결정 3) ``[A1, A2, M]`` 순으로
    나가고, 세 라인 모두 ``cancel_scope == "partial"`` 표식을 받는다(결정 5).
    """
    from foms.services.integrations.naver_commerce.fulfillment import (
        CANCEL_SCOPE_PARTIAL, cancel_order,
    )

    order_no = "N-PC-SUB"
    main = _link("PO-PC-SUB-M", order_no=order_no, addon=False)
    a1 = _link("PO-PC-SUB-A1", order_no=order_no, addon=True)
    a2 = _link("PO-PC-SUB-A2", order_no=order_no, addon=True)
    client = _StubClient()

    result = cancel_order(db_session, client, link_id=main, reason="INTENT_CHANGED",
                          product_order_ids=["PO-PC-SUB-M", "PO-PC-SUB-A1"])
    db_session.commit()

    assert _pids(client) == ["PO-PC-SUB-A1", "PO-PC-SUB-A2", "PO-PC-SUB-M"]
    assert result["auto_added"] == ["PO-PC-SUB-A2"]
    assert result["scope"] == "partial"
    for lid in (main, a1, a2):
        assert _state(lid)["canceled_at"]
        assert _state(lid)["cancel_scope"] == CANCEL_SCOPE_PARTIAL == "partial"


def test_cancel_without_the_key_covers_the_household(app):
    """★ 음성 대조군 — **키 부재**(``product_order_ids`` 를 안 넘김)는 오늘처럼 집 전체다.

    test_naver_cancel.py:83 과 같은 기대. 구현 전에도 통과해야 하고, 구현 뒤에도 그대로여야
    한다(옛 탭·옛 JS 의 하위호환 경로). ``scope`` 키 단언은 별도 테스트에 둔다.
    """
    from foms.services.integrations.naver_commerce.fulfillment import cancel_order

    order_no = "N-PC-HH"
    main = _link("PO-PC-HH-M", order_no=order_no, addon=False)
    _link("PO-PC-HH-A1", order_no=order_no, addon=True)
    client = _StubClient()

    result = cancel_order(db_session, client, link_id=main, reason="INTENT_CHANGED")
    db_session.commit()

    assert sorted(_pids(client)) == ["PO-PC-HH-A1", "PO-PC-HH-M"]
    assert sorted(result["canceled"]) == ["PO-PC-HH-A1", "PO-PC-HH-M"]


def test_household_cancel_marks_scope_household(app):
    """키 부재 취소의 성공 표식은 ``cancel_scope == "household"`` 다(계약 §5)."""
    from foms.services.integrations.naver_commerce.fulfillment import (
        CANCEL_SCOPE_HOUSEHOLD, cancel_order,
    )

    main = _link("PO-PC-HHS-M", order_no="N-PC-HHS", addon=False)
    a1 = _link("PO-PC-HHS-A1", order_no="N-PC-HHS", addon=True)

    result = cancel_order(db_session, _StubClient(), link_id=main, reason="INTENT_CHANGED")
    db_session.commit()

    assert result["scope"] == "household"
    for lid in (main, a1):
        assert _state(lid)["cancel_scope"] == CANCEL_SCOPE_HOUSEHOLD == "household"


def test_cancel_with_an_empty_list_is_refused_without_calls(app):
    """``[]`` 는 "전체" 가 아니라 **거절**이다(C2) — 호출 0회, 표식도 없다."""
    from foms.services.integrations.naver_commerce.fulfillment import (
        FulfillmentError, cancel_order,
    )

    main = _link("PO-PC-EMP-M", order_no="N-PC-EMP", addon=False)
    a1 = _link("PO-PC-EMP-A1", order_no="N-PC-EMP", addon=True)
    client = _StubClient()

    with pytest.raises(FulfillmentError) as err:
        cancel_order(db_session, client, link_id=main, reason="INTENT_CHANGED",
                     product_order_ids=[])
    db_session.commit()

    assert "대상 상품주문을 고르세요" in str(err.value)
    assert client.calls == []
    for lid in (main, a1):
        assert not _state(lid).get("last_error"), "빈 목록 거절이 라인에 실패를 남겼다"


def test_cancel_with_an_id_outside_the_household_is_refused(app):
    """집 밖 상품주문번호가 섞이면 한 건도 보내지 않고 그 id 를 말한다(C2)."""
    from foms.services.integrations.naver_commerce.fulfillment import (
        FulfillmentError, cancel_order,
    )

    main = _link("PO-PC-OUT-M", order_no="N-PC-OUT", addon=False)
    client = _StubClient()

    with pytest.raises(FulfillmentError) as err:
        cancel_order(db_session, client, link_id=main, reason="INTENT_CHANGED",
                     product_order_ids=["PO-NOPE"])

    assert "PO-NOPE" in str(err.value)
    assert client.calls == []


def test_main_only_selection_pulls_the_uncovered_addons_and_skips_covered_ones(app):
    """기준 사례 #2354 — 본품만 고르면 **남은** 추가구성 3건이 붙고, 이미 취소된 4건은 안 간다.

    ``addon_return_covered`` 가 CANCEL_DONE 형제를 충족으로 읽으므로 C1~C4 는 자동 동반
    대상이 아니고(보낼 수도 없다), A1~A3 만 붙어 ``[A1, A2, A3, M]`` 으로 나간다.
    """
    from foms.services.integrations.naver_commerce.fulfillment import cancel_order

    order_no = "N-PC-2354"
    ids = _household_2354(order_no)
    client = _StubClient()

    result = cancel_order(db_session, client, link_id=ids["M"], reason="INTENT_CHANGED",
                          product_order_ids=[_ext(order_no, "M")])
    db_session.commit()

    assert _pids(client) == [_ext(order_no, n) for n in ("A1", "A2", "A3", "M")]
    assert result["auto_added"] == [_ext(order_no, n) for n in ("A1", "A2", "A3")]
    for name in ("C1", "C2", "C3", "C4"):
        assert "canceled_at" not in _state(ids[name]), f"{name} 은 이미 취소된 건이다"


def test_cancel_scope_gap_sends_nothing_when_an_addon_cannot_go(app):
    """결정 4 — 취소 축에도 FAQ 3880 범위 규격. 함께 갈 추가구성상품이 못 가면 **0건 전송**.

    A1 은 이미 발송돼 취소를 보낼 수 없다(``cancel_sendable`` 거짓). 본품만 골라도 자동
    동반이 안 되니 gap 이고, 본품에 사유를 남기고 한 건도 보내지 않는다.
    """
    from foms.services.integrations.naver_commerce.fulfillment import (
        FulfillmentError, cancel_order,
    )

    order_no = "N-PC-GAP"
    main = _link("PO-PC-GAP-M", order_no=order_no, addon=False)
    _link("PO-PC-GAP-A1", order_no=order_no, addon=True, dispatched=True)
    client = _StubClient()

    with pytest.raises(FulfillmentError) as err:
        cancel_order(db_session, client, link_id=main, reason="INTENT_CHANGED",
                     product_order_ids=["PO-PC-GAP-M"])
    db_session.commit()

    assert "추가구성상품" in str(err.value)
    assert client.calls == [], "gap 인데 일부가 나갔다 — 2026-09-01 사고의 모양"
    assert _state(main)["last_error_action"] == "cancel"


def test_addon_only_cancel_is_not_blocked_by_the_scope_rule(app):
    """음성 대조군(test_naver_addon_claim_order.py:435 의 취소 축 거울) — 추가구성만 고르면 규격은 침묵한다."""
    from foms.services.integrations.naver_commerce.fulfillment import cancel_order

    order_no = "N-PC-ADDONLY"
    main = _link("PO-PC-AO-M", order_no=order_no, addon=False)
    _link("PO-PC-AO-A1", order_no=order_no, addon=True)
    client = _StubClient()

    result = cancel_order(db_session, client, link_id=main, reason="INTENT_CHANGED",
                          product_order_ids=["PO-PC-AO-A1"])
    db_session.commit()

    assert _pids(client) == ["PO-PC-AO-A1"]
    assert result["canceled"] == ["PO-PC-AO-A1"]
    assert "canceled_at" not in _state(main)


def test_addon_only_household_cancel_is_not_blocked_by_the_scope_rule(app):
    """★ 음성 대조군(키 부재 변형) — 추가구성상품만 있는 집의 집 전체 취소는 규격에 안 걸린다.

    구현 전에도 통과해야 한다: 취소 축에 범위 검사를 붙여도(결정 4) 대상에 본품이 없으면
    ``addon_return_gap`` 은 빈 목록이다.
    """
    from foms.services.integrations.naver_commerce.fulfillment import cancel_order

    a1 = _link("PO-PC-AOH-A1", order_no="N-PC-AOH", addon=True)
    client = _StubClient()

    result = cancel_order(db_session, client, link_id=a1, reason="INTENT_CHANGED")
    db_session.commit()

    assert _pids(client) == ["PO-PC-AOH-A1"]
    assert result["canceled"] == ["PO-PC-AOH-A1"]


def test_same_subset_twice_calls_naver_once(app):
    """C5 멱등 — 같은 부분집합을 두 번 보내면 두 번째는 조용히 빈다(예외 없음, 호출 0회)."""
    from foms.services.integrations.naver_commerce.fulfillment import cancel_order

    order_no = "N-PC-IDEM"
    main = _link("PO-PC-IDEM-M", order_no=order_no, addon=False)
    _link("PO-PC-IDEM-A1", order_no=order_no, addon=True)
    client = _StubClient()

    first = cancel_order(db_session, client, link_id=main, reason="INTENT_CHANGED",
                         product_order_ids=["PO-PC-IDEM-A1"])
    db_session.commit()
    second = cancel_order(db_session, client, link_id=main, reason="INTENT_CHANGED",
                          product_order_ids=["PO-PC-IDEM-A1"])
    db_session.commit()

    assert first["canceled"] == ["PO-PC-IDEM-A1"]
    assert second["canceled"] == []
    assert len(client.calls) == 1


def test_a_selected_row_that_is_not_sendable_sends_nothing(app):
    """C3/C4 — 고른 라인 중 보낼 수 없는 것이 있으면 조용히 빼지 않고 **0건 전송 + 그 라인 실패**.

    A1 에 고객 반품 요청이 걸려 있다. [A1, A2] 를 고르면 A2 만 보내는 것이 아니라 전부
    멈추고 A1 에만 사유를 남긴다 — 체크된 것과 나간 것이 다르면 재진술이 거짓이 된다.
    """
    from foms.services.integrations.naver_commerce.fulfillment import (
        FulfillmentError, cancel_order,
    )

    order_no = "N-PC-BLK"
    main = _link("PO-PC-BLK-M", order_no=order_no, addon=False)
    a1 = _link("PO-PC-BLK-A1", order_no=order_no, addon=True,
               claim="RETURN_REQUEST", claim_type="RETURN")
    a2 = _link("PO-PC-BLK-A2", order_no=order_no, addon=True)
    client = _StubClient()

    with pytest.raises(FulfillmentError):
        cancel_order(db_session, client, link_id=main, reason="INTENT_CHANGED",
                     product_order_ids=["PO-PC-BLK-A1", "PO-PC-BLK-A2"])
    db_session.commit()

    assert client.calls == []
    assert _state(a1)["last_error_action"] == "cancel"
    assert not _state(a2).get("last_error") and "canceled_at" not in _state(a2)


def test_cancel_never_passes_quantity(app):
    """결정 7 — 수량 일부 취소는 범위 밖. 집 전체·부분 어느 경로도 ``quantity`` 를 넘기지 않는다."""
    from foms.services.integrations.naver_commerce.fulfillment import cancel_order

    whole = _link("PO-PC-QW-M", order_no="N-PC-QW", addon=False)
    _link("PO-PC-QW-A1", order_no="N-PC-QW", addon=True)
    part = _link("PO-PC-QP-M", order_no="N-PC-QP", addon=False)
    _link("PO-PC-QP-A1", order_no="N-PC-QP", addon=True)
    client = _StubClient()

    cancel_order(db_session, client, link_id=whole, reason="INTENT_CHANGED")
    db_session.commit()
    cancel_order(db_session, client, link_id=part, reason="INTENT_CHANGED",
                 product_order_ids=["PO-PC-QP-A1"])
    db_session.commit()

    assert len(client.calls) == 3
    for call in client.calls:
        assert "quantity" not in call["kwargs"], call
        assert "cancelQuantity" not in call["kwargs"], call


def test_plan_restates_exactly_what_the_server_sends(app):
    """C1 — 미리보기(``plan_claim_scope``)의 ``todo`` 가 실제 호출 순서와 **한 글자도** 다르지 않다."""
    from foms.services.integrations.naver_commerce.fulfillment import (
        cancel_order, plan_claim_scope,
    )

    order_no = "N-PC-PLAN"
    ids = _household_2354(order_no)
    plan = plan_claim_scope(_links(ids["M"]), action="cancel",
                            product_order_ids=[_ext(order_no, "M")])
    assert plan["ok"] is True, plan["message"]

    client = _StubClient()
    cancel_order(db_session, client, link_id=ids["M"], reason="INTENT_CHANGED",
                 product_order_ids=[_ext(order_no, "M")])
    db_session.commit()

    assert plan["todo"] == _pids(client)
    assert plan["selected"] == [_ext(order_no, "M")]
    assert plan["auto_added"] == [_ext(order_no, n) for n in ("A1", "A2", "A3")]


# --------------------------------------------------------------------------- #
# 결정 5 — 부분 취소 뒤 남은 라인의 발주확인·발송
# --------------------------------------------------------------------------- #

def test_partial_cancel_leaves_the_rest_dispatchable(app):
    """부분 취소 표식(``cancel_scope="partial"``)은 집을 잠그지 않고 **그 라인만 대상에서 뺀다**.

    발송처리(M+A1 집, A1 취소 → M 만 발송)와 발주확인(M2+A4 집, A4 취소 → M2 만 발주확인)
    둘 다 — ``_cancel_guard`` 가 제외 목록을 돌려주는 계약 §1.
    """
    from foms.services.integrations.naver_commerce.fulfillment import (
        cancel_order, confirm_place_order, dispatch_order,
    )

    main = _link("PO-PC-D5-M", order_no="N-PC-D5", addon=False)
    _link("PO-PC-D5-A1", order_no="N-PC-D5", addon=True)
    main2 = _link("PO-PC-D5C-M", order_no="N-PC-D5C", addon=False, place="NOT_YET")
    _link("PO-PC-D5C-A4", order_no="N-PC-D5C", addon=True, place="NOT_YET")
    client = _StubClient()

    cancel_order(db_session, client, link_id=main, reason="INTENT_CHANGED",
                 product_order_ids=["PO-PC-D5-A1"])
    db_session.commit()
    dispatched = dispatch_order(db_session, client, link_id=main)
    db_session.commit()

    assert dispatched["dispatched"] == ["PO-PC-D5-M"]
    assert [str(r["productOrderId"]) for r in client.dispatch_calls[-1]] == ["PO-PC-D5-M"]

    cancel_order(db_session, client, link_id=main2, reason="INTENT_CHANGED",
                 product_order_ids=["PO-PC-D5C-A4"])
    db_session.commit()
    confirmed = confirm_place_order(db_session, client, link_id=main2)
    db_session.commit()

    assert confirmed["confirmed"] == ["PO-PC-D5C-M"]
    assert client.confirm_calls[-1] == ["PO-PC-D5C-M"]


def test_partial_cancel_survives_the_next_refresh(app):
    """다음 수집이 A1 스냅샷을 ``CANCEL_DONE`` 으로 바꿔도 남은 본품 발송은 열려 있다.

    집 단위 ``_claim_guard`` 가 partial 표식 라인을 판정에서 빼 주지 않으면, 우리가 낸
    부분 취소가 재수집 뒤 형제 클레임으로 읽혀 집 전체를 다시 잠근다(결정 5 의 두 번째 절반).
    """
    from foms.services.integrations.naver_commerce.fulfillment import (
        cancel_order, dispatch_order,
    )

    main = _link("PO-PC-RF-M", order_no="N-PC-RF", addon=False)
    a1 = _link("PO-PC-RF-A1", order_no="N-PC-RF", addon=True)
    client = _StubClient()
    cancel_order(db_session, client, link_id=main, reason="INTENT_CHANGED",
                 product_order_ids=["PO-PC-RF-A1"])
    db_session.commit()

    row = db_session.get(ExternalOrderLink, a1)
    snapshot = copy.deepcopy(row.raw_snapshot)
    snapshot["productOrder"]["claimStatus"] = "CANCEL_DONE"
    snapshot["productOrder"]["claimType"] = "CANCEL"
    row.raw_snapshot = snapshot
    flag_modified(row, "raw_snapshot")
    db_session.commit()

    dispatched = dispatch_order(db_session, client, link_id=main)
    db_session.commit()

    assert dispatched["dispatched"] == ["PO-PC-RF-M"]
    assert [str(r["productOrderId"]) for r in client.dispatch_calls[-1]] == ["PO-PC-RF-M"]


def test_household_cancel_still_blocks_dispatch(app):
    """★ 음성 대조군(test_naver_cancel.py:325 거울) — 집 전체 취소 뒤 발송처리는 여전히 거절.

    결정 5 는 partial 표식만 연다. household(또는 옛 키 없는) 표식은 오늘처럼 집을 잠근다.
    """
    from foms.services.integrations.naver_commerce.fulfillment import (
        FulfillmentError, cancel_order, dispatch_order,
    )

    main = _link("PO-PC-HB-M", order_no="N-PC-HB", addon=False)
    _link("PO-PC-HB-A1", order_no="N-PC-HB", addon=True)
    client = _StubClient()
    cancel_order(db_session, client, link_id=main, reason="INTENT_CHANGED")
    db_session.commit()

    with pytest.raises(FulfillmentError):
        dispatch_order(db_session, client, link_id=main)
    assert client.dispatch_calls == []


def test_a_failed_cancel_line_still_blocks_dispatch(app):
    """취소 **실패**가 남은 라인(``last_error_action == "cancel"``)이 있으면 집 전체 차단(결정 5 단서)."""
    from foms.services.integrations.naver_commerce.fulfillment import (
        FulfillmentError, cancel_order, dispatch_order,
    )

    main = _link("PO-PC-FL-M", order_no="N-PC-FL", addon=False)
    _link("PO-PC-FL-A1", order_no="N-PC-FL", addon=True)
    client = _StubClient(fail_ids={"PO-PC-FL-A1"})

    with pytest.raises(FulfillmentError):
        cancel_order(db_session, client, link_id=main, reason="INTENT_CHANGED",
                     product_order_ids=["PO-PC-FL-A1"])
    db_session.commit()

    with pytest.raises(FulfillmentError) as err:
        dispatch_order(db_session, client, link_id=main)
    assert "취소" in str(err.value)
    assert client.dispatch_calls == []


# --------------------------------------------------------------------------- #
# 서비스 — 반품 (계약 §1, 반품 축)
# --------------------------------------------------------------------------- #

def test_return_subset_calls_only_the_chosen_rows(app):
    """반품도 같은 규율 — 고른 추가구성 1건만 나가고 사유·회수방법이 그대로 실린다."""
    from foms.services.integrations.naver_commerce.fulfillment import (
        RETURN_COLLECT_METHOD, request_return,
    )

    order_no = "N-PC-RSUB"
    main = _link("PO-PC-RSUB-M", order_no=order_no, addon=False, dispatched=True)
    _link("PO-PC-RSUB-A1", order_no=order_no, addon=True, dispatched=True)
    _link("PO-PC-RSUB-A2", order_no=order_no, addon=True, dispatched=True)
    client = _StubClient()

    result = request_return(db_session, client, link_id=main, reason="COLOR_AND_SIZE",
                            product_order_ids=["PO-PC-RSUB-A1"])
    db_session.commit()

    assert _pids(client) == ["PO-PC-RSUB-A1"]
    assert client.calls[0]["kwargs"]["reason"] == "COLOR_AND_SIZE"
    assert client.calls[0]["kwargs"]["collect_method"] == RETURN_COLLECT_METHOD
    assert "quantity" not in client.calls[0]["kwargs"]
    assert result["returned"] == ["PO-PC-RSUB-A1"]
    assert result["scope"] == "partial"


def test_return_main_only_pulls_the_uncovered_addons(app):
    """본품만 고른 반품 — 남은 추가구성상품이 자동 동반돼 ``[A1, A2, M]`` 으로 나간다."""
    from foms.services.integrations.naver_commerce.fulfillment import request_return

    order_no = "N-PC-RMAIN"
    main = _link("PO-PC-RMAIN-M", order_no=order_no, addon=False, dispatched=True)
    _link("PO-PC-RMAIN-A1", order_no=order_no, addon=True, dispatched=True)
    _link("PO-PC-RMAIN-A2", order_no=order_no, addon=True, dispatched=True)
    client = _StubClient()

    result = request_return(db_session, client, link_id=main, reason="COLOR_AND_SIZE",
                            product_order_ids=["PO-PC-RMAIN-M"])
    db_session.commit()

    assert _pids(client) == ["PO-PC-RMAIN-A1", "PO-PC-RMAIN-A2", "PO-PC-RMAIN-M"]
    assert result["auto_added"] == ["PO-PC-RMAIN-A1", "PO-PC-RMAIN-A2"]


def test_return_with_an_empty_list_is_refused(app):
    """반품 ``[]`` 도 거절 — 호출 0회."""
    from foms.services.integrations.naver_commerce.fulfillment import (
        FulfillmentError, request_return,
    )

    main = _link("PO-PC-REMP-M", order_no="N-PC-REMP", addon=False, dispatched=True)
    client = _StubClient()

    with pytest.raises(FulfillmentError) as err:
        request_return(db_session, client, link_id=main, reason="COLOR_AND_SIZE",
                       product_order_ids=[])
    assert "대상 상품주문을 고르세요" in str(err.value)
    assert client.calls == []


def test_return_with_an_unknown_id_is_refused(app):
    """반품에 집 밖 id — 호출 0회, 그 id 를 말한다."""
    from foms.services.integrations.naver_commerce.fulfillment import (
        FulfillmentError, request_return,
    )

    main = _link("PO-PC-RUNK-M", order_no="N-PC-RUNK", addon=False, dispatched=True)
    client = _StubClient()

    with pytest.raises(FulfillmentError) as err:
        request_return(db_session, client, link_id=main, reason="COLOR_AND_SIZE",
                       product_order_ids=["PO-NOPE-R"])
    assert "PO-NOPE-R" in str(err.value)
    assert client.calls == []


def test_return_without_the_key_is_unchanged(app):
    """★ 음성 대조군 — 키 부재 반품은 오늘과 같다: 발송된 2건 전부, 추가구성 먼저."""
    from foms.services.integrations.naver_commerce.fulfillment import request_return

    order_no = "N-PC-RHH"
    main = _link("PO-PC-RHH-M", order_no=order_no, addon=False, dispatched=True)
    _link("PO-PC-RHH-A1", order_no=order_no, addon=True, dispatched=True)
    client = _StubClient()

    result = request_return(db_session, client, link_id=main, reason="COLOR_AND_SIZE")
    db_session.commit()

    assert _pids(client) == ["PO-PC-RHH-A1", "PO-PC-RHH-M"]
    assert sorted(result["returned"]) == ["PO-PC-RHH-A1", "PO-PC-RHH-M"]


# --------------------------------------------------------------------------- #
# 큐·워커 (계약 §2)
# --------------------------------------------------------------------------- #

class _FakeQueue:
    """``q.enqueue`` 인자를 기록하는 가짜 RQ 큐(test_naver_return_wiring.py 패턴)."""

    def __init__(self) -> None:
        self.seen: list[dict[str, Any]] = []

    def enqueue(self, path, *args, **kwargs):
        self.seen.append({"path": path, "args": args, "kwargs": kwargs})


def test_enqueue_cancel_passes_product_order_ids_only_when_given(monkeypatch):
    """목록을 주면 ``product_order_ids`` kwarg 로, None 이면 **kwarg 자체가 없다**(오늘 job 과 동일)."""
    from foms.services.jobs import queue as jobs_queue

    fake = _FakeQueue()
    monkeypatch.setattr(jobs_queue, "get_rq_queue", lambda: fake)

    assert jobs_queue.enqueue_naver_cancel(7, "INTENT_CHANGED", None, 42,
                                           product_order_ids=["PO-X", "PO-Y"]) is True
    assert jobs_queue.enqueue_naver_cancel(7, "INTENT_CHANGED", None, 42) is True

    with_ids, without = fake.seen
    assert with_ids["args"] == (7, "cancel", 42)
    assert with_ids["kwargs"]["product_order_ids"] == ["PO-X", "PO-Y"]
    assert "product_order_ids" not in without["kwargs"]
    assert without["kwargs"]["reason"] == "INTENT_CHANGED"


def test_enqueue_return_passes_product_order_ids_only_when_given(monkeypatch):
    """반품 큐도 같은 규칙 — None 이면 kwarg 부재."""
    from foms.services.jobs import queue as jobs_queue

    fake = _FakeQueue()
    monkeypatch.setattr(jobs_queue, "get_rq_queue", lambda: fake)

    assert jobs_queue.enqueue_naver_return(7, "COLOR_AND_SIZE", "색상", 42,
                                           product_order_ids=["PO-X"]) is True
    assert jobs_queue.enqueue_naver_return(7, "COLOR_AND_SIZE", "색상", 42) is True

    with_ids, without = fake.seen
    assert with_ids["args"] == (7, "return", 42)
    assert with_ids["kwargs"]["product_order_ids"] == ["PO-X"]
    assert with_ids["kwargs"]["approve"] is False
    assert "product_order_ids" not in without["kwargs"]


def test_worker_passes_product_order_ids_to_the_service(app, monkeypatch):
    """워커가 ``product_order_ids`` 를 서비스에 그대로 넘긴다(네이버 클라이언트는 스텁)."""
    from foms.services.jobs import tasks

    seen: dict[str, Any] = {}

    def _fake_cancel(session, client, *, link_id, reason, detail=None, actor_user_id=None,
                     product_order_ids=None):
        seen.update({"link_id": link_id, "reason": reason, "ids": product_order_ids})
        return {"canceled": ["X"], "skipped": [], "scope": "partial", "auto_added": []}

    monkeypatch.setattr(
        "foms.services.integrations.naver_commerce.fulfillment.cancel_order", _fake_cancel)
    monkeypatch.setattr(
        "foms.services.integrations.naver_commerce.client.NaverCommerceClient",
        lambda *a, **k: _StubClient())
    lid = _link("PO-PC-WK-M", order_no="N-PC-WK", addon=False)

    tasks.run_naver_fulfillment_task(lid, "cancel", 5, reason="INTENT_CHANGED",
                                     product_order_ids=["X"])

    assert seen == {"link_id": lid, "reason": "INTENT_CHANGED", "ids": ["X"]}


def test_worker_omits_the_kwarg_when_none(app, monkeypatch):
    """None 이면 워커는 kwarg 를 **안 넘긴다** — 옛 시그니처 가짜 서비스(test_naver_cancel.py:299 모양)가 TypeError 없이 받는다."""
    from foms.services.jobs import tasks

    seen: dict[str, Any] = {}

    def _old_shape_cancel(session, client, *, link_id, reason, detail=None, actor_user_id=None):
        seen.update({"link_id": link_id, "reason": reason})
        return {"canceled": [], "skipped": []}

    monkeypatch.setattr(
        "foms.services.integrations.naver_commerce.fulfillment.cancel_order", _old_shape_cancel)
    monkeypatch.setattr(
        "foms.services.integrations.naver_commerce.client.NaverCommerceClient",
        lambda *a, **k: _StubClient())
    lid = _link("PO-PC-WKN-M", order_no="N-PC-WKN", addon=False)

    tasks.run_naver_fulfillment_task(lid, "cancel", 5, reason="INTENT_CHANGED")

    assert seen == {"link_id": lid, "reason": "INTENT_CHANGED"}


# --------------------------------------------------------------------------- #
# 라우트 (계약 §3) — web 은 큐에 넣기만 한다
# --------------------------------------------------------------------------- #

def _capture_enqueue(monkeypatch, name: str) -> list[dict[str, Any]]:
    """``foms.services.jobs.queue.<name>`` 을 기록기로 바꾼다(**kwargs 로 새 인자도 받는다)."""
    calls: list[dict[str, Any]] = []

    def _fake(link_id, reason, detail=None, actor_user_id=None, **kwargs):
        calls.append({"link_id": link_id, "reason": reason, "detail": detail,
                      "actor_user_id": actor_user_id, **kwargs})
        return True

    monkeypatch.setattr(f"foms.services.jobs.queue.{name}", _fake)
    return calls


def _last_audit(action: str) -> SecurityLog:
    """그 action 의 마지막 감사 행."""
    db_session.expire_all()
    row = (db_session.query(SecurityLog).filter(SecurityLog.action == action)
           .order_by(SecurityLog.id.desc()).first())
    assert row is not None, f"{action} 감사 행이 없다"
    return row


def test_cancel_route_400s_on_an_empty_list(auth_client, monkeypatch, workbench_on, partial_on):
    """빈 목록은 400 — "선택 없으면 전체" 는 2026-08-14 사고의 모양이다(C2)."""
    calls = _capture_enqueue(monkeypatch, "enqueue_naver_cancel")
    lid = _link("PO-PC-R0-M", order_no="N-PC-R0", addon=False)

    response = auth_client.post(f"/admin/naver-ingest/{lid}/cancel",
                                json={"reason": "INTENT_CHANGED", "product_order_ids": []})

    assert response.status_code == 400
    assert response.get_json()["error"] == "대상 상품주문을 고르세요."
    assert calls == []


def test_cancel_route_400s_on_an_id_outside_the_household(auth_client, monkeypatch,
                                                          workbench_on, partial_on):
    """집 밖 id 는 400 이고 그 id 를 말한다 — 큐에 넣지 않는다."""
    calls = _capture_enqueue(monkeypatch, "enqueue_naver_cancel")
    lid = _link("PO-PC-RX-M", order_no="N-PC-RX", addon=False)

    response = auth_client.post(f"/admin/naver-ingest/{lid}/cancel",
                                json={"reason": "INTENT_CHANGED",
                                      "product_order_ids": ["PO-NOPE-ROUTE"]})

    assert response.status_code == 400
    assert "PO-NOPE-ROUTE" in response.get_json()["error"]
    assert calls == []


def test_cancel_route_403s_when_the_partial_gate_is_off_but_ids_are_given(auth_client, monkeypatch,
                                                                          workbench_on):
    """부분 선택 게이트가 꺼진 화면에서 목록이 오면 403 — 게이트 끄기가 롤백 경로다(C8)."""
    _partial_off(monkeypatch)
    calls = _capture_enqueue(monkeypatch, "enqueue_naver_cancel")
    lid = _link("PO-PC-RG-M", order_no="N-PC-RG", addon=False)

    response = auth_client.post(f"/admin/naver-ingest/{lid}/cancel",
                                json={"reason": "INTENT_CHANGED",
                                      "product_order_ids": ["PO-PC-RG-M"]})

    assert response.status_code == 403
    assert response.get_json()["error"] == "이 화면에서는 일부 상품주문만 고를 수 없습니다."
    assert calls == []


def test_cancel_route_passes_ids_to_the_queue_and_audits_them(auth_client, monkeypatch,
                                                              workbench_on, partial_on):
    """목록이 큐 kwarg 로 가고, 응답과 감사 원장이 ``scope="partial"`` 과 목록을 함께 남긴다."""
    calls = _capture_enqueue(monkeypatch, "enqueue_naver_cancel")
    lid = _link("PO-PC-RQ-M", order_no="N-PC-RQ", addon=False)
    _link("PO-PC-RQ-A1", order_no="N-PC-RQ", addon=True)

    response = auth_client.post(f"/admin/naver-ingest/{lid}/cancel",
                                json={"reason": "INTENT_CHANGED",
                                      "product_order_ids": ["PO-PC-RQ-A1"]})

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["data"]["scope"] == "partial"
    assert body["data"]["product_order_ids"] == ["PO-PC-RQ-A1"]
    assert len(calls) == 1 and calls[0]["product_order_ids"] == ["PO-PC-RQ-A1"]
    audit = _last_audit("NAVER_INGEST_CANCEL_ENQUEUE")
    assert audit.detail["product_order_ids"] == ["PO-PC-RQ-A1"]
    assert audit.detail["scope"] == "partial"


def test_cancel_route_without_the_key_enqueues_the_household(auth_client, monkeypatch,
                                                             workbench_on, partial_on):
    """★ 음성 대조군 — 키 부재 본문은 오늘처럼 집 전체: 큐에 ``product_order_ids`` 가 None 이거나 없다."""
    calls = _capture_enqueue(monkeypatch, "enqueue_naver_cancel")
    lid = _link("PO-PC-RH-M", order_no="N-PC-RH", addon=False)

    response = auth_client.post(f"/admin/naver-ingest/{lid}/cancel",
                                json={"reason": "INTENT_CHANGED"})

    assert response.status_code == 200
    assert response.get_json()["success"] is True
    assert len(calls) == 1
    assert calls[0].get("product_order_ids") is None


def test_return_route_400s_on_an_empty_list(auth_client, monkeypatch, workbench_on, partial_on):
    """반품 라우트 — 빈 목록 400(취소의 거울)."""
    calls = _capture_enqueue(monkeypatch, "enqueue_naver_return")
    lid = _link("PO-PC-RR0-M", order_no="N-PC-RR0", addon=False, dispatched=True)

    response = auth_client.post(f"/admin/naver-ingest/{lid}/return",
                                json={"reason": "COLOR_AND_SIZE", "product_order_ids": []})

    assert response.status_code == 400
    assert response.get_json()["error"] == "대상 상품주문을 고르세요."
    assert calls == []


def test_return_route_passes_ids_to_the_queue_and_audits_them(auth_client, monkeypatch,
                                                              workbench_on, partial_on):
    """반품 라우트 — 목록이 큐로 가고 ``NAVER_INGEST_RETURN_ENQUEUE`` 감사 detail 에 남는다."""
    calls = _capture_enqueue(monkeypatch, "enqueue_naver_return")
    lid = _link("PO-PC-RRQ-M", order_no="N-PC-RRQ", addon=False, dispatched=True)
    _link("PO-PC-RRQ-A1", order_no="N-PC-RRQ", addon=True, dispatched=True)

    response = auth_client.post(f"/admin/naver-ingest/{lid}/return",
                                json={"reason": "COLOR_AND_SIZE",
                                      "product_order_ids": ["PO-PC-RRQ-A1"]})

    assert response.status_code == 200
    body = response.get_json()
    assert body["data"]["scope"] == "partial"
    assert body["data"]["product_order_ids"] == ["PO-PC-RRQ-A1"]
    assert len(calls) == 1 and calls[0]["product_order_ids"] == ["PO-PC-RRQ-A1"]
    audit = _last_audit("NAVER_INGEST_RETURN_ENQUEUE")
    assert audit.detail["product_order_ids"] == ["PO-PC-RRQ-A1"]
    assert audit.detail["scope"] == "partial"


# --------------------------------------------------------------------------- #
# 미리보기 GET /claim-plan (계약 §3, T5) — web 에서 돌고 네이버를 부르지 않는다
# --------------------------------------------------------------------------- #

def _plan(client, link_id: int, query: str) -> Any:
    """claim-plan 응답 전체(JSON)."""
    return client.get(f"/admin/naver-ingest/{link_id}/claim-plan?{query}")


def test_claim_plan_returns_the_default_selection(client, workbench_on, partial_on):
    """``po`` 부재 = 보낼 수 있는 전부(claim 순). 이미 취소된 C1 은 ``sendable False, reason_code "claim"``."""
    _login(client)
    order_no = "N-PC-CP"
    ids = _household_2354(order_no)

    response = _plan(client, ids["M"], "action=cancel")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["link_id"] == ids["M"]
    assert data["todo"] == [_ext(order_no, n) for n in ("A1", "A2", "A3", "M")]
    rows = {r["external_id"]: r for r in data["rows"]}
    assert rows[_ext(order_no, "C1")]["sendable"] is False
    assert rows[_ext(order_no, "C1")]["reason_code"] == "claim"
    assert rows[_ext(order_no, "M")]["is_addon"] is False
    assert len(data["rows"]) == 8


def test_claim_plan_applies_auto_companion(client, workbench_on, partial_on):
    """``po=M`` 만 고르면 서버가 A1~A3 을 자동 동반으로 붙이고 ``ok`` 다(결정 3)."""
    _login(client)
    order_no = "N-PC-CPA"
    ids = _household_2354(order_no)

    data = _plan(client, ids["M"], f"action=cancel&po={_ext(order_no, 'M')}").get_json()["data"]

    assert data["ok"] is True
    assert data["auto_added"] == [_ext(order_no, n) for n in ("A1", "A2", "A3")]
    assert data["todo"] == [_ext(order_no, n) for n in ("A1", "A2", "A3", "M")]
    assert data["selected"] == [_ext(order_no, "M")]


def test_claim_plan_says_so_on_an_empty_selection(client, workbench_on, partial_on):
    """``po=``(빈 문자열) = [] — ``ok False`` 와 고르라는 문장. 빈 선택은 전체가 아니다."""
    _login(client)
    ids = _household_2354("N-PC-CPE")

    data = _plan(client, ids["M"], "action=cancel&po=").get_json()["data"]

    assert data["ok"] is False
    assert data["message"] == "대상 상품주문을 고르세요."
    assert data["todo"] == []


def test_claim_plan_404s_when_the_gate_is_off(client, monkeypatch, workbench_on):
    """부분 선택 게이트가 꺼진 화면에는 이 경로가 없다(404)."""
    _partial_off(monkeypatch)
    _login(client)
    ids = _household_2354("N-PC-CPG")

    assert _plan(client, ids["M"], "action=cancel").status_code == 404


def test_claim_plan_400s_on_a_bad_action(client, workbench_on, partial_on):
    """``action`` 은 cancel|return 만 — 그 밖은 400 JSON."""
    _login(client)
    ids = _household_2354("N-PC-CPB")

    response = _plan(client, ids["M"], "action=swap")

    assert response.status_code == 400
    body = response.get_json()
    assert body["success"] is False
    assert body["error"] == "action 이 올바르지 않습니다."


def test_claim_plan_never_constructs_the_naver_client(client, monkeypatch, workbench_on,
                                                      partial_on):
    """미리보기는 순수 계산이다 — 클라이언트 생성 자체를 폭탄으로 바꿔도 200."""
    def _boom(*a, **k):
        raise AssertionError("claim-plan 이 NaverCommerceClient 를 만들었다 — web 에서 네이버로 나간다")

    monkeypatch.setattr(
        "foms.services.integrations.naver_commerce.client.NaverCommerceClient", _boom)
    _login(client)
    ids = _household_2354("N-PC-CPN")

    response = _plan(client, ids["M"], "action=return")

    assert response.status_code == 200
    assert response.get_json()["success"] is True


# --------------------------------------------------------------------------- #
# 화면 — pane (계약 §4)
# --------------------------------------------------------------------------- #

def _pane_of(client, link_id: int) -> str:
    """pane 조각 HTML."""
    response = client.get(f"{PANE_PATH}?link_id={link_id}")
    assert response.status_code == 200, response.status_code
    return response.get_data(as_text=True)


def test_cancel_modal_lists_rows_with_checkboxes_when_the_gate_is_on(client, workbench_on,
                                                                     partial_on):
    """게이트 ON — 취소 모달이 집의 상품주문을 체크박스 목록으로 그리고, 이미 취소된 C1 은 잠긴다.

    기준 사례 #2354 그대로다(브리프 §2-1 ①). 형제 ``CANCEL_DONE``(판매자센터 취소)은
    ``household_claimed`` 로 발주확인·발송 축을 잠그지만, 계약 §4 개정(2026-09-11 CEO)으로
    ``can_cancel`` 은 ``household_claimed`` 를 안 본다 — ``cancel_sendable_count`` 와 서버
    ``_claim_guard(scope=todo)`` 가 형제 클레임을 행 단위로 거른다. 그래서 이 집에서도 취소
    모달이 렌더되고 C1 은 "취소 완료" 로 잠긴다(단언 유지).
    """
    _login(client)
    order_no = "N-PC-UI"
    ids = _household_2354(order_no)

    pane = _pane_of(client, ids["M"])

    assert 'id="wb-cancel-scope"' in pane
    assert 'class="form-check-input wb-scope-pick"' in pane
    assert 'name="po"' in pane
    assert f'value="{_ext(order_no, "A1")}"' in pane
    assert is_disabled(pane, f"wb-cancel-po-{ids['C1']}") is True
    assert is_disabled(pane, f"wb-cancel-po-{ids['A1']}") is False
    assert 'id="wb-cancel-selected-count"' in pane
    assert has_attribute(pane, "wb-cancel-scope-auto", "data-foms-no-autodismiss")


def test_cancel_modal_disables_our_partially_canceled_row(client, workbench_on, partial_on):
    """게이트 ON, 잠기지 않는 집 — 우리가 부분 취소한 라인은 체크 불가(``canceled_ours``), 나머지는 체크 가능.

    위 테스트가 집 잠금 결정에 걸려 있어, 계약 §3 그대로도 반드시 green 이어야 하는
    변형을 따로 둔다: 형제 표식이 partial 이면 ``cancel_lock`` 이 거짓이라 모달이 뜬다.
    """
    _login(client)
    order_no = "N-PC-UIP"
    main = _link("PO-PC-UIP-M", order_no=order_no, addon=False)
    a1 = _link("PO-PC-UIP-A1", order_no=order_no, addon=True)
    done = _link("PO-PC-UIP-A2", order_no=order_no, addon=True,
                 canceled=True, cancel_scope="partial")

    pane = _pane_of(client, main)

    assert 'id="wb-cancel-scope"' in pane
    assert is_disabled(pane, f"wb-cancel-po-{done}") is True
    assert is_disabled(pane, f"wb-cancel-po-{a1}") is False
    assert is_disabled(pane, f"wb-cancel-po-{main}") is False
    assert 'id="wb-cancel-selected-list"' in pane
    assert 'id="wb-cancel-scope-rest"' in pane
    assert has_attribute(pane, "wb-cancel-scope-auto", "data-foms-no-autodismiss")


def test_cancel_modal_is_the_old_one_when_the_gate_is_off(client, monkeypatch, workbench_on):
    """★ 음성 대조군 — 게이트 OFF 면 옛 모달 그대로: 목록 없음, "상품주문 1건을" 재진술(단건 집)."""
    _partial_off(monkeypatch)
    _login(client)
    main = _link("PO-PC-OLD-M", order_no="N-PC-OLD", addon=False)

    pane = _pane_of(client, main)

    assert 'id="wb-modal-cancel"' in pane
    assert "wb-cancel-scope" not in pane
    assert "상품주문 1건을" in pane


def test_members_table_shows_our_cancel_line(client, workbench_on):
    """멤버 표 클레임 칸에 취소 축 "우리 취소 {시각}" 줄이 생긴다 — 재수집 전엔 스냅샷에 없어서다."""
    _login(client)
    order_no = "N-PC-MEM"
    main = _link("PO-PC-MEM-M", order_no=order_no, addon=False)
    _link("PO-PC-MEM-A1", order_no=order_no, addon=True, canceled=True, cancel_scope="partial")

    pane = _pane_of(client, main)

    assert "우리 취소 " in pane


def test_partially_canceled_household_keeps_confirm_open(client, workbench_on):
    """결정 5 화면 — partial 표식 형제는 발주확인 버튼을 잠그지 않는다; household 표식은 잠근다(v3 :413)."""
    _login(client)
    open_main = _link("PO-PC-CF-M", order_no="N-PC-CF", addon=False, place="NOT_YET")
    _link("PO-PC-CF-A1", order_no="N-PC-CF", addon=True, place="NOT_YET",
          canceled=True, cancel_scope="partial")
    lock_main = _link("PO-PC-CFL-M", order_no="N-PC-CFL", addon=False, place="NOT_YET")
    _link("PO-PC-CFL-A1", order_no="N-PC-CFL", addon=True, place="NOT_YET",
          canceled=True, cancel_scope="household")

    open_pane = _pane_of(client, open_main)
    locked_pane = _pane_of(client, lock_main)

    assert is_disabled(open_pane, "wb-confirm") is False
    assert 'id="wb-modal-confirm"' in open_pane
    assert is_disabled(locked_pane, "wb-confirm") is True


def _list_row(client, order_no: str) -> str:
    """처리 목록(``tab=work``)에서 그 주문번호 집의 줄(``<a class="wb-row" …</a>``) 하나.

    test_naver_workbench._row_of 와 같은 규칙 — 줄을 먼저 나누고 그 안에서 찾는다. 주문번호는
    줄의 ``data-find`` 에 소문자로만 들어 있어 소문자로 맞춘다.
    """
    body = client.get(f"{TRIAGE_PATH}?tab=work").get_data(as_text=True)
    for chunk in body.split('<a class="wb-row')[1:]:
        row = '<a class="wb-row' + chunk.split("</a>")[0]
        if order_no.lower() in row:
            return row
    raise AssertionError(f"목록에 '{order_no}' 집의 줄이 없다")


def _pick_tag(row: str) -> str:
    """목록 줄 안의 벌크 체크박스(``class="wb-pick"``) 여는 태그."""
    at = row.find('class="wb-pick"')
    assert at >= 0, "목록 줄에 벌크 체크박스가 없다"
    return row[row.rfind("<", 0, at):row.find(">", at) + 1]


def _partial_sibling_household(order_no: str, *, cancel_scope: str) -> tuple[int, int]:
    """본품(NOT_YET) + 형제 1건(우리 취소 표식 + 재수집된 ``CANCEL_DONE``) 집 — (본품, 형제) link id.

    ``cancel_scope`` 가 ``partial`` 이면 결정 5 의 열린 집, ``household``·빈 값(옛 표식)이면
    집 전체 취소로 잠기는 집이다. 형제 스냅샷에 클레임을 함께 심는 이유는 다음 수집 뒤 모양
    (부분 취소가 형제 클레임으로 읽히는 자리)을 재현하기 위해서다.
    """
    main = _link(f"{order_no}-M", order_no=order_no, addon=False, place="NOT_YET")
    a1 = _link(f"{order_no}-A1", order_no=order_no, addon=True, canceled=True,
               cancel_scope=cancel_scope, claim="CANCEL_DONE", claim_type="CANCEL")
    return main, a1


def test_list_row_and_pane_stay_open_for_a_partially_canceled_sibling(client, workbench_on):
    """결정 5 목록 줄 — 우리가 일부 취소한 형제의 ``CANCEL_DONE`` 은 집을 잠그지 않는다.

    ``_attach_household_counts``(옛 경로)·``_build_sibling_index`` 가 ``_group_queue``·
    ``_household_has_claim`` 과 같은 규칙으로 partial 행을 건너뛰어야 목록 줄이 ``stop``/
    ``locked`` 로 그려지지 않고 벌크 체크가 열리며, pane 의 발주확인 버튼도 같은 말을 한다.
    음성 대조군: 같은 집에서 표식이 ``household`` 또는 키 없음(옛 표식)이면 stop/locked.
    """
    _login(client)
    open_main, _ = _partial_sibling_household("N-PC-LST", cancel_scope="partial")

    row = _list_row(client, "N-PC-LST")
    assert "wb-row--stop" not in row, row
    assert "wb-row--locked" not in row, row
    assert "disabled" not in _pick_tag(row), _pick_tag(row)
    pane = _pane_of(client, open_main)
    assert is_disabled(pane, "wb-confirm") is False
    assert 'id="wb-modal-confirm"' in pane

    for order_no, scope in (("N-PC-LSTH", "household"), ("N-PC-LSTO", "")):
        lock_main, _ = _partial_sibling_household(order_no, cancel_scope=scope)
        locked_row = _list_row(client, order_no)
        assert "wb-row--stop" in locked_row, (scope, locked_row)
        assert "wb-row--locked" in locked_row, (scope, locked_row)
        assert "disabled" in _pick_tag(locked_row), (scope, _pick_tag(locked_row))
        assert is_disabled(_pane_of(client, lock_main), "wb-confirm") is True, scope


def test_pane_buttons_do_not_depend_on_which_sibling_opened_it(client, workbench_on):
    """M-4 — pane 을 **부분 취소 행 자체**(A1)로 열어도 발주확인·발송 버튼은 본품(M)으로 열 때와 같다.

    A1 의 스냅샷은 ``CANCEL_DONE`` 이라 ``selected.claim.blocking`` 이 참이다. pane 이 그것을
    ``selected.partial_canceled`` 없이 ``household_claimed`` 로 읽으면 A1 로 연 화면만 잠긴다.
    발주확인 전 집(NOT_YET)은 ``wb-confirm`` 이, 발주확인이 끝난 집은 ``wb-dispatch`` 가
    두 화면에서 똑같이 열려 있어야 한다.
    """
    _login(client)
    confirm_main, confirm_a1 = _partial_sibling_household("N-PC-SIB", cancel_scope="partial")
    dispatch_main = _link("PO-PC-SIBD-M", order_no="N-PC-SIBD", addon=False)
    dispatch_a1 = _link("PO-PC-SIBD-A1", order_no="N-PC-SIBD", addon=True, canceled=True,
                        cancel_scope="partial", claim="CANCEL_DONE", claim_type="CANCEL")

    by_main, by_a1 = _pane_of(client, confirm_main), _pane_of(client, confirm_a1)
    assert is_disabled(by_main, "wb-confirm") is False
    assert is_disabled(by_a1, "wb-confirm") is is_disabled(by_main, "wb-confirm")
    assert is_disabled(by_a1, "wb-dispatch") is is_disabled(by_main, "wb-dispatch")

    by_main, by_a1 = _pane_of(client, dispatch_main), _pane_of(client, dispatch_a1)
    assert is_disabled(by_main, "wb-dispatch") is False
    assert is_disabled(by_a1, "wb-dispatch") is is_disabled(by_main, "wb-dispatch")
    assert is_disabled(by_a1, "wb-confirm") is is_disabled(by_main, "wb-confirm")


# --------------------------------------------------------------------------- #
# 벌크 발송 pre-check — `_cancel_guard` 거울 (결정 5, 스펙 §11 결정 9)
# --------------------------------------------------------------------------- #

def test_bulk_blocking_reason_mirrors_the_cancel_guard(app):
    """``bulk_dispatch._blocking_reason`` 은 순수 함수다 — 네이버 0회, ``_StubClient`` 조차 없다.

    partial 표식 + 재수집 ``CANCEL_DONE`` 형제 집은 ``""``(보낼 수 있다), household 표식 집은
    '취소한 주문입니다', 취소 실패가 남은(``last_error_action == "cancel"``) 집은
    '취소가 실패한 상품주문이 있습니다' — ``fulfillment._cancel_guard`` 와 같은 갈래·순서.
    """
    from foms.services.integrations.naver_commerce.bulk_dispatch import _blocking_reason

    open_main = _link("PO-PC-BK-M", order_no="N-PC-BK", addon=False)
    _link("PO-PC-BK-A1", order_no="N-PC-BK", addon=True, canceled=True,
          cancel_scope="partial", claim="CANCEL_DONE", claim_type="CANCEL")
    lock_main = _link("PO-PC-BKH-M", order_no="N-PC-BKH", addon=False)
    _link("PO-PC-BKH-A1", order_no="N-PC-BKH", addon=True, canceled=True,
          cancel_scope="household")
    fail_main = _link("PO-PC-BKF-M", order_no="N-PC-BKF", addon=False)
    fail_a1 = _link("PO-PC-BKF-A1", order_no="N-PC-BKF", addon=True)
    row = db_session.get(ExternalOrderLink, fail_a1)
    row.triage_state = {"fulfillment": {"last_error": "상품 주문 상태 확인 필요",
                                        "last_error_action": "cancel"}}
    flag_modified(row, "triage_state")
    db_session.commit()

    assert _blocking_reason(_links(open_main)) == ""
    assert _blocking_reason(_links(lock_main)).startswith("취소한 주문입니다")
    assert "1건" in _blocking_reason(_links(lock_main))
    assert _blocking_reason(_links(fail_main)).startswith("취소가 실패한 상품주문이 있습니다")


def test_no_duplicate_wb_ids_with_both_scope_modals(client, workbench_on, partial_on):
    """새 모달 목록이 붙어도 ``id="wb-…"`` 는 문서 안에서 유일하다(v3 절대 규칙 1).

    취소 모달(발송 0건 집)과 반품 모달(발송 집)은 한 pane 에 함께 뜰 수 없으므로 각각 렌더해
    센다 — 겹치면 5번째 행 취소가 1번째 집으로 나간다.
    """
    _login(client)
    cancel_main = _link("PO-PC-DUP-M", order_no="N-PC-DUP", addon=False)
    _link("PO-PC-DUP-A1", order_no="N-PC-DUP", addon=True)
    return_main = _link("PO-PC-DUPR-M", order_no="N-PC-DUPR", addon=False, dispatched=True)
    _link("PO-PC-DUPR-A1", order_no="N-PC-DUPR", addon=True, dispatched=True)

    for link_id in (cancel_main, return_main):
        pane = _pane_of(client, link_id)
        counts = Counter(re.findall(r'id="(wb-[^"]+)"', pane))
        dupes = {k: v for k, v in counts.items() if v > 1}
        assert not dupes, f"중복 id: {dupes}"


# --------------------------------------------------------------------------- #
# 정적 계약 — JS·핀
# --------------------------------------------------------------------------- #

def _js_block(js: str, first: str, last: str) -> str:
    """``first`` 함수 정의부터 ``last`` 함수 정의가 끝나는 곳(다음 함수 선언 직전)까지."""
    start = re.search(rf"(function\s+{first}\s*\(|{first}\s*=\s*(async\s*)?(function|\())", js)
    assert start, f"{first} 정의가 없다"
    tail = re.search(rf"(function\s+{last}\s*\(|{last}\s*=\s*(async\s*)?(function|\())", js)
    assert tail, f"{last} 정의가 없다"
    after = re.search(r"\n\s*(async\s+)?function\s+\w+\s*\(|\n\s*(const|let|var)\s+\w+\s*=\s*(async\s*)?\(",
                      js[tail.end():])
    end = tail.end() + after.start() if after else len(js)
    return js[start.start():end]


def test_js_sends_product_order_ids_and_locks_more_buttons():
    """JS 계약 — 본문에 ``product_order_ids``, 미리보기 함수 3종, 잠금 목록 확장, 새 블록에 innerHTML 없음."""
    js = JS_PATH.read_text(encoding="utf-8")

    for needle in ("product_order_ids", "scopeSelection", "refreshClaimPlan", "renderClaimPlan",
                   "/claim-plan", "'wb-return-reject'", "'wb-return-approve-btn'",
                   "대상 상품주문을 고르세요", "submitCancel", "submitReturn", "watchFulfillment("):
        assert needle in js, f"{needle} 가 JS 에 없다"

    block = _js_block(js, "scopeSelection", "renderClaimPlan")
    assert "innerHTML" not in block, "새 함수 블록이 innerHTML 을 쓴다(XSS) — textContent 만"


def test_workbench_pins_moved_to_20260911a():
    """CSS·JS 를 고쳤으면 ``?v`` 핀이 함께 움직인다(SW staticCacheFirst) — 2026-09-11 부분 취소·반품."""
    markup = WORKBENCH_TEMPLATE.read_text(encoding="utf-8")

    assert markup.count("?v=20260911a") == 2
    assert "?v=20260910a" not in markup
