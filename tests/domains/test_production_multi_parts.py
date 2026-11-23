"""여러 파트(P2) — 계정 파트 0 ~ 4개 · 대신(파트 없는 생산팀) · 판 머리 고르기 · 다른 파트 줄 '내 담당'.

설계서 ``docs/specs/2026-11-23-production-self-claim-and-factory2_SPEC.md`` §4-12 · §5 권한 표 · §6-1 · §8-1 '여러 파트(P2)' · §12.
이름은 모두 지어낸 값이다.

되돌리면 실패: 파트 둘 중 둘째 파트 쓰기 403 · 내 파트 밖 파트 쓰기 200 · 대신을 읽기 전용으로(카드 쓰기 403 · 창 없음) · 대신의 공정 칸
잠금 · 고르기를 파트 하나인 계정에도 그림 · 주소 ``part`` 가 내 파트 밖인데 그 판 · '내 담당'을 파트 하나인 계정 · 관리자에게도 ·
받아 오기 낱말이 판과 다름 · 새 칸이 옛 칸과 어긋날 때 새 칸만 믿음 · 쿼리 수 늘림.
대조군: 파트 하나인 계정의 판 · 제목 · 주소는 지금 그대로 · 읽기 전용(CS · 도면 · 다른 팀 매니저)은 그대로 못 씀 · 관리자 감사 꼬리 그대로.
"""
from __future__ import annotations

import datetime
import re
from itertools import count
from types import SimpleNamespace

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.datetime_kst import get_today_kst, now_utc_naive
from foms.services.production.part_access import (
    can_override_marks,
    own_parts,
    part_view_mode,
    steps_locked_for,
    writable_parts,
)
from foms.services.production.part_constants import (
    PRODUCTION_PART_KEYS,
    account_production_part,
    account_production_parts,
    normalize_production_parts,
    production_part_columns,
    production_parts_label,
)
from models import ProductionPartMark, SecurityLog, User
from tests.domains.test_production_part_board import _board, _files, _mark, _order, _today
from tests.domains.test_production_selfclaim_query_count import MEASURED, _measure
from tests.support.production_part_claim_seed import Person, check_step, code, login, make_order, mark, row

HOME = "/erp/production/home"
_seq = count(1)


@pytest.fixture
def cohort(monkeypatch):
    """모바일 v2 셸 코호트(모두) — 태블릿 표면의 서버 문 하나."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")


@pytest.fixture
def policy_on(app):
    """이 시험 동안만 정책 가드(매니페스트)를 켠다 — 대신도 앞문(팀 PRODUCTION)을 지나야 한다."""
    sentinel = object()
    prev = app.config.get("AUTH_POLICY_ENABLED", sentinel)
    app.config["AUTH_POLICY_ENABLED"] = True
    yield
    if prev is sentinel:
        app.config.pop("AUTH_POLICY_ENABLED", None)
    else:
        app.config["AUTH_POLICY_ENABLED"] = prev


def _db_user(name: str, *, parts: list[str] | None = None, team: str | None = "PRODUCTION", role: str = "STAFF") -> User:
    """새 칸(목록) + 옛 칸(첫 파트)을 관리자 저장처럼 같이 적은 가짜 계정(같은 두 함수를 거친다)."""
    stored, first = production_part_columns(team, normalize_production_parts(parts))
    user = User(username=f"mp_{next(_seq)}", password=generate_password_hash("x"), role=role, team=team, name=name,
                is_active=True, production_parts=stored, production_part=first)
    db_session.add(user)
    db_session.commit()
    return user


def _user(name: str, **kw) -> Person:
    user = _db_user(name, **kw)
    return Person(user.id, user.username, user.role, name)


def _ns(*, team: str | None = "PRODUCTION", role: str = "STAFF", parts=None, legacy=None) -> SimpleNamespace:
    return SimpleNamespace(team=team, role=role, production_parts=parts, production_part=legacy, is_active=True,
                           partner_org_id=None, id=7)


# --------------------------------------------------------------------------- #
# 1. 값 한 곳 — 정규화 · 두 칸 · 읽기
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(("raw", "expected"), [
    (["edge", "cut"], ["cut", "edge"]), (["cut", "cut", " Edge "], ["cut", "edge"]), ([], None), (None, None), ("", None),
    ("inspect", ["inspect"]), (["", "assemble"], ["assemble"]),
    (("inspect", "assemble", "edge", "cut"), ["cut", "edge", "assemble", "inspect"]),
])
def test_normalize_production_parts_orders_dedupes_and_empties_to_none(raw, expected):
    assert normalize_production_parts(raw) == expected


@pytest.mark.parametrize("raw", [["cut", "paint"], ["재단"], "cut;drop"])
def test_normalize_production_parts_rejects_unknown(raw):
    with pytest.raises(ValueError):
        normalize_production_parts(raw)


def test_columns_write_list_and_first_part_and_clear_outside_production():
    assert production_part_columns("PRODUCTION", ["edge", "inspect"]) == (["edge", "inspect"], "edge")
    assert production_part_columns(" production ", ["cut"]) == (["cut"], "cut")
    assert production_part_columns("CS", ["cut"]) == (None, None)
    assert production_part_columns("PRODUCTION", None) == (None, None)
    assert production_parts_label(["edge", "cut"]) == "재단 · 엣지" and production_parts_label(None) is None


def test_account_parts_read_new_column_and_follow_old_column_when_they_disagree():
    assert account_production_parts(_ns(parts=["cut", "edge"], legacy="cut")) == ("cut", "edge")
    assert account_production_parts(_ns(parts=["edge", "cut"], legacy="cut")) == ("cut", "edge")  # 정의 순서
    assert account_production_parts(_ns(parts=None, legacy="edge")) == ("edge",)  # 마이그레이션 전 · 옛 판이 만든 행
    assert account_production_parts(_ns(parts=["cut", "edge"], legacy="assemble")) == ("assemble",)  # 옛 판이 나중에 고침
    assert account_production_parts(_ns(parts=["cut", "edge"], legacy=None)) == ()  # 옛 판이 '없음'으로 고침
    assert account_production_parts(_ns(team="CS", parts=["cut"], legacy="cut")) == ()  # 생산팀이 아니면 없다
    assert account_production_parts(None) == () and account_production_part(_ns(parts=["edge", "inspect"], legacy="edge")) == "edge"


# --------------------------------------------------------------------------- #
# 2. 보기 모드 다섯 · 권한 표(§5) — 한 곳(part_access)
# --------------------------------------------------------------------------- #
ALL = PRODUCTION_PART_KEYS


@pytest.mark.parametrize(("who", "mode", "parts", "override", "locked"), [
    (dict(parts=["cut"], legacy="cut"), "part", ("cut",), False, True),
    (dict(parts=["cut", "edge"], legacy="cut"), "part", ("cut", "edge"), False, True),
    (dict(parts=list(ALL), legacy="cut"), "part", ALL, False, True),
    (dict(), "sub", ALL, True, False),  # 파트 없는 생산팀 STAFF = 대신(예전 읽기 전용)
    (dict(role="MANAGER"), "sub", ALL, True, False),
    (dict(role="ADMIN", team="CS"), "admin", ALL, True, False),
    (dict(role="ADMIN", parts=["cut"], legacy="cut"), "admin", ALL, True, False),  # 관리자는 계정 파트를 무시(D55)
    (dict(team="CS"), "readonly", (), False, False),
    (dict(team="DRAWING"), "readonly", (), False, False),
    (dict(team="CS", role="MANAGER"), "readonly", (), False, False),  # 다른 팀 매니저 = 읽기 전용
    (dict(role="VIEWER", parts=["cut"], legacy="cut"), "readonly", (), False, False),
    (dict(team=None), "none", (), False, False),
])
def test_view_modes_and_write_rules_follow_the_permission_table(who, mode, parts, override, locked):
    person = _ns(**who)
    assert part_view_mode(person) == mode
    assert writable_parts(person) == parts and can_override_marks(person) is override and steps_locked_for(person) is locked
    assert own_parts(person) == (parts if mode == "part" else ())


# --------------------------------------------------------------------------- #
# 3. 쓰기 API — 파트 둘인 계정 · 대신
# --------------------------------------------------------------------------- #
def test_two_part_account_writes_both_parts_but_not_a_third_and_steps_stay_locked(client):
    order = make_order(2)
    login(client, _user("김두파", parts=["cut", "edge"]))
    assert mark(client, order, 0, "cut", "take", "none").status_code == 200
    assert mark(client, order, 0, "edge", "take", "none").status_code == 200
    bad = mark(client, order, 0, "assemble", "take", "none")
    assert bad.status_code == 403 and code(bad) == "PART_FORBIDDEN" and bad.get_json()["error"] == "자기 파트만 체크할 수 있어요."
    assert row(order.id, order.keys[0], "assemble") is None
    locked = check_step(client, make_order(1).id, "cut", True)  # 공정 칸 직접 쓰기 = 카드로만(파트 계정)
    assert locked.status_code == 403 and code(locked) == "PART_ACCOUNT_USE_CARDS"


def test_two_part_account_takes_over_on_edge_but_not_on_assemble_or_releases_others(client):
    """사진 5 와 같은 경우 — 엣지 판에서 남이 맡은 장 [담당 바꾸기] = 됨, 조립 장은 안 됨(내 파트 밖), 남의 장 맡기 취소는 안 됨(§5)."""
    order = make_order(2)
    edge, asm = _user("박엣지", parts=["edge"]), _user("이조립", parts=["assemble"])
    login(client, edge)
    assert mark(client, order, 0, "edge", "take", "none").status_code == 200
    assert mark(client, order, 1, "edge", "take", "none").status_code == 200
    login(client, asm)
    assert mark(client, order, 0, "assemble", "take", "none").status_code == 200
    me = _user("김두파", parts=["cut", "edge"])
    login(client, me)
    ok = mark(client, order, 0, "edge", "takeover", "need", seen_by=edge.id)
    assert ok.status_code == 200, ok.get_json()
    taken = row(order.id, order.keys[0], "edge")
    assert (taken.picked_by_user_id, taken.picked_by_name, taken.handed_from_name) == (me.id, "김두파", "박엣지")
    no = mark(client, order, 0, "assemble", "takeover", "need", seen_by=asm.id)
    assert no.status_code == 403 and code(no) == "PART_FORBIDDEN"
    assert row(order.id, order.keys[0], "assemble").picked_by_name == "이조립"
    release = mark(client, order, 1, "edge", "release", "need")
    assert release.status_code == 403 and code(release) == "RELEASE_NOT_HOLDER"


@pytest.mark.parametrize("role", ["STAFF", "MANAGER"])
def test_sub_mode_writes_any_part_finishes_and_releases_others_and_hand_checks(client, policy_on, role):
    order = make_order(2)
    holder = _user("박엣지", parts=["edge"])
    login(client, holder)
    assert mark(client, order, 0, "edge", "take", "none").status_code == 200
    assert mark(client, order, 1, "edge", "take", "none").status_code == 200
    login(client, _user("박반장", role=role))  # 파트 없는 생산팀 = 대신
    assert mark(client, order, 1, "assemble", "take", "none").status_code == 200  # 아무 파트나(앞문도 지남)
    done = mark(client, order, 0, "edge", "done", "need")  # 남이 맡은 장 대신 완료
    assert done.status_code == 200, done.get_json()
    finished = row(order.id, order.keys[0], "edge")
    assert (finished.state, finished.picked_by_name, finished.done_by_name) == ("DONE", "박엣지", "박반장")
    assert mark(client, order, 1, "edge", "release", "need").status_code == 200  # 남의 장 맡기 취소
    assert row(order.id, order.keys[1], "edge").state == "NONE"
    db_session.expire_all()
    logs = [r.message for r in db_session.query(SecurityLog).filter(SecurityLog.message.like("%대신 처리%"))]
    assert len(logs) == 2 and not any("관리자 덮어쓰기" in m for m in logs), logs
    assert check_step(client, make_order(1).id, "cut", True).status_code == 200  # 공정 칸 손 체크(잠금 없음)


def test_readonly_staff_still_cannot_write(client):
    order = make_order(1)
    for who in (_user("도면사람", team="DRAWING"), _user("상담매니저", team="CS", role="MANAGER")):
        login(client, who)
        resp = mark(client, order, 0, "cut", "take", "none")
        assert resp.status_code == 403 and code(resp) == "PART_REQUIRED"


# --------------------------------------------------------------------------- #
# 4. 판 — 고르기 · 주소 part · 다른 파트 줄 '내 담당'
# --------------------------------------------------------------------------- #
def test_board_picks_only_my_parts_and_falls_back_to_my_first(app):
    me = _db_user("김두파", parts=["cut", "edge"])
    _order("한빛", _files("mp", 2))
    board = _board(me)
    assert (board["mode"], board["part"], board["pick"], board["url_part"]) == ("part", "cut", True, "cut")
    assert [p["key"] for p in board["parts"]] == ["cut", "edge"]
    edge = _board(me, part="edge")
    assert (edge["part"], edge["writable"], edge["url_part"]) == ("edge", True, "edge")
    assert _board(me, part="assemble")["part"] == "cut" and _board(me, part="paint")["part"] == "cut"  # 내 파트 밖 → 첫 파트
    assert _board(_db_user("이조검", parts=["inspect", "assemble"]))["part"] == "assemble"
    single = _board(_db_user("박재단", parts=["cut"]), part="edge")  # 대조군: 파트 하나 = 지금 그대로
    assert (single["part"], single["pick"], single["url_part"]) == ("cut", False, None)
    sub = _board(_db_user("박반장"), part="edge")
    assert (sub["mode"], sub["part"], sub["writable"], sub["pick"], sub["url_part"]) == ("sub", "edge", True, False, "edge")
    assert len(sub["parts"]) == 4 and _today(sub)["cards"] and not _today(sub)["cards"][0]["badge"]


def test_other_part_line_says_mine_only_for_my_second_part(app):
    me = _db_user("김두파", parts=["cut", "edge"])
    single = _db_user("박재단", parts=["cut"])
    admin = _db_user("관리자", team="CS", role="ADMIN")
    order = _order("한빛", _files("mo", 2))
    _mark(order, "mo/d0.png", "edge", "NEED", picked=me)
    _mark(order, "mo/d1.png", "edge", "NEED", picked=single)

    def words(user):
        return {c["key"]: {o["part"]: (o["word"], o["tone"]) for o in c["others"]} for c in _today(_board(user))["cards"]}

    mine = words(me)
    assert mine["mo/d0.png"]["edge"] == ("내 담당", "mine") and mine["mo/d1.png"]["edge"] == ("중", "need")
    for viewer in (single, admin):  # 대조군: 그 파트가 내 파트가 아니면 지금 낱말(단 하나 파트 계정은 자기가 맡았어도)
        got = words(viewer)
        assert got["mo/d0.png"]["edge"] == ("중", "need") and got["mo/d1.png"]["edge"] == ("중", "need")


def test_sync_words_follow_the_viewer_like_the_board(client):
    order = make_order(1)
    me = _user("김두파", parts=["cut", "edge"])
    login(client, me)
    assert mark(client, order, 0, "edge", "take", "none").status_code == 200
    since = (now_utc_naive() - datetime.timedelta(days=3)).isoformat()
    url = f"/api/production/part-marks?order_ids={order.id}&since={since}"
    edge = next(m for m in client.get(url).get_json()["data"]["marks"] if m["part"] == "edge")
    assert (edge["word"], edge["tone"]) == ("내 담당", "mine")
    login(client, _user("박재단", parts=["cut"]))
    edge = next(m for m in client.get(url).get_json()["data"]["marks"] if m["part"] == "edge")
    assert (edge["word"], edge["tone"]) == ("중", "need")


# --------------------------------------------------------------------------- #
# 5. 화면 — 판 머리 고르기 · 제목 · 같은 날 주소 · 대신 '도면 카드'
# --------------------------------------------------------------------------- #
def _get(client, url: str) -> str:
    resp = client.get(url)
    assert resp.status_code == 200, resp.status_code
    return resp.get_data(as_text=True)


def _tablet(client, who: Person) -> None:
    login(client, who)
    client.set_cookie("foms_ptr", "coarse", domain="localhost")


def _pane(html: str) -> str:
    key = get_today_kst().isoformat()
    return html.split(f'data-foms-home-daypane="{key}"')[1].split("data-foms-home-daypane=")[0]


def _day_hrefs(html: str) -> list[str]:
    return re.findall(r'href="([^"]*)" data-foms-erp-no-shell="1" data-foms-home-daybtn', html)


def test_two_part_account_head_picks_parts_keeps_day_and_titles_both(client, cohort):
    _order("한빛", _files("ms", 2))
    _tablet(client, _user("김두파", parts=["cut", "edge"]))
    html = _get(client, HOME)
    pane = _pane(html)
    nav = pane.split('<nav class="pp-picks" aria-label="파트 고르기">', 1)[1].split("</nav>", 1)[0]
    assert re.fullmatch(r'<a class="pp-pick is-on" href="[^"]*part=cut[^"]*" data-pp-pick="cut" aria-current="page">재단</a>'
                        r'<a class="pp-pick" href="[^"]*part=edge[^"]*" data-pp-pick="edge">엣지</a>', nav)
    assert all(f"day={get_today_kst().isoformat()}" in href for href in re.findall(r'href="([^"]*)"', nav))  # 같은 날
    assert '<h1 class="foms-prod-home__title">재단 · 엣지 <span class="foms-prod-home__me">김두파</span></h1>' in html
    assert _day_hrefs(html) and all("part=cut" in href for href in _day_hrefs(html))  # 날을 바꿔도 고른 파트
    assert 'data-pp-act="take">내가 자름<' in pane and 'class="pp-parts"' not in pane  # 관리자 네 파트 고르기는 없다
    edge = _pane(_get(client, HOME + "?part=edge"))
    assert 'data-pp-pick="edge" aria-current="page">엣지</a>' in edge and 'data-pp-act="take">내가 엣지<' in edge
    assert "pp-bulk" not in edge and "시공 1건 · 도면 나온 1집" in edge  # 엣지 판 머리 글은 지금 그대로
    assert 'data-pp-pick="cut" aria-current="page">' in _pane(_get(client, HOME + "?part=inspect"))  # 내 파트 밖 → 첫 파트


def test_single_part_account_head_and_links_stay_as_now(client, cohort):
    _order("한빛", _files("mt", 2))
    _tablet(client, _user("박재단", parts=["cut"]))
    html = _get(client, HOME + "?part=edge")
    assert "pp-picks" not in html and "data-pp-pick" not in html
    assert '<h1 class="foms-prod-home__title">재단 <span class="foms-prod-home__me">박재단</span></h1>' in html
    assert _day_hrefs(html) and not any("part=" in href for href in _day_hrefs(html))
    assert 'data-pp-act="take">내가 자름<' in _pane(html)


def test_sub_mode_sees_cards_tab_with_buttons_like_admin(client, cohort):
    order = _order("한빛", _files("mu", 2))
    holder = _db_user("박재단", parts=["cut"])
    _mark(order, "mu/d0.png", "cut", "NEED", picked=holder)
    _tablet(client, _user("박반장"))
    date = _get(client, HOME)
    assert "data-foms-home-partslink" in date and "data-pp-card" not in date  # 날짜 탭은 지금 그대로(줄 목록 + [도면 카드로 보기])
    html = _get(client, HOME + "?tab=parts&part=cut")
    pane = _pane(html)
    assert html.count('id="foms-part-confirm-modal"') == 1 and '&#34;mode&#34;: &#34;sub&#34;' in html
    assert 'class="pp-parts"' in pane and 'data-pp-act="take"' in pane and "박재단 맡음" not in pane
    assert "작업 필요 · 박재단" in pane and 'data-pp-act="done"' in pane  # 남이 맡은 장 = 관리자와 같은 칸 · [재단 완료]
    assert "<h1 class=\"foms-prod-home__title\">생산</h1>" in html


def _old_claim(order, key: str, part: str, me: User) -> None:
    """밤 넘긴 내 담당 한 장(맡은 때 = 이틀 전)."""
    old = now_utc_naive() - datetime.timedelta(days=2)
    db_session.add(ProductionPartMark(order_id=order.id, drawing_key=key, part=part, state="NEED", picked_by_user_id=me.id,
                                      picked_by_name=me.name, picked_at=old, updated_by_user_id=me.id, updated_at=old))
    db_session.commit()


def test_morning_chip_counts_all_my_parts_and_each_line_goes_to_its_part(client, cohort):
    """재단을 보는 중인데 엣지에 밤 넘긴 담당이 있어도 칩이 뜬다(칩 숫자 = 내 파트 전부). 줄마다 파트 이름 · [보기]는 그 파트 판."""
    me = _db_user("김두파", parts=["cut", "edge"])
    order = _order("아침집", _files("mm", 3))
    _old_claim(order, "mm/d0.png", "edge", me)
    _old_claim(order, "mm/d1.png", "edge", me)
    _old_claim(order, "mm/d2.png", "cut", me)
    _tablet(client, Person(me.id, me.username, me.role, me.name))
    html = _get(client, HOME)
    assert 'aria-controls="pp-mpop">어제부터 내 담당 3장 <span aria-hidden="true">›</span>' in html
    lines = re.findall(r'<p>(시공 [^<]*?) (\d)장 <a href="([^"]*)" aria-label="([^"]*)">보기</a></p>', html)
    day = get_today_kst()
    assert [(t.rsplit(" ", 1)[1], n) for t, n, _h, _a in lines] == [("재단", "1"), ("엣지", "2")]
    assert "part=cut" in lines[0][2] and "part=edge" in lines[1][2] and all(f"day={day.isoformat()}" in h for _t, _n, h, _a in lines)
    assert lines[1][3].endswith(" 엣지 보기")
    other = _db_user("이엣재", parts=["cut", "edge"])
    _old_claim(order, "mm/d1.png", "cut", other)  # 엣지를 보는 중에도 재단에 밤 넘긴 담당이 있으면 칩이 뜨고 [보기]는 재단 판
    _tablet(client, Person(other.id, other.username, other.role, other.name))
    html = _get(client, HOME + "?part=edge")
    assert 'aria-controls="pp-mpop">어제부터 내 담당 1장' in html
    only = re.findall(r'<p>(시공 [^<]*?) 1장 <a href="([^"]*)"', html)
    assert len(only) == 1 and only[0][0].endswith(" 재단") and "part=cut" in only[0][1]


def _nav(html: str) -> dict[str, str]:
    box = html.split('<nav class="foms-prod-home__nav" aria-label="화면">', 1)[1].split("</nav>", 1)[0]
    return {label: href.replace("&amp;", "&") for href, label in re.findall(r'href="([^"]*)"[^>]*>(날짜|바뀐 것|찾기)', box)}


def test_top_tabs_keep_the_chosen_part_for_two_part_accounts_only(client, cohort):
    _order("한빛", _files("mn", 2))
    _tablet(client, _user("김두파", parts=["cut", "edge"]))
    nav = _nav(_get(client, HOME + "?part=edge"))
    assert all("part=edge" in nav[k] for k in ("날짜", "바뀐 것", "찾기")), nav
    for tab in ("all", "changes"):  # '찾기' · '바뀐 것'에 갔다가 [날짜]로 돌아와도 고른 파트
        back = _nav(_get(client, HOME + f"?tab={tab}&part=edge"))["날짜"]
        assert "part=edge" in back, (tab, back)
        assert 'data-pp-pick="edge" aria-current="page">엣지</a>' in _pane(_get(client, back))
    assert "part=" not in _nav(_get(client, HOME + "?tab=all&part=assemble"))["날짜"]  # 내 파트 밖은 안 실음
    for who in (_user("박재단", parts=["cut"]), _user("박반장"), _user("관리자", team="CS", role="ADMIN")):
        _tablet(client, who)  # 대조군: 파트 하나 · 파트 없는 생산팀 · 관리자는 위 탭 주소 그대로
        for url in (HOME + "?part=edge", HOME + "?tab=all&part=edge", HOME + "?tab=changes&part=edge"):
            assert not any("part=" in href for href in _nav(_get(client, url)).values()), (who, url)


# --------------------------------------------------------------------------- #
# 6. 쿼리 수 — 계정 파트는 이미 읽은 사용자 행에서(0)
# --------------------------------------------------------------------------- #
def test_query_counts_stay_for_two_part_date_tab_and_sub_cards_tab(client, cohort, monkeypatch):
    me = _user("김두파", parts=["cut", "edge"])
    _tablet(client, me)
    _small, big, html = _measure(client, HOME, me, (3000, 3100))
    assert "data-pp-pick" in html and big == MEASURED["date_part"], big  # 파트 하나인 계정과 같다(11)
    boss = _user("박반장")
    _tablet(client, boss)
    url = HOME + "?tab=parts&part=edge"
    _small, sub, html = _measure(client, url, boss, (3200, 3300))
    assert "data-pp-card " in html and 'data-pp-act="take"' in html
    # 대조: 같은 사람을 예전 보기 모드(읽기 전용)로 — 대신이 더한 쿼리는 0. 생산팀 사람은 관리자보다 늘 하나 더 읽는다(설정 한 줄 —
    # P2 와 무관, 관리자 '도면 카드' 실측 MEASURED["parts_tab"] = 9 · 생산팀 10)
    monkeypatch.setattr("foms.services.production.part_access.can_write_production", lambda user: False)
    _small, readonly, html = _measure(client, url, boss, (3400, 3500))
    assert 'data-pp-act="' not in html and sub == readonly == MEASURED["parts_tab"] + 1, (sub, readonly)
