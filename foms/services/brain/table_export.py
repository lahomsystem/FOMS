"""회사 지식 표 내려받기(판 ⑦ [내보내기] — 점검 2차 w1-10 · 사용자 결정 D233).

지금 거른 표(유형 · 거르기 · 정렬 — :class:`.browse.TableQuery`)를 엑셀로 바로 열리는 CSV(UTF-8 BOM · CRLF)로 만든다.
줄은 :func:`.browse.table_rows` 가 보기 범위 · 유효 기간으로 질의 단계에서 거른 것뿐이다(볼 수 없는 유형 · 층은 파일에도 없다).
한 번에 :data:`MAX_EXPORT_ROWS` 줄까지 — 넘으면 만들지 않는다(부르는 쪽이 '거르기로 줄여 주세요'). 글은 줄 칸 그대로이고,
``=`` · ``+`` · ``-`` · ``@`` 로 시작하는 칸은 엑셀이 셈으로 읽지 않게 앞에 ``'`` 를 붙인다.
"""

from __future__ import annotations

import csv
import datetime
import io
from typing import Any, Mapping

from foms.services.brain.display import (
    BRAND_LABELS, CONFIDENCE_LABELS, GRADE_LABELS, LAYER_LABELS, STATUS_LABELS, TYPE_DISPLAY,
)

MAX_EXPORT_ROWS = 5000
HEADERS: tuple[str, ...] = ("키", "이름", "유형", "쓰는 팀", "브랜드", "상태", "확실한 정도", "위험 등급", "쓰인 횟수",
                            "마지막 확인", "확인한 사람", "다시 볼 날", "수정 대기", "엇갈림")
_BOM = "﻿"
_CRLF = "\r\n"
_FORMULA_HEADS = ("=", "+", "-", "@", "\t", "\r")


def _cell(value: Any) -> Any:
    """엑셀이 셈으로 읽을 머리 글자면 앞에 ``'`` — 수는 그대로."""
    if isinstance(value, str) and value.startswith(_FORMULA_HEADS):
        return "'" + value
    return value


def _label(table: Mapping[str, str], value: Any) -> str:
    return table.get(value, str(value)) if value else ""


def _row(item: Mapping[str, Any]) -> list[Any]:
    kind = TYPE_DISPLAY.get(item.get("type"), (item.get("type") or "",))[0]
    return [_cell(v) for v in (
        item.get("key") or "", item.get("name") or "", kind, _label(LAYER_LABELS, item.get("layer")),
        _label(BRAND_LABELS, item.get("brand")), _label(STATUS_LABELS, item.get("status")),
        _label(CONFIDENCE_LABELS, item.get("confidence")), _label(GRADE_LABELS, item.get("grade")),
        int(item.get("usage_count") or 0), item.get("checked_at") or "", item.get("checked_by") or "",
        item.get("stale_after") or "", int(item.get("open_changes") or 0), int(item.get("conflicts") or 0))]


def build_csv(rows: list[Mapping[str, Any]]) -> str:
    """목록 줄(:func:`.browse.light_rows` 모양) → CSV 글 전체(BOM 으로 시작 · 줄마다 CRLF)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator=_CRLF)
    writer.writerow(HEADERS)
    for item in rows:
        writer.writerow(_row(item))
    return _BOM + buffer.getvalue()


def export_filename(item_type: Any, today: datetime.date) -> str:
    """ASCII 파일 이름 — ``brain-table-<유형|all>-<YYYYMMDD>.csv``."""
    return f"brain-table-{item_type or 'all'}-{today:%Y%m%d}.csv"
