"""PASSWORD-POLICY-01 — 비밀번호 강도 정책 감사·회전 CLI (operator maintenance).

두 가지 operator 작업을 제공한다.

    python tools/ops/password_policy_audit.py audit
    python tools/ops/password_policy_audit.py rotate <username>

``audit`` 는 누가 legacy 인지, role 별 count, ENFORCED 준비도(active legacy count 0)를
보고한다 — **비밀번호 hash/평문을 절대 출력하지 않는다**(상태만).

``rotate`` 는 대상 사용자의 비밀번호를 강력한 새 값으로 교체한다. 비밀번호는 argv/env 가
아니라 **비에코 터미널 프롬프트(getpass)** 로만 읽고, 즉시 hash 하며, stdout/log 에 절대
쓰지 않는다(STARTUP-ADMIN-01 ``bootstrap_admin.py`` 패턴). 약한 비번은 거부한다(약한
비번 거부이자 weak rollback 거부). 성공 시 ``password_policy_version`` 이 STRONG 으로
기록되어 감사·ENFORCED count 에 즉시 반영된다.
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from db import db_session, init_db  # noqa: E402
from models import User  # noqa: E402
from foms.services.security.password_policy import (  # noqa: E402
    WeakPasswordError,
    active_legacy_count,
    is_password_legacy,
    is_policy_enforced,
    legacy_counts_by_role,
    set_strong_password,
)
from foms.services.security.password_policy import (  # noqa: E402
    _legacy_version_filter as legacy_version_filter,
)


def run_audit(session) -> int:
    """legacy 감사·ENFORCED 준비도를 보고한다(hash/평문 미출력).

    :param session: SQLAlchemy 세션.
    :return: 프로세스 exit code(0=정상).
    """
    total = session.query(User).count()
    active_legacy = active_legacy_count(session)
    by_role = legacy_counts_by_role(session, active_only=True)
    enforced = is_policy_enforced(session)

    print("[PASSWORD-POLICY] audit")
    print(f"  전체 사용자: {total}")
    print(f"  활성 legacy 계정: {active_legacy}")
    print(f"  role별 활성 legacy: {by_role or '{}'}")
    print(f"  정책 상태: {'ENFORCED (활성 legacy 0)' if enforced else 'WARN (legacy 잔존)'}")

    legacy_rows = (
        session.query(User)
        .filter(legacy_version_filter())
        .order_by(User.is_active.desc(), User.role, User.username)
        .all()
    )
    if legacy_rows:
        print("  legacy 계정 목록 (상태만 — 비밀번호 미노출):")
        for u in legacy_rows:
            state = "active" if u.is_active else "inactive"
            print(f"    - {u.username} (role={u.role}, {state})")
    return 0


def run_rotate(session, username: str) -> int:
    """대상 사용자의 비밀번호를 강력한 새 값으로 회전한다(getpass·비밀번호 미출력).

    :param session: SQLAlchemy 세션.
    :param username: 대상 사용자명(비밀번호가 아니므로 argv 허용).
    :return: exit code(0=성공, 1=대상 없음, 2=약한 비번 거부).
    """
    user = session.query(User).filter_by(username=username).first()
    if user is None:
        print(f"[REFUSED] 사용자 '{username}' 를 찾을 수 없습니다.")
        return 1

    was_legacy = is_password_legacy(user)
    password = getpass.getpass(f"'{username}' 새 비밀번호: ")
    confirm = getpass.getpass("새 비밀번호 확인: ")
    if password != confirm:
        print("[REFUSED] 비밀번호가 일치하지 않습니다.")
        return 2
    try:
        set_strong_password(user, password)
    except WeakPasswordError as exc:
        # 사유만 출력하고 비밀번호는 절대 출력하지 않는다.
        print(f"[REFUSED] 강도 미달 — {exc}")
        return 2
    session.commit()
    remaining = active_legacy_count(session)
    print(f"[PASSWORD-POLICY] '{username}' 비밀번호 회전 완료 (STRONG 기록).")
    if was_legacy:
        print(f"  남은 활성 legacy 계정: {remaining}"
              f"{' — ENFORCED 준비 완료' if remaining == 0 else ''}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """CLI 인자 파서를 구성한다(password 는 인자로 받지 않는다)."""
    parser = argparse.ArgumentParser(description="비밀번호 강도 정책 감사·회전")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("audit", help="legacy 감사·ENFORCED 준비도 보고")
    sub.add_parser("readiness", help="audit 의 별칭(ENFORCED 준비도)")
    rot = sub.add_parser("rotate", help="대상 사용자 비밀번호 회전(getpass)")
    rot.add_argument("username", help="회전할 사용자명(비밀번호 아님)")
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI 엔트리포인트: password 는 절대 argv/env/log 로 받지 않는다."""
    args = build_parser().parse_args(argv)
    init_db()
    try:
        if args.command in ("audit", "readiness"):
            return run_audit(db_session)
        if args.command == "rotate":
            return run_rotate(db_session, args.username)
        return 1
    except Exception as exc:  # noqa: BLE001 - operator exit code 로 표면화
        db_session.rollback()
        print(f"[PASSWORD-POLICY] 실패: {exc}")
        return 1
    finally:
        db_session.close()


if __name__ == "__main__":
    raise SystemExit(main())
