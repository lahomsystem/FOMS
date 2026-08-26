"""CI-KDF-01 봉인 계약 — 테스트 레인 PBKDF2 완화가 유효하고, 운영으로 새지 않는다.

tests/conftest.py 는 CI `Run tests` 839초의 약 73%(실측 676초)를 차지하던
PBKDF2 600,000 반복을 테스트 레인에서만 10 으로 낮춘다. 그 완화에는 두 가지
조용한 실패 양식이 있고, 둘 다 아무도 눈치채지 못한 채 지나간다:

1. **무음 무효화** — werkzeug 가 기본 알고리즘을 바꾸거나(3.0 은 실제로 기본을
   scrypt 로 바꿨다) 상수명을 바꾸면 패치가 아무 일도 하지 않는다. 테스트는
   그대로 통과하고 CI 만 다시 14분으로 돌아간다.
2. **운영 오염** — 완화가 운영 경로로 새면 실제 사용자 비밀번호가 10 회
   반복으로 저장된다. 이건 성능 문제가 아니라 보안 사고다.

이 파일은 그 둘을 각각 빨강으로 만든다.
"""
import re
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

from tests.conftest import (
    FOMS_TEST_PBKDF2_ITERATIONS,
    PRODUCTION_PBKDF2_ITERATIONS,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_test_lane_relaxation_is_actually_in_effect() -> None:
    """완화가 실제로 적용됐는지 — 무음 무효화(werkzeug 기본값 변경)를 잡는다."""
    prefix = generate_password_hash("contract-probe").split("$")[0]
    assert prefix == f"pbkdf2:sha256:{FOMS_TEST_PBKDF2_ITERATIONS}", (
        f"테스트 레인 PBKDF2 완화가 먹지 않았다 (실제 prefix={prefix!r}). "
        "werkzeug 가 기본 알고리즘이나 DEFAULT_PBKDF2_ITERATIONS 상수를 바꿨을 수 있다. "
        "tests/conftest.py 의 CI-KDF-01 블록을 새 werkzeug API 에 맞춰 고쳐라 — "
        "그냥 두면 CI 가 조용히 다시 14분이 된다."
    )


def test_relaxed_hash_still_round_trips() -> None:
    """반복수는 해시 문자열에 박히므로 대조가 정상 동작해야 한다."""
    hashed = generate_password_hash("contract-probe")
    assert check_password_hash(hashed, "contract-probe") is True
    assert check_password_hash(hashed, "wrong-password") is False


def test_production_default_iterations_remain_strong() -> None:
    """운영이 쓰는 werkzeug 기본 반복수는 여전히 튼튼해야 한다.

    conftest 가 덮어쓰기 **직전에** 갈무리한 원본 값을 검사한다. 의존성 갱신으로
    이 값이 내려가면 운영 해싱이 약해진 것이므로 여기서 막는다.
    """
    assert PRODUCTION_PBKDF2_ITERATIONS >= 600_000, (
        f"werkzeug 기본 PBKDF2 반복수가 {PRODUCTION_PBKDF2_ITERATIONS} 로 내려갔다 — "
        "운영 비밀번호 해싱 강도 저하다. 의존성 갱신 내역을 확인하라."
    )


def test_production_code_never_pins_a_weak_kdf() -> None:
    """운영 코드가 method= 로 약한 KDF 를 박아두지 않는다.

    운영 해싱은 werkzeug 기본값을 그대로 써야 한다. 호출부가 method= 를 직접
    지정하기 시작하면 conftest 완화와 무관하게 운영 강도가 코드에 고정된다.
    """
    offenders: list[str] = []
    for path in (REPO_ROOT / "foms").rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in re.finditer(r"generate_password_hash\s*\(([^)]*)\)", text):
            if "method" in match.group(1):
                line = text[: match.start()].count("\n") + 1
                offenders.append(f"{path.relative_to(REPO_ROOT).as_posix()}:{line}")
    assert not offenders, (
        "운영 코드가 generate_password_hash 에 method= 를 지정한다: "
        + ", ".join(offenders)
        + " — 운영은 werkzeug 기본값을 써야 한다."
    )


def test_kdf_relaxation_lives_only_in_the_test_lane() -> None:
    """DEFAULT_PBKDF2_ITERATIONS 를 건드리는 코드는 tests/ 밖에 없어야 한다."""
    offenders: list[str] = []
    for base in ("foms", "tools", "scripts"):
        root = REPO_ROOT / base
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="replace")
            if "DEFAULT_PBKDF2_ITERATIONS" in text:
                offenders.append(path.relative_to(REPO_ROOT).as_posix())
    for name in ("app.py", "models.py", "db.py"):
        candidate = REPO_ROOT / name
        if candidate.is_file():
            text = candidate.read_text(encoding="utf-8", errors="replace")
            if "DEFAULT_PBKDF2_ITERATIONS" in text:
                offenders.append(name)
    assert not offenders, (
        "테스트 레인 전용 KDF 완화가 운영 경로로 샜다: "
        + ", ".join(offenders)
        + " — 실제 사용자 비밀번호가 약하게 저장된다."
    )
