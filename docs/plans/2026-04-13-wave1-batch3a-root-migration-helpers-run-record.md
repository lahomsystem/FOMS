# Wave 1 Batch W1-B3A — Migration helper 패밀리 → `scripts/migrations/`
> batch ID: **W1-B3A**  
> risk axis: **filesystem / import 경로 (루트 shim + 스크립트 부트스트랩)**  
> 실행일: 2026-04-13

## 1. 요약
- 루트에 있던 마이그레이션·스키마 헬퍼 9개를 `scripts/migrations/`로 이동했다.
- `run.py`·`apps/admin.py` 수정 금지 계약을 유지하기 위해 **`safe_schema_migration`·`web_migration`은 루트에 importlib 기반 thin shim**만 남겼다 (모듈명 불변).
- `scripts/migrations/*.py`를 직접 실행할 때도 `db`/`models` 등을 찾을 수 있도록 각 파일 상단에 **저장소 루트를 `sys.path`에 넣는 부트스트랩**을 추가했다.

## 2. 이동한 파일
| 이전 (루트) | 이후 |
|-------------|------|
| `migrate_as_orders.py` | `scripts/migrations/migrate_as_orders.py` |
| `migrate_attachment_user.py` | `scripts/migrations/migrate_attachment_user.py` |
| `migrate_blueprint_field.py` | `scripts/migrations/migrate_blueprint_field.py` |
| `migrate_local_attachment_user.py` | `scripts/migrations/migrate_local_attachment_user.py` |
| `migrate_local_to_remote.py` | `scripts/migrations/migrate_local_to_remote.py` |
| `migrate_local_uploads_to_r2.py` | `scripts/migrations/migrate_local_uploads_to_r2.py` |
| `railway_migrate_team.py` | `scripts/migrations/railway_migrate_team.py` |
| `safe_schema_migration.py` (구현) | `scripts/migrations/safe_schema_migration.py` |
| `web_migration.py` (구현) | `scripts/migrations/web_migration.py` |

## 3. 루트에 남은 shim
- `safe_schema_migration.py` → `SafeSchemaMigration`, `run_safe_migration` 재노출
- `web_migration.py` → `run_web_migration` 재노출

## 4. 문서 갱신
- `MIGRATION_GUIDE_RAILWAY.md`: `railway run python scripts/migrations/safe_schema_migration.py`
- `MIGRATION_RAILWAY_R2.md`: `python scripts/migrations/migrate_local_uploads_to_r2.py` (dry-run / execute)
- `migrate_local_to_remote.py` 내부 안내 문구: 동일하게 새 경로 반영

## 5. 검증 (2026-04-13 실행 기록)
| 검사 | 결과 |
|------|------|
| APP_OK | 통과 |
| `python tools/harness/verify_result.py --json` | `success: true` |
| `pytest tests/test_sqlite_startup_compat.py` | 4 passed |
| 루트 shim | `from safe_schema_migration` / `from web_migration` 통과 |

## 6. Direction Lock
- 단일 risk axis: migration 파일 위치 + 호환 shim. `app.py`·`run.py`·`apps/` 본문 미수정.

## 7. Stop condition
- **미발동** (검증 통과 시).

## 8. 파일명 (계획서 §7.1 정합)
- 본 문서의 규범 파일명: `2026-04-13-wave1-batch3a-root-migration-helpers-run-record.md`  
- 동일 내용의 이전 비규범 파일명 `2026-04-13-wave1-batch3a-migrations-run-record.md` 가 있었다면 **삭제·대체**로 정합을 맞춘다.
