"""주문 만들기 되돌리기 계약 (2026-11-12 운영 #6098 정광호).

추가결제·재결제를 새 주문으로 잘못 만들었을 때, 휴지통에 먼저 넣지 않아도 같은
``/detach`` 로 링크를 수집 직후로 돌리고 만든 주문을 휴지통으로 보낸다
(:func:`promotion.undo_created_order`). ``test_naver_attach.py`` 가 500줄 래칫에 닿아
따로 둔다 — 도우미는 그 파일 것을 그대로 쓴다.
"""

from __future__ import annotations

import pytest

from db import db_session
from models import Order
from tests.services.integrations.test_naver_attach import (
    _created_order_link,
    _fresh,
    _link,
    _order,
)

# ── 주문 만들기 되돌리기 (2026-11-12 운영 #6098) ─────────────────────────────
# 추가결제·재결제를 새 주문으로 잘못 만들었을 때, 휴지통에 먼저 넣지 않아도 같은
# /detach 로 링크를 수집 직후로 돌리고 만든 주문을 휴지통으로 보낸다.

def _undo(auth_client, link_id: int, body=None):
    return auth_client.post(f"/admin/naver-ingest/{link_id}/detach", json=body or {})


def test_undo_create_releases_links_and_trashes_the_created_order(auth_client):
    made_order_id = _order()
    right_order_id = _order()
    first_id = _created_order_link("PO-UN1", order_no="N-UNDO-CREATE", order_id=made_order_id)
    second_id = _created_order_link("PO-UN2", order_no="N-UNDO-CREATE", order_id=made_order_id)

    response = _undo(auth_client, first_id)
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["data"]["trashed"] is True
    for link_id in (first_id, second_id):
        link = _fresh(link_id)
        assert link.order_id is None
        assert link.relation == "NEW"
        assert link.sync_status == "COLLECTED"
    made = db_session.get(Order, made_order_id)
    assert made.deleted_at, "만든 주문이 휴지통으로 가지 않았다"
    assert "주문 만들기 되돌림" in ((made.structured_data or {}).get("delete") or {}).get("reason", "")
    assert db_session.get(Order, right_order_id).deleted_at is None

    # 그다음 기존 주문에 붙일 수 있어야 이 기능의 끝이다.
    attached = auth_client.post(f"/admin/naver-ingest/{first_id}/attach",
                                json={"order_id": right_order_id, "relation": "REPAY"})
    assert attached.status_code == 200, attached.get_json()
    assert _fresh(second_id).order_id == right_order_id


def test_undo_create_after_receipt_stage_needs_admin_reason(auth_client):
    """접수 이후 단계는 관리자가 사유를 적어야 한다(유령 주문 접기와 같은 문턱)."""
    made_order_id = _order()
    db_session.get(Order, made_order_id).status = "MEASURE"
    db_session.commit()
    link_id = _created_order_link("PO-UNST", order_no="N-UNST", order_id=made_order_id)

    response = _undo(auth_client, link_id)
    assert response.status_code == 400
    assert "사유" in response.get_json()["error"] or "적어" in response.get_json()["error"]
    assert _fresh(link_id).order_id == made_order_id
    assert db_session.get(Order, made_order_id).deleted_at is None

    response = _undo(auth_client, link_id, {"reason": "추가결제를 새 주문으로 잘못 만듦"})
    assert response.status_code == 200, response.get_json()
    assert _fresh(link_id).order_id is None


def test_undo_create_after_receipt_stage_refuses_non_admin(app):
    from foms.services.integrations.naver_commerce.promotion import (
        PromotionError,
        undo_created_order,
    )

    made_order_id = _order()
    db_session.get(Order, made_order_id).status = "MEASURE"
    db_session.commit()
    link_id = _created_order_link("PO-UNNA", order_no="N-UNNA", order_id=made_order_id)

    with pytest.raises(PromotionError, match="관리자만"):
        undo_created_order(db_session, link_id=link_id, actor_user_id=1,
                           is_admin=False, note="사유")
    db_session.rollback()
    assert _fresh(link_id).order_id == made_order_id


def test_undo_create_refuses_when_other_naver_payments_ride_the_order(auth_client):
    """그 주문에 다른 집의 네이버 결제가 붙어 있으면 지우지 않는다 — 그 결제가 미아가 된다."""
    made_order_id = _order()
    link_id = _created_order_link("PO-UNO1", order_no="N-UNO", order_id=made_order_id)
    other_id = _link("PO-UNO2", order_no="N-UNO-OTHER")
    assert auth_client.post(f"/admin/naver-ingest/{other_id}/attach",
                            json={"order_id": made_order_id,
                                  "relation": "ADDON"}).status_code == 200

    response = _undo(auth_client, link_id)
    assert response.status_code == 400
    assert "다른 네이버 결제" in response.get_json()["error"]
    assert _fresh(link_id).order_id == made_order_id
    db_session.expire_all()
    assert db_session.get(Order, made_order_id).deleted_at is None


def test_undo_create_on_an_already_trashed_order_only_releases(auth_client):
    made_order_id = _order()
    link_id = _created_order_link("PO-UNTR", order_no="N-UNTR", order_id=made_order_id)
    db_session.get(Order, made_order_id).deleted_at = "2026-11-11 08:00:00"
    db_session.commit()

    response = _undo(auth_client, link_id)
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["data"]["trashed"] is False
    assert _fresh(link_id).order_id is None


def test_undo_create_refuses_an_order_marked_repay_expected(auth_client):
    """사람이 '재결제 예정' 을 켠 주문은 되돌리기로 지우지 않는다 — 재결제를 기다리는 주문이다."""
    from foms.services.integrations.naver_commerce.ghost_orders import set_repay_expected
    from sqlalchemy.orm.attributes import flag_modified

    made_order_id = _order()
    order = db_session.get(Order, made_order_id)
    set_repay_expected(order, actor_user_id=1, actor_name="시험")
    flag_modified(order, "structured_data")
    db_session.commit()
    link_id = _created_order_link("PO-UNRE", order_no="N-UNRE", order_id=made_order_id)

    response = _undo(auth_client, link_id)
    assert response.status_code == 400
    assert "재결제 예정" in response.get_json()["error"]
    assert _fresh(link_id).order_id == made_order_id
