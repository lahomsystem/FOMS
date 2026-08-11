"""감사 로그 표시 SSOT — 영문 필드·원시 값을 FOMS 업무 언어로 옮긴다 (AUDIT-LOG P4).

**왜 SSOT 인가**: 한글 라벨 사전은 원래 ``foms/web/orders/edit.py`` 안의 **지역 변수**였다.
그래서 같은 회사 시스템인데 화면 A는 "시공정보 발송", 화면 B는
``regional_construction_info_sent`` 로 보였다(운영 실측: 최근 30일 보안 로그의 38%가
영문 필드명·``True``·python dict repr·HTML 원문). 사전을 여기로 모아 **쓰기 경로와 화면이
같은 문장 규격**을 쓰게 한다.

두 방향을 모두 지원한다:

* **쓰기 시점** — :func:`describe_field_change` 로 사람 문장을 만들어 ``security_logs.message``
  에 넣는다(구조화 ``detail`` 은 호출부가 함께 남긴다).
* **읽기 시점** — :func:`humanize_message` 가 **과거에 쌓인 자유 텍스트**(운영 24,605행)를
  역파싱해 같은 규격으로 보여준다. 재기록은 불가능하고, 파싱 실패분은 원문을 그대로 낸다
  (감사 화면은 읽지 못한 값을 감추지 않는다).
"""

from __future__ import annotations

import ast
import re
from typing import Any, Iterable, Mapping

from foms.services.orders.as_availability import (
    AS_AVAILABILITY_DAY_LABELS,
    AS_AVAILABILITY_TIME_LABELS,
)
from foms.services.orders.status_constants import STATUS

__all__ = [
    "ACTION_LABELS",
    "FIELD_LABELS",
    "action_label",
    "describe_action",
    "collect_order_ids",
    "describe_field_change",
    "describe_order_action",
    "extract_order_ids",
    "field_label",
    "format_value",
    "humanize_message",
    "order_label",
]

#: 영문 필드 → 업무 라벨. ``foms/web/orders/edit.py`` 의 지역 dict 에서 이관했다
#: (그쪽은 이 상수를 import 한다 — 사전이 두 벌이 되면 즉시 어긋난다).
FIELD_LABELS: dict[str, str] = {
    # --- 접수/기본 ---
    "received_date": "접수일",
    "received_time": "접수시간",
    "customer_name": "고객명",
    "phone": "전화번호",
    "address": "주소",
    "product": "제품",
    "options": "옵션 상세",
    "notes": "비고",
    "regional_memo": "메모",
    "status": "상태",
    "manager_name": "담당자",
    "manager": "담당자",
    "payment_amount": "결제금액",
    # --- 일정 ---
    "measurement_date": "실측일",
    "measurement_time": "실측시간",
    "scheduled_date": "설치예정일",
    "completion_date": "설치완료일",
    "shipping_scheduled_date": "상차 예정일",
    "construction_date": "시공일",
    # --- 주문 성격 ---
    "is_regional": "지방 주문",
    "is_self_measurement": "자가실측",
    "is_cabinet": "수납장",
    "construction_type": "시공 구분",
    "sales_delivery": "영업 배송",
    # --- 지방 체크리스트 6종 ---
    "measurement_completed": "실측완료",
    "regional_sales_order_upload": "영업발주 업로드",
    "regional_blueprint_sent": "도면 발송",
    "regional_order_upload": "발주 업로드",
    "regional_cargo_sent": "화물 발송",
    "regional_construction_info_sent": "시공정보 발송",
    # --- AS ---
    "as_visit_date": "AS 방문일",
    "as_completed_date": "AS 완료일",
    "as_content": "AS 내용",
    "as_visit_availability": "AS 방문 가능시간",
    "as_billing_type": "AS 비용 구분",
}

#: 체크박스형 필드 — True/False 를 "완료/해제"로 읽는다(예/아니오보다 업무 언어에 가깝다).
_CHECKLIST_FIELDS = frozenset({
    "measurement_completed",
    "regional_sales_order_upload",
    "regional_blueprint_sent",
    "regional_order_upload",
    "regional_cargo_sent",
    "regional_construction_info_sent",
})

#: 행위 코드 → 업무 라벨 (AUDIT-LOG P4 C1). 필드 변경이 아닌 **행위**(시공 시작·결제 확인
#: ·도면 전달 등)를 남길 때 쓴다. 코드는 ``security_logs.action`` 에 그대로 들어가므로
#: SQL 로 물을 수 있고, 화면에는 여기 라벨로 나온다. 사전에 없는 코드는 코드 자체를
#: 보여준다(감추지 않는다 — 새 배선이 라벨을 빠뜨려도 로그는 남는다).
ACTION_LABELS: dict[str, str] = {
    # --- 결제 ---
    "PAYMENT_CONFIRMED": "결제 확인",
    "PAYMENT_CONFIRM_CLEARED": "결제 확인 해제",
    # --- 시공 ---
    "CONSTRUCTION_STARTED": "시공 시작",
    "CONSTRUCTION_COMPLETED": "시공 완료",
    "CONSTRUCTION_REWORK_REQUESTED": "시공 불가(재작업 요청)",
    "CONSTRUCTION_EVIDENCE_UPDATED": "시공 증빙 등록",
    # --- 생산 ---
    "PRODUCTION_STARTED": "제작 시작",
    "PRODUCTION_COMPLETED": "제작 완료",
    "PRODUCTION_START_CANCELED": "제작 시작 취소",
    "PRODUCTION_COMPLETE_CANCELED": "제작 완료 취소",
    "PRODUCTION_REWORK_STARTED": "수정 제작 시작",
    "PRODUCTION_STEP_CHECKED": "생산 공정 체크",
    "PRODUCTION_DEFECT_REPORTED": "생산 불량 보고",
    "PRODUCTION_HOLD_SET": "생산 보류",
    "PRODUCTION_HOLD_RELEASED": "생산 보류 해제",
    "PRODUCTION_CHANGE_ACKNOWLEDGED": "생산 변경 확인",
    "LOGISTICS_STATUS_CHANGED": "물류 상태 변경",
    # --- AS ---
    "AS_RECEIVED": "AS 접수",
    "AS_SCHEDULED": "AS 방문일 지정",
    "AS_SCHEDULE_CANCELED": "AS 방문일 취소",
    "AS_STARTED": "AS 시작",
    "AS_COMPLETED": "AS 완료",
    "AS_REOPENED": "AS 재개봉",
    "AS_CATEGORY_CHANGED": "AS 분류 변경",
    "AS_BILLING_DECIDED": "AS 비용 판정",
    "AS_ROUND_VERDICT": "AS 회차 판정",
    "AS_SCHEDULE_LINK_CHANGED": "AS 기준 일정",
    "AS_LOG_ADDED": "AS 기록 추가",
    "AS_LOG_UPDATED": "AS 기록 수정",
    "AS_LOG_DELETED": "AS 기록 삭제",
    # --- 도면 ---
    "DRAWING_DELIVERED": "도면 전달 완료",
    "DRAWING_DELIVERY_CANCELED": "도면 전달 취소",
    "DRAWING_GATEWAY_FILE_UPLOADED": "도면 창구 파일 업로드",
    "BLUEPRINT_UPLOAD_ISSUED": "도면 업로드 발급",
    "BLUEPRINT_UPLOADED": "도면 업로드",
    # --- 실측·출고·업무 ---
    "MEASUREMENT_UPDATED": "실측 정보 수정",
    "SHIPMENT_UPDATED": "출고 정보 수정",
    "SHIPMENT_PACKING_SAVED": "출고 포장 저장",
    "SHIPMENT_CHANGE_ACKNOWLEDGED": "출고 변경 확인",
    "DRAWING_CHANGE_ACKNOWLEDGED": "도면 변경 확인",
    "DRAFTSMAN_ASSIGNED": "도면 담당자 배정",
    "QUEST_CREATED": "퀘스트 생성",
    "QUEST_STATUS_CHANGED": "퀘스트 상태 변경",
    "QUEST_APPROVED": "퀘스트 승인",
    "ORDER_TASK_CREATED": "업무 추가",
    "ORDER_TASK_UPDATED": "업무 수정",
    "ORDER_TASK_DELETED": "업무 삭제",
    "ORDER_CALL_LOGGED": "통화 기록",
    # --- 파일 ---
    "FILE_UPLOADED": "파일 업로드",
    "FILE_DELETED": "파일 삭제",
    "FILE_RESTORED": "파일 복구",
    "FILE_UPLOAD_FINALIZED": "파일 업로드 확정",
    "CHAT_MESSAGE_SENT": "채팅 메시지 발송",
    # --- 단가표·견적 마스터데이터 ---
    "CATALOG_ITEM_SAVED": "단가표 항목 저장",
    "CATALOG_ITEM_DELETED": "단가표 항목 삭제",
    "ESTIMATE_SAVED": "견적 저장",
    "ESTIMATE_DELETED": "견적 삭제",
    "ESTIMATE_ORDER_MATCHED": "견적-주문 연결",
    "ESTIMATE_ORDER_UNMATCHED": "견적-주문 연결 해제",
    "ESTIMATE_SYNCED_TO_ORDER": "견적 주문 반영",
    "ORDER_ESTIMATE_CREATED": "주문 견적 생성",
    "ORDER_ESTIMATE_UPDATED": "주문 견적 수정",
    "ORDER_ESTIMATE_DELETED": "주문 견적 삭제",
    "ORDER_STRUCTURED_SAVED": "주문 저장",
    "ORDER_ADDRESS_UPDATED": "주소 수정",
    "ADDRESS_LEARNING_ADDED": "주소 학습 등록",
    "STORAGE_SETTING_UPDATED": "스토리지 설정 변경",
    "NOTIFICATION_SENT": "알림 발송",
    "NOTIFICATION_ARCHIVED": "알림 보관",
    "NOTIFICATIONS_DELETED": "알림 일괄 삭제",
    "URGENT_MENTION_SENT": "긴급 호출",
    "CHANNEL_PUSH_SENT": "채널톡 발송",
    "ALIMTALK_MANUAL_SENT": "알림톡 수동 발송",
    "SHARE_LINK_CREATED": "고객 공유 링크 발급",
    "SHARE_LINK_REVOKED": "고객 공유 링크 회수",
    "BLUEPRINT_DELETED": "도면 삭제",
    "DRAWING_WIZARD_SAVED": "도면 마법사 저장",
    "DRAWING_WIZARD_ASSET_ADDED": "도면 마법사 자산 추가",
    "DRAWING_WIZARD_SHEET_SAVED": "도면 마법사 시트 저장",
    "DRAWING_WIZARD_SNAPSHOT_SAVED": "도면 마법사 버전 저장",
    "DRAWING_WIZARD_PENDING_DELETED": "도면 마법사 임시본 삭제",
    "ORDER_DRAFT_SAVED": "임시 주문 저장",
    "ORDER_DRAFT_SUBMITTED": "임시 주문 제출",
    "ORDER_DRAFT_DELETED": "임시 주문 삭제",
    # --- 주문 편집·상태 (2026-08-11: 운영 감사 화면에서 가장 자주 보이는데 라벨이 없었다) ---
    "ORDER_FIELD_UPDATED": "주문 항목 변경",
    "ORDER_MEMO_UPDATED": "메모 변경",
    "ORDER_CHECKLIST_UPDATED": "체크리스트 변경",
    "ORDER_STATUS_CHANGED": "상태 변경",
    "ORDER_SOFT_DELETED": "주문 휴지통 이동",
    # --- 파일 열람(access_logs 화면과 같은 코드를 쓴다) ---
    "FILE_VIEW": "파일 열람",
    "FILE_DOWNLOAD": "파일 다운로드",
    "FILE_PRESIGNED": "서명 URL 발급",
    # --- 계정·인증 ---
    "LOGIN_OK": "로그인 성공",
    "LOGIN_FAIL": "로그인 실패",
    "IMPERSONATE": "계정 전환(대리 로그인)",
    "USER_UPDATE": "사용자 정보 변경",
    "USER_APPROVE": "가입 승인",
    "USER_DEACTIVATE": "사용자 비활성화",
    "USER_PASSWORD_RESET": "비밀번호 재설정",
    "USER_BOOTSTRAP": "최초 관리자 생성",
    "RESET_REQUEST_HANDLE": "재설정 요청 처리",
    # --- 차단(거부 기록) ---
    "ACCESS_DENIED": "권한 거부",
    "CSRF_BLOCKED": "CSRF 차단",
    "WRITE_BLOCKED": "쓰기 차단",
}

#: 비어 있음을 뜻하는 원시 값들(문자열 비교는 소문자로 한다).
_EMPTY_TOKENS = frozenset({"", "none", "null", "-"})

#: 값을 비운 결과 표기(after 쪽).
_EMPTY_DISPLAY = "(지움)"

#: 원래 비어 있던 값 표기(before 쪽). "(지움) → 새 값"은 사실과 다르다 —
#: 지운 게 아니라 처음부터 없던 것이다.
_EMPTY_BEFORE_DISPLAY = "(없음)"

#: AS 내용처럼 긴 본문을 줄일 상한.
_LONG_TEXT_LIMIT = 60

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

#: 과거 자유 텍스트 3종(운영 실측 상위 유형) 역파싱.
#: 예) ``지방 주문 #4336의 'regional_blueprint_sent' 상태를 'True'(으)로 변경``
_LEGACY_FIELD_CHANGE_RE = re.compile(
    r"^(?P<prefix>지방 주문|자가실측 주문|자가실측|주문)\s*#(?P<order_id>\d+)의\s*"
    r"'(?P<field>[^']+)'\s*(?:필드|상태)를\s*'(?P<value>.*)'\(으\)로 변경$",
    re.S,
)

#: 상태 전이 구 형식. 예) ``자가실측 주문 #4679 상태 변경: 'MEASURE' → 'SHIPPED_PENDING'``
#: · ``주문 #4183 휴지통 이동 (bulk): MEASURE → DELETED``. 코드가 그대로 남아 있어
#: 운영자가 단계 이름을 외워야 읽힌다.
_LEGACY_STATUS_CHANGE_RE = re.compile(
    r"^(?P<prefix>지방 주문|자가실측 주문|자가실측|주문)\s*#(?P<order_id>\d+)\s*"
    r"(?P<verb>상태 변경|휴지통 이동(?:\s*\(bulk\))?)\s*:\s*"
    r"'?(?P<before>[^'→]*?)'?\s*→\s*'?(?P<after>[^']*?)'?$"
)

#: 문장 안의 주문 언급(고객명 병기 대상). **접두 라벨을 필수로 둔다** — 맨 숫자까지 받으면
#: ``사용자 #58 삭제`` 의 58 을 주문 58 로 착각해 엉뚱한 고객명을 붙인다(감사 로그에서는
#: 그런 오표기가 곧 오판이다).
_ORDER_MENTION_RE = re.compile(r"(?P<label>지방 주문|자가실측 주문|자가실측|주문)\s*#(?P<order_id>\d+)")


def field_label(field: str | None) -> str:
    """영문 필드명을 업무 라벨로 옮긴다.

    :param field: 필드명(``regional_blueprint_sent`` 등). ``None``/빈값 허용.
    :return: 사전에 있으면 한글 라벨, 없으면 원문(감추지 않는다).
    """
    if not field:
        return ""
    return FIELD_LABELS.get(field, field)


def _strip_markup(text: str) -> str:
    """HTML 태그를 지우고 공백을 접어 한 줄 텍스트로 만든다."""
    return _WS_RE.sub(" ", _TAG_RE.sub(" ", text)).strip()


def _summarize_text(value: Any) -> str:
    """자유 텍스트를 한 줄 요약으로 만든다(태그 제거 + 상한 초과 시 말줄임).

    :param value: 원시 값(HTML 이 섞여 있을 수 있다).
    :return: 한 줄 요약 문자열(빈 문자열 가능).
    """
    text = str(value).strip()
    if "<" in text and ">" in text:
        text = _strip_markup(text)
    if len(text) > _LONG_TEXT_LIMIT:
        return f"{text[:_LONG_TEXT_LIMIT]}…"
    return text


def _format_availability(value: Any) -> str | None:
    """``{"days":..,"time":..}`` 가능시간을 ``평일 · 오전`` 형태로 옮긴다.

    :param value: dict 이거나 그 python repr 문자열.
    :return: 표시 문자열, 해석 불가면 ``None``.
    """
    data = value
    if isinstance(data, str):
        text = data.strip()
        if not (text.startswith("{") and text.endswith("}")):
            return None
        try:
            data = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            return None
    if not isinstance(data, Mapping):
        return None

    parts = [
        AS_AVAILABILITY_DAY_LABELS.get(str(data.get("days")), None),
        AS_AVAILABILITY_TIME_LABELS.get(str(data.get("time")), None),
    ]
    shown = [p for p in parts if p]
    note = str(data.get("note") or "").strip()
    if note:
        shown.append(note)
    return " · ".join(shown) if shown else None


def format_value(field: str | None, value: Any) -> str:
    """원시 값을 사람이 읽는 표기로 옮긴다.

    규칙: 빈 값 → ``(지움)`` / 체크박스 → ``완료``·``해제`` / 그 밖의 불리언 → ``예``·``아니오``
    / 상태 코드 → 한글 단계명 / 가능시간 dict → ``평일 · 오전`` / HTML 본문 → 태그 제거 후 요약.

    :param field: 값이 속한 필드명(표기 규칙 선택에 쓴다). 모르면 ``None``.
    :param value: 원시 값(문자열·불리언·dict 모두 허용).
    :return: 표시 문자열.
    """
    if value is None:
        return _EMPTY_DISPLAY

    if isinstance(value, bool):
        truthy = value
    else:
        text_probe = str(value).strip()
        if text_probe.lower() in _EMPTY_TOKENS:
            return _EMPTY_DISPLAY
        truthy = None
        if text_probe.lower() in ("true", "false"):
            truthy = text_probe.lower() == "true"

    if truthy is not None:
        if field in _CHECKLIST_FIELDS:
            return "완료" if truthy else "해제"
        return "예" if truthy else "아니오"

    if field == "as_visit_availability":
        formatted = _format_availability(value)
        if formatted:
            return formatted

    text = str(value).strip()
    if field == "status":
        return STATUS.get(text, text)

    return _summarize_text(text) or _EMPTY_DISPLAY


def order_label(
    order_id: int | str,
    *,
    customer_name: str | None = None,
    order_type: str | None = None,
) -> str:
    """주문 표기 문자열(``지방 주문 #4183 (김철수)``)을 만든다.

    고객명이 함께 있어야 로그만 보고 "누구 건인지"를 알 수 있다. 이름을 모르면
    (삭제된 주문 등) 주문번호만 낸다 — 없는 이름을 지어내지 않는다.

    :param order_id: 주문 id.
    :param customer_name: 고객명(없으면 생략).
    :param order_type: ``지방 주문``·``자가실측`` 같은 접두. 없으면 ``주문``.
    :return: 표시 문자열.
    """
    head = (order_type or "주문").strip() or "주문"
    name = (customer_name or "").strip()
    return f"{head} #{order_id} ({name})" if name else f"{head} #{order_id}"


def describe_field_change(
    *,
    order_id: int | str,
    field: str,
    after: Any,
    before: Any = None,
    has_before: bool = False,
    customer_name: str | None = None,
    order_type: str | None = None,
) -> str:
    """필드 변경 1건을 사람 문장으로 만든다(쓰기 경로 공용).

    ``has_before`` 가 True 면 ``이전 → 이후`` 로, 아니면 결과만 적는다. 체크박스 필드는
    "…로 표시"라고 적어 목록에서 상태 변화가 눈에 띄게 한다.

    :param order_id: 대상 주문 id.
    :param field: 변경된 필드명.
    :param after: 변경 후 값.
    :param before: 변경 전 값(``has_before`` 가 True 일 때만 쓴다).
    :param has_before: 변경 전 값을 알고 있는지 여부.
    :param customer_name: 고객명(있으면 병기).
    :param order_type: 주문 성격 접두(``지방 주문``·``자가실측``).
    :return: ``지방 주문 #4183 (김철수) — 시공정보 발송: 완료로 표시`` 형태 문장.
    """
    head = order_label(order_id, customer_name=customer_name, order_type=order_type)
    label = field_label(field)
    after_text = format_value(field, after)

    if has_before:
        before_text = format_value(field, before)
        # 빈 값 두 종류(``(없음)``/``(지움)``)는 표기만 다를 뿐 같은 상태다. 텍스트로만 비교하면
        # "없던 값을 지웠다"는 화살표가 생겨 사실과 다르게 읽힌다(2026-08-10 운영 실측).
        both_empty = before_text == _EMPTY_DISPLAY and after_text == _EMPTY_DISPLAY
        if before_text == _EMPTY_DISPLAY:
            before_text = _EMPTY_BEFORE_DISPLAY
        if not both_empty and before_text != after_text:
            return f"{head} — {label}: {before_text} → {after_text}"
    if field in _CHECKLIST_FIELDS:
        return f"{head} — {label}: {after_text}로 표시"
    return f"{head} — {label}: {after_text}"


def action_label(action: str | None) -> str:
    """행위 코드를 업무 라벨로 옮긴다.

    :param action: 행위 코드(``CONSTRUCTION_COMPLETED`` 등). ``None``/빈값 허용.
    :return: 사전에 있으면 한글 라벨, 없으면 원문(감추지 않는다).
    """
    if not action:
        return ""
    return ACTION_LABELS.get(action, action)


def describe_action(
    action: str,
    *,
    target_label: str | None = None,
    note: str | None = None,
) -> str:
    """주문이 아닌 대상(채팅방·단가표·견적 등)의 행위 문장을 만든다.

    주문 대상은 :func:`describe_order_action` 이 담당한다. 여기서는 대상 표기를 호출부가
    문자열로 넘긴다(대상 종류가 제각각이라 공통 스키마가 없다).

    :param action: 행위 코드(:data:`ACTION_LABELS` 키).
    :param target_label: 대상 표기(``단가표 '상판'``·``채팅방 #3``). 없으면 생략.
    :param note: 짧은 부연. 길면 잘라 요약한다.
    :return: ``단가표 '상판' — 단가 항목 저장`` 형태 문장.
    """
    label = action_label(action)
    head = (target_label or "").strip()
    line = f"{head} — {label}" if head else label
    tail = _summarize_text(note) if note else ""
    return f"{line}: {tail}" if tail else line


def describe_order_action(
    *,
    order_id: int | str,
    action: str,
    customer_name: str | None = None,
    order_type: str | None = None,
    note: str | None = None,
) -> str:
    """주문에 대한 **행위** 1건을 사람 문장으로 만든다(쓰기 경로 공용).

    필드 변경은 :func:`describe_field_change` 가, "시공을 시작했다"처럼 값이 아니라
    행위 자체가 기록 대상인 경우는 이 함수가 문장을 만든다. 두 경로 모두 같은 주문 표기
    (``지방 주문 #4183 (김철수)``)를 쓰므로 화면에서 한 줄로 섞여 읽힌다.

    :param order_id: 대상 주문 id.
    :param action: 행위 코드(:data:`ACTION_LABELS` 키).
    :param customer_name: 고객명(있으면 병기).
    :param order_type: 주문 성격 접두(``지방 주문``·``자가실측 주문``).
    :param note: 행위에 딸린 짧은 부연(전달 메모·결제 종류 등). 길면 잘라 요약한다.
    :return: ``주문 #4109 (홍길동) — 시공 완료`` 형태 문장.
    """
    head = order_label(order_id, customer_name=customer_name, order_type=order_type)
    label = action_label(action)
    tail = _summarize_text(note) if note else ""
    return f"{head} — {label}: {tail}" if tail else f"{head} — {label}"


def extract_order_ids(message: str | None) -> list[int]:
    """문장에서 언급된 주문 id 를 뽑는다(화면이 고객명을 배치 조회하기 위한 입력).

    :param message: 로그 메시지.
    :return: 등장 순서의 주문 id 목록(중복 제거).
    """
    if not message:
        return []
    seen: dict[int, None] = {}
    for match in _ORDER_MENTION_RE.finditer(message):
        seen.setdefault(int(match.group("order_id")), None)
    return list(seen)


def _annotate_order_mentions(message: str, customer_names: Mapping[int, str]) -> str:
    """이미 읽을 만한 문장의 ``#주문번호`` 뒤에 고객명만 덧붙인다.

    **이미 이름이 병기된 문장은 건드리지 않는다** — P4 C 이후 쓰기 경로가 만드는 문장은
    ``주문 #4704 (황인영) — …`` 처럼 이름을 이미 포함한다. 무조건 덧붙이면 운영 화면에
    ``(황인영) (황인영)`` 이 찍힌다(2026-08-10 운영 실측).
    """

    def _repl(match: re.Match[str]) -> str:
        order_id = int(match.group("order_id"))
        name = (customer_names.get(order_id) or "").strip()
        if not name:
            return match.group(0)
        tail = message[match.end():]
        if tail.lstrip().startswith("("):  # 이미 (이름) 이 붙어 있다.
            return match.group(0)
        return f"{match.group(0)} ({name})"

    return _ORDER_MENTION_RE.sub(_repl, message)


def humanize_message(message: str | None, customer_names: Mapping[int, str] | None = None) -> str:
    """저장된 로그 문장을 화면 표기로 옮긴다(구 형식 역파싱 포함).

    운영에 이미 쌓인 자유 텍스트는 재기록할 수 없다. 그래서 읽는 시점에 옮긴다:
    필드 변경 3종은 라벨·값 규격으로 다시 쓰고, 그 밖의 문장은 주문번호 옆에 고객명만
    덧붙인다. **어느 쪽도 실패하면 원문을 그대로 돌려준다**(값을 감추지 않는다).

    :param message: 저장된 ``security_logs.message``.
    :param customer_names: ``{주문 id: 고객명}`` (화면이 배치 조회해 넘긴다).
    :return: 표시 문장.
    """
    if not message:
        return ""
    names = customer_names or {}

    text = message.strip()

    status_match = _LEGACY_STATUS_CHANGE_RE.match(text)
    if status_match:
        order_id = int(status_match.group("order_id"))
        head = order_label(
            order_id,
            customer_name=names.get(order_id),
            order_type=status_match.group("prefix"),
        )
        verb = "휴지통으로 이동" if "휴지통" in status_match.group("verb") else "상태"
        after = format_value("status", status_match.group("after"))
        raw_before = status_match.group("before").strip()
        if not raw_before:
            # 구 bulk 기록은 이전 상태를 안 남긴 건이 있다. "(지움) → 삭제됨"은 사실과 다르다
            # (지운 게 아니라 애초에 기록이 없다) — 화살표 없이 결과만 적는다.
            return f"{head} — {verb}: {after}"
        return f"{head} — {verb}: {format_value('status', raw_before)} → {after}"

    match = _LEGACY_FIELD_CHANGE_RE.match(text)
    if match:
        order_id = int(match.group("order_id"))
        return describe_field_change(
            order_id=order_id,
            field=match.group("field"),
            after=match.group("value"),
            customer_name=names.get(order_id),
            order_type=match.group("prefix"),
        )

    return _annotate_order_mentions(message, names)


def collect_order_ids(messages: Iterable[str | None]) -> list[int]:
    """여러 메시지에서 주문 id 를 모은다(페이지 단위 배치 조회용 — N+1 금지).

    :param messages: 로그 메시지들.
    :return: 중복 없는 주문 id 목록.
    """
    seen: dict[int, None] = {}
    for message in messages:
        for order_id in extract_order_ids(message):
            seen.setdefault(order_id, None)
    return list(seen)
