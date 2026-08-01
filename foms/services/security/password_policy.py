"""PASSWORD-POLICY-01 — 비밀번호 강도 정책 버전 SSOT + legacy 이행 서비스.

비밀번호 강도는 **``users.password_policy_version`` 컬럼**이 유일한 진실(SSOT)이다.
저장된 hash 를 재계산(rehash)해서 강도를 추정하지 않는다 — hash 는 단방향이라 강도를
역산할 수 없고, 추정은 legacy 계정을 조용히 strong 으로 오분류해 정책을 무력화한다. 대신
비밀번호를 설정/변경할 때 강도 검사를 통과하면 그 시점에 버전을 ``STRONG`` 으로 **명시
기록**하고, 그 외 모든 기존 행은 ``LEGACY`` 로 둔다(마이그레이션 server_default).

정책 상태:

* **WARN(기본)**: active legacy 계정이 남아 있는 동안. legacy 사용자의 로그인·업무는
  **차단하지 않고**(가장 중요한 함정 — WARN 이 업무를 막으면 안 된다), persistent banner
  로만 비밀번호 변경을 유도한다.
* **ENFORCED**: active legacy count 가 0 이 되면 전환. 새/변경/reset 은 항상 strong 이므로
  이 상태에서는 남은 모든 계정이 strong 이다.

새/변경/admin reset 은 항상 strong 을 강제하고(약한 비번 거부), 한번 strong 이 된 비번을
약한 값으로 되돌리는 것(weak rollback)은 모든 경로에서 구조적으로 불가능하다
(:func:`set_strong_password` 가 유일한 설정 chokepoint 이며 항상 강도 검사를 통과해야 한다).
"""
from __future__ import annotations

from typing import Any, Optional

from werkzeug.security import generate_password_hash

#: LEGACY = 강도 미검증(기존/약할 수 있음). 마이그레이션 server_default 이자 model default.
#: "모르면 legacy" — hash 로 추정하지 않는다.
POLICY_VERSION_LEGACY: int = 0
#: STRONG = 현행 강도 정책을 통과해 설정된 비번. 설정 시점에 명시 기록한다.
POLICY_VERSION_STRONG: int = 1
#: 현행 정책 버전(새/변경 비번이 기록할 값).
CURRENT_POLICY_VERSION: int = POLICY_VERSION_STRONG

#: 강도 최소 길이. ponytail: 길이+문자군 heuristic. 더 엄격한 검사가 필요하면
#: zxcvbn 등 엔트로피 추정기로 교체(이 함수 한 곳만 바꾸면 전 경로 반영).
MIN_STRONG_LENGTH: int = 8


class WeakPasswordError(ValueError):
    """강도 정책을 통과하지 못한 비밀번호 설정 시도(약한 비번 거부·weak rollback 거부)."""


def validate_password_strength(password: Optional[str]) -> tuple[bool, str]:
    """비밀번호가 현행 strong 정책을 만족하는지 검사한다(강도 SSOT 판정).

    강도 기준: 길이 ``MIN_STRONG_LENGTH`` 이상, 영문자 1개 이상, 숫자 1개 이상.
    저장된 hash 를 보지 않고 **평문 후보**만 검사한다.

    :param password: 검사할 평문 비밀번호 후보(``None``/빈 문자열은 거부).
    :return: ``(통과 여부, 사유 문자열)``. 통과면 사유는 빈 문자열.
    """
    if not password:
        return False, "비밀번호를 입력해주세요."
    if len(password) < MIN_STRONG_LENGTH:
        return False, f"비밀번호는 {MIN_STRONG_LENGTH}자 이상이어야 합니다."
    has_letter = any(ch.isalpha() for ch in password)
    has_digit = any(ch.isdigit() for ch in password)
    if not (has_letter and has_digit):
        return False, "비밀번호는 영문자와 숫자를 모두 포함해야 합니다."
    return True, ""


def is_password_strong(password: Optional[str]) -> bool:
    """:func:`validate_password_strength` 의 bool 어댑터(기존 호출부 호환).

    :param password: 평문 비밀번호 후보.
    :return: 강도 정책 통과 여부.
    """
    ok, _reason = validate_password_strength(password)
    return ok


def set_strong_password(user: Any, plaintext: Optional[str]) -> None:
    """user 의 비밀번호를 강도 검사 후 hash 로 설정하고 버전을 STRONG 으로 기록한다.

    비밀번호 설정의 **유일한 chokepoint**. 강도 검사를 통과하지 못하면
    :class:`WeakPasswordError` 를 던지고 user 를 건드리지 않는다(약한 비번 거부이자
    weak rollback 거부 — 한번 strong 이 된 계정도 이 경로 외로는 약한 값이 될 수 없다).

    :param user: ``password``/``password_policy_version`` 속성을 가진 User(미저장도 허용).
    :param plaintext: 설정할 평문 비밀번호. 즉시 hash 되며 원문은 보관하지 않는다.
    :raises WeakPasswordError: 강도 정책 미달.
    """
    ok, reason = validate_password_strength(plaintext)
    if not ok:
        raise WeakPasswordError(reason)
    user.password = generate_password_hash(plaintext)
    user.password_policy_version = POLICY_VERSION_STRONG


def is_password_legacy(user: Any) -> bool:
    """user 의 비밀번호가 legacy(강도 미검증)인지 컬럼 SSOT 로 판정한다.

    저장된 hash 를 rehash 하지 않고 ``password_policy_version`` 컬럼만 읽는다.

    :param user: ``password_policy_version`` 속성을 가진 User(``None`` 은 False).
    :return: legacy 이면 True.
    """
    if user is None:
        return False
    version = getattr(user, "password_policy_version", POLICY_VERSION_LEGACY)
    return (version or POLICY_VERSION_LEGACY) < POLICY_VERSION_STRONG


def _legacy_version_filter():
    """``password_policy_version`` 이 STRONG 미만(=legacy)인 SQLAlchemy 조건."""
    from models import User

    return User.password_policy_version < POLICY_VERSION_STRONG


def active_legacy_count(db: Any) -> int:
    """active(is_active=True) legacy 사용자 수를 반환한다.

    ENFORCED 전환 판정과 CLI readiness 의 기준. 비활성 계정은 세지 않는다(reactivate
    시 강도 재검사로 걸러지므로 ENFORCED 준비도에서 제외).

    :param db: SQLAlchemy 세션.
    :return: active legacy 사용자 수.
    """
    from models import User

    return (
        db.query(User)
        .filter(User.is_active.is_(True), _legacy_version_filter())
        .count()
    )


def legacy_counts_by_role(db: Any, *, active_only: bool = True) -> dict[str, int]:
    """role 별 legacy 사용자 수를 반환한다(Admin 목록·CLI 감사용, hash/평문 미노출).

    :param db: SQLAlchemy 세션.
    :param active_only: True 면 active 계정만 집계(기본).
    :return: ``{role: count}`` (legacy 가 있는 role 만 포함).
    """
    from sqlalchemy import func

    from models import User

    query = db.query(User.role, func.count(User.id)).filter(_legacy_version_filter())
    if active_only:
        query = query.filter(User.is_active.is_(True))
    rows = query.group_by(User.role).all()
    return {role: count for role, count in rows}


def is_policy_enforced(db: Any) -> bool:
    """정책이 ENFORCED 상태인지(active legacy count == 0) 반환한다.

    :param db: SQLAlchemy 세션.
    :return: active legacy 가 하나도 없으면 True(ENFORCED), 아니면 False(WARN).
    """
    return active_legacy_count(db) == 0
