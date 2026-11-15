"""접목판 점검 2차 고치기 — 새 회사 지식 화면의 첫 화면 · 승인 대기 · 찾기(w1-02 · 03 · 06 · 10 · 11 · 12 · 17 · 18).

- 찾기 첫 화면 = 모든 유형 표(D232 · w1-06): 유형 없이 지식 표를 읽고, 볼 수 없는 유형 · 층은 줄 · 수 어디에도 없다
  (같은 모집단의 ADMIN 대조군).
- 이름 칸 꼬리표(w1-11): 수정 대기 수 · 엇갈림 수를 가른다. 엇갈림 하나가 모든 줄을 '확인 필요'로 만들던 상관 부분 질의를 고쳤다.
- 마지막 확인한 사람(w1-12): 확인 날이 처음 들어간 판을 승인한 사람(뒤의 다른 고침이 이름을 바꾸지 않는다).
- 내보내기(D233 · w1-10): ADMIN 만(서버도), 지금 거른 표 그대로 CSV(UTF-8 BOM), 볼 수 없는 것은 파일에도 없다, 감사 한 줄,
  상한을 넘으면 400.
- 첫 화면(w1-02): 지식 제안이 0 이어도 이 사람이 결정할 AI 할 일 제안이 있으면 승인 대기(스위치 끈 화면은 그대로).
- 제안 자세히(w1-03): 이미 처리된 제안은 누가 · 언제 · 결과(done)를 싣는다 — 결정할 수 있는 제안은 ``None``.
합성 계정 · 합성 항목 · 합성 주문만.
"""

from __future__ import annotations

import csv
import io

import pytest

from db import db_session
from foms.api import brain as brain_api
from foms.persistence.brain.models import BrainObject
from foms.services.brain.apply import apply_change
from foms.services.brain.browse import TableQuery, known_count, table_page
from foms.services.brain.proposals import Proposer, propose_update
from foms.services.brain.scope import viewer_of
from foms.services.brain.store import current_object
from foms.services.erp_actions import views
from foms.services.erp_actions.lifecycle import reject
from foms.services.graft_flags import FLAGS
from models import SecurityLog, User
from tests.domains.test_erp_actions_api import BASE, _data, switches, world  # noqa: F401 — 시험 재료(고정물) 같이 씀
from tests.support.brain_screen_support import TODAY
from tests.support.brain_screen_support import world as brain_world
from tests.support.brain_support import NOW, REASON, create, link

EXPORT = "/api/brain/table/export.csv"


@pytest.fixture
def people(app, monkeypatch):
    for env in FLAGS.values():
        monkeypatch.delenv(f"{env}_ENABLED", raising=False)
        monkeypatch.delenv(f"{env}_COHORT", raising=False)
    made = brain_world(db_session)
    ids = {name: user.id for name, user in made.items()}  # 요청이 끝나면 세션이 닫힌다 — 번호만 들고 다닌다
    return _People(ids)


class _People(dict):
    """이름 → 사람(부를 때마다 지금 세션에서 다시 읽는다)."""

    def __init__(self, ids):
        super().__init__()
        self.ids = ids

    def __getitem__(self, name):
        return db_session.get(User, self.ids[name])


def _client(app, user):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
    return client


def _switch(monkeypatch, short):
    monkeypatch.setenv(f"{FLAGS[short]}_ENABLED", "1")
    monkeypatch.setenv(f"{FLAGS[short]}_COHORT", "all")


def _conflict_about_door(admin):
    create(db_session, admin, "conflict/door", item_type="conflict", name="합성 엇갈림", checked_at="2026-10-28")
    link(db_session, admin, "about", "conflict/door", "common/door")
    db_session.commit()


# ── 모든 유형 표(w1-06 · D232) ───────────────────────────────────────────────
def test_table_without_a_type_lists_every_visible_type_and_hides_the_rest(people):
    admin = table_page(db_session, viewer_of(people["admin"]), TableQuery(), today=TODAY)
    cs = table_page(db_session, viewer_of(people["cs_mgr"]), TableQuery(), today=TODAY)
    admin_types = {row["type"] for row in admin["rows"]}
    assert {"product_line", "build_rule", "price_rule", "question", "drawing_rule"} <= admin_types  # 대조군: 있다
    assert {row["type"] for row in cs["rows"]} == {"product_line", "build_rule"}  # 가격 재량 · 관리 · 도면팀 0
    assert cs["total"] == len(cs["rows"]) == 6 and cs["type"] is None  # 초안 · 은퇴도 표에는 든다(상태 거르기로 고른다)
    assert "common/discount" not in [r["key"] for r in cs["rows"]] and "drawing/rule" not in [r["key"] for r in cs["rows"]]
    assert admin["total"] == 9
    status = table_page(db_session, viewer_of(people["cs_mgr"]), TableQuery(status="retired"), today=TODAY)
    assert [r["key"] for r in status["rows"]] == ["common/old"]  # 거르기는 유형 없이도 걸린다


def test_table_api_answers_without_a_type_and_rejects_unknown_types(app, people, monkeypatch):
    client = _client(app, people["cs_mgr"])
    body = client.get("/api/brain/table").get_json()
    assert body["success"] is True and body["data"]["type"] is None and body["data"]["total"] == 6
    assert client.get("/api/brain/table?type=nope").status_code == 400
    assert _client(app, people["cs_staff"]).get("/api/brain/table").status_code == 404  # 화면을 못 여는 사람


# ── 꼬리표 · 확인한 사람 · 사용 중 수(w1-11 · 12 · 10) ──────────────────────
def test_flags_split_open_changes_and_conflicts_and_one_conflict_flags_only_its_item(people):
    _conflict_about_door(people["admin"])
    rows = {r["key"]: r for r in table_page(db_session, viewer_of(people["admin"]), TableQuery(), today=TODAY)["rows"]}
    assert (rows["common/fit"]["open_changes"], rows["common/fit"]["conflicts"]) == (1, 0)
    assert (rows["common/door"]["open_changes"], rows["common/door"]["conflicts"]) == (0, 1)
    assert rows["common/door"]["needs_check"] is True and rows["common/fit"]["needs_check"] is True
    assert sorted(k for k, r in rows.items() if r["needs_check"]) == ["common/door", "common/fit"]
    assert rows["common/slide"]["needs_check"] is False  # 대조군 — 엇갈림은 문짝 하나에 대한 것
    needs = table_page(db_session, viewer_of(people["admin"]), TableQuery(check="needs_check"), today=TODAY)
    assert sorted(r["key"] for r in needs["rows"]) == ["common/door", "common/fit"]


def test_checked_by_is_who_approved_the_version_that_set_the_check_date(people):
    admin, other = people["admin"], people["cs_mgr"]
    db_session.query(User).filter(User.id == admin.id).update({"name": "합성 확인자"})
    db_session.query(User).filter(User.id == other.id).update({"name": "합성 다른 사람"})
    fresh = current_object(db_session, "common/fresh")
    later = propose_update(db_session, key="common/fresh", base_version=fresh.version, after={"text": "합성 새 글"},
                           reason=REASON, proposer=Proposer.user(other.id), now=NOW, known="")
    apply_change(db_session, later.id, actor=db_session.get(User, admin.id), now=NOW)
    db_session.query(BrainObject).filter(BrainObject.item_key == "common/fresh", BrainObject.superseded_at.is_(None)) \
        .update({"human_approver_id": other.id})  # 뒤 판(글만 고침)은 다른 사람이 승인 — 확인한 사람은 바뀌지 않는다
    db_session.commit()
    rows = {r["key"]: r for r in table_page(db_session, viewer_of(people["admin"]), TableQuery(), today=TODAY)["rows"]}
    assert rows["common/fresh"]["checked_at"] == "2026-11-01" and rows["common/fresh"]["checked_by"] == "합성 확인자"
    assert rows["common/door"]["checked_at"] is None and rows["common/door"]["checked_by"] is None


def test_known_count_is_every_visible_item_including_draft_and_retired(people):
    assert known_count(db_session, viewer_of(people["cs_mgr"]), today=TODAY) == 6  # 숨긴 셋 뺌 · 초안 · 은퇴 듦
    assert known_count(db_session, viewer_of(people["admin"]), today=TODAY) == 9  # 대조군: 숨긴 셋이 든다


def test_search_header_shows_active_count_and_the_export_button_only_to_admin(app, people, monkeypatch):
    _switch(monkeypatch, "brain_ui")
    admin = _client(app, people["admin"]).get("/brain?tab=search").get_data(as_text=True)
    manager = _client(app, people["cs_mgr"]).get("/brain?tab=search").get_data(as_text=True)
    assert "지식 9개 · 사용 중 7개" in admin and "data-ds-export" in admin and f'data-export-url="{EXPORT}"' in admin
    assert "지식 6개 · 사용 중 4개" in manager and "data-ds-export" not in manager and "data-export-url" not in manager


# ── 내보내기(D233 · w1-10) ───────────────────────────────────────────────────
def _csv(resp):
    assert resp.status_code == 200 and resp.mimetype == "text/csv"
    text = resp.get_data(as_text=True)
    assert text.startswith("﻿")
    return list(csv.reader(io.StringIO(text[1:])))


def test_export_is_admin_only_filtered_like_the_table_and_audited(app, people):
    client = _client(app, people["admin"])
    rows = _csv(client.get(f"{EXPORT}?type=build_rule&status=active&sort=name"))
    assert rows[0][:3] == ["키", "이름", "유형"] and [r[0] for r in rows[1:]] == ["common/fit", "common/fresh"]
    whole = _csv(client.get(EXPORT))
    assert {"common/discount", "common/ask", "drawing/rule"} <= {r[0] for r in whole[1:]}  # ADMIN 은 다 본다
    log = db_session.query(SecurityLog).filter(SecurityLog.action == "BRAIN_TABLE_EXPORT_CSV").all()
    assert len(log) == 2 and log[0].detail["query"] == {"type": "build_rule", "status": "active", "sort": "name"} and log[0].detail["rows"] == 2
    assert _client(app, people["cs_mgr"]).get(EXPORT).status_code == 403  # 화면은 열지만 관리자가 아니다
    assert _client(app, people["cs_staff"]).get(EXPORT).status_code == 404
    assert client.get(f"{EXPORT}?type=nope").status_code == 400
    assert db_session.query(SecurityLog).filter(SecurityLog.action == "BRAIN_TABLE_EXPORT_CSV").count() == 2


def test_export_never_carries_hidden_layers_even_for_a_scoped_admin_view(app, people, monkeypatch):
    """층 · 유형 거르기는 표와 같은 질의 단계 — 보기 범위로 숨긴 것이 파일에 새지 않는지 MANAGER 범위로 본다(같은 함수)."""
    from foms.services.brain.browse import table_rows

    total, rows = table_rows(db_session, viewer_of(people["cs_mgr"]), TableQuery(), today=TODAY, limit=100)
    assert total == 6 and {r["key"] for r in rows}.isdisjoint({"common/discount", "common/ask", "drawing/rule"})


def test_export_refuses_more_than_the_limit_and_guards_spreadsheet_formulas(app, people, monkeypatch):
    client = _client(app, people["admin"])
    monkeypatch.setattr(brain_api, "MAX_EXPORT_ROWS", 3)
    resp = client.get(EXPORT)
    assert resp.status_code == 400 and "거르기로 줄여" in resp.get_json()["error"]
    monkeypatch.setattr(brain_api, "MAX_EXPORT_ROWS", 5000)
    create(db_session, people["admin"], "common/formula", name="=1+1 합성", checked_at="2026-10-28")
    db_session.commit()
    names = {r[0]: r[1] for r in _csv(client.get(f"{EXPORT}?type=product_line"))[1:]}
    assert names["common/formula"] == "'=1+1 합성"


# ── 첫 화면(w1-02) · 제안 자세히(w1-03) · 결정할 수(views) ─────────────────
def test_first_tab_is_the_inbox_when_only_ai_proposals_wait(app, world, monkeypatch):  # noqa: F811
    admin = db_session.get(User, world["admin_id"])
    db_session.query(type(admin)).filter_by(id=admin.id).update({"role": "ADMIN"})
    from foms.persistence.brain.models import BrainChange
    assert db_session.query(BrainChange).count() == 0  # 지식 제안 0
    body = world["client"].get("/brain").get_data(as_text=True)
    assert 'data-ds-inbox-view="inbox"' in body  # AI 할 일 제안 셋 → 승인 대기
    assert views.decidable_count(db_session, admin) == 3
    monkeypatch.setenv("FOMS_GRAFT_BRAIN_UI_ENABLED", "0")  # 스위치 끈 화면은 지금 그대로(지식 제안만 센다)
    old = world["client"].get("/brain").get_data(as_text=True)
    assert "data-ds-inbox-view" not in old


def test_first_tab_stays_search_without_anything_to_decide(app, world, monkeypatch):  # noqa: F811
    for row in world["rows"]:
        reject(db_session, row["id"], actor=db_session.get(User, world["admin_id"]), code="other", now=NOW)
    db_session.commit()
    body = world["client"].get("/brain").get_data(as_text=True)
    assert 'data-ds-search-page data-ds-search-mode="table"' in body  # 결정할 것이 없으면 찾기(모든 유형 표)


def test_detail_says_who_when_and_what_for_a_decided_proposal(world):  # noqa: F811
    row = world["rows"][0]
    open_one = _data(world["client"].get(f"{BASE}/proposals/{row['id']}"))["data"]
    assert open_one["done"] is None  # 결정할 수 있는 제안은 단추 그대로
    reject(db_session, row["id"], actor=db_session.get(User, world["admin_id"]), code="wrong_date", now=NOW)
    db_session.commit()
    done = _data(world["client"].get(f"{BASE}/proposals/{row['id']}"))["data"]["done"]
    assert done["status"] == "rejected" and done["label"] == "거절했어요 — 날짜가 틀림"
    assert done["by"] == "합성 관리자" and done["at"]
