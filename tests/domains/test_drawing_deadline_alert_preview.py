"""도면 마감 알림 미리 보기 명령(``tools/ops/drawing_deadline_alert_preview.py``) — 읽기만(설계서 2026-11-22 §9-8 · §11)."""
from __future__ import annotations

import datetime
import json
from types import SimpleNamespace

import pytest

from db import db_session
from foms.services.notifications import drawing_deadline_alert as alert
from tests.domains.test_loop_heartbeat_wiring import _REPO_ROOT, _load
from tests.support.drawing_deadline_seed import make_order, rows, seed_world, state, statements


@pytest.fixture
def world(app):
    return seed_world()


# --------------------------------------------------------------------------- #
# 미리 보기 명령 — 읽기만
# --------------------------------------------------------------------------- #
def test_미리_보기는_아무것도_쓰지_않는다(world, monkeypatch, capsys):
    preview = _load(_REPO_ROOT / "tools" / "ops" / "drawing_deadline_alert_preview.py")
    monkeypatch.delenv(alert.ENABLED_ENV, raising=False)  # 스위치와 상관없이 돈다
    monkeypatch.setenv(alert.ONLY_USERS_ENV, str(world["sales"]))
    has = make_order("카가짜", "2026-11-25", assignees=((world["draw"], "장가짜"),))
    none = make_order("타가짜", "2026-11-25", status="PENDING")
    late = make_order("파가짜", "2026-11-24", assignees=((world["draw"], "장가짜"),))  # 마감 11/20 지남
    with statements() as seen:
        got = preview.build_preview(db_session, datetime.date(2026, 11, 23))
    assert seen and not [s for s in seen if not s.startswith("SELECT")]
    assert rows() == [] and state() == {}
    kinds = sorted((i["order_id"], i["kind"]) for i in got["items"])
    assert kinds == sorted([(has, "am"), (has, "pm"), (none, "am"), (none, "pm"), (late, "late")])
    item = next(i for i in got["items"] if i["order_id"] == none and i["kind"] == "am")
    assert item["fallback"] and item["admins"] == ["관가짜"] and item["drawing"] == ["도가짜", "장가짜"]
    assert item["skipped"] == ["관가짜", "도가짜", "장가짜"] and item["status"] == "담당 없음 · 영업 이가짜"
    text = preview.render_report(got)
    assert f"#{none} 마감 날 아침" in text and "카가짜" not in text and "010" not in text
    monkeypatch.setattr(preview, "_make_readonly_session",
                        lambda url: (db_session, SimpleNamespace(dispose=lambda: None)))
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    assert preview.main(["--date", "2026-11-23", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["date"] == "2026-11-23"
    assert preview.main(["--date", "2026-11-28"]) == 0 and "영업일이 아니라" in capsys.readouterr().out
    assert rows() == [] and state() == {}
