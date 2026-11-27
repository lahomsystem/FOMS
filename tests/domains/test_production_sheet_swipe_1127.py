"""생산 작업 시트 큰 도면 칸 — 손가락으로 옆으로 밀어 앞 · 다음 도면(사장님 2026-11-27 "이 화면에서도 도면 스와이프 해서 넘길 수 있게").

넘기기는 이미 있는 [앞] [다음] 단추를 누르는 길(foms-production-sheet-page.js 는 그대로 — 300줄 래칫).
판정 값은 공용 GlobalImageViewer 넘김과 같다(56px · 1.2배, 빠른 튕김 250ms · 30px). touch* 만, 칸마다 한 번 묶음, 민 뒤 click 삼킴.
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.datetime_kst import get_today_kst
from models import Order, ProductionRun, User

ROOT = Path(__file__).resolve().parents[2]
JS = ROOT / "static/js/production/foms-production-sheet-swipe.js"
PIN = "20261127m"  # 밀기 스크립트 핀
CSS_PIN = "20261127u"  # sheet.css — 밀기(m) 뒤 도면 있는 주문 공정 보기 줄(test_production_steps_view_only_1127)과 합쳐 한 번 더
SHEET_URL = "/erp/production/sheet/{id}"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _login(client, username: str) -> None:
    user = User(username=username, password=generate_password_hash("pw"), role="STAFF", team="PRODUCTION", name=username, is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    client.set_cookie("foms_ptr", "coarse", domain="localhost")


def _seed(files: list[dict]) -> Order:
    today = get_today_kst()
    sd = {
        "workflow": {"stage": "PRODUCTION"},
        "parties": {"customer": {"name": "가나다", "phone": "010-0000-0000"}},
        "schedule": {"construction": {"date": (today + datetime.timedelta(days=3)).isoformat()}},
        "items": [{"product_name": "붙박이장", "spec_width": "2400", "quantity": 1}],
        "drawing_current_files": files,
    }
    order = Order(
        received_date=today.isoformat(), customer_name="가나다", phone="010-0000-0000", address="서울",
        product="붙박이장", manager_name="관리", status="PRODUCTION", is_erp_order=True,
        structured_data=sd, erp_stage_code="PRODUCTION", erp_construction_date=(today + datetime.timedelta(days=3)).isoformat(),
    )
    db_session.add(order)
    db_session.commit()
    db_session.add(ProductionRun(order_id=order.id, status="IN_PROGRESS", steps=[], defects=[], is_current=True))
    db_session.commit()
    return order


def test_작업_시트가_밀기_스크립트와_새_CSS_핀을_싣는다() -> None:
    page = _read("templates/production/sheet.html")
    tag = f"js/production/foms-production-sheet-swipe.js') }}}}?v={PIN}\" defer></script>"
    assert page.count(tag) == 1
    # 넘기기 함수(sheet-page.js)보다 뒤에 싣는다 — 단추 위임이 먼저 묶여 있어야 click() 이 넘긴다
    assert page.index("foms-production-sheet-page.js") < page.index("foms-production-sheet-swipe.js")
    assert f"css/contexts/production/sheet.css') }}}}?v={CSS_PIN}" in page
    # (옆 시트 칸반 본문은 2026-11-27 옛 생산 보드와 함께 지웠다 — 밀기 스크립트 · 시트 CSS 를 싣는 곳은 작업 시트 하나)


def test_큰_그림_칸은_세로_굴림과_두_손가락_확대만_브라우저에_맡긴다() -> None:
    css = _read("static/css/contexts/production/sheet.css")
    rule = [line for line in css.splitlines() if line.startswith(".foms-prod-page__main-btn {")]
    assert len(rule) == 1 and "touch-action: pan-y pinch-zoom;" in rule[0]


def test_밀기_JS_원문_계약() -> None:
    js = JS.read_text(encoding="utf-8")
    assert len(js.splitlines()) <= 300
    # ES5 꼴
    for bad in (r"\bconst\b", r"\blet\b", r"=>", r"innerHTML", "`"):
        assert not re.search(bad, js), bad
    # touch* 만(iOS gesture* · pointer* · mouse* 안 씀)
    for ev in ("touchstart", "touchmove", "touchend", "touchcancel"):
        assert f"addEventListener('{ev}'" in js, ev
    for bad in ("gesturestart", "gesturechange", "pointerdown", "pointermove", "mousedown"):
        assert bad not in js, bad
    # 한 번만 묶음(칸마다 · 문서 리스너 한 번)
    assert "window.__FOMS_PROD_SHEET_SWIPE_BOUND = window.__FOMS_PROD_SHEET_SWIPE_BOUND || {}" in js
    assert "bound.el === stage" in js and "bound.el = stage;" in js
    assert "if (!bound.doc) {" in js and "bound.doc = true;" in js
    # 가로 판정 — 공용 뷰어와 같은 값, 튕김도 가로가 세로의 1.2배 넘을 때만
    assert "var SWIPE_MIN = 56;" in js and "var FLICK_MIN = 30;" in js and "var FLICK_MS = 250;" in js and "var RATIO = 1.2;" in js
    assert "var swipe = ax > SWIPE_MIN && ax > Math.abs(dy) * RATIO;" in js
    assert "var flick = dt < FLICK_MS && ax > FLICK_MIN && ax > Math.abs(dy) * RATIO;" in js
    # 두 손가락 · 화면 확대 중에는 넘기지 않는다
    assert "s.multi = true" in js and "vv.scale > 1.01" in js
    # 왼쪽 밀기 = 다음, 오른쪽 = 앞 — 이미 있는 단추를 누른다(1장이면 단추가 없어 아무 일 없음)
    assert "navButton(dx < 0 ? 1 : -1)" in js
    assert "'[data-foms-sheet-dwg-next]' : '[data-foms-sheet-dwg-prev]'" in js
    # 민 뒤 click 삼킴(칸에서 capture 로 먼저 받아 크게 보기 위임까지 안 간다)
    assert "s.swallowUntil = Date.now() + SWALLOW_MS;" in js
    click = js.split("stage.addEventListener('click'", 1)[1]
    assert "e.stopPropagation();" in click.split("}, true);")[0]
    # 넘기기 함수 파일은 안 고쳤다(300줄 래칫)
    assert len(_read("static/js/production/foms-production-sheet-page.js").splitlines()) <= 299


def test_도면_1장_주문도_화면이_열리고_넘김_단추가_없다(client) -> None:
    _login(client, "swipe_one")
    order = _seed([{"key": "drawings/one.png", "filename": "한 장.png"}])
    response = client.get(SHEET_URL.format(id=order.id))
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "도면 1 / 1" in html
    assert f"foms-production-sheet-swipe.js?v={PIN}" in html
    assert "data-foms-sheet-dwg-next" not in html and "data-foms-sheet-dwg-prev" not in html


def test_도면_여러_장_주문은_넘김_단추와_밀기_스크립트가_같이_있다(client) -> None:
    _login(client, "swipe_many")
    order = _seed([
        {"key": "drawings/a.png", "filename": "정면.png"},
        {"key": "drawings/b.png", "filename": "측면.png"},
    ])
    response = client.get(SHEET_URL.format(id=order.id))
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "도면 1 / 2" in html
    assert "data-foms-sheet-dwg-next" in html and "data-foms-sheet-dwg-prev" in html and "data-foms-sheet-dwg-open" in html
    assert f"foms-production-sheet-swipe.js?v={PIN}" in html
