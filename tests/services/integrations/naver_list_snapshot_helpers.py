"""처리 목록 축소 스냅샷 계약의 공용 재료 — 모양 표본·경로 추적기·포함 판정.

SQLite 레인(``test_naver_workbench_list_snapshot``)과 PG 레인
(``tests/postgres/test_naver_workbench_list_snapshot_pg``)이 **같은 표본**을 쓴다. 표본은
목록 함수의 갈래가 한 번씩 걸리게 만든 것이다: 평평한 응답, ``productOrder`` 가 dict 가
아닌 원본, 배송지·발송 블록의 폴백 자리(최상위·상품주문·주문), 클레임 블록 다섯 그릇,
보류·배송비 귀책, 추가구성상품, 사본 컬럼이 빈 구매확정, 명시적 null, 빈 원본, 그리고
목록이 안 읽는 키만 든 원본.
"""
from __future__ import annotations

import copy
import datetime
from typing import Any, Optional

from models import ExternalOrderLink

_REVIEWED_AT = datetime.datetime(2026, 10, 2, 0, 0, 0)

#: 목록이 **안 읽는** 큰 덩어리 — 투영이 떨어뜨려야 할 것들.
_DROPPED_PO = {"takingAddress": {"name": "회수지", "baseAddress": "경기 물류로 1"},
               "inflowPath": "검색", "mallId": "m-1", "commissionRatingType": "A",
               "knowledgeShoppingSellingInterlockCommission": 0, "itemNo": "I-1"}
_DROPPED_ORDER = {"ordererName": "주문자", "ordererTel": "010-0000-0000", "ordererId": "uid"}
_DROPPED_ROOT = {"completedClaims": [{"claimType": "CANCEL", "claimStatus": "CANCEL_REJECT"}]}


def _po(pid: str, name: str, tel: str, addr: str, **extra: Any) -> dict[str, Any]:
    """중첩 응답의 상품주문 한 덩어리(목록이 읽는 키 전부 + 안 읽는 키)."""
    body = {
        "productOrderId": pid, "productName": f"{name} 상품", "productOption": "색상: 흰색",
        "productClass": "조합형옵션상품", "productOrderStatus": "PAYED", "quantity": 1,
        "totalPaymentAmount": 300000, "unitPrice": 320000, "optionPrice": 0,
        "productDiscountAmount": 20000, "expectedSettlementAmount": 280000,
        "placeOrderStatus": "NOT_YET", "placeOrderDate": "2026-10-01T10:00:00.000+09:00",
        "shippingDueDate": "2026-10-05T23:59:59.000+09:00",
        "shippingAddress": {"name": name, "tel1": tel, "tel2": "02-000-0000",
                            "baseAddress": addr, "detailedAddress": "101호", "zipCode": "04500"},
        "appliedCoupons": [
            {"couponClassCode": "NMP_PRD_DCNT", "couponDiscountAmount": 10000,
             "couponPublishNumber": "C-1", "naverBurdenRatio": 100},
            {"couponClassCode": "NMP_PRD_DUP_DCNT", "couponDiscountAmount": 5000,
             "couponPublishNumber": "C-2", "naverBurdenRatio": None},
        ],
        "appliedCardPromotion": {"promotionName": "카드 3%", "cardCompanyName": "삼성",
                                 "promotionApplyAmount": 9000},
        **_DROPPED_PO,
    }
    body.update(extra)
    return body


def _order(order_no: str, **extra: Any) -> dict[str, Any]:
    body = {"orderId": order_no, "orderDate": "2026-10-01T09:00:00.000+09:00",
            "paymentDate": "2026-10-01T09:01:00.000+09:00", "paymentMeans": "신용카드",
            "payLocationType": "MOBILE", **_DROPPED_ORDER}
    body.update(extra)
    return body


def _nested(order_no: str, pid: str, name: str, tel: str, addr: str, *,
            po: Optional[dict] = None, order: Optional[dict] = None,
            **root: Any) -> dict[str, Any]:
    return {"order": _order(order_no, **(order or {})),
            "productOrder": _po(pid, name, tel, addr, **(po or {})),
            **_DROPPED_ROOT, **root}


_DELIVERY = {"deliveryMethod": "DIRECT_DELIVERY", "deliveryStatus": "DELIVERED",
             "sendDate": "2026-10-02T10:00:00.000+09:00", "isWrongTrackingNumber": "false"}

#: ``{이름표: (원본, 행 속성)}`` — 이름표는 사람이 읽는 것이고 external_id 의 꼬리다.
SHAPES: dict[str, tuple[Any, dict[str, Any]]] = {
    "중첩-정상": (_nested("LS-1", "LS-P1", "가집", "010-7000-0001", "서울 A로 1"), {}),
    "추가구성상품-형제": (_nested("LS-1", "LS-P1A", "가집", "010-7000-0001", "서울 A로 1",
                                po={"productClass": "추가구성상품", "totalPaymentAmount": 0}),
                         {"relation": "ADDON"}),
    "발주확인끝난-반품형제": (_nested("LS-1", "LS-P1B", "가집", "010-7000-0001", "서울 A로 1",
                                    po={"placeOrderStatus": "OK", "claimStatus": "RETURN_REQUEST",
                                        "claimType": "RETURN"}, delivery=_DELIVERY),
                            {"place_order_status": "OK", "sync_status": "LINKED",
                             "reviewed_at": _REVIEWED_AT}),
    "취소요청-cancel블록": (_nested("LS-2", "LS-P2", "나집", "010-7000-0002", "서울 B로 2",
                                  po={"claimStatus": "CANCEL_REQUEST", "claimType": "CANCEL"},
                                  cancel={"claimStatus": "CANCEL_REQUEST", "cancelReason": "단순변심",
                                          "cancelDetailedReason": "재결제 예정",
                                          "claimRequestDate": "2026-10-02",
                                          "holdbackStatus": "HOLDBACK"}), {}),
    "currentClaim-반품래퍼": (_nested("LS-3", "LS-P3", "다집", "010-7000-0003", "서울 C로 3",
                                    delivery=_DELIVERY,
                                    currentClaim={"return": {
                                        "claimStatus": "RETURN_REQUEST", "returnReason": "파손",
                                        "claimDeliveryFeePayMethod": "SELLER"}}),
                            {"triage_state": {"fulfillment": {"dispatched_at": "2026-10-02T01:00:00"}}}),
    "currentClaim-평평한교환": (_nested("LS-4", "LS-P4", "라집", "010-7000-0004", "서울 D로 4",
                                      currentClaim={"claimStatus": "EXCHANGE_REQUEST",
                                                    "claimType": "EXCHANGE"}), {}),
    "beforeClaim-교환": (_nested("LS-5", "LS-P5", "마집", "010-7000-0005", "서울 E로 5",
                                beforeClaim={"exchange": {"claimStatus": "EXCHANGE_DONE",
                                                          "claimType": "EXCHANGE"}}), {}),
    "return블록-완료": (_nested("LS-6", "LS-P6", "바집", "010-7000-0006", "서울 F로 6",
                              delivery=_DELIVERY,
                              **{"return": {"claimStatus": "RETURN_DONE", "claimType": "RETURN",
                                            "returnCompletedDate": "2026-10-02",
                                            "collectAddress": {"name": "바집"}}}),
                       {"triage_state": {"return": {"requested_at": "2026-10-01T00:00:00",
                                                    "approved_at": "2026-10-02T00:00:00"}}}),
    "returnInfo-수거중": (_nested("LS-7", "LS-P7", "사집", "010-7000-0007", "서울 G로 7",
                                returnInfo={"claimStatus": "COLLECTING"}),
                         {"triage_state": {"return": {"requested_at": "2026-10-01T00:00:00",
                                                      "approve_skipped_reason": "보류"}}}),
    "발송-상품주문폴백": (_nested("LS-8", "LS-P8", "아집", "010-7000-0008", "서울 H로 8",
                                po={"delivery": dict(_DELIVERY)}), {}),
    "발송-주문폴백": (_nested("LS-9", "LS-P9", "자집", "010-7000-0009", "서울 I로 9",
                             order={"delivery": dict(_DELIVERY)}), {}),
    "배송지-최상위폴백": ({**_nested("LS-10", "LS-P10", "차집", "010-7000-0010", "서울 J로 10",
                                    po={"shippingAddress": None}),
                          "shippingAddress": {"name": "차집", "tel1": "010-7000-0010",
                                              "baseAddress": "서울 J로 10"}}, {}),
    "평평한응답": ({"productOrderId": "LS-P11", "productName": "평평 상품", "quantity": 2,
                  "totalPaymentAmount": 50000, "claimStatus": "CANCEL_REQUEST",
                  "claimType": "CANCEL", "placeOrderStatus": "NOT_YET",
                  "shippingDueDate": "2026-10-06", "productOrderStatus": "PAYED",
                  "shippingAddress": {"name": "평평", "tel1": "010-7000-0011",
                                      "baseAddress": "서울 K로 11"},
                  "appliedCoupons": [{"couponDiscountAmount": 1000}], **_DROPPED_PO}, {}),
    "productOrder-dict아님": ({"order": _order("LS-12"), "productOrder": "깨짐",
                               "productName": "깨진 원본", "placeOrderStatus": "NOT_YET",
                               "shippingAddress": {"tel1": "010-7000-0012"}}, {}),
    "구매확정-사본없음": (_nested("LS-13", "LS-P13", "카집", "010-7000-0013", "서울 L로 13",
                               po={"productOrderStatus": "PURCHASE_DECIDED"}, delivery=_DELIVERY),
                        {"product_order_status": None}),
    "구매확정-최상위키": ({**_nested("LS-14", "LS-P14", "타집", "010-7000-0014", "서울 M로 14",
                                   delivery=_DELIVERY),
                          "productOrderStatus": "PURCHASE_DECIDED"},
                         {"product_order_status": None}),
    "명시적null": ({"order": None, "productOrder": {"productOrderId": "LS-P15", "claimStatus": None,
                                                    "appliedCoupons": None, "shippingAddress": None,
                                                    "quantity": None},
                    "delivery": None, "cancel": None}, {}),
    "주문쪽-보류": (_nested("LS-16", "LS-P16", "파집", "010-7000-0016", "서울 N로 16",
                           po={"claimStatus": "RETURN_REQUEST", "claimType": "RETURN"},
                           order={"holdbackStatus": "HOLDBACK",
                                  "claimDeliveryFeePayMethod": "BUYER"}, delivery=_DELIVERY), {}),
    "직권취소": (_nested("LS-17", "LS-P17", "하집", "010-7000-0017", "서울 O로 17",
                       po={"claimStatus": "ADMIN_CANCEL_DONE", "claimType": "ADMIN_CANCEL"}),
                {"triage_state": {"fulfillment": {"canceled_at": "2026-10-02T00:00:00",
                                                  "cancel_scope": "partial"},
                                  "cancel": {"superseded_at": "2026-10-02T00:00:00",
                                             "superseded_status": "CANCEL_REQUEST"}}}),
    "빈원본": ({}, {}),
    "안읽는키만": (copy.deepcopy(_DROPPED_ROOT), {}),
    "원본없음": (None, {}),
}


def seed_shapes(session, *, commit: bool) -> list[ExternalOrderLink]:
    """표본을 링크로 심는다(기본: 확인 대기 수집분, 사본 컬럼은 원본에서 채운 값).

    Args:
        session: DB 세션.
        commit: True 면 커밋(SQLite 레인), False 면 flush(PG 레인 — 테스트 끝에 롤백).

    Returns:
        심은 링크 목록.
    """
    rows = []
    for index, (label, (snapshot, attrs)) in enumerate(SHAPES.items()):
        order_no = ""
        if isinstance(snapshot, dict) and isinstance(snapshot.get("order"), dict):
            order_no = str(snapshot["order"].get("orderId") or "")
        values = {"channel": "NAVER", "external_id": f"LS-{index:02d}-{label}",
                  "external_order_no": order_no, "sync_status": "COLLECTED",
                  "place_order_status": "NOT_YET", "product_order_status": "PAYED",
                  "raw_snapshot": copy.deepcopy(snapshot)}
        values.update(copy.deepcopy(attrs))
        row = ExternalOrderLink(**values)
        session.add(row)
        rows.append(row)
    if commit:
        session.commit()
    else:
        session.flush()
    return rows


# --------------------------------------------------------------------------- #
# 경로 추적기 — 목록 함수가 원본의 어느 자리를 읽는지 적는다
# --------------------------------------------------------------------------- #

#: 값 하나가 아니라 **자리 전체**를 보는 접근. 투영이 그 자리를 통째로 남겨야만 안전하다.
WHOLE_NODE_OPS = frozenset({"iter", "keys", "items", "values", "eq", "repr", "copy",
                            "reduce", "index", "contains_value"})


def traced(value: Any, path: tuple, log: set) -> Any:
    """dict·list 를 읽기 기록 대역으로 감싼다(그 밖의 값은 그대로)."""
    if isinstance(value, dict):
        return _TracedDict(value, path, log)
    if isinstance(value, list):
        return _TracedList(value, path, log)
    return value


class _TracedDict(dict):
    def __init__(self, raw: dict, path: tuple, log: set):
        super().__init__(raw)
        self._p, self._l, self._c = path, log, {}

    def _child(self, key):
        if key not in self._c:
            self._c[key] = traced(dict.__getitem__(self, key), self._p + (key,), self._l)
        return self._c[key]

    def get(self, key, default=None):
        self._l.add((self._p + (key,), "get"))
        return self._child(key) if dict.__contains__(self, key) else default

    def __getitem__(self, key):
        self._l.add((self._p + (key,), "get"))
        return self._child(key)

    def __contains__(self, key):
        self._l.add((self._p + (key,), "contains"))
        return dict.__contains__(self, key)

    def __len__(self):
        self._l.add((self._p, "len"))
        return dict.__len__(self)

    def _whole(self, op):
        self._l.add((self._p, op))

    def __iter__(self):
        self._whole("iter")
        return dict.__iter__(self)

    def keys(self):
        self._whole("keys")
        return dict.keys(self)

    def items(self):
        self._whole("items")
        return [(key, self._child(key)) for key in dict.keys(self)]

    def values(self):
        self._whole("values")
        return [self._child(key) for key in dict.keys(self)]

    def __eq__(self, other):
        self._whole("eq")
        return dict.__eq__(self, other)

    def __ne__(self, other):
        self._whole("eq")
        return dict.__ne__(self, other)

    __hash__ = None  # type: ignore[assignment]

    def __repr__(self):
        self._whole("repr")
        return dict.__repr__(self)

    def copy(self):
        self._whole("copy")
        return dict.copy(self)

    def __reduce_ex__(self, protocol):
        self._whole("reduce")
        return dict(dict.items(self)).__reduce_ex__(protocol)


class _TracedList(list):
    def __init__(self, raw: list, path: tuple, log: set):
        super().__init__(raw)
        self._p, self._l = path, log

    def __iter__(self):
        self._l.add((self._p, "iter"))
        for index in range(list.__len__(self)):
            yield traced(list.__getitem__(self, index), self._p + ("[]",), self._l)

    def __getitem__(self, index):
        self._l.add((self._p, "index"))
        value = list.__getitem__(self, index)
        return value if isinstance(index, slice) else traced(value, self._p + ("[]",), self._l)

    def __len__(self):
        self._l.add((self._p, "len"))
        return list.__len__(self)

    def __contains__(self, item):
        self._l.add((self._p, "contains_value"))
        return list.__contains__(self, item)

    def __eq__(self, other):
        self._l.add((self._p, "eq"))
        return list.__eq__(self, other)

    __hash__ = None  # type: ignore[assignment]


def _walk(path: tuple, spec: Optional[dict]) -> tuple[bool, bool]:
    """``(투영이 이 자리를 싣는가, 이 자리가 통째 마디 안인가)``."""
    node: Any = spec
    for key in path:
        if node is None:
            return True, True
        if not isinstance(node, dict) or key not in node:
            return False, False
        node = node[key]
    return True, node is None


def uncovered_reads(ops: set, spec: dict) -> set:
    """투영 나무가 못 덮는 읽기를 돌려준다(빈 집합이면 계약 통과).

    - ``get``·``contains``·``len`` — 그 자리가 투영에 실려야 한다.
    - 자리 전체를 보는 접근(:data:`WHOLE_NODE_OPS`) — 그 자리가 **통째 마디 안**이어야 한다.

    Args:
        ops: 추적기가 모은 ``(경로, 접근)`` 집합.
        spec: 투영 나무(:data:`naver_list_snapshot.LIST_SNAPSHOT_SPEC` 또는 음성 대조군).

    Returns:
        덮이지 않은 ``(경로, 접근)`` 집합.
    """
    missing = set()
    for path, op in ops:
        kept, whole = _walk(path, spec)
        if op in WHOLE_NODE_OPS:
            if not whole:
                missing.add((path, op))
        elif not kept:
            missing.add((path, op))
    return missing


def spec_without(spec: dict, path: tuple) -> dict:
    """``path`` 하나를 뺀 투영 나무 사본 — 음성 대조군용."""
    clone = copy.deepcopy(spec)
    node = clone
    for key in path[:-1]:
        node = node[key]
    del node[path[-1]]
    return clone
