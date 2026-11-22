"""생산 첫 화면 셸 조각 304 — 아무것도 안 바뀌면 If-None-Match 에 304, 바뀌면 200(2026-11-22 터치 감사 D3).

예전엔 본문의 받은 시각(``data-loaded-at`` · 'HH:MM 에 받음', 초 단위)과 파트 판의 첫 받아 오기 기준 시각(``data-pp-since``)이
요청마다 달라 같은 화면도 늘 200 이었다(같은 조각 세 번 = ETag 세 개). 받은 시각은 본문에서 빼고(셸이 #main-content 에 적는다),
기준 시각은 본문에 두되 ETag 재료에서 뺀다(``foms.web.production.home._ETAG_VOLATILE``). 시드 · 로그인 도우미는 파트 화면 시험 것.
"""
from __future__ import annotations

import re
import time

import pytest

from db import db_session
from models import Order
from tests.domains.test_production_parts_screen import HOME, _login, _seed_day, _user


@pytest.fixture
def cohort(monkeypatch):
    """모바일 v2 셸 코호트(모두) — 태블릿 표면의 서버 문 하나."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")


# --------------------------------------------------------------------------- #
# 셸 조각 304(11-22 터치 감사 D3) — 받은 시각 · 첫 받아 오기 기준 시각 때문에 늘 200 이던 것
# --------------------------------------------------------------------------- #
_SHELL = {"X-FOMS-ERP-SHELL": "1", "X-Requested-With": "XMLHttpRequest"}


def _frag(client, url: str, etag: str | None = None):
    headers = dict(_SHELL, **({"If-None-Match": etag} if etag else {}))
    return client.get(url + ("&" if "?" in url else "?") + "foms_shell=fragment", headers=headers)


@pytest.mark.parametrize("who", ["part", "readonly", "pc"])
def test_home_fragment_answers_304_until_something_changes(client, cohort, who):
    me, park = _user("김재단", part="cut"), _user("박재단", part="cut")
    ids = _seed_day(me, park)
    if who == "part":
        _login(client, me)
        url = HOME
    elif who == "readonly":
        _login(client, _user("상담", team="CS"))
        url = HOME + "?tab=parts&part=cut"
    else:
        # PC 보기 전용(쓰기 팀 아님). 쓰기 팀 PC 는 [고치기] 단추의 서버 시각(data-foms-prod-edit-now)이 본문에 있어 아직 늘 200 이다.
        _login(client, _user("상담", team="CS"), ptr="fine")
        url = HOME + "?tab=all"
    first = _frag(client, url)
    body = first.get_data(as_text=True)
    assert first.status_code == 200 and first.headers.get("X-FOMS-ERP-FRAGMENT") == "1"
    assert "data-loaded-at" not in body and not re.search(r"\d\d:\d\d 에 받", body), "받은 시각은 본문에 없다"
    assert ("data-pp-since=" in body) is (who != "pc"), "카드 판이 있는 화면은 첫 받아 오기 기준 시각을 그대로 싣는다"
    etag = first.headers["ETag"]
    time.sleep(1.1)  # 예전 data-loaded-at 은 초 단위 — 1초 넘겨야 그것만으로도 달라진다
    again = _frag(client, url, etag)
    assert again.status_code == 304, "아무것도 안 바뀌었으면 304"
    # 대조군: 바뀌면 200 · 다른 ETag
    order = db_session.get(Order, ids["b"])
    order.customer_name = "늘봄새이름"
    sd = dict(order.structured_data)
    sd["parties"] = {"customer": {"name": "늘봄새이름", "phone": "010-0000-0000"}}
    order.structured_data = sd
    db_session.commit()
    changed = _frag(client, url, etag)
    assert changed.status_code == 200 and changed.headers["ETag"] != etag
    assert "늘봄새이름" in changed.get_data(as_text=True)


def test_negative_control_since_in_etag_breaks_304(client, cohort, monkeypatch):
    """음성 대조군: 기준 시각을 ETag 에서 빼지 않으면(아무것도 안 거르는 식) 같은 화면도 늘 200 이다."""
    me, park = _user("김재단", part="cut"), _user("박재단", part="cut")
    _seed_day(me, park)
    _login(client, me)
    monkeypatch.setattr("foms.web.production.home._ETAG_VOLATILE", re.compile(rb"(?!)"))
    first = _frag(client, HOME)
    assert "data-pp-since=" in first.get_data(as_text=True)
    assert _frag(client, HOME, first.headers["ETag"]).status_code == 200
