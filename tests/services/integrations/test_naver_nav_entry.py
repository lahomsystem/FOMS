"""NAVER-INGEST-01 잔여: 관리자 메뉴 진입구 계약 (SQLite 레인).

화면을 만들어도 메뉴에 링크가 없으면 사람은 못 찾는다(2026-08-14 실제 신고). 고정하는 계약:

* ADMIN 메뉴에 '네이버 수집'·'수집 확인' 두 링크가 있다.
* 확인 대기가 있으면 '수집 확인' 옆에 건수 뱃지가 뜬다.
* ADMIN 이 아닌 사용자에게는 링크도 뱃지 쿼리도 없다.
"""

from __future__ import annotations

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.integrations.naver_commerce.constants import CHANNEL
from foms.services.integrations.naver_commerce.triage_count import (
    get_triage_pending_count,
    reset_triage_count_cache_for_tests,
)
from models import ExternalOrderLink, User

TRIAGE_PATH = "/admin/naver-ingest/triage"
INGEST_PATH = "/admin/naver-ingest"


@pytest.fixture(autouse=True)
def _reset_cache():
    reset_triage_count_cache_for_tests()
    yield
    reset_triage_count_cache_for_tests()


def _login(client, *, username: str, role: str) -> User:
    user = User(username=username, password=generate_password_hash("pw"), role=role,
                team="CS", name=f"{role} 사용자", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _link(external_id: str, *, reviewed: bool = False, status: str = "LINKED") -> ExternalOrderLink:
    from foms.services.datetime_kst import now_utc_naive

    link = ExternalOrderLink(channel=CHANNEL, external_id=external_id, sync_status=status,
                             reviewed_at=now_utc_naive() if reviewed else None)
    db_session.add(link)
    db_session.commit()
    return link


def test_admin_menu_exposes_both_naver_entries(client):
    """ADMIN 은 메뉴에서 두 화면으로 갈 수 있다."""
    _login(client, username="nav_admin", role="ADMIN")

    html = client.get("/erp/dashboard").get_data(as_text=True)

    assert INGEST_PATH in html, "'네이버 수집' 링크가 메뉴에 없다"
    assert TRIAGE_PATH in html, "'수집 확인'(트리아지) 링크가 메뉴에 없다"


def test_pending_badge_shows_the_queue_size(client):
    """확인 대기 건수가 메뉴 뱃지로 보인다."""
    _login(client, username="nav_admin_badge", role="ADMIN")
    _link("PO-N-1")
    _link("PO-N-2")
    _link("PO-N-3", reviewed=True)      # 확인 완료 — 제외
    _link("PO-N-4", status="FAILED")    # 실패 — 제외

    html = client.get("/erp/dashboard").get_data(as_text=True)

    assert TRIAGE_PATH in html
    assert '<span class="badge bg-danger ms-2">2</span>' in html


def test_non_admin_sees_no_entry(client):
    """STAFF 에게는 관리자 진입구가 없다."""
    _login(client, username="nav_staff", role="STAFF")
    _link("PO-N-5")

    html = client.get("/erp/dashboard").get_data(as_text=True)

    assert TRIAGE_PATH not in html
    assert INGEST_PATH not in html


def test_count_is_cached_so_nav_does_not_query_every_render(app):
    """nav 는 모든 페이지에 있다 — 30초 캐시가 실제로 재조회를 막는다."""
    _link("PO-N-6")
    first = get_triage_pending_count(db_session)
    _link("PO-N-7")
    second = get_triage_pending_count(db_session)

    assert first == 1
    assert second == 1, "캐시 유효 구간에서 재조회하면 안 된다"

    reset_triage_count_cache_for_tests()
    assert get_triage_pending_count(db_session) == 2


def test_broken_db_does_not_break_the_page(app):
    """뱃지는 부가 정보 — 조회가 깨져도 0 으로 넘어간다(페이지 사망 금지)."""
    from foms.services.integrations.naver_commerce.triage_count import (
        compute_triage_pending_count,
    )

    class _BrokenSession:
        def query(self, *args, **kwargs):
            from sqlalchemy.exc import OperationalError

            raise OperationalError("SELECT 1", {}, Exception("boom"))

    assert compute_triage_pending_count(_BrokenSession()) == 0
