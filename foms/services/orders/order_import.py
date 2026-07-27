"""admin Excel import 정본 서비스 (ORDER-IMPORT-01).

admin Excel import 를 **strict schema·full validate·all-or-none·file-hash receipt** 로
정본화한다. 검증 통과 행만 :func:`~foms.services.orders.order_create.create_order` 를 경유해
batch 생성하고(raw ``Order(...)`` constructor·row commit 금지) 한 tx 로 커밋한다. 원본·에러
리포트는 **server-derived private key**(``order_imports/...`` — public/local temp path 금지)로
:class:`~models.OrderImportArtifact` 에 24h 보관하며, 만료 정리는 SIDEFX worker 300s expiry
scan provider 가 수행한다(별도 cleanup scheduler 없음).

HTTP 배선(:mod:`foms.web.admin.excel_import`)은 이 서비스를 호출만 한다 — 권한(in-handler
``evaluate_policy`` Admin/Manager)·flash/redirect·error download 스트림은 route 몫이다.

경계·불변식:

* **strict**: 10MiB·1000-row 상한 초과는 :class:`OrderImportTooLarge` 로 거부한다.
* **full validate**: 전 행을 먼저 검증하고, 한 행이라도 실패하면 주문을 하나도 만들지 않는다
  (부분 진행 0). 실패 시 ``FAILED`` artifact(원본+에러 리포트)를 커밋하고
  :class:`OrderImportValidationError` 를 raise 한다(error download 로 원인 확인).
* **all-or-none**: 검증 통과 행을 한 tx 로 create_order batch 생성한다. 한 행이라도 실패하면
  전체 rollback(주문·artifact 모두 미커밋).
* **file-hash receipt**: 같은 파일(sha256) 재import 는 기존 receipt 를 그대로 돌려주고
  주문을 재생성하지 않는다(멱등).
* **scan ready precondition**: private artifact 는 24h 후 scan provider 가 정리하므로,
  worker readiness 를 확인한 뒤에만 새 artifact 를 만든다(정리 안 될 파일 누적 방지).
"""
from __future__ import annotations

import csv
import datetime
import hashlib
import io
from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd
from sqlalchemy.orm import Session

from foms.services.datetime_kst import get_today_kst, now_utc_naive
from foms.services.orders.order_create import create_order, resolve_order_owner
from foms.services.sidefx_worker import (
    ReadinessThresholds,
    collect_readiness_observations,
    evaluate_readiness,
)
from models import ORDER_IMPORT_ARTIFACT_TTL_HOURS, OrderImportArtifact

#: strict 상한 — 10 MiB 원본, 1000 데이터 행. 초과는 거부(부분 처리 없음).
MAX_IMPORT_BYTES = 10 * 1024 * 1024
MAX_IMPORT_ROWS = 1000
#: 필수 컬럼(schema)과 행별 필수 값(non-empty full validate 대상).
REQUIRED_COLUMNS = ('접수일', '고객명', '전화번호', '주소', '제품')
_REQUIRED_CELLS = ('고객명', '전화번호', '주소', '제품')
#: server-derived private key 네임스페이스(클라이언트 경로·public static·tmp 아님).
PRIVATE_KEY_PREFIX = 'order_imports'


class OrderImportError(RuntimeError):
    """ORDER-IMPORT-01 계약 위반 베이스(호출자가 status_code 로 HTTP 매핑)."""

    status_code = 400
    error_code = 'ORDER_IMPORT_ERROR'


class OrderImportTooLarge(OrderImportError):
    """strict 상한(10MiB / 1000-row) 초과. 413."""

    status_code = 413
    error_code = 'ORDER_IMPORT_TOO_LARGE'


class OrderImportSchemaError(OrderImportError):
    """필수 컬럼 누락·엑셀 파싱 불가. 400."""

    status_code = 400
    error_code = 'ORDER_IMPORT_SCHEMA'


class ScanNotReadyError(OrderImportError):
    """정리 worker 가 ready 가 아님 — private artifact 24h 정리 보장 불가. 503."""

    status_code = 503
    error_code = 'ORDER_IMPORT_SCAN_NOT_READY'


class OrderImportValidationError(OrderImportError):
    """full validate 실패 — 주문 미생성, FAILED artifact(error download) 발급. 422."""

    status_code = 422
    error_code = 'ORDER_IMPORT_VALIDATION'

    def __init__(self, message: str, receipt: 'ImportReceipt') -> None:
        super().__init__(message)
        self.receipt = receipt


@dataclass
class ImportReceipt:
    """import 결과 receipt(file-hash 멱등·resources[]·error download 키)."""

    artifact_id: int
    file_hash: str
    state: str
    row_count: int
    resource_order_ids: list[int] = field(default_factory=list)
    idempotent: bool = False
    source_object_key: Optional[str] = None
    error_object_key: Optional[str] = None
    row_errors: list[dict] = field(default_factory=list)


def compute_file_hash(file_bytes: bytes) -> str:
    """원본 파일의 sha256 hex 를 계산한다(재import 멱등 receipt 의 정본 키)."""
    return hashlib.sha256(file_bytes).hexdigest()


def _cell(row: dict, key: str) -> str:
    """행 dict 셀을 trim 문자열로 정규화한다(NaN/None → '')."""
    val = row.get(key)
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ''
    text = str(val).strip()
    return '' if text.lower() == 'nan' else text


def _parse_date(val: Any) -> Optional[str]:
    """엑셀 셀을 ``YYYY-MM-DD`` 로 정규화한다(파싱 불가면 None)."""
    dt = pd.to_datetime(val, errors='coerce')
    return dt.strftime('%Y-%m-%d') if pd.notna(dt) else None


def _parse_time(val: Any) -> Optional[str]:
    """엑셀 셀을 ``HH:MM`` 로 정규화한다(파싱 불가면 None)."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if isinstance(val, (datetime.time, datetime.datetime)):
        return val.strftime('%H:%M')
    dt = pd.to_datetime(val, errors='coerce')
    return dt.strftime('%H:%M') if pd.notna(dt) else None


def _parse_int(val: Any) -> int:
    """엑셀 셀을 정수로 정규화한다(콤마 허용, 파싱 불가면 0)."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return 0
    try:
        if isinstance(val, str):
            return int(float(val.replace(',', '') or '0'))
        return int(val)
    except (ValueError, TypeError):
        return 0


def _read_rows(file_bytes: bytes) -> list[dict]:
    """strict schema 로 Excel bytes 를 행 dict 목록으로 읽는다(10MiB·1000-row·필수 컬럼).

    Raises:
        OrderImportTooLarge: 바이트/행 상한 초과.
        OrderImportSchemaError: 파싱 불가·필수 컬럼 누락.
    """
    if len(file_bytes) > MAX_IMPORT_BYTES:
        raise OrderImportTooLarge(
            f"파일이 너무 큽니다(최대 {MAX_IMPORT_BYTES // (1024 * 1024)}MiB).")
    try:
        df = pd.read_excel(io.BytesIO(file_bytes))
    except OrderImportError:
        raise
    except Exception as exc:  # openpyxl/pandas 파싱 실패는 schema 오류로 명시 매핑
        raise OrderImportSchemaError(f"엑셀 파일을 읽을 수 없습니다: {exc}") from exc
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise OrderImportSchemaError(f"필수 컬럼 누락: {', '.join(missing)}")
    if len(df) > MAX_IMPORT_ROWS:
        raise OrderImportTooLarge(
            f"행이 너무 많습니다(최대 {MAX_IMPORT_ROWS}행, 입력 {len(df)}행).")
    return df.to_dict(orient='records')


def _normalize_row(row: dict, defaults: dict) -> dict[str, Any]:
    """검증 통과 행을 create_order 용 Order scalar kwargs 로 정규화한다."""
    fields: dict[str, Any] = {
        'customer_name': _cell(row, '고객명'),
        'phone': _cell(row, '전화번호'),
        'address': _cell(row, '주소'),
        'product': _cell(row, '제품'),
        'options': _cell(row, '옵션') or None,
        'notes': _cell(row, '비고') or None,
        'received_date': _parse_date(row.get('접수일')) or get_today_kst().strftime('%Y-%m-%d'),
        'received_time': _parse_time(row.get('접수시간')),
        'status': 'RECEIVED',
        'measurement_date': _parse_date(row.get('실측일')),
        'measurement_time': _parse_time(row.get('실측시간')),
        'completion_date': _parse_date(row.get('설치완료일')),
        'manager_name': _cell(row, '담당자') or None,
        'payment_amount': _parse_int(row.get('결제금액')),
        'is_regional': False,
    }
    for key in ('scheduled_date', 'as_received_date', 'as_completed_date'):
        if defaults.get(key):
            fields[key] = defaults[key]
    return fields


def _validate_and_normalize(rows: list[dict], defaults: dict) -> tuple[list[dict], list[dict]]:
    """전 행을 검증(full validate)해 (정규화 order_fields, row_errors) 를 반환한다.

    한 행이라도 error 가 있으면 caller 는 주문을 하나도 만들지 않는다(부분 진행 0).
    행 번호는 헤더(1행) 다음부터라 ``idx + 2`` 로 보고한다.
    """
    normalized: list[dict] = []
    errors: list[dict] = []
    for idx, row in enumerate(rows):
        missing = [c for c in _REQUIRED_CELLS if not _cell(row, c)]
        if missing:
            errors.append({'row': idx + 2, 'field': ', '.join(missing), 'reason': '필수 값 누락'})
            continue
        normalized.append(_normalize_row(row, defaults))
    return normalized, errors


def _error_report_bytes(errors: list[dict]) -> bytes:
    """row_errors 를 Excel 친화 CSV(UTF-8 BOM) 바이트로 만든다(error download 본문)."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['row', 'field', 'reason'])
    for err in errors:
        writer.writerow([err['row'], err['field'], err['reason']])
    return '﻿'.encode('utf-8') + buf.getvalue().encode('utf-8')


def _store_private(storage: Any, artifact_id: int, filename: str, data: bytes) -> str:
    """server-derived private key(``order_imports/{id}/...``) 로 바이트를 저장하고 key 반환.

    Raises:
        OrderImportError: 스토리지 저장 실패.
    """
    folder = f"{PRIVATE_KEY_PREFIX}/{artifact_id}"
    result = storage.upload_file(io.BytesIO(data), filename or 'import.xlsx', folder)
    if not result or not result.get('success') or not result.get('key'):
        detail = (result or {}).get('message', 'unknown')
        raise OrderImportError(f"아티팩트 저장 실패: {detail}")
    return result['key']


def _require_scan_ready(session: Session, thresholds: Optional[ReadinessThresholds]) -> None:
    """SIDEFX worker readiness 를 확인한다(정리 보장 없는 private artifact 생성 차단).

    Raises:
        ScanNotReadyError: worker heartbeat 부재/stale 등 not-ready.
    """
    observations = collect_readiness_observations(session)
    report = evaluate_readiness(observations, thresholds or ReadinessThresholds())
    if not report.ready:
        raise ScanNotReadyError(
            "정리 워커가 준비되지 않아 import 를 진행할 수 없습니다(잠시 후 다시 시도).")


def _receipt(art: OrderImportArtifact, *, idempotent: bool = False,
             resource_order_ids: Optional[list[int]] = None,
             row_errors: Optional[list[dict]] = None) -> ImportReceipt:
    """OrderImportArtifact 행에서 ImportReceipt 를 만든다."""
    return ImportReceipt(
        artifact_id=art.id,
        file_hash=art.file_hash,
        state=art.state,
        row_count=art.row_count or 0,
        resource_order_ids=(resource_order_ids if resource_order_ids is not None
                            else list(art.resource_order_ids or [])),
        idempotent=idempotent,
        source_object_key=art.source_object_key,
        error_object_key=art.error_object_key,
        row_errors=row_errors or [],
    )


def find_existing_receipt(session: Session, file_hash: str) -> Optional[ImportReceipt]:
    """만료 전(state<>EXPIRED) 같은 hash 의 기존 receipt 를 반환한다(재import 멱등)."""
    art = (
        session.query(OrderImportArtifact)
        .filter(OrderImportArtifact.file_hash == file_hash,
                OrderImportArtifact.state != 'EXPIRED')
        .order_by(OrderImportArtifact.id.desc())
        .first()
    )
    return None if art is None else _receipt(art, idempotent=True)


def _persist_failed(session: Session, storage: Any, *, file_hash: str, filename: str,
                    file_bytes: bytes, rows: list[dict], errors: list[dict],
                    actor_id: int, now: datetime.datetime,
                    expires_at: datetime.datetime) -> ImportReceipt:
    """FAILED artifact(원본+에러 리포트)를 커밋하고 OrderImportValidationError 를 raise 한다."""
    art = OrderImportArtifact(
        uploaded_by=actor_id, file_hash=file_hash, filename=filename,
        row_count=len(rows), state='FAILED', created_at=now, expires_at=expires_at)
    session.add(art)
    session.flush()  # id 확보(private key 네임스페이스)
    art.source_object_key = _store_private(storage, art.id, filename, file_bytes)
    art.error_object_key = _store_private(
        storage, art.id, 'import_errors.csv', _error_report_bytes(errors))
    session.commit()
    raise OrderImportValidationError(
        "검증 실패로 주문이 생성되지 않았습니다(에러 리포트를 확인하세요).",
        _receipt(art, row_errors=errors))


def _persist_completed(session: Session, storage: Any, *, file_hash: str, filename: str,
                       file_bytes: bytes, normalized: list[dict], actor: Any,
                       owner_user_id: Optional[int], actor_id: int,
                       now: datetime.datetime,
                       expires_at: datetime.datetime) -> ImportReceipt:
    """검증 통과 행을 create_order 경유 batch 생성하고 원본 artifact 와 한 tx 로 커밋한다."""
    owner_id = resolve_order_owner(
        session, actor=actor, requested_owner_user_id=owner_user_id)
    art = OrderImportArtifact(
        uploaded_by=actor_id, file_hash=file_hash, filename=filename,
        row_count=len(normalized), state='COMPLETED', created_at=now, expires_at=expires_at)
    session.add(art)
    session.flush()
    order_ids: list[int] = []
    for fields in normalized:
        order = create_order(
            session, actor_user_id=actor_id, owner_user_id=owner_id,
            order_fields=fields, is_erp_order=False, now=now)
        order_ids.append(order.id)
    art.source_object_key = _store_private(storage, art.id, filename, file_bytes)
    art.resource_order_ids = order_ids
    session.commit()
    return _receipt(art, resource_order_ids=order_ids)


def import_orders(session: Session, *, actor: Any, owner_user_id: Optional[int],
                  file_bytes: bytes, filename: str, storage: Any,
                  form_defaults: Optional[dict] = None,
                  now: Optional[datetime.datetime] = None,
                  check_readiness: bool = True,
                  readiness_thresholds: Optional[ReadinessThresholds] = None) -> ImportReceipt:
    """admin Excel import 를 strict·full-validate·all-or-none·file-hash 멱등으로 수행한다.

    Args:
        session: business tx 세션(이 함수가 commit/rollback 소유).
        actor: import 를 실행하는 사용자(``id``/``role``/``team``; owner 정책 판정).
        owner_user_id: Admin/Manager 가 지정한 SALES owner user id(explicit owner).
        file_bytes: 업로드 원본 바이트(sha256 receipt·10MiB 상한 판정).
        filename: 원본 파일명(receipt display; 경로로 쓰지 않음).
        storage: private 저장소(``upload_file(file_obj, filename, folder)`` 계약).
        form_defaults: 전 행 공통 폼 값(scheduled_date/as_received_date/as_completed_date).
        now: 테스트용 시각 주입(기본 now_utc_naive()).
        check_readiness: True 면 새 artifact 생성 전 worker readiness 를 요구.
        readiness_thresholds: readiness 임계(기본 ReadinessThresholds()).

    Returns:
        성공 시 COMPLETED :class:`ImportReceipt`(resources[] 포함), 재import 면 idempotent receipt.

    Raises:
        OrderImportTooLarge / OrderImportSchemaError: strict 상한/스키마 위반.
        ScanNotReadyError: worker not-ready.
        OrderImportValidationError: full validate 실패(FAILED artifact 커밋 후 raise).
        OwnerPolicyError: owner 정책 위반(create_order 계약).
    """
    now = now or now_utc_naive()
    defaults = form_defaults or {}
    file_hash = compute_file_hash(file_bytes)

    existing = find_existing_receipt(session, file_hash)
    if existing is not None:
        return existing

    rows = _read_rows(file_bytes)
    normalized, errors = _validate_and_normalize(rows, defaults)

    if check_readiness:
        _require_scan_ready(session, readiness_thresholds)

    expires_at = now + datetime.timedelta(hours=ORDER_IMPORT_ARTIFACT_TTL_HOURS)
    actor_id = int(getattr(actor, 'id'))

    if errors:
        return _persist_failed(
            session, storage, file_hash=file_hash, filename=filename,
            file_bytes=file_bytes, rows=rows, errors=errors,
            actor_id=actor_id, now=now, expires_at=expires_at)
    try:
        return _persist_completed(
            session, storage, file_hash=file_hash, filename=filename,
            file_bytes=file_bytes, normalized=normalized, actor=actor,
            owner_user_id=owner_user_id, actor_id=actor_id, now=now,
            expires_at=expires_at)
    except Exception:
        session.rollback()  # all-or-none: 한 행 실패=주문·artifact 전체 미커밋
        raise


__all__ = [
    'MAX_IMPORT_BYTES',
    'MAX_IMPORT_ROWS',
    'REQUIRED_COLUMNS',
    'PRIVATE_KEY_PREFIX',
    'OrderImportError',
    'OrderImportTooLarge',
    'OrderImportSchemaError',
    'ScanNotReadyError',
    'OrderImportValidationError',
    'ImportReceipt',
    'compute_file_hash',
    'find_existing_receipt',
    'import_orders',
]
