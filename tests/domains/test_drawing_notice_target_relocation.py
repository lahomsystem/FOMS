"""자리 고정 — 도면 알림의 영업 쪽 받는 사람 규칙은 서비스 층 한 함수이고, 부르는 곳 넷이 모두 그것을 부른다.

``foms/api/drawing/erp_orders_drawing.py`` 의 ``_drawing_notice_target`` 을 ``foms.services.notifications.drawing_notice_target``
으로 옮겼다(설계서 docs/specs/2026-11-22-production-drawing-arrival-upgrade_SPEC.md §9-3 — 백그라운드 도면 마감 알림이 api 층을
거꾸로 부르지 않게). 옮긴 뒤 누가 api 쪽에 사본을 다시 만들거나, 부르는 곳 하나가 다른 규칙으로 갈라지면 여기서 빨강이 된다.
"""
from __future__ import annotations

import ast
import inspect
import pathlib

import foms.api.drawing.as_drawing as as_drawing_api
import foms.api.drawing.erp_orders_drawing as drawing_api
from foms.services.notifications import drawing_notice_target as target_mod

_ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_규칙은_서비스_층_한_함수이고_부르는_곳_넷이_같은_것을_쓴다() -> None:
    fn = target_mod.drawing_notice_target
    assert drawing_api.drawing_notice_target is fn
    assert as_drawing_api.drawing_notice_target is fn
    # 부르는 곳 셋: 도면 전달 · 전달 취소 · AS 도면 전달
    assert "drawing_notice_target(\n        db, manager_name, partner=is_partner_sd(s_data))" in inspect.getsource(
        drawing_api.perform_drawing_transfer)
    assert "= drawing_notice_target(\n                db, _mgr, partner=is_partner_sd(s_data))" in inspect.getsource(
        drawing_api.api_order_cancel_transfer)
    assert "sales_target = drawing_notice_target(sess, order_manager_label(sd), partner=is_partner_sd(sd))" in (
        inspect.getsource(as_drawing_api.run_as_transfer))


def test_api_층에_옛_이름이나_사본이_없다() -> None:
    assert not hasattr(drawing_api, "_drawing_notice_target")
    home = _ROOT / "foms" / "services" / "notifications" / "drawing_notice_target.py"
    files = [p for p in sorted((_ROOT / "foms").rglob("*.py")) if p != home and "__pycache__" not in p.parts]
    assert len(files) > 100  # 모집단이 비면 이 시험은 아무것도 안 본다
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert "_drawing_notice_target" not in text, path
        assert "def drawing_notice_target" not in text, path
        assert "ADMIN_HANDLED_MANAGER_KEYWORD = " not in text, path


def test_서비스_층은_api_를_부르지_않는다() -> None:
    """옮긴 모듈은 api · web 층을 import 하지 않는다(레이어 래칫과 같은 방향)."""
    tree = ast.parse(inspect.getsource(target_mod))
    names = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    names += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
    assert not [n for n in names if n.startswith(("foms.api", "foms.web"))]


def test_옮긴_뒤에도_같은_답(app) -> None:
    """옮기기 전 시험(``tests/security/test_partner_manager.py``)과 같은 경우 + 라홈 · 양산 · 빈 이름."""
    from db import db_session
    from tests.support.drawing_deadline_seed import make_user

    make_user("영업김", "SALES")
    fn = target_mod.drawing_notice_target
    assert fn(db_session, "영업김", partner=True) == ("CS", None, None)
    assert fn(db_session, "영업김") == (None, "영업김", None)
    assert fn(db_session, "라홈 직원") == ("CS", None, None)
    assert fn(db_session, "양산지사") == (None, None, "ADMIN")
    assert fn(db_session, "") == ("SALES", None, None)
