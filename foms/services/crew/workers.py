"""설치 작업자 마스터 CRUD + display projection (CREW-00, §5.2).

외부 설치 작업자(:class:`~models.InstallationWorker`)의 create/update/deactivate 와
crew picker display projection 을 제공한다. 경계(CREW-00):

* crew row 를 **어떤 authorization 판정에도 쓰지 않는다**(순수 운영 마스터).
* **free-name master write 금지** — 마스터는 이 명시 CRUD 를 통해서만 만든다.
* route/endpoint 실배선은 하류(SHIPMENT-REFERENCE-01) — 여기선 라이브러리만.

lifecycle 계약:

* ``external_worker_id`` 는 **활성 상태에서만** 유일하다(partial unique). 같은 external
  ID 로 활성 worker 를 두 번 만들면 :class:`DuplicateExternalWorkerIdError`(409).
* ``user_id`` 를 주면 실존·활성 User 임을 write 시점에 검증한다(:class:`LinkedUserInvalidError`).
* 활성 배정이 남아 있는 worker 는 비활성화할 수 없다(:class:`WorkerInUseError` 409).
"""
from __future__ import annotations

import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from foms.services.datetime_kst import now_utc_naive
from models import InstallationWorker, OrderInstallationAssignment, User

EXTERNAL_ID_MAX = 64
DISPLAY_NAME_MAX = 120
PHONE_MAX = 40


# --------------------------------------------------------------------------- #
# errors (호출자가 status_code 로 HTTP 매핑)
# --------------------------------------------------------------------------- #
class CrewError(RuntimeError):
    """CREW-00 계약 위반 베이스."""

    status_code = 409
    error_code = "CREW_ERROR"


class CrewValidationError(CrewError):
    """입력 검증 실패(빈 필드·길이 초과 등). 422."""

    status_code = 422
    error_code = "CREW_VALIDATION"


class WorkerNotFoundError(CrewError):
    """대상 worker 마스터 행이 없음. 404."""

    status_code = 404
    error_code = "WORKER_NOT_FOUND"

    def __init__(self, worker_id: int):
        super().__init__(f"installation worker {worker_id} not found.")
        self.worker_id = worker_id


class DuplicateExternalWorkerIdError(CrewError):
    """이미 활성 상태인 external_worker_id 로 새 활성 worker 를 만들려 함. 409."""

    status_code = 409
    error_code = "DUPLICATE_EXTERNAL_WORKER_ID"

    def __init__(self, external_worker_id: str):
        super().__init__(
            f"active installation worker with external id {external_worker_id!r} "
            "already exists."
        )
        self.external_worker_id = external_worker_id


class LinkedUserInvalidError(CrewValidationError):
    """linked user_id 가 존재하지 않거나 비활성. 422."""

    error_code = "LINKED_USER_INVALID"

    def __init__(self, user_id: int):
        super().__init__(f"linked user {user_id} does not exist or is inactive.")
        self.user_id = user_id


class WorkerInUseError(CrewError):
    """활성 배정이 남아 있는 worker 를 비활성화하려 함. 409."""

    status_code = 409
    error_code = "WORKER_IN_USE"

    def __init__(self, worker_id: int, active_count: int):
        super().__init__(
            f"installation worker {worker_id} has {active_count} active assignment(s); "
            "release them before deactivating."
        )
        self.worker_id = worker_id
        self.active_count = active_count


# --------------------------------------------------------------------------- #
# 내부 helper
# --------------------------------------------------------------------------- #
def _clean_required(value: Optional[str], *, field: str, max_len: int) -> str:
    """필수 문자열을 trim·비어있지 않음·상한 검증."""
    trimmed = (value or "").strip()
    if not trimmed:
        raise CrewValidationError(f"{field} is required.")
    if len(trimmed) > max_len:
        raise CrewValidationError(f"{field} exceeds {max_len} chars.")
    return trimmed


def _clean_optional(value: Optional[str], *, field: str, max_len: int) -> Optional[str]:
    """선택 문자열을 trim; 있을 때만 상한 검증(빈 값은 None)."""
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    if len(trimmed) > max_len:
        raise CrewValidationError(f"{field} exceeds {max_len} chars.")
    return trimmed


def _validate_linked_user(session: Session, user_id: Optional[int]) -> Optional[int]:
    """linked user_id 가 실존·활성 User 인지 검증(없으면 None).

    Args:
        session: DB 세션.
        user_id: link 대상 user_id (None 이면 검증 없이 None).

    Returns:
        검증된 user_id 또는 None.

    Raises:
        LinkedUserInvalidError: user 가 없거나 비활성.
    """
    if user_id is None:
        return None
    user = session.query(User).filter(User.id == user_id).one_or_none()
    if user is None or not user.is_active:
        raise LinkedUserInvalidError(user_id)
    return user_id


def _active_external_exists(
    session: Session, external_worker_id: str, *, exclude_id: Optional[int] = None,
) -> bool:
    """같은 external_worker_id 의 활성 worker 가 이미 있는지(자기 자신 제외)."""
    q = session.query(InstallationWorker.id).filter(
        InstallationWorker.external_worker_id == external_worker_id,
        InstallationWorker.is_active.is_(True),
    )
    if exclude_id is not None:
        q = q.filter(InstallationWorker.id != exclude_id)
    return session.query(q.exists()).scalar()


def _get_worker(session: Session, worker_id: int) -> InstallationWorker:
    """worker 행을 로드(없으면 404)."""
    worker = session.get(InstallationWorker, worker_id)
    if worker is None:
        raise WorkerNotFoundError(worker_id)
    return worker


# --------------------------------------------------------------------------- #
# CRUD
# --------------------------------------------------------------------------- #
def create_worker(
    session: Session, *, external_worker_id: str, display_name: str,
    phone: Optional[str] = None, user_id: Optional[int] = None,
    now: Optional[datetime.datetime] = None,
) -> InstallationWorker:
    """활성 설치 작업자 마스터 행을 만든다.

    Args:
        session: DB 세션.
        external_worker_id: 외부 작업자 식별자(활성 상태에서 유일).
        display_name: 표시명.
        phone: 연락처(선택).
        user_id: linked 내부 계정(선택 — 주면 실존·활성 검증).
        now: 생성 시각(테스트 주입용, 기본 now_utc_naive).

    Returns:
        flush 된 :class:`InstallationWorker`.

    Raises:
        CrewValidationError: external_worker_id/display_name 누락·초과.
        DuplicateExternalWorkerIdError: 이미 활성인 external_worker_id.
        LinkedUserInvalidError: user_id 가 없거나 비활성.
    """
    ts = now or now_utc_naive()
    ext = _clean_required(external_worker_id, field="external_worker_id", max_len=EXTERNAL_ID_MAX)
    name = _clean_required(display_name, field="display_name", max_len=DISPLAY_NAME_MAX)
    phone_clean = _clean_optional(phone, field="phone", max_len=PHONE_MAX)
    linked = _validate_linked_user(session, user_id)
    if _active_external_exists(session, ext):
        raise DuplicateExternalWorkerIdError(ext)
    worker = InstallationWorker(
        external_worker_id=ext, display_name=name, phone=phone_clean, user_id=linked,
        is_active=True, created_at=ts, updated_at=ts,
    )
    session.add(worker)
    session.flush()
    return worker


# sentinel: update 에서 "인자 미전달" 과 "명시적 None" 을 구분한다.
_UNSET = object()


def update_worker(
    session: Session, worker_id: int, *, display_name: Optional[str] = None,
    phone=_UNSET, user_id=_UNSET, now: Optional[datetime.datetime] = None,
) -> InstallationWorker:
    """설치 작업자 표시명/연락처/linked user 를 수정한다.

    ``phone``·``user_id`` 는 sentinel 로 "미전달"(변경 안 함)과 "명시적 None"(해제)을
    구분한다. ``display_name`` 은 None 이면 변경하지 않는다. ``external_worker_id`` 는
    lifecycle 식별자라 여기서 바꾸지 않는다(변경이 필요하면 deactivate 후 재등록).

    Raises:
        WorkerNotFoundError: worker 없음(404).
        CrewValidationError: display_name 빈 문자열·초과.
        LinkedUserInvalidError: user_id 가 없거나 비활성.
    """
    ts = now or now_utc_naive()
    worker = _get_worker(session, worker_id)
    if display_name is not None:
        worker.display_name = _clean_required(
            display_name, field="display_name", max_len=DISPLAY_NAME_MAX)
    if phone is not _UNSET:
        worker.phone = _clean_optional(phone, field="phone", max_len=PHONE_MAX)
    if user_id is not _UNSET:
        worker.user_id = _validate_linked_user(session, user_id)
    worker.updated_at = ts
    session.flush()
    return worker


def deactivate_worker(
    session: Session, worker_id: int, *, now: Optional[datetime.datetime] = None,
) -> InstallationWorker:
    """설치 작업자를 비활성화한다 — 활성 배정이 남아 있으면 409.

    Raises:
        WorkerNotFoundError: worker 없음(404).
        WorkerInUseError: 활성(status='ACTIVE') 배정이 남아 있음(409).
    """
    ts = now or now_utc_naive()
    worker = _get_worker(session, worker_id)
    if not worker.is_active:
        return worker  # 이미 비활성 — idempotent.
    active_count = (
        session.query(OrderInstallationAssignment.id)
        .filter(
            OrderInstallationAssignment.worker_id == worker_id,
            OrderInstallationAssignment.status == 'ACTIVE',
        )
        .count()
    )
    if active_count:
        raise WorkerInUseError(worker_id, active_count)
    worker.is_active = False
    worker.deactivated_at = ts
    worker.updated_at = ts
    session.flush()
    return worker


# --------------------------------------------------------------------------- #
# display projection (crew picker)
# --------------------------------------------------------------------------- #
def _project(worker: InstallationWorker) -> dict:
    """worker 를 picker/표시용 dict 로 투영(내부 상태 컬럼 노출 최소)."""
    return {
        "id": worker.id,
        "external_worker_id": worker.external_worker_id,
        "display_name": worker.display_name,
        "phone": worker.phone,
        "user_id": worker.user_id,
    }


def list_active_workers(session: Session) -> List[dict]:
    """crew picker: 활성 worker 를 display_name(→id) 정렬로 투영해 돌려준다.

    Returns:
        활성 worker projection dict 목록(display_name asc, id asc).
    """
    rows = (
        session.query(InstallationWorker)
        .filter(InstallationWorker.is_active.is_(True))
        .order_by(InstallationWorker.display_name.asc(), InstallationWorker.id.asc())
        .all()
    )
    return [_project(w) for w in rows]


def get_worker(session: Session, worker_id: int) -> dict:
    """worker 한 건을 projection dict 로(없으면 404)."""
    return _project(_get_worker(session, worker_id))


__all__ = [
    "EXTERNAL_ID_MAX", "DISPLAY_NAME_MAX", "PHONE_MAX",
    "CrewError", "CrewValidationError", "WorkerNotFoundError",
    "DuplicateExternalWorkerIdError", "LinkedUserInvalidError", "WorkerInUseError",
    "create_worker", "update_worker", "deactivate_worker",
    "list_active_workers", "get_worker",
]
