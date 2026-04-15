# W8-B0 — Readiness gate + authoritative bridge queue lock

| Field | Value |
|-------|-------|
| Batch | `W8-B0` |
| 실행일 | 2026-04-14 |
| 진입 branch | (초기) — **Branch A** 판정 |
| Baseline policy | **inherited-red baseline** + **fresh green** on focused gates |

## Predecessor evidence

| Source | Verdict |
|--------|---------|
| Wave 7 closeout (`docs/plans/2026-04-14-wave7-batch7-closeout-run-record.md`) | **accepted** |
| Wave 7 status register W7-B6 | **accepted** |
| `docs/plans/2026-04-14-wave8-pre-execution-gdm-handoff.md` | **accepted** |

Wave 7 equivalent evidence: closeout run records 존재; 별도 waiver 불필요.

## inherited-red baseline

- `python -m pytest tests --collect-only -q` → **ERROR** `tests/test_sqlite_startup_compat.py`: `ModuleNotFoundError: No module named 'safe_schema_migration'`.
- 549 tests collected before error. Wave 8 code batch 검증은 plan 초점 pytest subset + `APP_OK` / `verify_result`로 수행.

## Fresh green (gate subset)

- `python -c "import app; print('APP_OK')"` → **APP_OK**
- `python tools/harness/verify_result.py --json` → **success: true**

## Live bridge snapshot (pilot files)

### Service compat shim (4 files) — 존재 확인

| Path | Present |
|------|---------|
| `services/realtime_notifications.py` | yes |
| `services/file_utils.py` | yes |
| `foms/services/realtime_notifications.py` | yes |
| `foms/services/file_utils.py` | yes |

### Direct-import bridge (6 files) — 존재 확인

| Path | Present |
|------|---------|
| `apps/api/files.py` | yes |
| `apps/api/address.py` | yes |
| `apps/api/erp_measurement.py` | yes |
| `apps/erp_measurement_dashboard.py` | yes |
| `apps/erp_production_page.py` | yes |
| `apps/erp_completion_page.py` | yes |

### `foms/platform/blueprints.py` import sources (현재, excerpt)

- `from apps.erp_measurement_dashboard import erp_measurement_dashboard_bp`
- `from apps.erp_production_page import erp_production_page_bp`
- `from apps.erp_completion_page import erp_completion_page_bp`
- `from apps.api.files import files_bp`
- `from apps.api.address import address_bp`
- `from apps.api.erp_measurement import erp_measurement_bp`

## rg snapshot (non-doc `.py`, 요약)

- `services.realtime_notifications` / `foms.services.realtime_notifications`: 주로 `tests/contracts/runtime/foms_namespace_surface_tests.py`, shim 파일, 패키지 `__init__.py` 주석.
- `services.file_utils` / `foms.services.file_utils`: 동상.
- `apps.api.files` 등: `blueprints.py`, `apps/api/*` consumer, runtime tests 문자열.

## Branch 판정

- Predecessor **accepted**
- Service compat pilot **ready** (product는 이미 대부분 `foms.services.notifications.*` / `foms.services.files.file_utils`; 제거는 테스트+shim 정리)
- Direct-import pilot **ready** (canonical 모듈 존재, `blueprints` import line만 전환 예정)

→ **Branch A** (`W8-B0 → … → W8-B7` full mainline 시도)

## Direction Lock (10)

1. 순감: 본 batch는 문서만 — bridge count 변화 없음 (기준선 고정).
2. behavior: 코드 변경 없음.
3. canonical owner: 이미 존재 (Wave 3/4/6 증거).
4. shell collapse: mainline pilot에 미포함.
5. runtime string: 미터치.
6. `blueprints.py` registration order: 미터치 (본 batch).
7. sentinel: 본 batch 해당 없음.
8. defer why-not-now: N/A
9. DB/template/packaging: 미터치.
10. 다음 batch 전제: B1 taxonomy freeze 준비 완료.

## Next legal batch

`W8-B1`

## Verification commands (executed)

```text
python -c "import app; print('APP_OK')"
python tools/harness/verify_result.py --json
python -m pytest tests --collect-only -q  → inherited-red (safe_schema_migration)
```
