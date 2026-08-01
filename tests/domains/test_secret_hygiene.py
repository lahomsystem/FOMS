"""SECRET-02 - secret hygiene gate tests.

Covers the static credential-literal scanner
(``tools/harness/secret_literal_scan.py``) and the deployed-environment credential
presence gate (``tools/ops/check_deploy_secrets.py``).

Boundary: the two Flask/WAM signing-secret fallbacks are owned by
SESSION-SIGNING-SECRET-01 and are intentionally NOT flagged here (env-backed /
attribute-target); this suite proves that. No credential value is ever asserted,
printed, or stored by these tests - only variable names and presence.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.harness import secret_literal_scan as scanner
from tools.ops import check_deploy_secrets as deploy

REPO_ROOT = Path(__file__).resolve().parents[2]

# Synthetic, secret-shaped value used only inside tests (never a real credential):
# mixed case + digits, no underscore/whitespace, 18 chars.
_FAKE_SECRET = "aA0bB1cC2dD3eE4fF5"
_FAKE_VAR = "MY_SERVICE_API_KEY"


def _write_py(tmp_path: Path, body: str) -> Path:
    f = tmp_path / "sample_mod.py"
    f.write_text(body, encoding="utf-8")
    return f


# --------------------------------------------------------------------------- #
# Scanner: detection, allowlist, non-secret shapes, real-tree baseline.
# --------------------------------------------------------------------------- #


def test_scanner_detects_hardcoded_credential_literal(tmp_path: Path) -> None:
    """A bare credential-named constant assigned a secret-shaped literal is red."""
    f = _write_py(tmp_path, f'{_FAKE_VAR} = "{_FAKE_SECRET}"\n')
    findings = scanner.scan_files([f])
    assert len(findings) == 1
    assert findings[0].name == _FAKE_VAR
    assert findings[0].length == len(_FAKE_SECRET)
    # The literal value must never be retained on the finding.
    assert not hasattr(findings[0], "value")


def test_scanner_green_after_literal_removed(tmp_path: Path) -> None:
    """Reading the same var from the environment removes the finding (red -> green)."""
    f = _write_py(tmp_path, f'{_FAKE_VAR} = os.environ.get("{_FAKE_VAR}")\n')
    assert scanner.scan_files([f]) == []


def test_scanner_respects_allowlist(tmp_path: Path) -> None:
    """An allowlisted name (by name, file optional) is suppressed."""
    f = _write_py(tmp_path, f'{_FAKE_VAR} = "{_FAKE_SECRET}"\n')
    raw = scanner.scan_files([f])
    assert raw, "precondition: literal should be detected before allowlisting"
    allow = [scanner.AllowEntry(name=_FAKE_VAR, file=None, reason="test-only")]
    filtered = [x for x in raw if not scanner._is_allowlisted(x, allow)]
    assert filtered == []


@pytest.mark.parametrize(
    "body",
    [
        'VAPID_PUBLIC_KEY_ENV = "VAPID_PUBLIC_KEY"\n',        # env-var name reference
        'TOKEN_CLI_ARG = "--approval-token-file"\n',          # CLI flag name
        'PUSH_TOKEN_KEY = "push_token_estimate"\n',           # lower_snake dict key
        'CHANNEL_APP_SECRET = os.environ.get("X", "fallbk")\n',  # env-backed (call value)
        'app.secret_key = "dev-secret-key-abcdef123"\n',      # attribute target (SESSION-SIGNING)
        'SHORT_SECRET = "abc123"\n',                          # under the 12-char threshold
    ],
)
def test_scanner_ignores_non_secret_shapes(tmp_path: Path, body: str) -> None:
    """Env-name refs, CLI flags, dict keys, env-backed reads, attribute targets and
    short values are not credential literals."""
    f = _write_py(tmp_path, body)
    assert scanner.scan_files([f]) == []


def test_real_tree_has_no_unallowlisted_credential_literals() -> None:
    """Gate baseline: the live foms/, SCheduler/, app.py surface is green."""
    findings = scanner.scan()
    assert findings == [], (
        "unexpected credential literal(s): "
        f"{[(f.path, f.line, f.name) for f in findings]}"
    )


def test_allowlist_records_names_not_values() -> None:
    """The allowlist inventory carries the public key's NAME but never its VALUE."""
    entries = scanner.load_allowlist()
    assert any(e.name == "KAKAO_JS_API_KEY" for e in entries)
    text = scanner.ALLOWLIST_PATH.read_text(encoding="utf-8")
    from foms.services.common import geocode_config

    assert geocode_config.KAKAO_JS_API_KEY not in text


def test_scanner_output_never_prints_literal_value(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The CLI reports the offending variable name and location but not its value."""
    (tmp_path / "foms").mkdir()
    (tmp_path / "foms" / "leaky.py").write_text(
        f'{_FAKE_VAR} = "{_FAKE_SECRET}"\n', encoding="utf-8"
    )
    rc = scanner.main(["--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 1
    assert _FAKE_VAR in out
    assert _FAKE_SECRET not in out


# --------------------------------------------------------------------------- #
# Deploy credential presence gate.
# --------------------------------------------------------------------------- #

_DEPLOYED = {"RAILWAY_ENVIRONMENT": "production"}


def _base_env(**extra: str) -> dict[str, str]:
    env = dict(_DEPLOYED)
    env.update(
        {
            "SECRET_KEY": "present-secret",
            "KAKAO_REST_API_KEY": "present-rest",
            "DATABASE_URL": "postgresql://u:p@h/db",
        }
    )
    env.update(extra)
    return env


def test_deploy_check_passes_when_required_present() -> None:
    assert deploy.missing_secrets(_base_env()) == []


def test_deploy_check_fails_when_secret_key_missing() -> None:
    env = _base_env()
    del env["SECRET_KEY"]
    assert "SECRET_KEY" in deploy.missing_secrets(env)


def test_deploy_check_accepts_pg_set_without_database_url() -> None:
    env = _base_env()
    del env["DATABASE_URL"]
    env.update({"PGHOST": "h", "PGUSER": "u", "PGPASSWORD": "p", "PGDATABASE": "d"})
    assert deploy.missing_secrets(env) == []


def test_deploy_check_reports_missing_database_when_neither_form_present() -> None:
    env = _base_env()
    del env["DATABASE_URL"]
    missing = deploy.missing_secrets(env)
    assert any("DATABASE_URL" in m for m in missing)


def test_deploy_check_web_push_conditional() -> None:
    env = _base_env(FOMS_WEB_PUSH_ENABLED="1")
    missing = deploy.missing_secrets(env)
    assert "VAPID_PRIVATE_KEY" in missing and "VAPID_PUBLIC_KEY" in missing
    env.update({"VAPID_PRIVATE_KEY": "priv", "VAPID_PUBLIC_KEY": "pub"})
    assert deploy.missing_secrets(env) == []


def test_deploy_check_r2_conditional() -> None:
    env = _base_env(STORAGE_TYPE="r2")
    missing = deploy.missing_secrets(env)
    assert any("R2_ENDPOINT" in m for m in missing)
    assert "R2_ACCESS_KEY_ID" in missing
    env.update(
        {
            "R2_ACCOUNT_ID": "acc",
            "R2_ACCESS_KEY_ID": "k",
            "R2_SECRET_ACCESS_KEY": "s",
            "R2_BUCKET_NAME": "b",
        }
    )
    assert deploy.missing_secrets(env) == []


def test_deploy_check_web_push_off_by_default() -> None:
    """VAPID is not required when web push is disabled/unset."""
    assert "VAPID_PRIVATE_KEY" not in deploy.missing_secrets(_base_env())


def test_deploy_main_exit_codes() -> None:
    assert deploy.main([], env=_base_env()) == 0
    env = _base_env()
    del env["SECRET_KEY"]
    assert deploy.main([], env=env) == 1


def test_deploy_main_skips_off_deployment() -> None:
    assert deploy.main([], env={"SECRET_KEY": ""}) == 0  # not deployed -> skip
    assert deploy.main(["--force"], env={}) == 1  # forced -> everything missing


def test_deploy_output_never_prints_credential_values(capsys: pytest.CaptureFixture[str]) -> None:
    """Neither the OK path nor the FAIL path echoes any credential value."""
    secret_val = "SUPERSECRET-doNotLeak-000111222"
    rest_val = "RESTSECRET-doNotLeak-333444555"
    ok_env = _base_env(SECRET_KEY=secret_val)
    ok_env["KAKAO_REST_API_KEY"] = rest_val
    deploy.main([], env=ok_env)
    ok_out = capsys.readouterr().out
    assert secret_val not in ok_out and rest_val not in ok_out

    fail_env = _base_env(SECRET_KEY=secret_val)
    del fail_env["KAKAO_REST_API_KEY"]  # force the FAIL branch while a real-ish value is set
    deploy.main([], env=fail_env)
    fail_out = capsys.readouterr().out
    assert secret_val not in fail_out
