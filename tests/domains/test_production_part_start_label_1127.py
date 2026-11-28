"""도면 카드 [작업 시작] → [<파트> 시작] (사장님 2026-11-27 "재단 탭 = 재단 시작, 엣지 탭 = 엣지 시작 ....이런식으로 텍스트 변경해")
+ 쓰기 뒤 '남은 공정' 바로 반영(같은 날 "작업시작 하면 내 공정에 바로바로 실시간 반영 되게 > 지금은 딜레이가 있던데").

* 카드 단추(서버 home_parts.html pp_act · JS crew.render · 크게 보기는 카드 단추를 복사)가 파트 탭마다 [재단 시작] · [엣지 시작] ·
  [조립 시작] · [검수 시작](같은 날 오후 [<파트> 같이 작업] · [<파트> 시작 취소]도 — test_production_part_named_buttons_1127). 파트 이름은 완료 단추 [<파트> 완료]와 같은 낱말 원본(``PRODUCTION_PART_LABELS`` → 판 ``part_label`` → JS cfg.label).
* 같은 단추가 여는 창: 제목 "엣지 시작할까요?" · 실행 단추 [엣지 시작] · 끝난 뒤 알림 "엣지 시작했어요"(누른 단추 말 그대로).
* 그대로인 것(대조군): [기본] · 서버 넘김 글. 작업 시트 바뀐 기록 낱말은 같은 날 '작업 시작' → '시작'(test_production_record_words_tone_1127).
* 바로 반영: 위 탭 숫자는 서버가 그릴 때만 적혀(쓰기 응답 · 30초 받아 오기는 카드만) 옛 숫자였고, 셸이 60초 받아 둔 탭 사본을 다시 끼웠다.
  쓰기 성공 → parts.js 가 'foms:prod-parts-written' → parts-fresh.js 가 위 탭 · 지금 주소 셸 사본을 버리고(요청 0), 주문 칸이 바뀐
  쓰기(제작 시작 · 그 시작 되돌림 ``run_cancelled`` · 공정 칸 · 제작 완료)만 ``?view=counts`` 한 번(그리기 없이 숫자). 쓰기 길 쿼리는 그대로.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from foms.services.production.part_constants import PRODUCTION_PART_LABELS
from tests.domains.test_production_home_query_count import _count_queries
from tests.domains.test_production_multi_holder_board import _act, _card, _node, _page, _post, cohort  # noqa: F401
from tests.support.production_factory_seed import HOME_NONE
from tests.support.production_part_claim_seed import login, make_order, make_user

ROOT = Path(__file__).resolve().parents[2]
JS = ROOT / "static/js/production"
TPL = ROOT / "templates/production/partials/home_parts.html"
PARTS = (("cut", "재단"), ("edge", "엣지"), ("assemble", "조립"), ("inspect", "검수"))


def test_labels_come_from_the_one_part_name_source():
    assert tuple(PRODUCTION_PART_LABELS.items()) == PARTS  # 새 상수 없이 완료 단추와 같은 원본


@pytest.mark.parametrize("part,label", PARTS)
def test_part_account_board_says_part_start(client, cohort, part, label):
    # 검수는 앞 파트가 모두 끝나야 열린다(검수 전 칸) — 앞 세 칸을 켜 둔 주문으로 잰다
    order = make_order(2, steps_done=("cut", "edge", "assemble") if part == "inspect" else ())
    act = _act(_card(_page(client, make_user(f"가짜{label}", part=part)), order.keys[0]))
    assert f'data-pp-act="take">{label} 시작</button>' in act
    assert ">작업 시작<" not in act  # 옛 글 없음
    others = [lb for _, lb in PARTS if lb != label]
    assert not any(f">{lb} 시작<" in act for lb in others)  # 음성 대조 — 다른 파트 이름을 쓰지 않는다


def test_lead_and_admin_boards_say_picked_part_start(client, cohort):
    order = make_order(2)
    lead = make_user("박반장", lead=True)
    edge = _act(_card(_page(client, lead, HOME_NONE + "&tab=parts&part=edge"), order.keys[0]))
    assert 'data-pp-act="take">엣지 시작</button>' in edge and 'data-pp-act="check">엣지 완료</button>' in edge
    cut = _act(_card(_page(client, make_user("관리", team="CS", role="ADMIN"), HOME_NONE + "&tab=parts&part=cut"), order.keys[0]))
    assert 'data-pp-act="basic">기본</button>' in cut and 'data-pp-act="take">재단 시작</button>' in cut  # [기본]은 그대로
    view = _act(_card(_page(client, make_user("상담", team="CS"), HOME_NONE + "&tab=parts&part=cut"), order.keys[0]))
    assert "<button" not in view  # 보기만 = 단추 없음(그대로)


def test_js_redraw_window_and_notice_use_the_same_word(client, cohort, tmp_path):
    order = make_order(3, run=False)  # 첫 카드 = 제작 시작도 같이
    me = make_user("박엣지", part="edge")
    page = tmp_path / "edge.html"
    page.write_text(_page(client, me), encoding="utf-8")
    took = _post(client, me, {"order_id": order.id, "drawing_key": order.keys[0], "part": "edge", "action": "take",
                              "seen": "none", "seen_me": "none"})
    assert took["success"] is True and took["data"]["run_started"] is True
    res = _node(page, {"posts": [took], "steps": [
        {"do": "parity"}, {"do": "click", "key": order.keys[0], "act": "take"}, {"do": "run"}, {"do": "card", "key": order.keys[1]}]})
    out = res["out"]
    assert out[0]["cards"] == 3 and out[0]["diffs"] == []  # 서버 칸 = JS 가 다시 그린 칸([엣지 시작] 포함)
    w = out[1]["modal"]
    assert (w["title"], w["run"]["text"], w["line"]) == ("엣지 시작할까요?", "엣지 시작", "미정 → 작업 중 · 박엣지")  # 11-27 앞말 미정
    assert w["body"] == "이 주문 첫 도면이라 제작 시작도 같이 돼요."  # 제작 시작 한 줄은 그대로
    assert out[2]["status"] == "엣지 시작했어요 · 제작 시작도 같이 됐어요" and out[2]["modal"]["hidden"] is True
    act = out[3]["card"]["act"]
    assert act == [{"tag": "button", "cls": "foms-prod-home__btn foms-prod-home__btn--pri pp-act", "act": "take", "text": "엣지 시작", "kids": []}]


def test_source_contract_start_words_and_untouched_words():
    crew = (JS / "foms-production-parts-crew.js").read_text(encoding="utf-8")
    modal = (JS / "foms-production-parts-modal.js").read_text(encoding="utf-8")
    parts = (JS / "foms-production-parts.js").read_text(encoding="utf-8")
    tpl = TPL.read_text(encoding="utf-8")
    assert tpl.count('data-pp-act="take">{{ pb.part_label }} 시작</button>') == 3 and 'data-pp-act="take">작업 시작<' not in tpl
    assert "LABEL + ' 시작', 'take')" in crew and "'작업 시작', 'take'" not in crew
    assert "title: LABEL + ' 시작할까요?'" in modal and "run: LABEL + ' 시작'" in modal and "작업을 시작할까요" not in modal
    # 알림 = 누른 단추 말 + 했어요("엣지 시작했어요") — 정규식이 '시작'으로 끝나는 단추를 그대로 받는다
    assert "/(완료|시작|취소)$/.test(p.run || '')) ? p.run + '했어요'" in parts
    # 11-27 오후 [같이 작업] · [시작 취소]에도 파트 이름(사장님 "둘 다 파트 이름 붙이기") — 자세한 글은 test_production_part_named_buttons_1127
    assert "LABEL + ' 같이\\u00a0작업', 'join'" in crew and 'data-pp-act="release">{{ pb.part_label }} 시작&nbsp;취소</button>' in tpl
    assert "run: LABEL + ' 시작 취소'" in modal and "p.run + ' 시작했어요'" in parts
    sheet = (JS / "foms-production-sheet-parts.js").read_text(encoding="utf-8")
    assert "take: '시작'" in sheet and "'작업 시작'" not in sheet  # 작업 시트 바뀐 기록 낱말 — 단추 말과 맞춤(11-27, test_production_record_words_tone_1127)
    viewer = (JS / "foms-production-parts-viewer.js").read_text(encoding="utf-8")
    assert "copy = el.cloneNode(true)" in viewer and "시작" not in viewer  # 크게 보기는 카드 단추를 복사(글을 따로 짓지 않음)


# --------------------------------------------------------------------------- #
# 일 2 — 쓰기 뒤 '남은 공정' 바로 반영
# --------------------------------------------------------------------------- #
COUNTS = "/erp/production/home?view=counts"
FRESH = JS / "foms-production-parts-fresh.js"
FRESH_HARNESS = ROOT / "tests/support/production_parts_fresh_node_check.js"
ADMIN_TABS = [{"href": "/erp/production/home", "small": None}, {"href": "/erp/production/home?tab=steps", "small": "3"},
              {"href": "/erp/production/home?tab=changes", "small": "0"}, {"href": "/erp/production/home?tab=all", "small": None}]
HERE = "/erp/production/home?tab=parts&part=cut&day=none"


def _nav(html: str) -> dict:
    """위 탭 숫자 — '남은 공정 N' · '바뀐 것 N'(서버가 그린 화면)."""
    steps = re.search(r"남은 공정 <small>(\d+)</small>", html)
    changed = re.search(r'바뀐 것 <small(?: class="is-hot")?>(\d+)</small>', html)
    return {"making": int(steps.group(1)) if steps else None, "changed": int(changed.group(1))}


def _counts(client) -> dict:
    resp = client.get(COUNTS)
    assert resp.status_code == 200 and resp.headers["Cache-Control"] == "private, no-store"
    body = resp.get_json()
    assert body["success"] is True and body["error"] is None
    return body["data"]["counts"]


def _take(client, who, order, j: int) -> dict:
    return _post(client, who, {"order_id": order.id, "drawing_key": order.keys[j], "part": "cut", "action": "take",
                               "seen": "none", "seen_me": "none"})


def test_counts_view_matches_the_drawn_tabs_and_moves_with_first_card(client, cohort):
    admin = make_user("관리", team="CS", role="ADMIN")
    order = make_order(3, run=False)  # 제작 대기 — 아직 '남은 공정' 줄에 없다
    login(client, admin)
    before = _counts(client)
    assert before == _nav(_page(client, admin, HOME_NONE + "&tab=parts&part=cut"))  # 화면과 같은 함수 · 같은 묘비
    took = _take(client, admin, order, 0)
    assert took["data"]["run_started"] is True  # 첫 카드 = 제작 시작(STARTING_ACTIONS)
    after = _counts(client)
    assert after["making"] == before["making"] + 1 and after["changed"] == before["changed"]
    assert after == _nav(_page(client, admin, HOME_NONE + "&tab=parts&part=cut"))  # 다시 그린 화면과 같다
    # 음성 대조 — 둘째 카드 [재단 시작]은 주문 칸을 안 바꾼다(제작 시작 · 공정 칸 없음) → 숫자 그대로
    again = _take(client, admin, order, 1)
    assert again["data"]["run_started"] is False and again["data"]["order_step"] is None
    assert _counts(client) == after


def test_start_cancel_rollback_recounts_and_remaining_number_goes_down(client, cohort):
    """시작 취소로 제작 대기로 돌아가면(run_cancelled — 2026-11-27 start_rollback) '남은 공정 N'이 그 자리에서 준다. 서버 답은 진짜 API JSON."""
    admin = make_user("관리", team="CS", role="ADMIN")
    order = make_order(2, run=False)
    login(client, admin)
    before = _counts(client)
    assert _take(client, admin, order, 0)["data"]["run_started"] is True
    during = client.get(COUNTS).get_json()
    assert during["data"]["counts"]["making"] == before["making"] + 1
    cancel = {"order_id": order.id, "drawing_key": order.keys[0], "part": "cut", "action": "release", "seen": "need",
              "seen_me": "held", "seen_by": admin.id}
    released = _post(client, admin, cancel)["data"]
    assert (released["run_cancelled"], released["run_started"], released["order_step"]) == (True, False, None)
    reply = client.get(COUNTS).get_json()
    assert reply["data"]["counts"] == before  # 서버 숫자가 원래대로
    tabs = [dict(t, small=str(during["data"]["counts"]["making"])) if "tab=steps" in t["href"] else t for t in ADMIN_TABS]
    out = _fresh({"tabs": tabs, "here": HERE, "reply": reply, "steps": [
        {"type": "foms:prod-parts-written", "detail": {"action": "release", "data": released}},
        {"type": "foms:prod-parts-written", "detail": {"action": "release", "data": dict(released, run_cancelled=False)}}]})
    assert out[0]["calls"] == [{"url": COUNTS, "method": "GET", "cache": "no-store"}]
    assert out[0]["smalls"][1] == {"text": str(before["making"]), "hot": False}  # 화면 숫자가 그 자리에서 준다
    assert out[1]["calls"] == []  # 음성 대조 — 다른 도면이 남아 제작 시작이 그대로인 시작 취소는 받지 않는다


def test_counts_view_is_lighter_than_a_screen_and_the_write_path_is_unchanged(client, cohort):
    admin = make_user("관리", team="CS", role="ADMIN")
    order = make_order(4, run=False)
    _page(client, admin, HOME_NONE + "&tab=steps")  # warmup(첫 요청의 한 번뿐인 쿼리 빼기)
    _counts(client)
    _, q_counts = _count_queries(lambda: client.get(COUNTS))
    _, q_steps = _count_queries(lambda: client.get(HOME_NONE + "&tab=steps"))
    _, q_parts = _count_queries(lambda: client.get(HOME_NONE + "&tab=parts&part=cut"))
    assert q_counts < q_steps and q_counts < q_parts, (q_counts, q_steps, q_parts)
    assert q_counts <= 11  # 첫 화면 절대 상한(test_production_home_query_count ABS_QUERY_CAP)과 같은 줄
    body = {"order_id": order.id, "drawing_key": order.keys[0], "part": "cut", "action": "take", "seen": "none", "seen_me": "none"}
    resp, q_write = _count_queries(lambda: client.post("/api/production/part-marks", json=body))
    assert resp.status_code == 200 and resp.get_json()["data"]["run_started"] is True
    assert "counts" not in resp.get_json()["data"]  # 쓰기 응답에 숫자 읽기를 얹지 않았다
    print(f"QUERIES counts={q_counts} steps={q_steps} parts={q_parts} write_first_card={q_write}")


def test_counts_view_door_is_the_screen_door(client, cohort):
    """숫자 길은 화면 문(can_view_production_home)과 같은 답 — 화면을 못 보는 사람은 숫자도 못 보고, 보는 사람은 둘 다 연다.
    팀 없는 직원은 2026-11-27 부터 첫 화면을 보기만 하므로(옛 보드 없애기 ②) 닫힌 쪽 표본은 목록 밖 팀 글자 계정이다."""
    login(client, make_user("목록밖팀", team="WAREHOUSE"))
    assert client.get(HOME_NONE).status_code == 403 and client.get(COUNTS).status_code == 403  # 같은 문
    login(client, make_user("팀없음", team=None))
    assert client.get(HOME_NONE).status_code == 200 and client.get(COUNTS).status_code == 200


def _fresh(want: dict) -> list:
    node = shutil.which("node")
    assert node, "node must be on PATH for JS checks"
    proc = subprocess.run([node, str(FRESH_HARNESS), str(FRESH), json.dumps(want, ensure_ascii=False)], capture_output=True,
                          text=True, encoding="utf-8", timeout=60, cwd=str(ROOT))
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_js_written_event_drops_tab_copies_and_recounts_only_on_order_change(client, cohort):
    admin = make_user("관리", team="CS", role="ADMIN")
    make_order(2, run=False)
    assert "foms-production-parts-fresh.js?v=20261127t" in _page(client, admin, HOME_NONE + "&tab=parts&part=cut")
    reply = client.get(COUNTS).get_json()  # 진짜 서버 답
    reply["data"]["counts"]["changed"] = 2  # '바뀐 것' 빨간 점 켜짐도 본다(숫자만 바꾼 같은 꼴)
    making = reply["data"]["counts"]["making"]
    out = _fresh({"tabs": ADMIN_TABS, "here": HERE, "reply": reply, "steps": [
        {"type": "foms:prod-parts-written", "detail": {"action": "take", "data": {"run_started": True, "order_step": None}}},
        {"type": "foms:prod-parts-written", "detail": {"action": "take", "data": {"run_started": False, "order_step": None}}},
        {"type": "foms:prod-parts-written", "detail": {"action": "done", "data": {"run_started": False,
                                                                                 "order_step": {"key": "cut", "done": True}}}},
        {"type": "foms:prod-parts-written", "detail": {"action": "bulk", "data": {"run_started": [], "order_steps": []}}},
        {"type": "foms:prod-parts-written", "detail": {"action": "complete", "data": {}}},
        {"type": "foms:part-card-updated", "detail": {"key": "x"}}]})
    every = [HERE] + [t["href"] for t in ADMIN_TABS]
    assert all(o["dropped"] == every for o in out)  # 어느 쓰기 · 받아 오기 고치기든 위 탭 · 지금 주소 사본을 버린다
    assert all(o["listeners"] == 1 for o in out)  # 두 번 실려도 리스너는 한 번
    first = out[0]
    assert first["calls"] == [{"url": COUNTS, "method": "GET", "cache": "no-store"}]
    assert first["smalls"][1] == {"text": str(making), "hot": False} and first["smalls"][2] == {"text": "2", "hot": True}
    assert out[1]["calls"] == [] and out[3]["calls"] == []  # 음성 대조 — 주문 칸이 안 바뀐 쓰기 · 0장 일괄은 받지 않는다
    assert len(out[2]["calls"]) == 1 and len(out[4]["calls"]) == 1  # 공정 칸 켜짐 · 제작 완료는 한 번
    assert out[5]["calls"] == []  # 받아 오기 고치기(남의 손)는 사본만 버린다 — 새 실시간 장치 없음


def test_js_part_account_without_steps_tab_never_recounts():
    tabs = [ADMIN_TABS[0], ADMIN_TABS[2], ADMIN_TABS[3]]  # 파트 계정 = '남은 공정' 탭 없음(D50)
    out = _fresh({"tabs": tabs, "here": "/erp/production/home", "reply": {"success": True, "data": {"counts": {}}},
                  "steps": [{"type": "foms:prod-parts-written", "detail": {"action": "take", "data": {"run_started": True}}}]})
    assert out[0]["calls"] == [] and out[0]["dropped"] == ["/erp/production/home"] + [t["href"] for t in tabs]


def test_source_contract_written_event_and_script_order():
    parts = (JS / "foms-production-parts.js").read_text(encoding="utf-8")
    ok = parts.split("if (result.ok && body.success === true) {", 1)[1].split("if (result.status === 0", 1)[0]
    assert "document.dispatchEvent(new CustomEvent('foms:prod-parts-written', { detail: { action: p.action, data: data } }))" in ok
    assert parts.count("foms:prod-parts-written") == 1  # 성공 길에서만(거절 · 끊김은 안 쏜다)
    fresh = FRESH.read_text(encoding="utf-8")
    assert len(parts.splitlines()) <= 300 and len(fresh.splitlines()) <= 300
    assert "invalidateFragmentCache" in fresh and "'/erp/production/home?view=counts'" in fresh
    assert "setInterval" not in fresh and "WebSocket" not in fresh and "EventSource" not in fresh  # 새 실시간 장치 없음
    shell = (ROOT / "static/js/runtime/erp-shell.js").read_text(encoding="utf-8")
    assert "window.FOMS_ERP_SHELL.invalidateFragmentCache = invalidateFragmentCache;" in shell  # 쓰는 셸 문은 이미 있는 것
    tpl = (ROOT / "templates/production/partials/home_scripts.html").read_text(encoding="utf-8")
    assert tpl.index("foms-production-parts-sync.js") < tpl.index("foms-production-parts-fresh.js') }}?v=20261127t")
    assert "foms-production-parts.js') }}?v=20261128d" in tpl  # 11-27 [<파트> 같이 작업] 알림 · 11-28 [시작 취소] 창 한 줄 · "창에 보인 대로만 된다"로 한 번씩 더
