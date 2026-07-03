# Measurement Ladder v2 (field > lab, 2026-07 검증)

**원칙:** 스캐너 finding은 "실측 후보"일 뿐. 코드를 뜯기 전에 아래 사다리로 서버/네트워크/클라/DB/캐시를 분리한다.
Do not invent Lighthouse metrics. gstack browse when URL/runtime available (headless=SW 미등록).

## 1. Wire 실측 — 압축·캐시 헤더 직접 확인

requests 라이브러리는 압축을 **해제한 뒤** 바이트를 본다 → "압축 없음" 오판(2026-07). curl 로 raw 헤더를 본다.

```bash
curl -sS -o /dev/null -D - \
  -H 'Accept-Encoding: gzip, br' \
  -H 'Cookie: <session>' \
  'https://<staging-host>/erp/dashboard' | grep -iE 'content-encoding|cache-control|content-length'
```

기대: `content-encoding: br` 또는 `gzip` 존재 = 압축 작동(재조사 금지). 정적파일 `Cache-Control` 정책은 css/js=no-cache.

## 2. 서버 vs 네트워크 분리 — TTFB vs 서버 렌더 시간

```bash
curl -sS -o /dev/null -w 'TTFB=%{time_starttransfer}s total=%{time_total}s\n' \
  -D /tmp/hdr.txt -H 'Cookie: <session>' 'https://<staging-host>/erp/dashboard'
grep -i 'X-FOMS-EPT-B7-RENDER-MS' /tmp/hdr.txt
```

서버 렌더(`X-FOMS-EPT-B7-RENDER-MS`) 작고 TTFB 큰 tail = **네트워크**(한국↔싱가포르 단일리전). 코드로 못 고친다.

## 3. 클라 탭스왑 — in-page 이벤트 타이밍 (CLI 오버헤드 배제)

탭 클릭→`foms:erp-shell-fragment-swapped` 이벤트 delta 를 브라우저 콘솔에서 직접 측정. 실측탭 5,827ms→21ms(entry singleton) 사건이 여기서 잡혔다.

```js
// 브라우저 콘솔에 붙여넣고 탭을 여러 번 클릭
(() => {
  let t0 = 0;
  document.addEventListener('click', (e) => {
    if (e.target.closest('[data-erp-tab], .erp-tab, [data-fragment-tab]')) t0 = performance.now();
  }, true);
  document.addEventListener('foms:erp-shell-fragment-swapped', () => {
    if (t0) console.log('tab swap Δ =', (performance.now() - t0).toFixed(1), 'ms');
    t0 = 0;
  });
  console.log('swap timer armed — 탭 10회 클릭');
})();
```

느린 스왑 = fragment 내 `<script>` 재실행 의심 → entry singleton(`erp-dashboard-entry.js`/`measurement-entry.js`) 패턴으로 통합.

## 4. DB EXPLAIN — 운영 인덱스 스캔 확인 (읽기전용)

```bash
railway variables --service Postgres        # DATABASE_PUBLIC_URL 확인
psql "$DATABASE_PUBLIC_URL" -c "EXPLAIN (ANALYZE, BUFFERS) <hot query>;"
```

`Seq Scan` on 큰 테이블 = 무인덱스. JSONB path 필터는 flat sync 컬럼(`erp_stage_code`)+인덱스로. 생산탭 1,894행→59행.

## 5. 캐시 — miss 폭풍 신호

운영 로그에서 `[DashCache] result=miss` 가 mutation 직후 전 family 로 반복되면 = 통무효화(`invalidate_all_dashboard_slice_caches`) 폭풍(2026-07, 22곳). 티어 무효화(`invalidate_order_dashboard_families`/`invalidate_dashboard_families`)로 스코프 축소.

---

## 기존 확인 항목 (유지)

- **Chrome SW** — real browser only(no headless SW). gstack browse 는 SW 미등록이라 코드-vs-캐시 격리에 유용.
- **Seq Scan 0** — hot query EXPLAIN 에 Seq Scan 없음.
