# Step 3 Batch 7 Run Record
> 작성일: 2026-04-07
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-07-step3-batch6-erp-shipment-settings-run-record.md`

- 일시: 2026-04-07
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: `erp_display`를 여섯 번째 실제 `foms/services` vertical slice로 이동하되, 호출부 전면 교체 대신 `foms/services/map_snapshot.py` 한 곳만 canonical import로 전환하는 staged 방식으로 `foms/services/*` 내부의 마지막 `services.*` 간선을 제거한다

## 1. 전체 판정
**Verdict: Step 3 Batch 7 executed, staged `erp_display` slice moved under `foms/`**

이유:
- `foms/services/erp_display.py`를 여섯 번째 canonical source of truth로 추가했다.
- legacy `services/erp_display.py`는 공개 함수만 재수출하는 thin shim으로 전환했다.
- production 호출부는 전면 교체하지 않고, `foms/services/map_snapshot.py`만 canonical import로 전환해 batch 리스크를 최소화했다.
- shim 계약 테스트와 포커스 헬퍼 테스트를 추가해 staged 이관의 안전성을 고정했다.

## 2. 후보 비교와 선정 근거
검토한 Batch 7 후보:
1. `services/erp_display.py`
2. `services/erp_utils.py`
3. `services/file_utils.py`
4. 대안 검토: `services/erp_template_filters.py`

선정 이유:
- `erp_utils`는 가장 작고 안전하지만 `foms/services/*` 내부의 남은 legacy `services.*` 간선을 줄이지 못한다.
- `file_utils`는 production import가 사실상 없어 구조 이득이 거의 없다.
- `erp_template_filters`는 Jinja 등록과 연계되어 소규모이지만 `foms/services/*` 간선 제거에는 기여하지 않는다.
- `erp_display`는 호출부가 넓어 한 번에 canonical import 정리까지 하면 위험하지만, `foms/services/map_snapshot.py`가 직접 참조하는 마지막 `services.*` 축이기도 하다. 따라서 이번 배치는 staged 방식(`canonical + shim + map_snapshot만 canonical import`)으로 진행하는 것이 가장 합리적이었다.

## 3. 실제 변경 범위
### 3.1 canonical source
- `foms/services/erp_display.py`

### 3.2 legacy compatibility shim
- `services/erp_display.py`

### 3.3 canonical caller 전환 (staged)
- `foms/services/map_snapshot.py`

### 3.4 테스트 추가/보강
- `tests/test_erp_display.py`
- `tests/test_foms_namespace_imports.py`

## 4. 감리 결과 요약
### 4.1 사전 감리
- `erp_display`, `erp_utils`, `file_utils`와 대안 `erp_template_filters`를 비교했다.
- 구조 목표(이미 이관된 `foms/services/*` 내부의 legacy `services.*` 간선 제거) 기준으로는 `erp_display`만 직접적인 진전을 만든다는 점이 확인됐다.
- 다만 호출부가 넓어 전면 canonical import 정리는 위험하므로, `foms/services/map_snapshot.py` 한 곳만 먼저 canonical로 돌리는 staged 접근이 추천되었다.

### 4.2 사후 감리
- `foms/services/*` 기준 `services.erp_display` import는 더 이상 남아 있지 않음을 확인했다.
- shim은 `__all__`과 명시적 재수출만 유지하며 `STAGE_NAME_TO_CODE` 같은 내부 상수는 legacy 경로로 새어 나오지 않음을 테스트로 고정했다.
- 사후 감리에서 `apply_erp_display_fields_to_orders()`의 docstring 누락이 지적됐고, 이는 즉시 보완했다.
- low 수준에서 canonical `erp_display`가 아직 `services.erp_policy`, `services.business_calendar`에 의존한다는 점과 `apply_erp_display_fields*` 행동 테스트가 얕다는 점이 residual risk로 남았다.

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
- `apps/*`, `services/*`의 기존 `from services.erp_display ...` 호출부 전반
- `services/erp_policy.py`
- `services/business_calendar.py`
- `services/erp_utils.py`
- `services/file_utils.py`
- `services/erp_template_filters.py`

## 6. 검증 결과
### 6.1 namespace smoke
- 실행: `python -c "import services.erp_display as legacy; import foms.services.erp_display as canonical; assert legacy.normalize_manager_name is canonical.normalize_manager_name; assert legacy.apply_erp_display_fields is canonical.apply_erp_display_fields; assert legacy._ensure_dict is canonical._ensure_dict; print('ERP_DISPLAY_NS_OK')"`
- 결과: `ERP_DISPLAY_NS_OK`

### 6.2 focused tests
- 실행: `python -m pytest tests/test_erp_display.py tests/test_foms_namespace_imports.py tests/test_map_snapshot.py -q`
- 결과: `13 passed`

### 6.3 app import
- 실행: `python -c "import app; print('APP_OK')"`
- 결과: `APP_OK`

### 6.4 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 6.5 전체 테스트
- 실행: `python -m pytest -q`
- 결과: `205 passed, 3 warnings in 32.25s`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속

### 6.6 lint
- 실행: `ReadLints` (`erp_display` canonical/shim, `foms/services/map_snapshot.py`, 테스트 2파일)
- 결과: 신규 lint 없음

## 7. 해석
- Step 3는 이제 `map_snapshot`, `request_utils`, `measurement_manager_colors`, `geocode_helpers`, `erp_shipment_settings`, `erp_display`까지 총 6개의 실제 source of truth를 `foms/services` 아래로 이동한 상태다.
- 이번 배치로 `foms/services/map_snapshot.py`가 `services.erp_display`를 직접 참조하던 마지막 `services.*` 간선을 제거했다.
- 현재 `foms/services/*`의 남은 주요 legacy 축은 `services.erp_policy`, `services.business_calendar`, 그리고 root `db`/`models` 계열이다.
- 다른 production 호출부들은 의도적으로 legacy shim 경로를 유지하고 있으므로, 다음 단계에서는 “전체 canonical import 정리”를 할지 “더 안쪽 의존 축 정리”를 할지 선택해야 한다.

## 8. 다음 단계
1. 다음 구조 배치를 `erp_display` 호출부 전면 canonical import 정리로 갈지, 아니면 `services.erp_policy`/`services.business_calendar`/root `models` 축으로 더 안쪽 의존 정리를 할지 비교
2. 별도 품질 배치로 `apply_erp_display_fields*` 행동 테스트 보강, `erp_shipment_settings` 예외 처리, `manager_filter` 이중 적용, `lat/lng` 안전 파싱 중 어디부터 감리할지 결정
3. `erp_utils`와 `file_utils`는 안전도는 높지만 구조 이득이 낮으므로 후순위 유지
