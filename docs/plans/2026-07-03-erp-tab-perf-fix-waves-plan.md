# ERP 탭 성능 근본수정 3-Wave 계획 (2026-07-03)

## 배경 (검증 완료된 근거)

2026-07-03 6-agent 병렬 감사 + 전 항목 코드/운영 재검증 완료. 핵심 실측:

- **실측탭 A-B-A 스왑 5,827ms vs 주문 대시보드 82ms (71배)** — `docs/harness/evidence/stress-compare-2026-07-02T103000-final.json` `tab_stress_l2_headless.aba`
- 운영 로그 DashCache miss 반복 (`summary_counts result=miss compute_ms=21` 연속)
- 압축은 **이미 작동**(운영 wire 실측 HTML=br, CSS=gzip) — 압축 관련 수정 불필요 (기각 finding)
- 네트워크 tail(p95 5-10s) = 한국↔싱가포르 경로, 코드 무관 — **이 계획의 목표 아님**
- baseline eef8e96에도 실측탭 스왑 구조 동일 → 회귀 아닌 **장기 잠복**. 이 계획은 회귀 복원이 아니라 잠복 부채 상환.

목표: **코드가 만드는 지연 제거**. warm 탭 전환 체감(특히 실측탭)과 캐시 히트율 정상화. 네트워크 tail은 범위 외.

## 원칙

- CLAUDE.md 근본수정 원칙: 증상 우회 금지, 각 수정은 원인 제거형.
- **측정 게이트**: Wave마다 수정 전/후 동일 도구로 실측(아래 검증 절), 개선 수치 없으면 머지 금지.
- 브랜치: `deploy` 스테이징 검증 → 사용자 승인 → production 승격 (운영 푸시는 사용자 명시 요청 시에만 — 절대규칙).
- Wave별 독립 커밋(한글 메시지, `git commit -F`), 각 Wave 후 `scripts/ops/pre_push_smoke.ps1` exit 0.

---

## Wave 1 — 실측탭 스왑 파이프라인 (최대 체감, 5.8s → 목표 <500ms)

### 원인 (검증됨)
1. `templates/measurement/partials/dashboard_scripts.html:2-8` — `<script src>` 7개(~83KB+)가 fragment 내부 → `erp-shell.js activateScripts()`가 **매 스왑 전부 재실행** (동적 삽입엔 defer 무효).
2. `static/js/measurement/dashboard-columns.js:12` — 모듈 재실행마다 `var desktopResizer=null` 리셋 → 가드 무력화 → **매 스왑 new ColumnResizer** = getComputedStyle/getBoundingClientRect 연타(강제 리플로우) + `window resize` 리스너 누수.
3. `static/js/runtime/erp-shell.js:51` — `NO_FRAGMENT_CACHE_PATHS=['/erp/measurement']` → 실측만 warm캐시·프리페치 제외, 재방문마다 풀 fetch.
4. (부가) `image-export.js:426` document 리스너 재등록 누수.

대비 정상 패턴: 주문 대시보드 = `static/js/orders/erp-dashboard-entry.js` `window.__fomsErpDashboardBundleLoaded` singleton → 스왑 재실행 0 → 82ms. **이 패턴을 실측에 복제한다.**

### 수정 설계
- **W1-1** `static/js/measurement/measurement-entry.js` 신설(erp-dashboard-entry.js 패턴): `window.__fomsMeasurementBundleLoaded` singleton, 최초 1회만 7개 스크립트 로드(또는 번들), 이후 스왑은 `foms:erp-shell-fragment-swapped` 수신 → 각 모듈의 idempotent `init()` 재호출.
- **W1-2** `dashboard_scripts.html`에서 `<script src>` 7개 제거 → entry 1개만 남김(fragment 내 재실행 대상 최소화). 인라인 부트 블록은 데이터 주입(JSON)만 유지.
- **W1-3** 각 모듈(dashboard.js/mobile.js/dashboard-columns.js/manual-rows.js/image-export.js)을 **재init 함수 추출 리팩터** — 단순 가드 추가가 아님(리뷰 MAJOR-4 반영). 현재 모듈들은 top-level 실행+`readyState` 분기(dashboard.js:670, columns:250)로 매 스왑 재실행에 의존하며, 일부 리스너는 익명 함수라 remove 불가(columns.js:239 `window resize`) → named 함수 + singleton 등록으로 재작성. dashboard.js의 AbortController 미적용 리스너(tbody click:592, input:587 등)는 위임 1회 등록 또는 AbortController로 통일. ColumnResizer는 스왑 시 기존 인스턴스 destroy 후 새 테이블 DOM에 재attach(재생성 비용·리스너 누수 제거). **공수: 모듈당 구조 수정 — Wave 1이 3-Wave 중 최대 작업량임을 명시.**
- **W1-3a (재init 트리거 표준, 리뷰 MAJOR-3 반영)**: 재init 이벤트는 `foms:erp-shell-fragment-swapped` **단일 표준**으로 통일. entry가 이 이벤트 1곳만 구독 → 각 모듈의 `reinit(root)` 호출. 현행 `image-export.js:426`은 `foms:main-content-swapped` 구독(전 탭에서 재실행됨) — entry 이관 시 이 자체 구독 제거하고 entry 경유로 전환. 모듈별 트리거를 계획 없이 혼용 금지.
- **W1-4** `NO_FRAGMENT_CACHE_PATHS`에서 `/erp/measurement` 제거 → warm캐시·프리페치 활성. 단 **선행 게이트**: 제외 도입 커밋 `76ed4a09`("실측 대시보드 중복 날짜 표시 수정") diff 확인 — 중복 표시 원인이 script 재실행(=W1-3이 해소)이었는지 확인 후 제거. stale 방어는 기존 메커니즘(mutation-sensitive TTL `cacheTtlForKey` + focus revalidate + `invalidateFragmentCache`)으로 충족되는지 점검, 부족하면 실측 mutation API 성공 시 `invalidateFragmentCache('/erp/measurement')` 호출 배선.

### 함정 (구현 Worker 필독)
- **계약 테스트 3종 — 전부 필수 갱신 (리뷰 MAJOR-1·2 반영)**:
  1. `tests/performance/test_page_local_defer_contract.py:36` — dashboard_scripts.html script 목록 직접 단언 → entry 구조로 계약 갱신.
  2. `tests/contracts/runtime/test_ptc_physical_exactness.py:151` `test_ptc_committed_root_allowlist_exact` — **exact-set 하드 단언(no extras, no omissions)**. 신설 `measurement-entry.js`를 §2.6.1 allowlist에 **필수 등록**(선택 아님 — 미등록 시 즉시 fail).
  3. `tests/performance/test_perf_regression_guard.py:85-87,162` — **G4 fragment-재실행 leaky script baseline 목록** 보유. measurement script가 fragment에서 빠지면 baseline drift → fail. 제거 항목을 baseline에서 삭제 갱신. (memory: 심볼 이동 시 위치-고정 계약 함정과 동류)
  - `test_measurement_js_contract.py`, `test_erp_runtime_shell_js_contract.py`도 참조 여부 grep 후 정렬.
- **모바일 코호트**: mobile.js는 모바일 v2 전용 로직 — entry에서 코호트/뷰포트 조건 로드 가능(불필요 데스크톱 로드 회피). 단 게이트 3곳 규칙(memory: erp_mobile_v2_cohort_gate)과 충돌 금지.
- fragment 스왑 시 이전 테이블 DOM 참조를 쥔 모듈 상태(예: dashboard-columns의 table 참조) → 재init 때 반드시 새 DOM 재조회. 죽은 참조로 인한 무동작 회귀 주의.
- SW 캐시 phantom(memory: fragment_swap_sw_cache_phantom): 검증은 실제 Chrome + 헤드리스(SW 무) 양쪽.

### 검증 (완료 기준)
1. `python tools/perf/measure_erp_tab_switch.py` + `tools/perf/browser_tab_stress_compare.py` — deploy 스테이징에서 수정 전/후: `measurement_aba` **5,827ms → <500ms** 목표(최소 10배 개선 없으면 원인 재분석).
2. 기능 스모크(gstack browse + 실제 Chrome): 실측탭 3회 왕복 — 날짜 중복 표시 없음(76ed4a09 회귀 방지), 컬럼 리사이즈 동작, 이미지 내보내기 동작, 모바일 큐 렌더, console 에러 0.
3. 리스너 누수 검증: DevTools에서 스왑 10회 후 `getEventListeners(window).resize` 개수 불변.
4. `pre_push_smoke.ps1` exit 0 (defer/PTC 계약 갱신 포함).

---

## Wave 2 — 캐시 유효성 복원 + 실측 N+1 (서버 부하·일관성)

### 원인 (검증됨)
1. `invalidate_all_dashboard_slice_caches()` 호출 **22곳/11파일**(리뷰 실측 정정: erp_orders_structured×4, quest×4, drawing 계열×5, files 계열×4(direct_upload+order_routes×3), shipment×2, field_update, as_orders, mobile_queue_action) → 아무 수정이나 7 family 전멸 → TTL(120s) 무력화 → 상시 miss herd. family 7개 상수({orders,measurement,shipment,construction,history,production,drawing})는 `build_dashboard_cache_key` page 인자와 정합 확인됨(리뷰 통과).
2. `foms/web/orders/dashboard.py:379-407` `order_detail_payload_assembly` slice — fingerprint에 `order_ids` 나열 + compute 0-4ms → **캐시가 계산보다 비쌈**(음수가치).
3. `foms/web/measurement/dashboard.py:308` — `build_mobile_queue_order_row(db,_o,current_user)` `batch_ctx` 미전달 → 모바일 코호트 실측탭 행당 ~5쿼리 × 최대 300행. shipment는 `shipment_dashboard_display.py:124`에서 `build_mobile_queue_batch_context` 사용(정상 패턴).

### 수정 설계
- **W2-1** mutation→family 매핑 테이블 신설(`dashboard_cache.py` 근처 상수): 주문 필드/구조 수정→`orders`+무대 관련탭, 도면→`drawing`+`orders`, quest→소속 무대 family, 파일→`orders`+해당 탭, 출고→`shipment`+`orders` 등. 23개 호출부를 `invalidate_dashboard_family(...)` 조합으로 치환. **보수 원칙**: 판단 애매하면 넓게(과무효화 허용, 과소무효화 금지 — stale이 더 나쁨). `invalidate_all`은 관리자 수동/마이그레이션 용도로만 존치.
- **W2-2** `order_detail_payload_assembly` slice 캐시 제거 → 직접 compute (호출 1곳, 저위험).
- **W2-3** 실측 모바일 큐: 루프 전 `ctx = build_mobile_queue_batch_context(db, rows)` 생성 후 `batch_ctx=ctx` 전달 — shipment 패턴 그대로.
- (부가) `dashboard_cache.py` Redis 클라이언트에 `socket_timeout`/`socket_connect_timeout` 부여 — Redis 딸꾹질 시 요청 무한대기 차단(fail-open 정합).

### 함정
- family 상수명 SSOT: `dashboard_cache.py`의 family 목록과 read-model들이 쓰는 page명 일치 확인(오타=무효화 누락=stale 버그).
- **hold 액션 매핑(리뷰 MINOR-2)**: `mobile_queue_action.apply_queue_hold`는 status만 변경(stage/sync 무변경)이지만 **뱃지 카운트에 영향** → orders+해당 무대 family 무효화에 반드시 포함(누락 시 hold 후 stale 뱃지).
- 무효화 축소 후 **stale 시나리오 테스트 필수**: A탭에서 수정 → B탭 반영 확인(특히 orders 수정→실측/생산 뱃지 카운트).
- W2-3 후 담당자 표시 회귀 주의: 실측은 manager가 user id로 저장되는 케이스 정규화(`normalize_manager_name`) 로직이 루프 안에 있음 — batch_ctx 도입해도 유지.

### 검증
1. `tests/domains/test_shipment_mobile_queue_query_count.py` 패턴 복제 → `test_measurement_mobile_queue_query_count.py` 신설: 300행 기준 쿼리 수 상한 단언(고정 상수 + 행수 무관).
2. 캐시 히트율: 스테이징에서 mutation 1회 후 각 탭 요청 → 로그로 miss가 **관련 family만** 발생 확인. `test_dashboard_cache.py` 확장(매핑 단위 테스트).
3. stale 회귀 스위트: 주문 수정→7개 탭 표시값 일치 스모크.
4. `pre_push_smoke.ps1` exit 0.

---

## Wave 3 — 생산탭 쿼리 + 잔여 서버 비용

### 원인 (검증됨)
1. `foms/services/production_read_model.py:34` — `stage_col`(JSONB path cast) `.in_()` 필터, 인덱스 없음. `models.py:89` `erp_stage_code`(index=True)가 동일 값 보유(`erp_sync_columns.py:37`이 workflow.stage **원값 그대로** 동기화 — 한글 포함, models.py 주석의 "영문코드"는 낡음).
2. `production_read_model.py:112-176` — KPI가 필터셋 **전 행** hydrate 후 파이썬 집계, `total=len(rows)`.
3. `foms/services/context_processors.py:77-87` — ADMIN이면 매 렌더 전체 활성유저 SELECT(캐시 없음).
4. `wdcalculator_db.py:72` pool 10+10 vs 메인 5+5 → 프로세스당 30, ×4 = 최대 120 커넥션(비대칭·과다).

### 수정 설계
- **W3-1 [게이트 선행]** erp_stage_code 정합 검증: 운영/스테이징 DB에서 `SELECT count(*) FROM orders WHERE is_erp_order AND (erp_stage_code IS DISTINCT FROM structured_data#>>'{workflow,stage}')` — 불일치 0 확인. 불일치 있으면 백필 스크립트(배치 UPDATE) 선행. **불일치 검증 없이 필터 전환 금지.** (리뷰 확인: stage 기록 경로 전수(listing/quest/field_update/status/production/construction/cs)가 commit 경계에서 `sync_erp_flat_columns` 호출 — sync 누락 근본결함 없음. `orders/dashboard_read_model.py:250`에 erp_stage_code.in_() 선례 존재.)
- **W3-2** `stage_col.in_(['"고객컨펌"',...])` → `Order.erp_stage_code.in_(['고객컨펌','생산','시공','CONFIRM','PRODUCTION','CONSTRUCTION'])` (JSON따옴표 제거된 원값). f_stage 분기 3곳 동일 전환. `EXPLAIN`으로 인덱스 사용 확인(성능 가드레일 규칙).
- **W3-3** KPI: `total_orders`는 `func.count()`, imminent/overdue 뱃지는 SQL `case` 합산(orders `compute_orders_summary_slice` 기존 패턴 복제). 전행 hydrate 제거.
- **W3-4** admin 유저목록: 모듈 레벨 60s 인메모리 캐시(프로세스별 허용 — 4프로세스 각자 60s면 충분) 또는 드롭다운 lazy API. 1안(캐시) 우선.
- **W3-5** `wdcalculator_db.py` pool_size 10→3, max_overflow 10→3 (계산기 트래픽 << ERP).

### 함정
- W3-2는 **값 SSOT 함정**: stage 신규 값 추가 시 두 표현(JSONB/플랫)이 갈리면 생산탭 누락 — `erp_sync_columns.py`가 유일 기록 경로인지 확인(직접 JSONB 수정 경로 있으면 sync 누락 지점 = 근본 결함, 발견 시 별도 수정).
- W3-5는 견적계산기 동시사용 피크 확인 후(운영 로그) 적용 — 축소로 계산기가 pool_timeout 걸리면 역효과.
- W3-3 KPI 값 회귀: 파이썬 집계와 SQL 집계 결과 동일성 스냅샷 테스트 선행.

### 검증
1. 생산탭 TTFB 전/후 실측(`fragment_tail_ttfb_diagnostic.py` 대상 경로 추가) + `EXPLAIN` Seq Scan 없음.
2. KPI 값 동일성 테스트(고정 fixture로 파이썬 vs SQL 결과 비교).
3. 관리자 계정 탭 전환 스모크.
4. `pre_push_smoke.ps1` exit 0.

---

## Wave 4 — 백로그 (이번 범위 제외, 기록만)

- 실측 500행×2tr eager 상세 lazy화(클릭 시 렌더) — DOM 파싱량 감소, 대공사
- `dashboard_grid.html:431` detail_payload 50개 preload lazy화 + 48KB inline style 정적 CSS 추출
- @import 자식 11개 `?v=` 버전화(+수동 스탬프→해시 자동화), CDN preconnect 4origin, 데스크톱 SW 등록
- personal_board 날짜 필터 SQL화(정확도 버그 겸), trash 페이지네이션, `active_filter` draft 술어 최적화
- 네트워크 tail 근본 = 리전 이전(별도 결정 사안, `docs/guides/NETWORK_EDGE_TAIL_FIX.md`)

## 리스크 매트릭스

| Wave | 리스크 | 완화 |
|---|---|---|
| 1 | 실측탭 JS 재구조 — 기능 회귀(리사이저/내보내기/모바일큐) | 기능 스모크 체크리스트 + 계약 테스트 갱신 + 실제 Chrome 검증 |
| 1 | 캐시 재활성 → stale 표시 재발(76ed4a09 사유) | 도입 커밋 diff 게이트 + mutation invalidate 배선 + 중복표시 스모크 |
| 2 | 무효화 축소 → 과소무효화 stale | 보수 매핑(애매하면 넓게) + stale 스위트 |
| 3 | stage 값 불일치 → 생산탭 주문 누락 | W3-1 정합 게이트 필수 선행 |

## 실행 순서

Wave 1 → 측정 게이트 통과 → Wave 2 → Wave 3. 각 Wave: Worker(Opus) 구현 → Advisor diff·테스트 검증 → deploy 커밋 → 스테이징 실측 → 다음 Wave. production 승격은 전 Wave 완료 + 스테이징 안정 + **사용자 명시 승인** 후.
