"""감사 기록 고객 개인정보 가림 계약 (AUDIT-PII-00).

설계: ``docs/specs/2026-10-19-audit-log-masking_SPEC.md``.

``security_logs`` 에 고객 전화·주소·이름이 원문으로 남던 구멍(2026-08-07 운영 실측: 메시지 12.6% 에
전화번호, 11.8% 에 주소)을 **기록을 쓰는 한 지점**에서 막는다. 여기서 고정하는 것:

1. 저장 길 네 개(``log_access``·직접 ``SecurityLog``·``write_security_log_detached``·
   ``record_access_denied``)가 모두 같은 가림을 지난다.
2. 남겨야 할 것은 남는다 — 주문 번호, 바뀐 칸 라벨, 직원·발주사 연락처, 대표번호, 식별자 키.
3. 변경 전후값(JSON ``detail``)도 가려진다.
4. 감사 화면은 살아 있는 주문의 현재 이름을 보여 주고, 이름 검색도 된다.
5. 래칫 — ORM 훅을 거치지 않고 ``security_logs`` 에 쓰는 곳이 새로 생기면 실패한다.

테스트 데이터는 무해 표지 ``CLAUDE-TEST-`` 와 가짜 번호(``010-0000-…``)만 쓴다.
"""

from __future__ import annotations

import ast
import itertools
import pathlib
import re
from collections import Counter
from datetime import date

import pytest
from sqlalchemy import event
from werkzeug.security import generate_password_hash

import models
from db import db_session
from foms.services import audit_masking, audit_writer
from foms.services.audit_masking import (
    MASK_FAILED_MESSAGE,
    mask_address,
    mask_person_name,
    mask_security_log_values,
)
from foms.web.auth.routes import log_access
from models import Order, SecurityLog, User

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_counter = itertools.count(1)

_NAME = "CLAUDE-TEST-고객"
_PHONE_OLD = "010-0000-1234"
_PHONE_NEW = "010-0000-5678"
_ADDR_OLD = "서울특별시 강남구 테스트로 1"
_ADDR_NEW = "경기도 성남시 분당구 가상로 235"
_STAFF_PHONE = "01000001111"
_COMPANY_PHONE = "1566-0000"


@pytest.fixture(autouse=True)
def _audit_isolation():
    """dedupe 캐시는 프로세스 전역이다 — 테스트마다 비워 격리한다."""
    audit_writer.reset_dedupe_cache()
    yield
    audit_writer.reset_dedupe_cache()


def _make_user(*, role: str = "ADMIN") -> int:
    n = next(_counter)
    user = User(username=f"claude-test-mask-{n}", password=generate_password_hash("pw"),
                role=role, name=f"CLAUDE-TEST-직원{n}", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user.id


def _make_order(*, customer_name: str = _NAME) -> int:
    order = Order(received_date=date.today().isoformat(), customer_name=customer_name,
                  phone=_PHONE_OLD, address=_ADDR_OLD, product="CLAUDE-TEST-붙박이장",
                  status="RECEIVED", is_erp_order=True, erp_stage_code="RECEIVED",
                  structured_data={"workflow": {"stage": "RECEIVED"}})
    db_session.add(order)
    db_session.commit()
    return order.id


def _last_log() -> SecurityLog:
    db_session.expire_all()
    return db_session.query(SecurityLog).order_by(SecurityLog.id.desc()).first()


def _blob(row: SecurityLog) -> str:
    return f"{row.message or ''} {row.detail or ''}"


def _assert_no_customer_pii(row: SecurityLog) -> None:
    blob = _blob(row)
    for raw in (_PHONE_OLD, _PHONE_NEW, "01000001234", "01000005678", "테스트로 1", "가상로 235", _NAME):
        assert raw not in blob, f"원문이 남았다: {raw!r} in {blob!r}"


# --------------------------------------------------------------------------- #
# 1. 저장 길 네 개가 모두 가린다
# --------------------------------------------------------------------------- #
def _order_edit_message(order_id: int) -> str:
    return (f"주문 #{order_id} ({_NAME}) 수정 - 담당자: CLAUDE-TEST-직원 (ID: 1) | 변경내용: "
            f"전화번호: {_PHONE_OLD} ⇒ {_PHONE_NEW}; 주소: {_ADDR_OLD} ⇒ {_ADDR_NEW}")


def test_log_access_masks_phone_address_and_name(app):
    """``log_access``(ORM 훅) — 문장의 전화·주소·고객명이 가려지고 주문 번호·라벨은 남는다."""
    order_id = _make_order()
    with app.app_context():
        log_access(_order_edit_message(order_id), None, action="ORDER_FIELD_UPDATED",
                   target_type="order", target_id=order_id, detail={"customer_name": _NAME})

    row = _last_log()
    _assert_no_customer_pii(row)
    assert row.message.startswith(f"주문 #{order_id} ({mask_person_name(_NAME)}) 수정")
    assert "전화번호: 010****1234 ⇒ 010****5678" in row.message
    assert "주소: 서울특별시 강남구 *** ⇒ 경기도 성남시 분당구 ***" in row.message
    assert row.detail["customer_name"] == mask_person_name(_NAME)
    assert row.target_id == order_id and row.action == "ORDER_FIELD_UPDATED"


def test_direct_orm_security_log_is_masked(app):
    """``db.add(SecurityLog(...))`` 직접 쓰기(27곳)도 같은 훅을 지난다 — 호출부 수정 없이."""
    order_id = _make_order()
    db_session.add(SecurityLog(user_id=None, message=_order_edit_message(order_id),
                               action="ORDER_FIELD_UPDATED", target_type="order", target_id=order_id))
    db_session.commit()

    row = _last_log()
    _assert_no_customer_pii(row)
    assert f"주문 #{order_id} (" in row.message


def test_detached_core_writer_is_masked(app):
    """Core insert 길(``write_security_log_detached``)도 같은 함수를 부른다."""
    order_id = _make_order()
    assert audit_writer.write_security_log_detached(
        _order_edit_message(order_id), None, action="ORDER_FIELD_UPDATED",
        target_type="order", target_id=order_id,
        detail={"customer_name": _NAME, "note": f"고객 번호 {_PHONE_OLD}"},
    )
    row = _last_log()
    _assert_no_customer_pii(row)
    assert row.detail["note"] == "고객 번호 010****1234"


def test_record_access_denied_is_masked(app):
    """접근거부 기록(dedupe 후 Core 길)도 가려진다."""
    assert audit_writer.record_access_denied(
        f"권한 거부: CLAUDE-TEST 메모 {_PHONE_NEW}", user_id=None, ip="127.0.0.1",
        endpoint="claude_test.endpoint", action="policy:CLAUDE-TEST",
        structured_action="ACCESS_DENIED", detail={"memo": f"{_ADDR_OLD} 방문"},
    )
    row = _last_log()
    _assert_no_customer_pii(row)
    assert "010****5678" in row.message
    assert row.detail["memo"] == "서울특별시 강남구 *** 방문"


# --------------------------------------------------------------------------- #
# 2. 남겨야 할 것은 남는다
# --------------------------------------------------------------------------- #
def test_staff_contact_row_is_left_untouched(app):
    """직원 대상 행(``target_type='user'``) — 직원 발신번호 변경은 고객 정보가 아니라 그대로 남는다."""
    message = f"사용자 #5 수정: sender_phone {_STAFF_PHONE}→01000002222"
    detail = {"changes": {"sender_phone": {"from": _STAFF_PHONE, "to": "01000002222"}}}
    with app.app_context():
        log_access(message, None, action="USER_UPDATE", target_type="user", target_id=5, detail=detail)

    row = _last_log()
    assert row.message == message
    assert row.detail == detail


def test_order_number_labels_company_numbers_and_ids_survive(app):
    """주문 번호·바뀐 칸 라벨·발주사 연락처·대표번호·식별자 키는 가리지 않는다."""
    order_id = _make_order()
    message = (f"주문 #{order_id} ({_NAME}) — 주문 저장: 전체 저장 · 발주사 연락처 02-0000-0000 → "
               f"{_COMPANY_PHONE} · 실측일 2026-10-01 → 2026-10-19")
    detail = {"storage_key": f"orders/{order_id}/01000001234.png", "change_set": "claude-test-01000001234",
              "changes": [{"path": "parties.orderer.phone", "before": "02-0000-0000", "after": _COMPANY_PHONE}]}
    db_session.add(SecurityLog(message=message, action="ORDER_STRUCTURED_SAVED", target_type="order",
                               target_id=order_id, detail=detail))
    db_session.commit()

    row = _last_log()
    assert f"주문 #{order_id} ({mask_person_name(_NAME)})" in row.message
    assert f"발주사 연락처 02-0000-0000 → {_COMPANY_PHONE}" in row.message
    assert "실측일 2026-10-01 → 2026-10-19" in row.message
    assert row.detail["storage_key"] == detail["storage_key"]
    assert row.detail["change_set"] == detail["change_set"]
    assert row.detail["changes"][0]["before"] == "02-0000-0000"


def test_empty_markers_and_dates_are_not_masked():
    """빈 값 표기와 날짜 괄호는 이름·번호가 아니다."""
    message, _ = mask_security_log_values(
        "주문 #3 (2026-10-19) — 전화번호: (없음) → 010-0000-0000", None, target_type="order")
    assert message == "주문 #3 (2026-10-19) — 전화번호: (없음) → 010****0000"


# --------------------------------------------------------------------------- #
# 3. 변경 전후값(JSON) 도 가린다
# --------------------------------------------------------------------------- #
def test_structured_change_values_in_detail_are_masked(app):
    """``detail.changes[]`` 의 고객 칸 before/after 와 평면 ``field/before/after`` 가 가려진다."""
    order_id = _make_order()
    detail = {
        "customer_name": _NAME,
        "changes": [
            {"path": "parties.customer.phone", "before": _PHONE_OLD, "after": _PHONE_NEW},
            {"path": "parties.customer.name", "before": _NAME, "after": "CLAUDE-TEST-새고객"},
            {"path": "site.address_full", "before": _ADDR_OLD, "after": _ADDR_NEW},
            {"path": "site.address_detail", "before": "CLAUDE-TEST 101동 1001호", "after": ""},
            {"path": "schedule.measurement.date", "before": "2026-10-01", "after": "2026-10-19"},
        ],
    }
    message = (f"주문 #{order_id} ({_NAME}) — 주문 저장: 전체 저장 · 전화번호 {_PHONE_OLD} → "
               f"{_PHONE_NEW} · 주소 {_ADDR_OLD} → {_ADDR_NEW} 외 3건")
    db_session.add(SecurityLog(message=message, action="ORDER_STRUCTURED_SAVED", target_type="order",
                               target_id=order_id, detail=detail))
    db_session.commit()

    row = _last_log()
    _assert_no_customer_pii(row)
    changes = {c["path"]: c for c in row.detail["changes"]}
    assert (changes["parties.customer.phone"]["before"], changes["parties.customer.phone"]["after"]) == (
        "010****1234", "010****5678")
    assert changes["parties.customer.name"]["after"] == mask_person_name("CLAUDE-TEST-새고객")
    assert changes["site.address_full"]["before"] == "서울특별시 강남구 ***"
    assert changes["site.address_detail"] == {"path": "site.address_detail", "before": "***", "after": ""}
    assert changes["schedule.measurement.date"]["after"] == "2026-10-19"
    assert "전화번호 010****1234 → 010****5678" in row.message
    assert "주소 서울특별시 강남구 *** → 경기도 성남시 분당구 ***" in row.message


def test_flat_field_change_detail_is_masked():
    """평면 칼럼 변경(``field/before/after``)도 칸 이름으로 가린다."""
    _, detail = mask_security_log_values(
        "주문 #4 — 주소: A → B",
        {"field": "address", "before": _ADDR_OLD, "after": _ADDR_NEW, "change_set": "x"},
        target_type="order")
    assert detail == {"field": "address", "before": "서울특별시 강남구 ***",
                      "after": "경기도 성남시 분당구 ***", "change_set": "x"}


def test_order_edit_form_route_stores_masked_message(client):
    """실제 라우트 — 주문 수정 폼(``edit.py``)으로 전화·주소를 바꾸면 저장된 문장에 원문이 없다."""
    with client.session_transaction() as sess:
        sess["user_id"] = _make_user()
    order_id = _make_order()

    resp = client.post(f"/edit/{order_id}", data={"customer_name": _NAME, "phone": _PHONE_NEW,
                                                  "address": _ADDR_NEW}, follow_redirects=False)
    assert resp.status_code in (200, 302), resp.get_data(as_text=True)[:300]

    db_session.expire_all()
    row = (db_session.query(SecurityLog)
           .filter(SecurityLog.action == "ORDER_FIELD_UPDATED", SecurityLog.target_id == order_id)
           .order_by(SecurityLog.id.desc()).first())
    assert row is not None
    _assert_no_customer_pii(row)
    assert f"주문 #{order_id} ({mask_person_name(_NAME)}) 수정" in row.message
    # 바뀐 칸 이름과 가린 전후값은 남는다 — "어느 칸이 바뀌었나" 는 감사에서 읽혀야 한다.
    assert "전화번호: 010****1234 ⇒ 010****5678" in row.message, row.message
    assert "주소: 서울특별시 강남구 *** ⇒ 경기도 성남시 분당구 ***" in row.message, row.message


# --------------------------------------------------------------------------- #
# 4. 멱등·실패·규칙 단위
# --------------------------------------------------------------------------- #
def test_masking_is_idempotent():
    """두 번 가려도 같다 — ``before_update`` 로 다시 지나도 안전하다."""
    once = mask_security_log_values(_order_edit_message(9), {"customer_name": _NAME}, target_type="order")
    twice = mask_security_log_values(*once, target_type="order")
    assert once == twice


def test_mask_failure_stores_marker_not_original(app, monkeypatch):
    """가림 함수가 터지면 원문 대신 표식을 저장한다 — 업무 트랜잭션도 살아 있다."""
    def _boom(*_args, **_kwargs):
        raise RuntimeError("CLAUDE-TEST 가림 오류")

    monkeypatch.setattr(audit_masking, "_mask_message", _boom)
    order_id = _make_order()
    db_session.add(SecurityLog(message=_order_edit_message(order_id), target_type="order",
                               target_id=order_id))
    db_session.commit()

    row = _last_log()
    assert row.message == MASK_FAILED_MESSAGE
    assert row.detail == {"mask_failed": True}
    assert row.target_id == order_id


def test_rule_units():
    """규칙 단위 — 성만 남기기·시·구까지·전화 가운데 자리."""
    assert mask_person_name("CLAUDE-TEST-가") == "C" + "*" * (len("CLAUDE-TEST-가") - 1)
    assert mask_person_name("홍길동") == "홍**" and mask_person_name("홍**") == "홍**"
    assert mask_address(_ADDR_OLD) == "서울특별시 강남구 ***"
    assert mask_address("CLAUDE-TEST 101동") == "***"
    assert mask_address("서울특별시 강남구") == "서울특별시 강남구"
    assert audit_masking.mask_phone_text(f"연락 {_PHONE_OLD} / 01000005678") == "연락 010****1234 / 010****5678"
    assert audit_masking.mask_phone_text(f"대표 {_COMPANY_PHONE}") == f"대표 {_COMPANY_PHONE}"
    # 문장 요약(60자 말줄임)에 잘린 번호도 앞 3자리만 남긴다.
    assert audit_masking.mask_phone_text("메모 010-0000-56…") == "메모 010-****-**…"


def test_estimate_saved_note_name_is_masked():
    """견적 저장 꼬리말(견적 고객명)도 가린다 — ``describe_action(note=고객명)`` 형태."""
    message, _ = mask_security_log_values(f"견적 #3 — 견적 저장: {_NAME}", {"estimate_id": 3},
                                          target_type="wdc_estimate", action="ESTIMATE_SAVED")
    assert message == f"견적 #3 — 견적 저장: {mask_person_name(_NAME)}"


# --------------------------------------------------------------------------- #
# 5. 감사 화면 — 현재 이름으로 보이고, 이름으로 찾힌다
# --------------------------------------------------------------------------- #
def test_admin_screen_shows_live_name_and_search_by_name_finds_masked_row(client, app):
    """원장은 ``(C***…)`` 로 가려 저장되지만 화면은 주문 표의 현재 이름을 붙이고 이름 검색도 된다."""
    with client.session_transaction() as sess:
        sess["user_id"] = _make_user()
    order_id = _make_order()
    with app.app_context():
        log_access(f"주문 #{order_id} ({_NAME}) — CLAUDE-TEST 시공 시작", None,
                   action="CONSTRUCTION_STARTED", target_type="order", target_id=order_id,
                   detail={"customer_name": _NAME})
        log_access("CLAUDE-TEST 다른 행", None, action="LOGIN_OK")
    db_session.expire_all()
    stored = db_session.query(SecurityLog).filter(SecurityLog.action == "CONSTRUCTION_STARTED").one()
    assert _NAME not in _blob(stored), "원장에는 이름이 가려져 있어야 한다"

    body = client.get(f"/security_logs?search={_NAME}").get_data(as_text=True)
    assert "CLAUDE-TEST 시공 시작" in body, "이름 검색이 가려 저장된 행을 못 찾았다"
    assert "CLAUDE-TEST 다른 행" not in body
    # 화면은 ``주문 #N`` 을 링크로 감싼다(order_link 필터) — 링크 뒤에 현재 이름이 붙어야 한다.
    assert f"주문 #{order_id}</a> ({_NAME})" in body, "화면이 현재 이름을 다시 붙이지 않았다"


# --------------------------------------------------------------------------- #
# 6. 래칫 — ORM 훅을 거치지 않고 security_logs 에 쓰는 곳
# --------------------------------------------------------------------------- #
#: 허용 목록. Core 길은 같은 가림 함수를 직접 부르고, 운영 도구 2곳은 앱을 import 하지 않는
#: 독립 스크립트라 문장에 고객 필드를 싣지 않는다(아래 별도 테스트가 강제).
_ALLOWED_BYPASS = Counter({
    ("foms/services/audit_writer.py", "core_insert"): 1,
    ("tools/ops/bulk_complete_past_construction_core.py", "raw_sql_insert"): 1,
    ("tools/ops/data_doctor.py", "raw_sql_insert"): 1,
})
_SCAN_DIRS = ("foms", "scripts", "tools", "migrations")
_RAW_INSERT_RE = re.compile(r"INSERT\s+INTO\s+security_logs\b", re.IGNORECASE)
_RAW_UPDATE_RE = re.compile(r"UPDATE\s+security_logs\s+SET\b", re.IGNORECASE)


def _scan_files() -> list[pathlib.Path]:
    files = [p for d in _SCAN_DIRS for p in (_REPO_ROOT / d).rglob("*.py")]
    files += [p for p in _REPO_ROOT.glob("*.py")]
    return [p for p in files if "__pycache__" not in p.parts]


def _is_security_log(node: ast.AST) -> bool:
    """``SecurityLog`` 또는 ``SecurityLog.__table__`` 을 가리키는 식인가."""
    if isinstance(node, ast.Name):
        return node.id == "SecurityLog"
    return isinstance(node, ast.Attribute) and node.attr == "__table__" and _is_security_log(node.value)


def _chain_has_security_log_query(node: ast.AST) -> bool:
    """``query(SecurityLog)…`` 체인 위에서 부른 호출인가."""
    while isinstance(node, (ast.Call, ast.Attribute)):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "query" and node.args and _is_security_log(node.args[0]):
                return True
            node = func
        else:
            node = node.value
    return False


def _bypass_writes(path: pathlib.Path) -> list[str]:
    source = path.read_text(encoding="utf-8", errors="replace")
    kinds = ["raw_sql_insert"] * len(_RAW_INSERT_RE.findall(source))
    kinds += ["raw_sql_update"] * len(_RAW_UPDATE_RE.findall(source))
    if "SecurityLog" not in source:
        return kinds
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return kinds
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name in ("insert", "update") and isinstance(func, ast.Attribute) and _is_security_log(func.value):
            kinds.append(f"core_{name}")  # SecurityLog.__table__.insert()
        elif name in ("insert", "update") and node.args and _is_security_log(node.args[0]):
            kinds.append(f"core_{name}")  # insert(SecurityLog) / update(SecurityLog)
        elif name in ("bulk_insert_mappings", "bulk_update_mappings") and node.args and _is_security_log(node.args[0]):
            kinds.append("bulk_mappings")
        elif name == "bulk_save_objects":
            kinds.append("bulk_save_objects")  # 이 파일이 SecurityLog 를 만지므로 의심 — 허용 목록 등재 필요.
        elif name == "update" and isinstance(func, ast.Attribute) and _chain_has_security_log_query(func.value):
            kinds.append("query_update")
    return kinds


def test_no_security_log_write_bypasses_the_masking_point():
    """ORM 훅·Core 가림을 거치지 않는 쓰기가 허용 목록과 **정확히** 같아야 한다.

    새 우회가 생기면(raw SQL·``insert(SecurityLog)``·bulk·query-level update) 실패한다.
    해결은 ``log_access``/``SecurityLog(...)``/``write_security_log_detached`` 로 쓰는 것이다.
    """
    found: Counter = Counter()
    for path in _scan_files():
        rel = path.relative_to(_REPO_ROOT).as_posix()
        for kind in _bypass_writes(path):
            found[(rel, kind)] += 1
    assert found == _ALLOWED_BYPASS, (
        f"허용 목록 밖 우회 쓰기: {dict(found - _ALLOWED_BYPASS)} · 사라진 허용 항목: "
        f"{dict(_ALLOWED_BYPASS - found)}"
    )


def test_bypass_scanner_catches_a_new_raw_insert(tmp_path):
    """음성 대조 — 스캐너가 실제로 우회를 잡는다(빈 스캐너가 초록을 내지 않게)."""
    sample = tmp_path / "claude_test_bypass.py"
    sample.write_text(
        "from models import SecurityLog\n"
        "def f(conn, s, rows):\n"
        "    conn.execute(SecurityLog.__table__.insert().values(message='x'))\n"
        "    s.bulk_insert_mappings(SecurityLog, rows)\n"
        "    s.query(SecurityLog).filter(SecurityLog.id == 1).update({'message': 'y'})\n"
        "    conn.execute('INSERT INTO security_logs(message) VALUES (1)')\n",
        encoding="utf-8",
    )
    assert sorted(_bypass_writes(sample)) == sorted(
        ["core_insert", "bulk_mappings", "query_update", "raw_sql_insert"])


def test_standalone_ops_tools_do_not_put_customer_fields_in_raw_audit_rows():
    """허용된 raw SQL 2곳은 가림 함수를 못 지나므로 문장·detail 에 고객 필드를 싣지 않는다."""
    for rel, _kind in _ALLOWED_BYPASS:
        if not rel.startswith("tools/"):
            continue
        source = (_REPO_ROOT / rel).read_text(encoding="utf-8")
        start = _RAW_INSERT_RE.search(source).start()
        statement = source[start:source.find("return", start)]
        for field in ("customer_name", "phone", "address"):
            assert field not in statement, f"{rel}: raw 감사 INSERT 에 {field} 가 실렸다"


def test_orm_masking_hook_is_registered():
    """ORM 길의 한 지점(훅)이 실제로 등록돼 있다 — 지워지면 직접 ``db.add`` 27곳이 원문을 쓴다."""
    assert event.contains(SecurityLog, "before_insert", models._mask_security_log_pii)
    assert event.contains(SecurityLog, "before_update", models._mask_security_log_pii)
