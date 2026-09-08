"""휴지통 ``deleted_at`` 백필의 **판정·보정·되돌리기 알맹이** (삭제 축 통일 W3).

왜 두 파일인가: 이 도구는 마커 규칙·함정·되돌리기 계약을 길게 적어야 하는 물건이라
한 파일에 다 담으면 대형 파일 계약(500줄)을 넘는다. 그래서 **계약 전문과 CLI 는**
``backfill_deleted_at_utc.py`` 에 두고, 순수 로직만 여기에 둔다. 계약 전문을 먼저 읽어라 —
마커 둘이 왜 배타인지, 왜 ISO 행의 시각을 옮기지 않는지, 표식이 왜 필요한지가 거기 있다.

이 파일에는 CLI 도 ``__main__`` 도 없다. 진입점은 언제나 ``backfill_deleted_at_utc.py`` 다.
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
