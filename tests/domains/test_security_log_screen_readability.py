"""AUDIT-LOG P4 A2·A3: 보안 로그 화면 가독성·거부 로그 분리 계약.

스펙: ``docs/specs/2026-08-08-audit-log-readability-coverage-design.md`` §3-1·§3-4.

고정하는 계약:

1. **구 형식 행도 읽힌다** — 운영에 이미 쌓인 자유 텍스트(재기록 불가)가 화면에서 업무
   언어로 보이고, 주문번호 옆에 고객명이 붙는다.
2. **구조화 행은 before → after 까지 보인다** — T8 ``detail`` 이 있으면 그것으로 문장을 만든다.
3. **원문은 사라지지 않는다** — 한글화한 행은 "기록 원문"을 함께 낸다(감사 신뢰의 근거).
4. **조회는 배치 1회** — 고객명 때문에 페이지당 50번 주문을 조회하지 않는다.
5. **거부 기록 분리** — 기본 목록에서 빠지고 스위치로만 본다(운영 실측: 전체의 32%).
"""

from __future__ import annotations

import itertools
import re

import pytest

from db import db_session
from models import Order, SecurityLog, User
from foms.web.auth.routes import log_access

_counter = itertools.count(1)
_PATH = "/security_logs"


def _make_user(role: str = "ADMIN") -> int:
    n = next(_counter)
    user = User(username=f"p4-screen-{n}", password="x", role=role,
                name=f"관리자{n}", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user.id


def _make_order(customer_name: str) -> int:
    order = Order(
        received_date="2026-08-08", customer_name=customer_name, phone="01000000000",
        address="서울시 테스트구", product="붙박이장", status="RECEIVED",
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _text(body: str) -> str:
    """HTML 태그를 걷어낸 본문 텍스트.

    ``order_link`` 필터가 '주문 #N' 을 서버 생성 ``<a>`` 로 감싸므로(저장형 XSS 방지),
    문장 단언은 태그를 걷고 해야 링크 유무에 흔들리지 않는다.
    """
    return re.sub(r"<[^>]+>", "", body)


def _admin_client(app):
    admin_id = _make_user()
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = admin_id
    return client, admin_id


# --------------------------------------------------------------------------
# 1~3. 표기
# --------------------------------------------------------------------------
def test_legacy_free_text_row_is_rendered_in_business_language(app):
    """구 형식 행이 업무 언어 + 고객명으로 보인다(운영 24,605행이 이 경로를 탄다)."""
    with app.app_context():
        client, admin_id = _admin_client(app)
        order_id = _make_order("김철수")
        log_access(
            f"지방 주문 #{order_id}의 'regional_construction_info_sent' 상태를 'True'(으)로 변경",
            admin_id,
        )

        body = client.get(_PATH).get_data(as_text=True)

    text = _text(body)
    assert f"지방 주문 #{order_id} (김철수)" in text
    assert "시공정보 발송" in text
    assert "regional_construction_info_sent" not in body.split("기록 원문")[0]
    # 원문은 접힌 채로 함께 남는다.
    assert "기록 원문" in body
    assert "regional_construction_info_sent" in body


def test_structured_row_shows_before_and_after(app):
    """구조화 detail 이 있으면 '이전 → 이후'가 문장에 나온다."""
    with app.app_context():
        client, admin_id = _admin_client(app)
        order_id = _make_order("이영희")
        log_access(
            "주문 필드 변경",
            admin_id,
            action="ORDER_FIELD_UPDATED",
            target_type="order",
            target_id=order_id,
            detail={"field": "as_completed_date", "before": "2026-07-02", "after": ""},
        )

        body = client.get(_PATH).get_data(as_text=True)

    text = _text(body)
    assert f"주문 #{order_id} (이영희)" in text
    assert "AS 완료일: 2026-07-02 → (지움)" in text


def test_unparseable_message_is_left_untouched(app):
    """해석 못 하는 문장은 그대로 — 감사 화면은 값을 감추거나 지어내지 않는다."""
    with app.app_context():
        client, admin_id = _admin_client(app)
        log_access("엑셀 업로드 22건 처리", admin_id)

        body = client.get(_PATH).get_data(as_text=True)

    assert "엑셀 업로드 22건 처리" in body


def test_customer_names_are_loaded_in_one_batched_query(app):
    """고객명 조회는 페이지당 1회 — 행마다 조회하면 50 쿼리가 된다(N+1 금지)."""
    from sqlalchemy import event

    with app.app_context():
        client, admin_id = _admin_client(app)
        order_ids = [_make_order(f"고객{i}") for i in range(5)]
        for order_id in order_ids:
            log_access(f"주문 #{order_id}의 'measurement_date' 필드를 '2026-08-01'(으)로 변경", admin_id)

        seen: list[str] = []

        def _capture(conn, cursor, statement, parameters, context, executemany):
            if "FROM orders" in statement:
                seen.append(statement)

        engine = db_session.get_bind()
        event.listen(engine, "before_cursor_execute", _capture)
        try:
            body = client.get(_PATH).get_data(as_text=True)
        finally:
            event.remove(engine, "before_cursor_execute", _capture)

    text = _text(body)
    assert all(f"(고객{i})" in text for i in range(5))
    assert len(seen) == 1, f"orders 조회가 {len(seen)}회 — 배치 1회여야 한다"


def test_missing_order_renders_number_without_inventing_name(app):
    """주문이 없으면 번호만 — 없는 고객명을 지어내지 않는다."""
    with app.app_context():
        client, admin_id = _admin_client(app)
        log_access("주문 #999999의 'measurement_date' 필드를 '2026-08-01'(으)로 변경", admin_id)

        body = client.get(_PATH).get_data(as_text=True)

    text = _text(body)
    assert "주문 #999999" in text
    assert "주문 #999999 (" not in text


# --------------------------------------------------------------------------
# 5. 거부 로그 분리 (A3)
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "kwargs",
    [
        {"action": "ACCESS_DENIED"},   # T8 구조화 형태
        {},                            # 구형식 자유 텍스트
    ],
)
def test_denied_rows_are_hidden_by_default_and_reachable_on_demand(app, kwargs):
    """거부 기록은 기본 목록에서 빠지고 스위치로만 보인다(구조화·구형식 둘 다)."""
    with app.app_context():
        client, admin_id = _admin_client(app)
        log_access("권한 없는 접근 시도: /trash", admin_id, **kwargs)
        log_access("업무 기록 표식 ZZTOP", admin_id)

        default_body = client.get(_PATH).get_data(as_text=True)
        with_denied = client.get(f"{_PATH}?include_denied=1").get_data(as_text=True)

    assert "업무 기록 표식 ZZTOP" in default_body
    assert "권한 없는 접근 시도" not in default_body

    assert "권한 없는 접근 시도" in with_denied
    assert "업무 기록 표식 ZZTOP" in with_denied


def test_explicit_action_filter_still_reaches_denied_rows(app):
    """action 을 직접 지정하면(예: ACCESS_DENIED) 스위치 없이도 조회된다."""
    with app.app_context():
        client, admin_id = _admin_client(app)
        log_access("권한 없는 접근 시도: /trash", admin_id, action="ACCESS_DENIED")

        body = client.get(f"{_PATH}?action=ACCESS_DENIED").get_data(as_text=True)

    assert "권한 없는 접근 시도" in body


def test_pagination_links_preserve_denied_switch(app):
    """페이지 링크는 켜진 스위치만 유지한다."""
    with app.app_context():
        client, admin_id = _admin_client(app)
        for index in range(55):
            log_access(f"페이지 행 {index:03d}", admin_id, auto_commit=False)
        db_session.commit()

        on = client.get(f"{_PATH}?include_denied=1").get_data(as_text=True)
        off = client.get(_PATH).get_data(as_text=True)

    on_pager = on.split('aria-label="보안 로그 페이지"')[1]
    off_pager = off.split('aria-label="보안 로그 페이지"')[1]
    assert "include_denied=1" in on_pager
    assert "include_denied" not in off_pager
