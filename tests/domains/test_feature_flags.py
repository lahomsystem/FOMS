from __future__ import annotations

import pytest

from foms.services import feature_flags


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("true", True),
        ("TRUE", True),
        ("1", True),
        ("yes", True),
        ("Y", True),
        ("on", True),
        ("false", False),
        ("0", False),
        ("off", False),
    ],
)
def test_env_bool_truthy_and_falsy_values(monkeypatch, value: str, expected: bool) -> None:
    monkeypatch.setenv("TEST_FLAG", value)
    assert feature_flags.env_bool("TEST_FLAG") is expected


def test_env_bool_uses_default_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("MISSING_FLAG", raising=False)
    assert feature_flags.env_bool("MISSING_FLAG", default=True) is True
    assert feature_flags.env_bool("MISSING_FLAG", default=False) is False


def test_env_id_list_empty_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("COHORT", raising=False)
    assert feature_flags.env_id_list("COHORT") == set()


def test_env_id_list_parses_single_and_multiple_ids(monkeypatch) -> None:
    monkeypatch.setenv("COHORT", " 3 , 17 ,42 ")
    assert feature_flags.env_id_list("COHORT") == {3, 17, 42}


def test_env_id_list_ignores_non_numeric_tokens(monkeypatch) -> None:
    monkeypatch.setenv("COHORT", "3,abc,17")
    assert feature_flags.env_id_list("COHORT") == {3, 17}


def test_is_enabled_for_user_false_when_flag_off(monkeypatch) -> None:
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "false")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "3,17")
    assert feature_flags.is_enabled_for_user(
        "ERP_MOBILE_V2_ENABLED",
        3,
        cohort_key="FOMS_V3_SHELL_COHORT",
    ) is False


def test_is_enabled_for_user_false_when_flag_on_but_cohort_empty(monkeypatch) -> None:
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.delenv("FOMS_V3_SHELL_COHORT", raising=False)
    assert feature_flags.is_enabled_for_user(
        "ERP_MOBILE_V2_ENABLED",
        3,
        cohort_key="FOMS_V3_SHELL_COHORT",
    ) is False


def test_is_enabled_for_user_true_when_flag_on_and_user_in_cohort(monkeypatch) -> None:
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "3,17,42")
    assert feature_flags.is_enabled_for_user(
        "ERP_MOBILE_V2_ENABLED",
        17,
        cohort_key="FOMS_V3_SHELL_COHORT",
    ) is True


def test_is_enabled_for_user_false_when_user_not_in_cohort(monkeypatch) -> None:
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "3,17")
    assert feature_flags.is_enabled_for_user(
        "ERP_MOBILE_V2_ENABLED",
        99,
        cohort_key="FOMS_V3_SHELL_COHORT",
    ) is False


def test_is_enabled_for_user_false_when_user_id_missing(monkeypatch) -> None:
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "3,17")
    assert feature_flags.is_enabled_for_user(
        "ERP_MOBILE_V2_ENABLED",
        None,
        cohort_key="FOMS_V3_SHELL_COHORT",
    ) is False


@pytest.mark.parametrize("cohort_value", ["all", "ALL", "*", " All ", "*,25"])
def test_is_cohort_all_recognizes_rollout_tokens(monkeypatch, cohort_value: str) -> None:
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", cohort_value)
    assert feature_flags.is_cohort_all("FOMS_V3_SHELL_COHORT") is True


def test_is_cohort_all_false_for_id_list_only(monkeypatch) -> None:
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "3,17")
    assert feature_flags.is_cohort_all("FOMS_V3_SHELL_COHORT") is False


@pytest.mark.parametrize("cohort_value", ["all", "ALL", "*"])
def test_is_enabled_for_user_true_for_any_user_when_cohort_all(
    monkeypatch, cohort_value: str
) -> None:
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", cohort_value)
    assert feature_flags.is_enabled_for_user(
        "ERP_MOBILE_V2_ENABLED",
        99,
        cohort_key="FOMS_V3_SHELL_COHORT",
    ) is True


def test_is_enabled_for_user_false_when_cohort_all_but_user_id_missing(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")
    assert feature_flags.is_enabled_for_user(
        "ERP_MOBILE_V2_ENABLED",
        None,
        cohort_key="FOMS_V3_SHELL_COHORT",
    ) is False


def test_prefers_mobile_wizard_client_query_param(app) -> None:
    with app.test_request_context("/add?wizard=1"):
        from flask import request

        assert feature_flags.prefers_mobile_wizard_client(request) is True


def test_prefers_mobile_wizard_client_desktop_ua(app) -> None:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
    with app.test_request_context("/add", headers=headers):
        from flask import request

        assert feature_flags.prefers_mobile_wizard_client(request) is False


def test_should_render_new_order_wizard_requires_mobile_client(app, monkeypatch) -> None:
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
    with app.test_request_context("/add?open=erp-order", headers=headers):
        from flask import request

        assert feature_flags.should_render_new_order_wizard(1, request) is False
    with app.test_request_context("/add?wizard=1", headers=headers):
        from flask import request

        assert feature_flags.should_render_new_order_wizard(1, request) is True
