"""파트 맡기 고침 P1 화면(설계서 2026-11-23 §8 · 승인 때 고친 것 1~3) — 그려진 HTML · JS 배선 구조.

* 지금 글은 그대로(승인 때 고친 것 1): [내가 엣지] · "박재단 맡음" · "작업 필요 · 김재단" · [되돌리기] · "안 본 도면" · 거르개 글.
  새 칸에만 새 글: [맡기 취소] · "내 담당" 꼬리 · "미정" · "재단 3/5" · "n장 미완료" · "바뀐 기록 보기" · 아침 칩.
* 막힌 칸 = button aria-disabled + 까닭(서버 거절 글) — 누를 수 있고(초점) 말풍선이 뜬다. 남이 맡은 칸 = 누르면 [담당 바꾸기] 창.
* 작업 시트: 카드 쓴 파트 칸 옆 글 · 막힘 글 자리 · [바뀐 기록 보기] · 회색 [제작 완료] 까닭 · 반장 손 체크 확인 창.
대조군: 읽기 전용 · 카드를 안 쓴 주문은 지금 꼴(새 단추 · 새 글 없음).
"""
from __future__ import annotations

import datetime
import json
import re
import shutil
import subprocess
from html import unescape
from itertools import count
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.datetime_kst import get_today_kst, now_utc_naive
from models import Order, ProductionPartMark, ProductionRun, User

ROOT = Path(__file__).resolve().parents[2]
HOME = "/erp/production/home"
JS = ROOT / "static/js/production"
NEW_JS = ("foms-production-parts-claim.js", "foms-production-parts-modal.js", "foms-production-sheet-parts.js")
TOUCHED_JS = NEW_JS + ("foms-production-parts.js", "foms-production-parts-viewer.js", "foms-production-parts-sync.js",
                       "foms-production-sheet-page.js", "foms-production-home-steps.js")
_seq = count(1)


@pytest.fixture
def cohort(monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")


def _user(name: str, part: str | None = None, role: str = "STAFF", team: str = "PRODUCTION") -> User:
    user = User(username=f"sfsc_{next(_seq)}", password=generate_password_hash("x"), role=role, team=team, name=name,
                is_active=True, production_part=part)
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user: User, ptr: str = "coarse") -> None:
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = user.id, user.username, user.role
    client.set_cookie("foms_ptr", ptr, domain="localhost")
    client.set_cookie("foms_vw", "wide", domain="localhost")
    client.set_cookie("foms_scr", "1280", domain="localhost")


def _order(name: str, n: int, *, steps=None, hold=False, run=True) -> Order:
    when = get_today_kst().isoformat()
    sd = {"workflow": {"stage": "PRODUCTION"}, "parties": {"customer": {"name": name, "phone": "010-0000-0000"}},
          "schedule": {"construction": {"date": when}}, "items": [{"product_name": "붙박이장"}],
          "drawing_current_files": [{"key": f"{name}/d{j}.png", "filename": f"d{j}.png"} for j in range(n)],
          "production": {"steps": steps or []}}
    if hold:
        sd["production"]["hold"] = {"active": True, "reason": "자재 기다림"}
    order = Order(received_date=when, customer_name=name, phone="010-0000-0000", address="가짜시", product="붙박이장",
                  status="PRODUCTION", is_erp_order=True, erp_stage_code="PRODUCTION", erp_construction_date=when, structured_data=sd)
    db_session.add(order)
    db_session.flush()
    if run:
        db_session.add(ProductionRun(order_id=order.id, status="IN_PROGRESS", steps=[], defects=[], is_current=True))
    db_session.commit()
    return order


def _mark(order: Order, j: int, part: str, state: str, who: User, *, picked_at=None, handed=None) -> None:
    done = state in ("DONE", "BASIC")
    db_session.add(ProductionPartMark(
        order_id=order.id, drawing_key=f"{order.customer_name}/d{j}.png", part=part, state=state,
        picked_by_user_id=None if state == "BASIC" else who.id, picked_by_name=None if state == "BASIC" else who.name,
        picked_at=picked_at or now_utc_naive(), done_by_user_id=who.id if done else None, done_by_name=who.name if done else None,
        done_at=now_utc_naive() if done else None, handed_from_name=handed, handed_at=now_utc_naive() if handed else None,
        updated_by_user_id=who.id, updated_at=now_utc_naive()))
    db_session.commit()


def _get(client, url: str) -> str:
    resp = client.get(url)
    assert resp.status_code == 200, (url, resp.status_code)
    return resp.get_data(as_text=True)


def _card(html: str, name: str, j: int) -> str:
    start = html.index(f'data-key="{name}/d{j}.png"')
    return html[html.rindex("<article", 0, start):html.index("</article>", start)]


# --------------------------------------------------------------------------- #
# 파트 계정 카드
# --------------------------------------------------------------------------- #
def test_내_담당은_한_층_맡기_취소_남의_담당은_누름_칸_막힘은_까닭(client, cohort) -> None:
    me, park = _user("김민준", "edge"), _user("박엣지", "edge")
    order = _order("한빛", 4)
    held = _order("보류집", 1, hold=True)
    _mark(order, 0, "edge", "NEED", me, picked_at=now_utc_naive() - datetime.timedelta(days=1))
    _mark(order, 1, "edge", "NEED", park)
    _mark(order, 2, "edge", "DONE", me)
    me_id, held_id, order_id = me.id, held.id, order.id
    _login(client, me)
    html = _get(client, HOME)
    mine = _card(html, "한빛", 0)
    assert '<div class="pp-two is-mine"><button type="button" class="foms-prod-home__btn pp-release" data-pp-act="release">맡기 취소</button>' in mine
    assert '<button type="button" class="fph-qr__done pp-act pp-fin is-pair" data-pp-act="done">엣지 완료</button></div>' in mine
    assert '<span class="pp-tag" data-pp-tag aria-label="내 담당 · 어제부터">내 담당 · <span class="is-old">어제부터</span></span>' in mine
    assert 'class="fph-dr__by pp-by has-tag"' in mine and f'data-picked-id="{me_id}"' in mine
    other = _card(html, "한빛", 1)
    assert 'class="fph-wi pp-act pp-st-taken pp-held" data-pp-act="held"' in other and "<b>박엣지 맡음</b>" in other  # 지금 글 그대로
    assert "pp-tag" not in other
    assert "엣지 끝 · 김민준" in _card(html, "한빛", 2) and "되돌리기" in _card(html, "한빛", 2)  # 지금 글 그대로
    assert "내가 엣지" in _card(html, "한빛", 3)  # 지금 글 그대로
    hold = _card(html, "보류집", 0)
    assert '<button type="button" class="fph-wi pp-act pp-st-hold" aria-disabled="true"' in hold and ">보류 · 자재 기다림</button>" in hold
    assert 'data-pp-why="보류된 주문이라 지금은 못 눌러요. 보류가 풀리면 다시 돼요."' in hold and 'data-pp-act="take"' not in hold
    assert f'aria-describedby="pp-why-{held_id}-1"' in hold and f'<p class="pp-why" id="pp-why-{held_id}-1" role="status" hidden></p>' in hold
    # 이름 줄 = 작업 시트 링크 · 시공 줄 감싸개 · 판 순서(미정 → 담당 → 완료)
    assert f'<a class="pp-ln pp-sheetlink" href="/erp/production/sheet/{order_id}"' in mine and '<div class="pp-duerow">' in mine
    keys = re.findall(r'data-key="한빛/d(\d)\.png"', html)
    assert keys == ["3", "0", "1", "2"]
    # 아침 칩(밤 넘긴 내 담당 1장) · 창 몸 글 · 고르기 · 거절 글 자리
    assert 'data-pp-mchip aria-expanded="false" aria-controls="pp-mpop">어제부터 내 담당 1장' in html
    assert '<p class="pp-mbody" data-pp-modal-body hidden></p>' in html and "data-pp-modal-choices" in html
    assert 'role="alert" aria-live="assertive"' in html
    # 30초 받아 오기 "어제부터" 판정 = 서버 KST 오늘
    cfg = json.loads(unescape(re.search(r'data-foms-parts-config="([^"]+)"', html).group(1)))
    assert cfg["today"] == get_today_kst().isoformat()


def test_손_체크한_파트_카드는_완료_칸이고_단추가_없다(client, cohort) -> None:
    me = _user("김재단", "cut")
    _order("손집", 2, steps=[{"key": "cut", "label": "재단", "done": True, "by_name": "박반장"}])
    _login(client, me)
    html = _get(client, HOME)
    card = _card(html, "손집", 0)
    assert 'data-state="hand"' in card and 'class="pp-card is-done"' in card
    assert ('<button type="button" class="fph-wi pp-act pp-st-done pp-hand" aria-disabled="true"' in card
            and "<span>재단 완료 · 박반장</span><small>작업 시트</small></button>" in card)
    assert 'data-pp-act="' not in card and "안 본 도면 없어요" in html  # 미정 수 · 일괄 기본에서 빠짐


def test_보류_주문은_완료_기본_카드에도_막힘을_싣고_되돌린_뒤_그림_규칙이_서버와_같다(client, cohort) -> None:
    """완료 · 기본 카드에도 data-pp-block — 되돌리면(완료 → 담당 · 기본 → 안 봄) JS 가 그 값으로 그린다. 서버는 같은 상태를
    [맡기 취소][보류 칸] · 보류 칸으로 그린다. JS 규칙(claim.special 은 상태와 상관없이 카드의 data-pp-block 을 읽음)은 아래 정적 단언."""
    me = _user("김재단", "cut")
    held = _order("보류집", 4, hold=True)
    _mark(held, 0, "cut", "DONE", me)
    _mark(held, 1, "cut", "BASIC", me)
    _mark(held, 2, "cut", "NEED", me)  # = 완료 카드를 되돌린 뒤 상태(내 담당)
    _login(client, me)
    html = _get(client, HOME)
    for j in range(4):  # 완료 · 기본 · 담당 · 안 본 장 모두 같은 막힘 값
        card = _card(html, "보류집", j)
        assert 'data-pp-block="hold" data-pp-block-text="보류 · 자재 기다림"' in card, j
    done, basic = _card(html, "보류집", 0), _card(html, "보류집", 1)
    assert "재단 끝 · 김재단" in done and 'data-pp-act="undo"' in done  # 완료 취소는 보류에도 된다(§4-6)
    assert 'data-pp-act="undo"' in basic
    # 되돌린 뒤 상태의 서버 그림 = 내 담당 [맡기 취소][보류 칸] · 안 본 장 = 보류 칸(단추 없음)
    mine = _card(html, "보류집", 2)
    assert '<div class="pp-two is-mine"><button type="button" class="foms-prod-home__btn pp-release" data-pp-act="release">맡기 취소</button><button type="button" class="fph-wi pp-act pp-st-hold"' in mine
    fresh = _card(html, "보류집", 3)
    assert 'class="fph-wi pp-act pp-st-hold"' in fresh and 'data-pp-act=' not in fresh
    claim = (JS / "foms-production-parts-claim.js").read_text(encoding="utf-8")
    block = claim[claim.index("function block(card)"):claim.index("function whyId(")]
    assert block.index("attr(card, 'data-pp-block')") < block.index("preLeft(card)")  # 주문 막힘이 먼저(상태 무관)
    special = claim[claim.index("function special("):claim.index("function renderTag(")]
    assert "var b = block(card);" in special and "if (st === 'none') { if (b) { box.appendChild(blockChip(card, b)); } return !!b; }" in special
    assert "two.appendChild(b ? blockChip(card, b) : actBtn(" in special


def test_남은_N장_모두_기본은_막힌_안_본_장을_빼고_창_목록과_같다(client, cohort) -> None:
    me = _user("김재단", "cut")
    _order("보통집", 2)
    _order("보류한집", 3, hold=True)
    _login(client, me)
    html = _get(client, HOME)
    assert '<span class="pp-unseen" data-pp-unseen-text="5">안 본 도면 <b>5</b>장</span>' in html  # 안 본 도면 글은 모두(지금 글)
    assert '<span>남은 <span data-pp-count="unseen">2</span>장 모두 기본</span>' in html  # 단추 = 막히지 않은 2장
    bulk = re.search(r'<button type="button" class="foms-prod-home__btn" data-pp-act="bulk"[^>]*>', html).group(0)
    assert "hidden" not in bulk
    parts = (JS / "foms-production-parts.js").read_text(encoding="utf-8")
    assert "function bulkable(card) { return attr(card, 'data-state') === 'none' && !attr(card, 'data-pp-block'); }" in parts
    assert "unseen: bulkable(card) ? 1 : 0, look: st === 'none' ? 1 : 0" in parts  # 단추 숫자 · 글 숫자 따로
    assert "openModal('bulk', board.cardsOf(pane).filter(bulkable), btn);" in parts  # 창 목록 = 단추 숫자 기준


def test_모두_막힌_날은_모두_기본_단추가_숨는다(client, cohort) -> None:
    me = _user("김재단", "cut")
    _order("보류만집", 2, hold=True)
    _login(client, me)
    html = _get(client, HOME)
    bulk = re.search(r'<button type="button" class="foms-prod-home__btn" data-pp-act="bulk"[^>]*>', html).group(0)
    assert bulk.endswith(" hidden>") and '<span data-pp-count="unseen">0</span>' in html
    assert "안 본 도면 <b>2</b>장" in html


def test_관리자_남의_담당은_고르기_창_단추_지금_완료_단추_그대로_읽기_전용은_지금_꼴(client, cohort) -> None:
    kim, admin, cs = _user("김재단", "cut"), _user("관리", role="ADMIN", team="CS"), _user("상담", team="CS")
    order = _order("한빛", 1)
    _mark(order, 0, "cut", "NEED", kim)
    cs_user = (cs.id, cs.username, cs.role)
    _login(client, admin)
    card = _card(_get(client, HOME + "?tab=parts&part=cut"), "한빛", 0)
    assert 'class="fph-wi pp-act pp-st-need pp-not-need pp-held" data-pp-act="held"' in card and "<b>작업 필요 · 김재단</b>" in card
    assert '<button type="button" class="fph-qr__done pp-act pp-fin pp-only-need" data-pp-act="done">재단 완료</button>' in card
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = cs_user
    card = _card(_get(client, HOME + "?tab=parts&part=cut"), "한빛", 0)
    assert '<span class="fph-wi pp-act pp-st-need">작업 필요 · 김재단</span>' in card and "<button" not in card.split("pp-actbox")[1]


# --------------------------------------------------------------------------- #
# 날짜 줄 · 작업 시트
# --------------------------------------------------------------------------- #
def test_날짜_줄_칸_아래_이름과_단계_칸_미완료(client, cohort) -> None:
    kim, park = _user("김재단", "cut"), _user("박재단", "cut")
    order = _order("부분집", 5)
    for j in range(3):
        _mark(order, j, "cut", "DONE", kim)
    _mark(order, 3, "cut", "NEED", park)
    _login(client, _user("반장"))
    html = _get(client, HOME)
    row = html.split(f'data-foms-home-dayrow="{order.id}"', 1)[1].split("</a>", 1)[0]
    assert '<span class="fph-dr__sg">재단 중<small class="is-miss">2장 미완료</small></span>' in row
    assert '<span class="fph-dr__steps has-hd" aria-label="공정">' in row
    assert '<i></i>재단 3/5<span class="visually-hidden">, 재단 3/5 · 2장 미완료 · 담당 박재단</span>' in row
    assert '<small class="fph-dr__hd" aria-hidden="true"><b>박재단</b></small>' in row
    assert row.count('<small class="fph-dr__hd is-none" aria-hidden="true"><b>미정</b></small>') == 3


def test_작업_시트_카드_진행_글_막힘_글_바뀐_기록_까닭_손_체크_창(client, cohort) -> None:
    kim = _user("김재단", "cut")
    order = _order("시트집", 5)
    for j in range(3):
        _mark(order, j, "cut", "DONE", kim)
    _mark(order, 3, "cut", "NEED", kim, handed="박재단")
    plain_id, order_id = _order("빈시트", 2).id, order.id
    _login(client, _user("반장"))
    html = _get(client, f"/erp/production/sheet/{order_id}")
    assert '<small class="fpp-note is-miss" data-foms-sheet-step-meta data-foms-sheet-cardnote>도면 3/5 · 2장 미완료 · 바뀜 1</small>' in html
    assert '<p class="fpp-stepmsg" data-foms-sheet-stepmsg role="status" hidden></p>' in html
    assert 'data-foms-sheet-loglink aria-expanded="false" aria-controls="foms-sheet-log">바뀐 기록 보기 ›</button>' in html
    assert 'data-foms-sheet-complete-why="아직 미완료가 있어요 — 재단 2장 · 엣지 5장 · 조립 5장 · 검수 5장"' in html
    parts = json.loads(unescape(re.search(r'data-foms-sheet-parts="([^"]+)"', html).group(1)))
    assert parts["sheets"] == 5 and parts["parts"]["cut"]["uses_cards"] and parts["parts"]["cut"]["left_n"] == 2
    assert html.count("data-foms-sheet-confirm ") + html.count("data-foms-sheet-confirm hidden") >= 1
    assert "foms-production-sheet-parts.js?v=" in html and html.index("sheet-parts.js") < html.index("sheet-page.js")
    # 대조군: 카드를 안 쓴 주문 — 칸 옆 글 · 기록 단추 · 까닭 글 없음(손 체크 확인 창 자료는 있다)
    other = _get(client, f"/erp/production/sheet/{plain_id}")
    assert "fpp-note" not in other and "data-foms-sheet-loglink" not in other and "data-foms-sheet-complete-why" not in other
    assert "data-foms-sheet-parts=" in other


# --------------------------------------------------------------------------- #
# JS 배선
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", TOUCHED_JS)
def test_JS_크기_문법_innerHTML_없음(name) -> None:
    path = JS / name
    src = path.read_text(encoding="utf-8")
    assert len(src.splitlines()) < 300, f"{name} — 새 JS 300줄 래칫"
    assert "innerHTML" not in src and "insertAdjacentHTML" not in src, f"{name} — 서버 글은 textContent 로만"
    assert "location.reload" not in src
    node = shutil.which("node")
    if node is None:
        pytest.skip("node 없음")
    result = subprocess.run([node, "--check", str(path)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def test_새_JS_는_화면마다_한_번_싣는_차례() -> None:
    claim = (JS / "foms-production-parts-claim.js").read_text(encoding="utf-8")
    modal = (JS / "foms-production-parts-modal.js").read_text(encoding="utf-8")
    sheet = (JS / "foms-production-sheet-parts.js").read_text(encoding="utf-8")
    assert "if (bound.claim === root || board.root !== root) { return; }" in claim
    assert "if (bound.modal === root) { return; }" in modal and "window.__FOMS_SHEET_PARTS_BOUND" in sheet
    for src in (claim, modal):
        assert not re.search(r"fetch\s*\(|fomsMutationFetch|XMLHttpRequest|sendBeacon", src), "쓰기는 parts.js send() 하나"
    assert not re.search(r"method: 'POST'|fomsMutationFetch", sheet), "시트 JS 의 POST 는 시트 공정 길 하나"
    tpl = (ROOT / "templates/production/partials/home_scripts.html").read_text(encoding="utf-8")
    order = [tpl.index(f"js/production/foms-production-parts{n}.js") for n in ("-viewer", "-claim", "-modal", "", "-sync")]
    assert order == sorted(order)
    # P2(2026-11-23 §4-12)가 modal(대신 한 줄)을 다시 올렸다 — parts · claim 은 P1 핀 그대로
    assert len(re.findall(r"foms-production-parts(?:-claim)?\.js'\) \}\}\?v=20261123v\" defer", tpl)) == 2
    assert len(re.findall(r"foms-production-parts-modal\.js'\) \}\}\?v=20261124a\" defer", tpl)) == 1


def test_창_초점_가두기_되돌리기_막힘_이어_뜨는_창_잠금() -> None:
    modal = (JS / "foms-production-parts-modal.js").read_text(encoding="utf-8")
    parts = (JS / "foms-production-parts.js").read_text(encoding="utf-8")
    sync = (JS / "foms-production-parts-sync.js").read_text(encoding="utf-8")
    assert "n.inert = true" in modal and "n.inert = false" in modal  # 창 밖 판은 inert
    assert "e.key !== 'Tab'" in modal and "last.focus()" in modal and "first.focus()" in modal  # 초점 가두기
    assert "cards.find(o.key[0], o.key[1])" in modal  # 연 단추가 다시 그려졌으면 같은 카드로 초점
    # 연 단추가 문서에 있어도 숨었으면 가지 않고, 다 숨었으면 늘 보이는 판 머리 거르개(고른 칸)로
    assert "n.offsetParent !== null && !n.closest('[hidden]')" in modal and "[data-pp-view].is-on" in modal
    assert "var next = pick.filter(shown)[0];" in modal
    # 목록 없는 창(제작 완료 물음)은 빈 줄을 안 남긴다
    assert "list.hidden = !items.length;" in modal
    css = (ROOT / "static/css/contexts/production/parts.css").read_text(encoding="utf-8")
    assert ".foms-prod-home .pp-modal .foms-prod-change-modal__list[hidden] { display: none; }" in css
    assert "var LOCK_MS = 800;" in modal and "run.setAttribute('aria-disabled', 'true');" in modal
    assert "pending.busy || pending.locked" in parts  # 두 번 누름 · 잠금 중 누름은 버린다
    assert "data.order_ready && p.action === 'done'" in parts and "'/production/complete'" in parts
    assert "M.lost(text, M.nowLine(data.mark));" in parts and "body.seen_by" in parts
    assert "claim.busy(card)" in parts and "window.FomsPartsClaim.recheck(card)" in sync  # 받아 오기가 열린 말풍선 · 창을 안 덮음
    claim = (JS / "foms-production-parts-claim.js").read_text(encoding="utf-8")
    assert "var WHY_MS = 6000;" in claim and "whyTimer = window.setTimeout(hideWhy, WHY_MS);" in claim  # 말풍선은 저절로 닫힌다


def test_작업_시트_JS_는_새_파일이_없으면_지금_그대로() -> None:
    page = (JS / "foms-production-sheet-page.js").read_text(encoding="utf-8")
    assert "var sp = window.FomsSheetParts;" in page and "if (sp && !btn.hasAttribute('data-foms-sheet-asked'))" in page
    assert "sp && sp.refused(page, result) ? '' : failText(result)" in page
    assert "var why = window.FomsSheetParts && window.FomsSheetParts.why(page);" in page and "completeBlockedText()" in page
    sheet = (JS / "foms-production-sheet-parts.js").read_text(encoding="utf-8")
    assert "' 완료로 체크할까요?'" in sheet and "'이 주문의 도면 ' + sheets + '장이 모두 ' + label + ' 완료로 처리돼요.'" in sheet
    assert "if (!done) { go(); return; }" in sheet  # 끌 때는 묻지 않는다
    assert "part.uses_cards" in sheet and "/api/production/part-history?order_id=" in sheet


def test_PC_완료_칸_날짜는_아주_넓은_화면에서만() -> None:
    """2026-11-23 지휘: 칸 아래 이름(has-hd)을 늘 보이게 한 뒤에도 아주 넓은 화면(줄 칸 1,500px 이상)의 "김재단 11/21" 글은 그대로."""
    css = (ROOT / "static/css/contexts/production/pc.css").read_text(encoding="utf-8")
    base, wide = css.split("@container fpc (min-width: 1500px) {", 1)
    assert ".fpc-s__m > .fpc-s__at { display: none;" in base
    block = wide[:wide.index("/* ── 작업 시트(PC)")]  # 아주 넓은 덩이(다음 절 앞까지)
    assert ".fpc-s__m > .fpc-s__at { display: inline; }" in block
    tpl = (ROOT / "templates/production/partials/home_pc_macros.html").read_text(encoding="utf-8")
    assert "<small class=\"fpc-s__at\">{{ _day or '기록 없음' }}</small>" in tpl
