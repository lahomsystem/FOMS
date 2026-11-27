"""여러 명이 같이 작업 M3 — 도면 판 밖의 화면(설계서 2026-11-25 multi-holder §10 M3 · §11 M2 · M3 · §8-2 24 · 37 ~ 45 · §8-3 지휘 판결).

* PC 도면별 창(``GET /api/production/part-sheet``): 줄 글은 서버가 사람마다 한 조각씩("작업 시작 이시영 · 11/25 08:10" · "완료 이시영 ·
  11/25 11:30", K6) · 상태 칸 "재단 1/2 완료" + 작은 글 "김재단 작업 중" · 모두 완료 "재단 완료"(K4) · 아무도 안 시작 "담당 미정"(K2 그대로).
* 창 JS(Node — 서버가 그린 진짜 PC 화면 + 진짜 API 응답): 단추 [완료 처리] · [완료 취소] · [모두 완료 처리] · [모두 완료 취소](K3),
  [완료 처리] = POST 한 번(action ``check`` — 판결 2, 옛 맡기 → 완료 두 요청 없음), [모두 완료 처리] 확인 창 글은 그대로("…작업 완료로
  처리할까요?" · [작업 완료]). JS 가 보낸 몸을 진짜 서버에 다시 보내 — 남이 작업 중인 장 = 남은 사람 몫 대신 완료(반장은 '작업 시작'
  줄에 안 섬) · 빈 장 = 반장 시작 + 완료 · [완료 취소] 뒤 나 하나면 시작 취소까지.
* 바뀐 기록 낱말(작업 시트 · PC 창 같은 renderLog — §8-2 24 · §8-1): "작업 시작" · "같이 작업" · "김재단 시작 취소 (박반장)" · "완료".
* 날짜 줄 · PC 첫 화면 줄 공정 칸 아래 = 한 명 + "외 n"(같이 작업하는 사람도 셈 — part_holders 그대로), 작업 시트 칸 옆 글은 도면 수 그대로.
* '끝' → '완료'(K4 · 지휘 판결): 단계 큰 글자 "검수 완료" = 상수 하나(견주는 다섯 곳), '내 공정' [재단 완료] · PC 마우스 글 "재단 완료 · …".
  문장 속 '끝'("끝내면 다음은" · "끝냈어요") · 이벤트 이름 "검수 끝 전제"는 그대로(음성 대조).

되돌리면 실패: 줄 글을 한 명짜리 칸으로 그림 · "재단 끝" · [작업] 단추 · PC 가 take → done 두 요청 · 대신 완료가 반장을 '작업 시작'
줄에 넣음 · 다섯 곳 중 한 곳이라도 옛 글자로 견줌. 이름은 모두 지어낸 값이다.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path

from foms.services.order_event_display import translate_admin_override_gates
from foms.services.production.late_rule import late_spot
from foms.services.production.steps import PRODUCTION_FINISHED_STAGE
from foms.services.production_home_days import _row_bar_kind
from foms.services.production_home_read_model import production_home_stage, production_home_step_queues
from tests.domains.test_production_pc_sheet import API, HOME, PC, TABLET, _edit, _login, _order, cohort  # noqa: F401
from tests.support.production_part_claim_seed import HISTORY, ONE, make_user

ROOT = Path(__file__).resolve().parents[2]
NODE_CHECK = ROOT / "tests/support/production_pc_sheet_node_checks.js"
STAMP = r"\d{1,2}/\d{1,2} \d{2}:\d{2}"


def _key(name: str, j: int) -> str:
    return f"orders/pcs/{name}_{j}.png"


def _press(client, who, oid: int, key: str, action: str, seen: str, part: str = "cut", **extra) -> dict:
    _login(client, who)
    resp = client.post(ONE, json={"order_id": oid, "drawing_key": key, "part": part, "action": action, "seen": seen, **extra})
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["data"]


def _like(lines: list[str], heads: list[str]) -> bool:
    """줄 글이 ``heads``("작업 시작 이시영" …) 차례와 같고 모두 " · M/D HH:MM" 로 끝나는지."""
    return len(lines) == len(heads) and all(re.fullmatch(re.escape(h) + " · " + STAMP, line) for line, h in zip(lines, heads))


def _seed():
    """도면 5장 재단(엣지는 손 체크) — 1 둘이 모두 완료 · 2 이시영만 완료(1/2) · 3 이시영 작업 중(김재단은 반장이 시작 취소) ·
    4 아무도 안 시작(김재단이 시작했다가 시작 취소) · 5 반장이 PC [완료 처리](빈 장 = 시작 + 완료)."""
    order = _order("가람", 5, done=("edge",))
    oid, name = order.id, order.customer_name
    lee, kim = make_user("이시영", part="cut"), make_user("김재단", part="cut")
    boss = make_user("박반장", lead=True)
    return oid, name, lee, kim, boss


def _crew_state(client, oid, name, lee, kim, boss) -> None:
    k = [_key(name, j) for j in range(5)]
    _press(client, lee, oid, k[0], "take", "none")
    assert _press(client, kim, oid, k[0], "take", "none")["joined_late"] is True  # 거의 같이 = 저절로 같이 작업(M1)
    _press(client, lee, oid, k[0], "done", "need")
    _press(client, kim, oid, k[0], "done", "need")
    _press(client, lee, oid, k[1], "take", "none")
    _press(client, kim, oid, k[1], "join", "need", seen_me="none")
    _press(client, lee, oid, k[1], "done", "need", seen_me="held")
    _press(client, lee, oid, k[2], "take", "none")
    _press(client, kim, oid, k[2], "join", "need", seen_me="none")
    _press(client, boss, oid, k[2], "remove", "need", target_user_id=kim.id)
    _press(client, kim, oid, k[3], "take", "none")
    _press(client, kim, oid, k[3], "release", "need", seen_me="held")
    _press(client, boss, oid, k[4], "check", "none")


def _sheet(client, oid: int, part: str = "cut") -> dict:
    body = client.get(f"{API}?order_id={oid}&part={part}").get_json()
    assert body["success"] is True, body
    return body["data"]


def _node(page: Path, want: dict) -> dict:
    node = shutil.which("node")
    assert node, "node must be on PATH for JS checks"
    proc = subprocess.run([node, str(NODE_CHECK), str(page), json.dumps(want, ensure_ascii=False)], capture_output=True, text=True,
                          encoding="utf-8", timeout=60, cwd=str(ROOT))
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


# --------------------------------------------------------------------------- #
# PC 도면별 창 — 서버 자료(사람마다 줄 · 1/2 완료 · 모두 완료 · 빈 도면)
# --------------------------------------------------------------------------- #
def test_pc_window_rows_are_one_piece_per_person(client, cohort) -> None:
    oid, name, lee, kim, boss = _seed()
    _crew_state(client, oid, name, lee, kim, boss)
    _login(client, boss)
    d = _sheet(client, oid)
    rows = d["rows"]
    assert [r["word"] for r in rows] == ["재단 완료", "재단 1/2 완료", "작업 중", "미정", "재단 완료"]
    assert [r["note"] for r in rows] == [None, "김재단 작업 중", None, None, None]
    assert [r["act"] for r in rows] == ["uncheck", "check", "check", "check", "uncheck"]
    assert _like(rows[0]["lines"], ["작업 시작 이시영", "완료 이시영", "작업 시작 김재단", "완료 김재단"])  # 모두 보임 — 사람마다
    assert _like(rows[1]["lines"], ["작업 시작 이시영", "완료 이시영", "작업 시작 김재단"])
    assert _like(rows[2]["lines"], ["작업 시작 이시영"])  # 반장이 시작 취소한 김재단은 줄에 없다
    assert rows[3]["lines"] == ["담당 미정"]  # K2 그대로
    assert _like(rows[4]["lines"], ["작업 시작 박반장", "완료 박반장"])
    assert [r["undo_releases"] for r in rows] == [False, False, False, False, True]  # 나 혼자 시작 + 완료한 장만
    for r in rows:  # 한 명짜리 옛 칸(담당 · 완료 · 본 담당)은 PC 창 자료에서 뺐다 — 줄 글은 lines 하나
        assert not {"holder", "done", "seen_by"} & set(r), r
    # 작업 시트 공정 칸 옆 글은 도면 수 그대로 — "1/2 완료"는 도면 한 장 자리에만(Q11)
    sheet = client.get(f"/erp/production/sheet/{oid}").get_data(as_text=True)
    assert "도면 2/5 · 3장 미완료" in sheet and "1/2 완료" not in sheet


def test_pc_window_js_sends_one_check_and_server_finishes_the_rest(client, cohort, tmp_path) -> None:
    """창 JS 를 진짜 PC 화면 위에서 돌리고(Node), JS 가 보낸 몸을 진짜 서버에 다시 보낸다."""
    oid, name, lee, kim, boss = _seed()
    _crew_state(client, oid, name, lee, kim, boss)
    k = [_key(name, j) for j in range(5)]
    _login(client, boss)
    _edit(client)
    page = tmp_path / "pc.html"
    page.write_text(client.get(f"{HOME}?day={_order_day(oid)}").get_data(as_text=True), encoding="utf-8")
    sheets = {part: _sheet(client, oid, part) for part in ("cut", "edge", "assemble")}
    history = client.get(HISTORY, query_string={"order_id": oid, "part": "cut"}).get_json()["data"]["items"]
    me = sheets["cut"]["me"]
    held = {"success": True, "data": {"changed": True, "mark": {"state": "need", "holders": [
        {"user_id": lee.id, "name": "이시영", "done": False}, {"user_id": kim.id, "name": "김재단", "done": False}]}}}
    alone = {"success": True, "data": {"changed": True, "mark": {"state": "need", "holders": [{"user_id": me, "name": "박반장",
                                                                                               "done": False}]}}}
    out = _node(page, {"oid": oid, "sheets": sheets, "history": history, "key_need": k[1], "key_done": k[0], "key_mine": k[4],
                       "posts": [{"success": True, "data": {"changed": True, "proxied": True, "mark": {"state": "done"}}},
                                 held, alone, {"success": True, "data": {"changed": True, "mark": {"state": "none"}}}]})
    assert out["title"] == "재단 · 도면 5장"
    assert [r["button"] for r in out["rows"]] == ["완료 취소", "완료 처리", "완료 처리", "완료 처리", "완료 취소"]  # K3
    assert [r["lines"] for r in out["rows"]] == [r["lines"] for r in sheets["cut"]["rows"]]  # 서버 글 그대로(JS 는 안 만든다)
    assert [(r["word"], r["note"]) for r in out["rows"]][:2] == [("재단 완료", None), ("재단 1/2 완료", "김재단 작업 중")]
    assert out["tools"] == []  # 카드를 쓴 파트 — 창 머리 단추 없음
    # [완료 처리] = POST 한 번, action check(시작 · 완료를 따로 보내지 않는다 — 판결 2)
    assert [p["body"] for p in out["checkPosts"]] == [
        {"order_id": oid, "drawing_key": k[1], "part": "cut", "action": "check", "seen": "need"}]
    assert [p["body"]["action"] for p in out["undoPosts"]] == ["undo"]  # 같이 작업한 장은 완료 취소만
    assert [(p["body"]["action"], p["body"]["seen"], p["body"].get("seen_by")) for p in out["minePosts"]] == [
        ("undo", "done", None), ("release", "need", me)]  # 나 혼자 시작 + 완료한 장 = 시작 취소까지
    # 도면 5장 주문 = 아무도 안 시작한 파트도 [모두 완료 처리] 없음 · 확인 창 0 · 공정 칸 쓰기 0(사장님 2026-11-27 "도면 두 장 이상이면 막기" —
    # 1장 주문의 [모두 완료 처리] 확인 창은 test_production_per_sheet_only_1127)
    assert out["allTools"] == [] and out["confirmOpen"] is False
    assert out["postsAfterCancel"] == 4
    assert out["handTools"] == ["모두 완료 취소"] and {r["word"] for r in out["handRows"]} == {"엣지 완료 · 박반장"}
    # 바뀐 기록 낱말(§8-2 24 · §8-1) — 도면마다 한 줄
    log = out["log"]
    assert re.fullmatch(rf"재단 도면 1/5: 이시영 작업 시작 {STAMP} → 김재단 같이 작업 [0-9:]+ → 이시영 완료 [0-9:]+ → 김재단 완료 [0-9:]+",
                        log[0]), log[0]
    assert re.search(r" → 김재단 같이 작업 [0-9:]+ → 김재단 시작 취소 \(박반장\) [0-9:]+$", log[2]), log[2]
    assert re.fullmatch(rf"재단 도면 4/5: 김재단 작업 시작 {STAMP} → 김재단 시작 취소 [0-9:]+", log[3]), log[3]
    assert re.fullmatch(rf"재단 도면 5/5: 박반장 완료 {STAMP}", log[4]), log[4]
    assert not any("맡음" in line or "맡기" in line for line in log)
    # JS 가 보낸 [완료 처리] 몸 그대로 → 진짜 서버: 남은 사람 몫 대신 완료, 반장은 '작업 시작' 줄에 안 선다
    _login(client, boss)
    done = client.post(ONE, json=out["checkPosts"][0]["body"]).get_json()["data"]
    assert (done["proxied"], done["mark"]["state"]) == (True, "done")
    after = _sheet(client, oid)["rows"]
    assert after[1]["word"] == "재단 완료" and after[1]["note"] is None
    assert _like(after[1]["lines"], ["작업 시작 이시영", "완료 이시영", "작업 시작 김재단", "완료 박반장"])
    assert not any(line.startswith("작업 시작 박반장") for r in after[:4] for line in r["lines"])
    # 반장 [완료 취소] 둘(JS 몸 그대로) — 나 혼자 한 장은 시작 취소까지 이어 "미정 · 담당 미정"
    for body in [p["body"] for p in out["minePosts"]]:
        assert client.post(ONE, json=body).status_code == 200, body
    mine = _sheet(client, oid)["rows"][4]
    assert (mine["word"], mine["lines"]) == ("미정", ["담당 미정"])
    # 대신 완료 기록 줄 — "완료"(check) 낱말
    items = client.get(HISTORY, query_string={"order_id": oid, "part": "cut"}).get_json()["data"]["items"]
    again = _node(page, {"log_only": [i for i in items if i["drawing_key"] == k[1]], "keys": sheets["cut"]["keys"]})
    assert re.search(r"→ 박반장 \([^)]*김재단[^)]*대신\) 완료 [0-9:]+$", again["log"][0]), again["log"][0]


def _order_day(oid: int) -> str:
    from db import db_session
    from models import Order

    return db_session.get(Order, oid).erp_construction_date


# --------------------------------------------------------------------------- #
# 날짜 줄 · PC 첫 화면 줄 — 칸 아래 "이시영 외 1"
# --------------------------------------------------------------------------- #
def test_date_rows_count_coworkers_in_more_n(client, cohort) -> None:
    order = _order("나래", 2)
    oid, name = order.id, order.customer_name
    lee, kim = make_user("이시영", part="cut"), make_user("김재단", part="cut")
    choi = make_user("최엣지", part="edge")
    _press(client, lee, oid, _key(name, 0), "take", "none")
    _press(client, kim, oid, _key(name, 0), "take", "none")  # 같은 도면을 같이 작업
    _press(client, choi, oid, _key(name, 1), "take", "none", part="edge")  # 대조 — 혼자 작업하는 파트
    viewer = make_user("관리", role="ADMIN", team="CS")
    day = _order_day(oid)
    _login(client, viewer)
    pc = client.get(f"{HOME}?day={day}").get_data(as_text=True).split(f'data-foms-home-dayrow="{oid}"', 1)[1].split('<div class="fpc-r', 1)[0]
    cut = pc.split('data-foms-pc-sheet="cut"', 1)[1].split('data-foms-pc-sheet="edge"', 1)[0]
    assert '<span class="fpc-s__m"><b>이시영</b><span>외 1</span>' in cut
    assert re.search(r'data-tip="재단 0/2 · 2장 미완료 · 이시영 작업 중 · 함께 하는 사람 김재단"', pc)
    edge = pc.split('data-foms-pc-sheet="edge"', 1)[1].split('data-foms-pc-sheet="assemble"', 1)[0]
    assert "<b>최엣지</b></span>" in edge and "외 " not in edge  # 혼자면 "외 n" 없음
    _login(client, viewer, TABLET)
    tab = client.get(f"{HOME}?day={day}").get_data(as_text=True).split(f'data-foms-home-dayrow="{oid}"', 1)[1].split("</a>", 1)[0]
    assert '<small class="fph-dr__hd" aria-hidden="true"><b>이시영</b><span>외 1</span></small>' in tab
    assert '<small class="fph-dr__hd" aria-hidden="true"><b>최엣지</b></small>' in tab


# --------------------------------------------------------------------------- #
# '끝' → '완료'(K4 · 지휘 판결) — 단계 큰 글자 상수 하나 · '내 공정' [재단 완료]
# --------------------------------------------------------------------------- #
def test_finished_stage_word_is_one_constant_in_five_places(app) -> None:
    """단계 큰 글자 "검수 완료"(K4) — 만드는 곳이 그린 값을 견주는 다섯 곳이 모두 '끝난 줄'로 읽는다(그린 값으로 잰다, 11-25 검토 10)."""
    assert PRODUCTION_FINISHED_STAGE == "검수 완료"
    steps = [{"key": k, "label": label, "done": True, "now": False}
             for k, label in (("cut", "재단"), ("edge", "엣지"), ("assemble", "조립"), ("inspect", "검수"))]
    stage, _sub, view = production_home_stage("PRODUCTION", True, steps, False)  # 만드는 곳
    assert (stage, view) == ("검수 완료", "prod")
    row = {"id": 7, "home_stage": stage, "home_view": view, "home_steps": steps, "hold_active": False, "home_has_run": True}
    cutting = {**row, "home_stage": "재단 중", "home_steps": [dict(steps[0], done=False, now=True)] + steps[1:]}
    assert production_home_step_queues([row, cutting])["finished"] == 1  # ① 첫 화면 '검수 완료' 셈(대조: 재단 중은 안 셈)
    assert _row_bar_kind(row) == "f" and _row_bar_kind(cutting) == "p"  # ② 날짜 띠 막대 = 완료 색
    assert late_spot(row) == (None, "제작 완료 전") and late_spot(cutting) == ("early", "재단")  # ③ 늦음 판정 자리
    with app.test_request_context():
        pc = str(app.jinja_env.get_template("production/partials/home_pc_macros.html").module.pc_status(row))
        tab = str(app.jinja_env.get_template("production/partials/home_date_macros.html").module.fph_row(row))
        pc_cut = str(app.jinja_env.get_template("production/partials/home_pc_macros.html").module.pc_status(cutting))
    assert pc.startswith('<span class="fpc-st is-f"') and "<b>검수 완료</b>" in pc and 'class="fpc-st is-p"' in pc_cut  # ④ PC 줄
    assert tab.lstrip().startswith('<a class="fph-dr is-f"') and '<span class="fph-dr__sg">검수 완료' in tab  # ⑤ 태블릿 날짜 줄
    # 음성 대조 — 이벤트 이름은 그대로(§8-3 끝): 관리자가 건너뛴 검사 이름 글
    assert translate_admin_override_gates({"gates": ["STEPS_INCOMPLETE"]}) == "검수 끝 전제"


def test_moving_words_stay_and_my_steps_status_says_done_rendered(client, cohort, tmp_path) -> None:
    """'내 공정' — 문장 속 움직임 말("끝내면 다음은" · "끝냈어요")은 그대로, 판 [재단 완료] 뒤 상태 줄은 "{고객} 재단 완료"(K4 · 지휘 판결).
    서버가 그린 판 · 줄 위에서 JS 를 돌려 상태 줄에 그린 글을 잰다(소스 글자 단언이 아니다)."""
    from tests.domains.test_production_my_steps_confirm import PC as STEPS_PC, WORDS, _node as steps_node, _seed as steps_seed
    from tests.support.production_home_step_panel_seed import SHELL, get_html, login as steps_login, pane_html, set_cookies

    drawn, bare, _revising, _held = steps_seed()
    steps_login(client)
    set_cookies(client, TABLET)
    page = get_html(client, HOME + "?tab=steps&view=fragment", SHELL)
    assert "끝내면 다음은 <b>" in pane_html(page, drawn.id)  # 판 아래 다음 손님 글 그대로
    steps_node(tmp_path, page, {"mode": "panel", "first": drawn.id, "sheets": 1, "next": bare.id, **WORDS,
                                "done_status": f"{drawn.customer_name} 재단 완료"})
    set_cookies(client, STEPS_PC)
    client.set_cookie("foms_prod_edit", str(int(time.time())), domain="localhost", path="/erp/production")
    page = get_html(client, HOME + "?tab=steps&view=fragment", SHELL)
    steps_node(tmp_path, page, {"mode": "row", "first": drawn.id, "bare": bare.id, **WORDS,
                                "done_status": "끝냈어요. 다음 공정으로 옮겨요"})


def test_finished_rows_say_inspect_done_and_my_steps_button_says_done(client, cohort) -> None:
    full = _order("다솜", 2, done=("cut", "edge", "assemble", "inspect"))
    cutting = _order("라온", 1)  # 도면 1장(여러 장 줄은 [재단 완료] 자리가 막힌다 — 사장님 2026-11-27)
    fid, cid, day = full.id, cutting.id, full.erp_construction_date
    boss = make_user("박반장", lead=True)
    _login(client, boss)
    pc = client.get(f"{HOME}?day={day}").get_data(as_text=True)
    row = pc.split(f'data-foms-home-dayrow="{fid}"', 1)[1].split('<div class="fpc-r', 1)[0]
    assert re.search(r'<span class="fpc-st is-f"[^>]*><b>검수 완료</b>', row)  # 완료 색 + 새 글
    other = pc.split(f'data-foms-home-dayrow="{cid}"', 1)[1].split('<div class="fpc-r', 1)[0]
    assert re.search(r'<span class="fpc-st is-p"[^>]*><b>재단 작업 중</b>', other)  # 대조
    _login(client, boss, TABLET)
    tab = client.get(f"{HOME}?day={day}").get_data(as_text=True)
    trow = tab.split(f'data-foms-home-dayrow="{fid}"', 1)[0].rsplit("<a ", 1)[1]
    assert trow.startswith('class="fph-dr is-f') and '<span class="fph-dr__sg">검수 완료' in tab
    # '내 공정' PC 줄 [재단 완료](옛 [재단 끝] — 지휘 판결), 마우스 글 "재단 완료 · …"
    _login(client, boss)
    _edit(client)
    steps = client.get(f"{HOME}?tab=steps").get_data(as_text=True)
    assert '</svg>재단 완료</button>' in steps and "재단 끝" not in steps
    assert 'data-tip="재단 완료 · 박반장 · 11/24 10:20"' in client.get(f"{HOME}?day={day}").get_data(as_text=True)
