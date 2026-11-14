"""접목판 스위치 판정(설계서 2026-11-14-foms-graft 4절 — 모두 처음 끔 · 판정은 graft_flags 한 곳).

- 이름 일곱 · 짧은 이름 표 · env 이름도 받는다 · 모르는 이름은 오류(조용히 '끔'으로 삼키지 않는다).
- 사람별: ``_ENABLED`` + ``_COHORT``(번호들 · ``all``) — 끔 · 목록 밖 · 목록 안 · all · 로그인 안 함.
- 기대는 스위치: actions 는 brain_ui 도 켜진 사람만, 칸 셋은 actions(→ brain_ui)도 켜진 사람만. 전역 판정도 같은 사슬.
- proposers 는 사람별이 아니다(``_COHORT`` 를 읽지 않는다).
- 템플릿 전역 ``graft_enabled`` 는 ``g.current_user`` 로 판정한다. DB 를 읽지 않는다.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from flask import g

from foms.services import graft_flags
from foms.services.graft_flags import FLAGS, SHORT_NAMES, enabled, enabled_global, flag_name

ME = SimpleNamespace(id=7)
OTHER = SimpleNamespace(id=8)


@pytest.fixture(autouse=True)
def _all_off(monkeypatch):
    for env in FLAGS.values():
        monkeypatch.delenv(f"{env}_ENABLED", raising=False)
        monkeypatch.delenv(f"{env}_COHORT", raising=False)


def _on(monkeypatch, short, cohort="all"):
    monkeypatch.setenv(f"{FLAGS[short]}_ENABLED", "1")
    if cohort is not None:
        monkeypatch.setenv(f"{FLAGS[short]}_COHORT", cohort)


def test_seven_names_and_short_names():
    assert FLAGS == {
        "brain_ui": "FOMS_GRAFT_BRAIN_UI", "erp_read": "FOMS_GRAFT_ERP_READ", "actions": "FOMS_GRAFT_ACTIONS",
        "cell_pc": "FOMS_GRAFT_CELL_PC", "cell_tablet": "FOMS_GRAFT_CELL_TABLET",
        "cell_mobile": "FOMS_GRAFT_CELL_MOBILE", "proposers": "FOMS_GRAFT_PROPOSERS",
    }
    assert SHORT_NAMES == tuple(FLAGS)
    assert flag_name("FOMS_GRAFT_ACTIONS") == "actions" == flag_name("FOMS_GRAFT_ACTIONS_ENABLED")
    with pytest.raises(ValueError):
        flag_name("brain_iu")
    with pytest.raises(ValueError):
        enabled("nope", ME)


def test_everything_is_off_by_default():
    for short in SHORT_NAMES:
        assert enabled(short, ME) is False and enabled_global(short) is False, short


def test_per_person_cohort_rules(monkeypatch):
    _on(monkeypatch, "erp_read", cohort=None)  # 켬인데 사람 목록이 비면 끔(feature_flags 규칙)
    assert enabled("erp_read", ME) is False and enabled_global("erp_read") is True
    _on(monkeypatch, "erp_read", cohort="7, 9")
    assert enabled("erp_read", ME) is True and enabled("erp_read", OTHER) is False
    assert enabled("erp_read", None) is False  # 로그인 안 함
    _on(monkeypatch, "erp_read", cohort="all")
    assert enabled("erp_read", OTHER) is True and enabled("erp_read", None) is False
    monkeypatch.setenv("FOMS_GRAFT_ERP_READ_ENABLED", "0")
    assert enabled("erp_read", ME) is False and enabled_global("erp_read") is False


def test_actions_needs_brain_ui_and_cells_need_actions(monkeypatch):
    _on(monkeypatch, "actions")
    for cell in ("cell_pc", "cell_tablet", "cell_mobile"):
        _on(monkeypatch, cell)
    assert not enabled("actions", ME) and not enabled_global("actions")  # brain_ui 꺼짐
    assert not any(enabled(c, ME) or enabled_global(c) for c in ("cell_pc", "cell_tablet", "cell_mobile"))
    _on(monkeypatch, "brain_ui", cohort="8")  # 다른 사람에게만
    assert enabled("actions", OTHER) and not enabled("actions", ME)
    assert enabled("cell_pc", OTHER) and not enabled("cell_pc", ME)
    assert enabled_global("actions") and enabled_global("cell_mobile")
    monkeypatch.setenv("FOMS_GRAFT_ACTIONS_COHORT", "7")  # actions 사람 목록에서 빠지면 칸도 끔
    assert not enabled("cell_tablet", OTHER) and not enabled("actions", OTHER)
    monkeypatch.setenv("FOMS_GRAFT_CELL_PC_ENABLED", "0")
    assert not enabled_global("cell_pc") and enabled_global("cell_tablet")


def test_proposers_is_global_only(monkeypatch):
    monkeypatch.setenv("FOMS_GRAFT_PROPOSERS_ENABLED", "1")  # _COHORT 없음
    assert enabled_global("proposers") is True
    assert enabled("proposers", None) is True and enabled("proposers", ME) is True
    assert "proposers" in graft_flags.GLOBAL_ONLY


def test_template_global_reads_the_signed_in_person(app, monkeypatch):
    _on(monkeypatch, "brain_ui", cohort="7")
    tpl = "{{ graft_enabled('brain_ui') }}|{{ graft_enabled('actions') }}"
    template = app.jinja_env.from_string(tpl)  # 앱 전역만(문맥 처리기 없이) — 판정 하나만 본다
    with app.test_request_context("/"):
        g.current_user = ME
        assert template.render() == "True|False"
        g.current_user = OTHER
        assert template.render() == "False|False"
        g.current_user = None
        assert template.render() == "False|False"
