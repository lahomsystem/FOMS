# ERP 셸 하트비트 — 렌더 전에 끝나는 재검증 (**보류: S2b 기각, 2026-09-03**)

> 2026-09-01 작성. **2026-09-03 상태: S1·S2a 는 운영 반영, S2b(렌더 전 304)는 접었다.**
> 접은 이유는 위험이 아니라 **이득 부재**다 — 운영 적중률 21%(`orders` 가 재검증보다
> 자주 오른다). 정확성은 이틀 연속 mismatch 0 으로 증명됐다. 상세·재시도 순서는
> 원장 §P12. 그림자 관측 플래그는 양쪽 환경에서 off.
> 관련 실측·조사 기록: `docs/plans/2026-08-31-settlement-dashboard-impl-ledger.md` §P2.

## 1. 무엇이 문제인가 (실측)

ERP 셸은 인접 탭 프래그먼트를 주기적으로 재검증한다 — primary 8건/240초 + fresh 2건/50초
(`static/js/runtime/erp-shell.js:59-60, 1077-1087`). 조건은 "탭이 보이고 10분 내 활동".

ETag 는 **렌더가 끝난 뒤** 붙는다(`foms/services/common/erp_shell_http.py:76-78` —
`response.add_etag()` → `make_conditional(req)`). 즉 **304 여도 서버는 화면을 전부 렌더한다.**
스테이징 실측(2026-09-01, healthz 델타):

| 경로 | 200 서버시간 | 304 서버시간 | 본문(해압) |
|---|---|---|---|
| `/erp/as?view=fragment` | 71.8ms | **67.4ms** | 724KB |
| `/erp/dashboard?view=fragment` | 71.7ms | **74.6ms** | 394KB |
| `/erp/production/dashboard?view=fragment` | 56.0ms | **64.9ms** | 408KB |

304 가 아끼는 것은 **전송뿐**이다. `erp-shell.js:62-64` 주석의 "대부분 304 로 값싸게 끝난다"는
대역폭 기준으로 맞고 서버 CPU 기준으로는 틀리다. 탭 하나가 열려 있으면 시간당 약 260회
보드 렌더가 돈다(정확히: 8×15 + 2×72 = 264).

## 2. 목표 / 비목표

- **목표**: 본문이 안 바뀌었으면 **렌더 전에** 304 로 끝낸다. 현재의 정확성(내용이 바뀌면
  반드시 새 본문)을 한 톨도 양보하지 않는다.
- **비목표**: 하트비트 주기·대상 변경(체감 속도 설계는 그대로), 프래그먼트 HTML 서버 캐싱
  (`dashboard_cache.py:2-9` 가 HTML 캐시를 금지한다 — DTO 만 캐시).

## 3. 핵심 난점 — "본문이 안 바뀌었다"의 정의가 넓다

조사 결과(`foms/web/**` 9 라우트) 본문은 아래 **전부**에 좌우된다.

| 축 | 근거 |
|---|---|
| orders + 함께 읽는 테이블 4종(`order_schedule_dates`·`order_attachments`·`users`/`order_assignments`·`system_settings`) | 예: `foms/services/orders/dashboard_read_model.py:44,394,428,473,482` |
| 요청 파라미터(화면마다 6~14종) | 예: `foms/services/orders/dashboard_filters.py:63-99` |
| 사용자 축: id·role·team·`mine` 쿠키·CONSTRUCTION 강제 mine | `foms/services/common/erp_mine_filter.py:7-25, 37-40` |
| 코호트 변형(v2/v3) | `foms/services/feature_flags.py:256-286, 367-396` |
| **서버 오늘 날짜** | `get_today_kst()` 다수. shipment 는 오늘~+14일 창이 캐시 키(`foms/web/shipment/dashboard.py:368-369`) |
| 60일 활성 창의 이동 | `models.py:176` (`datetime.now()-60d`) |

그리고 **범용 `updated_at` 컬럼이 orders 에 없다**(`models.py:21-210`). 있는 것은
`created_at`·`structured_updated_at`(인덱스 없음, 일부 쓰기 경로만 갱신)·
`erp_stage_updated_at`(인덱스 있음, 그러나 값의 출처가 JSON)·`mutation_version`(인덱스 없음).
어느 컬럼에도 `onupdate` 가 없고 DB 트리거도 없다.

→ **"orders 의 max(updated_at)" 식 단순 버전 키는 이 저장소에서 성립하지 않는다.**

## 4. 설계안: 커밋 시점에 올리는 **패밀리 버전 카운터**

> **2026-09-01 S0 1차 결과로 수정됨**: 아래 1번의 신호원을 `execute_order_mutation` intent 로
> 잡으면 **안 된다**. 일정·첨부 쓰기 29경로 중 엔진 경유는 2건뿐이고, 일정 행의 유일한
> 생산자(`order_date_sync.py:271`)부터가 엔진 밖 `before_flush` 훅이다. 신호원은
> **전역 세션 훅**(`before_flush` 에서 더러운 엔티티 종류를 모으고 `after_commit` 에서 카운터
> 증가)으로 간다 — 같은 이유로 날짜 동기화가 이미 그 자리를 쓰고 있다
> (`order_date_sync.py:519-521`: "모든 쓰기가 통과하는 유일 지점"). ORM 우회 쓰기
> (`.update({` 16곳 · raw SQL 4곳)는 개별 등재 대상. 상세는 원장 §P7.


이미 있는 것을 쓴다: 대시보드 캐시 무효화가 **`Session.after_commit` 리스너**로 배선돼 있고
(`foms/services/common/dashboard_cache.py:655-690`), 무효화 intent 는 canonical mutation
엔진이 남긴다(`foms/services/orders/revision.py:177-204`).

1. 그 리스너가 무효화할 때 Redis 에 **패밀리별 정수 카운터**를 `INCR` 한다
   (`foms:dashver:v1:<family>`). 새 저장소·새 개념 없이 기존 패밀리 상수를 그대로 쓴다.
2. 프래그먼트 라우트는 **렌더 전에** 약한 키를 만든다:
   `hash(route, 정규화된 요청 파라미터, user_id·role·team·mine, 코호트 변형, KST 오늘,
   그 화면이 읽는 패밀리들의 카운터 값)`.
3. `If-None-Match` 가 그 키와 같으면 **렌더 없이 304**. 다르면 평소대로 렌더하고 응답에
   같은 키를 ETag 로 싣는다(지금의 본문 해시 ETag 를 대체).

### 왜 이 형태인가
- 커밋 훅이 이미 "무엇이 바뀌었나"를 알고 있다 — 새 추적 장치를 만들지 않는다.
- 날짜·사용자·코호트·파라미터를 키에 넣으므로 3장의 축이 전부 반영된다.
- Redis 가 없거나 꺼져 있으면(`dashboard_cache.py:52-53, 180, 191`) **키 생성을 포기하고
  지금 동작 그대로**(렌더 후 본문 ETag) 간다 — fail-open 이 아니라 fail-safe(느릴 뿐 정확).

## 5. 이 설계가 깨질 수 있는 지점 (착수 전 반드시 실측으로 답할 것)

1. **mutation 엔진을 거치지 않는 쓰기 경로.** `revision.py` 밖에서 orders/첨부/일정/사용자
   설정을 바꾸는 경로가 하나라도 있으면 그 변경이 카운터를 못 올려 **오래된 304** 가 나간다
   (화면이 조용히 낡는다 — 지금 결함보다 나쁘다).
   → 착수 전 과제: 각 화면이 읽는 5개 테이블에 대해 "쓰기 경로 전수 조사 + 카운터 미갱신 0건"
   을 소스 스캔 게이트로 고정한다. 미갱신이 하나라도 남으면 **그 화면은 이 설계에서 제외**한다.
2. **`system_settings`·`users` 변경**은 대시보드 패밀리 개념 밖이다. 별도 패밀리를 신설하거나,
   해당 화면(shipment·measurement·drawing)은 카운터에 그 테이블을 포함해야 한다.
   > **2026-09-01 S1 해소**: 키를 패밀리가 아니라 **테이블 이름**으로 잡아 이 문제 자체가
   > 사라졌다(그 쓰기들도 전부 ORM 을 통과한다). `table_version_counter.VERSIONED_TABLES` 참조.
   > 또한 워커는 `rq worker` 로 떠서 `app.py` 를 import 하지 않아 세션 훅이 **하나도 없었다** —
   > `foms/services/jobs/tasks.py` import 시점 등록으로 카운터 훅만 배선했다(원장 §P8 S1-2).
3. **서버 날짜 경계**: 자정을 넘기면 키가 바뀌어야 한다(오늘 날짜를 키에 넣으면 자동 충족).
4. **기존 계약**: `tests/domains/test_erp_shell_fragment_conditional.py:74-86` 이 "2회 렌더
   바이트 동일 + ETag 동일"을, `:120-148` 이 "Order 를 insert 하면 ETag 가 바뀐다"를 고정한다.
   ETag 의 생성 근거가 바뀌므로 두 테스트는 **의미를 유지한 채** 다시 써야 한다(느슨하게 푸는
   것 금지 — insert 후 ETag 변경은 이 설계의 심장이다).
5. **Flask-Compress 가 ETag 를 재작성**한다(`foms/platform/app_factory.py:172-177`,
   `COMPRESS_EVALUATE_CONDITIONAL_REQUEST=True`). 렌더 전 304 를 내면 압축 경로의 재평가가
   개입하지 않으므로, 클라가 들고 있는 **접미사 붙은 ETag**(`"abc:br"`)와의 대조 규칙을
   먼저 정해야 한다(접미사 무시 비교 또는 키 자체를 접미사 포함으로 발급).
6. **perf-gate 계약**: `etag_required`·`conditional_304_required`(`tools/perf/staging_perf_gate.py`)
   가 유지돼야 한다. 게이트는 "ETag 가 있고 그 값으로 304 가 나온다"만 보므로 설계와 충돌하지 않는다.

## 6. 단계 계획 (각 단계가 독립적으로 되돌릴 수 있어야 한다)

| 단계 | 내용 | 완료 기준 |
|---|---|---|
| S0 | 쓰기 경로 전수 조사(§5-1·5-2) | 표 1장: 테이블×쓰기경로×카운터 갱신 여부. 미갱신 0 이 아니면 대상 화면 축소 — **완료**(원장 §P7: 163경로 중 엔진 경유 31%) |
| S1 | ~~패밀리~~ **테이블** 카운터 `INCR` 배선(읽는 쪽 없음) | 계약: mutation 후 카운터 증가, Redis 없을 때 무해, 우회 쓰기 UNSIGNALED 0 — **완료**(원장 §P8) |
| S2 | 화면 **1개**(가장 단순한 `/erp/history/` 또는 `/erp/completion`)에 렌더 전 304 적용 | 스테이징 실측: 304 서버시간이 200 대비 유의하게 낮다(현재는 같다). 기존 조건부 계약 테스트 통과 |
| S3 | 스테이징에서 하루 관측 후 나머지 화면 확대 | 화면별 전후 서버시간 표 + 오탐(낡은 304) 0건 증거 |

## 7. 대안 (기각 사유 포함)

- **하트비트 주기를 늘린다**: 서버 부하는 줄지만 체감 속도(warm 캐시)가 목적이라 제품 결정이
  필요하다. 성능 문제를 UX 후퇴로 갚는 것이라 이 스펙에서는 기각한다.
- **프래그먼트 HTML 을 서버 캐시**: `dashboard_cache.py:2-9` 가 명시적으로 금지(권한·코호트가
  섞인 HTML 을 캐시하면 유출 위험). 기각.
- **`mutation_version` 최대값을 키로**: 인덱스가 없고(`models.py:96`) orders 외 테이블 변경을
  못 잡는다. 단독으로는 부족.

---

## 8. S2 설계 (2026-09-01 작성 · **S2a 승인됨** — 사용자 선택, 2026-09-01)

S1 이 신호원을 만들었다. S2 는 그 신호로 **렌더 전에** 조건부 응답을 끝낸다. 대상은 화면
1개(`/erp/history/`).

### 8.1 선결과제 2건 — 실측으로 답했다

**(a) Flask-Compress ETag 접미사 대조 규칙(§5-5).**
`flask_compress.py:229-237` 은 `status_code >= 300` 이면 **압축도 ETag 재작성도 하지 않고
조기 반환**한다. 재작성은 `:263-268`(`"K"` → `"K:br"`), 조건부 재평가는 `:270-276`.

→ 규칙: **받은 `If-None-Match` 에서 `:<algo>` 접미사를 벗기고 비교한다.** 304 응답에는
클라가 보낸 검증자를 **그대로 에코**한다(오늘 압축 경로 304 의 동작과 동일한 와이어 모양).
200 은 지금처럼 Compress 가 접미사를 붙인다.

**(b) 키 축이 소스 독해로 안 닫힌다.**
`/erp/history/` 프래그먼트는 전역 컨텍스트 프로세서를 그대로 받는다 —
`inject_foms_flags`(shell_variant·코호트 플래그 12종)·`inject_foms_nav_badges`(주문 건수).
템플릿이 그중 무엇을 실제로 렌더에 쓰는지 읽어서 세는 것은 검증이 아니다. 하나라도
빠뜨리면 **낡은 304**(§5-1: 지금 결함보다 나쁘다)가 나간다.

→ 그래서 S2 는 **두 단계**로 쪼갠다. 위험을 감수한 뒤 증거를 모으는 게 아니라, 증거를
먼저 모은 뒤 위험을 감수한다.

### 8.2 S2a — 키 빌더 + **그림자 모드** (동작 변경 0)

신설 `foms/services/common/fragment_revalidation.py`:

- `build_fragment_version_key(route_id, req, user, tables) -> str | None`
  재료 = route_id · **정규화된 요청 파라미터**(그 라우트가 읽는 인자 이름 allowlist —
  **미등재 인자가 하나라도 오면 `None`**) · user id/role/team/mine · shell_variant +
  코호트 플래그 · KST 오늘 · `get_table_versions(tables)`.
  `get_table_versions` 가 `None`(Redis 없음)이면 **`None`** → 지금 동작 그대로(fail-safe).
- `record_shadow_observation(key, body)` — Redis 에 `sha256(body)[:16]` 을 짧은 TTL 로
  적어두고 **다음에 같은 키로 온 요청의 본문 해시와 대조**한다. 어긋나면 mismatch
  카운터 INCR + 경고 로그. 진단 헤더 `X-FOMS-FRAGVER: new|match|MISMATCH`.

`/erp/history/` 에만 배선한다. 렌더 경로·응답 바이트·ETag 는 **전부 그대로**.

**완료 기준**: 스테이징 하루 관측에서 **mismatch 0**. 하나라도 나오면 그 요청의 축을
찾아 키에 추가한다 — 즉 "키가 불완전하다"는 증거를 **렌더 전 304 를 켜기 전에** 얻는다.

### 8.3 S2b — 렌더 전 304 (env 플래그 뒤, S2a 증거 확보 후)

`FOMS_FRAGMENT_PRERENDER_304_ENABLED`(기본 off).

1. 라우트 진입 직후 키를 만든다. `None` 이면 지금 경로 그대로.
2. `If-None-Match` 를 접미사 벗겨 대조 → 일치면 **렌더 없이 304**
   (클라 검증자 에코 + `X-FOMS-ERP-FRAGMENT`·`X-FOMS-ERP-FRAGMENT-TIER` 헤더 유지).
3. 불일치면 평소대로 렌더하되 ETag 를 **본문 해시가 아니라 키**로 발급한다
   (그래야 다음 요청이 렌더 전에 끝난다).

**기존 계약 2건은 의미를 유지한 채 재작성**(§5-4):
`test_fragment_etag_byte_stable_across_renders` → "같은 내용 → 같은 키",
`test_fragment_new_etag_after_data_change` → **강화**(Order insert 가 `orders` 카운터를
올리므로 키가 바뀐다 — 렌더 전 304 경로에서도 반드시 200).

**perf-gate**: `etag_required`·`conditional_304_required` 둘 다 그대로 성립한다.

**측정**: `/erp/history/` 200 vs 304 서버시간 델타(healthz 델타, 여러 런 분포).
현재는 둘이 같다(§1). 304 가 유의하게 낮아지는 것이 성공 판정이다.

### 8.4 이 설계가 P4 의 교훈을 어기지 않는 이유

P4 는 "총 바이트가 같다"는 근거로 첫 페인트 경로에 일을 옮겼다가 되돌렸다. S2 는 첫
페인트 경로에 **일을 더하지 않는다** — 키 계산(해시 1회 + Redis MGET 1회)만 앞에 붙고,
그 대가로 **렌더 전체**(orders 쿼리 + 템플릿)를 건너뛴다. 다만 S2a 그림자 모드는 관측
비용(본문 해시 + Redis 왕복)을 **일시적으로** 첫 페인트 경로에 얹으므로, S2a 는 스테이징
전용으로 돌리고 운영에는 켜지 않는다.
