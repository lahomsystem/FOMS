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


## 9. 운영 구간 실측 (2026-09-11 저녁, 계측 배포 뒤 첫 측정)

`0c0d0fe14`(내 계측 포함) + `9eeb8c916`(타 세션 뱃지 지연 평가·엔드포인트 분리) 반영 뒤. claude_master 해제→측정→재잠금.

```
== 웜(연속) ==
A-all   render 558~624ms   wb_work_groups=129~146  wb_template=421~468   html 234KB
B-dash  render  42~702ms   phases=None                                    html 556KB
== 콜드(40초 간격) ==
A-all   render 709 / 754ms  wb_work_groups=153 / 445  wb_template=545 / 300
B-dash  render 583 / 568ms  phases=None
== 뱃지 엔드포인트 ==
pending-count  ttfb 248ms (임계경로 밖)
```

### 반증된 내 가설 둘 (§6 에서 "아직 모르는 것" 으로 적었던 것)

| 가설 | 실측 |
|---|---|
| `_place_groups` 가 링크 1,500건을 읽어 집 500으로 자르며 버릴 1,000집을 파싱한다 | **운영은 링크 171건·집 56개.** 두 상한에 전혀 안 걸린다. 낭비 0 |
| `_build_sibling_index` 형제 조회에 LIMIT 이 없어 단조 증가한다 | **형제 포함 172건**(본체 171 + 1). 그 쿼리 `EXPLAIN ANALYZE` **1.3ms**, buffers 68 |

`raw_snapshot` 총량도 400KB(평균 2.4KB × 171)뿐이다. **SQL·JSONB 파싱은 범인이 아니다.**
스테이징이 더 나빠 보였던 것은 그쪽 처리 탭 집이 214개로 운영(56)보다 많았기 때문이다 —
**스테이징 숫자로 운영을 추정하면 안 된다.**

### 남은 최대 몫: `wb_template` 300~545ms

A-all(이력 탭)의 서버 렌더 대부분이 템플릿 렌더다. 이력은 **페이지당 50집**(`PAGE_SIZE=50`, 전체 885집)이고
HTML 234KB — 행당 약 4.7KB·6~11ms. 서버가 이미 계산해 둔 dict 를 Jinja 가 그리는 데 그만큼 든다.
`wb_work_groups`(129~153ms)보다 3~4배 크다. 더 쪼개려면 **템플릿 안에 구간 계측이 더 필요하다**(미착수).

### B 쪽은 뱃지 분리 효과가 확인된다

`phases=None`(계산 자체를 안 함) + 웜 render **42ms**. 다만 콜드 568~583ms 는 남아 있고
그건 뱃지가 아니라 대시보드 자체 캐시(슬라이스) 몫이다.

### 규율 메모

이번에도 **추정이 실측에 졌다.** 상한 불일치·LIMIT 부재는 코드만 읽으면 분명한 낭비로 보이지만
운영 모집단에서는 둘 다 걸리지 않았다. 고치기 전에 **모집단 크기를 먼저 세라**.

---

## §10 템플릿 안을 쪼개는 계측 (2026-09-11, `c60417401`)

§9 에서 "더 쪼개려면 템플릿 안 계측이 필요하다"고 적은 것을 만들었다. Jinja 에서는 파이썬
컨텍스트 매니저를 못 쓰므로 **같은 이름을 두 번 부르는 것**으로 구간을 만든다.

```jinja
{{ mark('hist_rows') }}
{% for row in history.rows %} ... {% endfor %}
{{ mark('hist_rows') }}
```

첫 호출이 시작 시각을 적고 두 번째가 경과를 `record_phase` 로 넘긴다. 결과는 기존
`X-FOMS-EPT-B7-PHASES` 헤더에 그대로 실린다. 짝이 안 맞으면(한 번만 부르면) 아무것도 기록하지
않는다 — 조건 분기 안에 한쪽만 남아도 거짓 숫자가 안 나온다.

| 구간 | 자리 | 무엇을 재나 |
|---|---|---|
| `work_rows` | `naver_workbench.html:685`/`:771` | 처리 탭 집 목록 `for` 전체 |
| `pane` | `:777`/`:779` | 상세 pane include(파셜 2,274줄) |
| `hist_rows` | `:1013`/`:1169` | 수집 이력 행 `for` 전체(행 블록 156줄) |

`wb_template` 에서 이 셋을 뺀 나머지가 셸·필터 칩·모달 몫이다.

**아직 안 잰 것**: 이 마커가 실린 응답을 아직 못 읽었다. 스테이징은 코호트 밖이라
관리자 사용자 전환(id 38)으로 넘어야 하고, 운영은 승격이 필요하다.

### §10.1 실측 — 템플릿은 범인이 아니었다 (스테이징, `247f8ded9`)

```
처리 탭  wb_template=299~777   shell_head=0~2  shell_nav=2  wb_head_region=0~1
                               work_rows=15    pane=25~183  wb_modals=0  shell_scripts=0
이력 탭  wb_template=173~188   shell_head=0    shell_nav=2  hist_rows=3~5
                               wb_modals=0     shell_scripts=0
```

**셸 전체가 2ms다.** `layout_head`(1,270줄)·`layout_scripts`(1,750줄)를 의심했는데 둘 다 0ms.
이력 행 50줄이 HTML 231KB 를 만드는 데 **3~5ms**. Jinja 는 느리지 않다.

그러면 `wb_template` 173ms 중 **167ms 가 어디인가** — 답은 **템플릿 밖**이었다.

```python
with phase("wb_template"):
    return render_template(
        "admin/naver_workbench.html",
        history=_history_view(db) if active_tab == "all" else {},   # ← DB 조회
        failures=_failure_rows(db),                                  # ← DB 조회
        ghosts=_ghost_view(db) ...,                                  # ← DB 조회
        **_pane_context(db, _selected_link(db, visible), ...),       # ← DB 조회 여러 벌
    )
```

인자 식은 `render_template` 이 불리기 **전에** 평가된다. 그래서 이 조회들이 전부
`wb_template` 으로 계상됐다. 구간 이름이 거짓말을 하고 있었다 — "템플릿 렌더 300~545ms"
라는 §9 의 결론은 **측정 도구가 만든 착시**다.

### §10.2 고침 — 인자를 먼저 만들고 각각 잰다

`_render_workbench` 를 다시 짰다(동작 동일, 호출 순서·횟수 그대로).

| 새 구간 | 재는 것 |
|---|---|
| `wb_history` | 수집 이력 페이지(50집) 조회·조립 |
| `wb_failures` | 실패 띠 |
| `wb_ghosts` · `wb_origin_cleanup` · `wb_bulk_dispatch` | 처리 탭 전용 띠 셋 |
| `wb_refresh` | 다시 읽기 버튼·진행 상태(ADMIN 전용) |
| `wb_counts` | 칩 숫자·손댈 수 있는 집 수(메모리) |
| `wb_pane_ctx` | 선택 링크 + pane 컨텍스트 |
| `wb_template` | **이제 진짜 Jinja 렌더만** |

### 규율 메모 (둘째)

§9 의 "남은 최대 몫은 템플릿" 은 **내가 그은 구간선이 틀려서** 나온 결론이었다.
구간 계측은 추정보다 낫지만, **구간의 경계가 코드의 실제 평가 순서와 맞는지**를 먼저 봐야 한다.
파이썬에서 인자 식은 호출 전에 평가된다 — `with` 블록 안에 호출문만 있다고 그 블록이
호출의 비용만 재는 것이 아니다.

### §10.3 구간선을 고친 뒤의 실측 (스테이징 `467e8f5ab`, 각 3회)

**이력 탭(`?tab=all`)** — 서버 render 506~747ms

| 구간 | ms | 무엇 |
|---|---|---|
| `wb_work_groups` | 308~355 | 처리 목록(`wg_fetch` 93~100 · `wg_sibling` 110~133 · `wg_group_queue` 62~80) |
| `wb_history` | 74~104 | 이력 50집 조회·조립 |
| `wb_refresh` | 65~253 | **버튼 하나의 상태**(다시 읽기 대상 수 + 진행 중 여부) |
| `wb_pane_ctx` | 42~45 | 선택 링크 + pane 컨텍스트 |
| `wb_failures` | 3 | 실패 띠 |
| `wb_template` | **5~7** | 진짜 Jinja 렌더 |

**처리 탭(`?tab=work`)** — 서버 render 618~1,016ms

| 구간 | ms | 무엇 |
|---|---|---|
| `wb_work_groups` | 389~549 | 위와 같음 |
| `wb_ghosts` | 71~231 | 유령 주문 띠 |
| `wb_refresh` | 62~70 | 위와 같음 |
| `wb_pane_ctx` | 45~63 | 위와 같음 |
| `wb_bulk_dispatch` | 14~20 | 오늘 실측 건 |
| `wb_origin_cleanup` | 7~8 | 재결제 정리 띠 |
| `wb_template` | 13~237 | 이 중 `pane` include 0~129 · `work_rows` 9~13 |

### 결론 — 이 페이지는 처음부터 끝까지 **조회 비용**이다

렌더는 사실상 공짜다(이력 탭 5~7ms). 느린 것은 **한 요청이 서로 다른 조회를 예닐곱 벌
돌린다**는 점이다. 이력 탭 한 번에 최소 네 묶음(`work_groups` · `history` · `refresh` ·
`pane_ctx`)이 돌고, 그중 **이력 탭에서는 쓰지도 않는 처리 목록**(`wb_work_groups` 308~355ms)이
가장 크다.

**다음에 손댈 후보(값이 큰 순서)**

1. **이력 탭에서 `_work_groups` 를 통째로 돌리는 것** — 308~355ms. 이력 탭 화면은 이 목록을
   그리지 않는다. 칩 숫자와 탭 배지 때문에 필요하지만, 그건 수(count)지 목록이 아니다.
2. **`wb_refresh` 62~253ms** — 버튼 하나의 상태에 이만큼 쓴다. ADMIN 이 아니면 아예 안 센다.
3. **`wb_ghosts` 71~231ms**(처리 탭) — 유령 주문 띠.
4. `wb_work_groups` 내부의 `wg_sibling` 110~133ms — `display=True` 라 JSONB 스냅샷을 통째로
   싣는다(타 세션 측정). 처리 탭은 그 스냅샷을 실제로 쓰지만 이력 탭은 안 쓴다.

넷 다 **운영에서 같은 헤더로 확인한 뒤** 손대야 한다 — 스테이징 집 수(214)가 운영(56)보다 많다.

---

## §11 운영 실측 (2026-09-12, production `911964691`, 1회 세션·읽기 전용·계정 재잠금)

스테이징 숫자로 운영을 추정하면 안 된다는 §8 의 교훈대로 운영에서 다시 쟀다. 집 수가 다르다
(운영 56 · 스테이징 214).

### 이력 탭(`?tab=all`) — 3회

| 구간 | #1 | #2 | #3 |
|---|---|---|---|
| `wb_work_groups` | 123 | 131 | 141 |
| `wb_history` | 117 | 99 | 145 |
| `wb_refresh` | 91 | 73 | 92 |
| `wb_pane_ctx` | 76 | 61 | 102 |
| `wb_failures` | 5 | 4 | 7 |
| `wb_template` | **594** | **9** | **551** |
| (그 안) `hist_rows` | 6 | 5 | 6 |
| 서버 render | 1,026 | **388** | 1,061 |

### 처리 탭(`?tab=work`) — 3회

| 구간 | #1 | #2 | #3 |
|---|---|---|---|
| `wb_work_groups` | 116 | 159 | 112 |
| `wb_ghosts` | 168 | 184 | 162 |
| `wb_refresh` | 97 | 86 | 80 |
| `wb_pane_ctx` | 91 | 108 | 61 |
| `wb_bulk_dispatch` | 71 | 68 | 52 |
| `wb_origin_cleanup` | 25 | 30 | 24 |
| `wb_template` | 201 | **783** | 200 |
| (그 안) `pane` | 196 | 420 | 195 |
| 서버 render | 775 | 1,428 | 696 |

대시보드는 `render 1,079ms`(구간 계측 없음), 뱃지 엔드포인트는 `ttfb 262ms`.

### 새로 드러난 것 1 — `wb_template` 널뛰기는 **Jinja 컴파일**이다

이력 탭이 9ms 와 594ms 를 번갈아 낸다. 마커 합은 어느 쪽이든 6ms 다. 원인은 템플릿 컴파일이
**프로세스마다 첫 렌더 1회**만 든다는 것이다. 로컬에서 직접 확인했다.

```
workbench compile     1st= 84.5ms   2nd=0.01ms
pane partial compile  1st=136.8ms   2nd=0.01ms
layout_head compile   1st= 18.8ms
```

운영은 web 2 replica × gunicorn 2 worker = **4 프로세스**라, 재배포 직후 각 프로세스의 첫
방문자가 이 값을 혼자 치른다(운영 실측 550~590ms, 개발기보다 느린 것과 맞는다). 3회 중 2회가
느린 것도 요청이 서로 다른 프로세스에 붙었기 때문이다.

**고치는 길**: 부팅 때 `jinja_env.get_template(...)` 로 무거운 것들을 미리 컴파일한다(워밍).
사람이 기다리는 자리에서 빼는 것이고 동작은 안 바뀐다.

### 새로 드러난 것 2 — 정상 상태의 비용표 (컴파일 제외)

| 화면 | 총 render | 큰 몫 |
|---|---|---|
| 이력 탭 | **388ms** | 처리 목록 131 · 이력 99 · 다시 읽기 73 · pane 컨텍스트 61 |
| 처리 탭 | **696~775ms** | 유령 띠 168 · pane 렌더 195 · 처리 목록 115 · 다시 읽기 85 · pane 컨텍스트 75 · 일괄 발송 60 |

**스테이징과 순위가 다르다.** 스테이징 최대는 처리 목록(308~355ms)이었는데 운영은 112~159ms 다
(집 56 대 214). 운영에서 제일 큰 단일 항목은 처리 탭의 **유령 주문 띠 168ms** 와 **pane 렌더 195ms** 다.

### 다음 후보 (운영 값 기준)

1. **재배포 직후 템플릿 컴파일 550~590ms × 4 프로세스** — 부팅 워밍으로 사람 앞에서 뺀다. 가장 싸고 확실하다.
2. **처리 탭 `pane` 렌더 195ms** — 파셜 2,274줄. 첫 화면에 꼭 필요한지(선택 링크 없이 열 수 있는지)부터 본다.
3. **`wb_ghosts` 168ms**(처리 탭) — 유령 주문 띠.
4. **`wb_refresh` 73~97ms** — 두 탭 모두. 버튼 하나의 상태다.
5. **이력 탭의 `wb_work_groups` 131ms** — 그 탭은 목록을 그리지 않는다. 칩 숫자만 필요하다.

`wb_counts`·`wb_household`·`wb_row_flags`·`wb_sort` 는 전부 0~1ms 다 — **건드릴 값이 없다.**

---

## §12 고친 것 — 배포 직후 첫 방문자의 550~590ms (TEMPLATE-WARM-01)

사용자 선택: "배포 뒤 첫 화면 느림부터".

Jinja 는 프로세스마다 첫 렌더에서 한 번 컴파일한다. 그래서 재배포 직후 **각 프로세스의 첫
방문자 한 사람**이 그 값을 혼자 치렀다(운영 4 프로세스 = 네 사람). 부팅으로 옮긴다.

- `foms/services/common/template_warm.py` — `warm_templates(app, names, budget_ms)`.
  목록은 **컴파일 실측으로** 골랐다(로컬 ms, 무거운 순):

  | 템플릿 | ms |
  |---|---|
  | `admin/partials/naver_workbench_pane.html` | 112 |
  | `drawing/partials/workbench_detail_body.html` | 78 |
  | `admin/naver_workbench.html` | 75 |
  | `measurement/partials/dashboard_main.html` | 54 |
  | `measurement/regional_dashboard.html` | 47 |
  | `orders/index.html` | 43 |
  | `measurement/metropolitan_dashboard.html` | 33 |
  | `measurement/self_measurement_dashboard.html` | 23 |
  | 셸 3종(`layout_head`·`layout_scripts`·`layout_nav`) | 16 · 15 · 10 |

  포함 파셜을 **따로 적는다** — 부모를 컴파일해도 `{% include %}` 대상은 첫 렌더에서 컴파일된다.
  예산 2,500ms 를 넘으면 남은 것은 첫 렌더에 맡긴다(워밍이 배포를 늦추는 쪽이 더 나쁠 수 있다).
  실패는 무해하다 — 못 데워도 첫 렌더가 그때 컴파일한다.
- `foms/platform/app_factory.py` — `is_production or is_railway` 일 때만 부른다. dev 는
  `TEMPLATES_AUTO_RELOAD` 가 켜져 있어 파일을 고치면 어차피 다시 컴파일하므로 건너뛴다.
- `tests/performance/test_template_warm.py` — 계약 5건: 캐시에 실제로 들어가는가(두 번째 조회
  5ms 미만), 목록 경로가 실재하는가(옛 경로면 조용히 아무 일도 안 한다), 없는 이름이 예외를
  안 내는가, 예산이 자르는가, **배선이 배포 게이트 안에 있는가**.

돌연변이 검증: `get_template` 호출을 지우면 계약 2건이 red.

**아직 확인 못 한 것**: 운영 효과(배포 뒤 첫 요청의 `wb_template` 이 9ms 대로 떨어지는가).
운영 측정은 1회 세션 규칙이라 사용자 요청이 다시 있을 때 잰다.
