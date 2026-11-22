"""생산 전체 화면 작업 시트 — 설계서 §12.2 (2026-11-09, 안 2 "도면 먼저 작업 화면").

도면 전부(이미지 썸네일 + PDF 는 파일 열기)·전화·주소·시공팀·공정 5줄·불량 칩 4·단추(옆 시트와 같은 계약).
금액 없음(D7). 인라인 style·script 없음. 쿼리 수는 옆 시트와 같은 수준(고정 상한).
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path

from sqlalchemy import event
from werkzeug.security import generate_password_hash

from db import db_session, engine
from foms.services.datetime_kst import get_today_kst
from foms.services.production_sheet_view import _format_at_kst, _prod_sheet_drawing_files
from models import Order, OrderEvent, ProductionRun, User

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
    # 작업 시트 단추는 쓰기 팀 + 태블릿(foms_ptr=coarse) 또는 PC [고치기] 켬일 때만 그린다(설계서 2026-11-21-production-pc-viewer §4 · §5).
    # 이 파일은 공장 태블릿 화면을 본다 — PC 보기 전용은 test_production_pc_viewer.
    client.set_cookie("foms_ptr", "coarse", domain="localhost")
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


def test_팀_없으면_403_없는_주문은_404(client) -> None:
    # 도면팀은 2026-11-21 보는 팀(설계서 production-pc-viewer §9-1) — 막히는 쪽은 첫 화면을 못 보는 사람(팀 없음)이다.
    _make_user(client, "sheet_drawing_staff", "DRAWING")
    order = _seed_order()
    assert client.get(SHEET_URL.format(id=order.id)).status_code == 200
    _make_user(client, "sheet_noteam_staff", None)
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


# --------------------------------------------------------------------------- #
# 11-21 시안 안 2 맞춤(사용자 "목업대로") — 아래 단추 줄 · 검수 전 회색 [제작 완료] · 지금 여기 · W×D×H · 저장/연결 한 줄
# --------------------------------------------------------------------------- #
def _all_steps_done(order: Order) -> None:
    sd = dict(order.structured_data)
    sd["production"] = dict(sd["production"], steps=[
        {"key": k, "label": k, "done": True, "at": "2026-11-09T00:12:00+00:00", "by_name": "이철호"}
        for k in ("cut", "edge", "assemble", "inspect")
    ])
    order.structured_data = sd
    db_session.commit()


def _complete_button(html: str) -> str:
    import re
    return re.search(r'<button [^>]*data-tablet-sheet-action="production-complete"[^>]*>.*?</button>', html, re.S).group(0)


def test_검수_전_제작_완료는_회색이고_누를_수_없다(client) -> None:
    """회색 · 막힘은 그대로 — 2026-11-22 부터 진짜 disabled 없이 aria-disabled 만(누르면 남은 공정을 알린다,
    test_production_sheet_tap_explains)."""
    _make_user(client, "sheet_prod_gate1", "PRODUCTION")
    order = _seed_order()  # 공정 1/4
    html = client.get(SHEET_URL.format(id=order.id)).get_data(as_text=True)
    btn = _complete_button(html)
    assert "foms-prod-page__btn--off" in btn and "foms-prod-page__btn--pri" not in btn
    assert " disabled" not in btn and 'aria-disabled="true"' in btn and "data-foms-sheet-complete" in btn
    assert ">제작 완료<" in btn and "검수까지 끝나면 눌러요" in btn and "data-foms-sheet-complete-hint>" in btn


def test_검수까지_끝나면_제작_완료가_파랗다(client) -> None:
    _make_user(client, "sheet_prod_gate2", "PRODUCTION")
    order = _seed_order()
    _all_steps_done(order)
    html = client.get(SHEET_URL.format(id=order.id)).get_data(as_text=True)
    btn = _complete_button(html)
    assert "foms-prod-page__btn--pri" in btn and "foms-prod-page__btn--off" not in btn
    assert " disabled" not in btn and "aria-disabled" not in btn
    assert "data-foms-sheet-complete-hint hidden" in btn and ">4/4<" in html
    assert "지금 여기" not in html  # 다 끝나면 '지금' 칸이 없다


def test_공정_칸을_한_칸도_안_켠_주문은_제작_완료가_파랗다(client) -> None:
    """11-21 사용자 "공정 칸을 쓴 주문만 막기": 한 칸도 안 켠 주문은 규칙 밖 — 서버가 그대로 완료시키니 단추도 파랑."""
    _make_user(client, "sheet_prod_gate3", "PRODUCTION")
    order = _seed_order()
    sd = dict(order.structured_data)
    sd["production"] = dict(sd["production"], steps=[dict(s, done=False, at=None, by_name=None)
                                                    for s in sd["production"]["steps"]])
    order.structured_data = sd
    db_session.commit()
    html = client.get(SHEET_URL.format(id=order.id)).get_data(as_text=True)
    btn = _complete_button(html)
    assert "foms-prod-page__btn--pri" in btn and "foms-prod-page__btn--off" not in btn
    assert " disabled" not in btn and "data-foms-sheet-complete-hint hidden" in btn


def test_아래_단추_줄_지금_여기_치수_연결_한_줄(client) -> None:
    _make_user(client, "sheet_prod_foot", "PRODUCTION")
    order = _seed_order()
    html = client.get(SHEET_URL.format(id=order.id)).get_data(as_text=True)
    side = html.split('class="foms-prod-page__side"', 1)[1]
    scroll, foot = side.split('class="foms-prod-page__foot"', 1)
    # 위 굴러가는 칸: 공정(최근 불량 줄 포함) · 바뀐 것 · 만들 것 · 고객(11-21 순서). 단추는 없다
    assert 'class="foms-prod-page__side-scroll"' in scroll and 'aria-label="공정"' in scroll and "최근 불량 · 파손" in scroll
    assert "data-tablet-sheet-action" not in scroll and "data-foms-sheet-defect-toggle" not in scroll
    # 아래 줄: [불량 알리기] · [보류] 한 줄 → 칩 → 큰 단추 → 저장 · 연결
    pair = foot.split('class="foms-prod-page__pair"', 1)[1].split("</div>", 1)[0]
    assert pair.index("data-foms-sheet-defect-toggle") < pair.index('data-tablet-sheet-action="production-hold"')
    assert foot.index("data-foms-sheet-defect-reasons") < foot.index('data-tablet-sheet-action="production-complete"')
    assert foot.index('data-tablet-sheet-action="production-complete"') < foot.index("data-foms-sheet-status")
    assert "data-foms-sheet-net>연결 좋음<" in foot
    # 공정: 지금 칸(엣지) 옆 '지금 여기', 끝난 칸은 누가 · 몇 시
    assert html.count("지금 여기") == 1 and "이철호 · 11/9 09:12" in html
    # 만들 것: 품목마다 'W×D×H · 수량'(시드는 가로만 있어 W 만)
    assert "<span>거실장</span><span>W3100 · 1</span>" in html and "<span>W2160 · 1</span>" in html


def test_만들_것_치수는_있는_축만_칸마다() -> None:
    from foms.services.production_sheet_view import _prod_sheet_spec_rows_view
    rows = _prod_sheet_spec_rows_view([
        {"product_name": "거실장", "spec_width": "3100", "spec_depth": "500", "spec_height": "2300", "quantity": 1},
        {"product_name": "장", "spec_rows": [{"w": "1200", "d": "600", "h": "2300"}, {"spec_width": "900", "spec_height": "2100"}]},
        {"product_name": "빈 것"},
    ])
    assert [r["whd"] for r in rows] == ["W3100 × D500 × H2300", "W1200 × D600 × H2300 / W900 × H2100", ""]
    assert rows[1]["w"] == "2100" and rows[2]["w"] == "-"  # 옆 시트가 쓰는 총 가로 폭은 그대로


def test_아래_단추_줄은_가로_태블릿에서만_바닥에_붙는다() -> None:
    css = (ROOT / "static/css/contexts/production/sheet.css").read_text(encoding="utf-8")
    gate = "@media (min-width: 992px) and (orientation: landscape) and (pointer: coarse) {"
    head, _, rest = css.partition(gate)
    block = rest.split("\n}\n", 1)[0]
    assert ".foms-prod-page__side { overflow: hidden; padding-bottom: 12px; }" in block
    assert ".foms-prod-page__side-scroll { flex: 1 1 auto; min-height: 0; overflow-y: auto;" in block
    assert ".foms-prod-page__foot { flex-shrink: 0;" in block
    assert "overflow-y: auto" not in head.split(".foms-prod-page__side-scroll", 1)[1].split("}", 1)[0]  # 밖(PC · 세로)에서는 안 굴린다
    assert ".foms-prod-page__pair { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);" in head
    assert ".foms-prod-page__btn--off, .foms-prod-page__btn--off:disabled, .foms-prod-page__btn--off:hover { opacity: 1;" in head
    assert ".foms-prod-page__btn:disabled > * { pointer-events: none; }" in head


def test_시트_JS는_공정을_체크하면_제작_완료를_바로_바꾼다() -> None:
    """11-21 서버도 같은 규칙: 공정 API 응답의 complete_ready(서버 한 함수)로 단추를 바꾼다 — 응답이 없을 때만
    (오프라인 줄 세움) 칸 모양으로 미리 보인다. 옆 시트도 같은 단추(공정 루트 밖 바닥 줄)를 찾는다."""
    js = (ROOT / "static/js/production/foms-production-sheet-page.js").read_text(encoding="utf-8")
    assert "function syncComplete(serverReady)" in js and "[data-foms-sheet-complete]" in js and "[data-foms-sheet-complete-hint]" in js
    assert "typeof serverReady === 'boolean' ? serverReady" in js
    assert "buttons.every(function (b) { return b.getAttribute('aria-pressed') === 'true'; })" in js
    # 오프라인 미리 판정도 서버와 같다 — 한 칸도 안 켰으면 규칙 밖(파랑, 11-21 "공정 칸을 쓴 주문만 막기")
    assert "|| buttons.every(function (b) { return b.getAttribute('aria-pressed') !== 'true'; })" in js
    assert "renderSteps(payload.steps, payload.complete_ready)" in js and "syncComplete(serverReady);" in js
    assert js.count("syncComplete();") == 1  # 목록 없이 한 칸만 바꿀 때(오프라인 줄 세움)
    assert "page.closest('.foms-prod-sheet')" in js  # 옆 시트 단추는 공정 루트 밖
    assert "completeBase + '--pri'" in js and "completeBase + '--off'" in js
    # 지금 여기 · 연결 한 줄은 전체 화면 시트에만(옆 시트에는 data-foms-sheet-net 이 없다)
    assert "var nowText = netEl ? '지금 여기' : '';" in js and "(isNow ? nowText : '')" in js
    assert "navigator.onLine !== false && !netFailed" in js
    side = (ROOT / "templates/production/partials/tablet_sheet.html").read_text(encoding="utf-8")
    assert "data-foms-sheet-net" not in side
    assert "data-foms-sheet-complete" in side and "foms-prod-sheet__btn--off" in side  # 옆 시트도 검수 전 회색(11-21)


def test_오른쪽_칸은_공정_바뀐_것_만들_것_고객_순서(client) -> None:
    """11-21 사용자 결정 — 바닥 단추 줄을 고정해(53d1c5bb6) 굴러가는 칸이 작아졌고, 공정 칸을 켜야 [제작 완료]가
    풀리므로 공정 4칸 줄을 맨 위로. 마크업 순서 = 읽기 · 키보드 순서(CSS order 아님). 보류 사유는 바뀐 것 다음,
    특이사항은 만들 것 다음. 옆 시트(tablet_sheet.html)는 그대로(고객 → … → 공정)."""
    from foms.services.datetime_kst import now_utc_naive
    _make_user(client, "sheet_prod_order", "PRODUCTION")
    order = _seed_order()
    now = now_utc_naive()
    sd = dict(order.structured_data)
    sd["production"] = {**sd["production"], "hold": {"active": True, "reason": "자재 기다림", "at": now.isoformat()}}
    order.structured_data = sd
    order.erp_stage_updated_at = now - datetime.timedelta(days=4)
    db_session.add(OrderEvent(order_id=order.id, event_type="CONSTRUCTION_DATE_CHANGED",
                              payload={"from": (get_today_kst() + datetime.timedelta(days=5)).isoformat(),
                                       "to": (get_today_kst() + datetime.timedelta(days=3)).isoformat()},
                              created_at=now - datetime.timedelta(hours=5)))
    db_session.commit()
    html = client.get(SHEET_URL.format(id=order.id)).get_data(as_text=True)
    scroll = html.split('class="foms-prod-page__side-scroll"', 1)[1].split('class="foms-prod-page__foot"', 1)[0]
    marks = ['aria-label="공정"', 'aria-label="변경 알림"', "보류 사유 <strong>자재 기다림</strong>",
             'aria-label="만들 것"', 'aria-label="특이사항"', 'aria-label="고객"']
    pos = [scroll.find(m) for m in marks]
    assert -1 not in pos, dict(zip(marks, pos))
    assert pos == sorted(pos), dict(zip(marks, pos))
    # 공정이 굴러가는 칸의 첫 상자다(앞에 다른 상자 · 안내 줄이 없다)
    head = scroll[: pos[0]]
    assert head.count("<section") == 1 and "foms-prod-page__callout" not in head and "<p" not in head
    # 순서는 마크업으로 — CSS order 로 바꾸지 않는다
    css = (ROOT / "static/css/contexts/production/sheet.css").read_text(encoding="utf-8")
    assert not re.search(r"(?<![\w-])order\s*:", css)
    # 옆 시트는 범위 밖 — 규격이 공정보다 먼저(그대로)
    side = (ROOT / "templates/production/partials/tablet_sheet.html").read_text(encoding="utf-8")
    assert 0 <= side.find('aria-label="규격"') < side.find('aria-label="공정"')
