"""master brain — 지식 문서를 표로 옮기기(판 0) · 그림자 견주기 관리자 스크립트(설계서 2026-11-02-haud-master-brain 7.5 끝 · D97).

**기본은 모의 실행이다**: 브랜드마다 저장된 지식 문서를 읽어 옮기기 계획(만들기 · 고치기 · 지우기 · 같음 — 키 · 개수만)과
지금 표에서 다시 만든 문서와의 견줌(항목 id · 칸 이름만)을 낸다. 글 · 가격은 내지 않는다. ``--apply`` 를 줘야 쓴다.

- 쓰기는 :mod:`foms.services.brain.doc_import` 한 길이다(옮기기 제안 → 반영 동작, 판 0 · 근거 종류 ``import``). 멱등 —
  다시 돌리면 같은 항목은 쓰지 않는다. 커밋은 여기서.
- ``--apply`` 에는 ``--actor``(켜진 ADMIN 아이디)가 꼭 있어야 한다. 운영 막기는 기준 답 스크립트
  (``tools/ops/cs_agent_knowledge.py``)의 환경 판정을 그대로 쓴다 — local · staging 밖은 ``--i-have-owner-approval`` 없이 쓰지 않는다.
- ``--compare`` 는 읽기만 한다(견줌만).
- **표가 정본이다**(3.1 규칙 1): 옮기기는 사람이 승인한 판 · 링크가 닿은 항목을 고치거나 지우거나 나누지 않고(``unmanaged`` ·
  ``protected`` 로 알림), 표에서 다시 만든 문서가 저장된 문서와 같으면 아무것도 하지 않는다. 반영 동작은 지식 문서 유형 항목을
  바꿀 때마다 지식 문서를 표에서 다시 쓴다(:mod:`foms.services.brain.doc_sync`).
- ``--publish`` = 맞추기(표 → 문서): 브랜드마다 표에서 다시 만든 문서를 새 버전으로 넣는다(문서를 직접 고쳐 반영이 멈출 때 —
  ``BRAIN_DOC_SYNC``). 문서에만 있던 글은 빠진다(수정 기록에는 남는다). ``--apply`` 와 같은 막기(``--actor`` · 운영 승인 표시).

사용 예 (PowerShell 5.x)::

    python scripts/maintenance/brain_import_knowledge.py
    python scripts/maintenance/brain_import_knowledge.py --compare --brand LAHOM
    python scripts/maintenance/brain_import_knowledge.py --apply --actor <ADMIN 아이디>
    python scripts/maintenance/brain_import_knowledge.py --publish --actor <ADMIN 아이디>
"""
import argparse
import importlib.util
import json
import os
import sys
from typing import Any, Optional

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, ROOT)

from app import app  # noqa: E402
from db import DB_URL, db_session  # noqa: E402
from foms.platform.sentry_setup import resolve_environment  # noqa: E402
from foms.services.brain import doc_bridge, doc_import, doc_sync  # noqa: E402
from foms.services.brain.errors import BrainError  # noqa: E402
from foms.services.cs_agent.knowledge import KNOWN_BRANDS  # noqa: E402

EXIT_OK, EXIT_REFUSED = 0, 1


def _knowledge_tool() -> Any:
    """기준 답 관리자 스크립트(환경 판정 · ADMIN 확인 · 멈춤 까닭)를 그대로 불러 쓴다."""
    path = os.path.join(ROOT, "tools", "ops", "cs_agent_knowledge.py")
    spec = importlib.util.spec_from_file_location("cs_agent_knowledge_tool", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TOOL = _knowledge_tool()
Refused = TOOL.Refused


def parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    """CLI 인자."""
    parser = argparse.ArgumentParser(description="master brain — import knowledge documents (default dry-run) / compare.")
    parser.add_argument("--compare", action="store_true", help="견줌만(읽기만)")
    parser.add_argument("--brand", choices=sorted(KNOWN_BRANDS), help="--compare · --publish 할 브랜드(없으면 모두)")
    parser.add_argument("--apply", action="store_true", help="실제로 옮긴다(기본은 모의 실행)")
    parser.add_argument("--publish", action="store_true", help="맞추기: 표에서 다시 만든 지식 문서를 넣는다(표 → 문서)")
    parser.add_argument("--actor", help="--apply · --publish 때 꼭: 반영하는 사람(켜진 ADMIN 아이디)")
    parser.add_argument("--i-have-owner-approval", dest="owner_approval", action="store_true",
                        help="local · staging 밖(운영)에 쓸 때 꼭: 사장님이 옮기기를 승인했다")
    return parser.parse_args(argv)


def check_apply(args: argparse.Namespace, environment: str) -> None:
    """``--apply`` · ``--publish`` 앞 검사 — DB 를 건드리기 전에 모두 본다."""
    if args.compare:
        raise Refused("APPLY_WITH_COMPARE", "--apply · --publish 는 --compare 와 같이 쓰지 않는다")
    if args.apply and args.publish:
        raise Refused("APPLY_WITH_PUBLISH", "--apply(문서 → 표)와 --publish(표 → 문서)는 같이 쓰지 않는다")
    if not args.actor:
        raise Refused("ACTOR_REQUIRED", "--apply · --publish 에는 --actor(켜진 ADMIN 아이디)가 있어야 한다")
    if TOOL.needs_owner_approval(environment) and not args.owner_approval:
        raise Refused("OWNER_APPROVAL_REQUIRED",
                      f"{environment} 에는 사장님 승인 표시(--i-have-owner-approval) 없이 쓰지 않는다")


def compare(session: Any, brands: list) -> list:
    """브랜드마다 저장 문서 ↔ 표에서 다시 만든 문서."""
    return [doc_bridge.shadow_compare(session, brand) for brand in brands]


def publish(session: Any, args: argparse.Namespace) -> dict:
    """맞추기(표 → 문서) — 브랜드마다 새 버전 · 차이(항목 id · 칸 이름만) 뒤 견줌."""
    actor_id = TOOL.resolve_actor(session, args.actor)
    brands = [args.brand] if args.brand else sorted(KNOWN_BRANDS)
    out: dict = {"mode": "publish", "publish": doc_sync.publish_documents(session, actor_id=actor_id, brands=brands)}
    session.commit()
    out["compare"] = compare(session, brands)
    return out


def work(session: Any, args: argparse.Namespace) -> dict:
    """모의 실행 · 옮기기 · 맞추기 · 견줌."""
    if args.compare:
        return {"mode": "compare", "compare": compare(session, [args.brand] if args.brand else sorted(KNOWN_BRANDS))}
    if args.publish:
        return publish(session, args)
    versions, problems = doc_import.load_documents(session)
    out: dict = {"mode": "import", "documents": {b: v for b, (v, _doc) in sorted(versions.items())},
                 "document_problems": problems}
    if problems:
        raise Refused("DOCUMENT_UNREADABLE", "저장된 지식 문서 꼴이 틀린 브랜드가 있다 — 옮기지 않는다")
    actor = session.get(TOOL.User, TOOL.resolve_actor(session, args.actor)) if args.apply else None
    out["import"] = doc_import.run_import(session, versions, actor=actor, apply=args.apply)
    if args.apply:
        session.commit()
    out["compare"] = compare(session, sorted(versions))
    return out


def _print(out: dict) -> None:
    """JSON 출력(PS-ENC-01 — cp949 콘솔에서도 한글이 깨지지 않게 UTF-8 로)."""
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2), flush=True)


def run(argv: Optional[list] = None) -> int:
    """CLI 진입점.

    Returns:
        0 = 정상(모의 실행 · 옮김 · 견줌), 1 = 쓰지 않고 멈춤(운영 막기 · ADMIN 아님 · 문서 꼴 · brain 반영 오류).
    """
    args = parse_args(argv)
    environment = TOOL.target_environment(resolve_environment(), DB_URL, os.environ.get("RAILWAY_PROJECT_NAME"),
                                          os.environ.get("RAILWAY_SERVICE_ID"))
    out: dict = {"environment": environment, "applied": False}
    try:
        if args.apply or args.publish:
            check_apply(args, environment)
        with app.app_context():
            try:
                out.update(work(db_session, args))
            finally:
                db_session.rollback()  # 모의 실행 · 멈춤의 트랜잭션을 닫는다(옮긴 것은 이미 커밋)
                db_session.remove()
    except (Refused, BrainError) as exc:
        out.update(ok=False, error=getattr(exc, "code", "ERROR"), message=str(exc))
        if getattr(exc, "problems", None):
            out["problems"] = list(exc.problems)
        _print(out)
        return EXIT_REFUSED
    out["ok"] = True
    published = any(entry.get("diff") for entry in out.get("publish", {}).values())
    out["applied"] = bool(out.get("import", {}).get("applied")) or published
    _print(out)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(run())
