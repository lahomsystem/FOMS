"""RESP-HEADERS-01: 앱 전역 표준 응답 헤더 계약(2026-10-19).

설계서 ``docs/specs/2026-10-19-response-headers_SPEC.md``. 앞단이 Railway 엣지뿐이라
(Cloudflare 없음) 앱이 직접 붙인다. 등록은 ``foms/platform/http.py`` after_request 한 곳,
정책 값은 ``foms/platform/security_headers.py``.

잠그는 것:
1. 대표 화면(HTML)·JSON API·404·정적 아닌 다운로드(정산 CSV)에 헤더 6종 중 5종이 붙는다
   (HSTS 는 배포 환경 전용).
2. 이미 정한 값은 덮어쓰지 않는다 — 공유 화면 ``no-referrer`` 유지, CSV ``nosniff`` 중복 없음.
3. 채널톡 데스크 iframe 경로(``/channel/wam``)는 채널톡 출처를 허용하고 XFO 를 붙이지 않는다.
   이름이 비슷한 다른 경로는 같은 출처만(음성 대조군).
4. 비배포 환경(테스트)엔 HSTS 가 없다. 배포 기준은 app_factory 의
   ``is_production or is_railway`` 와 같다.
"""

from __future__ import annotations

import inspect

import pytest
from werkzeug.wrappers import Response

import foms.api.share as share_routes
from db import db_session
from foms.platform import app_factory
from foms.platform.security_headers import (
    FRAME_ANCESTORS_CHANNEL,
    FRAME_ANCESTORS_DEFAULT,
    HSTS_VALUE,
    PERMISSIONS_POLICY,
    REFERRER_POLICY,
    apply_security_headers,
    is_channel_frame_path,
)
from foms.services import order_share as osvc
from tests.domains.test_auth_finance import _login, _make_user
from tests.domains.test_order_share_view import FakeR2Storage, _mk_order

CSV_EXPORT_URL = "/api/settlement/channel/export.csv?kind=settle_case"


def _assert_default_headers(resp) -> None:
    """같은 출처 기본 정책 5종이 정확히 1개씩 붙었는지 확인한다."""
    headers = resp.headers
    assert headers.getlist("X-Content-Type-Options") == ["nosniff"], headers
    assert headers.getlist("Referrer-Policy") == [REFERRER_POLICY], headers
    assert headers.getlist("X-Frame-Options") == ["SAMEORIGIN"], headers
    assert headers.getlist("Content-Security-Policy") == [FRAME_ANCESTORS_DEFAULT], headers
    assert headers.getlist("Permissions-Policy") == [PERMISSIONS_POLICY], headers


# --------------------------------------------------------------------------
# 1. 대표 응답 — 화면·JSON·오류·다운로드
# --------------------------------------------------------------------------
def test_login_page_gets_default_headers(client, app):
    resp = client.get("/login")

    assert resp.status_code == 200
    assert resp.mimetype == "text/html"
    _assert_default_headers(resp)


def test_json_api_gets_default_headers(client, app):
    resp = client.get("/healthz")

    assert resp.mimetype == "application/json"
    _assert_default_headers(resp)


def test_authenticated_json_api_gets_default_headers(client, app):
    _login(client, _make_user(role="ADMIN"))

    resp = client.get("/erp/api/notifications/badge")

    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.mimetype == "application/json"
    _assert_default_headers(resp)


def test_not_found_page_gets_default_headers(client, app):
    resp = client.get("/definitely-not-a-route-resp-headers")

    assert resp.status_code == 404
    _assert_default_headers(resp)


def test_csv_download_keeps_single_nosniff_and_gets_frame_policy(client, app):
    """라우트가 직접 붙인 nosniff 는 그대로 1개, 나머지는 전역 기본값이 채운다."""
    _login(client, _make_user(role="ADMIN"))

    resp = client.get(CSV_EXPORT_URL)

    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.mimetype == "text/csv"
    assert resp.headers["Content-Disposition"].startswith("attachment;")
    _assert_default_headers(resp)


# --------------------------------------------------------------------------
# 2. 덮어쓰지 않기 — 공유 화면
# --------------------------------------------------------------------------
def test_share_view_keeps_no_referrer(client, app, monkeypatch):
    stub = FakeR2Storage()
    monkeypatch.setattr(share_routes, "get_storage", lambda: stub)
    order = _mk_order()
    _row, token = osvc.create_share_token(db_session, order.id, "drawing")
    db_session.commit()

    resp = client.get(f"/s/{token}")

    assert resp.status_code == 200
    assert resp.headers.getlist("Referrer-Policy") == ["no-referrer"]
    assert resp.headers["X-Robots-Tag"] == "noindex, nofollow"
    assert resp.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert resp.headers["Content-Security-Policy"] == FRAME_ANCESTORS_DEFAULT


def test_share_view_error_keeps_no_referrer(client, app):
    resp = client.get("/s/definitely-not-a-token")

    assert resp.status_code == 404
    assert resp.headers.getlist("Referrer-Policy") == ["no-referrer"]
    assert resp.headers["X-Content-Type-Options"] == "nosniff"


# --------------------------------------------------------------------------
# 3. 채널톡 데스크 iframe 경로
# --------------------------------------------------------------------------
@pytest.mark.parametrize("path", ["/channel/wam/", "/channel/wam/api/bootstrap"])
def test_channel_wam_allows_channel_desk_frame(client, app, path):
    resp = client.get(path)

    assert resp.status_code == 410  # 퇴역 안내가 데스크 iframe 안에서 보여야 한다
    assert resp.headers.getlist("Content-Security-Policy") == [FRAME_ANCESTORS_CHANNEL]
    assert "https://desk.channel.io" in resp.headers["Content-Security-Policy"]
    assert "X-Frame-Options" not in resp.headers
    assert resp.headers["X-Content-Type-Options"] == "nosniff"


def test_channel_short_link_is_same_origin_only(client, app):
    """/w/ 짧은 링크는 새 탭으로 열리는 모바일 ERP 리다이렉트라 채널 예외가 아니다."""
    resp = client.get("/w/not-a-token", follow_redirects=False)

    assert resp.status_code == 401
    _assert_default_headers(resp)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/channel/wam", True),
        ("/channel/wam/", True),
        ("/channel/wam/api/telemetry", True),
        ("/channel/wamx", False),
        ("/channel/functions", False),
        ("/erp/orders/1/mobile", False),
        ("/w/token", False),
        ("/", False),
    ],
)
def test_channel_frame_path_predicate(path, expected):
    assert is_channel_frame_path(path) is expected


# --------------------------------------------------------------------------
# 4. HSTS — 배포 환경 전용
# --------------------------------------------------------------------------
def test_non_deployed_app_has_no_hsts(client, app):
    resp = client.get("/login")

    assert "Strict-Transport-Security" not in resp.headers


def test_deployed_flag_adds_hsts_without_subdomains_or_preload():
    resp = apply_security_headers(Response("ok"), "/login", hsts=True)

    assert resp.headers.getlist("Strict-Transport-Security") == [HSTS_VALUE]
    assert "includeSubDomains" not in HSTS_VALUE
    assert "preload" not in HSTS_VALUE


def test_existing_headers_are_not_overwritten():
    preset = Response("ok")
    preset.headers["Referrer-Policy"] = "no-referrer"
    preset.headers["X-Frame-Options"] = "DENY"
    preset.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
    preset.headers["Strict-Transport-Security"] = "max-age=60"

    resp = apply_security_headers(preset, "/login", hsts=True)

    assert resp.headers.getlist("Referrer-Policy") == ["no-referrer"]
    assert resp.headers.getlist("X-Frame-Options") == ["DENY"]
    assert resp.headers.getlist("Content-Security-Policy") == ["frame-ancestors 'none'"]
    assert resp.headers.getlist("Strict-Transport-Security") == ["max-age=60"]


def test_hsts_uses_same_deployed_criterion_as_secure_cookie():
    """HSTS 기준이 SESSION_COOKIE_SECURE 기준(is_production or is_railway)과 갈라지지 않는다."""
    src = inspect.getsource(app_factory)

    assert "deployed=(is_production or is_railway)" in src
    assert "if is_production or is_railway:\n        app.config[\"SESSION_COOKIE_SECURE\"] = True" in src


# --------------------------------------------------------------------------
# 5. Permissions-Policy — 쓰는 기능은 self, 안 쓰는 기능만 막는다
# --------------------------------------------------------------------------
def test_permissions_policy_allows_used_features_and_blocks_unused():
    directives = dict(item.split("=", 1) for item in PERMISSIONS_POLICY.split(", "))

    for feature in ("camera", "microphone", "geolocation"):
        assert directives[feature] == "(self)", feature
    for feature in ("payment", "usb", "serial", "hid", "midi", "accelerometer", "gyroscope",
                    "magnetometer", "display-capture"):
        assert directives[feature] == "()", feature
    # 코드가 쓰는 기능(전체 화면·공유·클립보드)은 목록에 넣지 않아 브라우저 기본값(self)을 쓴다.
    for feature in ("fullscreen", "web-share", "clipboard-write"):
        assert feature not in directives, feature
