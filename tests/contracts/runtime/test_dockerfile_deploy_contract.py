"""Railway Docker build contract tests."""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]


def test_dockerfile_pip_install_is_resilient_to_slow_package_downloads() -> None:
    """Production Docker builds should tolerate transient PyPI read stalls."""
    dockerfile = (_REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "PIP_DISABLE_PIP_VERSION_CHECK=1" in dockerfile
    assert "PIP_DEFAULT_TIMEOUT=120" in dockerfile
    assert "PIP_RETRIES=10" in dockerfile
    assert "python -m pip install --upgrade pip setuptools wheel" in dockerfile
    assert "--timeout 120 --retries 10 -r requirements.txt" in dockerfile


def test_dockerfile_preserves_railway_runtime_entrypoint_contract() -> None:
    """The Docker fallback must keep the shared requirements/start.sh contract."""
    dockerfile = (_REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "COPY requirements.txt ." in dockerfile
    assert 'CMD ["sh", "start.sh"]' in dockerfile
