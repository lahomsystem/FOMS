"""Wave 4.1: ERP shell fragment conditional GET (ETag / 304).

The shell fragment body is large (dashboard ~640KB / production ~550KB
decompressed) and the client heartbeat re-fetches it every 50s/240s. When the
tab body is unchanged the server must answer **304 (empty body)** so the client
only extends its warm-cache TTL instead of re-downloading the payload.

These tests fix:
- fragment responses carry a strong ETag,
- ETag is byte-stable across renders of the same content (strategy precondition),
- a matching ``If-None-Match`` collapses to 304 + empty body (fragment header kept),
- a stale/mismatched ``If-None-Match`` returns the full 200 body + fresh ETag,
- a real data mutation yields a new ETag (200 for a client holding the old one).
"""

from __future__ import annotations

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User


@pytest.fixture(autouse=True)
def _reset_dashboard_cache_runtime():
    from foms.services.common import dashboard_cache as dc

    dc.reset_dashboard_cache_runtime_for_tests()
    yield
    dc.reset_dashboard_cache_runtime_for_tests()


def _login_erp_admin(client):
    user = User(
        username="wave41_cond_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="Wave41 Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _fragment(client, path="/erp/dashboard", extra_headers=None):
    headers = {"X-FOMS-ERP-SHELL": "1"}
    if extra_headers:
        headers.update(extra_headers)
    return client.get(f"{path}?view=fragment", headers=headers)


def test_fragment_response_has_etag(client, monkeypatch):
    """Every shell fragment response advertises a strong ETag for revalidation."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("FOMS_DASHBOARD_MICRO_CACHE_ENABLED", "1")
    _login_erp_admin(client)

    resp = _fragment(client)
    assert resp.status_code == 200
    assert resp.headers.get("X-FOMS-ERP-FRAGMENT") == "1"
    etag = resp.headers.get("ETag")
    assert etag, "fragment must expose an ETag"
    # Strong etag (not weak) so the client can echo it verbatim as If-None-Match.
    assert not etag.startswith("W/"), etag


def test_fragment_etag_byte_stable_across_renders(client, monkeypatch):
    """Byte-stability gate as a test: same content → identical ETag (else 304 never hits)."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("FOMS_DASHBOARD_MICRO_CACHE_ENABLED", "1")
    _login_erp_admin(client)

    for path in ("/erp/dashboard", "/erp/production/dashboard", "/erp/shipment"):
        r1 = _fragment(client, path)
        r2 = _fragment(client, path)
        assert r1.status_code == 200 and r2.status_code == 200, path
        assert r1.data == r2.data, f"fragment body not byte-stable: {path}"
        assert r1.headers.get("ETag") == r2.headers.get("ETag"), path
        assert r1.headers.get("ETag"), path


def test_fragment_if_none_match_returns_304_empty_body(client, monkeypatch):
    """Same session, 2nd request with matching If-None-Match → 304 + empty body."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("FOMS_DASHBOARD_MICRO_CACHE_ENABLED", "1")
    _login_erp_admin(client)

    first = _fragment(client)
    etag = first.headers.get("ETag")
    assert first.status_code == 200 and etag

    second = _fragment(client, extra_headers={"If-None-Match": etag})
    assert second.status_code == 304
    assert second.data == b"", "304 must carry an empty body (no 640KB re-send)"
    # ETag echoed; fragment header survives make_conditional so the client contract holds.
    assert second.headers.get("ETag") == etag
    assert second.headers.get("X-FOMS-ERP-FRAGMENT") == "1"


def test_fragment_stale_if_none_match_returns_200(client, monkeypatch):
    """Mismatched If-None-Match (client holds an old/foreign etag) → full 200 + fresh ETag."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("FOMS_DASHBOARD_MICRO_CACHE_ENABLED", "1")
    _login_erp_admin(client)

    resp = _fragment(client, extra_headers={"If-None-Match": '"stale-does-not-match"'})
    assert resp.status_code == 200
    assert resp.data, "mismatch must return the full body"
    assert resp.headers.get("ETag")
    assert resp.headers.get("X-FOMS-ERP-FRAGMENT") == "1"


def test_fragment_new_etag_after_data_change(client, monkeypatch):
    """A real order mutation changes the body → new ETag, so a client's old etag → 200."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("FOMS_DASHBOARD_MICRO_CACHE_ENABLED", "1")
    from foms.services.common import dashboard_cache as dc

    _login_erp_admin(client)

    before = _fragment(client)
    etag_before = before.headers.get("ETag")
    assert before.status_code == 200 and etag_before

    order = Order(
        received_date="2026-01-01",
        customer_name="WAVE41_MUTATION",
        phone="01000000000",
        address="Addr",
        product="P",
        is_erp_order=True,
        structured_data={"workflow": {"stage": "RECEIVED"}},
    )
    db_session.add(order)
    db_session.commit()
    dc.reset_dashboard_cache_runtime_for_tests()

    after = _fragment(client, extra_headers={"If-None-Match": etag_before})
    assert after.status_code == 200, "changed content must not 304 against the old etag"
    etag_after = after.headers.get("ETag")
    assert etag_after and etag_after != etag_before


def test_fragment_304_on_compressed_path_with_suffixed_etag(client, monkeypatch):
    """프로덕션 경로 회귀 방어: 압축 응답에서의 304.

    실브라우저는 Accept-Encoding 을 보내고, Flask-Compress 는 압축한 200 의 강한
    ETag 를 ``"abc"`` → ``"abc:br"`` 처럼 재작성한 뒤 ``COMPRESS_EVALUATE_CONDITIONAL_REQUEST``
    (app_factory 에서 명시 고정)로 조건부 평가를 재실행한다. 즉 프로덕션 304 는
    Flask-Compress 재평가로 성립하므로, 접미사 붙은 ETag 를 에코했을 때 304 가
    나오는지 검증한다. 이 테스트가 깨지면 하트비트가 소리 없이 매번 전체 페이로드를
    다시 받는 퇴화(영구 200)가 시작된 것이다.
    """
    _login_erp_admin(client)
    first = _fragment(client, extra_headers={"Accept-Encoding": "gzip, br"})
    assert first.status_code == 200
    etag = first.headers.get("ETag")
    assert etag, "compressed fragment must still carry an ETag"
    enc = first.headers.get("Content-Encoding")
    if enc:
        assert etag.rstrip('"').endswith(enc) or ":" in etag, (
            "Flask-Compress must suffix the strong etag on compressed responses"
        )

    second = _fragment(
        client,
        extra_headers={"Accept-Encoding": "gzip, br", "If-None-Match": etag},
    )
    assert second.status_code == 304, "suffixed etag echo must 304 on the compressed path"
    assert second.get_data() == b""
