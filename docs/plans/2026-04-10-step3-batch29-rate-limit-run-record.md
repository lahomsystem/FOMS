# Step 3 Batch 29 Run Record
> 작성일: 2026-04-10
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-10-step3-batch28-order-storage-cleanup-run-record.md`

- 일시: 2026-04-10 10:35:55
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: `rate_limit`를 스물일곱 번째 실제 `foms/services` source of truth로 이동하고 `app.py` 부팅 경로가 canonical path를 직접 사용하도록 정리한다
- 제외 축: 사용자 지시에 따라 `business_calendar` / `/calendar` 기능 축은 이번 배치에서도 제외

## 1. 전체 판정
**Verdict: Step 3 Batch 29 executed, `rate_limit` canonical migration completed without changing limiter initialization behavior**

이유:
- `foms/services/rate_limit.py`를 새 canonical source로 추가하고, 기존 `services/rate_limit.py`는 thin shim으로 전환했다.
- `app.py`가 limiter 초기화 helper를 canonical path에서 직접 import하도록 정리했다.
- 새 단위 테스트로 default limit 파싱, memory/redis storage URI 결정, rate-limit key 우선순위를 고정했다.
- 후감리에서 발견된 low 문서성 이슈(`app.py` 주석 경로 불일치)를 즉시 수정했고, `RATE_LIMIT_NS_OK`/`verify_result.py --json`/전체 `pytest`를 재통과했다.

## 2. 선정 근거
Batch 28 완료 후 자동 전감리 결과:
1. `rate_limit`
2. `realtime_notifications`
3. `user_deletion`

선정 이유:
- `rate_limit`는 caller가 실질적으로 `app.py` 한 곳뿐인 leaf helper였다.
- cross-service import가 없고, runtime 의미론이 `init_limiter(app)` 하나에 집중돼 있어 thin shim 패턴에 적합했다.
- startup wiring만 정확히 고정하면 되는 배치라 structure-only 전개가 쉬웠다.

## 3. 실제 변경 범위
### 3.1 canonical source 추가
- `foms/services/rate_limit.py`
  - 기존 rate limiter 초기화 구현을 canonical 위치로 이동
  - module docstring, `__all__`, 반환 타입/내부 변수명 정리
  - key 우선순위는 기존과 동일하게 유지:
    - `session['user_id']`
    - 세션 쿠키 SHA-1 해시
    - `X-Forwarded-For`
    - `X-Real-IP`
    - `get_remote_address()`

### 3.2 legacy shim 전환
- `services/rate_limit.py`
  - `init_limiter`만 canonical에서 재수출하는 thin shim으로 전환

### 3.3 caller canonical import 정리
- `app.py`
  - `from services.rate_limit import init_limiter` → `from foms.services.rate_limit import init_limiter`
  - 후감리 low 메모를 반영해 바로 위 주석도 canonical 경로 기준으로 정정

## 4. 테스트 보강
### 4.1 namespace / caller binding
- `tests/test_foms_namespace_imports.py`
  - `legacy_rate_limit` / `namespaced_rate_limit` import 추가
  - `test_legacy_rate_limit_shim_preserves_canonical_contract()` 추가
  - `test_app_uses_canonical_rate_limit_import()` 추가

### 4.2 focused behavior verification
- `tests/test_rate_limit.py`
  - `test_init_limiter_passes_expected_storage_uri_and_parsed_limits()` 추가
  - `test_init_limiter_falls_back_to_memory_and_default_limits_when_env_blank()` 추가
  - `test_init_limiter_rate_limit_key_precedence()` 추가
  - `Limiter`를 spy 객체로 대체해 실제 Redis 연결 없이 설정값과 key function 의미론을 검증

## 5. 감리 결과 요약
### 5.1 사후 감리
- 신규 high/medium 회귀 없음
- low 하나 발견:
  - `app.py`의 주석이 여전히 `services/rate_limit.py`를 가리킴
- 조치:
  - 같은 배치 안에서 `canonical foms/services/rate_limit.py`로 수정

### 5.2 residual gap
- 단위 테스트는 `Limiter`를 spy로 대체하므로 실제 Redis + `flask-limiter` storage 연결 자체를 통합 수준에서 검증하는 것은 아니다.
- 그러나 이번 배치는 structure-only import 정렬이 목적이고, `verify_result.py --json`과 전체 `pytest` 기준에서 startup regression은 재현되지 않았다.

## 6. 의도적으로 건드리지 않은 것
- `flask-limiter` 실제 운영 설정/배포 토폴로지
- `config/rate_limit.py`
- backup 경로의 legacy snapshot
- `business_calendar` / `/calendar`

## 7. 검증 결과
### 7.1 focused tests
- 실행:
  - `python -m pytest tests/test_rate_limit.py tests/test_foms_namespace_imports.py -q`
- 결과:
  - `43 passed`

### 7.2 namespace smoke
- 실행: `python -c "import foms.services.rate_limit as m; print('RATE_LIMIT_NS_OK')"`
- 결과: `RATE_LIMIT_NS_OK`

### 7.3 shared verification
- 실행: `python tools/harness/verify_result.py --json`
- 결과: `success: true`

### 7.4 전체 테스트
- 실행: `python -m pytest`
- 결과: `293 passed, 3 warnings`
- 관찰 사항: 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속

### 7.5 lint
- 실행: `ReadLints`
- 결과: 신규 lint 없음

## 8. 해석
- `rate_limit`는 스물일곱 번째 실제 `foms/services` source of truth가 되었고, 앱 startup path의 canonical limiter import 정리가 완료됐다.
- 다음 자동 전감리 기준 가장 안전한 구조 후보는 `realtime_notifications`다.
- 그 다음 비교 후보는 `user_deletion`, `order_attachment_thumbnail` 순으로 유지된다.

## 9. 다음 단계
1. 자동 다음 구조 후보는 `realtime_notifications`
2. 그 다음 비교 후보는 `user_deletion`
3. storage/RQ/thread pool 결합이 있는 `order_attachment_thumbnail`는 그 다음 비교 후보로 유지
