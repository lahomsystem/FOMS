# Step 3 Batch 6 Run Record
> 작성일: 2026-04-07
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-07-step3-batch5-geocode-helpers-run-record.md`

- 일시: 2026-04-07
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: `erp_shipment_settings`를 다섯 번째 실제 `foms/services` vertical slice로 이동하고, 이미 이관된 `foms/services/map_snapshot.py`의 legacy `services` 의존을 한 단계 더 줄인다

## 1. 전체 판정
**Verdict: Step 3 Batch 6 executed, fifth real service slice moved under `foms/`**

이유:
- `foms/services/erp_shipment_settings.py`를 다섯 번째 canonical source of truth로 추가했다.
- legacy `services/erp_shipment_settings.py`는 공개 API만 재수출하는 thin shim으로 전환했다.
- 실제 호출부 `foms/services/map_snapshot.py`, `apps/api/erp_shipment_settings.py`, `apps/erp_shipment_page.py`, `apps/erp_measurement_dashboard.py`, `apps/erp_dashboard.py`, `apps/api/erp_measurement.py`, `apps/erp_production_page.py`, `apps/erp_drawing_workbench.py`를 canonical import로 정리했다.
- 사전 감리에서 후보 3안을 비교했고, 사후 감리에서 구조/테스트/잔여 리스크를 다시 점검했다.

## 2. 후보 비교와 선정 근거
검토한 Batch 6 후보:
1. `services/erp_shipment_settings.py`
2. `services/erp_utils.py`
3. `services/file_utils.py`

선정 이유:
- `erp_utils`는 가장 작고 안전하지만 `foms/services/map_snapshot.py`의 legacy `services/*` 의존을 줄이지 못한다.
- `file_utils`는 현재 production import가 사실상 없어서 구조 이득이 거의 없다.
- `erp_shipment_settings`는 DB/JSON 의존으로 이전 배치보다 조심스러운 후보지만, 이미 이관된 canonical 모듈인 `foms/services/map_snapshot.py`가 직접 참조하던 `services.erp_shipment_settings` 간선을 실제로 제거할 수 있는 유일한 후보였다.

## 3. 실제 변경 범위
### 3.1 canonical source
- `foms/services/erp_shipment_settings.py`

### 3.2 legacy compatibility shim
- `services/erp_shipment_settings.py`

### 3.3 canonical caller 전환
- `foms/services/map_snapshot.py`
- `apps/api/erp_shipment_settings.py`
- `apps/erp_shipment_page.py`
- `apps/erp_measurement_dashboard.py`
- `apps/erp_dashboard.py`
- `apps/api/erp_measurement.py`
- `apps/erp_production_page.py`
- `apps/erp_drawing_workbench.py`

### 3.4 테스트 추가/보강
- `tests/test_erp_shipment_settings.py`
- `tests/test_foms_namespace_imports.py`

## 4. 감리 결과 요약
### 4.1 사전 감리
- `erp_shipment_settings`, `erp_utils`, `file_utils` 3안을 비교했다.
- blast radius만 보면 `erp_utils`가 가장 작았지만, Step 3 구조 목표는 canonical 내부의 legacy `services/*` 간선을 줄이는 것이다.
- 그 기준에서 `erp_shipment_settings`만이 `foms/services/map_snapshot.py`의 남은 legacy service 의존 축을 직접 줄일 수 있어 Go 판정을 받았다.

### 4.2 사후 감리
- production Python 코드 기준 `from services.erp_shipment_settings ...` 사용처는 shim/test를 제외하고 모두 제거된 것으로 확인됐다.
- shim은 `__all__`과 명시적 재수출만 유지하며 `db_session` 같은 내부 심볼이 legacy 경로로 새어 나오지 않는다는 점을 테스트로 고정했다.
- medium 수준에서 canonical 모듈의 예외 처리(`print(...)`)가 기존 품질 부채로 재확인됐고, low 수준에서 DB load/save 경로의 단위 테스트 공백이 남아 있음을 기록했다.
- 그러나 이번 배치 범위 안에서 새로 유입된 기능 회귀나 과도한 shim 노출은 발견되지 않았다.

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
- `services/erp_display.py`
- `services/erp_utils.py`
- `services/file_utils.py`

## 6. 검증 결과
### 6.1 namespace smoke
- 실행: `python -c "import services.erp_shipment_settings as legacy; import foms.services.erp_shipment_settings as canonical; assert legacy.load_erp_shipment_settings is canonical.load_erp_shipment_settings; assert legacy.save_erp_shipment_settings is canonical.save_erp_shipment_settings; assert legacy.is_order_mine_for_user is canonical.is_order_mine_for_user; assert legacy.normalize_erp_shipment_workers is canonical.normalize_erp_shipment_workers; print('ERP_SHIPMENT_SETTINGS_NS_OK')"`
- 결과: `ERP_SHIPMENT_SETTINGS_NS_OK`

### 6.2 focused tests
- 실행: `python -m pytest tests/test_erp_shipment_settings.py tests/test_foms_namespace_imports.py tests/test_map_snapshot.py -q`
- 결과: `13 passed`

### 6.3 app import
- 실행: `python -c "import app; print('APP_OK')"`
- 결과: `APP_OK`

### 6.4 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 6.5 전체 테스트
- 실행: `python -m pytest -q`
- 결과: `197 passed, 3 warnings in 22.27s`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속

### 6.6 lint
- 실행: `ReadLints` (`erp_shipment_settings` canonical/shim, 호출부 8파일, 테스트 2파일)
- 결과: 신규 lint 없음

## 7. 해석
- Step 3는 이제 `map_snapshot`, `request_utils`, `measurement_manager_colors`, `geocode_helpers`, `erp_shipment_settings`까지 총 5개의 실제 source of truth를 `foms/services` 아래로 이동한 상태다.
- 이번 배치로 `foms/services/map_snapshot.py`가 `services.erp_shipment_settings`를 직접 참조하던 legacy 간선 하나를 제거했다.
- 이제 `map_snapshot`가 남긴 주요 legacy 축은 `services.erp_display`와 root `models` import로 더 좁아졌다.
- 별도 품질 배치로 분리하기로 한 `manager_filter` 이중 적용, `lat/lng` 안전 파싱, 긴 함수 분해는 이번 구조 배치와 섞지 않았다.

## 8. 다음 단계
1. 여섯 번째 vertical slice 후보 3안을 다시 비교해 추천안 확정
2. `map_snapshot`의 남은 legacy 축(`services.erp_display`, `models`) 중 어디를 다음 구조 배치로 볼지 판단
3. 별도 품질 배치로 `manager_filter` 이중 적용, `lat/lng` 안전 파싱, 긴 함수 분해, `erp_shipment_settings`의 `print` 예외 처리 중 어디부터 감리할지 결정
