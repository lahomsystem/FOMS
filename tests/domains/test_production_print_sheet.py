"""작업지시서 인쇄 `GET /erp/production/print/<id>` — 설계서 F8 (D8, 2026-11-09).

생산팀 200, 도면팀 403, 취소 품목 제외, 도면 장수 = 쪽수(+ 머리 1쪽), 공정 빈 칸 4, 금액 없음, 인라인 style·script 없음.
시트 두 곳(전체 화면·옆 시트)에 [인쇄] 링크.
"""

from __future__ import annotations

import copy
from pathlib import Path

from db import db_session
from tests.domains.test_production_sheet_page import _make_user, _seed_order

ROOT = Path(__file__).resolve().parents[2]
PRINT_URL = "/erp/production/print/{id}"


def test_생산팀은_작업지시서를_뽑는다(client) -> None:
    _make_user(client, "print_prod_staff", "PRODUCTION")
    order = _seed_order()
    # 품목 하나를 취소 표시(확정 뒤 취소) → 종이에 안 나온다
    sd = copy.deepcopy(order.structured_data)
    sd["items"].append({"product_name": "취소된장", "spec_width": "900", "quantity": 1, "price": 10,
                        "cancel": {"reason": "고객 요청", "at": "2026-11-09T00:00:00", "by": 1}})
    order.structured_data = sd
    db_session.commit()

    resp = client.get(PRINT_URL.format(id=order.id))
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "작업지시서" in html and f"#{order.id}" in html and "김하늘" in html
    assert "010-1234-5678" in html and "서울 송파구 올림픽로 300" in html
    assert "시공팀</dt><dd>박성민, 최우진" in html
    # 규격: 거실장·몰딩 벽박이장 2줄, 취소된장은 없음
    assert "거실장" in html and "몰딩 벽박이장" in html and "취소된장" not in html
    # 공정 빈 칸 4(도장 없음)
    steps = html[html.index('class="foms-print__steps"'):]
    steps = steps[: steps.index("</ul>")]
    assert steps.count("foms-print__box") == 4 and "도장" not in steps and "재단" in steps
    # 도면: 이미지 2 → 도면 쪽 2(+ 머리 1 = 3쪽), PDF 는 글로만
    assert html.count('class="foms-print__page foms-print__page--drawing"') == 2
    assert html.count('class="foms-print__page') == 3
    assert "파일 상세.pdf" in html and "도면 1 / 2" in html and "도면 2 / 2" in html
    # 금액 없음(D7), 특이사항
    assert "1234000" not in html and "1,234,000" not in html and "890000" not in html
    assert "모서리 라운드 처리" in html
    # 단추 JS·CSS
    assert "js/production/foms-production-print.js" in html and "css/contexts/production/print.css" in html


def test_도면팀은_403_없는_주문_404(client) -> None:
    _make_user(client, "print_drawing_staff", "DRAWING")
    order = _seed_order()
    assert client.get(PRINT_URL.format(id=order.id)).status_code == 403
    _make_user(client, "print_prod_staff2", "PRODUCTION")
    assert client.get(PRINT_URL.format(id=order.id + 999)).status_code == 404


def test_시트_두_곳에_인쇄_링크(client) -> None:
    _make_user(client, "print_prod_links", "PRODUCTION")
    order = _seed_order()
    page = client.get(f"/erp/production/sheet/{order.id}").get_data(as_text=True)
    side = client.get(f"/erp/production/tablet-sheet/{order.id}").get_data(as_text=True)
    for html in (page, side):
        assert f"/erp/production/print/{order.id}" in html and ">인쇄</a>" in html


def test_인쇄_템플릿은_인라인_style_script_없음() -> None:
    text = (ROOT / "templates/production/print_sheet.html").read_text(encoding="utf-8")
    assert 'style="' not in text and "<script>" not in text
    assert "@page" in (ROOT / "static/css/contexts/production/print.css").read_text(encoding="utf-8")
