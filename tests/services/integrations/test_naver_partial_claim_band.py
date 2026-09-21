"""부분 취소 띠 — 집 하나가 통째로 취소·반품됐는데 살아 있는 집이 남은 주문 (2026-09-21).

유령 띠(``find_ghost_orders``)는 "붙은 링크가 **전부** 취소"만 센다. 그 제외는 의도된
안전장치지만, 추가결제가 붙은 주문에서는 **본품 반품 전체를 화면에서 지웠다** — 운영
#5268(김현정)은 본품 5건이 전부 ``RETURN_REQUEST`` 인데 추가결제 6건이 살아 있어 어느 띠에도
안 떴고, 사용자가 "네이버엔 반품 2건인데 FOMS 엔 1건"으로 보고했다.

여기서 못박는 것 넷:

1. 집 하나가 통째로 취소·반품 + 살아 있는 링크가 남음 → **이 띠에 뜬다**.
2. 같은 주문이 유령 띠에는 **여전히 안 뜬다**(유령 판정은 한 글자도 안 바뀌었다).
3. 확정된(``done``) 부분 취소는 안 센다 — 재결제로 이미 정리된 정상 모양이라 소음이다.
4. 전부 취소된 주문은 이 띠에 **안 뜬다**(유령 띠 몫, 음성 대조군).
"""
import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.integrations.naver_commerce.constants import CHANNEL
from foms.services.integrations.naver_commerce.ghost_orders import (
    find_ghost_orders,
    find_partial_claim_orders,
)
from foms.services.integrations.naver_commerce.mapping import group_key_text
from models import ExternalOrderLink, Order, User

_SEQ = [0]


def _uid() -> str:
    _SEQ[0] += 1
    return f"{_SEQ[0]:04d}"


@pytest.fixture()
def workbench_on(monkeypatch):
    """워크벤치 게이트를 켠다(전역 on + 코호트 all)."""
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_ENABLED", "1")
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_COHORT", "all")
    yield


def _login(client, *, role: str = "ADMIN") -> User:
    user = User(username=f"partial_{role.lower()}_{_uid()}",
                password=generate_password_hash("pw"), role=role, team="CS",
                name=f"{role} 사용자", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _order(*, status: str = "MEASURE", tel: str = "010-7100-0001") -> Order:
    order = Order(received_date="2026-09-11", customer_name=f"부분{_uid()}", phone=tel,
                  erp_phone_digits=tel.replace("-", ""), address="서울 강남구 2 201호",
                  product="붙박이장", status=status, payment_amount=0)
    db_session.add(order)
    db_session.commit()
    return order


def _link(*, order_no: str, amount: int, claim: str = "", order_id: int,
          tel: str = "010-7100-0001", relation: str = "NEW") -> ExternalOrderLink:
    product_order = {
        "productOrderId": f"PO-P-{_uid()}",
        "productName": "붙박이장",
        "totalPaymentAmount": amount,
        "shippingAddress": {"name": "이수취", "tel1": tel,
                            "baseAddress": "서울 강남구 2", "detailedAddress": "201호"},
    }
    if claim:
        product_order["claimStatus"] = claim
    snapshot = {"order": {"orderId": order_no, "ordererTel": tel},
                "productOrder": product_order}
    link = ExternalOrderLink(channel=CHANNEL, external_id=product_order["productOrderId"],
                             external_order_no=order_no, raw_snapshot=snapshot,
                             group_key=group_key_text(snapshot), sync_status="LINKED",
                             relation=relation, order_id=order_id)
    db_session.add(link)
    db_session.commit()
    return link


def _main_returned_with_live_addon(*, tel: str) -> Order:
    """운영 #5268 모양 — 본품 집 전부 반품 요청 + 추가결제 집 살아 있음."""
    order = _order(tel=tel)
    order_id = int(order.id)
    _link(order_no=f"N-MAIN-{_uid()}", amount=497_000, claim="RETURN_REQUEST",
          order_id=order_id, tel=tel)
    _link(order_no=f"N-ADD-{_uid()}", amount=120_000, order_id=order_id, tel=tel,
          relation="ADDON")
    return order


def test_returned_household_with_live_addon_shows_in_the_band(app):
    """본품 집이 통째로 반품 요청인데 추가결제가 살아 있으면 이 띠에 뜬다."""
    order = _main_returned_with_live_addon(tel="010-7100-0002")

    row = next(row for row in find_partial_claim_orders(db_session)["rows"]
               if row["order_id"] == int(order.id))

    assert row["claim_kind"] == "반품"
    assert row["claim_phase"] == "pending"
    assert row["dead_link_count"] == 1
    assert row["alive_link_count"] == 1
    assert row["lead_link_id"]
    # 금액은 **죽은 집**의 것이다 — 살아 있는 추가결제까지 더하면 환불 예정액을 거짓말한다.
    assert row["naver_amount_total"] == 497_000


def test_same_order_still_missing_from_the_ghost_band(app):
    """유령 판정은 한 글자도 안 바뀌었다 — 그 띠는 여전히 '전부 취소'만 센다."""
    order = _main_returned_with_live_addon(tel="010-7100-0003")

    ids = [row["order_id"] for row in find_ghost_orders(db_session)["rows"]]

    assert int(order.id) not in ids


def test_confirmed_partial_cancel_is_not_counted(app):
    """확정된 부분 취소는 안 센다 — 재결제로 이미 정리된 정상 모양이라 소음이다."""
    order = _order(tel="010-7100-0004")
    order_id = int(order.id)
    _link(order_no="N-OLD-1", amount=300_000, claim="CANCEL_DONE", order_id=order_id,
          tel="010-7100-0004")
    _link(order_no="N-NEW-1", amount=330_000, order_id=order_id, tel="010-7100-0004",
          relation="REPAY")

    ids = [row["order_id"] for row in find_partial_claim_orders(db_session)["rows"]]

    assert order_id not in ids


def test_fully_canceled_order_is_not_in_this_band(app):
    """전부 취소는 유령 띠 몫이다 — 같은 주문을 두 띠가 외치지 않는다(음성 대조군)."""
    order = _order(tel="010-7100-0005")
    order_id = int(order.id)
    _link(order_no="N-ALL-1", amount=200_000, claim="RETURN_REQUEST", order_id=order_id,
          tel="010-7100-0005")

    partial_ids = [row["order_id"] for row in find_partial_claim_orders(db_session)["rows"]]
    ghost_ids = [row["order_id"] for row in find_ghost_orders(db_session)["rows"]]

    assert order_id not in partial_ids
    assert order_id in ghost_ids


def test_half_claimed_household_alone_is_not_enough(app):
    """집 안에서 **일부만** 취소된 것은 안 센다 — 통째로 죽은 집이 있어야 한다."""
    order = _order(tel="010-7100-0006")
    order_id = int(order.id)
    _link(order_no="N-HALF-1", amount=100_000, claim="RETURN_REQUEST", order_id=order_id,
          tel="010-7100-0006")
    _link(order_no="N-HALF-1", amount=100_000, order_id=order_id, tel="010-7100-0006")

    ids = [row["order_id"] for row in find_partial_claim_orders(db_session)["rows"]]

    assert order_id not in ids


def test_workbench_work_tab_renders_the_band(app, client, workbench_on):
    """처리 탭이 실제로 띠를 그린다 — 서비스 함수만 맞고 화면이 비면 고친 게 아니다."""
    _login(client)
    order = _main_returned_with_live_addon(tel="010-7100-0007")
    order_id = int(order.id)

    response = client.get("/admin/naver-ingest/triage?tab=work")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "일부만 취소·반품된 주문" in body
    assert f'data-partial-order-id="{order_id}"' in body


def test_history_tab_does_not_render_the_band(app, client, workbench_on):
    """이력 탭은 지난 기록을 보는 자리다 — 할 일 띠를 띄우지 않는다(유령 띠와 같은 규율)."""
    _login(client)
    _main_returned_with_live_addon(tel="010-7100-0008")

    body = client.get("/admin/naver-ingest/triage?tab=all").get_data(as_text=True)

    assert "일부만 취소·반품된 주문" not in body
