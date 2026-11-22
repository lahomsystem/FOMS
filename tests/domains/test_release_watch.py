"""STALE-TAB-01: 열어 둔 탭이 새 배포를 알아채게 서버가 지금 릴리스를 알린다(2026-11-22).

2026-11-21 운영: 공장 태블릿이 아침에 연 생산 첫 화면이 뒤에서 멈췄다가 오후에 깨어났는데, 그 사이 나간 배포를
못 받고 옛 HTML · 옛 핀 CSS/JS 를 그대로 보였다. 서버 쪽 계약:

- 문서는 그린 릴리스를 ``<script data-foms-release>`` 로 싣는다(로그인 문서만 — 로그인 화면은 감시 없음).
- HTML 문서 · 셸 조각 응답과 304(하트비트 재검증)에 ``X-Foms-Release`` 머리글. JSON 폴링에는 싣지 않는다.
- ``GET /api/foms/release`` 는 같은 값을 ``{'success', 'data', 'error'}`` · ``no-store`` 로 준다.
- 값 = ``fragment_revalidation.RELEASE_ID``. 출처가 프로세스 uuid(워커마다 다름)면 빈 값 — 탭이 되풀이해 읽지 않게.

브라우저 쪽 판정(언제 새로 읽나 · 되풀이 방지)은 ``test_foms_release_watch_js.py`` 가 node 로 돌린다.
"""

from __future__ import annotations

import re
from unittest.mock import patch

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.auth.freelancer_scope import FREELANCER_ALLOWED_ENDPOINTS
from foms.services.common import fragment_revalidation as fr
from foms.services.common.release_watch import RELEASE_HEADER, public_release_id
from models import User

_SCRIPT_RE = re.compile(r'<script src="[^"]*foms-release-watch\.js\?v=[0-9a-f]+" data-foms-release="([^"]*)" defer>')


@pytest.fixture(autouse=True)
def _reset_dashboard_cache_runtime():
    from foms.services.common import dashboard_cache as dc

    dc.reset_dashboard_cache_runtime_for_tests()
    yield
    dc.reset_dashboard_cache_runtime_for_tests()


@pytest.fixture
def stable_release():
    """배포 env 로 정한 릴리스처럼(워커 간 같은 값) 고정한다."""
    with patch.object(fr, "RELEASE_ID", "relAAAA1111"), patch.object(fr, "RELEASE_ID_SOURCE", "env"):
        yield "relAAAA1111"


def _login(client, username: str = "stale_tab_admin") -> None:
    user = User(username=username, password=generate_password_hash("pw"), role="ADMIN", team="CS",
                name="Stale Tab", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def test_release_endpoint_reports_current_release(client, stable_release):
    resp = client.get("/api/foms/release")
    assert resp.status_code == 200
    assert resp.get_json() == {"success": True, "data": {"release": stable_release}, "error": None}
    assert resp.headers.get(RELEASE_HEADER) == stable_release
    assert resp.headers.get("Cache-Control") == "no-store"


def test_release_endpoint_follows_a_new_deploy(client, stable_release):
    """배포하면 프로세스가 새로 떠 값이 바뀐다 — 같은 서버 코드가 바뀐 값을 그대로 낸다(복사해 둔 값이 없다)."""
    with patch.object(fr, "RELEASE_ID", "relBBBB2222"):
        assert client.get("/api/foms/release").get_json()["data"]["release"] == "relBBBB2222"


def test_process_uuid_release_is_not_advertised(client):
    """워커마다 다른 식별자를 알리면 탭이 워커를 옮길 때마다 새로 읽는다 — 빈 값 · 머리글 없음."""
    with patch.object(fr, "RELEASE_ID", "uuid0001"), patch.object(fr, "RELEASE_ID_SOURCE", fr.RELEASE_SOURCE_PROCESS):
        assert public_release_id() == ""
        resp = client.get("/api/foms/release")
        assert resp.get_json()["data"]["release"] == ""
        assert RELEASE_HEADER not in resp.headers


def test_release_value_has_no_separator_chars():
    """탭 표식이 ``|`` 로 칸을 가른다 — 운영이 심은 FOMS_RELEASE_ID 에 이상한 글자가 있어도 걸러 알린다."""
    with patch.object(fr, "RELEASE_ID", "v1|2 <x>"), patch.object(fr, "RELEASE_ID_SOURCE", "env"):
        assert public_release_id() == "v12x"


def test_release_source_is_stable_in_tests_and_deploys():
    """시험 · 이미지에서는 템플릿 digest 또는 배포 env 가 잡힌다(uuid 최후 수단이 아니다)."""
    assert fr.RELEASE_ID_SOURCE in ("env", "templates")
    assert public_release_id() == fr.RELEASE_ID


def test_release_source_prefers_explicit_env(monkeypatch):
    monkeypatch.setenv("FOMS_RELEASE_ID", "deadbeefcafe0002")
    assert fr._compute_release_id_and_source() == ("deadbeefcafe0002", "env")


def test_full_page_embeds_its_release_and_header(client, stable_release):
    _login(client)
    resp = client.get("/erp/dashboard")
    assert resp.status_code == 200
    assert resp.headers.get(RELEASE_HEADER) == stable_release
    found = _SCRIPT_RE.findall(resp.get_data(as_text=True))
    assert found == [stable_release], "로그인 문서에는 감시 스크립트가 한 번, 그린 릴리스와 함께 실린다"


def test_shell_fragment_and_its_304_carry_release_header(client, monkeypatch, stable_release):
    """하트비트는 대부분 304 다 — 304 는 Content-Type 이 지워져도 머리글이 남아야 셸이 감시에 알린다."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("FOMS_DASHBOARD_MICRO_CACHE_ENABLED", "1")
    _login(client)
    headers = {"X-FOMS-ERP-SHELL": "1"}
    first = client.get("/erp/dashboard?foms_shell=fragment", headers=headers)
    assert first.status_code == 200
    assert first.headers.get("X-FOMS-ERP-FRAGMENT") == "1"
    assert first.headers.get(RELEASE_HEADER) == stable_release
    assert "foms-release-watch.js" not in first.get_data(as_text=True), "조각에는 싣지 않는다(문서에 한 번)"
    etag = first.headers.get("ETag")
    assert etag
    again = client.get("/erp/dashboard?foms_shell=fragment", headers={**headers, "If-None-Match": etag})
    assert again.status_code == 304
    assert again.headers.get(RELEASE_HEADER) == stable_release


def test_login_page_has_no_release_watch(client, stable_release):
    resp = client.get("/login")
    assert resp.status_code == 200
    assert "foms-release-watch.js" not in resp.get_data(as_text=True)


def test_json_polls_do_not_carry_release_header(client, stable_release):
    """머리글은 HTML · 304 에만 — 알림 폴링 같은 JSON 응답마다 붙이지 않는다."""
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert RELEASE_HEADER not in resp.headers


def test_freelancer_tabs_may_ask_release():
    """켜진 프리랜서도 같은 ERP 문서를 쓴다 — 막히면 302 로 대시보드를 통째로 그려 돌려준다."""
    assert "health.foms_release" in FREELANCER_ALLOWED_ENDPOINTS
