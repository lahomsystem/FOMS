"""SESSION-COOKIE-01: 세션 쿠키를 덮어써서 방금 쓴 값을 지우지 않는다.

배경(2026-09-09 운영 사고): permanent 세션 + ``SESSION_REFRESH_EACH_REQUEST`` 조합에서
Flask 는 세션을 고치지 않은 응답에도 ``Set-Cookie`` 를 다시 썼다. 그 값은 그 요청이
시작될 때 로드한 스냅샷이라, 탭마다 도는 폴링(알림 배지)이 나중에 응답하며 페이지가
방금 심은 세션 값(CSRF seed)을 지웠고, 그 페이지의 모든 저장이 403 이 됐다.
"""

import re
import time

from werkzeug.security import generate_password_hash

from db import db_session
from models import User

_COOKIE = "session_staging"


def _login(client, *, username="session-stability-user"):
    """활성 사용자 1명을 만들고 permanent 로그인 세션을 심는다."""
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role="STAFF",
        team="CS",
        name=f"{username}-name",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    uid = user.id
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["username"] = username
        sess["role"] = "STAFF"
        sess.permanent = True
        sess["last_seen_touch_ts"] = time.time()  # last-seen 터치 창 안 = 세션 쓰기 없음
    return uid


def _set_cookie_headers(resp):
    return [h for h in resp.headers.getlist("Set-Cookie") if h.startswith(f"{_COOKIE}=")]


def test_poll_without_session_write_sends_no_set_cookie(client, app):
    """세션을 고치지 않은 폴링 응답은 쿠키를 다시 쓰지 않는다(덮어쓰기 원천 제거)."""
    _login(client)

    resp = client.get("/erp/api/notifications/badge")

    assert resp.status_code == 200
    assert _set_cookie_headers(resp) == []


def test_session_write_still_reissues_cookie_with_expiry(client, app):
    """세션을 실제로 고친 응답은 만료 시각과 함께 쿠키를 재발급한다(슬라이딩 유지)."""
    _login(client)
    with client.session_transaction() as sess:
        sess["last_seen_touch_ts"] = 0  # 터치 창 만료 → last-seen 이 세션을 고친다

    resp = client.get("/erp/api/notifications/badge")

    headers = _set_cookie_headers(resp)
    assert len(headers) == 1, resp.headers
    assert "Expires=" in headers[0]


def test_permanent_flag_is_not_rewritten_every_request(client, app):
    """이미 permanent 인 세션에 다시 대입해 modified 로 만들지 않는다(사고의 방아쇠)."""
    _login(client)

    first = client.get("/erp/api/notifications/badge")
    second = client.get("/erp/api/notifications/badge")

    assert _set_cookie_headers(first) == []
    assert _set_cookie_headers(second) == []


def test_session_value_survives_concurrent_poll(client, app):
    """페이지가 심은 세션 값이 동시 폴링 응답에 지워지지 않는다(사고 재현 시나리오)."""
    uid = _login(client)
    serializer = app.session_interface.get_signing_serializer(app)

    with client.session_transaction() as sess:
        sess["probe_value"] = "keep-me"
    live_cookie = client.get_cookie(_COOKIE).value

    # 이전 스냅샷(probe_value 없음)을 든 폴링 요청이 나중에 응답한다.
    stale = app.test_client()
    with stale.session_transaction() as sess:
        sess["user_id"] = uid
        sess.permanent = True
        sess["last_seen_touch_ts"] = time.time()
    poll = stale.get("/erp/api/notifications/badge")

    assert _set_cookie_headers(poll) == []  # 덮어쓸 쿠키 자체를 안 보낸다
    assert serializer.loads(live_cookie, max_age=10**9)["probe_value"] == "keep-me"


def test_cookie_name_pattern_is_the_session_cookie(client, app):
    """헬퍼가 보는 쿠키 이름이 실제 세션 쿠키와 같다(테스트 자체의 음성 대조군)."""
    _login(client)
    with client.session_transaction() as sess:
        sess["last_seen_touch_ts"] = 0

    resp = client.get("/erp/api/notifications/badge")

    raw = resp.headers.getlist("Set-Cookie")
    assert raw and re.match(rf"{_COOKIE}=", raw[0]), raw
