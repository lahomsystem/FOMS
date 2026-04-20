from db import db_session
from models import Order, OrderAttachment
from foms.services.channel_security import (
    generate_wam_launch_token,
    generate_wam_session_token,
    generate_wam_short_link_token,
)


def _create_order(**overrides):
    order = Order(
        received_date="2026-03-27",
        customer_name="WAM Customer",
        phone="010-1111-2222",
        address="Seoul Test-gu 123",
        product="Starter Kitchen",
        status="RECEIVED",
        manager_name="Manager Kim",
        structured_data={
            "workflow": {"stage": "DRAWING"},
            "parties": {
                "customer": {"name": "WAM Customer", "phone": "010-1111-2222"},
                "manager": {"name": "Manager Kim"},
            },
            "site": {"address_full": "Seoul Test-gu 123"},
            "items": [{"product_name": "Starter Kitchen"}],
            "schedule": {
                "measurement": {"date": "2026-03-28"},
                "construction": {"date": "2026-04-01"},
            },
        },
        is_erp_order=True,
    )
    for key, value in overrides.items():
        setattr(order, key, value)
    db_session.add(order)
    db_session.commit()
    return order


def _create_attachment(order_id: int, **overrides):
    attachment = OrderAttachment(
        order_id=order_id,
        filename="drawing.png",
        file_type="image",
        category="drawing",
        item_index=None,
        file_size=1024,
        storage_key="wam/test-drawing.png",
        thumbnail_key=None,
    )
    for key, value in overrides.items():
        setattr(attachment, key, value)
    db_session.add(attachment)
    db_session.commit()
    return attachment


def _set_wam_session_cookie(client, order_id: int, *, manager_id: str = "wam_viewer", scopes=None):
    token = generate_wam_session_token(manager_id, order_id, scopes=scopes)
    client.set_cookie("wam_session", token, path="/channel/wam")
    return token


def test_wam_api_missing_token_returns_json(client):
    response = client.get("/channel/wam/api/bootstrap")

    assert response.status_code == 401
    assert response.json["ok"] is False
    assert response.json["error"]["code"] == "missing_session_token"


def test_wam_bootstrap_api_returns_page_vm(client, app):
    with app.app_context():
        order = _create_order()
    _set_wam_session_cookie(client, order.id)

    response = client.get("/channel/wam/api/bootstrap")

    assert response.status_code == 200
    assert response.json["ok"] is True
    assert response.json["page"]["order_id"] == order.id
    assert response.json["page"]["header"]["customer_name"] == "WAM Customer"
    assert response.json["api"]["attachments_url"].endswith("/channel/wam/api/attachments")
    section_keys = [section["key"] for section in response.json["page"]["sections"]]
    assert "people" not in section_keys

    customer_section = next(section for section in response.json["page"]["sections"] if section["key"] == "customer")
    schedule_section = next(section for section in response.json["page"]["sections"] if section["key"] == "schedule")

    assert [row["label"] for row in customer_section["payload"]["columns"][0]["rows"]] == [
        "고객명",
        "연락처",
        "발주처",
    ]
    assert [row["label"] for row in customer_section["payload"]["columns"][1]["rows"]] == [
        "담당 매니저",
        "도면 담당",
        "시공 담당",
        "시공 구분",
    ]
    assert [row["label"] for row in schedule_section["payload"]["rows"]] == [
        "접수일",
        "실측일 / 실측시간",
        "시공일 / 시공시간",
        "AS 방문일",
    ]


def test_wam_attachments_api_returns_grouped_metadata(client, app):
    with app.app_context():
        order = _create_order()
        attachment = _create_attachment(order.id)
    _set_wam_session_cookie(client, order.id)

    response = client.get("/channel/wam/api/attachments")

    assert response.status_code == 200
    assert response.json["ok"] is True
    assert response.json["total_count"] == 1
    group = response.json["groups"][0]
    item = group["items"][0]
    assert group["count"] == 1
    assert item["id"] == attachment.id
    assert f"/channel/wam/api/attachments/{attachment.id}/open" in item["open_url"]


def test_wam_attachment_scope_blocks_cross_order_access(client, app, monkeypatch):
    class DummyStorage:
        def get_download_url(self, key, expires_in=3600, response_content_disposition=None):
            return f"/signed/{key}"

    monkeypatch.setattr("foms.services.channel_wam_attachments.get_storage", lambda: DummyStorage())

    with app.app_context():
        first_order = _create_order(customer_name="First")
        second_order = _create_order(customer_name="Second", phone="010-9999-8888")
        foreign_attachment = _create_attachment(second_order.id, storage_key="wam/foreign.png")
    _set_wam_session_cookie(client, first_order.id)

    response = client.get(f"/channel/wam/api/attachments/{foreign_attachment.id}/open")

    assert response.status_code == 404
    assert response.json["ok"] is False
    assert response.json["error"]["code"] == "attachment_not_found"


def test_wam_attachment_download_scope_blocks_cross_order_access(client, app, monkeypatch):
    class DummyStorage:
        def get_download_url(self, key, expires_in=3600, response_content_disposition=None):
            return f"/signed/{key}"

    monkeypatch.setattr("foms.services.channel_wam_attachments.get_storage", lambda: DummyStorage())

    with app.app_context():
        first_order = _create_order(customer_name="First")
        second_order = _create_order(customer_name="Second", phone="010-9999-8888")
        foreign_attachment = _create_attachment(second_order.id, storage_key="wam/foreign-download.png")
    _set_wam_session_cookie(client, first_order.id)

    response = client.get(f"/channel/wam/api/attachments/{foreign_attachment.id}/download")

    assert response.status_code == 404
    assert response.json["ok"] is False
    assert response.json["error"]["code"] == "attachment_not_found"


def test_wam_attachment_scope_blocks_page_only_session_cookie(client, app):
    with app.app_context():
        order = _create_order()
        _create_attachment(order.id)
    _set_wam_session_cookie(client, order.id, scopes=["page"])

    response = client.get("/channel/wam/api/attachments")

    assert response.status_code == 403
    assert response.json["ok"] is False
    assert response.json["error"]["code"] == "forbidden"


def test_wam_attachment_open_redirects_for_scoped_attachment(client, app, monkeypatch):
    class DummyStorage:
        def get_download_url(self, key, expires_in=3600, response_content_disposition=None):
            return f"/signed/{key}"

    monkeypatch.setattr("foms.services.channel_wam_attachments.get_storage", lambda: DummyStorage())

    with app.app_context():
        order = _create_order()
        attachment = _create_attachment(order.id, storage_key="wam/allowed.png")
    _set_wam_session_cookie(client, order.id)

    response = client.get(f"/channel/wam/api/attachments/{attachment.id}/open", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/signed/wam/allowed.png")


def test_wam_api_uses_session_cookie_after_shortlink_entry(client, app):
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

    html_response = client.get(entry_response.headers["Location"])

    assert html_response.status_code == 200

    api_response = client.get("/channel/wam/api/bootstrap")

    assert api_response.status_code == 200
    assert api_response.json["ok"] is True
    assert api_response.json["page"]["order_id"] == order.id


def test_wam_entry_ticket_is_single_use(client, app):
    with app.app_context():
        order = _create_order()
        token = generate_wam_short_link_token(order.id)

    redirect_response = client.get(f"/w/{token}", follow_redirects=False)
    entry_url = redirect_response.headers["Location"]

    first_entry = client.get(entry_url, follow_redirects=False)
    second_client = app.test_client()
    second_entry = second_client.get(entry_url, follow_redirects=False)

    assert first_entry.status_code == 302
    assert second_entry.status_code == 401


def test_wam_api_requires_session_cookie_instead_of_launch_token(client, app):
    with app.app_context():
        order = _create_order()
        token = generate_wam_launch_token("wam_viewer", order.id)

    response = client.get(f"/channel/wam/api/bootstrap?launch_token={token}")

    assert response.status_code == 401
    assert response.json["ok"] is False


def test_wam_html_requires_entry_or_session_ticket(client, app):
    with app.app_context():
        order = _create_order()
        token = generate_wam_launch_token("wam_viewer", order.id)

    response = client.get(f"/channel/wam/?launch_token={token}")

    assert response.status_code == 401
    assert "entry" in response.get_data(as_text=True).lower()


def test_wam_invalid_session_cookie_returns_401(client):
    client.set_cookie("wam_session", "invalid-token", path="/channel/wam")

    response = client.get("/channel/wam/api/bootstrap")

    assert response.status_code == 401
    assert response.json["ok"] is False
    assert response.json["error"]["code"] == "invalid_session_token"


def test_wam_attachment_routes_work_with_session_cookie_only(client, app, monkeypatch):
    class DummyStorage:
        def get_download_url(self, key, expires_in=3600, response_content_disposition=None):
            return f"/signed/{key}"

    monkeypatch.setattr("foms.services.channel_wam_attachments.get_storage", lambda: DummyStorage())

    with app.app_context():
        order = _create_order()
        attachment = _create_attachment(order.id, storage_key="wam/cookie-only.png")
    _set_wam_session_cookie(client, order.id)

    list_response = client.get("/channel/wam/api/attachments")
    assert list_response.status_code == 200
    assert list_response.json["ok"] is True
    assert list_response.json["total_count"] == 1

    open_response = client.get(
        f"/channel/wam/api/attachments/{attachment.id}/open",
        follow_redirects=False,
    )
    assert open_response.status_code == 302
    assert open_response.headers["Location"].endswith("/signed/wam/cookie-only.png")

    download_response = client.get(
        f"/channel/wam/api/attachments/{attachment.id}/download",
        follow_redirects=False,
    )
    assert download_response.status_code == 302
    assert download_response.headers["Location"].endswith("/signed/wam/cookie-only.png")


def test_wam_v1_fallback_renders_when_v2_flag_off_without_v2_template_lookup(client, app, monkeypatch):
    monkeypatch.setenv("CHANNEL_WAM_V2_ENABLED", "false")
    rendered = {}

    def _fake_render_template(template_name, **context):
        rendered["template_name"] = template_name
        rendered["context"] = context
        return context["summary"]["customer_name"]

    monkeypatch.setattr("foms.api.channel.channel_wam.render_template", _fake_render_template)

    with app.app_context():
        order = _create_order()
    _set_wam_session_cookie(client, order.id)

    response = client.get("/channel/wam/")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert rendered["template_name"] == "channel/wam_index.html"
    assert rendered["context"]["summary"]["address"] == "Seoul Test-gu 123"
    assert body == "WAM Customer"


def test_wam_v1_fallback_hides_attachments_when_disabled(client, app, monkeypatch):
    monkeypatch.setenv("CHANNEL_WAM_V2_ENABLED", "false")
    monkeypatch.setenv("CHANNEL_WAM_ATTACHMENTS_ENABLED", "false")
    rendered = {}

    def _fake_render_template(template_name, **context):
        rendered["template_name"] = template_name
        rendered["context"] = context
        return context["summary"]["customer_name"]

    monkeypatch.setattr("foms.api.channel.channel_wam.render_template", _fake_render_template)

    with app.app_context():
        order = _create_order()
        attachment = _create_attachment(order.id)
        assert attachment.id is not None
    _set_wam_session_cookie(client, order.id)

    response = client.get("/channel/wam/")

    assert response.status_code == 200
    assert rendered["template_name"] == "channel/wam_index.html"
    assert rendered["context"]["attachments"] == []


def test_wam_disabled_gate_blocks_html_and_api(client, app, monkeypatch):
    monkeypatch.setenv("CHANNEL_WAM_ENABLED", "false")

    with app.app_context():
        order = _create_order()
    _set_wam_session_cookie(client, order.id)

    html_response = client.get("/channel/wam/")
    api_response = client.get("/channel/wam/api/bootstrap")

    assert html_response.status_code == 404
    assert api_response.status_code == 404
    assert api_response.json["error"]["code"] == "wam_disabled"


def test_wam_disabled_gate_blocks_shortlink_route(client, app, monkeypatch):
    monkeypatch.setenv("CHANNEL_WAM_ENABLED", "false")

    with app.app_context():
        order = _create_order()
        token = generate_wam_short_link_token(order.id)

    response = client.get(f"/w/{token}")

    assert response.status_code == 404


def test_wam_attachments_disabled_gate_blocks_attachment_routes(client, app, monkeypatch):
    monkeypatch.setenv("CHANNEL_WAM_ATTACHMENTS_ENABLED", "false")

    with app.app_context():
        order = _create_order()
        attachment = _create_attachment(order.id)
    _set_wam_session_cookie(client, order.id)

    list_response = client.get("/channel/wam/api/attachments")
    open_response = client.get(f"/channel/wam/api/attachments/{attachment.id}/open")

    assert list_response.status_code == 404
    assert list_response.json["error"]["code"] == "attachments_disabled"
    assert open_response.status_code == 404
    assert open_response.json["error"]["code"] == "attachments_disabled"


def test_wam_invalid_manager_binding_is_rejected(client, app):
    with app.app_context():
        order = _create_order()
    _set_wam_session_cookie(client, order.id, manager_id="unknown-manager")

    response = client.get("/channel/wam/")

    assert response.status_code == 403
    assert "binding" in response.get_data(as_text=True).lower()


def test_wam_shortlink_binding_missing_is_rejected(client, app):
    with app.app_context():
        order = _create_order()
        token = generate_wam_short_link_token(order.id, manager_id="unknown-manager")

    response = client.get(f"/w/{token}")

    assert response.status_code == 403
    assert "binding" in response.get_data(as_text=True).lower()


def test_wam_telemetry_endpoint_logs_when_enabled(client, app, monkeypatch, caplog):
    monkeypatch.setenv("CHANNEL_WAM_TELEMETRY_ENABLED", "true")

    with app.app_context():
        order = _create_order()
    _set_wam_session_cookie(client, order.id)

    with caplog.at_level("INFO"):
        response = client.post(
            "/channel/wam/api/telemetry",
            json={
                "event_name": "wam_page_opened",
                "page_state": "ready",
                "section_count": 6,
                "attachment_count": 1,
                "latency_ms": 123,
            },
        )

    assert response.status_code == 204
    assert "wam_telemetry" in caplog.text
