"""생산 도면 펜 기록 — 화면 몫(일꾼 ⓒ, 설계서 docs/specs/2026-11-28-production-pen-record_SPEC.md §6 · §9-3 '화면').

서버 몫(ⓑ — 판 카드 ``note`` · 판 설정 ``pen`` · API 셋)은 다른 일꾼이 만든다. 여기서는 약속한 꼴을 흉내 내 템플릿 · JS 를 본다:
판 카드 재료 ``note = {version, by, at, view_url}`` · ``note_old`` 는 ``build_part_board`` 를 감싸 얹고, 판 설정 ``pen = {on, can_write, first}``
는 ``_part_screen`` 을 감싸 얹는다(스위치가 꺼지면 ``pen`` 키가 없다). API 는 Node 가짜 fetch 가 답한다.

* 스위치 꺼짐 = 새 마크업 · 새 CSS/JS 태그 0, 도면 보기 머리 줄 · 아래 줄이 바탕 커밋(881aca26c)과 한 글자도 같다.
* 켬 + note = 카드 속성 넷 · 딱지(그림 칸 안), note_old = data-note-old, 쓰기 문(can_write)이 없으면 [기록 쓰기] · 쓰는 줄 0.
* 쓰기 JS 둘은 첫 화면에 script 로 싣지 않는다 — [기록 쓰기]를 처음 누를 때 받는다.
* 쓰는 상태(Node, tests/support/production_pen_node_checks.js): 펜 · 마우스 = 쓰기, 손가락 = 안 씀 · 지우개(댄 것 하나) · 되돌리기 · 다시 하기 ·
  [저장] 잠김 · 풀림 · 다 지우고 [저장] = DELETE · 30초 받아 오기에도 쓰기 화면 그대로 · 409 NOTE_CHANGED 때 쓴 것 그대로.
이름은 모두 지어낸 값이다(김재단 · 정하늘).
"""
from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from flask import url_for
from sqlalchemy.orm.attributes import flag_modified

import foms.web.production.home as home_view
from db import db_session
from foms.services.production import pen_record
from models import Order
from tests.support.production_factory_seed import HOME_NONE, TABLET, set_cookies
from tests.support.production_part_claim_seed import login, make_order, make_user

ROOT = Path(__file__).resolve().parents[2]
JS = ROOT / "static/js/production"
CHECK = ROOT / "tests/support/production_pen_node_checks.js"
CSS = ROOT / "static/css/contexts/production/pen-record.css"
PIN = "20261128q"
NOTE = {"version": 3, "by": "김재단", "at": "11/27 16:40", "view_url": "/api/files/view/orders/9/production/note3.png"}
# 바탕 커밋(881aca26c) home_parts_overlays.html 의 도면 보기 — 스위치 꺼짐이면 한 글자도 같아야 한다(머리 줄 · 아래 줄)
BASE_VIEWER = """<div class="pp-view" data-pp-viewer role="dialog" aria-modal="true" aria-labelledby="foms-part-view-title" hidden>
  <header class="foms-prod-home__bar pp-vtop">
    <h2 class="foms-prod-home__title" id="foms-part-view-title" data-pp-v-title>도면</h2>
    <span class="foms-prod-home__date" data-pp-v-sub></span>
  </header>
  <button type="button" class="pp-vimg" data-pp-v-zoom aria-label="손가락으로 크게 보기"><img data-pp-v-img alt=""></button>
  <div class="pp-vbot">
    <button type="button" class="foms-prod-home__btn pp-nav" data-pp-v-step="-1" aria-label="앞 장">◀</button>
    <b class="pp-page" data-pp-v-page>1 / 1</b>
    <button type="button" class="foms-prod-home__btn pp-nav" data-pp-v-step="1" aria-label="다음 장">▶</button>
    <span class="fph-dr__by pp-by" data-pp-v-by></span>
    <span class="pp-vsp"></span>
    <button type="button" class="foms-prod-home__btn pp-close" data-pp-v-close>닫기</button>
    <span class="pp-vact" data-pp-v-act></span>
  </div>
</div>"""
BASE_VIEWER = "\n".join(line.lstrip() for line in BASE_VIEWER.split("\n"))  # 앱이 HTML 줄 앞 공백을 걷어 낸다 — 화면에 가는 꼴로 견준다
BASE_VIEWER_BOTTOM = BASE_VIEWER.split('<div class="pp-vbot">', 1)[1].rsplit("</div>", 1)[0]
NEW_MARKERS = ("data-note-", "pp-ptag", "pen-record.css", "foms-production-pen", "data-pp-pbar", "pp-view--pen", PIN,
               "data-pp-pen", "data-pp-ptext", "data-pp-ptoast", "생산 기록")


@pytest.fixture
def cohort(monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")


def _fake_server(monkeypatch, *, can_write: bool = True, first: bool = False, note_on=(1,), old_on=(2,), note: dict | None = None) -> None:
    """서버 일꾼(ⓑ) 약속 흉내 — 판 카드 note · note_old, 판 설정 pen(스위치 켬일 때만 — 꺼지면 키가 없다)."""
    real_board = home_view.build_part_board
    real_screen = home_view._part_screen

    def board(*args, **kwargs):
        built = real_board(*args, **kwargs)
        for pane in built["panes"].values():
            for card in pane["cards"]:
                if card["no"] in note_on:
                    card["note"] = dict(note or NOTE)
                if card["no"] in old_on:
                    card["note_old"] = True
        return built

    def screen(*args, **kwargs):
        out = real_screen(*args, **kwargs)
        if out.get("part_config") is not None and pen_record.enabled():
            out["part_config"]["pen"] = {"on": True, "can_write": can_write, "first": first}
        return out

    monkeypatch.setattr(home_view, "build_part_board", board)
    monkeypatch.setattr(home_view, "_part_screen", screen)


def _seed(client):
    """확정 그림 도면 셋 주문 — 확정 도면 칸은 실데이터처럼 원본 주소(/api/files/view/…)를 가진다."""
    seed = make_order(3)
    order = db_session.get(Order, seed.id)
    sd = copy.deepcopy(order.structured_data)
    for f in sd["drawing_current_files"]:
        f["view_url"] = "/api/files/view/" + f["key"]
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()
    login(client, make_user("김재단", part="cut"))
    set_cookies(client, TABLET)
    return seed


def _home(client) -> str:
    resp = client.get(HOME_NONE)
    assert resp.status_code == 200, resp.status_code
    return resp.get_data(as_text=True)


def _stable(html: str) -> str:
    """요청마다 바뀌는 값(CSRF 토큰 · 받아 오기 첫 시각)만 지운다."""
    html = re.sub(r'(name="csrf-token" content=")[^"]*', r"\1", html)
    return re.sub(r'(data-pp-since=")[^"]*', r"\1", html)


def _card(html: str, no: int) -> str:
    for card in re.findall(r"<article class=\"pp-card[^>]*>.*?</article>", html, flags=re.S):
        head = card.split(">", 1)[0]
        if "data-pp-card" in head and f'data-no="{no}"' in head:
            return card
    raise AssertionError(f"카드 {no} 없음")


# --------------------------------------------------------------------------- #
# 스위치 꺼짐 — 지금과 한 글자도 같다
# --------------------------------------------------------------------------- #
def test_꺼짐_화면은_새_마크업_0_이고_도면_보기가_바탕과_같다(client, cohort, monkeypatch) -> None:
    monkeypatch.delenv(pen_record.SWITCH_ENV, raising=False)
    _seed(client)
    plain = _home(client)
    _fake_server(monkeypatch)  # 서버가 note 를 실어도 스위치가 꺼지면 화면은 그대로
    noted = _home(client)
    assert BASE_VIEWER in plain and BASE_VIEWER in noted
    for marker in NEW_MARKERS:
        assert marker not in plain and marker not in noted, marker
    assert _stable(plain) == _stable(noted)
    assert "foms-production-parts-viewer.js?v=20261127y" in plain and "foms-production-parts-zoom.js?v=20261127f" in plain  # 옛 핀 그대로


def test_꺼짐_작업_시트도_딱지_0(client, cohort, monkeypatch, app) -> None:
    monkeypatch.delenv(pen_record.SWITCH_ENV, raising=False)
    seed = _seed(client)
    with app.test_request_context():
        url = url_for("erp_production_page.erp_production_sheet_page", order_id=seed.id)
    plain = client.get(url).get_data(as_text=True)
    _sheet_note(monkeypatch)
    noted = client.get(url).get_data(as_text=True)
    assert 'data-foms-sheet-dwg-th="0"' in plain
    for marker in NEW_MARKERS:
        assert marker not in noted, marker
    assert _stable(plain) == _stable(noted)


def _sheet_note(monkeypatch) -> None:
    real = home_view.build_production_sheet_view

    def sheet(*args, **kwargs):
        view = real(*args, **kwargs)
        view["drawing_files"][0]["note"] = dict(NOTE)
        return view

    monkeypatch.setattr(home_view, "build_production_sheet_view", sheet)


# --------------------------------------------------------------------------- #
# 스위치 켬 — 카드 속성 · 딱지 · 머리 줄 · 늦게 받는 쓰기 JS
# --------------------------------------------------------------------------- #
def test_켬_기록_있는_카드는_속성_넷과_딱지_바뀌기_전은_data_note_old(client, cohort, monkeypatch) -> None:
    monkeypatch.setenv(pen_record.SWITCH_ENV, "1")
    _fake_server(monkeypatch)
    _seed(client)
    html = _home(client)
    one, two, three = _card(html, 1), _card(html, 2), _card(html, 3)
    head = one.split(">", 1)[0]
    assert (f'data-note-v="3"' in head and 'data-note-by="김재단"' in head and 'data-note-at="11/27 16:40"' in head
            and f'data-note-url="{NOTE["view_url"]}"' in head and "data-note-old" not in head)
    img = re.search(r'<button type="button" class="pp-img" data-pp-open[^>]*>.*?</button>', one, flags=re.S).group(0)
    assert img.endswith('alt=""><span class="pp-ptag" data-pp-ptag>생산 기록</span></button>')  # 그림 칸 안(카드 높이 그대로)
    assert 'aria-label="가짜고객 도면 1/3 크게 보기 · 생산 기록"' in img
    assert 'data-note-old="1"' in two.split(">", 1)[0] and "data-note-v" not in two and "pp-ptag" not in two
    assert "data-note-" not in three and "pp-ptag" not in three
    # 도면 보기: 머리 줄 한 줄(보는 줄 · 쓰는 줄 · 묻는 줄) — 아래 줄은 지금 그대로(12번 답)
    assert html.count("data-pp-pbar") == 1 and 'class="pp-view pp-view--pen"' in html
    assert BASE_VIEWER_BOTTOM in html
    for text in ("‹ 닫기", ">생산 기록</button>", ">원본</button>", ">기록 쓰기</button>", ">취소</button>", ">펜</button>", ">형광펜</button>",
                 ">텍스트</button>", ">화살표</button>", ">지우개</button>", ">저장</button>", "쓴 것을 버릴까요?", "저장하지 않은 기록이 사라져요.",
                 ">계속 쓰기</button>", ">버리기</button>"):
        assert text in html, text
    for label in ("되돌리기", "다시 하기", "빨강", "파랑", "검정", "가늘게", "보통", "굵게"):
        assert f'aria-label="{label}"' in html, label
    # 쓰기 JS 둘은 첫 화면에 script 로 싣지 않는다 — [기록 쓰기]의 data-* 주소로 처음 누를 때 받는다
    assert not re.search(r"<script[^>]+foms-production-pen", html)
    assert f'data-pp-pen-ink="/static/js/production/foms-production-pen-ink.js?v={PIN}"' in html
    assert f'data-pp-pen-js="/static/js/production/foms-production-pen.js?v={PIN}"' in html
    assert f"pen-record.css?v={PIN}" in html
    assert f"foms-production-parts-viewer.js?v={PIN}" in html and f"foms-production-parts-zoom.js?v={PIN}" in html
    assert "20261127y" not in html  # 켬이면 새 핀만
    cfg = json.loads(re.search(r'data-foms-parts-config="([^"]*)"', html).group(1).replace("&#34;", '"').replace("&quot;", '"'))
    assert cfg["pen"] == {"on": True, "can_write": True, "first": False}


def test_켬_쓰기_문이_없으면_기록_쓰기_쓰는_줄_0(client, cohort, monkeypatch) -> None:
    monkeypatch.setenv(pen_record.SWITCH_ENV, "1")
    _fake_server(monkeypatch, can_write=False)
    _seed(client)
    html = _home(client)
    assert "data-pp-pbar" in html and "data-pp-pshow" in html  # [생산 기록 | 원본]은 누구나(6번 답)
    for marker in ("data-pp-pen-open", "data-pp-pedit", "data-pp-pask", "data-pp-ptext", "data-pp-ptoast", "foms-production-pen"):
        assert marker not in html, marker


def test_켬_작업_시트_작은_그림_딱지(client, cohort, monkeypatch, app) -> None:
    monkeypatch.setenv(pen_record.SWITCH_ENV, "1")
    seed = _seed(client)
    _sheet_note(monkeypatch)
    with app.test_request_context():
        url = url_for("erp_production_page.erp_production_sheet_page", order_id=seed.id)
    html = client.get(url).get_data(as_text=True)
    th = re.search(r'<button type="button" class="foms-prod-page__th[^"]*"\s+data-foms-sheet-dwg-th="0".*?</button>', html, flags=re.S).group(0)
    assert '<b class="pp-ptag pp-ptag--th">생산 기록</b>' in th and "· 생산 기록\"" in th
    assert html.count("pp-ptag--th") == 1 and f"pen-record.css?v={PIN}" in html


# --------------------------------------------------------------------------- #
# 원문 계약 — 래칫 · 손가락 구분 · 공용 쓰기 길 · 꺼짐이면 하는 일 없음
# --------------------------------------------------------------------------- #
def test_원문_계약() -> None:
    pen = (JS / "foms-production-pen.js").read_text(encoding="utf-8")
    ink = (JS / "foms-production-pen-ink.js").read_text(encoding="utf-8")
    viewer = (JS / "foms-production-parts-viewer.js").read_text(encoding="utf-8")
    zoom = (JS / "foms-production-parts-zoom.js").read_text(encoding="utf-8")
    for name, src in (("pen", pen), ("ink", ink), ("viewer", viewer), ("zoom", zoom)):
        assert len(src.splitlines()) < 300, name
        assert "innerHTML" not in src and "=>" not in src and not re.search(r"(?<![\w.])(const|let)\s", src), name  # ES5 꼴
        assert "style=\"" not in src and "onerror" not in src, name
    assert "e.pointerType === 'touch'" in ink and "e.preventDefault(); // 호환 mouse" in ink  # 손가락은 확대 · 이동(14번 답 "펜으로만")
    assert "MAX_OBJS = 300" in ink and "MAX_NUMS = 2000" in ink and "MAX_TEXT = 40" in ink and "BASE_W = 1478" in ink
    assert "window.fomsMutationFetch" in pen and "var data = body.data || {}; // 앞 층 거절은 data: null" in pen  # parts.js post() · handle() 과 같은 길
    assert "REFUSE[data.code || body.code] || REFUSE.SAVE_FAILED" in pen and "opts.headers['X-CSRFToken'] = window.fomsCsrfToken()" in pen
    assert "'/api/production/drawing-notes'" in pen and "form.append('ink', blob, 'ink.png')" in pen
    assert "!inking()" in zoom and "ink.style.transform = img.style.transform" in zoom
    assert "if (!card || !viewer || penEditing()) { return; }" in viewer  # 쓰는 동안 다시 안 그림(§6-3 끝)
    css = CSS.read_text(encoding="utf-8")
    assert ".pp-pbar { flex: 0 0 52px; height: 52px;" in css and "--pp-pen: #5a67d8;" in css
    assert "56px" not in css  # 큰 단추 없음(9번 답)
    for size in re.findall(r"font-size:\s*([^;]+);", css):
        assert re.fullmatch(r"calc\(\d+px \* var\(--foms-fs, 1\)\)", size.strip()), size


# --------------------------------------------------------------------------- #
# 쓰는 상태 — Node(진짜 판 + 늦게 받는 쓰기 JS 둘)
# --------------------------------------------------------------------------- #
def _page(client, monkeypatch, tmp_path: Path, **pen) -> Path:
    monkeypatch.setenv(pen_record.SWITCH_ENV, "1")
    _fake_server(monkeypatch, **pen)
    _seed(client)
    page = tmp_path / "board.html"
    page.write_text(_home(client), encoding="utf-8")
    return page


def _run(page: Path, steps: list[dict], **want) -> list[dict]:
    node = shutil.which("node")
    assert node, "node must be on PATH for JS checks"
    proc = subprocess.run([node, str(CHECK), str(page), json.dumps({"steps": steps, **want}, ensure_ascii=False)],
                          capture_output=True, text=True, encoding="utf-8", timeout=60, cwd=str(ROOT))
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)["out"]


def _payload(write: dict) -> dict:
    return json.loads(next(e["v"] for e in write["form"] if e["k"] == "payload"))


LINE_A = [[100, 100], [160, 100], [220, 100], [300, 100]]
LINE_B = [[100, 500], [160, 500], [220, 500], [300, 500]]


def test_펜_마우스는_쓰고_손가락은_안_쓴다_되돌리기_저장_잠김_풀림_PUT(client, cohort, monkeypatch, tmp_path) -> None:
    page = _page(client, monkeypatch, tmp_path)
    out = _run(page, [{"do": "open", "no": 2}, {"do": "write"},
                      {"do": "pointer", "type": "touch", "path": LINE_A}, {"do": "pointer", "type": "pen", "path": LINE_A},
                      {"do": "pointer", "type": "mouse", "path": LINE_B}, {"do": "btn", "v": "undo"}, {"do": "btn", "v": "undo"},
                      {"do": "btn", "v": "redo"}, {"do": "btn", "v": "save"}])
    opened, editing, finger, pen, mouse, undo1, undo2, redo, saved = out
    assert (opened["has_pen"], opened["loaded"], opened["write"]) == (False, [], {"hidden": False, "text": "기록 쓰기"})  # 첫 화면 값 0
    assert editing["loaded"] == [f"/static/js/production/foms-production-pen-ink.js?v={PIN}", f"/static/js/production/foms-production-pen.js?v={PIN}"]
    assert (editing["editing"], editing["edit_cls"], editing["view_hidden"], editing["edit_hidden"], editing["vbot_hidden"]) == (True, True, True, False, True)
    assert editing["title"] == "도면 2/3 · 생산 기록" and editing["ink"] and editing["gets"][0]["url"].startswith("/api/production/drawing-notes?order_id=")
    assert editing["save"] == {"disabled": True, "text": "저장"} and editing["undo"] and editing["redo"]  # 바뀐 것이 없으면 잠김
    assert (finger["objs"], finger["prevented"], finger["save"]["disabled"]) == ([], False, True)  # 손가락은 안 써진다
    assert len(pen["objs"]) == 1 and pen["prevented"] and pen["save"]["disabled"] is False and pen["undo"] is False
    assert pen["objs"][0]["stroke"] == "#e11d1d" and pen["objs"][0]["points"] == "100,100 160,100 220,100 300,100"
    assert len(mouse["objs"]) == 2  # 마우스(PC)도 쓴다
    assert (len(undo1["objs"]), len(undo2["objs"]), undo2["save"]["disabled"], undo2["redo"]) == (1, 0, True, False)  # 처음으로 = 잠김
    assert (len(redo["objs"]), redo["save"]["disabled"]) == (1, False)
    put = saved["writes"][0]
    body = _payload(put)
    assert (put["url"], put["method"], put["timeoutMs"]) == ("/api/production/drawing-notes", "PUT", 30000)
    assert [e["k"] for e in put["form"]] == ["payload", "ink"] and put["form"][1]["name"] == "ink.png" and put["form"][1]["v"]["fake"] == "png"
    assert put["form"][1]["v"]["width"] == 1400 and put["form"][1]["v"]["height"] == 1000  # 긴 변 = 원본 긴 변
    assert (body["seen_version"], body["base_w"], body["base_h"], body["drawing_key"].endswith("d1.png")) == (0, 1478, 1056, True)
    assert body["objects"] == [{"type": "pen", "points": [100, 100, 160, 100, 220, 100, 300, 100], "stroke": "#e11d1d", "strokeWidth": 5}]
    assert (saved["editing"], saved["vbot_hidden"], saved["view_hidden"], saved["ink"]) == (False, False, False, False)
    assert saved["toast"] == "저장했어요. 주문 첨부 '생산'에도 들어갔어요."
    assert saved["card"]["v"] == "1" and saved["card"]["tag"] and saved["card"]["aria"].endswith("· 생산 기록")
    assert saved["src"] == "/api/files/view/orders/1/production/n1.png" and saved["show"] == "note" and saved["meta"] == "김재단 11/28 10:00"
    assert saved["write"]["text"] == "기록 고치기" and [s["dot"] for s in saved["sheets"]] == [True, True, False]


def test_지우개는_댄_것_하나만_도구_고르면_색_굵기_자리_비움(client, cohort, monkeypatch, tmp_path) -> None:
    page = _page(client, monkeypatch, tmp_path)
    out = _run(page, [{"do": "open", "no": 2}, {"do": "write"}, {"do": "pointer", "path": LINE_A}, {"do": "pointer", "path": LINE_B},
                      {"do": "tool", "v": "erase"}, {"do": "pointer", "path": [[220, 500]]}, {"do": "btn", "v": "undo"},
                      {"do": "tool", "v": "marker"}, {"do": "pointer", "path": [[400, 300], [500, 300]]}, {"do": "tool", "v": "arrow"},
                      {"do": "color", "v": "#1c62d6"}, {"do": "width", "v": "9"}, {"do": "pointer", "path": [[600, 600], [700, 700]]},
                      {"do": "tool", "v": "text"}, {"do": "text", "x": 800, "y": 200, "value": "선반 간격 320"}, {"do": "btn", "v": "save"}])
    erase_on, erased, undone = out[4], out[5], out[6]
    assert (erase_on["tool"], erase_on["colors_off"], erase_on["widths_off"]) == ("erase", True, True)
    assert erase_on["toast"] == "선이나 글에 대면 그 하나가 통째로 지워져요"
    assert [o["points"] for o in erased["objs"]] == ["100,100 160,100 220,100 300,100"]  # 댄 선(B) 하나만 통째로
    assert len(undone["objs"]) == 2
    assert (out[7]["colors_off"], out[7]["widths_off"], out[9]["colors_off"]) == (True, True, False)  # 형광펜 = 색 · 굵기 고정
    assert out[14]["box_open"]
    objs = _payload(out[-1]["writes"][0])["objects"]
    assert objs[2] == {"type": "pen", "points": [400, 300, 500, 300], "stroke": "#ffd400", "strokeWidth": 24, "opacity": 0.4}
    assert objs[3] == {"type": "arrow", "points": [600, 600, 700, 700], "stroke": "#1c62d6", "strokeWidth": 9}
    assert objs[4] == {"type": "text", "x": 800, "y": 200, "text": "선반 간격 320", "fill": "#1c62d6", "fontSize": 38}


def test_다_지우고_저장은_DELETE_먼저_보기와_바꾸기(client, cohort, monkeypatch, tmp_path) -> None:
    page = _page(client, monkeypatch, tmp_path, first=True)
    old = [{"type": "pen", "points": [100, 100, 300, 100], "stroke": "#000000", "strokeWidth": 3},
           {"type": "text", "x": 500, "y": 500, "text": "서랍 레일 450", "fill": "#e11d1d", "fontSize": 38}]
    out = _run(page, [{"do": "open", "no": 1}, {"do": "show", "v": "orig"}, {"do": "show", "v": "note"}, {"do": "write"},
                      {"do": "tool", "v": "erase"}, {"do": "pointer", "path": [[300, 100]]}, {"do": "pointer", "path": [[500, 500]]},
                      {"do": "btn", "v": "save"}],
               get_note={"objects": old, "base_w": 1478, "base_h": 1056, "version": 3, "by": "김재단", "at": "11/27 16:40"},
               writes=[{"ok": True, "kind": "ok", "status": 200, "data": {"success": True, "data": {"note": None}, "error": None}, "message": ""}])
    opened, orig, note, editing = out[0], out[1], out[2], out[3]
    # 먼저 보기 켠 사람 = 생산 기록이 먼저(2번 답) · 누구나 눌러 바꿈(6번 답) — 그림 주소만 바뀐다
    assert (opened["src"], opened["show"], opened["meta"]) == (NOTE["view_url"], "note", "김재단 11/27 16:40")
    assert opened["sheets"] == [{"text": "도면 1", "pressed": "true", "label": "도면 1 · 생산 기록", "dot": True},
                                {"text": "도면 2", "pressed": "false", "label": "도면 2", "dot": False},
                                {"text": "도면 3", "pressed": "false", "label": "도면 3", "dot": False}]
    assert (orig["src"], orig["show"]) == (opened["view_url"], "orig") and note["src"] == NOTE["view_url"]
    assert editing["src"] == opened["view_url"] and len(editing["objs"]) == 2  # 쓰기는 원본 위 · 받은 기록을 얹는다
    cleared = out[6]
    assert cleared["objs"] == [] and cleared["save"]["disabled"] is False  # 다 지움도 바뀐 것
    deleted = out[7]
    w = deleted["writes"][0]
    assert (w["method"], w["url"], w["form"]) == ("DELETE", "/api/production/drawing-notes", None)
    assert w["json"]["seen_version"] == 3 and w["json"]["drawing_key"].endswith("d0.png") and isinstance(w["json"]["order_id"], int)
    assert deleted["toast"] == "생산 기록을 지웠어요. 원본 도면만 남아요."
    assert deleted["card"] == {"v": None, "by": None, "at": None, "url": None, "tag": False, "aria": "가짜고객 도면 1/3 크게 보기"}
    assert (deleted["show"], deleted["meta"], deleted["write"]["text"], deleted["src"]) == (None, None, "기록 쓰기", opened["view_url"])


def test_받아_오기가_다시_그려도_쓰기_화면_유지_Esc_는_묻는_줄(client, cohort, monkeypatch, tmp_path) -> None:
    # 기록 있는 장 · 생산 기록 먼저 보기 — 보는 상태라면 합친 그림이 뜨는 장이라, 다시 그리면 쓰는 층 아래가 합친 그림으로 바뀐다(되돌리면 실패)
    page = _page(client, monkeypatch, tmp_path, first=True)
    out = _run(page, [{"do": "open", "no": 1}, {"do": "write"}, {"do": "pointer", "path": LINE_A}, {"do": "synced"}, {"do": "synced"},
                      {"do": "escape"}, {"do": "btn", "v": "keep"}, {"do": "synced"}, {"do": "btn", "v": "cancel"}, {"do": "btn", "v": "drop"}],
               get_note={"objects": [], "base_w": 1478, "base_h": 1056, "version": 3, "by": "김재단", "at": "11/27 16:40"})
    opened, drawn = out[0], out[2]
    assert opened["src"] == NOTE["view_url"] and drawn["src"] == opened["view_url"]  # 보기 = 합친 그림, 쓰기 = 원본 위
    for synced in (out[3], out[4], out[7]):  # 30초 받아 오기 뒤 카드 고침 사건 — 다시 그리지 않는다
        assert (synced["editing"], synced["edit_hidden"], synced["vbot_hidden"], synced["view_hidden"]) == (True, False, True, True)
        assert synced["objs"] == drawn["objs"] and synced["src"] == opened["view_url"] and synced["ink"] and synced["hidden"] is False
    asked = out[5]
    assert (asked["editing"], asked["ask_hidden"], asked["edit_hidden"], asked["hidden"]) == (True, False, True, False)  # Esc = [취소] — 창 없이 묻는 줄
    assert (out[6]["ask_hidden"], out[6]["edit_hidden"], len(out[6]["objs"])) == (True, False, 1)  # [계속 쓰기]
    assert out[8]["ask_hidden"] is False
    dropped = out[9]
    assert (dropped["editing"], dropped["view_hidden"], dropped["vbot_hidden"], dropped["ink"], dropped["writes"]) == (False, False, False, False, [])
    assert dropped["src"] == NOTE["view_url"] and dropped["card"]["v"] == "3"  # 버리면 보던 쪽(생산 기록) 그대로 · 카드 그대로


def test_409_NOTE_CHANGED_때_쓴_것_유지_저장_중_잠김(client, cohort, monkeypatch, tmp_path) -> None:
    page = _page(client, monkeypatch, tmp_path)
    server_text = "그사이 김재단이 기록을 고쳤어요. 닫고 다시 열어 주세요."
    refused = {"ok": False, "kind": "409", "status": 409, "data": {"success": False, "data": {"code": "NOTE_CHANGED"}, "error": server_text}, "message": server_text}
    bare = {"ok": False, "kind": "error", "status": 413, "data": {"success": False, "data": {"code": "NOTE_TOO_LARGE"}}, "message": ""}
    out = _run(page, [{"do": "open", "no": 2}, {"do": "write"}, {"do": "pointer", "path": LINE_A}, {"do": "btn", "v": "save"},
                      {"do": "pointer", "path": LINE_B}, {"do": "release"}, {"do": "btn", "v": "save"}, {"do": "btn", "v": "save"}],
               writes=[{"hold": True}, refused, refused, bare])
    busy = out[3]
    assert busy["save"] == {"disabled": True, "text": "저장 중…"} and busy["undo"] is True and busy["editing"]
    assert len(out[4]["objs"]) == 1  # 저장 중에는 안 써진다
    lost = out[5]
    assert (lost["editing"], lost["toast"], len(lost["objs"]), lost["save"]) == (True, server_text, 1, {"disabled": False, "text": "저장"})
    assert lost["card"]["v"] is None and lost["card"]["tag"] is False  # 카드는 그대로
    assert out[6]["toast"] == server_text and len(out[6]["objs"]) == 1  # 다시 눌러도 쓴 것은 그대로
    assert out[7]["toast"] == "기록이 너무 많아요. 조금 지우고 다시 저장해 주세요."  # 서버 글이 없으면 §6-5 글


def test_앞_층_거절_꼴에도_죽지_않고_코드가_없으면_SAVE_FAILED_글_CSRF_머리글(client, cohort, monkeypatch, tmp_path) -> None:
    """서버 일꾼(ⓑ)이 알린 실제 꼴 — 권한 문 403 data:null · 큰 몸 error 객체 · 스위치 꺼짐 404 HTML(fomsMutationFetch = malformed)."""
    page = _page(client, monkeypatch, tmp_path)
    gate = {"ok": False, "kind": "403", "status": 403, "data": {"success": False, "data": None, "error": "권한 문 글", "message": "권한 문 글", "code": "X"}, "message": "권한 문 글"}
    big = {"ok": False, "kind": "error", "status": 413, "data": {"success": False, "message": "큰 몸 글", "error": {"code": "REQUEST_BODY_TOO_LARGE"}}, "message": "큰 몸 글"}
    bare = {"ok": False, "kind": "error", "status": 413, "data": {"success": False, "error": {"code": "REQUEST_BODY_TOO_LARGE"}}, "message": "처리에 실패했습니다. (HTTP 413)"}
    html404 = {"ok": False, "kind": "malformed", "status": 404, "data": {}, "message": "서버 응답을 해석하지 못했습니다."}
    out = _run(page, [{"do": "open", "no": 2}, {"do": "write"}, {"do": "pointer", "path": LINE_A}]
               + [{"do": "btn", "v": "save"}] * 4, writes=[gate, big, bare, html404])
    texts = [o["toast"] for o in out[3:]]
    assert texts == ["권한 문 글", "큰 몸 글", "저장하지 못했어요. 잠시 뒤 다시 눌러 주세요.", "저장하지 못했어요. 잠시 뒤 다시 눌러 주세요."]
    for o in out[3:]:
        assert (o["editing"], len(o["objs"]), o["save"]["disabled"]) == (True, 1, False)  # 쓴 것은 그대로 — 다시 누를 수 있다
    for w in out[-1]["writes"]:
        assert w["method"] == "PUT" and w["headers"] == {"X-CSRFToken": "tok-1"}  # Content-Type 은 브라우저가(multipart 경계)


def test_합친_그림이_지워진_기록은_원본만_기록_고치기는_그대로(client, cohort, monkeypatch, tmp_path) -> None:
    page = _page(client, monkeypatch, tmp_path, first=True, note=dict(NOTE, view_url=""))
    out = _run(page, [{"do": "open", "no": 1}])
    opened = out[0]
    assert opened["src"] == opened["view_url"] and opened["show"] is None  # [생산 기록 | 원본] 숨김 · 원본만
    assert opened["write"] == {"hidden": False, "text": "기록 고치기"} and opened["meta"] == "김재단 11/27 16:40"
    assert opened["sheets"][0]["dot"] is True and opened["card"]["tag"] is True
