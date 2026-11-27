"""PostgreSQL 두 세션 — 파트 카드 쓰기는 주문 행 잠금 아래에서 판정한다(설계서 2026-11-23 §4-5 '경합' · §4-2 순서).

연결 B 가 주문 행을 ``FOR UPDATE`` 로 쥐고 카드 쓰기(담당 바꾸기 · 맡기 취소 · 맡기)를 한 뒤 커밋 전에 기다리는 동안 실제 Flask
라우트(스레드 A)를 부른다. A 는 잠금에서 기다렸다가 **B 의 결과 위에서** 판정해야 한다.

* 담당 바꾸기(B) 대 옛 담당의 완료(A) — A 는 409 ``MARK_CONFLICT``(담당이 바뀜), B 의 새 담당이 남는다.
* 맡기 취소(B) 대 담당 바꾸기(A) — A 는 409(맡기가 취소됨), 줄은 NONE 그대로.
* 카드 맡기(B) 대 반장 공정 칸 체크(A) — A 는 409 ``PART_USES_CARDS``(카드가 먼저면 칸이 막힌다), 칸은 꺼진 채.
* 여러 명(2026-11-25 multi-holder §11 PG): 같은 '미정' 도면에 같은 때 [작업 시작](B 먼저) — A 는 200 저절로 같이 작업(``joined_late``),
  목록 [B, A]. [같이 작업](A) 대 마지막 사람의 시작 취소(B) — 잠금 차례대로 A 는 그냥 작업 시작(판결 1), 목록 [A].
  마지막 두 사람 동시 [완료](B 먼저) — A 는 B 의 완료 위에 내 몫을 더해 DONE. 본인 [완료](B) 대 반장 [대신 완료](A ``check``) — A 는
  남은 사람 몫만 반장 이름으로(B 본인 이름 그대로, 기록 '대신' 대상 = 남은 사람).

음성 대조(``mode="plain"``): 카드 쓰기의 첫 조회를 잠금 대신 일반 조회로 바꾸면 A 가 B 커밋 전 모습으로 판정해 B 의 쓰기를
덮는다(lost update) — 시나리오가 결함을 실제로 잡는다는 증거다. ``FOMS_TEST_DATABASE_URL`` 미설정이면 레인을 건너뛴다.
"""
from __future__ import annotations

import threading
import time

import pytest
from sqlalchemy.orm import sessionmaker
from werkzeug.security import generate_password_hash

import foms.platform.http as platform_http
import foms.services.production.part_mark_write as part_mark_write
from foms.services.datetime_kst import now_utc_naive
from foms.services.production import mark_crew
from models import Order, OrderEvent, ProductionPartMark, ProductionRun, User

_HOLD_SECONDS = 1.0
_SEQ = [0]


@pytest.fixture
def pg_app(pg_engine, monkeypatch):
    """전역 db_session 을 PG 엔진에 묶은 Flask 앱(테스트 끝에 원래 엔진으로 되돌린다)."""
    from app import app as flask_app
    from db import db_session, engine as default_engine

    db_session.remove()
    db_session.configure(bind=pg_engine)
    flask_app.config["TESTING"] = True
    monkeypatch.setattr(platform_http, "touch_last_seen", lambda user: False)
    try:
        yield flask_app
    finally:
        db_session.remove()
        db_session.configure(bind=default_engine)


def _session(pg_engine):
    return sessionmaker(bind=pg_engine)()


def _user(s, name: str, part: str | None, tag: str, *, lead: bool | None = None) -> tuple[int, str, str]:
    user = User(username=f"race_{name}_{tag}", password=generate_password_hash("pw"), role="STAFF", team="PRODUCTION",
                name=name, is_active=True, production_part=part, production_lead=lead)
    s.add(user)
    s.flush()
    return user.id, user.username, user.role


def _seed(pg_engine, *, mark_state: str | None):
    """제작 중 주문 1건(도면 2장) + 엣지 계정 셋 + 반장. ``mark_state`` 면 첫 장 엣지 표시(박엣지 담당)."""
    _SEQ[0] += 1
    tag = f"{_SEQ[0]}_{int(time.time() * 1000) % 100000}"
    s = _session(pg_engine)
    try:
        park, kim, choi = (_user(s, n, "edge", tag) for n in ("박엣지", "김민준", "최가은"))
        foreman = _user(s, "박반장", None, tag, lead=True)  # 반장(설계서 2026-11-23 '승인 때 고친 것' 5 — 공정 칸 손 체크)
        files = [{"key": f"race{tag}/d{j}.png", "filename": f"d{j}.png", "sheet_id": f"race{tag}-s{j}"} for j in range(2)]
        order = Order(received_date="2026-11-23", customer_name="가짜고객", phone="010-0000-0000", address="가짜시",
                      product="가짜장", status="PRODUCTION", is_erp_order=True, erp_stage_code="PRODUCTION",
                      structured_data={"workflow": {"stage": "PRODUCTION"}, "drawing_current_files": files,
                                       "parties": {"customer": {"name": "가짜고객"}}})
        s.add(order)
        s.flush()
        s.add(ProductionRun(order_id=order.id, status="IN_PROGRESS", steps=[], defects=[], is_current=True))
        if mark_state:
            now = now_utc_naive()
            s.add(ProductionPartMark(order_id=order.id, drawing_key=files[0]["key"], part="edge", state=mark_state,
                                     picked_by_user_id=park[0], picked_by_name="박엣지", picked_at=now,
                                     updated_by_user_id=park[0], updated_at=now))
        s.commit()
        return order.id, files[0]["key"], {"park": park, "kim": kim, "choi": choi, "foreman": foreman}
    finally:
        s.close()


def _hold_and_write(pg_engine, order_id, key, write, started, done, a_read=None):
    """연결 B: 주문 행을 FOR UPDATE 로 쥐고 표시 줄을 고친 뒤 커밋 전 대기 → 커밋."""
    s = _session(pg_engine)
    try:
        s.query(Order).filter(Order.id == order_id).with_for_update().one()
        mark = s.query(ProductionPartMark).filter_by(order_id=order_id, drawing_key=key, part="edge").one_or_none()
        write(s, mark)
        s.flush()
        started.set()
        if a_read is not None:
            assert a_read.wait(10.0), "A 가 일반 조회를 하지 않았다"
        else:
            time.sleep(_HOLD_SECONDS)
        s.commit()
    finally:
        s.close()
        done.set()


def _call_route(app, user, url, body, out):
    client = app.test_client()
    uid, username, role = user
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = uid, username, role
    resp = client.post(url, json=body)
    out["status"], out["json"] = resp.status_code, resp.get_json()


def _race(pg_engine, app, order_id, key, write_b, user_a, url, body, a_read=None):
    started, done = threading.Event(), threading.Event()
    tb = threading.Thread(target=_hold_and_write, args=(pg_engine, order_id, key, write_b, started, done, a_read))
    tb.start()
    assert started.wait(5.0), "연결 B 가 잠금을 잡지 못했다"
    out: dict = {}
    ta = threading.Thread(target=_call_route, args=(app, user_a, url, body, out))
    ta.start()
    ta.join(15.0)
    tb.join(15.0)
    assert "status" in out, "라우트 A 가 끝나지 않았다"
    return out


def _arm_plain(monkeypatch, mode):
    """plain 이면 카드 쓰기의 첫 조회를 잠그지 않는 일반 조회로 바꾸고, A 가 읽은 순간 켜지는 Event 를 돌려준다."""
    if mode != "plain":
        return None
    a_read = threading.Event()

    def _plain_fetch(db, order_id):
        found = db.query(Order).filter(Order.id == order_id).first()
        rows = db.query(ProductionPartMark).filter(ProductionPartMark.order_id == order_id).all()
        _ = (found.structured_data if found else None, [r.state for r in rows])
        a_read.set()
        return found

    monkeypatch.setattr(part_mark_write, "lock_order_row", _plain_fetch)
    return a_read


def _final_mark(pg_engine, order_id, key):
    s = _session(pg_engine)
    try:
        m = s.query(ProductionPartMark).filter_by(order_id=order_id, drawing_key=key, part="edge").one()
        return m.state, m.picked_by_name, m.done_by_name, m.handed_from_name
    finally:
        s.close()


@pytest.mark.parametrize("mode", ["lock", "plain"])
def test_takeover_then_old_holder_done(pg_engine, pg_app, monkeypatch, mode):
    order_id, key, who = _seed(pg_engine, mark_state="NEED")
    a_read = _arm_plain(monkeypatch, mode)

    def takeover(s, mark):  # B = 김민준이 담당 바꾸기
        mark.handed_from_name, mark.handed_at = mark.picked_by_name, now_utc_naive()
        mark.picked_by_user_id, mark.picked_by_name, mark.picked_at = who["kim"][0], "김민준", now_utc_naive()

    out = _race(pg_engine, pg_app, order_id, key, takeover, who["park"], "/api/production/part-marks",
                {"order_id": order_id, "drawing_key": key, "part": "edge", "action": "done", "seen": "need",
                 "seen_by": who["park"][0]}, a_read)
    if mode == "lock":
        assert out["status"] == 409 and out["json"]["data"]["code"] == "MARK_CONFLICT"
        assert out["json"]["error"] == "그사이 김민준으로 담당이 바뀌었어요. 이 장은 이제 김민준이 해요."
        assert _final_mark(pg_engine, order_id, key) == ("NEED", "김민준", None, "박엣지")
    else:  # 음성 대조 — 낡은 모습으로 판정해 담당 바꾸기를 덮는다
        assert out["status"] == 200
        assert _final_mark(pg_engine, order_id, key)[0] == "DONE"


def test_release_then_takeover(pg_engine, pg_app):
    order_id, key, who = _seed(pg_engine, mark_state="NEED")

    def release(s, mark):  # B = 박엣지가 맡기 취소
        mark.state, mark.picked_by_user_id, mark.picked_by_name, mark.picked_at = "NONE", None, None, None

    out = _race(pg_engine, pg_app, order_id, key, release, who["choi"], "/api/production/part-marks",
                {"order_id": order_id, "drawing_key": key, "part": "edge", "action": "takeover", "seen": "need",
                 "seen_by": who["park"][0]})
    assert out["status"] == 409 and out["json"]["error"] == "그사이 시작이 취소됐어요. 지금은 담당 미정이에요."
    assert _final_mark(pg_engine, order_id, key) == ("NONE", None, None, None)


def test_card_take_then_foreman_step_check(pg_engine, pg_app):
    order_id, key, who = _seed(pg_engine, mark_state=None)

    def take(s, _mark):  # B = 박엣지가 첫 장 엣지 맡기(카드를 쓴 파트가 된다)
        now = now_utc_naive()
        s.add(ProductionPartMark(order_id=order_id, drawing_key=key, part="edge", state="NEED",
                                 picked_by_user_id=who["park"][0], picked_by_name="박엣지", picked_at=now,
                                 updated_at=now))

    out = _race(pg_engine, pg_app, order_id, key, take, who["foreman"], f"/api/orders/{order_id}/production/steps",
                {"key": "edge", "done": True})
    assert out["status"] == 409 and out["json"]["data"]["code"] == "PART_USES_CARDS"
    assert out["json"]["data"]["left"] == 2
    s = _session(pg_engine)
    try:
        steps = (s.get(Order, order_id).structured_data.get("production") or {}).get("steps") or []
        assert not any(st.get("key") == "edge" and st.get("done") for st in steps)
    finally:
        s.close()


def _crew(pg_engine, order_id, key):
    s = _session(pg_engine)
    try:
        m = s.query(ProductionPartMark).filter_by(order_id=order_id, drawing_key=key, part="edge").one()
        return m.state, [item["name"] for item in mark_crew.crew_of(m)]
    finally:
        s.close()


@pytest.mark.parametrize("mode", ["lock", "plain"])
def test_two_takes_at_once_both_end_up_working(pg_engine, pg_app, monkeypatch, mode):
    order_id, key, who = _seed(pg_engine, mark_state=None)
    a_read = _arm_plain(monkeypatch, mode)

    def take(s, _mark):  # B = 박엣지가 먼저 [작업 시작](새 코드가 쓰는 꼴 — 목록 + 요약 칸)
        now = now_utc_naive()
        crew = [mark_crew.member(who["park"][0], "박엣지", mark_crew.to_iso(now))]
        s.add(ProductionPartMark(order_id=order_id, drawing_key=key, part="edge", holders=crew,
                                 updated_by_user_id=who["park"][0], updated_at=now, **mark_crew.summarize(crew)))

    out = _race(pg_engine, pg_app, order_id, key, take, who["kim"], "/api/production/part-marks",
                {"order_id": order_id, "drawing_key": key, "part": "edge", "action": "take", "seen": "none"}, a_read)
    if mode == "lock":  # 잠금 아래에서 B 의 결과를 보고 같이 작업으로 넘어간다(Q16)
        assert out["status"] == 200, out["json"]
        assert out["json"]["data"]["joined_late"] is True
        assert out["json"]["data"]["notice"] == "박엣지가 먼저 시작했어요."
        assert _crew(pg_engine, order_id, key) == ("NEED", ["박엣지", "김민준"])
    else:  # 음성 대조 — 낡은 '미정' 으로 판정해 새 줄을 넣다가 유일 제약에 걸린다(넘김이 안 일어남)
        assert out["status"] == 409 and out["json"]["data"]["code"] == "MARK_CONFLICT"
        assert _crew(pg_engine, order_id, key) == ("NEED", ["박엣지"])


def _seed_two(pg_engine):
    """첫 장 엣지 = 박엣지 · 김민준이 같이 작업 중(새 코드가 쓰는 꼴 — 목록 + 요약 칸, 둘 다 아직)."""
    order_id, key, who = _seed(pg_engine, mark_state=None)
    s = _session(pg_engine)
    try:
        at = mark_crew.to_iso(now_utc_naive())
        crew = [mark_crew.member(who["park"][0], "박엣지", at), mark_crew.member(who["kim"][0], "김민준", at)]
        s.add(ProductionPartMark(order_id=order_id, drawing_key=key, part="edge", holders=crew, updated_by_user_id=who["kim"][0],
                                 updated_at=now_utc_naive(), **mark_crew.summarize(crew)))
        s.commit()
    finally:
        s.close()
    return order_id, key, who


def _park_finishes(who):
    """연결 B = 박엣지가 자기 몫 [엣지 완료](새 코드가 쓰는 꼴)."""
    def write(s, mark):
        crew = mark_crew.finish(mark_crew.crew_of(mark), who["park"][0], by_uid=who["park"][0], by_name="박엣지", now=now_utc_naive())
        for column, value in mark_crew.summarize(crew).items():
            setattr(mark, column, value)
        mark.holders, mark.updated_by_user_id, mark.updated_at = crew, who["park"][0], now_utc_naive()
    return write


def _finished_by(pg_engine, order_id, key):
    s = _session(pg_engine)
    try:
        m = s.query(ProductionPartMark).filter_by(order_id=order_id, drawing_key=key, part="edge").one()
        return m.state, [(item["name"], item["done_name"]) for item in mark_crew.crew_of(m)]
    finally:
        s.close()


@pytest.mark.parametrize("mode", ["lock", "plain"])
def test_last_two_finish_at_once_both_count(pg_engine, pg_app, monkeypatch, mode):
    """마지막 두 사람이 같은 때 [엣지 완료](B 박엣지 먼저) — A(김민준)는 잠금 아래 B 의 결과 위에서 내 몫을 더해 도면이 완료(DONE)."""
    order_id, key, who = _seed_two(pg_engine)
    a_read = _arm_plain(monkeypatch, mode)
    out = _race(pg_engine, pg_app, order_id, key, _park_finishes(who), who["kim"], "/api/production/part-marks",
                {"order_id": order_id, "drawing_key": key, "part": "edge", "action": "done", "seen": "need", "seen_me": "held"}, a_read)
    assert out["status"] == 200, out["json"]
    if mode == "lock":
        assert out["json"]["data"]["mark"]["state"] == "done"
        assert _finished_by(pg_engine, order_id, key) == ("DONE", [("박엣지", "박엣지"), ("김민준", "김민준")])
    else:  # 음성 대조 — 낡은 '둘 다 아직' 으로 판정해 박엣지 완료를 덮는다(도면이 1/2 완료로 남음)
        assert _finished_by(pg_engine, order_id, key) == ("NEED", [("박엣지", None), ("김민준", "김민준")])


@pytest.mark.parametrize("mode", ["lock", "plain"])
def test_proxy_finish_versus_own_finish(pg_engine, pg_app, monkeypatch, mode):
    """본인 [엣지 완료](B 박엣지 먼저) 대 반장 [대신 완료](A — ``check``) — A 는 남은 사람(김민준) 몫만 반장 이름으로, 박엣지 몫은 본인 이름 그대로."""
    order_id, key, who = _seed_two(pg_engine)
    a_read = _arm_plain(monkeypatch, mode)
    out = _race(pg_engine, pg_app, order_id, key, _park_finishes(who), who["foreman"], "/api/production/part-marks",
                {"order_id": order_id, "drawing_key": key, "part": "edge", "action": "check", "seen": "need", "seen_me": "none"},
                a_read)
    assert out["status"] == 200, out["json"]
    if mode == "lock":
        assert (out["json"]["data"]["proxied"], out["json"]["data"]["mark"]["state"]) == (True, "done")
        assert _finished_by(pg_engine, order_id, key) == ("DONE", [("박엣지", "박엣지"), ("김민준", "박반장")])
        s = _session(pg_engine)
        try:
            payload = s.query(OrderEvent).filter_by(order_id=order_id, event_type="PRODUCTION_PART_MARKED").order_by(
                OrderEvent.id.desc()).first().payload
            assert payload["holder_name"] == "김민준"  # 바뀐 기록 '대신' 대상 = 대신 완료된 남만
        finally:
            s.close()
    else:  # 음성 대조 — 낡은 모습으로 둘 다 반장 이름으로 덮는다(박엣지 본인 완료가 사라짐)
        assert _finished_by(pg_engine, order_id, key) == ("DONE", [("박엣지", "박반장"), ("김민준", "박반장")])


def test_join_while_last_person_releases_becomes_plain_take(pg_engine, pg_app):
    order_id, key, who = _seed(pg_engine, mark_state="NEED")

    def release(s, mark):  # B = 박엣지(유일한 사람)가 [시작 취소]
        mark.state, mark.picked_by_user_id, mark.picked_by_name, mark.picked_at, mark.holders = "NONE", None, None, None, []

    out = _race(pg_engine, pg_app, order_id, key, release, who["choi"], "/api/production/part-marks",
                {"order_id": order_id, "drawing_key": key, "part": "edge", "action": "join", "seen": "need",
                 "seen_me": "none"})
    assert out["status"] == 200, out["json"]
    assert (out["json"]["data"]["joined_late"], out["json"]["data"]["notice"]) == (False, None)  # 판결 1 — 글 없음
    assert _crew(pg_engine, order_id, key) == ("NEED", ["최가은"])


@pytest.mark.parametrize("mode", ["lock", "plain"])
def test_lead_direct_done_on_unseen_versus_take(pg_engine, pg_app, monkeypatch, mode):
    """반장이 미정 도면에 [엣지 완료](A — ``check`` · 본 상태 none, 사장님 2026-11-27) 대 박엣지 [작업 시작](B 먼저) — A 는 잠금 아래
    B 의 결과를 보고 대신 완료(판결 2 그대로 — 반장은 목록에 안 들어감, 박엣지 몫을 반장 이름으로 완료)."""
    order_id, key, who = _seed(pg_engine, mark_state=None)
    a_read = _arm_plain(monkeypatch, mode)

    def take(s, _mark):  # B = 박엣지가 먼저 [작업 시작](새 코드가 쓰는 꼴 — 목록 + 요약 칸)
        now = now_utc_naive()
        crew = [mark_crew.member(who["park"][0], "박엣지", mark_crew.to_iso(now))]
        s.add(ProductionPartMark(order_id=order_id, drawing_key=key, part="edge", holders=crew,
                                 updated_by_user_id=who["park"][0], updated_at=now, **mark_crew.summarize(crew)))

    out = _race(pg_engine, pg_app, order_id, key, take, who["foreman"], "/api/production/part-marks",
                {"order_id": order_id, "drawing_key": key, "part": "edge", "action": "check", "seen": "none", "seen_me": "none"},
                a_read)
    if mode == "lock":
        assert out["status"] == 200, out["json"]
        assert (out["json"]["data"]["proxied"], out["json"]["data"]["mark"]["state"]) == (True, "done")
        assert _finished_by(pg_engine, order_id, key) == ("DONE", [("박엣지", "박반장")])
    else:  # 음성 대조 — 낡은 '미정' 으로 판정해 새 줄을 넣다가 유일 제약에 걸린다(대신 완료로 안 넘어감)
        assert out["status"] == 409 and out["json"]["data"]["code"] == "MARK_CONFLICT"
        assert _crew(pg_engine, order_id, key) == ("NEED", ["박엣지"])
