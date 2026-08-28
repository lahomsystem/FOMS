"""**거부된 클레임**을 진행 중인 것처럼 말하지 않는다 (R-8, 2026-08-28).

세 화면이 전부 `claim_label` **존재 여부**로 분기했다. `RETURN_REJECT`("반품 거부")면
환불이 **영영 없는데** 도크는 "환불액은 아직 빠지지 않은 금액입니다"라고 말하고, ⚠ 경고
배지를 살아 있는 주문에 붙이고, 목록은 빨강 배지를 단다. `CANCEL_REJECT` 도 같다.

라벨은 사실이라 계속 보여준다 — 바뀌는 것은 **그것을 진행 중 클레임으로 세는 것**뿐이다.
"""

from __future__ import annotations

from foms.services.integrations.naver_commerce.mapping import (
    extract_claim,
    is_money_back_claim,
)


def _claim(status: str, claim_type: str = "") -> dict:
    product_order = {"productOrderId": "PO-R8", "claimStatus": status}
    if claim_type:
        product_order["claimType"] = claim_type
    return extract_claim({"productOrder": product_order})


# ── 술어 ─────────────────────────────────────────────────────────────────────

def test_rejected_claims_are_not_money_back():
    """거부는 돈이 되돌아가지 않는다 — 주문도 결제도 살아 있다."""
    for status in ("CANCEL_REJECT", "RETURN_REJECT", "EXCHANGE_REJECT"):
        assert is_money_back_claim(_claim(status)) is False, status


def test_live_and_finished_money_back_claims_count():
    """요청·처리중·완료는 전부 센다 — 결제액에서 환불이 아직 안 빠졌다는 사실은 같다."""
    for status in ("CANCEL_REQUEST", "CANCELING", "CANCEL_DONE",
                   "RETURN_REQUEST", "COLLECTING", "COLLECT_DONE", "RETURN_DONE"):
        assert is_money_back_claim(_claim(status)) is True, status


def test_exchange_is_not_money_back():
    """교환은 대체품을 받는 것이라 환불 축이 아니다."""
    for status in ("EXCHANGE_REQUEST", "EXCHANGE_DONE"):
        assert is_money_back_claim(_claim(status, "EXCHANGE")) is False, status


def test_unknown_and_empty_never_count():
    """**음성 대조군** — 모르는 상태를 환불 대기로 세지 않는다."""
    for status in ("SOME_NEW_NAVER_STATUS", "PURCHASE_DECISION_HOLDBACK", ""):
        assert is_money_back_claim(_claim(status)) is False, status


# ── 도크 예약금 단서 ─────────────────────────────────────────────────────────

def test_deposit_note_stays_quiet_for_a_rejected_claim():
    """거부 건에 "환불액은 아직 빠지지 않았다"고 말하지 않는다 — 환불이 영영 없다."""
    from foms.services.integrations.naver_commerce.dock import _deposit_note

    note = _deposit_note(has_superseded=False, claim_label="반품 거부",
                         claim_money_back=False)

    assert "환불" not in note
    assert note == ""


def test_deposit_note_still_explains_a_live_cancel():
    """**음성 대조군** — 진짜 취소 건에서는 예전처럼 설명한다."""
    from foms.services.integrations.naver_commerce.dock import _deposit_note

    note = _deposit_note(has_superseded=False, claim_label="취소 요청",
                         claim_money_back=True)

    assert "환불액은 아직 빠지지 않은 금액입니다" in note
    assert "취소 요청" in note


# ── 화면 실물 ────────────────────────────────────────────────────────────────

import pytest  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402

from db import db_session  # noqa: E402
from foms.services.integrations.naver_commerce.constants import CHANNEL  # noqa: E402
from foms.services.integrations.naver_commerce.mapping import group_key_text  # noqa: E402
from models import ExternalOrderLink, User  # noqa: E402

_SEQ = [0]


def _uid() -> str:
    _SEQ[0] += 1
    return f"{_SEQ[0]:03d}"


@pytest.fixture()
def workbench_on(monkeypatch):
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_ENABLED", "1")
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_COHORT", "all")
    yield


def _login(client) -> User:
    user = User(username=f"r8_admin_{_uid()}", password=generate_password_hash("pw"),
                role="ADMIN", team="CS", name="관리자", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _link(status: str) -> ExternalOrderLink:
    external_id = f"PO-R8-{_uid()}"
    order_no = f"N-R8-{_uid()}"
    snapshot = {
        "order": {"orderId": order_no},
        "productOrder": {"productOrderId": external_id, "productName": "붙박이장",
                         "claimStatus": status, "placeOrderStatus": "OK",
                         "shippingAddress": {"name": "이수취", "tel1": "010-4444-5555",
                                             "baseAddress": "서울 강남구 1",
                                             "detailedAddress": "101호"}},
    }
    link = ExternalOrderLink(channel=CHANNEL, external_id=external_id,
                             external_order_no=order_no, raw_snapshot=snapshot,
                             group_key=group_key_text(snapshot), sync_status="COLLECTED",
                             place_order_status="OK")
    db_session.add(link)
    db_session.commit()
    return link


def test_rejected_claim_is_not_painted_as_danger(app, client, workbench_on):
    """거부 배지는 빨강이 아니다 — 사실은 남고 경보만 뗀다."""
    _login(client)
    _link("CANCEL_REJECT")

    body = client.get("/admin/naver-ingest/triage?tab=work").get_data(as_text=True)

    assert 'bg-secondary">취소 거부' in body, "사실이 사라졌다"
    assert 'bg-danger">취소 거부' not in body


def test_a_live_cancel_is_still_painted_as_danger(app, client, workbench_on):
    """**음성 대조군** — 진짜 취소는 예전처럼 빨강이다(경고가 다 빠지면 사고를 놓친다)."""
    _login(client)
    _link("CANCEL_REQUEST")

    body = client.get("/admin/naver-ingest/triage?tab=work").get_data(as_text=True)

    assert 'bg-danger">취소 요청' in body
