"""FILE-01: 파일 view/download/presigned 권한 계약 테스트 (red→green).

§5.2 FILE-01: presign/view/download route 에 **attachment row + order read scope** 권한을
적용한다. 검증 대상:

* canonical ``orders/{order_id}/...`` key → 소유 order 의 read scope(:func:`user_can_read_order`)
  로 게이트. read scope 있으면 200/302, 없으면 403.
* **raw key 직접 요청 거부**: 임의 object key(비정규 namespace·attachment row 미보유)는
  거부한다(arbitrary R2 object 접근 차단).
* **legacy coverage gate**: 비정규 key 는 OrderAttachment row(storage_key|thumbnail_key)가
  cover 할 때만 허용하고, row 가 없으면 거부한다.
* **draft key ownership**: ``order-drafts/{user_id}/...`` 는 본인(또는 ADMIN/MANAGER)만.
* **미인증 거부**: 세션 없으면 파일이 서빙되지 않는다.
* traversal/타 order escape 는 거부한다.

경계: 다운로드 비즈니스(R2 fetch) 로직은 무변경 — 권한만 검증한다. 업로드 route 무접근.
"""

from __future__ import annotations

import itertools

import pytest

import foms.api.files.routes as file_routes
from db import db_session
from models import Order, OrderAttachment, User

_counter = itertools.count(1)

_R2_HOST = "https://account.r2.cloudflarestorage.com/"


class FakeR2Storage:
    """R2 모드 storage stub — 허용 시 302 redirect(다운로드 비즈니스 무변경)."""

    storage_type = "r2"

    def get_download_url(
        self,
        storage_key: str,
        expires_in: int = 3600,
        response_content_disposition: str | None = None,
    ) -> str:
        return f"{_R2_HOST}{storage_key}?X-Amz-Signature=fresh"


@pytest.fixture
def r2_storage(monkeypatch):
    monkeypatch.setattr(file_routes, "get_storage", lambda: FakeR2Storage())
    return FakeR2Storage()


def _make_user(*, role: str = "STAFF", is_active: bool = True) -> User:
    n = next(_counter)
    user = User(
        username=f"file-auth-user-{n}",
        password="x",
        role=role,
        name=f"user-{n}",
        is_active=is_active,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _make_order() -> Order:
    order = Order(
        received_date="2026-03-26",
        customer_name="c",
        phone="010-0000-0000",
        address="addr",
        product="p",
        status="RECEIVED",
    )
    db_session.add(order)
    db_session.commit()
    return order


def _make_attachment(order_id: int, storage_key: str, thumbnail_key: str | None = None) -> OrderAttachment:
    att = OrderAttachment(
        order_id=order_id,
        filename="old.jpg",
        file_type="image",
        category="measurement",
        file_size=1,
        storage_key=storage_key,
        thumbnail_key=thumbnail_key,
    )
    db_session.add(att)
    db_session.commit()
    return att


def _client(app, user: User | None):
    client = app.test_client()
    if user is not None:
        with client.session_transaction() as sess:
            sess["user_id"] = user.id
    return client


def _is_r2_redirect(resp) -> bool:
    return resp.status_code == 302 and resp.headers.get("Location", "").startswith(_R2_HOST)


# --------------------------------------------------------------------------
# canonical order key + read scope
# --------------------------------------------------------------------------
def test_canonical_key_with_read_scope_serves_file(app, r2_storage):
    with app.app_context():
        user = _make_user()
        order = _make_order()
        client = _client(app, user)
        key = f"orders/{order.id}/attachments/photo.jpg"

        assert _is_r2_redirect(client.get(f"/api/files/view/{key}", follow_redirects=False))
        assert _is_r2_redirect(client.get(f"/api/files/download/{key}", follow_redirects=False))

        pres = client.get(f"/api/files/presigned-urls/{key}")
        assert pres.status_code == 200
        assert pres.get_json()["view_url"].startswith(_R2_HOST)


def test_read_scope_denied_blocks_canonical_key(app, r2_storage, monkeypatch):
    """order read scope 가 없으면 canonical key 도 거부(read scope 게이트 증명)."""
    monkeypatch.setattr(file_routes, "user_can_read_order", lambda u, o=None: False)
    with app.app_context():
        user = _make_user()
        order = _make_order()
        client = _client(app, user)
        key = f"orders/{order.id}/attachments/photo.jpg"

        for path in (f"/api/files/view/{key}", f"/api/files/download/{key}",
                     f"/api/files/presigned-urls/{key}"):
            resp = client.get(path, follow_redirects=False)
            assert not _is_r2_redirect(resp)
            assert resp.status_code == 403


# --------------------------------------------------------------------------
# raw key 직접 요청 거부 + traversal
# --------------------------------------------------------------------------
def test_raw_arbitrary_key_denied(app, r2_storage):
    """attachment row 없는 임의 object key(비정규 namespace) 는 거부."""
    with app.app_context():
        user = _make_user()
        client = _client(app, user)
        for key in ("secret/backups/dump.sql", "some-bucket/private.txt", "config/keys.env"):
            resp = client.get(f"/api/files/view/{key}", follow_redirects=False)
            assert not _is_r2_redirect(resp)
            assert resp.status_code == 403


def test_traversal_key_denied(app, r2_storage):
    """타 order escape/traversal 은 파일을 서빙하지 않는다."""
    with app.app_context():
        user = _make_user()
        order = _make_order()
        client = _client(app, user)
        resp = client.get(
            f"/api/files/view/orders/{order.id}/../999/secret.jpg", follow_redirects=False
        )
        assert not _is_r2_redirect(resp)
        assert resp.status_code >= 400


# --------------------------------------------------------------------------
# legacy coverage gate
# --------------------------------------------------------------------------
def test_legacy_key_covered_by_attachment_row_allowed(app, r2_storage):
    """비정규 legacy key 라도 OrderAttachment row 가 cover 하면 read scope 로 허용."""
    with app.app_context():
        user = _make_user()
        order = _make_order()
        legacy_key = "legacy_uploads/2019/old_photo.jpg"
        _make_attachment(order.id, legacy_key)
        client = _client(app, user)
        assert _is_r2_redirect(client.get(f"/api/files/view/{legacy_key}", follow_redirects=False))


def test_legacy_key_thumbnail_covered_allowed(app, r2_storage):
    """thumbnail_key 로도 coverage 인정."""
    with app.app_context():
        user = _make_user()
        order = _make_order()
        thumb_key = "legacy_uploads/2019/old_thumb.jpg"
        _make_attachment(order.id, "legacy_uploads/2019/old_photo.jpg", thumbnail_key=thumb_key)
        client = _client(app, user)
        assert _is_r2_redirect(client.get(f"/api/files/view/{thumb_key}", follow_redirects=False))


def test_legacy_key_uncovered_denied(app, r2_storage):
    """attachment row 가 없는 비정규 legacy key 는 거부(coverage gate)."""
    with app.app_context():
        user = _make_user()
        _make_order()
        client = _client(app, user)
        resp = client.get("/api/files/view/legacy_uploads/2019/ghost.jpg", follow_redirects=False)
        assert not _is_r2_redirect(resp)
        assert resp.status_code == 403


# --------------------------------------------------------------------------
# draft key ownership
# --------------------------------------------------------------------------
def test_draft_key_owner_allowed(app, r2_storage):
    with app.app_context():
        user = _make_user()
        client = _client(app, user)
        key = f"order-drafts/{user.id}/wiz-abc/photo.jpg"
        assert _is_r2_redirect(client.get(f"/api/files/view/{key}", follow_redirects=False))


def test_draft_key_other_user_denied(app, r2_storage):
    with app.app_context():
        owner = _make_user()
        intruder = _make_user()
        client = _client(app, intruder)
        key = f"order-drafts/{owner.id}/wiz-abc/photo.jpg"
        resp = client.get(f"/api/files/view/{key}", follow_redirects=False)
        assert not _is_r2_redirect(resp)
        assert resp.status_code == 403


# --------------------------------------------------------------------------
# 미인증
# --------------------------------------------------------------------------
def test_unauthenticated_not_served(app, r2_storage):
    with app.app_context():
        order = _make_order()
        client = _client(app, None)
        resp = client.get(
            f"/api/files/view/orders/{order.id}/attachments/photo.jpg", follow_redirects=False
        )
        assert not _is_r2_redirect(resp)
