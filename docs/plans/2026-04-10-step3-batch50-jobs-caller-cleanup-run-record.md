# Step 3 Batch 50 Run Record
> 작성일: 2026-04-10
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-10-step3-batch49-jobs-package-run-record.md`

- 일시: 2026-04-10
- 브랜치: `deploy` (작업 기준)
- 실행자: AI agent
- 목적: Batch 49에서 canonical source로 고정한 `foms.services.jobs`를 기준으로 app/API/script live caller import를 canonical path로 정리해 `services.jobs` legacy import를 shim/tests 범위로만 축소한다
- 제외 축: Redis enqueue 문자열 `services.jobs.tasks.*` 자체는 backlog 호환 때문에 유지하며, `business_calendar` 및 `/calendar` 축은 계속 migration scope 밖으로 둔다

## 1. 전체 판정
**Verdict: Step 3 Batch 50 executed — live jobs caller cleanup completed without changing queue contract**

이유:
- `apps/api/channel_integration.py`, `erp_measurement.py`, `erp_orders_structured.py`, `erp_shipment_settings.py`, `orders.py`, `erp_map.py`, `apps/order_pages.py`, `apps/order_edit.py`, `scripts/maintenance/geocode_backfill.py`의 live jobs caller import를 canonical `foms.services.jobs` 경로로 정리했다.
- `erp_measurement.py`와 `erp_map.py`의 sync fallback용 `geocode_order_address` local import도 canonical `foms.services.jobs.tasks`로 맞췄다.
- `scripts/maintenance/geocode_backfill.py`는 `import_module("foms.services.jobs.queue").get_rq_queue()`로 queue resolver를 canonical path에 맞췄다.
- `services.jobs.*` import 검색 결과는 tests/shim만 남아 구조적 cleanup 목표를 충족했다.

## 2. 변경 파일 (요약)
- Caller: `apps/api/channel_integration.py`, `apps/api/erp_measurement.py`, `apps/api/erp_orders_structured.py`, `apps/api/erp_shipment_settings.py`, `apps/api/orders.py`, `apps/api/erp_map.py`, `apps/order_pages.py`, `apps/order_edit.py`, `scripts/maintenance/geocode_backfill.py`
- 테스트: `tests/test_foms_namespace_imports.py`
- 문서: 본 run record, `docs/AI_STATUS.md`, `docs/ARCHIVE_INDEX.md`, `docs/context/COMPACT_CHECKPOINT.md`, `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`

## 3. 검증
- `python -m pytest tests/test_foms_namespace_imports.py tests/test_order_attachment_thumbnail.py tests/test_channel_integration_smoke.py tests/test_channel_webhooks.py tests/test_channel_push_messages.py` — 통과 (`147 passed`)
- `rg`로 live `services.jobs` import 검색 — tests/shim만 남음
- `python -c "… JOBS_CALLERS_NS_OK …"` — 통과
- `python -c "import app; print('APP_OK')"` — 통과
- `python tools/harness/verify_result.py --json` — 통과
- `ReadLints` — 신규 lint 없음

## 4. 잔여 리스크 / 후속 후보
- enqueue 문자열 `services.jobs.tasks.*`는 의도적 legacy 유지다. 완전 cutover를 원하면 queue drain + worker/web 동시 배포가 필요하다.
- `services.jobs` 축은 구조상 정리됐고, 다음 Step 3 후보는 다른 legacy caller cleanup 또는 거버넌스 SPEC의 대형 파일 inventory/품질 배치다.
- `business_calendar` 및 `/calendar` 축은 사용자 지시에 따라 계속 migration scope 밖이다.
