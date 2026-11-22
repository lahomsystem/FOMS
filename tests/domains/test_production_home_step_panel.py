"""생산 첫 화면 '내 공정' 탭 오른쪽 판 — 설계서 ``docs/specs/2026-11-21-production-my-steps-panel_SPEC.md``.

사용자 결정(2026-11-21) "추천안(반반)대로 만들기": 목업 ``tablet-production-my-steps-panel.html`` ③ 그대로 — 줄 칸 : 판 = 50:50,
엣지 줄 없음, 줄 [끝]은 판으로, 빈 칸 대신 그림, 보류 주문은 [끝] 자리에 '보류 중 · 사유', 판 [<공정> 끝]만 확인 창.

① 판 자료 순수 함수(앞 공정 · 다음 공정 · 색 · 그림 640/원본/파일/없음 · 다음 손님 · 고른 줄)
② 문: 태블릿 가로(모바일 v2 + 터치 + 넓은 창)만, 파트 계정 · PC · 폰 · 레거시는 판 0개, 판 없는 화면 출력은 지금 그대로
③ 판 마크업(요소 · 순서 · 640 주소 · 원본 뷰어 목록) · 보류 판 · 확인 창 · 실을 것
쓰기 길(Node) · 쿼리 수 · CSS 는 test_production_home_step_panel_wiring.py.
"""
from __future__ import annotations

import datetime
import json
import re
from pathlib import Path

import pytest

from foms.api.production.orders import _PRODUCTION_DEFECT_REASONS, _PRODUCTION_STEP_DEFS
from foms.services.production.home_step_panel import (
    STEP_PANEL_LAST_NEXT,
    attach_step_panels,
    parse_step_order,
    production_home_step_panel,
    step_panel_for,
)
from tests.support.production_home_step_panel_seed import (
    HOME,
    SHELL,
    STEPS_JS,
    TABLET,
    get_html,
    login,
    pane_html,
    panel_url,
    queue_html,
    seed_cut_queue,
    set_cookies,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def cohort(monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")


# --------------------------------------------------------------------------- #
# ① 판 자료 순수 함수
# --------------------------------------------------------------------------- #
def _row(oid, *, key_done=(), hold=False, files=(), handle=None, material="그레이", started=None, defects=None):
    steps = [{"key": k, "label": l, "done": k in key_done,
              "at": "2026-11-21T00:12:00+00:00" if k in key_done else None,
              "by_name": "김재단" if k in key_done else None} for k, l in _PRODUCTION_STEP_DEFS]
    item = {"product_name": "붙박이장"}
    if handle is not None:
        item["handle"] = handle
    production = {"steps": steps}
    if hold:
        production["hold"] = {"active": True, "reason": " 자재 기다림 "}
    if defects:
        production["defects"] = defects
    return {"id": oid, "customer_name": f"손님{oid}", "hold_active": hold, "v3_product_label": "붙박이장",
            "v3_spec_display": "W2740 × D700 × H2330", "v3_material": material, "run_started_at": started,
            "structured_data": {"items": [item], "production": production, "drawing_current_files": list(files)}}


def test_앞_공정_다음_공정_글() -> None:
    cut = production_home_step_panel(_row(1, started=datetime.datetime(2026, 11, 20, 23, 40)), "cut", None)
    assert cut["prev"] == "제작 시작 · 11/21 08:40" and cut["next_step"] == "엣지" and cut["label"] == "재단"
    assert production_home_step_panel(_row(1), "cut", None)["prev"] == "제작 시작"  # 시각이 없으면 글만
    edge = production_home_step_panel(_row(2, key_done=("cut",)), "edge", None)
    assert edge["prev"] == "재단 끝 · 김재단 · 11/21 09:12" and edge["next_step"] == "조립"
    blank = production_home_step_panel(_row(3), "assemble", None)  # 앞 공정 이름 · 시각이 비면 '엣지 끝' 만
    assert blank["prev"] == "엣지 끝" and blank["next_step"] == "검수"
    inspect = production_home_step_panel(_row(4), "inspect", None)
    assert inspect["next_step"] == STEP_PANEL_LAST_NEXT == "제작 완료"
    # 회차 시작 시각은 UTC — 글자 시각(iso)도 같은 답
    assert production_home_step_panel(_row(5, started="2026-11-20T07:10:00"), "cut", None)["prev"] == "제작 시작 · 11/20 16:10"


def test_색_손잡이_줄과_품목_치수() -> None:
    assert production_home_step_panel(_row(1, handle="없음"), "cut", None)["color"] == "그레이 · 손잡이 없음"
    assert production_home_step_panel(_row(1), "cut", None)["color"] == "그레이"
    assert production_home_step_panel(_row(1, handle="블랙", material=""), "cut", None)["color"] == "손잡이 블랙"
    assert production_home_step_panel(_row(1, material=""), "cut", None)["color"] == ""  # 줄을 안 그린다
    row = _row(1)
    assert production_home_step_panel(row, "cut", None)["sub"] == "붙박이장 · W2740 × D700 × H2330"
    row.update(v3_spec_display="")
    assert production_home_step_panel(row, "cut", None)["sub"] == "붙박이장"
    row.update(v3_product_label="")
    assert production_home_step_panel(row, "cut", None)["sub"] == "품목 없음"


def test_그림은_첫_그림_640_원본_뷰어는_그림_전부_파일만이면_새_탭_0장이면_도면_없음() -> None:
    files = [{"key": "orders/1/drawing/a.pdf", "filename": "a.pdf"}, {"key": "orders/1/drawing/b.png", "filename": "b.png"},
             {"key": "orders/1/drawing/x_png", "filename": "한글.png"}]
    pic = production_home_step_panel(_row(1, files=files), "cut", None)["pic"]
    assert pic["kind"] == "image" and pic["label"] == "도면 3장"
    assert pic["src"] == "/api/files/thumb/orders/1/drawing/b.png?w=640"
    assert [f["view_url"] for f in pic["files"]] == ["/api/files/view/orders/1/drawing/b.png", "/api/files/view/orders/1/drawing/x_png"]
    # 640 을 만들 수 없는 key(그림 이름이지만 파생 파일)는 원본
    odd = production_home_step_panel(_row(1, files=[{"key": "orders/1/drawing/sthumb640_a.png", "filename": "a.png"}]), "cut", None)["pic"]
    assert odd["src"] == "/api/files/view/orders/1/drawing/sthumb640_a.png"
    pdf = production_home_step_panel(_row(1, files=[{"key": "orders/1/drawing/a.pdf", "filename": "a.pdf"}]), "cut", None)["pic"]
    assert pdf == {"kind": "file", "label": "도면 1장 · 파일", "href": "/api/files/view/orders/1/drawing/a.pdf", "files": []}
    assert production_home_step_panel(_row(1), "cut", None)["pic"]["kind"] == "none"
    assert production_home_step_panel(_row(1), "cut", None)["pic"]["label"] == "도면 없음"


def test_보류_사유와_최근_불량() -> None:
    held = production_home_step_panel(_row(1, hold=True), "cut", None)
    assert held["hold_active"] is True and held["hold_reason"] == "자재 기다림"
    defect = production_home_step_panel(
        _row(1, defects=[{"reason": "파손", "by_name": "김재단", "at": "2026-11-21T01:00:00+00:00"}]), "cut", None)
    assert defect["latest_defect"] == {"reason": "파손", "meta": "김재단 11/21 10:00"}
    assert production_home_step_panel(_row(1), "cut", None)["latest_defect"] is None


def test_다음_손님은_보류_줄을_건너뛰고_고른_줄은_order_보류_아닌_첫_줄_모두_보류면_첫_줄() -> None:
    rows = [_row(1), _row(2, hold=True), _row(3), _row(4, hold=True)]
    queues = {"queues": [{"key": "cut", "label": "재단", "rows": rows}, {"key": "edge", "label": "엣지", "rows": []},
                         {"key": "assemble", "label": "조립", "rows": [_row(7, hold=True), _row(8, hold=True)]},
                         {"key": "inspect", "label": "검수", "rows": [_row(9, hold=True), _row(10)]}]}
    assert attach_step_panels(queues, None) is None
    cut = queues["queues"][0]
    # 공정 줄마다 고른 줄 판 하나만 그린다(2026-11-22 — 숨은 판을 다 그리면 주문 150건에 396KB · DOM 13,100)
    assert [(p["id"], p["next_id"], p["next_name"]) for p in cut["panels"]] == [(1, 3, "손님3")]
    assert cut["selected_id"] == 1
    assert queues["queues"][1]["selected_id"] is None and queues["queues"][1]["panels"] == []
    assert queues["queues"][2]["selected_id"] == 7 and [p["id"] for p in queues["queues"][2]["panels"]] == [7]  # 모두 보류면 첫 줄
    assert queues["queues"][3]["selected_id"] == 10 and [p["id"] for p in queues["queues"][3]["panels"]] == [10]
    # 다른 줄 판(누를 때 받는 조각) = 같은 공정 줄에서 — '끝내면 다음은' 이 다 그릴 때와 같다(보류 건너뜀 · 마지막 줄 없음)
    assert [(p["id"], p["next_id"], p["next_name"]) for p in (step_panel_for(queues, "cut", i) for i in (1, 2, 3, 4))] == [
        (1, 3, "손님3"), (2, 3, "손님3"), (3, None, ""), (4, None, "")]
    assert step_panel_for(queues, "assemble", 7)["next_id"] is None  # 다음 줄이 모두 보류
    assert step_panel_for(queues, "inspect", 9)["next_id"] == 10 and step_panel_for(queues, "inspect", 9)["key"] == "inspect"
    # 그 공정 줄에 없는 주문(다른 공정으로 옮겨 감 · 없는 번호 · 모르는 공정)은 None → 404
    for key, oid in (("edge", 1), ("cut", 9), ("cut", 999), ("paint", 1), ("cut", None)):
        assert step_panel_for(queues, key, oid) is None, (key, oid)
    # order= 가 선 줄 · 그 공정 열쇠(첫 탭) — 고른 판도 그 줄
    assert attach_step_panels(queues, 4) == "cut" and cut["selected_id"] == 4 and [p["id"] for p in cut["panels"]] == [4]
    assert attach_step_panels(queues, 9) == "inspect" and queues["queues"][3]["selected_id"] == 9
    assert attach_step_panels(queues, 999) is None and cut["selected_id"] == 1


def test_order_주소는_숫자만() -> None:
    assert parse_step_order("5107") == 5107
    for raw in (None, "", "abc", "-1", "1 OR 1=1", "1.5", "9" * 13):
        assert parse_step_order(raw) is None, raw


# --------------------------------------------------------------------------- #
# ② 문 — 태블릿 가로만, 판 없는 화면은 지금 그대로
# --------------------------------------------------------------------------- #
def test_판은_태블릿_가로_터치_넓은_창에서만(client, cohort) -> None:
    login(client)
    a, b, c, d, e = seed_cut_queue()
    set_cookies(client, TABLET)
    html = get_html(client, HOME + "?tab=steps")
    # 판 = 공정 줄마다 고른 줄 하나(재단 박서준 · 엣지 엣지집) — 다른 줄 판은 누를 때 받는다
    assert re.findall(r'data-foms-step-pane="(\d+)"', html) == [str(a.id), str(e.id)]
    assert "foms-step-confirm-modal" not in html and html.count("data-foms-step-base=") == 1  # 확인 창 없음(11-22)
    assert 'class="foms-prod-home fph-has-sp"' in html
    # 문 밖: PC 마우스 · 폰(세로) · 쿠키 없음(안전 폴백 = 다 그림)은 각각
    for cookies, want in (({"foms_ptr": "fine", "foms_vw": "wide"}, 0), ({"foms_ptr": "coarse", "foms_vw": "narrow", "foms_scr": "915"}, 0),
                          (None, 2)):
        set_cookies(client, cookies)
        out = get_html(client, HOME + "?tab=steps")
        assert out.count('data-foms-step-pane="') == want, cookies
        assert ("data-foms-step-base=" in out) == bool(want), cookies
        if not want:
            assert "fph-has-sp" not in out and STEPS_JS not in out and "fph-q__list" not in out
            # 판 없는 화면 = 지금 그대로: 줄마다 [끝](보류 줄 빼고), 줄 링크 = 작업 시트. PC 마우스는 보기 전용이라
            # [끝]이 없다(설계서 2026-11-21-production-pc-viewer §5 — [고치기] 켬일 때만, test_production_pc_viewer)
            pc = cookies["foms_ptr"] == "fine"
            assert out.count("data-foms-home-step-done") == (0 if pc else 3 + 1)
            assert f'href="/erp/production/sheet/{a.id}"' in queue_html(out, "cut")
            assert "data-foms-wide-surface-omitted" not in out  # 폰 · PC 는 생략 표식도 없다


def test_세로로_든_태블릿은_판을_빼고_가로로_돌리면_다시_받는_표식(client, cohort) -> None:
    login(client)
    seed_cut_queue()
    set_cookies(client, {"foms_ptr": "coarse", "foms_vw": "narrow", "foms_scr": "1280"})
    html = get_html(client, HOME + "?tab=steps")
    assert 'data-foms-step-pane="' not in html and html.count("data-foms-wide-surface-omitted") == 1
    assert "foms-wide-surface-recover.js" in html
    assert "data-foms-wide-surface-omitted" not in get_html(client, HOME)  # 다른 탭은 그대로


def test_파트_계정은_내_공정_탭이_없어_판도_없다(client, cohort) -> None:
    login(client, "김재단", part="cut")
    seed_cut_queue()
    set_cookies(client, TABLET)
    html = get_html(client, HOME + "?tab=steps")
    assert 'data-foms-home-tab="date"' in html and 'data-foms-step-pane="' not in html and STEPS_JS not in html


def test_레거시_셸은_판이_없다(client, monkeypatch) -> None:
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "false")
    login(client)
    seed_cut_queue()
    set_cookies(client, TABLET)
    html = get_html(client, HOME + "?tab=steps")
    assert 'data-foms-step-pane="' not in html and html.count("data-foms-home-step-done") == 4


@pytest.mark.parametrize("who", [("관리자", None, "CS", "ADMIN"), ("영업", None, "SALES", "STAFF"), ("상담", None, "CS", "STAFF")])
def test_관리자_영업_CS_도_판을_본다(client, cohort, who) -> None:
    name, part, team, role = who
    login(client, name, part=part, team=team, role=role)
    seed_cut_queue()
    set_cookies(client, TABLET)
    html = get_html(client, HOME + "?tab=steps")
    assert html.count('data-foms-step-pane="') == 2 and "data-foms-step-base=" in html


# --------------------------------------------------------------------------- #
# ③ 판 마크업
# --------------------------------------------------------------------------- #
def test_판_요소와_순서_640_그림_원본_뷰어(client, cohort) -> None:
    login(client)
    a, b, c, d, e = seed_cut_queue()
    set_cookies(client, TABLET)
    html = get_html(client, HOME + "?tab=steps")
    pane = pane_html(html, a.id)
    order = ["data-foms-step-name", "data-foms-step-sub", "fph-sp__pic", "fph-sp__spec", "data-foms-step-finish",
             "data-foms-sheet-defect-toggle", 'data-tablet-sheet-action="production-hold"', "data-foms-sheet-defect-reasons",
             "fph-sp__next"]
    assert [pane.index(k) for k in order] == sorted(pane.index(k) for k in order)
    assert f'<a href="/erp/production/sheet/{a.id}" data-foms-step-name>박서준</a> <small>#{a.id}</small>' in pane
    assert "슬라이딩 붙박이장 · W2740 × D700 × H2330" in pane
    assert f'src="/api/files/thumb/orders/x/drawing/박서준_0.png?w=640"' in pane and 'loading="lazy"' in pane
    view = json.loads(re.search(r'data-foms-step-view="([^"]+)"', pane).group(1).replace("&#34;", '"'))
    assert [f["view_url"] for f in view] == [f"/api/files/view/orders/x/drawing/박서준_{j}.png" for j in range(3)]
    assert ">도면 3장<" in pane and "눌러서 크게" in pane
    assert "<dt>색</dt><dd>그레이 · 손잡이 없음</dd>" in pane and "<dt>앞 공정</dt><dd>제작 시작 · 11/21 08:40</dd>" in pane
    assert "<dt>다음 공정</dt><dd>엣지</dd>" in pane and "엣지</dt>" not in pane  # 엣지 사양 줄 없음(D11)
    assert (f'data-foms-step-finish data-order-id="{a.id}" data-step-key="cut" data-step-label="재단" data-next-order="{b.id}">'
            in pane) and ">재단 끝</button>" in pane
    assert f'data-foms-prod-sheet-page data-order-id="{a.id}"' in pane
    assert [m for m in re.findall(r'data-foms-sheet-defect-reason="([^"]+)"', pane)] == list(_PRODUCTION_DEFECT_REASONS)
    assert "끝내면 다음은 <b>김하늘</b>" in pane
    # 고른 줄(보류 아닌 첫 줄) 판만 그리고 줄에 남색 표시 · 다른 줄 판은 그리지 않는다(누를 때 받는다)
    cut = queue_html(html, "cut")
    assert re.search(rf'<section class="fph-sp" data-foms-step-pane="{a.id}" aria-label="[^"]+">', cut)
    assert f'data-foms-step-pane="{b.id}"' not in cut and f'data-foms-step-pane="{d.id}"' not in cut
    assert '<div class="fph-sp-wait" data-foms-step-wait role="status" aria-live="polite" hidden>' in cut
    assert f'<div class="fph-qr is-on" data-foms-home-qrow="{a.id}" aria-current="true">' in cut
    # 줄 = 진짜 링크(?tab=steps&order=, 셸 교체 아님) + 판이 안 보일 때 갈 작업 시트. 줄 [끝]은 마크업에 남는다(세로로 돌리면 보인다)
    assert (f'href="/erp/production/home?tab=steps&amp;order={a.id}" data-foms-erp-no-shell="1" '
            f'data-foms-step-sheet="/erp/production/sheet/{a.id}"') in cut
    assert cut.count("data-foms-home-step-done") == 3
    # PDF 만 · 그림 0장
    assert f'class="fph-sp__pic is-file" href="/api/files/view/orders/x/drawing/엣지집_0.pdf" target="_blank"' in pane_html(html, e.id)
    assert "도면 1장 · 파일" in pane_html(html, e.id)
    d_pane = get_html(client, panel_url("cut", d.id))  # 고르지 않은 줄 = 판 하나 조각
    assert '<div class="fph-sp__pic is-none"><b data-foms-step-piclabel>도면 없음</b></div>' in pane_html(d_pane, d.id)
    # 금액 · 인라인 style · script 없음
    panes = "".join(pane_html(get_html(client, panel_url("cut", o.id)), o.id) for o in (a, b, c, d)) + pane_html(html, e.id)
    assert not re.search(r"금액|단가|price|amount|₩|\d원", panes)
    for rel in ("home_step_panel.html", "home_steps.html"):
        text = (ROOT / "templates/production/partials" / rel).read_text(encoding="utf-8")
        assert 'style="' not in text and "<script" not in text, rel


def test_보류_판은_끝_자리에_보류_중_사유_보류_해제(client, cohort) -> None:
    login(client)
    a, b, c, d, e = seed_cut_queue()
    set_cookies(client, TABLET)
    html = get_html(client, HOME + f"?tab=steps&order={c.id}")
    pane = pane_html(html, c.id)
    assert "data-foms-step-finish" not in pane
    assert ">보류 중</b><span>보류 사유 · 고객 연락 기다림</span>" in pane
    hold = re.search(r'<button[^>]*data-tablet-sheet-action="production-hold"[^>]*>.*?</button>', pane).group(0)
    assert 'class="fph-sp__act is-on"' in hold and 'data-hold-active="1"' in hold and 'data-hold-reason="고객 연락 기다림"' in hold
    assert hold.endswith(">보류 해제</button>")
    assert "끝내면 다음은 <b>오민재</b>" in pane  # 보류 아닌 다음 줄
    assert "키큰장 · W600 × D600 × H2300" in pane and "<dd>화이트 · 손잡이 블랙</dd>" in pane
    assert "<dd>제작 시작 · 11/20 16:10</dd>" in pane
    # order= 로 고른 줄 · 주소 · [다시 받기] · 첫 탭 고정
    cut = queue_html(html, "cut")
    assert f'<div class="fph-qr is-hold is-on" data-foms-home-qrow="{c.id}" aria-current="true">' in cut
    assert '<span class="fph-qr__holdtag">보류</span>' in cut
    assert f'data-foms-home-reload data-foms-erp-no-shell="1" href="{HOME}?tab=steps&amp;order={c.id}"' in html
    assert 'data-foms-home-step-pin="cut"' in html


def test_order_가_선_탭이_첫_탭이고_없는_번호는_무시(client, cohort) -> None:
    login(client)
    a, b, c, d, e = seed_cut_queue()
    set_cookies(client, TABLET)
    html = get_html(client, HOME + f"?tab=steps&order={e.id}")
    assert 'data-foms-home-step-pin="edge"' in html
    assert 'data-foms-home-steptab="edge" aria-selected="true"' in html and 'data-foms-home-steptab="cut" aria-selected="false"' in html
    assert re.search(r'<div class="fph-q fph-q--sp has-sp" id="fph-q-cut" [^>]* hidden>', html)
    for bad in ("999999", "abc", "-3"):
        out = get_html(client, HOME + f"?tab=steps&order={bad}")
        assert "data-foms-home-step-pin" not in out and f'data-foms-home-reload data-foms-erp-no-shell="1" href="{HOME}?tab=steps"' in out


def test_확인_창은_없고_실을_것(client, cohort) -> None:
    """2026-11-22 사장님 "확인 창 빼기"(두 번 누름 + 되돌리기) — 판 [끝] 확인 창 · 그 꼴 CSS(parts.css)를 싣지 않는다."""
    login(client)
    seed_cut_queue()
    set_cookies(client, TABLET)
    html = get_html(client, HOME + "?tab=steps")
    assert "foms-step-confirm-modal" not in html and "data-foms-step-modal" not in html and "pp-modal" not in html
    assert not (ROOT / "templates/production/partials/home_step_confirm.html").exists()
    assert f'data-foms-step-base="{HOME}?tab=steps"' in html and "data-foms-home-status" in html
    # 확인 창 꼴이 쓰던 parts.css 는 이제 도면 카드 판에만. 새 JS 는 머리(일찍), 시트 JS 는 문서당 한 번
    assert "css/contexts/production/parts.css" not in html
    assert html.index(STEPS_JS + "?v=20261122t") < html.index("</head>")
    assert 'js/production/foms-production-sheet-page.js?v=20261122t" defer data-foms-run-once="prod-sheet-page"' in html
    assert "js/foms/tablet-domain-sheets.js?v=" in html and "js/foms/foms-reason-sheet.js?v=" in html
    assert html.count("data-foms-reason-sheet") == 1 and "css/components/foms-reason-sheet.css?v=" in html
    # 셸 조각도 같은 것(조각 맨 앞에 새 JS)
    frag = get_html(client, HOME + "?tab=steps&view=fragment", SHELL)
    assert "<!DOCTYPE" not in frag and frag.index(STEPS_JS) < frag.index("data-foms-prod-home")
    for asset in ("foms-production-sheet-page.js", "tablet-domain-sheets.js", "foms-reason-sheet.js"):
        assert asset in frag, asset
    assert "parts.css" not in frag
    # 판 없는 화면은 하나도 싣지 않는다
    set_cookies(client, {"foms_ptr": "fine", "foms_vw": "wide"})
    pc = get_html(client, HOME + "?tab=steps")
    for asset in (STEPS_JS, "foms-production-sheet-page.js", "tablet-domain-sheets.js", "foms-reason-sheet.js", "parts.css"):
        assert asset not in pc, asset


# --------------------------------------------------------------------------- #
# ④ 판 하나 조각(view=panel, 2026-11-22) — 고른 판만 그리고 다른 줄은 누를 때 받는다
# --------------------------------------------------------------------------- #
def _norm(pane: str) -> str:
    """판 마크업 견주기 — 줄 앞 공백(include 들여쓰기)만 무시한다."""
    return re.sub(r"\s+", " ", pane).strip()


def test_판_하나_조각은_다_그릴_때와_같은_판이고_다음_손님도_같다(client, cohort) -> None:
    login(client)
    a, b, c, d, e = seed_cut_queue()
    set_cookies(client, TABLET)
    resp = client.get(panel_url("cut", b.id))
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200 and resp.headers["X-FOMS-HOME-PANEL"] == str(b.id)
    assert resp.headers["Cache-Control"] == "no-store"
    # 판 하나뿐 — 페이지 틀 · 다른 판 · 줄 · 확인 창 · 스크립트 없음, 숨김 아님
    assert re.findall(r'data-foms-step-pane="(\d+)"', body) == [str(b.id)]
    assert "<html" not in body and "data-foms-home-qrow" not in body and "foms-step-confirm-modal" not in body
    assert "<script" not in body and f'data-foms-step-pane="{b.id}" aria-label="김하늘 #{b.id}">' in body
    # 같은 줄을 order= 로 골라 다 그린 페이지의 판과 같다(공백만 다름) — 다음 손님 = 보류 건너뛴 오민재
    full = get_html(client, HOME + f"?tab=steps&order={b.id}")
    assert _norm(pane_html(body, b.id)) == _norm(pane_html(full, b.id))
    assert "끝내면 다음은 <b>오민재</b>" in body and f'data-next-order="{d.id}"' in body
    # 마지막 줄 = 다음 손님 없음 · 보류 줄 = [끝] 자리에 보류 글
    assert "fph-sp__next" not in pane_html(get_html(client, panel_url("cut", d.id)), d.id)
    held = get_html(client, panel_url("cut", c.id))
    assert "data-foms-step-finish" not in held and ">보류 중</b>" in held


def test_판_하나_조각_문_밖_파트_계정_다른_공정_없는_번호는_404(client, cohort, monkeypatch) -> None:
    login(client)
    a, b, c, d, e = seed_cut_queue()
    set_cookies(client, TABLET)
    for url in (panel_url("edge", b.id), panel_url("cut", e.id), panel_url("cut", 999999), panel_url("paint", b.id),
                f"{HOME}?tab=steps&order=abc&view=panel&step=cut", f"{HOME}?tab=steps&view=panel&step=cut",
                f"{HOME}?tab=date&order={b.id}&view=panel&step=cut"):
        assert client.get(url).status_code == 404, url
    # 문 밖(PC 마우스 · 폰 · 세로 태블릿)은 판이 없는 화면이라 조각도 없다
    for cookies in ({"foms_ptr": "fine", "foms_vw": "wide"}, {"foms_ptr": "coarse", "foms_vw": "narrow", "foms_scr": "915"},
                    {"foms_ptr": "coarse", "foms_vw": "narrow", "foms_scr": "1280"}):
        set_cookies(client, cookies)
        assert client.get(panel_url("cut", b.id)).status_code == 404, cookies
    # 파트 계정(D50 — 내 공정 탭이 없다)은 어느 파트 판도 못 받는다
    login(client, "김재단", part="cut")
    set_cookies(client, TABLET)
    for step, oid in (("cut", a.id), ("cut", b.id), ("edge", e.id)):
        assert client.get(panel_url(step, oid)).status_code == 404, (step, oid)
    # 레거시 셸도 판이 없다
    login(client, "박생산")
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "false")
    assert client.get(panel_url("cut", b.id)).status_code == 404


@pytest.mark.parametrize("who, writes", [(("이철호", "PRODUCTION", "STAFF"), True), (("관리자", "CS", "ADMIN"), True),
                                         (("상담", "CS", "STAFF"), False), (("영업", "SALES", "STAFF"), False)])
def test_판_하나_조각의_쓰기_단추는_다_그린_탭과_같은_사람만(client, cohort, who, writes) -> None:
    name, team, role = who
    login(client, name, team=team, role=role)
    a, b, c, d, e = seed_cut_queue()
    set_cookies(client, TABLET)
    body = get_html(client, panel_url("cut", b.id))
    full = get_html(client, HOME + "?tab=steps")
    for mark in ("data-foms-step-finish", "data-foms-sheet-defect-toggle", 'data-tablet-sheet-action="production-hold"'):
        assert (mark in body) == writes == (mark in pane_html(full, a.id)), (name, mark)
