"""NAVER-INGEST-01 잔여 + T14-A + v3 §6: 네이버 진입구 계약 (SQLite 레인).

화면을 만들어도 메뉴에 링크가 없으면 사람은 못 찾는다(2026-08-14 실제 신고). 고정하는 계약:

* 주 메뉴에 '네이버 수집' 탭이 있고, 확인 대기가 있으면 건수 뱃지가 뜬다(전 직원).
* **이름 하나·진입구 하나**(v3 계약 §6). nav 에서 '네이버 수집'으로 가는 길은 트리아지
  하나뿐이다 — 이름 4개(네이버 주문/네이버 수집/수집 확인/수집 상태)·진입구 4개가
  "왔다 갔다 헷갈린다"의 원인이었다.
* 옛 수집 운영 화면('/admin/naver-ingest')은 사라지지 않는다 — 게이트 OFF ADMIN 은
  트리아지 화면 안의 링크로, 게이트 ON 이면 리다이렉트로 같은 자료에 닿는다.
* 주문 목록('/')에는 대기>0 일 때만 인박스 스트립이 뜬다.
* 뱃지 모집단 = **그 사람이 링크를 눌렀을 때 볼 목록**. 게이트 OFF 는 확인 대기 큐
  (COLLECTED+LINKED), 게이트 ON 은 워크벤치 처리 탭(``_work_groups``).
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
from foms.services.integrations.naver_commerce.mapping import group_key_text
from models import ExternalOrderLink, User

TRIAGE_PATH = "/admin/naver-ingest/triage"
INGEST_PATH = "/admin/naver-ingest"


@pytest.fixture(autouse=True)
def _reset_cache():
    reset_triage_count_cache_for_tests()
    yield
    reset_triage_count_cache_for_tests()


@pytest.fixture()
def workbench_on(monkeypatch):
    """워크벤치 v3 게이트를 켠다(전역 on + 코호트 all)."""
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_ENABLED", "1")
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_COHORT", "all")
    yield


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


def _link(external_id: str, *, reviewed: bool = False, status: str = "LINKED",
          group_key: str | None = None) -> ExternalOrderLink:
    from foms.services.datetime_kst import now_utc_naive

    link = ExternalOrderLink(channel=CHANNEL, external_id=external_id, sync_status=status,
                             group_key=group_key,
                             reviewed_at=now_utc_naive() if reviewed else None)
    db_session.add(link)
    db_session.commit()
    return link


def test_nav_has_exactly_one_naver_entry_named_collect(client):
    """nav 진입구는 하나다 — 이름은 '네이버 수집', 목적지는 트리아지(v3 계약 §6).

    옛 이름('네이버 주문'·'수집 확인')과 옛 진입구(수집 운영 화면 드롭다운 항목)가
    같은 화면에 함께 있으면 사람이 어디로 가야 할지 매번 고른다.
    """
    _login(client, username="nav_admin", role="ADMIN")

    html = client.get("/erp/dashboard").get_data(as_text=True)

    assert f'href="{TRIAGE_PATH}"' in html, "'네이버 수집'(트리아지) 링크가 메뉴에 없다"
    assert html.count(f'href="{TRIAGE_PATH}"') == 2, (
        "진입구는 주 메뉴 탭 + ADMIN 드롭다운 두 자리에 각각 하나씩 — 그 이상이면 중복"
    )
    assert f'href="{INGEST_PATH}"' not in html, (
        "옛 수집 운영 화면 진입구는 nav 에서 뺐다(게이트 ON 이면 트리아지로 리다이렉트라 제자리 뛰기)"
    )
    assert "네이버 수집" in html
    assert "네이버 주문" not in html, "옛 탭 이름이 남아 있다"
    assert "수집 확인</span>" not in html, "옛 드롭다운 이름이 남아 있다"


def test_gate_off_admin_still_reaches_the_old_ingest_screen(client):
    """게이트 OFF ADMIN 의 옛 수집 운영 화면 경로는 살아 있다 — nav 에서 뺐어도.

    nav 항목만 지우고 대체 경로를 확인하지 않으면 워터마크·인증 만료일을 볼 곳이
    사라진다(수집이 조용히 멈춰도 아무도 모른다).
    """
    _login(client, username="nav_admin_old", role="ADMIN")

    html = client.get(TRIAGE_PATH).get_data(as_text=True)

    assert f'href="{INGEST_PATH}"' in html, "트리아지 화면의 '수집 상태 화면으로' 링크가 없다"
    assert client.get(INGEST_PATH).status_code == 200


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
    """STAFF 도 '네이버 수집' 탭·뱃지는 본다(T14-A 개방). 수집 운영 화면 링크는 없다."""
    _login(client, username="nav_staff", role="STAFF")
    _link("PO-N-5")

    html = client.get("/erp/dashboard").get_data(as_text=True)

    assert TRIAGE_PATH in html, "'네이버 수집' 탭이 STAFF 에게 없다"
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


def test_badge_counts_households_not_product_orders(client):
    """뱃지 숫자는 화면 필터와 **같은 단위(집)** 여야 한다(03 감사 결함 #2).

    네이버는 본품과 구성 옵션을 각각 다른 상품주문으로 준다. 링크 행을 세면 한 집이
    6건으로 잡혀 nav 는 140, 화면 필터는 43 을 보여줬다 — 업무량이 3배로 읽힌다.
    """
    _login(client, username="nav_admin_unit", role="ADMIN")
    _link("PO-U-1", group_key="N-1\x1f010-0000-0000\x1f서울 강남구 1")
    _link("PO-U-2", group_key="N-1\x1f010-0000-0000\x1f서울 강남구 1")
    _link("PO-U-3", group_key="N-1\x1f010-0000-0000\x1f서울 강남구 1")
    _link("PO-U-4", group_key="N-2\x1f010-0000-0000\x1f부산 해운대구 9")

    html = client.get("/erp/dashboard").get_data(as_text=True)

    assert '<span class="badge rounded-pill bg-danger">2</span>' in html, "집 단위로 세야 한다"


def test_badge_falls_back_to_order_no_when_group_key_missing(client):
    """묶음키가 없는 옛 행도 주문번호로 묶인다 — 폴백이 이력 표와 같은 규칙이다."""
    _login(client, username="nav_admin_fb", role="ADMIN")
    _link("PO-FB-1")
    _link("PO-FB-2")
    for link in db_session.query(ExternalOrderLink).filter(
            ExternalOrderLink.external_id.in_(["PO-FB-1", "PO-FB-2"])).all():
        link.external_order_no = "N-FB"
    db_session.commit()
    reset_triage_count_cache_for_tests()

    html = client.get("/erp/dashboard").get_data(as_text=True)
    assert '<span class="badge rounded-pill bg-danger">1</span>' in html


def test_inbox_strip_labels_the_unit_as_households(client):
    """인박스 스트립 문구도 집 단위여야 한다 — 숫자만 바꾸고 라벨을 두면 더 헷갈린다."""
    _login(client, username="nav_admin_strip", role="ADMIN")
    _link("PO-S-1", group_key="N-S\x1f010-0000-0000\x1f서울 강남구 1")
    _link("PO-S-2", group_key="N-S\x1f010-0000-0000\x1f서울 강남구 1")

    html = client.get("/").get_data(as_text=True)

    assert "naver-inbox-strip" in html
    sub = html.split('naver-inbox-strip__sub">')[1].split("</div>")[0]
    assert "1집" in sub, sub
    assert "건" not in sub, sub

# --------------------------------------------------------------------------- #
# v3 §6 — 뱃지 모집단은 "그 사람이 볼 목록"과 같다
# --------------------------------------------------------------------------- #

def _snapshot(order_no: str, external_id: str, *, product: str = "붙박이장",
              address: str = "서울 강남구 1", tel: str = "010-3333-4444") -> dict:
    """수집 파이프라인이 만드는 모양의 원본 스냅샷(묶음키 계산에 필요)."""
    return {
        "order": {"orderId": order_no, "ordererName": "김주문",
                  "ordererTel": "010-1111-2222"},
        "productOrder": {
            "productOrderId": external_id, "productName": product,
            "productOption": "", "totalPaymentAmount": 100000,
            "claimStatus": None, "placeOrderStatus": None,
            "shippingAddress": {"name": "이수취", "tel1": tel,
                                "baseAddress": address, "detailedAddress": "101호"},
        },
    }


def _collected_link(order_no: str, external_id: str, *, reviewed: bool = False,
                    status: str = "COLLECTED", place_status: str | None = None,
                    address: str = "서울 강남구 1") -> ExternalOrderLink:
    """워크벤치 목록 함수가 읽을 수 있는 링크 1건."""
    from foms.services.datetime_kst import now_utc_naive

    snapshot = _snapshot(order_no, external_id, address=address)
    snapshot["productOrder"]["placeOrderStatus"] = place_status
    link = ExternalOrderLink(channel=CHANNEL, external_id=external_id,
                             sync_status=status, external_order_no=order_no,
                             raw_snapshot=snapshot, group_key=group_key_text(snapshot),
                             place_order_status=place_status,
                             reviewed_at=now_utc_naive() if reviewed else None)
    db_session.add(link)
    db_session.commit()
    return link


def test_workbench_badge_counts_the_work_tab_list_not_the_old_queue(app, workbench_on):
    """게이트 ON 뱃지 == 처리 탭 목록 길이(v3 계약 §6).

    옛 정의(``COLLECTED|LINKED`` + ``reviewed_at IS NULL``)는 확인이 끝났지만 아직
    발주확인을 안 보낸 집을 못 센다 — nav 67 · 탭 45 로 어긋났던 자리다. 두 모집단이
    실제로 다른 상황을 만들어 놓고, 뱃지가 **목록 쪽**을 따라가는지 본다.
    """
    from foms.web.admin.naver_ingest import _work_groups

    # 확인 대기(큐) 집 — 두 모집단 모두에 든다.
    _collected_link("N-WB-Q", "PO-WBQ-1")
    # 확인은 끝났지만 발주확인 전 — 큐에는 없고 처리 탭 목록에만 있다.
    _collected_link("N-WB-P", "PO-WBP-1", reviewed=True, status="LINKED",
                    address="부산 해운대구 9")

    groups, _truncated = _work_groups(db_session)

    reset_triage_count_cache_for_tests()
    assert get_triage_pending_count(db_session, workbench=False) == 1, "옛 큐 정의는 1집"
    reset_triage_count_cache_for_tests()
    assert get_triage_pending_count(db_session, workbench=True) == len(groups)
    assert len(groups) == 2, "처리 탭은 확인 큐 ∪ 발주확인 전 집"


def test_workbench_and_legacy_badges_do_not_share_a_cache_slot(app, workbench_on):
    """모집단이 둘이면 캐시 칸도 둘 — 같은 칸을 쓰면 먼저 렌더한 쪽 숫자를 읽는다."""
    _collected_link("N-WB-C", "PO-WBC-1")
    _collected_link("N-WB-D", "PO-WBD-1", reviewed=True, status="LINKED",
                    address="대구 수성구 3")

    reset_triage_count_cache_for_tests()
    legacy_first = get_triage_pending_count(db_session, workbench=False)
    work_first = get_triage_pending_count(db_session, workbench=True)

    assert legacy_first == 1
    assert work_first == 2, "캐시가 섞이면 여기서 1 이 나온다"


def test_nav_badge_uses_the_workbench_number_when_gate_is_on(client, workbench_on):
    """게이트 ON 사용자의 nav 뱃지는 처리 탭 숫자를 그린다(화면과 nav 가 같은 말)."""
    _login(client, username="nav_admin_wb", role="ADMIN")
    _collected_link("N-NAV-Q", "PO-NAVQ-1")
    _collected_link("N-NAV-P", "PO-NAVP-1", reviewed=True, status="LINKED",
                    address="인천 연수구 7")
    reset_triage_count_cache_for_tests()

    html = client.get("/erp/dashboard").get_data(as_text=True)

    assert '<span class="badge rounded-pill bg-danger">2</span>' in html
    assert '<span class="badge bg-danger ms-2">2</span>' in html
