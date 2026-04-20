# Step 3 Batch 4 Run Record
> 작성일: 2026-04-07
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-07-step3-batch3-request-utils-run-record.md`

- 일시: 2026-04-07
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: `measurement_manager_colors`를 세 번째 실제 `foms/services` vertical slice로 이동하고, 이미 이관된 `foms/services/map_snapshot.py`의 legacy `services` 의존 한 축을 제거

## 1. 전체 판정
**Verdict: Step 3 Batch 4 executed, third real service slice moved under `foms/`**

이유:
- `foms/services/measurement_manager_colors.py`를 세 번째 canonical source of truth로 추가했다.
- legacy `services/measurement_manager_colors.py`는 공개 API만 재수출하는 thin shim으로 전환했다.
- 실제 호출부 `foms/services/map_snapshot.py`, `apps/erp_measurement_dashboard.py`, `tests/test_measurement_manager_colors.py`를 canonical import로 정리했다.
- 사전 감리에서 후보 3안을 비교했고, 사후 감리에서 나온 shim identity 테스트 갭까지 즉시 보강했다.

## 2. 후보 비교와 선정 근거
검토한 세 번째 vertical slice 후보:
1. `services/measurement_manager_colors.py`
2. `services/geocode_helpers.py`
3. `services/order_display_utils.py`

선정 이유:
- `measurement_manager_colors`는 호출 범위가 좁고(`map_snapshot`, 실측 대시보드, 전용 테스트), 외부/DB/부팅 의존성이 없으며 기존 테스트가 이미 존재한다.
- `geocode_helpers`도 순수 유틸이지만 호출 범위가 더 넓고 테스트 기반이 없어서, 이번 턴의 “안전 우선” 기준에서는 한 단계 뒤로 미루는 편이 낫다.
- `order_display_utils`는 안전하지만 이번 배치에서는 `foms/services/map_snapshot.py`의 legacy 의존 축을 줄이지 못한다.

## 3. 실제 변경 범위
### 3.1 canonical source
- `foms/services/measurement_manager_colors.py`

### 3.2 legacy compatibility shim
- `services/measurement_manager_colors.py`

### 3.3 canonical caller 전환
- `foms/services/map_snapshot.py`
- `apps/erp_measurement_dashboard.py`
- `tests/test_measurement_manager_colors.py`

### 3.4 테스트 보강
- `tests/test_foms_namespace_imports.py`

## 4. 감리 결과 요약
### 4.1 사전 감리
- `measurement_manager_colors`, `geocode_helpers`, `order_display_utils` 3안을 비교했다.
- `measurement_manager_colors`는 저위험이면서도 이미 이관된 `map_snapshot`의 legacy `services` 의존을 실제로 하나 줄일 수 있어 Go 판정을 받았다.

### 4.2 사후 감리
- high 신규 결함은 없다고 판정됐다.
- medium 수준에서 shim 계약 테스트가 공개 심볼 전체의 object identity를 고정하지 못한다는 지적이 있었고, 팔레트/기본색/정규화 함수/정렬 함수까지 identity 검증을 추가해 보강했다.
- low 수준으로는 기존 모듈 내부 `999` 매직 넘버가 남아 있다는 유지보수 지적이 있었지만, 이번 구조 배치와 섞지 않고 residual risk로만 기록했다.

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
- `services/geocode_helpers.py`
- `services/order_display_utils.py`
- `services/erp_shipment_settings.py`

## 6. 검증 결과
### 6.1 namespace smoke
- 실행: `python -c "import services.measurement_manager_colors as legacy; import foms.services.measurement_manager_colors as canonical; assert legacy.normalize_measurement_manager_key is canonical.normalize_measurement_manager_key; assert legacy.MEASUREMENT_MANAGER_PALETTE is canonical.MEASUREMENT_MANAGER_PALETTE; print('MEASUREMENT_COLORS_NS_OK')"`
- 결과: `MEASUREMENT_COLORS_NS_OK`

### 6.2 focused tests
- 실행: `python -m pytest tests/test_measurement_manager_colors.py tests/test_foms_namespace_imports.py -q`
- 결과: `7 passed`

### 6.3 app import
- 실행: `python -c "import app; print('APP_OK')"`
- 결과: `APP_OK`

### 6.4 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 6.5 전체 테스트
- 실행: `python -m pytest -q`
- 결과: `183 passed, 3 warnings in 21.20s`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속

### 6.6 lint
- 실행: `ReadLints` (`services/measurement_manager_colors.py`, `foms/services/measurement_manager_colors.py`, `foms/services/map_snapshot.py`, `apps/erp_measurement_dashboard.py`, 테스트 2파일)
- 결과: 신규 lint 없음

## 7. 해석
- Step 3는 이제 `map_snapshot`, `request_utils`, `measurement_manager_colors`까지 총 3개의 실제 source of truth를 `foms/services` 아래로 이동한 상태다.
- 이번 배치로 `foms/services/map_snapshot.py`가 `services.measurement_manager_colors`를 직접 참조하던 legacy 간선 하나를 제거했다.
- `geocode_helpers`는 여전히 유력한 다음 후보지만, 이번에는 “호출 범위가 좁고 테스트가 이미 있는 slice”를 택해 위험을 더 낮췄다.
- 별도 품질 배치로 분리하기로 한 `manager_filter` 이중 적용, `lat/lng` 안전 파싱, 긴 함수 분해는 이번 구조 배치와 섞지 않았다.

## 8. 다음 단계
1. 네 번째 vertical slice 후보 3안을 다시 비교해 추천안 확정
2. 별도 품질 배치로 `manager_filter` 이중 적용, `lat/lng` 안전 파싱, 긴 함수 분해 중 어디부터 감리할지 결정
3. `geocode_helpers`를 다음 구조 배치 후보 1순위로 재검토
