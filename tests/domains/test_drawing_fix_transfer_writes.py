"""생산 넘어간 주문의 도면 수정 D2 — 수정본 보내기의 쓰기 · 미리 보기(설계서 2026-11-25 §3-4 ~ §3-7 · §6 · R1).

* 풀림(§3-4): 이번 전달이 건드린 열쇠의 [수정 시작] 표시만 지운다 — 안 건드린 도면은 그대로 막힘. 전달 쓰기와 같은 사본(원자).
* 손 처리 풀기(§3-6 ②, 답 Q13): 카드 0장 · 칸 켜진 파트는 안 바뀐 도면만 ``DONE``(완료한 사람 = 칸을 켠 사람 — 장별 기록도 같은
  사람), 새 판은 할 일로 남고 칸은 꺼진다. 검수 준비 문은 걸지 않는다.
* 패킹 풀기(§3-7, 답 Q10): 고친 도면 줄의 체크만 푼다. 출발 보고 뒤에는 그대로.
* 파일 이어받기(§3-5, 답 Q14): 고른 도면의 공장 · '바뀐 도면' 짝(``file_successor``)을 새 파일이 이어받는다.
* ``changed`` · 공장 '바뀐 것' 글 "도면 2 바뀜 · 메모: …" · 알림 글(§6) · R1 미리 보기(전달과 같은 함수 · 쿼리 = 주문 1 + 표시 1).

되돌리면 실패: 안 건드린 도면 막힘이 풀림 · 손 처리 파트가 새 판도 완료로 보임 · 기록 이름이 보낸 도면팀원 · 고친 도면 패킹 체크가
남음 · 출발 뒤 체크가 풀림 · 파일 새 판이 1공장으로 돌아감 · '바뀐 것'에 번호 없음. 이름은 모두 지어낸 값이다.
"""
from __future__ import annotations

import datetime
import pytest
from sqlalchemy import event

from db import db_session, engine
from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.notifications.production_change import NOTIFICATION_TYPE
from foms.services.orders import drawing_fix as fx
from foms.services.orders.drawing_factory import sheet_factory
from foms.services.production.part_board import index_marks, replaced_info
from foms.services.production_change_alerts import _build_change_lists
from models import Notification, OrderEvent
from tests.support.drawing_fix_transfer_seed import (  # noqa: F401  quiet · team = 시험 준비물
    STEP_AT,
    key,
    last_transfer as _last_transfer,
    login,
    make_order,
    manual_key,
    marks,
    names as _names,
    patch,
    put_mark,
    quiet,
    sd_of,
    send,
    team,
)

PATHS = ("drawing", "pending")
SINCE = datetime.datetime(2000, 1, 1)   # 창 시작 — 시드 · 새 전달 모두 뒤(오늘을 가정하지 않는다)
FIX = {"no": 2, "by_user_id": None, "by_name": "김도면", "at": "2026-11-25T05:10:00Z"}


@pytest.mark.parametrize("path", PATHS)
def test_release_clears_only_touched_fixing_in_the_same_write(client, quiet, team, path):
    oid = make_order(assignees=(team.drawer.id,),
                     extra={"drawing_fix": {"fixing": {"sheet:s1": FIX, "sheet:s2": dict(FIX, no=3)}}})
    login(client, team.other)
    res = send(client, path, oid, "s1")
    assert res.status_code == 200, res.get_json()
    sd = sd_of(oid)
    assert set(sd["drawing_fix"]["fixing"]) == {"sheet:s2"}            # 안 건드린 도면 3 은 그대로 막힘
    assert fx.blocked(sd).idents == frozenset({"sheet:s2"})
    log = sd["drawing_fix"]["log"][-1]
    assert (log["act"], log["idents"], log["numbers"], log["by_name"]) == ("done", ["sheet:s1"], [2], "오도면")
    assert _names(sd)[1] == "s1-v2.png" and sd["drawing_status"] == "CONFIRMED"   # 같은 쓰기


@pytest.mark.parametrize("path", PATHS)
def test_hand_part_keeps_unchanged_drawings_done_and_makes_only_the_fixed_one_work(client, quiet, team, path):
    oid = make_order(assignees=(team.drawer.id,), steps_done=("cut", "inspect"), step_by="박반장")
    login(client, team.drawer)
    res = send(client, path, oid, "s1", ack_worked=["sheet:s1"])      # 손 처리 파트 = 작업이 닿은 도면 → ack
    assert res.status_code == 200, res.get_json()
    rows = marks(oid)
    step_at = datetime.datetime.fromisoformat(STEP_AT).replace(tzinfo=None)
    for part in ("cut", "inspect"):                                    # 검수 준비 문은 걸지 않는다(전달이 막히면 안 됨)
        for j in (0, 2):
            row = rows[(key(oid, f"s{j}"), part)]
            assert (row.state, row.done_by_name, row.done_at) == ("DONE", "박반장", step_at)
            assert row.updated_by_user_id == team.drawer.id
        assert (key(oid, "s1-v2"), part) not in rows                   # 새 판은 할 일
    steps = {s["key"]: s["done"] for s in sd_of(oid)["production"]["steps"]}
    assert steps == {"cut": False, "edge": False, "assemble": False, "inspect": False}
    events = (db_session.query(OrderEvent).filter_by(order_id=oid, event_type="PRODUCTION_PART_MARKED").all())
    assert len(events) == 4 and {e.payload["via"] for e in events} == {"step_expand"}
    assert {e.payload["by_name"] for e in events} == {"박반장"}         # 장별 기록 = 표시 줄 사람
    login(client, team.admin)
    history = client.get(f"/api/production/part-history?order_id={oid}&key={key(oid, 's0')}")
    assert history.status_code == 200, history.get_json()
    assert {i["by_name"] for i in history.get_json()["data"]["items"]} == {"박반장"}


def test_card_part_is_left_to_today_sync(client, quiet, team):
    """대조: 카드를 쓴 파트는 풀어 쓰지 않는다(지금 동기화가 칸을 맞춘다)."""
    oid = make_order(assignees=(team.drawer.id,), steps_done=("cut",))
    put_mark(oid, key(oid, "s0"), "cut", "DONE", sheet_id="s0")
    login(client, team.drawer)
    assert send(client, "drawing", oid, "s1").status_code == 200
    assert set(marks(oid)) == {(key(oid, "s0"), "cut")}


def _packing(*, departed: bool) -> dict:
    items = [{"key": f"sheet:s{j}", "checked": True, "at": "2026-11-25T01:00:00", "by_name": "최시공"} for j in range(3)]
    return {"packing": {"layout": "factory", "items": items, **({"departed_at": "2026-11-25T02:00:00"} if departed else {})}}


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("departed", [False, True])
def test_packing_check_of_the_fixed_drawing_is_released_until_departure(client, quiet, team, path, departed):
    oid = make_order(assignees=(team.drawer.id,), extra={
        "drawing_factory": {"sheets": {"s2": 2}, "files": {}}, "shipment": _packing(departed=departed)})
    login(client, team.drawer)
    assert send(client, path, oid, "s1").status_code == 200
    checked = {r["key"]: r["checked"] for r in sd_of(oid)["shipment"]["packing"]["items"]}
    assert checked == {"sheet:s0": True, "sheet:s1": departed, "sheet:s2": True}


def test_changed_numbers_feed_the_factory_line_and_notices(client, quiet, team):
    """고침 · 빠짐 = 옛 번호(보내기 전 모두가 아는 번호 · 경고 글과 같은 번호), 새 도면 = 새 번호 — 빠짐이 앞에 있어도(D2 검토 E).
    보내는 창 줄 · 공장 '바뀐 것' · 알림 글 · 이력 ``changed`` 가 같은 값이다."""
    oid = make_order(4, assignees=(team.drawer.id,))
    wizard = dict(sd_of(oid)["drawing_wizard"])
    wizard["sheets"] = [s for s in wizard["sheets"] if s["id"] != "s0"] + [{"id": "s9", "name": "현관", "form": {}, "objects": []}]
    patch(oid, drawing_wizard=wizard)                                  # 시트 s0 지움(도면 1 빠짐) · s9 새로 만듦(새 도면)
    login(client, team.drawer)
    preview = client.get(f"/api/orders/{oid}/drawing/fix/progress?sheet=s2&sheet=s9&mode=APPEND").get_json()["data"]["plan"]
    assert preview["changed_line"] == "바뀐 도면: 도면 3 (고침) · 도면 4 (새 도면) · 도면 1 (빠짐)"
    assert send(client, "drawing", oid, "s2", "s9").status_code == 200
    sd = sd_of(oid)
    assert _names(sd) == ["s1.png", "s2-v2.png", "s3.png", "s9-v2.png"]
    assert _last_transfer(sd)["changed"] == preview["changed"] == {"replaced": [3], "added": [4], "removed": [1]}
    words = "도면 3 바뀜 · 도면 4 새로 추가 · 도면 1 빠짐 · 메모: 상판 깊이 600 → 580"
    alerts, _history = _build_change_lists([], sd, SINCE, SINCE)
    assert next(a for a in alerts if a["label"] == "도면 바뀜(바로 반영)")["detail"] == words
    notes = db_session.query(Notification).filter(Notification.order_id == oid).all()
    prod = [n for n in notes if n.notification_type == NOTIFICATION_TYPE and n.target_team == "PRODUCTION"]
    assert prod and prod[0].message.endswith(f"새 도면으로 만들어 주세요. {words})")
    sales = next(n for n in notes if n.notification_type == "DRAWING_TRANSFERRED")
    assert sales.message.endswith(f"확인할 필요 없습니다. {words}")


def test_old_transfer_line_without_numbers_keeps_memo_only():
    at = (SINCE + datetime.timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    sd = {"drawing_transfer_history": [{"action": "TRANSFER", "transferred_at": at, "hotfix": True, "note": " 상판 "}]}
    alerts, _history = _build_change_lists([], sd, SINCE, SINCE)
    assert alerts[0]["detail"] == "상판"


def test_uploaded_file_inherits_factory_fix_and_replaced_pair(client, quiet, team):
    oid = make_order(assignees=(team.drawer.id,), manual=(2,))
    old = manual_key(oid, "up2")
    patch(oid, drawing_factory={"sheets": {}, "files": {old: 2}},
          drawing_fix={"fixing": {f"file:{old}": dict(FIX, no=3)}})
    put_mark(oid, old, "cut", "DONE", name="김재단")
    login(client, team.drawer)
    new = manual_key(oid, "up2-fixed")
    res = send(client, "drawing", oid, manual=[{"key": new, "filename": "up2-fixed.pdf", "replace_of": old}],
               ack_worked=[f"file:{old}"])
    assert res.status_code == 200, res.get_json()
    sd = sd_of(oid)
    entries = resolve_final_drawing_files(sd)
    assert [e["key"] for e in entries][2] == new
    assert sheet_factory(sd, entries[2]) == 2                         # 공장 이어받음
    assert sd["drawing_fix"]["file_successor"] == {new: old} and sd["drawing_fix"]["fixing"] == {}
    _slots, by_sheet = index_marks(marks(oid).values())
    info = replaced_info(oid, entries[2], {e["key"] for e in entries}, by_sheet, "cut", fx.file_successor(sd).get(new, ""))
    assert info is not None and info["label"] == "바뀐 도면 · 전 도면 재단 완료(김재단)"


def test_new_drawing_pick_stays_first_factory_without_successor(client, quiet, team):
    oid = make_order(assignees=(team.drawer.id,))
    login(client, team.drawer)
    new = manual_key(oid, "extra")
    assert send(client, "drawing", oid, manual=[{"key": new, "filename": "extra.pdf", "replace_of": "NEW"}]).status_code == 200
    sd = sd_of(oid)
    assert sheet_factory(sd, resolve_final_drawing_files(sd)[-1]) == 1 and "drawing_fix" not in sd


# --- R1 미리 보기 -----------------------------------------------------------------


def _statements(fn):
    seen: list[str] = []

    def _before(_conn, _cursor, statement, *_a, **_k):
        seen.append(" ".join(str(statement).split()).lower())

    event.listen(engine, "before_cursor_execute", _before)
    try:
        return fn(), seen
    finally:
        event.remove(engine, "before_cursor_execute", _before)


def test_progress_preview_is_the_same_calculation_with_order_and_marks_queries_only(client, quiet, team):
    oid = make_order(assignees=(team.drawer.id,))
    put_mark(oid, key(oid, "s1"), "cut", "DONE", name="김재단", sheet_id="s1")
    put_mark(oid, key(oid, "s1"), "edge", "NEED", name="박엣지", sheet_id="s1")
    login(client, team.other)
    url = f"/api/orders/{oid}/drawing/fix/progress?sheet=s1&sheet=s9&mode=APPEND"
    res, seen = _statements(lambda: client.get(url))
    assert res.status_code == 200, res.get_json()
    data = res.get_json()["data"]
    assert [d["no"] for d in data["drawings"]] == [1, 2, 3] and data["drawings"][1]["worked"] is True
    assert data["drawings"][1]["parts"]["cut"] == {"state": "done", "name": "김재단"}
    assert data["drawings"][1]["line"] == "도면 2 · 재단 완료 · 엣지 작업 중"
    plan = data["plan"]
    assert plan["changed_line"] == "바뀐 도면: 도면 2 (고침) · 도면 4 (새 도면)"
    worked = send(client, "drawing", oid, "s1").get_json()["data"]["warnings"]
    assert plan["warnings"] == worked                                  # 전달 API 409 와 같은 글
    reads = [s for s in seen if " from orders" in s or " from production_part_marks" in s]
    assert len([s for s in reads if " from orders" in s]) == 1
    assert len([s for s in reads if " from production_part_marks" in s]) == 1


def test_progress_preview_picks_and_rights(client, quiet, team):
    oid = make_order(assignees=(team.drawer.id,))
    login(client, team.drawer)
    res = client.get(f"/api/orders/{oid}/drawing/fix/progress?pick={key(oid, 's2')}&pick=NEW&pick=")
    assert res.get_json()["data"]["plan"]["changed_line"] == "바뀐 도면: 도면 3 (고침) · 도면 4 (새 도면)"
    assert "plan" not in client.get(f"/api/orders/{oid}/drawing/fix/progress").get_json()["data"]
    login(client, team.sales)
    assert client.get(f"/api/orders/{oid}/drawing/fix/progress").status_code == 403
