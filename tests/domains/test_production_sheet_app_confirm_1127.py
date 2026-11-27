"""작업 시트 · 생산 첫 화면 생산 단추의 확인 창 = 앱 창(사장님 결정 2026-11-27 "앱 창으로 바꾸기").

작업 시트(``templates/production/sheet.html``)의 [제작 시작] · [제작 완료](시공일 둘이면 덧붙는 줄) · [완료 취소] · [보류 해제] ·
보류 중 다시 묻기 · 공장 단추와 생산 첫 화면 '남은 공정' 판의 [보류 해제]는 인터넷 기본 창(window.confirm) 대신 작업 시트 공정 칸과 같은
앱 창(``sheet_step_confirm.html`` + ``foms-production-sheet-parts.js`` confirm)으로 묻는다. 글과 흐름은 그대로 — 제목 = 묻는 글,
덧붙는 줄 = 본문, 단추 = [닫기] · [한 일 이름]. 같은 JS 를 쓰는 옆 시트 · 옛 칸반 · 출고, 창 조각이 없는 화면은 지금 기본 창 그대로.

되돌리면 실패: 작업 시트에 창 조각이 없음 · 앱 창 길에서 기본 창이 뜸 · [닫기] · Esc · 바깥에 POST · 두 번 눌러 POST 둘 ·
주소 · 몸통이 바뀜 · 옆 시트(창 조각이 있어도)가 앱 창으로 바뀜 · 핀이 화면마다 다름 · 창 제목 글자가 글자 크기를 안 따름 · 단추 48px 아래.
"""
from __future__ import annotations

import copy
import datetime
import html as html_lib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from foms.services.datetime_kst import get_today_kst
from models import Order
from tests.support.production_factory_seed import factory_user, mixed_order, set_factory_done
from tests.support.production_home_step_panel_seed import HOME, TABLET, add_order, get_html, login, pane_html, set_cookies
from tests.support.production_part_claim_seed import login as login_person

ROOT = Path(__file__).resolve().parents[2]
NODE_CHECK = ROOT / "tests/support/production_sheet_confirm_node_checks.js"
PIN = "20261127a"
SHEET_PARTS_PIN = "20261127d"  # 11-27 d: sheet-parts.js 만 한 번 더(도면 여러 장 주문 공정 칸 막힘 — test_production_per_sheet_only_1127)
PARTS_JS = "static/js/production/foms-production-sheet-parts.js"
SHEETS_JS = "static/js/foms/tablet-domain-sheets.js"
FACTORY_JS = "static/js/production/foms-production-sheet-factory.js"
ALL_STEPS = ("cut", "edge", "assemble", "inspect")
HOLD = "자재 기다림"


def _run(tmp_path, html: str, want: dict) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node 없음")
    page = tmp_path / "page.html"
    page.write_text(html, encoding="utf-8")
    proc = subprocess.run([node, str(NODE_CHECK), str(page), json.dumps(want, ensure_ascii=False)], capture_output=True,
                          text=True, encoding="utf-8", timeout=120)
    assert proc.returncode == 0 and proc.stdout.strip().endswith("OK"), proc.stdout + proc.stderr


def _md(day: datetime.date) -> str:
    return f"{day.month}/{day.day}"


def _patch(order: Order, *, stage: str | None = None, dates: str | None = None) -> None:
    db_session.expire_all()
    row = db_session.get(Order, order.id)
    sd = copy.deepcopy(row.structured_data)
    if stage:
        sd["workflow"]["stage"] = stage
        row.erp_stage_code = stage
        row.status = stage
    if dates:
        sd["schedule"]["construction"]["date"] = dates
    row.structured_data = sd
    flag_modified(row, "structured_data")
    db_session.commit()


def _sheet(client, oid: int) -> str:
    set_cookies(client, TABLET)
    return get_html(client, f"/erp/production/sheet/{oid}")


def _act(action: str, oid: int) -> str:
    return f'[data-tablet-sheet-action="{action}"][data-order-id="{oid}"]'


# --------------------------------------------------------------------------- #
# ① 작업 시트에 창 조각이 실리고, 각 단추가 앱 창을 거쳐 같은 주소 · 같은 몸통으로 POST(② ③ ⑤)
# --------------------------------------------------------------------------- #
def test_작업_시트_생산_단추는_앱_창으로_묻고_같은_주소로_한_번_저장한다_Node(client, tmp_path) -> None:
    login(client, lead=True)  # 반장 — 작업 시트 쓰기 단추가 있는 사람
    wait = add_order("가람대기집", 1, run=False)
    first, second = get_today_kst() + datetime.timedelta(days=1), get_today_kst() + datetime.timedelta(days=9)
    making = add_order("가람제작집", 1, done=ALL_STEPS, hold=HOLD)
    _patch(making, dates=f"{first.isoformat()}, {second.isoformat()}")
    done = add_order("가람완료집", 1, done=ALL_STEPS)
    _patch(done, stage="CONSTRUCTION")
    split = f"시공일이 {_md(first)} · {_md(second)} 두 번이에요. 제품이 모두 제작됐나요?"

    pages = {oid: _sheet(client, oid) for oid in (wait.id, making.id, done.id)}
    for page in pages.values():  # 창 조각 하나 · 같은 핀(그려서 확인)
        assert page.count("data-foms-sheet-confirm hidden") == 1
        assert f"foms-production-sheet-parts.js?v={SHEET_PARTS_PIN}" in page and f"tablet-domain-sheets.js?v={PIN}" in page
        assert '<section class="foms-prod-page" data-foms-prod-sheet-page' in page
    assert f'data-production-split-note="{split}"' in pages[making.id]
    assert 'data-hold-active="1"' in pages[making.id] and f'data-hold-reason="{HOLD}"' in pages[making.id]

    base = {"scripts": [PARTS_JS, SHEETS_JS], "cohort": False}
    _run(tmp_path, pages[wait.id], {**base, "app": [
        {"sel": _act("production-start", wait.id), "title": "제작을 시작할까요?", "body": "", "yes": "제작 시작",
         "url": f"/api/orders/{wait.id}/production/start", "post": {}},
    ]})
    _run(tmp_path, pages[making.id], {**base, "app": [
        # 보류 중 주문 — 첫 응답 409 HOLD_ACTIVE 면 같은 창에 다시 묻고 release_hold 를 붙여 한 번 더
        {"sel": _act("production-complete", making.id), "title": "제작을 완료할까요?", "body": split, "yes": "제작 완료",
         "url": f"/api/orders/{making.id}/production/complete", "post": {}, "hold": HOLD},
        {"sel": _act("production-hold", making.id), "title": "보류를 해제할까요?", "body": f"(사유: {HOLD})", "yes": "보류 해제",
         "url": f"/api/orders/{making.id}/production/hold", "post": {"active": False, "reason": ""}},
    ]})
    _run(tmp_path, pages[done.id], {**base, "app": [
        {"sel": _act("production-uncomplete", done.id), "title": "완료를 취소하고 제작중으로 되돌릴까요?", "body": "", "yes": "완료 취소",
         "url": f"/api/orders/{done.id}/production/uncomplete", "post": {}},
    ]})


def test_작업_시트_공장_단추도_앱_창으로_묻는다_Node(client, tmp_path) -> None:
    seed = mixed_order(3, f2=(2,))
    set_factory_done(seed.id, 2, [seed.keys[2]])
    login_person(client, factory_user("정관리", role="ADMIN", team="CS"))
    page = _sheet(client, seed.id)
    assert page.count("data-foms-sheet-confirm hidden") == 1 and f"foms-production-sheet-factory.js?v={PIN}" in page
    tag = re.search(r'<button [^>]*data-foms-sheet-factory="2" data-done="0"[^>]*>(.*?)</button>', page)
    label = html_lib.unescape(re.sub(r"<[^>]+>", "", tag.group(1))).strip()
    assert label.endswith("완료 취소"), label
    _run(tmp_path, page, {"scripts": [PARTS_JS, FACTORY_JS], "cohort": False, "app": [
        {"sel": '[data-foms-sheet-factory="2"]', "title": label + "할까요?", "body": "", "yes": label, "keeps_lock": True,
         "url": f"/api/orders/{seed.id}/production/factory-done", "post": {"factory": 2, "done": False}},
    ]})


def test_남은_공정_판_보류_해제도_앱_창_공정을_안_체크하는_계정은_기본_창_Node(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")  # '내 공정' 판 = 생산 첫 화면 코호트(test_production_my_steps_confirm 과 같다)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")
    held = add_order("가람보류집", 1, hold=HOLD)
    set_cookies(client, TABLET)
    login(client)  # 반장 — '내 공정' 판에 [끝] 확인 창 조각이 이미 있다
    page = get_html(client, HOME + "?tab=steps")
    pane = pane_html(page, held.id)
    assert 'data-tablet-sheet-action="production-hold"' in pane and 'data-hold-active="1"' in pane
    assert page.count("data-foms-sheet-confirm hidden") == 1 and f"tablet-domain-sheets.js?v={PIN}" in page
    _run(tmp_path, page, {"scripts": [PARTS_JS, SHEETS_JS], "cohort": False, "app": [
        {"sel": _act("production-hold", held.id), "title": "보류를 해제할까요?", "body": f"(사유: {HOLD})", "yes": "보류 해제",
         "url": f"/api/orders/{held.id}/production/hold", "post": {"active": False, "reason": ""}},
    ]})
    # 공정을 체크하지 않는 생산팀 계정 — 판의 [보류]는 있지만 창 조각이 없는 화면이라 지금 기본 창(④)
    login(client, "가람보기", lead=False)
    page = get_html(client, HOME + "?tab=steps")
    if 'data-tablet-sheet-action="production-hold"' not in page:
        pytest.skip("이 계정에는 판 [보류]가 없다")
    assert "data-foms-sheet-confirm" not in page
    _run(tmp_path, page, {"scripts": [SHEETS_JS], "cohort": False, "plain": [
        {"sel": _act("production-hold", held.id), "plain": f"보류를 해제할까요? (사유: {HOLD})",
         "url": f"/api/orders/{held.id}/production/hold", "post": {"active": False, "reason": ""}},
    ]})


# --------------------------------------------------------------------------- #
# ④ 옆 시트(옛 칸반이 여는 것)는 창 조각이 있어도 지금 기본 창 그대로
# --------------------------------------------------------------------------- #
def test_옆_시트는_창_조각이_있어도_기본_창_그대로_Node(client, tmp_path) -> None:
    login(client, lead=True)
    first, second = get_today_kst() + datetime.timedelta(days=1), get_today_kst() + datetime.timedelta(days=9)
    making = add_order("가람옆집", 1, done=ALL_STEPS, hold=HOLD)
    _patch(making, dates=f"{first.isoformat()}, {second.isoformat()}")
    split = f"시공일이 {_md(first)} · {_md(second)} 두 번이에요. 제품이 모두 제작됐나요?"
    set_cookies(client, TABLET)
    frag = get_html(client, f"/erp/production/tablet-sheet/{making.id}")
    assert frag.count("data-foms-sheet-confirm hidden") == 1  # 공정 칸 손 체크 창 — 생산 단추는 이 창을 쓰지 않는다
    assert '<section class="foms-prod-page"' not in frag and "data-foms-prod-home" not in frag
    _run(tmp_path, frag, {"scripts": [PARTS_JS, SHEETS_JS], "cohort": True, "plain": [
        {"sel": _act("production-complete", making.id), "plain": "제작을 완료할까요?\n\n" + split,
         "url": f"/api/orders/{making.id}/production/complete", "post": {}},
        {"sel": _act("production-hold", making.id), "plain": f"보류를 해제할까요? (사유: {HOLD})",
         "url": f"/api/orders/{making.id}/production/hold", "post": {"active": False, "reason": ""}},
    ]})


def test_출고_옛_칸반_화면에는_앱_창_조각도_생산_묻기_단추도_없다() -> None:
    """출고 화면이 실는 같은 JS 는 [저장](묻지 않음)만 쓴다 — 앱 창으로 바뀔 단추가 없다. 옛 칸반 몸통은 창 조각을 싣지 않는다(옆 시트 조각만)."""
    asks = re.compile(r'data-tablet-sheet-action="production-(start|complete|uncomplete|hold)"')
    for rel in Path(ROOT / "templates/shipment").rglob("*.html"):
        text = rel.read_text(encoding="utf-8")
        assert not asks.search(text) and "data-foms-sheet-confirm" not in text and "sheet_step_confirm" not in text, rel
    kanban = (ROOT / "templates/production/partials/tablet_kanban_body.html").read_text(encoding="utf-8")
    assert "sheet_step_confirm" not in kanban and not asks.search(kanban)


# --------------------------------------------------------------------------- #
# 원문 계약 — 고른 범위 · 핀 · 창 글자 크기 · 단추 높이
# --------------------------------------------------------------------------- #
def test_앱_창_범위는_작업_시트와_생산_첫_화면뿐이고_기본_창_글은_그대로() -> None:
    js = (ROOT / SHEETS_JS).read_text(encoding="utf-8")
    assert 'var APP_CONFIRM_SCOPE = "section.foms-prod-page, [data-foms-prod-home]";' in js
    assert js.count("window.confirm(") == 1 and "if (window.confirm(q.plain)) go();" in js  # 기본 창은 한 곳(창 조각 · 범위 밖)
    assert 'plain: holdConfirmText(hold), again: true' in js and 'yes: "보류 해제하고 진행"' in js
    assert "if ((btn.disabled && !q.again) || !box.hidden) return;" in js and "Promise.resolve(go()).then(unlock, unlock);" in js
    assert '{ title: "제작을 시작할까요?", yes: "제작 시작", plain: "제작을 시작할까요?" }' in js
    assert 'ask(btn, { title: text, yes: "완료 취소", plain: text }' in js
    assert 'ask(btn, { title: "보류를 해제할까요?", note: why, yes: "보류 해제", plain: releaseMsg }' in js
    parts = (ROOT / PARTS_JS).read_text(encoding="utf-8")
    assert "doneText: doneText, confirm: open };" in parts and "text.hidden = !o.body;" in parts
    assert "if (no) { no.textContent = o.no || '취소'; }" in parts  # 공정 칸 손 체크 창은 [취소] 그대로
    factory = (ROOT / FACTORY_JS).read_text(encoding="utf-8")
    assert "sp.confirm({ title: question, yes: label, no: '닫기', opener: btn, go: save });" in factory
    assert factory.count("window.confirm(") == 1 and "if (window.confirm(question)) { save(); }" in factory
    for src in (parts, factory):
        assert len(src.splitlines()) <= 300


def test_핀은_싣는_곳마다_같다() -> None:
    read = lambda rel: (ROOT / rel).read_text(encoding="utf-8")  # noqa: E731
    for rel in ("templates/production/partials/home_body.html", "templates/production/partials/tablet_kanban_body.html",
                "templates/production/sheet.html"):
        assert f"tablet-domain-sheets.js') }}}}?v={PIN}" in read(rel), rel
    assert f"'/static/js/foms/tablet-domain-sheets.js?v={PIN}'" in read("static/js/shipment/shipment-entry.js")
    assert f"shipment-entry.js') }}}}?v={PIN}" in read("templates/shipment/partials/dashboard_scripts.html")
    assert read("templates/production/partials/home_scripts.html").count(f"foms-production-sheet-parts.js') }}}}?v={SHEET_PARTS_PIN}") == 2
    for rel in ("templates/production/sheet.html", "templates/production/partials/tablet_kanban_body.html"):
        assert f"foms-production-sheet-parts.js') }}}}?v={SHEET_PARTS_PIN}" in read(rel), rel
        assert f"css/contexts/production/sheet.css') }}}}?v=20261127m" in read(rel), rel  # 11-27 도면 밀어 넘기기(touch-action)로 한 번 더 올림
    assert f"foms-production-sheet-factory.js') }}}}?v={PIN}" in read("templates/production/sheet.html")
    # home.css 는 같은 날 날짜 줄 이름 한 줄 고침과 겹쳐 핀을 한 번 더 올렸다(합칠 때마다 올림)
    assert "css/contexts/production/home.css') }}?v=20261127g" in read("templates/production/partials/home_styles.html")


def test_창_제목은_글자_크기를_따르고_단추는_48px_이상() -> None:
    sheet = (ROOT / "static/css/contexts/production/sheet.css").read_text(encoding="utf-8")
    home = (ROOT / "static/css/contexts/production/home.css").read_text(encoding="utf-8")
    title = "font-size: calc(20px * var(--foms-fs, 1)); line-height: 1.4; word-break: keep-all;"
    assert f".fpp-confirm .foms-reason-sheet__title {{ {title} }}" in sheet
    assert f".foms-prod-home .fpp-confirm .foms-reason-sheet__title {{ {title} }}" in home
    btn = "min-height: 48px; font-size: calc(17px * var(--foms-fs, 1));"
    assert f".fpp-confirm .foms-reason-sheet__actions > .foms-btn {{ {btn} }}" in sheet
    assert f".foms-prod-home .fpp-confirm .foms-reason-sheet__actions > .foms-btn {{ {btn} }}" in home
    tablet = "min-height: calc(48px / var(--foms-ui-zoom, 1));"
    assert f".fpp-confirm .foms-reason-sheet__actions > .foms-btn {{ {tablet} }}" in sheet
    assert f".foms-prod-home .fpp-confirm .foms-reason-sheet__actions > .foms-btn {{ {tablet} }}" in home
    assert "calc(44px / var(--foms-ui-zoom, 1))" not in sheet.split("/* 반장 손 체크 확인 창", 1)[1].split("/*", 1)[0]
