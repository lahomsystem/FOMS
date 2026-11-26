"""여러 명이 같이 작업 M2 — 공장 태블릿 도면 판(설계서 2026-11-25 multi-holder §8 · §10 M2 · §11 M2, 시안 01 A ~ I · 창 셋).

서버가 그린 판(템플릿)과 판 JS(crew · claim · modal · parts · sync)를 같은 표시 줄 위에서 본다. 표시 줄은 진짜 쓰기 API 로 만든다.
* 칸 글: [작업 시작](네 파트 같은 글) · 남이 작업 중 = "이시영 작업 중" 칸 + [같이 작업] · 둘 "이시영 · 김재단 작업 중" · 셋
  "이시영 · 김재단 외 1 작업 중"(이름 줄 = 서버 한 함수 — "외 n" · "작업 중"은 칸 없는 띄어쓰기) · 내 작업 꼬리 "내 작업 · 이시영과 같이" ·
  "내 작업 · 이시영 완료" · 내 몫만 완료 = '완료' 칸 "재단 1/2 완료 · 김재단 작업 중" + 되돌리기 줄 "재단 1/2 완료"(Q12) · 모두 완료
  "재단 완료 · 이시영 · 김재단" · 반장 칸 이름 + 둘째 줄 "재단 1/2 완료" · 보기만 "이시영 · 김재단 작업 중" · 검수 판 "재단 미완료".
* JS: 서버 칸 ↔ JS 가 다시 그린 칸이 같다(카드 전부) · [같이 작업] 창 · 거의 같이 [작업 시작] 말풍선(서버 글 그대로, 그림 칸 안 · 누르면
  닫힘) · [담당 바꾸기] 사람 고르기(바꿀 사람이 둘 이상일 때만 — 하나면 지금 동작, 완료한 사람 빠짐, 고르기 전 실행 잠금) · 반장 고르기
  ([담당 바꾸기(둘 이상이면 ›)] · [대신 완료] · [같이 작업](아직 작업자가 아닐 때, Q22) · [{이름} 시작 취소]) · 남은 사람이 있는 [완료] ·
  [시작 취소] 창 · 30초 받아 오기가 이름 줄을 바꿈 · 토씨가 붙는 문장의 "외 n명"(Q20 — 토씨는 서버가). 서버 답은 진짜 API 응답 JSON 이다.
되돌리면 실패: 이름 줄을 JS 가 짓기(서버 head · who 대신) · "1/2 완료"를 '작업 필요' 칸에 · [같이 작업] 대신 담당 바꾸기만 · 완료한 사람을 고르기에 ·
고르기 전 실행 · 넘김 글을 버림. 이름은 모두 지어낸 값이다.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from html import unescape
from pathlib import Path
from types import SimpleNamespace

import pytest

from foms.services.production import mark_crew as mc, part_card_crew
from foms.services.production.part_card_crew import NBSP, crew_view, with_particle
from tests.support.production_factory_seed import HOME_NONE, TABLET, factory_user, mixed_order, set_cookies
from tests.support.production_part_claim_seed import ONE, login, make_order, make_user, mark

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "tests/support/production_multi_holder_node_checks.js"
CUT_ADMIN = HOME_NONE + "&tab=parts&part=cut"


@pytest.fixture
def cohort(monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")


def _press(client, who, order, j, action, seen, part="cut", **extra):
    login(client, who)
    resp = mark(client, order, j, part, action, seen, **extra)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["data"]


def _seed(client) -> SimpleNamespace:
    """정하늘 도면 6장(재단): 0 · 4 = 아무도 안 시작(A), 1 = 이시영(B), 2 = 이시영 완료 · 김재단 작업 중(E1 · E2 · G · H — 엣지 ·
    조립 완료), 3 = 둘 다 완료(F), 5 = 이시영 · 김재단 · 최재단(I)."""
    p = SimpleNamespace(lee=make_user("이시영", part="cut"), kim=make_user("김재단", part="cut"), park=make_user("박재단", part="cut"),
                        choi=make_user("최재단", part="cut"), lead=make_user("박반장", lead=True),
                        edge=make_user("박엣지", part="edge"), asm=make_user("박조립", part="assemble"),
                        insp=make_user("강검수", part="inspect"), cs=make_user("상담", team="CS"))
    order = make_order(6)
    _press(client, p.lee, order, 1, "take", "none")
    _press(client, p.lee, order, 2, "take", "none")
    _press(client, p.kim, order, 2, "join", "need")
    _press(client, p.lee, order, 2, "done", "need")
    for who, part in ((p.edge, "edge"), (p.asm, "assemble")):
        _press(client, who, order, 2, "take", "none", part)
        _press(client, who, order, 2, "done", "need", part)
    _press(client, p.lee, order, 3, "take", "none")
    _press(client, p.kim, order, 3, "join", "need")
    _press(client, p.lee, order, 3, "done", "need")
    _press(client, p.kim, order, 3, "done", "need")
    for who in (p.lee, p.kim, p.choi):
        _press(client, who, order, 5, "join" if who is not p.lee else "take", "need" if who is not p.lee else "none")
    p.order = order
    return p


def _page(client, who, url: str = HOME_NONE) -> str:
    login(client, who)
    set_cookies(client, TABLET)
    resp = client.get(url)
    assert resp.status_code == 200, resp.status_code
    return resp.get_data(as_text=True)


def _card(html: str, key: str) -> str:
    start = html.index(f'data-key="{key}"')
    return html[html.rindex("<article", 0, start):html.index("</article>", start)]


def _act(card: str) -> str:
    return card.split('role="status" hidden></p>', 1)[1]


def _crew(card: str) -> dict:
    return json.loads(unescape(re.search(r'data-pp-crew="([^"]+)"', card).group(1)))


def _node(page: Path, want: dict) -> dict:
    node = shutil.which("node")
    assert node, "node must be on PATH for JS checks"
    proc = subprocess.run([node, str(CHECK), str(page), json.dumps(want, ensure_ascii=False)], capture_output=True, text=True,
                          encoding="utf-8", timeout=60, cwd=str(ROOT))
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _body(order, j: int, action: str, seen: str, **extra) -> dict:
    return {"order_id": order.id, "drawing_key": order.keys[j], "part": "cut", "action": action, "seen": seen, **extra}


def _post(client, who, body: dict) -> dict:
    login(client, who)
    resp = client.post(ONE, json=body)
    return {"__status": resp.status_code, "body": resp.get_json()} if resp.status_code != 200 else resp.get_json()


# --------------------------------------------------------------------------- #
# 이름 줄 — 서버 한 함수(crew_view)
# --------------------------------------------------------------------------- #
def test_crew_view_lines_for_each_viewer() -> None:
    rows = [{"user_id": 1, "name": "이시영", "done": True, "picked_at": "2026-11-24T23:10:00+00:00", "picked_day": "2026-11-25",
             "done_name": "이시영"},
            {"user_id": 2, "name": "김재단", "done": False, "picked_at": "2026-11-25T00:02:00+00:00", "picked_day": "2026-11-25"},
            {"user_id": 3, "name": "최재단", "done": False, "picked_at": "2026-11-25T00:05:00+00:00", "picked_day": "2026-11-25"}]
    kim = crew_view(rows, 2, "김재단")
    assert (kim["n"], kim["d"], kim["me"], kim["who"]) == (3, 1, "held", "이시영 · 김재단 외 1")
    assert kim["head"] == f"이시영 · 김재단 외{NBSP}1 작업{NBSP}중"  # "외 1" · "작업 중"은 안 쪼개짐(§8-2 6)
    assert (kim["left"], kim["others_left"], kim["done"], kim["with"]) == ("김재단 · 최재단", "최재단", "이시영", "이시영 · 최재단")
    assert kim["tag"] == "이시영 완료" and kim["sig"] == "1:1,2:0,3:0"
    park = crew_view(rows, 9, "박재단")
    assert (park["me"], park["join"], park["tag"], park["with"]) == ("none", "이시영 · 김재단 외 2", "", "")
    swap = {p["name"]: (p["swap"], p["drop"]) for p in park["people"]}
    assert swap == {"이시영": ("박재단 · 김재단 외 1", "김재단 · 최재단"), "김재단": ("이시영 · 박재단 외 1", "이시영 · 최재단"),
                    "최재단": ("이시영 · 김재단 외 1", "이시영 · 김재단")}
    two = crew_view(rows[1:], 2, "김재단")
    assert two["tag"] == "최재단과 같이" and crew_view(rows[:2], 2, "김재단")["tag"] == "이시영 완료"
    assert crew_view([], 2, "김재단")["who"] == "" and crew_view(None, 2, "")["n"] == 0
    assert [with_particle(n) for n in ("이시영", "김재단", "이시영 외 1", "이시영 외 2", "박서희")] == [
        "이시영과", "김재단과", "이시영 외 1과", "이시영 외 2와", "박서희와"]
    # 문장 속 이름 줄 = "외 n명" + 토씨는 서버가(Q20) — 칸 글(who · head)은 "외 n" 그대로
    four = rows + [{"user_id": 4, "name": "박재단", "done": False, "picked_at": None, "picked_day": None}]
    assert (kim["who_subj"], kim["done_subj"], kim["others_left_subj"]) == ("이시영 · 김재단 외 1명이", "이시영이", "최재단이")
    kim4 = crew_view(four, 2, "김재단")
    assert (kim4["who"], kim4["who_subj"], kim4["others_left_subj"]) == ("이시영 · 김재단 외 2", "이시영 · 김재단 외 2명이",
                                                                          "최재단 · 박재단이")
    assert crew_view([dict(r, done=False) for r in four], 2, "김재단")["tag"] == "이시영 · 최재단 외 1명과 같이"
    assert [p["subj"] for p in kim4["people"]] == ["이시영이", "김재단이", "최재단이", "박재단이"]
    # "외 n명" 규칙은 한 벌(mark_crew.name_sentence) — 카드 칸 문장도 같은 함수가 지은 글(11-25 검토 5)
    assert kim4["who_subj"] == mc.name_sentence(["이시영", "김재단", "최재단", "박재단"]) + "이" == "이시영 · 김재단 외 2명이"
    assert not hasattr(part_card_crew, "sentence_line")


# --------------------------------------------------------------------------- #
# 서버가 그린 판(시안 01 A ~ I)
# --------------------------------------------------------------------------- #
def test_board_cards_follow_the_mockup(client, cohort) -> None:
    p = _seed(client)
    k = p.order.keys
    kim = _page(client, p.kim)
    a = _act(_card(kim, k[0]))  # A — [기본][작업 시작]
    assert ('data-pp-act="basic">기본</button><button type="button" class="foms-prod-home__btn foms-prod-home__btn--pri" '
            'data-pp-act="take">작업 시작</button></div>') in a
    b = _card(kim, k[1])  # B — 이시영 작업 중 + [같이 작업]
    assert 'class="pp-card is-other"' in b and '<div class="pp-two pp-two--join">' in _act(b)
    assert f"<b>이시영 작업{NBSP}중</b>" in _act(b) and 'data-pp-act="join">같이 작업</button></div>' in _act(b)
    assert 'data-in-need="0" data-in-done="0"' in b and _crew(b)["join"] == "이시영 · 김재단"
    e2 = _card(kim, k[2])  # E2 — 내 작업(이시영은 완료)
    assert 'class="pp-card is-mine"' in e2 and '<span class="pp-tag" data-pp-tag aria-label="내 작업 · 이시영 완료">내 작업 · 이시영 완료</span>' in e2
    assert 'data-pp-act="release">시작 취소</button>' in _act(e2) and 'data-pp-act="done">재단 완료</button></div>' in _act(e2)
    f = _act(_card(kim, k[3]))  # F — 모두 완료
    assert '<span class="fph-wi pp-act pp-st-done pp-not-done">재단 완료 · 이시영 · 김재단</span>' in f and 'data-pp-act="undo"' in f
    mine3 = _card(kim, k[5])
    assert "내 작업 · 이시영 · 최재단과 같이" in mine3
    assert 'data-pp-count="need">2<' in kim and 'data-pp-count="done">1<' in kim

    lee = _page(client, p.lee)
    e1 = _card(lee, k[2])  # E1 — 내 몫만 완료 = '완료' 칸
    assert 'data-in-need="0" data-in-done="1"' in e1 and 'class="pp-card"' in e1
    assert '<span class="fph-wi pp-act pp-st-need pp-not-done">재단 1/2 완료 · 김재단 작업 중</span>' in _act(e1)
    assert ('<div class="fph-wi pp-act pp-undo-row pp-st-done pp-only-done"><span>재단 1/2 완료</span><button type="button" '
            'class="foms-prod-home__btn pp-undo" data-pp-act="undo">되돌리기</button></div>') in _act(e1)
    assert 'data-pp-count="need">2<' in lee and 'data-pp-count="done">2<' in lee  # 1/2 완료도 내 '완료' 칸(Q12)

    park = _page(client, p.park)
    assert f"<b>이시영 · 김재단 작업{NBSP}중</b>" in _act(_card(park, k[2]))  # D — 남의 화면 · 이름 둘
    i = _act(_card(park, k[5]))  # I — 셋 = 둘까지 + 외 1
    assert f"<b>이시영 · 김재단 외{NBSP}1 작업{NBSP}중</b>" in i and 'data-pp-act="join"' in i

    lead = _act(_card(_page(client, p.lead, CUT_ADMIN), k[2]))  # G — 반장: 이름 칸 둘째 줄 "재단 1/2 완료" + [재단 완료]
    assert 'class="fph-wi pp-act pp-st-need pp-not-need pp-held" data-pp-act="held"' in lead
    assert f"<b>이시영 · 김재단 작업{NBSP}중</b><small>재단 1/2 완료</small>" in lead
    assert 'data-pp-act="check">재단 완료</button>' in lead and 'data-pp-act="join"' not in lead  # 반장 칸 [재단 완료] = 대신 완료
    ro = _act(_card(_page(client, p.cs, CUT_ADMIN), k[2]))  # 보기만 — 같은 이름 줄(K5)
    assert ro.strip().startswith(f'<span class="fph-wi pp-act pp-st-need">이시영 · 김재단 작업{NBSP}중</span>') and "<button" not in ro

    insp = _card(_page(client, p.insp), k[2])  # H — 검수 판: 재단 1/2 완료 = 미완료, 다른 파트 낱말 '완료'
    assert ">재단 미완료</button>" in _act(insp) and "<i>재단</i> 중" in insp and "<i>엣지</i> 완료" in insp and "<i>조립</i> 완료" in insp

    _press(client, p.kim, p.order, 1, "join", "need")  # C — 내 화면 · 둘이 작업
    c = _card(_page(client, p.kim), k[1])
    assert 'class="pp-card is-mine"' in c and "내 작업 · 이시영과 같이" in c and 'data-pp-act="release">시작 취소</button>' in c
    assert f"<b>이시영 · 김재단 작업{NBSP}중</b>" in _act(_card(_page(client, p.park), k[1]))  # D


def test_other_factory_card_names_everyone_from_the_mark_row(client, cohort) -> None:
    """남의 공장 카드 글(factory_scope.elsewhere_info)에 판이 표시 줄을 넘긴다 — "이시영 · 김재단 작업 중" · "재단 완료 · 이시영 · 김재단"."""
    seed = mixed_order(3, f2=(1, 2))
    lee, kim = factory_user("이시영", factory=2, part="cut"), factory_user("김재단", factory=2, part="cut")
    _press(client, lee, seed, 1, "take", "none")
    _press(client, kim, seed, 1, "join", "need")
    for who, action in ((lee, "take"), (kim, "join"), (lee, "done"), (kim, "done")):
        _press(client, who, seed, 2, action, "none" if action == "take" else "need")
    html = _page(client, factory_user("박재단", part="cut"))  # 1공장 재단 — 도면 2 · 3 은 남의 공장 카드
    texts = re.findall(r'data-pp-elsewhere data-order-id="%d" data-key="[^"]+".*?<span data-pp-elsewhere-text>([^<]*)</span>' % seed.id,
                       html, re.S)
    assert texts == ["이시영 · 김재단 작업 중", "재단 완료 · 이시영 · 김재단"]


def test_write_sync_and_refusal_carry_the_viewers_crew(client, cohort) -> None:
    p = _seed(client)
    data = _press(client, p.kim, p.order, 1, "take", "none", seen_me="none")  # 늦은 [작업 시작](Q16)
    assert data["notice"] == "이시영이 먼저 시작했어요." and data["mark"]["crew"]["me"] == "held"
    assert data["mark"]["crew"]["tag"] == "이시영과 같이" and data["mark"]["crew"]["who"] == "이시영 · 김재단"
    login(client, p.park)
    got = client.get(f"/api/production/part-marks?order_ids={p.order.id}&since=2000-01-01T00:00:00").get_json()["data"]["marks"]
    cut1 = next(m for m in got if m["drawing_key"] == p.order.keys[1] and m["part"] == "cut")
    assert (cut1["crew"]["me"], cut1["crew"]["join"]) == ("none", "이시영 · 김재단 외 1")  # 받는 사람(박재단) 몫 · 둘까지 + 외 n
    lost = client.post(ONE, json=_body(p.order, 3, "join", "need"))  # 모두 완료 도면에 [같이 작업] — 409 에도 서버 모습 + crew
    assert lost.status_code == 409 and lost.get_json()["data"]["mark"]["crew"]["done"] == "이시영 · 김재단"


# --------------------------------------------------------------------------- #
# JS — 서버가 그린 판 위에서
# --------------------------------------------------------------------------- #
def test_js_redraws_every_card_like_the_server(client, cohort, tmp_path) -> None:
    p = _seed(client)
    _press(client, p.kim, p.order, 1, "join", "need")
    for who, url in ((p.kim, HOME_NONE), (p.lee, HOME_NONE), (p.park, HOME_NONE), (p.insp, HOME_NONE), (p.lead, CUT_ADMIN),
                     (p.cs, CUT_ADMIN)):
        page = tmp_path / f"board_{who.id}.html"
        page.write_text(_page(client, who, url), encoding="utf-8")
        out = _node(page, {"steps": [{"do": "parity"}]})["out"][0]
        assert out["cards"] == 6 and out["diffs"] == [], (who.name, out["diffs"])


def test_js_join_window_and_late_start_notice(client, cohort, tmp_path) -> None:
    p = _seed(client)
    k = p.order.keys
    page = tmp_path / "kim.html"
    page.write_text(_page(client, p.kim), encoding="utf-8")  # 김재단 화면 — 도면 2 = 이시영 작업 중, 도면 5 = 미정
    join = _body(p.order, 1, "join", "need", seen_me="none", seen_by=p.lee.id)
    took = _body(p.order, 4, "take", "none", seen_me="none")
    _press(client, p.lee, p.order, 4, "take", "none")  # 그사이 이시영이 도면 5 [작업 시작]
    replies = [_post(client, p.kim, join), _post(client, p.kim, took)]
    res = _node(page, {"posts": replies, "steps": [
        {"do": "click", "key": k[1], "act": "join"}, {"do": "run"}, {"do": "card", "key": k[1]},
        {"do": "click", "key": k[4], "act": "take"}, {"do": "run"}, {"do": "card", "key": k[4]}, {"do": "notice", "key": k[4]},
        {"do": "click", "key": k[5], "act": "done"}, {"do": "close"},
        {"do": "click", "key": k[5], "act": "release"}, {"do": "close"}]})
    out, calls = res["out"], res["calls"]
    w1 = out[0]["modal"]  # 창 1
    assert (w1["title"], w1["line"], w1["run"]["text"]) == ("같이 작업할까요?", "이시영 작업 중 → 이시영 · 김재단 작업 중", "같이 작업")
    assert re.fullmatch(r"이시영이 \d\d:\d\d부터 작업 중인 도면이에요\. 같이 작업하면 두 사람 모두 \[재단 완료\]를 눌러야 완료돼요\.", w1["note"])
    assert [c["body"] for c in calls] == [join, took]  # 몸 = 본 내 몫 · 본 담당(옛 호환) · 넘김은 서버가
    c = out[2]["card"]
    assert (c["state"], c["in_need"], c["tag"]) == ("need", "1", "내 작업 · 이시영과 같이") and "is-mine" in c["cls"]
    assert out[3]["modal"]["title"] == "재단 작업을 시작할까요?" and out[3]["modal"]["run"]["text"] == "작업 시작"
    e0 = out[5]["card"]  # E0 — 늦은 사람도 같이 작업 + 서버 글 그대로, 단추 칸이 아니라 그림 칸 아래쪽 안
    assert e0["notice"] == "이시영이 먼저 시작했어요." and e0["notice_in_img"] and e0["why"] is None
    assert e0["tag"] == "내 작업 · 이시영과 같이" and e0["picked_me"] == "1"
    assert out[6] == {"do": "notice", "hidden": True, "stopped": True, "viewer_open": False}  # 누르면 바로 닫힘 · 크게 보기 안 열림
    out = out[1:]
    done = out[6]["modal"]  # 남은 사람이 있는 내 [재단 완료]
    assert done["line"] == "작업 필요 → 재단 1/3 완료 · 김재단"
    assert done["note"] == "이시영 · 최재단이 아직 작업 중이라 이시영 · 최재단이 완료해야 도면이 완료돼요."
    rel = out[8]["modal"]
    assert (rel["title"], rel["line"], rel["run"]["text"]) == ("시작을 취소할까요?", "이시영 · 김재단 외 1 작업 중 → 이시영 · 최재단 작업 중",
                                                               "시작 취소")


def test_js_takeover_picks_who_and_lead_choices(client, cohort, tmp_path) -> None:
    p = _seed(client)
    k = p.order.keys
    _press(client, p.kim, p.order, 1, "join", "need")  # 도면 2 = 이시영 · 김재단(둘 다 아직)
    page = tmp_path / "park.html"
    page.write_text(_page(client, p.park), encoding="utf-8")
    swap = _body(p.order, 1, "takeover", "need", seen_me="none", seen_by=p.lee.id, target_user_id=p.kim.id)
    res = _node(page, {"posts": [_post(client, p.park, swap)], "steps": [
        {"do": "click", "key": k[2], "act": "held"}, {"do": "close"},  # 고를 사람 하나(이시영은 완료) — 고르기 없이 지금 창
        {"do": "click", "key": k[1], "act": "held"}, {"do": "run"}, {"do": "who", "index": 1}, {"do": "run"},
        {"do": "card", "key": k[1]}]})
    out, calls = res["out"], res["calls"]
    one = out[0]["modal"]
    assert (one["title"], one["line"], one["choices"]) == ("담당을 김재단에서 박재단으로 바꿀까요?", "담당 이시영 · 김재단 → 담당 이시영 · 박재단", [])
    w3 = out[2]["modal"]  # 창 3 — 누구와(둘 다 아직 = 둘)
    assert (w3["title"], w3["note"], w3["line"]) == ("누구와 담당을 바꿀까요?", "완료를 누른 사람은 바꿀 수 없어요.", "담당 이시영 · 김재단")
    assert w3["choices_cls"] == "pp-mchoices pp-mchoices--who" and w3["run"]["locked"] is True
    assert [re.sub(r"\d\d:\d\d부터", "HH:MM부터", c["text"]) for c in w3["choices"]] == ["이시영 · HH:MM부터 작업 중", "김재단 · HH:MM부터 작업 중"]
    assert out[3]["sent"] == 0  # 고르기 전 실행 = 안 나감
    picked = out[4]["modal"]
    assert picked["line"] == "담당 이시영 · 김재단 → 담당 이시영 · 박재단" and picked["run"]["locked"] is False
    assert [c["pressed"] for c in picked["choices"]] == ["false", "true"]
    assert [c["body"] for c in calls] == [swap]
    assert out[6]["card"]["tag"] == "내 작업 · 이시영과 같이 · 김재단에서 바뀜" and out[6]["card"]["picked_me"] == "1"

    page = tmp_path / "lead.html"
    page.write_text(_page(client, p.lead, CUT_ADMIN), encoding="utf-8")  # 반장 — 도면 3 = 이시영 완료 · 김재단 작업 중
    remove = _body(p.order, 2, "remove", "need", seen_me="none", seen_by=p.lee.id, target_user_id=p.kim.id)
    res = _node(page, {"posts": [_post(client, p.lead, remove)], "steps": [
        {"do": "click", "key": k[2], "act": "held"}, {"do": "choice", "text": "같이 작업"}, {"do": "close"},
        {"do": "click", "key": k[2], "act": "held"}, {"do": "choice", "text": "김재단 시작 취소"}, {"do": "card", "key": k[2]}]})
    out, calls = res["out"], res["calls"]
    w2 = out[0]["modal"]  # 창 2 — 바꿀 사람이 하나(김재단)면 [담당 바꾸기]는 지금처럼 바로(› 없음) · 반장은 아직 작업자가 아니라 [같이 작업]
    assert (w2["title"], w2["note"], w2["line"], w2["close"]) == (
        "이시영 · 김재단 작업 중", "재단 1/2 완료 — 이시영 완료 · 김재단 작업 중", "", "닫기")  # 제목 한 줄(사장님 2026-11-26) — 한 명만 완료한 줄은 남긴다
    assert [(c["text"], c["choice"], c["target"], c["next"]) for c in w2["choices"]] == [
        ("담당 바꾸기", "takeover", str(p.kim.id), False), ("대신 완료", "check", None, False), ("같이 작업", "join", None, True),
        ("김재단 시작 취소", "remove", str(p.kim.id), False)]
    assert w2["choices_cls"] == "pp-mchoices pp-mchoices--two" and "pp-mgo--join" in w2["choices"][2]["cls"]  # 넷 = 2 × 2
    w1 = out[1]["modal"]  # 반장 [같이 작업] = 파트 계정과 같은 확인 창(Q22)
    assert out[1]["sent"] == 0 and (w1["title"], w1["line"], w1["run"]["text"]) == (
        "같이 작업할까요?", "이시영 · 김재단 작업 중 → 이시영 · 김재단 외 1 작업 중", "같이 작업")
    assert w1["note"].startswith("이시영 · 김재단이 ") and w1["note"].endswith("같이 작업하면 모두 [재단 완료]를 눌러야 완료돼요.")
    assert [c["body"] for c in calls] == [remove] and out[4]["sent"] == 1
    after = out[5]["card"]  # 남은 사람(이시영)이 모두 완료 = 저절로 완료(Q6) — 상태 줄은 한 명 완료 때와 같은 지금 글
    assert after["state"] == "done" and after["act"][0]["text"] == "재단 완료 · 이시영" and out[4]["status"] == "김재단 시작 취소했어요"


def test_js_sync_changes_the_name_line_and_e1_undo_window(client, cohort, tmp_path) -> None:
    p = _seed(client)
    k = p.order.keys
    page = tmp_path / "kim.html"
    page.write_text(_page(client, p.kim), encoding="utf-8")
    _press(client, p.park, p.order, 1, "join", "need")  # 그사이 박재단이 도면 2 에 같이 작업
    login(client, p.kim)
    synced = client.get(f"/api/production/part-marks?order_ids={p.order.id}&since=2000-01-01T00:00:00").get_json()
    res = _node(page, {"sync": True, "gets": [synced], "steps": [{"do": "sync"}, {"do": "card", "key": k[1]},
                                                              {"do": "click", "key": k[2], "act": "release"}, {"do": "close"},
                                                              {"do": "click", "key": k[3], "act": "undo"}]})
    assert res["out"][4]["modal"]["line"] == "재단 완료 → 작업 필요 · 김재단"  # 파트 계정 본인 몫 되돌리기 = 지금 꼴(H 대조군)
    rel = res["out"][2]["modal"]  # 내 [시작 취소] — 남은 이시영이 완료 = 저절로 완료(Q6), 바뀐 뒤는 완료 칸 글
    assert (rel["title"], rel["line"], rel["note"]) == ("시작을 취소할까요?", "이시영 · 김재단 작업 중 → 재단 완료 · 이시영",
                                                        "남은 사람이 모두 완료라 도면이 완료돼요.")
    card = res["out"][1]["card"]
    assert card["act"][0]["cls"] == "pp-two pp-two--join" and card["act"][0]["kids"][0]["text"] == "이시영 · 박재단 작업 중›"

    page = tmp_path / "lee.html"
    page.write_text(_page(client, p.lee), encoding="utf-8")
    res = _node(page, {"steps": [{"do": "click", "key": k[2], "act": "undo"}]})
    undo = res["out"][0]["modal"]
    assert (undo["title"], undo["line"]) == ("작업 필요로 되돌릴까요?", "재단 1/2 완료 → 작업 필요 · 이시영")


def test_lead_window_join_and_swap_follow_who_can_be_picked(client, cohort, tmp_path) -> None:
    """반장 고르기 창(시안 창 2): [같이 작업]은 반장이 아직 작업자가 아니고 도면이 모두 완료가 아닐 때만(Q22) · [담당 바꾸기]는 바꿀 사람이
    하나면 › 없이 바로 실행(지금 동작) · 둘 이상이면 › 고르기 창. 남의 공장 도면 · 모두 완료 도면에는 고르기 창 자체가 없다."""
    p = _seed(client)
    k = p.order.keys
    _press(client, p.kim, p.order, 1, "join", "need")  # 도면 2 = 이시영 · 김재단(둘 다 아직)
    _press(client, p.lead, p.order, 5, "join", "need")  # 도면 6 = 반장도 작업자
    _press(client, p.lead, p.order, 5, "done", "need", seen_me="held")  # 반장 몫만 완료(남은 사람 셋)
    page = tmp_path / "lead.html"
    html = _page(client, p.lead, CUT_ADMIN)
    page.write_text(html, encoding="utf-8")
    assert 'data-pp-act="held"' not in _act(_card(html, k[3]))  # 모두 완료 = 고르기 창 없음(되돌리기 줄)
    swap = _body(p.order, 2, "takeover", "need", seen_me="none", seen_by=p.lee.id, target_user_id=p.kim.id)
    res = _node(page, {"posts": [_post(client, p.lead, swap)], "steps": [
        {"do": "click", "key": k[1], "act": "held"}, {"do": "choice", "text": "담당 바꾸기 ›"}, {"do": "close"},
        {"do": "click", "key": k[5], "act": "held"}, {"do": "close"},
        {"do": "click", "key": k[2], "act": "held"}, {"do": "choice", "text": "담당 바꾸기"},
        {"do": "click", "key": k[3], "act": "undo"}]})
    out, calls = res["out"], res["calls"]
    undo = out[7]["modal"]  # H — 반장 되돌리기 = 완료한 사람 모두 되돌림, 작업하던 사람은 그대로(누른 반장 이름이 아니다)
    assert (undo["title"], undo["line"]) == ("작업 필요로 되돌릴까요?", "재단 완료 → 이시영 · 김재단 작업 중") and "박반장" not in undo["line"]
    two = out[0]["modal"]["choices"]
    assert [(c["text"], c["next"]) for c in two][:3] == [("담당 바꾸기 ›", True), ("대신 완료", False), ("같이 작업", True)]
    assert out[1]["sent"] == 0 and out[1]["modal"]["title"] == "누구와 담당을 바꿀까요?"  # 둘 = 고르기 창
    mine = [c["text"] for c in out[3]["modal"]["choices"]]  # 반장이 이미 작업자(완료) — [같이 작업] 없음
    assert "같이 작업" not in mine and mine[:2] == ["담당 바꾸기 ›", "대신 완료"]
    assert out[6]["sent"] == 1 and [c["body"] for c in calls] == [swap]  # 하나 = 고르기 없이 바로(지금 동작)

    seed = mixed_order(3, f2=(2,))  # 남의 공장(2공장) 도면 = 누름 칸 · 고르기 창 없음(서버 문 그대로)
    two_lee = factory_user("이시영", factory=2, part="cut")
    _press(client, two_lee, seed, 2, "take", "none")
    html = _page(client, p.lead, CUT_ADMIN)
    other = html[html.index(f'data-pp-elsewhere data-order-id="{seed.id}"'):]
    other = other[:other.index("</article>")]
    assert "data-pp-act" not in other and "같이 작업" not in other and "이시영 작업 중" in other


def test_sentences_say_n_people_and_js_adds_no_particles(client, cohort, tmp_path) -> None:
    """이름 줄이 "외 n"으로 끝나는 문장은 "외 n명"(Q20) — [같이 작업] 창 안내 · 내 [재단 완료] 창 안내 · 내 작업 꼬리. 토씨는 서버가 붙인
    완성 조각만 쓴다(JS 가 이름 줄에 토씨를 붙이지 않는다)."""
    p = _seed(client)
    k = p.order.keys
    _press(client, p.park, p.order, 5, "join", "need")  # 도면 6 = 이시영 · 김재단 · 최재단 · 박재단
    oh = make_user("오재단", part="cut")
    page = tmp_path / "oh.html"
    page.write_text(_page(client, oh), encoding="utf-8")
    note = _node(page, {"steps": [{"do": "click", "key": k[5], "act": "join"}]})["out"][0]["modal"]["note"]
    assert re.fullmatch(r"이시영 · 김재단 외 2명이 \d\d:\d\d부터 작업 중인 도면이에요\. 같이 작업하면 모두 \[재단 완료\]를 눌러야 완료돼요\.", note)
    html = _page(client, p.kim)
    assert "내 작업 · 이시영 · 최재단 외 1명과 같이" in _card(html, k[5])
    page.write_text(html, encoding="utf-8")
    res = _node(page, {"steps": [{"do": "click", "key": k[5], "act": "done"}, {"do": "card", "key": k[5]}]})["out"]
    assert res[0]["modal"]["note"] == "이시영 · 최재단 외 1명이 아직 작업 중이라 이시영 · 최재단 외 1명이 완료해야 도면이 완료돼요."
    assert res[1]["card"]["tag"] == "내 작업 · 이시영 · 최재단 외 1명과 같이"
    for name in ("crew", "modal"):
        src = (ROOT / f"static/js/production/foms-production-parts-{name}.js").read_text(encoding="utf-8")
        assert not re.search(r"josa\((cr|crew|who|holder|picked)\b", src), name  # 이름 줄에 JS 토씨 없음
