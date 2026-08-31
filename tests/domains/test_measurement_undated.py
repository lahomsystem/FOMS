"""실측일 미정 기능 — 판정·SQL 모집단·HTTP 계약 테스트.

핵심 회귀축 3가지:
1. '추후통보'/'미정' 같은 텍스트 실측일은 반드시 '미정'으로 잡혀야 한다
   (날짜 축 SQL 선스코프를 쓰면 이 목표군이 통째로 빠진다).
2. SQL ``NOT IN`` 은 NULL 을 통과시키지 않는다 — ``erp_stage_code`` 가 NULL 인
   비ERP 주문이 조용히 전량 탈락하지 않는지 고정한다.
3. 전수 대조 — 반환 id 집합 == 기대 id 집합 등호 assert 로 포함(양성)과
   배제(음성 대조군)를 같은 단언으로 동시에 확인한다.
"""

from __future__ import annotations

from urllib.parse import urlparse, parse_qs

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderScheduleDate, User

from foms.services.measurement_undated import (
    MEASUREMENT_UNDATED_DISPLAY_CAP,
    MEASUREMENT_UNDATED_SCAN_LIMIT,
    apply_measurement_undated_sql_scope,
    build_measurement_undated_payload,
    build_measurement_undated_row,
    is_measurement_undated,
    resolve_manager_name,
)

UNDATED_API = "/api/erp/measurement/undated"


# ---------------------------------------------------------------- 공용 헬퍼

def _login_admin(client):
    """세션 직접 주입 로그인 (tests/domains/test_measurement_route_eta.py 관례)."""
    user = User(
        username="undated_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="Undated Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _mk(**kw) -> Order:
    """주문 1건 생성 후 커밋. 필수 NOT NULL 컬럼은 기본값으로 채운다."""
    payload = {
        "received_date": "2026-08-12",
        "customer_name": "미정 고객",
        "phone": "010-1111-2222",
        "address": "서울특별시 강남구 테헤란로 1",
        "product": "붙박이장",
    }
    payload.update(kw)
    order = Order(**payload)
    db_session.add(order)
    db_session.commit()
    return order


def _sched(order: Order, kind: str, date: str, source: str = "beta_schedule") -> None:
    """order_schedule_dates 행 1건 추가 (실측일 SSOT read model)."""
    db_session.add(
        OrderScheduleDate(order_id=order.id, kind=kind, date=date, source=source)
    )
    db_session.commit()
    db_session.refresh(order)


def _rows(resp) -> list:
    return resp.get_json()["data"]["rows"]


def _ids(resp) -> set:
    return {row["id"] for row in _rows(resp)}


# ================================================================ A군. 판정 함수
# 양성(미정)과 음성(날짜 있음) 대조군을 같은 표에서 둘 다 세운다.

def test_undated_when_measurement_date_is_empty_string(app):
    assert is_measurement_undated(_mk(measurement_date="")) is True


def test_undated_when_measurement_date_is_none(app):
    assert is_measurement_undated(_mk(measurement_date=None)) is True


def test_undated_when_measurement_date_is_future_notice_text(app):
    """핵심 목표군 — '추후통보' 는 컬럼에 실제로 들어 있고 정규화에서만 탈락한다."""
    assert is_measurement_undated(_mk(measurement_date="추후통보")) is True


def test_undated_when_measurement_date_is_tbd_text(app):
    assert is_measurement_undated(_mk(measurement_date="미정")) is True


def test_not_undated_when_legacy_column_has_real_date(app):
    """음성 대조군 — 날짜가 있는 비ERP 주문은 미정이 아니다."""
    assert is_measurement_undated(_mk(measurement_date="2026-09-01")) is False


def test_not_undated_when_erp_schedule_has_real_date(app):
    order = _mk(
        is_erp_order=True,
        structured_data={"schedule": {"measurement": {"date": "2026-09-01"}}},
    )
    assert is_measurement_undated(order) is False


def test_undated_when_erp_schedule_date_is_future_notice_text(app):
    order = _mk(
        is_erp_order=True,
        structured_data={"schedule": {"measurement": {"date": "추후통보"}}},
    )
    assert is_measurement_undated(order) is True


def test_not_undated_when_erp_item_has_measurement_date(app):
    """schedule 없이 items[].measurement_date 만 있어도 날짜가 있는 것이다."""
    order = _mk(
        is_erp_order=True,
        structured_data={"items": [{"measurement_date": "2026-09-02"}]},
    )
    assert is_measurement_undated(order) is False


def test_not_undated_when_schedule_dates_relation_has_measurement(app):
    order = _mk(measurement_date=None)
    _sched(order, "measurement", "2026-09-03")
    assert is_measurement_undated(order) is False


def test_undated_when_only_construction_schedule_date_exists(app):
    """시공일만 있는 건은 실측일이 없는 것이므로 미정이다."""
    order = _mk(measurement_date=None)
    _sched(order, "construction", "2026-09-03")
    assert is_measurement_undated(order) is True


def test_not_undated_when_erp_schedule_date_is_comma_multi(app):
    """완료일·실측일은 콤마 복수 표기가 정본이다 (싱크 컬럼=첫 날짜만 함정)."""
    order = _mk(
        is_erp_order=True,
        structured_data={
            "schedule": {"measurement": {"date": "2026-09-01, 2026-09-02"}}
        },
    )
    assert is_measurement_undated(order) is False


# ============================================== B군. SQL 모집단 (상위집합 술어)

def _scope_ids() -> set:
    """apply_measurement_undated_sql_scope 통과 id 집합."""
    query = apply_measurement_undated_sql_scope(db_session.query(Order))
    return {row.id for row in query.all()}


def test_sql_scope_includes_in_progress_and_excludes_finished(app):
    """포함/배제를 한 등호 assert 로 동시에 고정한다 (전수 대조)."""
    include = {
        # 접수 단계 — 아직 실측 전
        _mk(status="RECEIVED", erp_stage_code=None, is_erp_order=True).id,
        # 실측 진행 중
        _mk(status="MEASURE", erp_stage_code="MEASURE", is_erp_order=True).id,
        # 보류는 아직 진행 중이다
        _mk(status="ON_HOLD").id,
        # 자가실측 대기
        _mk(status="SELF_MEASUREMENT", is_self_measurement=True).id,
        # NULL 함정 회귀축: 비ERP 주문은 erp_stage_code 가 영원히 NULL 이다.
        # `~col.in_([...])` 만 쓰면 이 건이 조용히 탈락한다.
        _mk(status="RECEIVED", is_erp_order=False, erp_stage_code=None).id,
        # status 를 명시적으로 None 으로 넣어도 ORM 컬럼 default 가 적용된다
        # (실제 SQL NULL 이 되지는 않는다 — 그래도 예외 없이 통과해야 한다).
        _mk(status=None).id,
    }

    exclude = {
        _mk(status="COMPLETED").id,
        _mk(status="MEASURED").id,
        _mk(status="REGIONAL_MEASURED", is_regional=True).id,
        _mk(status="SELF_MEASURED", is_self_measurement=True).id,
        _mk(status="SCHEDULED").id,
        _mk(status="SHIPPED_PENDING").id,
        _mk(status="AS_COMPLETED").id,
        _mk(status="AS_RECEIVED").id,
        _mk(status="DELETED").id,
        _mk(status="MEASURE", deleted_at="2026-08-01 10:00:00").id,
        _mk(status="MEASURE", is_erp_order=True, erp_stage_code="DRAWING").id,
        # sync 가 workflow.stage 원문을 그대로 복사해 한글 라벨이 실제로 들어온다
        _mk(status="MEASURE", is_erp_order=True, erp_stage_code="도면").id,
        # JSON 따옴표 변형
        _mk(status="MEASURE", is_erp_order=True, erp_stage_code='"COMPLETED"').id,
        # ERP draft (active_filter)
        _mk(
            status="MEASURE",
            is_erp_order=True,
            structured_data={"meta": {"draft": True}},
        ).id,
        _mk(status="DRAFT", is_erp_order=True).id,
    }

    got = _scope_ids()
    assert got == include, f"기대={sorted(include)} 실제={sorted(got)} 초과={sorted(got - include)}"
    assert not (got & exclude)


# ================================================ C군. 자가실측 4체크 제외

def test_self_measurement_four_checks_done_is_excluded(client):
    """4체크 완료 자가실측 건은 실측일이 없어도 목록에서 빠진다."""
    _login_admin(client)
    done = _mk(
        customer_name="자가완료",
        status="SELF_MEASUREMENT",
        is_self_measurement=True,
        measurement_date="",
        measurement_completed=True,
        regional_sales_order_upload=True,
        regional_blueprint_sent=True,
        regional_order_upload=True,
    )
    partial = _mk(
        customer_name="자가진행",
        status="SELF_MEASUREMENT",
        is_self_measurement=True,
        measurement_date="",
        measurement_completed=True,
        regional_sales_order_upload=True,
        regional_blueprint_sent=True,
        regional_order_upload=False,
    )
    done_id, partial_id = done.id, partial.id

    resp = client.get(UNDATED_API)
    assert resp.status_code == 200
    got = _ids(resp)
    assert partial_id in got, "4체크 중 하나라도 미완이면 포함되어야 한다"
    assert done_id not in got, "4체크 완료 자가실측은 제외되어야 한다"


# ================================================ D군. HTTP 엔드포인트

def test_undated_api_requires_login(client):
    """미인증 요청이 200 JSON success 를 주면 안 된다."""
    resp = client.get(UNDATED_API)
    if resp.status_code == 200:
        payload = resp.get_json(silent=True)
        assert not (isinstance(payload, dict) and payload.get("success") is True), (
            "login_required 없이 데이터가 노출되었다"
        )
    else:
        assert resp.status_code in (301, 302, 401, 403)


def test_undated_api_payload_shape(client):
    _login_admin(client)
    _mk(status="MEASURE", measurement_date="추후통보")

    resp = client.get(UNDATED_API)
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    data = payload["data"]
    for key in ("rows", "count", "total", "truncated", "scan_capped", "display_cap"):
        assert key in data, f"data.{key} 누락"
    assert data["count"] == len(data["rows"])
    assert data["display_cap"] == MEASUREMENT_UNDATED_DISPLAY_CAP
    assert data["truncated"] is False
    assert data["scan_capped"] is False
    assert MEASUREMENT_UNDATED_SCAN_LIMIT > MEASUREMENT_UNDATED_DISPLAY_CAP


def test_undated_api_exhaustive_set_equality(client):
    """전수 대조 — 날짜 있는 5건은 배제, 미정 3건만 반환."""
    _login_admin(client)

    dated = [
        _mk(customer_name="날짜A", status="MEASURE", measurement_date="2026-09-01").id,
        _mk(customer_name="날짜B", status="RECEIVED", measurement_date="2026-09-02").id,
        _mk(
            customer_name="날짜C",
            status="MEASURE",
            is_erp_order=True,
            structured_data={"schedule": {"measurement": {"date": "2026-09-03"}}},
        ).id,
        _mk(
            customer_name="날짜D",
            status="MEASURE",
            is_erp_order=True,
            structured_data={"items": [{"measurement_date": "2026-09-04"}]},
        ).id,
        _mk(customer_name="날짜E", status="ON_HOLD", measurement_date="2026-09-05").id,
    ]
    undated = [
        _mk(customer_name="미정A", status="MEASURE", measurement_date="추후통보").id,
        _mk(customer_name="미정B", status="RECEIVED", measurement_date="").id,
        _mk(customer_name="미정C", status="MEASURE", measurement_date=None).id,
    ]

    resp = client.get(UNDATED_API)
    assert resp.status_code == 200
    got = _ids(resp)
    assert got == set(undated), (
        f"기대={sorted(undated)} 실제={sorted(got)} "
        f"거짓양성={sorted(got & set(dated))}"
    )
    assert resp.get_json()["data"]["total"] == len(undated)


def test_undated_api_q_filter(client):
    _login_admin(client)
    hit = _mk(customer_name="검색대상홍길동", status="MEASURE", measurement_date="").id
    miss = _mk(customer_name="다른고객", status="MEASURE", measurement_date="미정").id

    resp = client.get(UNDATED_API, query_string={"q": "검색대상"})
    assert resp.status_code == 200
    got = _ids(resp)
    assert got == {hit}, f"기대={{{hit}}} 실제={sorted(got)} (miss={miss})"


def test_undated_api_manager_filter_is_trimmed_and_case_insensitive(client):
    _login_admin(client)
    mine = _mk(
        customer_name="담당매칭", status="MEASURE", measurement_date="", manager_name="김영업"
    ).id
    other = _mk(
        customer_name="담당불일치", status="MEASURE", measurement_date="", manager_name="박담당"
    ).id

    resp = client.get(UNDATED_API, query_string={"manager_filter": " 김영업 "})
    assert resp.status_code == 200
    got = _ids(resp)
    assert got == {mine}, f"기대={{{mine}}} 실제={sorted(got)} (other={other})"


def test_undated_api_edit_url_has_single_question_mark(client):
    """기존 템플릿의 `?return_to=x?open=y` 이중 물음표 버그 복제 방지."""
    _login_admin(client)
    oid = _mk(status="MEASURE", measurement_date="추후통보").id

    resp = client.get(UNDATED_API)
    row = next(r for r in _rows(resp) if r["id"] == oid)
    edit_url = row["edit_url"]

    assert edit_url.count("?") == 1, f"이중 물음표: {edit_url}"
    parsed = urlparse(edit_url)
    assert parsed.path == f"/edit/{oid}", edit_url
    assert parse_qs(parsed.query) == {
        "return_to": ["erp_measurement_dashboard"],
        "open": ["erp-order"],
    }, edit_url


def test_undated_api_row_keys_present(client):
    _login_admin(client)
    _mk(status="MEASURE", measurement_date="추후통보", manager_name="김영업")

    resp = client.get(UNDATED_API)
    row = _rows(resp)[0]
    for key in (
        "id",
        "customer_name",
        "phone",
        "address",
        "manager_name",
        "status_label",
        "received_date",
        "product",
        "is_regional",
        "is_self_measurement",
        "edit_url",
    ):
        assert key in row, f"row.{key} 누락"
    assert isinstance(row["is_regional"], bool)
    assert isinstance(row["is_self_measurement"], bool)


def test_undated_api_status_label_is_never_blank(client):
    _login_admin(client)
    erp_id = _mk(
        customer_name="ERP실측",
        status="MEASURE",
        is_erp_order=True,
        erp_stage_code="MEASURE",
        structured_data={"workflow": {"stage": "MEASURE"}},
        measurement_date="추후통보",
    ).id
    legacy_id = _mk(
        customer_name="비ERP접수", status="RECEIVED", measurement_date="미정"
    ).id

    resp = client.get(UNDATED_API)
    labels = {row["id"]: row["status_label"] for row in _rows(resp)}
    assert labels.get(erp_id), "ERP 행의 status_label 이 비었다"
    assert labels.get(legacy_id), "비ERP 행의 status_label 이 비었다"
    assert labels[erp_id] == "실측"  # STAGE_LABELS['MEASURE']
    assert labels[legacy_id] == "접수"  # STATUS['RECEIVED']


# ================================================ E군. ERP 표시 필드 반영

def test_row_uses_erp_structured_display_fields(client):
    """컬럼값과 structured_data 가 다르면 structured_data 가 이긴다."""
    _login_admin(client)
    oid = _mk(
        customer_name="컬럼고객",
        phone="010-0000-0000",
        address="컬럼주소",
        product="컬럼제품",
        manager_name="컬럼담당",
        status="MEASURE",
        is_erp_order=True,
        erp_stage_code="MEASURE",
        measurement_date="추후통보",
        structured_data={
            "parties": {
                "customer": {"name": "박고객", "phone": "010-9999-8888"},
                "manager": {"name": "이담당"},
            },
            "site": {"address_full": "서울 강남구 삼성로 100"},
            "items": [{"product_name": "슬라이딩장"}],
        },
    ).id

    resp = client.get(UNDATED_API)
    row = next(r for r in _rows(resp) if r["id"] == oid)
    assert row["customer_name"] == "박고객"
    assert row["address"] == "서울 강남구 삼성로 100"
    assert "슬라이딩장" in row["product"]
    assert row["manager_name"] == "이담당"


def test_resolve_manager_name_prefers_structured_then_column(app):
    erp = _mk(
        is_erp_order=True,
        manager_name="컬럼담당",
        structured_data={"parties": {"manager": {"name": "이담당"}}},
    )
    legacy = _mk(manager_name="컬럼담당")
    assert resolve_manager_name(erp) == "이담당"
    assert resolve_manager_name(legacy) == "컬럼담당"


def test_build_measurement_undated_row_returns_contract_keys(app):
    """행 빌더 단위 계약 (url_for 때문에 요청 컨텍스트 안에서 호출)."""
    order = _mk(status="MEASURE", measurement_date="추후통보")
    oid = order.id
    with app.test_request_context("/erp/measurement"):
        row = build_measurement_undated_row(order)
    assert row["id"] == oid
    assert row["edit_url"].startswith(f"/edit/{oid}?")
    assert callable(build_measurement_undated_payload)


# ============================================ E군. 스캔 편향 회귀 (캡 먼저 → 필터 나중)

def test_old_undated_survives_when_scan_backstop_is_small(app, client, monkeypatch):
    """오래된 '미정' 건이 최신 '날짜 있는' 건에 밀려 사라지면 안 된다.

    이 기능의 존재 이유가 '오래 방치된 미정 건 찾기'라, 모집단을 파이썬 판정보다
    먼저 `id DESC LIMIT n` 으로 자르면 상한 예산을 날짜가 이미 있는 최신 주문이
    다 먹고 목표군이 통째로 0건이 된다. 배치 순회로 모집단을 다 훑는지 고정한다.
    """
    import foms.services.measurement_undated as mu

    _login_admin(client)
    old_undated = _mk(status="MEASURE", measurement_date="추후통보").id
    newer_dated = [
        _mk(status="MEASURE", measurement_date="2026-09-0%d" % (i + 1)).id
        for i in range(5)
    ]

    monkeypatch.setattr(mu, "MEASUREMENT_UNDATED_SCAN_BATCH", 2)

    resp = client.get(UNDATED_API)
    assert resp.status_code == 200
    ids = _ids(resp)
    assert old_undated in ids, "오래된 미정 건이 스캔 배치에 밀려 사라졌다"
    assert not (ids & set(newer_dated)), "날짜가 있는 주문이 목록에 새어 들어왔다"
    assert resp.get_json()["data"]["scan_capped"] is False


def test_scan_backstop_marks_scan_capped(app, client, monkeypatch):
    """폭주 backstop 이 실제로 걸리면 그 사실을 응답으로 노출한다(조용한 축소 금지)."""
    import foms.services.measurement_undated as mu

    _login_admin(client)
    for _ in range(6):
        _mk(status="MEASURE", measurement_date="추후통보")

    monkeypatch.setattr(mu, "MEASUREMENT_UNDATED_SCAN_BATCH", 2)
    monkeypatch.setattr(mu, "MEASUREMENT_UNDATED_SCAN_LIMIT", 2)

    resp = client.get(UNDATED_API)
    assert resp.status_code == 200
    assert resp.get_json()["data"]["scan_capped"] is True
