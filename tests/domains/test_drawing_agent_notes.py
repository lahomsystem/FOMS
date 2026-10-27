"""AI 도면팀원 주간 노트 · 질문 답하기 · 노트 화면 · 밤 단계 시험.

설계 정본: docs/plans/2026-10-27-drawing-ai-teammate-spec.md §2 A3 · §4
- 그 주(월~일, KST) 노트는 한 번만 — 다시 불러도 None, 다음 주에 새로 만든다.
- 물어볼 것 = 지난 4주 사람이 고른 아주 닮은 두 그림(0.95, 같은 보기 내부/도어는 0.985)인데 종류가 다른 쌍, 물은 쌍은 다시 안 묻는다.
- 답 a/b 는 틀린 쪽 기억 이름표를 맞추고, 답을 바꾸면 앞 답이 바꾼 것을 먼저 되돌린다. both 는 기록만.
- AI 도면팀원 계정은 로그인 못 함(비활성) · 팀 없음. 알림은 도면팀 앱 안 알림, 누르면 노트 화면.
"""

import hashlib
import shutil
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.api.notifications import _resolve_notification_deep_link
from foms.services import drawing_agent_digest as agent_digest
from foms.services import drawing_agent_notes as notes
from foms.services.drawing_agent_account import AGENT_NAME, AGENT_USERNAME
from models import DrawingPartMemory, Notification, NotificationUserState, Order, User
from tools.cron import drawing_agent_note as cron_note
from tools.cron.nightly import NIGHTLY_STEPS

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 10, 27, 1, 0, 0)          # 화요일 10:00 KST — 이번 주 월요일 = 10-26
IN_WEEK = datetime(2026, 10, 20, 3, 0, 0)      # 지난주(10-19 ~ 10-25 KST) 안
TOKEN = "note-token-" + "z" * 40
_SEQ = [0]


def _user(team="DRAWING", role="STAFF"):
    _SEQ[0] += 1
    user = User(username=f"note-{_SEQ[0]}", password=generate_password_hash("x"), role=role, team=team,
                name=f"노트사람{_SEQ[0]}", is_active=True)
    db_session.add(user)
    db_session.commit()
    # 요청이 끝나면 세션이 닫혀 ORM 객체가 떨어진다 — 쓸 값만 바로 옮겨 둔다
    return SimpleNamespace(id=user.id, username=user.username, role=user.role, team=user.team, name=user.name)


def _login(client, user):
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _order(sheets=None):
    order = Order(received_date=date.today().strftime("%Y-%m-%d"), customer_name="노트고객", phone="010-0000-0000",
                  address="대구", product="붙박이장", status="DRAWING", is_erp_order=True,
                  structured_data={"drawing_wizard": {"v": 1, "sheets": sheets or []}})
    db_session.add(order)
    db_session.commit()
    return order.id


def _vec(seed, base=None, noise=0.0):
    rng = np.random.default_rng(seed)
    v = base.copy() if base is not None else rng.normal(size=768)
    if noise:
        v = v + rng.normal(size=768) * noise
    return (v / np.linalg.norm(v)).astype(np.float32)


def _mem(order_id, key, vec, label, *, src="user", ai=None, at=IN_WEEK, user_id=None):
    row = DrawingPartMemory(order_id=order_id, asset_key=f"orders/{order_id}/drawing_wizard/assets/{key}.png",
                            feat=vec.astype("<f2").tobytes(), feat_v="f1-dv2s-8b1f", ai=ai, conf=0.6, head="h1",
                            label=label, src=src, active=True, created_by=user_id, updated_by=user_id,
                            created_at=at, updated_at=at)
    db_session.add(row)
    db_session.commit()
    return row.id


def _seed():
    """닮은 두 그림(다른 종류) 한 쌍 + 내부/도어 닮음 0.96(안 물음) + AI 줄 + 검수 메모 기록 시트."""
    worker = _user()
    review = [{"id": "s1", "name": "a", "form": {}, "objects": [],
               "review": {"off": ["dup"], "seen": ["dup", "head:phone", "head:address", "unsorted", "김비밀:x"]}}]
    o1, o2 = _order(review), _order()
    base = _vec(1)
    a = _mem(o1, "a", base, "서랍 단면", ai="부품 상세", user_id=worker.id)
    b = _mem(o2, "b", _vec(2, base, 0.005), "부품 상세", ai="부품 상세", user_id=worker.id)
    door = _vec(3)
    _mem(o1, "c", door, "정면·내부", ai="정면·도어", user_id=worker.id)
    _mem(o2, "d", _vec(4, door, 0.012), "정면·도어", ai="정면·도어", user_id=worker.id)
    _mem(o1, "e", _vec(5), "사진", src="ai", ai="사진")
    return worker, a, b


def test_week_helpers():
    assert notes.week_id(NOW) == "2026-W44"
    assert notes.week_start(NOW) == datetime(2026, 10, 25, 15, 0, 0)   # 10-26 00:00 KST
    assert notes.week_title(notes.week_start(NOW)) == "10월 3주"
    assert notes.week_id(datetime(2026, 10, 25, 14, 59)) == "2026-W43"   # 10-25 23:59 KST 는 지난주


def test_weekly_note_once_per_week_with_question_and_team_alert(app):
    worker, a, b = _seed()
    note = notes.create_weekly_note(db_session, NOW)
    db_session.commit()
    assert note["id"] == "2026-W44" and note["title"] == "10월 3주"
    assert note["stats"]["labels"] == 4 and note["stats"]["agree"] == 2 and note["stats"]["changed"] == 2
    assert note["stats"]["top_changes"] == [["부품 상세", "서랍 단면", 1], ["정면·도어", "정면·내부", 1]]
    assert note["review"] == {"dup": {"seen": 1, "off": 1}, "head": {"seen": 1, "off": 0}, "unsorted": {"seen": 1, "off": 0}}
    assert [q["id"] for q in note["questions"]] == ["q1"]   # 내부/도어 쌍은 0.985 아래라 안 묻는다
    q = note["questions"][0]
    assert {q["a"]["mem"], q["b"]["mem"]} == {a, b} and q["sim"] >= 0.95 and q["answer"] is None
    assert note["changes"] == [c for c in notes.load_changes() if c["date"] >= "2026-10-19"][-10:] and note["changes"]
    agent = db_session.query(User).filter(User.username == AGENT_USERNAME).one()
    assert agent.name == AGENT_NAME and agent.is_active is False and agent.team is None
    notif = db_session.query(Notification).filter(Notification.notification_type == notes.NOTIFICATION_TYPE).one()
    assert notif.target_team == "DRAWING" and notif.order_id is None and notif.created_by_user_id == agent.id
    assert notif.title == "AI 도면팀원 노트 · 10월 3주" and "물어볼 것 1개" in notif.message
    states = {s.user_id for s in db_session.query(NotificationUserState).filter(NotificationUserState.notification_id == notif.id)}
    assert worker.id in states and agent.id not in states
    assert notes.create_weekly_note(db_session, NOW + timedelta(days=2)) is None   # 같은 주
    later = notes.create_weekly_note(db_session, NOW + timedelta(days=7))
    db_session.commit()
    assert later["id"] == "2026-W45" and later["questions"] == []   # 물은 쌍은 다시 안 묻는다
    assert len(notes.load_book(db_session)["notes"]) == 2


def test_answer_moves_wrong_label_and_rewinds_on_change(app):
    worker, a, b = _seed()
    notes.create_weekly_note(db_session, NOW)
    db_session.commit()
    q = notes.load_book(db_session)["notes"][0]["questions"][0]
    left, right = q["a"], q["b"]

    def labels():
        db_session.expire_all()
        return {r.id: r.label for r in db_session.query(DrawingPartMemory).filter(DrawingPartMemory.id.in_([a, b]))}

    notes.answer(db_session, "2026-W44", "q1", "a", worker)
    db_session.commit()
    assert labels() == {left["mem"]: left["label"], right["mem"]: left["label"]}
    notes.answer(db_session, "2026-W44", "q1", "b", worker)
    db_session.commit()
    assert labels() == {left["mem"]: right["label"], right["mem"]: right["label"]}
    notes.answer(db_session, "2026-W44", "q1", "both", worker)
    db_session.commit()
    assert labels() == {left["mem"]: left["label"], right["mem"]: right["label"]}
    saved = notes.load_book(db_session)["notes"][0]["questions"][0]["answer"]
    assert saved["choice"] == "both" and saved["by"] == worker.id and saved["name"] == worker.name
    for args, status in ((("2026-W44", "q9", "a"), 404), (("2026-W01", "q1", "a"), 404), (("2026-W44", "q1", "c"), 400)):
        with pytest.raises(notes.NoteError) as err:
            notes.answer(db_session, *args, worker)
        assert err.value.status == status


def test_answer_api_permissions_and_shape(client):
    worker, a, b = _seed()
    notes.create_weekly_note(db_session, NOW)
    db_session.commit()
    url = "/api/drawing-agent/notes/2026-W44/answer"
    assert client.post(url, json={"qid": "q1", "choice": "a"}).status_code == 401
    _login(client, _user(team="SALES"))
    assert client.post(url, json={"qid": "q1", "choice": "a"}).status_code == 403
    _login(client, worker)
    for body in ({"qid": "q1", "choice": "x"}, {"qid": "1", "choice": "a"}, {"choice": "a"}):
        assert client.post(url, json=body).status_code == 400
    assert client.post("/api/drawing-agent/notes/bad/answer", json={"qid": "q1", "choice": "a"}).status_code == 400
    assert client.post("/api/drawing-agent/notes/2026-W01/answer", json={"qid": "q1", "choice": "a"}).status_code == 404
    resp = client.post(url, json={"qid": "q1", "choice": "both"})
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["data"]["question"] == {"id": "q1", "answer": {"choice": "both", "text": notes.CHOICE_TEXT["both"],
                                                                       "name": worker.name}}
    admin = _user(team=None, role="ADMIN")
    _login(client, admin)
    assert client.post(url, json={"qid": "q1", "choice": "a"}).status_code == 200


def test_note_page_shows_questions_and_answer_buttons_for_team_only(client):
    worker, a, b = _seed()
    _login(client, worker)
    empty = client.get("/erp/drawing-workbench/agent-note").get_data(as_text=True)
    assert "아직 노트가 없어요" in empty
    notes.create_weekly_note(db_session, NOW)
    db_session.commit()
    html = client.get("/erp/drawing-workbench/agent-note").get_data(as_text=True)
    assert "AI 도면팀원 노트" in html and "10월 3주" in html and "물어볼 것" in html
    assert "/drawing-wizard/asset-raw?key=orders%2F" in html and 'data-can-answer="1"' in html
    assert html.count('class="dan-btn"') == 3 and "agent-note.js" in html and "agent-note.css" in html
    assert "검수 메모" in html and "같은 그림 두 번 보인 시트 1 · 끈 시트 1" in html
    assert ' style="' not in html.split('<main class="dan-page"')[1].split("</main>")[0]   # 인라인 스타일 금지
    _login(client, _user(team="SALES"))
    other = client.get("/erp/drawing-workbench/agent-note").get_data(as_text=True)
    assert 'data-can-answer="0"' in other and 'class="dan-btn"' not in other and "도면팀이 답하면" in other


def test_digest_notes_hide_keys_and_names(client, monkeypatch):
    worker, a, b = _seed()
    notes.create_weekly_note(db_session, NOW)
    db_session.commit()
    notes.answer(db_session, "2026-W44", "q1", "a", worker)
    db_session.commit()
    monkeypatch.setenv(agent_digest.TOKEN_ENV, hashlib.sha256(TOKEN.encode()).hexdigest())
    body = client.get("/api/drawing-agent/digest?kind=notes", headers={"Authorization": f"Bearer {TOKEN}"}).get_json()["data"]
    (note,) = body["items"]
    q = note["questions"][0]
    assert len(q["a"]["key"]) == 16 and "orders/" not in str(body) and worker.name not in str(body)
    assert q["answer"]["choice"] == "a" and q["answer"]["by"].startswith("p") and note["stats"]["labels"] == 4


def test_deep_link_and_cron_step(app):
    link = _resolve_notification_deep_link(Notification(notification_type="DRAWING_AGENT_NOTE", title="t"), {})
    assert link["deep_link_url"] == "/erp/drawing-workbench/agent-note"
    steps = {s.name: (s.script, s.args) for s in NIGHTLY_STEPS}
    assert steps["drawing_agent_note"] == ("tools/cron/drawing_agent_note.py", ("--apply",))
    _seed()
    dry = cron_note.run(apply=False, session=db_session, now=NOW)
    assert dry == {"created": False, "week": "2026-W44", "reason": "dry-run", "questions": 1, "labels": 4}
    assert notes.load_book(db_session)["notes"] == []
    assert cron_note.run(apply=True, session=db_session, now=NOW) == {"created": True, "week": "2026-W44", "questions": 1, "labels": 4}
    assert cron_note.run(apply=True, session=db_session, now=NOW) == {"created": False, "week": "2026-W44", "reason": "already"}


def test_changes_file_and_script_checks():
    items = notes.load_changes()
    assert items and all(set(i) >= {"date", "text"} for i in items)
    js = ROOT / "static/js/drawing/agent-note.js"
    node = shutil.which("node")
    assert node
    proc = subprocess.run([node, "--check", str(js)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    src = js.read_text(encoding="utf-8")
    assert len(src.splitlines()) < 300 and "data.success" in src and "jQuery" not in src and "$(" not in src


def test_test_and_trashed_orders_stay_out_of_numbers_and_questions(app):
    """시험 주문(CLAUDE-TEST-) · 휴지통 주문 줄은 주간 노트 숫자 · 물어볼 것에서 빠진다(설계서 §9) — 시험 그림 두 장이
    닮았는데 종류가 달라도 도면팀에 묻지 않는다."""
    worker = _user()
    t1, t2, gone = _order(), _order(), _order()
    for oid in (t1, t2):
        db_session.get(Order, oid).customer_name = "CLAUDE-TEST-노트"
    db_session.commit()
    base = _vec(21)
    _mem(t1, "a", base, "서랍 단면", ai="부품 상세", user_id=worker.id)
    _mem(t2, "b", _vec(22, base, 0.005), "부품 상세", ai="부품 상세", user_id=worker.id)
    _mem(gone, "c", _vec(23), "정면·도어", ai="정면·내부", user_id=worker.id)
    order = db_session.get(Order, gone)
    order.status, order.deleted_at = "DELETED", "2026-10-27 12:00:00"
    db_session.commit()
    start = notes.week_start(NOW) - timedelta(days=7)
    stats = notes.label_stats(db_session, start, notes.week_start(NOW))
    assert stats["labels"] == 0 and stats["new_rows"] == 0 and stats["top_changes"] == []
    assert notes.find_questions(db_session, NOW, []) == []


def test_review_numbers_leave_out_test_and_trashed_orders(app):
    """검수 메모 숫자도 시험 · 휴지통 주문 시트는 세지 않는다(설계서 §9) — 같은 기록을 가진 세 주문 중 진짜 주문 하나만 센다."""
    review = [{"id": "s1", "name": "a", "form": {}, "objects": [],
               "review": {"off": ["dup"], "seen": ["dup", "head:phone"]}}]
    real, test, gone = _order(review), _order(review), _order(review)
    db_session.get(Order, test).customer_name = "CLAUDE-TEST-검수"
    order = db_session.get(Order, gone)
    order.status, order.deleted_at = "DELETED", "2026-10-27 12:00:00"
    db_session.commit()
    for oid, key, seed in ((real, "a", 31), (test, "b", 32), (gone, "c", 33)):
        _mem(oid, key, _vec(seed), "사진", src="ai", ai="사진")
    start = notes.week_start(NOW) - timedelta(days=7)
    assert notes.review_stats(db_session, start, notes.week_start(NOW)) == {
        "dup": {"seen": 1, "off": 1}, "head": {"seen": 1, "off": 0}}
