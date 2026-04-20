# Step 5 Batch 66 Run Record
> 작성일: 2026-04-10
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-10-step5-batch65-template-js-move-run-record.md`

- 일시: 2026-04-10
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: Step 5 measurement vertical slice의 후감리 verdict를 정리하고 거버넌스 상태 문서를 closeout한다
- 제외 축: 사용자 지시대로 `business_calendar` / `/calendar` 축은 계속 범위 밖으로 유지

## 1. 전체 판정
**Verdict: Step 5 closeout completed, measurement vertical slice pilot is closed**

이유:
- Batch 61~65 실행 기록을 `docs/plans/2026-04-10-step5-batch61~65-*.md`로 남겼다.
- `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`, `docs/AI_STATUS.md`, `docs/ARCHIVE_INDEX.md`, `docs/context/COMPACT_CHECKPOINT.md`를 Step 5 완료 상태로 갱신했다.
- canonical source of truth는 `foms/web/measurement/dashboard.py`, `foms/api/measurement.py`, `foms/api/measurement_map.py`, `foms/services/measurement_dates.py`로 닫혔고, legacy `apps/*` / template / JS path는 shim/wrapper로 유지됐다.

## 2. 실제 변경 범위
- `docs/plans/2026-04-10-step5-batch61-contract-freeze-run-record.md`
- `docs/plans/2026-04-10-step5-batch62-helper-extraction-run-record.md`
- `docs/plans/2026-04-10-step5-batch63-canonical-modules-run-record.md`
- `docs/plans/2026-04-10-step5-batch64-map-delegation-run-record.md`
- `docs/plans/2026-04-10-step5-batch65-template-js-move-run-record.md`
- `docs/plans/2026-04-10-step5-batch66-closeout-run-record.md`
- `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
- `docs/AI_STATUS.md`
- `docs/ARCHIVE_INDEX.md`
- `docs/context/COMPACT_CHECKPOINT.md`

## 3. 사후감리 요약
### 3.1 코드 관점
- independent post-audit 결과 high 신규 결함 없음
- medium residual risk:
  - summary API / measurement map query / dashboard 본문의 주문 집합 규칙이 완전히 동일하지 않다는 지적이 있었으나, pre-migration legacy source 확인 결과 `apps/api/erp_measurement.py`와 `apps/api/erp_map.py`도 이미 `Order.active_filter()` 기반이었고 `apps/erp_measurement_dashboard.py`만 `Order.dashboard_active_filter(days=60)`를 사용했다. 즉 Step 5가 만든 회귀가 아니라 기존 계약 유지다.
- low 정리:
  - `foms/api/measurement.py`, `foms/services/map_snapshot.py` docstring을 실제 legacy contract에 맞게 정정해 “대시보드와 동일한 집합”이라는 잘못된 설명을 제거했다.
  - legacy JS shim에는 `document.currentScript` fallback + `console.warn`를 추가해 로더 실패가 완전히 조용히 묻히지 않도록 했다.

### 3.2 운영 관점 residual risk
- legacy JS shim은 호환성 때문에 계속 `document.write`를 사용한다. 현재 계약은 유지되지만, 향후 strict CSP / async loader / bundler 전환 단계에서는 별도 정리가 필요하다.
- summary panel과 지도/동선 화면의 주문 집합 차이는 Step 5 회귀는 아니지만, 장기적으로 measurement read-model contract를 통일할지 여부를 Step 6 이후 별도 inventory/ADR로 판단할 필요가 있다.

## 4. 최종 검증 결과
### 4.1 전체 테스트
- 실행:
  - `python -m pytest -q`
- 결과:
  - `431 passed, 3 warnings`
- 관찰 사항:
  - 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속 (`foms/services/channel_inbound.py`, `tests/test_channel_webhooks.py`)

### 4.2 app import smoke
- 실행:
  - `python -c "import app; print('APP_OK')"`
- 결과:
  - `APP_OK`

### 4.3 shared verification
- 실행:
  - `python tools/harness/verify_result.py --json`
- 결과:
  - `success: true`

### 4.4 focused Step 5 gate re-check
- 실행:
  - `python -m pytest tests/test_measurement_js_contract.py tests/test_measurement_slice_contract.py tests/test_map_view_manager_contract.py tests/test_erp_measurement_mobile_render.py -q`
- 결과:
  - `16 passed in 1.38s`

### 4.5 lint
- 실행:
  - `ReadLints`
- 결과:
  - 신규 lint 없음

## 5. 해석
- Step 5의 목표였던 “vertical slice 1개를 구조-only 방식으로 시범 이관”은 measurement slice 기준으로 완료됐다.
- `business_calendar` / `/calendar`은 사용자 지시대로 끝까지 범위 밖에 두었고, Step 5는 해당 축을 건드리지 않았다.
- Step 5 후 measurement 관련 source of truth는 `foms/` namespace 아래로 모였고, legacy path는 compatibility shim으로 역할이 명확해졌다.

## 6. 다음 단계
1. 거버넌스 자동 다음 단계는 Step 6(대형 파일 분해 필요성 inventory)다.
2. 우선 inventory 후보는 Spec에 적힌 `apps/api/orders.py`, `templates/wdcalculator/partials/wdcalculator_scripts.html`를 기준으로 시작한다.
3. `business_calendar` / `/calendar` 축은 사용자 별도 지시 전까지 계속 제외한다.
