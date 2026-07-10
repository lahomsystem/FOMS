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


# ---------------------------------------------------------------------------
# resolve_shell_variant — 3-state (legacy / v2 / v3) matrix
# ---------------------------------------------------------------------------


def _set_v2_cohort(monkeypatch, *, enabled: bool, cohort: str) -> None:
    """Configure the legacy v2-shell eligibility gate for a test."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true" if enabled else "false")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", cohort)


def _set_v3_cohort(monkeypatch, *, enabled: bool, cohort: str) -> None:
    """Configure the new v3-shell eligibility gate for a test."""
    monkeypatch.setenv("FOMS_SHELL_V3_ENABLED", "true" if enabled else "false")
    monkeypatch.setenv("FOMS_SHELL_V3_COHORT", cohort)


def test_resolve_shell_variant_legacy_when_v2_off(monkeypatch) -> None:
    _set_v2_cohort(monkeypatch, enabled=False, cohort="3")
    # v3 fully on must not matter when v2 gate fails.
    _set_v3_cohort(monkeypatch, enabled=True, cohort="3")
    assert feature_flags.resolve_shell_variant(3) == "legacy"


def test_resolve_shell_variant_legacy_when_user_outside_v2_cohort(monkeypatch) -> None:
    _set_v2_cohort(monkeypatch, enabled=True, cohort="3,17")
    _set_v3_cohort(monkeypatch, enabled=True, cohort="all")
    assert feature_flags.resolve_shell_variant(99) == "legacy"


def test_resolve_shell_variant_v2_when_v3_off(monkeypatch) -> None:
    _set_v2_cohort(monkeypatch, enabled=True, cohort="3")
    _set_v3_cohort(monkeypatch, enabled=False, cohort="3")
    assert feature_flags.resolve_shell_variant(3) == "v2"


def test_resolve_shell_variant_v2_when_v3_cohort_unset(monkeypatch) -> None:
    _set_v2_cohort(monkeypatch, enabled=True, cohort="3")
    monkeypatch.setenv("FOMS_SHELL_V3_ENABLED", "true")
    monkeypatch.delenv("FOMS_SHELL_V3_COHORT", raising=False)
    assert feature_flags.resolve_shell_variant(3) == "v2"


def test_resolve_shell_variant_v2_when_v3_cohort_empty(monkeypatch) -> None:
    # Core invariant: empty v3 cohort => nobody enters v3 == today's behavior.
    _set_v2_cohort(monkeypatch, enabled=True, cohort="3")
    _set_v3_cohort(monkeypatch, enabled=True, cohort="")
    assert feature_flags.resolve_shell_variant(3) == "v2"


def test_resolve_shell_variant_v3_when_eligible_and_no_cookie(app, monkeypatch) -> None:
    _set_v2_cohort(monkeypatch, enabled=True, cohort="3")
    _set_v3_cohort(monkeypatch, enabled=True, cohort="3")
    with app.test_request_context("/"):
        from flask import request

        assert feature_flags.resolve_shell_variant(3, request) == "v3"


def test_resolve_shell_variant_v2_when_cookie_v2(app, monkeypatch) -> None:
    _set_v2_cohort(monkeypatch, enabled=True, cohort="3")
    _set_v3_cohort(monkeypatch, enabled=True, cohort="3")
    headers = {"Cookie": "foms_shell_pref=v2"}
    with app.test_request_context("/", headers=headers):
        from flask import request

        assert feature_flags.resolve_shell_variant(3, request) == "v2"


def test_resolve_shell_variant_v3_when_cookie_v3(app, monkeypatch) -> None:
    _set_v2_cohort(monkeypatch, enabled=True, cohort="3")
    _set_v3_cohort(monkeypatch, enabled=True, cohort="3")
    headers = {"Cookie": "foms_shell_pref=v3"}
    with app.test_request_context("/", headers=headers):
        from flask import request

        assert feature_flags.resolve_shell_variant(3, request) == "v3"


def test_resolve_shell_variant_v3_when_cookie_garbage(app, monkeypatch) -> None:
    _set_v2_cohort(monkeypatch, enabled=True, cohort="3")
    _set_v3_cohort(monkeypatch, enabled=True, cohort="3")
    headers = {"Cookie": "foms_shell_pref=zzz"}
    with app.test_request_context("/", headers=headers):
        from flask import request

        assert feature_flags.resolve_shell_variant(3, request) == "v3"


def test_resolve_shell_variant_cookie_v3_cannot_escalate_outside_cohort(
    app, monkeypatch
) -> None:
    # Forged cookie must not grant v3 to a user outside the v3 cohort.
    _set_v2_cohort(monkeypatch, enabled=True, cohort="3,99")
    _set_v3_cohort(monkeypatch, enabled=True, cohort="3")
    headers = {"Cookie": "foms_shell_pref=v3"}
    with app.test_request_context("/", headers=headers):
        from flask import request

        assert feature_flags.resolve_shell_variant(99, request) == "v2"


def test_resolve_shell_variant_v3_without_request_context(monkeypatch) -> None:
    # No request context => cookie unreadable => eligible user defaults to v3.
    _set_v2_cohort(monkeypatch, enabled=True, cohort="3")
    _set_v3_cohort(monkeypatch, enabled=True, cohort="3")
    assert feature_flags.resolve_shell_variant(3) == "v3"
