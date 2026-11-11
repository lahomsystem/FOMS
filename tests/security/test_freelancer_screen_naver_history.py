"""프리랜서 화면 묶음: 네이버 수집 이력(보기만) — 사용자 결정 2026-11-11.

묶음 파일: foms/services/auth/freelancer_screens/naver_history.py · 화면: foms/web/admin/naver_ingest.py.

* 켜진 프리랜서는 회사 영업과 같게 이력 탭을 본다 — '내 담당만' 기본 켜짐(내 주문 = 연결 표), 끄면 남의 이름으로도
  찾힌다(고객이 다른 네이버 아이디로 추가 결제하는 일).
* ``?tab=work`` 를 쳐도 이력 탭이다. 처리 탭 링크 · 행의 '처리 탭으로' 링크가 없다.
* '원본 보기'(읽기 전용 조각)는 열린다. 처리 pane · 배지 수 · 쓰기 라우트는 문지기가 막는다.
* 워크벤치 게이트가 꺼진 옛 화면(처리 큐)은 404.
* 대조군: 프리랜서 아닌 영업 직원은 처리 탭이 그대로 있다.
모든 이름 · 전화번호는 가짜 값이다.
"""
from __future__ import annotations

from db import db_session
from foms.services.auth.freelancer_scope import FREELANCER_ALLOWED_ENDPOINTS
from foms.services.sales_commission.settings import load_settings, save_freelancer
from models import ExternalOrderLink, Order, OrderFreelancerLink

from tests.services.integrations.test_naver_workbench import (  # noqa: F401 - fixture 재사용
    _collected,
    _login,
    _uid,
    workbench_on,
)

TRIAGE = "/admin/naver-ingest/triage"


def _history_tbody(body: str) -> str:
    return body.split('class="wb-cmp wb-hist"')[1].split("<tbody>")[1].split("</tbody>")[0]


def _freelancer(client):
    user = _login(client, role="STAFF", team="SALES")
    save_freelancer(db_session, user.id, {"match_name": f"가짜프리{_uid()}", "start_month": "2020-01",
                                          "tax_type": "NONE", "active": True},
                    base_version=load_settings(db_session)[0], actor_user_id=None)
    db_session.commit()
    return user


def _linked(product: str, *, freelancer_id: int | None) -> ExternalOrderLink:
    """FOMS 주문이 붙은 수집분 1건 — ``freelancer_id`` 가 있으면 그 프리랜서 연결 줄을 단다."""
    seq = _uid()
    order = Order(received_date="2026-10-01", customer_name=f"고객{seq}", phone="010-0000-0000",
                  address=f"가짜시 {seq}", product=product, status="RECEIVED")
    db_session.add(order)
    db_session.commit()
    link = _collected(order_no=f"N-FL-{seq}", product=product, amount=100_000,
                      address=f"가짜시 {seq}", tel="010-0000-0001")
    row = db_session.get(ExternalOrderLink, int(link.id))
    row.order_id = int(order.id)
    row.sync_status = "LINKED"
    if freelancer_id is not None:
        db_session.add(OrderFreelancerLink(order_id=order.id, user_id=freelancer_id, relation="MANAGER_PRIMARY"))
    db_session.commit()
    return row


def test_bundle_opens_only_history_and_readonly_detail():
    assert "admin.naver_ingest_triage" in FREELANCER_ALLOWED_ENDPOINTS
    assert "admin.naver_ingest_triage_detail" in FREELANCER_ALLOWED_ENDPOINTS
    for closed in ("admin.naver_ingest_triage_pane", "admin.naver_ingest_triage_pending_count",
                   "admin.naver_ingest_dashboard"):
        assert closed not in FREELANCER_ALLOWED_ENDPOINTS, closed


def test_freelancer_sees_own_by_default_and_others_when_mine_off(client, workbench_on):
    me = _freelancer(client)
    _linked("내프리 붙박이장", freelancer_id=me.id)
    _linked("남의 붙박이장", freelancer_id=None)

    resp = client.get(f"{TRIAGE}?tab=work")  # 처리 탭을 쳐도 이력 탭
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    tbody = _history_tbody(body)
    assert "내프리 붙박이장" in tbody and "남의 붙박이장" not in tbody
    assert 'data-tab="work"' not in body, "처리 탭 링크가 없어야 한다"
    assert "wb-hist-open" not in tbody, "행의 '처리 탭으로' 링크가 없어야 한다"

    off = _history_tbody(client.get(f"{TRIAGE}?tab=all&mine=0").get_data(as_text=True))
    assert "내프리 붙박이장" in off and "남의 붙박이장" in off


def test_freelancer_detail_open_pane_and_count_closed(client, workbench_on):
    _freelancer(client)
    other = _linked("남의 원본", freelancer_id=None)

    assert client.get(f"{TRIAGE}/detail?link_id={other.id}").status_code == 200
    assert client.get(f"{TRIAGE}/pane?link_id={other.id}").status_code in (302, 403)
    assert client.get(f"{TRIAGE}/pending-count",
                      headers={"Accept": "application/json"}).status_code in (302, 403)


def test_freelancer_old_screen_404_when_workbench_off(client, monkeypatch):
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_ENABLED", "0")
    _freelancer(client)
    assert client.get(TRIAGE).status_code == 404


def test_control_sales_staff_keeps_work_tab(client, workbench_on):
    _login(client, role="STAFF", team="SALES")
    body = client.get(f"{TRIAGE}?tab=all").get_data(as_text=True)
    assert 'data-tab="work"' in body


def test_freelancer_phone_render_has_history_only(client, workbench_on):
    """폰(아이폰 UA)으로 열어도 이력 탭만 그려지고 수집 관리 · 다시 읽기 손잡이가 없다."""
    me = _freelancer(client)
    _linked("폰 내 붙박이장", freelancer_id=me.id)
    ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148"
    resp = client.get(f"{TRIAGE}?tab=all", headers={"User-Agent": ua})
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "폰 내 붙박이장" in body
    for absent in ('data-tab="work"', 'id="wb-asheet-open"', 'id="wb-refresh-all"', 'id="wb-run-now"',
                   'id="wb-retry-failed"'):
        assert absent not in body, absent
