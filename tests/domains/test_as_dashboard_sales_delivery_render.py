"""AS 영업/택배 탭 "전달 배정" 화면 렌더 계약 (T4).

스펙: docs/specs/2026-09-09-as-sales-delivery-measurement-assignment-design.md §6.1·§7.
목업: Claude Design "AS 전달 배정 화면" (Main / AssignModal / NoCandidate 아트보드).

시드는 쓰기 API 를 거치지 않고 `sales_delivery_link.write_link()` 출력 형태의 dict 를
structured_data 에 직접 심는다(스키마 §2.1 고정). 검증 대상은 읽기 모델
(`as_dashboard_display.apply_sales_delivery_display_fields`) → 매크로
(`render_sales_delivery_cell`) → 템플릿 렌더 경로다.

정적 계약 3종도 함께 잠근다:
- 모달·JS 훅 문자열 존재(리팩터에서 버튼/모달이 통째로 사라지는 회귀 방지).
- 손댄 자산의 `?v=` 핀 동기화(SW staticCacheFirst 로 구버전이 계속 실행되는 사고 방지).
- colgroup 열 수 == thead 열 수(13열) — 둘이 어긋나면 table-layout:fixed 배분이 무너진다.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderScheduleDate, User

_ROOT = Path(__file__).resolve().parents[2]
_TODAY = date.today().strftime("%Y-%m-%d")
_ASSET_PIN = "20260909a"


def _login_as_admin(client, username: str = "sales-delivery-render-admin") -> None:
    """관리자 로그인 — 셀 액션 버튼은 `can_edit_erp` 게이트를 탄다(쓰기는 API 가 소유)."""
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role="ADMIN",
        team="CS",
        name="전달 배정 렌더 관리자",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _create_measurement_order(*, measurement_date: str, customer_name: str = "실측 고객") -> int:
    """기준 실측 주문 시드. 현재 실측일은 `order_schedule_dates(kind='measurement')` 가 SSOT."""
    order = Order(
        received_date=_TODAY,
        customer_name=customer_name,
        phone="010-0000-1111",
        address="성남시 분당구 판교로 256",
        product="붙박이장",
        status="MEASURE",
        manager_name="이정민",
        is_erp_order=True,
        structured_data={"parties": {"manager": "이정민"}},
    )
    db_session.add(order)
    db_session.commit()
    db_session.add(
        OrderScheduleDate(
            order_id=order.id,
            kind="measurement",
            date=measurement_date,
            source="test_seed",
        )
    )
    db_session.commit()
    return order.id


def _link(ref_order_id: int, ref_date: str, *, status: str = "assigned",
          ack_ref_date: str | None = None) -> dict:
    """`write_link()` 출력 형태 그대로의 링크 dict(스펙 §2.1)."""
    return {
        "ref_order_id": ref_order_id,
        "ref_kind": "measurement",
        "ref_date": ref_date,
        "ref_manager": "이정민",
        "assigned_at": "2026-09-09T00:00:00",
        "assigned_by_user_id": None,
        "assigned_by": "테스트",
        "source": "as_sales_delivery_modal",
        "ack_ref_date": ack_ref_date,
        "status": status,
        "delivered_at": "2026-09-09T01:00:00" if status == "delivered" else None,
        "delivered_by": "테스트" if status == "delivered" else None,
    }


def _create_delivery_order(*, customer_name: str, link: dict | None = None,
                           method: str | None = None) -> int:
    """영업/택배 탭 모집단(`shipment.sales_delivery = True`)의 AS 전달 건 시드."""
    shipment: dict = {"as_content": "<div>전달 건</div>", "sales_delivery": True}
    if link is not None:
        shipment["sales_delivery_link"] = link
    if method is not None:
        shipment["sales_delivery_method"] = method
    order = Order(
        received_date=_TODAY,
        customer_name=customer_name,
        phone="010-2222-3333",
        address="하남시 위례중앙로 185",
        product="붙박이장",
        status="AS_RECEIVED",
        manager_name="Alice",
        as_received_date=_TODAY,
        is_erp_order=True,
        structured_data={"shipment": shipment},
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _sales_delivery_body(client) -> str:
    resp = client.get("/erp/as?tab=sales_delivery")
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


def _cells(body: str) -> list[str]:
    """렌더 본문에서 전달 배정 셀 컨테이너 여는 태그만 잘라낸다(상태 속성 검사용)."""
    return re.findall(r'<div class="erp-as-sd-cell[^"]*"[^>]*>', body)


# ---------------------------------------------------------------------------
# 1) 4상태 셀 렌더
# ---------------------------------------------------------------------------


def test_unassigned_row_renders_assign_button(client):
    """미배정 행은 '실측에 태우기' 버튼 + 모달 인자(주소/좌표/주문id)를 들고 렌더된다."""
    _login_as_admin(client)
    as_id = _create_delivery_order(customer_name="미배정 고객")

    body = _sales_delivery_body(client)

    assert 'data-as-sd-state="unassigned"' in body
    assert "js-as-sd-open" in body
    assert "실측에 태우기" in body
    assert f'data-as-sd-cell="{as_id}"' in body
    assert 'data-address="하남시 위례중앙로 185"' in body


def test_assigned_row_renders_chip_and_actions(client):
    """배정 행은 담당자·날짜 칩 + '실측 #<id> <고객명>' 보조줄 + 변경/해제 아이콘을 낸다."""
    _login_as_admin(client)
    ref_id = _create_measurement_order(measurement_date="2026-09-11", customer_name="박준호")
    _create_delivery_order(customer_name="배정 고객", link=_link(ref_id, "2026-09-11"))

    body = _sales_delivery_body(client)

    assert 'data-as-sd-state="assigned"' in body
    assert "erp-as-sd-chip--assigned" in body
    assert "이정민" in body
    assert f"실측 #{ref_id} 박준호" in body
    assert "js-as-sd-unassign" in body
    assert "js-as-sd-deliver" in body
    # 배정 상태에서는 drift 조치 버튼이 뜨지 않는다(기준일이 그대로다).
    assert "js-as-sd-ack" not in body


def test_delivered_row_renders_badge_and_undo(client):
    """전달완료 행은 초록 배지 + 되돌리기 버튼을 낸다."""
    _login_as_admin(client)
    ref_id = _create_measurement_order(measurement_date="2026-09-11")
    _create_delivery_order(
        customer_name="전달완료 고객",
        link=_link(ref_id, "2026-09-11", status="delivered"),
    )

    body = _sales_delivery_body(client)

    assert 'data-as-sd-state="delivered"' in body
    assert "erp-as-sd-badge--delivered" in body
    assert "전달완료" in body
    assert "js-as-sd-undeliver" in body


def test_parcel_row_renders_gray_chip_and_cancel(client):
    """택배 행은 회색 칩 + 취소 버튼을 낸다(링크는 이미 해제된 상태)."""
    _login_as_admin(client)
    _create_delivery_order(customer_name="택배 고객", method="parcel")

    body = _sales_delivery_body(client)

    assert 'data-as-sd-state="parcel"' in body
    assert "erp-as-sd-chip--parcel" in body
    assert "js-as-sd-parcel-cancel" in body


# ---------------------------------------------------------------------------
# 2) drift(ref_moved / ref_gone)
# ---------------------------------------------------------------------------


def test_ref_moved_row_renders_drift_border_and_two_actions(client):
    """기준 실측일이 바뀌면 빨강 테두리 + '그대로 유지'(ack)·'다른 일정으로'(재배정)."""
    _login_as_admin(client)
    ref_id = _create_measurement_order(measurement_date="2026-09-16")
    _create_delivery_order(customer_name="드리프트 고객", link=_link(ref_id, "2026-09-09"))

    body = _sales_delivery_body(client)

    assert "erp-as-sd-cell--drift" in body
    assert "js-as-sd-ack" in body
    assert "그대로 유지" in body
    assert "다른 일정으로" in body
    assert 'data-reassign="1"' in body
    # 옛 날짜 취소선 → 새 날짜(요일 포함) 표기
    assert "09-09(수)" in body
    assert "09-16(수)" in body
    # 상단 경고 띠가 건수를 낸다
    assert "erp-as-sd-driftbar" in body
    assert "실측일이 바뀐 전달 건 1건" in body


def test_ref_gone_row_renders_drift_state(client):
    """기준 실측 주문이 삭제되면 '일정 사라짐'으로 표시되고 조치 버튼이 함께 뜬다."""
    _login_as_admin(client)
    ref_id = _create_measurement_order(measurement_date="2026-09-16")
    ref = db_session.get(Order, ref_id)
    ref.status = "DELETED"
    db_session.commit()
    _create_delivery_order(customer_name="고아 링크 고객", link=_link(ref_id, "2026-09-09"))

    body = _sales_delivery_body(client)

    assert "erp-as-sd-cell--drift" in body
    assert "일정 사라짐" in body
    assert "js-as-sd-ack" in body


def test_acked_row_has_no_drift_actions(client):
    """확인(ack) 처리된 변경은 경고를 접는다 — 테두리도 조치 버튼도 없다."""
    _login_as_admin(client)
    ref_id = _create_measurement_order(measurement_date="2026-09-16")
    _create_delivery_order(
        customer_name="확인 완료 고객",
        link=_link(ref_id, "2026-09-09", ack_ref_date="2026-09-16"),
    )

    body = _sales_delivery_body(client)

    assert "erp-as-sd-cell--drift" not in body
    assert "js-as-sd-ack" not in body
    assert "erp-as-sd-driftbar" not in body


# ---------------------------------------------------------------------------
# 3) 요약 pill (렌더된 행에서 파이썬 집계)
# ---------------------------------------------------------------------------


def test_summary_pills_count_rendered_rows(client):
    """요약 pill 4개가 렌더된 행의 상태별 건수를 그대로 낸다(탭 카운트 SQL 불변)."""
    _login_as_admin(client)
    ref_id = _create_measurement_order(measurement_date="2026-09-11")
    _create_delivery_order(customer_name="미배정A")
    _create_delivery_order(customer_name="미배정B")
    _create_delivery_order(customer_name="배정A", link=_link(ref_id, "2026-09-11"))
    _create_delivery_order(
        customer_name="완료A", link=_link(ref_id, "2026-09-11", status="delivered")
    )
    _create_delivery_order(customer_name="택배A", method="parcel")

    body = _sales_delivery_body(client)

    assert re.search(r'data-as-sd-summary="unassigned"[^>]*data-count="2"', body)
    assert re.search(r'data-as-sd-summary="assigned"[^>]*data-count="1"', body)
    assert re.search(r'data-as-sd-summary="delivered"[^>]*data-count="1"', body)
    assert re.search(r'data-as-sd-summary="parcel"[^>]*data-count="1"', body)
    # 기존 탭 카운트 마크업(정규식 계약)은 그대로 살아 있어야 한다.
    assert re.search(r'data-as-tab-key="sales_delivery"[^>]*data-as-tab-count="5"', body)


def test_summary_pills_are_absent_on_other_tabs(client):
    """미완료/완료 탭에는 전달 요약 pill 을 내지 않는다(그 탭의 축이 아니다)."""
    _login_as_admin(client)
    _create_delivery_order(customer_name="전달 건")

    body = client.get("/erp/as?tab=incomplete").get_data(as_text=True)

    assert "erp-as-sd-summary" not in body


# ---------------------------------------------------------------------------
# 4) 정적 계약 — 모달 마크업 / JS 훅 / 자산 핀 / 열 수
# ---------------------------------------------------------------------------


def test_sales_delivery_modal_markup_exists():
    """배정 모달(#salesDeliveryModal)과 정렬 탭 3종·빈 상태 택배 버튼이 마크업에 있다."""
    body = (_ROOT / "templates/cs/partials/as_dashboard_body.html").read_text(encoding="utf-8")

    assert 'id="salesDeliveryModal"' in body
    assert 'id="salesDeliveryResults"' in body
    assert 'id="salesDeliveryEmpty"' in body
    for sort in ("distance", "date", "combined"):
        assert f'data-sd-sort="{sort}"' in body, sort
    assert "js-as-sd-parcel" in body
    assert "택배로 보내기" in body
    assert 'id="salesDeliveryCarrier"' in body
    assert 'id="salesDeliveryTracking"' in body
    # 인라인 스타일 금지 — 모달 마크업에 style= 이 없어야 한다.
    modal = body[body.index('id="salesDeliveryModal"'):body.index('id="as-dashboard-config"')]
    assert "style=" not in modal


def test_sales_delivery_js_hooks_exist():
    """신규 IIFE 가 살아 있고, 기존 nearby 모달 로직과 분리돼 있다."""
    js = (_ROOT / "static/js/cs/as-dashboard.js").read_text(encoding="utf-8")

    assert "function salesDeliveryAssign()" in js
    assert "/sales-delivery" in js
    assert "kind: 'measurement'" in js
    assert "bootstrap.Modal.getOrCreateInstance" in js
    for hook in (
        "js-as-sd-open", "js-as-sd-pick", "js-as-sd-unassign", "js-as-sd-deliver",
        "js-as-sd-undeliver", "js-as-sd-parcel-cancel", "js-as-sd-ack", "js-as-sd-parcel",
    ):
        assert hook in js, hook
    # 기존 nearby 모달(#scheduleSearchModal) 훅은 그대로 남아 있어야 한다(분리 계약).
    assert "js-as-schedule-link" in js
    # 무음 실패 금지 — 토스트와 함께 인라인 상태 텍스트를 쓴다.
    assert "function sdNote(" in js
    assert "js-as-sd-msg" in js
    # 응답 검증은 data.success 로 한다(HTTP 200 + success:false 를 삼키지 않는다).
    assert "res.data.success !== true" in js
    # CSRF 수동 부착 금지 — 전역 인터셉터가 붙인다.
    assert "X-CSRFToken" not in js


def test_touched_asset_pins_are_bumped_and_in_sync():
    """as-dashboard.js / as-dashboard-body.css 핀이 이번 변경분으로 함께 올라갔다."""
    body = (_ROOT / "templates/cs/partials/as_dashboard_body.html").read_text(encoding="utf-8")

    for asset in ("js/cs/as-dashboard.js", "css/contexts/cs/as-dashboard-body.css"):
        pins = set(re.findall(re.escape(asset) + r"'\s*\)\s*\}\}\?v=([A-Za-z0-9._-]+)", body))
        assert pins == {_ASSET_PIN}, (asset, pins)


def test_table_colgroup_and_head_have_thirteen_matching_columns():
    """colgroup 열 수 == thead 열 수 == 13(전달 배정 열 추가분 포함).

    두 값이 어긋나면 table-layout:fixed 의 폭 배분이 통째로 어긋난다(2026-07-28 붕괴 이력).
    빈 목록 행 colspan 도 같은 수여야 "데이터가 없습니다" 줄이 표를 가로지른다.
    """
    body = (_ROOT / "templates/cs/partials/as_dashboard_body.html").read_text(encoding="utf-8")
    colgroup = body[body.index("<colgroup>"):body.index("</colgroup>")]
    thead = body[body.index("<thead>"):body.index("</thead>")]

    cols = re.findall(r'<col data-col-key="([a-z_]+)">', colgroup)
    ths = re.findall(r'<th data-col-key="([a-z_]+)"', thead)

    assert len(cols) == 13, cols
    assert cols == ths, (cols, ths)
    assert "sales_delivery" in cols
    assert 'colspan="13"' in body
