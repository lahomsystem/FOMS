"""여러 명 같이 작업 M1 ~ M3 검토(d1-review) 고침 — 판결 · 사장님 답(2026-11-25)을 글자 그대로 잰다.

1. 반장 · 관리자 [대신 완료](도면 판 고르기 창 · 반장 칸 [재단 완료]) = 서버에 ``check`` 로 따로 간다 — 반장이 같이 작업자여도 남은 사람
   몫 모두(자기 몫 포함)를 한 번에. 반장 자기 카드의 [재단 완료](``done``)는 자기 몫만. 자기 몫을 완료한 "1/2 완료" 장은 '완료' 칸에
   자기 몫 [되돌리기] 줄(대상 = 본인). 바뀐 기록 '대신' 대상은 대신 완료된 남만("박반장 (김재단 대신) 완료").
2. 멱등(``changed:false``)은 다시 보낸 같은 요청만 — 목록 밖 반장이 그 줄에 마지막으로 쓴 사람이어도 대상 없는 [되돌리기] · 옛 화면의 남의
   장 [시작 취소]는 실제로 일한다.
3. Q23 "두 사람 완료를 모두 되돌리기" — 반장 · 관리자의 대상 없는 [되돌리기]는 자기가 같이 작업자여도 완료한 사람 모두.
4. 되돌리기 경합 글 = 지금 글 "그사이 다른 사람이 바꿨어요. 다시 받아 주세요."(누른 본인 이름 · '시작' 글이 아니다).
6. 바뀐 도면 칸 글은 칸 꼴 "외 n"(문장 꼴 "외 n명" 아님), 전 판 이름은 목록에서.
7. 공장 옮김 막힘 — "재단 1/2 완료" 줄은 '이미 완료한 장' 글(완료 누른 사람만 이름), 시작 취소 부탁은 아직 완료 안 누른 사람만.

되돌리면 실패: [대신 완료]가 자기 몫만 · 다시 누르면 changed:false · 반장 1/2 카드에 되돌리기 줄 없음 · 기록에 반장 이름이 '대신' 대상 ·
마지막으로 쓴 반장의 대상 없는 되돌리기가 멱등 · 반장 자기 몫만 꺼짐 · "…먼저 시작했어요." · "외 1명" 칸 글 · 1/2 완료 줄에 시작 취소 부탁.
대조군: 파트 계정 본인 몫 되돌리기 · 같은 요청 다시 보냄 · 한 명짜리 줄 글은 지금 그대로. 이름은 모두 지어낸 값이다.
"""
from __future__ import annotations

import datetime
import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from db import db_session
from foms.services.orders.drawing_factory import sheet_work, work_block_message, work_people
from foms.services.production import mark_crew as mc
from foms.services.production.part_board import replaced_info
from foms.services.production.part_mark_decide import decide_mark
from foms.services.production.part_mark_rules import MarkSnapshot
from models import SecurityLog
from tests.support.production_factory_seed import HOME_NONE, TABLET, set_cookies
from tests.support.production_part_claim_seed import HISTORY, ONE, code, events, login, make_order, make_user, mark, row

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "tests/support/production_multi_holder_node_checks.js"
CUT_ADMIN = HOME_NONE + "&tab=parts&part=cut"
STALE = "그사이 다른 사람이 바꿨어요. 다시 받아 주세요."
UNDO_ROW = ('<div class="fph-wi pp-act pp-undo-row pp-st-done pp-only-done"><span>재단 1/2 완료</span><button type="button" '
            'class="foms-prod-home__btn pp-undo" data-pp-act="undo">되돌리기</button></div>')


@pytest.fixture
def cohort(monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")


def _ok(client, who, order, action, seen, j=0, **extra) -> dict:
    login(client, who)
    resp = mark(client, order, j, "cut", action, seen, **extra)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["data"]


def _crew(order, j=0) -> list[tuple[str, bool, str | None]]:
    db_session.expire_all()
    return [(m["name"], m["done_at"] is not None, m["done_name"]) for m in (row(order.id, order.keys[j], "cut").holders or [])]


def _last(order) -> dict:
    return events(order.id, "PRODUCTION_PART_MARKED")[-1].payload


def _history_last(client, order) -> dict:
    items = client.get(HISTORY, query_string={"order_id": order.id, "part": "cut"}).get_json()["data"]["items"]
    return [i for i in items if not i["kind"].startswith("step_")][-1]


def _audit(order) -> str:
    db_session.expire_all()
    return db_session.query(SecurityLog).filter_by(action="PRODUCTION_PART_MARKED", target_id=order.id).order_by(
        SecurityLog.id.desc()).first().message


def _people(client, order, *names):
    """이름 차례대로 [작업 시작](늦은 사람은 저절로 같이 작업 — Q16)."""
    out = [make_user(name, part="cut") for name in names]
    for who in out:
        login(client, who)
        assert mark(client, order, 0, "cut", "take", "none").status_code == 200
    return out


# --------------------------------------------------------------------------- #
# 1 — [대신 완료] = check(자기 몫 포함 남은 사람 모두) · 자기 카드 [재단 완료] = 자기 몫만
# --------------------------------------------------------------------------- #
def test_lead_proxy_finish_after_joining_finishes_everyone_left_including_own(client):
    order = make_order(1)
    lee, _kim = _people(client, order, "이시영", "김재단")
    _ok(client, lee, order, "done", "need", seen_me="held")
    boss = make_user("박반장", lead=True)
    _ok(client, boss, order, "join", "need", seen_me="none")  # 반장도 같이 작업자(Q22)
    data = _ok(client, boss, order, "check", "need", seen_me="held")  # 고르기 창 [대신 완료]
    assert (data["changed"], data["mark"]["state"], data["mark"]["done_n"], data["mark"]["holder_n"]) == (True, "done", 3, 3)
    assert _crew(order) == [("이시영", True, "이시영"), ("김재단", True, "박반장"), ("박반장", True, "박반장")]
    assert (_last(order)["override"], _last(order)["holder_name"]) == (True, "김재단")  # '대신' 대상 = 대신 완료된 남만
    item = _history_last(client, order)  # 바뀐 기록 "박반장 (김재단 대신) 완료"(check = '완료' 낱말)
    assert (item["kind"], item["by_name"], item["holder_name"]) == ("check", "박반장", "김재단")
    assert "생산 파트 체크: 재단 재단 1/3 완료 → 재단 완료 (대신 처리) · 공정 재단 켬" in _audit(order)


def test_lead_own_finish_is_own_share_then_proxy_finish_still_works(client):
    order = make_order(1)
    (lee,) = _people(client, order, "이시영")
    boss = make_user("박반장", lead=True)
    _ok(client, boss, order, "join", "need", seen_me="none")
    own = _ok(client, boss, order, "done", "need", seen_me="held")  # 자기 카드 [재단 완료] = 자기 몫만(파트 계정과 같다)
    assert (own["mark"]["state"], own["mark"]["done_n"]) == ("need", 1)
    assert _crew(order) == [("이시영", False, None), ("박반장", True, "박반장")]
    assert own["mark"]["crew"]["me"] == "done"
    again = _ok(client, boss, order, "done", "need", seen_me="held")  # 같은 [재단 완료]를 다시 보냄 = 멱등(대조)
    assert again["changed"] is False
    proxy = _ok(client, boss, order, "check", "need", seen_me="done")  # 그 뒤 [대신 완료] — 옛 판은 여기서 changed:false 막다른 길
    assert (proxy["changed"], proxy["mark"]["state"]) == (True, "done")
    assert _crew(order) == [("이시영", True, "박반장"), ("박반장", True, "박반장")]
    assert _last(order)["holder_name"] == "이시영"
    login(client, lee)  # 파트 계정은 [대신 완료](check)를 못 보낸다 — 지금 문 그대로
    denied = mark(client, order, 0, "cut", "check", "need")
    assert (denied.status_code, code(denied)) == (403, "PART_FORBIDDEN")


def _node(page: Path, want: dict) -> dict:
    node = shutil.which("node")
    assert node, "node must be on PATH for JS checks"
    proc = subprocess.run([node, str(CHECK), str(page), json.dumps(want, ensure_ascii=False)], capture_output=True, text=True,
                          encoding="utf-8", timeout=60, cwd=str(ROOT))
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _card(html: str, key: str) -> str:
    start = html.index(f'data-key="{key}"')
    return html[html.rindex("<article", 0, start):html.index("</article>", start)]


def _page(client, who) -> str:
    login(client, who)
    set_cookies(client, TABLET)
    resp = client.get(CUT_ADMIN)
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


def _post(client, who, body: dict) -> dict:
    login(client, who)
    resp = client.post(ONE, json=body)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def test_lead_half_done_card_has_own_undo_row_and_js_sends_check_and_self_target(client, cohort, tmp_path):
    order = make_order(2)
    (lee,) = _people(client, order, "이시영")
    login(client, lee)
    assert mark(client, order, 1, "cut", "take", "none").status_code == 200  # 대조 — 반장이 안 들어간 장
    boss = make_user("박반장", lead=True)
    _ok(client, boss, order, "join", "need", seen_me="none")
    _ok(client, boss, order, "done", "need", seen_me="held")  # 반장 자기 몫만 완료 = "재단 1/2 완료"
    html = _page(client, boss)
    card = _card(html, order.keys[0])
    assert 'data-in-need="1" data-in-done="1"' in card  # '작업 필요' 칸(고르기 · [대신 완료]) + '완료' 칸(자기 몫 되돌리기)
    assert 'class="fph-wi pp-act pp-st-need pp-not-need pp-not-done pp-held" data-pp-act="held"' in card
    assert "<small>재단 1/2 완료</small>" in card and 'data-pp-act="check">재단 완료</button>' in card and UNDO_ROW in card
    other = _card(html, order.keys[1])  # 대조 — 목록 밖 반장: 되돌리기 줄 없음 · '완료' 칸 아님
    assert 'data-in-done="0"' in other and "pp-undo-row" not in other and 'data-pp-act="check">재단 완료</button>' in other
    assert 'data-pp-count="done">1<' in html
    page = tmp_path / "lead.html"
    page.write_text(html, encoding="utf-8")
    base = {"order_id": order.id, "drawing_key": order.keys[0], "part": "cut", "seen": "need", "seen_by": lee.id}
    undo = {**base, "action": "undo", "seen_me": "done", "target_user_id": boss.id}
    check = {**base, "action": "check", "seen_me": "done"}
    undone = _post(client, boss, undo)  # 진짜 서버 답 — 반장 자기 몫만 꺼짐(이시영은 그대로 작업 중)
    assert undone["data"]["changed"] is True and _crew(order) == [("이시영", False, None), ("박반장", False, None)]
    _ok(client, boss, order, "done", "need", seen_me="held")  # 판 모습(반장 1/2 완료)으로 되돌려 놓고
    finished = _post(client, boss, check)
    res = _node(page, {"steps": [{"do": "parity"}]})["out"][0]
    assert res["diffs"] == [], res["diffs"]  # 서버 칸 = JS 가 다시 그린 칸(새 줄 · check 단추 포함)
    one = _node(page, {"posts": [undone], "steps": [{"do": "click", "key": order.keys[0], "act": "undo"}, {"do": "run"},
                                                    {"do": "card", "key": order.keys[0]}]})
    assert (one["out"][0]["modal"]["title"], one["out"][0]["modal"]["line"]) == ("작업 필요로 되돌릴까요?", "재단 1/2 완료 → 작업 필요 · 박반장")
    assert [c["body"] for c in one["calls"]] == [undo]  # 대상 = 본인(자기 몫만 — 판결 3)
    assert one["out"][2]["card"]["picked_me"] == "1" and one["out"][2]["card"]["in_done"] == "0"
    two = _node(page, {"posts": [finished], "steps": [
        {"do": "click", "key": order.keys[0], "act": "check"}, {"do": "close"},
        {"do": "click", "key": order.keys[0], "act": "held"}, {"do": "choice", "text": "대신 완료"}, {"do": "card", "key": order.keys[0]}]})
    w = two["out"][0]["modal"]  # 반장 칸 [재단 완료] = 같은 확인 창 글(지금 글)
    assert (w["title"], w["line"], w["run"]["text"]) == ("재단 완료로 바꿀까요?", "작업 필요 → 재단 완료 · 박반장", "재단 완료")
    assert [c["body"] for c in two["calls"]] == [check]  # [대신 완료] = check 한 요청
    assert two["out"][3]["status"] == "저장했어요" and two["out"][4]["card"]["state"] == "done"


# --------------------------------------------------------------------------- #
# 2 — 멱등은 같은 요청을 다시 보낸 것만
# --------------------------------------------------------------------------- #
def test_last_writer_lead_outside_the_list_still_undoes_and_releases(client):
    order = make_order(2)
    lee, kim, park = _people(client, order, "이시영", "김재단", "박재단")
    _ok(client, lee, order, "done", "need", seen_me="held")
    boss = make_user("박반장", lead=True)
    _ok(client, boss, order, "remove", "need", target_user_id=park.id)  # 반장이 그 줄에 마지막으로 씀(목록 밖)
    back = _ok(client, boss, order, "undo", "need")  # 대상 없는 [되돌리기] — 옛 판은 changed:false 로 아무 일 안 함
    assert back["changed"] is True and _crew(order) == [("이시영", False, None), ("김재단", False, None)]
    assert _ok(client, boss, order, "undo", "need")["changed"] is False  # 같은 요청 다시 보냄 = 멱등(대조)
    login(client, lee)
    assert mark(client, order, 1, "cut", "take", "none").status_code == 200
    login(client, kim)
    assert mark(client, order, 1, "cut", "take", "none").status_code == 200
    login(client, boss)
    assert mark(client, order, 1, "cut", "remove", "need", target_user_id=kim.id).status_code == 200  # 마지막으로 쓴 반장
    old = mark(client, order, 1, "cut", "release", "need", seen_by=lee.id).get_json()["data"]  # 옛 화면의 남의 장 [시작 취소]
    assert (old["changed"], old["mark"]["state"]) == (True, "none")
    resend = mark(client, order, 1, "cut", "release", "need", seen_by=lee.id).get_json()["data"]
    assert resend["changed"] is False  # 같은 요청 다시 보냄 = 멱등(대조)
    again = mark(client, order, 1, "cut", "remove", "need", target_user_id=kim.id).get_json()["data"]
    assert again["changed"] is False


# --------------------------------------------------------------------------- #
# 3 — Q23 대상 없는 대신 되돌리기 = 완료한 사람 모두(자기 몫 포함) · 자기 몫만 = 대상 본인
# --------------------------------------------------------------------------- #
def test_lead_undo_without_target_reverts_everyone_including_own_share(client):
    order = make_order(1)
    (lee,) = _people(client, order, "이시영")
    boss = make_user("박반장", lead=True)
    _ok(client, boss, order, "join", "need", seen_me="none")
    _ok(client, lee, order, "done", "need", seen_me="held")
    _ok(client, boss, order, "done", "need", seen_me="held")
    back = _ok(client, boss, order, "undo", "done", seen_me="done")  # 모두 완료 카드의 [되돌리기](대상 없음)
    assert (back["mark"]["state"], back["mark"]["done_n"], back["mark"]["holder_n"]) == ("need", 0, 2)
    assert _crew(order) == [("이시영", False, None), ("박반장", False, None)]
    assert (_last(order)["override"], _last(order)["holder_name"]) == (True, "이시영")  # 반장 자신은 '대신' 대상이 아니다
    assert "생산 파트 체크: 재단 재단 완료 → 작업 필요 (대신 처리)" in _audit(order)
    _ok(client, lee, order, "done", "need", seen_me="held")
    _ok(client, boss, order, "done", "need", seen_me="held")
    mine = _ok(client, boss, order, "undo", "done", seen_me="done", target_user_id=boss.id)  # 자기 몫만 = 대상 본인
    assert (mine["mark"]["state"], mine["mark"]["done_n"]) == ("need", 1)
    assert _crew(order) == [("이시영", True, "이시영"), ("박반장", False, None)]
    assert _last(order)["override"] is False and "holder_name" not in _last(order)
    _ok(client, boss, order, "done", "need", seen_me="held")
    own = _ok(client, lee, order, "undo", "done", seen_me="done")  # 대조 — 파트 계정 대상 없음 = 본인 몫만(Q3)
    assert _crew(order) == [("이시영", False, None), ("박반장", True, "박반장")] and own["mark"]["done_n"] == 1


# --------------------------------------------------------------------------- #
# 4 — 되돌리기 경합 글
# --------------------------------------------------------------------------- #
def test_undo_race_says_someone_changed_it_not_who_started(client):
    order = make_order(2)
    lee, kim = _people(client, order, "이시영", "김재단")
    _ok(client, lee, order, "done", "need", seen_me="held")
    _ok(client, kim, order, "done", "need", seen_me="held")
    _ok(client, lee, order, "undo", "done", seen_me="done")  # 이시영이 먼저 되돌림 → 재단 1/2 완료
    login(client, kim)
    late = mark(client, order, 0, "cut", "undo", "done", seen_me="done")  # 김재단의 낡은 화면(모두 완료로 봄)
    assert (late.status_code, code(late), late.get_json()["error"]) == (409, "MARK_CONFLICT", STALE)
    assert late.get_json()["data"]["mark"]["state"] == "need"  # 서버 모습을 실어 화면이 다시 그린다
    _ok(client, lee, order, "done", "need", seen_me="held")  # 그사이 다시 모두 완료
    login(client, lee)
    half = mark(client, order, 0, "cut", "undo", "need", seen_me="done")  # 1/2 완료로 본 낡은 화면
    assert (half.status_code, half.get_json()["error"]) == (409, STALE)
    for who in (lee, kim):  # 대조 — 완료 누름의 경합 글은 지금 그대로(이름 글)
        login(client, who)
        assert mark(client, order, 1, "cut", "take", "none").status_code == 200
    login(client, make_user("박재단", part="cut"))
    stranger = mark(client, order, 1, "cut", "done", "need")
    assert stranger.get_json()["error"] == "이시영 · 김재단이 먼저 시작했어요."


# --------------------------------------------------------------------------- #
# 6 — 바뀐 도면 칸 글(칸 꼴 "외 n") · 전 판 이름은 목록에서
# --------------------------------------------------------------------------- #
def _old_row(rid: int, crew: list[dict], state: str | None = None, **fields):
    at = datetime.datetime(2026, 11, 25, 1, 0)
    base = {"order_id": 1, "drawing_key": f"old-{rid}", "sheet_id": "sh", "part": "cut", "updated_at": at, "id": rid,
            "updated_by_user_id": None, "handed_from_name": None, "handed_at": None, "holders": crew}
    base.update(mc.summarize(crew) or {"state": state, "picked_by_user_id": None, "picked_by_name": None, "picked_at": None,
                                       "done_by_user_id": None, "done_by_name": None, "done_at": None})
    base.update(fields)
    return SimpleNamespace(**base)


def test_changed_drawing_cell_says_n_others_without_myeong_and_names_from_the_list():
    t = mc.to_iso(datetime.datetime(2026, 11, 25, 0, 0))
    three = [mc.member(1, "이시영", t), mc.member(2, "김재단", t), mc.member(3, "박재단", t)]
    info = replaced_info(1, {"key": "new", "sheet_id": "sh"}, {"new"}, {(1, "sh"): [_old_row(5, three)]}, "cut")
    assert info["label"] == "바뀐 도면 · 전 판 재단 중(이시영 · 김재단 외 1)"  # 칸 글 — "외 1명" 아님
    assert info["prev"]["cut"] == {"state": "need", "name": "이시영 · 김재단 외 1"}  # 첫 사람 한 명이 아니라 목록
    two_done = [mc.member(1, "이시영", t, done_at=t, done_uid=1, done_name="이시영"),
                mc.member(2, "김재단", t, done_at=t, done_uid=9, done_name="박반장")]
    done = replaced_info(1, {"key": "new", "sheet_id": "sh"}, {"new"}, {(1, "sh"): [_old_row(6, two_done)]}, "cut")
    assert done["label"] == "바뀐 도면 · 전 판 재단 완료(이시영 · 박반장)" and done["prev"]["cut"]["name"] == "이시영 · 박반장"
    one = [mc.member(1, "김재단", t)]  # 대조 — 한 명짜리 줄은 지금 글 그대로
    single = replaced_info(1, {"key": "new", "sheet_id": "sh"}, {"new"}, {(1, "sh"): [_old_row(7, one)]}, "cut")
    assert single["label"] == "바뀐 도면 · 전 판 재단 중(김재단)" and single["prev"]["cut"]["name"] == "김재단"


# --------------------------------------------------------------------------- #
# 7 — 공장 옮김 막힘: 1/2 완료 줄 = '이미 완료한 장' · 시작 취소 부탁은 아직인 사람만
# --------------------------------------------------------------------------- #
def test_half_done_sheet_is_already_done_and_release_ask_names_only_pending():
    t = mc.to_iso(datetime.datetime(2026, 11, 25, 0, 0))
    key = "k/d0.png"
    half = [mc.member(1, "이시영", t, done_at=t, done_uid=1, done_name="이시영"), mc.member(2, "김재단", t)]
    rows = [_old_row(1, half, drawing_key=key, part="cut")]
    work = sheet_work(key, rows)
    assert work == {"kind": "done", "part": "cut", "name": "이시영"}  # 완료를 누른 사람만
    assert work_block_message(work, from_factory=1, to_factory=2, people=work_people(key, rows, work)) == (
        "2공장으로 옮길 수 없어요 — 1공장에서 이시영이 재단을 이미 완료한 장이에요. 이미 완료한 장은 옮기지 않아요.")
    # 판단 근거 — 남은 김재단이 시작 취소하면 남은 사람이 모두 완료라 저절로 완료(Q6): 시작 취소 부탁으로는 옮길 수 없다
    left = decide_mark(MarkSnapshot.from_row(rows[0]), action="release", seen="need", actor_id=2, admin=False, label="재단")
    assert left.target == "DONE"
    held = [mc.member(1, "김민준", t), mc.member(2, "박엣지", t), mc.member(3, "최엣지", t)]
    rows = [_old_row(2, held, drawing_key=key, part="edge")]
    work = sheet_work(key, rows)
    assert work == {"kind": "held", "part": "edge", "name": "김민준 · 박엣지 외 1"}
    assert work_block_message(work, from_factory=1, to_factory=2, people=work_people(key, rows, work)) == (
        "2공장으로 옮길 수 없어요 — 1공장 김민준 · 박엣지 외 1명이 엣지 작업 중이에요. "
        "김민준 · 박엣지 외 1명에게 시작 취소를 부탁한 뒤 다시 해 주세요.")
