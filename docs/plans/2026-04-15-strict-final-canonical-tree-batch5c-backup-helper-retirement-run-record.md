# SFC-B5C — Backup/helper retirement

> Batch: `SFC-B5C`  
> 실행일: 2026-04-15  
> 성격: **code** (실행 계획 `§6.8`)  
> 선행: `SFC-B5B`  
> 권장 canonical home: `foms/services/admin/backup_service.py`

## 1. 목표

- 루트 `simple_backup_system.py` **제거** (importlib shim 포함).
- **런타임(API)** 은 `foms/services/admin/backup_service.SimpleBackupSystem` 만 참조; `scripts/ops/simple_backup_system.py`는 operator CLI 호환용 얇은 래퍼.
- `foms/api/backup.py`에서 **루트 모듈명 import 0**.

## 2. 수행 요약

| 항목 | 내용 |
|------|------|
| 정본 모듈 | `foms/services/admin/backup_service.py` (`SimpleBackupSystem`, CLI `main`) |
| 루트 제거 | `simple_backup_system.py` |
| `scripts/ops/simple_backup_system.py` | `foms.services.admin.backup_service` 재노출 + `__main__` 위임 |
| API | `foms/api/backup.py` → `from foms.services.admin.backup_service import SimpleBackupSystem` |
| 운영 배치 | `scripts/maintenance/🚨_간단_백업.bat` → `python -m foms.services.admin.backup_service` (저장소 루트 `cd` 유지) |

## 3. 검증 증거

| 검증 | 결과 |
|------|------|
| 제품 `.py` 트리 `simple_backup_system` 문자열 | **0건** (문서·백업 스냅샷 제외) |
| `python -c "import app; print('APP_OK')"` | `APP_OK` |
| `python tools/harness/verify_result.py --json` | `success: true` |
| `pytest tests` (full) | **574 passed** |

## 4. 다음 배치

- **`SFC-B6`** — Template namespace freeze (계획 §6.9) → **완료**: `2026-04-15-strict-final-canonical-tree-batch6-template-namespace-freeze-run-record.md`.
