# WR-S2 — Storage singleton shim retirement

> **batch ID:** WR-S2  
> **risk axis:** shim retirement / singleton-init-adjacent  
> **실행일:** 2026-04-15  
> **상위 문서:** `docs/plans/2026-04-14-post-wave9-endgame-master-sequence.md` Program 2, `docs/plans/2026-04-14-wave8-batch6-status-register-run-record.md` WR-S2

## 1. Scope lock

| 허용 | 금지 |
|------|------|
| `services/storage.py` retirement, runtime sentinel update, 본 run record | canonical `foms.services.storage` implementation 변경, upload/thumbnail behavior 변경, jobs/string contract 변경 |

## 2. Live truth before

- `foms/services/storage.py` already owned the real singleton implementation
- `services/storage.py` was only a compatibility shim
- repo search showed no live runtime caller still importing `services.storage`; only tests/backups/docs referenced the path

## 3. Implementation delta

### 3.1 Removal

- `services/storage.py` removed

### 3.2 Test delta

- `tests/contracts/runtime/foms_namespace_surface_tests.py`
  - old contract: legacy shim preserved canonical identity
  - new contract: legacy shim is retired (`find_spec("services.storage") is None`)
  - canonical `foms.services.storage` public surface remains asserted

## 4. Canonical target

- authoritative module: `foms/services/storage.py`
- retired shim: `services/storage.py`

## 5. Verification

### 5.1 Automated

- repo search for live `services.storage` imports -> only backup paths remain
- `python -c "import app; print('APP_OK')"` -> pass
- `python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py -k "wr_s2_legacy_storage_shim_retired or app_and_api_modules_use_canonical_storage_imports or jobs_tasks_uses_canonical_storage_lazy_import"` -> `3 passed`
- `python tools/harness/verify_result.py --json` -> `"success": true`

### 5.2 Lint

- `ReadLints` on edited file: no new WR-S2 diagnostic introduced
- residual workspace diagnostic remains unrelated (`erp_automation.build_auto_tasks`)

## 6. Guardrail check

- singleton owner를 바꾸지 않고 dead shim만 제거했다
- live app/API/worker import paths는 이미 canonical이라 추가 caller churn이 없었다
- one-family-per-batch 원칙 유지

## 7. Next legal batch

- `WR-H1` — high-risk cluster status/continuation lock
