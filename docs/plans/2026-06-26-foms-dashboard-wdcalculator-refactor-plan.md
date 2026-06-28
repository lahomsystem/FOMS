# FOMS Dashboard + WDCalculator Refactor Plan
> 작성일: 2026-06-26 | 상태: 구현 진행 중(staging 배포, production 무터치) | 범위: FOMS ERP 대시보드 전체 + WDCalculator
> 재검증: 2026-06-26 deep review 2-pass. 6개 결함 본문 반영(§3.1/§3.5/§3.6/Batch 1·2·7 + §10).
> 진행 현황·배포 커밋: **§11 참조**(2026-06-28 기준, f967ea36까지 deploy 배포).

## 1. What

### 1.1 최종 결과물
ERP 대시보드 6개 축(`/erp/dashboard`, production, construction, measurement, shipment, AS)과 WDCalculator를 기능 변경 없이 리팩터링한다.

목표는 화면을 바꾸는 것이 아니라 다음을 줄이는 것이다.

- 라우트 단일 함수 비대화
- template inline JS 비대화
- WDCalculator `window.*` 전역 초기화 결합
- `.all()` 후 Python 집계/필터 병목
- JSONB/text 검색 hot path
- fragment swap 시 listener 중복/초기화 drift
- WDCalculator settings lost-update와 N+1 조회 위험

### 1.2 CEO 판정
권장안: **단계형 strangler refactor**.

| 안 | 내용 | 판정 |
|---|---|---|
| A. 최소 패치 | N+1, 중복 listener, 일부 `.all()`만 고침 | 단기 효과는 있으나 구조 부채가 남음 |
| B. 단계형 read-model/service 분리 | 기능 freeze 후 slice별 서비스/DTO/JS module로 분리 | 채택 |
| C. 전면 rewrite | WDC/대시보드 UI와 API를 새 구조로 재작성 | 과위험. 운영 회귀 가능성 큼 |

이 계획은 B를 따른다. 한 번에 전면 rewrite하지 않는다. 한 PR은 한 경계만 만진다.

### 1.3 없음 판정
P0 즉시 중단급 증거는 없음.  
5개 카테고리(스파게티, 과대 코딩, 미래 부채, 성능, 나비효과)는 모두 실제 후보 있음.

## 2. Research Inputs

### 2.1 실행한 리뷰/도구
- `python tools/harness/task_classifier.py --repo-root . --profile review --prompt "...refactor plan..." --json`
  - 결과: `route_kind=review`, `level=low`, `verification=light review`
- `python tools/perf/perf_scan.py --audit`
  - 결과: `high=0`, `medium=30`
  - 이번 범위 직접 관련: `foms/api/wdcalculator/blueprint.py:1210`, `foms/web/orders/dashboard.py:642`
- multi-agent read-only review 2개
  - WDCalculator reviewer: WDC frontend/API/settings/DB/test surface
  - Dashboard reviewer: ERP dashboards, shell, template JS, query path

### 2.2 기존 결정/문서 반영
- `docs/specs/2026-04-10-large-file-decomposition-governance_SPEC.md`
  - 한 batch는 한 boundary만.
  - 첫 batch는 structure-only. behavior 변경 금지.
- `docs/plans/2026-04-12-wdcalculator-scripts-decomposition-plan.md`
  - 새 `*-host-bootstrap.js` 금지.
  - WDC는 micro extraction이 아니라 meaningful chunk로 재수렴.
- `docs/plans/2026-04-16-dashboard-micro-cache-execution-plan.md`
  - orders/measurement/shipment cache는 유지.
  - 전체 HTML cache 금지.
- `docs/specs/2026-04-17-erp-shell-fragment-contract_SPEC.md`
  - 9 primary ERP path의 full/fragment 의미 동일 유지.
  - fragment-ready path 계약을 깨지 않는다.
- `docs/guides/PERFORMANCE_GUARDRAILS.md`
  - N+1 금지.
  - JSONB/text ILIKE hot path 금지.
  - fragment-replayed JS listener singleton guard 필수.

## 3. 1:1 Source Review

### 3.1 ERP Orders Dashboard
| 분류 | 근거 | 판단 | 계획 |
|---|---|---|---|
| 스파게티 | `foms/web/orders/dashboard.py:132` route 시작, `:464` summary closure, `:600` attachment/assignee closure | route가 request/query/KPI/cache/render를 모두 담당 | `foms/services/orders/dashboard_read_model.py`로 query/service/DTO 분리 |
| 정합성 위험 | `foms/web/orders/dashboard.py:323` count 후 `:342` page load, `:366-410` Python 2차 필터 | 화면 rows(필터 후 <50) vs total/page(SQL count `:323`)가 어긋남. **f_has_alert/f_alert_type/f_team 설정 시에만 발현**(일반 브라우즈는 일치). `total_orders`는 필터 후 재계산 안 함(:323 SSOT 유지) — 의도된 "약간의 오차 허용"(:322 주석) | **분리 필수**: (1) 구조-추출 PR = 현재 count 동작 그대로 freeze, (2) count 교정 PR = behavior change이므로 별도 baseline·승인. ⚠ **pre-pagination read-model 금지** — 2차 필터는 `_erp_alerts()`+CS오버라이드(structured_data 파생)라 SQL 비표현·전체셋 로드=unbounded scan 회귀. page-bounded 유지가 기본 |
| 성능 후보 | `foms/web/orders/dashboard.py:642` `User.id.in_(...).all()` | perf audit medium. 현재 page-bounded라 즉시 P0는 아님 | query-count guard와 bounded-in proof 추가 |

### 3.2 Measurement Dashboard
| 분류 | 근거 | 판단 | 계획 |
|---|---|---|---|
| 스파게티 | `foms/web/measurement/dashboard.py:121` route, `:214` panel closure, `:420` product item closure | route 안에서 query, fallback, cache payload, row mutation 혼재 | `measurement_read_model.py`로 panel/main/product_items slice 분리 |
| 성능 후보 | `:192` limit 500, `:261` limit 1500 fallback, `:358` second fallback | bounded지만 데이터 증가 시 scan 비용 큼 | SQL window/fallback 기준 고정, EXPLAIN/TTFB gate 추가 |
| 나비효과 | `:388-392` focus row를 절단 전에 삽입 | 검색 카드 계약은 의도된 SSOT | refactor 전 focus_order regression test 필수 |

### 3.3 Shipment Dashboard
| 분류 | 근거 | 판단 | 계획 |
|---|---|---|---|
| 스파게티 | `foms/web/shipment/dashboard.py:230`, `:348`, `:457` | route가 panel query, aggregate, derived payload까지 보유 | `shipment_read_model.py`로 panel/derived/main rows 분리 |
| 성능 후보 | `:311` panel `.all()`, `:352-387` Python aggregate | 14일 window로 완화됐지만 worker/spec 집계가 Python side | SQL aggregate 가능 범위와 cache 유지 범위 분리 |
| 에러 진단 손실 | `:359`, `:370` malformed date를 조용히 continue | 데이터 오염 진단이 안 됨 | malformed count/debug log 추가. 화면은 유지 |

### 3.4 Production/Construction Dashboards
| 분류 | 근거 | 판단 | 계획 |
|---|---|---|---|
| 성능 후보 | `foms/web/production/dashboard.py:146-149` 전체 집합 scan 주석, `:330-331` `len(kpi_rows)` | 이미 별도 wave debt로 명시됨 | SQL aggregate 또는 cached read-model로 이동 |
| 성능 후보 | `foms/web/construction/dashboard.py:75`, `:238-240` all 후 Python pagination | 데이터 증가 시 page 전에 전부 계산 | construction read-model에서 DB count/page를 먼저 고정 |
| 중복 | production/construction body diff는 22 lines | 거의 같은 template 구조 | behavior freeze 후 shared partial 후보 |

### 3.5 AS Dashboard
| 분류 | 근거 | 판단 | 계획 |
|---|---|---|---|
| 스파게티 | `foms/web/cs/as_dashboard.py:269-447` route가 tab/search/count/page/render 담당 | AS tab logic이 커짐 | AS tab/query/count를 `as_dashboard_read_model.py`로 분리 |
| 성능 후보 | `foms/web/cs/as_dashboard.py:188-213` compact search + AS content ilike (`:211` `_sql_compact(...)`) | 기능 필요. **기존 trigram(phase_d `CAST(structured_data AS VARCHAR) gin_trgm_ops`)은 `_sql_compact` 변형+JSON 서브패스라 커버 안 함(non-sargable)** → 정규화 컬럼 정당 | normalized search text 컬럼 + 전용 expression/trigram index로 분리. ⚠ **새 인덱스는 CONCURRENTLY + 세션 advisory lock 필수**(replica INVALID 인덱스 레이스 기록, CLAUDE.md) |
| 과대 코딩 | `templates/cs/partials/as_dashboard_body.html:464`, `:1080`, `:2162-2292` | template가 JS app, save API, upload client까지 담당 | `static/js/cs/as-dashboard.js`로 단계 이동 |

### 3.6 WDCalculator
| 분류 | 근거 | 판단 | 계획 |
|---|---|---|---|
| 성능 P1 | `foms/api/wdcalculator/blueprint.py:1210-1213` match `.all()` 후 estimate N+1 | 즉시 개선 후보 | join/batch 조회 + query-count test |
| 미래 부채 P1 | `foms/api/wdcalculator/blueprint.py:299-416` singleton settings JSON load/save | **필드별 dirty-column UPDATE라 교차필드는 안전**(재검증 확인). 실위험=**동일 필드 동시편집 lost-update**(배열 read-modify-write, version 없음, last-wins). IntegrityError 재시도는 INSERT 레이스만 처리 | Batch 1은 `SettingsService` 경계 **design만**. version 컬럼/row lock/409는 DB migration → **별도 spec**(Stop Rule 준수) |
| 미래 부채 P2 | `wdcalculator_db.py:106-158` runtime DDL | app boot가 migration 역할 수행 | Alembic/init script 이동. app boot는 verify-only |
| 스파게티 P1 | `templates/wdcalculator/partials/wdcalculator_scripts.html:2`, `:47`, `:205` | DOMContentLoaded host가 many globals configure | `WdCalculatorApp` factory + compatibility adapter |
| 과대 코딩 P1 | `static/js/wdcalculator/composition.js:1-4`, `:2024-2103` | "새 host-bootstrap 금지" 주석에도 host wrappers 잔존 | existing chunk를 줄이고 host pair 제거 |
| 정책 위생 (P1→하향) | `static/js/wdcalculator/estimate-lifecycle.js:3428-3429` `bindOrderMatchButtons()` 가드 없음 | **재검증: `handleMatchOrderButtonClick`=IIFE 안정 named ref → `document.addEventListener` 다중 호출은 DOM dedupe → 실 중복바인딩 0.** "re-init 중복 binding 가능"은 사실상 거짓 | 가드 추가하되 **G4 정책 준수 위생 항목**으로 처리. 버그 예산/회귀 위험에서 제외 |
| 과대 코딩 P2 | `templates/wdcalculator/product_settings.html:604-2005`(인라인 1402 LOC), `location.reload()` ×12(`:694,785,1319,1422,1450,1580,1632,1641,1798,1807,1854,1863`) | CRUD/render/log/reload가 한 template script에 집중 | `product-settings.js` API client/state/render 분리 |
| 에러 숨기기 P1 (F5) | `foms/api/wdcalculator/blueprint.py:332,372,412` settings save `except Exception: print(); return False` | **CLAUDE.md "에러 숨기기/bare except 금지" 직접 위반.** 저장 실패 root error가 stdout로만 → 진단 손실 | Batch 1 SettingsService design에 포함: 구체 예외 + 구조화 로깅 + 사용자 메시지 분리 |
| 정보 누출 (F6, 저) | `foms/api/wdcalculator/blueprint.py:1226` order-estimates `jsonify({'message': str(e)})` | 예외 문자열 클라 노출 | N+1 수정 시 동시 정리(generic 메시지 + 서버 로그) |

### 3.7 Fragment/Shell Cross-Cutting
| 분류 | 근거 | 판단 | 계획 |
|---|---|---|---|
| 나비효과 | `foms/services/common/erp_navigation_contract.py:27`, `:39`; `static/js/runtime/erp-shell.js:25`, `:51` | Python/JS path/cache policy 중복 | Python SSOT를 JSON 주입하거나 generated JS로 동기화 |
| 나비효과 | `templates/shipment/partials/dashboard_main.html:1174`, `:1858`, `:1966`; `templates/cs/partials/as_dashboard_body.html:492` | 페이지별 listener 전략 제각각 | shell `init/teardown` registry와 page module contract 도입 |
| 과대 코딩 | `templates/shipment/partials/dashboard_main.html:571-596`, `:2029-2034` | inline localStorage/export listener 등 혼재 | shipment static module로 이동. inline은 config only |

## 4. Architecture Design

### 4.1 Target Shape
```text
request
  |
  v
route parser
  |
  v
dashboard read-model service
  |-- SQL predicates
  |-- cache slice
  |-- batch preload maps
  |-- DTO assembly
  v
template context DTO
  |
  v
Jinja render
  |
  v
page module init
```

라우트는 request parsing과 render만 한다.  
서비스는 SQL, cache, DTO를 담당한다.  
템플릿은 표시만 한다.  
JS는 static module이 init/teardown을 가진다.

### 4.2 WDCalculator Target Shape
```text
wdcalculator_scripts_config.html
  |
  v
static/js/wdcalculator/app.js
  |-- state store
  |-- lifecycle
  |-- form
  |-- pricing
  |-- order matching
  v
window compatibility adapter
```

기존 `window.WdCalculator*`는 바로 삭제하지 않는다. 테스트와 template include가 안정화될 때까지 adapter로 유지한다.

### 4.3 Dashboard Target Shape
```text
foms/web/<domain>/dashboard.py
  -> foms/services/<domain>/dashboard_filters.py
  -> foms/services/<domain>/dashboard_read_model.py
  -> foms/services/<domain>/dashboard_dto.py
```

공통화는 늦게 한다. orders/measurement/shipment/AS/production/construction이 각각 안정화된 뒤 반복이 명확한 부분만 `foms/services/common/dashboard_*`로 승격한다.

## 5. Execution Plan

### Batch 0 - Contract Freeze
- [ ] 현재 URLs full/fragment 200 OK 고정
- [ ] `APP_OK` 고정
- [ ] dashboard count/page/focus/mine/date regression tests 확정
- [ ] WDC save/load/order-match/product-settings contract tests 확정
- [ ] query-count baseline 기록
- [ ] `perf_scan.py --guard` clean 확인

### Batch 1 - WDCalculator P1 Hot Path
- [ ] `/api/wdcalculator/order-estimates/<order_id>` N+1 제거 (`in_()` 배치, 응답 shape 불변)
- [ ] (F6) 같은 핸들러 `str(e)` 노출 제거 → generic 메시지 + 서버 로그
- [ ] `EstimateOrderMatch` 중복 방지 정책 설계
- [ ] settings `SettingsService` 경계 **design만** (version/lock/409는 별도 migration spec)
- [ ] (F5) settings save `except Exception: print()` → 구체 예외 + 구조화 로깅
- [ ] `bindOrderMatchButtons()` 가드 추가 — **G4 정책 위생**(버그 아님, 회귀 예산 제외)
- [ ] 테스트: order-estimates query-count, duplicate match, settings save 실패 로깅 경로

### Batch 2 - Orders Dashboard Read Model
> ⚠ 결함 #2: 현재 total/page(SQL count)와 화면 rows(Python 2차 필터 후)가 alert/team 필터 시 어긋남. 이는 **의도된 기존 동작**. 구조 추출과 count 교정을 한 PR에 섞으면 §2.2 freeze·Stop Rule 위반. **반드시 2단계 분리.**

**Batch 2a (structure-only, behavior freeze)**
- [ ] `erp_dashboard()` request parser와 read-model 분리
- [ ] **현재 count/page/filter 동작을 정확히 그대로 보존** (불일치 포함). Batch 0 baseline = 현재(불완전) count로 고정
- [ ] attachment/assignee map cache slice 유지
- [ ] 테스트: q, focus_order, risk, mine, alert_type, team, page (= 기존 동작 회귀)

**Batch 2b (behavior change, 별도 PR + 승인)**
- [ ] count/page를 화면 rows와 정합되게 교정할지 **결정** (기본 권장: 현상 유지)
- [ ] 교정 시 alert/team 필터 카운트 변경 = 새 baseline·스크린샷·사용자 승인 필수
- [ ] ⚠ pre-pagination read-model(전체셋 로드) 금지 — unbounded scan 회귀

### Batch 3 - Measurement + Shipment Read Models
- [ ] measurement panel/main/product_items slice 분리
- [ ] shipment panel/aggregate/derived/main rows 분리
- [ ] mobile queue row builder batch preload API 설계
- [ ] 테스트: date/range/focus/mine, malformed date log, query-count

### Batch 4 - Production + Construction KPI/Pagination
- [ ] production KPI Python full scan을 SQL aggregate/read-model로 이동
- [ ] construction `kpi_rows` + Python pagination 제거
- [ ] production/construction shared template 후보는 구조 freeze 후 별도 PR
- [ ] 테스트: stage/q/mine/focus, count/page, process_steps

### Batch 5 - AS Dashboard + Shipment/AS Inline JS Extraction
- [ ] AS tab/count/query read-model 분리
- [ ] AS attachment/upload JS를 static module로 이동
- [ ] Shipment inline script를 static module로 이동
- [ ] shell fragment init/teardown contract 도입
- [ ] 테스트: AS tabs, upload fallback, shipment add-row, fragment swap listener duplicate

### Batch 6 - WDCalculator App Chunk Rebaseline
- [ ] `WdCalculatorApp` factory 도입
- [ ] `composition.js` host wrapper 제거 wave
- [ ] `product_settings.html` JS static module 이동
- [ ] product-settings CRUD에서 `location.reload()` 제거
- [ ] 테스트: `tests/contracts/wdcalculator/*`, product-settings no-reload, mobile resize smoke

### Batch 7 - Search/Index Tranche
> ⚠ 결함 F4: 기존 trigram(phase_d/e: `CAST(structured_data AS VARCHAR)`, manager_name)은 AS `_sql_compact` 변형·서브패스를 **커버하지 않음**. 새 인덱스 필요.
- [ ] AS/shipment/WDC order search normalized search field 설계
- [ ] trigram/GIN index 필요 여부 EXPLAIN으로 확정 (기존 phase_d/e 인덱스와 중복·충돌 확인)
- [ ] **새 인덱스 생성은 CONCURRENTLY + `env.py` 세션 advisory lock** (replica INVALID 인덱스 레이스 방지). byte-match SQL + `EXPLAIN`로 사용 확인
- [ ] JSONB text ILIKE fallback 격리
- [ ] 테스트: EXPLAIN no Seq Scan, q/focus behavior

## 6. Stop Rules
- 한 PR에서 API behavior 변경과 template/JS extraction을 섞으면 중단.
- DB migration이 필요하면 별도 spec으로 분리.
- public route, response JSON, template DOM id/class를 깨야 하면 contract test 먼저.
- cache hit/miss 결과가 달라지면 중단.
- fragment swap 후 listener 중복이 발견되면 다음 batch 금지.
- 운영 측정 없이 "성능 완료" 선언 금지.

## 7. Validation

### 공통
- [ ] `python -c "import app; print('APP_OK')"`
- [ ] `python tools/perf/perf_scan.py --guard`
- [ ] `powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` before deploy push

### Dashboard focused
- [ ] `pytest tests/domains/test_dashboard_cache.py tests/domains/test_dashboard_micro_cache_http_fallback.py -q`
- [ ] `pytest tests/domains/test_erp_shell_fragment_contract.py tests/domains/test_erp_runtime_shell_js_contract.py -q`
- [ ] `pytest tests/domains/test_erp_dashboard_active_filter.py tests/domains/test_erp_dashboard_history_redirect.py tests/domains/test_erp_dashboard_search_service.py -q`
- [ ] `pytest tests/domains/test_measurement_js_contract.py tests/domains/test_measurement_slice_contract.py -q`
- [ ] `pytest tests/domains/test_shipment_dashboard_mobile.py tests/domains/test_erp_mobile_layout_and_shipment.py -q`
- [ ] `pytest tests/domains/test_as_dashboard_mobile.py tests/domains/test_erp_as_dashboard_tabs.py -q`
- [ ] production/construction focused mobile tests

### WDCalculator focused
- [ ] `pytest tests/contracts/wdcalculator -q`
- [ ] `pytest tests/domains/test_wdcalculator_product_settings.py tests/domains/test_erp_wdc_estimate_sync.py -q`
- [ ] Node contract checks for changed WDC chunk
- [ ] order-estimates query-count regression
- [ ] settings lost-update concurrency regression

### Performance proof
- [ ] staging/prod server TTFB before/after
- [ ] EXPLAIN for q/date/mine/focus hot queries
- [ ] Chrome fragment navigation check, not headless-only

## 8. Not In Scope
- 새 UI/UX redesign
- WDC pricing rule 변경
- ERP workflow stage semantic 변경
- production push
- full rewrite
- unrelated channel/notification perf audit findings
- repo-local `.agents/skills/gstack` 복원

## 9. Final Inspection Checklist
- [ ] 발견 5개 카테고리 모두 계획에 반영됨
- [ ] `없음`으로 판단한 P0 즉시 중단급 없음 명시됨
- [ ] multi-agent findings 반영됨
- [ ] 기존 WDC decomposition direction lock과 충돌 없음
- [ ] dashboard micro-cache 유지
- [ ] ERP shell 9 primary contract 유지
- [ ] 한 batch 한 boundary 원칙 유지
- [ ] 최종 검증 명령 명시됨

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `gstack-plan-ceo-review` | 범위/전략 | 1 | CLEAR | 전면 rewrite 거부, 단계형 strangler refactor 채택 |
| Codex Review | `multi_agent_v1` | 독립 2nd opinion | 2 | CLEAR_WITH_FINDINGS | WDC 9건, Dashboard 9건. 모두 본 계획에 흡수 |
| Eng Review | `gstack-plan-eng-review` | 아키텍처/테스트/성능 | 1 | CLEAR_WITH_FINDINGS | P1/P2 batch와 검증 게이트로 전환 |
| Design Review | `not-run` | UI/UX visual audit | 0 | NOT_REQUIRED | 화면 redesign 없음. JS extraction 시 별도 필요 |
| DX Review | `not-run` | 개발자 경험 | 0 | NOT_REQUIRED | 구현 전 계획 단계 |

- **VERDICT:** CEO + ENG plan cleared for staged implementation. Code change는 아직 없음. 구현은 Batch 0부터 시작.
NO UNRESOLVED DECISIONS

## 10. Deep Re-Verification (2026-06-26, 2-pass)

직접 코드 트레이스(Read/Grep)로 플랜 클레임 재검증. 사실 정확도 ~95%. 6개 결함 본문 반영 완료.

### 직접 검증한 load-bearing 클레임 (VERIFIED)
- N+1: `blueprint.py:1210-1213` `.all()`→루프 per-row `.first()` — REAL.
- orders count/page 불일치: `dashboard.py:323`(SQL count)·`:342`(page)·`:366-410`(Python 2차 필터), `:451+`까지 재계산 없음 확인 — REAL (alert/team 필터 시만 발현).
- settings: `:299-416` 각 save = 단일 row 로드→1필드 dirty→commit. dirty-column UPDATE라 교차필드 안전. IntegrityError 재시도=INSERT 레이스. 실위험=동일필드 동시편집 lost-update.
- runtime DDL: `wdcalculator_db.py:170`(repo ROOT) `create_all()` at boot — REAL.
- composition.js host wrapper: `:2102-2103` `window.WdCalculatorEstimatesEarlyHostBootstrap` assign — REAL.
- 기존 trigram: `migrations/versions/phase_d_trgm_indexes.py:53`, `phase_e_trgm_perm_indexes.py` 존재. AS 서브패스 미커버 확인.
- 테스트 게이트 15개 + `tests/contracts/wdcalculator/*` 전부 실재.

### 정정/하향
- **나비효과 P1 → 정책 위생**: `estimate-lifecycle.js:3429` 가드 없음은 사실이나 `handleMatchOrderButtonClick`=안정 named ref → `document.addEventListener` 다중 호출 DOM dedupe → 실 중복바인딩 0. 호스트 wrapper 3블록(`composition.js:873/995/1170`) 경유해도 동일 ref. 가드는 G4 위생만.

### 신규 결함 (1차 미포착)
- **F4** AS Batch 7 인덱스 안전성(CONCURRENTLY+advisory lock) 누락 → 반영.
- **F5** `blueprint.py:332/372/412` settings save bare except+print = "에러 숨기기" 정책 위반 → Batch 1 반영.
- **F6** `blueprint.py:1226` order-estimates `str(e)` 클라 노출 → Batch 1 반영.

### 경미 (문서 정확도)
- 플랜 경로 표기: 실제 `foms/web|api/...` (CLAUDE.md `apps/` 설명 stale). `wdcalculator_db.py`는 repo ROOT.
- §3.3 shipment `:230`은 route 시작(closure 아님), 실제 closure `:348`.

### 최종 조치 매트릭스
| # | 결함 | 조치 | Batch |
|---|---|---|---|
| 1 | 리스너 가드 과대 | P1→정책 위생 강등 | 1 |
| 2 | count/page 불일치 | 2a 구조freeze / 2b count교정 분리, baseline=현재 count | 2 |
| 3 | OR 함정(pre-pagination) | 단일 결정(현상 freeze 권장), unbounded 금지 | 2 |
| F4 | AS 인덱스 | CONCURRENTLY+advisory lock 명시 | 7 |
| F5 | bare except+print | 구체 예외+구조화 로깅 | 1 |
| F6 | 예외 누출 | str(e) 제거 | 1 |

**안전 착수**: Batch 0~1 (N+1·settings design·DDL·F5·F6). **Batch 2 진입 금지** until #2·#3 분리 확정.
REVERIFIED — 6 FINDINGS APPLIED

## 11. Implementation Progress (staging 배포 — 2026-06-28 기준)

전부 `deploy`(staging)에만 푸시, `production`(현재 1de4e265) 무터치. 매 슬라이스 공통 절차:
flat service 모듈로 **verbatim 추출** + cache 키·fingerprint·get_or_compute는 라우트 유지(lambda 위임)
+ 미사용 import 정리 + APP_OK + 도메인테스트 + 계약(permissions/namespace/runtime) + perf guard(high=0)
+ pin grep + 독립 cavecrew-reviewer 1:1 + pre_push_smoke(247) + push deploy + production 불변 확인. **무회귀.**

### 완료 (deployed)
| Batch | 슬라이스 | 커밋 | 산출 모듈 |
|---|---|---|---|
| 1 | WDC order-estimates N+1 제거·F5(로깅)·F6(str(e) 제거)·G4 가드 + query-count test | f90c8230 | blueprint in-place |
| 2a-1 | orders request 파서 | b0bdbfa0 | services/orders/dashboard_filters.py |
| 2a-2 | orders SQL 쿼리빌드 | 256dd931 | services/orders/dashboard_read_model.py |
| 2a-3 | orders summary 집계 | c19bf7f8 | dashboard_read_model.py |
| 2a-2 후속 | mine-path 계약 갱신 | 57714528 | (test) |
| 2a-4 | orders 첨부/담당자 맵 | 2ab6c01b | dashboard_read_model.py |
| 2a-5 | orders 행 DTO 조립 | 2365ab38 | services/orders/dashboard_dto.py |
| 3-1 | measurement 파서 | c0ab3464 | services/measurement_dashboard_filters.py |
| 3-2 | measurement panel 집계 | 883a4a0a | services/measurement_read_model.py |
| 3-3 | measurement product_items | 71ae3d2b | measurement_read_model.py |
| 3-8 | measurement 날짜창 매칭/표시 헬퍼 | 7f23f285 | measurement_read_model.py |
| 3-9 | measurement 메인 rows 조립(+mine fallback 버그수정·회귀test) | bf4ddbb3 | measurement_read_model.py |
| 3-4 | shipment 파서 | 55a00c0d | services/shipment_dashboard_filters.py |
| 3 §3.3 | shipment malformed 시공일 진단 로그 | 5b296a9c | in-place |
| 3-5 | shipment 도메인 헬퍼 service화 | 6047da78 | services/shipment_dashboard_helpers.py |
| 3-6 | shipment panel aggregates | 114a7e4b | services/shipment_read_model.py |
| 3-7 | shipment panel derived | b12db787 | shipment_read_model.py |
| 4-1 | construction 파서 | b3dd92b8 | services/construction_dashboard_filters.py |
| 5-1 | AS 상단 파서 | adf10125 | services/as_dashboard_filters.py |
| (doc) | §11 진행현황 추가 | cafd538d | (plan) |
| 5-2 | AS 탭/카운트 조건 헬퍼 service화 | c5ff3f15 | services/as_dashboard_helpers.py |
| 4-2 | construction 행 DTO + 단계표시 헬퍼 service화 | 6978a292 | services/construction_dashboard_display.py |
| (doc) | §11 진행현황 갱신(5-2·4-2) | a59a5d85 | (plan) |
| 5 | AS SQL expression 헬퍼 분리 | 4a82bbb6 | as_dashboard_helpers.py |
| 5 | AS count context read-model 분리 | 0378e4b8 | as_dashboard_read_model.py |
| 5 | AS 탭 SQL 조건 context read-model 분리 | e97b7d9b | as_dashboard_read_model.py |
| 5-3 | AS row 표시필드 보강 블록 display화(+시공자명 정규화) | 4bbe8b76 | as_dashboard_display.py |
| 4-3 | production 요청 파서 분리 | b0d59829 | services/production_dashboard_filters.py |
| 4-4 | production read-model(query/counts/kpi/attach/paginate) | 8c51d9ef | services/production_read_model.py |
| 4-5 | production 행 DTO + 단계표시 헬퍼 display화 | adc45fde | services/production_dashboard_display.py |
| 4-4 후속 | production mine-path 계약 갱신 | a58fb149 | (test) |
| 3-10 | shipment 행 보강·정렬·모바일큐 빌더 display화 | f967ea36 | services/shipment_dashboard_display.py |

**도메인 상태**: orders(파서+read-model+dto 완성, 라우트 1015→640), measurement(파서+read-model 완성),
shipment(파서+헬퍼+read-model+행보강·정렬·모바일큐 display 완성), AS(파서+SQL expr/count·tab context read-model+행표시 display 완성),
construction(파서+행DTO·단계헬퍼), production(파서+read-model+display 완성, 라우트 337→134).
Batch 0 contract freeze는 기존(active_filter/history/search/cache/slice/mobile/focus)+신규 파서 단위테스트로 충족.

### 남은 작업 (미착수 — 전부 고위험/승인)
- **Batch 2b** orders count 정합성 — behavior change, **사용자 승인 필요**.
- **Batch 3 잔여** shipment mobile queue row builder의 per-row→batch preload 최적화(behavior change, 선택). ※ display 추출(3-10)로 verbatim 분리는 완료.
- **Batch 4** production/construction KPI Python-scan→SQL aggregate·pagination 교정 — behavior change(승인 필요).
  ※ production/construction 구조-추출(파서/read-model/display) + shipment display(3-10) 완료. KPI/pagination 본체만 잔여. **백엔드 구조-only 안전영역 소진.**
- **Batch 5 잔여** AS/shipment inline JS→static module, shell init/teardown contract — frontend(JS 단위테스트 약함, 사용자 방향확인 필요).
- **Batch 6** WDC app chunk(composition.js host wrapper, product_settings.html JS, location.reload×12) — frontend.
- **Batch 7** search normalized field + trigram index(CONCURRENTLY+advisory lock).

### 운영 함정 (실행 중 확인됨)
- 동시 Cursor 세션 git 레이스 → commit/push 전 reflog 확인.
- 위치-고정 계약 테스트(foms_namespace_surface·test_erp_permissions·slice_contract의
  `extract_all_measurement_dates`·`self_measurement_four_checks_done` 등) → 심볼 이동 시 pin 깨짐 주의.
  (production read-model 이전 시 test_erp_permissions mine-path 계약이 production_read_model.py도 합쳐 읽도록 갱신 — orders 선례 동일.)
- foms.services 패키지 standalone 순환(flat 모듈도 영향, app 컨텍스트선 정상) → unit test는 app 선로딩 의존.

DEPLOYED THROUGH f967ea36 — PRODUCTION UNTOUCHED (현재 1de4e265; 기존 400be33a에서 운영 승격됨, 본 세션은 production 무터치)
