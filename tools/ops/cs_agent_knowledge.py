"""AI 상담팀원 기준 답 · 지식 — 넣기 · 보기 · 되돌리기 관리자 스크립트(플랜 C2-1 · 설계서 7.1 C2-0 확정안 4 · 6).

기본은 모의 실행이다: 문서를 검사하고 지금 버전과 견준 요약(종류 · 상태별 개수, 더함 · 뺌 · 바뀜 항목 id, 재료에
새로 들어가는 · 빠지는 항목 id)만 낸다. 기준 답 글 · 가격은 화면에 내지 않는다. ``--apply`` 를 줘야 쓴다.

- 쓰기는 :mod:`foms.services.cs_agent.knowledge` 한 길이다(버전 대조 · 수정 기록 · 감사 원장, 커밋은 여기서).
- ``--apply`` 에는 ``--expected-version``(모의 실행이 알려 준 지금 버전)과 ``--actor``(켜진 ADMIN 아이디)가 꼭 있어야
  한다. 그사이 다른 사람이 넣었으면 버전이 달라 쓰지 않는다 — 모의 실행부터 다시.
- **운영 막기**: 실행 환경이 local · staging 이 아니면 ``--i-have-owner-approval`` 없이는 쓰지 않는다(C2-0 확정안 4).
  환경은 :func:`target_environment` 가 막는 쪽으로 정한다 — Railway 가 넣는 ``RAILWAY_PROJECT_NAME`` 이 ``-PRODUCTION``
  이면 늘 운영. 표시 없이 쓰는 곳은 둘뿐이다: DB 가 sqlite 파일이거나, ``RAILWAY_PROJECT_NAME`` 이 ``-DEV`` 이고
  Railway 가 넣은 서비스 표지(``RAILWAY_SERVICE_ID``)도 있을 때(스테이징 컨테이너 · ``railway run``). 그 밖은 —
  localhost 도 운영 DB 로 판 굴일 수 있고, PC 에 남은 ``FOMS_ENV`` · 프로젝트 이름은 믿지 않는다(원장 K-2 · R6-14) —
  ``unknown-remote`` 로 보고 운영과 같이 막는다. 사장님은 넣기 전에 묶음마다 승인하므로(C2-0 확정안 3) PC 에서는
  스테이징에도 표시를 붙인다. 모의 실행 · ``--show`` 는 읽기만 하므로 어디서나 된다.
- 항목마다의 승인(``approved_by`` · ``approved_at``)은 문서 안에 있고, ``--actor`` 는 넣은 사람(수정 기록 · 감사 주체)이다.
- 앱을 부팅해 쓴다(``run_cs_loop.py`` 와 같다) — ``system_settings`` 쓰기가 화면 304 판정 카운터를 올리게.

사용 예 (PowerShell 5.x)::

    python tools/ops/cs_agent_knowledge.py --brand LAHOM --show
    python tools/ops/cs_agent_knowledge.py --brand LAHOM --file <문서.json>
    python tools/ops/cs_agent_knowledge.py --brand LAHOM --file <문서.json> --apply --expected-version 3 --actor <ADMIN 아이디>
    python tools/ops/cs_agent_knowledge.py --brand LAHOM --rollback 2
    python tools/ops/cs_agent_knowledge.py --brand LAHOM --rollback 2 --apply --expected-version 4 --actor <ADMIN 아이디>
"""
import argparse
import json
import os
import sys
from typing import Any, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))

from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.exc import ArgumentError  # noqa: E402

from app import app  # noqa: E402
from db import DB_URL, db_session  # noqa: E402
from foms.platform.sentry_setup import resolve_environment  # noqa: E402
from foms.services.cs_agent import knowledge  # noqa: E402
from models import User  # noqa: E402

ENV_LOCAL, ENV_STAGING, ENV_PRODUCTION, ENV_UNKNOWN_REMOTE = "local", "staging", "production", "unknown-remote"
#: 사장님 승인 표시 없이 쓸 수 있는 환경. 그 밖(production · unknown-remote · 모르는 이름)은 모두 표시가 있어야 한다.
FREE_WRITE_ENVIRONMENTS = frozenset({ENV_LOCAL, ENV_STAGING})
EXIT_OK, EXIT_REFUSED = 0, 1


class Refused(Exception):
    """쓰지 않고 멈춘다 — 까닭 코드와 사람이 읽을 글."""

    def __init__(self, code: str, message: str) -> None:
        """까닭 코드를 싣는다."""
        super().__init__(message)
        self.code = code


def parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    """CLI 인자."""
    parser = argparse.ArgumentParser(description="AI CS agent knowledge — load / show / rollback (default dry-run).")
    parser.add_argument("--brand", required=True, choices=sorted(knowledge.KNOWN_BRANDS))
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--file", help="넣을 문서(JSON, UTF-8)")
    mode.add_argument("--rollback", type=int, metavar="VERSION", help="이 버전 문서로 되돌린다(새 버전으로 쓴다)")
    mode.add_argument("--show", action="store_true", help="지금 버전 · 개수 · 최근 수정 기록만 본다")
    parser.add_argument("--apply", action="store_true", help="실제로 쓴다(기본은 모의 실행)")
    parser.add_argument("--expected-version", type=int, help="--apply 때 꼭: 모의 실행이 알려 준 지금 버전")
    parser.add_argument("--actor", help="--apply 때 꼭: 넣는 사람(켜진 ADMIN 아이디)")
    parser.add_argument("--i-have-owner-approval", dest="owner_approval", action="store_true",
                        help="local · staging 밖(운영)에 쓸 때 꼭: 사장님이 이 묶음을 승인했다")
    return parser.parse_args(argv)


def _file_database(db_url: str) -> bool:
    """DB 가 sqlite 파일인가(서버일 수 없다). 주소를 읽을 수 없으면 아니다."""
    try:
        return make_url(db_url).get_backend_name() == "sqlite"
    except ArgumentError:
        return False


def target_environment(environment: str, db_url: str, project_name: Optional[str] = None,
                       service_id: Optional[str] = None) -> str:
    """쓰기 대상 환경 — 막는 쪽으로 닫힌다(모듈 설명 '운영 막기').

    Args:
        environment: ``resolve_environment()`` 값(``FOMS_ENV`` 가 먼저라 PC 에 남은 값일 수 있다).
        db_url: 앱이 붙은 DB 주소(``db.DB_URL`` — 비밀번호가 들어 있어 어디에도 찍지 않는다).
        project_name: ``RAILWAY_PROJECT_NAME``(Railway 컨테이너 · ``railway run`` 에 있다).
        service_id: ``RAILWAY_SERVICE_ID``(같은 곳에서 Railway 가 넣는 서비스 표지).

    Returns:
        환경 이름.
    """
    project = (project_name or "").strip().upper()
    if project.endswith("-PRODUCTION"):
        return ENV_PRODUCTION
    if _file_database(db_url):
        return environment
    if project.endswith("-DEV") and (service_id or "").strip():
        return ENV_STAGING
    return ENV_PRODUCTION if environment == ENV_PRODUCTION else ENV_UNKNOWN_REMOTE


def needs_owner_approval(environment: str) -> bool:
    """이 환경에 쓰려면 사장님 승인 표시가 있어야 하나."""
    return environment not in FREE_WRITE_ENVIRONMENTS


def read_document(path: str) -> Any:
    """문서 파일(JSON, UTF-8 — 앞 BOM 은 된다). 오류에는 파일 글을 싣지 않는다."""
    try:
        with open(path, encoding="utf-8-sig") as handle:
            return json.load(handle)
    except OSError as exc:
        raise Refused("FILE_UNREADABLE", f"문서 파일을 열 수 없다: {exc.strerror}") from exc
    except UnicodeDecodeError as exc:
        raise Refused("FILE_NOT_UTF8", "문서 파일이 UTF-8 이 아니다") from exc
    except json.JSONDecodeError as exc:
        raise Refused("FILE_NOT_JSON", f"JSON 이 아니다: {exc.lineno}줄 {exc.colno}칸 ({exc.msg})") from exc


def check_apply(args: argparse.Namespace, environment: str) -> None:
    """``--apply`` 앞 검사 — DB 를 건드리기 전에 모두 본다."""
    if args.show:
        raise Refused("APPLY_NEEDS_CHANGE", "--apply 는 --file · --rollback 과만 쓴다")
    if args.expected_version is None:
        raise Refused("EXPECTED_VERSION_REQUIRED", "--apply 에는 --expected-version(모의 실행이 알려 준 지금 버전)이 있어야 한다")
    if not args.actor:
        raise Refused("ACTOR_REQUIRED", "--apply 에는 --actor(켜진 ADMIN 아이디)가 있어야 한다")
    if needs_owner_approval(environment) and not args.owner_approval:
        raise Refused("OWNER_APPROVAL_REQUIRED",
                      f"{environment} 에는 사장님 승인 표시(--i-have-owner-approval) 없이 쓰지 않는다")


def resolve_actor(session: Any, username: str) -> int:
    """넣는 사람 — 켜진 ADMIN 계정의 id."""
    user = session.query(User).filter(User.username == username).one_or_none()
    if user is None or not user.is_active or str(user.role or "").upper() != "ADMIN":
        raise Refused("ACTOR_NOT_ADMIN", "--actor 는 켜진 ADMIN 계정이어야 한다")
    return int(user.id)


def show(session: Any, brand: str) -> dict[str, Any]:
    """지금 버전 · 개수 · 최근 수정 기록(글 없음)."""
    stored = knowledge.read_stored(session, brand)
    return {"mode": "show", "version": stored.version, "problem": stored.problem,
            "counts": knowledge.count_items(stored.document), "history": knowledge.history(session, brand)}


def _next_hint(version: int, environment: str) -> str:
    """모의 실행 뒤 넣는 명령의 꼬리."""
    hint = f"--apply --expected-version {version} --actor <ADMIN 아이디>"
    return hint + (" --i-have-owner-approval" if needs_owner_approval(environment) else "")


def change(session: Any, args: argparse.Namespace, environment: str) -> dict[str, Any]:
    """``--file`` · ``--rollback`` — 모의 실행이면 차이만, ``--apply`` 면 쓰고 커밋한다."""
    brand = args.brand
    stored = knowledge.read_stored(session, brand)
    document = (knowledge.validate_document(read_document(args.file), brand=brand) if args.file
                else knowledge.version_document(session, brand, args.rollback))
    diff = knowledge.diff_documents(stored.document, document)
    out: dict[str, Any] = {"mode": "load" if args.file else "rollback", "applied": False,
                           "current_version": stored.version, "stored_problem": stored.problem,
                           "restore_version": args.rollback, "owner_approval_required": needs_owner_approval(environment),
                           "diff": diff.summary()}
    if not args.apply:
        out["next"] = _next_hint(stored.version, environment) if diff.has_changes() else "바뀐 것 없음 — 넣지 않는다"
        return out
    actor_user_id = resolve_actor(session, args.actor)
    if args.file:
        result = knowledge.save_document(session, brand, document, actor_user_id=actor_user_id,
                                         expected_version=args.expected_version)
    else:
        result = knowledge.rollback(session, brand, args.rollback, actor_user_id=actor_user_id,
                                    expected_version=args.expected_version)
    session.commit()
    out.update(applied=True, version=result.version, receipt_id=result.receipt_id, diff=result.diff.summary())
    return out


def _refusal(exc: Exception) -> dict[str, Any]:
    """멈춘 까닭 → 출력 칸(문서 문제는 자리 · 까닭만, 충돌은 지금 버전)."""
    out: dict[str, Any] = {"ok": False, "error": getattr(exc, "code", "ERROR"), "message": str(exc)}
    if isinstance(exc, knowledge.KnowledgeSchemaError):
        out["problems"] = list(exc.problems)
    if isinstance(exc, knowledge.KnowledgeConflictError):
        out["current_version"] = exc.current_version
    return out


def _print(out: dict[str, Any]) -> None:
    """JSON 출력(PS-ENC-01 — cp949 콘솔에서도 한글이 깨지지 않게 UTF-8 로)."""
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2), flush=True)


def run(argv: Optional[list] = None) -> int:
    """CLI 진입점.

    Returns:
        0 = 정상(모의 실행 · 보기 · 넣음), 1 = 쓰지 않고 멈춤(문서 꼴 · 버전 충돌 · 운영 막기 · 기록 없음 등).
    """
    args = parse_args(argv)
    environment = target_environment(resolve_environment(), DB_URL, os.environ.get("RAILWAY_PROJECT_NAME"),
                                     os.environ.get("RAILWAY_SERVICE_ID"))
    out: dict[str, Any] = {"brand": args.brand, "environment": environment}
    try:
        if args.apply:
            check_apply(args, environment)
        with app.app_context():
            try:
                out.update(show(db_session, args.brand) if args.show else change(db_session, args, environment))
            finally:
                db_session.rollback()  # 모의 실행 · 멈춤의 트랜잭션을 닫는다(넣은 것은 이미 커밋)
                db_session.remove()
    except (Refused, knowledge.KnowledgeError) as exc:
        out.update(_refusal(exc))
        _print(out)
        return EXIT_REFUSED
    out["ok"] = True
    _print(out)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(run())
