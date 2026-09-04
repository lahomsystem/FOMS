"""Order workflow status labels, cabinet status maps, and bulk-action views."""

# Order status constants (Blueprint V3 기준: A→B→C→D→E→F→G→H)
STATUS = {
    # 메인 프로세스 단계
    'RECEIVED': '접수',           # A. 주문접수
    'MEASURE': '실측',            # C. 실측 (영업 방문 또는 고객 셀프)
    'DRAWING': '도면',            # D. 도면 작성
    'CONFIRM': '고객컨펌',        # E. 고객 컨펌
    'PRODUCTION': '생산',         # F. 생산
    'CONSTRUCTION': '시공',       # G. 시공
    'CS': 'CS',                   # H. CS 접수 및 처리 (신규)
    'COMPLETED': '완료',          # 최종 완료

    # AS 서브프로세스
    'AS': 'AS처리',              # CS 단계에서 AS 필요 시

    # 레거시 호환 (기존 시스템)
    'MEASURED': '실측완료',
    'REGIONAL_MEASURED': '지방실측',
    'SCHEDULED': '설치예정',
    'SHIPPED_PENDING': '상차예정',
    'AS_RECEIVED': 'AS접수',
    'AS_COMPLETED': 'AS완료',
    'ON_HOLD': '보류',
    'DELETED': '삭제됨'
}

# 자가실측·지방 대시보드(물류 콘솔) 드롭다운 SSOT.
# 메인 파이프라인(접수~CS)은 ERP 폼 전용 — 보드에 노출하지 않음.
LOGISTICS_BOARD_STATUS = {
    'MEASURED': '실측완료',
    'REGIONAL_MEASURED': '지방실측',
    'SCHEDULED': '설치예정',
    'SHIPPED_PENDING': '상차예정',
    'COMPLETED': '완료',
    'AS_RECEIVED': 'AS접수',
    'AS_COMPLETED': 'AS완료',
    'AS': 'AS처리',
    'ON_HOLD': '보류',
    'DELETED': '삭제됨',
}

LOGISTICS_BOARD_CODES = frozenset(LOGISTICS_BOARD_STATUS)

# 지방 대시보드(2026-08-07 개편)는 status 드롭다운을 쓰지 않는다 — 섹션=상태이며
# 행에는 읽기 전용 뱃지만 표기한다. 전이는 canonical 컨트롤(완료/AS완료 버튼)과
# 체크리스트 자동 승격이 담당한다. 그래서 REGIONAL_BOARD_STATUS 는 존재하지 않는다.

# 자가실측 대시보드 드롭다운 SSOT (2026-08-07 사용자 결정).
# 화면 프로세스(대기→설치예정→AS→완료)와 무관한 지방실측·상차예정 legacy 제거.
# 터미널 전이(완료)는 canonical 컨트롤(complete_order_control) 소관.
SELF_BOARD_STATUS = {
    'MEASURED': '실측완료',
    'SCHEDULED': '설치예정',
    'ON_HOLD': '보류',
}

# 수도권 대시보드 드롭다운 SSOT (2026-08-07 사용자 결정).
# 메인 파이프라인(접수~CS)은 ERP 폼 전용 원칙 준수 — 보드는 물류 중간 상태만.
METRO_BOARD_STATUS = {
    'MEASURED': '실측완료',
    'SCHEDULED': '설치예정',
    'SHIPPED_PENDING': '상차예정',
    'ON_HOLD': '보류',
}

# 물류 중간 상태: order.status만 바꾸고 workflow.stage는 보존(공정 오염 방지).
LOGISTICS_STATUS_PRESERVE_WORKFLOW_STAGE = frozenset(
    {
        'MEASURED',
        'REGIONAL_MEASURED',
        'SCHEDULED',
        'SHIPPED_PENDING',
        'ON_HOLD',
    }
)


# AS overlay 상태: order.status 만 바꾸고 workflow.stage 는 보존한다(STATE-AS-01).
#
# AS 축의 SSOT 는 ``structured_data['as_lifecycle']`` 이고 본공정 stage 는 직교한 축이다.
# 그런데 status 쓰기 경로 2곳(update_order_status·update_order_field)이 이 집합에 없다는
# 이유로 stage 를 AS_* 로 덮어 왔다 — 운영 실측(2026-09-04) ``STAGE_CHANGED{to:AS_*}``
# 61건(from 은 RECEIVED·MEASURE·CONSTRUCTION 등 깨끗한 본공정), stage 가 AS_* 인 미완료
# 주문 477건. AS 완료 전이는 stage 를 되돌리지 않으므로 한 번 덮이면 고착한다 —
# status=AS_COMPLETED 인데 stage=AS_RECEIVED 로 굳은 62건이 도면·생산·시공 큐에서
# 통째로 빠져 있었다.
#
# ``LOGISTICS_STATUS_PRESERVE_WORKFLOW_STAGE`` 를 늘리지 않고 별도 상수를 두는 이유:
# 그 상수는 ``state_axes_audit._is_normal_overlay_divergence`` 감사 분류에도 쓰여
# 값을 늘리면 불일치 집계가 함께 움직인다(두 관심사를 한 집합에 얹지 않는다).
AS_OVERLAY_PRESERVE_WORKFLOW_STAGE = frozenset({'AS_RECEIVED', 'AS_COMPLETED', 'AS'})


def is_logistics_board_status(code: object) -> bool:
    """물류 보드 상태 코드 여부."""
    return str(code or '').strip() in LOGISTICS_BOARD_CODES


def should_sync_workflow_stage_on_status(code: object) -> bool:
    """field_update status 변경 시 workflow.stage 동기화 여부."""
    text = str(code or '').strip()
    if not text:
        return False
    if text in LOGISTICS_STATUS_PRESERVE_WORKFLOW_STAGE:
        return False
    if text in AS_OVERLAY_PRESERVE_WORKFLOW_STAGE:
        return False
    return True

# 수납장 상태 매핑
CABINET_STATUS = {
    'RECEIVED': '접수',
    'IN_PRODUCTION': '제작중',
    'SHIPPED': '발송'
}

# 일괄 작업용 상태 목록 (삭제 제외)
BULK_ACTION_STATUS = {k: v for k, v in STATUS.items() if k != 'DELETED'}
