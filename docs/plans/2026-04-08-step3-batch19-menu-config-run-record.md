# Step 3 Batch 19 Run Record
> 작성일: 2026-04-08
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-08-step3-batch18-order-geocode-run-record.md`

- 일시: 2026-04-08 13:37:45
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: `menu_config`를 열일곱 번째 실제 `foms/services` source of truth로 이동하고 메뉴 주입/관리자 저장 caller 2곳을 canonical import로 정리한다
- 제외 축: 사용자 지시에 따라 `business_calendar` / `/calendar` 기능 축은 이번 배치에서도 제외

## 1. 전체 판정
**Verdict: Step 3 Batch 19 executed, `menu_config` canonical migration completed without intended menu behavior changes**

이유:
- `foms/services/menu_config.py`를 새 canonical source로 추가하고, 기존 `services/menu_config.py`는 공개 helper 2개만 재수출하는 thin shim으로 전환했다.
- production caller 2곳(`services/context_processors.py`, `apps/admin.py`)을 canonical import로 정리했고, legacy 경로는 thin shim과 namespace 계약 테스트만 남겼다.
- 전역 cache를 가진 모듈이므로 `tests/test_menu_config.py`를 추가해 기본 메뉴 fallback, cache invalidation reload, 시공팀 메뉴 제한, 일반 팀 메뉴 유지 계약을 고정했다.
- 후감리에서 지적된 테스트 전역 상태 복구 누락과 무음 예외 삼킴을 같은 배치 안에서 보강해 fixture 복구와 warning 로그 폴백까지 반영했다.
- `MENU_CONFIG_NS_OK`/`APP_OK`/`verify_result.py --json`/focused `pytest`/전체 `pytest`를 재통과했다.

## 2. 후보 비교와 선정 근거
검토한 다음 배치 후보:
1. `menu_config`
2. `order_storage_cleanup`
3. `channel_wam_view_models`

선정 이유:
- `menu_config`는 전역 메뉴 주입에 닿아 blast radius는 넓지만, DB/Auth/부트스트랩 코어를 직접 건드리지 않고 caller도 2곳이라 구조-only 배치로 통제 가능했다.
- `order_storage_cleanup`는 caller 수는 더 적어도 영구 삭제·스토리지 정합에 연결되어 회귀 비용이 더 컸다.
- `channel_wam_view_models`는 순수 helper에 가깝지만 channel/WAM 축으로 넘어가므로 이번 ERP/UI 중심 Step 3 흐름에서는 한 턴 뒤 후보로 두는 편이 자연스러웠다.

## 3. 실제 변경 범위
### 3.1 canonical source 추가
- `foms/services/menu_config.py`
  - 기존 메뉴 로딩/캐시 무효화 구현 전체를 이관
  - 공개 API `__all__` 명시:
    - `load_menu_config`
    - `invalidate_menu_config_cache`

### 3.2 legacy shim 전환
- `services/menu_config.py`
  - 위 2개 공개 helper만 재수출하는 thin shim으로 전환

### 3.3 caller canonical import 정리
- `services/context_processors.py`
- `apps/admin.py`

각 파일에서:
- `from services.menu_config import ...`
- → `from foms.services.menu_config import ...`

### 3.4 테스트 보강
- `tests/test_foms_namespace_imports.py`
  - `legacy_menu_config` / `namespaced_menu_config` import 추가
  - `__all__` 일치와 함수 객체 동일성(`is`) 검증 테스트 추가
- `tests/test_menu_config.py`
  - 파일이 없을 때 default 메뉴 반환
  - cache invalidation 후 JSON 재로딩
  - invalid JSON warning 로그 + default fallback
  - 시공팀(`CONSTRUCTION`) menu override
  - 일반 팀 menu 유지
  - autouse fixture로 `_MENU_CONFIG_PATH` / cache / mtime 원복

### 3.5 후감리 반영 수정
- `foms/services/menu_config.py`
  - `load_menu_config() -> dict[str, Any]`, `invalidate_menu_config_cache() -> None`, `_default_menu_config() -> dict[str, Any]` 타입 힌트 추가
  - `except Exception: pass`를 `except (OSError, json.JSONDecodeError)` + `logger.warning(...)`으로 교체해 fail-open이지만 묵시적 무시가 남지 않도록 정리

## 4. 감리 결과 요약
### 4.1 사전 감리
- `business_calendar` / `/calendar` 축은 이번 배치에서도 계속 제외했다.
- 구조 후보 비교상 `menu_config`가 가장 안전한 다음 구조 slice로 선정됐다. 전역 메뉴 주입에 닿지만 DB/Auth/부트스트랩 코어는 아니고, 메뉴 캐시 helper라는 구조 패턴이 명확했다.
- `order_storage_cleanup`는 영구 삭제/스토리지 정합 리스크 때문에 한 단계 뒤로 미뤘다.

### 4.2 사후 감리
- 초기 후감리에서는 (1) 테스트가 `menu_config` 전역 상태를 복구하지 않는 점, (2) `except Exception: pass`로 실패가 로그 없이 삼켜지는 점, (3) 타입 힌트/에러 경계 테스트 공백이 식별됐다.
- 이 중 high/medium 성격인 테스트 격리와 무음 예외 삼킴은 같은 배치 안에서 바로 수정했다.
- low 성격이던 타입 힌트와 invalid JSON fallback 테스트도 함께 보강해, 배치 종료 시점에는 새 high/medium finding이 남지 않도록 정리했다.

## 5. 의도적으로 건드리지 않은 것
- `menu_config.json` 상대 경로 설계 자체
- 기본 메뉴 안의 `/calendar` 항목 값
- `services/app_init.py`
- `apps/api/erp_orders_structured.py`
- `services/order_storage_cleanup.py`
- `services/business_calendar.py`
- `/calendar` 관련 기능/라우트
- `app.py`
- `run.py`
- `templates/`
- `static/`

## 6. 검증 결과
### 6.1 legacy import 제거 확인
- 실행: `rg`
- 패턴: `from services\.menu_config import|import services\.menu_config`
- 결과: production Python 코드 기준 match 없음
- 비고: legacy 참조는 `tests/test_foms_namespace_imports.py`의 shim 계약 검증 import만 유지

### 6.2 namespace smoke
- 실행: `python -c "import services.menu_config as legacy; import foms.services.menu_config as ns; assert legacy.load_menu_config is ns.load_menu_config; assert legacy.invalidate_menu_config_cache is ns.invalidate_menu_config_cache; print('MENU_CONFIG_NS_OK')"`
- 결과: `MENU_CONFIG_NS_OK`

### 6.3 focused tests
- 실행: `python -m pytest tests/test_menu_config.py tests/test_foms_namespace_imports.py`
- 결과: 초기 `23 passed` → 후감리 보강 후 `24 passed`

### 6.4 app import
- 실행: `python -c "import app; print('APP_OK')"`
- 결과: `APP_OK`

### 6.5 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 6.6 전체 테스트
- 실행: `python -m pytest`
- 결과: 초기 `255 passed, 3 warnings` → 후감리 보강 후 `256 passed, 3 warnings`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속

### 6.7 lint
- 실행: `ReadLints`
- 결과: 신규 lint 없음

## 7. 해석
- `menu_config`는 열일곱 번째 실제 `foms/services` source of truth가 되었고, 메뉴 캐시/기본 메뉴/관리자 저장 invalidation 흐름도 Step 3 canonical namespace 안으로 들어왔다.
- 이번 배치는 전역 메뉴에 닿았지만, 동작 변경 대신 구조 이동 + thin shim + helper 계약 테스트 + 후감리 보강으로만 통제했다.
- 구조 배치 안에서도 “새 테스트는 상태를 원복해야 한다”, “fail-open이어도 로그는 남겨야 한다”는 프로젝트 규칙을 같이 반영해 품질 기준을 한 단계 올렸다.

## 8. 다음 단계
1. 다음 구조 후보는 `order_storage_cleanup`와 `channel_wam_view_models`를 다시 비교하고, 필요하면 `file_utils` 같은 초저위험 slice도 포함해 Batch 20 후보를 좁힌다
2. 별도 품질 배치로 `services/app_init.py` 기본 관리자 자격 증명/로깅, `apps/api/erp_orders_structured.py` Channel gating 및 빈 주소 reset 조건을 위한 Spec 초안을 준비
3. `menu_config.json` 상대 경로 설계와 기본 메뉴의 `/calendar` 항목 제거 여부는 구조 배치가 아닌 별도 정책/제품 결정으로 분리 검토
