"""대피 구성용 env 변환기 계약 — tools/ops/vars_snapshot_to_env.py."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "vars_snapshot_to_env_under_test", REPO_ROOT / "tools" / "ops" / "vars_snapshot_to_env.py"
)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def test_convert_drops_railway_and_connection_values() -> None:
    snapshot = {
        "web": {"SECRET_KEY": "s", "RAILWAY_ENVIRONMENT": "production", "DATABASE_URL": "x", "REDIS_URL": "y",
                "FOMS_BASE_URL": "https://a", "FOMS_TRUSTED_PROXY_HOPS": "2"},
        "WORKER": {"USE_RQ_WORKER": "1", "PGPASSWORD": "p"},
        "Postgres": {"POSTGRES_PASSWORD": "never"},
    }
    out = mod.convert(snapshot)
    assert out["web"] == {"FOMS_BASE_URL": "https://a", "SECRET_KEY": "s"}
    assert out["worker"] == {"USE_RQ_WORKER": "1"}
    assert out["sidefx"] == {} and out["cron"] == {}
    assert "Postgres" not in out


def test_render_rejects_multiline_values() -> None:
    assert mod.render({"A": "1", "B": "two"}) == "A=1\nB=two\n"
    with pytest.raises(SystemExit):
        mod.render({"KEY": "line1\nline2"})


def test_main_refuses_output_inside_repo() -> None:
    with pytest.raises(SystemExit, match="저장소 안"):
        mod.main(["--out", str(REPO_ROOT / "deploy" / "compose" / "env")])
