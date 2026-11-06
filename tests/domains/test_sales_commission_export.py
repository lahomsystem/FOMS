"""FCOMM-01 T10 — 영업 수수료 마감 내려받기 CSV(``GET /api/sales-commission/export.csv``).

설계서 docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md §2.1-8 · §9 · J2(XLSX 아님 — 표 계산 프로그램에서
열리는 CSV). 파일은 마감 · 지급 완료 스냅샷만 옮긴다 — 실제로 준 돈과 같아야 해서다.
요율 · 금액 · 이름은 모두 가짜 값이다(저장소 공개 — 실제 요율은 설정에만 있다).
"""
from __future__ import annotations

import ast
import csv
import datetime
import io
from pathlib import Path

import pytest

from db import db_session
from foms.services.audit_message_display import ACTION_LABELS
from foms.services.sales_commission import closing as closing_mod
from foms.services.sales_commission.closing import close_month, closing_for_month, mark_paid
from foms.services.sales_commission.export import HEADERS, build_closing_csv, export_filename
from models import SecurityLog, User
from tests.domains.test_auth_finance import _login, _make_user
from tests.domains.test_sales_commission_api import MATCH, OTHER_MATCH, _add_freelancer, _input, _order
from tests.domains.test_sales_commission_closing import _set_tax

EXPORT = "/api/sales-commission/export.csv"
AUDIT_ACTION = "SALES_COMMISSION_EXPORT_CSV"
_ALLOWED = [("ADMIN", None), ("MANAGER", "ACCOUNTING"), ("STAFF", "ACCOUNTING")]
_DENIED = [("MANAGER", "CS"), ("STAFF", "SALES")]
_REPO_ROOT = Path(__file__).resolve().parents[2]
#: T10 이 새로 만들거나 고친 foms/ 파일 — 표 계산 라이브러리 이름 · 낱말이 다시 들어오지 않는다(J2).
_NEW_FOMS_FILES = ("foms/services/sales_commission/export.py", "foms/api/sales_commission.py",
                   "foms/services/sales_commission/closing.py", "foms/web/sales_commission.py")
_FORBIDDEN_WORDS = ("pandas", "openpyxl", "xlsxwriter", "excel", "xlsx")


@pytest.fixture(autouse=True)
def _today(monkeypatch):
    """오늘 = 2030-04-10(한국 시각). 시드 달이 '앞으로 올 달'로 막히지 않게 고정한다."""
    monkeypatch.setattr(closing_mod, "get_today_kst", lambda: datetime.date(2030, 4, 10))


@pytest.fixture
def world(app):
    """프리랜서 F: 계산 끝난 줄 2(합 180,000) + 시공비 기다림 1. 2030-03 마감 하나. G: 마감 없음."""
    fl = _add_freelancer(MATCH)
    other = _add_freelancer(OTHER_MATCH)
    # (2,500,000 − 1,000,000) × 4% = 60,000
    a = _order(manager=MATCH, orderer="라홈 가짜점", construction="2030-02-10", customer="가짜가")
    # (3,000,000 − 1,000,000) × 6% = 120,000
    b = _order(manager=MATCH, orderer="하우드", construction="2030-03-05", price=3_000_000, customer="가짜나")
    _order(manager=MATCH, orderer="라홈", construction="2030-03-20", customer="가짜기다림")  # 시공비 없음
    for oid in (a, b):
        _input(oid, install_cost=1_000_000)
    return {"fl": fl.id, "other": other.id, "a": a, "b": b}


def _close(user_id: int, month: str = "2030-03"):
    row = close_month(db_session, user_id, month, actor_user_id=None)
    db_session.commit()
    return row


def _client(app, role, team):
    client = app.test_client()
    user = _make_user(role, team)
    _login(client, user)
    return client, user


def _rows(text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text.lstrip("﻿"))))


def _summary(rows: list[list[str]]) -> dict[str, str]:
    """요약 줄(첫 칸 = 이름, 수수료 칸 = 값)만 모은다."""
    blank = rows.index([])
    col = HEADERS.index("수수료")
    return {row[0]: row[col] for row in rows[blank + 1:]}


def _audits() -> list[SecurityLog]:
    return db_session.query(SecurityLog).filter(SecurityLog.action == AUDIT_ACTION).order_by(SecurityLog.id).all()


# --------------------------------------------------------------------------
# 권한
# --------------------------------------------------------------------------
@pytest.mark.parametrize("role,team", _ALLOWED)
def test_accounting_and_admin_download_the_closed_month(app, world, role, team):
    row = _close(world["fl"])
    client, user = _client(app, role, team)
    actor_id, closing_id = user.id, row.id

    resp = client.get(f"{EXPORT}?user_id={world['fl']}&month=2030-03")

    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.mimetype == "text/csv"
    filename = export_filename(world["fl"], "2030-03")
    assert filename == f"sales-commission-{world['fl']}-2030-03.csv"
    assert resp.headers["Content-Disposition"] == f'attachment; filename="{filename}"'
    assert resp.headers["Cache-Control"] == "no-store"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    logs = _audits()
    assert len(logs) == 1
    log = logs[0]
    assert log.user_id == actor_id and log.target_type == "sales_commission_closing" and log.target_id == closing_id
    assert log.detail["filename"] == filename and log.detail["month"] == "2030-03"
    assert log.detail["user_id"] == world["fl"] and log.detail["line_count"] == 2
    assert "가짜가" not in str(log.detail)  # 감사 원장에 고객명 없음


@pytest.mark.parametrize("who", [*_DENIED, "freelancer"])
def test_cs_sales_and_freelancer_get_json_403(app, world, who):
    _close(world["fl"])
    if who == "freelancer":
        client = app.test_client()
        _login(client, db_session.get(User, world["fl"]))
    else:
        client, _user = _client(app, *who)

    resp = client.get(f"{EXPORT}?user_id={world['fl']}&month=2030-03")

    assert resp.status_code == 403
    body = resp.get_json()
    assert body["success"] is False and body["data"] is None and body["error"]
    assert "Content-Disposition" not in resp.headers
    assert _audits() == []


def test_login_required(app, world):
    _close(world["fl"])
    assert app.test_client().get(f"{EXPORT}?user_id={world['fl']}&month=2030-03").status_code == 401


def test_audit_label_is_registered():
    assert ACTION_LABELS[AUDIT_ACTION] == "영업 수수료 CSV 내려받기"


# --------------------------------------------------------------------------
# 404 · 400
# --------------------------------------------------------------------------
def test_month_without_closing_is_404(app, world):
    _close(world["fl"])
    client, _user = _client(app, "ADMIN", None)
    for query in (f"user_id={world['fl']}&month=2030-02",      # 그 달 마감 없음(03 마감에 들어갔어도)
                  f"user_id={world['other']}&month=2030-03"):  # 마감 없는 프리랜서
        resp = client.get(f"{EXPORT}?{query}")
        assert resp.status_code == 404, query
        assert resp.get_json()["success"] is False
    assert _audits() == []


def test_bad_params_are_400(app, world):
    client, _user = _client(app, "ADMIN", None)
    assert client.get(f"{EXPORT}?month=2030-03").status_code == 400
    assert client.get(f"{EXPORT}?user_id=x&month=2030-03").status_code == 400
    assert client.get(f"{EXPORT}?user_id={world['fl']}&month=2030-3").status_code == 400
    assert client.get(f"{EXPORT}?user_id={world['fl']}").status_code == 400


# --------------------------------------------------------------------------
# 파일 모양 · 숫자 = 스냅샷
# --------------------------------------------------------------------------
def test_bom_crlf_and_snapshot_rows(app, world):
    _close(world["fl"])
    client, _user = _client(app, "STAFF", "ACCOUNTING")
    text = client.get(f"{EXPORT}?user_id={world['fl']}&month=2030-03").get_data(as_text=True)

    assert text.startswith("﻿") and text.count("﻿") == 1
    assert text.endswith("\r\n")
    assert "\n" not in text.replace("\r\n", "")  # 홀로 선 LF 없음
    rows = _rows(text)
    assert tuple(rows[0]) == HEADERS
    body = rows[1:rows.index([])]
    assert sorted(body) == sorted([
        ["2030-02", "가짜가 · 가짜장", "라홈", "2500000", "1000000", "0", "4", "60000", "정상"],
        ["2030-03", "가짜나 · 가짜장", "하우드", "3000000", "1000000", "0", "6", "120000", "정상"],
    ])
    assert "가짜기다림" not in text  # 시공비 기다리는 줄은 마감에 없다
    summary = _summary(rows)
    assert summary["합계"] == "180000" and summary["실지급"] == "180000"
    assert summary["마감 상태"] == "마감"
    assert len(summary["마감일"]) == 10 and summary["마감일"][4] == "-"
    assert "지급일" not in summary and "소득세" not in summary and "부가세" not in summary


def test_file_keeps_the_snapshot_after_inputs_change(app, world):
    """마감 뒤 시공비를 고쳐도 파일은 마감 때 숫자 그대로다(파일 = 실제로 준 돈)."""
    _close(world["fl"])
    from models import SalesCommissionInput
    db_session.get(SalesCommissionInput, world["a"]).install_cost = 0
    db_session.commit()
    client, _user = _client(app, "ADMIN", None)
    text = client.get(f"{EXPORT}?user_id={world['fl']}&month=2030-03").get_data(as_text=True)
    assert _summary(_rows(text))["합계"] == "180000"


def test_withholding_tax_rows_and_paid_state(app, world):
    _set_tax(world["fl"], "WITHHOLD_3_3")
    row = _close(world["fl"])
    mark_paid(db_session, row.id, actor_user_id=None)
    db_session.commit()
    client, _user = _client(app, "ADMIN", None)
    summary = _summary(_rows(client.get(f"{EXPORT}?user_id={world['fl']}&month=2030-03").get_data(as_text=True)))
    # 180,000 × 3% = 5,400 · 지방 540 · 실지급 174,060
    assert summary["합계"] == "180000"
    assert summary["소득세"] == "5400" and summary["지방소득세"] == "540"
    assert summary["실지급"] == "174060"
    assert "부가세" not in summary
    assert summary["마감 상태"] == "지급 완료"
    assert len(summary["지급일"]) == 10


# --------------------------------------------------------------------------
# 순수 함수 — 가짜 스냅샷
# --------------------------------------------------------------------------
def _fake(tax_type: str, **over) -> dict:
    closing = {
        "month": "2030-05", "status": "CLOSED", "gross": 100_000, "tax_income": 0, "tax_local": 0, "vat": 0,
        "net": 100_000, "tax_type": tax_type, "closed_at": "2030-06-10 09:30", "paid_at": None,
        "lines": [
            {"order_id": 1, "kind": "NORMAL", "deal_type": "PERSONAL", "shipping_price": 1_000_000,
             "install_cost": 0, "deduction_total": 50_000, "rate_bp": 450, "commission": 42_750,
             "label": "가짜 · 장", "completion_month": "2030-04"},
            {"order_id": 2, "kind": "ADJUST", "deal_type": "MANUAL", "shipping_price": 0, "install_cost": 0,
             "deduction_total": 0, "rate_bp": 425, "commission": -2_750, "label": "=SUM(A1)",
             "completion_month": "2030-03"},
        ],
    }
    closing.update(over)
    return closing


@pytest.mark.parametrize("tax_type, present, absent", [
    ("WITHHOLD_3_3", {"소득세": "3000", "지방소득세": "300"}, ("부가세",)),
    ("VAT_10", {"부가세": "10000"}, ("소득세", "지방소득세")),
    ("NONE", {}, ("소득세", "지방소득세", "부가세")),
])
def test_tax_summary_rows_follow_tax_type(tax_type, present, absent):
    values = {"WITHHOLD_3_3": dict(tax_income=3000, tax_local=300, net=96_700),
              "VAT_10": dict(vat=10_000, net=110_000), "NONE": {}}[tax_type]
    summary = _summary(_rows(build_closing_csv(_fake(tax_type, **values))))
    for label, value in present.items():
        assert summary[label] == value
    for label in absent:
        assert label not in summary
    assert summary["실지급"] == str(_fake(tax_type, **values)["net"])
    assert summary["마감일"] == "2030-06-10"


def test_pure_rows_rate_kind_and_formula_guard():
    rows = _rows(build_closing_csv(_fake("NONE")))
    normal, adjust = rows[1], rows[2]
    assert normal == ["2030-04", "가짜 · 장", "개인영업", "1000000", "0", "50000", "4.5", "42750", "정상"]
    assert adjust[0] == "2030-03" and adjust[2] == "회계팀 지정" and adjust[6] == "4.25"
    assert adjust[7] == "-2750" and adjust[8] == "조정"
    assert adjust[1] == "'=SUM(A1)"  # 사람이 적은 글이 식으로 읽히지 않게


def test_closing_for_month_returns_none_for_bad_input(world):
    assert closing_for_month(db_session, world["fl"], "2030-3") is None
    assert closing_for_month(db_session, "x", "2030-03") is None
    assert closing_for_month(db_session, world["fl"], "2030-03") is None
    _close(world["fl"])
    assert closing_for_month(db_session, world["fl"], "2030-03")["line_count"] == 2


# --------------------------------------------------------------------------
# 금지 낱말 · 라이브러리(J2)
# --------------------------------------------------------------------------
@pytest.mark.parametrize("rel", _NEW_FOMS_FILES)
def test_no_spreadsheet_words_or_libraries_in_new_foms_files(rel):
    source = (_REPO_ROOT / rel).read_text(encoding="utf-8")
    lowered = source.lower()
    for word in _FORBIDDEN_WORDS:
        assert word not in lowered, f"{rel}: '{word}'"
    tree = ast.parse(source)
    for node in ast.walk(tree):
        names = ([alias.name for alias in node.names] if isinstance(node, ast.Import)
                 else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
        for name in names:
            assert name.split(".")[0].lower() not in _FORBIDDEN_WORDS, f"{rel}: import {name}"
