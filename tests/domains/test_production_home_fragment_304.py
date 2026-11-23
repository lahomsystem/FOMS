"""생산 첫 화면 셸 조각 304 — 아무것도 안 바뀌면 If-None-Match 에 304, 바뀌면 200(2026-11-22 터치 감사 D3).

예전엔 본문의 받은 시각(``data-loaded-at`` · 'HH:MM 에 받음', 초 단위)과 파트 판의 첫 받아 오기 기준 시각(``data-pp-since``)이
요청마다 달라 같은 화면도 늘 200 이었다(같은 조각 세 번 = ETag 세 개). 받은 시각은 본문에서 빼고(셸이 #main-content 에 적는다),
기준 시각은 본문에 두되 ETag 재료에서 뺀다(``foms.web.production.home._ETAG_VOLATILE``). 시드 · 로그인 도우미는 파트 화면 시험 것.
"""
from __future__ import annotations

import datetime
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


@pytest.mark.parametrize("who", ["part", "readonly", "pc", "pc_writer"])
def test_home_fragment_answers_304_until_something_changes(client, cohort, who):
    me, park = _user("김재단", part="cut"), _user("박재단", part="cut")
    ids = _seed_day(me, park)
    if who == "part":
        _login(client, me)
        url = HOME
    elif who == "readonly":
        _login(client, _user("상담", team="CS"))
        url = HOME + "?tab=parts&part=cut"
    elif who == "pc":
        _login(client, _user("상담", team="CS"), ptr="fine")  # PC 보기 전용(쓰기 팀 아님)
        url = HOME + "?tab=all"
    else:
        # 쓰기 팀 PC — [고치기] 단추의 서버 시각(data-foms-prod-edit-now · 초 단위)이 본문에 있다. 11-23 까지는 이 값이 ETag 에
        # 들어가 늘 200 이었고 운영 올림 perf-gate 의 조건부 304 확인이 초 경계에 따라 떨어졌다. 값은 본문에 두고 ETag 재료에서만
        # 뺀다. 전제: foms-production-edit.js 가 단추마다 받은 때부터 흐른 시간만 더하므로 304 로 옛 단추가 남아도 쿠키 시각은
        # 과거 쪽으로만 어긋난다(앞날 값 없음 — 서버는 pc_view.EDIT_CLOCK_SKEW_SECONDS 초 앞선 값까지만 받는다).
        _login(client, me, ptr="fine")
        url = HOME + "?tab=all"
    first = _frag(client, url)
    body = first.get_data(as_text=True)
    assert first.status_code == 200 and first.headers.get("X-FOMS-ERP-FRAGMENT") == "1"
    assert "data-loaded-at" not in body and not re.search(r"\d\d:\d\d 에 받", body), "받은 시각은 본문에 없다"
    assert ("data-pp-since=" in body) is (who in ("part", "readonly")), "카드 판이 있는 화면은 첫 받아 오기 기준 시각을 그대로 싣는다"
    stamp = re.search(r'data-foms-prod-edit-now="(\d+)"', body)
    assert (stamp is not None) is (who == "pc_writer"), "[고치기] 단추의 서버 시각은 쓰기 팀 PC 본문에만 있다"
    etag = first.headers["ETag"]
    time.sleep(1.1)  # 예전 data-loaded-at · [고치기] 서버 시각은 초 단위 — 1초 넘겨야 그것만으로도 달라진다
    if stamp:  # 본문 값은 여전히 요청마다 새 서버 시각이다(ETag 만 같다)
        fresh = _frag(client, url)
        assert fresh.headers["ETag"] == etag
        assert int(re.search(r'data-foms-prod-edit-now="(\d+)"', fresh.get_data(as_text=True)).group(1)) > int(stamp.group(1))
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
    """음성 대조군: 기준 시각을 ETag 에서 빼지 않으면(아무것도 안 거르는 식) 같은 화면도 늘 200 이다.

    기준 시각의 시계(``part_sync_cursor`` 가 읽는 ``now_utc_naive``)를 시험이 쥔다. 실제 시계에 맡기면 두 요청이
    같은 눈금(Windows 약 15ms)에 들어 기준 시각이 같아지고, 그러면 304 가 나와 대조군이 거짓으로 깨졌다.
    """
    clock = {"now": datetime.datetime(2026, 11, 22, 1, 2, 3, 456000)}
    monkeypatch.setattr("foms.services.production.part_board.now_utc_naive", lambda: clock["now"])
    me, park = _user("김재단", part="cut"), _user("박재단", part="cut")
    _seed_day(me, park)
    _login(client, me)
    monkeypatch.setattr("foms.web.production.home._ETAG_VOLATILE", re.compile(rb"(?!)"))
    first = _frag(client, HOME)
    first_since = re.search(r'data-pp-since="([^"]*)"', first.get_data(as_text=True)).group(1)
    clock["now"] += datetime.timedelta(seconds=30)  # 다음 받아 오기 — 바뀐 것은 기준 시각뿐
    second = _frag(client, HOME, first.headers["ETag"])
    assert second.status_code == 200 and second.headers["ETag"] != first.headers["ETag"]
    second_body = second.get_data(as_text=True)
    assert f'data-pp-since="{first_since}"' not in second_body and "data-pp-since=" in second_body
    # 같은 대조 화면도 기준 시각만 같으면 304 — 위의 200 은 기준 시각이 ETag 에 섞인 탓이다(다른 까닭이 아님)
    assert _frag(client, HOME, second.headers["ETag"]).status_code == 304
