# 성능 회귀 원천 차단 (Performance Guardrails)

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

새 동기 스크립트가 **정말** 불가피하면: ① 먼저 defer/async/lazy로 전환 시도 → ② 그래도
동기여야 하면 가드 파일의 `SYNC_SCRIPT_ALLOWLIST`에 **사유 주석과 함께** 추가(리뷰 필수).

## 필수 규칙 (리뷰에서 확인)

### 프론트엔드
- **`<script>`는 기본 `defer`**(또는 `type="module"`). 코어 라이브러리/파싱시점 전역 의존만 예외(allowlist).
- **무거운 라이브러리는 사용 시점 lazy 로드**. 예: `html2canvas`는 견적 내보내기 시
  `estimate-preview.js`의 `_ensureHtml2canvas()`로 1회 동적 로드(전역 로드 금지).
- **공용 partial에 페이지 전용 무거운 JS 추가 금지**. 특정 기능 JS는 그 기능 페이지/탭에서만 로드.
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
