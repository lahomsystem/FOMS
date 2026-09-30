"""SECRET-01 — Kakao REST secret must be env-only, never hardcoded.

P0-2: the Kakao REST API key was a literal in ``geocode_config.py`` and
``SCheduler/config.py`` (duplicated). It is now read from ``KAKAO_REST_API_KEY``
env only, with a per-feature fail-fast (``require_kakao_rest_key``) so the
geocoding/address feature raises a clear error when unset instead of silently
calling Kakao with a bogus ``KakaoAK None`` header.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from foms.services.common import geocode_config

ROOT = Path(__file__).resolve().parents[2]

# The leaked key must never reappear in tracked source (git history aside). Only its
# SHA-256 is kept here — a test that stores the literal leaks it again.
_LEAKED_KEY_SHA256 = "0c045bfc60d6dd545846e39af1d6977c5492514b7a35f68fa3c985ff94657d56"
_HEX32 = re.compile(r"\b[0-9a-f]{32}\b")


def test_no_hardcoded_rest_key_in_source() -> None:
    offenders: list[str] = []
    for path in list((ROOT / "foms").rglob("*.py")) + list((ROOT / "SCheduler").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if any(
            hashlib.sha256(m.encode()).hexdigest() == _LEAKED_KEY_SHA256 for m in _HEX32.findall(text)
        ):
            offenders.append(path.relative_to(ROOT).as_posix())
    assert not offenders, f"hardcoded Kakao REST key present: {offenders}"


def test_require_kakao_rest_key_fails_fast_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KAKAO_REST_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        geocode_config.require_kakao_rest_key()


def test_kakao_rest_headers_uses_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KAKAO_REST_API_KEY", "test-key-xyz")
    headers = geocode_config.kakao_rest_headers()
    assert headers == {"Authorization": "KakaoAK test-key-xyz"}


def test_kakao_rest_headers_fails_fast_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KAKAO_REST_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        geocode_config.kakao_rest_headers()
