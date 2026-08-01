"""설치 작업자 마스터 + 주문 배정 registry (CREW-00, §5.2).

worker CRUD·display projection(:mod:`foms.services.crew.workers`) 과 배정 registry·
audit·backfill(:mod:`foms.services.crew.assignments`) 의 공개 API 를 re-export 한다.

경계(CREW-00): crew row 를 **authorization 에 쓰지 않는다**(순수 운영 마스터). route
실배선은 하류(SHIPMENT-REFERENCE-01) — 이 패키지는 스키마+CRUD+registry+picker/audit/
backfill 라이브러리만 제공한다.
"""
from foms.services.crew.workers import (
    CrewError,
    CrewValidationError,
    DuplicateExternalWorkerIdError,
    LinkedUserInvalidError,
    WorkerInUseError,
    WorkerNotFoundError,
    create_worker,
    deactivate_worker,
    get_worker,
    list_active_workers,
    update_worker,
)
from foms.services.crew.assignments import (
    MAX_INSTALLATION_WORKERS,
    AssignmentCapExceededError,
    AssignmentNotActiveError,
    FreeNameAudit,
    InactiveWorkerError,
    WorkerAlreadyAssignedError,
    active_worker_ids,
    apply_backfill,
    assign_worker,
    assignment_history,
    audit_free_names,
    release_worker,
    replace_workers,
)

__all__ = [
    # workers
    "CrewError", "CrewValidationError", "WorkerNotFoundError",
    "DuplicateExternalWorkerIdError", "LinkedUserInvalidError", "WorkerInUseError",
    "create_worker", "update_worker", "deactivate_worker",
    "list_active_workers", "get_worker",
    # assignments
    "MAX_INSTALLATION_WORKERS",
    "AssignmentCapExceededError", "WorkerAlreadyAssignedError",
    "AssignmentNotActiveError", "InactiveWorkerError",
    "assign_worker", "release_worker", "replace_workers",
    "active_worker_ids", "assignment_history",
    "FreeNameAudit", "audit_free_names", "apply_backfill",
]
