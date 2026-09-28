"""CI-KDF-01 봉인 계약 — 테스트 레인 PBKDF2 완화가 유효하고, 운영으로 새지 않는다.

tests/conftest.py 는 CI `Run tests` 839초의 약 73%(실측 676초)를 차지하던
PBKDF2 600,000 반복을 테스트 레인에서만 10 으로 낮춘다. 그 완화에는 두 가지
조용한 실패 양식이 있고, 둘 다 아무도 눈치채지 못한 채 지나간다:

1. **무음 무효화** — werkzeug 가 기본 알고리즘을 바꾸거나(3.0 은 실제로 기본을
   scrypt 로 바꿨다) 상수명을 바꾸면 패치가 아무 일도 하지 않는다. 테스트는
   그대로 통과하고 CI 만 다시 14분으로 돌아간다.
2. **운영 오염** — 완화가 운영 경로로 새면 실제 사용자 비밀번호가 10 회
   반복으로 저장된다. 이건 성능 문제가 아니라 보안 사고다.

werkzeug 3 부터 기본 방식이 scrypt 라서, 운영 해싱은 werkzeug 기본값에 기대지 않고
``foms.services.security.password_policy.hash_password`` 한 곳이 방식(pbkdf2:sha256)과
반복수(``PASSWORD_PBKDF2_ITERATIONS``)를 명시한다(2026-09-28 사용자 결정: 지금과 같게).
그래서 세 번째 양식도 막는다:

3. **방식 표류** — 운영 코드가 그 한 곳을 거치지 않고 ``generate_password_hash`` 를
   직접 부르면 method 기본값(werkzeug 버전마다 다르다)이 조용히 운영 저장 방식이 된다.

이 파일은 셋을 각각 빨강으로 만든다.
"""
import re
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

from foms.services.security.password_policy import hash_password
from tests.conftest import (
    FOMS_TEST_PBKDF2_ITERATIONS,
    PRODUCTION_PBKDF2_ITERATIONS,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
_POLICY_PATH = "foms/services/security/password_policy.py"
_ROOT_MODULES = ("app.py", "models.py", "db.py")


def _production_sources() -> list[tuple[str, str]]:
    """tests/ 밖 운영·운영 도구 파이썬 소스 (상대경로, 본문) 목록."""
    out: list[tuple[str, str]] = []
    for base in ("foms", "tools", "scripts"):
        root = REPO_ROOT / base
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            out.append((path.relative_to(REPO_ROOT).as_posix(), path.read_text(encoding="utf-8", errors="replace")))
    for name in _ROOT_MODULES:
        candidate = REPO_ROOT / name
        if candidate.is_file():
            out.append((name, candidate.read_text(encoding="utf-8", errors="replace")))
    return out


def test_test_lane_relaxation_is_actually_in_effect() -> None:
    """완화가 실제로 적용됐는지 — 무음 무효화(werkzeug 기본값 변경)를 잡는다."""
    expected = f"pbkdf2:sha256:{FOMS_TEST_PBKDF2_ITERATIONS}"
    prefix = generate_password_hash("contract-probe").split("$")[0]
    assert prefix == expected, (
        f"테스트 레인 PBKDF2 완화가 먹지 않았다 (실제 prefix={prefix!r}). "
        "werkzeug 가 기본 알고리즘이나 DEFAULT_PBKDF2_ITERATIONS 상수를 바꿨을 수 있다. "
        "tests/conftest.py 의 CI-KDF-01 블록을 새 werkzeug API 에 맞춰 고쳐라 — "
        "그냥 두면 CI 가 조용히 다시 14분이 된다."
    )
    policy_prefix = hash_password("contract-probe").split("$")[0]
    assert policy_prefix == expected, (
        f"운영 해시 SSOT(hash_password)에 테스트 레인 완화가 먹지 않았다 (실제 prefix={policy_prefix!r}). "
        "tests/conftest.py 가 password_policy.PASSWORD_PBKDF2_ITERATIONS 를 낮추는지 확인하라."
    )


def test_relaxed_hash_still_round_trips() -> None:
    """반복수는 해시 문자열에 박히므로 대조가 정상 동작해야 한다."""
    for hashed in (generate_password_hash("contract-probe"), hash_password("contract-probe")):
        assert check_password_hash(hashed, "contract-probe") is True
        assert check_password_hash(hashed, "wrong-password") is False


def test_production_default_iterations_remain_strong() -> None:
    """운영 해싱 반복수(password_policy SSOT)는 여전히 튼튼해야 한다.

    conftest 가 덮어쓰기 **직전에** 갈무리한 원본 값을 검사한다. 이 값이 내려가면
    운영 해싱이 약해진 것이므로 여기서 막는다.
    """
    assert PRODUCTION_PBKDF2_ITERATIONS >= 600_000, (
        f"운영 PBKDF2 반복수가 {PRODUCTION_PBKDF2_ITERATIONS} 로 내려갔다 — "
        "운영 비밀번호 해싱 강도 저하다. password_policy.PASSWORD_PBKDF2_ITERATIONS 를 확인하라."
    )


def test_production_hashing_goes_through_one_ssot() -> None:
    """운영 코드의 비밀번호 해시 생성은 password_policy.hash_password 한 곳뿐이다(방식 표류 차단).

    그 한 곳은 pbkdf2:sha256 과 PASSWORD_PBKDF2_ITERATIONS 를 method 로 명시해야 한다.
    """
    offenders: list[str] = []
    policy_text = ""
    for rel, text in _production_sources():
        if rel == _POLICY_PATH:
            policy_text = text
            continue
        for match in re.finditer(r"generate_password_hash\s*\(", text):
            line = text[: match.start()].count("\n") + 1
            offenders.append(f"{rel}:{line}")
    assert not offenders, (
        "운영 코드가 generate_password_hash 를 직접 부른다: "
        + ", ".join(offenders)
        + " — foms.services.security.password_policy.hash_password 를 써라."
    )
    calls = re.findall(r"generate_password_hash\s*\(([^)]*)\)", policy_text)
    assert calls, "password_policy 에 해시 생성 호출이 없다 — SSOT 가 사라졌다."
    for args in calls:
        assert 'method=f"pbkdf2:sha256:{PASSWORD_PBKDF2_ITERATIONS}"' in args, (
            f"password_policy 의 해시 호출이 SSOT 방식을 명시하지 않는다: ({args}) — "
            "method 를 비우면 werkzeug 3 기본값 scrypt 로 바뀐다."
        )


def test_kdf_relaxation_lives_only_in_the_test_lane() -> None:
    """반복수 상수를 건드리는 코드는 tests/ 밖에 없어야 한다(SSOT 정의 1줄 제외)."""
    offenders: list[str] = []
    for rel, text in _production_sources():
        if "DEFAULT_PBKDF2_ITERATIONS" in text:
            offenders.append(rel)
        assigns = re.findall(r"PASSWORD_PBKDF2_ITERATIONS\s*(?::\s*int\s*)?=(?!=)", text)
        allowed = 1 if rel == _POLICY_PATH else 0
        if len(assigns) > allowed:
            offenders.append(f"{rel} (PASSWORD_PBKDF2_ITERATIONS 대입 {len(assigns)}회)")
    assert not offenders, (
        "테스트 레인 전용 KDF 완화가 운영 경로로 샜다: "
        + ", ".join(offenders)
        + " — 실제 사용자 비밀번호가 약하게 저장된다."
    )
