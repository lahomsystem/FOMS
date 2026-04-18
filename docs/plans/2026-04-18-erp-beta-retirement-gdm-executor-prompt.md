# ERP_BETA Retirement GDM Executor Prompt

아래 프롬프트를 다른 LLM 에이전트에게 그대로 전달해 실행하세요.

```text
당신은 FOMS 저장소에서 작업하는 실행 에이전트이며, 이번 작업은 반드시 GDM(Grand Develop Master) 방식으로 수행한다.

작업 목표:
- active runtime/product code에서만 `ERP_BETA`, `erp-beta`, `is_erp_beta` legacy compatibility를 단계적으로 retire한다.
- historical docs/backups/evidence는 보존한다.
- 운영 무중단 원칙을 지키며, 한 번에 전량 삭제하지 말고 gate 기반으로 진행한다.

반드시 먼저 읽을 문서:
1. `AGENTS.md`
2. `.cursor/agents/GDM_EXECUTION_PLAN.md`
3. `.cursor/agents/grand-develop-master.md`
4. `docs/specs/2026-04-18-erp-beta-retirement_SPEC.md`
5. `docs/plans/2026-04-18-erp-beta-retirement-execution-plan.md`

세션/환경 전제:
- 저장소 루트: `c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS`
- 운영 환경: Windows 11
- 기본 셸: PowerShell
- Git/문서/명령 예시도 PowerShell 기준으로 해석한다.

절대 규칙:
- Root Cause Fix Only. 증상 우회, 임시방편, 하드코딩, 조용한 예외 삼키기 금지.
- `try/except: pass`, 빈 catch, 경고 무시, 로그 없는 fail-open 금지.
- historical evidence는 삭제/치환 대상이 아니다:
  - `docs/plans/`
  - `docs/evolution/`
  - `docs/ARCHIVE_INDEX.md`
  - `backups/`
  - `docs/harness/runtime/`
  - `docs/harness/logs/`
- 이미 배포된 Alembic revision은 수정하지 말고, 필요하면 새 migration으로 처리한다.
- `ERP_BETA` retire는 코어 변경(DB/env/runtime contract)이므로 live gate 증거 없이 P2/P3 삭제를 강행하지 않는다.
- env cleanup, JS alias cleanup, deep-link cleanup, DB/bootstrap cleanup을 같은 deploy 감각으로 한 번에 몰아넣지 않는다.

GDM 실행 원칙:
- Spec 기반 실행이며, 승인 없는 코어 변경은 시작하지 않는다.
- 이 세션에 “구현 승인”이 명시되어 있지 않다면:
  1. spec/plan 핵심을 짧게 요약하고
  2. 어떤 배치부터 시작할지 제안한 뒤
  3. 사용자 승인 요청에서 멈춘다.
- 이 세션에 구현 승인이 이미 있다면, 바로 실행하되 반드시 gate 순서를 지킨다.

이번 작업의 SSOT:
- Spec: `docs/specs/2026-04-18-erp-beta-retirement_SPEC.md`
- Execution plan: `docs/plans/2026-04-18-erp-beta-retirement-execution-plan.md`

실행 순서:

1. 컨텍스트 고정
- 위 5개 문서를 읽고 이번 retire의 범위/금지 범위/게이트 조건을 요약한다.
- 현재 워크트리 변경사항을 확인하되, 내가 만들지 않은 변경은 절대 되돌리지 않는다.
- 관련 코드와 테스트를 검색해 현재 `ERP_BETA`, `erp-beta`, `is_erp_beta`가 active runtime/product code에 어디 남아 있는지 분류한다.

2. 게이트 판정
- 아래 4가지 증거가 확보됐는지 확인한다.
  - 운영/스테이징 DB에 `is_erp_beta`, `ix_orders_is_erp_beta`, dual-column 상태가 남아 있는지
  - Railway env에서 `ERP_ORDER_ENABLED`, `ERP_BETA_ENABLED`, `ERP_BETA_DEBUG` 실제 사용 상태
  - inbound legacy usage: `open=erp-beta`, `create_mode=ERP_BETA`
  - placeholder/draft/live drift 데이터 상태
- 로컬에서 확인 불가능한 항목은 추측하지 말고 “미확보”로 명시한다.

3. 배치 선택
- 기본 시작점은 Phase A / Task 1이다.
- live gate 증거가 미확보면:
  - Task 1(게이트 잠금, 테스트 보강, spec 체크리스트 고정)까지만 진행하거나
  - 명백히 안전한 P1 stale naming cleanup까지만 진행한다.
- live gate 증거가 명확히 확보된 경우에만 P2로 진행한다.
- DB/bootstrap canonicalization(P3)은 DB-side evidence 없이는 시작하지 않는다.

4. 구현 방식
- 각 배치는 다음 순서를 반드시 지킨다.
  1. 현상/계약을 테스트로 먼저 고정
  2. 관련 파일만 최소 범위 수정
  3. 왜 이 수정이 root cause 제거인지 설명 가능해야 함
  4. 테스트/검증 통과 확인
  5. spec 또는 상태 문서에 근거/게이트 반영
- 한 배치 안에서도 unrelated cleanup을 섞지 않는다.

5. 현재 plan 기준 우선순위
- Phase A / Task 1
  - `tests/domains/test_erp_order_shared_form_scripts.py`
  - `tests/domains/test_erp_shell_fragment_contract.py`
  - 필요 시 focused test 추가
  - spec에 live gate checklist와 verification SSOT 고정
- Phase B / Task 2 (증거 없어도 가능한 안전 배치)
  - `templates/orders/partials/erp_order_tab.html`
  - `static/css/foundation/erp-pro/09-mobile-erp-optimization.css`
  - `foms/platform/erp_blueprint.py`
  - `foms/api/notifications/__init__.py`
  - `foms/api/orders/calendar.py`
  - `foms/api/erp_orders_structured.py`
- Phase C / Task 3
  - `foms/services/context_processors.py`
  - `static/js/orders/erp-order-shared.js`
  - `static/js/orders/estimate-preview.js`
  - `templates/orders/add_order.html`
  - `templates/orders/edit_order.html`
  - `foms/web/orders/listing.py`
  - `foms/api/personal_board.py`
  - `foms/web/orders/trash.py`
- Phase D / Task 4
  - `models.py`
  - `foms/services/erp_order_flags.py`
  - `scripts/migrations/safe_schema_migration.py`
  - `scripts/ops/erp_build_step_runner.py`
  - `run.py`
  - `tests/domains/test_sqlite_startup_compat.py`

6. 검증 명령
- 앱 import:
  - `python -c "import app; print('APP_OK')"`
- 하네스 검증:
  - `python tools/harness/verify_result.py --json`
- focused tests:
  - `pytest tests/domains/test_erp_order_shared_form_scripts.py -q`
  - `pytest tests/domains/test_erp_shell_fragment_contract.py -q`
  - `pytest tests/domains/test_sqlite_startup_compat.py -q`
  - `pytest tests/domains/test_app_init.py tests/domains/test_app_bootstrap_contract.py -q`
- residual search:
  - active runtime/product code 기준 `ERP_BETA`, `erp-beta`, `is_erp_beta` 잔존 검색
  - historical docs/backups는 allowlist로 제외해서 판단

7. 구현 시 추가 지침
- `ERP_BETA` naming을 canonical naming(`ERP Order` / `erp-order` / `erp_order` / `is_erp_order`)으로 수렴시킨다.
- 주석/로그/내부 helper 명 변경은 cosmetic인지 runtime contract인지 구분해서 다룬다.
- placeholder/suppressor 제거는 live data cleanup 증거 없으면 성급히 지우지 않는다.
- deep-link alias와 request alias 제거는 inbound usage 0 증거 없으면 미룬다.
- DB synonym/bootstrap 제거는 startup compatibility test와 함께 움직인다.

8. 완료 보고 형식
- 최종 응답은 반드시 아래 3가지를 포함한다.
  1. 무엇을 발견했는가
  2. 무엇을 작업/수정했는가
  3. 왜 그런 결정을 내렸는가
- 추가로 아래도 포함한다.
  - 실행한 검증 명령과 결과
  - 아직 남은 gate/blocker
  - 다음 배치 추천

실행 태도:
- 추측하지 말고 증거 기반으로 움직여라.
- 위험한 삭제보다 gate 잠금과 계약 테스트 강화를 우선하라.
- “이번 턴에서 끝까지 밀기”보다 “안전한 배치를 정확히 끝내기”를 우선하라.
- 사용자가 승인하지 않은 고위험 코어 제거는 하지 마라.
```
