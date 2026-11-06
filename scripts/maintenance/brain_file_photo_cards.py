"""master brain — 다시 배운 사진 교훈 카드를 **승인 대기 제안**으로 넣는 관리자 스크립트(CS 설계서 17.11.3 · 사장님 D174).

**기본은 미리 보기다**: 카드 파일(저장소 밖 JSON 배열 — 예 ``/tmp/cards.json``)을 읽어 카드마다 제안 길을 그대로 돌려 보고
되돌린 뒤 넣을 수 · 건너뛸 수 · 관문에 막힐 수(관문 이름별)만 낸다(brain 쓰기 0). ``--apply`` 를 줘야 넣는다. 화면에는 키 · 수 ·
관문 이름만(카드 글 없음).

- 쓰기는 :mod:`foms.services.brain.photo_cards` 한 길이다 — 제안한 이 ``agent:cs_photo`` 의 열린 제안만 만들고 **반영하지
  않는다**(승인 화면에서 사람이 누른다 — 승인한 것만 지식 문서에 들어간다). 멱등 — 다시 돌려도 같은 키는 다시 넣지 않는다.
- 부딪침 관문이 카드마다 보조 모델 판정자를 두 번 부른다(돈 — 미리 보기도 같다). 몇 장만 보려면 ``--limit N``,
  스테이징 시험은 ``--only-key <카드 키>``(여러 번 줄 수 있다).
- 운영 막기는 기준 답 스크립트(``tools/ops/cs_agent_knowledge.py``)의 환경 판정을 그대로 쓴다 — local · staging 밖은
  ``--i-have-owner-approval`` 없이 넣지 않는다(스테이징에서 먼저 — 설계서 17.11.3 의 5).

사용 예 (PowerShell 5.x)::

    python scripts/maintenance/brain_file_photo_cards.py <카드 JSON 경로> --limit 3
    python scripts/maintenance/brain_file_photo_cards.py <카드 JSON 경로> --apply --only-key lahom/photo-<슬러그>
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
from foms.services.brain.photo_cards import file_cards  # noqa: E402

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


def _positive(value: str) -> int:
    """1 이상 정수."""
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("1 이상이어야 한다")
    return number


def parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    """CLI 인자."""
    parser = argparse.ArgumentParser(description="master brain — file re-learned photo lesson cards as open proposals "
                                                 "(default preview, never applies).")
    parser.add_argument("cards", help="카드 JSON 배열 파일 경로(저장소 밖)")
    parser.add_argument("--apply", action="store_true", help="실제로 제안을 넣는다(기본은 미리 보기 — 쓰기 0)")
    parser.add_argument("--only-key", dest="only_keys", action="append", default=[], metavar="KEY",
                        help="이 카드 키만(여러 번 줄 수 있다 — 스테이징 시험)")
    parser.add_argument("--limit", type=_positive, help="앞에서부터 이 수만(부딪침 판정자 돈을 아낀다)")
    parser.add_argument("--i-have-owner-approval", dest="owner_approval", action="store_true",
                        help="local · staging 밖(운영)에 넣을 때 꼭: 사장님이 카드 넣기를 승인했다")
    return parser.parse_args(argv)


def read_cards(path: str) -> list:
    """카드 파일(UTF-8 JSON 배열 — 앞 BOM 은 된다). 오류에는 파일 글을 싣지 않는다."""
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            cards = json.load(handle)
    except (OSError, ValueError):
        raise Refused("CARDS_UNREADABLE", "카드 파일을 읽지 못했다(경로 · JSON 꼴)") from None
    if not isinstance(cards, list):
        raise Refused("CARDS_UNREADABLE", "카드 파일이 JSON 배열이 아니다")
    return cards


def run(argv: Optional[list] = None) -> int:
    """CLI 진입점.

    Returns:
        0 = 정상(미리 보기 · 넣음 — 막힌 카드가 있어도), 1 = 쓰지 않고 멈춤(운영 막기 · 카드 파일).
    """
    args = parse_args(argv)
    environment = TOOL.target_environment(resolve_environment(), DB_URL, os.environ.get("RAILWAY_PROJECT_NAME"),
                                          os.environ.get("RAILWAY_SERVICE_ID"))
    out: dict = {"environment": environment, "applied": False}
    try:
        if args.apply and TOOL.needs_owner_approval(environment) and not args.owner_approval:
            raise Refused("OWNER_APPROVAL_REQUIRED",
                          f"{environment} 에는 사장님 승인 표시(--i-have-owner-approval) 없이 넣지 않는다")
        cards = read_cards(args.cards)
        with app.app_context():
            try:
                out.update(file_cards(db_session, cards, apply=args.apply, only_keys=args.only_keys,
                                      limit=args.limit))
            finally:
                db_session.rollback()  # 미리 보기 · 멈춤의 트랜잭션을 닫는다(넣은 것은 카드마다 이미 커밋)
                db_session.remove()
    except (Refused, BrainError) as exc:
        out.update(ok=False, error=getattr(exc, "code", "ERROR"), message=str(exc))
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
