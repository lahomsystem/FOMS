# ERP 셸 하트비트 — 렌더 전 304 다시 열기 (성능 원장 P3-5)

> 2026-10-05 작성. **설계만 — 코드 변경 없음.** 코어 변경(서버 응답 경로·하네스)이라 승인 뒤 구현한다.
> 기준 코드: `origin/deploy` `e9d2230ff`(운영 `origin/production` `73ee5e1dc` 와 하트비트 설정 동일).
> 선행 문서: `docs/specs/2026-09-01-shell-heartbeat-cheap-revalidation_SPEC.md`(9월 설계, S2b 보류),
> `docs/plans/2026-08-31-settlement-dashboard-impl-ledger.md` §P6~§P12(9월 실측·보류 판단),
> `docs/plans/2026-10-01-full-perf-audit-ledger.md` P3-5·P1-2.
> 운영 수치는 전부 Railway 로그를 **읽기만** 해서 얻었다(GraphQL query 만, 앱 로그인·DB 접속 없음).

## 0. 먼저 결론

1. **지금 버리는 일의 크기 [실측]**: 운영 영업일 3일(09-30~10-02) 평균 하루 304 응답 **3,474건**, 그
   304 를 만드느라 쓴 서버 처리 시간 **하루 1,334초**. 실측 탭 수정(P1-1) 뒤인 10-02 하루만 보면
   **2,972건 · 898초**. 9월 한 달로는 304 가 39,213건 · 18,133초로 **웹 전체 서버 처리 시간(84,001초)의 22%**
   였다. 사용자가 기다리는 요청이 아니라 뒤에서 도는 재검증이므로, 이득은 전부 서버 쪽(DB·CPU 여유)이다.
2. **이 일은 9월에 한 번 접었다.** 9월 설계(표 단위 쓰기 카운터)는 정확했지만(운영 이틀 mismatch 0)
   적중률이 21% 라 이득이 없었다 — 주문 표가 업무시간 1분에 한 번꼴로 바뀌어 키가 재검증보다 먼저 깨졌다.
   이번 설계는 **키를 탭이 실제로 그리는 행으로 좁혀** 그 벽을 넘는 것이 핵심이다.
3. **304 시간의 87% 가 fresh 3탭**(실측·대시보드·생산, 50초 주기)에 몰려 있다. 나머지 6탭은 합쳐 하루
   약 170초뿐이라 이번 범위에서 뺀다.
4. **권장 순서**
   - 0단계(위험 거의 0, 렌더 전 304 와 무관): primary 스윕이 fresh 3경로를 또 부르는 중복을 뺀다.
     활성 탭 하나당 시간당 30~45회(9~13%) 감소 [추정].
   - 1단계: 9월 계기의 결함(키를 렌더 **뒤에** 만든다)을 고친 그림자 관측을 생산 탭부터 단다. 키는
     `If-None-Match` 가 있는 요청(=뒤에서 도는 재검증)에서만 계산해 사용자가 기다리는 요청에는 일을 더하지 않는다.
   - 2단계 이후: 생산 → 실측 → 대시보드 순으로, 탭마다 관측 판정을 통과한 것만 켠다.
5. **데이터 버전은 "대시보드 캐시 무효화 지점에서 family 번호 올리기"로 하지 않는다.** 그 지점은
   캐시 조각(DTO)용으로 맞춰져 있고 빠뜨림을 TTL(최대 300초)이 덮어 주는 구조라, 버전 키로 쓰면 빠뜨림이
   **끝없는 옛 화면**이 된다(§3.3). 대신 **그 탭이 읽을 행들의 PostgreSQL `xmin` 지문**을 렌더 전에 한 번의
   SQL 로 만든다 — 어떤 쓰기 경로(엔진 밖·워커·raw SQL)도, 시간이 흘러 창에서 빠지는 행도 놓치지 않는다.
6. 기대 이득(fresh 3탭) [추정]: 하루 서버 처리 시간 **약 300~550초** 절감(10-02 기준 상한 764초).
   0단계는 별도로 하루 약 100~180초.

---

## 1. 지금 어떻게 도는가

### 1.1 클라이언트 — 하트비트 (`static/js/runtime/erp-shell.js`)

| 항목 | 값 | 위치 |
|---|---|---|
| primary 9경로 | 대시보드·실측·도면·생산·출고·AS·시공·완료·이력 | `:12-22` |
| fresh 3경로 | `/erp/dashboard`, `/erp/measurement`, `/erp/production/dashboard` | `:45-54` (생산은 09-29 `f02b58170` 에 추가) |
| primary 주기 / 대상 | 240초, **지금 화면 경로를 뺀 8경로**를 600ms 간격으로 | `:62`, `:69`, `:1136-1167` |
| fresh 주기 / 대상 | 50초, **지금 화면 경로를 포함한 3경로**를 300ms 간격으로 | `:63`, `:70`, `:1169-1195` |
| 도는 조건 | 화면이 보이고 마지막 입력 뒤 10분 이내 | `:71`, `:1125-1130`, `:1217-1227` |
| 복귀 재수혈 | 탭이 다시 보일 때·bfcache 복귀 때 fresh 3경로(15초 간격 제한) | `:1089-1111` |
| 조건부 요청 | 캐시에 ETag 가 있으면 `If-None-Match` 를 붙인다 | `:673-684` |
| 304 처리 | 들고 있던 HTML 을 그대로 쓰고 TTL 만 연장 | `:691-700`, `:725-727` |

- 계산: 화면이 보이고 일하는 중인 브라우저 탭 하나가 시간당 **fresh 3×72 + primary 8×15 = 336회**
  재검증한다(원장 P3-5 의 "약 336회" 와 같다).
- primary 대상 8경로에 fresh 3경로가 그대로 들어 있다. 50초마다 이미 갱신되는 경로를 240초마다 한 번
  더 부르는 셈이고, 이 요청은 거의 늘 304 다(§3.8 0단계).
- 화면 전환(`navigateByShell`, `:745`)은 캐시가 신선하면 네트워크를 안 탄다. 캐시가 식었으면 `cacheGet`
  이 행을 **지우므로**(`:265-278`) 전환 요청에는 `If-None-Match` 가 없다. 즉 **304 는 거의 전부 뒤에서
  도는 재검증**(하트비트·복귀 재수혈)이고, 사용자가 기다리는 요청이 아니다.

### 1.2 서버 — ETag 는 렌더가 끝난 뒤에 붙는다

- 9탭 라우트는 전부 렌더를 마친 응답에 `apply_erp_shell_fragment_headers` 를 부른다
  (`foms/services/common/erp_shell_http.py:43-77`). 이 함수가 `response.add_etag()`(본문 해시)와
  `make_conditional` 을 한다(`:75-77`).
- 실브라우저 경로에서 실제 304 판정은 Flask-Compress 가 압축 뒤에 다시 한다
  (`foms/platform/app_factory.py:220` `COMPRESS_EVALUATE_CONDITIONAL_REQUEST=True`). 200 의 ETag 는
  `"K"` → `"K:zstd"` 로 바뀌고, 304 에는 접미사가 안 붙는다(운영 압축은 zstd, 9월 원장 §P10-3).
- 그래서 **304 여도 쿼리·가공·템플릿·컨텍스트 프로세서가 전부 돈다.** 304 가 아끼는 것은 전송뿐이다.
- 기존 계약: `tests/domains/test_erp_shell_fragment_conditional.py` — ETag 존재(`:59`), 두 번 렌더
  바이트·ETag 동일(`:74`), 일치 시 빈 304(`:89`), 불일치 시 200(`:107`), 주문 추가 뒤 ETag 변경(`:120`),
  압축 경로 접미사 304(`:151`). perf-gate 는 `etag_required`·`conditional_304_required` 를 본다
  (`tools/perf/staging_perf_gate.py:351-353`).

### 1.3 9월에 이미 깔아 둔 장치 (S1·S2a)

| 장치 | 하는 일 | 위치 |
|---|---|---|
| 표 쓰기 카운터(S1) | ORM 세션 훅이 `after_flush` 에서 더러운 표 이름을 모으고 `after_commit` 에서 `foms:tabver:v1:<표>` 를 INCR. 대상 6표: orders·order_schedule_dates·order_attachments·users·system_settings·order_assignments | `foms/services/common/table_version_counter.py:66-76`, `:242-291` (워커는 `foms/services/jobs/tasks.py:86`) |
| ORM 우회 쓰기 게이트 | `.update({`·raw SQL 쓰기를 찾아 등재 강제, 지금 UNSIGNALED 0 | `tools/harness/orm_bypass_write_scan.py --check` |
| 버전 키 빌더(S2a) | 라우트·허용 인자·uid/role/team/mine·`inject_foms_flags` 전량·표면 힌트 3종·세션·릴리스·KST 오늘·표 카운터로 16자 키. 모르는 인자가 오거나 Redis 가 없으면 `None`(단축 포기) | `foms/services/common/fragment_revalidation.py:293-345` |
| 그림자 관측(S2a) | 같은 키에 다른 본문이 나오면 MISMATCH 를 센다(응답 불변). 플래그 `FOMS_FRAGMENT_SHADOW_REVALIDATION_ENABLED`, 9월 이후 양쪽 환경 off | 같은 파일 `:348-402` |
| 배선 | `/erp/history/` 한 곳뿐 | `foms/web/orders/history.py:127-157`, 호출 `:358` |

**계기 결함(9월 원장 §P12-3, 아직 그대로)**: `history.py:358` 은 렌더가 끝난 **뒤** 키를 만든다. 렌더 전 304
는 키를 렌더 **전**에 만든다. 순서가 다르면 그 사이 커밋 하나로 "키가 본문보다 새것"이 되어, 관측된
mismatch 가 실제 렌더 전 304 의 실패와 1:1 로 대응하지 않는다. 다시 잴 때 가장 먼저 고칠 곳이다.

**9월 결과(원장 §P10~§P12)**: 운영 이틀 mismatch 0(하루 orders 쓰기 +548 에도), 그러나 적중률 18/84 = 21%.
스테이징에서 원인을 못 찾은 mismatch 7건(전부 같은 릴리스 안)이 미해결로 남았다.

**이번 조사에서 새로 확인한 S2a 키의 빈틈**(이력 한 탭 기준으로도 이미 있다 — 운영 mismatch 0 은 관측 순서·
낮은 적중률·대리 접속 드묾 덕분이었을 수 있다):
1. 세션 재료가 늘 같은 값이다. `_session_material` 은 `session["csrf_token"]` 을 읽는데
   (`fragment_revalidation.py:247`) 실제 키 이름은 `_csrf_seed` 이고(`foms/services/request_write_guard.py:48`),
   로그인 사용자는 seed 를 세션에 저장하지 않고 (대리 접속자 id 또는 uid) + secret 으로 만든다(`:181-233`). 결과는
   항상 `"-"` 이고 **대리 접속(`impersonating_from`)이 키에 없다**(재확인).
2. `erp_mine_only` 쿠키 원값이 없다. 해석된 mine 만 있다(셸 머리는 쿠키 원값을 본다).
3. 릴리스가 커밋 SHA 우선이라(`:271-274`) 환경변수만 바꾼 재배포를 못 잡는다.
4. 코호트 재료가 `inject_foms_flags` 뿐이라 `ERP_ORDER_ENABLED`·`USE_DIRECT_UPLOAD`·`FOMS_NAVER_*`·
   `FOMS_V3_*_THUMB_ENABLED` 같은 렌더 중 env 읽기가 빠진다.
5. 하루 안에서 흐르는 시간(48시간 도면 지연, 60일 창)이 없다 — 오늘 날짜만 있다.
6. 표 카운터 6표 밖의 표를 읽는 탭이 있다: production_runs·order_events·external_order_links·notifications.
   생산·출고의 "변경 확인" API 는 주문을 안 바꾸고 order_events 에만 쓴다(`foms/api/production/orders.py:1328-1336`,
   `foms/api/shipment/change_ack.py:242-246`, 재확인).
7. 조각 갇힘: 표 카운터는 `after_commit` 에서 오르고 라우트의 family 무효화는 그 뒤에 온다. 그 틈의 요청이나
   무효화를 빠뜨린 쓰기는 "새 키 + 옛 조각" 본문을 만들고, 조각이 TTL 로 새로 계산돼 본문이 바뀌어도 키는
   그대로라 옛 본문이 304 로 남는다.

### 1.4 대시보드 조각 캐시와 무효화 (P1-2 이후)

- 조각 캐시는 HTML 이 아니라 DTO 만 담는다(`foms/services/common/dashboard_cache.py:1-9`). family 7개
  (`:81-97`): orders·measurement·shipment·construction·history·production·drawing. **AS·완료는 family 가 없다.**
- 무효화 신호는 세 갈래다: 저장 라우트가 부르는 `invalidate_dashboard_families_for_order_save`
  (저장 전후 축 비교, `:856-941`), 일정 표 훅의 `dashboard_families_for_schedule_change`(`:944-993`),
  변경 엔진 intent 를 소비하는 MUT-CACHE-01 리스너(`:1027-1062`).
- 규칙의 기준은 "**그 family 의 캐시된 조각이 이 주문의 바뀐 값을 담을 수 있는가**"다(`:686-697` 주석).
  빠뜨린 경우의 안전망은 TTL 90~300초(`:43-47`)다. 화면의 행 내용은 렌더마다 DB 에서 새로 읽는다
  (예: 이력 `fetch_history_orders_by_ids`, `history.py:284`).
- 엔진을 안 거치는 주문 쓰기도 여전히 있다. 예: 수정 제작 시작 `foms/api/production/orders.py:1110-1137`
  은 `structured_data`·`status="PRODUCTION"`·제작 회차를 직접 쓰고 `db.commit()` 만 한다(무효화 없음).
  9월 전수조사는 orders 쓰기 110경로 중 61경로가 엔진 밖이었다(원장 §P7 S0-3).

---

## 2. 비용 — 운영 실측

### 2.1 방법

- 출처: Railway `httpLogs`(운영 web), 09-30 00:00 ~ 10-02 24:00 KST 영업일 3일. 9탭 경로의 GET 17,185건.
  `path` 에 쿼리스트링이 없어 fragment 와 전체 문서를 가를 수 없다. 대신 **304 는 조건부 요청에만 나오므로
  304 = 뒤에서 도는 재검증**으로 센다(§1.1 근거). 시간은 `upstreamRqDuration`(엣지→오리진, 서버 처리 시간).
- 같은 클라이언트(접속 주소+UA 해시)가 6초 안에 다른 탭 경로 2개 이상을 함께 부른 요청을 "스윕"으로
  분류했다. 사무실 공유 주소 때문에 여러 사람이 한 클라이언트로 묶이므로, 스윕 분류는 304 비율의
  대략값에만 쓴다.
- 9월 30일 값은 성능 원장 트랙 D 의 원자료(125만 건)를 같은 방식으로 다시 셌다.
- 수집 도구는 `tools/perf/prod_route_latency_compare.py` 의 읽기 전용 함수(배포 목록·`httpLogs`
  페이지 넘기기)를 그대로 썼고 필드만 `httpStatus`·`srcIp`(해시만 저장)·`clientUa` 를 더했다(배포 41개,
  호출 61회, 행 190,909). 대시보드 캐시 무효화 횟수는 앱 로그 `[DashCache] invalidated family=` 를
  `environmentLogs` 로 읽었다(5,043줄).
- 한계: 10-03~04 는 휴일, 10-05 는 08:4x KST 배포 뒤 로그가 한 페이지(473행)만 와서 오늘 오전 값은 없다. 템플릿
  렌더 몫은 9월 EPT-B7 로그(`render_ms` p50: 대시보드 68ms · 생산 16ms)로만 봤다 — 키 계산과 나머지 렌더의
  비율은 1단계에서 처음 잰다.

### 2.2 탭별 304 (영업일 3일 평균, 하루 기준)

| 탭 | 주기 | 304 건 | 304 p50 ms | 304 평균 ms | 304 서버초 | 비중 | 200 건(전환·첫 로드 포함) | 스윕 중 304 비율 |
|---|---|---|---|---|---|---|---|---|
| 실측 `/erp/measurement` | 50초 | 957 | 256 | 591 | 566 | 42% | 340 | 75% |
| 대시보드 `/erp/dashboard` | 50초 | 812 | 235 | 409 | 332 | 25% | 639 | 59% |
| 생산 `/erp/production/dashboard` | 50초 | 1,009 | 111 | 266 | 268 | 20% | 185 | 85% |
| 도면 `/erp/drawing-workbench` | 240초 | 229 | 123 | 221 | 51 | 4% | 353 | 41% |
| 출고 `/erp/shipment` | 240초 | 88 | 280 | 414 | 36 | 3% | 102 | 47% |
| 시공 `/erp/construction/dashboard` | 240초 | 92 | 229 | 306 | 28 | 2% | 66 | 58% |
| AS `/erp/as` | 240초 | 83 | 153 | 246 | 20 | 2% | 203 | 34% |
| 완료 `/erp/completion` | 240초 | 101 | 96 | 177 | 18 | 1% | 65 | 61% |
| 이력 `/erp/history/` | 240초 | 104 | 32 | 140 | 14 | 1% | 152 | 42% |
| **합계** | | **3,474** | | | **1,334** | | 2,105 | 65% |

- fresh 3탭이 304 서버 시간의 **87%**(하루 1,166초)다.
- 평균이 p50 의 2배 넘게 큰 것은 오전 꼬리(P3-1, 컨텍스트 프로세서 안의 DB 대기) 때문이다 — 304 를 위해
  그 꼬리까지 그대로 맞는다.
- "스윕 중 304 비율"은 **본문이 안 바뀐 비율의 하한**이다. 스윕 200 에는 ETag 없는 첫 요청(전체 문서 로드
  직후 첫 하트비트·초기 프리페치)이 섞여 있기 때문이다.
- 날짜별: 09-30 4,105건·1,791초, 10-01 3,344건·1,314초, **10-02 2,972건·898초**(실측 탭 P1-1 반영 뒤, 실측
  304 p50 309→188ms). 앞으로의 판단은 10-02 를 기준으로 한다(fresh 3탭 합 764초).
- 시간대: 08~18시 KST 에 몰리고 시간당 380~700개의 스윕 요청이 온다. 12시에 꺾이고 13시에 가장 많다.

### 2.3 키가 얼마나 자주 깨지나 — 대시보드 캐시 무효화 빈도 (08~19시, 시간당)

| family | 09-30(범위 축소 전) | 10-02(P1-2 범위 축소 뒤) |
|---|---|---|
| orders | 31.3 | 18.9 |
| drawing | 22.7 | 11.7 |
| measurement | 21.0 | 10.0 |
| production | 18.3 | 7.5 |
| shipment | 8.5 | 4.4 |
| construction | 7.6 | 3.6 |
| history | 6.0 | 2.5 |

- 로그는 지운 키가 있을 때만 남으므로 **하한**이다. 10-02 는 연휴 앞 금요일이라 쓰기가 적었을 수 있다.
- 비교: 9월 표 카운터는 orders 하루 +548(업무시간 시간당 약 50), attachments +166, system_settings +175
  (사람 활동 없이도 오른다 — 네이버 동기화 커서·워커 감시 등 배경 쓰기), users +8(원장 §P12-1).

### 2.4 적중률 어림 [추정]

쓰기가 서로 무관하게 일어난다고 보면 재검증 간격 T 동안 키가 안 깨질 확률은 `exp(-시간당 깨짐 × T)` 다.

| 키 입도 | 50초(fresh) | 240초(primary) |
|---|---|---|
| 표 단위(9월 방식, 시간당 약 60) | 0.43 | 0.02 |
| family 단위(10-02 값) | 대시보드 0.77 · 실측 0.87 · 생산 0.90 | 도면 0.46 · 출고 0.75 · 시공 0.79 · 이력 0.85 |
| 행 지문(이번 권장, §3.3) | 본문이 그대로인 비율(하한 추정 생산 0.85 · 실측 0.75 · 대시보드 0.59)보다 조금 낮다 — 지문은 화면에 안 쓰는 칸의 변경에도 바뀌기 때문 | (범위 밖) |

- 9월 실측 21%(이력, 240초)는 위 표의 "표 단위·240초" 줄과 같은 방향이다.
- 키가 맞아도 본문이 바뀌었으면 304 를 내면 안 되므로, 어떤 방식도 **지금의 304 건수를 넘을 수 없다.**
  즉 절감 상한은 지금 304 에 쓰는 서버 시간(10-02 기준 하루 898초)이다.

---

## 3. 설계

### 3.1 원칙

1. **키는 렌더가 쓰는 모든 입력의 함수다.** 입력 하나라도 키 밖에 있으면 그 입력만 바뀐 순간 옛 화면이
   304 로 살아남는다. 이것이 이 설계의 가장 큰 위험이다(§4).
2. **모르면 포기한다.** 허용 목록에 없는 인자, Redis·DB 키 계산 실패, 끄기 스위치 확인 실패 → 키 `None` →
   지금 경로(렌더 후 본문 해시 ETag) 그대로. 느릴 뿐 틀리지 않는다.
3. **키는 데이터를 읽기 전에 만든다.** 키(T1) → 본문(T2) 순서면 본문은 늘 키보다 같거나 새것이다. 사이에
   커밋이 끼면 다음 요청의 키가 달라져 200 이 나갈 뿐이다(9월 원장 §P12-3 의 반대 순서 문제를 없앤다).
4. **인증·권한 판정 뒤에 판정한다.** `login_required`, 시공팀 리다이렉트(`foms/platform/http.py:246-298`), 뷰 안의
   리다이렉트(실측 `open_map`, 이력 검색 이동 등)를 다 통과한 뒤에만 304 를 낸다. 권한이 바뀐 사람에게 304 로 옛 화면이 남지 않게 role·team·활성 여부를 키에 넣는다.
5. **과다 포함은 재렌더 한 번, 과소 포함은 조용히 옛 화면.** 애매하면 넣는다.

### 3.2 키 재료 — 모든 탭 공통

| 축 | 재료 | 근거·주의 |
|---|---|---|
| 판 | `KEY_VERSION="v2"` | 올리면 모든 키가 바뀐다(긴급 무효화 수단 하나) |
| 라우트 | 라우트 id + 응답 모드(fragment/critical/heavy) | `erp_shell_http.py:10-27` |
| 요청 인자 | 그 탭이 읽는 인자의 허용 목록으로 정규화, 모르는 인자면 `None` | `fragment_revalidation.py:137-161`. 공용 셸 머리가 `mine`·`tower_mine` 을 직접 읽는다(`templates/partials/shared/erp_mobile_shell_header.html:3`) — 모든 탭 목록에 넣는다 |
| 원래 쿼리 문자열 | `request.full_path` 그대로(정렬 안 한 인자 순서 + `view` 모드 포함) | 셸 머리의 "내 일" 링크가 이 값을 본문에 박는다(`erp_mobile_shell_header.html:4`, 대시보드는 href 를 따로 넘겨 예외). 정렬한 인자만 넣으면 순서만 다른 요청이 같은 키·다른 본문이 된다. 대안은 그 href 를 정규화하는 것(결정 불필요, 구현 때 택일) |
| 쿠키 | `erp_mine_only` **원래 값**, `foms_ptr`, `foms_vw`, `foms_scr` | 셸 머리는 해석된 mine 이 아니라 쿠키 원값을 본다(같은 파일 `:3`). 이력은 `from_search=1` 이면 mine 을 끄지만 셸 머리·nav 배지는 여전히 쿠키를 따른다. 표면 판정은 `foms/services/feature_flags.py:140-271` |
| 사용자 | id·role·team·활성 여부·이름·username | 모바일 셸 서랍이 이름·역할을 그린다(`erp_mobile_menu_drawer.html:42-43`). mine SQL 은 이름·username·id 를 쓴다(`foms/services/erp_permissions.py:224-289`). 하위 메뉴는 `policy_can('SETTLEMENT_DASHBOARD_READ')`(role·team·활성) |
| mine | 그 요청에 적용된 최종 판정(쿠키·시공팀 강제·통합검색 예외 포함) | 예: `history.py:174-180` |
| 대리 접속 | `session["impersonating_from"]` 값 | 서랍의 "관리자 복귀" 폼과 **CSRF 토큰의 주체**가 이 값이다. 로그인 사용자 CSRF seed 는 세션에 저장하지 않고 (대리 접속자 id 또는 uid) + secret 으로 만든다(`foms/services/request_write_guard.py:181-233`, `:255-264`). 빠지면 같은 사용자를 대리 접속한 두 관리자가 같은 키·다른 토큰 → 304 로 남의 토큰 폼 → 로그아웃·복귀가 403 |
| 코호트 | `inject_foms_flags()` 전량 + `inject_status_list` 의 플래그(`erp_mobile_v2_enabled`·`shell_variant`·`can_toggle_order_flags`·`can_toggle_factory2_flag`·`use_direct_upload`·`erp_order_enabled`) + 표면 3종 | `foms/services/context_processors.py:215-284`, `:359-401`. S2a 는 앞의 것만 넣었다 |
| 릴리스·환경 | `RAILWAY_DEPLOYMENT_ID`(+ 커밋 SHA) | 9월 키는 커밋 SHA 를 먼저 썼다(`fragment_revalidation.py:271-274`). 환경변수만 바꾼 재배포는 SHA 가 같아 env 플래그 변화(예: 네이버 묶음 발송 플래그 `feature_flags.py:345-465`)를 놓칠 수 있다. 배포 id 는 재배포마다 바뀌고 같은 배포의 프로세스 4개가 같은 값을 갖는다 |
| 날짜 | KST 오늘(완료 탭은 달 단위 KPI 도 이것으로 덮인다) | 날짜 창·D-날·D+날 표시. fresh 3탭의 상대 시각("N분 전")은 서버가 아니라 JS 가 그린다(예: `templates/production/partials/scripts.html:1142-1144`). 예외는 AS 탭(§3.4) |
| 하루 안에서 흐르는 시간 | 신선도 상한 버킷(§3.6)이 덮는다 | **48시간 "도면 지연"** 은 `now - workflow.stage_updated_at ≥ 48h` 로 하루 중 아무 때나 뒤집힌다(`foms/services/erp_display.py:484-495`) — 대시보드·실측·생산·출고·이력 카드와 대시보드·생산 숫자판이 쓴다. 완료 60일 창 `Order.dashboard_active_filter` 는 초 단위 `datetime.now()`(`models.py:220-247`), 네이버 미연결 60일 창도 같다. 오늘 날짜만 넣으면 이 값들은 자정이나 다음 쓰기까지 옛 값으로 남는다 |
| 모바일 셸 값 | `erp_mobile_v2_enabled` 일 때 nav 배지 숫자 dict 자체 | 프래그먼트가 셸을 싣는다(`templates/production/partials/dashboard_body.html:4-5` 등). 배지는 프로세스 메모리 30초 캐시(`foms/services/dashboard_counts.py:23`, `:107`) |
| 데이터 | 탭별 데이터 지문(§3.3, §3.4) | |
| 신선도 상한 | `floor((지금초 + uid 별 어긋남) / C)` | §3.6, 결정 사항 |

### 3.3 데이터 버전 — 세 방식 비교와 권장

| | A. 대시보드 캐시 무효화 지점에서 family 번호 INCR | B. 세션 훅에서 탭별 세대 번호 INCR | **C. 탭이 읽을 행의 `xmin` 지문 (권장)** |
|---|---|---|---|
| 어떻게 | `invalidate_dashboard_family` 가 지울 때 `foms:tabgen:<family>` 를 함께 올린다 | S1 훅이 더러운 주문마다 "어느 탭에 보이나(전/후)"를 분류해 탭 번호를 올린다. 모르면 전부 | 렌더 전에 그 탭과 **같은 필터 객체**로 `SELECT 행 수, md5(string_agg(id‖xmin))` 를 한 번 돌리고, 딸린 표(첨부·일정·제작 회차 등)도 그 id 들로 같은 지문을 뜬다 |
| 엔진 밖·워커·raw SQL 쓰기 | **놓친다.** 9월 조사에서 orders 쓰기 110경로 중 61경로가 엔진 밖이고 그중 손으로 무효화를 부르지 않는 곳이 있다(예 `foms/api/production/orders.py:1110-1137`). 워커 프로세스에는 무효화 훅 자체가 없다(원장 §P8 S1-2) | ORM 은 덮고, 우회 쓰기는 기존 스캔 게이트로 전부 "모두 올림" | **전부 잡는다.** 행이 바뀌면 `xmin` 이 바뀐다(경로·프로세스 무관) |
| 규칙이 HTML 에 맞나 | 아니다. "캐시 조각이 그 값을 담나" 규칙이라, 화면에 보이는 행의 다른 칸이 바뀌어도 그 탭 family 를 안 비울 수 있다. 오늘은 행 내용을 렌더마다 새로 읽고 TTL 이 덮어서 문제가 안 된다 | 탭마다 SQL 필터를 파이썬으로 한 벌 더 써야 한다 — 둘이 어긋나면 옛 화면 | 같은 필터를 다시 돌리므로 어긋날 수 없다 |
| 시간이 흘러 창에서 빠지는 행 | 놓친다(예: `models.py:220-247` 완료 60일 창은 초 단위 `datetime.now()`) | 놓친다(별도 처리 필요) | 잡는다(필터를 매번 다시 돈다) |
| Redis INCR 실패 | 그 쓰기를 영영 놓친다(지금 S1 도 경고만 남긴다, `table_version_counter.py:277-286`) | 같다 | 데이터 부분은 Redis 무관 |
| AS·완료 | family 없음 | 새로 정의 | 같은 방식 |
| 키 비용 | Redis MGET 1회(약 1~2ms) | 같다 | SQL 1회 + 조각 캐시 읽기, 10~40ms [추정, 1단계에서 실측] |
| 구현 범위 | 작다 | 크다(분류기·실데이터 대조) | 크다(뷰를 "무엇을 그릴지 정하기"와 "그리기" 두 단계로 나눈다) |

**권장 C.** A 는 지금 구조에서 안전하지 않다 — 오늘은 무효화를 빠뜨려도 TTL 이 최대 300초로 덮지만, 버전 키로
쓰면 빠뜨린 변경은 다음 쓰기 전까지 **끝없이** 304 로 남는다. B 는 싸지만 SQL 필터를 파이썬으로 이중 관리하는
위험과 INCR 유실 구멍이 남는다. C 는 "같은 필터를 다시 돌린다"는 구조 하나로 쓰기 경로·프로세스·시간 창을
한꺼번에 덮는다. 대가는 키 계산 비용과 뷰 리팩터다.

**C 의 세부 규칙**
- 지문 SQL 은 탭 읽기 모델이 내놓는 **같은 쿼리 빌더**로 만든다(`population_query(filters, user)` 를 렌더와
  키가 함께 쓴다). 고르는 열은 `id`·`xmin` 뿐이라 JSONB 를 풀지 않는다(렌더 비용의 큰 몫인 TOAST 풀기를 피한다).
- `xmin` 은 행이 갱신·삽입될 때마다 새 값이 되고, 지워진 행은 집합에서 빠진다. 값이 같은데 바뀌는 경우
  (no-op UPDATE, 동결)는 **키가 쓸데없이 바뀌는 쪽**이라 안전하다.
- 조각 캐시(Redis DTO)에서 온 숫자·id 목록은 **값 자체의 digest** 를 키에 넣는다. 넣지 않으면 "무효화를
  빠뜨려 낡은 조각이 렌더됨 → TTL 만료로 조각이 새로 계산돼 본문이 바뀜 → 그러나 DB 행은 그대로라 키도
  그대로" 가 되어 낡은 조각 화면이 갇힌다(조각 갇힘).
- 작은 공용 표는 `xmin` 이 아니라 **화면에 쓰는 열의 값 digest** 로 뜬다.
  - `users`: id·name·username·role·team·is_active 값의 digest(행 수십 개). `xmin` 을 쓰면 안 되는 이유 —
    활동 중인 세션마다 5분에 한 번 `last_login` 을 ORM 밖 `update()` 로 쓴다(`foms/services/user_activity.py:29`,
    `:42-80`, 재확인). 사용자 열댓 명이면 users 행이 분에 몇 번씩 바뀌어 키가 계속 깨진다.
  - `system_settings`: 그 탭이 읽는 `setting_key` 행의 값 digest(배경 쓰기가 하루 +175 라 표 단위면 적중률이 깨진다).
- 쌓기만 하는 표(order_events 등)는 그 탭이 보는 주문 id·이벤트 종류·기간으로 좁힌 `행 수 + 최대 id` 로 충분하다.
  단 "그 표에 UPDATE 가 없다"를 스캔 계약으로 고정한다(있으면 `xmin` 지문으로 바꾼다).
- 렌더의 두 번째 단계는 첫 단계가 읽은 조각 값을 넘겨받아 다시 읽지 않는다(키 계산이 이중 일이 되지 않게).
- nav 배지(모바일 v2)는 값 자체를 넣는다. 컨텍스트 프로세서가 어차피 계산하는 값이고 프로세스 메모리 30초 캐시라
  두 번째 읽기는 거의 공짜다.
- SQL 이 아니라 파이썬이 시각으로 계산하는 값(48시간 도면 지연)은 지문이 못 잡는다 — §3.6 상한 버킷이 덮는다.

### 3.4 탭별 재료

조사 방법: 9탭 뷰에서 시작해 `foms/services/**` 도우미와 템플릿 include 를 끝까지 따라갔다(병렬 조사 3갈래 +
감독자 재확인). "재확인" 표시가 있는 줄은 감독자가 코드에서 직접 봤다. 공용 셸·컨텍스트 값은 §3.2 에 있다.

**모바일 v2 코호트면 모든 탭 프래그먼트가 공용 셸을 싣는다**(예 `templates/production/partials/dashboard_body.html:4-5`,
`templates/measurement/partials/dashboard_main.html:13-14`, `templates/orders/partials/dashboard_main.html:23-24`, 재확인).
`erp_mobile_v2_enabled` 는 코호트 판정이라 광폭 PC 에서도 켜진다. 셸이 그리는 것: nav 배지 숫자, 이름·역할, 대리 접속
복귀 폼과 CSRF 2개, `mine`/`tower_mine`/쿠키 원값으로 정하는 "내 일" 상태와 `request.full_path` href,
`flag_offline_sw`·`flag_bottom_nav_htmx`.

#### 생산 `/erp/production/dashboard` (1순위)

| 항목 | 내용 |
|---|---|
| 인자 | `stage`, `q`/`search`, `mine`, `focus_order`, `page`, `sort`(실측일·시공일만), `dir`, + 공용 `tower_mine` (`foms/services/production_dashboard_filters.py:45-56`) |
| 쿠키 | `erp_mine_only`, `foms_ptr`(칸반을 만들지), `foms_vw`, `foms_scr`(PC 격자) |
| 사용자 | id(사용자별 확인 창·삭제 묘비), role(`can_act_production`), team, name·username(mine) |
| 조각 캐시 → 값 digest | `production/summary_counts` 300초(`foms/web/production/dashboard.py:106-121`, 재확인 — 지문에 **오늘·team 없음**, 단계별 숫자에 48시간 도면 지연 포함 `foms/services/production_read_model.py:216-217`), `attachment_counts` 120초(`:197-217`) |
| 행 지문 | orders(목록 또는 칸반 최대 300행, focus 행), **production_runs**(`:222`, S1 6표 밖), **order_events**(변경 알림·확인 — 확인 API 는 주문을 안 바꾸고 이 표에만 쓴다, `foms/api/production/orders.py:1328-1336` 재확인), order_attachments(미리보기), users(도면 담당 이름), system_settings(출고 설정 키 1행), 삭제 묘비(삭제 주문 + 확인 이벤트, 오늘−14일) |
| 시간 | 날짜: D-n·D+n·주간 KPI·묘비 창. 흐르는 시간: 48시간 도면 지연 |
| env | 셸 코호트, `FOMS_OFFLINE_SW_ENABLED`, `FOMS_BOTTOM_NAV_HTMX_ENABLED`, 조각 캐시 플래그 |
| 판정 자리 | `dashboard.py:104`(쿼리 객체만 만든다)와 `:106` 사이. 첫 I/O 는 `:115` 조각 읽기. `kanban_wanted`(`:159`)는 쿠키·env 만 보므로 앞으로 당긴다 |

#### 실측 `/erp/measurement` (2순위)

| 항목 | 내용 |
|---|---|
| 인자 | `q`/`search`/`manager`, `date_from`·`date_to`(92일로 자름), `date`, `open_map`(리다이렉트), `manager_filter`, `focus_order`, `mine`, + `tower_mine` (`foms/services/measurement_dashboard_filters.py:55-73`, 뷰 `:299`) |
| 쿠키 | `erp_mine_only`, `foms_ptr`+`foms_vw`(모바일 묶음 계산 여부, `:488`) |
| 사용자 | id·role·username·team(조각 지문), name(mine·"나" 표시), `can_edit_erp`·`ERP_EDIT` 정책 |
| 조각 캐시 → 값 digest | `measurement_panel_assembly` 300초(`foms/web/measurement/dashboard.py:264-292`), `main_rows` 300초(`:300-334`, 오늘 없음), `measurement_product_items_build` 90초(`:378-404`) |
| 행 지문 | orders·order_schedule_dates(캐시된 id 를 다시 읽는 행), users(숫자 담당자 값마다 조회 `foms/services/erp_display.py:106-119`), system_settings(키 행), 영업 배송 지도용 orders 최대 300·일정, **네이버 발송 띠**(`:570-571` → `foms/services/integrations/naver_commerce/bulk_dispatch.py:1179-1281`: orders·일정·**external_order_links**(워커가 쓴다)·system_settings 백필 상태). 모바일 v2+모바일 폭일 때만: order_attachments·**order_events**+users(타임라인)·production_runs·**notifications**(당일 표시) |
| 시간 | 날짜: 패널 오늘~+14, 기본 날짜, `is-today`, D-day, 영업일 D-4/D-3. 흐르는 시간: 48시간 도면 지연, 60일 창 2개 |
| env | `FOMS_NAVER_BULK_DISPATCH_ENABLED`, `FOMS_NAVER_AUTO_DISPATCH_ENABLED`·`_AT`, `ERP_ORDER_ENABLED`, 셸 코호트, 셸 플래그 2개 |
| 판정 자리 | `open_map` 리다이렉트(`:213`) 뒤, 첫 I/O(`:282` 패널 조각) 전 — 대략 `:257`. `focus_order`(`:299`)를 앞으로 당기고, `mine_filter_active`(`:250`)는 사용자 객체라 `bool()` 로 정규화 |
| 주의 | 네이버 발송 띠는 캐시 없이 34~68ms(원장 10-01 운영 구간값)라 키 단계에서 그 입력(external_order_links 행 지문 + 플래그 + 오늘)을 따로 떠야 한다. 실측 탭은 입력이 가장 많아 1단계 그림자에서 mismatch 가 가장 나기 쉽다 |

#### 대시보드 `/erp/dashboard` (3순위)

| 항목 | 내용 |
|---|---|
| 인자 | `parse_orders_dashboard_filters`(`foms/services/orders/dashboard_filters.py:63-101`)의 `stage`·`urgent`·`has_alert`·`alert_type`·`q`/`search`·`team`·`sort`·`dir`·`today`·`tower_mine`·`mine`(빈 값도 의미 있음)·`date`·`field`·`risk`·`focus_order`·`status` + 뷰의 `page`·`from_history`·`from_dashboard`·`view=='queue'`·`mobile_chunk`·`order` |
| 쿠키 | `erp_mine_only`, `foms_ptr`, `foms_scr`, `foms_vw` |
| 사용자 | id·role·team·name·username, `is_admin`, 퀘스트 승인 버튼(role·team·id), `data-user-*` 속성 |
| 조각 캐시 → 값 digest | `orders/summary_counts` 300초(`foms/web/orders/dashboard.py:317-338`), `attachment_assignee_maps` 120초(`:348-373`), `mobile_control_tower` 300초(타워+모바일 폭일 때) |
| 행 지문 | orders(`_q.count()` 전체 수 + 50행 페이지 + focus + 이력 더보기), order_schedule_dates(`today`·`date` 필터), production_runs(생산 단계 행 보드 상태), users·order_assignments(네이버발 행 미배정), system_settings(담당 전화 지도 키), order_attachments(미리보기) |
| 시간 | 날짜: D-N 배지·D-4/3/2 창·`today_count`·타워 주간·`today_iso`. 흐르는 시간: 48시간 지연(숫자판·`alert_type`·타워 정체 목록), 60일 창 |
| env | 셸 코호트, `FOMS_TABLET_SPLIT_VIEW_ENABLED`, `CHANNEL_DESK_URL`, `ERP_ORDER_ENABLED`, `USE_DIRECT_UPLOAD`(+저장소 종류), 셸 플래그 2개 |
| 판정 자리 | 필터 해석 뒤 `:159`, 첫 I/O(`:164` 위험 필터 또는 `:175` count) 전 |
| 주의 | 진행 중 주문 전체가 숫자판에 걸리므로 적중률이 가장 낮을 것이다(§2.4). 전체 수(`count`)를 키 단계에서 돌려야 해서 키 비용도 셋 중 가장 크다 |

#### primary 6탭 — 이번 범위 밖, 다시 열 때 알아야 할 것

| 탭 | 하루 304 서버초 | 함정 |
|---|---|---|
| 도면 | 51 | 템플릿이 `request.args` 전체를 링크에 다시 싣는다(`templates/drawing/partials/workbench_dashboard_macros.html:1-30`). 큐 id 조각(300초) 지문에 name·username 없음. 판정 자리 `foms/web/drawing/workbench.py:604-606` |
| 출고 | 36 | 패널 조각 지문에 패널 id 가 들어가 패널 쿼리는 매번 돈다. 확인 API 가 order_events 만 쓴다(`foms/api/shipment/change_ack.py:242-246`, 재확인). 출고 설정은 캐시 없이 요청당 2회 이상 읽는다 |
| 시공 | 28 | 숫자판 지문에 team·name 없음(`foms/web/construction/dashboard.py:93-102`, 재확인), 자정 넘어 300초 동안 어제 D-3 숫자 |
| AS | 20 | **v2 가 아닌 사용자 카드가 서버에서 "방금/N분 전/N시간 전"을 그린다**(`foms/services/orders/as_log.py:254-269` → `templates/cs/partials/as_card_macros.html:52`, 재확인) — 분 단위로 본문이 바뀐다. 조각 캐시 없음(전부 매번 SQL). 304 비율이 9탭 중 가장 낮은(34%) 까닭과 맞는다 |
| 완료 | 18 | v2 가 아니면 뷰가 DB 를 안 읽는다(목록은 브라우저가 `/api/orders/completion` 으로 받는다). 입력이 가장 적어 가장 쉬운 후보지만 이득도 가장 작다 |
| 이력 | 14 | 9월 S2a 배선이 있는 곳. 필터 없는 하트비트는 빈 목록이라 304 p50 32ms — 아낄 게 없다 |

### 3.5 304 응답 규칙

1. **`If-None-Match` 가 없는 요청은 지금과 똑같이 처리한다**(렌더 후 본문 해시 ETag). 이런 요청은 화면 전환·
   첫 로드라 사용자가 기다린다 — 키 SQL 을 얹지 않는다. 있는 요청(뒤에서 도는 재검증)에서만 키를 만든다.
   키 ETag 는 `"fv2-<16자>"` 처럼 접두어로 본문 해시와 구별한다. 클라가 본문 해시 ETag 를 들고 오면 첫 번
   재검증에서 렌더 + 키 ETag 발급, 그다음부터 렌더 전 304 가 걸린다(탭 전환 뒤 렌더 한 번 더).
   키가 `None` 이면 지금 경로.
2. 받은 `If-None-Match` 의 각 값에서 압축 접미사를 벗겨(`strip_content_encoding_suffix`,
   `fragment_revalidation.py:114-134`, zstd/br/gzip/deflate) 키와 비교한다.
3. 같으면 **렌더 없이 304**: 본문 없음, 받은 검증자 에코, `X-FOMS-ERP-FRAGMENT`·`X-FOMS-ERP-FRAGMENT-TIER`
   유지, 진단 헤더 `X-FOMS-FRAGVER: hit`. 클라는 304 에서 헤더를 안 보지만(`erp-shell.js:691-700`) 그대로 둔다.
4. 다르면 렌더하고 ETag 를 **본문 해시가 아니라 키**로 단다. Flask-Compress 가 200 에 접미사를 붙이고,
   다음 요청은 2번에서 벗겨 비교한다. 압축 후 재평가(`app_factory.py:220`)는 키 ETag 와 클라 검증자가
   다르므로 200 그대로 둔다.
5. 클라 코드는 바꾸지 않는다.

### 3.6 신선도 상한 C (방어선)

키에 `floor((epoch초 + hash(uid) mod C) / C)` 를 넣으면 재료를 하나 빠뜨려도 옛 화면은 **최대 C초 + 재검증
주기**로 끝난다. 오늘 조각 캐시가 주는 안전망(TTL 최대 300초)과 같은 수준을 지키는 장치다. uid 별로 경계를
어긋나게 해 모두가 같은 순간 재렌더하는 몰림을 막는다. 대가: 50초 주기에서 경계를 넘는 비율 50/C 만큼 적중률이
깎인다(C=300 이면 약 17%, C=600 이면 약 8%).

**이 상한은 선택이 아니라 필수에 가깝다.** 48시간 도면 지연은 쓰기 없이 하루 중 아무 때나 뒤집히고, 그 값은
파이썬이 시각으로 계산해 행 지문에 안 잡힌다. 오늘도 생산 숫자판 조각(지문에 시각 없음, TTL 300초)이 같은 늦음을
갖고 있으므로 C=300 이면 지금보다 나빠지지 않는다. 상한을 없애려면 그런 값마다 "다음 경계 시각"을 키 재료로
따로 만들어야 한다. **C 값은 결정 사항.**

### 3.7 단계별 적용 순서와 끄기 스위치

| 단계 | 내용 | 넘어가는 기준 |
|---|---|---|
| 0 | primary 스윕에서 fresh 3경로 빼기(§3.8). 렌더 전 304 와 무관한 JS 한 곳 | 스테이징 실화면에서 fresh 3경로 갱신 주기 50초 유지 확인 |
| 1 | 계기 고치기(S2a′) + 생산 탭 두 단계 분리: 키를 렌더 **전**에 만들고(조건부 요청에서만, §3.5), 생산 탭에 그림자 관측. 키 계산 시간·렌더 시간·적중·mismatch 상세(라우트·인자 이름·코호트 digest·세션 여부)를 남긴다. **약하게 만든 대조 키**(데이터 지문 하나를 뺀 것)도 함께 관측해 계기가 mismatch 를 잡을 수 있음을 증명한다 | 운영 영업일 5일, 관측 각 1,000건 이상, 본 키 mismatch 0, 대조 키 mismatch > 0, 적중률 ≥ 50%, 키 계산 ≤ 렌더의 30%(p50) |
| 2 | 생산 탭 켜기(+ 상한 C, 표본 검증 렌더 5%) | 영업일 5일 표본 검증 mismatch 0 |
| 3 | 실측 탭: 두 단계 분리 → 그림자 → 켜기 | 1·2단계와 같은 기준 |
| 4 | 대시보드 탭: 두 단계 분리 → 그림자 → 적중률이 기준을 넘을 때만 켜기 | 같은 기준(적중률이 가장 낮을 것으로 예상) |
| 보류 | primary 6탭 | 합쳐 하루 약 170초. 이번 범위 밖, 3탭 결과를 보고 다시 판단 |

생산을 먼저 하는 이유: 본문이 그대로인 비율이 가장 높고(85%), 템플릿이 가장 가볍고, "도면 수정 중" 배지라는
분명한 옛 화면 확인점이 있다(fresh 경로로 옮긴 이유 자체가 그 배지의 신선도였다, `erp-shell.js:50-52`).
실측은 이득이 가장 크지만 입력이 가장 많아 둘째에 둔다.

**끄기 스위치(세 겹)**
1. env `FOMS_FRAGMENT_PRERENDER_304_ENABLED`(기본 off) + `FOMS_FRAGMENT_PRERENDER_304_TABS`(켤 탭 목록).
   Railway 는 변수를 바꿔도 재배포가 저절로 안 걸리므로 이것만으로는 즉시 끄기가 안 된다.
2. Redis 런타임 키 `foms:fragver:v2:off`(전체)·`foms:fragver:v2:off:<route>`(탭별). 키 계산의 Redis 읽기와
   한 번에 읽는다. 읽기 실패 = 꺼짐으로 본다. **배포 없이 즉시 끈다.**
3. 표본 검증 렌더가 mismatch 를 보면 그 탭의 런타임 키를 24시간 TTL 로 스스로 켜고(=그 탭 끄기) ERROR 로그를
   남긴다.
- 끈 뒤: 다음 요청부터 렌더 후 본문 해시 ETag 로 돌아간다. 클라가 들고 있던 키 ETag 는 본문 해시와 다르므로
  한 번 200 을 받고 다시 맞춰진다. `KEY_VERSION` 을 올리면 모든 클라 캐시가 한 번씩 200 으로 갱신된다.

### 3.8 0단계 — primary 스윕의 fresh 중복 빼기

`runPrimaryHeartbeat`(`erp-shell.js:1136-1167`)의 대상 목록에서 `FRESH_TTL_PATHS` 를 뺀다. fresh 스윕이 같은
조건(`heartbeatActive`)에서 50초마다 이미 갱신하므로 신선도는 그대로다. 활성 탭 하나당 시간당 30~45회
(지금 화면이 fresh 경로면 2×15, 아니면 3×15) — 전체 336회의 9~13% — 가 줄고, 줄어드는 요청은 50초 안에
이미 갱신된 경로라 거의 전부 304 였다. fresh 경로 304 중 약 12~17% 가 primary 스윕에서 온 것으로 보면
하루 약 100~180초 [추정]. 지금 화면 경로를 fresh 스윕에서 빼는 안은 **넣지 않는다** — 다른 탭에 갔다 돌아올 때
캐시가 식어 사용자가 기다리게 된다(체감 후퇴).

---

## 4. 위험

| # | 위험 | 결과 | 막는 장치 |
|---|---|---|---|
| 1 | **키 재료 하나 빠짐**(인자·쿠키·env·표·시간 창·컨텍스트 값) | 그 입력만 바뀐 순간 옛 화면이 304 로 남는다(가장 큰 위험) | §5 의 입력 기록 계약·행동 계약·음성 대조군, 그림자 관측, 표본 검증 렌더, 상한 C, 즉시 끄기 |
| 2 | 조각 갇힘(낡은 조각 캐시 + 그대로인 행) | TTL 이 지나도 화면이 안 고쳐진다 | 조각 값 digest 를 키에 넣는다(§3.3) |
| 3 | 9월 스테이징 mismatch 7건(원인 미상, 같은 릴리스 안) | "모르는 축이 하나 더 있다"는 신호 | 1단계 첫 숙제: 확장된 mismatch 상세로 재현·원인 판정 전에는 2단계 금지 |
| 4 | 키 계산이 렌더만큼 비싸다(특히 데이터 읽기가 비용의 대부분인 탭) | 이득 없음. 키를 모든 요청에서 만들면 사용자가 기다리는 화면 전환도 10~40ms 느려진다 | 키는 조건부 요청에서만(§3.5 1번). 1단계에서 키 시간/렌더 시간 실측, 30% 넘으면 그 탭 제외 |
| 5 | 적중률이 낮다(대시보드: 모든 진행 주문이 보이는 화면) | 이득 없음(9월 재현) | 탭별 판정, 기준 미달이면 켜지 않는다 |
| 6 | nav 배지가 프로세스마다 다르다(메모리 30초 캐시 4벌) | 같은 사람인데 프로세스마다 키가 갈려 적중률 손실(옛 화면은 아님). 지금 본문 해시 ETag 도 같은 이유로 흔들린다 | 결정 사항: 배지를 Redis 공유 캐시로(P2-2 의 네이버 배지와 같은 방식) |
| 7 | 권한 변경 직후 | 304 로 옛 화면 유지 | role·team·활성 여부를 키에, 판정은 권한 확인 뒤 |
| 8 | 세션·CSRF·대리 접속 | 옛 토큰 폼 → 로그아웃·복귀·저장 403 | 대리 접속 id 를 키에(9월 세션 재료는 늘 `"-"` 인 죽은 재료였다, §1.3). uid 는 키에 있고, secret 교체는 재배포라 배포 id 가 덮는다 |
| 9 | 배포 직후 | 옛 자산 핀 마크업 | 배포 id 를 키에(§3.2) |
| 10 | 진단 헤더·로그가 업무 데이터를 흘린다 | 정보 노출 | 헤더 값은 상태 단어와 16자 해시만, 로그는 인자 **이름**만 |
| 11 | 쓰기 없이 시각으로 뒤집히는 표시(48시간 도면 지연) | 상한 C 만큼 늦게 바뀐다 | 오늘 생산 숫자판 조각도 같은 늦음(TTL 300초)이라 C=300 이면 지금과 같다(§3.6) |
| 12 | "쌓기만 하는 표" 가정이 깨진다(order_events 에 UPDATE 가 생김) | 행 수·최대 id 지문이 변경을 놓친다 | 스캔 계약으로 고정, 깨지면 `xmin` 지문으로 |
| 13 | 공용 셸이 `request.full_path` 를 본문에 박는다 | 인자 순서만 다른 요청이 같은 키·다른 본문 | 원래 쿼리 문자열을 키에 넣거나 href 를 정규화(§3.2) |

---

## 5. 테스트 계획

### 5.1 계약 테스트 (탭마다)

1. **입력 기록 계약**: 테스트 클라이언트로 렌더하는 동안 `request.args`·`request.cookies`·`session`·`os.environ`
   읽기를 기록하는 대리 객체를 끼우고, SQLAlchemy `before_cursor_execute` 로 실행된 SQL 의 표 이름을 모은다.
   기록된 이름이 그 탭 키 명세(허용 인자·쿠키·세션 키·env 목록·지문 표 목록)의 **부분집합**이어야 통과.
2. **행동 계약(변이표)**: 실데이터 꼴 시드에서 변이 하나씩 — 화면 행의 고객명 변경, 단계 변경, 첨부 추가·삭제,
   일정 날짜 변경, 사용자 이름 변경, 설정 키 변경, 제작 회차 추가, 시각을 1분·1시간·하루·60일 창 경계 넘게 이동,
   쿠키·env 플래그 전환 — 을 적용한 뒤 **"본문이 바뀌었으면 키도 바뀌었다"** 를 단언한다. 반대(키만 바뀜)는 허용.
3. **음성 대조군**: 키 명세에서 재료 하나(예: `order_attachments` 지문, `tower_mine` 인자)를 뺀 변종으로 1·2 를
   돌리면 **반드시 실패**해야 한다. 이게 통과하면 계약이 아무것도 못 잡는다는 뜻이다. 대조군은 실제 탭 재료에서
   고른다.
4. **순서 계약**: 키 계산과 데이터 읽기 사이에 커밋을 끼워 넣으면 다음 요청이 200 이어야 한다.
5. **응답 모양**: 렌더 전 304 는 본문 없음·검증자 에코·셸 헤더 유지, `:zstd`/`:br` 접미사 검증자로도 304.
6. **실패 안전**: Redis 없음·지문 SQL 실패·런타임 끄기 키 → 지금 경로(200 또는 렌더 후 304).
7. **기존 계약 재작성**: `test_erp_shell_fragment_conditional.py:74`(같은 내용 → 같은 키)·`:120`(주문 추가 →
   키 변경, 렌더 전 304 경로에서도 200 — 느슨하게 풀지 않는다)·`:151`(접미사). perf-gate 의
   `etag_required`·`conditional_304_required` 는 그대로 성립해야 한다.

### 5.2 운영 관측

- 그림자(S2a′): 조건부 요청에서만 키를 렌더 전에 만들고, 렌더 뒤 본문 해시와 대조. 본 키와 약한 대조 키를 함께
  센다. mismatch 상세에는 라우트·인자 **이름**·코호트 digest·대리 접속 여부·두 관측의 배포 id 를 남긴다.
- 켠 뒤 표본 검증 렌더: 304 로 끝낼 요청의 5% 는 그대로 렌더해 그 키로 기록된 본문 해시와 대조, 어긋나면
  그 탭을 스스로 끈다(§3.7).
- 판정 지표: `X-FOMS-FRAGVER`·Redis 상태별 카운터 + 운영 httpLogs 의 탭별 304 서버 시간(§2 와 같은 방법).

### 5.3 실행할 명령(구현 단계)

- `python -m pytest tests/domains/test_fragment_revalidation.py tests/domains/test_erp_shell_fragment_conditional.py -q`
- `python -m pytest tests/harness -q -x -n auto`
- `python tools/harness/orm_bypass_write_scan.py --check`(C 방식은 이 게이트에 기대지 않지만 S1 이 남는다)
- `scripts/ops/pre_push_smoke.ps1` exit 0, push 뒤 CI·perf-gate green

---

## 6. 기대 이득 [추정]

| 범위 | 상한(10-02 실측 304 서버초) | 어림 | 근거 |
|---|---|---|---|
| 0단계 중복 제거 | — | 하루 100~180초 | 활성 탭당 요청 9~13% 감소, 줄어드는 요청은 거의 304 |
| 생산 | 209 | 120~170 | 적중 0.75~0.85, 키 비용 렌더의 15~30% |
| 실측 | 284 | 150~220 | 적중 0.7~0.85, 키 비용 15~30% |
| 대시보드 | 271 | 40~160 | 적중 0.3~0.7, 모든 진행 주문이 보이는 화면 |
| **합계(1~4단계)** | **764** | **약 300~550초/일** | |

- 사용자가 직접 기다리는 시간은 거의 줄지 않는다(뒤에서 도는 요청). 줄어드는 것은 오전 피크의 DB·CPU 부하이고,
  P3-1(오전 컨텍스트 프로세서 DB 대기) 꼬리에 간접 효과가 있을 수 있으나 그 크기는 재 보지 않았다.
- 9월 웹 전체 서버 처리 시간 대비 304 렌더가 22% 였다는 점이 이 일을 다시 여는 근거다. 그 뒤 실측 탭 등이
  빨라져 지금 비중은 더 작다.

---

## 7. 사용자 결정 목록

1. **다시 열지**: 9월에 "이득 없음"으로 접은 렌더 전 304 를, 키 입도를 바꿔 다시 연다. (아니면 0단계만 한다.)
2. **0단계 먼저**: primary 스윕에서 fresh 3경로 빼기를 렌더 전 304 와 떼어 작은 변경으로 먼저 낼지.
3. **범위**: fresh 3탭만(권장) / 9탭 전부.
4. **데이터 버전 방식**: C 행 지문(권장) / B 세션 훅 세대 번호 / A 대시보드 캐시 무효화 지점 재사용(비권장).
5. **신선도 상한 C**: 300초(오늘 조각 캐시와 같은 수준, 권장) / 600초 / 두지 않음(48시간 지연처럼 시각으로
   뒤집히는 값마다 "다음 경계 시각" 재료를 따로 만들어야 해서 비권장).
6. **운영 그림자 관측 켜기**: 운영 web env 변경 1회 + 탭마다 영업일 5일 관측. 조건부 요청(뒤에서 도는 재검증)에서만
   돌므로 사용자가 기다리는 요청에는 얹히지 않는다. 대신 그 재검증 요청이 키 SQL·본문 해시·Redis 왕복만큼 느려진다.
7. **넘어가는 기준**: mismatch 0 · 적중률 ≥ 50% · 키 계산 ≤ 렌더의 30% · 영업일 5일이 적당한지.
8. **즉시 끄기**: Redis 런타임 키(배포 없이 끔, 권장) / env 만.
9. **표본 검증 렌더 비율·자동 끄기**: 5% + 탭 자동 끄기(권장) / 다른 값.
10. **nav 배지 공유 캐시**: 모바일 v2 코호트의 키 흔들림을 줄이려 배지를 Redis 공유 캐시로 옮길지(별건).

---

## 8. 곁가지 발견 (이 설계와 별개, 미조치)

1. **대시보드 숫자판 조각의 지문 빈틈(코드상 확인, 화면 영향 미확인)**: `orders/summary_counts` 지문은
   mine·q·team·today 만 담는데(`foms/web/orders/dashboard.py:317-327`), 집계 쿼리 `_q_stats` 는 `date`·`field`·
   `risk`·`status` 필터를 건 **뒤에** 복제된다(`foms/services/orders/dashboard_read_model.py:102-140`). 필터만 다른
   요청들이 최대 300초 동안 한 숫자판 값을 나눠 쓸 수 있다. 렌더 전 304 와 무관하게 고칠 후보.
2. **생산 숫자판 조각 지문에 오늘·team 이 없다**(`foms/web/production/dashboard.py:106-113`, 재확인). 자정 직후나
   48시간 경계 뒤 최대 300초 옛 숫자. 시공 숫자판도 mine 일 때 uid·role 만 담고 mine SQL 이 쓰는 이름·username·
   team 은 없다(`foms/web/construction/dashboard.py:93-102`, 재확인).
3. **AS 탭(v2 아닌 사용자)은 서버가 "N분 전"을 그린다**(§3.4). 그래서 304 가 잘 안 난다(34%). 이 표시를 JS 로 옮기면
   지금 방식(렌더 후 본문 해시)으로도 AS 의 304·전송량이 좋아진다.
4. **하트비트 목록이 팀과 무관하다**: 시공팀은 출고·시공·완료·이력 밖의 `/erp/` 를 302 로 돌려보내는데
   (`foms/platform/http.py:246-298`), 하트비트는 누구에게나 9경로를 부른다(`erp-shell.js:12-22`). fetch 는 302 를
   따라가 출고 프래그먼트를 한 번 더 그린다. 3일간 9탭 302 는 실측 32·대시보드 15·생산 1건 등으로 작다(AS 111건은
   검색·포커스 리다이렉트가 섞여 있어 따로 봐야 한다). 목록을 팀 메뉴(`erp_mobile_shell.html:23-47`)와 맞추면 사라진다.
5. **출고 설정을 캐시 없이 요청당 2회 이상 읽는다**(`foms/services/erp_shipment_settings.py:214`, 원장 P3-8 과 같은 건).
   설정 행이 없으면 GET 안에서 JSON 이주 커밋도 한다(`:218-232`, 실제로는 1회성).
