# Step 3 Batch 3 Run Record
> 작성일: 2026-04-07
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-07-step3-batch2-map-snapshot-run-record.md`

- 일시: 2026-04-07
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: `request_utils`를 두 번째 실제 `foms/services` vertical slice로 이동하고 legacy 경로를 호환 shim으로 유지

## 1. 전체 판정
**Verdict: Step 3 Batch 3 executed, second real service slice moved under `foms/`**

이유:
- `foms/services/request_utils.py`를 canonical source of truth로 추가했다.
- legacy `services/request_utils.py`는 공개 API 하나만 재수출하는 thin shim으로 전환했다.
- 실제 호출부 `apps/order_pages.py`, `apps/order_edit.py`, `apps/order_trash.py`를 canonical import로 정리했다.
- 사전 감리와 사후 감리를 각각 수행했고, 사후 감리에서 나온 낮은 수준 테스트 현실성 이슈(`ImmutableMultiDict`)까지 보강했다.

## 2. 후보 비교와 선정 근거
검토한 두 번째 vertical slice 후보:
1. `services/request_utils.py`
2. `services/order_display_utils.py`
3. `services/measurement_manager_colors.py`

선정 이유:
- `request_utils`는 호출부가 좁고(주문 UI 3곳), 외부 의존성이 없으며, 부팅/DB/배포 리스크가 사실상 없다.
- `order_display_utils`는 안전하지만 표현 로직 범위가 더 넓다.
- `measurement_manager_colors`는 `map_snapshot` 축과 가깝지만 변경 의미가 더 넓어 “가장 안전한 다음 수순”에는 `request_utils`가 더 적합했다.

## 3. 실제 변경 범위
### 3.1 canonical source
- `foms/services/request_utils.py`

### 3.2 legacy compatibility shim
- `services/request_utils.py`

### 3.3 canonical caller 전환
- `apps/order_pages.py`
- `apps/order_edit.py`
- `apps/order_trash.py`

### 3.4 테스트 추가/보강
- `tests/test_request_utils.py`
- `tests/test_foms_namespace_imports.py`

## 4. 감리 결과 요약
### 4.1 사전 감리
- 호출자는 `order_pages`, `order_edit`, `order_trash` 3곳뿐이며, 모듈은 순수 유틸로 외부 import가 없어서 두 번째 slice로 Go 판정.
- 필수 보강으로 shim 계약 테스트와 행위 테스트 필요성이 제시됐다.

### 4.2 사후 감리
- high/medium 신규 결함은 없다고 판정됐다.
- 낮은 수준에서 테스트가 실제 `request.args` 타입을 쓰지 않는다는 지적이 있었고, `ImmutableMultiDict` 케이스를 추가해 보완했다.
- 나머지는 스타일/잔여 리스크 수준으로 분류했다.

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
- `services/measurement_manager_colors.py`
- `services/geocode_helpers.py`

## 6. 검증 결과
### 6.1 namespace smoke
- 실행: `python -c "from foms.services.request_utils import get_preserved_filter_args; from services.request_utils import get_preserved_filter_args as legacy_get_preserved_filter_args; print('REQUEST_NS_OK', get_preserved_filter_args is legacy_get_preserved_filter_args)"`
- 결과: `REQUEST_NS_OK True`

### 6.2 focused tests
- 실행: `python -m pytest tests/test_request_utils.py tests/test_foms_namespace_imports.py -q`
- 결과: `8 passed`

### 6.3 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 6.4 전체 테스트
- 실행: `python -m pytest -q`
- 결과: `182 passed, 3 warnings in 23.47s`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속

### 6.5 lint
- 실행: `ReadLints` (`services/request_utils.py`, `foms/services/request_utils.py`, 호출부 3파일, 테스트 2파일)
- 결과: 신규 lint 없음

## 7. 해석
- Step 3는 이제 `map_snapshot`에 이어 `request_utils`까지 실제 source of truth를 `foms/services` 아래로 옮긴 상태다.
- `request_utils`는 구조적으로 매우 단순한 slice였기 때문에, 다음 단계에서 조금 더 의미 있는 slice를 선택해도 현재 shim/canonical 패턴을 재사용할 수 있다.
- 별도 품질 배치로 분리하기로 한 `manager_filter` 이중 적용, `lat/lng` 안전 파싱, 긴 함수 분해는 이번 구조 배치와 섞지 않았다.

## 8. 다음 단계
1. 세 번째 vertical slice 후보 3안을 다시 비교해 추천안 확정
2. 별도 품질 배치로 `manager_filter` 이중 적용, `lat/lng` 안전 파싱, 긴 함수 분해 중 어디부터 감리할지 결정
3. `app.py` slim entrypoint 작업은 계속 별도 감리 단위로 유지
