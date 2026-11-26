"""여러 명 같이 작업 — 반장 · 관리자 '대신' 기록의 대상 이름(설계서 2026-11-25 multi-holder Q15 · Q23 · §8-1 바뀐 기록).

반장의 [대신 완료] · PC [완료 처리](``check``)는 "남은 사람 몫을 한 번에 완료"(Q15)라, 이벤트 ``holder_name``(바뀐 기록
"박반장 (김재단 대신) 완료"가 읽는 값)에는 **그 쓰기로 완료가 찍힌 사람만** 적힌다 — 이미 완료한 사람은 빠진다. 대신 되돌리기는
완료한 사람 몫을 모두 되돌리니(Q23) 되돌린 사람 모두, 대신 시작 취소는 고른 사람 하나. 이름은 모두 지어낸 값이다.

되돌리면 실패: '대신' 대상에 이미 완료한 사람까지 넣기. 대조군: 둘 다 남았으면 둘 다 적힌다.
"""
from __future__ import annotations

import pytest

from db import db_session
from models import SecurityLog
from tests.support.production_part_claim_seed import HISTORY, events, login, make_order, make_user, mark


def _crew(client, order, names: tuple[str, ...]):
    """이름 차례대로 [작업 시작](늦은 사람은 저절로 같이 작업) — 사람들(Person)."""
    people = [make_user(name, part="cut") for name in names]
    for who in people:
        login(client, who)
        assert mark(client, order, 0, "cut", "take", "none").status_code == 200
    return people


def _last(order) -> dict:
    return events(order.id, "PRODUCTION_PART_MARKED")[-1].payload


def _history_last(client, order) -> dict:
    """바뀐 기록 목록의 마지막 카드 줄(장 하나 · 모두 완료면 뒤에 붙는 공정 칸 줄 ``step_on`` 은 뺀다)."""
    items = client.get(HISTORY, query_string={"order_id": order.id, "part": "cut"}).get_json()["data"]["items"]
    return [i for i in items if not i["kind"].startswith("step_")][-1]


@pytest.mark.parametrize("action,seen", [("done", "need"), ("check", "need")])
def test_proxy_finish_names_only_people_finished_by_this_write(client, action, seen):
    order = make_order(1)
    lee, _kim = _crew(client, order, ("이시영", "김재단"))
    login(client, lee)
    assert mark(client, order, 0, "cut", "done", "need").status_code == 200  # 이시영은 이미 완료
    login(client, make_user("박반장", lead=True))
    resp = mark(client, order, 0, "cut", action, seen)
    assert resp.status_code == 200 and resp.get_json()["data"]["mark"]["state"] == "done"
    payload = _last(order)
    assert (payload["override"], payload["holder_name"]) == (True, "김재단")  # 남은 사람만
    item = _history_last(client, order)
    assert (item["by_name"], item["holder_name"], item["override"]) == ("박반장", "김재단", True)
    audit = db_session.query(SecurityLog).filter_by(action="PRODUCTION_PART_MARKED", target_id=order.id).all()[-1]
    assert "이시영" not in audit.message and "(대신 처리)" in audit.message


def test_proxy_finish_names_every_remaining_person_control(client):
    """대조군 — 둘 다 남았으면 둘 다, 셋 이상이면 이름 줄 규칙(둘까지 + "외 n")."""
    order = make_order(1)
    _crew(client, order, ("이시영", "김재단"))
    login(client, make_user("박반장", lead=True))
    mark(client, order, 0, "cut", "done", "need")
    assert _last(order)["holder_name"] == "이시영 · 김재단"
    many = make_order(1)
    first, *_rest = _crew(client, many, ("이시영", "김재단", "박재단", "최재단"))
    login(client, first)
    mark(client, many, 0, "cut", "done", "need")
    login(client, make_user("반장둘", lead=True))
    mark(client, many, 0, "cut", "check", "need")
    assert _last(many)["holder_name"] == "김재단 · 박재단 외 1"


def test_proxy_undo_names_everyone_undone_and_proxy_release_names_the_one(client):
    order = make_order(1)
    lee, kim = _crew(client, order, ("이시영", "김재단"))
    for who in (lee, kim):
        login(client, who)
        mark(client, order, 0, "cut", "done", "need")
    boss = make_user("박반장", lead=True)
    login(client, boss)
    assert mark(client, order, 0, "cut", "undo", "done").status_code == 200  # 둘 다 되돌림(Q23)
    assert _last(order)["holder_name"] == "이시영 · 김재단"
    assert mark(client, order, 0, "cut", "remove", "need", target_user_id=kim.id).status_code == 200
    assert (_last(order)["holder_name"], _last(order)["target_name"]) == ("김재단", "김재단")  # 고른 사람 하나
