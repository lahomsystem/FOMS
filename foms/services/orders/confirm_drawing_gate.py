"""고객컨펌 → 생산 도면 게이트 판정(순수 함수) — 2차 묶음 2a-2 (C21 · M3).

도면이 "영업이 수령 확정한 최신본"이 아니면 정식 경로(고객컨펌 승인·제작 시작)로는 생산으로
넘어가지 않는다. 서버 라우트·전이 엔진 방어선·화면 CTA·생산 보드 배지가 **이 모듈의 같은
함수**를 불러 같은 답을 낸다(화면 == 서버). DB·Flask 를 import 하지 않는다.

* :func:`effective_drawing_status` — 도면 상태 판정의 단일 정본. 최상위 ``drawing_status`` 가
  우선이고, 없을 때만 옛 데이터의 중첩 ``drawing.status`` 를 본다(도면 상태를 **쓰는** 코드는
  모두 최상위만 쓴다 — 중첩은 옛 데이터일 뿐이다).
* :func:`confirm_exit_block` — 허용 목록(M3): CONFIRMED 만 통과. 고객컨펌 승인·제작 시작 (b).
* :func:`revision_in_flight_block` — 막는 목록: RETURNED·TRANSFERRED 만. 생산 단계 run 시작 (a)
  와 생산 보드 "도면 수정 중" 배지.
"""
from __future__ import annotations

from typing import Any, Iterable, NamedTuple, Optional

from foms.services.orders.erp_policy_constants import STAGE_NAME_TO_CODE

__all__ = [
    "DRAWING_GATED_COMMANDS",
    "DRAWING_STATUS_CODE",
    "GateBlock",
    "confirm_exit_block",
    "drawing_revision_in_progress",
    "effective_drawing_status",
    "is_confirm_stage",
    "normalize_stage_code",
    "production_block_reason",
    "production_drawing_badge",
    "production_start_block",
    "revision_in_flight_block",
    "stage_override_drawing_warning",
]

#: 게이트 오류 코드(``admin_override.GATE_DRAWING_STATUS`` 와 같은 글자).
DRAWING_STATUS_CODE = "DRAWING_STATUS"

#: 전이 엔진이 잠금 아래에서 도면 게이트를 다시 보는 command(방어선).
DRAWING_GATED_COMMANDS: frozenset[str] = frozenset({"CUSTOMER_CONFIRM", "PRODUCTION_START"})

_REVISION_IN_FLIGHT = ("RETURNED", "TRANSFERRED")

_SALES_REASONS = {
    "RETURNED": "도면 수정 요청이 진행 중입니다. 수정본을 받아 수령 확정한 뒤 고객 컨펌을 완료하세요.",
    "TRANSFERRED": "새로 전달된 도면을 아직 수령 확정하지 않았습니다. 도면을 확인하고 수령 확정부터 해 주세요.",
}
_SALES_REASON_DEFAULT = "도면 수령 확정 기록이 없습니다. 도면 전달과 수령 확정을 먼저 해 주세요."

_PRODUCTION_REASONS = {
    "RETURNED": "도면을 고치는 중이라 아직 제작을 시작할 수 없어요. 영업 담당({names})이 새 도면을 수령 확정하면 시작할 수 있어요.",
    "TRANSFERRED": "새 도면이 도착했지만 영업 담당({names})이 아직 수령 확정하지 않았어요. 확정되면 시작할 수 있어요.",
}
_PRODUCTION_REASON_DEFAULT = "도면 수령 확정 기록이 없어 제작을 시작할 수 없어요. 영업 담당({names})에게 도면 확정을 요청해 주세요."

_BADGE_TITLES = {
    "RETURNED": "도면 수정요청이 진행 중입니다. 새 도면이 수령 확정될 때까지 옛 도면으로 만들지 마세요.",
    "TRANSFERRED": "수정된 도면이 도착했지만 영업 담당이 아직 수령 확정하지 않았습니다.",
}

_STATUS_WORDS = {"RETURNED": "수정 중", "TRANSFERRED": "수령 전"}
_PRODUCTION_AND_AFTER = ("PRODUCTION", "CONSTRUCTION", "CS", "COMPLETED")


class GateBlock(NamedTuple):
    """막힌 판정 — 코드·영업용 사유·그 순간의 도면 상태."""

    code: str
    reason: str
    drawing_status: str


def normalize_stage_code(raw: Any) -> str:
    """단계값(영문 코드·한글 이름)을 영문 코드로. 운영에 '고객컨펌' 같은 한글 값이 실재한다."""
    text = str(raw or "").strip()
    return STAGE_NAME_TO_CODE.get(text, text)


def is_confirm_stage(raw: Any) -> bool:
    """고객컨펌 단계인가(영문·한글 모두)."""
    return normalize_stage_code(raw) == "CONFIRM"


def effective_drawing_status(sd: Any, default: str = "NONE") -> str:
    """도면 상태 판정 정본 — 최상위 ``drawing_status`` 우선, 없으면 중첩 ``drawing.status``.

    빈 문자열은 없음으로 본다. 대문자로 돌려준다. 둘 다 없으면 ``default``.
    """
    if not isinstance(sd, dict):
        return default
    top = str(sd.get("drawing_status") or "").strip().upper()
    if top:
        return top
    drawing = sd.get("drawing")
    nested = drawing.get("status") if isinstance(drawing, dict) else None
    return str(nested or "").strip().upper() or default


def confirm_exit_block(sd: Any) -> Optional[GateBlock]:
    """고객컨펌 → 생산 허용 목록 판정(M3). CONFIRMED 면 None, 아니면 막힌 이유."""
    status = effective_drawing_status(sd)
    if status == "CONFIRMED":
        return None
    reason = _SALES_REASONS.get(status, _SALES_REASON_DEFAULT)
    return GateBlock(DRAWING_STATUS_CODE, reason, status)


def revision_in_flight_block(sd: Any) -> Optional[GateBlock]:
    """도면 수정이 진행 중인가(RETURNED·TRANSFERRED 만 막는다). 생산 단계 run 시작·배지용."""
    status = effective_drawing_status(sd)
    if status not in _REVISION_IN_FLIGHT:
        return None
    return GateBlock(DRAWING_STATUS_CODE, _SALES_REASONS[status], status)


def drawing_revision_in_progress(sd: Any) -> bool:
    """생산 보드 "도면 수정 중" 배지를 달아야 하는가 — 제작 시작 (a) 게이트와 같은 술어."""
    return revision_in_flight_block(sd) is not None


def production_drawing_badge(sd: Any) -> Optional[dict[str, str]]:
    """생산 화면(PC 보드·모바일) 카드 배지 — 없으면 None. 판정은 :func:`revision_in_flight_block`."""
    block = revision_in_flight_block(sd)
    if block is None:
        return None
    label = "도면 수정 중" if block.drawing_status == "RETURNED" else "도면 수정 중 · 확정 대기"
    return {
        "label": label,
        "title": _BADGE_TITLES[block.drawing_status],
        "drawing_status": block.drawing_status,
    }


def production_start_block(stage_raw: Any, sd: Any) -> Optional[GateBlock]:
    """[제작 시작] 이 도면 게이트에 막히는가 — 제작 시작 라우트와 같은 단계 분기(화면 == 서버).

    생산 단계(진행 중 run 없음 = 제작 대기)는 (a) :func:`revision_in_flight_block`, 고객컨펌
    호환 경로는 (b) :func:`confirm_exit_block`(허용 목록). 그 밖의 단계는 막지 않는다.
    """
    stage = normalize_stage_code(stage_raw)
    if stage == "PRODUCTION":
        return revision_in_flight_block(sd)
    if stage == "CONFIRM":
        return confirm_exit_block(sd)
    return None


def production_block_reason(block: GateBlock, sales_names: Iterable[str] = ()) -> str:
    """생산팀용 막힘 문구(제작 시작 (a)·(b) 공통). 이름이 없으면 "영업 담당"만 남긴다."""
    names = ", ".join(n for n in (str(x or "").strip() for x in sales_names) if n)
    template = _PRODUCTION_REASONS.get(block.drawing_status, _PRODUCTION_REASON_DEFAULT)
    text = template.format(names=names)
    return text.replace("영업 담당()", "영업 담당")


def stage_override_drawing_warning(sd: Any, to_stage: Any) -> Optional[str]:
    """단계 강제 변경(Q5) 경고 — 목표가 생산 이후인데 도면이 CONFIRMED 가 아니면 한 줄."""
    if normalize_stage_code(to_stage) not in _PRODUCTION_AND_AFTER:
        return None
    status = effective_drawing_status(sd)
    if status == "CONFIRMED":
        return None
    word = _STATUS_WORDS.get(status, "기록 없음")
    return f"도면이 아직 확정되지 않았어요(지금 상태: {word}). 옛 도면으로 생산될 수 있어요."
