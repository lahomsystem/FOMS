from db import db_session
from models import Order, OrderAttachment
from foms.services.channel_security import generate_wam_session_token, generate_wam_short_link_token


def _create_order():
    order = Order(
        received_date="2026-03-27",
        customer_name="ERP Beta",
        phone="000-0000-0000",
        address="-",
        product="ERP Beta",
        status="RECEIVED",
        is_erp_beta=True,
        structured_data={
            "workflow": {"stage": "DRAWING"},
            "parties": {
                "customer": {"name": "Real Customer", "phone": "010-1234-5678"},
                "manager": {"name": "Mango"},
                "orderer": {"name": "오더홈"},
            },
            "site": {"address_full": "Seoul Teheran-ro 123", "address_detail": "11F"},
            "items": [{"product_name": "Kitchen Set", "option": "Premium"}],
            "shipment": {"drawing_manager": "Draft Lee", "construction_workers": ["Team A"]},
            "schedule": {
                "measurement": {"date": "2026-03-28", "time": "오전"},
                "construction": {"date": "2026-04-01"},
            },
        },
    )
    db_session.add(order)
    db_session.commit()
    return order


def _set_wam_session_cookie(client, order_id: int, *, manager_id: str = "wam_viewer", scopes=None):
    token = generate_wam_session_token(manager_id, order_id, scopes=scopes)
    client.set_cookie("wam_session", token, path="/channel/wam")
    return token


def test_channel_wam_html_shell_sets_session_cookie_after_shortlink_entry(client, app):
    with app.app_context():
        order = _create_order()
        token = generate_wam_short_link_token(order.id)

    redirect_response = client.get(f"/w/{token}", follow_redirects=False)
    assert redirect_response.status_code == 302
    assert "/channel/wam/?entry_ticket=" in redirect_response.headers["Location"]

    entry_response = client.get(redirect_response.headers["Location"], follow_redirects=False)
    assert entry_response.status_code == 302
    assert entry_response.headers["Location"].endswith("/channel/wam/")
    assert "wam_session=" in entry_response.headers.get("Set-Cookie", "")

    response = client.get(entry_response.headers["Location"])
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Real Customer" in body
    assert 'data-section-key="customer"' in body
    assert 'data-section-key="people"' not in body
    assert 'wam-split-card' in body
    assert "핵심 요약" in body
    assert "읽기 전용 화면입니다." not in body
    assert "고객과 발주 관련 정보를 확인합니다." not in body
    assert "현장 / 주소" not in body
    assert 'data-open-section="attachments"' in body
    assert "aria-label=\"FOMS 상세 화면 열기\"" in body
    assert "wam-sticky-bar" not in body
    assert "wam-header__primary-action" not in body


def test_channel_wam_bootstrap_api_returns_page_payload(client, app):
    with app.app_context():
        order = _create_order()
    _set_wam_session_cookie(client, order.id)

    response = client.get("/channel/wam/api/bootstrap")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["view_key"] == "order-detail"
    assert payload["page"]["page_state"] == "ready"
    assert payload["page"]["header"]["customer_name"] == "Real Customer"
    assert payload["page"]["summary_strip"]["title"] == "핵심 요약"
    assert payload["api"]["attachments_url"].endswith("/channel/wam/api/attachments")
    assert payload["page"]["order_id"] == order.id
    assert payload["page"]["sticky_action_bar"] is None
    assert "actions" in payload["page"]["header"]
    assert "site" not in [section["key"] for section in payload["page"]["sections"]]


def test_channel_wam_html_renders_attachment_modal_and_clickable_preview(client, app):
    with app.app_context():
        order = _create_order()
        db_session.add(
            OrderAttachment(
                order_id=order.id,
                filename="preview.png",
                file_type="image",
                category="measurement",
                file_size=10,
                storage_key="wam/preview.png",
            )
        )
        db_session.commit()
    _set_wam_session_cookie(client, order.id)

    response = client.get("/channel/wam/")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "wam-attachment-modal" in body
    assert 'data-attachment-open="true"' in body
    assert ">보기<" not in body
    assert "다운로드" in body


def test_channel_wam_attachments_api_groups_payload(client, app):
    with app.app_context():
        order = _create_order()
        db_session.add_all(
            [
                OrderAttachment(
                    order_id=order.id,
                    filename="measure.png",
                    file_type="image",
                    category="measurement",
                    file_size=10,
                    storage_key="wam/measure.png",
                ),
                OrderAttachment(
                    order_id=order.id,
                    filename="draw.pdf",
                    file_type="file",
                    category="drawing",
                    file_size=10,
                    storage_key="wam/draw.pdf",
                ),
            ]
        )
        db_session.commit()
    _set_wam_session_cookie(client, order.id)

    response = client.get("/channel/wam/api/attachments")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    labels = {group["label"] for group in payload["groups"]}
    assert "Measurement" in labels
    assert "Drawing" in labels
    assert payload["groups"][0]["preview"][0]["open_url"]


def test_channel_wam_attachment_scope_blocks_other_order_attachment(client, app):
    with app.app_context():
        order_a = _create_order()
        order_b = _create_order()
        attachment = OrderAttachment(
            order_id=order_b.id,
            filename="secret.png",
            file_type="image",
            category="measurement",
            file_size=10,
            storage_key="wam/secret.png",
        )
        db_session.add(attachment)
        db_session.commit()
    _set_wam_session_cookie(client, order_a.id)

    response = client.get(f"/channel/wam/api/attachments/{attachment.id}/open")
    payload = response.get_json()

    assert response.status_code == 404
    assert payload["ok"] is False
    assert payload["error"]["code"] == "attachment_not_found"
