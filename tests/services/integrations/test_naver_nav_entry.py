"""NAVER-INGEST-01 잔여 + T14-A: 네이버 진입구 계약 (SQLite 레인).

화면을 만들어도 메뉴에 링크가 없으면 사람은 못 찾는다(2026-08-14 실제 신고). 고정하는 계약:

* 주 메뉴에 '네이버 주문' 탭이 있고, 확인 대기가 있으면 건수 뱃지가 뜬다(전 직원).
* 주문 목록('/')에는 대기>0 일 때만 인박스 스트립이 뜬다.
* 뱃지·큐 카운트는 COLLECTED(주문 만들기 대기)와 LINKED(미확인)를 함께 센다.
* 수집 운영 화면('/admin/naver-ingest')·ADMIN 드롭다운 진입구는 관리자 전용으로 남는다.
* VIEWER 는 트리아지 화면 접근 불가, 뱃지 쿼리도 내지 않는다.
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


def test_pending_badge_counts_collected_and_linked(client):
    """뱃지는 큐 정의 그대로 COLLECTED+LINKED(미확인)를 센다."""
    _login(client, username="nav_admin_badge", role="ADMIN")
    _link("PO-N-1")
    _link("PO-N-2")
    _link("PO-N-2C", status="COLLECTED")  # 주문 만들기 대기 — 포함 (T14-A 수정)
    _link("PO-N-3", reviewed=True)      # 확인 완료 — 제외
    _link("PO-N-4", status="FAILED")    # 실패 — 제외

    html = client.get("/erp/dashboard").get_data(as_text=True)

    assert TRIAGE_PATH in html
    # ADMIN 드롭다운 뱃지 + 주 메뉴 탭 뱃지 둘 다 같은 수를 보여준다.
    assert '<span class="badge bg-danger ms-2">3</span>' in html
    assert '<span class="badge rounded-pill bg-danger">3</span>' in html


def test_staff_sees_tab_but_not_admin_ops_entry(client):
    """STAFF 도 '네이버 주문' 탭·뱃지는 본다(T14-A 개방). 수집 운영 화면 링크는 없다."""
    _login(client, username="nav_staff", role="STAFF")
    _link("PO-N-5")

    html = client.get("/erp/dashboard").get_data(as_text=True)

    assert TRIAGE_PATH in html, "'네이버 주문' 탭이 STAFF 에게 없다"
    assert '<span class="badge rounded-pill bg-danger">1</span>' in html
    # 운영 화면은 관리자 전용 — 정확한 href 로만 검사(트리아지 URL 이 이 경로를 포함하므로).
    assert f'href="{INGEST_PATH}"' not in html


def test_staff_can_open_triage_page(client):
    """STAFF 는 트리아지 화면을 연다(T14-A 권한 개방)."""
    _login(client, username="nav_staff_triage", role="STAFF")
    _link("PO-N-5T")

    response = client.get(TRIAGE_PATH)

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "수집 주문 확인" in html
    # 관리자 전용 운영 화면 링크는 STAFF 화면에 없다.
    assert f'href="{INGEST_PATH}"' not in html


def test_viewer_cannot_open_triage_and_gets_no_badge(client):
    """VIEWER 는 화면 접근 불가 — 메뉴 뱃지도 계산하지 않는다."""
    _login(client, username="nav_viewer", role="VIEWER")
    _link("PO-N-5V")

    assert client.get(TRIAGE_PATH).status_code in (302, 403)

    html = client.get("/erp/dashboard").get_data(as_text=True)
    assert '<span class="badge rounded-pill bg-danger">' not in html


def test_order_list_shows_inbox_strip_only_when_pending(client):
    """주문 목록('/') 인박스 스트립 — 대기>0 이면 뜨고, 0 이면 없다."""
    _login(client, username="nav_staff_strip", role="STAFF")

    html = client.get("/").get_data(as_text=True)
    # CSS 정의는 항상 실려 있으므로 실제 렌더된 div 로만 판정한다.
    assert '<div class="naver-inbox-strip"' not in html, "대기 0 인데 스트립이 떴다"

    _link("PO-N-6S", status="COLLECTED")
    reset_triage_count_cache_for_tests()

    html = client.get("/").get_data(as_text=True)
    assert '<div class="naver-inbox-strip"' in html
    assert "네이버 새 수집" in html
    assert TRIAGE_PATH in html


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
