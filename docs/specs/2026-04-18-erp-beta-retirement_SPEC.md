# ERP_BETA Retirement Spec
> 작성일: 2026-04-18 | 상태: 🟡 Phase A Task 1 완료 · §7 게이트 **부분 확보** (G-ENV·G-IN 약한 신호·G-DB/G-DATA는 VPC 내 SQL 대기) — 근거: `docs/harness/evidence/2026-04-18-erp-beta-retirement-gate-evidence.json`

## 0. 현재 상태 요약
- `erporder`는 이미 canonical naming이지만, active runtime에는 아직 `ERP_BETA` legacy boundary가 남아 있다.
- 현재 상태에서 `ERP_BETA`를 전량 삭제하면 운영 DB bootstrap, legacy deep-link, env fallback, old request/data normalization, static asset cache skew 위험이 있다.
- 목표는 historical docs/backups를 보존하면서, **active runtime/product code에서만** `ERP_BETA`를 완전 은퇴하는 것이다.
- 본 Spec은 FOMS 시스템 운영에 지장 없이 `ERP_BETA`를 retire하기 위한 **게이트 기반 실행 계획**이다.

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
- active runtime/product code에서 `ERP_BETA`, `erp-beta`, `is_erp_beta` legacy compatibility가 제거된다.
- 운영/스테이징 모든 환경에서 `ERP_ORDER_*`만으로 동일 기능이 유지된다.
- `/add`, `/edit/<id>`, ERP dashboard family, measurement/shipment/CS page, structured save/load, draft 생성, payment confirm, attachment flow가 기존과 동일하게 동작한다.
- DB/bootstrap/startup 경로가 `is_erp_order` canonical schema만 가정하도록 정리된다.

### 1.2 기능 요구사항
1. 운영/스테이징 DB에서 `orders.is_erp_order`만 사용하고 `is_erp_beta`/`ix_orders_is_erp_beta` 의존이 없어야 한다.
2. 라이브 env는 `ERP_ORDER_ENABLED`만 사용하고 `ERP_BETA_ENABLED`, `ERP_BETA_DEBUG`에 의존하지 않아야 한다.
3. legacy deep-link `open=erp-beta`와 legacy form mode `ERP_BETA`는 사용량이 0임이 확인된 뒤 제거해야 한다.
4. `"ERP Beta"` placeholder/sentinel 데이터는 제거 또는 canonical 치환 후 runtime guard를 제거해야 한다.
5. static JS/CSS/template에서 stale `ERP_BETA` naming debt를 제거해도 기능 회귀가 없어야 한다.
6. 운영 safety를 위해 retire는 한 번에 전량 삭제하지 않고, 우선순위 배치 순서대로 진행해야 한다.

### 1.3 예외/제약 조건
- `docs/plans/`, `docs/evolution/`, `docs/ARCHIVE_INDEX.md`, `backups/`, `docs/harness/runtime/`, `docs/harness/logs/`의 historical evidence는 삭제/치환 대상이 아니다.
- 이미 배포된 Alembic revision 파일은 원칙적으로 수정하지 않는다. 추가 DB 조정이 필요하면 새 migration으로 처리한다.
- `ERP_BETA` 완전 은퇴는 코어 변경(DB/env/runtime contract)이므로, live gate 증거 확보 전 코드 삭제 금지.
- env cleanup, JS alias cleanup, deep-link cleanup, DB synonym/bootstrap cleanup은 같은 deploy에 몰아넣지 않는다.

## 2. How — 어떻게 만드는가

### 2.1 수정 대상 파일
| 우선순위 | 파일 | 변경 내용 |
|------|------|-----------|
| P0 | `docs/specs/2026-04-18-erp-beta-retirement_SPEC.md` | retirement gate, scope, verification SSOT |
| P0 | `tests/domains/test_erp_order_shared_form_scripts.py` | beta shim 제거 전/후 계약을 명시적으로 고정 |
| P0 | `tests/domains/test_erp_shell_fragment_contract.py` | `open=erp-beta` 사용량 0 확인 후 제거 배치를 위한 계약 보강 |
| P0 | 신규 또는 기존 focused tests | env fallback, estimate-preview precedence, startup canonical-only gate 보강 |
| P1 | `templates/orders/partials/erp_order_tab.html` | `erp_beta_default_stage_received` fallback 제거 (완료: 기본 `false`) |
| P1 | `static/css/foundation/erp-pro/09-mobile-erp-optimization.css` | `#erp-beta`, `.erp-beta-tabs-nav`, `#erpBetaTabs` stale selector 제거 (완료) |
| P1 | `foms/platform/erp_blueprint.py` | `ERP_BETA_DEBUG` 제거 또는 canonical debug 명으로 정리 |
| P1 | `foms/api/notifications/__init__.py` | dead debug env read 제거 |
| P1 | `foms/api/orders/calendar.py` | `_apply_erp_order_display_overrides`(구 `_apply_erp_beta_display_overrides`) 내부명 정리 |
| P1 | `foms/api/erp_orders_structured.py` | `[ERP_BETA]` log prefix canonical rename, placeholder handling 분리 |
| P1 | comment/docstring-only refs in active code | stale naming 정리 |
| P2 | `foms/services/context_processors.py` | `ERP_BETA_ENABLED` env fallback 제거 |
| P2 | `static/js/orders/erp-order-shared.js` | `ERP_BETA_ENABLED`, `__ERP_BETA_DRAFT_MODE`, `data-erp-beta-*` JS fallback 제거 |
| P2 | `static/js/orders/estimate-preview.js` | `ERP_BETA_ENABLED` fallback 제거 |
| P2 | `templates/orders/add_order.html` | `open=erp-beta` 허용 제거 |
| P2 | `templates/orders/edit_order.html` | `open=erp-beta` 허용 제거 |
| P2 | `foms/web/orders/listing.py` | `create_mode=ERP_BETA` 수용 제거 |
| P2 | `foms/api/personal_board.py` | legacy placeholder/status suppressor canonical 정리 |
| P2 | `foms/web/orders/trash.py` | `"ERP Beta"` placeholder cleanup guard canonical 정리 |
| P3 | `models.py` | `is_erp_beta = synonym('is_erp_order')` 제거 |
| P3 | `foms/services/erp_order_flags.py` | `is_erp_beta` fallback 제거 |
| P3 | `scripts/migrations/safe_schema_migration.py` | legacy column rename/repair 제거, canonical-only bootstrap 정리 |
| P3 | `scripts/ops/erp_build_step_runner.py` | legacy ERP_BETA step logic/key retire 또는 별도 step-key migration |
| P3 | `run.py` | `safe_schema_migration` legacy-aware startup 호출 재정렬 |
| P3 | `tests/domains/test_sqlite_startup_compat.py` | canonical-only startup compatibility로 갱신 |

### 2.2 아키텍처 방향
- canonical naming은 `ERP Order` / `erp-order` / `erp_order` / `is_erp_order` 하나로 수렴한다.
- legacy compatibility는 runtime 삭제 전에 **live evidence로 사용량 0을 먼저 증명**하고 retire한다.
- DB/bootstrap 경계는 `app/runtime -> migration/bootstrap -> model/helper` 순으로 정리한다.
- frontend 경계는 `stale debt -> JS alias -> deep-link/input alias` 순으로 정리한다.
- data/placeholder 경계는 live data cleanup과 read-side drift 점검이 끝난 뒤 제거한다.

### 2.3 의존성 및 영향 범위
- 영향 범위: orders add/edit, ERP shared form runtime, estimate preview, structured save/load, measurement/shipment/CS dashboard family, startup bootstrap, DB schema repair, board/trash/read-model display
- DB 영향: live DB schema 상태 확인 필수, 필요 시 새 migration 추가 가능
- 배포 영향: Railway env snapshot, static asset cache 관찰, multi-service restart 필요 가능성
- 외부 입력 영향: 북마크/알림/old links/old forms에서 `open=erp-beta`, `create_mode=ERP_BETA` 사용량 확인 필요

## 3. Steps — 실행 단계

### Phase A — 게이트 잠금 (승인 후 첫 배치)
- [ ] Step A1: 운영/스테이징 DB에서 `is_erp_beta`, `ix_orders_is_erp_beta`, dual-column 상태를 확인한다. (VPC/SSH 대기 — `railway_db_gate_snapshot_ssh.py` 배포 후 실행)
- [x] Step A2: Railway env snapshot을 수집하고 `ERP_ORDER_ENABLED`, `ERP_BETA_ENABLED`, `ERP_BETA_DEBUG` 실사용 상태를 기록한다. (production: 세 변수 **미설정**, `ERP_MOBILE_V2_ENABLED`만 존재 — 증거 JSON)
- [~] Step A3: access/log/search 기준 `open=erp-beta`, `create_mode=ERP_BETA` inbound 사용량을 확인한다. (Railway 앱 로그 3000줄·`erp-beta` 필터 **0건** — **쿼리스트링 미기록 가능**, 엣지 로그 권장)
- [ ] Step A4: placeholder/draft/live drift 데이터 점검 기준(SQL 또는 운영 리포트)을 확정한다.
- [x] Step A5: focused tests를 보강해 retire 전/후 회귀를 CI에서 잡을 수 있게 만든다. (`test_erp_order_shared_form_scripts.py`에 env 우선순위·deep-link·estimate-preview 순서 계약 추가)

### Phase B — P1 stale debt cleanup
- [ ] Step B1: clearly stale template/css/comment/debug naming을 제거한다.
- [ ] Step B2: P1 cleanup 후 UI/runtime smoke와 focused tests를 통과시킨다.

### Phase C — P2 runtime compatibility retirement
- [ ] Step C1: Railway에서 `ERP_ORDER_ENABLED` 명시 확인 후 `ERP_BETA_DEBUG`를 먼저 retire한다.
- [ ] Step C2: `foms/services/context_processors.py`의 `ERP_BETA_ENABLED` fallback 제거 후 add/edit/dashboard smoke를 확인한다.
- [ ] Step C3: `erp-order-shared.js`와 `estimate-preview.js`의 beta JS alias를 같은 배치에서 제거한다.
- [ ] Step C4: `open=erp-beta`, `create_mode=ERP_BETA`, placeholder suppressor 등 inbound/runtime alias를 제거한다.

### Phase D — P3 DB/bootstrap canonicalization
- [ ] Step D1: `safe_schema_migration.py`, `run.py`, `erp_build_step_runner.py`를 canonical-only 기준으로 정리한다.
- [ ] Step D2: `models.py` synonym과 `erp_order_flags.py` fallback을 제거한다.
- [ ] Step D3: startup compatibility tests와 focused domain tests를 canonical-only 기준으로 갱신한다.
- [ ] Step D4: 필요 시 새 migration 또는 persisted step-key migration을 추가한다.

### Phase E — 최종 검증 및 closeout
- [ ] Step E1: `python -c "import app; print('APP_OK')"` 통과
- [ ] Step E2: `python tools/harness/verify_result.py --json` 통과
- [ ] Step E3: focused pytest 및 startup compatibility 통과
- [ ] Step E4: `/add`, `/edit/<id>`, measurement/shipment/CS/dashboard family manual smoke 완료
- [ ] Step E5: active runtime/product code 기준 `ERP_BETA`, `erp-beta`, `is_erp_beta` residual 0 또는 approved allowlist만 남았는지 확인

## 4. 우선순위 체크리스트

### P0 — 구현 시작 전 반드시 충족
- [ ] 운영 DB 컬럼/인덱스 상태 증거 확보 (로컬에서 사설 DB 직접 연결 불가 — **배포 후 SSH** 또는 대시보드 SQL)
- [x] Railway env snapshot 확보 (production 링크 기준)
- [~] inbound legacy usage 증거 확보 (앱 로그만으로는 불충분할 수 있음)
- [ ] placeholder/draft/drift 데이터 현황 확보 (DB 읽기 필요)
- [x] 회귀 테스트 보강 (Phase A: env/`open=`/estimate-preview 계약 고정; P2+ 삭제는 gate 이후)

### P1 — 지금 바로 정리 가능성이 높은 것
- [x] `erp_beta_default_stage_received` fallback (partial: `erp_order_default_stage_received`만 사용, 미정의 시 `false`)
- [x] `#erp-beta`, `.erp-beta-tabs-nav`, `#erpBetaTabs` stale selector (모바일 CSS)
- [ ] `ERP_BETA_DEBUG` dead read
- [x] `_apply_erp_order_display_overrides` 내부명 (calendar.py; 구 beta 접두 함수명)
- [x] `[ERP_ORDER]` log prefix (`erp_orders_structured.py`; 구 `[ERP_BETA]` 문자열)

### P2 — 운영 증거 확인 후 제거
- [ ] `ERP_BETA_ENABLED` env fallback
- [ ] `ERP_BETA_ENABLED` JS mirror
- [ ] `__ERP_BETA_DRAFT_MODE` JS mirror
- [ ] `data-erp-beta-*` DOM fallback
- [ ] `open=erp-beta` deep-link alias
- [ ] `create_mode=ERP_BETA` request alias
- [ ] `"ERP Beta"` placeholder suppressor

### P3 — DB/bootstrap canonicalization 이후 제거
- [ ] `is_erp_beta` ORM synonym
- [ ] `is_erp_beta` helper fallback
- [ ] legacy schema rename/repair bootstrap
- [ ] `ERP_BETA` persisted step-key logic
- [ ] canonical-only startup compatibility test 전환

## 5. 검증 기준
- [ ] `python -c "import app; print('APP_OK')"` 통과
- [ ] `python tools/harness/verify_result.py --json` 통과
- [ ] `pytest tests/domains/test_erp_order_shared_form_scripts.py -q` 통과
- [ ] `pytest tests/domains/test_erp_shell_fragment_contract.py -q` 통과
- [ ] `pytest tests/domains/test_sqlite_startup_compat.py -q` 통과
- [ ] `pytest tests/domains/test_app_init.py tests/domains/test_app_bootstrap_contract.py -q` 통과
- [ ] `/add`, `/edit/<id>` ERP tab open / draft / save / attachment / payment smoke 정상
- [ ] measurement / shipment / CS page에서 ERP gate ON/OFF 정상
- [ ] active runtime/product code 기준 `ERP_BETA` residual이 approved allowlist 밖에 남지 않음

## 6. 참고 자료
- 관련 결정: `docs/AI_STATUS.md` 현재 상태
- 관련 결정: `docs/harness/policy/DECISIONS.md`
- 관련 인덱스: `docs/ARCHIVE_INDEX.md`
- 관련 스펙: `docs/specs/2026-04-17-erporder-cleanup-and-rename_SPEC.md`
- 관련 기록: `docs/plans/2026-04-14-wave5-batch7-erp-beta-contract-freeze-run-record.md`
- 관련 기록: `docs/plans/2026-04-14-wave5-batch8-erp-beta-rebaseline-run-record.md`

## 7. Live gate evidence (SSOT · 수집 시 이 표만 갱신)

로컬 에이전트가 Railway/운영 DB에 직접 접속하지 못하면 **미확보**로 둔다. 추측으로 체크하지 않는다.

**SSOT 파일:** `docs/harness/evidence/2026-04-18-erp-beta-retirement-gate-evidence.json` (갱신 시 UTC 타임스탬프만 바꾸지 말고, 환경명·deployment id·명령을 함께 적는다.)

| Gate | 확인 항목 | 증거 / 산출물 | 상태 |
|------|-----------|----------------|------|
| G-DB | `orders`에 `is_erp_beta` 컬럼 잔존, `ix_orders_is_erp_beta` 잔존, `is_erp_order`와 dual-column 여부 | 스테이징·운영 각각 `\d orders` 또는 Alembic 현재 head + 실제 스키마 덤프 | **미확보** (사설 DB — 배포 후 `tools/harness/railway_db_gate_snapshot_ssh.py`를 컨테이너에서 실행) |
| G-ENV | `ERP_ORDER_ENABLED` 단독 설정 여부, `ERP_BETA_*` 의존 | Railway Variables 스크린샷 또는 `railway variables` 내보내기 (비밀값 마스킹) | **부분 확보** — production: `ERP_ORDER_ENABLED` / `ERP_BETA_*` **미설정**, `ERP_MOBILE_V2_ENABLED=true`만 존재 (`DATABASE_URL`은 설정됨, 값 비공개) |
| G-IN | `open=erp-beta`, `create_mode=ERP_BETA` 요청 비율 | 앱 로그/프록시/분석에서 7~30일 윈도우 집계 | **약한 신호** — `railway logs -n 3000 --filter "erp-beta"` **0건** (앱 로그에 쿼리스트링이 안 찍힐 수 있음) |
| G-DATA | `"ERP Beta"` placeholder·draft drift | 운영에서 허용하는 점검 SQL/리포트 결과 | **미확보** (G-DB와 동일 블로커) |

### 7.1 수집 절차 (PowerShell · 예시)

- **DB (읽기 전용)**: 배포 가이드에 맞는 `psql` 또는 GUI로 `information_schema.columns` / `\d orders` 확인. 결과를 스펙 표에 날짜·환경명과 함께 붙인다.
- **Railway**: 대시보드에서 Variables 내보내기 또는 CLI로 스냅샷; `ERP_ORDER_DEBUG` 도입 후에도 레거시 `ERP_BETA_DEBUG`는 동일 플래그로 별칭 처리됨(코드: `foms/platform/erp_blueprint.py`).
- **Inbound**: 로그 필드에 `open=` / `create_mode`가 있다면 쿼리 예시를 runbook에 고정한다. 없으면 “로그 미수집”으로 명시하고 대체 증거(지원팀 북마크 감사 등)를 정한다.

### 7.2 Verification commands (자동)

```text
python -c "import app; print('APP_OK')"
python tools/harness/verify_result.py --json
pytest tests/domains/test_erp_order_shared_form_scripts.py -q
pytest tests/domains/test_erp_shell_fragment_contract.py -q
```

게이트 미확보 시 **P2( env/JS/deep-link )·P3(DB/bootstrap)** 배치는 시작하지 않는다.

### 7.3 사용자가 제공하면 G-DB / G-IN / G-DATA를 한 번에 강화할 수 있는 것

1. **스테이징 Railway 프로젝트/서비스 링크** (`railway link`로 해당 환경) — 스테이징 DB에 공개 엔드포인트가 있으면 로컬 스냅샷 스크립트 재시도 가능.
2. **엣지/프록시 접근 로그** (Cloudflare, Nginx, Railway HTTP 로그 등) — `open=erp-beta`, `create_mode=ERP_BETA` 문자열 검색 가능한 샘플 7~30일.
3. **대시보드에서 읽기 전용 Postgres Query** 실행 결과 붙여넣기 (`information_schema` + 선택적 `COUNT` 쿼리) — 에이전트가 DB URL을 직접 받지 않아도 됨.
4. (선택) **운영이 아닌 복제 DB** 또는 **마스킹된 `\d orders`** 텍스트 — dual-column 여부만 확인되면 됨.
