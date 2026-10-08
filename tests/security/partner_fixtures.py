"""협력사 화면 테스트 공용 준비물(PARTNER-02·03) — test_partner_portal*.py 가 같이 쓴다."""
from __future__ import annotations

import io
import itertools

import pytest

import foms.api.partner as partner_api
from db import db_session
from models import Order, PartnerOrg, User

_counter = itertools.count(1)


def _user(*, role="STAFF", team="CS", org=None, name=None, is_active=True) -> User:
    n = next(_counter)
    user = User(username=f"pp-{n}", password="x", role=role, team=team, name=name or f"user-{n}",
                partner_org_id=org.id if org else None, is_active=is_active)
    db_session.add(user)
    db_session.commit()
    return user


def _client(app, user: User | None):
    client = app.test_client()
    if user is not None:
        with client.session_transaction() as sess:
            sess["user_id"] = user.id
    return client


@pytest.fixture
def world(app):
    sales = _user(team="SALES", name="영업김")
    org_a = PartnerOrg(name="가나가구", owner_user_id=sales.id)
    org_b = PartnerOrg(name="다라가구", owner_user_id=sales.id)
    db_session.add_all([org_a, org_b])
    db_session.commit()
    return {
        "sales": sales.id,
        "org_a": org_a.id,
        "org_b": org_b.id,
        "partner_a": _user(role="PARTNER", team=None, org=org_a, name="가나 직원").id,
        "partner_b": _user(role="PARTNER", team=None, org=org_b).id,
        "staff": _user().id,
        "admin": _user(role="ADMIN", team=None).id,
    }


_PAYLOAD = {
    "customer_name": "홍길동",
    "customer_phone": "010-1234-5678",
    "address": "서울시 어딘가 1",
    "measured_on": "2026-10-07",
    "memo": "현관 좁음",
    "items": [{"product_name": "붙박이장", "width": "2400", "depth": "600", "height": "2300", "quantity": "1"}],
}


def _create(app, partner_id, payload=None):
    client = _client(app, db_session.get(User, partner_id))
    return client.post("/api/partner/orders", json=payload or _PAYLOAD)


class _FakeStorage:
    storage_type = "r2"

    def __init__(self):
        self.calls = []

    def upload_file(self, file, filename, folder):
        self.calls.append(folder)
        return {"success": True, "key": f"{folder}/20261008_abc_{filename}"}

    def get_file_type(self, filename):
        return "image" if filename.endswith(".jpg") else "file"


@pytest.fixture
def fake_storage(monkeypatch):
    storage = _FakeStorage()
    monkeypatch.setattr(partner_api, "get_storage", lambda: storage)
    monkeypatch.setattr(partner_api, "schedule_order_attachment_thumbnail_generation", lambda *a, **k: None)
    return storage


def _upload(client, order_id, filename, kind):
    return client.post(
        f"/api/partner/orders/{order_id}/files",
        data={"kind": kind, "file": (io.BytesIO(b"x" * 10), filename)},
        content_type="multipart/form-data",
    )


class _LogoStorage:
    storage_type = "r2"

    def __init__(self):
        self.files = {}

    def upload_file(self, file, filename, folder):
        key = f"{folder}/20261008_x_{filename}"
        self.files[key] = file.read()
        return {"success": True, "key": key}

    def read_file_bytes(self, key):
        return self.files.get(key)


def _to_confirm(order_id, *, drawing_status="CONFIRMED"):
    from sqlalchemy.orm.attributes import flag_modified

    order = db_session.get(Order, order_id)
    sd = dict(order.structured_data)
    sd["workflow"] = {"stage": "CONFIRM"}
    sd["drawing_status"] = drawing_status
    sd["drawing_current_files"] = [{"key": f"orders/{order_id}/drawing/final.pdf", "filename": "final.pdf"}]
    order.structured_data = sd
    flag_modified(order, "structured_data")
    order.erp_stage_code = "CONFIRM"
    order.status = "CONFIRM"
    db_session.commit()


def _to_stage(order_id, stage):
    from sqlalchemy.orm.attributes import flag_modified

    order = db_session.get(Order, order_id)
    sd = dict(order.structured_data)
    sd["workflow"] = {"stage": stage}
    order.structured_data = sd
    flag_modified(order, "structured_data")
    order.erp_stage_code = stage
    order.status = stage
    db_session.commit()


@pytest.fixture
def logo_storage(monkeypatch):
    import foms.web.admin.partners as admin_partners

    storage = _LogoStorage()
    monkeypatch.setattr(admin_partners, "get_storage", lambda: storage)
    monkeypatch.setattr(partner_api, "get_storage", lambda: storage)
    return storage


@pytest.fixture
def quiet_push(monkeypatch):
    monkeypatch.setattr(partner_api, "enqueue_push_for_notification", lambda *a, **k: None)
