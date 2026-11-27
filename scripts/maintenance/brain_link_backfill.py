"""회사 지식 — 쌓인 지식을 한 번에 잇는 되채우기 관리자 스크립트(설계 글 ``docs/specs/2026-11-26-brain-ontology-linking_SPEC.md``
7.3 · 사장님 11-26 '뻔한 것은 AI가 바로' · 11-27 "공정 단계만 여쭙게 하고 켜기").

**기본은 미리 돌려 보기다**: 잇기 계획 파일(저장소 밖 JSON — 사람 세션이 지식 전체를 읽어 만든 목록, 여러 묶음은 ``--plan`` 을
여러 번)을 읽어 밤 이어 붙이기와 **같은 거르기 · 가름 규칙**으로 '바로 넣을 것 / 사장님께 올릴 것'을 저장점 안에서 끝까지 돌려 보고
되돌린 뒤 **수만** 낸다(글 · 이름 · 금액은 내지 않는다 — 버린 줄의 차례 · 키는 ``--show-dropped`` 일 때만). ``--apply`` 를 줘야
넣는다.

- 쓰기는 :func:`foms.services.cs_agent.handoff_learning_backfill.run_backfill` 한 길이다 — 계획 꼴 · 거르기 · 가름 · 넣는 길 ·
  내는 수 칸은 그 모듈 머리말. 멱등 — 다시 돌려도 들어간 잇기 · 열린 같은 제안은 다시 넣지 않는다. 시작 지식에 사람 근거 둘이
  없는 줄(옮기기 · 사장님 승인 · 직접 고침으로 생긴 판)은 버리지 않고 옮기기 묶음 제안으로 올린다(``ask_why.no_evidence`` — 바로 넣지
  않는다).
- 운영 막기는 기준 답 스크립트(``tools/ops/cs_agent_knowledge.py``)의 환경 판정을 그대로 쓴다 — local · staging 밖은
  ``--i-have-owner-approval`` 없이 넣지 않는다(미리 돌려 보기는 쓰기 0 이라 막지 않는다).
- 작게 시작: ``--only auto`` · ``--only ask`` 로 한쪽만, ``--limit N`` 으로 앞 N 줄만, ``--kinds a,b`` 로 종류만. 한 번에 올리는 수는
  ``--max-ask``(기본 60 — 사장님 하루 몫, 넘는 것은 ``ask_left`` 로 세고 다음 실행이 넣는다).

사용 예 (Git Bash — 표준 입력 ``<`` 은 PowerShell 5.x 에 없다)::

    python scripts/maintenance/brain_link_backfill.py --plan <계획 JSON> --plan <둘째 묶음 JSON>
    python scripts/maintenance/brain_link_backfill.py --plan <계획 JSON> --apply --only auto --limit 20
    railway ssh -s web -e production -- python scripts/maintenance/brain_link_backfill.py --plan - < <계획 JSON>
    railway ssh -s web -e production -- python scripts/maintenance/brain_link_backfill.py --plan - --apply \\
        --i-have-owner-approval --only auto < <계획 JSON>
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
from foms.services.cs_agent.handoff_learning_backfill import LANES, MAX_ASK, run_backfill  # noqa: E402
from foms.services.cs_agent.handoff_learning_link_prompt import KINDS  # noqa: E402
from foms.services.datetime_kst import now_kst  # noqa: E402

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
    parser = argparse.ArgumentParser(description="master brain — link the stored knowledge from a session-made plan "
                                                 "with the nightly linking rules (default dry-run).")
    parser.add_argument("--plan", action="append", required=True,
                        help="잇기 계획 JSON 경로(저장소 밖 — 여러 번 줄 수 있다, '-' 는 표준 입력)")
    parser.add_argument("--apply", action="store_true", help="실제로 넣는다(기본은 미리 돌려 보기)")
    parser.add_argument("--i-have-owner-approval", dest="owner_approval", action="store_true",
                        help="local · staging 밖(운영)에 넣을 때 꼭: 사장님이 미리 돌려 본 수를 보고 넣으라고 했다")
    parser.add_argument("--only", choices=LANES, help="한쪽만 넣는다(auto = 바로 넣을 것, ask = 사장님께 올릴 것)")
    parser.add_argument("--limit", type=int, help="앞 N 줄만(--kinds 로 고른 뒤)")
    parser.add_argument("--kinds", help="이 잇기 종류만(쉼표로 — 예: applies_to,uses)")
    parser.add_argument("--max-ask", dest="max_ask", type=int, default=MAX_ASK,
                        help=f"한 번에 사장님께 올리는 수 상한(기본 {MAX_ASK})")
    parser.add_argument("--show-dropped", dest="show_dropped", action="store_true",
                        help="버린 줄의 차례 · 키 · 까닭을 낸다(글 없음)")
    return parser.parse_args(argv)


def read_plan(path: str) -> dict:
    """계획 파일(UTF-8 JSON — 앞 BOM 은 된다). ``-`` 이면 표준 입력. 오류에는 파일 글을 싣지 않는다."""
    try:
        if path == "-":
            plan = json.loads(sys.stdin.buffer.read().decode("utf-8-sig"))
        else:
            with open(path, "r", encoding="utf-8-sig") as handle:
                plan = json.load(handle)
    except (OSError, ValueError):
        raise Refused("PLAN_UNREADABLE", "계획 파일을 읽지 못했다(경로 · JSON 꼴)") from None
    if not isinstance(plan, dict) or not isinstance(plan.get("links", []), list):
        raise Refused("PLAN_UNREADABLE", "계획 파일이 links 목록이 있는 JSON 객체가 아니다")
    return plan


def read_kinds(value: Optional[str]) -> Optional[frozenset]:
    """``--kinds`` → 종류 모음(모르는 종류면 멈춘다)."""
    if value is None:
        return None
    kinds = frozenset(part.strip() for part in value.split(",") if part.strip())
    if not kinds or not kinds <= set(KINDS):
        raise Refused("KINDS_UNKNOWN", f"--kinds 는 {', '.join(KINDS)} 가운데서 고른다")
    return kinds


def run(argv: Optional[list] = None) -> int:
    """CLI 진입점.

    Returns:
        0 = 정상(미리 돌려 보기 · 넣음), 1 = 쓰지 않고 멈춤(운영 막기 · 계획 파일 · 인자 꼴).
    """
    args = parse_args(argv)
    environment = TOOL.target_environment(resolve_environment(), DB_URL, os.environ.get("RAILWAY_PROJECT_NAME"),
                                          os.environ.get("RAILWAY_SERVICE_ID"))
    out: dict = {"environment": environment, "applied": False}
    try:
        if args.apply and TOOL.needs_owner_approval(environment) and not args.owner_approval:
            raise Refused("OWNER_APPROVAL_REQUIRED",
                          f"{environment} 에는 사장님 승인 표시(--i-have-owner-approval) 없이 넣지 않는다")
        if args.plan.count("-") > 1:
            raise Refused("PLAN_UNREADABLE", "표준 입력(-)은 한 번만 줄 수 있다")
        kinds = read_kinds(args.kinds)
        plans = [read_plan(path) for path in args.plan]
        with app.app_context():
            try:
                out.update(run_backfill(db_session, plans, now=now_kst(), apply=args.apply, only=args.only,
                                        limit=args.limit, kinds=kinds, max_ask=args.max_ask,
                                        show_dropped=args.show_dropped))
            finally:
                db_session.rollback()  # 미리 돌려 보기 · 멈춤의 트랜잭션을 닫는다(넣은 것은 안마다 이미 커밋)
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
