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
import copy
import json
import re
import sys
from collections import Counter
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.orm.attributes import flag_modified  # noqa: E402

from db import engine  # noqa: E402
from foms.services.datetime_kst import now_utc_naive  # noqa: E402
from models import Order  # noqa: E402

TOOL_NAME = "backfill_deleted_at_utc"
# 멱등 열쇠. 이 키가 있는 행은 두 마커 모두에서 뺀다(위 docstring 의 교차 오염 함정).
BACKFILL_KEY = "delete_backfill"
MARKER_ISO = "iso"
MARKER_LEGACY_KST = "legacy_kst"
# 정본 형식(soft_delete._DELETED_AT_FORMAT 와 같은 값이지만, 이 도구는 정본 모듈의
# 비공개 상수를 끌어다 쓰지 않고 계약을 문자로 못박는다).
TARGET_FORMAT = "%Y-%m-%d %H:%M:%S"
FIXED_WIDTH_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
KST_OFFSET_HOURS = 9
DEFAULT_BATCH_SIZE = 200


@dataclass
class _Tally:
    """마커별 scanned/changed/skipped 집계 + 전체 skip 사유 카운터."""

    scanned: int = 0
    changed: int = 0
    journal_rows: int = 0
    markers: dict[str, Counter] = field(
        default_factory=lambda: {MARKER_ISO: Counter(), MARKER_LEGACY_KST: Counter()}
    )
    skipped: Counter = field(default_factory=Counter)
    iso_delta_hours: Counter = field(default_factory=Counter)

    def note_skip(self, reason: str, marker: Optional[str] = None) -> None:
        """skip 1건 기록. 마커 안에서 난 skip 이면 마커 카운터에도 더한다."""
        self.skipped[f"{marker}:{reason}" if marker else reason] += 1
        if marker:
            self.markers[marker]["skipped"] += 1

    def summary(self, *, mode: str, journal_path: Optional[Path]) -> dict[str, Any]:
        """CLI 출력·테스트가 읽는 요약 dict."""
        return {
            "mode": mode,
            "scanned": self.scanned,
            "changed": self.changed,
            "markers": {
                name: {
                    "scanned": counts["scanned"],
                    "changed": counts["changed"],
                    "skipped": counts["skipped"],
                }
                for name, counts in self.markers.items()
            },
            "skipped": dict(self.skipped),
            "journal": str(journal_path) if journal_path else None,
            "journal_rows": self.journal_rows,
            "iso_created_at_delta_hours": dict(self.iso_delta_hours),
        }


def _structured(order: Order) -> dict[str, Any]:
    """``order.structured_data`` 를 dict 로(형식이 아니면 빈 dict)."""
    return order.structured_data if isinstance(order.structured_data, dict) else {}


def _has_marker(order: Order) -> bool:
    """이미 이 도구가 손댄 행이면 True(멱등 열쇠)."""
    return BACKFILL_KEY in _structured(order)


def _classify(order: Order) -> tuple[Optional[str], str]:
    """행 하나의 마커를 정한다.

    판정 순서가 계약이다 — 문자열 모양(``T`` 유무)이 먼저고, 두 마커는 배타다.

    Args:
        order: ``deleted_at`` 이 채워진 Order row.

    Returns:
        ``(마커 이름, "")`` 또는 마커에 해당하지 않으면 ``(None, 사유)``.
    """
    raw = order.deleted_at
    if not isinstance(raw, str) or not raw.strip():
        return None, "empty_value"
    if "T" in raw:
        return MARKER_ISO, ""
    if not FIXED_WIDTH_RE.match(raw):
        return None, "unknown_shape"
    if (order.status or "").strip() != "DELETED":
        return None, "not_legacy_status"
    if order.original_status is None:
        return None, "no_original_status"
    if "delete" in _structured(order):
        return None, "has_delete_projection"  # 정본 projection 행 — 이미 규약대로다
    return MARKER_LEGACY_KST, ""


def _convert(marker: str, raw: str) -> tuple[Optional[str], str]:
    """마커에 맞는 새 ``deleted_at`` 문자열.

    Args:
        marker: :data:`MARKER_ISO` 또는 :data:`MARKER_LEGACY_KST`.
        raw: 지금 저장돼 있는 ``deleted_at`` 문자열.

    Returns:
        ``(새 문자열, "")``, 바꿀 수 없으면 ``(None, 사유)``(호출부가 skipped 로 센다).
    """
    try:
        if marker == MARKER_ISO:
            # 형식만 정규화한다. 시각은 한 초도 옮기지 않는다(위 docstring 계약).
            moment = datetime.fromisoformat(raw)
            if moment.tzinfo is not None:
                # 오프셋이 붙어 있으면 기준축을 '아는' 값이지만, 이 도구는 판단을
                # 사람에게 넘긴다. tzinfo 만 떼면 벽시계를 그대로 UTC 라고 다시 적는
                # 셈이라 '+09:00' 행에 9시간 오차를 영구히 못박는다.
                return None, "tz_aware"
            return moment.strftime(TARGET_FORMAT), ""
        moment = datetime.strptime(raw, TARGET_FORMAT)
    except ValueError:
        return None, "unparsable"
    return (moment - timedelta(hours=KST_OFFSET_HOURS)).strftime(TARGET_FORMAT), ""


def _note_iso_delta(order: Order, tally: _Tally) -> None:
    """참고용: ISO 행의 ``created_at - deleted_at`` 시간차 분포(시 단위 반올림).

    운영자가 나중에 "이 ISO 행이 UTC 로 적힌 것인가 KST 로 적힌 것인가" 를 **사람 눈으로**
    판단할 때 쓰는 근거일 뿐이다. 이 값으로 시각을 자동 보정하지 않는다(계약).
    """
    created = getattr(order, "created_at", None)
    raw = order.deleted_at
    if not isinstance(created, datetime) or not isinstance(raw, str):
        return
    try:
        moment = datetime.fromisoformat(raw)
    except ValueError:
        return
    if moment.tzinfo is not None:
        return  # 오프셋 행은 tz_aware 로 빠진다 — 기준축이 섞인 참고값을 내지 않는다
    delta = created - moment
    tally.iso_delta_hours[round(delta.total_seconds() / 3600)] += 1


def _apply_change(order: Order, marker: str, before: str, after: str) -> None:
    """``deleted_at`` 을 바꾸고 멱등 열쇠 표식을 남긴다(``--apply`` 일 때만 호출).

    JSONB 쓰기는 프로젝트 규칙대로 ``copy.deepcopy`` + ``flag_modified``.
    ``status``·``original_status``·``structured_data['delete']`` 는 건드리지 않는다.
    """
    sd = copy.deepcopy(_structured(order))
    sd[BACKFILL_KEY] = {
        "tool": TOOL_NAME,
        "marker": marker,
        "before": before,
        "after": after,
        "at": now_utc_naive().isoformat(),
    }
    order.structured_data = sd
    flag_modified(order, "structured_data")
    order.deleted_at = after


def _process_order(
    order: Order, tally: _Tally, write_line: Callable[[dict[str, Any]], None], *, apply: bool
) -> None:
    """행 하나를 분류하고, 바꿀 값이 있으면 저널을 먼저 쓴 뒤 (apply 면) 실제로 바꾼다."""
    tally.scanned += 1
    if _has_marker(order):
        tally.note_skip("already_backfilled")  # 두 마커 모두 표식 있는 행을 뺀다
        return
    marker, reason = _classify(order)
    if marker is None:
        tally.note_skip(reason)
        return
    tally.markers[marker]["scanned"] += 1
    if marker == MARKER_ISO:
        _note_iso_delta(order, tally)
    raw = order.deleted_at
    after, convert_reason = _convert(marker, raw)
    if after is None:
        tally.note_skip(convert_reason, marker)
        return
    if after == raw:
        tally.note_skip("already_normalized", marker)
        return
    # 되돌리기 파일을 **먼저** 쓴다 — UPDATE 뒤에 죽어도 원값이 파일에 남는다.
    write_line({"order_id": order.id, "marker": marker, "before": raw, "after": after})
    tally.journal_rows += 1
    tally.markers[marker]["changed"] += 1
    tally.changed += 1
    if apply:
        _apply_change(order, marker, raw, after)


@contextmanager
def _journal_writer(journal_path: Optional[Path]) -> Iterator[Callable[[dict[str, Any]], None]]:
    """JSONL 저널 writer. dry-run 도 쓴다(그게 미리보기다). 경로가 없으면 버린다.

    ``"x"``(배타 생성)로 연다. 되돌리기 자료가 이 파일 하나뿐인데 2회차 실행은 멱등이라
    ``changed=0`` 이다 — ``"w"`` 였다면 그 0행 실행이 1회차 원값을 0바이트로 잘라 영구히
    날린다. 이미 있으면 :exc:`FileExistsError` 를 올리고 CLI 가 exit 2 로 막는다.
    """
    if journal_path is None:
        yield lambda row: None
        return
    handle = open(journal_path, "x", encoding="utf-8", newline="\n")
    try:

        def write_line(row: dict[str, Any]) -> None:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()  # UPDATE 보다 먼저 디스크에 내린다

        yield write_line
    finally:
        handle.close()


def _target_ids(session: Session) -> list[int]:
    """``deleted_at`` 이 채워진 주문 id(오름차순).

    표식·모양 판정은 파이썬에서 한다 — JSONB 컨테인먼트는 인덱스가 없어 풀스캔이다.
    """
    rows = (
        session.query(Order.id)
        .filter(Order.deleted_at.isnot(None))
        .order_by(Order.id)
        .all()
    )
    return [row[0] for row in rows]


def _chunks(items: list[int], size: int) -> Iterator[list[int]]:
    """id 목록을 batch_size 단위로 자른다(대량 실행 시 트랜잭션 크기 제한)."""
    step = max(1, size)
    for start in range(0, len(items), step):
        yield items[start : start + step]


def _invalidate_trash_caches(reason: str) -> None:
    """휴지통·대시보드 read-slice 캐시를 정본 엔진과 같은 범위로 비운다.

    왜: 이 도구는 ``execute_order_mutation`` 을 안 거치므로 after_commit 무효화
    리스너가 돌지 않는다. 정본 엔진(``soft_delete.py:55`` ``_CACHE_FAMILIES``)은 같은
    컬럼을 건드릴 때 반드시 비운다 — 안 비우면 운영자가 옛 시각·옛 정렬을 보고
    "백필이 안 먹었다"고 읽는다. Redis 가 없으면 조용히 0 이라 테스트에서도 안전하다.

    Args:
        reason: 무효화 로그에 남길 사유.
    """
    # lazy import: 이 도구는 CLI 로도 도는데 대시보드 캐시 모듈은 무거운 의존을 끈다.
    from foms.services.common.dashboard_cache import (
        invalidate_dashboard_caches_after_delete_transition,
    )

    invalidate_dashboard_caches_after_delete_transition(reason)


def run_backfill(
    session: Session,
    *,
    apply: bool = False,
    journal_path: Optional[str] = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> dict[str, Any]:
    """``deleted_at`` 문자열을 정본 규약(naive UTC 고정폭)으로 백필한다.

    Args:
        session: SQLAlchemy 세션(Flask ``db_session`` 또는 독립 세션 모두 가능).
        apply: True 면 실제로 쓰고 커밋한다. False(기본)면 한 행도 쓰지 않는다.
        journal_path: 되돌리기 JSONL 경로. None 이면 저널을 남기지 않는다
            (CLI 는 항상 경로를 준다 — dry-run 저널이 곧 미리보기다). 배타 생성이라
            이미 있는 경로면 :exc:`FileExistsError` — 원값을 덮어쓰지 않는다.
        batch_size: 이 개수만큼 처리할 때마다 중간 커밋.

    Returns:
        :meth:`_Tally.summary` 요약 dict.

    Note:
        ``apply=True`` 로 실제 바뀐 행이 있으면 :func:`_invalidate_trash_caches` 를
        부른다. 그래도 Redis 가 없거나 무효화가 실패하면 휴지통·대시보드 캐시가
        만료(최대 300초)될 때까지 화면에 **옛 시각·옛 정렬**이 남는다 — 운영자가
        "안 먹었다"고 읽고 재실행하지 않도록 기다린다.
    """
    tally = _Tally()
    path = Path(journal_path) if journal_path else None
    ids = _target_ids(session)
    with _journal_writer(path) as write_line:
        for chunk in _chunks(ids, batch_size):
            orders = session.query(Order).filter(Order.id.in_(chunk)).order_by(Order.id).all()
            for order in orders:
                _process_order(order, tally, write_line, apply=apply)
            if apply:
                session.commit()
    # dry-run 은 한 행도 안 고치므로(_apply_change 를 아예 안 부른다) 되감을 것이 없다.
    # 여기서 rollback 하면 세션을 주입한 호출자의 미커밋 작업까지 함께 날아간다.
    if apply and tally.changed:
        _invalidate_trash_caches("deleted_at_backfill")
    return tally.summary(mode="apply" if apply else "dry-run", journal_path=path)


def _read_journal(path: Path) -> Iterator[dict[str, Any]]:
    """JSONL 저널을 한 줄씩 읽는다(빈 줄 무시)."""
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if text:
                yield json.loads(text)


def _revert_reason(order: Optional[Order], row: dict[str, Any]) -> str:
    """되돌릴 수 없는 사유(빈 문자열이면 되돌릴 수 있다)."""
    if order is None:
        return "order_missing"
    if not isinstance(row.get("before"), str):
        return "bad_journal_row"
    if not _has_marker(order):
        return "no_backfill_marker"
    if order.deleted_at != row.get("after"):
        return "value_moved"  # 백필 뒤 누가 또 바꿨다 — 임의로 덮어쓰지 않는다
    return ""


def _undo_change(order: Order, before: str) -> None:
    """원값을 복원하고 표식을 지운다(``copy.deepcopy`` + ``flag_modified``)."""
    sd = copy.deepcopy(_structured(order))
    sd.pop(BACKFILL_KEY, None)
    order.structured_data = sd
    flag_modified(order, "structured_data")
    order.deleted_at = before


def run_revert(
    session: Session, revert_path: str, *, apply: bool = False
) -> dict[str, Any]:
    """저널(JSONL)을 읽어 ``before`` 값을 되돌리고 표식을 지운다.

    Args:
        session: SQLAlchemy 세션.
        revert_path: 백필이 남긴 JSONL 저널 경로.
        apply: True 면 실제로 되돌리고 커밋한다. False 면 셈만 한다.

    Returns:
        ``{"mode", "scanned", "reverted", "skipped"}``.
    """
    scanned = 0
    reverted = 0
    skipped: Counter = Counter()
    for row in _read_journal(Path(revert_path)):
        scanned += 1
        order = session.query(Order).filter(Order.id == row.get("order_id")).one_or_none()
        reason = _revert_reason(order, row)
        if reason:
            skipped[reason] += 1
            continue
        reverted += 1
        if apply:
            _undo_change(order, row["before"])
    if apply:
        session.commit()
        if reverted:
            _invalidate_trash_caches("deleted_at_backfill_revert")
    # dry-run 은 한 행도 안 고치므로(_undo_change 를 아예 안 부른다) 되감을 것이 없다.
    return {
        "mode": "revert" if apply else "revert-dry-run",
        "scanned": scanned,
        "reverted": reverted,
        "skipped": dict(skipped),
    }


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
