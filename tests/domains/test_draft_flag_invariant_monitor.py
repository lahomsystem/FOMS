"""초안 표식 규칙 감시 도구(``tools/ops/check_draft_flag_invariant.py``) 계약.

* 숨은 모양(ERP · 표식 참 · status 가 DRAFT/DELETED 아님)만 센다 — 휴지통 행도 센다.
* **음성 대조군**: 정상 초안·승격 주문·버린 초안·정본 삭제된 초안·표식 참 비ERP 행은 세지 않는다.
* SQL 술어(:func:`hidden_draft_shape_filter`)와 행 판정(:func:`violates_draft_flag_rule`)이 같은 답.
* 출력에 고객 정보가 없고, 종료 코드는 0(없음)·3(있음)·1(실패).
* 매일 밤 단계에는 **아직 걸지 않았다**(사용자 결정 2026-10-05 — 운영 7건 정리 뒤 이 단언을 뒤집는다).
"""

from __future__ import annotations

import json

import pytest

from db import db_session
from foms.services.orders.draft_guard import violates_draft_flag_rule
from models import Order
from tools.cron.nightly import NIGHTLY_STEPS
from tools.ops import check_draft_flag_invariant as monitor

_SECRET_NAME = "감시고객비밀이름"


def _order(*, status: str, draft: bool, erp: bool = True, deleted_at=None) -> int:
    order = Order(
        received_date="2026-10-05", customer_name=_SECRET_NAME, phone="010-9999-0000",
        address="서울 감시로 1", product="붙박이장", status=status, deleted_at=deleted_at,
        is_erp_order=erp,
        structured_data={"meta": {"draft": draft}, "workflow": {"stage": "MEASURE"}},
    )
    db_session.add(order)
    db_session.commit()
    return int(order.id)


def _controls() -> list[int]:
    """세면 안 되는 행들(음성 대조군)."""
    return [
        _order(status="DRAFT", draft=True),                                   # 정상 초안
        _order(status="RECEIVED", draft=False),                               # 승격 주문
        _order(status="DELETED", draft=True, deleted_at="2026-10-05 00:00:00"),  # 버린 초안
        _order(status="DRAFT", draft=True, deleted_at="2026-10-05 00:00:00"),    # 정본 삭제 초안
        _order(status="MEASURE", draft=True, erp=False),                      # 비ERP
    ]


class _FakeEngine:
    def dispose(self) -> None:
        return None


class _BorrowedSession:
    """요청 세션을 빌려 쓰되 도구의 close() 가 시험 세션을 닫지 않게 한다."""

    def query(self, *args, **kwargs):
        return db_session.query(*args, **kwargs)

    def close(self) -> None:
        return None


@pytest.fixture
def borrowed_db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setattr(monitor, "_make_readonly_session",
                        lambda url: (_BorrowedSession(), _FakeEngine()))


def test_counts_only_hidden_shape_including_trashed(app):
    controls = _controls()
    hidden_alive = _order(status="MEASURE", draft=True)
    hidden_trashed = _order(status="RECEIVED", draft=True, deleted_at="2026-10-05 00:00:00")

    rows = monitor.find_hidden_draft_orders(db_session)

    assert [row["id"] for row in rows] == [hidden_alive, hidden_trashed]
    assert rows[0] == {"id": hidden_alive, "status": "MEASURE", "trashed": False,
                       "created_day": rows[0]["created_day"]}
    assert rows[1]["trashed"] is True
    # SQL 술어와 행 판정이 같은 답을 낸다(대조군 포함 전체).
    db_session.expire_all()
    by_python = sorted(
        int(o.id) for o in db_session.query(Order).filter(Order.id.in_(controls + [
            hidden_alive, hidden_trashed])).all() if violates_draft_flag_rule(o)
    )
    assert by_python == [hidden_alive, hidden_trashed]


def test_controls_only_count_zero(app):
    _controls()
    assert monitor.find_hidden_draft_orders(db_session) == []


def test_main_exit_3_and_report_has_no_customer_info(app, borrowed_db, capsys):
    _controls()
    hidden = _order(status="MEASURE", draft=True)

    code = monitor.main([])
    out = capsys.readouterr().out

    assert code == monitor.EXIT_VIOLATIONS == 3
    assert f"주문 #{hidden} status=MEASURE" in out
    assert _SECRET_NAME not in out and "010-9999-0000" not in out and "감시로" not in out


def test_main_json_and_exit_0_when_clean(app, borrowed_db, capsys):
    _controls()

    code = monitor.main(["--json"])
    payload = json.loads(capsys.readouterr().out)

    assert code == monitor.EXIT_CLEAN == 0
    assert payload == {"violations": 0, "rows": []}


def test_main_exit_1_without_database_url(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert monitor.main([]) == monitor.EXIT_FAILED == 1


def test_monitor_not_yet_wired_into_nightly():
    """보류(사용자 결정 2026-10-05): 운영 숨은 초안 7건을 정리한 뒤에 nightly 에 건다.

    그때 ``tools/cron/nightly.py`` 의 ``NIGHTLY_STEPS`` 에서 ``cleanup_order_drafts`` 다음에
    이 도구를 넣고, 이 단언을 "들어 있다"로 뒤집는다.
    """
    scripts = [step.script for step in NIGHTLY_STEPS]
    assert "tools/ops/check_draft_flag_invariant.py" not in scripts
    assert scripts[0] == "tools/cron/cleanup_order_drafts.py"
