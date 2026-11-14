"""쓰인 곳 기록(설계서 2026-11-14-foms-graft 3.4 · 3.8 · 표 ``brain_usage_events``).

완료 기준: 겹친 키는 한 번 · 빈 · 긴 키는 빠짐 · 50개까지 · 커밋은 부르는 쪽 · 모르는 읽은 쪽 · 빈 번호는 거절 · 창(지난 N일) 수는
읽은 쪽마다(창 밖 · 다른 키는 세지 않음) · 최근 줄은 새것 먼저 · 차례 · 제안이 쓴 키는 처음 쓴 차례대로 겹침 없이 · 합 표
``brain_usage`` 는 건드리지 않음. 지어낸 키만 쓴다. 바깥 호출 없음.
"""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy import func, select

from db import db_session
from foms.persistence.brain.models import BrainUsage
from foms.persistence.graft.models import BrainUsageEvent
from foms.services.brain import usage_events as ue

NOW = datetime.datetime(2026, 11, 14, 1, 0)


def count_rows():
    return db_session.scalar(select(func.count()).select_from(BrainUsageEvent))


def test_record_uses_adds_one_row_per_distinct_key_and_leaves_the_commit_to_the_caller(app):
    added = ue.record_uses(db_session, ["common/door", "erp:order/7", "common/door", "", None, 5, "k" * 121],
                           "erp_action", "proposal", 12, NOW)
    assert added == 2
    db_session.rollback()  # 커밋 전 — 부르는 쪽이 되돌리면 남지 않는다
    assert count_rows() == 0
    ue.record_uses(db_session, ["common/door", "erp:order/7"], "erp_action", "proposal", 12, NOW)
    db_session.commit()
    rows = db_session.execute(select(BrainUsageEvent.item_key, BrainUsageEvent.reader, BrainUsageEvent.ref_kind,
                                     BrainUsageEvent.ref_id).order_by(BrainUsageEvent.id)).all()
    assert [tuple(row) for row in rows] == [("common/door", "erp_action", "proposal", "12"),
                                            ("erp:order/7", "erp_action", "proposal", "12")]
    assert db_session.scalar(select(func.count()).select_from(BrainUsage)) == 0  # 합 표는 그대로


def test_record_uses_stops_at_fifty_keys(app):
    assert ue.record_uses(db_session, [f"common/k{i}" for i in range(60)], "chatbot", "question", "3", NOW) == 50
    db_session.commit()
    assert count_rows() == 50


def test_record_uses_refuses_unknown_readers_and_bad_refs(app):
    for reader, kind, ref in (("cs_brain", "cs_turn", "1"), ("cs_draft", "", "1"), ("cs_draft", "cs_turn", None),
                              ("cs_draft", "x" * 17, "1"), ("cs_draft", "cs_turn", "9" * 65)):
        with pytest.raises(ValueError):
            ue.record_uses(db_session, ["common/door"], reader, kind, ref, NOW)
    assert count_rows() == 0


def test_uses_window_counts_per_reader_inside_the_window_only(app):
    ue.record_uses(db_session, ["common/door"], "cs_draft", "cs_turn", "1", NOW - datetime.timedelta(days=1))
    ue.record_uses(db_session, ["common/door"], "cs_draft", "cs_turn", "2", NOW - datetime.timedelta(days=13))
    ue.record_uses(db_session, ["common/door"], "chatbot", "question", "3", NOW - datetime.timedelta(hours=2))
    ue.record_uses(db_session, ["common/door"], "erp_action", "proposal", "4", NOW - datetime.timedelta(days=15))
    ue.record_uses(db_session, ["common/other"], "cs_draft", "cs_turn", "5", NOW)  # 대조군: 다른 키
    db_session.commit()
    assert ue.uses_window(db_session, "common/door", 14, now=NOW) == {"cs_draft": 2, "erp_action": 0, "chatbot": 1}
    assert ue.uses_window(db_session, "common/door", 30, now=NOW)["erp_action"] == 1
    assert ue.uses_window(db_session, "common/none", 14, now=NOW) == {"cs_draft": 0, "erp_action": 0, "chatbot": 0}
    for bad in (0, 366, True, "14"):
        with pytest.raises(ValueError):
            ue.uses_window(db_session, "common/door", bad, now=NOW)


def test_recent_uses_newest_first_with_a_limit(app):
    for hours, ref in ((5, "a"), (1, "b"), (3, "c")):
        ue.record_uses(db_session, ["erp:order/7"], "cs_draft", "cs_turn", ref, NOW - datetime.timedelta(hours=hours))
    db_session.commit()
    recent = ue.recent_uses(db_session, "erp:order/7", 2)
    assert [use.ref_id for use in recent] == ["b", "c"]
    assert recent[0] == ue.Use("cs_draft", "cs_turn", "b", NOW - datetime.timedelta(hours=1))
    assert ue.recent_uses(db_session, "erp:order/7", 0) == [] and len(ue.recent_uses(db_session, "erp:order/7", 99)) == 3


def test_refs_of_lists_the_keys_a_turn_used_in_first_use_order(app):
    ue.record_uses(db_session, ["common/b", "common/a"], "cs_draft", "cs_turn", 9, NOW)
    ue.record_uses(db_session, ["common/a", "erp:order/7"], "cs_draft", "cs_turn", 9, NOW + datetime.timedelta(minutes=1))
    ue.record_uses(db_session, ["common/z"], "cs_draft", "cs_turn", 10, NOW)  # 대조군: 다른 차례
    db_session.commit()
    assert ue.refs_of(db_session, "cs_turn", 9) == ["common/b", "common/a", "erp:order/7"]
    assert ue.refs_of(db_session, "proposal", 9) == []
