"""master brain — 사장님이 승인한 자료 계획을 **열린 제안**으로 넣는 관리자 스크립트(설계서 7.8 '자료(제안)' · D130).

**기본은 모의 실행이다**: 계획 파일(저장소 밖 JSON — 금액이 들어 있다)을 읽어 넣을 제안을 저장점 안에서 만들어 보고 되돌린 뒤,
동작별 · 까닭별 **수만** 낸다(항목 글 · 이름 · 금액은 내지 않는다 — 못 찾은 가리킴은 항목 키만). ``--apply`` 를 줘야 넣는다.

- 쓰기는 :mod:`foms.services.brain.plan_proposals` 한 길이다 — 옮기기 묶음 제안만 만들고 **반영하지 않는다**(카드마다 승인 화면에서
  사장님 · 팀장이 누른다). 멱등 — 다시 돌려도 같은 제안은 다시 넣지 않고, 승인 대기 항목에 걸린 링크 · 은퇴는 승인 뒤 다시
  돌리면 들어간다(``deferred``). 커밋은 여기서.
- 운영 막기는 기준 답 스크립트(``tools/ops/cs_agent_knowledge.py``)의 환경 판정을 그대로 쓴다 — local · staging 밖은
  ``--i-have-owner-approval`` 없이 넣지 않는다.

사용 예 (PowerShell 5.x)::

    python scripts/maintenance/brain_plan_proposals.py --plan <계획 JSON 경로>
    python scripts/maintenance/brain_plan_proposals.py --plan <계획 JSON 경로> --apply
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
from foms.services.brain.errors import BrainError  # noqa: E402
from foms.services.brain.plan_links import source_name  # noqa: E402
from foms.services.brain.plan_proposals import file_plan, withdraw_open  # noqa: E402
from foms.services.datetime_kst import now_utc_naive  # noqa: E402
from foms.services.cs_agent.knowledge import KNOWN_BRANDS  # noqa: E402

EXIT_OK, EXIT_REFUSED = 0, 1


def _knowledge_tool() -> Any:
    """기준 답 관리자 스크립트(환경 판정 · 멈춤 까닭)를 그대로 불러 쓴다."""
    path = os.path.join(ROOT, "tools", "ops", "cs_agent_knowledge.py")
    spec = importlib.util.spec_from_file_location("cs_agent_knowledge_tool", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TOOL = _knowledge_tool()
Refused = TOOL.Refused


def parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    """CLI 인자."""
    parser = argparse.ArgumentParser(description="master brain — file the approved data plan as open proposals "
                                                 "(default dry-run, never applies).")
    parser.add_argument("--plan", required=True, help="자료 계획 JSON 경로(저장소 밖)")
    parser.add_argument("--brand", default="LAHOM", choices=sorted(KNOWN_BRANDS), help="계획의 브랜드(기본 LAHOM)")
    parser.add_argument("--apply", action="store_true", help="실제로 제안을 넣는다(기본은 모의 실행)")
    parser.add_argument("--i-have-owner-approval", dest="owner_approval", action="store_true",
                        help="local · staging 밖(운영)에 넣을 때 꼭: 사장님이 자료 계획을 승인했다")
    parser.add_argument("--withdraw-open", dest="withdraw_open", action="store_true",
                        help="넣기 전에 이 계획이 넣고 아직 아무도 결정하지 않은 제안을 거둔다(계획을 고친 뒤 다시 넣을 때 — "
                             "결정된 제안은 건드리지 않는다)")
    return parser.parse_args(argv)


def read_plan(path: str) -> tuple[dict, str]:
    """계획 파일(UTF-8 JSON — 앞 BOM 은 된다)과 근거 자리 이름. 오류에는 파일 글을 싣지 않는다."""
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            plan = json.load(handle)
    except (OSError, ValueError):
        raise Refused("PLAN_UNREADABLE", "계획 파일을 읽지 못했다(경로 · JSON 꼴)") from None
    if not isinstance(plan, dict):
        raise Refused("PLAN_UNREADABLE", "계획 파일이 JSON 객체가 아니다")
    stem = os.path.splitext(os.path.basename(path))[0]
    return plan, source_name(plan if plan.get("schema") else {"schema": stem})


def run(argv: Optional[list] = None) -> int:
    """CLI 진입점.

    Returns:
        0 = 정상(모의 실행 · 넣음), 1 = 쓰지 않고 멈춤(운영 막기 · 계획 파일 · 계획 꼴).
    """
    args = parse_args(argv)
    environment = TOOL.target_environment(resolve_environment(), DB_URL, os.environ.get("RAILWAY_PROJECT_NAME"),
                                          os.environ.get("RAILWAY_SERVICE_ID"))
    out: dict = {"environment": environment, "applied": False}
    try:
        if args.apply and TOOL.needs_owner_approval(environment) and not args.owner_approval:
            raise Refused("OWNER_APPROVAL_REQUIRED",
                          f"{environment} 에는 사장님 승인 표시(--i-have-owner-approval) 없이 넣지 않는다")
        plan, source = read_plan(args.plan)
        with app.app_context():
            try:
                if args.withdraw_open:  # 모의 실행이면 거둔 수만 세고 아래 rollback 이 되돌린다
                    out["withdrawn"] = withdraw_open(db_session, source=source, now=now_utc_naive())
                out.update(file_plan(db_session, plan, brand=args.brand, apply=args.apply, source=source))
                if args.apply:
                    db_session.commit()
            finally:
                db_session.rollback()  # 모의 실행 · 멈춤의 트랜잭션을 닫는다(넣은 것은 이미 커밋)
                db_session.remove()
    except (Refused, BrainError) as exc:
        out.update(ok=False, error=getattr(exc, "code", "ERROR"), message=str(exc))
        if getattr(exc, "problems", None):
            out["problems"] = list(exc.problems)
        _print(out)
        return EXIT_REFUSED
    out["ok"] = True
    _print(out)
    return EXIT_OK


def _print(out: dict) -> None:
    """JSON 출력(PS-ENC-01 — cp949 콘솔에서도 한글이 깨지지 않게 UTF-8 로)."""
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    sys.exit(run())
