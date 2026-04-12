# Step 4 Batch 56 Run Record
> 작성일: 2026-04-10
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-10-step4-batch55-bootstrap-contract-freeze-run-record.md`

- 일시: 2026-04-10
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: 루트 `app.py`의 blueprint import/register 블록만 `foms/platform/blueprints.py`로 분리하되 등록 순서를 1:1 유지한다
- 제외 축: 사용자 지시대로 `business_calendar` / `/calendar` 축은 계속 범위 밖으로 유지

## 1. 전체 판정
**Verdict: Step 4 Batch 56 executed, blueprint registry extraction completed**

이유:
- `foms/platform/blueprints.py`에 기존 순서를 그대로 유지한 `register_blueprints(app)`를 추가했다.
- 루트 `app.py`는 전체 blueprint import/register block 대신 registrar 호출만 수행하도록 줄였다.
- request hook과 realtime 경로가 아직 루트에 남아 있었기 때문에 `get_user_by_id`, `register_chat_socketio_handlers`, `can_edit_erp` 최소 runtime binding만 root에 유지했다.
- `calendar_bp` 등록은 사용자 제외 축이므로 제거/정리하지 않고 그대로 유지했다.

## 2. 실제 변경 범위
- `foms/platform/__init__.py`
- `foms/platform/blueprints.py`
- `app.py`

## 3. 의도적으로 건드리지 않은 것
- request hooks / error handlers / teardown / context processors
- limiter / notification badge patch / Socket.IO init
- middleware / secret key / WhiteNoise / ProxyFix

## 4. 검증 결과
### 4.1 focused Step 4 contract suite
- 실행:
  - `python -m pytest tests/test_app_bootstrap_contract.py tests/test_foms_namespace_imports.py tests/test_rate_limit.py -q`
- 결과:
  - `138 passed in 0.19s`

## 5. 해석
- 가장 큰 blast radius였던 blueprint registry가 별도 module로 빠졌지만, root 공개 계약과 `/calendar` registration은 유지됐다.

## 6. 다음 단계
1. Batch 57에서 request hook / error handler / favicon / `__build` / teardown/context registration을 `foms/platform/http.py`로 분리한다.
