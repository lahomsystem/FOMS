"""실측 날짜 패널 캐시는 선택 날짜와 무관하다.

패널(오늘~14일 날짜별 카운트)은 날짜칩을 눌러도 범위·숫자가 같고 선택 표시(is_selected)만
달라진다. 예전에는 캐시 키에 선택 날짜가 들어가 날짜칩을 처음 누를 때마다 패널 전체를 다시
계산했다(스테이징 실측 첫 클릭 801~886ms, 2026-10-01 전체 성능 검사). 이제 키에서 빼고
선택 표시는 캐시 밖에서 입힌다 — 여기서 지키는 것: 다른 날짜가 같은 캐시 값을 쓰는가,
그래도 선택 표시는 그 요청의 날짜를 따르는가, 캐시 값을 고쳐 쓰지 않는가.
"""

from __future__ import annotations

import datetime
import inspect

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.datetime_kst import get_today_kst
from foms.web.measurement import dashboard as measurement_dashboard
from models import User


def _login(client):
    user = User(
        username="meas_panel_date_free",
        password=generate_password_hash("x"),
        role="ADMIN",
        team="CS",
        name="Panel Date Free",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def test_panel_fingerprint_has_no_selected_date():
    src = inspect.getsource(measurement_dashboard.erp_measurement_dashboard)
    panel_fp = src[src.index("_panel_fp = {"): src.index("_panel_key")]
    assert '"selected_date"' not in panel_fp


def test_two_dates_share_one_panel_compute_and_mark_their_own_chip(client, monkeypatch):
    store: dict[str, object] = {}
    panel_computes: list[str] = []

    def _memo(key, ttl, compute, **kwargs):
        if key not in store:
            if kwargs.get("slice_name") == "measurement_panel_assembly":
                panel_computes.append(key)
            store[key] = compute()
        return store[key]

    monkeypatch.setattr(measurement_dashboard, "get_or_compute_dashboard_slice", _memo)
    _login(client)
    today = get_today_kst()
    d1 = (today + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    d2 = (today + datetime.timedelta(days=2)).strftime("%Y-%m-%d")

    first = client.get(f"/erp/measurement?date={d1}").get_data(as_text=True)
    second = client.get(f"/erp/measurement?date={d2}").get_data(as_text=True)

    assert len(panel_computes) == 1, "날짜만 바꿨는데 패널을 다시 계산했다"

    def _selected_chip_dates(body: str) -> set[str]:
        out = set()
        for date in (d1, d2):
            marker = f'id="date-{date}"'
            if marker in body:
                tag = body[body.index(marker): body.index(">", body.index(marker))]
                if "is-selected" in tag:
                    out.add(date)
        return out

    assert _selected_chip_dates(first) == {d1}
    assert _selected_chip_dates(second) == {d2}

    # 공유 캐시 값은 그대로다(요청마다 새 dict 로 선택을 입힌다).
    blob = next(v for k, v in store.items() if k == panel_computes[0])
    assert not any(item.get("is_selected") for item in blob["panel_summary_stat_cards"])
