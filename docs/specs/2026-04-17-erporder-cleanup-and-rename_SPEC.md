# ERP Order Cleanup And Rename Spec
> 작성일: 2026-04-17 | 상태: 🟢 코드/검증 완료 (운영 one-time DB apply만 남음)
> 최종 갱신: 2026-04-17 | 기준: 현재 코드/검증 결과 반영

## 0. 현재 상태 요약
- [x] same-tab `/edit/<id>` 첫 진입 시 structured detail + measurement panel blank-screen 이슈는 해소되었다.
- [x] active UI/runtime naming은 대체로 `ERP Order`/`erp-order`/`erp_order` 기준으로 정리되었다.
- [x] `/edit/<id>`는 full-document canonical route로 정리되었고, `templates/orders/edit_order_fragment.html`은 retire되었다.
- [x] startup auto-init은 deploy-time `FOMS_AUTO_INIT_*` env flag가 아니라 FOMS 내부 bounded policy로 정리되었다.
- [x] `orders.is_erp_beta` → `orders.is_erp_order` physical column/index rename migration file과 runtime caller cleanup은 landed 상태다.
- [x] protected path 밖 residual old canonical naming의 잔여 test/current docs final sweep과 final review loop을 완료했다.
- [ ] 운영 반영 시 원격 DB에는 `rename_orders_erp_beta_flag_to_erp_order.py`를 one-time apply 해야 한다.

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
- ERP 화면에서 같은 탭으로 `/edit/<id>`에 처음 진입해도 새로고침 없이 주문 상세 구조화 데이터와 실측 일정 패널이 즉시 로딩된다.
- active product surface의 명칭과 계약을 `ERP Beta`/`erp-beta`/`erp_beta` 중심에서 `ERP Order`/`erp-order`/`erp_order` 중심으로 정리한다.
- edit surface는 fragment 전용 템플릿에 의존하지 않고 full-document canonical route + shared bootstrap 계약으로 동작한다.

### 1.2 기능 요구사항
1. ERP same-tab 첫 진입 시 `/api/orders/<id>/structured`와 `/api/erp/measurement/summary`가 refresh 없이 호출되어야 한다.
2. orders list / global-nav fragment 전용 query(`view=nav-fragment`)가 edit URL로 누수되지 않아야 한다.
3. `/edit/<id>`는 full-document canonical route로 동작해야 하며, shell/global-nav fragment transport가 edit bootstrap을 소유하지 않아야 한다.
4. active code/test/current docs의 canonical naming은 `erporder` 계열로 정리한다.
5. legacy deep link `open=erp-beta`는 compatibility boundary에서 계속 받아들여야 한다.
6. active config/env의 canonical naming은 `ERP_ORDER_*` 기준으로 정리하되, startup 정책은 deploy-time opt-in flag가 아니라 FOMS 내부 정책으로 유지한다.
7. historical run record / archive / backup / harness runtime log는 대량 치환하지 않는다.

### 1.3 예외/제약 조건
- 과거 증거 문서, run record, archive 문서는 당시 사실 기록이므로 원문을 보존한다.
- `backups/`, `docs/harness/runtime/`, `docs/harness/logs/`, evidence JSON은 rename 대상에서 제외한다.
- DB physical column/index rename이 포함되면 migration과 runtime caller를 같은 배치에서 정리해야 한다.
- 임시 우회 코드 누적 금지. transport, bootstrap, naming boundary를 각각 한 곳으로 모은다.
- 원격 배포마다 수동 env choreography를 반복하는 구조는 허용하지 않는다.

## 2. How — 어떻게 만드는가

### 2.1 실제 수정/영향 파일
| 파일 | 변경 내용 |
|------|-----------|
| `templates/orders/index.html` | edit 링크에서 raw `request.args` 전달 제거, preserved filter만 유지, `view` 누수 차단 |
| `static/js/global-nav-runtime.js` | nav-fragment transport state가 edit/detail URL에 섞이지 않도록 경계 고정 |
| `static/js/runtime/erp-shell.js` | edit 특수 rescue 제거, shell transport/prefetch/cache 책임으로 단순화 |
| `templates/orders/edit_order.html` | full-document canonical edit 진입점 정리, inline helper/init 중복 제거 |
| `templates/orders/edit_order_fragment.html` | retired (edit fragment contract 제거) |
| `templates/orders/partials/edit_order_body.html` | order id / enablement / open target을 담는 canonical root config source 정리 |
| `templates/orders/partials/erp_order_tab.html` | ERP Order 탭 DOM/data-* contract 정리 |
| `static/js/orders/erp-order-shared.js` | single idempotent mount/bootstrap canonical module |
| `static/js/orders/estimate-preview.js` | legacy `ERP_BETA_ENABLED` fallback boundary 유지 |
| `foms/web/orders/edit.py` | canonical query/route contract 유지, legacy `open=erp-beta` compatibility boundary 처리 |
| `foms/web/orders/listing.py` | create mode / placeholder / list display naming 정리 |
| `foms/services/context_processors.py` | `ERP_ORDER_ENABLED` canonical env + legacy fallback boundary 정리 |
| `models.py` | canonical ORM/physical column을 `is_erp_order`로 정리, legacy Python attr `is_erp_beta`는 synonym boundary로 축소 |
| `migrations/versions/rename_orders_erp_beta_flag_to_erp_order.py` | `orders.is_erp_beta` → `orders.is_erp_order` physical rename/idempotent index rename migration |
| `foms/services/db_indexes.py` | bounded startup DDL/repair policy (internal) |
| `foms/services/app_init.py` | internal bounded auto-init/backfill policy; deploy-time env choreography 제거 |
| `foms/services/erp_order_flags.py` | legacy flag fallback을 single helper boundary로 집중 |
| `scripts/migrations/safe_schema_migration.py`, `scripts/migrations/backfill_erp_flat_columns.py`, `scripts/ops/erp_build_step_runner.py` | canonical `is_erp_order` 기준 bootstrap/backfill/migration helper 정리 |
| `foms/web/orders/dashboard.py`, `foms/web/production/dashboard.py`, `foms/web/construction/dashboard.py` | dashboard payload key를 `is_erp_order` canonical shape로 정리 |
| `templates/measurement/*`, `templates/shipment/*`, `templates/orders/partials/*`, `templates/production/*`, `templates/construction/*`, `templates/cs/*` | active template flag/fallback를 `erp_order_enabled` / `is_erp_order` 기준으로 정리 |
| `tests/domains/test_app_init.py`, `tests/domains/test_db_indexes.py` | startup policy regression |
| `tests/domains/test_erp_order_shared_form_scripts.py`, `tests/domains/test_erp_shell_fragment_contract.py`, `tests/domains/test_erp_runtime_shell_js_contract.py` | first-entry/shell/rename contract regression |
| `docs/specs/*`, `docs/ARCHIVE_INDEX.md`, active current docs | active current spec/테스트 sweep 완료, protected historical docs는 보존 |

### 2.2 landed 아키텍처 방향
- `static/js/runtime/erp-shell.js`는 shell navigation/prefetch/cache만 담당한다.
- edit surface 초기화는 `static/js/orders/erp-order-shared.js`가 담당한다.
- `/edit/<id>`는 full-document canonical route이며, 별도 fragment edit template에 의존하지 않는다.
- `erporder`가 canonical naming이며, legacy compatibility는 deep-link/env parsing boundary에서만 허용한다.
- query transport state(`view=nav-fragment`, shell fragment modes)는 navigation/runtime layer에만 머물고 business URL로 새지 않게 한다.
- startup auto-init은 lock/statement timeout이 걸린 bounded internal policy이며, deploy-time `FOMS_AUTO_INIT_*` flag를 요구하지 않는다.

### 2.3 의존성 및 영향 범위
- 영향 범위: orders list/edit, ERP dashboards linking to edit page, channel/deep links, measurement summary panel, structured order load path
- DB 마이그레이션: physical rename migration file은 landed, 실제 원격 DB apply는 one-time migration step으로 남아 있음
- 환경변수 영향: `ERP_ORDER_*` canonical 유지, `FOMS_AUTO_INIT_*` deploy-time flag는 제거
- 외부 링크 영향: 기존 `?open=erp-beta` 링크는 compatibility 유지

## 3. Steps — 실행 단계
- [x] Step 1: active rename/cleanup boundary 확정, protected path(historical docs/backups/runtime logs) 제외 규칙 적용
- [x] Step 2: `orders/index.html`와 global-nav 경계에서 `view=nav-fragment` 누수 제거
- [x] Step 3: edit page bootstrap를 single mount contract로 재구성하고 `runtime-shell.js`의 edit 특수 rescue 제거 (`edit_order_fragment.html` retire 포함)
- [x] Step 4: shared bootstrap/DOM 계약을 `erporder` canonical naming으로 정리 (`erp-order-shared.js`, `erp_order_tab.html`)
- [x] Step 5: Python active code / env / query contracts를 `erporder` naming으로 정리하고 legacy deep-link/env boundary만 유지
- [x] Step 6: DB schema/index physical rename migration 추가 및 ORM/query caller canonical cleanup
- [x] Step 7: focused tests/manual verification + core runtime review loop 수행
- [x] Follow-up: residual old canonical naming의 test/current docs final sweep + final GDM/code-review loop

## 4. 검증 기준
- [x] `python -c "import app"` 통과
- [x] `python tools/harness/verify_result.py --json` 통과
- [x] orders list → same-tab edit first entry에서 `/api/orders/<id>/structured`와 `/api/erp/measurement/summary`가 refresh 전 호출됨
- [x] ERP Order edit first entry에서 structured detail + measurement schedule panel이 즉시 보임
- [x] 관련 focused pytest 통과 (`test_erp_shell_fragment_contract.py`, `test_erp_runtime_shell_js_contract.py`, `test_erp_order_shared_form_scripts.py`, startup regressions 포함)
- [x] deploy-time `FOMS_AUTO_INIT_*` env flag choreography 없이 startup 가능
- [x] test/current docs에서 old canonical naming이 protected path 밖에 남지 않음
- [x] final state 기준 GDM/code-review loop high-severity finding 0 재확인

## 5. 참고 자료
- 관련 결정: `docs/harness/policy/DECISIONS.md` — live runtime layout/contract drift는 split-brain 없이 same batch 정렬
- 관련 기록: `docs/plans/2026-04-17-erp-fast-page-and-tab-navigation-execution-plan.md`
- 관련 기록: `docs/plans/2026-04-17-ept-b5-subordinate-shell-run-record.md`
- 관련 기록: `docs/plans/2026-04-17-ept-b6-prefetch-warm-nav-run-record.md`
- 관련 기록: `docs/plans/2026-04-17-ept-b7-html-diet-page-assets-profiling-run-record.md`
- 관련 기록: `docs/plans/2026-04-17-ept-b8-verification-railway-evidence-run-record.md`
- 관련 기록: `docs/plans/2026-04-17-gnv-run-record.md`
