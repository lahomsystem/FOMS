"""생산 전체 화면 작업 시트 — 설계서 §12.2 (2026-11-09, 안 2 "도면 먼저 작업 화면").

도면 전부(이미지 썸네일 + PDF 는 파일 열기)·전화·주소·시공팀·공정 5줄·불량 칩 4·단추(옆 시트와 같은 계약).
금액 없음(D7). 인라인 style·script 없음. 쿼리 수는 옆 시트와 같은 수준(고정 상한).
"""

from __future__ import annotations

import datetime
from pathlib import Path

from sqlalchemy import event
from werkzeug.security import generate_password_hash

from db import db_session, engine
from foms.services.datetime_kst import get_today_kst
from foms.services.production_sheet_view import _format_at_kst, _prod_sheet_drawing_files
from models import Order, ProductionRun, User

ROOT = Path(__file__).resolve().parents[2]
SHEET_URL = "/erp/production/sheet/{id}"


def _make_user(client, username: str, team: str | None, role: str = "STAFF") -> User:
    user = User(username=username, password=generate_password_hash("pw"), role=role, team=team, name=username, is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _seed_order(*, with_run: bool = True) -> Order:
    today = get_today_kst()
    sd = {
        "workflow": {"stage": "PRODUCTION"},
        "parties": {"customer": {"name": "김하늘", "phone": "010-1234-5678"}},
        "site": {"address_full": "서울 송파구 올림픽로 300, 101동 1203호"},
        "schedule": {
            "measurement": {"date": (today - datetime.timedelta(days=12)).isoformat()},
            "construction": {"date": (today + datetime.timedelta(days=3)).isoformat()},
        },
        "shipment": {"construction_workers": ["박성민", {"name": "최우진"}]},
        "items": [
            {"product_name": "거실장", "spec_width": "3100", "quantity": 1, "price": 1234000, "material": "화이트 오크"},
            {"product_name": "몰딩 벽박이장", "spec_width": "2160", "quantity": 1, "price": 890000},
        ],
        "notes": "모서리 라운드 처리",
        "drawing_current_files": [
            {"key": "drawings/a.png", "filename": "거실장 정면.png"},
            {"key": "drawings/b.jpg", "filename": "거실장 측면.jpg"},
            {"key": "drawings/c.pdf", "filename": "상세.pdf"},
        ],
        "production": {
            "steps": [
                {"key": "cut", "label": "재단", "done": True, "at": "2026-11-09T00:12:00+00:00", "by_name": "이철호"},
                {"key": "edge", "label": "엣지", "done": False, "at": None, "by_name": None},
            ],
            "defects": [{"reason": "파손", "at": "2026-11-08T08:05:00+00:00", "by_name": "이철호"}],
        },
    }
    order = Order(
        received_date=today.isoformat(), customer_name="김하늘", phone="010-1234-5678", address="서울 송파구",
        product="거실장", manager_name="관리", status="PRODUCTION", is_erp_order=True,
        structured_data=sd, erp_stage_code="PRODUCTION", erp_construction_date=(today + datetime.timedelta(days=3)).isoformat(),
    )
    db_session.add(order)
    db_session.commit()
    if with_run:
        db_session.add(ProductionRun(order_id=order.id, status="IN_PROGRESS", steps=[], defects=[], is_current=True))
        db_session.commit()
    return order


def _count_queries(fn):
    counter = {"n": 0}

    def _before(conn, cursor, statement, params, context, executemany):
        counter["n"] += 1

    event.listen(engine, "before_cursor_execute", _before)
    try:
        result = fn()
    finally:
        event.remove(engine, "before_cursor_execute", _before)
    return result, counter["n"]


def test_생산팀은_전체_화면_시트에서_도면_연락처_공정_단추를_본다(client) -> None:
    _make_user(client, "sheet_prod_staff", "PRODUCTION")
    order = _seed_order()
    response, n_queries = _count_queries(lambda: client.get(SHEET_URL.format(id=order.id)))
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    # 머리: 이름·#id·품목·시공일 요일
    assert "김하늘" in html and f"#{order.id}" in html and "거실장" in html
    assert "시공 " in html and "(" in html
    # 고객: 전화 글자 + tel 링크, 주소 + 지도, 실측·시공팀
    assert "010-1234-5678" in html and 'href="tel:01012345678"' in html
    assert "서울 송파구 올림픽로 300" in html and "map.kakao.com" in html
    assert "시공팀 박성민, 최우진" in html
    # 도면: 이미지 2 썸네일 + PDF 파일 열기 1, 첫 장 캡션
    assert html.count("data-foms-sheet-dwg-th=") == 2
    assert html.count("파일 열기") == 1
    assert "도면 1 / 2" in html and "/api/files/view/drawings/a.png" in html
    # 공정 4줄(도장 없음, D15): 재단 끝(누가·몇 시), 엣지가 지금 여기
    assert html.count("data-foms-sheet-step=") == 4
    assert 'data-foms-sheet-step="cut" aria-pressed="true"' in html
    assert "이철호 · 11/9 09:12" in html
    assert 'is-now' in html and ">1/4<" in html
    # 불량: 최근 1줄 + 칩 4
    assert "최근 불량 · 파손" in html
    assert html.count("data-foms-sheet-defect-reason=") == 4
    # 단추: 제작중 → 보류 · 제작 취소 · 제작 완료(옆 시트와 같은 계약, 글만 제작 완료)
    assert 'data-tablet-sheet-action="production-hold"' in html
    assert 'data-tablet-sheet-action="production-cancel"' in html
    assert 'data-tablet-sheet-action="production-complete"' in html and ">제작 완료<" in html
    assert "생산 완료" not in html
    # 특이사항, 금액 없음(D7)
    assert "모서리 라운드 처리" in html
    assert "1234000" not in html and "1,234,000" not in html and "890000" not in html
    # 배선 세트 + 페이지 JS·CSS
    assert "js/foms/tablet-domain-sheets.js" in html and "data-foms-reason-sheet" in html
    assert "js/production/foms-production-sheet-page.js" in html and "css/contexts/production/sheet.css" in html
    # 쿼리 수: 사용자·주문·run·게이트·변경 이벤트 정도 — N+1 없음
    assert n_queries <= 14, n_queries


def test_제작대기_주문은_제작_시작_단추를_보인다(client) -> None:
    _make_user(client, "sheet_prod_staff2", "PRODUCTION")
    order = _seed_order(with_run=False)
    html = client.get(SHEET_URL.format(id=order.id)).get_data(as_text=True)
    assert 'data-tablet-sheet-action="production-start"' in html and ">제작 시작<" in html
    assert 'data-tablet-sheet-action="production-complete"' not in html
    # 제작 전엔 '지금 여기' 표시 없음
    assert "is-now" not in html


def test_도면팀은_403_없는_주문은_404(client) -> None:
    _make_user(client, "sheet_drawing_staff", "DRAWING")
    order = _seed_order()
    assert client.get(SHEET_URL.format(id=order.id)).status_code == 403
    _make_user(client, "sheet_prod_staff3", "PRODUCTION")
    assert client.get(SHEET_URL.format(id=order.id + 999)).status_code == 404


def test_옆_시트는_그대로_그린다(client) -> None:
    """뷰 모델을 서비스로 옮겼어도 옆 시트 fragment 는 같은 키로 그린다."""
    _make_user(client, "sheet_side_admin", "CS", role="ADMIN")
    order = _seed_order()
    html = client.get(f"/erp/production/tablet-sheet/{order.id}").get_data(as_text=True)
    assert "foms-prod-sheet" in html and "김하늘" in html
    assert 'data-tablet-sheet-action="production-complete"' in html
    assert "/api/files/view/drawings/a.png" in html


def test_템플릿에_인라인_style_script_없음() -> None:
    text = (ROOT / "templates/production/sheet.html").read_text(encoding="utf-8")
    assert 'style="' not in text
    assert "<script>" not in text
    home = (ROOT / "templates/production/home.html").read_text(encoding="utf-8")
    assert 'style="' not in home and "<script>" not in home


def test_도면_목록과_시각_규칙() -> None:
    files = _prod_sheet_drawing_files({"drawing_current_files": [
        {"key": "d/1.PNG", "filename": "1.PNG"}, {"key": "d/2.pdf", "filename": "2.pdf"}, {"filename": "키 없음"},
    ]})
    assert [f["kind"] for f in files] == ["image", "file"]
    assert files[0]["view"] == "/api/files/view/d/1.PNG" and files[0]["download"] == "/api/files/download/d/1.PNG"
    assert _format_at_kst("2026-11-09T00:12:00+00:00") == "11/9 09:12"
    assert _format_at_kst("2026-11-09T00:12:00Z") == "11/9 09:12"
    assert _format_at_kst("") == "" and _format_at_kst("이상") == ""
