"""생산 도면 '크게 보기' 한 겹 — 그 자리 손가락 확대 · 이동(사장님 2026-11-27 "큰 화면에서 바로 확대 (Recommended)").

전에는 크게 보기 그림을 한 번 더 누르면 공용 GlobalImageViewer 가 두 번째 화면으로 떠서 확대 · 닫기를 두 번 했다.
이제 크게 보기 그림 칸(``[data-pp-v-zoom]``)에서 바로: 두 손가락 = 1 ~ 5배(손가락 가운데 기준) · 확대 뒤 한 손가락 = 이동(그림
가장자리까지만) · 두 번 두드리기 = 2.5배 ↔ 1배 · 휠 · 끌기(PC). 한 번 두드리기는 아무 것도 열지 않는다(그림이 아닌 파일 장만 새 창 — 있던 길).
다른 장으로 넘기거나 닫으면 1배, 30초 받아 오기로 다시 그려도 확대는 그대로, 창 크기가 바뀌면 경계를 다시 잰다.

서버가 그린 진짜 판 위에서 보기 JS 둘(viewer → zoom)을 Node 로 돌린다(tests/support/production_viewer_zoom_node_checks.js).
그림 칸 800 × 600, 그림 800 × 400(1배에 칸 너비에 맞음)으로 잰다. 이름 · 주문은 지어낸 값이다.
되돌리면 실패: 그림을 누르면 GlobalImageViewer.open · 확대 상한 · 하한 없음 · 이동 경계 없음 · 장을 넘겨도 확대가 남음 · 30초마다 1배.
"""
from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from models import Order
from tests.support.production_factory_seed import HOME_NONE, TABLET, set_cookies
from tests.support.production_part_claim_seed import login, make_order, make_user

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "tests/support/production_viewer_zoom_node_checks.js"
JS = ROOT / "static/js/production"
VIEWER_JS = JS / "foms-production-parts-viewer.js"
ZOOM_JS = JS / "foms-production-parts-zoom.js"
PIN = "20261127f"


@pytest.fixture
def cohort(monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")


def _page(client, tmp_path: Path) -> Path:
    """도면 셋(그림 둘 + 그림이 아닌 파일 하나) 주문 — 확정 도면 칸은 실데이터처럼 원본 주소(/api/files/view/…)를 가진다."""
    seed = make_order(2)
    order = db_session.get(Order, seed.id)
    sd = copy.deepcopy(order.structured_data)
    files = sd["drawing_current_files"]
    files.append({"key": files[0]["key"].replace("d0.png", "d2.pdf"), "filename": "d2.pdf", "sheet_id": files[0]["sheet_id"] + "p"})
    for f in files:
        f["view_url"] = "/api/files/view/" + f["key"]
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()
    who = make_user("박재단", part="cut")
    login(client, who)
    set_cookies(client, TABLET)
    resp = client.get(HOME_NONE)
    assert resp.status_code == 200, resp.status_code
    html = resp.get_data(as_text=True)
    assert html.count("data-pp-viewer") == 1 and "data-pp-v-zoom" in html
    page = tmp_path / "board.html"
    page.write_text(html, encoding="utf-8")
    return page


def _run(page: Path, steps: list[dict], **want) -> list[dict]:
    node = shutil.which("node")
    assert node, "node must be on PATH for JS checks"
    proc = subprocess.run([node, str(CHECK), str(page), json.dumps({"steps": steps, **want}, ensure_ascii=False)],
                          capture_output=True, text=True, encoding="utf-8", timeout=60, cwd=str(ROOT))
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)["out"]


def _pinch(a: list[list[int]], b: list[list[int]]) -> list[dict]:
    return [{"do": "touch", "type": "touchstart", "touches": a, "changed": a},
            {"do": "touch", "type": "touchmove", "touches": b, "changed": b}]


END2 = {"do": "touch", "type": "touchend", "touches": [], "changed": [[0, 0], [0, 0]]}


def _double(x: int, y: int) -> list[dict]:
    return [{"do": "clock", "ms": 1000}, {"do": "tap", "x": x, "y": y}, {"do": "tap", "x": x, "y": y}]


# --------------------------------------------------------------------------- #
# 손짓 — 진짜 판 위에서
# --------------------------------------------------------------------------- #
def test_두_손가락_확대_상한_하한과_손가락_가운데(client, cohort, tmp_path) -> None:
    page = _page(client, tmp_path)
    out = _run(page, [{"do": "open", "no": 1}]
               + _pinch([[350, 300], [450, 300]], [[250, 300], [550, 300]])  # 100 → 300px = 3배(칸 가운데)
               + [{"do": "touch", "type": "touchmove", "touches": [[0, 300], [1000, 300]], "changed": [[0, 300], [1000, 300]]}, END2]  # 10배 → 5배
               + _pinch([[0, 300], [1000, 300]], [[450, 300], [550, 300]]) + [END2]  # 5 × 0.1 → 1배에서 멈춤
               + _pinch([[100, 100], [200, 100]], [[50, 100], [250, 100]]) + [END2])  # 왼쪽 위(150, 100) 기준 2배
    opened = out[0]
    assert (opened["hidden"], opened["scale"], opened["transform"], opened["img_hidden"]) == (False, 1, "", False)
    assert opened["src"] == opened["view_url"] and opened["src"].startswith("/api/files/view/")  # 원본 그림 그대로(두 번째 화면이 받던 것)
    three = out[2]
    assert (three["scale"], three["tx"], three["ty"], three["prevented"], three["zoomed"]) == (3, 0, 0, True, True)
    assert three["transform"] == "translate(0px, 0px) scale(3)"
    assert out[3]["scale"] == 5 and out[4]["scale"] == 5  # 상한 5배 — 손가락을 떼도 그대로
    assert (out[6]["scale"], out[6]["transform"], out[6]["zoomed"]) == (1, "", False)  # 하한 1배
    # 손가락 가운데 아래 점이 그 자리: tx = -250 − 2 × (−250) = 250 · ty = 200 → 위아래 경계 (800 − 600) / 2 = 100 에서 멈춤
    assert (out[9]["scale"], out[9]["tx"], out[9]["ty"]) == (2, 250, 100)
    assert out[-1]["gv"] == 0  # 두 번째 화면(GlobalImageViewer) 없음


def test_확대_뒤_한_손가락_이동은_경계_안에서만_1배에서는_아무_일_없음(client, cohort, tmp_path) -> None:
    page = _page(client, tmp_path)
    one = [{"do": "touch", "type": "touchstart", "touches": [[400, 300]], "changed": [[400, 300]]}]
    out = _run(page, [{"do": "open", "no": 1}]
               + one + [{"do": "touch", "type": "touchmove", "touches": [[100, 300]], "changed": [[100, 300]]},  # 1배 밀기
                        {"do": "touch", "type": "touchend", "touches": [], "changed": [[100, 300]]}]
               + _pinch([[100, 100], [200, 100]], [[50, 100], [250, 100]]) + [END2]  # 2배(tx 250 · ty 100)
               + one + [{"do": "touch", "type": "touchmove", "touches": [[1400, 300]], "changed": [[1400, 300]]},
                        {"do": "touch", "type": "touchmove", "touches": [[400, -700]], "changed": [[400, -700]]},
                        {"do": "touch", "type": "touchend", "touches": [], "changed": [[400, -700]]}])
    slid = out[2]
    assert (slid["scale"], slid["tx"], slid["ty"], slid["page"], slid["open"]) == (1, 0, 0, "1 / 3", [])  # 넘김 손짓 없음(◀ ▶ 단추만)
    assert (out[6]["tx"], out[6]["ty"]) == (250, 100)
    right = out[8]
    assert (right["tx"], right["ty"], right["transform"]) == (400, 100, "translate(400px, 100px) scale(2)")  # 좌우 경계 (1600 − 800) / 2
    up = out[9]
    assert (up["tx"], up["ty"], up["scale"]) == (250, -100, 2)  # 위아래 경계 −100


def test_두_번_두드리기_왕복과_한_번_두드리기는_아무_것도_안_엶(client, cohort, tmp_path) -> None:
    page = _page(client, tmp_path)
    out = _run(page, [{"do": "open", "no": 1}] + _double(600, 300) + _double(600, 300)
               + [{"do": "clock", "ms": 1000}, {"do": "tap", "x": 600, "y": 300}, {"do": "click", "on": "img"}])
    first_tap, zoomed = out[2], out[3]
    assert (first_tap["scale"], first_tap["prevented"], first_tap["gv"], first_tap["open"]) == (1, False, 0, [])
    # 두드린 곳(칸 가운데 + 200) 기준 2.5배: tx = 200 − 2.5 × 200 = −300(경계 600 안) · 움직임(is-anim) · click 안 만듦
    assert (zoomed["scale"], zoomed["tx"], zoomed["ty"], zoomed["anim"], zoomed["prevented"]) == (2.5, -300, 0, True, True)
    assert zoomed["transform"] == "translate(-300px, 0px) scale(2.5)"
    back = out[6]
    assert (back["scale"], back["tx"], back["transform"], back["zoomed"]) == (1, 0, "", False)
    single = out[-1]
    assert (single["scale"], single["gv"], single["open"], single["hidden"]) == (1, 0, [], False)  # 한 번 두드림 = 아무 일 없음


def test_다른_장으로_넘기거나_닫으면_1배_파일_장은_새_창(client, cohort, tmp_path) -> None:
    page = _page(client, tmp_path)
    out = _run(page, [{"do": "open", "no": 1}] + _double(400, 300) + [{"do": "step", "by": 1}]
               + _double(400, 300) + [{"do": "step", "by": 1}, {"do": "tap", "x": 400, "y": 300}]
               + _pinch([[350, 300], [450, 300]], [[250, 300], [550, 300]])
               + [{"do": "step", "by": -1}] + _double(400, 300) + [{"do": "close"}, {"do": "open", "no": 1}])
    assert (out[3]["scale"], out[3]["page"]) == (2.5, "1 / 3")
    moved = out[4]
    assert (moved["scale"], moved["transform"], moved["zoomed"], moved["page"]) == (1, "", False, "2 / 3")
    assert out[7]["scale"] == 2.5
    pdf = out[8]
    assert (pdf["scale"], pdf["transform"], pdf["img_hidden"], pdf["page"]) == (1, "", True, "3 / 3")
    file_tap = out[9]
    assert len(file_tap["open"]) == 1 and file_tap["open"][0].endswith("d2.pdf") and file_tap["gv"] == 0  # 그림이 아닌 파일만 새 창(있던 길)
    assert (out[11]["scale"], out[11]["prevented"]) == (1, False)  # 파일 장은 손짓을 안 받는다
    assert out[15]["scale"] == 2.5
    closed, reopened = out[16], out[17]
    assert (closed["hidden"], closed["scale"], closed["transform"], closed["src"]) == (True, 1, "", None)
    assert (reopened["hidden"], reopened["scale"], reopened["transform"], reopened["page"]) == (False, 1, "", "1 / 3")


def test_휠_끌기_창_크기_받아_오기_화면_크기_배율(client, cohort, tmp_path) -> None:
    page = _page(client, tmp_path)
    out = _run(page, [{"do": "open", "no": 1},
                      {"do": "wheel", "dy": -100, "x": 400, "y": 300}, {"do": "wheel", "dy": 100, "x": 400, "y": 300}]
               + _double(400, 300)
               + [{"do": "mouse", "type": "mousedown", "x": 400, "y": 300}, {"do": "mouse", "type": "mousemove", "x": 900, "y": 300},
                  {"do": "mouse", "type": "mouseup", "x": 900, "y": 300}, {"do": "mouse", "type": "mousemove", "x": 0, "y": 300},
                  {"do": "updated"}, {"do": "stage", "rect": {"width": 400}}, {"do": "resize"}])
    assert (out[1]["scale"], out[1]["prevented"]) == (1.1, True)
    assert out[2]["scale"] == 1  # 1.1 × 0.9 = 0.99 → 1배 아래로 안 감
    assert out[5]["scale"] == 2.5
    assert (out[6]["prevented"], out[7]["tx"], out[9]["tx"]) == (True, 500, 500)  # 끌기 500px(경계 600 안) · 놓은 뒤 움직임은 무시
    updated = out[10]
    assert (updated["scale"], updated["tx"]) == (2.5, 500)  # 30초 받아 오기로 다시 그려도 확대 그대로
    resized = out[12]
    # 칸 너비 400 → 1배 그림 400 × 200 · 2.5배 1000 → 좌우 경계 (1000 − 400) / 2 = 300
    assert (resized["scale"], resized["tx"], resized["resize_listeners"]) == (2.5, 300, 1)

    shrunk = _run(page, [{"do": "open", "no": 1}] + _double(600, 300), ui_zoom=0.8)[-1]
    # 화면 크기 80%: 옮김은 보이는 px(−300)로 재고 style 에는 ÷ 0.8(전역 뷰어와 같은 식)
    assert (shrunk["scale"], shrunk["tx"], shrunk["transform"]) == (2.5, -300, "translate(-375px, 0px) scale(2.5)")


# --------------------------------------------------------------------------- #
# 원문 계약
# --------------------------------------------------------------------------- #
def test_보기_JS_는_전역_뷰어를_더는_안_부르고_확대는_새_파일() -> None:
    viewer = VIEWER_JS.read_text(encoding="utf-8")
    zoom = ZOOM_JS.read_text(encoding="utf-8")
    assert "GlobalImageViewer" not in viewer and "gv.open" not in viewer and "function zoom()" not in viewer
    assert "GlobalImageViewer.open" not in zoom
    assert "zoomCall('reset')" in viewer and viewer.count("zoomCall('reset')") == 3  # 열기 · 넘기기 · 닫기
    assert "render(); zoomCall('refit');" in viewer
    assert "window.FomsPartsZoom = {" in zoom and "MAX = 5" in zoom and "TAP_ZOOM = 2.5" in zoom
    assert "window.fomsUiZoom" in zoom and "s.tx / z" in zoom  # 화면 크기 배율 보정(전역 뷰어와 같은 식)
    assert "'touchmove', onTouchMove, { passive: false }" in zoom and "gesture" not in zoom  # touch* 로만(iOS gesture* 안 씀)
    assert "bound.zoom === root" in zoom and "bound.zoomDoc" in zoom  # 셸 조각 교체로 다시 실행돼도 한 번만 묶인다
    for name, src in (("viewer", viewer), ("zoom", zoom)):
        assert len(src.splitlines()) < 300, name
        assert "innerHTML" not in src and "const " not in src and "let " not in src and "=>" not in src, name  # ES5 꼴


def test_그림_칸_touch_action_과_칸_안_확대() -> None:
    css = (ROOT / "static/css/contexts/production/parts.css").read_text(encoding="utf-8")
    assert ".pp-vimg { touch-action: none; -webkit-user-select: none; user-select: none; }" in css
    rule = re.search(r"\.pp-vimg \{ flex: 1;[^}]*\}", css).group(0)
    assert "overflow: hidden" in rule and "cursor: zoom-in" not in rule  # 칸 안에서만 확대 — 아래 단추 줄을 안 가린다
    assert ".pp-vimg.is-anim img { transition: transform 0.22s ease; }" in css
    assert ".pp-vimg.is-zoomed { cursor: grab; }" in css
    assert "will-change:" not in css.split("/* 그 자리 손가락 확대", 1)[1].split("/* ──", 1)[0]
    overlays = (ROOT / "templates/production/partials/home_parts_overlays.html").read_text(encoding="utf-8")
    assert 'class="pp-vimg" data-pp-v-zoom' in overlays and "style=" not in overlays


def test_핀() -> None:
    scripts = (ROOT / "templates/production/partials/home_scripts.html").read_text(encoding="utf-8")
    viewer_tag = f"js/production/foms-production-parts-viewer.js') }}}}?v={PIN}\" defer></script>"
    zoom_tag = f"js/production/foms-production-parts-zoom.js') }}}}?v={PIN}\" defer></script>"
    assert viewer_tag in scripts and zoom_tag in scripts
    assert scripts.index(viewer_tag) < scripts.index(zoom_tag) < scripts.index("foms-production-parts-claim.js")
    styles = (ROOT / "templates/production/partials/home_styles.html").read_text(encoding="utf-8")
    assert f"css/contexts/production/parts.css') }}}}?v=20261127s" in styles  # 비평 시안 · 카드 키 일괄로 올림
