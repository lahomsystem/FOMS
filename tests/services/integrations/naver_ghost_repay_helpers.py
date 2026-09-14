# -*- coding: utf-8 -*-
"""유령 주문 '재결제 예정' 테스트 공용 재료 (2026-09-14).

판정·라우트·화면 세 파일이 **같은 모집단 만드는 법**을 써야 한다 — 파일마다 유령 주문을
다르게 지어내면 같은 기능을 서로 다른 사실 위에서 재게 된다. 파일 크기 계약(500줄) 때문에
셋으로 쪼개면서 재료만 여기로 모았다(:mod:`naver_partial_claim_helpers` 와 같은 관례).
"""
from __future__ import annotations

import pathlib
import re

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.integrations.naver_commerce.constants import CHANNEL
from foms.services.integrations.naver_commerce.ghost_orders import (
    _fold_link,
    _new_bucket,
    find_ghost_orders,
)
from foms.services.integrations.naver_commerce.mapping import group_key_text
from models import ExternalOrderLink, Order, User

REPAY_PATH = "/admin/naver-ingest/ghost/{}/repay-expected"
DISCARD_PATH = "/admin/naver-ingest/ghost/{}/discard"
ATTACH_PATH = "/admin/naver-ingest/{}/attach"

#: 표시를 켜는 **유일한 입구**가 사는 자리들. 이 버튼이 조용히 사라져도 서버 테스트는
#: 전부 초록이라(라우트는 그대로 살아 있다) 화면에서 기능만 죽는다 — 글자로 못박는다.
BAND_TEMPLATE = pathlib.Path("templates/admin/naver_workbench.html")
PANE_TEMPLATE = pathlib.Path("templates/admin/partials/naver_workbench_pane.html")
STRIP_TEMPLATE = pathlib.Path("templates/measurement/partials/naver_dispatch_strip.html")
BULK_BUTTON_TEMPLATE = pathlib.Path(
    "templates/partials/shared/naver_bulk_dispatch_button.html")
WORKBENCH_JS = pathlib.Path("static/js/admin/naver-workbench.js")
WORKBENCH_CSS = pathlib.Path("static/css/admin/naver-workbench.css")

#: 표시 시각의 모양. **ISO 가 아니다** — 템플릿이 아무 변환 없이 그대로 찍는다.
AT_SHAPE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")

_SEQ = [0]


def _uid() -> str:
    """테스트 안에서 겹치지 않는 짧은 번호."""
    _SEQ[0] += 1
    return f"{_SEQ[0]:04d}"


@pytest.fixture()
def workbench_on(monkeypatch):
    """워크벤치 게이트를 켠다(전역 on + 코호트 all) — 게이트가 이 기능의 롤백 경로다."""
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_ENABLED", "1")
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_COHORT", "all")
    yield


def _user(*, role: str = "ADMIN") -> User:
    """행위자 1명. ``actor_user_id`` 는 FK 로 흘러가므로 실제 행이 필요하다."""
    user = User(username=f"repay_{role.lower()}_{_uid()}",
                password=generate_password_hash("pw"), role=role, team="CS",
                name=f"{role} 사용자", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, *, role: str = "ADMIN") -> User:
    """세션에 사용자를 심는다(기존 유령 테스트와 같은 모양)."""
    user = _user(role=role)
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _order(*, status: str = "RECEIVED", tel: str) -> Order:
    """유령 후보와 같은 모양의 ERP 주문 1건."""
    order = Order(received_date="2026-09-01", customer_name=f"재결제{_uid()}", phone=tel,
                  erp_phone_digits=tel.replace("-", ""), address="서울 강남구 1 101호",
                  product="붙박이장", status=status, payment_amount=0)
    db_session.add(order)
    db_session.commit()
    return order


def _link(*, order_no: str, amount: int, tel: str, claim: str = "",
          order_id: int | None = None) -> ExternalOrderLink:
    """그 주문에 붙은 네이버 상품주문 1줄(``claim`` 이 비면 살아 있는 결제)."""
    external_id = f"PO-RX-{_uid()}"
    product_order = {
        "productOrderId": external_id, "productName": "붙박이장",
        "totalPaymentAmount": amount,
        "shippingAddress": {"name": "이수취", "tel1": tel,
                            "baseAddress": "서울 강남구 1", "detailedAddress": "101호"},
    }
    if claim:
        product_order["claimStatus"] = claim
    snapshot = {"order": {"orderId": order_no, "ordererTel": tel},
                "productOrder": product_order}
    link = ExternalOrderLink(channel=CHANNEL, external_id=external_id,
                             external_order_no=order_no, raw_snapshot=snapshot,
                             group_key=group_key_text(snapshot),
                             sync_status="LINKED" if order_id else "COLLECTED",
                             relation="NEW", order_id=order_id)
    db_session.add(link)
    db_session.commit()
    return link


def _ghost(*, tel: str, order_no: str, amount: int = 1_000_000,
           claim: str = "CANCEL_DONE", status: str = "RECEIVED") -> Order:
    """네이버 결제가 전부 취소된 살아 있는 주문 1건(띠 모집단에 드는 모양)."""
    order = _order(status=status, tel=tel)
    _link(order_no=order_no, amount=amount, tel=tel, claim=claim, order_id=int(order.id))
    return order


def _row(order_id: int) -> dict:
    """띠에서 그 주문의 행 하나(없으면 실패 — '모집단에 남는다'가 곧 계약이다)."""
    rows = find_ghost_orders(db_session, limit=1000)["rows"]
    picked = [row for row in rows if row["order_id"] == order_id]
    assert len(picked) == 1, f"order {order_id} 의 행이 띠에 하나가 아니다"
    return picked[0]


def _bucket_of(order_id: int) -> dict:
    """그 주문의 링크를 **운영과 같은 셈법**(``_fold_link``)으로 접은 버킷."""
    bucket = _new_bucket()
    rows = (db_session.query(ExternalOrderLink)
            .filter(ExternalOrderLink.order_id == int(order_id)).all())
    for link in rows:
        _fold_link(bucket, snapshot=link.raw_snapshot,
                   order_no=link.external_order_no, link_id=link.id)
    return bucket
