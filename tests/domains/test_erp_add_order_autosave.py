"""ERP add_order 자동저장 엔드포인트 계약.

핵심 불변식:
- 자동저장은 draft를 승격하지 않는다(status='DRAFT', meta.draft=True 유지).
- 내용이 미약하면 서버 draft를 생성하지 않는다(order_id=None).
- GET은 생성하지 않고 복원용 상태만 반환한다.
- discard는 세션 draft를 소프트 삭제한다.
"""

from __future__ import annotations

import json

import pytest
from werkzeug.security import generate_password_hash


def _login(client, app, username: str = "autosave_user") -> None:
    from db import db_session
    from models import User

    with app.app_context():
        if not db_session.query(User).filter_by(username=username).first():
            db_session.add(
                User(
                    username=username,
                    password=generate_password_hash("admin"),
                    role="ADMIN",
                    team="CS",
                    name="Autosave User",
                )
            )
            db_session.commit()
    client.post(
        "/login",
        data={"username": username, "password": "admin"},
        follow_redirects=True,
    )


def _structured(name: str = "", phone: str = "", address: str = "", items=None) -> dict:
    return {
        "entity_type": "order_structured",
        "schema_version": 1,
        "parties": {"customer": {"name": name, "phone": phone}},
        "site": {"address_full": address, "address_main": address, "address_detail": ""},
        "schedule": {},
        "items": items or [],
    }


def _autosave(client, structured, token="tok-1", **extra):
    body = {"draft_token": token, "structured_data": structured}
    body.update(extra)
    return client.post(
        "/api/orders/erp/draft/autosave",
        data=json.dumps(body),
        content_type="application/json",
    )


def test_autosave_empty_does_not_create_draft(client, app) -> None:
    _login(client, app, "autosave_empty_user")
    resp = _autosave(client, _structured(), token="tok-empty")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["order_id"] is None  # 내용 미약 → 서버 draft 미생성


def test_autosave_meaningful_creates_draft_without_promotion(client, app) -> None:
    from db import db_session
    from models import Order

    _login(client, app, "autosave_meaningful_user")
    resp = _autosave(
        client,
        _structured(name="고명옥", phone="010-1234-5678", address="서울시 강남구"),
        token="tok-meaningful",
        received_date="2026-06-30",
        notes="현장 메모",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    order_id = data["order_id"]
    assert order_id

    with app.app_context():
        order = db_session.query(Order).filter_by(id=order_id).one()
        # 승격 금지: draft 상태 그대로.
        assert order.status == "DRAFT"
        assert (order.structured_data or {}).get("meta", {}).get("draft") is True
        assert order.structured_data["parties"]["customer"]["name"] == "고명옥"
        assert order.notes == "현장 메모"


def test_autosave_repeated_reuses_same_draft(client, app) -> None:
    from db import db_session
    from models import Order

    _login(client, app, "autosave_reuse_user")
    first = _autosave(client, _structured(name="첫입력", phone="010-1"), token="tok-reuse")
    second = _autosave(
        client, _structured(name="첫입력 수정", phone="010-1", address="대전"), token="tok-reuse"
    )
    id1 = first.get_json()["order_id"]
    id2 = second.get_json()["order_id"]
    assert id1 and id1 == id2  # 세션 draft 재사용 → 행 폭증 없음

    with app.app_context():
        order = db_session.query(Order).filter_by(id=id1).one()
        # 같은 행을 제자리 갱신: 최신 입력이 반영된다.
        assert order.structured_data["parties"]["customer"]["name"] == "첫입력 수정"
        assert order.structured_data["site"]["address_full"] == "대전"


def test_get_draft_empty_when_none(client, app) -> None:
    _login(client, app, "autosave_get_empty_user")
    resp = client.get("/api/orders/erp/draft?draft_token=tok-none")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["draft"] is None


def test_get_draft_reports_content_for_restore(client, app) -> None:
    _login(client, app, "autosave_get_user")
    _autosave(
        client,
        _structured(name="복원대상", phone="010-9999-0000", address="부산"),
        token="tok-restore",
    )
    resp = client.get("/api/orders/erp/draft?draft_token=tok-restore")
    data = resp.get_json()
    assert data["draft"] is not None
    assert data["draft"]["has_content"] is True
    assert data["draft"]["order_id"]


def test_discard_soft_deletes_draft(client, app) -> None:
    from db import db_session
    from models import Order

    _login(client, app, "autosave_discard_user")
    created = _autosave(
        client, _structured(name="버릴주문", phone="010-5", address="인천"), token="tok-discard"
    )
    order_id = created.get_json()["order_id"]

    discard = client.post(
        "/api/orders/erp/draft/discard",
        data=json.dumps({"draft_token": "tok-discard"}),
        content_type="application/json",
    )
    assert discard.status_code == 200
    assert discard.get_json()["success"] is True

    with app.app_context():
        order = db_session.query(Order).filter_by(id=order_id).one()
        assert order.status == "DELETED"
        assert order.deleted_at

    # 세션 분리 → GET은 다시 None.
    after = client.get("/api/orders/erp/draft?draft_token=tok-discard")
    assert after.get_json()["draft"] is None
