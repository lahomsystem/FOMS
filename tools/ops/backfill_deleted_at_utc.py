"""휴지통 ``deleted_at`` 저장 규약 백필 (1회성, 삭제 축 통일 W3).

문제: ``Order.deleted_at`` 은 문자열 컬럼이고, 읽는 쪽
(``format_datetime_kst(..., assume_utc_if_naive=True)``)은 정본 규약
"naive UTC 고정폭 ``%Y-%m-%d %H:%M:%S``"(``foms/services/orders/soft_delete.py:48``)를
전제한다. 그런데 과거에 쓴 자리들이 규약을 안 지켰다 — 일괄 삭제는 KST 를 그대로 적었고
(9시간 앞선 시각이 화면에 뜬다), 초안 폐기는 ``datetime.now().isoformat()`` 이라 ``T`` 가
섞인 컨테이너 로컬 시각이다. 이 스크립트는 그 과거 행들을 정본 규약으로 옮긴다.

**두 마커만 고른다.** 공통 전제는 ``deleted_at IS NOT NULL`` 이고
``structured_data['delete_backfill']`` 표식이 **없는** 행이다.

* ``iso`` — ``deleted_at`` 에 ``T`` 가 있다 → **형식만** 고정폭으로 정규화한다.
  **시각은 한 초도 옮기지 않는다.** 그 값이 UTC 인지 KST 인지 알 방법이 없다(컨테이너
  TZ 를 모르고, 대조로 쓸 UTC 컬럼도 없다 — ``Order.created_at`` 기본값도
  ``datetime.datetime.now``, ``models.py:36``). 모르는 값을 옮기지 않는다가 계약이다.
  ``datetime.fromisoformat`` 파싱 실패 행은 건드리지 않고 skipped 로만 센다.
* ``legacy_kst`` — 고정폭 ``^\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2}$`` 이고
  ``status='DELETED'`` 이고 ``original_status IS NOT NULL`` 이고
  ``structured_data['delete']`` 가 없다 → legacy 일괄 삭제가 KST 로 적은 행이다.
  **-9시간** 보정한다.

**두 마커는 배타이고, 판정은 문자열 모양(``T`` 유무)이 먼저다.** 여기에 함정이 하나 있다:
초안 폐기가 남긴 ISO 행은 ``status='DELETED'`` + ``original_status='DRAFT'`` + delete meta
없음이라, ``iso`` 가 고정폭으로 바꿔 놓으면 **2회차에 ``legacy_kst`` 에 걸려 9시간이 더
깎인다.** 그래서 바꾼 행마다 표식(``structured_data['delete_backfill']``)을 남기고 두 마커
모두 표식 있는 행을 뺀다. 이 표식을 읽는 운영 코드는 없다(``read_order_trash`` 는
``structured_data['delete']`` 만 본다) — 순수한 멱등 열쇠다.

되돌릴 수 있다: 변경 1건마다 JSONL 저널에 ``{order_id, marker, before, after}`` 를
**UPDATE 보다 먼저** 적는다. dry-run 도 같은 저널을 쓴다(그게 미리보기다).
``--revert <저널> --apply`` 는 그 파일을 읽어 ``before`` 를 되돌리고 표식을 지운다.

사용법::

    # 미리보기 (기본, 아무것도 쓰지 않는다. 저널 파일만 생긴다)
    python tools/ops/backfill_deleted_at_utc.py --journal preview.jsonl

    # 실제 보정
    python tools/ops/backfill_deleted_at_utc.py --apply --journal run1.jsonl

    # 되돌리기
    python tools/ops/backfill_deleted_at_utc.py --revert run1.jsonl --apply

저널 파일은 **배타 생성**(``open(..., "x")``)이다. 되돌리기 자료가 이 파일 하나뿐인데
2회차 실행은 멱등이라 ``changed=0`` 이고, 그때 같은 이름을 ``"w"`` 로 열면 1회차 원값이
0바이트로 잘려 영구히 사라진다. 이미 있는 경로를 주면 exit 2 로 죽는다 — 새 이름을 준다.

``--apply`` 뒤 **휴지통·대시보드 캐시**: 이 도구는 정본 mutation 엔진
(``execute_order_mutation``)을 안 거치므로 after_commit 무효화 리스너가 돌지 않는다.
정본 엔진은 같은 컬럼을 건드릴 때 ``_CACHE_FAMILIES``(``ORDERS_INDEX``·``TRASH_INDEX``,
``soft_delete.py:55``)를 반드시 비운다. 그래서 이 도구도 실제 바뀐 행이 있으면
:func:`_invalidate_trash_caches` 로 같은 범위를 비운다. 그래도 Redis 가 없거나 무효화가
실패하면 TTL(최대 300초)이 지날 때까지 화면에 **옛 시각·옛 정렬**이 남는다 — 그 사이에
"백필이 안 먹었다"고 읽고 재실행하면 위 저널 문제와 맞물린다. 캐시가 만료될 때까지 기다린다.

이 저장소의 다른 백필 도구(``backfill_as_schedule_links.py``)는 실제 쓰기 플래그가
``--execute`` 지만, 이 도구는 브리프 계약대로 ``--apply`` 다. ``--dry-run`` 은 기본값의
명시적 별칭이고 ``--apply`` 와 동시 지정하면 exit 2 로 죽는다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy.orm import sessionmaker  # noqa: E402

from db import engine  # noqa: E402
from foms.services.datetime_kst import now_utc_naive  # noqa: E402

# 알맹이는 ``backfill_deleted_at_core`` 에 있다(대형 파일 계약 500줄). 이 파일은
# **계약 전문 + CLI** 다. 아래 재수출은 부르는 쪽이 이 모듈 이름 하나만 알면 되게
# 유지한다 — 진입점이 둘로 갈리면 어느 쪽이 정본인지 모르게 된다.
from tools.ops.backfill_deleted_at_core import (  # noqa: E402
    BACKFILL_KEY,
    DEFAULT_BATCH_SIZE,
    FIXED_WIDTH_RE,
    KST_OFFSET_HOURS,
    MARKER_ISO,
    MARKER_LEGACY_KST,
    TARGET_FORMAT,
    TOOL_NAME,
    run_backfill,
    run_revert,
)


def _render_table(summary: dict[str, Any]) -> str:
    """마커별 scanned/changed/skipped 요약표(사람이 읽는 줄)."""
    lines = [
        f"mode={summary['mode']} scanned={summary['scanned']} "
        f"changed={summary.get('changed', summary.get('reverted', 0))}"
    ]
    for marker, counts in (summary.get("markers") or {}).items():
        lines.append(
            f"  {marker:<11} scanned={counts['scanned']:<6} "
            f"changed={counts['changed']:<6} skipped={counts['skipped']}"
        )
    for reason, count in sorted((summary.get("skipped") or {}).items()):
        lines.append(f"  skip[{reason}] = {count}")
    return "\n".join(lines)


def _default_journal_path() -> str:
    """기본 저널 파일명 — ``backfill_deleted_at_utc_<UTC타임스탬프>.jsonl``."""
    return f"{TOOL_NAME}_{now_utc_naive().strftime('%Y%m%dT%H%M%SZ')}.jsonl"


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    """CLI 인자 파싱 — 기본 dry-run, ``--apply`` 로만 실제 쓰기."""
    parser = argparse.ArgumentParser(
        description="Backfill Order.deleted_at strings to the canonical naive-UTC "
        "fixed-width format (default: dry-run, writes nothing)."
    )
    parser.add_argument(
        "--apply", action="store_true", help="Actually write. Without this, nothing is written."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Explicit alias of the default (no writes)."
    )
    parser.add_argument(
        "--journal",
        default=None,
        help="Revert journal path (JSONL). Created exclusively; existing path = exit 2.",
    )
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument(
        "--revert", default=None, help="Revert mode: read this journal and restore 'before'."
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entrypoint. exit 0=정상, 2=플래그 오용 또는 저널 파일 중복."""
    args = _parse_args(argv)
    if args.dry_run and args.apply:
        print("[ERROR] --dry-run 과 --apply 는 동시에 쓸 수 없다")
        return 2

    make_session = sessionmaker(bind=engine)
    session = make_session()
    try:
        if args.revert:
            summary = run_revert(session, args.revert, apply=args.apply)
        else:
            summary = run_backfill(
                session,
                apply=args.apply,
                journal_path=args.journal or _default_journal_path(),
                batch_size=args.batch_size,
            )
    except FileExistsError as exc:
        # 되돌리기 자료를 지키는 마지막 문 — 덮어쓰지 않고 사람에게 새 이름을 받는다.
        print(f"[ERROR] 저널 파일이 이미 있다: {exc.filename} — 새 이름을 주십시오")
        return 2
    finally:
        session.close()

    print(_render_table(summary))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
