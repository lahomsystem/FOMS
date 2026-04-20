# Step 3 Batch 13 Run Record
> 작성일: 2026-04-08
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-08-step3-batch12-erp-product-items-run-record.md`

- 일시: 2026-04-08 09:47:38
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: Batch 11에서 staged 상태로 남겨둔 `erp_sync_columns` caller cleanup을 마무리해 production caller 전부를 `foms.services.erp_sync_columns` canonical import로 통일한다
- 제외 축: 사용자 지시에 따라 `business_calendar` / `/calendar` 기능 축은 이번 배치에서도 제외

## 1. 전체 판정
**Verdict: Step 3 Batch 13 executed, staged `erp_sync_columns` caller cleanup completed without business logic changes**

이유:
- `foms/services/erp_sync_columns.py` 자체는 그대로 두고, production caller 11곳의 import만 canonical path로 정리했다.
- legacy `services/erp_sync_columns.py` thin shim은 유지해 shim 계약과 호환 경로를 보존했다.
- production Python 코드 기준 `from services.erp_sync_columns import sync_erp_flat_columns` 패턴은 제거됐고, legacy 참조는 thin shim 파일 자체와 namespace 계약 테스트만 남았다.
- `ERP_SYNC_COLUMNS_NS_OK`/focused tests/`APP_OK`/`verify_result.py --json`/전체 `pytest -q`를 재통과했다.

## 2. 후보 비교와 선정 근거
검토한 다음 배치 후보:
1. `erp_sync_columns` caller cleanup
2. `channel_event_payloads` 또는 유사 low-risk channel slice
3. `channel_quick_actions` / `erp_policy` 관련 staged 설계

선정 이유:
- `channel_quick_actions`는 DB/스토리지/WAM/권한과 `erp_display` 비공개 심볼 의존이 얽혀 있어 구조-only 배치로 보기 어려웠다.
- `erp_policy`는 `business_calendar` eager import와 광범위 caller 때문에 여전히 고위험 후보로 남았다.
- `erp_sync_columns`는 Batch 11에서 canonical source + thin shim 패턴이 이미 완성돼 있었고, 남은 작업이 import 경로 정리에 가까워 이번 구조-only 배치와 가장 잘 맞았다.
- dirty worktree 상태에서도 로직 변경 없이 caller import만 정리할 수 있다는 점이 결정적이었다.

## 3. 실제 변경 범위
### 3.1 production caller canonical import 정리
- `apps/api/orders.py`
- `apps/api/erp_measurement.py`
- `apps/api/erp_orders_as.py`
- `apps/api/erp_orders_structured.py`
- `apps/api/erp_orders_draftsman.py`
- `apps/api/erp_orders_production.py`
- `apps/api/erp_orders_construction.py`
- `apps/api/erp_orders_cs.py`
- `apps/api/quest.py`
- `apps/order_pages.py`
- `services/app_init.py`

각 파일에서:
- `from services.erp_sync_columns import sync_erp_flat_columns`
- → `from foms.services.erp_sync_columns import sync_erp_flat_columns`

### 3.2 유지한 것
- `foms/services/erp_sync_columns.py`
  - canonical source 유지, 구현 변경 없음
- `services/erp_sync_columns.py`
  - 공개 함수 `sync_erp_flat_columns`만 재수출하는 thin shim 유지
- `tests/test_foms_namespace_imports.py`
  - legacy shim과 canonical object identity 계약 검증용 import 유지

## 4. 감리 결과 요약
### 4.1 사전 감리
- `business_calendar` / `/calendar` 축은 이번 배치에서도 계속 제외하기로 유지했다.
- 읽기 전용 감리에서 `channel_quick_actions`는 구조-only 배치로 부적합, `erp_policy`는 여전히 고위험, `erp_sync_columns` caller cleanup은 medium risk지만 가장 통제 가능한 후보라는 결론이 나왔다.
- 이에 따라 이번 배치는 source of truth 추가 없이 staged cleanup 마감 배치로 결정했다.

### 4.2 사후 감리
- production caller 기준 legacy import가 사라졌고, cleanup 결과는 구조-only 배치로 유지된다는 판정을 받았다.
- 후감리에서는 low 수준 residual risk로 `foms/services/erp_sync_columns.py`의 타입 힌트 부족, `stage_updated_at` 파싱 실패 시 조용한 `pass`, `services/app_init.py`의 `print` logging이 재확인됐다.
- 위 세 항목은 이번 batch에서 새로 도입된 문제가 아니며, 구조-only 원칙 때문에 별도 품질 배치로 분리했다.

## 5. 의도적으로 건드리지 않은 것
- `services/business_calendar.py`
- `/calendar` 관련 기능/라우트
- `services/channel_quick_actions.py`
- `services/channel_event_payloads.py`
- `services/erp_policy.py`
- `foms/services/erp_sync_columns.py` 내부 구현
- `services/erp_sync_columns.py` thin shim
- root `db.py`
- root `models.py`
- `templates/`
- `static/`
- `app.py`
- `run.py`

## 6. 검증 결과
### 6.1 legacy import 제거 확인
- 실행: `rg`
- 패턴: `from services\.erp_sync_columns import sync_erp_flat_columns`
- 결과: production Python 코드 기준 match 없음
- 비고: legacy 참조는 `services/erp_sync_columns.py` thin shim과 `tests/test_foms_namespace_imports.py`만 유지

### 6.2 namespace smoke
- 실행: `python -c "import services.erp_sync_columns as legacy; import foms.services.erp_sync_columns as ns; assert legacy.sync_erp_flat_columns is ns.sync_erp_flat_columns; print('ERP_SYNC_COLUMNS_NS_OK')"`
- 결과: `ERP_SYNC_COLUMNS_NS_OK`

### 6.3 focused tests
- 실행: `pytest -q tests/test_erp_sync_columns.py tests/test_foms_namespace_imports.py`
- 결과: `15 passed`

### 6.4 app import
- 실행: `python -c "import app; print('APP_OK')"`
- 결과: `APP_OK`

### 6.5 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 6.6 전체 테스트
- 실행: `pytest -q`
- 결과: `224 passed, 3 warnings`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속

### 6.7 lint
- 실행: `ReadLints`
- 결과: 신규 lint 없음

## 7. 해석
- Step 3의 staged `erp_sync_columns` 작업은 이제 source of truth 이동(Batch 11) + production caller cleanup(Batch 13)까지 닫힌 상태다.
- canonical source 개수는 여전히 11개이며, 이번 배치는 새 slice 추가가 아니라 기존 staged batch의 후속 정리라는 점이 핵심이다.
- 다음 구조 배치는 다시 새로운 소형 slice(`channel_event_payloads` 등)를 비교할지, 아니면 구조 변경 대신 별도 품질 배치로 전환할지 판단하는 단계로 넘어갔다.

## 8. 다음 단계
1. 다음 low-risk 구조 후보(`channel_event_payloads` 등)와 품질 배치 후보를 다시 비교
2. `channel_quick_actions` / `erp_policy`는 고위험 후보로 계속 감리 보류
3. 별도 품질 배치로 `erp_sync_columns` 타입 힌트/parse fallback, `services/app_init.py` print logging, `erp_shipment_settings` 예외 처리, `orders.py`의 `ensure_path` 중복 등을 우선순위화
