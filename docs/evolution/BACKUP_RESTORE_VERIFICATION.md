# 백업/복원 검증: 주문 건 + 주문 상태 완전 저장·복원

**목적**: GDM 더블체크 — 주문 데이터뿐 아니라 **주문의 상태**까지 백업에 포함되고 복원 시 동일하게 복원되는지 검증·기록.

---

## 1. 저장 범위 (백업에 포함되는 것)

### 1.1 방식

- **데이터베이스**: `pg_dump`로 **DB 전체** 덤프. 테이블/컬럼 선택 제외 없음.
- **파일**: `simple_backup_system.py`의 `source_files`에 정의된 시스템 파일 복사.

### 1.2 주문 테이블 `orders` — 상태 관련 컬럼

| 컬럼 | 설명 | 백업 포함 |
|------|------|-----------|
| `id` | 주문 PK | ✅ |
| `status` | 주문 단계 (RECEIVED → MEASURE → DRAWING → CONFIRM → PRODUCTION → CONSTRUCTION → CS → COMPLETED) | ✅ |
| `original_status` | 원본 상태 보관 | ✅ |
| `cabinet_status` | 수납장 상태 (RECEIVED/IN_PRODUCTION/SHIPPED) | ✅ |
| `structured_data` | JSONB: ERP 워크플로우, 체크리스트, 실측·도면·설치 등 **모든 구조화 상태** | ✅ |
| `structured_schema_version`, `structured_confidence`, `structured_updated_at` | 구조화 메타 | ✅ |
| 기타 | received_date, customer_name, scheduled_date, measurement_date, is_erp_beta 등 **전체 컬럼** | ✅ |

`pg_dump`는 스키마+데이터 전체를 덤프하므로 위 컬럼이 빠지지 않음.

### 1.3 관련 테이블 (주문 상태·이력)

| 테이블 | 역할 | 백업 포함 |
|--------|------|-----------|
| `order_events` | 단계 변경/일정 변경 등 이벤트 스트림 | ✅ |
| `order_tasks` | 팔로업/이슈 추적 | ✅ |
| `order_attachments` | 첨부 메타 (파일은 R2 등 스토리지) | ✅ |
| 기타 주문 FK 테이블 | 모두 DB 내 | ✅ |

---

## 2. 복원 방식

- **스크립트**: 각 백업 폴더의 `🔧_복구_스크립트.bat` (또는 동일 내용의 수동 명령).
- **명령**: `psql -U ... -h ... -d ... -f "database_backup_YYYYMMDD_HHMMSS.sql"`.
- **결과**: 덤프된 **전부**가 현재 DB에 덮어쓰기(또는 빈 DB에 적재). 따라서 **주문 건 + status/original_status/cabinet_status/structured_data** 등 상태 전부가 복원 시점과 동일하게 복원됨.

---

## 3. 더블체크 체크리스트

- [x] `orders.status` — pg_dump 대상 테이블에 포함됨.
- [x] `orders.original_status`, `orders.cabinet_status` — 동일.
- [x] `orders.structured_data` (JSONB) — 워크플로우·체크리스트 등 포함, pg_dump에 포함됨.
- [x] 복원 시 `psql -f`로 덤프 전체 적용 → 테이블·컬럼 누락 없음.
- [x] `simple_backup_system.py`에서 `pg_dump` 호출 시 테이블 제외 옵션 없음 (전체 덤프).

**결론**: 주문 건과 주문의 상태(컬럼 및 관련 테이블)는 **완전히 저장·복원**됨.

---

## 4. 참조

- 백업 로직: `simple_backup_system.py` — `backup_database()`, `execute_backup()`.
- 백업 API: `app.py` — `/api/simple_backup`, `/api/backup_status`, `_run_backup_job`.
- 주문 모델: `models.py` — `Order` (status, original_status, cabinet_status, structured_data).
- GDM 분석: `docs/evolution/GDM_BACKUP_ISSUE_ANALYSIS_2026-02-17.md`.

*문서 생성: 2026-02-17. GDM 백업/복원 검증 의무 반영.*
