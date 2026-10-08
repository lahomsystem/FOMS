"""PARTNER-02: 협력사 화면 · 협력사 관리 · 고객 메시지 차단 계약.

스펙 docs/specs/2026-10-08-partner-portal_SPEC.md §5 · §6 · §10 (2단계).
각 차단 테스트에는 같은 조건의 우리 주문(음성 대조군)을 함께 둔다.
"""
from __future__ import annotations

import io
import itertools

import pytest

import foms.api.partner as partner_api
from db import db_session
from foms.services import kakao_alimtalk as ka
from foms.services import order_share as osvc
from foms.services.order_attachment_permissions import can_delete_order_attachment
from models import Order, OrderAssignment, OrderAttachment, PartnerOrg, User

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


# --------------------------------------------------------------------------
# 주문 등록
# --------------------------------------------------------------------------
def test_partner_order_lands_in_measure_owned_by_cs_with_our_sales_owner(app, world):
    resp = _create(app, world["partner_a"])
    body = resp.get_json()
    assert resp.status_code == 200 and body["success"] is True, body
    order = db_session.get(Order, body["data"]["order_id"])
    sd = order.structured_data
    assert order.partner_org_id == world["org_a"]
    assert sd["source"] == "PARTNER"
    assert sd["parties"]["orderer"]["name"] == "가나가구"
    assert order.erp_stage_code == "MEASURE" and order.status == "MEASURE"
    assert order.erp_owner_team_code == "CS"
    assert order.measurement_completed is True
    # 우리 실측 일정표에 섞이지 않게 실측일은 schedule 에 넣지 않는다.
    assert not (sd.get("schedule") or {}).get("measurement")
    assert sd["partner_intake"]["measured_on"] == "2026-10-07"
    assert sd["partner_intake"]["submitted_by_name"] == "가나 직원"
    # 영업 담당은 협력사가 아니라 우리 직원이다.
    owners = db_session.query(OrderAssignment).filter(OrderAssignment.order_id == order.id).all()
    assert [(a.domain, a.user_id) for a in owners] == [("SALES", world["sales"])]
    quest = next(q for q in sd["quests"] if q.get("stage") == "MEASURE")
    assert quest["owner_team"] == "CS"


def test_partner_order_rejected_without_our_owner(app, world):
    org = db_session.get(PartnerOrg, world["org_a"])
    org.owner_user_id = None
    db_session.commit()
    resp = _create(app, world["partner_a"])
    assert resp.status_code == 400
    assert db_session.query(Order).count() == 0


def test_partner_order_requires_fields(app, world):
    resp = _create(app, world["partner_a"], {**_PAYLOAD, "items": [{"product_name": ""}]})
    assert resp.status_code == 400 and "품목" in resp.get_json()["error"]


def test_staff_cannot_use_partner_api_or_pages(app, world):
    client = _client(app, db_session.get(User, world["staff"]))
    assert client.post("/api/partner/orders", json=_PAYLOAD).status_code == 403
    assert client.get("/partner").status_code == 403


# --------------------------------------------------------------------------
# 목록 · 상세 범위
# --------------------------------------------------------------------------
def test_partner_sees_only_own_orders(app, world):
    own = _create(app, world["partner_a"]).get_json()["data"]["order_id"]
    other = _create(app, world["partner_b"], {**_PAYLOAD, "customer_name": "다른고객"}).get_json()["data"]["order_id"]
    client = _client(app, db_session.get(User, world["partner_a"]))
    html = client.get("/partner").get_data(as_text=True)
    assert "홍길동" in html and "다른고객" not in html
    assert client.get(f"/partner/orders/{own}").status_code == 200
    assert client.get(f"/partner/orders/{other}").status_code == 404


# --------------------------------------------------------------------------
# 파일 올리기
# --------------------------------------------------------------------------
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


def test_partner_upload_goes_to_partner_folders(app, world, fake_storage):
    order_id = _create(app, world["partner_a"]).get_json()["data"]["order_id"]
    client = _client(app, db_session.get(User, world["partner_a"]))
    assert _upload(client, order_id, "site.jpg", "photo").status_code == 200
    assert _upload(client, order_id, "draft.pdf", "draft").status_code == 200
    rows = db_session.query(OrderAttachment).filter(OrderAttachment.order_id == order_id).order_by(OrderAttachment.id).all()
    assert [(r.category, r.storage_key.split("/")[2]) for r in rows] == [
        ("measurement", "partner_measurement"), ("drawing", "partner_draft"),
    ]
    assert _upload(client, order_id, "bad.exe", "draft").status_code == 400
    assert _upload(client, order_id, "x.pdf", "photo").status_code == 400  # 사진 칸에 pdf


def test_partner_cannot_upload_to_other_or_started_orders(app, world, fake_storage):
    other = _create(app, world["partner_b"]).get_json()["data"]["order_id"]
    own = _create(app, world["partner_a"]).get_json()["data"]["order_id"]
    client = _client(app, db_session.get(User, world["partner_a"]))
    assert _upload(client, other, "a.jpg", "photo").status_code == 404
    order = db_session.get(Order, own)
    order.erp_stage_code = "DRAWING"
    db_session.commit()
    assert _upload(client, own, "a.jpg", "photo").status_code == 409
    assert fake_storage.calls == []


def test_partner_originals_only_admin_can_delete(app, world):
    order = Order(received_date="2026-10-08", customer_name="c", phone="0", address="a", product="p")
    db_session.add(order)
    db_session.commit()
    # 둘 다 같은 직원이 올린 것으로 둔다 — 올린 사람 규칙보다 원본 보존이 먼저인지 본다.
    original = OrderAttachment(order_id=order.id, filename="d.pdf", file_type="file", category="drawing",
                               file_size=1, storage_key=f"orders/{order.id}/partner_draft/d.pdf",
                               user_id=world["staff"])
    ours = OrderAttachment(order_id=order.id, filename="o.jpg", file_type="image", category="measurement",
                           file_size=1, storage_key=f"orders/{order.id}/attachments/o.jpg",
                           user_id=world["staff"])
    db_session.add_all([original, ours])
    db_session.commit()
    staff = db_session.get(User, world["staff"])
    admin = db_session.get(User, world["admin"])
    assert can_delete_order_attachment(staff, order, original) is False
    assert can_delete_order_attachment(admin, order, original) is True
    assert can_delete_order_attachment(staff, order, ours) is True  # 대조군: 올린 사람은 우리 첨부를 지운다


# --------------------------------------------------------------------------
# 고객 메시지 차단
# --------------------------------------------------------------------------
def test_alimtalk_eligibility_blocks_partner_orders_only(app, world):
    partner_order = db_session.get(Order, _create(app, world["partner_a"]).get_json()["data"]["order_id"])
    assert ka._ineligible_reason(partner_order, partner_order.structured_data) == ka.PARTNER_ORDER_REASON
    assert ka.draft_ineligible_reason({"source": "PARTNER"}) == ka.PARTNER_ORDER_REASON
    ours = Order(received_date="2026-10-08", customer_name="c", phone="0", address="a", product="p",
                 structured_data={"parties": {"orderer": {"name": "하우드"}}})
    db_session.add(ours)
    db_session.commit()
    assert ka._ineligible_reason(ours, ours.structured_data) != ka.PARTNER_ORDER_REASON
    assert ka.PARTNER_ORDER_REASON not in ka._RETRYABLE_SEND_ERRORS


@pytest.mark.parametrize("path", ["send-sms", "send-alimtalk"])
def test_share_sends_refuse_partner_orders(app, world, path, monkeypatch):
    sent = []
    monkeypatch.setattr(ka, "_solapi_send", lambda **k: sent.append(k) or "X")
    monkeypatch.setattr(ka, "_solapi_send_text", lambda **k: sent.append(k) or "X")
    order_id = _create(app, world["partner_a"]).get_json()["data"]["order_id"]
    row, token = osvc.create_share_token(db_session, order_id, "drawing")
    db_session.commit()
    client = _client(app, db_session.get(User, world["staff"]))
    resp = client.post(f"/api/share/{path}/{row.id}", json={"token": token})
    assert resp.status_code == 409
    assert resp.get_json()["error"] == ka.PARTNER_ORDER_REASON
    assert sent == []


def test_share_create_hides_customer_phone_for_partner_orders(app, world):
    order_id = _create(app, world["partner_a"]).get_json()["data"]["order_id"]
    client = _client(app, db_session.get(User, world["staff"]))
    resp = client.post(f"/api/share/create/{order_id}", json={"kind": "drawing"})
    data = resp.get_json()["data"]
    assert resp.status_code == 200 and data["url"]
    assert data["to_phone"] == "" and data["sms_text"] == ""


# --------------------------------------------------------------------------
# 협력사 관리 화면
# --------------------------------------------------------------------------
def test_admin_creates_partner_and_account(app, world):
    client = _client(app, db_session.get(User, world["admin"]))
    resp = client.post("/admin/partners", data={"name": "마바가구", "owner_user_id": world["sales"]})
    assert resp.status_code == 302
    org_id = db_session.query(PartnerOrg.id).filter(PartnerOrg.name == "마바가구").scalar()
    resp = client.post(f"/admin/partners/{org_id}/users",
                       data={"username": "maba1", "name": "마바", "password": "Strong-pass-2026!"})
    assert resp.status_code == 302
    user = db_session.query(User).filter(User.username == "maba1").one()
    assert user.role == "PARTNER" and user.partner_org_id == org_id and user.team is None
    page = client.get("/admin/partners").get_data(as_text=True)
    assert "마바가구" in page and "maba1" in page


def test_admin_partner_owner_must_be_sales(app, world):
    client = _client(app, db_session.get(User, world["admin"]))
    client.post("/admin/partners", data={"name": "영업아님", "owner_user_id": world["staff"]})
    assert db_session.query(PartnerOrg).filter(PartnerOrg.name == "영업아님").count() == 0


def test_generic_user_edit_refuses_partner_accounts(app, world):
    client = _client(app, db_session.get(User, world["admin"]))
    resp = client.get(f"/admin/users/edit/{world['partner_a']}")
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/admin/partners")


def test_non_admin_cannot_manage_partners(app, world):
    client = _client(app, db_session.get(User, world["staff"]))
    client.post("/admin/partners", data={"name": "몰래", "owner_user_id": world["sales"]})
    assert db_session.query(PartnerOrg).filter(PartnerOrg.name == "몰래").count() == 0


# --------------------------------------------------------------------------
# 직원 화면 표식
# --------------------------------------------------------------------------
def test_staff_list_marks_partner_orders_only(app, world):
    _create(app, world["partner_a"])
    ours = Order(received_date="2026-10-08", customer_name="우리고객", phone="010-0000-0000", address="a",
                 product="p", structured_data={"parties": {"orderer": {"name": "하우드"}}})
    db_session.add(ours)
    db_session.commit()
    client = _client(app, db_session.get(User, world["staff"]))
    html = client.get("/").get_data(as_text=True)
    assert "우리고객" in html and "홍길동" in html
    assert html.count('class="foms-partner-mark"') == 1
    assert "협력사 · 가나가구" in html
