"""직원이 붙인 사진의 설명 뽑기(설계서 17.6.1 (d) · (f) 시험 5 · 사장님 결정 D94) — 15분 바퀴만 · 스위치 · 확인 칸 · 상한 · 돈 · 가림.

합성 그림(Pillow 평면도)과 가짜 저장소 · 가짜 모델(구조화 출력)만 쓴다 — 네트워크 · 손님 사진 · 금액 없음. 전화 꼴 글은 실행 때
만든다(공개 저장소에 전화 꼴 숫자를 두지 않는다). 시각은 2026-11 KST(11-02 월).
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.exc import OperationalError

from db import db_session
from foms.services.cs_agent import brain_spend, learning_pass, loop, photo_desc, turns
from foms.services.cs_agent import settings as st
from foms.services.cs_agent.edit_detail_settings import PHOTO_DESC_FIELD
from models import CsAgentTurn, CsAgentTurnPhoto, SystemSetting
from tests.domains.test_cs_drafting import channel  # noqa: F401 — fixture(승인 지식 · 두뇌 env · 진짜 SDK 막기)
from tests.support.cs_agent_fakes import FakeAnthropic, FakeClock, at, keys, make_reader, naive  # noqa: F401
from tests.support.cs_image_support import encoded, plan_image

ROOT = Path(__file__).resolve().parents[2]
NOW = at(2, 9)
GOOD = {"description": "합성 계산기 화면 캡처 — 선반 깊이 350mm 칸이 보인다."}
PHONE = "-".join(("01" + "0", "5" * 4, "6" * 4))  # 실행 때 만드는 전화 꼴


class FakeStore:
    """저장소 대역 — key → 바이트(읽은 key 를 남긴다)."""

    def __init__(self, data: bytes) -> None:
        self.data, self.reads = data, []

    def read_file_bytes(self, key):
        self.reads.append(key)
        return self.data


def panel(**extra):
    db_session.merge(SystemSetting(setting_key=st.SETTINGS_KEY, setting_value={
        **st.DEFAULTS, PHOTO_DESC_FIELD: True, "learning_cap_usd_panel": "5.00", **extra}))
    db_session.merge(SystemSetting(setting_key=turns.SWITCH_KEY, setting_value={"loop": "on", "draft": "memo"}))
    db_session.commit()


def edited_turn(n: int = 1) -> int:
    row = CsAgentTurn(brand="LAHOM", chat_id=f"uc-{n}", last_user_message_id=f"m-{n}", state="posted",
                      outcome="edited", edit_reason="wrong_fact", edit_detail_masked="합성 이유 — 선반 깊이를 틀렸다",
                      sent_by_user_id=n, sent_at=naive(at(2, 8, 55)))
    db_session.add(row)
    db_session.commit()
    return row.id


def photo(turn_id: int, seq: int = 1, *, no_personal: bool = True, state: str = "pending", desc_at=None) -> int:
    row = CsAgentTurnPhoto(turn_id=turn_id, seq=seq, storage_key=f"cs-agent/edit-photos/{turn_id}/p{seq}.jpg",
                           content_type="image/jpeg", bytes=1000, width=1600, height=1200, sha256=f"{seq:064x}",
                           no_personal=no_personal, desc_state=state, desc_at=desc_at, uploaded_by=1,
                           created_at=naive(at(2, 8, 56)))
    db_session.add(row)
    db_session.commit()
    return row.id


def fresh(photo_id: int) -> CsAgentTurnPhoto:
    db_session.expire_all()
    return db_session.get(CsAgentTurnPhoto, photo_id)


def run(client, store=None, **kw):
    return photo_desc.run_photo_desc(db_session, now=NOW, client=client,
                                     storage=store or FakeStore(encoded(plan_image())), **kw)


@pytest.fixture
def ready(channel):  # noqa: F811
    panel()
    return channel


@pytest.fixture
def no_face(monkeypatch):
    monkeypatch.setattr(photo_desc, "_faces", lambda _image: None)


# ── 한 장 — 설명 · 돈 두 줄 ───────────────────────────────────────────────
def test_a_confirmed_photo_gets_a_masked_description_and_both_ledgers_are_charged(ready):
    photo_id = photo(edited_turn())
    client = FakeAnthropic(GOOD)
    counts = run(client)  # 진짜 얼굴 거르기(YuNet)를 지난다 — 합성 평면도엔 얼굴이 없다
    row = fresh(photo_id)
    assert counts["done"] == 1 and row.desc_state == "done" and row.desc_masked == GOOD["description"]
    assert row.desc_at is not None
    (params,) = client.params
    assert params["model"] == st.DEFAULTS["photo_desc_model"] and params["max_tokens"] == photo_desc.MAX_TOKENS
    assert params["output_config"]["effort"] == "low"
    image = params["messages"][0]["content"][0]
    assert image["type"] == "image" and image["source"]["media_type"] == "image/jpeg"
    task = params["messages"][0]["content"][1]["text"]
    assert "wrong_fact" in task and "합성 이유 — 선반 깊이를 틀렸다" in task
    learning = brain_spend.today_spend(db_session, now=NOW, key=brain_spend.LEARNING_SPEND_KEY)
    daily = brain_spend.today_spend(db_session, now=NOW)
    assert Decimal(learning["usd"]) > 0 and learning["calls"] == 1 and Decimal(learning["reserved"]) == 0
    assert Decimal(daily["usd"]) == Decimal(learning["usd"]) and Decimal(daily["reserved"]) == 0


# ── 부르지 않는 때 ───────────────────────────────────────────────────────
@pytest.mark.parametrize("change", ["switch_off", "emergency_stop", "draft_off", "no_learning_cap"])
def test_nothing_is_sent_when_any_gate_is_closed(ready, no_face, change):
    if change == "switch_off":
        panel(**{PHOTO_DESC_FIELD: False})
    elif change == "no_learning_cap":
        panel(learning_cap_usd_panel=None)
    else:
        db_session.merge(SystemSetting(setting_key=turns.SWITCH_KEY, setting_value={
            "loop": "off" if change == "emergency_stop" else "on", "draft": "off" if change == "draft_off" else "memo"}))
        db_session.commit()
    photo_id = photo(edited_turn())
    client = FakeAnthropic(GOOD)
    store = FakeStore(encoded(plan_image()))
    assert run(client, store) == {"off": change}
    assert client.params == [] and store.reads == [] and fresh(photo_id).desc_state == "pending"


def test_a_photo_without_the_staff_confirmation_is_never_sent(ready, no_face):
    turn_id = edited_turn()
    unchecked = photo(turn_id, 1, no_personal=False)
    client = FakeAnthropic(GOOD)
    store = FakeStore(encoded(plan_image()))
    assert run(client, store)["done"] == 0
    assert client.params == [] and store.reads == [] and fresh(unchecked).desc_state == "pending"


def test_a_face_or_a_broken_face_check_skips_without_a_call(ready, monkeypatch):
    first, second = photo(edited_turn(1)), photo(edited_turn(2))
    codes = iter(["skipped_face", "skipped_face_check"])
    monkeypatch.setattr(photo_desc, "_faces", lambda _image: next(codes))
    client = FakeAnthropic(GOOD)
    assert run(client)["skipped"] == 2 and client.params == []
    assert (fresh(first).desc_state, fresh(second).desc_state) == ("skipped", "skipped")


# ── 결과 꼴 ─────────────────────────────────────────────────────────────
def test_a_phone_shaped_description_is_a_leak_and_keeps_no_text(ready, no_face):
    photo_id = photo(edited_turn())
    counts = run(FakeAnthropic({"description": f"합성 화면에 {PHONE} 번호가 보인다."}))
    row = fresh(photo_id)
    assert counts["leak"] == 1 and (row.desc_state, row.desc_masked) == ("leak", None)


@pytest.mark.parametrize("answer, state", [({"description": "  "}, "skipped"), ({"wrong": 1}, "failed")])
def test_empty_or_broken_answers_are_not_kept(ready, no_face, answer, state):
    photo_id = photo(edited_turn())
    assert run(FakeAnthropic(answer))[state] == 1
    assert (fresh(photo_id).desc_state, fresh(photo_id).desc_masked) == (state, None)


def test_an_unreadable_original_fails_without_a_call(ready, no_face):
    photo_id = photo(edited_turn())
    client = FakeAnthropic(GOOD)
    assert run(client, FakeStore(b"not an image"))["failed"] == 1 and client.params == []
    assert fresh(photo_id).desc_state == "failed"


# ── 상한 ────────────────────────────────────────────────────────────────
def test_ten_photos_per_pass(ready, no_face):
    turn_ids = [edited_turn(n) for n in range(1, 4)]
    ids = [photo(turn_ids[i % 3], i // 3 + 1) for i in range(12)]
    client = FakeAnthropic(GOOD)
    assert run(client)["done"] == photo_desc.PER_PASS == 10 and len(client.params) == 10
    assert sum(fresh(i).desc_state == "pending" for i in ids) == 2


def test_the_daily_cap_counts_today_in_kst(ready, no_face):
    old_turn, turn_id = edited_turn(1), edited_turn(2)
    for seq in range(1, 11):  # 어제(KST) 설명 10장은 세지 않는다
        photo(old_turn, seq, state="done", desc_at=naive(at(1, 23, 50)))
    for n in range(photo_desc.PER_DAY - 1):  # 오늘 99장
        db_session.add(CsAgentTurnPhoto(turn_id=edited_turn(10 + n), seq=1, storage_key=None, content_type="image/jpeg",
                                        bytes=1, width=1, height=1, sha256="0" * 64, no_personal=True,
                                        desc_state="done", desc_at=naive(at(2, 0, 30)), uploaded_by=1))
    db_session.commit()
    first, second = photo(turn_id, 1), photo(turn_id, 2)
    client = FakeAnthropic(GOOD)
    assert run(client)["done"] == 1 and len(client.params) == 1
    assert (fresh(first).desc_state, fresh(second).desc_state) == ("done", "pending")
    again = FakeAnthropic(GOOD)
    assert run(again)["halted"] == "daily_cap" and again.params == []


def test_the_pass_stops_after_sixty_seconds(ready, no_face):
    first, second = photo(edited_turn(1)), photo(edited_turn(2))
    ticks = iter([0.0, 0.0, photo_desc.PASS_SECONDS + 1])
    counts = run(FakeAnthropic(GOOD), clock=lambda: next(ticks))
    assert counts["done"] == 1 and counts["halted"] == "time"
    assert (fresh(first).desc_state, fresh(second).desc_state) == ("done", "pending")


def test_the_learning_cap_stops_the_pass_and_leaves_photos_pending(ready, no_face):
    panel(learning_cap_usd_panel="0.00")
    photo_id = photo(edited_turn())
    client = FakeAnthropic(GOOD)
    counts = run(client)
    assert counts["halted"] == brain_spend.DAILY_CAP_REACHED and client.params == []
    assert fresh(photo_id).desc_state == "pending"


# ── 배선 — 15분 바퀴만 ───────────────────────────────────────────────────
def test_the_fast_path_never_describes_photos():
    source = (ROOT / "foms/services/cs_agent/realtime.py").read_text(encoding="utf-8")
    for name in ("photo_desc", "learning_pass", "run_learning", "weekly_fix"):
        assert name not in source, name


@pytest.mark.parametrize("mode, called", [("memo", True), ("off", False)])
def test_the_quarter_hour_pass_runs_learning_only_when_drafting_is_not_off(ready, monkeypatch, mode, called):
    db_session.merge(SystemSetting(setting_key=turns.SWITCH_KEY, setting_value={"loop": "on", "draft": mode}))
    db_session.commit()
    calls = []
    monkeypatch.setattr(loop, "run_drafting", lambda *a, **k: None)
    monkeypatch.setattr(loop, "run_learning", lambda session, **k: calls.append(k) or {"photo_desc": {"done": 0}})
    result = loop.run_pass(db_session, config=loop.LoopConfig(), stop=loop.StopFlag(), now=at(2, 9, 2),
                           reader=make_reader(ready, FakeClock()), clock=lambda: 0.0, is_business_day=lambda _d: True)
    assert result.outcome == "ok" and bool(calls) is called
    assert ("learning" in result.summary()) is called


def test_a_failing_learning_step_is_logged_and_does_not_break_the_pass(ready, monkeypatch, caplog):
    def broken(*_a, **_k):
        raise OperationalError("SELECT 1", {}, Exception("synthetic"))

    monkeypatch.setattr(learning_pass, "run_photo_desc", broken)
    monkeypatch.setattr(learning_pass, "run_weekly_fix", lambda *_a, **_k: {"off": "not_window"})
    with caplog.at_level("WARNING", logger="foms.services.cs_agent.learning_pass"):
        out = learning_pass.run_learning(db_session, now=NOW, stop_check=lambda: None)
    assert out == {"photo_desc": {"error": "OperationalError"}}
    assert "photo_desc 실패" in caplog.text and "code=OperationalError" in caplog.text


def test_switched_off_learning_steps_leave_the_pass_summary_as_before(ready):
    panel(**{PHOTO_DESC_FIELD: False})
    assert learning_pass.run_learning(db_session, now=NOW, stop_check=lambda: None) is None
