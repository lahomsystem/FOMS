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
import json
import re
from typing import Any, Iterable, Mapping

from foms.services.orders.as_availability import (
    AS_AVAILABILITY_DAY_LABELS,
    AS_AVAILABILITY_TIME_LABELS,
)
from foms.services.orders.status_constants import CABINET_STATUS, STATUS
# 원장 값 규칙 SSOT. 의존 방향은 **표시 → diff** 한 쪽뿐이다 — ``structured_diff`` 는 이
# 모듈을 import 하지 않는다(그쪽 모듈 docstring 규칙 3: 라벨은 읽기 시점에 붙인다).
# 태그 제거·절단 표식을 여기에 다시 적으면 원장에 담긴 텍스트와 화면에 뜨는 텍스트가
# 서로 다른 규칙으로 잘린다.
from foms.services.orders.structured_diff import (
    CONTENT_MODIFIED_MARK,
    NUMERIC_PATH_SUFFIXES,
    strip_markup,
)

__all__ = [
    "ACTION_LABELS",
    "FIELD_LABELS",
    "PATH_LABELS",
    "action_label",
    "describe_change",
    "path_label",
    "summarize_changes",
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
    # 수납장 대시보드 typed 컬럼(STORAGE-WRITER-01). 값은 코드라 format_value 가 CABINET_STATUS
    # 로 옮긴다.
    "cabinet_status": "수납장 상태",
    "shipping_fee": "배송비",
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
    "as_received_date": "AS 접수일",
    "as_completed_date": "AS 완료일",
    "as_content": "AS 내용",
    "as_visit_availability": "AS 방문 가능시간",
    "as_billing_type": "AS 비용 구분",
}

#: **코드 값을 쓰는 필드 → 그 코드 사전**. 원장·로그에는 ``SHIPPED`` 같은 코드가 그대로
#: 저장되므로 읽는 시점에 옮긴다. 사전은 업무 로직이 쓰는 것을 **그대로 재사용**한다 —
#: 여기에 한글을 베껴 쓰면 단계·상태가 추가될 때 화면만 낡는다(이 모듈이 생긴 이유가
#: 라벨 사전 이중화였다). 사전에 없는 코드는 코드 원문을 낸다(감사 화면은 값을 감추지 않는다).
_CODE_LABEL_MAPS: dict[str, Mapping[str, str]] = {
    "status": STATUS,
    "cabinet_status": CABINET_STATUS,
}

#: 체크박스형 필드 — True/False 를 "완료/해제"로 읽는다(예/아니오보다 업무 언어에 가깝다).
#:
#: ``is_self_measurement``·``is_cabinet`` 은 2026-08-26(AUDIT-GAP-01)에 합류했다. 둘 다 주문
#: 수정 폼의 **체크박스**(``edit.py:187``·``:243``)인데 여기 없어서 같은 폼의 체크리스트 6종은
#: "완료/해제", 이 둘만 "예/아니오"로 읽혔다. ``is_regional`` 은 그대로 뺀다 — 그건 사람이 켜는
#: 체크가 아니라 주문 성격 분류(지방/수도권)라 "완료"가 뜻이 통하지 않는다.
_CHECKLIST_FIELDS = frozenset({
    "measurement_completed",
    "regional_sales_order_upload",
    "regional_blueprint_sent",
    "regional_order_upload",
    "regional_cargo_sent",
    "regional_construction_info_sent",
    "is_self_measurement",
    "is_cabinet",
})

#: 행위 코드 → 업무 라벨 (AUDIT-LOG P4 C1). 필드 변경이 아닌 **행위**(시공 시작·결제 확인
#: ·도면 전달 등)를 남길 때 쓴다. 코드는 ``security_logs.action`` 에 그대로 들어가므로
#: SQL 로 물을 수 있고, 화면에는 여기 라벨로 나온다. 사전에 없는 코드는 코드 자체를
#: 보여준다(감추지 않는다 — 새 배선이 라벨을 빠뜨려도 로그는 남는다).
ACTION_LABELS: dict[str, str] = {
    # --- 네이버 스마트스토어 수집 (NAVER-INGEST-01) ---
    "NAVER_INGEST_RUN_NOW": "네이버 수집 수동 실행",
    "NAVER_INGEST_BACKFILL_ENQUEUE": "네이버 과거 주문 소급 수집 요청",
    "NAVER_INGEST_SNAPSHOT_VIEW": "네이버 수집 원본 열람",
    "NAVER_INGEST_MARK_REVIEWED": "네이버 수집 확인 완료",
    "NAVER_INGEST_SET_APP_EXPIRY": "네이버 커머스API 인증 만료일 등록",
    "NAVER_INGEST_SET_ASSIGNEE": "네이버 수집 담당자 지정",
    "NAVER_INGEST_CREATE_ORDER": "네이버 수집분 주문 생성",
    "NAVER_INGEST_ATTACH_ORDER": "네이버 수집분 기존 주문 연결",
    "NAVER_INGEST_GHOST_DISCARD": "네이버 유령 주문 취소 처리",
    "NAVER_INGEST_REPAY_RECONCILE": "네이버 재결제 정리",
    "NAVER_INGEST_DETACH_ORDER": "네이버 수집분 연결 되돌림",
    "NAVER_INGEST_FULFILLMENT_ENQUEUE": "네이버 발주확인·발송처리 요청",
    "NAVER_INGEST_BULK_DISPATCH_ENQUEUE": "네이버 일괄 발송처리 요청(오늘 실측분)",
    "NAVER_INGEST_BULK_DISPATCH_AUTO": "네이버 자동 발송처리(평일 정시)",
    "NAVER_INGEST_REFRESH_ENQUEUE": "네이버 다시 읽기 요청",
    "NAVER_ORIGIN_CLEANUP_REFRESH_ENQUEUE": "네이버 옛 주문 일괄 다시 읽기",
    "NAVER_INGEST_REFRESH_ALL_ENQUEUE": "네이버 전체 다시 읽기",
    "NAVER_INGEST_CANCEL_ENQUEUE": "네이버 판매자 직접취소 요청",
    "NAVER_INGEST_RETURN_ENQUEUE": "네이버 판매자 반품 접수 요청",
    # 접수와 **가른다** — 승인은 환불이 나가는 사건이라 감사 원장에서 따로 읽혀야 한다.
    "NAVER_INGEST_RETURN_APPROVE_ENQUEUE": "네이버 판매자 반품 접수+승인 요청",
    # 거부는 **다른 사건**이다 — 접수·승인과 갈라 읽을 수 있어야 "누가 무슨 문장을
    # 고객에게 보냈나"에 답할 수 있다(문장 원문은 detail 에 남는다).
    "NAVER_INGEST_RETURN_REJECT_ENQUEUE": "네이버 판매자 반품 거부 요청",
    "NAVER_INGEST_REJECT_TEMPLATES_SAVE": "네이버 반품 거부 상용구 저장",
    # 승인 2종(T9). **접수+승인과 또 가른다** — 위 ``..._RETURN_APPROVE_ENQUEUE`` 는
    # "우리가 접수하면서 같이 승인한 것"이고, 아래는 "이미 있던 클레임을 승인한 것"이다.
    # 같은 이름을 재사용하면 "누가 환불을 냈나"를 갈라 읽을 수 없다.
    "NAVER_INGEST_CANCEL_APPROVE_ENQUEUE": "네이버 구매자 취소요청 승인",
    "NAVER_INGEST_RETURN_APPROVE_ONLY_ENQUEUE": "네이버 반품 승인(접수 없이)",
    "NAVER_INGEST_FULFILLMENT_CLEAR": "네이버 발주확인·발송처리 실패 기록 지움",
    "NAVER_DOCK_STATE_SET": "네이버 도크 반영 상태 저장",
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
    "AS_UPLOAD_ANCHOR": "AS 첨부 위치",
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
    "ORDER_CHANGE_REASON_SET": "변경 사유 입력",
    "ORDER_ADDRESS_UPDATED": "주소 수정",
    "ADDRESS_LEARNING_ADDED": "주소 학습 등록",
    "STORAGE_SETTING_UPDATED": "스토리지 설정 변경",
    "NOTIFICATION_SENT": "알림 발송",
    "NOTIFICATION_ARCHIVED": "알림 보관",
    "NOTIFICATIONS_DELETED": "알림 일괄 삭제",
    "URGENT_MENTION_SENT": "긴급 호출",
    "CHANNEL_PUSH_SENT": "채널톡 발송",
    "ALIMTALK_MANUAL_SENT": "알림톡 수동 발송",
    "ALIMTALK_CHANNEL_CONFIRMED": "알림톡 발송 채널 확인",
    "SHARE_LINK_CREATED": "고객 공유 링크 발급",
    "SHARE_LINK_REVOKED": "고객 공유 링크 회수",
    "SHARE_SMS_SENT": "고객 공유 링크 문자 발송",
    "SHARE_ALIMTALK_SENT": "고객 공유 링크 알림톡 발송",
    "SHARE_HISTORY_VIEWED": "고객 열람 계약서 기록 조회",
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
    "ORDER_FIELD_RESTORED": "변경 되돌리기",
    "OPS_BACKUP_HEARTBEAT": "백업 성공 알림",
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

#: 구조화 경로(``structured_data`` 점 경로) → 업무 라벨 (ORDER-DIFF-00).
#: :data:`FIELD_LABELS` 와 사전을 나눈 이유는 문법이 다르기 때문이다 — 저쪽은 평면 컬럼명
#: (``measurement_date``), 이쪽은 중첩 경로(``schedule.measurement.date``)다. 품목은 인덱스가
#: 변하므로 ``items.*.<필드>`` 로 등재하고 :func:`path_label` 이 번호를 붙인다.
#: **라벨은 읽기 시점에 붙인다** — 기록에는 경로만 남기므로 여기를 고치면 과거 기록도 함께 고쳐진다.
PATH_LABELS: dict[str, str] = {
    # --- 일정 ---
    "schedule.measurement.date": "실측일",
    "schedule.measurement.time": "실측시간",
    "schedule.construction.date": "시공일",
    "schedule.construction.time": "시공시간",
    "schedule.as_visit.date": "AS 방문일",
    "schedule.as_visit.time": "AS 방문시간",
    "schedule.as_visit.availability": "AS 방문 가능시간",
    # --- 당사자 ---
    "parties.customer.name": "고객명",
    "parties.customer.phone": "전화번호",
    "parties.customer.phone2": "보조 연락처",
    # ORDERER-AXIS-01: parties.orderer 는 발주처(라홈/하우드) 자리다. 주문한 사람은 buyer.
    # 구 라벨이 '주문자명'이라 두 뜻이 겹쳐 있던 흔적이었다 — 과거 이력 표시를 위해 경로는
    # 남기되 라벨만 바로잡는다.
    "parties.orderer.name": "발주사",
    "parties.orderer.phone": "발주사 연락처",
    "parties.buyer.name": "주문자명",
    "parties.buyer.phone": "주문자 연락처",
    "parties.manager.name": "담당자",
    # --- 현장 ---
    "site.address_full": "주소",
    "site.address_detail": "상세주소",
    # --- 단계/플래그/배정 ---
    "workflow.stage": "단계",
    "flags.urgent": "긴급",
    "flags.urgent_reason": "긴급 사유",
    "flags.factory2": "라홈시스템(2공장)",
    # 평면 컬럼이라 structured 경로가 없다. 원장에는 컬럼명을 그대로 경로로 싣는다
    # (drawing_order_change 의 변경 리스트도 같은 bare 키 규약을 쓴다).
    "is_regional": "지방 주문",
    "construction_type": "지방주문 구분",
    "assignments.owner_team": "담당 팀",
    "assignments.drawing_assignee_user_ids": "도면 배정자",
    # --- 금액 ---
    "totals.items_total": "품목 합계",
    "totals.deposit_amount": "예약금",
    "totals.balance_amount": "잔금",
    "totals.final_amount": "최종 금액",
    "totals.discount_amount": "할인",
    "totals.free_input_amount": "자유입력 금액",
    "totals.contract_total": "계약 총액",
    "totals.shipping_price": "출고가",
    # --- 결제 입력 ---
    "payment.deposit": "예약금 입력",
    "payment.discount": "할인 입력",
    "payment.free_input": "자유입력",
    "payment.cash_receipt": "현금영수증",
    "payment.balance_note": "잔금 비고",
    # --- 출고/시공 ---
    "shipment.sales_delivery": "영업 배송",
    "shipment.construction_time": "시공 시간",
    "shipment.construction_workers": "시공 인원",
    "shipment.trip": "출장",
    "shipment.as_billing": "AS 비용 구분",
    "shipment.as_pending": "AS 보류",
    "shipment.as_content": "AS 내용",
    # 값은 건수 요약이다(``structured_diff._site_extra_summary``) — 본문 20개를 원장 한 칸에
    # 담지 않는다.
    "shipment.site_extra": "현장 특이사항",
    # --- 비고 ---
    # sd 의 ``notes`` **객체**(주소·실측·시공 특이사항 4칸)다. ``Order.notes`` 컬럼은 별도
    # textarea 라 아래 ``order_notes`` 로 나눠 둔다 — 같은 라벨이면 감사 화면에 뜻이 다른
    # "비고" 두 줄이 나란히 뜬다.
    "notes": "비고",
    # --- 품목(인덱스는 path_label 이 붙인다) ---
    "items.*.product_name": "품목명",
    "items.*.price": "단가",
    "items.*.spec": "규격",
    "items.*.spec_width": "규격(가로)",
    "items.*.spec_height": "규격(세로)",
    "items.*.spec_depth": "규격(깊이)",
    "items.*.color": "색상",
    "items.*.handle": "손잡이",
    "items.*.option_detail": "옵션 상세",
    "items.*.extra_input": "추가 입력",
    "items.*.misc": "기타",
    "items.*.internal": "내부 메모",
    "items.*.measurement_date": "실측일",
    "items.*.construction_date": "시공일",
    "items.*.spec_rows": "규격표",
    # --- 평면 컬럼(AUDIT-GAP-01) ---
    # 위 ``is_regional``·``construction_type`` 과 같은 bare 키 규약이다: ``Order`` 의 typed
    # 컬럼은 structured 경로가 없어 컬럼명을 그대로 원장 ``path`` 로 싣는다. 라벨이 여기
    # 없으면 감사 화면에 영문 컬럼명이 그대로 뜬다.
    "is_self_measurement": "자가실측",
    "is_cabinet": "수납장",
    "cabinet_status": "수납장 상태",
    # ``notes``(sd 비고 **객체**)와 이름을 나눈다 — 위 ``notes`` 항목의 주석 참조.
    "order_notes": "주문 비고",
    "received_date": "접수일",
    "received_time": "접수시간",
    "shipping_fee": "배송비",
    "payment_amount": "결제금액",
    "completion_date": "설치완료일",
    "as_received_date": "AS 접수일",
    "as_completed_date": "AS 완료일",
    "shipping_scheduled_date": "상차 예정일",
    "options": "옵션 상세",
    "status": "상태",
    # :data:`FIELD_LABELS` 쪽은 "메모"다 — 그쪽 문장은 ``지방 주문 #4183 (김철수) — 메모: …``
    # 처럼 주문 접두가 이미 "지방"을 말한다. 원장 행에는 그 접두가 없어(``메모 A → B``) 어느
    # 메모인지 알 수 없으므로 여기서만 "지방"을 붙인다.
    "regional_memo": "지방 메모",
    # AUDIT-GAP-01: 비ERP 주문 폴백 경로(``field_update`` 는 sd 가 없는 주문에서만 평면 컬럼명을
    # 쓴다). 라벨은 **sd 쌍둥이와 같은 말**로 맞춘다 — 같은 원장 표에 ``schedule.measurement.date``
    # 행과 나란히 놓이는데 이름이 다르면 한 값이 두 가지로 읽힌다.
    "manager_name": "담당자",
    "measurement_date": "실측일",
    "scheduled_date": "시공일",
    # 지방 체크리스트 6종. 값 표기는 _PATH_VALUE_FIELD 가 체크박스 규칙으로 넘긴다.
    "regional_sales_order_upload": "영업발주 업로드",
    "regional_blueprint_sent": "도면 발송",
    "regional_order_upload": "발주 업로드",
    "regional_cargo_sent": "화물 발송",
    "regional_construction_info_sent": "시공정보 발송",
    "measurement_completed": "실측완료",
}

#: 품목 경로 분해용. ``items.2`` (품목 자체 추가/삭제)와 ``items.2.price`` 를 모두 받는다.
_ITEM_PATH_RE = re.compile(r"^items\.(?P<index>\d+)(?:\.(?P<field>[A-Za-z0-9_]+))?$")

#: 경로별 **값 표기 규칙** 위임(원장 ``path`` → :func:`format_value` 의 ``field``).
#: 단계 코드는 :func:`format_value` 의 ``status`` 규칙을 그대로 쓴다.
#:
#: 평면 컬럼(AUDIT-GAP-01)은 경로와 필드명이 같아 자기 이름을 가리킨다. **생략하면 안 된다** —
#: 위임이 없으면 :func:`format_value` 가 ``field=None`` 으로 불려 체크박스가 ``완료/해제`` 대신
#: ``예/아니오``, 상태 코드가 한글 단계명 대신 ``MEASURE`` 로 나온다(같은 값이 화면마다 다르게
#: 읽히는 것이 이 모듈이 없애려는 문제다).
_PATH_VALUE_FIELD: dict[str, str] = {
    # 가능시간 dict 는 ``format_value`` 의 as_visit_availability 규칙이 "평일 · 오전"으로
    # 읽어준다. 위임이 없으면 화면에 JSON 원문이 그대로 뜬다.
    "schedule.as_visit.availability": "as_visit_availability",
    "workflow.stage": "status",
    "status": "status",
    "is_self_measurement": "is_self_measurement",
    "is_cabinet": "is_cabinet",
    "cabinet_status": "cabinet_status",
    "measurement_completed": "measurement_completed",
    "regional_sales_order_upload": "regional_sales_order_upload",
    "regional_blueprint_sent": "regional_blueprint_sent",
    "regional_order_upload": "regional_order_upload",
    "regional_cargo_sent": "regional_cargo_sent",
    "regional_construction_info_sent": "regional_construction_info_sent",
}

#: 비어 있음을 뜻하는 원시 값들(문자열 비교는 소문자로 한다).
_EMPTY_TOKENS = frozenset({"", "none", "null", "-"})

#: 값을 비운 결과 표기(after 쪽).
_EMPTY_DISPLAY = "(지움)"

#: 원래 비어 있던 값 표기(before 쪽). "(지움) → 새 값"은 사실과 다르다 —
#: 지운 게 아니라 처음부터 없던 것이다.
_EMPTY_BEFORE_DISPLAY = "(없음)"

#: 객체·목록이 저장돼 있으나 안에 내용이 하나도 없을 때 표기. 빈 칸만 담긴 비고 객체가
#: 화면에 JSON 원문으로 남지 않게 한다(값이 없다는 사실 자체는 감추지 않는다).
_EMPTY_CONTENT_DISPLAY = "(내용 없음)"

#: AS 내용처럼 긴 본문을 줄일 상한.
_LONG_TEXT_LIMIT = 60

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


def _summarize_text(value: Any) -> str:
    """자유 텍스트를 한 줄 요약으로 만든다(태그 제거 + 상한 초과 시 말줄임).

    :param value: 원시 값(HTML 이 섞여 있을 수 있다).
    :return: 한 줄 요약 문자열(빈 문자열 가능).
    """
    text = str(value).strip()
    if "<" in text and ">" in text:
        text = strip_markup(text)
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


def _format_structured_text(text: str) -> str:
    """JSON 으로 저장된 값(비고 객체·배정자 목록 등)을 사람 표기로 옮긴다.

    원장에는 값이 문자열 한 칸으로 들어가므로, 객체·목록은 직렬화된 채 남는다. 그대로 내면
    화면에 ``{"address_note": "", "construction_note": …`` 가 뜬다(2026-08-14 운영 실측).
    표기 규칙은 채널톡 변경 알림이 쓰는 것과 **같은 SSOT** 를 쓴다 — 사전을 두 벌 두면
    한쪽만 고쳐진다. import 는 함수 안에서 한다(표시 모듈이 알림·모델 의존을 로드 시점에
    끌고 오지 않게).

    이미 쌓인 이력에는 **저장 상한(120자)에서 잘린** 객체가 섞여 있다
    (``{"address_note": "", "construction_n…``). 그대로 두면 과거 행만 JSON 원문으로 남으므로,
    잘린 조각은 마지막으로 온전한 항목까지 되살려 읽고 ``…`` 로 잘렸음을 밝힌다(무성 복원 금지).

    :param text: 값 문자열. JSON 객체·배열 형태가 아니면 빈 문자열을 낸다.
    :return: 사람 표기(``주소 특이사항 잠금장치, 실측 특이사항 오전만``) 또는 빈 문자열.
    """
    if not (text.startswith("{") or text.startswith("[")):
        return ""
    from foms.services.notifications.drawing_order_change import format_value_for_display

    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        salvaged = _salvage_clipped_json(text)
        if salvaged is None:
            return ""
        rendered = format_value_for_display(salvaged).strip()
        return f"{rendered} …" if rendered else _EMPTY_CONTENT_DISPLAY
    return format_value_for_display(parsed).strip() or _EMPTY_CONTENT_DISPLAY


def _salvage_clipped_json(text: str) -> Any | None:
    """상한에서 잘린 JSON 조각을 마지막 온전한 항목까지 되살린다.

    ``_clip`` 은 값이 120자를 넘으면 뒤를 자르고 ``…`` 를 붙인다 — 객체·배열이 잘리면
    ``json.loads`` 가 실패하고 화면에 원문이 남는다. 마지막 쉼표까지 되돌린 뒤 괄호를 닫아
    다시 읽는다. **되살린 부분만** 쓰고, 잘린 사실은 호출부가 ``…`` 로 표기한다.

    :param text: 잘린 JSON 문자열.
    :return: 파싱된 값. 되살릴 수 없으면 ``None``.
    """
    closer = "}" if text.startswith("{") else "]"
    body = text.rstrip("…").rstrip()
    cut = body.rfind(",")
    while cut > 0:
        try:
            return json.loads(body[:cut] + closer)
        except (TypeError, ValueError):
            cut = body.rfind(",", 0, cut)
    return None


def format_value(field: str | None, value: Any) -> str:
    """원시 값을 사람이 읽는 표기로 옮긴다.

    규칙: 빈 값 → ``(지움)`` / 체크박스 → ``완료``·``해제`` / 그 밖의 불리언 → ``예``·``아니오``
    / 코드 값(:data:`_CODE_LABEL_MAPS`: 단계·수납장 상태) → 한글 이름 / 가능시간 dict →
    ``평일 · 오전`` / HTML 본문 → 태그 제거 후 요약.

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
    codes = _CODE_LABEL_MAPS.get(field or "")
    if codes is not None:
        return codes.get(text, text)

    structured = _format_structured_text(text)
    if structured:
        return _summarize_text(structured)

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


def path_label(path: str | None) -> str:
    """구조화 경로를 업무 라벨로 옮긴다 (ORDER-DIFF-00).

    품목 경로는 인덱스를 사람 번호로 바꿔 앞에 붙인다(``items.1.price`` → ``2번 품목 단가``).
    사전에 없는 경로는 **경로 자체**를 낸다 — 새 필드가 라벨 등재를 빠뜨려도 변경 사실은 보인다.

    :param path: ``structured_data`` 점 경로.
    :return: 표시 라벨.
    """
    if not path:
        return ""
    known = PATH_LABELS.get(path)
    if known:
        return known

    match = _ITEM_PATH_RE.match(path)
    if not match:
        return path
    head = f"{int(match.group('index')) + 1}번 품목"
    field = match.group("field")
    if not field:
        return head
    return f"{head} {PATH_LABELS.get(f'items.*.{field}', field)}"


#: 파생 ``totals.*`` 행 → 그 값을 만든 **입력** 경로. 폼이 예약금을 한 번 고치면 입력 경로와
#: 서버 파생 합계가 **같은 말을 두 줄로** 남긴다(2026-08-21 스테이징 실화면:
#: ``예약금 0 → 100,000`` + ``예약금 입력 0 → 100,000``). 원장에는 둘 다 남기고 화면만 접는다.
MIRROR_DERIVED_TO_INPUT: dict[str, str] = {
    "totals.deposit_amount": "payment.deposit",
    "totals.discount_amount": "payment.discount",
    "totals.free_input_amount": "payment.free_input",
}


def resolve_mirror_rows(rows: Iterable[Mapping[str, Any]]) -> tuple[set[Any], dict[Any, str]]:
    """한 저장(change set) 안에서 파생·입력 쌍이 같은 값을 말하는 행을 찾는다.

    값이 다르면 접지 않는다 — 파생 계산이 입력과 어긋난 상태 자체가 봐야 할 정보다.

    :param rows: ``id``·``path``·``before``·``after`` 를 가진 매핑들(한 change set 분량).
    :return: ``(숨길 행 id 집합, 살아남는 행 id → 대체 라벨)``. 살아남는 쪽은 사람이 입력한
        경로이고, 라벨은 짧은 파생 쪽 이름(``예약금 입력`` 대신 ``예약금``)을 쓴다.
    """
    by_path: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        path = str(row.get("path") or "")
        if path:
            by_path.setdefault(path, row)

    dropped: set[Any] = set()
    labels: dict[Any, str] = {}
    for derived_path, input_path in MIRROR_DERIVED_TO_INPUT.items():
        derived = by_path.get(derived_path)
        source = by_path.get(input_path)
        if derived is None or source is None:
            continue
        same = (
            str(derived.get("before") or "").strip() == str(source.get("before") or "").strip()
            and str(derived.get("after") or "").strip() == str(source.get("after") or "").strip()
        )
        if not same:
            continue
        dropped.add(derived.get("id"))
        labels[source.get("id")] = path_label(derived_path)
    return dropped, labels


def is_first_fill_row(op: Any, before: Any) -> bool:
    """변경 1건이 "최초 입력"(빈칸·폼 placeholder → 첫 값)인지 판정한다 (ORDER-DIFF-02).

    접수 직후 저장 한 번이면 빈 칸이 실제 값으로 한꺼번에 채워진다. 원장에는 남겨야 하지만
    (되돌리기 대상이고 감사 증거다) 화면 맨 앞에 깔리면 **진짜 수정이 묻힌다** — 운영 원장
    3,606행 중 1,737행(48%)이 이 종류였다(2026-08-21 실측). 화면은 이 값으로 접어 둔다.

    placeholder 목록은 도면 변경 피드와 같은 SSOT를 쓴다(사전을 두 벌 두지 않는다).

    :param op: 원장 ``op``(``set``·``add``·``clear``·``remove``). 품목 추가/삭제(``add``·
        ``remove``)는 최초 입력이 아니다 — 구성이 바뀐 사실 자체가 정보다.
    :param before: 원장 ``before_value``.
    :return: 최초 입력이면 ``True``.
    """
    from foms.services.notifications.drawing_order_change import is_unset_display_value

    if str(op or "").strip().lower() != "set":
        return False
    return is_unset_display_value(before)


def _format_money_text(path: str, text: str) -> str:
    """금액 경로의 값에 천단위 구분을 넣는다.

    ``100000`` 은 사람이 자릿수를 세야 읽힌다. 금액 경로 판정은 원장 differ 와 같은 SSOT
    (:data:`~foms.services.orders.structured_diff.NUMERIC_PATH_SUFFIXES`)를 쓴다.

    :param path: 구조화 경로.
    :param text: 이미 표시형으로 옮긴 값.
    :return: 금액이면 ``100,000``, 아니면 원문 그대로.
    """
    if not any(path.endswith(suffix) for suffix in NUMERIC_PATH_SUFFIXES):
        return text
    probe = text.replace(",", "").strip()
    if not probe or not probe.lstrip("-").isdigit():
        return text
    return f"{int(probe):,}"


def describe_change(change: Mapping[str, Any], *, label_override: str | None = None) -> str:
    """변경 1건을 ``라벨: 이전 → 이후`` 한 줄로 옮긴다 (ORDER-DIFF-00).

    **표시값이 같아지는 행**에는 :data:`~foms.services.orders.structured_diff.CONTENT_MODIFIED_MARK`
    를 붙인다. 원장에 행이 있다는 것은 절단 전 원문으로 이미 "바뀌었다"고 판정됐다는 뜻인데,
    값은 두 번 줄어든다 — 쓰기 시점 120자 절단(``structured_diff._clip``)과 읽기 시점
    :data:`_LONG_TEXT_LIMIT` 요약이다. 그래서 앞부분이 같은 긴 값은 화면에 ``A → A`` 로 나오고
    읽는 사람은 오타나 버그로 여긴다. 표식은 "여기서 더 보여줄 수 없을 뿐 값은 달라졌다"를
    말한다(본문은 주문 화면이 갖는다 — 요약은 은닉이 아니다).

    쓰기 시점 표식(요약 축의 ``3건(내용 수정)``)과 겹치지 않는다: 그때는 ``before``/``after``
    가 이미 다르므로 여기 조건에 걸리지 않는다. 반대로 그 표식이 읽기 요약에서 잘려 나간
    긴 값(지방 메모)은 여기서 다시 붙는다.

    :param change: :func:`foms.services.orders.structured_diff.diff_structured` 가 만든 dict
        (``path``·``before``·``after``·``op``, 품목이면 ``item``).
    :return: 사람이 읽는 한 줄. 품목 추가/삭제는 화살표 대신 ``추가``/``삭제`` 로 적는다.
    """
    path = str(change.get("path") or "")
    label = label_override or path_label(path)
    op = change.get("op")

    item_match = _ITEM_PATH_RE.match(path)
    if item_match and not item_match.group("field"):
        name = change.get("after") if op == "add" else change.get("before")
        verb = "추가" if op == "add" else "삭제"
        return f"{label} {verb}({name})" if name else f"{label} {verb}"

    value_field = _PATH_VALUE_FIELD.get(path)
    before_text = _format_money_text(path, format_value(value_field, change.get("before")))
    after_text = _format_money_text(path, format_value(value_field, change.get("after")))
    # 빈값 표기를 먼저 맞춘다 — 그래야 "빈값 → 빈값" 행(``(없음) → (지움)``)이 아래 비교에
    # 걸려 엉뚱하게 "내용 수정" 으로 읽히지 않는다.
    if before_text == _EMPTY_DISPLAY:
        before_text = _EMPTY_BEFORE_DISPLAY
    if before_text == after_text:
        after_text = f"{after_text}{CONTENT_MODIFIED_MARK}"
    return f"{label} {before_text} → {after_text}"


def summarize_changes(
    changes: Iterable[Mapping[str, Any]],
    *,
    total: int | None = None,
    head_count: int = 1,
) -> str:
    """변경 목록을 한 줄 요약으로 만든다 (ORDER-DIFF-00).

    목록 전체를 문장에 넣으면 감사 표의 한 행이 화면을 덮는다. 앞 몇 건만 적고 나머지는
    개수로 남긴다 — 전체 내역은 ``detail`` 원문에 그대로 있다(요약은 은닉이 아니다).

    :param changes: 변경 dict 목록.
    :param total: 상한 절단 전 실제 건수(없으면 목록 길이).
    :param head_count: 문장에 풀어 쓸 앞쪽 건수.
    :return: ``실측일 2026-08-12 → 2026-08-14 외 3건`` 형태. 변경이 없으면 빈 문자열.
    """
    listed = list(changes)
    if not listed:
        return ""
    real_total = total if total is not None else len(listed)
    head = " · ".join(describe_change(change) for change in listed[:head_count])
    rest = real_total - min(head_count, len(listed))
    return f"{head} 외 {rest}건" if rest > 0 else head


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
