# Step 3 Batch 10 Run Record
> 작성일: 2026-04-08
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-08-step3-batch9-erp-order-detail-run-record.md`

- 일시: 2026-04-08 09:01:16
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: `business_calendar` 축을 계속 제외한 채, 다음 구조 배치를 가장 낮은 blast radius의 utility slice(`db_url_resolver`, `erp_utils`)로 수행해 `foms/services` canonical source를 추가하고 실제 caller import를 최소 범위로 정렬한다
- 제외 축: 사용자 지시에 따라 `business_calendar` / `/calendar` 기능 축은 이번 배치에서도 제외

## 1. 전체 판정
**Verdict: Step 3 Batch 10 executed, `db_url_resolver` and `erp_utils` moved under `foms/services` with thin legacy shims**

이유:
- `foms/services/db_url_resolver.py`, `foms/services/erp_utils.py`를 각각 여덟 번째, 아홉 번째 canonical service source of truth로 추가했다.
- legacy `services/db_url_resolver.py`, `services/erp_utils.py`는 공개 API만 재수출하는 thin shim으로 전환했다.
- 실제 direct caller 3곳(`apps/api/erp_orders_as.py`, `scripts/backup_order_schedule_dates.py`, `scripts/restore_order_schedule_dates.py`)만 canonical import로 정리해 배치 표면을 최소화했다.
- 새 utility 행위 테스트와 shim 계약 테스트를 추가하고, `UTILITY_NS_OK`/`APP_OK`/`verify_result.py --json`/전체 `pytest -q`를 재통과했다.

## 2. 후보 비교와 선정 근거
검토한 다음 배치 후보:
1. root service slice `erp_sync_columns`
2. root service slice `erp_product_items`
3. 저위험 utility slice (`db_url_resolver`, `erp_utils`)

선정 이유:
- `erp_sync_columns`는 모듈 자체는 작지만 주문 쓰기 API 다수와 `services/app_init.py`, 백필 스크립트까지 연결돼 있어 조용한 데이터 불일치 리스크가 컸다.
- `erp_product_items`는 caller 수는 적지만 DB 조회, attachment URL 조합, JSONB 표시 계약이 함께 묶여 있어 “구조만 이동” 배치로 보기 어려웠다.
- `db_url_resolver`는 백업/복원 스크립트 2곳만, `erp_utils`는 `apps/api/erp_orders_as.py` 1곳만 직접 사용해 caller 폭이 가장 작았다.
- 두 모듈 모두 외부 API/권한/worker/runtime bootstrap 축과 직접 결합하지 않는 순수 utility 성격이라, 같은 risk axis의 소형 utility batch로 묶는 편이 가장 안전했다.

## 3. 실제 변경 범위
### 3.1 canonical source
- `foms/services/db_url_resolver.py`
  - canonical module 신설
  - `prepare_database_url_env()`를 공개 API로 고정하고 `__all__` 도입
  - 내부 scheme/public-url helper는 canonical module 내부 private helper로 유지
- `foms/services/erp_utils.py`
  - canonical module 신설
  - `ensure_path()`를 공개 API로 고정하고 `__all__` 도입

### 3.2 legacy compatibility shim
- `services/db_url_resolver.py`
  - 공개 함수 `prepare_database_url_env`만 재수출하는 thin shim으로 전환
- `services/erp_utils.py`
  - 공개 함수 `ensure_path`만 재수출하는 thin shim으로 전환

### 3.3 canonical caller 전환
- `apps/api/erp_orders_as.py`
  - `from services.erp_utils import ensure_path` → `from foms.services.erp_utils import ensure_path`
- `scripts/backup_order_schedule_dates.py`
- `scripts/restore_order_schedule_dates.py`
  - `from services.db_url_resolver import prepare_database_url_env` → `from foms.services.db_url_resolver import prepare_database_url_env`

### 3.4 테스트 추가/보강
- `tests/test_db_url_resolver.py`
  - 기존 `DATABASE_URL` 정규화
  - PG 개별 env 조합 시 URL 생성/quoting
  - public DB URL 우선 경로
  - env 후보가 없을 때 `None` 반환
- `tests/test_erp_utils.py`
  - nested dict 생성
  - 기존 nested dict 재사용
  - key가 없을 때 원본 dict 반환
- `tests/test_foms_namespace_imports.py`
  - `db_url_resolver`, `erp_utils` legacy shim과 canonical module의 `__all__`/object identity 계약 테스트 추가

## 4. 감리 결과 요약
### 4.1 사전 감리
- `business_calendar` / `/calendar` 축은 이번 배치에서 계속 제외하기로 유지했다.
- 서브에이전트 감리 결과가 `erp_sync_columns`와 utility slice 사이에서 갈렸으나, 직접 파일/호출자 비교 후 utility slice가 더 작은 blast radius를 가진다고 최종 판정했다.
- `erp_policy`는 여전히 `_DATA_ROOT` 및 광범위 caller 문제 때문에 구조-only 배치에서 제외했다.

### 4.2 사후 감리
- caller 정리 결과 `apps/`와 `scripts/` 범위에서 legacy import가 모두 제거된 것을 확인했다.
- 신규 canonical module 2개는 공개 API만 `__all__`로 노출하고, legacy shim에서 private helper가 새로 노출되지 않음을 shim 계약 테스트로 확인했다.
- low 수준 residual risk로는 `apps/api/orders.py` 내부의 로컬 `ensure_path` 중복이 남아 있지만, 이번 배치에서는 business logic/대형 파일 정리를 섞지 않기 위해 의도적으로 건드리지 않았다.

## 5. 의도적으로 건드리지 않은 것
- `services/business_calendar.py`
- `/calendar` 관련 기능/라우트
- `services/erp_sync_columns.py`
- `services/erp_product_items.py`
- `services/channel_quick_actions.py`
- `services/erp_policy.py`
- `apps/api/orders.py` 내부 로컬 `ensure_path`
- root `db.py`
- root `models.py`
- `templates/`
- `static/`
- `app.py`
- `run.py`

## 6. 검증 결과
### 6.1 caller 정리 확인
- 실행: `rg` (`apps`, `scripts` 범위)
- 패턴: `from services\.db_url_resolver import|import services\.db_url_resolver`, `from services\.erp_utils import|import services\.erp_utils`
- 결과: 모두 `No matches found`

### 6.2 namespace smoke
- 실행: `python -c "from services.db_url_resolver import prepare_database_url_env as legacy_prepare; from foms.services.db_url_resolver import prepare_database_url_env as namespaced_prepare; from services.erp_utils import ensure_path as legacy_ensure; from foms.services.erp_utils import ensure_path as namespaced_ensure; assert legacy_prepare is namespaced_prepare; assert legacy_ensure is namespaced_ensure; print('UTILITY_NS_OK')"`
- 결과: `UTILITY_NS_OK`

### 6.3 focused tests
- 실행: `pytest -q tests/test_db_url_resolver.py tests/test_erp_utils.py tests/test_foms_namespace_imports.py`
- 결과: `18 passed`

### 6.4 app import
- 실행: `python -c "import app; print('APP_OK')"`
- 결과: `APP_OK`

### 6.5 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 6.6 전체 테스트
- 실행: `pytest -q`
- 결과: `217 passed, 3 warnings`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속

### 6.7 lint
- 실행: `ReadLints`
- 결과: 신규 lint 없음

## 7. 해석
- Step 3는 이제 `map_snapshot`, `request_utils`, `measurement_manager_colors`, `geocode_helpers`, `erp_shipment_settings`, `erp_display`, `erp_order_detail`, `db_url_resolver`, `erp_utils`까지 총 9개의 실제 source of truth를 `foms/services` 아래로 이동한 상태다.
- 이번 배치는 그중에서도 production/runtime 중심 서비스가 아닌 보조 utility layer를 처음으로 `foms/services`에 편입한 구조-only 배치라는 의미가 있다.
- 다음 구조 배치는 다시 `erp_sync_columns` 같은 작지만 caller 폭이 넓은 root service slice를 갈지, `erp_product_items`처럼 caller 수는 적지만 도메인 결합이 있는 slice를 갈지, 혹은 별도 품질 배치를 먼저 할지 재비교하는 흐름이 적절하다.

## 8. 다음 단계
1. root service 다음 후보(`erp_sync_columns`, `erp_product_items`, `channel_quick_actions`)를 같은 방식으로 재비교
2. 또는 `services/erp_policy.py`를 `business_calendar` 제외 조건 하에 staged 설계만 별도 감리
3. 별도 품질 배치로 `manager_filter` 이중 적용, `lat/lng` 안전 파싱, `erp_shipment_settings` 예외 처리, `orders.py`의 `ensure_path` 중복 정리 우선순위 재평가
