"""생산 새 흐름 화면(ⓒ1) — 탭 줄 · '내 공정' 탭 · '작업 중' 탭 · 도면 보기 칩 · 담으면 빠지기(설계서
2026-11-28-production-my-steps-flow §3-1 ~ §3-6 · §4, 사장님 답 2 · 3 · 9 · 10 · 13 · 18 · 19 · 24 · 29 · 30 · 31 · 32).

서버가 그린 진짜 화면(템플릿)과 판 JS(viewer · claim · modal · cancel · crew · give · parts · sync · flow)를 같은 표시 줄 위에서 본다
(표시 줄은 진짜 쓰기 API 로, JS 에 주는 서버 답도 진짜 API 응답 · 진짜 화면 HTML).
되돌리면 실패: PC · 폰 탭 줄이 바뀜 · 파트 계정 '내 작업' 칩이 남음 · '오늘 끝낸 것'에 [완료 취소] · 같이 작업 카드 id 겹침 ·
담아도 카드가 판에 남음 · 반장 판 카드가 빠짐 · 섞인 화면에서 엣지 카드 요청이 재단(part=cut)으로 나감 · 받아 오기가 다른 파트 줄을 이 카드에 덮음.
이름은 모두 지어낸 값이다(김재단 · 오재단 · 박엣지 · 박반장 · 고객 정하늘 · 윤봄 · 서가을).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from tests.domains.test_production_flow_read import _done, _join, _order, _take, cohort  # noqa: F401
from tests.support.production_factory_seed import PC, TABLET, set_cookies
from tests.support.production_part_claim_seed import HOME_MINE, ONE, Person, login, make_user, mark

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "tests/support/production_flow_node_checks.js"
HOME = "/erp/production/home"
HOME_CREW = HOME + "?tab=crew"
PHONE = {"foms_ptr": "coarse", "foms_vw": "narrow", "foms_scr": "844"}
TPL = ROOT / "templates/production/partials"
FLOW_JS = ROOT / "static/js/production/foms-production-flow.js"


def _page(client, who: Person, url: str = HOME, cookies: dict = TABLET) -> str:
    login(client, who)
    set_cookies(client, cookies)
    resp = client.get(url)
    assert resp.status_code == 200, (url, resp.status_code)
    return resp.get_data(as_text=True)


def _nav(html: str) -> str:
    return html.split('<nav class="foms-prod-home__nav" aria-label="화면">', 1)[1].split("</nav>", 1)[0]


def _tabs(html: str) -> list[str]:
    return [re.sub(r"<[^>]+>", "", m).strip() for m in re.findall(r'<a class="foms-prod-home__navtab[^"]*"[^>]*>(.*?)</a>', _nav(html), re.S)]


def _card(html: str, key: str, start: int = 0) -> str:
    at = html.index(f'data-key="{key}"', start)
    return html[html.rindex("<article", 0, at):html.index("</article>", at)]


def _screen(html: str) -> str:
    return html[html.index("data-flow-screen"):html.index('class="pp-overlays"')]


def _node(html: str, tmp_path: Path, want: dict) -> dict:
    node = shutil.which("node")
    assert node, "node must be on PATH for JS checks"
    page, spec = tmp_path / "flow.html", tmp_path / "want.json"  # 서버 답(화면 HTML)이 길어 명령 줄이 아니라 파일로 넘긴다
    page.write_text(html, encoding="utf-8")
    spec.write_text(json.dumps(want, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run([node, str(CHECK), str(page), str(spec)], capture_output=True, text=True,
                          encoding="utf-8", timeout=60, cwd=str(ROOT))
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _post(client, who: Person, body: dict) -> dict:
    login(client, who)
    resp = client.post(ONE, json=body)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def _body(order, j: int, action: str, seen: str, part: str = "cut", **extra) -> dict:
    return {"order_id": order.id, "drawing_key": order.keys[j], "part": part, "action": action, "seen": seen, "seen_me": "none", **extra}


def _people():
    return (make_user("김재단", part="cut"), make_user("오재단", part="cut"), make_user("박엣지", part="edge"),
            make_user("박반장", lead=True))


# --------------------------------------------------------------------------- #
# 탭 줄
# --------------------------------------------------------------------------- #
def test_tab_rows_part_four_lead_admin_readonly_five_with_counts(client, cohort):
    kim, oh, edge, lead = _people()
    order = _order("정하늘", 3)
    _take(client, kim, order, 0)
    _take(client, kim, order, 1)
    _take(client, edge, order, 0, "edge")
    assert _tabs(_page(client, kim)) == ["날짜", "내 공정 2", "바뀐 것 0", "찾기"]
    assert _tabs(_page(client, kim, HOME_MINE)) == ["날짜", "내 공정 2", "바뀐 것 0", "찾기"]
    admin, ro = make_user("관리자", team="CS", role="ADMIN"), make_user("상담", team="CS")
    for who in (lead, admin, ro):
        tabs = _tabs(_page(client, who))
        assert tabs[:2] == ["날짜", "작업 중 3"] and tabs[2].startswith("남은 공정 ") and tabs[3:] == ["바뀐 것 0", "찾기"], who.name
    html = _page(client, lead, HOME_CREW)
    assert '<a class="foms-prod-home__navtab is-on" href="/erp/production/home?tab=crew" data-flow-tab="crew" aria-current="page">작업 중 <small data-flow-count="crew">3</small></a>' in html
    # 숫자가 None 인 탭(남은 공정 · 바뀐 것 · 찾기) — 숫자 칸을 숨겨 두고 흐름 JS 가 ?view=counts 로 채운다
    for url in (HOME + "?tab=changes", HOME + "?tab=all"):
        page = _page(client, kim, url)
        assert '<small data-flow-count="mine" hidden></small></a>' in page and "foms-production-flow.js?v=" in page, url
    assert '<small data-flow-count="crew" hidden></small>' in _page(client, lead, HOME + "?tab=steps")


def test_pc_and_phone_tab_row_is_byte_for_byte_the_old_one(client, cohort):
    """문 밖(PC 마우스 · 폰)은 flow 가 None — 탭 줄 · 스크립트 · CSS 가 바탕 커밋과 한 글자도 같다(답 28 "PC · 폰은 그대로")."""
    kim, _oh, _edge, lead = _people()
    order = _order("정하늘", 2)
    _take(client, kim, order, 0)
    old = ('\n\n<a class="foms-prod-home__navtab is-on" href="/erp/production/home" aria-current="page">날짜</a>\n'
           '{steps}<a class="foms-prod-home__navtab" href="/erp/production/home?tab=changes">바뀐 것 <small>0</small></a>\n'
           '<a class="foms-prod-home__navtab" href="/erp/production/home?tab=all">찾기</a>\n')
    steps = '<a class="foms-prod-home__navtab" href="/erp/production/home?tab=steps">남은 공정 <small>1</small></a>\n'
    for who, cookies in ((lead, PC), (kim, PC), (kim, PHONE), (lead, PHONE)):
        html = _page(client, who, HOME, cookies)
        assert _nav(html) == old.format(steps="" if who is kim else steps), (who.name, cookies)
        assert "data-flow" not in html and "foms-production-flow.js" not in html and "my-steps.css" not in html
        if who is kim and cookies is PHONE:  # 폰 파트 계정 판(가로로 돌려도 안 보이는 숨은 판)은 칩까지 지금 그대로
            assert '>내 작업 <small data-pp-count="need">' in html
    assert _page(client, kim, HOME_MINE, PC).count('data-foms-home-tab="date"') == 1  # 문 밖에서 ?tab=mine = 날짜


# --------------------------------------------------------------------------- #
# 도면 보기 칩 · 아침 칩 · 판에서 빠진 주문(받아 오기)
# --------------------------------------------------------------------------- #
def test_chips_two_for_part_three_for_lead_and_board_lists_dropped_orders(client, cohort):
    kim, _oh, _edge, lead = _people()
    order = _order("정하늘", 3, day=None)
    _take(client, kim, order, 0)
    part = _page(client, kim, HOME + "?day=none")
    chips = re.findall(r'data-pp-view="(\w+)"[^>]*>([^<]+)<small', part)
    assert [(v, t.strip()) for v, t in chips] == [("all", "전체 도면"), ("done", "완료")]  # '내 작업'만 없앰(답 10)
    assert 'data-pp-count="all">2<' in part and f'data-pp-orders="{order.id}"' in part  # 내 카드 한 장이 빠진 판 = 그 날 주문을 같이 받는다
    lead_html = _page(client, lead, HOME + "?day=none&tab=parts&part=cut")
    assert [t.strip() for _v, t in re.findall(r'data-pp-view="(\w+)"[^>]*>([^<]+)<small', lead_html)] == ["전체 도면", "작업 중", "완료"]
    assert lead_html.count("data-pp-card ") == 3 and "data-pp-orders" not in lead_html  # 반장 판은 아무 카드도 안 빠진다(답 19)


def test_morning_chip_view_goes_to_my_steps_tab(client, cohort):
    import datetime

    from db import db_session
    from foms.services.datetime_kst import now_utc_naive
    from models import ProductionPartMark
    kim = make_user("김재단", part="cut")
    order = _order("윤봄", 2)
    old = now_utc_naive() - datetime.timedelta(days=2)
    db_session.add(ProductionPartMark(order_id=order.id, drawing_key=order.keys[0], part="cut", state="NEED", picked_by_user_id=kim.id,
                                      picked_by_name=kim.name, picked_at=old, updated_by_user_id=kim.id, updated_at=old))
    db_session.commit()
    html = _page(client, kim)
    assert 'aria-controls="pp-mpop">어제부터 내 작업 1장' in html
    assert re.findall(r'<a href="([^"]*)" aria-label="[^"]*보기">보기</a>', html) == [HOME_MINE]  # 빈 #pp-mine 대신 '내 공정' 탭


# --------------------------------------------------------------------------- #
# '내 공정' 탭
# --------------------------------------------------------------------------- #
def test_my_steps_strip_groups_done_words_and_no_undo_for_part_staff(client, cohort):
    kim, oh, _edge, _lead = _people()
    a, b, c = _order("정하늘", 2, day=1), _order("윤봄", 1, day=3), _order("서가을", 1, day=None)
    _take(client, kim, a, 0)
    _take(client, kim, a, 1)
    _take(client, oh, b, 0)
    _join(client, kim, b, 0)
    _take(client, kim, c, 0)
    _done(client, kim, c, 0)
    html = _page(client, kim, HOME_MINE)
    date = _page(client, kim, HOME + "?day=none")
    scr = _screen(html)
    rows = re.findall(r'<button type="button" class="fph-sd([^"]*)" data-flow-day="([^"]+)" aria-pressed="(\w+)">\s*'
                      r'<span class="fph-sd__d"><b>([^<]+)</b><small>([^<]*)</small></span>\s*<span class="fph-sd__mid"></span>\s*'
                      r'<span class="fph-sd__n">(.*?)</span>\s*</button>', scr)
    assert len(rows) == 1 + len(re.findall(r'<a class="fph-sd[ "]', date))  # 날짜 탭과 같은 줄 + 맨 위 '전체'
    assert rows[0][1:5] == ("all", "true", "전체", "모든 날") and "is-on" in rows[0][0]  # 처음 골라짐(답 29)
    nums = {key: re.sub(r"<[^>]+>", "", n) for _c, key, _p, _l, _s, n in rows}
    assert nums["all"] == "3장" and sum(1 for v in nums.values() if v) == 3  # 전체 · 내일 · D-3 세 줄만 숫자
    assert all(("is-zero" in cls) == (not re.sub(r"<[^>]+>", "", n)) for cls, _k, _p, _l, _s, n in rows)  # 0 인 줄은 흐리게 · 숫자 없음
    assert '<div class="fph-strip__h">출고일 2주<small>내가 담은 도면</small></div>' in scr
    heads = [re.sub(r"<[^>]+>", "", h).strip() for h in re.findall(r'<h[34] class="fpf-[go]">(.*?)</h[34]>', scr)]
    assert re.fullmatch(r"내일 \d+/\d+ \(.\) 시공 · 2장", heads[0]) and heads[1] == f"정하늘 #{a.id} · 2장"
    assert re.fullmatch(r"\d+/\d+ \(.\) 시공 · 1장", heads[2]) and heads[3] == f"윤봄 #{b.id} · 1장"
    assert heads[4] == "오늘 끝낸 것 1"
    done = scr.split("data-flow-done", 1)[1]
    assert f'data-key="{c.keys[0]}"' in done and 'data-pp-act="undo"' not in done and ">재단 완료 · 김재단</span>" in done  # 파트 직원 = 완료 취소 없음
    assert 'data-pp-act="undo"' in _card(date, c.keys[0])  # 대조군 — 날짜 판 '완료' 카드는 지금 그대로
    mine = _card(scr, a.keys[0])
    assert 'data-pp-act="release">재단 시작&nbsp;취소</button>' in mine and 'data-pp-act="done">재단 완료</button>' in mine
    assert re.search(r'data-part="cut" data-part-label="재단" data-day="20\d\d-\d\d-\d\d"', mine)  # 띠 줄 열쇠(카드 파트 · 날)
    assert '<p class="pp-empty" data-flow-empty hidden>담은 도면이 없어요. 날짜 탭에서 [재단 시작]을 누르면 여기에 모여요.</p>' in scr
    assert len(re.findall(r'id="(pp-why-[^"]+)"', scr)) == len(set(re.findall(r'id="(pp-why-[^"]+)"', scr)))
    empty = _screen(_page(client, oh := make_user("최재단", part="cut"), HOME_MINE))
    assert '<p class="pp-empty" data-flow-empty>담은 도면이 없어요. 날짜 탭에서 [재단 시작]을 누르면 여기에 모여요.</p>' in empty
    assert oh.name == "최재단" and ">오늘 끝낸 것 <small data-flow-done-n>0</small>" in empty


def test_my_steps_cap_line_uses_the_board_cap_words(client, cohort, monkeypatch):
    kim = make_user("김재단", part="cut")
    order = _order("정하늘", 3)
    for j in range(3):
        _take(client, kim, order, j)
    monkeypatch.setattr("foms.services.production.part_board.PART_BOARD_CARD_CAP", 2)
    scr = _screen(_page(client, kim, HOME_MINE))
    assert scr.count("data-pp-card ") == 2 and '<p class="pp-cap">1장이 더 있어요. [찾기]에서 손님 이름으로 찾아 주세요.</p>' in scr


# --------------------------------------------------------------------------- #
# '작업 중' 탭
# --------------------------------------------------------------------------- #
def _crew_seed(client):
    kim, oh, edge, lead = _people()
    order = _order("정하늘", 4)
    _take(client, kim, order, 0)
    _take(client, kim, order, 1)
    _join(client, oh, order, 1)
    _take(client, edge, order, 0, "edge")
    return kim, oh, edge, lead, order


def test_crew_people_groups_ids_parts_none_buttons_and_readonly(client, cohort):
    kim, oh, edge, lead, order = _crew_seed(client)
    k = order.keys
    scr = _screen(_page(client, lead, HOME_CREW))
    heads = [re.sub(r"<[^>]+>", "", h).strip() for h in re.findall(r'<h3 class="fpf-g">(.*?)</h3>', scr)]
    assert heads == ["김재단 · 재단 2장", "오재단 · 재단 1장", "박엣지 · 엣지 1장", "미정"]
    assert scr.count(f'data-key="{k[1]}"') == 2  # 같이 작업 카드는 두 사람 묶음에 모두(답 32)
    ids = re.findall(r'id="(pp-why-[^"]+)"', scr)
    assert len(ids) == len(set(ids)) == scr.count("data-pp-card ")  # 같은 장이 두 번 · 두 파트로 서도 말풍선 id 가 안 겹친다
    for ref in re.findall(r'aria-describedby="(pp-why-[^"]+)"', scr):
        assert ref in ids
    assert re.findall(r'data-part="(\w+)" data-part-label="(\w+)"', scr) == [("cut", "재단")] * 3 + [("edge", "엣지")]
    edge_card = _card(scr, k[0], scr.index("박엣지"))
    assert 'data-pp-act="check">엣지 완료</button>' in edge_card and "재단 완료" not in edge_card  # 카드마다 그 파트 글
    chips = re.findall(r'<a class="pp-part( is-on)?" href="([^"]+)"[^>]*>(\w+)</a>', scr)
    assert [(on, t) for on, _h, t in chips] == [(" is-on", "전체"), ("", "재단"), ("", "엣지"), ("", "조립"), ("", "검수")]
    buttons = re.findall(r'<a class="foms-prod-home__btn fpf-none__btn" href="([^"]+)">(\w+) 미정 (\d+)장 ›</a>', scr)
    assert [(t, n) for _h, t, n in buttons] == [("재단", "2"), ("엣지", "3"), ("조립", "4"), ("검수", "4")]
    assert [h for h, _t, _n in buttons] == [h for _on, h, _t in chips[1:]]  # 단추 = 그 파트 칩 주소
    for _h, label, n in buttons:  # 파트를 고르면 미정 카드가 펼쳐진다 — 숫자 = 카드 수
        key = {"재단": "cut", "엣지": "edge", "조립": "assemble", "검수": "inspect"}[label]
        picked = _screen(_page(client, lead, HOME_CREW + "&part=" + key))
        none = picked[picked.index('class="fpf-none'):]
        assert f">미정 <small>· {label} {n}장</small></h3>" in none and none.count("data-pp-card ") == int(n), label
    ro = _screen(_page(client, make_user("상담", team="CS"), HOME_CREW))
    assert ro.count("data-pp-card ") == 4 and "data-pp-act=" not in ro  # 읽기 전용 = 단추 없이


def test_crew_empty_words_and_factory_links_come_from_the_server(client, cohort):
    lead = make_user("박반장", lead=True)
    _order("서가을", 2)
    scr = _screen(_page(client, lead, HOME_CREW))
    assert '<p class="pp-empty is-full">지금 작업 중인 도면이 없어요.</p>' in scr and "pp-parts--fac" not in scr
    assert "url_for(" not in (TPL / "home_crew.html").read_text(encoding="utf-8")  # 주소는 서버(home_flow)가 짓는다


# --------------------------------------------------------------------------- #
# 화면 글(설계서 §4) · 파일 약속
# --------------------------------------------------------------------------- #
def test_screen_words_are_the_spec_words_and_files_keep_their_limits():
    body = (TPL / "home_body.html").read_text(encoding="utf-8")
    mine = (TPL / "home_mine.html").read_text(encoding="utf-8")
    crew = (TPL / "home_crew.html").read_text(encoding="utf-8")
    flow = FLOW_JS.read_text(encoding="utf-8")
    assert "{{ '내 공정' if ft == 'mine' else '작업 중' }}" in body
    for word in ("출고일 2주<small>내가 담은 도면</small>", " 시공{% endif %} <small>· {{ day.count }}장</small>",
                 "{{ o.name }} #{{ o.id }} <small>· {{ o.count }}장</small>", "오늘 끝낸 것 <small data-flow-done-n>",
                 "담은 도면이 없어요. 날짜 탭에서 [{{ pb.part_label if pb else '' }} 시작]을 누르면 여기에 모여요."):
        assert word in mine, word
    for word in ("{{ g.name }} <small>· {{ g.part_label }} {{ g.cards | length }}장</small>", "<h3 class=\"fpf-g\">미정</h3>",
                 "{{ p.label }} 미정 {{ cw.none.counts[p.key] }}장 ›", "미정 <small>· {{ picked.label }} ", "지금 작업 중인 도면이 없어요."):
        assert word in crew, word
    assert "var SAID = ' · 내 공정에 담았어요';" in flow and "주문 줄로 보기" not in crew  # 답 30 '가' — 남은 공정 탭이 있어 링크 없음
    assert len(flow.splitlines()) < 300
    for name, cap in (("parts", 299), ("parts-viewer", 299), ("parts-sync", 299)):
        assert len((ROOT / f"static/js/production/foms-production-{name}.js").read_text(encoding="utf-8").splitlines()) <= cap, name
    for tpl in (mine, crew):
        assert "style=" not in tpl and "<script" not in tpl


# --------------------------------------------------------------------------- #
# JS — 담으면 빠지기 · 반장은 그대로 · 띠 거르기 · 받아 오기 다시 받기 · 섞인 화면 카드 파트
# --------------------------------------------------------------------------- #
def test_js_take_and_join_leave_the_board_with_count_and_words(client, cohort, tmp_path):
    kim, oh, _edge, _lead = _people()
    order = _order("정하늘", 2, day=None)
    _take(client, oh, order, 1)
    html = _page(client, kim, HOME + "?day=none")
    took = _post(client, kim, _body(order, 0, "take", "none"))
    joined = _post(client, kim, _body(order, 1, "join", "need", seen_by=oh.id))
    res = _node(html, tmp_path, {"href": HOME + "?day=none", "posts": [took, joined], "steps": [
        {"do": "screen"}, {"do": "click", "key": order.keys[0], "act": "take"}, {"do": "run"},
        {"do": "click", "key": order.keys[1], "act": "join"}, {"do": "run"}]})
    out, calls = res["out"], res["calls"]
    before, first, second = out[0]["screen"], out[2], out[4]
    assert before["cards"] == list(order.keys) and before["all_chip"] == "2" and before["mine"]["text"] == "0"
    assert first["sent"] == 1 and first["modal"]["hidden"] and first["screen"]["cards"] == [order.keys[1]]
    assert first["screen"]["status"] == "재단 시작했어요 · 내 공정에 담았어요"  # 답 31
    assert (first["screen"]["all_chip"], first["screen"]["mine"]["text"]) == ("1", "1")
    assert second["screen"]["status"] == "재단 같이 작업 시작했어요 · 내 공정에 담았어요"
    assert second["screen"]["cards"] == [] and second["screen"]["mine"]["text"] == "2" and second["screen"]["empty"]["hidden"] is False
    assert [c["body"]["part"] for c in calls if c["method"] == "POST"] == ["cut", "cut"]


def test_js_lead_board_keeps_cards_and_refreshes_the_crew_count(client, cohort, tmp_path):
    _kim, _oh, _edge, lead = _people()
    order = _order("정하늘", 2, day=None)
    html = _page(client, lead, HOME + "?day=none&tab=parts&part=cut")
    took = _post(client, lead, _body(order, 0, "take", "none"))
    login(client, lead)
    counts = client.get(HOME + "?view=counts").get_json()
    res = _node(html, tmp_path, {"href": HOME + "?day=none&tab=parts&part=cut", "posts": [took],
                                 "gets": [{"match": "view=counts", "json": counts}],
                                 "steps": [{"do": "click", "key": order.keys[0], "act": "take"}, {"do": "run"}]})
    after = res["out"][1]["screen"]
    assert after["cards"] == list(order.keys) and after["status"] == "재단 시작했어요"  # 반장 판 = 아무 카드도 안 빠진다(답 19)
    assert after["crew"] == {"text": "1", "hidden": False} and res["left"] == []


def test_js_my_steps_strip_filters_cards_groups_and_done(client, cohort, tmp_path):
    kim = make_user("김재단", part="cut")
    a, b, c = _order("정하늘", 2, day=1), _order("윤봄", 1, day=3), _order("서가을", 1, day=1)
    for o, j in ((a, 0), (a, 1), (b, 0), (c, 0)):
        _take(client, kim, o, j)
    _done(client, kim, c, 0)
    html = _page(client, kim, HOME_MINE)
    day1 = re.search(r'data-flow-day="(20[0-9-]+)" aria-pressed="false">\s*<span class="fph-sd__d"><b>[^<]+</b><small>[^<]*내일', html).group(1)
    res = _node(html, tmp_path, {"href": HOME_MINE, "steps": [{"do": "screen"}, {"do": "day", "key": day1}, {"do": "day", "key": "later"},
                                                             {"do": "day", "key": "all"}]})
    full, one, none, back = (o["screen"] for o in res["out"])
    cut = [f"{key}@cut" for key in (a.keys[0], a.keys[1], b.keys[0])]
    assert full["cards"] == cut and full["done"] == [c.keys[0]] and full["done_n"] == "1"
    assert one["cards"] == cut[:2] and one["done"] == [c.keys[0]] and one["pressed"] == [day1]  # 끝낸 것도 그날 것만
    assert len(one["groups"]) == 2 and one["empty"]["hidden"] is True
    assert none["cards"] == [] and none["done"] == [] and none["done_n"] == "0" and none["empty"]["hidden"] is False
    assert back == full and res["calls"] == []  # 화면 거르기 — 요청 없음


def test_js_sync_mine_now_and_not_mine_reload_the_day_pane(client, cohort, tmp_path):
    kim, oh, _edge, lead = _people()
    order = _order("정하늘", 3, day=None)
    _take(client, oh, order, 1)
    _take(client, kim, order, 2)
    url = HOME + "?day=none"
    html = _page(client, kim, url)
    since = re.search(r'data-pp-since="([^"]+)"', html).group(1)
    assert f'data-pp-orders="{order.id}"' in html and f'data-key="{order.keys[2]}"' not in html
    _post(client, lead, _body(order, 1, "takeover", "need", seen_by=oh.id, target_user_id=oh.id, to_user_id=kim.id))  # 반장이 나에게 줌
    _post(client, lead, _body(order, 2, "takeover", "need", seen_by=kim.id, target_user_id=kim.id, to_user_id=oh.id))  # 내 것을 남에게
    login(client, kim)
    synced = client.get(f"/api/production/part-marks?order_ids={order.id}&since={since}").get_json()
    day = client.get(url + "&view=day")
    counts = client.get(HOME + "?view=counts").get_json()
    res = _node(html, tmp_path, {"href": url, "gets": [
        {"match": "/api/production/part-marks?", "json": synced},
        {"match": "view=day", "html": day.get_data(as_text=True), "header": {"X-FOMS-HOME-DAY": "none"}},
        {"match": "view=counts", "json": counts}], "steps": [{"do": "sync"}]})
    after = res["out"][0]["screen"]
    gets = [c["url"] for c in res["calls"] if c["method"] == "GET"]
    assert any("view=day" in u and "day=none" in u for u in gets) and res["left"] == []  # 그 날 장 다시 받기(새 길 없음)
    assert after["cards"] == [order.keys[0], order.keys[2]] and after["mine"]["text"] == "1"  # 받은 카드는 빠지고 넘긴 카드는 판으로


def test_js_my_steps_done_and_sync_reload_the_screen(client, cohort, tmp_path):
    kim, oh, _edge, lead = _people()
    order = _order("정하늘", 2, day=1)
    _take(client, kim, order, 0)
    _take(client, kim, order, 1)
    html = _page(client, kim, HOME_MINE)
    done = _post(client, kim, _body(order, 0, "done", "need", seen_me="held", seen_by=kim.id))
    after_done = _page(client, kim, HOME_MINE)
    res = _node(html, tmp_path, {"href": HOME_MINE, "posts": [done], "gets": [{"match": HOME_MINE, "html": after_done}],
                                 "steps": [{"do": "click", "key": order.keys[0], "act": "done"}, {"do": "run"}]})
    assert res["out"][0]["modal"]["title"] == "재단 완료할까요?"
    moved = res["out"][1]["screen"]
    assert moved["cards"] == [order.keys[1] + "@cut"] and moved["done"] == [order.keys[0]] and moved["mine"]["text"] == "1"
    assert moved["status"] == "재단 완료했어요" and res["left"] == []

    since = re.search(r'data-pp-since="([^"]+)"', after_done).group(1)
    _post(client, lead, _body(order, 1, "takeover", "need", seen_by=kim.id, target_user_id=kim.id, to_user_id=oh.id))
    login(client, kim)
    synced = client.get(f"/api/production/part-marks?order_ids={order.id}&since={since}").get_json()
    gone = _page(client, kim, HOME_MINE)
    res = _node(after_done, tmp_path, {"href": HOME_MINE, "gets": [{"match": "/api/production/part-marks?", "json": synced},
                                                                   {"match": HOME_MINE, "html": gone}], "steps": [{"do": "sync"}]})
    assert res["out"][0]["screen"]["cards"] == [] and res["out"][0]["screen"]["mine"]["text"] == "0" and res["left"] == []


def test_js_crew_mixed_parts_write_and_sync_follow_the_card_part(client, cohort, tmp_path):
    """'작업 중' 전체(파트 섞임): 엣지 카드 [엣지 완료] = 요청 part edge · 창 글 엣지, 같은 장 재단 카드는 그대로. 받아 오기도 장 + 파트로."""
    kim, _oh, edge, lead = _people()
    order = _order("정하늘", 2)
    _take(client, kim, order, 0)
    _take(client, edge, order, 0, "edge")
    html = _page(client, lead, HOME_CREW)
    since = re.search(r'data-pp-since="([^"]+)"', html).group(1)
    checked = _post(client, lead, _body(order, 0, "check", "need", part="edge", seen_by=edge.id))
    after = _page(client, lead, HOME_CREW)
    res = _node(html, tmp_path, {"href": HOME_CREW, "posts": [checked], "gets": [{"match": HOME_CREW, "html": after}], "steps": [
        {"do": "card", "key": order.keys[0], "part": "cut"},
        {"do": "click", "key": order.keys[0], "part": "edge", "act": "check"}, {"do": "run"},
        {"do": "card", "key": order.keys[0], "part": "cut"}]})
    out, calls = res["out"], res["calls"]
    assert out[1]["modal"]["title"] == "엣지 완료할까요?" and out[1]["modal"]["run"] == "엣지 완료"  # 머리 파트(재단) 글이 아니다
    assert [c["body"]["part"] for c in calls if c["method"] == "POST"] == ["edge"]  # 남의 줄(재단)을 고치지 않는다
    same = ("state", "acts", "text", "part")
    assert {k: out[3]["card"][k] for k in same} == {k: out[0]["card"][k] for k in same} and out[0]["card"]["state"] == "need"  # 같은 장 재단 카드 = 그대로
    assert out[2]["screen"]["cards"] == [f"{order.keys[0]}@cut"] and res["left"] == []  # 다시 받은 화면 — 엣지 카드는 끝나 빠짐

    # 받아 오기: 엣지 줄의 변화는 엣지 카드에만, 같은 장 재단 카드에는 다른 파트 낱말로만(장 key + 카드 파트로 맞춘다)
    _take(client, edge, order, 1, "edge")
    _take(client, kim, order, 1)
    page = _page(client, lead, HOME_CREW)
    since = re.search(r'data-pp-since="([^"]+)"', page).group(1)
    _post(client, lead, _body(order, 1, "check", "need", part="edge", seen_by=edge.id))
    login(client, lead)
    synced = client.get(f"/api/production/part-marks?order_ids={order.id}&since={since}").get_json()
    res = _node(page, tmp_path, {"href": HOME_CREW, "gets": [{"match": "/api/production/part-marks?", "json": synced}], "steps": [
        {"do": "card", "key": order.keys[1], "part": "cut"}, {"do": "sync"},
        {"do": "card", "key": order.keys[1], "part": "cut"}, {"do": "card", "key": order.keys[1], "part": "edge"}]})
    cut0, cut1, edge1 = res["out"][0]["card"], res["out"][2]["card"], res["out"][3]["card"]
    assert edge1["state"] == "done" and edge1["text"].startswith("엣지 완료 · 박반장")  # 다시 그린 글도 카드 파트 이름(반장 대신 완료)
    assert {k: cut1[k] for k in same} == {k: cut0[k] for k in same} and cut1["state"] == "need"  # 재단 카드 상태 · 단추 그대로
    assert "edge:fph-by pp-w-done" in cut1["others"] and "edge:fph-by pp-w-done" not in cut0["others"]  # 다른 파트 낱말만 바뀜
    assert any(c["method"] == "GET" and c["url"].endswith(HOME_CREW) for c in res["calls"])  # 카드가 바뀌면 화면 다시 받기(사람 묶음 · 숫자)
