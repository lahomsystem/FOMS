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

from tests.domains.test_production_pc_sheet import HOME, _edit, _login, _seed_five, _user, cohort  # noqa: F401 (cohort = 고정물)
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
    assert "'release'" in write  # 완료가 막히면 맡기만 남지 않게 되돌린다
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
