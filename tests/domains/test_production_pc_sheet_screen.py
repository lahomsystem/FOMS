"""PC 도면 목록 창 화면 계약(사장님 2026-11-24 "PC 에서도 도면별로 체크") — 창 틀 · 스크립트 싣는 곳 · JS · CSS.

* 창 틀(home_pc_sheet.html)은 PC 날짜 · 찾기 탭에만 하나, 쓰기 파일 · 손 체크 확인 창(작업 시트와 같은 조각)은 [고치기] 켬일 때만.
  '내 공정' · '바뀐 것' 탭 · 태블릿은 싣지 않는다(음성 대조).
* 새 JS 300줄 아래 · node --check · 읽기 try/catch + success 검사 · innerHTML 없음(줄 칸은 서버 매크로 HTML 을 outerHTML 로 바꿔 끼움) ·
  인라인 style 없음, pc.css 새 덩이 글자 15px 이상 · 단추 46px · 상태 토큰 = 도면 판(parts.css) 값 · 색 짝 거리 · 대비.
창 자료 API · 칸 · 쓰기 길은 ``test_production_pc_sheet.py``.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from tests.domains.test_production_pc_sheet import HOME, TABLET, _edit, _login, _order, _seed_five, _user, cohort  # noqa: F401
from tests.support.color_contrast import contrast_ratio, hex_rgb, pair_distances

ROOT = Path(__file__).resolve().parents[2]
VIEW_JS = ROOT / "static/js/production/foms-production-pc-sheet.js"
WRITE_JS = ROOT / "static/js/production/foms-production-pc-sheet-write.js"


def test_창_틀_스크립트는_PC_날짜_찾기만_쓰기는_고치기_켬만(client, cohort) -> None:
    order, _ = _seed_five()
    admin = _login(client, _user("관리", role="ADMIN", team="CS"))
    for url in (HOME + f"?day={order.erp_construction_date}", HOME + "?tab=all"):
        html = client.get(url).get_data(as_text=True)
        assert html.count("data-foms-pc-sheet-box") == 1 and 'data-edit="0"' in html, url
        assert "foms-production-pc-sheet.js?v=" in html and "foms-production-sheet-parts.js?v=" in html, url
        assert "foms-reason-sheet.css?v=" in html, url
        assert "foms-production-pc-sheet-write.js" not in html and "data-foms-sheet-confirm" not in html, url
    for url in (HOME + "?tab=steps", HOME + "?tab=changes"):
        html = client.get(url).get_data(as_text=True)
        assert "data-foms-pc-sheet-box" not in html and "foms-production-pc-sheet" not in html, url
    _login(client, admin)
    _edit(client)
    html = client.get(HOME + f"?day={order.erp_construction_date}").get_data(as_text=True)
    assert 'data-edit="1"' in html and "foms-production-pc-sheet-write.js?v=" in html
    assert html.count("data-foms-sheet-confirm hidden") == 1  # [모두 체크] 확인 창 = 작업 시트와 같은 조각
    assert html.index("foms-production-sheet-parts.js") < html.index("foms-production-pc-sheet.js") < html.index("pc-sheet-write.js")


def test_도면_카드_읽기를_못_하는_사람은_PC_공정_칸이_글만(client, cohort, monkeypatch) -> None:
    """켜진 프리랜서처럼 ``parts_read`` 가 거짓이면(PC 도면 창 API 가 403) 칸은 누르는 칸이 아니라 글만, 창 틀도 없다(2026-11-27).

    음성 대조: 같은 화면 · 같은 계정에서 플래그만 참이면 칸 넷이 창을 연다.
    """
    import foms.services.production.pc_view as pc_view
    from foms.services.production.part_access import VIEW_NONE

    order, _ = _seed_five()
    url = HOME + f"?day={order.erp_construction_date}"
    _login(client, _user("관리", role="ADMIN", team="CS"))
    on = client.get(url).get_data(as_text=True)
    assert on.count('data-foms-pc-sheet="') >= 4 and "data-foms-pc-sheet-box" in on
    monkeypatch.setattr(pc_view, "part_view_mode", lambda user: VIEW_NONE)
    off = client.get(url).get_data(as_text=True)
    assert 'data-foms-pc-sheet="' not in off and "data-foms-pc-sheet-box" not in off
    assert 'aria-label="공정"' in off  # 칸 글은 그대로


def _sheet(client, oid: int) -> str:
    return client.get(f"/erp/production/sheet/{oid}").get_data(as_text=True)


def test_PC_로_연_작업_시트_공정_칸은_같은_창_태블릿은_그대로(client, cohort) -> None:
    """둘째 판(2026-11-24 지휘): 작업 시트의 PC/태블릿 가르기는 이 화면이 이미 쓰는 pc_view(pc.css · 보기 전용 표 · 시공일 D-n 과 같은 판정)."""
    order, _ = _seed_five()
    oid, bare_id = order.id, _order("빈도면", 0).id
    admin = _login(client, _user("관리", role="ADMIN", team="CS"))
    view = _sheet(client, oid)  # 보기 전용 — 칸은 div, 누르면 보기 창(단추 · 물음 · 쓰기 파일 없음)
    assert view.count('tabindex="0" role="button" aria-haspopup="dialog" data-foms-pc-sheet="') == 4
    assert view.count("data-foms-pc-sheet-box") == 1 and "foms-production-pc-sheet.js?v=" in view
    assert "pc-sheet-write.js" not in view and "data-foms-pc-sheet-ask" not in view and "data-foms-sheet-confirm" not in view
    _login(client, admin)
    _edit(client)
    edit = _sheet(client, oid)  # [고치기] — 확인 창은 시트 것 하나(겹치지 않음). 2026-11-27 "도면이 주, 작업 시트는 보기": 도면 있는 주문은
    # [고치기]여도 칸이 보기 줄(체크 칸 없음) — 누르면 같은 도면 목록 창(옛 단언 'data-foms-sheet-step="cut"' → 없음)
    assert edit.count('aria-haspopup="dialog" data-foms-pc-sheet="') == 4 and 'data-foms-sheet-step="cut"' not in edit
    assert edit.count('data-foms-sheet-line="') == 4
    assert edit.count("data-foms-sheet-confirm hidden") == 1 and "pc-sheet-write.js?v=" in edit and "data-foms-pc-sheet-ask" in edit
    assert edit.index("foms-production-sheet-page.js") < edit.index("foms-production-pc-sheet.js") < edit.index("pc-sheet-write.js")
    assert "data-foms-pc-sheet" not in _sheet(client, bare_id)  # 도면 0장 = 지금 그대로(통째 손 체크)
    part = _login(client, _user("재단", part="cut"))  # 파트 계정 — 잠금 안내 글 그대로, 칸은 보기 창
    _edit(client)
    locked = _sheet(client, oid)
    assert "data-foms-sheet-steps-locked" in locked and locked.count('data-foms-pc-sheet="') == 4 and part.id
    _login(client, admin, TABLET)  # 음성 대조 — 태블릿 시트에는 표지 · 창 · 스크립트 하나도 없다
    tablet = _sheet(client, oid)
    steps = tablet.split('aria-label="공정"', 1)[1].split("</section>", 1)[0]
    assert "data-foms-pc-sheet" not in tablet and "foms-production-pc-sheet" not in tablet and "aria-haspopup" not in steps


# --------------------------------------------------------------------------- #
# 정적 — JS · CSS
# --------------------------------------------------------------------------- #
def test_새_JS_는_300줄_아래_읽기는_try_catch_와_success_검사() -> None:
    view, write = VIEW_JS.read_text(encoding="utf-8"), WRITE_JS.read_text(encoding="utf-8")
    for js in (view, write):
        assert len(js.splitlines()) < 300 and "innerHTML" not in js and ".style." not in js
    assert "try {" in view and "body.success === true" in view and "/api/production/part-sheet?" in view
    assert "/api/production/part-history?" in view and "sp.renderLog(" in view
    assert "outerHTML = d.cells_html" in view and "S.busy" in view and "aria-disabled" in view
    assert "e.key === 'Escape'" in view and "e.key !== 'Tab'" in view and "back.focus()" in view
    assert "'/api/production/part-marks'" in write and "/production/steps" in write and "sp.beforeToggle(page, btn, true, go)" in write
    assert "fetch(" not in write.replace("window.fomsMutationFetch", "") or "try {" in write
    # [완료 처리] = action check 한 요청(2026-11-25 multi-holder 판결 2) — 옛 두 요청 길(맡기 → 완료 → 막히면 맡기 취소)은 없다
    assert "function check(d, r) { return mark(d, r.key, 'check', r.seen); }" in write
    for gone in ("'take'", "'done'", "rel.ok ? fin : rel", "picked_by_user_id"):
        assert gone not in write, gone
    # [완료 취소] 뒤 작업하는 사람이 나 하나면 시작 취소까지 · 같이 작업한 장 · 남의 장은 완료 취소만(둘째 판)
    assert "!onlyMe(m, d.me)" in write and "return mark(d, r.key, 'release', 'need', d.me);" in write
    assert "if (!r.undo_releases ||" in write  # 시작 취소까지는 서버가 준 판정(2분)일 때만(셋째 판 4)
    # 단추 이름(K3) — 줄 글은 서버가 사람마다 만든 r.lines 그대로(JS 는 글을 안 만든다)
    assert "r.act === 'check' ? '완료 처리' : '완료 취소'" in view and "actButton('모두 완료 처리', 'all'" in view
    assert "actButton('모두 완료 취소', 'hand-off'" in view and "var meta = r.lines || [];" in view
    assert "'작업'" not in view and "'작업 취소'" not in view and "'모두 작업" not in view and "r.holder" not in view
    # 쓰는 중에는 닫기 · Esc · 바깥 누름 모두 막고 10초 넘으면 푼다(셋째 판 2) · 첫 화면 제작 완료 뒤 닫으면 [다시 받기] 길(셋째 판 3)
    assert "if (box.hidden || S.busy) { return; }" in view and "var BUSY_MS = 10000;" in view and "'[data-foms-pc-sheet-act], .fpc-sheet__x'" in view
    assert "res.reload = true;" in write and "root.querySelector('[data-foms-home-reload]')" in write
    assert "if (writer() && r.act)" in view  # 단추는 서버 act 만 따른다(막힌 장은 서버가 비움)
    # "제작 완료할까요?" — 태블릿 창과 같은 본문 · 0.8초 잠금 · 지금 제작 완료 API
    assert "장이 모두 완료됐어요. 제작 완료하면 시공 대기로 넘어가요." in write and "var LOCK_MS = 800;" in write
    assert "/production/complete" in write and "res.data.order_ready && W.ask(box, S.data)" in view
    # 작업 시트: 칸 누름은 붙잡는 단계에서 받고 밖으로 안 보냄 · 쓰고 닫으면 공정 줄을 서버 값으로(단계가 바뀌면 통째)
    assert "}, true);" in view and view.count("e.stopPropagation();") == 2 and "window.FomsPcSheetWrite.afterClose(root, S.reload)" in view
    assert "data-foms-prod-page-stage" in write and "window.location.reload()" in write
    sheet = (ROOT / "static/js/production/foms-production-sheet-parts.js").read_text(encoding="utf-8")
    assert "renderLog: renderLog" in sheet
    node = shutil.which("node")
    if node:
        for path in (VIEW_JS, WRITE_JS):
            subprocess.run([node, "--check", str(path)], check=True)


def test_새_창_틀은_인라인_style_이_없다() -> None:
    tpl = (ROOT / "templates/production/partials/home_pc_sheet.html").read_text(encoding="utf-8")
    assert "style=" not in tpl and "<script" not in tpl and 'role="dialog" aria-modal="true"' in tpl


def test_pc_css_창_덩이는_본문_15px_이상_단추_46px_토큰은_도면_판_값() -> None:
    css = (ROOT / "static/css/contexts/production/pc.css").read_text(encoding="utf-8")
    block = css.split("/* ── 공정 칸 → 도면 목록 창", 1)[1]
    sizes = [int(n) for n in re.findall(r"font-size: calc\((\d+)px \* var\(--foms-fs, 1\)\)", block)]
    assert sizes and min(sizes) >= 15 and "font-size: " not in re.sub(r"font-size: calc\(\d+px \* var\(--foms-fs, 1\)\)", "", block)
    assert block.count("min-height: 46px") == 2 and "!important" not in block  # 단추 46px = 80% 배율에서 보이는 36.8px
    parts = (ROOT / "static/css/contexts/production/parts.css").read_text(encoding="utf-8")
    tok = dict(re.findall(r"(--f(?:ph|pc)-[a-z0-9-]+):\s*(#[0-9a-f]{6});", css + parts))
    for name in ("need-50", "need-700", "done-50", "done-800", "basic-50", "basic-700"):
        assert tok[f"--fpc-{name}"] == tok[f"--fph-{name}"], name
    bgs = [hex_rgb(tok[f"--fpc-{k}"]) for k in ("need-50", "done-50", "basic-50")]
    for i in range(3):
        for j in range(i + 1, 3):
            normal, deu, pro = pair_distances(bgs[i], bgs[j])
            assert normal >= 10 and deu >= 6 and pro >= 6, (i, j)
    for bg, fg in (("need-50", "need-700"), ("done-50", "done-800"), ("basic-50", "basic-700")):
        assert contrast_ratio(hex_rgb(tok[f"--fpc-{bg}"]), hex_rgb(tok[f"--fpc-{fg}"])) >= 4.5, bg
