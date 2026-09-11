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
