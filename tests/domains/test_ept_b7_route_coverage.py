"""EPT-B7 서버 시간 헤더가 도면 작업실·완료 탭에도 실린다(원장 P3-2 계측 공백).

9탭 중 실측·도면 작업실·완료 세 화면에 헤더가 없어 운영에서 어느 구간이 큰지 갈라 볼 수
없었다. 실측은 2026-10-01 에 붙었고(``test_measurement_panel_cache_date_free``), 여기서는
나머지 둘을 지킨다. 값은 진단 전용이라 크기는 보지 않고 **있는가·어느 화면 것인가**만 본다.
"""

from __future__ import annotations

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.common import dashboard_cache as dc
from models import User

ROUTE = "X-FOMS-EPT-B7-ROUTE"
RENDER_MS = "X-FOMS-EPT-B7-RENDER-MS"
PHASES = "X-FOMS-EPT-B7-PHASES"


@pytest.fixture(autouse=True)
def _no_redis(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    dc.reset_dashboard_cache_runtime_for_tests()
    yield
    dc.reset_dashboard_cache_runtime_for_tests()


def _login(client) -> None:
    user = User(
        username="ept_b7_cover_admin",
        password=generate_password_hash("x"),
        role="ADMIN",
        team="CS",
        name="계측 확인",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _phase_names(header: str) -> list[str]:
    """구간 이름 목록. 템플릿 쪽 표시(``shell_head`` 등 ``mark()`` 쌍)는 렌더 중에 붙어 뒤에 온다."""
    return [part.split("=", 1)[0] for part in header.split(";") if part]


def test_drawing_workbench_reports_route_render_and_phases(client) -> None:
    _login(client)

    response = client.get("/erp/drawing-workbench")

    assert response.status_code == 200
    assert response.headers.get(ROUTE) == "erp_drawing_workbench_dashboard"
    assert float(response.headers[RENDER_MS]) >= 0
    phases = _phase_names(response.headers.get(PHASES, ""))
    assert phases[:4] == ["seed", "hydrate", "rows", "filter_sort"], phases


def test_completion_reports_route_and_render_without_cohort_phase_on_pc(client) -> None:
    """PC(legacy 셸)는 태블릿 금액 그리드를 안 만든다 — 구간도 없어야 한다(음성).
    앞 요청(도면 작업실)의 구간이 다음 요청 헤더로 새지 않는다(음성)."""
    _login(client)
    client.get("/erp/drawing-workbench")

    response = client.get("/erp/completion")

    assert response.status_code == 200
    assert response.headers.get(ROUTE) == "erp_completion_dashboard"
    assert float(response.headers[RENDER_MS]) >= 0
    phases = _phase_names(response.headers.get(PHASES, ""))
    assert "cohort_grid" not in phases, phases
    assert "seed" not in phases, phases


def test_completion_cohort_grid_phase_when_mobile_v2(client, monkeypatch) -> None:
    """모바일 코호트(v2)면 금액 그리드를 만들고, 그 시간이 cohort_grid 구간으로 나온다."""
    from foms.web.cs import completion_dashboard

    monkeypatch.setattr(completion_dashboard, "is_mobile_v2_shell", lambda _variant: True)
    _login(client)

    response = client.get("/erp/completion")

    assert response.status_code == 200
    assert response.headers.get(ROUTE) == "erp_completion_dashboard"
    phases = _phase_names(response.headers.get(PHASES, ""))
    assert phases[:1] == ["cohort_grid"], phases
