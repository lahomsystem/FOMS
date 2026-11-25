"""고객컨펌 → 생산 도면 게이트 판정(순수 함수) — 2차 묶음 2a-2 (C21 · M3).

도면이 "영업이 수령 확정한 최신본"이 아니면 정식 경로(고객컨펌 승인·제작 시작)로는 생산으로
넘어가지 않는다. 서버 라우트·전이 엔진 방어선·화면 CTA·생산 보드 배지가 **이 모듈의 같은
함수**를 불러 같은 답을 낸다(화면 == 서버). DB·Flask 를 import 하지 않는다.

* :func:`effective_drawing_status` — 도면 상태 판정의 단일 정본. 최상위 ``drawing_status`` 가
  우선이고, 없을 때만 옛 데이터의 중첩 ``drawing.status`` 를 본다(도면 상태를 **쓰는** 코드는
  모두 최상위만 쓴다 — 중첩은 옛 데이터일 뿐이다).
* :func:`confirm_exit_block` — 허용 목록(M3): CONFIRMED 만 통과. 고객컨펌 승인·제작 시작 (b).
* :func:`revision_in_flight_block` — 막는 목록: RETURNED·TRANSFERRED 만. 생산 단계 run 시작 (a)
  와 생산 보드 "도면 수정 중" 배지. **주문 통째** 막힘만 뜻한다(2026-11-25 설계서 §3-3): 생산 · 시공 단계에서 영업 요청이
  지금 도면 중 일부만 가리키면(:func:`targeted_revision_request`) 그 도면만 막히므로(도면별 판정 ``drawing_fix``) 여기서는 None.
  고객컨펌 단계 요청 · 대상이 없거나 못 푸는 요청 · 지금 도면 전부를 가리키는 요청(도면 1장 주문 · 협력사 요청)은 지금처럼 통째.
"""
from __future__ import annotations

from typing import Any, Iterable, NamedTuple, Optional

from foms.services.orders.erp_policy_constants import STAGE_NAME_TO_CODE

__all__ = [
    "DRAWING_GATED_COMMANDS",
    "DRAWING_STATUS_CODE",
    "GateBlock",
    "PER_DRAWING_STAGES",
    "confirm_exit_block",
    "drawing_revision_in_progress",
    "effective_drawing_status",
    "is_confirm_stage",
    "last_revision_request",
    "normalize_stage_code",
    "per_drawing_stage",
    "production_block_reason",
    "production_drawing_badge",
    "production_start_block",
    "revision_in_flight_block",
    "revision_request_target_keys",
    "revision_status_block",
    "stage_override_drawing_warning",
    "targeted_revision_request",
]

#: 영업 수정 요청이 대상 도면만 막는 단계(2026-11-25 설계서 §3-3 4 — 고객컨펌 단계 요청은 지금처럼 통째).
PER_DRAWING_STAGES: tuple[str, ...] = ("PRODUCTION", "CONSTRUCTION")

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


def per_drawing_stage(sd: Any) -> bool:
    """도면별 막힘을 보는 단계인가 — 주문 ``workflow.stage`` 가 생산 · 시공(영문 · 한글 모두, §3-3 4)."""
    workflow = sd.get("workflow") if isinstance(sd, dict) else None
    stage = workflow.get("stage") if isinstance(workflow, dict) else None
    return normalize_stage_code(stage) in PER_DRAWING_STAGES


def last_revision_request(sd: Any) -> Optional[dict[str, Any]]:
    """전달 이력의 마지막 영업 수정 요청 줄(``REQUEST_REVISION``) — 열린 영업 요청은 한 주문에 늘 하나(설계서 §1-1)."""
    history = sd.get("drawing_transfer_history") if isinstance(sd, dict) else None
    for item in reversed(history if isinstance(history, list) else []):
        if isinstance(item, dict) and str(item.get("action") or "").upper() == "REQUEST_REVISION":
            return item
    return None


def revision_request_target_keys(request: Any) -> tuple[str, ...]:
    """요청 줄이 가리킨 도면 저장 key(``target_drawing_keys`` · 옛 단일 ``target_drawing_key``) — 순서 유지 · 빈 값 버림."""
    if not isinstance(request, dict):
        return ()
    raw = request.get("target_drawing_keys")
    keys = raw if isinstance(raw, list) else [request.get("target_drawing_key")]
    return tuple(dict.fromkeys(k.strip() for k in keys if isinstance(k, str) and k.strip()))


def targeted_revision_request(sd: Any) -> Optional[dict[str, Any]]:
    """생산 · 시공 단계 RETURNED 의 영업 요청이 지금 도면 **일부**를 가리키면 그 요청 줄(도면별 막힘), 아니면 None(통째).

    통째로 남는 것(사장님 답 5 "도면을 안 고른 요청은 지금처럼 전체"): 고객컨펌 등 다른 단계 · 요청 줄 없음 · 대상 없음 ·
    대상 key 가 지금 도면에 없음(못 풂) · 대상이 지금 도면 전부(도면 1장 주문은 서버가 그 장을 저절로 고르고, 협력사 요청은 늘 전부다 —
    설계서 §1-1 · §12 의 '안 고른 요청'). 판정은 key 로만 한다(요청 ~ 수정본 사이에는 지금 도면 목록이 바뀌지 않는다).
    """
    if effective_drawing_status(sd) != "RETURNED" or not per_drawing_stage(sd):
        return None
    request = last_revision_request(sd)
    keys = set(revision_request_target_keys(request))
    files = sd.get("drawing_current_files") if isinstance(sd, dict) else None
    current = {str(f.get("key") or "").strip() for f in files if isinstance(f, dict)} - {""} if isinstance(files, list) else set()
    if not keys or not keys <= current or keys == current:
        return None
    return request


def revision_status_block(sd: Any) -> Optional[GateBlock]:
    """도면 상태가 수정 중(RETURNED) · 수령 전(TRANSFERRED)인가 — 대상이 몇 장이든(도면별 · 통째를 가르지 않음).

    ERP 보드 단계 칸 "도면 수정 중 · 도면 작업실 열기"(``board_state_display``)는 영업 요청이 걸려 있는 동안 지금처럼 보인다
    (2026-11-25 D1 검토 판결 F — 통째 판정을 좁힌 것이 그 화면을 바꾸지 않게). 생산 쪽 막는 문은 :func:`revision_in_flight_block`.
    """
    status = effective_drawing_status(sd)
    if status not in _REVISION_IN_FLIGHT:
        return None
    return GateBlock(DRAWING_STATUS_CODE, _SALES_REASONS[status], status)


def revision_in_flight_block(sd: Any) -> Optional[GateBlock]:
    """도면 수정이 진행 중인가(RETURNED·TRANSFERRED 만 막는다) — **주문 통째**. 생산 단계 run 시작·배지용.

    생산 · 시공 단계에서 영업 요청이 도면 일부만 가리키면(:func:`targeted_revision_request`) 통째가 아니다(None) — 그 도면만 막는
    판정은 ``foms.services.orders.drawing_fix`` 가 한다(2026-11-25 설계서 §3-3).
    """
    block = revision_status_block(sd)
    if block is not None and block.drawing_status == "RETURNED" and targeted_revision_request(sd) is not None:
        return None
    return block


def drawing_revision_in_progress(sd: Any) -> bool:
    """주문 **통째** "도면 고치는 중"인가 — 제작 시작 (a) 게이트 · 생산 보드 배지와 같은 술어(도면별 막힘은 ``drawing_fix``)."""
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
