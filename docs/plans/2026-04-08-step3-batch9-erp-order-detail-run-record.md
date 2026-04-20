# Step 3 Batch 9 Run Record
> 작성일: 2026-04-08
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-08-step3-batch8-persistence-import-alignment-run-record.md`

- 일시: 2026-04-08 08:37:44
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: `business_calendar` 축을 건드리지 않은 채, root service 중 가장 안전한 다음 vertical slice로 `erp_order_detail`를 `foms/services` canonical source로 이동하고 실제 dashboard 호출부 3곳을 canonical import로 정렬한다
- 제외 축: 사용자 지시에 따라 `business_calendar` / `/calendar` 기능 축은 이번 배치에서 의도적으로 제외

## 1. 전체 판정
**Verdict: Step 3 Batch 9 executed, `erp_order_detail` moved under `foms/services` with thin legacy shim**

이유:
- `foms/services/erp_order_detail.py`를 일곱 번째 canonical service source of truth로 추가했다.
- legacy `services/erp_order_detail.py`는 공개 함수만 재수출하는 thin shim으로 전환했다.
- 실제 production caller 3곳(`apps/erp_dashboard.py`, `apps/erp_production_page.py`, `apps/erp_construction_page.py`)만 canonical import로 정리해 배치 표면을 최소화했다.
- 사후 감리에서 지적된 fallback payload shape 불일치와 테스트명 오해 가능성을 즉시 수정해 배치 내부에서 닫았다.

## 2. 후보 비교와 선정 근거
검토한 다음 배치 후보:
1. `apps/api/erp_map.py` 중심 API slice
2. `apps/*` dashboard/page의 `services.erp_display` caller slice
3. root `services/*` 소형 slice (`erp_order_detail`, `channel_quick_actions` 등)

선정 이유:
- `erp_map`/`erp_measurement` 축은 대형 API 파일이고 `erp_measurement`는 `business_calendar`를 직접 사용해 이번 제약과 리뷰 노이즈가 겹친다.
- dashboard/page 전면 정리는 파일 수가 많아 Batch 8에서 이미 과대 표면적으로 판정된 방향이다.
- root service 소형 slice 중에서도 `channel_quick_actions`는 DB/스토리지/WAM/권한/ERP 표시 규칙이 한 모듈에 묶여 있어 통합 영향이 컸다.
- `erp_order_detail`는 `foms.services.erp_display` 의존만 가지는 좁은 helper 모듈이고 caller도 3개 페이지 + 전용 테스트로 한정되어 있어, canonical + shim + 최소 caller churn 원칙에 가장 잘 맞았다.

## 3. 실제 변경 범위
### 3.1 canonical source
- `foms/services/erp_order_detail.py`
  - canonical module 신설
  - `_ensure_dict` import를 `foms.services.erp_display` 경로로 정렬
  - `__all__` 도입
  - 실제 동작에 맞게 docstring 정리

### 3.2 legacy compatibility shim
- `services/erp_order_detail.py`
  - 공개 함수(`build_order_detail_payload_map`, `attach_order_detail_payloads`)만 재수출하는 thin shim으로 전환

### 3.3 canonical caller 전환
- `apps/erp_dashboard.py`
- `apps/erp_production_page.py`
- `apps/erp_construction_page.py`
  - `from services.erp_order_detail ...` → `from foms.services.erp_order_detail ...`

### 3.4 테스트 추가/보강
- `tests/test_erp_order_detail_preload.py`
  - canonical import로 전환
  - 기존 테스트명을 실제 계약에 맞게 정리
  - fallback payload가 lazy-load shape(`attachments` 없음)를 유지하는지 추가 검증
- `tests/test_foms_namespace_imports.py`
  - legacy shim과 canonical module의 `__all__` / object identity를 검증하는 계약 테스트 추가

## 4. 감리 결과 요약
### 4.1 사전 감리
- `business_calendar` / `/calendar` 축은 이번 배치에서 제외하기로 명시했다.
- `erp_map`/`erp_measurement` API slice, dashboard/page caller slice, root service slice를 비교했고, 그중 `erp_order_detail`와 `channel_quick_actions`를 tie-break 대상으로 좁혔다.
- `erp_order_detail`는 의존성과 caller 범위가 가장 좁아 다음 vertical slice로 선정되었다.

### 4.2 사후 감리
- medium 지적 1: `tests/test_erp_order_detail_preload.py`의 첫 테스트명이 실제 검증 내용과 어긋난다는 점이 확인되었고, 즉시 이름을 정정했다.
- medium 지적 2: `attach_order_detail_payloads()` fallback payload에만 `attachments` 키가 존재하는 shape 불일치가 확인되었고, fallback에서 해당 키를 제거해 정상 경로와 계약을 통일했다.
- low 수준 residual risk로는 canonical `erp_order_detail`의 타입 힌트 미흡과, production/construction 대시보드 경로에 대한 별도 preload route smoke 테스트 부재가 남았다.

## 5. 의도적으로 건드리지 않은 것
- `services/business_calendar.py`
- `/calendar` 관련 기능/라우트
- `services/channel_quick_actions.py`
- `services/erp_policy.py`
- `services/erp_display.py`
- root `db.py`
- root `models.py`
- `apps/api/*`
- `templates/`
- `static/`
- `app.py`
- `run.py`

## 6. 검증 결과
### 6.1 caller 정리 확인
- 실행: `rg` (`apps`, `services` 범위)
- 패턴: `from services\.erp_order_detail import|import services\.erp_order_detail`
- 결과: `No matches found`

### 6.2 namespace smoke
- 실행: `python -c "import foms.services.erp_order_detail as namespaced; import services.erp_order_detail as legacy; print('ERP_ORDER_DETAIL_NS_OK' if legacy.attach_order_detail_payloads is namespaced.attach_order_detail_payloads else 'ERP_ORDER_DETAIL_NS_FAIL')"`
- 결과: `ERP_ORDER_DETAIL_NS_OK`

### 6.3 focused tests
- 실행: `pytest -q tests/test_erp_order_detail_preload.py tests/test_foms_namespace_imports.py`
- 결과: `12 passed`

### 6.4 app import
- 실행: `python -c "import app; print('APP_OK')"`
- 결과: `APP_OK`

### 6.5 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 6.6 전체 테스트
- 실행: `pytest -q`
- 결과: `208 passed, 3 warnings`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속

### 6.7 lint
- 실행: `ReadLints`
- 결과: 신규 lint 없음

## 7. 해석
- Step 3는 이제 `map_snapshot`, `request_utils`, `measurement_manager_colors`, `geocode_helpers`, `erp_shipment_settings`, `erp_display`, `erp_order_detail`까지 총 7개의 실제 source of truth를 `foms/services` 아래로 이동한 상태다.
- 이번 배치는 `apps/*`의 세 dashboard caller를 처음으로 직접 canonical `foms.services.erp_order_detail`로 정리한 root service slice라는 의미가 있다.
- `business_calendar` 축을 제외한다는 사용자 제약도 유지했으므로, 다음 구조 배치는 다시 root service 소형 slice를 이어가거나(`channel_quick_actions` 등), `erp_policy` staged 설계, 혹은 더 넓은 caller cleanup을 비교하는 방식으로 이어가는 것이 맞다.

## 8. 다음 단계
1. root service 다음 후보(`channel_quick_actions`, `erp_sync_columns`, `erp_product_items`)를 같은 방식으로 재비교
2. 또는 `services/erp_policy.py`를 `business_calendar` 제외 조건 하에 staged 설계만 별도 감리
3. 별도 품질 배치로 `manager_filter` 이중 적용, `lat/lng` 안전 파싱, `erp_shipment_settings` 예외 처리, 긴 함수 분해 우선순위 재평가
