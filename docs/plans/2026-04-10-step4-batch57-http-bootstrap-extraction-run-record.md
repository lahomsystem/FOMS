# Step 4 Batch 57 Run Record
> 작성일: 2026-04-10
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-10-step4-batch56-blueprint-registry-extraction-run-record.md`

- 일시: 2026-04-10
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: request hook, error handler, favicon/`__build`, teardown/context registration을 `foms/platform/http.py`로 분리한다
- 제외 축: 사용자 지시대로 `business_calendar` / `/calendar` 축은 계속 범위 밖으로 유지

## 1. 전체 판정
**Verdict: Step 4 Batch 57 executed, HTTP bootstrap extraction completed**

이유:
- `foms/platform/http.py`에 `register_http_bootstrap()`를 추가해 app-level request hook/response logging/error handler/route/teardown wiring을 한곳으로 모았다.
- 루트 `app.py`는 `register_context_processors` 공개 계약을 계속 유지하면서 registrar 호출만 수행하도록 변경했다.
- 시공팀 접근 제한 로직의 `/calendar` 차단 분기와 ERP shipment redirect는 동작 변경 없이 그대로 보존했다.

## 2. 실제 변경 범위
- `foms/platform/http.py`
- `app.py`

## 3. 의도적으로 건드리지 않은 것
- blueprint registration
- limiter / notification badge patch
- Socket.IO init / chat handler binding
- middleware / Flask app 생성 로직

## 4. 검증 결과
### 4.1 focused Step 4 contract suite
- 실행:
  - `python -m pytest tests/test_app_bootstrap_contract.py tests/test_foms_namespace_imports.py tests/test_rate_limit.py -q`
- 결과:
  - `138 passed in 0.21s`

## 5. 해석
- HTTP bootstrap가 module로 분리되면서 root `app.py`의 request/error/route wiring이 크게 줄었고, context processor export 계약은 유지됐다.

## 6. 다음 단계
1. Batch 58에서 limiter/badge patch/Socket.IO initialization을 `foms/platform/realtime.py`로 분리한다.
