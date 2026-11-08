"""생산 탭 렌더 전 304 키 — 물어보기 설정(서랍 '회사 지식' 줄)도 키 재료다(회사 지식 다듬기 2차 F7).

서랍 메뉴의 '회사 지식' 줄은 화면을 못 여는 내부 직원에게 물어보기 설정(스위치 · 여는 단계)에 달려 있다
(:func:`foms.web.brain.chat_page_open`). 그 설정이 키에 없으면 설정을 바꿔도 304 가 옛 메뉴를 돌려줄 수 있다.

1. 상수 — 키가 읽는 설정 키 목록에 물어보기 설정 키 정본(:data:`foms.services.brain.chat_settings.SETTINGS_KEY`)이 있다.
2. 입력 기록 계약 — 내부 직원(영업 STAFF)으로 생산 탭을 그리면 렌더가 그 설정을 실제로 읽고, 읽은 설정 키는 모두 키 명세 안이다.
   음성 대조군: 명세에서 그 키를 빼면 반드시 위반이 나온다.
3. 행동 계약 — 설정을 '내부 직원 전부 · 켬'으로 바꾸면 본문(서랍 줄)이 바뀌고 키도 바뀐다.
   음성 대조군: 키 재료에서 설정 갈래를 빼면 본문은 바뀌는데 키는 그대로다.
"""

from __future__ import annotations

from db import db_session, engine
from foms.services import production_fragment_version as pfv
from foms.services.brain.chat_settings import SETTINGS_KEY
from models import SystemSetting
from tests.support.production_prerender_board import (  # noqa: F401 - 픽스처는 이름으로 등록된다
    KANBAN_COOKIES,
    PATH,
    _clean_process_caches,
    _login,
    _render,
    _seed,
    _set_cookies,
    _sqlite_attachment_counts,
    _v2_cohort,
    _weaken,
    shadow,
)
from tests.support.render_input_recorder import record_render_inputs

BRAIN_NAV_TEXT = "회사 지식".encode("utf-8")


def _open_chat_to_all() -> None:
    """물어보기를 켜고 '내부 직원 전부'로 연다 — 화면을 못 여는 영업 STAFF 의 서랍에 '회사 지식' 줄이 생긴다."""
    db_session.add(SystemSetting(setting_key=SETTINGS_KEY, setting_value={"enabled": True, "stage": "all"}))
    db_session.commit()


def _staff_render_pair(client, monkeypatch, shadow):
    _v2_cohort(monkeypatch)
    ctx = _seed()
    _login(client, ctx["sales"])
    _set_cookies(client, KANBAN_COOKIES)
    body_a, key_a = _render(client, shadow)
    _open_chat_to_all()
    body_b, key_b = _render(client, shadow)
    assert key_a is not None and key_b is not None, shadow.get("abandon")
    return body_a, key_a, body_b, key_b


def test_brain_chat_settings_key_is_render_key_material():
    assert SETTINGS_KEY == "brain_chat_settings"
    assert SETTINGS_KEY in pfv.KEY_SETTING_KEYS
    assert len(set(pfv.KEY_SETTING_KEYS)) == len(pfv.KEY_SETTING_KEYS)


def test_staff_render_reads_chat_settings_and_spec_covers_it(app, client, monkeypatch):
    _v2_cohort(monkeypatch)
    _login(client, _seed()["sales"])
    _set_cookies(client, KANBAN_COOKIES)
    with record_render_inputs(app, "erp_production_page.erp_production_dashboard", monkeypatch, engine) as log:
        resp = client.get(PATH, headers={"X-FOMS-ERP-SHELL": "1"})
    assert resp.status_code == 200
    assert SETTINGS_KEY in log.setting_keys, "내부 직원 렌더가 물어보기 설정을 안 읽는다 — 시나리오가 성립하지 않는다"
    assert log.setting_keys <= set(pfv.KEY_SETTING_KEYS), sorted(log.setting_keys - set(pfv.KEY_SETTING_KEYS))
    weakened = set(pfv.KEY_SETTING_KEYS) - {SETTINGS_KEY}
    assert SETTINGS_KEY in log.setting_keys - weakened, "명세에서 빼도 위반이 안 난다 — 대조군이 약하지 않다"


def test_opening_chat_changes_the_staff_menu_and_the_key(client, monkeypatch, shadow):
    body_a, key_a, body_b, key_b = _staff_render_pair(client, monkeypatch, shadow)
    assert body_a != body_b, "설정을 바꿨는데 본문이 그대로다 — 이 변이는 아무것도 증명하지 못한다"
    assert BRAIN_NAV_TEXT not in body_a and BRAIN_NAV_TEXT in body_b, "서랍 '회사 지식' 줄이 설정을 따라가지 않는다"
    assert key_a.key != key_b.key, "물어보기 설정이 바뀌었는데 키가 그대로다 — 304 가 옛 메뉴를 돌려준다"


def test_negative_control_key_without_settings_misses_the_menu_change(client, monkeypatch, shadow):
    _weaken(monkeypatch, (("data", "settings"),))
    body_a, key_a, body_b, key_b = _staff_render_pair(client, monkeypatch, shadow)
    assert body_a != body_b
    assert key_a.key == key_b.key, "설정 갈래를 뺐는데도 키가 바뀌었다 — 이 대조군으로는 빠뜨림을 못 잡는다"
