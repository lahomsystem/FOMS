# FOMS 전체 성능 검사 원장 (2026-10-01)

> 요청: "FOMS 전체 성능 검사 — 모든 페이지 로딩 속도·실행 속도, 느려진 곳, 빨라지게 할 방안"
> 방식: 6개 트랙 병렬(서브에이전트) + 감독자 코드 재확인. **조사만 했고 코드는 고치지 않았다.**
> 기준 코드: origin/deploy `51a8858fe`(스테이징), origin/production `88350fef1`(운영). 로컬 체크아웃은 origin/deploy 보다 166 커밋 뒤처져 있었다 — 아래 경로:행은 전부 origin 기준이다.
> 상세 원자료: 트랙 A `2026-10-01-full-perf-audit/A-staging-server-ttfb.md`, 트랙 D `2026-10-01-full-perf-audit/D-production-http-logs.md`. 나머지 트랙(B·C·E·F)은 보고 파일이 없어 이 원장이 유일한 기록이다.

## 트랙과 범위

| 트랙 | 범위 | 대상 | 접근 |
|---|---|---|---|
| A | 서버 응답(TTFB·render 헤더) 104경로 × 5회 | 스테이징 | claude_master 로그인, GET 만 |
| B | 화면 자산·브라우저 실행·탭 전환 | 스테이징 | Playwright headless Chrome, GET 만 |
| C | DB 쿼리·인덱스·EXPLAIN | 스테이징 DB | 읽기 전용 세션 |
| D | 실사용 HTTP 로그 30일(125만 건)·지표·RUM | 운영 + 스테이징 | Railway GraphQL query 만 |
| E | 서버 코드 hot path·스캐너 63건 분류·Jinja 컴파일 | origin/deploy 트리 | 로컬 실행 |
| F | 워커·크론·SIDEFX 실행 시간·외부 호출 | 운영 로그 30일 | Railway GraphQL query 만 |

운영은 앱 로그인·DB 접속을 하지 않았다(요청이 운영 측정을 명시하지 않음). 운영 수치는 전부 Railway 로그·지표에서 왔다.

**로그 시간의 의미(트랙 D 확인)**: Railway httpLogs 의 `totalDuration` 은 싱가포르 엣지→오리진 구간이라 한국↔싱가포르 네트워크가 들어 있지 않다(`upstreamRqDuration` 과의 차이 99% 가 1ms 이하, 앱 `req_duration` 로그와 ±2%). 아래 운영 ms 는 서버 처리 시간이다.

## 우선순위 표 (실사용 영향 × 근거 강도)

표기: [실측] 로그·EXPLAIN·브라우저에서 잰 값, [추정] 코드·계산으로 낸 값, (확인) 감독자가 코드에서 직접 재확인.

### P1 — 실사용 영향이 크고 근거가 겹치는 것

**P1-1. 실측 탭 `/erp/measurement` — 운영 실사용 1위, 서서히 느려지는 중**
- 운영 30일 [실측]: 21,052건, p50 531 · p95 2,229 · p99 2,827ms. 사용자가 응답 전에 끊은 요청 913건(4%). 9월 첫 주 → 마지막 주 p50 376→607, p95 1,713→2,445. `measurement_panel_assembly` 캐시 miss 계산이 948→1,388ms 로 거의 직선 증가(계단 아님 = 데이터 비례). 30일 계산 시간 합 10,122초로 전 경로 1위. (D)
- 원인 1 [실측]: 날짜 보충 쿼리가 날짜마다 `CAST(structured_data AS VARCHAR) ILIKE '%날짜%'` 를 OR 로 붙인다(최대 42개, 범위 모드 279개). 429~486ms · 19,206 buffers(orders heap 의 30배 = TOAST 풀기), 결과 2행. 이 가지만 빼면 2.0ms · 303 buffers. 날짜로 걸린 표본 12건은 실측일이 아니라 created_at·sent_at 같은 기록 시각 오탐이었고, 실측일 있는 ERP 주문 1,801건은 전부 `order_schedule_dates` 행이 이미 있다. `foms/services/measurement_read_model.py:218-233`, 호출 `:290`·`:466` (C, E, 확인)
- 원인 2 [실측]: 렌더마다 네이버 발송 미리보기를 캐시 없이 재계산 — raw_snapshot 을 통째로 읽고, 사용자와 무관한 결과를 사용자마다 계산. 실측 탭 쿼리 12개 중 4개. `foms/web/measurement/dashboard.py:127`·`:585` → `bulk_dispatch.py:814`·`:1179` (E)
- 원인 3 [실측]: 패널 캐시 키에 `selected_date` 가 들어가 날짜칩마다 콜드. 날짜칩 첫 클릭 801~886ms(5/5회), 웜 160~175ms. 패널 범위는 날짜와 무관(`measurement_dashboard_filters.py:86-87`), 이 값은 선택 표시에만 쓰인다(`measurement_read_model.py:355`). `foms/web/measurement/dashboard.py:266` (A, 확인)
- 콜드 로드 [실측]: 엔트리 체인이 스크립트 12개를 하나씩 받아 1,154→2,399ms(약 1.25초). `static/js/measurement/measurement-entry.js:55-56` (B)
- 계측 공백: 이 라우트에 EPT 헤더가 없다(`measurement/dashboard.py:180`). (A, E)
- 방안: ① blob 가지 제거 → `order_schedule_dates` 로 대체(486→2ms, 제거 전 "blob 에만 있는 진짜 실측일" 데이터 대조) ② 미리보기를 날짜 키 30~60초 공유 캐시 ③ 캐시 키에서 `selected_date` 제거 ④ 엔트리 체인 병렬 삽입(`async=false`) ⑤ EPT 헤더·phase 추가.

**P1-2. 대시보드 캐시가 하루 500~1,300번 통째로 비워진다 — 적중률 38~53%**
- 운영 [실측]: 무효화 하루 500~1,300회, 캐시 hit 율 늘 38~53%. miss 폭풍(짧은 몰림)은 없었다(분당 최대 73). (D)
- 원인 (확인): `invalidate_all_dashboard_slice_caches()` 를 저장 경로 13곳에서 부른다 — `foms/api/cs/as_orders.py:118`, `drawing/erp_orders_draftsman.py:443`, `erp_orders_structured.py:1214·1776·1904·1991`, `orders/call_log.py:231`, `orders/copy.py:77`, `orders/field_update.py:1001`, `quest.py:196·468·658·787`. 비우는 방식은 SCAN 후 키마다 DELETE 1회(`foms/services/common/dashboard_cache.py:478-499`)라 저장 요청 안에서 Redis 를 키 수만큼 왕복. 한 건 저장이 전 사용자 7개 탭 캐시를 비운다. (E)
- 이 항목이 P1-1·P1-3·P2-2 의 miss 비용을 증폭한다.
- 방안: ① 13곳을 바뀐 단계의 family 만 비우게(`invalidate_order_dashboard_families` 류, 계약 테스트 필수 — 덜 비우면 최대 300초 옛 숫자) ② family 세대 번호(INCR 1회) 방식으로 SCAN+DELETE 제거.

**P1-3. 통합 검색·과거 이력 검색 — 09-29 #439 이후 느려짐, 인덱스를 막는 조건 4개**
- 운영 [실측]: #439(`3038c5276`, 09-29 11:19 KST) 이후 `/api/foms/search/fragment` p50 516→636, p95 757→984. `/erp/history` p50 452→657, history `page_rows` 417→611ms(+47%). (D)
- 원인 [실측]: #439 가 이력·통합 검색을 `erp_order_dashboard_search_predicate` 로 바꿨는데(확인: diff), 이 OR 20가지 중 4가지에 맞는 인덱스가 없어 다른 trgm 인덱스까지 전부 못 쓴다 — `Order.id.cast(String).ilike`(`erp_dashboard_search.py:190`), `parties.buyer.name`·`.phone`(`:178-179`, 08-20 `872a670ee` 추가), `parties.manager->>'name'`(기존 인덱스는 `->` 형태라 불일치). 155~218ms · 약 38,100 buffers(heap 의 59배). 4가지를 빼면 0.60ms · 96 buffers(약 270배). 전화 숫자 검색 `erp_phone_digits LIKE '%x%'`(`:45`)도 btree 로 못 탄다. (C, 확인)
- 승격 전 주의: 스테이징에만 있는 `131f0c3b4`("검색 결과 위에 과거 이력 N건 더")가 대시보드 검색 때 이력 건수 질의를 추가한다 — 같은 느린 술어를 다시 타는지 승격 전에 확인. (D)
- 방안: 인덱스 4개 CONCURRENTLY(buyer name·phone `->>`, manager `->>'name'`, `erp_phone_digits` trgm) + id 가지는 숫자일 때만 `id = n`. 위험: id 부분 일치 동작이 바뀜(제품 판단). **DB 마이그레이션 = 코어 변경, Spec → 승인 필요.**

**P1-4. 출고 대시보드 `as-recommendations/prewarm` — 요청 하나가 평균 8초 web 을 붙잡는다**
- 운영 [실측]: 835건, p50 7,866 · p95 15,914 · 최대 23,582ms. 30일 내내 같은 수준(악화 아님, 원래 느림). web 을 월 1.8시간 점유, 한 인스턴스에서 최대 7개 동시. 출고 대시보드가 브라우저 유휴 시간에 스스로 보낸다. (D, F)
- 원인: 진짜 N+1(`foms/api/shipment/recommendations.py:472`) + 외부 호출. `/api/orders/nearby` 도 p50 9.0s, 카카오 길찾기 최대 15개 병렬에 timeout 없음(`nearby.py:116`, `erp_map.py:678`). (E, F)
- 방안: N+1 제거, 외부 호출 전 DB 세션 반환, 길게는 rq 잡으로 이동(현재 rq 1개라 별도 큐 필요).

**P1-5. AS 탭 — PC 에서 숨은 모바일 목록이 프래그먼트의 52%**
- 스테이징 [실측]: 탭 전환 다음 페인트 398ms(9탭 중 최장), 세션 첫 진입 950ms, long task 118ms. DOM 6,827개 중 61% 가 PC 에서 숨어 있고, `section.erp-as-mobile-list` 하나가 숨은 노드 3,643개 · 279KB. (B)
- 원인 (확인): 다른 탭(시공·도면·실측·대시보드)은 `{% if erp_mobile_v2_enabled and mobile_width_surfaces %}` 로 광폭 PC 에서 모바일 목록을 빼는데, AS 만 CSS `d-md-none` 으로 숨기기만 한다. `templates/cs/partials/as_dashboard_body.html:445`
- 방안: 같은 가드로 감싸기. 효과 [추정] 페인트 398→200~250ms, 첫 진입 950→약 550ms. 위험 낮음, 난이도 낮음.

### P2 — 효과가 분명하지만 범위·위험이 더 큰 것

**P2-1. 모든 대시보드의 `active_filter` 가 JSONB `meta.draft` 를 매번 풀어 읽는다**
- [실측]: 그대로 15.7ms · 3,331 buffers, 조건을 빼면 2.7ms · 645 buffers(4~5배). ERP 대시보드 쿼리 4개가 각 16~21ms → 4~5ms, 완료 API 20.2 → 6.5ms. (C)
- 위치 (확인): `models.py` `erp_draft_predicate` 의 `structured_data[("meta","draft")]`.
- 방안: 사본 컬럼 `erp_meta_draft`(GENERATED STORED 권장). 위험: 스테이징에 `meta.draft=true` 인데 status≠DRAFT 인 행 39건 — 결과 동일성 테스트 필수. **마이그레이션 = Spec → 승인.**

**P2-2. 네이버 수집 작업대 — render 예산(500ms) 초과, 데이터 비례로 느려짐**
- 스테이징 [실측]: `/admin/naver-ingest/triage` render 625ms, 이력 탭 559ms. `wb_work_groups` 472~550(09-11 기록 308~355), 그 안 `wg_sibling` 172~242 · `wg_fetch` 146 · `wg_group_queue` 106. 처리 묶음 214→319 로 늘었다. 배지 `/triage/pending-count` 콜드 674~757ms(코드 주석의 08-24 값 113ms 의 5배+). (A)
- 운영 [실측]: triage p50 466 · p95 1,401, pending-count 8,377건 p50 123. (D)
- 원인: ① 이력 탭은 처리 목록을 그리지 않는데 전체를 계산(`foms/web/admin/naver_ingest.py:2509-2510`, 템플릿 `naver_workbench.html:775`) ② 이미 읽은 행의 큰 JSON 을 다시 통째로 읽음(`:3586` → `:3924-3928`) ③ 배지 캐시가 프로세스 메모리 30초라 프로세스 4개가 각자 콜드 계산(`triage_count.py:29`, 확인) ④ 큐 쿼리가 raw_snapshot 을 통째로 실어 출력 4.7MB, 직렬화만 34ms(`naver_ingest.py:1800-1822`). (A, C, E)
- 방안: 이력 탭은 배지 캐시 값만 쓰기, sibling 재읽기 제거(두 표시 모드 동일 결과 규칙 `:3563` 유지), 배지 Redis 공유 캐시, 큐는 `_snapshot_projection`(`:1722`)·defer.

**P2-3. 탭 전환마다 공용 셸 스크립트 21~28개 재실행 + 메모리 누적**
- 스테이징 [실측]: 스왑마다 200~430KB 스크립트 재실행, Alpine·htmx 재초기화. 출처: 각 프래그먼트의 `erp_mobile_shell.html` include → `foms_app_shell.html:13-26` → `erp-shell.js:312-342` `activateScripts`. `erp_mobile_v2_enabled` 는 코호트 판정이라 광폭 PC 에서도 켜진다. 이력↔완료 100회 왕복 시 GC 뒤 heap 1.9→69.6MB, document 리스너 139→335. 완료 탭 인라인 스크립트(`templates/cs/partials/completion_scripts.html`)만 막아도 20스왑 뒤 16.7→6.1MB. (B)
- 방안: 공용 셸 스크립트 1회만 실행(레이아웃으로 이동 또는 `activateScripts` 에서 건너뛰기) — 스왑당 −10~37ms, 리스너 누적 정지 [실측 A/B]. 완료 탭 누수는 힙 스냅샷으로 붙잡는 경로 찾기.

**P2-4. 콜드 로드(배포 직후·캐시 비었을 때)**
- [실측]: 화면당 자산 124~158개, 대시보드 1,111KB. CSS 직렬 3단(HTML 407 → erp-pro 528 → 01-intro-tokens 662 → foms-tokens 793ms). 엔트리 체인 직렬 1.2초대(실측·대시보드·출고). 자산 230개 Last-Modified 가 전부 배포 시각(배포마다 재다운로드, 단 SW cache-first `static/sw.js:86-89` 덕에 체감은 작음). (B)
- 운영 RUM [실측]: LCP p95 9월 초 약 1.9초 → 09-22~25 2.6~3.7초(경고 3회) → 현재 2.3~2.6초. LOAD p95 약 2.0 → 3.7~4.4초. 같은 시기 서버 시간에는 계단이 없다 → 서버 밖 원인. (D)
- 방안: ① 엔트리 체인 병렬 삽입 `static/js/measurement/measurement-entry.js:55-56`, `static/js/orders/erp-dashboard-entry.js:47-48`, `static/js/shipment/shipment-entry.js:47-48` [추정 콜드 −0.8~1.2초] ② 결제 아이콘 PNG 4개(`static/images/pay-*.png`, 합 673KB, 640px 원본을 40px 로 표시)를 80px 로 → 27KB (확인) ③ `erp-pro/01-intro-tokens.css:4` 의 무버전 `@import foms-tokens.css` 는 `layout_head.html:207` 의 `?v=` 링크와 URL 이 달라 같은 파일을 두 번 받는다(확인 — 파일 주석은 "토큰 브리지 계약 `test_token_alias_bridge`" 때문에 남겼다고 적음, 제거 전 그 계약 확인) ④ 1단 @import 를 head `<link>` 로 펼치기 ⑤ `tablet-measure-form.js`(`layout_scripts.html:99`)·flatpickr·socket.io 를 쓰는 화면에서만. 인라인 `<script>` 를 외부+defer 로 빼는 것은 **금지**(2026-07 DCL 10초 회귀 전례).

**P2-5. Jinja 미리 컴파일 목록이 ERP 9탭과 어긋남 + 워커까지 예열**
- [실측]: 템플릿 278개 전부 컴파일 3.9초. 현재 목록 11개(`foms/services/common/template_warm.py:30`, 확인)는 9탭 템플릿(include 포함 136개)의 91% 를 안 덮는다 — 출고 `dashboard_main` 108ms, `as_dashboard_body` 96, `dashboard_grid` 95 등이 빠짐. 프로세스당 9탭 첫 방문 추가 시간 928ms → 9탭을 다 데우면 116ms. 운영 web 은 2 replica × gunicorn 2 = 4 프로세스, `--preload` 없음. 바이트코드 캐시를 쓰면 278개 전부 0.25초. (E)
- 반대로 WORKER 는 자식 6개가 각자 앱 전체를 불러오고 예열(1.7s씩)까지 해 부팅이 CPU 1개 한도에 1~2분 붙어 있다(`app_factory.py:310-311`). (F)
- 방안: 목록을 9탭 include 전체로 자동 계산 + Docker 빌드 때 바이트코드 캐시, 예열은 web 프로세스에서만.

**P2-6. 워커 재배포 공백 — 큐를 처리하는 프로세스가 0개인 시간 월 50분**
- 운영 [실측]: WORKER 30일 244회 재배포(주로 08~16시). 새 rq 준비 p50 20s · p90 32s 인데 옛 컨테이너는 약 7초 뒤 내려감(WORKER 는 healthcheck 없음) → 공백 157회, p50 15.5s, 최대 248s, 합계 50분(업무시간 45분). 최대 248s 는 09-30 16:35 KST — 새 컨테이너가 Redis 에 3.5분 연결 실패, 워커 감시 push 2건 실제 발송. (F)
- 방안: ① `worker_supervisor.py:76-123` 에서 rq 먼저 띄우고 나머지 루프 10~15초 늦게 ② 예열 web 만(P2-5) ③ `RAILWAY_DEPLOYMENT_OVERLAP_SECONDS`(운영 설정 변경 = 사용자 승인) ④ WORKER CPU 한도 1→2. 위험: 겹치는 동안 루프 두 벌(수집·정산은 같은 결과, 자동발송은 DB 로 막힘).

**P2-7. timeout 없는 외부 호출 — 무한 대기 가능**
- (확인) 웹푸시 `foms/services/notifications/push_sender.py:503`·`:753` `webpush(...)` 에 timeout 인자 없음(pywebpush 기본 None). SIDEFX 단일 루프에서 걸리면 전달·하트비트·감시가 모두 멈출 수 있다 [추정].
- (확인) 카카오 길찾기 `foms/services/common/address_converter.py` `calculate_route(..., timeout=None)` 기본값을 `erp_map.py:678`·`nearby.py:116` 이 그대로 쓴다 — web 요청이 DB 커넥션을 쥔 채 기다린다.
- 나머지는 timeout 있음: 네이버 30s(재시도 3), R2 10/15s, solapi 5s, 카카오·채널톡 10s.
- 방안: `webpush(timeout=10)`, 길찾기 3~5초. 위험·난이도 낮음.

### P3 — 원인 미확정·조사 필요·작은 것

**P3-1. 09-09 KST 부터 HTML 화면에만 느린 꼬리가 생겼다 — 원인 미확정**
- 운영 [실측]: p50 은 그대로인데 p95 가 2~3배(production 379→752, `/` 415→1,234, regional 345→1,132, trash 563→1,318). 700ms 초과 비율 0.7~2% → 11~15%. 오래 떠 있던 인스턴스에서도 같아 배포 직후 콜드가 아니다. 같은 기간 JSON API 는 변화 없음. 의심 범위 운영 머지 #322(`b12bd29d4`)~#339(`3888da9ab`), 배포별 비율이 들쭉날쭉해 커밋 확정 못 함. 기존 구간 계측(DashCache·EPT-B7)이 못 잡는 구간이다. gevent 루프 막힘은 아님(느린 요청 중 배지 p95 51→78ms). (D)
- 다음 단계: 공용 before_request·context processor·레이아웃 렌더에 phase 계측을 넣고 운영에서 하루 받아 확정. 그 전에 코드를 고치지 않는다.

**P3-2. 계측 공백 — 104경로 중 85경로가 서버 시간 헤더 없음**
- 9탭 중 `/erp/measurement`(`measurement/dashboard.py:180`)·`/erp/drawing-workbench`(`workbench.py:565`)·`/erp/completion`(`completion_dashboard.py:539`) 없음. 작업대 `/triage/pane`(`naver_ingest.py:2615`)은 구간을 재고도 헤더를 안 붙여 값이 버려진다. `/edit/<id>`, 모바일 상세, 태블릿 시트 6종, 주문 상세 JSON API 5종, 정산 API 전부 없음. DASH-SLICES 헤더는 시공 대시보드에만. `/erp/dashboard` 는 헤더가 렌더 이후만 재서 Δ103ms 중 약 85ms 가 비어 있다(`foms/web/orders/dashboard.py:175,179,202,332,367,381`). (A, E)

**P3-3. RUM 전송의 20% 가 429 로 버려진다**
- 운영 [실측]: `/api/foms/rum` 67,836건 429 — RUM 표본이 치우쳤을 수 있다. 기본 rate limit 이 라우트·사용자별 키로 요청마다 Redis 약 2회 왕복(E 로컬 확인). (D, E)
- 방안: RUM 엔드포인트를 rate limit 에서 빼거나 별도 한도.

**P3-4. 생산 탭이 PC 에서도 칸반 전량(최대 300행)을 읽고 가공**
- `foms/web/production/dashboard.py:153·215·230` — 칸반은 모바일 v2 + 터치에서만 그린다(`dashboard_body.html:152`). deploy 에서 생산 탭이 50초 하트비트 대상에 들어가 비용이 커졌다(`erp-shell.js:52`). 운영 production p95 870ms. (E, D)
- 방안: 칸반 계산을 모바일 v2 + 터치일 때만(변경 칩 숫자 `:254` 는 따로 세기).

**P3-5. 하트비트가 304 여도 매번 전체 렌더**
- `erp-shell.js:62-63`, 렌더 전 304 단계(S2b) 미연결(`history.py:142` 관측 하나뿐). 활성 탭 하나가 시간당 약 336회 렌더 [추정]. (E)
- 방안: S2b 연결. 위험: 키에 빠진 조건이 있으면 옛 화면이 나감 — 난이도 상.

**P3-6. 정산 API·휴지통**
- `/api/settlement/aggregates` Δ228ms, `/api/settlement/rows` Δ202ms — 전체 주문 JSON 을 다 읽고 파이썬에서 거름(`foms/services/settlement_aggregation.py:528-538`, `settlement_rows.py:384-386`). `/trash` Δ130 — 한 번에 전체(`foms/web/orders/trash.py:276`). `/metropolitan_dashboard` Δ170 — 메뉴 링크 못 찾음(사용 여부 확인 후 은퇴 검토). 빈도 낮음. (A)

**P3-7. 워커 쪽 작은 것** (F)
- 썸네일 잡마다 R2 클라이언트 초기화(135잡 135줄) — `run_rq_worker.py` 에서 미리 불러오기 [추정 잡당 0.3~0.6s].
- "전체 다시 읽기" 89잡이 61초 직렬(10-01 08:20) — 잡 1개 + 100건 단위 조회(`naver_ingest.py:5102,5266`, `client.py:492`).
- 네이버 429 2건(그중 반품 승인 실패 1건) — 클레임 호출에 초당 2회 속도 조절.
- 잠금 쥔 채 외부 호출(p50 0.7~1.1s): 초안 알림톡(`erp_order_draft_send.py:271` 행 잠금 → `:288` solapi), `push-manual`(`channel_integration.py:403` advisory lock, 1,109건), 도면 전달 R2 직렬 업로드.

**P3-8. 그 밖의 작은 것**
- Redis 초기화가 한 번 실패하면 그 프로세스는 재시작 전까지 캐시를 안 씀(`dashboard_cache.py:191-229`) — 60초 뒤 재시도. (E)
- 출고 설정 무캐시 조회 요청당 1~3회(`erp_shipment_settings.py:214`), 사용자 재조회(`auth/routes.py:303`, `listing.py:277`, `edit.py:254·655`). (E)
- `layout_scripts.html:1085` `bell-shake infinite` — 유휴 3초당 AS 203ms·대시보드 91ms 메인 스레드 [실측 headless]. (B)
- `erp-mobile-shell.js:8` 강제 레이아웃을 PC 에서 건너뛰기(스타일 −17ms). (B)
- sync.js 이중 실행(`layout_scripts.html:77` + `foms_p2_surface_bundle.html:9`). (B)
- 죽은 파일 `static/css/foundation/style.css`(33KB, 참조 0). (B)

**P3-9. DB 관리**
- `pg_stat_statements` 가 preload 는 됐는데 `CREATE EXTENSION` 이 안 돼 쓸 수 없다 — 스테이징·운영 모두 켜고 `track_io_timing=on`(운영은 승인). (C)
- idx_scan=0 인 인덱스 116개 17MB. 단 product·items0·meas_date trgm 은 검색 OR 이 막혀서 0회일 뿐 — P1-3 을 고치면 쓰인다. 진짜 정리 후보(완전 중복 5쌍 등)는 운영 통계로 재확인 후. orders 인덱스 44개 28MB(본체 5MB), 갱신의 82% 가 non-HOT. (C)
- 연결 풀: gevent 워커 2, 프로세스당 5+5, 대기 10초(`db.py:33-38`). 운영 30일 풀 고갈 0건 — 지금은 문제 아님, 풀 대기 계측이 없다. (C, D, F)

## 문제 없음 (조치 불필요로 판정)

- 자원 포화 없음: web CPU 최대 0.43/2 vCPU, 메모리 0.68/6GB, Postgres 0.57 vCPU. 시간대별 p95 평탄 — 부하 경합이 아니라 요청 하나의 일 크기 문제. (D)
- gunicorn 시간 초과 0, DB 풀 고갈 0, OOM 0. 5xx 40건은 09-29 psycopg3 사건 10건 + 09-30 16:39~16:56 플랫폼 502 24건(엣지 dial timeout·내부 DNS 실패). (D)
- 워커 잡: 3,247건, 느려진 잡 없음 — 9월 둘째 주부터 p50 약 절반(썸네일 2.80→1.07s). 정산 루프 41/41 OK, 야간 cron 단계마다 0.4~1.7s. WORKER 메모리 0.6→1.1GB 한 번 상승 후 평평(누수 아님). (F)
- ERP 9개 fragment 는 스테이징 예산 안, 09-11 증거와 ±10ms — 최근 회귀 없음. (A)
- 정적 스캐너 high 2건(시공 `scripts.html`, 출고 `dashboard_scripts.html` 다중 script)은 **오탐** — 스크립트를 막아도 29.5→26.8ms, 13.2→12.3ms [실측 A/B], entry 싱글톤 정상. (B)
- 스캐너 63건 중 49건은 콜드 경로(관리자 23, 백필·워커 26). hot path 14건 중 실제 조치 대상은 전체 비우기 2건 + N+1 1건(P1-2, P1-4 에 흡수). (E)
- 매 요청 공통 비용은 작다: 사용자 조회 1쿼리, Redis 약 2왕복, 컨텍스트 프로세서 0.3~0.4ms, 주요 22경로 lazy load 0. (E)
- 한국↔싱가포르 네트워크 tail 은 기규명(재조사 안 함).

## 성능 밖 발견

- 운영 SIDEFX `FOMS_WORKER_WATCHDOG_ENABLED=1` 이고 09-30 에 감시 push 가 실제로 나갔다. 메모에는 "09-29 사용자가 당분간 꺼 두기로 함" — 서로 맞지 않는다, 확인 필요. (F)
- 로컬 `C:\DEV\FOMS` 의 deploy 체크아웃이 origin/deploy 보다 166 커밋 뒤, 9 커밋 앞. 수정 작업 전에 워크트리를 origin 기준으로 열 것.

## 진행 기록

- 2026-10-01: 6트랙 조사 완료, 이 원장 작성. 감독자 재확인: P1-1 원인 1·3, P1-2 호출처 13곳·SCAN+DELETE, P1-3 술어·#439 diff, P1-5 가드 누락, P2-1 술어, P2-2 ③, P2-4 ②③, P2-5 목록, P2-7 두 곳. 수정은 아직 없음.
- 2026-10-01: 쉬운 수정 5건 `a86754a2c` — P1-5 AS 탭 생략 표식, P2-7 timeout 2곳, P2-4② 결제 아이콘 673→51KB(120px), P2-5 예열 목록 9탭 29개 추가·WORKER 자식 예열 생략, P1-1③ 패널 캐시 키에서 selected_date 제거. 음성 대조군·smoke 통과. 스테이징 실측 전.
- 2026-10-01: 실측 탭 P1-1① blob ILIKE 보충 가지 제거 + ⑤ EPT 헤더·phase(panel·main_rows·hydrate·sales_delivery·naver_preview)·DASH-SLICES. 근거: 스테이징 주문 3,520건 중 "정식 실측일이 일정표에 없는 주문" 0건(검출기 음성 대조군 3/3 검출, 3건 모두 평평한 컬럼 안전망에 걸림). **운영 데이터로는 아직 확인 안 함** — 운영 승격 전 같은 검사 1회 필요. P1-1② 네이버 미리보기 캐시는 **하지 않기로** — 스테이징 캡처에서 미리보기 쿼리 합 약 6ms 라 이득이 작고, 발송 직후 옛 상태를 보여 줄 위험(불가역 조작)이 더 크다. 배포 후 `naver_preview` 구간 실측으로 다시 판단.
- 곁가지 발견(미조치): "내 담당" 필터 `erp_permissions.py:268` `_json_like_condition` 도 structured_data 통째 LIKE 다 — mine 필터를 켠 모든 대시보드에 해당, 실측 후 판단.
