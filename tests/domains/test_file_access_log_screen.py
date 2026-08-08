"""AUDIT-LOG T12: 파일 열람 기록 화면(``/admin/file-access-logs``) 계약 테스트.

스펙: ``docs/specs/2026-08-05-system-audit-logging-design.md`` §4 T6(기록) — 조회 화면은
그 기록을 SQL 없이 읽게 하는 후속 작업이다.

고정하는 계약:

1. **권한** — ADMIN 만 본다(비-ADMIN 은 공유 ``role_required`` 리다이렉트).
2. **필터** — 열람자·행위·기간(KST)·주문번호·파일 키가 실제로 행을 줄인다.
   특히 기간은 **한국 날짜**로 물어야 한다(naive=UTC 저장 규약 ↔ KST 입력).
3. **주문 필터의 접두 오탐 금지** — 주문 12 조회가 주문 123 행을 끌고 오지 않는다.
4. **페이지네이션** — 50행 초과 시 2페이지가 나오고 링크가 필터를 유지한다.
5. **XSS** — User-Agent·파일 키에 스크립트가 저장돼 있어도 실행 가능한 형태로 나가지 않는다.

기록은 실제 writer(:func:`foms.services.audit_writer.record_file_access`)로 만든다 —
화면 필터와 writer 의 ``additional_data`` 인코딩이 어긋나면 그 자리에서 red 가 된다.
"""

from __future__ import annotations

import datetime
import itertools

import pytest

from db import db_session
from foms.services import audit_writer
from models import AccessLog, User

_counter = itertools.count(1)
_UA = "Mozilla/5.0 (FOMS-T12-Screen)"
_IP = "203.0.113.11"
_PATH = "/admin/file-access-logs"


@pytest.fixture(autouse=True)
def _audit_isolation():
    """dedupe 캐시는 프로세스 전역이다 — 테스트마다 비워 격리한다."""
    audit_writer.reset_dedupe_cache()
    yield
    audit_writer.reset_dedupe_cache()


def _make_user(role: str = "ADMIN") -> int:
    n = next(_counter)
    user = User(
        username=f"t12-screen-{n}", password="x", role=role,
        name=f"열람자{n}", is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user.id


def _login(client, user_id: int) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def _record(
    action: str,
    *,
    storage_key: str,
    user_id: int | None = None,
    order_id: int | None = None,
    user_agent: str = _UA,
) -> None:
    """writer 를 그대로 태워 access_logs 1건을 남긴다(인코딩 계약 동시 검증)."""
    audit_writer.record_file_access(
        action,
        storage_key=storage_key,
        user_id=user_id,
        ip=_IP,
        user_agent=user_agent,
        order_id=order_id,
    )


def _stamp_last_row(timestamp: datetime.datetime) -> None:
    """마지막 기록 행의 시각을 지정 UTC naive 값으로 바꾼다(기간 필터 검증용)."""
    db_session.expire_all()
    row = db_session.query(AccessLog).order_by(AccessLog.id.desc()).first()
    row.timestamp = timestamp
    db_session.commit()


# --------------------------------------------------------------------------
# 1. 권한
# --------------------------------------------------------------------------
def test_screen_requires_admin_role(app):
    """비-ADMIN 은 화면을 볼 수 없다(공유 role_required 리다이렉트)."""
    with app.app_context():
        staff_id = _make_user(role="STAFF")
        client = app.test_client()
        _login(client, staff_id)

        resp = client.get(_PATH, follow_redirects=False)

    assert resp.status_code == 302
    assert "/admin/file-access-logs" not in (resp.headers.get("Location") or "")


def test_screen_renders_for_admin_with_recorded_row(app):
    """ADMIN 은 200 + 기록된 파일 키·IP·UA·행위가 화면에 보인다."""
    with app.app_context():
        admin_id = _make_user()
        _record("FILE_VIEW", storage_key="orders/4401/attachments/proof.jpg",
                user_id=admin_id, order_id=4401)

        client = app.test_client()
        _login(client, admin_id)
        resp = client.get(_PATH)
        body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert "orders/4401/attachments/proof.jpg" in body
    assert "FILE_VIEW" in body
    assert _IP in body
    assert "FOMS-T12-Screen" in body


# --------------------------------------------------------------------------
# 2. 필터
# --------------------------------------------------------------------------
def test_action_filter_narrows_rows(app):
    """행위 필터가 다른 종류의 행을 제외한다."""
    with app.app_context():
        admin_id = _make_user()
        _record("FILE_VIEW", storage_key="orders/1/attachments/view-only.jpg",
                user_id=admin_id, order_id=1)
        _record("FILE_DOWNLOAD", storage_key="orders/1/attachments/download-only.jpg",
                user_id=admin_id, order_id=1)

        client = app.test_client()
        _login(client, admin_id)
        filtered = client.get(f"{_PATH}?action=FILE_DOWNLOAD").get_data(as_text=True)
        unfiltered = client.get(_PATH).get_data(as_text=True)

    assert "download-only.jpg" in filtered
    assert "view-only.jpg" not in filtered
    # 필터가 진짜 원인임을 고정 — 필터 없으면 둘 다 보인다.
    assert "download-only.jpg" in unfiltered and "view-only.jpg" in unfiltered


def test_user_filter_narrows_rows(app):
    """열람자 필터가 다른 사람의 열람을 제외한다."""
    with app.app_context():
        admin_id = _make_user()
        other_id = _make_user(role="STAFF")
        _record("FILE_VIEW", storage_key="orders/2/attachments/mine.jpg",
                user_id=admin_id, order_id=2)
        _record("FILE_VIEW", storage_key="orders/2/attachments/theirs.jpg",
                user_id=other_id, order_id=2)

        client = app.test_client()
        _login(client, admin_id)
        body = client.get(f"{_PATH}?user_id={other_id}").get_data(as_text=True)

    assert "theirs.jpg" in body
    assert "mine.jpg" not in body


def test_order_filter_does_not_match_prefix_collision(app):
    """주문 12 조회가 주문 123·1234 행을 끌고 오지 않는다(문자열 매칭 오탐 가드)."""
    with app.app_context():
        admin_id = _make_user()
        _record("FILE_VIEW", storage_key="orders/12/attachments/target.jpg",
                user_id=admin_id, order_id=12)
        _record("FILE_VIEW", storage_key="orders/123/attachments/collide.jpg",
                user_id=admin_id, order_id=123)
        _record("FILE_VIEW", storage_key="orders/1234/attachments/collide2.jpg",
                user_id=admin_id, order_id=1234)

        client = app.test_client()
        _login(client, admin_id)
        body = client.get(f"{_PATH}?order_id=12").get_data(as_text=True)

    assert "target.jpg" in body
    assert "collide.jpg" not in body
    assert "collide2.jpg" not in body


def test_order_filter_matches_row_without_suppressed_key(app):
    """억제 카운트가 없는 행(주문 id 가 JSON 끝에 붙는 경우)도 주문 필터에 걸린다."""
    with app.app_context():
        admin_id = _make_user()
        # storage_key 가 없으면 order_id 가 마지막 키가 되어 '}' 로 끝난다 —
        # 구분자 분기(',' / '}') 양쪽을 다 덮는지 고정한다.
        audit_writer.write_access_log_detached(
            "FILE_DOWNLOAD", user_id=admin_id, ip=_IP, user_agent=_UA,
            additional_data={"order_id": 777},
        )

        client = app.test_client()
        _login(client, admin_id)
        body = client.get(f"{_PATH}?order_id=777").get_data(as_text=True)

    assert "777" in body
    assert "열람 기록이 없습니다" not in body


def test_storage_key_search_narrows_rows(app):
    """파일 키 검색이 부분 일치로 행을 줄인다."""
    with app.app_context():
        admin_id = _make_user()
        _record("FILE_VIEW", storage_key="orders/31/attachments/blueprint.pdf",
                user_id=admin_id, order_id=31)
        _record("FILE_VIEW", storage_key="orders/31/attachments/photo.jpg",
                user_id=admin_id, order_id=31)

        client = app.test_client()
        _login(client, admin_id)
        body = client.get(f"{_PATH}?storage_key=blueprint").get_data(as_text=True)

    assert "blueprint.pdf" in body
    assert "photo.jpg" not in body


def test_date_filter_uses_kst_day_boundary(app):
    """기간은 한국 날짜 기준이다 — UTC 15:00 은 다음날 KST 00:00 로 잡힌다."""
    with app.app_context():
        admin_id = _make_user()
        _record("FILE_VIEW", storage_key="orders/41/attachments/kst-midnight.jpg",
                user_id=admin_id, order_id=41)
        # 2026-08-06 15:00 UTC = 2026-08-07 00:00 KST
        _stamp_last_row(datetime.datetime(2026, 8, 6, 15, 0, 0))

        _record("FILE_VIEW", storage_key="orders/41/attachments/previous-day.jpg",
                user_id=admin_id, order_id=41)
        # 2026-08-06 14:59 UTC = 2026-08-06 23:59 KST (전날)
        _stamp_last_row(datetime.datetime(2026, 8, 6, 14, 59, 0))

        client = app.test_client()
        _login(client, admin_id)
        body = client.get(
            f"{_PATH}?date_from=2026-08-07&date_to=2026-08-07"
        ).get_data(as_text=True)

    assert "kst-midnight.jpg" in body
    assert "previous-day.jpg" not in body


def test_date_filter_end_day_includes_whole_day(app):
    """종료일 당일 23:59(KST) 열람도 포함된다(경계 미만 비교)."""
    with app.app_context():
        admin_id = _make_user()
        _record("FILE_VIEW", storage_key="orders/42/attachments/late-night.jpg",
                user_id=admin_id, order_id=42)
        # 2026-08-07 14:59 UTC = 2026-08-07 23:59 KST
        _stamp_last_row(datetime.datetime(2026, 8, 7, 14, 59, 0))

        client = app.test_client()
        _login(client, admin_id)
        body = client.get(f"{_PATH}?date_to=2026-08-07").get_data(as_text=True)

    assert "late-night.jpg" in body


def test_invalid_date_input_is_ignored_not_500(app):
    """형식이 틀린 날짜는 필터 미적용으로 흡수한다(감사 화면이 죽지 않는다)."""
    with app.app_context():
        admin_id = _make_user()
        _record("FILE_VIEW", storage_key="orders/43/attachments/any.jpg",
                user_id=admin_id, order_id=43)

        client = app.test_client()
        _login(client, admin_id)
        resp = client.get(f"{_PATH}?date_from=2026-13-45&date_to=oops")

    assert resp.status_code == 200
    assert "any.jpg" in resp.get_data(as_text=True)


# --------------------------------------------------------------------------
# 3. 페이지네이션
# --------------------------------------------------------------------------
def test_pagination_preserves_filters(app):
    """50행 초과 시 2페이지가 나오고 링크가 필터를 유지한다."""
    with app.app_context():
        admin_id = _make_user()
        for index in range(55):
            _record("FILE_DOWNLOAD",
                    storage_key=f"orders/51/attachments/page-{index:03d}.jpg",
                    user_id=admin_id, order_id=51)

        client = app.test_client()
        _login(client, admin_id)
        first = client.get(f"{_PATH}?action=FILE_DOWNLOAD")
        first_body = first.get_data(as_text=True)
        second = client.get(f"{_PATH}?action=FILE_DOWNLOAD&page=2")
        second_body = second.get_data(as_text=True)

    assert first.status_code == 200 and second.status_code == 200
    assert "page=2" in first_body and "action=FILE_DOWNLOAD" in first_body
    # 최신순 정렬 — 가장 오래된 000 행은 2페이지에 온다.
    assert "page-000.jpg" in second_body
    assert "page-000.jpg" not in first_body


# --------------------------------------------------------------------------
# 4. XSS
# --------------------------------------------------------------------------
def test_user_agent_script_is_escaped(app):
    """User-Agent 는 공격자가 정하는 값이다 — 화면에서 실행 가능한 형태로 나가지 않는다."""
    with app.app_context():
        admin_id = _make_user()
        _record("FILE_VIEW", storage_key="orders/61/attachments/ua.jpg",
                user_id=admin_id, order_id=61,
                user_agent="<script>alert('ua')</script>")

        client = app.test_client()
        _login(client, admin_id)
        body = client.get(_PATH).get_data(as_text=True)

    assert "<script>alert('ua')</script>" not in body
    # 정보는 남되 escape 된 형태여야 한다.
    assert "alert(" in body


def test_storage_key_script_is_escaped(app):
    """파일 키에 스크립트가 섞여 저장돼 있어도 그대로 렌더되지 않는다."""
    with app.app_context():
        admin_id = _make_user()
        _record("FILE_VIEW", storage_key="orders/62/<script>alert('key')</script>.jpg",
                user_id=admin_id, order_id=62)

        client = app.test_client()
        _login(client, admin_id)
        body = client.get(_PATH).get_data(as_text=True)

    assert "<script>alert('key')</script>" not in body
    assert "alert(" in body
