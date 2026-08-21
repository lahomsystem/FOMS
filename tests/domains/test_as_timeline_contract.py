"""T12 — as_content 쓰기 퇴역 이후의 AS 타임라인 계약.

네 가지를 고정한다.
1) `update_order_field` 는 `as_content`/`as_content_2` 를 더 이상 받지 않는다(400).
   신규 AS 기록은 `POST /api/orders/<id>/as/log` 한 곳으로만 들어온다.
2) 최초 append 가 기존 `as_content` 를 legacy 항목으로 **영구화**한다(표시 시점 lazy
   마이그레이션이 아니라 DB 에 굳는다).
3) 같은 라우트의 `sales_delivery` 토글은 퇴역과 무관하게 살아 있다(회귀 가드).
4) `/erp/as?q=` 검색이 `as_log` 본문까지 본다 — quick-add 로 쌓이는 기록이
   검색 사각지대가 되면 AS 내용 검색은 시간이 갈수록 비어간다(T10 U3).
"""

from __future__ import annotations

from datetime import date

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User


def _login_as_admin(client, username="as-timeline-contract-admin") -> int:
    """ADMIN/CS 사용자로 로그인하고 id 만 반환(teardown detach 회피)."""
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role="ADMIN",
        team="CS",
        name="AS 타임라인 계약 관리자",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    user_id = user.id
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["username"] = user.username
        sess["role"] = user.role
    return user_id


def _create_as_order(
    *,
    shipment_extra=None,
    as_content_2="<div>2번 내용</div>",
    customer_name="AS 계약 고객",
    status="AS_RECEIVED",
):
    """AS 주문 1건 생성. shipment_extra 가 as_content 를 덮어쓸 수 있다."""
    today = date.today().strftime("%Y-%m-%d")
    shipment = {"as_content": "<div>1번 내용</div>"}
    if as_content_2 is not None:
        shipment["as_content_2"] = as_content_2
    if shipment_extra:
        shipment.update(shipment_extra)
    order = Order(
        received_date=today,
        customer_name=customer_name,
        phone="010-1234-5678",
        address="Seoul",
        product="붙박이장",
        status=status,
        manager_name="Alice",
        as_received_date=today,
        is_erp_order=True,
        structured_data={"workflow": {"stage": status}, "shipment": shipment},
    )
    db_session.add(order)
    db_session.commit()
    return order


# ---------------------------------------------------------------------------
# 1) update_order_field 퇴역
# ---------------------------------------------------------------------------


def test_update_order_field_rejects_as_content(client):
    _login_as_admin(client, username="as-contract-reject-1")
    order = _create_as_order()

    res = client.post(
        "/api/update_order_field",
        json={"order_id": order.id, "field_name": "as_content", "new_value": "x"},
    )

    assert res.status_code == 400
    assert res.get_json()["success"] is False


def test_update_order_field_rejects_as_content_2(client):
    _login_as_admin(client, username="as-contract-reject-2")
    order = _create_as_order()

    res = client.post(
        "/api/update_order_field",
        json={"order_id": order.id, "field_name": "as_content_2", "new_value": "x"},
    )

    assert res.status_code == 400
    assert res.get_json()["success"] is False


def test_update_order_field_rejection_does_not_touch_structured_data(client):
    """거부는 부작용이 없어야 한다 — 기존 as_content 원문이 그대로 남는다."""
    _login_as_admin(client, username="as-contract-reject-3")
    order = _create_as_order(shipment_extra={"as_content": "<div>보존될 원문</div>"})
    order_id = order.id

    client.post(
        "/api/update_order_field",
        json={"order_id": order_id, "field_name": "as_content", "new_value": ""},
    )

    db_session.expire_all()
    shipment = db_session.get(Order, order_id).structured_data["shipment"]
    assert shipment["as_content"] == "<div>보존될 원문</div>"


# ---------------------------------------------------------------------------
# 2) legacy 영구화
# ---------------------------------------------------------------------------


def test_first_append_persists_legacy(client):
    """최초 append 가 기존 as_content 를 legacy 항목으로 흡수·보존한다."""
    _login_as_admin(client, username="as-contract-legacy")
    order = _create_as_order(
        shipment_extra={"as_content": "<div>옛 접수 원문</div>"}, as_content_2=None
    )
    order_id = order.id

    res = client.post(
        f"/api/orders/{order_id}/as/log", json={"type": "call", "text": "통화"}
    )
    assert res.status_code == 200

    db_session.expire_all()
    log = db_session.get(Order, order_id).structured_data["shipment"]["as_log"]
    assert any(
        e.get("legacy") is True and "옛 접수 원문" in e.get("text", "") for e in log
    )
    assert any(e.get("type") == "call" for e in log)


# ---------------------------------------------------------------------------
# 3) 퇴역 후에도 살아 있어야 하는 같은 라우트 경로
# ---------------------------------------------------------------------------


def test_sales_delivery_toggle_still_works(client):
    _login_as_admin(client, username="as-contract-sales")
    order = _create_as_order()
    order_id = order.id

    res = client.post(
        "/api/update_order_field",
        json={"order_id": order_id, "field_name": "sales_delivery", "new_value": True},
    )

    assert res.status_code == 200 and res.get_json()["success"] is True
    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.structured_data["shipment"]["sales_delivery"] is True


# ---------------------------------------------------------------------------
# 4) as_log 검색 (T10 U3)
# ---------------------------------------------------------------------------


def _log_entry(text: str, *, entry_id="al_1", log_type="memo") -> dict:
    return {
        "id": entry_id,
        "ts": "2026-07-24T00:00:00",
        "by": "관리자",
        "by_id": None,
        "type": log_type,
        "text": text,
        "edited_at": None,
        "edited_by": None,
    }


def test_search_finds_as_log_text(client):
    """quick-add 로 쌓인 as_log 본문이 검색에 잡힌다(as_content 에는 없는 문장)."""
    _login_as_admin(client, username="as-contract-search-1")
    _create_as_order(
        customer_name="로그검색대상",
        shipment_extra={"as_log": [_log_entry("<div>손잡이 교체 완료</div>")]},
    )
    _create_as_order(customer_name="검색제외대상")

    res = client.get("/erp/as?q=손잡이교체")

    assert res.status_code == 200
    body = res.get_data(as_text=True)
    assert "로그검색대상" in body
    assert "검색제외대상" not in body


def test_search_expressions_concatenate_on_postgres():
    """검색 식의 문자열 결합은 postgres 에서 `||` 로 컴파일돼야 한다.

    sqlite 는 `+`/`||` 를 둘 다 받아들여 **런타임 테스트 레인이 이 회귀를 못 잡는다**.
    그래서 dialect 컴파일 결과를 직접 단언한다(sqlite 레인에서 돌아가는 정적 검사).

    게이트 실측(T13):
      - F4 이전: `||` — `case(cond, else_='')` 의 String 타입이 앵커 역할을 했다.
      - F4 직후: `+`  — 세 성분이 전부 `func.regexp_replace` 산물(NullType)이라
        SQLAlchemy 가 문자열 결합으로 승격하지 못했다. 운영 postgres 에서
        `연산자 없음: text + text` → **검색어가 있는 모든 AS 요청 500**.
      - 수정 후: `||` — `func.regexp_replace(..., type_=String)`.
    타입 단언까지 함께 두는 이유: SQL 문자열만 보면 성분이 하나로 줄어든 미래 리팩터에서
    `+` 가 안 보인다고 통과할 수 있는데, 근본 원인은 어디까지나 무타입(NullType)이다.
    """
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.sql.sqltypes import NullType

    from foms.services.as_dashboard_helpers import (
        _combined_as_content_expr,
        _display_address_expr,
    )

    exprs = {
        "combined_as_content": _combined_as_content_expr(
            dialect_name="postgresql", use_postgres_regex=True
        ),
        "display_address": _display_address_expr(dialect_name="postgresql"),
    }
    for label, expr in exprs.items():
        sql = str(
            expr.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
        )
        assert "||" in sql, f"{label}: 문자열 결합이 사라졌다"
        assert " + " not in sql, f"{label}: `+` 로 컴파일됨 → postgres text + text 500"
        assert not isinstance(expr.type, NullType), f"{label}: 무타입 산물 — 결합 시 `+` 로 샌다"


def test_search_ignores_as_log_entry_id(client):
    """항목 id·ts 는 검색 대상이 아니다 — 배열째 텍스트화하면 숫자 검색이 전부 오탐이 된다."""
    _login_as_admin(client, username="as-contract-search-id")
    _create_as_order(
        customer_name="아이디오탐대상",
        shipment_extra={
            "as_log": [_log_entry("<div>문고리 교체</div>", entry_id="al_1753999999_ab")]
        },
    )

    res = client.get("/erp/as?q=1753999999")

    assert res.status_code == 200
    assert "아이디오탐대상" not in res.get_data(as_text=True)


def test_search_survives_malformed_as_log(client):
    """as_log 가 배열이 아닌 오염 행 하나가 검색 전체를 500 으로 만들면 안 된다."""
    _login_as_admin(client, username="as-contract-search-3")
    _create_as_order(customer_name="오염행고객", shipment_extra={"as_log": "배열이 아님"})
    _create_as_order(
        customer_name="정상행고객",
        shipment_extra={"as_log": [_log_entry("<div>문틀 보수</div>")]},
    )

    res = client.get("/erp/as?q=문틀보수")

    assert res.status_code == 200
    assert "정상행고객" in res.get_data(as_text=True)


# ---------------------------------------------------------------------------
# 5) as_log 본문 sanitize 신뢰 계약 (T11 이월 c / T7 이월 d)
# ---------------------------------------------------------------------------

_XSS_PAYLOAD = '<img src=x onerror="alert(1)">본문'

# as_log 항목을 만드는 호출부 전수. 렌더(`|safe`)와 `as_content_html_to_text(
# already_sanitized=True)` 가 "저장된 text 는 이미 sanitize 됐다"를 전제하므로,
# 새 쓰기 경로가 생기면 이 목록이 어긋나 red 되어야 한다.
_AS_LOG_WRITE_CALL_SITES = {
    ("foms/api/cs/as_orders.py", "append_client_log"),  # register(접수 원문) · POST /as/log
    # T14 시스템 이벤트. 본문은 사용자 입력 조립본이라 append_system_log 가 생성 지점에서
    # escape + AS_LOG_TEXT_MAX 절단한다(별도 sanitize 불필요).
    ("foms/api/cs/as_orders.py", "append_system_log"),  # register·schedule·billing·complete
    # T15c 회차 판정 전용 경로 — 사유는 라우트가 sanitize 후 전달, 값 검증은 서비스 소유.
    ("foms/api/cs/as_orders.py", "append_verdict_log"),
    ("foms/api/orders/field_update.py", "append_system_log"),  # 방문일·완료일 정본 쓰기 경로
    # AS-BIND-01 주차 메모. 본문은 서버 리터럴(AS_UPLOAD_PARK_TEXT="첨부 파일")이라
    # 사용자 입력이 섞이지 않는다 — 호출부 sanitize 대상이 아니다.
    ("foms/services/orders/as_upload_anchor.py", "append_client_log"),
    ("foms/services/orders/as_cycle_service.py", "append_system_log"),  # LEGACY_BRIDGE 전환 기록(서버 고정 리터럴)
    # AS-BIND-01 주차 메모. 본문은 고정 리터럴 '첨부 파일' 이고 append_client_log 가 sanitize 한다.
    ("foms/services/orders/as_upload_anchor.py", "append_client_log"),
    ("foms/services/orders/as_log.py", "build_as_log_entry"),  # append_client/system/verdict_log 내부
    ("foms/services/orders/as_log.py", "_legacy_entries_from_content"),  # migrate/lazy legacy
    # 회차 차트 lazy legacy(읽기 전용·비파괴) — 쓰기가 아니라 표시 시점 변환이다.
    ("foms/services/orders/as_round_chart.py", "_legacy_entries_from_content"),
    ("foms/services/orders/as_log.py", 'as_log"].append'),  # 원시 append = 정본 생성지점 3곳뿐(client/system/verdict)
}


def test_as_log_write_call_sites_are_the_known_set():
    """as_log 쓰기 경로가 늘면 red — 새 경로도 sanitize 를 지나는지 확인하고 목록을 갱신할 것."""
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    pattern = re.compile(
        r"(?<!def )\b(append_client_log|append_system_log|append_verdict_log|build_as_log_entry"
        r"|_legacy_entries_from_content"
        r"|as_log[\"']\]\s*\.append)\s*\("  # 헬퍼 우회 원시 append 도 red
    )
    found = {
        (path.relative_to(root).as_posix(), match.group(1))
        for path in root.glob("foms/**/*.py")
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()
        for match in pattern.finditer(line)
    }

    assert found == _AS_LOG_WRITE_CALL_SITES


def test_as_log_write_paths_all_sanitize(client):
    """쓰기 4경로(register·POST·PATCH·migrate)가 전부 sanitize 를 지난다."""
    user_id = _login_as_admin(client, username="as-contract-sanitize")
    order = _create_as_order(shipment_extra={"as_content": _XSS_PAYLOAD}, as_content_2=None)
    order_id = order.id

    # (1) POST /as/log — 이 append 가 (2) migrate(legacy 영구화)를 함께 태운다
    res = client.post(
        f"/api/orders/{order_id}/as/log", json={"type": "memo", "text": _XSS_PAYLOAD}
    )
    assert res.status_code == 200
    memo_id = res.get_json()["entry"]["id"]

    # (3) PATCH /as/log/<id>
    res = client.patch(
        f"/api/orders/{order_id}/as/log/{memo_id}", json={"text": _XSS_PAYLOAD}
    )
    assert res.status_code == 200

    # (4) POST /as/register — 접수 원문
    res = client.post(
        f"/api/orders/{order_id}/as/register", json={"as_content": _XSS_PAYLOAD}
    )
    assert res.status_code == 200

    db_session.expire_all()
    log = db_session.get(Order, order_id).structured_data["shipment"]["as_log"]
    by_kind = {
        "memo": [e for e in log if e.get("id") == memo_id],
        "legacy": [e for e in log if e.get("legacy") is True],
        "reception": [e for e in log if e.get("type") == "reception"],
    }
    for kind, entries in by_kind.items():
        assert entries, f"{kind} 항목이 없다 — 경로가 안 돌았다"
        for entry in entries:
            assert "onerror" not in entry["text"], kind
            assert "<img" not in entry["text"], kind
            assert "본문" in entry["text"], kind
    assert user_id  # 작성자 판정 경로(PATCH 403 가드)가 실제로 로그인 사용자를 썼다


def test_append_system_log_escapes_text():
    """system 문구는 사용자 입력 조립본이라 생성 지점에서 escape 한다(렌더는 |safe)."""
    from foms.services.orders.as_log import append_system_log

    sd = {"shipment": {}}
    entry = append_system_log(sd, text=_XSS_PAYLOAD + " <b>굵게</b>")

    assert "<img" not in entry["text"]
    assert "<b>" not in entry["text"]
    assert "&lt;img" in entry["text"] and "&lt;b&gt;" in entry["text"]
    assert "본문" in entry["text"]


def test_search_still_finds_legacy_as_content(client):
    """legacy as_content 검색은 유지된다(as_log 확장이 기존 경로를 덮지 않는다)."""
    _login_as_admin(client, username="as-contract-search-2")
    _create_as_order(
        customer_name="레거시검색대상",
        shipment_extra={"as_content": "<div>경첩 파손</div>"},
        as_content_2=None,
    )
    _create_as_order(customer_name="레거시제외대상", as_content_2=None)

    res = client.get("/erp/as?q=경첩파손")

    assert res.status_code == 200
    body = res.get_data(as_text=True)
    assert "레거시검색대상" in body
    assert "레거시제외대상" not in body
