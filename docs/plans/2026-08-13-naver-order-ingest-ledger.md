# NAVER-INGEST-01 진행 원장 (네이버 스마트스토어 주문 자동 수집)

- 스펙: `docs/specs/2026-08-13-naver-order-ingest_SPEC.md` (승인 완료)
- 등급: `**C` 릴레이 — task 단위로 구현 → 검증 → 커밋 → 이 원장 갱신
- 작업 위치: **세션 worktree `c:\tmp\foms-s-naver-ingest`** (브랜치 `session/naver-ingest`, base `origin/deploy`)
- push 대상: **deploy 전용** (production 승격 금지)

> **주의 — 메인 트리(`C:\DEV\FOMS`)는 쓰지 말 것.** 2026-08-13 확인 시 메인 트리의 로컬
> `deploy` 는 `origin/deploy` 보다 **316 커밋 뒤처져** 있었고(merge-base 2026-07-30), `models.py`
> 를 포함해 200개 파일이 달랐다. 거기서 만든 T2 커밋(`40560f21`)은 `down_revision=auditlife_00`
> 이라 원격 체인과 맞지 않는다(원격에는 그 뒤로 마이그레이션 5개가 더 있다). 그 커밋은 폐기하고
> 이 worktree 에서 다시 만들었다. **재개 시에도 이 worktree 에서 작업한다.**
- 상태 범례: `PENDING` / `IN_PROGRESS` / `DONE` / `BLOCKED` / `N/A`

## 재개 규칙 (compaction 이후 읽는 순서)

1. 이 파일의 `## Task 표` 에서 첫 `PENDING` 을 찾는다.
2. 선행 task 가 `DONE` 인지 확인한다 (의존 열).
3. 해당 task 절(§T*)의 완료 기준 명령을 그대로 실행해 현재 상태를 재확인한 뒤 착수한다.
4. 막히면 `BLOCKED` + 사유를 기록하고 다음 독립 task 로 전진한다.

## 확정 사항 (재논의 금지 — 스펙 §7)

| # | 결정 |
|---|---|
| Q1 | 수집 주문 owner = 미배정 보류함 계정(`naver_unassigned`) 후 수동 배정 |
| Q2 | `productOption` 자동 파싱 v1 미포함 (원문만 보관) |
| Q3 | 폴링 주기 5분 (`FOMS_NAVER_SYNC_INTERVAL_SECONDS=300`) |
| Q4 | 수집 범위 전 상품 (상품 필터 없음, 필터는 `productOrderStatus == PAYED` 하나뿐) |

## 절대 지킬 함정 3개 (매 task 착수 전 재확인)

1. **네이버로 나가는 HTTP 는 WORKER 서비스에서만.** 커머스API센터 IP 한도 3 = Railway static IP 3, 여유 0.
   web 의 "지금 수집" 은 `default` 큐 rq enqueue 만 한다. web 에서 직접 호출하면 IP 불일치로 차단.
2. **네이버 좌표를 `Order.lat/lng` 에 주입하지 않는다** (2026-08-13 사용자 정정으로 설계 변경).
   네이버 좌표는 주문서 주소 기준이고 실제 고객(시공) 주소와 다른 경우가 많다. 주입하면
   `geocode_status='success'` 라 재지오코딩에서도 빠져 **틀린 좌표가 조용히 굳는다**.
   → 수집 주문도 기존 경로 그대로 지오코딩한다. `create_order()` 를 기본값으로 호출해 GEOCODE
   outbox 를 정상 예약하고, 네이버 좌표는 `raw_snapshot` 에만 남긴다.
   **`skip_geocode` 파라미터는 만들지 않는다**(초안에 있었으나 폐기 — `create_order()` 시그니처 불변).
3. **raw `Order(...)` 생성 금지** (ORDER-CREATE-01). 반드시 `create_order()` 경유.
   신규 mutation 경로는 `docs/harness/foms_order_mutation_writer_allowlist.json` +
   `docs/harness/foms_order_mutation_policy_manifest.json` 2종 등재 필수(미등재 시 CI red).

## 이 작업에서 새로 밟은 하네스 게이트 (재개 시 재발 방지)

| 게이트 | 증상 | 대응 |
|---|---|---|
| `foms/services/` 최상위 닫힌집합 (`foms_namespace_surface_tests.py` §4.4) | 새 디렉토리 `integrations` 추가만으로 red | `_SLG_FOMS_SERVICES_TOP_LEVEL_ALLOWED` 에 등재(T3에서 완료) |
| fail-open 인벤토리 (`tests/domains/test_failopen_inventory.py`) | ① 로거 없는 broad catch 1건 추가 → baseline 180→181 red ② 인벤토리 파일 미갱신 red | ① 모든 broad catch 에 `logger.warning(...)` 배선 ② `python tools/harness/failopen_scan.py` 로 재생성(**반드시 원격 tip worktree 에서**) |
| 세션 worktree alembic 차단 (`migrations/env.py`) | worktree 에서 `alembic upgrade` 실행 시 `RuntimeError` | 예외가 있다: DB 이름이 `foms_test_` 로 시작하면 허용. 왕복 검증은 `foms_test_naver_wt` 같은 일회용 DB 로 한다 |

## Task 표

| T | 내용 | 의존 | 상태 | 커밋 |
|---|---|---|---|---|
| T0 | 선행: 시크릿 재발급(사람) · 시스템 계정 2개(**완료**) · WORKER static IP(사람) | — | PARTIAL | 계정 스크립트+스테이징 반영 |
| T2 | `ExternalOrderLink` 모델 + alembic 마이그레이션 | — | DONE | `naver_link_00` (`down_revision=senderphone_00`) |
| T3 | `naver_commerce/client.py` (토큰 캐시·조회·재시도·백오프) | — | DONE | 테스트 24 green |
| T4 | 매핑 + `create_order()` 연동 (좌표 주입 없음) | T2, T3 | DONE | 테스트 20 green |
| T5 | WORKER 폴링 루프 + 게이트 + rq enqueue 경로 | T4 | DONE | 테스트 15 green |
| T1 | Railway WORKER static IP 실검증 (`--once --dry-run`) | T0, T3 | PENDING | — |
| T6 | 관리 화면 (수집 이력·수동 실행·원본 스냅샷) | T4, T5 | DONE(부분) | 테스트 13 green |
| T7 | 앱 인증 만료 D-7 알림 | — | DONE | 테스트 11 green |
| T8 | 트리아지 상태 컬럼 2개 + 마이그레이션 | T2 | DONE | `naver_triage_00` |
| T9 | 트리아지 작업대 화면 | T8 | DONE | 테스트 15 green |
| T10 | 담당자 지정(`set_sales_assignee`) | T8 | DONE(부분) | PG 레인 3 green |

> 순서 주의: 스펙의 T1(인프라 실검증)은 T0 사람 작업과 코드(T3)가 모두 있어야 가능하므로
> 실행 순서에서는 T3 뒤로 내렸다. 스펙 번호는 그대로 둔다(대조 가능하게).

---

## T0 — 선행 작업 (코드 아님, 사람 손 필요)

**항목**
1. 커머스API센터 애플리케이션 **시크릿 재발급** (2026-08-13 시험 중 세션 기록에 노출됨).
2. 시스템 계정 2개 생성:
   - `naver_ingest_bot` — role=MANAGER, actor(이벤트 author·`assigned_by`).
   - `naver_unassigned` — role=STAFF, team=SALES, active=True, **로그인 잠금**. 미배정 보류함 owner.
3. Railway **WORKER 서비스** static outbound IP 활성화 → IPv4 3개 확보 →
   커머스API센터 호출 IP 목록을 이 3개로 **교체**(사무실 IP 제거, 한도 3 = 여유 0).

**완료 기준**
- 새 `NAVER_COMMERCE_CLIENT_SECRET` 이 Railway WORKER 환경변수에 설정됨(값은 저장소에 남기지 않음).
- `SELECT id, username, role, team, is_active FROM users WHERE username IN ('naver_ingest_bot','naver_unassigned');` 2행.
- Railway WORKER `egressGateways` 에 IPv4 3개, 커머스API센터 등록 IP 와 정확히 일치.

**진행 메모 (2026-08-13)**
- 시스템 계정 2개: **완료**. 정책은 `foms/services/integrations/naver_commerce/accounts.py`,
  실행은 `python scripts/maintenance/create_naver_ingest_accounts.py`(멱등).
  **스테이징(FOMS-DEV) 반영됨** — `naver_ingest_bot` id=62, `naver_unassigned` id=63.
  **운영 DB 는 미반영**(사용자 명시 요청 시에만). 로그인은 난수 비밀번호로 잠갔다
  (`is_active=False` 로는 못 잠근다 — owner 계약이 활성 SALES 를 요구한다).
- 시크릿 재발급 · Railway WORKER static IP 3개 발급/등록: **사람 손 필요, 미완료**.
- T1(실 API 검증)은 위 둘이 끝나야 가능하다.

---

## T2 — `ExternalOrderLink` 모델 + 마이그레이션

**범위**: `models.py` 신규 테이블 + `migrations/versions/` 신규 리비전 (down_revision = `auditlife_00`).

컬럼: `id` PK / `channel` / `external_id` / `order_id` FK→orders.id nullable /
`external_order_no` / `raw_snapshot` JSONB / `sync_status`(`LINKED`·`PENDING_REVIEW`·`FAILED`) /
`failure_reason` / `created_at` / `updated_at`.
**`UNIQUE (channel, external_id)`** — 동시 실행 레이스 방어의 본체(앱 체크로는 못 막음).
워터마크 저장 위치도 이 task 에서 확정(기존 `system_setting` 계열 재사용 여부 조사 후 결정).

**체인**: `down_revision = 'senderphone_00'` (작성 시점 원격 tip). 원격 체인은
`auditlife_00 → accesslog_detail_00 → seclog_time_00 → orderdiff_01 → share_token_00 →
itemuid_00 → senderphone_00 → naver_link_00` 이다.

**완료 기준 / 검증 결과 (2026-08-13 실행, worktree)**
- `python -m alembic heads` → `naver_link_00 (head)` **단일 head** ✅
- 왕복: 일회용 DB `foms_test_naver_wt` 에서 `create_all` 베이스라인 + `stamp head` →
  `downgrade -1`(`naver_link_00 → senderphone_00`, 테이블 소멸 `to_regclass = None`) →
  `upgrade head`(재생성, 제약 4종 복원) ✅
  ※ **빈 DB 에서 `upgrade head` 는 원래 안 선다** — 레거시 초기 마이그레이션이 `orders` 존재를
  전제한다(`ALTER TABLE orders ADD COLUMN measurement_completed` 에서 UndefinedTable).
  이 저장소의 정본 검증법은 `create_all` 베이스라인 + `stamp` 후 왕복이다. 재검증 시 이 방법을 쓸 것.
- ORM↔마이그레이션 스키마 parity: 컬럼·제약·인덱스 3항목 모두 일치 ✅
- 멱등 본체 실증: 같은 `(NAVER, PO-TEST-1)` 2회 INSERT → `UniqueViolation` ✅ /
  `(COUPANG, PO-TEST-1)` 은 허용(채널 확장 여지) ✅ / `sync_status='BOGUS'` → `CheckViolation` ✅
- 마이그레이션은 `models` 를 import 하지 않음(상수 동결) ✅
- `python -c "import app; print('APP_OK')"` ✅ / `pre_push_smoke` exit 0 (310 passed) ✅

**결정**: 워터마크는 새 테이블 없이 기존 `system_settings`(`SystemSetting`, JSONB + optimistic
`version`) 를 재사용한다. 키는 T5 에서 `naver_sync_watermark` 로 고정하고, 값에
`last_success_to`(구간 끝 ISO)·`last_run_at`·`last_error` 를 담는다. 전용 테이블을 만들지 않는
이유: 단일 행 스칼라 상태이고, 동시 갱신 방어는 이미 `version` optimistic lock 이 제공한다.

---

## T3 — `foms/services/integrations/naver_commerce/client.py`

**범위**: 신규 패키지 `foms/services/integrations/naver_commerce/`.

- 토큰: `POST /external/v1/oauth2/token`, `grant_type=client_credentials`, `type=SELF`.
  서명 = `base64(bcrypt.hashpw(f"{client_id}_{timestamp_ms}", client_secret))` — **client_secret 이 salt**.
- `expires_in=10799`(3h) → Redis 캐시, 만료 5분 전 갱신. Redis 장애 시 fail-open(메모리 폴백) — 스토어 의존 함정.
- 조회: `GET /v1/pay-order/seller/product-orders/last-changed-statuses`(구간 최대 24h) +
  `POST /v1/pay-order/seller/product-orders/query`(배치·페이징).
- 24h 초과 구간은 하루씩 분할 순회. HTTP 오류·rate limit 은 지수 백오프 재시도.
- 비밀값은 환경변수만 (`NAVER_COMMERCE_CLIENT_ID`/`_SECRET`). 하드코딩 금지.

**완료 기준 / 검증 결과 (2026-08-13 실행)**
- `python -m pytest tests/services/integrations/test_naver_commerce_client.py -q` → **24 passed** ✅
  (서명 4 · 토큰 캐시 5 · 구간 분할 5 · 배치 2 · 재시도/오류 분류 7 · Redis fail-open 1)
- 네트워크 없이 통과 — 전송(`transport`)·대기(`sleep`)·캐시를 전부 주입한다. 실 API 호출은 T1.
- `foms/services/integrations` 를 §4.4 닫힌집합에 등재(위 게이트 표 참조) ✅
- fail-open 인벤토리 재생성 후 게이트 13 green ✅ / `pre_push_smoke` exit 0 (322 passed) ✅

**실 API 계약(2026-08-13 실호출로 확인된 값 — 추정 아님)**
- BASE = `https://api.commerce.naver.com/external`
- 토큰: `POST /v1/oauth2/token`, form(`client_id`·`timestamp`·`client_secret_sign`·
  `grant_type=client_credentials`·`type=SELF`), `expires_in=10799`
- 변경분: `GET /v1/pay-order/seller/product-orders/last-changed-statuses`
  (`lastChangedFrom`/`lastChangedTo` = 밀리초 ISO+09:00) → `data.lastChangeStatuses[]`
- 상세: `POST /v1/pay-order/seller/product-orders/query`, body `{"productOrderIds": [...]}` → `data[]`
- 시크릿은 bcrypt salt 라 반드시 `$2` 로 시작한다. 아니면 서명이 조용히 틀리는 대신 즉시 실패시킨다.

---

## T4 — 매핑 + `create_order()` 연동 (좌표 주입 없음)

**범위**
- 수집 매핑 모듈: 스펙 §3.6 표 그대로. `takingAddress` 는 버린다(반품 수거지).
  `status='RECEIVED'` 고정, `structured_data['source']='NAVER_SMARTSTORE'`,
  `structured_data['orderer']` 에 주문자 보존(주문자≠수취인 실재).
- **좌표는 주입하지 않는다.** `create_order()` 를 기본 인자로 호출해 GEOCODE outbox 가
  기존 주문과 똑같이 예약되게 둔다(함정 표 2번 참조).
- 매핑 실패는 **주문을 만들지 않고** `ExternalOrderLink.sync_status='PENDING_REVIEW'` 로 남긴다.
- mutation manifest 2종 등재.

**완료 기준**
**검증 결과 (2026-08-13 실행)**
- `python -m pytest tests/services/integrations/test_naver_ingest.py -q` → **20 passed** ✅
  (순수 매핑 9 · 계정 정책 2 · 파이프라인 9)
- 멱등: 같은 fixture 3회 실행 → 주문 1건 고정, 2회차부터 상세 조회 자체를 안 함(`fetched=0`) ✅
- UNIQUE backstop: 선체크를 우회시켜도 `IntegrityError` 를 잡아 skip 으로 센다 ✅
- GEOCODE outbox 1건 예약 확인 — 좌표 미주입이라 기존 주문과 동일 경로 ✅
- 회귀: `-k "order_create or order_import or rev_99 or write_guard or state_guard"` → 65 passed ✅
- `pre_push_smoke` exit 0 (322 passed) ✅

**구현 메모 (재개 시 알아야 할 결정)**
- 수집 주문은 **`is_erp_order=True`** 로 만든다. ERP 대시보드·통합검색·CS·도면 마법사가 전부
  `Order.is_erp_order.is_(True)` 로 거른다 — False 로 만들면 수집 주문이 현대 UI 에서 **안 보인다**.
  선례: `foms/services/security/channel_order/creation.py`(채널톡 수신 주문도 ERP=True).
- `structured_data` 는 ERP canonical 키 위치를 쓴다: 고객 `parties.customer`, 주문자
  `parties.orderer`, 주소 `site.*`, 품목 `items[]`, 네이버 고유값은 `naver.*` 아래로 격리.
  (`erp_dashboard_search.py` 가 읽는 자리와 동일해야 검색에 걸린다)
- **manifest 2종 등재 불필요**로 판명: 수집 경로는 `create_order()` 만 부르고 자체적으로
  `flag_modified`/`mutation_version` 을 건드리지 않아 REV-99 스캐너가 writer 로 잡지 않는다.
  (`rev_99`·`write_guard`·`state_guard` 게이트 전부 green 으로 확인)

---

## T5 — WORKER 폴링 루프 + 게이트 + rq enqueue

**범위**
- `scripts/maintenance/run_naver_order_sync.py` — `run_notification_escalation.py` 패턴 그대로
  (`--loop --interval --json --once --dry-run`, app 1회 부팅, 실패가 본체를 안 죽임).
- `start.sh` 의 `USE_RQ_WORKER=1` 분기 안, `FOMS_ESCALATION_LOOP_ENABLED` 옆에
  `FOMS_NAVER_SYNC_ENABLED` 게이트로 백그라운드 서브셸 추가(기본 off).
- 워터마크: 성공한 구간 끝까지만 전진(유실 방지). 실패는 구간 단위 재시도.
- web "지금 수집" = `foms/services/jobs/queue.py` 경유 `default` 큐 enqueue **만**.

**검증 결과 (2026-08-13 실행)**
- `python -m pytest tests/services/integrations/test_naver_sync_wiring.py -q` → **15 passed** ✅
- **web 경계 계약 고정**: `foms/web`·`foms/api` 전 파일에 `naver_commerce` 문자열이 없어야 통과.
  enqueue 헬퍼 본문에도 클라이언트 생성이 없음을 별도 검사 ✅
- `start.sh` 게이트: WORKER 분기 안 + 기본 off + `&` 백그라운드 + 기본 간격 300초 ✅,
  gunicorn(web) 분기에는 없음 ✅, `bash -n start.sh` 통과 ✅
- 워터마크: 전진은 성공 시에만·역행 불가·실패 시 사유만 기록(구간 재시도)·깨진 값이면 기본 구간 ✅
- `pre_push_smoke` exit 0 (322 passed) ✅

**추가로 밟은 게이트**: `services/jobs/{queue,tasks}` 의 `__all__` 은 닫힌집합 계약이다
(`foms_namespace_surface_tests.py`). 새 public 이름(`enqueue_naver_order_sync`·
`run_naver_order_sync_task`)을 그 pinned 리스트에 등재해야 green.

**워터마크 저장소**: `system_settings` 의 `naver_sync_watermark` 행
(`foms/services/integrations/naver_commerce/watermark.py`). 값 =
`last_success_to`·`last_run_at`·`last_error`·`last_summary`. 조회 끝은 현재보다 1분 앞당긴다
(네이버 인덱싱 지연으로 경계 변경이 양쪽 구간에서 다 빠지는 것 방지).

---

## T1 — Railway static IP 실검증 (T0·T3 이후)

**완료 기준**: WORKER 컨테이너에서
`python scripts/maintenance/run_naver_order_sync.py --once --dry-run --json`
→ 토큰 발급 성공 + 변경분 조회 성공(HTTP 200, 건수 로그). 주문 생성 없음(dry-run).

---

## T6 — 관리 화면

**구현 완료** (`foms/web/admin/naver_ingest.py` + `templates/admin/naver_ingest.html`)

- `/admin/naver-ingest` (ADMIN 전용): 워터마크·마지막 실행 결과·앱 만료일 카드 3장 +
  상태 필터(전체/수집됨/확인 필요/실패) + 이력 표 + 페이지네이션.
- "지금 수집" = `POST /admin/naver-ingest/run` → **rq enqueue 만**. 큐가 없으면 503 으로
  실패를 알린다(직접 호출 폴백은 존재하지 않는다 — IP 제약).
- 원본 스냅샷 = `GET /admin/naver-ingest/<id>/snapshot` (ADMIN 전용). 개인정보라 **열람 자체를
  `SecurityLog` 에 기록**한다. 목록에 미리 실어 보내지 않는다(보는 사람만 받아간다).
- 새 CSS 파일 없음(Bootstrap 유틸리티만) → `?v=` 범프 불필요. CSRF 는 공용 레이아웃의
  fetch 래퍼가 자동 부착한다.

**추가로 밟은 게이트**: 새 mutation route 는 `docs/harness/foms_write_guard_manifest.json` 에
등재해야 한다(미등재 = static fail). `admin.naver_ingest_run_now` → `mode: guard` 로 등재.
감사 커버리지 인벤토리도 재생성(UNAUDITED 0 유지, 총 177 라우트).

**검증 결과 (2026-08-13 실행)**
- `python -m pytest tests/services/integrations/test_naver_admin_surface.py -q` → **13 passed** ✅
  (권한 2 · 목록/필터 3 · 워터마크·만료 표시 3 · enqueue 경계 3 · 스냅샷 2)
- `pre_push_smoke` exit 0 (322 passed) ✅

**스테이징 실검증 (2026-08-13, `lahom-dev.up.railway.app`, claude_master 로그인)**
- `/admin/naver-ingest` 200 렌더 — 카드 3장·이력표 문구 전부 확인 ✅
- "지금 수집" POST → `{"success": true, "queued": true}` → **WORKER 가 rq job 을 실제로 소비**해
  `run_sweep` 실행 → 자격증명 미설정으로 실패 → 화면에 그대로 표출:
  "실패 / NAVER_COMMERCE_CLIENT_ID / NAVER_COMMERCE_CLIENT_SECRET 가 설정되지 않았다. /
  워터마크는 전진하지 않았습니다" ✅
  → **web enqueue → WORKER 실행 → 실패 기록 → 화면 표출 전 구간이 실배선으로 증명됐다.**
  남은 것은 자격증명(T0)뿐이며, 실패가 조용하지 않고 정확한 원인 문장으로 뜨는 것까지 확인됐다.
- 스테이징 스키마: `external_order_links` 존재 ✅, alembic head `orderreason_00`
  (타 세션이 `naver_link_00` 위에 쌓음 — 체인 정상, 단일 head)

**추가 게이트(하네스 사각 — 재개 시 주의)**: 새 mutation route 는 auth policy manifest
(`docs/harness/foms_order_mutation_policy_manifest.json`)에도 등재해야 한다
(`tests/domains/test_auth_enforcement.py::test_static_gate_every_mutation_route_classified`).
**이 테스트는 `pre_push_smoke` 서브셋에 없어 로컬에서 안 잡힌다** — CI 전수 확인에서 발견했다.
write guard manifest 와 **별개 파일**이라 둘 다 등재해야 한다.

**남은 T6 잔여(의도적으로 손대지 않음)**
- 주문 상세의 "네이버 수집" 배지, 대시보드의 "담당 미지정" 뱃지 2표면.
  `templates/orders/edit_order.html`(1,300줄)·공유 `erp_order_tab.html` 은 알려진 회귀
  핫스팟이라(outer/inner 탭 분기 함정) 별도 패스로 다뤄야 한다. 수집 여부 자체는
  관리 화면과 `structured_data.source == 'NAVER_SMARTSTORE'` 로 이미 식별 가능하다.

---

## T7 — 앱 인증 만료 알림

**구현**: `foms/services/integrations/naver_commerce/app_expiry.py`

- 만료일은 API 로 못 읽는다(커머스API센터 화면 값). `system_settings.naver_app_expiry` 에
  사람이 적거나 환경변수 `NAVER_COMMERCE_APP_EXPIRES_ON` 으로 준다. **모르면 알리지 않는다** —
  모름을 임박으로 오해해 매 스윕 알림을 쏘면 잡음이 되고 진짜 경고를 놓친다.
- 임계값 D-7 / D-3 / D-1 / D-0, **임계값당 1회**(5분 폴링이라 중복 방지가 필수).
- ADMIN 은 role 이라 팀 타깃으로 못 고른다 → 활성 ADMIN **사용자별 1건**(`target_user_id`),
  `fan_out_new_notification` 훅 경유(공유 state row 직접 생성 금지 규약).
- `push_sender._DEFAULT_P1_TYPES` 에 `NAVER_APP_EXPIRY` 등재 — 미등재면 enqueue 해도
  push 가 조용히 no-op 된다(무음 알림의 유일한 기전).
- 인증을 갱신하면(만료일 변경) 발송 이력을 초기화한다.
- 스윕에 붙이되 **실패해도 수집을 롤백하지 않는다**. 부가 알림이 본체를 죽이면 안 된다.

**검증 결과 (2026-08-13 실행)**
- `python -m pytest tests/services/integrations/test_naver_app_expiry.py -q` → **11 passed** ✅
  (D-7 발송·중복 방지·근접 임계값 재발송·만료 후 제목·ADMIN 다중/비활성 제외·갱신 시 이력 초기화·
  깨진 값 무시·알림 실패가 성공한 수집을 롤백하지 않음)
- `pre_push_smoke` exit 0 (322 passed) ✅

---

## 공통 종료 절차 (매 task)

1. `python -c "import app; print('APP_OK')"`
2. 해당 task 완료 기준 명령 실행 → 출력 확인
3. `pwsh scripts/ops/pre_push_smoke.ps1` exit 0
4. UTF-8 파일로 커밋 메시지 작성 → `git commit -F <파일> -- <경로들>` (동시 세션 레이스 방어)
5. 이 원장 Task 표 상태·커밋 SHA 갱신
6. push 는 `deploy` 만. push 후 `gh run list --branch deploy` 로 전 워크플로 green 확인

---

## 마이그레이션 체인 함정 (2026-08-13 실사고 — 재개 시 반드시 확인)

동시 세션이 **같은 부모에 마이그레이션을 붙이면 alembic head 가 둘이 되고 배포가 파산한다.**
이번에 실제로 났다: 리베이스 시점에 타 세션이 `orderreason_00` 위에 `asfresh_00` 을 붙였는데
내 `naver_triage_00` 도 같은 부모를 보고 있었다 → head 2개.

**규칙**: `git rebase origin/deploy` 직후 **반드시** `python -m alembic heads` 로 단일 head 를
확인하고, 둘이면 내 마이그레이션의 `down_revision` 을 상대 head 뒤로 재연결한 뒤 왕복을
다시 검증한다. `tests/domains/test_alembic_single_head.py` 가 잡아주지만
**`pre_push_smoke` 서브셋에는 들어 있으므로 smoke 를 리베이스 후에도 다시 돌려야 한다.**

## T8 — 트리아지 상태 컬럼 (스펙 §8.3)

**범위**: `ExternalOrderLink` 에 `reviewed_at`(DateTime, nullable)·`reviewed_by_user_id`
(FK → users.id, ON DELETE SET NULL) 추가 + 마이그레이션(`down_revision` = 그 시점 원격 head).

`sync_status` 에 값을 더하지 않는다 — 그건 수집 결과 축이고 트리아지는 사람 처리 축이라
섞으면 "수집 성공했지만 사람이 아직 안 본" 상태를 표현할 수 없다.

**검증 결과 (2026-08-13 실행)** — `down_revision = orderreason_00`
- 왕복: `foms_test_naver_t8` 에서 `create_all`+`stamp head` → `downgrade -1`(컬럼 소멸 확인) →
  `upgrade head`(재생성) ✅
- `alembic heads` → `naver_triage_00` 단일 head ✅
- ORM↔마이그레이션 parity: 제약·인덱스 일치 ✅ / 컬럼은 **순서만 다름**(ALTER TABLE ADD COLUMN 은
  항상 뒤에 붙는다 — 불가피하며 체인 지문 테스트는 `(table, column)` 키라 순서 무관)
- PG 레인 체인 왕복 `tests/postgres/test_migration_chain.py` 1 passed ✅
- 부분 인덱스 확인: `btree (channel, created_at) WHERE (reviewed_at IS NULL)` ✅
- `APP_OK` + `pre_push_smoke` exit 0 (322 passed) ✅

**밟은 함정**: FK 이름을 마이그레이션에서 임의로 지으면(`fk_external_order_link_reviewed_by`)
`downgrade` 가 `UndefinedObject` 로 죽는다 — ORM `ForeignKey` 는 이름을 안 주므로 create_all
레인이 **PostgreSQL 기본명**(`external_order_links_reviewed_by_user_id_fkey`)으로 만든다.
같은 테이블 `order_id` FK 도 같은 규칙. 마이그레이션은 기본명을 그대로 써야 한다.

## T9 — 트리아지 작업대 (스펙 §8.2)

**범위**: `/admin/naver-ingest/triage` (또는 기존 화면의 탭). 좌=확인 대기 큐, 우=네이버 원본
(옵션 원문·주문자·수취인·주소)과 FOMS 현재 값 대조 + 주문 편집기 링크 + "확인 완료".

**규격 입력은 이 화면에서 하지 않는다** — `spec_rows` 는 W 가 출고가·시공비와 결합돼 있어
(`eval_spec_width_mm` 가 총폭 SSOT) 두 번째 입력 UI 를 만들면 계산 규칙이 갈라진다.

**검증 결과 (2026-08-13 실행)** — `/admin/naver-ingest/triage`
- `python -m pytest tests/services/integrations/test_naver_triage.py -q` → **15 passed** ✅
- `reviewed_at IS NULL` 인 `LINKED` 건만 큐에 뜬다(확인 완료·보류·실패 제외) ✅
- "확인 완료" → `reviewed_at`/`reviewed_by_user_id` 기록 → 큐에서 빠짐 ✅
  **재요청이 첫 확인 시각을 덮지 않는다**(첫 확인이 기록이다) ✅
- 옵션 원문 노출 + 원본↔FOMS 대조표(주문자·상품코드 포함) + 편집기 링크 ✅
- 게이트 3곳 등재 완료: write guard manifest · auth policy manifest · `ACTION_LABELS` ✅

## T10 — 담당자 지정 + "담당 미지정" 뱃지 (스펙 §8.4)

**범위**: 작업대에서 SALES 담당자 지정 → `foms/services/orders/assignment.py::set_sales_assignee()`
경유(`OrderAssignment` 직접 생성 금지 — REV-00 version bump·receipt·`SALES_ASSIGNEE_SET` 이벤트가
따라온다). 보류함에서 실제 담당자로 옮기는 것은 **교체**라 `reason` 이 필수 — 화면이 기본 사유를 보낸다.
대시보드의 "담당 미지정" 뱃지(T6 에서 미룬 잔여)도 여기서 함께 처리한다.

**검증 결과 (2026-08-13 실행)**
- **PG 레인** `tests/postgres/test_naver_triage_assignment.py` → **3 passed** ✅
  (보류함 owner 교체 후 active SALES 정확히 1명 / `SALES_ASSIGNEE_SET` 이벤트 + version bump /
  사유 없는 교체 거부)
- SQLite 레인은 라우트 배선만 고정(서비스 호출 인자·감사 기록) ✅

**레인 함정(중요)**: SALES active-owner 유일성은 `postgresql_where` 부분 유니크라
**SQLite create_all 에서는 predicate 없는 전체 유니크**가 된다. 그래서 owner 교체는 SQLite
레인에서 `UNIQUE constraint failed: order_assignments.order_id` 로 반드시 실패한다 —
배정 교체 계약은 PG 레인에만 둔다.

**구조 변경**: 채널 코드·시스템 계정 username 을 `naver_commerce/constants.py`(의존성 없는
모듈)로 분리했다. web 화면이 `ingest` 에서 상수를 당겨오면 web 이 수집 파이프라인을 import 하게
되어 WORKER 단일 출구 계약 테스트가 red 가 된다(실제로 잡혔다).

**잔여**: 대시보드 "담당 미지정" 뱃지. 공유 `edit_order.html`·`erp_order_tab.html` 회귀 핫스팟과
같은 표면이라 별도 패스로 남긴다(T6 잔여와 동일 사유).
