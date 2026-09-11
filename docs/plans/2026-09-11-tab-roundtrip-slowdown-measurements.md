# 실측 원장: 운영 두 탭 왕복 지연 (2026-09-11)

> 사용자 보고: `/admin/naver-ingest/triage` ↔ `/erp/dashboard` **왕복**이 느리다. "왜 느려졌는지 deep research".
> 이 파일은 **총괄(메인 세션)이 직접 잰 숫자**만 담는다. 리더·CEO 보고는 별도.

## 1. 측정 조건

- 시각 2026-09-11 오후(KST). 운영 `lahom-production.up.railway.app`, production HEAD 는 그날 PR #354 까지 머지된 상태.
- 계정 `claude_master`(production id 57, ADMIN). 정책대로 **잠금 해제 → 읽기 전용 GET 만 → 재잠금**(스크립트가 `finally` 에서 재잠금, 로그로 확인).
- 쓰기 0회. 측정 도구 `scratchpad/prod_tab_roundtrip_measure.py`(세션 스크래치, 커밋하지 않음).
- 측정 지점은 **한국의 사용자 PC**(이 세션). 즉 네트워크 구간이 실제 사용자와 같다.

## 2. 서버 기본 지연 (로그인 불필요)

```
/healthz   ttfb 192~215ms (5회)        ← 앱 최소 경로
/login     dns 8ms · tcp 42ms · tls 90ms · ttfb 195~236ms · total 290~340ms (10회)
```

**네트워크 왕복만 ~150ms**(tcp+tls 구간). 한국↔싱가포르 경로다(과거 RCA `docs/incidents/` 의 그 경로).
즉 **어떤 요청이든 150ms 는 코드와 무관하게 든다.**

## 3. 페이지 실측 (로그인, 각 5회)

| 화면 | TTFB 중앙값 | 최대 | HTML 크기(압축 해제) |
|---|---|---|---|
| A-work `/admin/naver-ingest/triage?tab=work` | **541ms** | 1,471ms | 175KB |
| A-all `/admin/naver-ingest/triage?tab=all` | **428ms** | 1,216ms | **234KB** |
| B-dash `/erp/dashboard` | **449ms** | 836ms | **604KB** |

- 기본 지연 200ms 를 빼면 **앱 처리 시간 A-work ~340ms · A-all ~230ms · B-dash ~250ms**. 단독으로는 재앙적이지 않다.
- **간헐 스파이크가 있다**: 같은 URL 5회 중 1회가 2~3배(1.2~1.5초). 과거 tail 스파이크 RCA 와 같은 모양.
- HTML 은 **brotli 압축된다**(`/login` 98KB → wire 22.8KB). 전송량은 문제가 아니다. 다만 **압축 해제 후 604KB** 는 브라우저 파싱·DOM 구축 비용으로 그대로 든다.

## 4. 왕복 시나리오 — 사용자 증상 재현됨

A-all → B-dash 를 3바퀴 연속:

| 바퀴 | A-all TTFB | B-dash TTFB |
|---|---|---|
| 1 | **1,011ms** | 431ms |
| 2 | **823ms** | 279ms |
| 3 | **766ms** | 297ms |

**A-all 이 단독(428ms)보다 왕복에서 1.8~2.4배 느리다.** B-dash 는 오히려 빨라진다(캐시 덥혀짐).
= "왕복할 때 느리다" 는 사용자 체감이 서버 숫자로 재현된다. 원인 후보는 서버 쪽(워커 점유·캐시 상호 무효화)이며 확정은 CEO 조사와 합친다.

## 5. 정적 자산 — 결정적 단서

첫 방문(캐시 없음) 기준:

| 화면 | 자산 수 | 합계 크기 | 직렬 합 시간 |
|---|---|---|---|
| A-all | 41개 | 620KB | 4,565ms |
| B-dash | **80개** | **1,229KB** | **9,151ms** |

브라우저는 6커넥션 병렬이라 직렬 합 그대로는 아니지만, **자산 1개당 왕복 150ms** 가 곱해진다.

### 캐시 헤더 실측

| 자산 | Cache-Control |
|---|---|
| `?v=` 핀 있는 css/js (예: `naver-workbench.js?v=20260910a`, 157KB) | `public, max-age=3600` ← **1시간뿐** |
| `?v=` 핀 **없는** css/js (예: `style-pro-max.css`, `js/runtime/script.js`, `sw.js`) | `no-cache` ← **매 방문 재검증** |
| 이미지 (`pay-coin.png` 201KB) | `max-age=31536000` (1년) |

근거 코드: `foms/platform/app_factory.py:85-123` `_versioned_static_cache_middleware`.
그 docstring 이 **이번 증상을 그대로 적어 놓았다**:

> "모든 css/js를 `no-cache`로 둘 수밖에 없었고… 브라우저가 **매 네비게이션마다** css/js를 재검증(304)한다
> → 적은 web 워커에서 정적 요청 폭주 → **탭전환 지연**"

2026-06-16 커밋 `a30e2ed3d` 가 `?v=` 붙은 css/js 에 한해 `max-age=3600` 을 줘서 완화했다. 남은 구멍 둘:

1. **1시간이 지나면 전부 다시 재검증된다.** 하루 종일 쓰는 화면에서 매시간 한 번씩 80개 자산 재검증
   → 6커넥션 기준 14라운드 × 150ms ≈ **2초**.
2. **핀 없는 css/js 는 지금도 매번 `no-cache`** 다. 이번 측정에서 확인된 것만 `style-pro-max.css`·`js/runtime/script.js`·`sw.js`.

서비스워커(`static/sw.js`, `CACHE_VERSION = "foms-p2-v10"`)의 `staticCacheFirst` 는 TTL **5분**(주석 :86)이라
5분이 지나면 다시 서버에 묻는다 — SW 도 이 구멍을 못 막는다.

## 6. 아직 모르는 것 (조사 중)

- 왕복에서 A-all 만 2배 느려지는 서버 쪽 이유: gunicorn 워커 수·DB 커넥션·캐시 상호 무효화 중 무엇인가.
- 자산 41/80개 중 **핀 없는 것이 정확히 몇 개**인가(이번 측정은 상위 6개만 출력).
- "느려졌다" 의 기준점: 언제부터인가. RUM 테이블이 운영 DB 에 없어(`information_schema` 조회 0건) 과거 수치가 없다.
- 간헐 스파이크(1.2~1.5초)가 네트워크인지 앱인지.

## 7. 규율 메모

- production 측정은 **1회 세션**으로 끝냈고 계정은 재잠금됐다(로그 `[account] is_active -> False`).
- 추가 측정이 필요하면 사용자에게 알리고 다시 1회.


## 8. 원인 확정과 수정 (2026-09-11 저녁, 세션 3곳 합동)

### 걷어낸 가설 넷 — 전부 **측정 조건**이 실사용과 달라서 틀렸다

| 가설 | 왜 틀렸나 |
|---|---|
| "워크벤치 서버 코드가 3주 만에 12배로 커져서" | 코드 크기는 사실(29KB→347KB)이나 **응답 시간은 안 커졌다**. 운영 A-all 428ms vs B 449ms |
| "공유 배지 계산은 콜드 4~5ms 라 범인이 아니다" | **코호트 밖 계정**으로 잰 싼 COUNT 경로였다. 코호트 안에서는 **411~428ms**(100배) |
| "ETag 재검증은 정상(129개 전부 304)" | **HEAD 로 ETag 를 모았다.** HEAD 는 본문이 없어 압축이 안 걸려 strong 값을 준다. 실제 브라우저(GET, 압축)는 weak 값을 받고 그걸 되돌리면 200 이다 |
| "수집 화면이 대시보드보다 빠르다" | **웜만 봤다.** 운영은 실사용자 트래픽이 30초 캐시를 덥힌다. 콜드는 766~1,011ms |

교훈: 측정 조건(HEAD vs GET · 코호트 소속 · 웜 vs 콜드)이 실사용과 다르면 **초록도 거짓**이다.

### 고친 것 넷

| # | 수정 | 실측 효과 |
|---|---|---|
| 1 | **weak ETag 비교 복원** — 요청 `If-None-Match` 의 `W/` 만 벗겨 RFC 7232 weak 비교(`app_factory._weak_etag_revalidation_middleware`) | 재검증이 **200+38,659B → 304+0B**. 타 세션 독립 검증 |
| 2 | **버전 자산 `max-age` 1시간 → 하루** | 대시보드 자산 84개 중 73개가 1시간마다 전량 재검증이던 것 제거 |
| 3 | **한 요청이 처리 탭 목록을 두 번 세던 것** — 페이지 답을 요청 스코프(`g.wb_actionable_count`)로 재사용 | 워크벤치 콜드 `nvbadge` **420ms → 0ms**, render 1,019~1,387 → **552~806ms** |
| 4 | **뱃지를 안 그리는 응답이 계산하고 버리던 것** — `LazyBadgeCount` 지연 평가(타 세션 `2b98985ab`) | **프래그먼트(탭 전환) render 590ms → 34ms** = 약 555ms·94% 절감 |

4번이 사용자 증상에 가장 직접 듣는다 — **탭 전환이 곧 프래그먼트 요청**이기 때문이다.
뱃지를 그리는 템플릿은 `layout_nav.html`·`orders/index.html`·`admin/naver_ingest.html` 셋뿐인데
컨텍스트 프로세서라 모든 렌더가 계산했다. `phases=None` 이 "계산 자체를 안 했다"의 증거다.

### 계측이 이 모두를 찾았다

`/admin/naver-ingest/triage` 에 `apply_ept_b7_render_headers` + `phase("wb_work_groups")`·`phase("wb_template")` 를 달기 전까지
이 화면은 **서버 계측 0곳·성능 예산 0건**이라 아무도 시간을 재 본 적이 없었다. 달고 나서 한 번의 콜드 측정이
1,387ms = `wb_work_groups` 436 + `nvbadge` 428 + `wb_template` 945 로 갈렸고, 3번과 4번이 거기서 나왔다.

### 남은 것

- **전체 문서 렌더는 콜드마다 약 400ms 를 그대로 낸다.** 거기서는 뱃지가 실제로 필요해 지연 평가로 안 줄어든다.
  남은 길: 공유 캐시(프로세스 4벌 × 30초 TTL 제거) 또는 뱃지를 늦은 XHR 로(표시 지연을 값으로 치름). 미착수.
- `wb_template` 184~945ms 변동. wire 는 40.7KB 고정이라 바이트가 아니라 렌더 쪽. 미착수.
- `_place_groups` 상한 불일치 — 링크 1,500건을 읽어 집 500으로 자른다(`naver_ingest.py:3241` 대 `:3253`).
  버릴 1,000집의 스냅샷 파싱 비용이 그대로 든다. 미착수.
- **COUNT 전환은 하지 않기로 했다.** 클레임 판정이 JSONB 파싱에 의존하고,
  `bulk_dispatch.dispatch_pending_clause` 가 같은 문제를 SQL 쌍둥이로 풀다 "쌍둥이가 미묘하게 다른 것을 본다"고
  스스로 경고해 둔 전례가 있다(`bulk_dispatch.py:227`).
