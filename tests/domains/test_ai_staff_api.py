"""AI 직원 API(설계서 2026-11-14-foms-graft 3.10, 머리 ``/api/ai-staff``) — 답 꼴 · 캐시 머리글 · 목록 · 자세히 · 수준 저장.

완료 기준:
- 목록: 직원 다섯 · 상태 꼬리표(운영 AI · 일정 AI '시험 중') · 고치기 칸.
- 자세히: 모델 이름은 설정 값 · 상담 AI 주문 읽기 '있음'(새로 붙음 아님) · 규칙 직원 '시험 중 · 규칙' · 할 일 줄(수준 · 고를 값 ·
  2주 승인율 · 건수 · 규칙 메모) · 승인율 계산(14일 안 결정만 · 고쳐서 승인도 승인 · 결정 0 은 None) · 상담 초안 '그대로 보냄' ·
  최근 실패 · 실행 기록(상담 AI 는 전체 시간만 · 훑기는 단계마다) · 시공 팀 · 인원 글 없음(D211) · 손님 글 없음.
- 수준 저장: 저장 → 다음 읽기에 반영 · 꼴 틀림 400(칸 이름) · 모르는 직원 404.
합성 계정 · 합성 주문 · 합성 차례만. 바깥 호출 없음(훑기는 알림톡을 보내지 않는다).
"""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy import event
from werkzeug.security import generate_password_hash

from db import db_session
from foms.persistence.graft.models import ErpActionProposal
from foms.services.ai_staff import sweeps
from foms.services.ai_staff.levels import levels_view
from foms.services.ai_staff.views import staff_detail
from foms.services.brain.scope import viewer_of
from foms.services.cs_agent.settings_field import MODEL_NAMES
from foms.services.datetime_kst import now_utc_naive
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.graft_flags import FLAGS
from models import CsAgentTurn, Order, User

BASE = "/api/ai-staff"


@pytest.fixture
def switches(monkeypatch):
    """접목판 스위치를 모두 끈 뒤 새 화면만 모두에게 켠다."""
    for env in FLAGS.values():
        monkeypatch.delenv(f"{env}_ENABLED", raising=False)
        monkeypatch.delenv(f"{env}_COHORT", raising=False)
    monkeypatch.setenv("FOMS_GRAFT_BRAIN_UI_ENABLED", "1")
    monkeypatch.setenv("FOMS_GRAFT_BRAIN_UI_COHORT", "all")
    return monkeypatch


@pytest.fixture
def client(app, switches):
    admin = User(username="as_admin", password=generate_password_hash("pw"), role="ADMIN", name="합성 관리자",
                 is_active=True)
    db_session.add(admin)
    db_session.commit()
    test_client = app.test_client()
    with test_client.session_transaction() as sess:
        sess["user_id"] = admin.id
    return test_client


def _data(resp, status=200):
    assert resp.status_code == status, resp.get_data(as_text=True)
    assert resp.headers["Cache-Control"] == "private, no-store"
    body = resp.get_json()
    assert set(body) == {"success", "data", "error"}
    return body


def _order(stage: str = "DRAWING", stage_days: float = 3) -> Order:
    sd = {"workflow": {"stage": stage,
                       "stage_updated_at": (now_utc_naive() - datetime.timedelta(days=stage_days)).isoformat()}}
    order = Order(received_date="2030-01-01", customer_name="합성손님", phone="010-0000-0000", address="합성 주소",
                  product="합성 품목", status=stage, is_erp_order=True, structured_data=sd)
    sync_erp_flat_columns(order, sd)
    db_session.add(order)
    db_session.commit()
    return order


def _decided(agent: str, action: str, decided: str, *, days_ago: float = 1, status: str = "executed",
             order_id: int = 1, error_code=None) -> None:
    now = now_utc_naive()
    db_session.add(ErpActionProposal(
        action=action, proposed_by=f"agent:{agent}", order_id=order_id, params={}, preview=[], reason="합성", evidence=[],
        level=1, status=status, dedupe_key=f"{action}:{order_id}:{decided}:{days_ago}", decided_by=1,
        decided_at=now - datetime.timedelta(days=days_ago), decided_action=decided, error_code=error_code,
        created_at=now - datetime.timedelta(days=days_ago)))
    db_session.commit()


def _duty(data, key):
    return next(row for row in data["duties"] if row["key"] == key)


def test_list_has_five_agents_with_status_tags(client):
    body = _data(client.get(BASE))
    assert body["success"] is True and body["error"] is None
    agents = {item["key"]: item for item in body["data"]["agents"]}
    assert list(agents) == ["cs", "drawing", "ask", "ops", "schedule"]
    assert agents["ops"]["tag"] == {"text": "시험 중", "tone": "warning"} and agents["schedule"]["trial"] is True
    assert agents["cs"]["tag"] == {"text": "수준 1", "tone": "primary"}
    assert agents["ask"]["tag"] == {"text": "수준 0", "tone": "success"}  # 무채색 꼬리표 없음
    assert agents["cs"]["sub"].startswith("있음 · ") and agents["ops"]["sub"].startswith("새로 · ")
    assert body["data"]["can_edit"] is True


def test_cs_detail_model_reads_tools_and_draft_rate(client):
    now = now_utc_naive()
    for n, outcome in enumerate(("as_is", "as_is", "edited")):
        db_session.add(CsAgentTurn(brand="LAHOM", chat_id=f"c{n}", last_user_message_id=f"m{n}", state="posted",
                                   send_state="sent", sent_at=now, outcome=outcome, latency_ms=4000 + n * 1000,
                                   model="claude-sonnet-x", check_codes=[], created_at=now - datetime.timedelta(hours=1)))
    db_session.commit()
    data = _data(client.get(f"{BASE}/cs"))["data"]
    assert data["model"] in MODEL_NAMES.values()  # 설정 값 그대로(처음 값)
    assert data["status"] == {"text": "있음 · 수준 1 초안", "tone": "success"}
    reads = [item["label"] for item in data["reads"]]
    assert "주문 · 방문 읽기" in reads
    assert not any(tool["new"] for tool in data["tools"] if tool["name"] == "erp.order.find")  # 11-12 부터 있음
    draft = _duty(data, "cs_draft")
    assert draft["rate"] == {"days": 14, "decided": 3, "approved": 2, "pct": 67} and draft["count"] == 3
    assert draft["editable"] is False and draft["note"] == "'그대로 보냄' 비율"
    assert _duty(data, "send_measure_alimtalk")["level_label"] == "못 함"
    assert data["usage"]["avg_ms"] == 5000 and data["usage"]["count"] == 3 and "cost" in data["usage"]
    run = data["run"]
    assert run["per_step"] is False and run["total_ms"] == 6000
    assert [step["tool"] for step in run["steps"]][:1] == ["cs.thread.read"]
    assert all(step["ms"] is None for step in run["steps"])


def test_cs_run_shows_a_proposal_step_from_the_turn(client):
    turn = CsAgentTurn(brand="HAUD", chat_id="c9", last_user_message_id="m9", state="posted", latency_ms=7200,
                       model="claude-sonnet-x", check_codes=["date_promise"])
    db_session.add(turn)
    db_session.commit()
    db_session.add(ErpActionProposal(action="move_construction", proposed_by="agent:cs", order_id=5, params={},
                                     preview=[], reason="합성", evidence=[], level=2, status="open",
                                     dedupe_key="move_construction:5:x", source_kind="cs_turn", source_ref=str(turn.id),
                                     created_at=now_utc_naive()))
    db_session.commit()
    run = _data(client.get(f"{BASE}/cs"))["data"]["run"]
    assert run["proposals"] == 1 and run["total_ms"] == 7200
    details = [step["detail"] for step in run["steps"]]
    assert "걸림 1개" in details and "방문 옮기기(시공) · 수준 2" in details


def test_rule_agent_detail_rate_counts_and_failures(client):
    _decided("schedule", "schedule_construction", "approve")
    _decided("schedule", "schedule_construction", "edit_approve")
    _decided("schedule", "schedule_construction", "reject", status="rejected")
    _decided("schedule", "schedule_construction", "approve", days_ago=20)  # 2주 밖
    _decided("schedule", "schedule_construction", "approve", status="failed", error_code="ACTION_FAILED", order_id=9)
    data = _data(client.get(f"{BASE}/schedule"))["data"]
    assert data["status"] == {"text": "시험 중 · 규칙", "tone": "warning"} and data["model"] is None
    duty = _duty(data, "schedule_construction")
    assert duty["rate"] == {"days": 14, "decided": 4, "approved": 3, "pct": 75}
    assert duty["count"] == 4 and duty["note"].startswith("규칙 S1 — ")
    assert [c["value"] for c in duty["choices"]] == [0, 1, 2] and duty["editable"] is True
    assert data["failures"][0]["label"] == "시공 잡기 — #9" and data["failures"][0]["href"] == "/erp/orders/9"
    assert data["failures"][0]["code"] == "ACTION_FAILED"
    ops = _data(client.get(f"{BASE}/ops"))["data"]
    stage = _duty(ops, "advance_stage")
    assert stage["level"] == 0 and stage["rate"] == {"days": 14, "decided": 0, "approved": 0, "pct": None}
    assert stage["note"].startswith("규칙 O2 — ") and stage["count"] == 0
    assert ops["run"] is None and ops["failures"] == []


def test_sweep_run_shows_per_step_times(client, switches):
    switches.setenv("FOMS_GRAFT_PROPOSERS_ENABLED", "1")
    _order("DRAWING", stage_days=3)
    sweeps.run_sweep(db_session)
    db_session.commit()
    run = _data(client.get(f"{BASE}/ops"))["data"]["run"]
    assert run["per_step"] is True and run["proposals"] == 1 and run["outcome"] == "끝남"
    assert all(isinstance(step["ms"], int) for step in run["steps"])
    assert _data(client.get(f"{BASE}/ops"))["data"]["usage"]["count"] == 1


def test_no_customer_text_and_no_crew_counts(client):
    _order("DRAWING")
    for path in (BASE, f"{BASE}/cs", f"{BASE}/ops", f"{BASE}/schedule", f"{BASE}/ask", f"{BASE}/drawing"):
        text = client.get(path).get_data(as_text=True)
        for word in ("합성손님", "010-0000-0000", "합성 주소", "인원", "÷ 300", "팀 자리"):
            assert word not in text, (path, word)


def test_save_levels_round_trip_and_errors(client):
    body = _data(client.post(f"{BASE}/levels", json={"levels": {"ops": {"advance_stage": 1}}}))
    assert body["success"] is True
    assert next(r for r in body["data"]["agents"]["ops"] if r["action"] == "advance_stage")["level"] == 1
    assert _duty(_data(client.get(f"{BASE}/ops"))["data"], "advance_stage")["level"] == 1
    bad = _data(client.post(f"{BASE}/levels", json={"levels": {"ops": {"advance_stage": 3}}}), 400)
    assert bad["success"] is False and bad["data"] == {"code": "LEVEL_SHAPE", "fields": ["ops.advance_stage"]}
    assert bad["error"] == "수준 값이 맞지 않아요 — 다시 골라 주세요."
    assert _data(client.post(f"{BASE}/levels", data="not json"), 400)["data"]["fields"] == ["levels"]
    assert _data(client.get(f"{BASE}/nope"), 404)["error"] == "찾을 수 없습니다."


# ── 질의 수 · 색인(R-35 · R-36) ──────────────────────────────────────────
def _statements(fn):
    """``fn`` 이 낸 SQL 과 인자 목록."""
    seen: list[tuple[str, object]] = []
    engine = db_session.get_bind()

    def _listen(_conn, _cursor, statement, parameters, *_args):
        seen.append((statement, parameters))

    event.listen(engine, "before_cursor_execute", _listen)
    try:
        fn()
    finally:
        event.remove(engine, "before_cursor_execute", _listen)
    return seen


@pytest.mark.parametrize("key, ceiling", [("cs", 14), ("ops", 10), ("schedule", 7), ("ask", 5), ("drawing", 3)])
def test_detail_reads_each_thing_once(client, key, ceiling):
    """R-35 — 자세히 한 장은 수준 표 · 상담 초안 수를 한 번만 읽고, 승인율은 그 직원 할 일만 센다(전에는 상담 AI 23번)."""
    admin = db_session.query(User).filter(User.username == "as_admin").one()
    viewer = viewer_of(admin)
    seen = _statements(lambda: staff_detail(db_session, viewer, key, now_utc_naive()))
    assert len(seen) <= ceiling, [statement.split("FROM")[0][:60] for statement, _ in seen]
    assert sum("cs_agent_messages" in statement for statement, _ in seen) == (1 if key == "cs" else 0)


def test_detail_levels_version_is_the_saved_table_version(client):
    """R-35 — 판 번호는 수준 표를 다시 읽지 않고 같은 줄에서(저장 뒤 판 번호와 같다)."""
    _data(client.post(f"{BASE}/levels", json={"levels": {"ops": {"advance_stage": 1}}}))
    _data(client.post(f"{BASE}/levels", json={"levels": {"ops": {"advance_stage": 0}}}))
    version = levels_view(db_session)["version"]
    assert version == 2 and _data(client.get(f"{BASE}/ops"))["data"]["levels_version"] == version


def test_turn_reads_use_an_index(client):
    """R-36 — 상담 AI 자세히의 차례 줄 읽기는 색인을 탄다(``created_at`` 만으로 거르면 표 전체 · 따로 정렬)."""
    now = now_utc_naive()
    for n, (state, age) in enumerate((("posted", 1), ("failed", 2), ("posted", 20 * 24))):
        db_session.add(CsAgentTurn(brand="LAHOM", chat_id=f"ix{n}", last_user_message_id=f"ixm{n}", state=state,
                                   latency_ms=1000 * (n + 1), cost_usd=1,
                                   error_code="error" if state == "failed" else None,
                                   created_at=now - datetime.timedelta(hours=age),
                                   updated_at=now - datetime.timedelta(hours=age)))
    db_session.commit()
    admin = db_session.query(User).filter(User.username == "as_admin").one()
    data: dict = {}
    seen = _statements(lambda: data.update(staff_detail(db_session, viewer_of(admin), "cs", now)))
    raw = db_session.connection().connection
    mine = [(s, p) for s, p in seen if "cs_agent_turns" in s and "cs_agent_messages" not in s]
    assert len(mine) == 4  # 시간 평균 · 비용 · 최근 실패 · 마지막 차례
    for statement, params in mine:
        plan = " | ".join(row[-1] for row in raw.execute("EXPLAIN QUERY PLAN " + statement, params).fetchall())
        assert "TEMP B-TREE" not in plan, (statement, plan)
        assert "USING INDEX" in plan or "ORDER BY cs_agent_turns.id DESC" in statement, (statement, plan)
    assert data["usage"]["avg_ms"] == 1500 and data["usage"]["cost"] == "$2.00"  # 20일 된 줄은 빠진다
    assert [item["code"] for item in data["failures"]] == ["error"]
    assert data["run"]["total_ms"] == 3000  # 마지막 차례 = 가장 큰 번호
