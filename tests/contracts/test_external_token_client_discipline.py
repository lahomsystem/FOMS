"""EXT-TOKEN-01: 외부 API 토큰 클라이언트 규율 계약.

2026-08-27 운영 사고: 채널톡 ``issueToken`` 이 주는 ``expiresIn`` 은 앱 **공유 세션의
남은 수명**이다(실측 1800 → 1533 → 1521 로 감소). 클라이언트가 이를 무시하고 항상
29분을 캐시한 탓에 세션 중간에 받은 토큰이 캐시 만료 전에 죽었고, 401 을 받아도 토큰을
버리지 않아 그 창 동안 수동 푸시가 전부 502 로 실패했다.

외부에서 발급받은 토큰을 캐시하는 클라이언트가 지켜야 하는 규율 2가지:

* **R1** 캐시 수명을 응답의 ``expires_in``/``expiresIn`` 에서 유도한다(고정 상수 금지).
* **R2** 인증 실패(401/unauthenticated)를 받으면 캐시 토큰을 버리고 재발급해 재시도한다.

이 파일은 규율을 **행동 테스트로 강제**하는 대신 그 행동 테스트의 **존재**를 강제한다:
클라이언트마다 R1·R2 를 증명하는 테스트 함수를 등재하게 하고, 새 클라이언트가 등재 없이
들어오면 실패시킨다. 규율 자체의 검증은 각 클라이언트 스위트가 한다.
"""

from __future__ import annotations

import importlib
import pathlib
import re

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_FOMS_ROOT = _REPO_ROOT / "foms"

#: 등재부 — {클라이언트 소스 경로: (행동 테스트 모듈, R1·R2 를 증명하는 테스트 함수)}
_TOKEN_CLIENT_CONTRACTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "foms/services/channel_client.py": (
        "tests.domains.test_channel_client",
        (
            # R1: expiresIn 을 캐시 수명으로 쓴다(없을 때만 고정 폴백).
            "test_issue_token_uses_expires_in_from_response",
            "test_issue_token_falls_back_to_default_ttl_without_expires_in",
            # R2: 401 이면 죽은 토큰을 버리고 재발급해 1회 재시도한다.
            "test_send_group_message_reissues_token_and_retries_on_unauthenticated",
            "test_send_group_message_gives_up_when_retry_also_unauthenticated",
        ),
    ),
    "foms/services/integrations/naver_commerce/client.py": (
        "tests.services.integrations.test_naver_commerce_client",
        (
            # R1: expires_in 에서 갱신 마진을 뺀 값이 캐시 TTL 이다.
            "test_token_cache_ttl_shrinks_by_refresh_margin",
            # R2: 401 이면 강제 재발급 후 1회 재시도, 그래도 401 이면 무한루프 없이 종료.
            "test_unauthorized_refreshes_token_once_then_succeeds",
            "test_persistent_unauthorized_raises_auth_error_without_loop",
        ),
    ),
}

_TOKEN_RE = re.compile(r"(access[_ ]?token|accessToken|issue_?token|issueToken)", re.IGNORECASE)
_CACHE_RE = re.compile(r"(_token_cache|token_cache|TokenCache|cache\.set\()")


def _discover_token_caching_modules() -> set[str]:
    """
    Find every ``foms/`` module that caches an externally issued token.

    토큰을 다루면서(``access_token``/``issueToken`` 등) 캐시에 넣는(``_token_cache``·
    ``TokenCache``·``cache.set(``) 파일을 후보로 본다. 자격증명을 캐시하지 않는
    presigned URL 생성기(``storage.py``)나 호출마다 서명하는 클라이언트는 걸리지 않는다.

    Returns:
        저장소 루트 기준 posix 경로 집합.
    """
    found: set[str] = set()
    for path in _FOMS_ROOT.rglob("*.py"):
        source = path.read_text(encoding="utf-8", errors="ignore")
        if _TOKEN_RE.search(source) and _CACHE_RE.search(source):
            found.add(path.relative_to(_REPO_ROOT).as_posix())
    return found


def test_every_token_caching_client_is_registered() -> None:
    """토큰을 캐시하는 새 클라이언트는 등재부에 올라야 한다(규율 누락 방지)."""
    discovered = _discover_token_caching_modules()
    unregistered = sorted(discovered - set(_TOKEN_CLIENT_CONTRACTS))

    assert not unregistered, (
        "외부 토큰을 캐시하는 클라이언트가 등재되지 않았다:\n"
        f"  {unregistered}\n"
        "R1(expires_in 기반 TTL)·R2(401 시 재발급 후 재시도)를 증명하는 테스트를 만들고 "
        "_TOKEN_CLIENT_CONTRACTS 에 등재하라. 근거: 2026-08-27 채널톡 401 사고."
    )


@pytest.mark.parametrize(
    ("client_path", "test_module", "required_tests"),
    [
        (client_path, test_module, required_tests)
        for client_path, (test_module, required_tests) in sorted(_TOKEN_CLIENT_CONTRACTS.items())
    ],
)
def test_registered_client_keeps_its_discipline_tests(
    client_path: str, test_module: str, required_tests: tuple[str, ...]
) -> None:
    """등재된 클라이언트가 저장소에 있으면 R1·R2 행동 테스트도 같이 있어야 한다."""
    if not (_REPO_ROOT / client_path).exists():
        pytest.skip(f"{client_path} 없음 — 이 저장소 상태에서는 규율 대상이 아니다")

    module = importlib.import_module(test_module)
    missing = sorted(name for name in required_tests if not hasattr(module, name))

    assert not missing, (
        f"{client_path} 의 토큰 규율 테스트가 사라졌다: {missing} (모듈={test_module})\n"
        "테스트를 지우거나 이름을 바꿨다면 등재부도 같이 고쳐라 — 규율이 조용히 풀린다."
    )
