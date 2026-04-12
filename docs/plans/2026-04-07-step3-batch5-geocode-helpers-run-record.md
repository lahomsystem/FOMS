# Step 3 Batch 5 Run Record
> 작성일: 2026-04-07
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-07-step3-batch4-measurement-manager-colors-run-record.md`

- 일시: 2026-04-07
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: `geocode_helpers`를 네 번째 실제 `foms/services` vertical slice로 이동하고, 이미 이관된 `foms/services/map_snapshot.py`의 legacy `services` 의존을 추가로 줄인다

## 1. 전체 판정
**Verdict: Step 3 Batch 5 executed, fourth real service slice moved under `foms/`**

이유:
- `foms/services/geocode_helpers.py`를 네 번째 canonical source of truth로 추가했다.
- legacy `services/geocode_helpers.py`는 공개 API만 재수출하는 thin shim으로 전환했다.
- 실제 호출부 `foms/services/map_snapshot.py`, `apps/api/erp_map.py`, `apps/api/erp_orders_structured.py`, `services/jobs/tasks.py`, `scripts/geocode_backfill.py`를 canonical import로 정리했다.
- 사전 감리에서 후보 3안을 다시 비교했고, 사후 감리에서 나온 테스트 공백까지 즉시 보강했다.

## 2. 후보 비교와 선정 근거
검토한 Batch 5 후보:
1. `services/geocode_helpers.py`
2. `services/order_display_utils.py`
3. `services/erp_utils.py`

선정 이유:
- 순수 “최소 변경 반경”만 보면 `erp_utils`가 더 작지만, 이번 Step 3 목표는 이미 `foms/services/*`로 옮긴 canonical 모듈이 legacy `services/*`에 덜 의존하도록 만드는 것이다.
- `geocode_helpers`는 현재 `foms/services/map_snapshot.py`가 직접 참조하는 legacy service이며, 이 배치로 canonical 내부의 legacy 의존 간선을 실제로 하나 더 제거할 수 있다.
- `order_display_utils`는 안전하지만 이번 구조 목표와 직접 연결되지 않는다.

## 3. 실제 변경 범위
### 3.1 canonical source
- `foms/services/geocode_helpers.py`

### 3.2 legacy compatibility shim
- `services/geocode_helpers.py`

### 3.3 canonical caller 전환
- `foms/services/map_snapshot.py`
- `apps/api/erp_map.py`
- `apps/api/erp_orders_structured.py`
- `services/jobs/tasks.py`
- `scripts/geocode_backfill.py`

### 3.4 테스트 추가/보강
- `tests/test_geocode_helpers.py`
- `tests/test_foms_namespace_imports.py`

## 4. 감리 결과 요약
### 4.1 사전 감리
- `geocode_helpers`, `order_display_utils`, `erp_utils` 3안을 비교했다.
- raw 안전성만 보면 `erp_utils`가 가장 작았지만, Step 3 구조 목표와의 정합성까지 포함하면 `geocode_helpers`가 더 적합하다고 판정했다.
- `geocode_helpers`는 순수 함수 모듈이고 `foms/services/map_snapshot.py`가 직접 의존하고 있어 Go 판정을 받았다.

### 4.2 사후 감리
- high 신규 결함은 없다고 판정됐다.
- medium 수준에서 “표시용 주소 경로와 지오코딩용 주소 경로가 아직 완전히 같은 함수로 통일되지는 않았다”는 구조 리스크가 확인됐지만, 이는 이번 batch의 import 이동 범위를 넘어서는 동작/표시 로직 정리이므로 residual risk로만 기록했다.
- low 수준에서 `test_geocode_helpers.py`의 엣지 케이스 공백이 지적됐고, 비문자/빈 입력, `address_full == '-'` 폴백, ERP Beta invalid site address 폴백 케이스를 추가해 보강했다.

## 5. 의도적으로 건드리지 않은 것
- `app.py`
- `run.py`
- `start.sh`
- `Procfile`
- `railway.toml`
- `Dockerfile`
- `alembic.ini`
- `migrations/env.py`
- `db.py`
- `models.py`
- `templates/`
- `static/`
- `services/order_display_utils.py`
- `services/erp_utils.py`
- `services/erp_shipment_settings.py`
- `services/erp_display.py`

## 6. 검증 결과
### 6.1 namespace smoke
- 실행: `python -c "import services.geocode_helpers as legacy; import foms.services.geocode_helpers as canonical; assert legacy.compute_address_hash is canonical.compute_address_hash; assert legacy.extract_address_from_structured_data is canonical.extract_address_from_structured_data; assert legacy.extract_address_from_order is canonical.extract_address_from_order; print('GEOCODE_HELPERS_NS_OK')"`
- 결과: `GEOCODE_HELPERS_NS_OK`

### 6.2 focused tests
- 실행: `python -m pytest tests/test_geocode_helpers.py tests/test_foms_namespace_imports.py tests/test_map_snapshot.py -q`
- 결과: `16 passed`

### 6.3 app import
- 실행: `python -c "import app; print('APP_OK')"`
- 결과: `APP_OK`

### 6.4 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 6.5 전체 테스트
- 실행: `python -m pytest -q`
- 결과: `192 passed, 3 warnings in 23.60s`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속

### 6.6 lint
- 실행: `ReadLints` (`services/geocode_helpers.py`, `foms/services/geocode_helpers.py`, 관련 호출부 5파일, 테스트 2파일)
- 결과: 신규 lint 없음

## 7. 해석
- Step 3는 이제 `map_snapshot`, `request_utils`, `measurement_manager_colors`, `geocode_helpers`까지 총 4개의 실제 source of truth를 `foms/services` 아래로 이동한 상태다.
- 이번 배치로 `foms/services/map_snapshot.py`가 `services.geocode_helpers`를 직접 참조하던 legacy 간선 하나를 제거했다.
- 이제 `map_snapshot`가 남긴 주요 legacy service 의존은 `erp_display`, `erp_shipment_settings` 축으로 더 좁아졌다.
- 별도 품질 배치로 분리하기로 한 `manager_filter` 이중 적용, `lat/lng` 안전 파싱, 긴 함수 분해는 이번 구조 배치와 섞지 않았다.

## 8. 다음 단계
1. 다섯 번째 vertical slice 후보 3안을 다시 비교해 추천안 확정
2. 별도 품질 배치로 `manager_filter` 이중 적용, `lat/lng` 안전 파싱, 긴 함수 분해 중 어디부터 감리할지 결정
3. `erp_utils`와 `order_display_utils`는 “안전도”는 높지만 구조 이득이 낮으므로, `map_snapshot` 남은 의존 축(`erp_display`, `erp_shipment_settings`)과 함께 재평가
