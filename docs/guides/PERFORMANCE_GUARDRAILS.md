# 성능 회귀 원천 차단 (Performance Guardrails)

> **North Star:** deploy 직후 “전체 ERP 로딩/체감 느려짐” 재발을 deploy 전에 차단한다.
> TTFB 정상 ≠ deploy 가능. 8차원 broad 탐색: [`ERP_SLOWDOWN_RADAR.md`](ERP_SLOWDOWN_RADAR.md)
>
> 코드·기능 추가가 **서버/페이지를 느리게 만드는 일을 머지 전에 차단**한다.
> 일부는 자동 테스트로 강제(차단), 일부는 리뷰 필수 규칙이다.

## 왜 (실제 장애 사례)

- **2026-06-15 견적서/계산기 배포**: `html2canvas`(CDN 동기) + 견적 스크립트들을 `defer` 없이
  공용 partial(`erp_order_js.html`)에 추가 → 모든 ERP 탭에서 ~1.2MB JS가 렌더 차단.
  **서버 TTFB는 200~600ms로 빨랐는데** 클라이언트 체감만 크게 느려짐.
- **서비스워커(`static/sw.js`) networkFirst 무 timeout**: 모든 css/js를 매 로드 서버 강제
  재검증하는데 timeout이 없어, fetch 지연 시 `respondWith` 미해결 → **탭 로딩 스피너 무한 회전**
  (페이지 내용은 떴는데도).
- **JSONB→text ILIKE 풀스캔**: 대시보드/검색/가시성 필터가 `cast(structured_data, String).ilike`
  형태라 인덱스를 못 타 주문 N행 비례 Seq Scan(다중 사용자 시 DB 풀 고갈).

교훈: **"느려졌다"는 대부분 서버가 아니라 프론트(렌더 차단/번들 무게)·SW·인덱스 누락**이다.
신고 시 **서버 TTFB부터 측정**해 서버/프론트/SW/네트워크를 분리한다.

## 자동 강제 (pre_push_smoke 차단)

`tests/performance/test_perf_regression_guard.py` — exit 0 아니면 push 금지.

- **G1 렌더 차단 스크립트 금지**: 템플릿에 `defer`/`async`/`type=module` 없는 신규 `<script src>` 금지.
- **G2 외부 CDN 동기 스크립트 금지**: 신규 CDN `<script>`는 반드시 `defer`/동적 로드/self-host.
- **G3 서비스워커 timeout 필수**: SW의 network-first 류 fetch는 timeout + 캐시 폴백 필수.
- **G4 fragment 재실행 JS 중복 listener 금지**: ERP shell fragment 안에서 다시 평가되는 JS가
  `window`/`document`/`body` 전역 listener를 추가하면 singleton guard(`window.__*_BOUND`) 필수.

새 동기 스크립트가 **정말** 불가피하면: ① 먼저 defer/async/lazy로 전환 시도 → ② 그래도
동기여야 하면 가드 파일의 `SYNC_SCRIPT_ALLOWLIST`에 **사유 주석과 함께** 추가(리뷰 필수).

## 스테이징 성능 게이트 (배포 후 검증 / 승격 전 필수)

`tools/perf/staging_perf_gate.py` — 배포된 스테이징(lahom-dev)에 로그인 → 9개 primary
fragment 경로를 반복 측정(첫 회 웜업 버림) → 커밋된 예산(`tools/perf/perf_budgets.json`)과
비교해 초과 시 exit 1 로 승격을 차단한다. "커밋→푸쉬→사용자가 느려짐 발견" 악순환에서
**발견 주체를 사용자 → 봇**으로 옮기는 인프라다.

- **언제**: deploy 배포 완료 후 검증 / production 승격 직전 필수. pre-push 기본에는 안 낀다
  (`scripts/ops/pre_push_smoke.ps1 -PerfGate` 로만 실행 — 스테이징이 살아있어야 하는 배포 후 도구).
- **판정 철학 v2(절대) — 창 분산·tail 오염 면역**: 경로 TTFB 대표값은 warm 표본 **최솟값(min)**,
  판정값은 **`min(path) − min(healthz)` = 델타(dTTFB)** 다.
  - **왜 min**: 네트워크 tail(2~9s)은 값을 **올리기만** 하므로 min 은 tail 오염에 완전 면역이다.
    반면 균일 서버 회귀(N+1 추가 등)는 전 표본을 올려 min 도 상승 → 감지가 유지된다.
    (실전 2회 오탐: median 이 tail 뭉침에 뚫려 정상 창을 FAIL 시킴 → min 이 근본 해결.)
  - **왜 healthz 델타**: 매 런 시작 시 무인증 `GET /healthz`(순수 liveness, 서버 작업 0) 를
    반복 측정한 min = 그 창의 **네트워크 베이스 RTT**. 경로 min 에서 이를 빼면 시간대별 베이스
    RTT 분산(창 분산)이 상쇄돼, 빠른 창에 시드한 예산이 정상 창을 오탐하던 결함이 사라진다.
  - **median/p95/최댓값은 판정에 절대 넣지 않는다**(리포트 정보용). 정밀 서버 회귀는
    render_ms_max·바이트·쿼리 계약이 잡는다.
- **budgets 스키마 v2**: 경로별 판정 키 `ttfb_delta_min_ms`(신규) + `body_bytes_max`(유지).
  v1 의 `ttfb_warm_median_ms` 는 제거됨. `_global.schema: 2` 표기.
- **조건부 304 계약**: 각 경로 1회 ETag 에코(If-None-Match) → 304 확인(하트비트 경제성 회귀 감시).
- **예산 갱신 규칙**: `--seed` 는 델타 실측 + 마진 `max(delta*1.3, delta+80ms)` 으로 budgets 를
  재생성한다(델타는 값이 작아 상대 30% 만으로는 빡빡 → 절대 하한 80ms 병행).
  **의도된 성능 변화 때만** 실행하고, budgets diff 는 반드시 리뷰 대상(무단 상향 = 게이트 무력화).
- **exit**: 0=PASS · 1=FAIL(예산 초과) · 2=크리덴셜 부재/로그인 실패(게이트 SKIP ≠ 실패).
- 참고: 바이트는 requests 가 gzip/br 자동 해압한 **해압 후** 크기(wire 아님). 네트워크 예외/5xx 1회 재시도.
  델타 위반 시 1회 재측정 후 재판정(v2 에선 min 면역으로 발동 확률 낮음).

### 자동화 — 하이브리드 게이트 (`.github/workflows/perf-gate.yml`)

GitHub Actions 가 게이트를 자동 실행하되, 이벤트별로 블로킹 강도를 나눈다. 사람이 게이트를
떠올릴 필요 없이 **발견 주체를 사용자 → 봇**으로 옮기면서도, 무관 커밋 연쇄 fail 은 막는다.

- **왜 하이브리드**: 판정이 커밋 diff 가 아니라 **CI 시점 staging 상태**라, deploy 마다
  블로킹하면 한 번 예산 초과 시 그 상태에 무관한 후속 커밋까지 전부 연쇄 fail 한다
  (비귀속·상태의존). → deploy 는 조기 신호만 주는 advisory, **승격 게이트에서만 하드 차단**하고,
  예산 재시드/근본수정은 별도 커밋으로 처리한다.
- **트리거**:
  - `push: [deploy]` → **비블로킹 advisory**(`staging_perf_gate.py --advisory`). 예산 초과는
    경고 어노테이션·step summary 로만 뜨고 **exit 0** → 무관 커밋 연쇄 fail 방지.
  - `pull_request: [production]`(deploy→production 승격 PR) + `workflow_dispatch`(수동) →
    **블로킹 하드 게이트**(`--advisory` 없음). 예산 초과 → exit 1 → job fail → 승격 차단.
  - 로컬/PowerShell 수동 실행은 여전히 `/perf-gate`(위 명령) 또는 `pre_push_smoke.ps1 -PerfGate`.
- **배포 완료 대기(push 만)**: `tools/perf/wait_staging_deploy.py --sha $GITHUB_SHA` 가 스테이징
  `/healthz` 의 `commit`(Railway `RAILWAY_GIT_COMMIT_SHA`)이 이 커밋과 일치할 때까지
  15s 간격 폴링(기본 timeout 600s). 구버전 컨테이너를 재는 레이스를 차단한다.
  PR/dispatch 는 현재 살아있는 staging 을 그대로 측정한다(승격 후보 검증).
- **concurrency**: `perf-gate-${{ github.ref }}` 그룹 + `cancel-in-progress` 로 빠른 연속 푸시의
  중복 런을 취소한다(진행 중 런 노이즈·크레딧 낭비 감소).
- **판정**: 예산 초과(정상 exit 1)는 advisory 모드에선 경고만(exit 0), 승격/수동에선 job fail.
  단 **exit 2(크리덴셜 부재/로그인 실패)** 는 advisory 무관하게 항상 job fail — 측정 불가는
  사고로 취급한다(자동화에선 secret 누락도 조용히 통과시키지 않는다).
- **evidence**: 판정 JSON 을 artifact(`perf-gate-evidence`, 보존 14일)로 업로드만 하고
  CI 에선 repo 에 커밋하지 않는다(로컬 실행과 무충돌).
- **필요 secrets**(레포 설정): `FOMS_STAGING_USERNAME`, `FOMS_STAGING_PASSWORD`.
- **의존 최소**: 게이트 import 체인은 순수 stdlib(`erp_navigation_contract`) + requests
  (`ept_b8` 로그인)뿐이라 CI 는 `pip install requests` 만 한다(앱 전체 설치 불필요).

### RUM 일일 자동 리포트 (`.github/workflows/rum-daily.yml`)

매일 아침(KST 07:30 = cron `30 22 * * *` UTC) production 의 RUM 집계 p95 추세·회귀를
조회해 리포트한다(실사용 성능 회귀를 대시보드가 사용자보다 먼저 잡는 그물).

- **경로**: admin 엔드포인트 `GET /api/foms/rum/report`(login_required + role ADMIN 403,
  Redis 부재 503). 운영 Redis 는 앱 내부에서만 접근되므로 이 엔드포인트가 유일한 외부 조회로.
  집계·판정 로직은 `foms/services/rum_aggregate.py::build_rum_report`(CLI·엔드포인트 공용 SSOT).
- **워크플로**: `tools/perf/rum_report_http.py` 가 production 로그인 → report GET →
  `regressed=true` 면 exit 1(job fail=알림), 결과를 step summary 에 표로 남긴다.
  `schedule` + `workflow_dispatch`(수동). 같은 `FOMS_STAGING_*` secrets 재사용.
- **주의(cron 기본 브랜치)**: GitHub 의 `schedule` 은 **기본 브랜치(이 레포=production)의
  워크플로 파일만** 실행한다. `rum-daily.yml` 이 production 에 승격돼야 매일 자동 실행되며,
  `deploy` 에만 있으면 수동 dispatch 만 가능하다.

## 필수 규칙 (리뷰에서 확인)

### 프론트엔드
- **`<script>`는 기본 `defer`**(또는 `type="module"`). 코어 라이브러리/파싱시점 전역 의존만 예외(allowlist).
- **무거운 라이브러리는 사용 시점 lazy 로드**. 예: `html2canvas`는 견적 내보내기 시
  `estimate-preview.js`의 `_ensureHtml2canvas()`로 1회 동적 로드(전역 로드 금지).
- **공용 partial에 페이지 전용 무거운 JS 추가 금지**. 특정 기능 JS는 그 기능 페이지/탭에서만 로드.
- **ERP shell fragment에서 재실행되는 JS는 idempotent 필수.** `foms_app_shell.html`/P2 bundle/모바일
  shell에 추가되는 JS가 `window.addEventListener`, `document.addEventListener`,
  `document.body.addEventListener`를 쓰면 `window.__*_BOUND` 같은 단일 초기화 가드로 중복 바인딩을 막는다.
- 인라인 스타일·대형 인라인 script 금지(`CLAUDE.md` 프론트 규칙 준수).

### 서비스워커 (`static/sw.js`)
- network-first/네트워크 fetch는 **timeout(현재 3s) + 캐시 폴백** 필수. 무한 대기 금지.
- `CACHE_VERSION` 범프는 신중히(범프 시 첫 로드 캐시 없음 → 타임아웃 폴백 무력).

### 백엔드 / DB
- **JSONB/text `cast(...).ilike('%..%')` 는 인덱스 없이 hot path 금지.**
  부분일치는 trigram(`gin_trgm_ops`) 인덱스, id 멤버십은 `@>` containment(jsonb GIN).
  새 인덱스 표현식은 SQLAlchemy 생성 SQL과 byte-match + `EXPLAIN`으로 인덱스 사용 확인.
- **N+1 금지**: 리스트는 `in_(ids)` 배치 로드(첨부/상세/담당자 맵).
- **매 요청 무거운 계산은 캐시**(`dashboard_cache.py` micro-cache 패턴, Redis).
- **마이그레이션 CONCURRENTLY + 다중 replica**: `env.py`는 세션 레벨 advisory lock
  (`pg_advisory_lock`) 사용. 트랜잭션 레벨(`pg_advisory_xact_lock`)은 내부 COMMIT에 풀려 레이스.

### 검증 (대시보드/리스트/검색/액션 변경 시)
- 머지 전 **서버 TTFB 측정** + 대시보드 주요 쿼리 `EXPLAIN (ANALYZE)`로 **Seq Scan 없음** 확인.
- UI/스크립트 변경은 **첫 페인트(FCP)·`load` 가 동기 스크립트로 지연되지 않는지** 확인.
- 운영급 검증은 staging(운영급 박스) 또는 운영에서. 약한 dev 인스턴스의 절대 시간은 신뢰 금지.
- 서비스워커 동작은 **실제 Chrome**에서 확인(헤드리스는 SW 미등록).

## 관련 파일
- 가드 테스트: `tests/performance/test_perf_regression_guard.py`
- 게이트: `scripts/ops/pre_push_smoke.ps1`
- SW: `static/sw.js` / 견적 lazy 로드: `static/js/orders/estimate-preview.js`
- 인덱스 마이그레이션: `migrations/versions/phase_d_trgm_indexes.py`, `phase_e_trgm_perm_indexes.py`
- 마이그레이션 락: `migrations/env.py`
- 점검 엔진(도구 무관): `tools/perf/perf_scan.py`
- 점검 진입점: Claude `.claude/commands/perf-guard.md` · `perf-audit.md`(슬래시 `/perf-guard`), Cursor 네이티브 `.cursor/rules/02-performance-guardrails.mdc` §점검 실행, Codex `AGENTS.md`+스크립트 직접 실행

## 점검 스킬 실행 절차 (Cursor·Claude·Codex 공통)

### A. perf-guard — deploy veto (매 코드 수정 후, push/deploy 전 필수)
1. `python tools/perf/perf_scan.py --guard` 실행(변경분만, 신규 high면 exit 1 → **배포 금지**).
2. 스크립트가 못 잡는 부분을 **diff에서 직접** 점검(아래 수동 체크리스트).
3. 발견 시 위 "필수 규칙"대로 수정. 그래도 동기 스크립트가 불가피하면 사유와 함께
   `tests/performance/test_perf_regression_guard.py`의 allowlist에 추가.
4. 결과: `[차단|주의|통과]` + 파일:라인 + 수정안.

**수동 체크리스트(정적 스캔이 못 잡는 것):**
- 플래그된 `structured_data ... ilike` → 매칭 trigram 인덱스가 실제 있는지 `EXPLAIN`으로 확인.
  있으면 OK, 없으면 회귀(인덱스 추가).
- N+1: 리스트/루프 안에서 주문별 쿼리 → `in_(ids)` 배치로.
- 매 요청 무거운 계산(집계/렌더) 추가 → Redis micro-cache 적용 여부.
- 공용 partial(`erp_order_js.html`/layout)에 페이지 전용 무거운 JS·CSS 추가 금지.
- 서비스워커 fetch 전략 변경 시 timeout+캐시 폴백 유지.
- ERP shell fragment 재실행 경로에 추가한 JS의 전역 listener가 singleton guard로 보호되는지 확인.

### B. perf-audit — ERP Slowdown Radar (주 1회 + production 승격 전 필수)
1. `python tools/perf/perf_scan.py --audit` + `--radar` (전체 후보 + 8차원 요약). 상세: ERP_SLOWDOWN_RADAR.md
2. **운영급 측정**(staging/prod, 실제 Chrome): 대시보드/검색/탭전환 **서버 TTFB** +
   주요 쿼리 `EXPLAIN (ANALYZE)`로 **Seq Scan 없음** + 정적 자원 캐시 적중 확인.
   (약한 dev 인스턴스 절대 시간은 신뢰 금지. SW 동작은 실제 Chrome에서만.)
3. high/빈도순 우선순위화 → 안전 수정(인덱스·캐시·lazy·페이지네이션) 설계.
4. 결과: 상위 개선 후보 + 예상 효과 + 안전한 적용안.
