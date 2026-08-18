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
| T0 | 선행: 시크릿 재발급 · 시스템 계정 2개 · static IP 등록 | — | DONE(스테이징) | 운영은 승격 후 재등록 필요 |
| T2 | `ExternalOrderLink` 모델 + alembic 마이그레이션 | — | DONE | `naver_link_00` (`down_revision=senderphone_00`) |
| T3 | `naver_commerce/client.py` (토큰 캐시·조회·재시도·백오프) | — | DONE | 테스트 24 green |
| T4 | 매핑 + `create_order()` 연동 (좌표 주입 없음) | T2, T3 | DONE | 테스트 20 green |
| T5 | WORKER 폴링 루프 + 게이트 + rq enqueue 경로 | T4 | DONE | 테스트 15 green |
| T1 | Railway WORKER static IP 실검증 → 스테이징 실수집 30건 | T0, T3 | DONE | 2026-08-13 실 API |
| T6 | 관리 화면 (수집 이력·수동 실행·원본 스냅샷) | T4, T5 | DONE | 테스트 13 green |
| T7 | 앱 인증 만료 D-7 알림 | — | DONE | 테스트 11 green |
| T8 | 트리아지 상태 컬럼 2개 + 마이그레이션 | T2 | DONE | `naver_triage_00` |
| T9 | 트리아지 작업대 화면 | T8 | DONE | 테스트 15 green |
| T10 | 담당자 지정(`set_sales_assignee`) | T8 | DONE | PG 레인 3 green |
| T11 | 대시보드 '담당 미지정' 뱃지 + T0 준비 안내서 | T10 | DONE | 테스트 7 green |
| T14-A | 진입구: 주 메뉴 '네이버 주문' 탭+뱃지 · '/' 인박스 스트립 · 전 직원 권한 개방 | T9 | DONE | `51e0894a` (deploy) · 스테이징 눈 확인 완료 |
| T14-B | 네이버 원본 도크 (편집 셸 우측 독립 마운트) | T14-A | DONE | `0bc5fc04`+`e7157b5b`+`291085bc` (deploy) · 스테이징 #4462 실검증 |
| T14-D | 배송메모 유실 수정(실필드 productOrder.shippingMemo) + 도크 수취인·메모 머리말 | T14-B | DONE | `3fedff20` |
| T14-C | 확인 대기 큐 묶음 표시(한 집 한 줄) | T13 | DONE | `4d179161`+`21ef7d5c` (deploy) · 스테이징 14집/42건 확인 |
| T14-E | 네이버 원본 필드 전수 점검 → 취소·반품 차단 + 필드 4종 수집 | T14-C | DONE | `12660909` (deploy) · 스테이징 link 20 실검증 |
| T14-F | 수집 후 취소 추적(알림) + 새 값 도크·이력 표시 | T14-E | DONE | `e8f9d535` (deploy) · 스테이징 이력/도크 확인 |
| T14-G | 확인 화면을 CS 실제 흐름에 맞춤(2단계·새 탭) | T14-F | DONE | `8c750d13` (deploy) · 스테이징 확인 |
| T14-H | 관리자 수집 이력도 한 집 한 줄 묶기 | T14-C | DONE | `4c761b0b` (deploy) · 스테이징 23묶음 확인 |
| T14-I | 규격 입력 도우미(총폭 계산·cm→mm·사양 불일치 경고) | T14-B | DONE | `eab92b41` (deploy) · 스테이징 #4466 확인 |
| T15-A | 운영 켜기 체크리스트(PR #113 머지 후 4단계) — 가이드 상단 등재 | — | DONE | 이 커밋 · `docs/guides/NAVER_INGEST_SETUP.md` |
| T15-B | 예전 승격 PR #92 닫기 | — | DONE | 2026-08-18 CLOSED (#113 로 대체) |
| T15-C | 취소 추적 드릴(연습 서버 리허설 도구) + 스테이징 실행·원복 | T14-F | DONE | 이 커밋 · `scripts/maintenance/naver_claim_drill.py` |
| T15-D | 폰(모바일 메뉴) '네이버 주문' 탭 | T14-A | 보류(사용자 결정 2026-08-18) | 나중에 — PC 확인 큐 흐름 안정 후 |

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
- 시크릿 재발급 · static IP 3개 등록: **2026-08-13 사용자 완료**. 등록된 IP 는 **dev worker** 것이라
  실검증(T1)도 스테이징에서 했다. 자격증명 5종은 FOMS-DEV `worker` 에만 둔다
  (운영 `WORKER` 에 잘못 들어갔던 5개는 삭제 완료).
- **운영 승격 시**: 커머스API센터 IP 한도 3 = dev 가 다 쓰고 있으므로 운영 WORKER IP 로 **교체**해야 한다.

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

## T1 — Railway static IP 실검증 — **DONE (2026-08-13, 스테이징 실 API)**

**검증 결과**: dev worker 에 자격증명 5종 주입 후 수집 루프 기동 → **실주문 30건 수집**.
토큰 발급·변경분 조회·상세 조회 전부 성공, `last_error: null`,
워터마크 `last_success_to 2026-08-13T20:53:29+09:00` 정상 전진.
"지금 수집" 재실행 → `fetched 0 / created 0 / skipped 0` = 멱등 정상.

**실데이터 화면 점검(전부 PASS)**: 대시보드 '담당 미지정' 30건(보류함 이름 노출 0) ·
관리 화면 이력 30행 · 트리아지 큐 30건(대조표·편집기 링크·확인 완료 버튼) · 주문 상세 표식 ·
원본 스냅샷 200 · 담당자 지정 왕복(30 → 29 → 30).
매핑 실물 확인: 수취인=고객·주문자 별도 보존·품목/옵션 원문·금액·`naver.product_order_id`·
접수 퀘스트 생성, **좌표 미주입(lat 0건) + GEOCODE outbox 30건 예약** = 설계대로.

**변수 배치**: 자격증명은 **FOMS-DEV `worker`** 에만 있다. 운영(FOMS-PRODUCTION `WORKER`)에
잘못 들어갔던 5개는 삭제했다(남은 키 0).

**재개 시 반드시 알 것 2가지**

1. **IP 슬롯 3개는 지금 dev worker 가 쓰고 있다.** 커머스API센터 한도가 3이라
   운영 승격 후 수집을 운영 WORKER 로 옮기려면 **등록 IP 교체가 필요**하다 —
   dev·운영 동시 운용은 불가능하다.
2. **스테이징 GEOCODE outbox 가 소비되지 않는다**(전체 33건 PENDING, 완료 이력 0 —
   수집 이전 3건 포함). `tools/ops/run_domain_side_effect_outbox.py` 가 스테이징에서
   안 도는 것으로 보인다. 수집 주문의 지도 좌표가 안 잡힌다. 원인 조사는 미착수(사용자 보류).

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

## 운영 승격 (PR #92 — 머지 대기)

- 브랜치 `promote/naver-ingest`(승격 트리 `c:\tmp\foms-pnav`), production HEAD 위 **21커밋**.
  PR: https://github.com/lahomsystem/FOMS/pull/92 — perf-gate pass · pg-lane pass · CLEAN.
- 운영은 **잠든 상태로** 올라간다: `FOMS_NAVER_SYNC_ENABLED` 미설정(off) · 자격증명 없음 ·
  시스템 계정 2개 미생성(머지 후 `create_naver_ingest_accounts.py`).

**체인 의존과 그 처리(재개 시 그대로 따라갈 것)**

운영 head `senderphone_00` → `naver_link_00` → **`orderreason_00`** → **`asfresh_00`** →
`naver_triage_00`. 굵은 둘은 타 세션 기능의 마이그레이션이라 빼면 체인이 끊긴다.
→ **마이그레이션 파일 2개 + 대응 모델 정의만** 동반하고 기능 코드는 두고 왔다
(둘 다 additive: `order_change_reasons` 테이블 신설 · `order_attachments.as_log_id` 컬럼).

**밟은 함정 3개**

| 증상 | 원인 | 대응 |
|---|---|---|
| cherry-pick 충돌 (인벤토리 JSON 3종) | 생성물이라 트리마다 내용이 다르다 | `--theirs` 로 받고 승격 트리에서 재생성(failopen·audit_coverage·mutation/state writer) |
| `test_manifest_covers_every_mutation_route` red | write guard manifest 에 운영에 없는 라우트(`events.api_set_order_change_reason`) = stale | 그 항목만 제거(같이 딸려온 `erp_orders_as.api_as_log_*` 는 운영에 실재하므로 **지우면 안 된다**) |
| **pg-lane red**: `index ix_order_attachments_as_log_id does not exist` | 체인 왕복 테스트 베이스라인이 alembic 이 아니라 **models 의 `create_all`** 이다. 마이그레이션만 가져오면 create_all 이 그 객체를 안 만들어 downgrade 가 죽는다 | 동반 마이그레이션에 **대응하는 모델 정의도 함께** 가져온다(컬럼 1·클래스 1, 라우트·서비스는 그대로 두고) |

**머지 후 순서**: ① 운영 DB 계정 2개 생성 ② 시크릿·static IP·env (`docs/guides/NAVER_INGEST_SETUP.md`)
③ `/admin/naver-ingest` "지금 수집" 1회 성공 확인.

## T12·T13 — 수집·생성 분리 + 묶기 (2026-08-14 deploy 완료)

- **T12** (`cdb624de`): 수집은 `COLLECTED` 링크만 남기고 주문은 "주문 만들기" 버튼으로.
  `promotion.py`(web-safe, 네트워크 없음)·`navercollect_00` 마이그레이션·manifest 3종 등재.
  스테이징 실검증: 34건 수집→주문 0, 버튼 1회=주문 1(멱등 2회차 created:false).
- **T13** (`85590337`): 같은 `(주문번호, 수취인 전화, 주소)` 는 주문 1건으로 묶는다.
  대표=금액 최대(0원 구성 대표 방지), 금액=합계, items[]=상품주문별 1행, 분할배송 미병합.
  사용자 실사용 확인: #4462 에 4개 상품주문이 품목 4행으로 묶임(스크린샷).
- 스테이징 자동생성분 34건 soft delete + 링크 COLLECTED 복원 완료. 수집 루프 ON.

## T14 — 사용자 피드백 3건 (2026-08-14, 다음 작업)

1. ~~추가 옵션이 별도 주문으로 생김~~ → T13 으로 해결됨. 잔여: **품목 순서**(대표 본품이
   1번이어야 — 실측 스크린샷에선 33,200원 길이추가가 1번, 본품 496,000원이 2번).
2. 기본 정보(이름·주소·전화·본품)는 자동, **추가 옵션 규격은 사람이 편집기에 수동 입력** —
   업무 프로세스 개선안 deep research + 목업.
3. 진입구가 사용자 드롭다운 안이라 안 보임 — ERP 주문 흐름 안에서 쓰기 쉬운 배치 연구 + 목업.

### T14-D 배송메모 유실 수정 + 도크 머리말 (2026-08-14, 커밋 `3fedff20`)

**사용자 확정(AskUserQuestion)**: "수취인명 기준" = **화면 대표 이름 = 수취인**(갈래 4) ·
과거 수집분 **재처리 없음**(앞으로 수집분만) · T14-C 는 뒤로 · 완료 기준 = **스테이징 눈
확인까지**. 이어서 "배송메세지도 수집" 요청 → 같은 덩이에 편입. 후속 확정: 메모는
**화면 표시·복사까지만**(주문 데이터 자동 기입 없음) · 과거분은 **화면만 자동 소급** ·
이름은 **도크에 '주문자 다름' 표시 추가** · 묶음 메모는 **다르면 전부 보존**.

**근본 원인(실측)**: 배송메모를 `shippingAddress.shippingMemo` 에서 읽고 있었다. 스테이징
실수집 42건 전수 조사 결과 **그 키는 응답에 없다** — 실위치는 **`productOrder.shippingMemo`**
(42건 중 13건 비어 있지 않음). 값이 항상 빈 문자열이라 화면에도 안 떠서 조용히 유실됐다.
※ 조사 방법: FOMS-DEV `DATABASE_PUBLIC_URL` 로 `external_order_links.raw_snapshot` 을
읽어 `memo|message|request` 키 전수 스캔(읽기 전용). 다음에 필드 위치가 의심되면 같은 방법.

**같이 확인된 실측치**: 수취인≠주문자 **9/42건**(대리주문 실재) · 묶음 14개 중 11개가
2건 이상 · **묶음 안에서 메모가 서로 다른 경우는 0건**(그래도 보존 규칙으로 구현).

**변경**
- `mapping.extract_shipping_memo()` 신설(productOrder 우선 + 폴백 2단), `build_structured_data`
  가 이걸 쓴다. `map_group` 은 상품주문별 메모를 **중복 제거 후 전부** 이어 붙인다(대표 먼저).
- `foms/web/admin/naver_ingest.py::_triage_pane` 도 같은 헬퍼로 — **원본 스냅샷에서 읽으므로
  과거 수집분도 재처리 없이 그대로 보인다**(사용자 선택: 화면만 자동 소급).
- `dock.py`: payload 에 `recipient_name`·`orderer_name`·`orderer_differs`·`shipping_memo`
  (링크별 메모 중복 제거 병합). 새 except 블록 없이 기존 `_row_source` try 안에서 뽑았다
  (fail-open 인벤토리 baseline 불변).
- 도크 프론트: 머리말에 수취인 + '주문자 다름' 뱃지 + 배송메모 박스(복사 버튼).
  폼 DOM 무참조 유지. `?v=20260814d` 범프(CSS·JS 둘 다).

**검증**: naver 4개 스위트 **74 passed**(신규 7 — 메모 실필드·부재 시 빈 값·묶음 보존/중복
제거·도크 payload 3종) · `pre_push_smoke` exit 0 (**323 passed**) · APP_OK.

**스테이징 실검증 (2026-08-14, lahom-dev, claude_master)**
- 트리아지 `?link_id=49`(과거 수집분, **재처리 안 함**) → "배송 메모 / 문 앞에 놓아주세요" 표출 ✅
- 주문 만들기 → #4466 생성, `structured_data.naver.shipping_memo` 에 메모 저장(신규 경로) ✅
- 이름 다른 건(link 41·42 → #4467): 도크 머리말 "수취인 원주현 / **주문자 다름 · 정현태**" +
  배송메모 "공동현관 1202#0907#" + 복사 버튼 ✅, 콘솔 에러 0
- 1920 도킹 pane 정상 · 1366 FAB 폭 176px(`.row > *` 풀폭 회귀 없음) ✅
- **검증용 스테이징 주문 2건(#4466·#4467)이 남아 있다** — 정리는 사용자 판단.

**CI**: `917b5b1e` — FOMS CI · Harness CI · PG Lane · perf-gate(staging) **4개 전부 green**.

**사용자 결정**: 검증용 스테이징 주문 2건(#4466·#4467)은 **그대로 둔다**. 다음 작업 = T14-C.

### T14-C 구현 기록 (2026-08-14 완료)

**사용자 확정(AskUserQuestion)**: 묶음 모양 = **한 줄로 접기(펼치기 가능)** · 적용 범위 =
**확인 화면(트리아지)만** · 버튼 = **묶음당 1개** · 정렬 = **최신 수집순 유지**.

**구현** (`foms/web/admin/naver_ingest.py::_group_queue` + `templates/admin/naver_triage.html`)
- 묶음 키는 **주문 생성과 같은** `mapping.group_key`(주문번호·수취인 전화·주소). 화면과 생성
  결과가 갈리면 "한 줄인데 주문 2건" 사고가 난다. 대표=금액 최대(`map_group` 규칙),
  펼침 목록도 **대표 먼저**(0원 구성이 첫 줄이면 본품을 못 찾는다 — 스테이징 눈 확인에서 잡아 수정).
- 링크 조회 상한 `QUEUE_LINK_FETCH_LIMIT = PAGE_SIZE*5`(250). **상한에 걸리면 마지막 묶음은
  반쪽일 수 있어 통째로 버린다** — 구성 일부만 보여주면 사람이 남은 건을 못 본다.
- 헤더 'N집 / 상품주문 M건', 대표 줄 '외 N건' 뱃지, 구성은 Bootstrap collapse.
- 버튼: '주문 만들기'=대표 링크 id(형제는 `promote_link_to_order` 가 묶음), '확인 완료'=
  `data-link-ids` 전체를 순차 review. **새 라우트 없음** → manifest 등재 불필요.
- 원본 파싱 실패 링크는 `__ungrouped__` 단독 묶음으로 남긴다(큐에서 사라지면 사람이 못 본다).

**검증**: `test_naver_triage.py` **23 passed**(신규 5 — 묶음 1줄·대표=본품·대표 먼저·주소
다르면 분리·버튼 묶음 단위) · integrations 168 · `pre_push_smoke` exit 0 (323) · APP_OK.

**스테이징 실검증**: 링크 42건 → **14집**, '외 N건' 뱃지 11개, 선택 묶음 자동 펼침,
접힌 묶음 토글 클릭 시 `show` 전환(높이 88px), 콘솔 에러 0.

**CI 주의(이 세션 아님)**: `4d179161` 의 FOMS CI red 는 타 세션 정렬 헤더 작업 회귀
(`test_production_transition_guard_api` 'filters' undefined · `test_tablet_t2_contract`)로,
그 세션이 `27a46486` 에서 수정했다. 리베이스 후 `21ef7d5c` 로 재검증.

### T14-E 원본 필드 전수 점검 (2026-08-14~15 완료)

**조사**: FOMS-DEV `raw_snapshot` 47건을 필드 단위로 전수 나열 → 코드가 읽는 이름과 대조.
**필드 120개 중 코드가 읽던 건 26개**. 조사 스크립트 방식(재사용): JSON 리프 경로 전수 수집 +
`naver_commerce` 패키지·web 화면의 따옴표 토큰 집합과 교차. (경로에 백슬래시를 쓰면 grep 이
전부 miss 하므로 forward slash 로 쓸 것 — 1차 시도가 그렇게 전수 "미사용"으로 잘못 나왔다.)

**최대 구멍 — 취소가 안 보였다**: 수집 필터가 `productOrderStatus == PAYED` 하나뿐이라
**`claimStatus = CANCEL_REQUEST` 인 건도 PAYED 로 수집된다**(실물 `link 20`). 그 값을 아무도
읽지 않아 화면에 표시조차 없었고, "주문 만들기"를 누르면 취소 건이 정상 주문이 됐다.

**사용자 확정**: 취소 처리 = **경고 + 주문 만들기 막기**. 추가 필드 = **4종 전부**
(보조 연락처·결제일/수단·금액 상세·상품 식별자/유입경로).

**구현**
- `mapping.extract_claim()` — `productOrder.claimStatus` + `cancel.*` + `currentClaim.cancel.*`
  3경로. `BLOCKING_CLAIM_STATUSES`(취소·반품 진행/완료)만 차단, `CANCEL_REJECT`(=정상 진행)는 통과.
- `promote_link_to_order()` 가 묶음 형제까지 검사해 `PromotionError`. **화면 버튼만 잠그면 API
  직접 호출로 뚫리므로 서비스에서 막는다**(스테이징에서 실제로 fetch 로 뚫어 봤고 400 으로 막혔다).
- 화면: 큐 빨간 배지 · pane 경고 배너(사유·요청시각) · 버튼 `disabled` · 도크 상단 취소 배너.
- 신규 수집 값: `parties.customer.phone2`(tel2) · `naver.payment`(결제일·수단·위치·단가·옵션가·
  할인·쿠폰·정산예정액) · `naver.product_id`/`original_product_id`/`item_no`/`inflow_path`.
  **Order 스칼라 필드는 불변** — structured_data 와 화면 표시만 늘렸다.

**검증**: integrations **183 passed**(신규 12) · `pre_push_smoke` exit 0 · APP_OK ·
CI 폴링. 스테이징 실검증(`?link_id=20`): 경고 배너 "네이버 취소 요청 · 사유
SIMPLE_INTENT_CHANGED · 2026-08-13T19:20" + 버튼 `disabled=true`, **API 직접 호출 400**
(`order_id` 여전히 NULL).

**남은 관찰(미구현)**: 수집 **이후** 취소되는 건은 재조회를 안 해서 여전히 모른다. 사용자
선택으로 자동 추적은 제외했다 — 필요해지면 5분 스윕에 상태 재조회를 붙이는 것이 다음 수순.

### T14-F 수집 후 취소 추적 + 화면 확장 (2026-08-16 완료)

**사용자 확정**: 감지 = **변화 생긴 것만 다시 보기** · 동작 = **표시 + 담당자 알림**(자동
상태 변경 없음) · 화면 = **도크 + 수집 이력(관리자)**.

**설계**
- `claim_watch.refresh_claims()` — 5분 스윕이 **이미 받는** 변경 목록(`last-changed-statuses`)
  에 기존 링크가 뜬 경우에만 그 건의 상세를 재조회한다. 변경 없으면 **추가 호출 0회**.
  변경 목록의 상태 문자열로 판정하지 않는다: 취소가 그 목록에 어떤 이름으로 실리는지
  실물 미확인이고, 정본은 상세 응답 `claimStatus` 다(실측).
- **원본 스냅샷을 최신으로 교체**한다. 큐·트리아지·도크가 전부 스냅샷에서 읽으므로 이것만으로
  표시가 최신이 된다(대신 최초 수집 시점 원본은 보존되지 않는다 — 필요해지면 별도 이력 필요).
- 동기화 상태는 `triage_state['claim_sync']`(`last_status`·`notified_status`·`refreshed_at`).
  도크 체크(`checked`·`assigned_main`)와 다른 축이라 키를 분리했다.
- 알림 `NAVER_ORDER_CLAIMED` — 주문 담당 SALES, 보류함/미배정이면 활성 ADMIN 전원.
  **상태별 1회**(5분 폴링 중복 방지). `push_sender._DEFAULT_P1_TYPES` 등재(미등재 = 무음).
- **주문 상태 자동 변경 안 함** — 이미 잡힌 일정·도면이 있으면 자동 변경이 더 큰 혼란.

**화면 확장**: 도크 = 보조 연락처(복사 버튼)·결제일/수단·할인 합계, 관리자 수집 이력 =
결제/할인 칸 + 취소 배지. 도크 자산 `?v=20260816a`.

**검증**: integrations **193 passed**(신규 9) · `pre_push_smoke` exit 0 · APP_OK.
스테이징: 이력 표 결제·할인 칸 렌더 · 2페이지에서 취소 배지("수집됨(주문 전) / 취소 요청") ·
주문 #4467 도크 "결제 2026-08-13T15:35 · 신용카드 간편결제 / 할인 1,531,300원", 콘솔 에러 0.
할인 값 교차검증: link 40 단가 230,000 × 수량 13 − 할인 1,520,300 = 결제 1,469,700 ✅.

### T14-G CS 업무 흐름 반영 (2026-08-17 완료)

**사용자가 알려준 실제 흐름(설계 전제로 고정)**: 수집 → **CS 가 주문 만들기 → erporder 에서
제품 규격 입력까지**. **담당자 지정은 접수 단계가 아니다** — 고객 통화 → 실측일 지정 →
실측 일정 스케줄링 시점에 한다. 따라서 주문 생성 시 담당자 입력은 요구하지 않는다.

**구현**
- pane 상단 2단계 표시(① 주문 만들기 ② ERP 규격 입력) + "지금 할 일" 문구. 담당자 지정
  UI 는 남기되 라벨에 "(실측 일정 잡을 때)" 를 붙여 성격을 못 박았다.
- 규격 입력 판정 SSOT = `structured_data['items'][*]['spec_rows']`.
  **최상위 `spec_rows` 를 보면 항상 0 으로 잘못 읽는다**(실데이터로 확인 — 수집 주문 전량이
  items 안에만 규격을 갖는다). `order_has_spec_rows()` 가 이 판정의 단일 지점.
- '확인 완료'는 규격·담당자로 **잠그지 않는다**(사용자 확정). 규격이 비면 경고 문구만.
- '주문 만들기' 응답에 `edit_url` 을 실어 화면이 편집기를 **새 탭**으로 연다(목록은 남아
  다음 건을 이어서 처리). 팝업 차단 시 주소를 문구로 남긴다.
- 큐 줄에 다음 할 일 배지(주문 만들기 / 규격 입력) — 취소 배지가 있으면 그쪽이 우선.

**검증**: test_naver_triage **30 passed**(신규 5) · integrations 198 · smoke exit 0 · APP_OK.
스테이징: 24집 목록에 '주문 만들기' 배지, `?link_id=49`(주문 있음·규격 없음)에서
"편집기에서 제품 규격을 채우세요" + "규격이 아직 비어 있습니다" 경고 + 확인 완료 버튼
활성(disabled=false) + 새 탭 코드 배포 확인, 콘솔 에러 0.

**미실행(사용자 결정)**: 취소 추적 실전 시험은 **진짜 취소가 나올 때까지 기다린다**
(연습 데이터 인위 조작 안 함).

### T14-H 수집 이력 묶기 (2026-08-18 완료)

**사용자 확정**: 페이지 = **묶음 50개** · 필터 = **해당 줄이 하나라도 있으면 그 집을 통째로**
· 구성은 **접어두기**.

**설계 차이(확인 화면과 다른 점)**: 이력의 묶음 키는 **네이버 주문번호**다(`_history_group_key`).
확인 화면은 분할배송까지 갈라내는 `mapping.group_key`(주문번호·전화·주소)를 쓰지만, 이력은
**페이지 경계에서 한 집이 쪼개지지 않는 것**이 목적이라 SQL 로 셀 수 있는 키가 필요하다.
주문번호가 없는 링크(실패 건 등)는 `link:<id>` 로 자기 자신이 한 묶음이 된다.

- 상태 필터는 **묶음 선정에만** 적용하고, 뽑힌 묶음의 상품주문은 상태 불문 전부 싣는다.
- 대표 = 금액 최대, 수량·금액·할인은 합계, 상태 배지는 묶음 안 상태 전부(중복 제거).
- 대표 줄에 **대표 상품주문번호를 남긴다** — 없애면 단독 묶음(실패 건)을 추적할 수 없다
  (테스트가 이걸 잡았다).
- '주문 만들기'는 묶음당 1개(미생성 대표 링크), 주문이 있으면 '규격 입력' 다음 할 일 표시.

**검증**: test_naver_admin_surface **16 passed**(신규 2) · integrations 200 · smoke exit 0 ·
APP_OK. 스테이징: 23묶음/141행, 펼침 시 구성 6줄+원본 버튼 6개, 주문 만들기 버튼 23개
(묶음당 1), 필터별 묶음 수(COLLECTED 20·LINKED 4·PENDING_REVIEW 1·FAILED 1), 콘솔 에러 0.

### T14-I 규격 입력 도우미 (2026-08-18 완료)

**사용자가 알려준 실제 수작업 2가지**
1. 1cm 추가 옵션까지 합쳐 총폭을 암산한다 — 예: `로라 무몰딩 여닫이 30cm` 12개 +
   `로라 무몰딩 1cm` 12개 = **3,600 + 120 = 3,720**.
   1.1 본품과 1cm 상품의 사양이 같은지도 눈으로 대조한다 — 고객이 본품은 **무몰딩**인데
   1cm 는 **몰딩**으로 주문하는 경우가 간혹 있다.
2. `240cm` 표기를 `2400` 으로 환산한다.

**구현**(전부 도크 안, 폼 무참조 — 사용자 확정 "복사만 유지")
- `parse_length_mm()` — cm/mm/m → mm(240cm→2400, 1cm→10). 못 읽으면 힌트를 만들지 않는다
  (틀린 숫자를 보여주느니 없는 게 낫다).
- `build_width_hint()` — 본품 모듈폭 × 수량 + **길이추가(1cm) 옵션만** × 수량.
  수납구성(TYPE A)·거울도어는 폭과 무관해 더하지 않는다. 계산식 문자열과 복사 칩 제공.
- 사양 불일치 3축(몰딩 / 문 방식 / 손잡이) 비교. **'무몰딩'을 '몰딩'보다 먼저 검사**한다
  (부분문자열 함정). 다르면 경고 줄을 띄운다.
- 자동 기입 없음 — `spec_rows`·`eval_spec_width_mm` 계산 규칙과 폼은 그대로다.
  도크 자산 `?v=20260818a`.

**검증**: test_naver_dock **27 passed**(신규 6) · integrations 206 · smoke exit 0 · APP_OK.
스테이징 #4466 실화면: `총폭 1,570mm / 300mm × 5 + 10mm × 2 + 10mm × 5` + 복사 칩,
그리고 **실데이터에서 경고가 실제로 걸렸다** — "문 방식: 본품 여닫이 · 추가 슬라이딩"
(보테가 슬라이딩 1cm 옵션이 로라 여닫이 본품에 붙어 있던 건). 콘솔 에러 0.

## T14-C 착수 전 미해결 요청 (2026-08-14 사용자, **확인 없이 구현 금지**)

> 사용자 원문: **"주문 수집시 수취인명 기준으로"** — 문장이 끊겨 의도가 확정되지 않았다.
> 다음 세션은 **코드를 건드리기 전에** 아래를 사용자에게 물어 확정할 것.

현재 사실(대조용):
- 묶음 키 `group_key()` = **(네이버 orderId, 수취인 전화 `tel1`, 주소)** — `mapping.py`.
  **수취인명(`shippingAddress.name`)은 키에 없다.**
- 대표(본품) 선정 = 금액 최대. 트리아지 큐 정렬 = `created_at desc`.
- 큐 목록 표시 이름 = `order.customer_name` 또는 스냅샷 `shippingAddress.name`.

물어야 할 갈래(예시):
1. **묶음 키에 수취인명 추가**(전화·주소 같아도 이름 다르면 분리)인가?
2. **묶음 키를 이름 기준으로 완화**(전화가 달라도 같은 이름+주소면 한 건)인가?
3. 묶기와 무관하게 **목록 정렬/그룹 표시를 수취인명 기준**으로 바꾸는 것인가(T14-C 본체)?
4. 주문자(orderer)와 수취인이 다를 때 **어느 이름을 화면 대표로** 삼는가?

⚠️ 1·2는 이미 수집된 데이터의 묶음 결과를 바꾸므로 **과거 수집분 재처리 여부**까지 함께 확정해야 한다.

## T14 구현 계획 (2026-08-15 목업 승인 대기 후 착수 — 새 세션 릴레이용)

**확정 결정 (재논의 금지)**
1. **기존 erporder 폼 UX/UI 불가침** — 제안 요소는 전부 폼 바깥. 도크 패널은 폼 DOM 을
   참조하지 않는 독립 부품, 값 전달은 클립보드 복사 버튼만(WDCalculator additive 패턴).
2. 본품 여러 개여도 주소·수취인 같으면 **FOMS 주문 1건**(group_key 가 주소 다르면 이미 분리).
   본품↔옵션 짝짓기는 네이버 API 에 부모 링크가 없어 **추정 표시 + 사람 확정**(귀속 미정은
   드롭다운, 선택 전 확인 완료 잠금). 짝짓기는 표시/체크리스트용 — items 데이터 구조 불변.
3. 파싱 자동 기입 금지 — 힌트/복사까지만(규격 SSOT `spec_rows`·`eval_spec_width_mm` 보호).

**목업 (사용자 검토 중)**
- v2.1(실화면 통합·폼 불가침·시나리오 A/B): https://claude.ai/code/artifact/215d75b1-8fea-4da4-afbb-9fb4f6d9dcea
- v1(개념·페르소나): https://claude.ai/code/artifact/d1b30d4b-f2e4-4fd5-b867-11abf14bd229

**구현 덩이 3개 (예상 순서, 착수 전 사용자에게 순서·범위 확인 필수)**
- **T14-A 진입구**: ① 주문 대시보드 인박스 스트립(대기>0 일 때만 렌더, `naver_triage_pending`
  30초 캐시 재사용) ② 주 메뉴 '네이버' 탭 승격(`menu_config` + 뱃지). 반나절.
- **T14-B 네이버 원본 도크**: `erp-edit-shell--split-ready` 빈 우측에 독립 마운트(기존 폼
  템플릿·JS 무수정 — 회귀 핫스팟 주의: edit_order.html 1,300줄·erp_order_tab 공유).
  데이터 = `erp-order-bootstrap` JSON 에 원본 요약 동봉(추가 fetch 0, 관리자 외 마스킹 검토).
  체크·귀속 상태 = `ExternalOrderLink` 트리아지 축 저장. 좁은 폭 = 컨테이너 폭 기준 서랍 전환
  (뷰포트 MQ 금지 — 공용 부품 규칙). 제일 큰 덩이.
- **T14-C 잔여**: 수집 목록/트리아지 화면을 본품별 묶음 표시로 정렬(naver_role 활용).

**하네스 주의(이 작업에서 이미 밟은 것)**: 새 mutation route 는 write guard + auth policy
manifest 2종 + ACTION_LABELS 등재 / fail-open 인벤토리 재생성 / CSS·JS 수정 시 `?v=` 범프 /
services/jobs `__all__` 닫힌집합 / pre_push_smoke 는 리베이스 후 재실행.

### T14-A 구현 기록 (2026-08-14 완료)

**사용자 확정(AskUserQuestion)**: 시작=T14-A, 탭+스트립 한 task, 메뉴 라벨=**'네이버 주문'**,
완료 기준=커밋+deploy push+스테이징 눈 확인. T14-B 선결정: 도크=**전 직원**·**마스킹 안 함**·
**체크 즉시 저장**. 진입구 권한=**전 직원 + 권한 개방**(트리아지 화면·확인·주문 만들기·담당
지정을 STAFF 이상으로, 운영 화면·지금 수집·raw 스냅샷은 ADMIN 유지).

**변경**
- 뱃지 카운트 불일치 수정: `triage_count.py` 가 `LINKED` 만 세던 것을 큐 정의와 동일하게
  `COLLECTED+LINKED`(미확인)로 — COLLECTED(주문 만들기 대기)가 뱃지 0 으로 보이던 버그.
- `context_processors.py`: 뱃지 계산을 ADMIN→ADMIN/MANAGER/STAFF 로(30초 전역 캐시 그대로).
- `naver_ingest.py`: triage·create_order·mark_reviewed·set_assignee 를
  `role_required(["ADMIN","MANAGER","STAFF"])` 로. 정책 manifest 3건 ADMIN_OPS→STAFF_MUTATION.
- 메뉴: `menu_config.py` 기본값 + `data/admin/menu_config.json` 에
  `naver_orders`('네이버 주문', `/admin/naver-ingest/triage`) — 실측 다음 위치.
  `layout_nav.html` 주 메뉴 루프에 해당 탭만 대기 뱃지. CONSTRUCTION 팀은 inject_menu 가
  main_menu 를 통째 교체하므로 자동 제외.
- `orders/index.html`: 대기>0 일 때만 렌더되는 `.naver-inbox-strip`(로컬 style 블록,
  기존 페이지 인라인 스타일 관례) + '확인하기'→트리아지.
- `naver_triage.html`: '수집 상태 화면으로' 버튼 ADMIN 게이트.

**검증**: 대상 테스트 29 passed (nav_entry 9·triage 16·menu_config 4) + pre_push_smoke
exit 0 (322 passed) + APP_OK. 신규 계약: COLLECTED 포함 카운트·STAFF 탭/뱃지·STAFF 트리아지
200·STAFF 확인 완료 기록·VIEWER 차단·스트립 대기>0 조건.

**범위 밖(미룸)**: 모바일 v2/v3 셸 nav 의 네이버 탭(3곳 분산 배선 — 별도 task 필요 시),
스트립의 '마지막 수집 시각' 표기(워터마크 추가 조회라 제외, 목업 대비 축소).

### T14-B 구현 기록 (2026-08-14 완료)

**핵심 발견**: 본품/추가옵션 판정은 원본 ``productClass`` 가 정본이다(스테이징 실데이터
42건 실측 — ``조합형옵션상품`` = 본품, ``추가구성상품`` = 추가옵션). 이름 휴리스틱은
귀속 추정(어느 본품의 옵션인가)에만 쓴다.

**구현**
- 마이그레이션 `naverdock_00`(← navercollect_00): `external_order_links.triage_state`
  JSONB 1개 — 체크(반영 표시)·귀속 상태. **reviewed_at 재사용 안 함**(그건 큐 이탈·첫
  확인 시각 불변 축, 도크 체크는 토글 가능한 표시 축). 모델 컬럼 동반(create_all parity).
- `naver_commerce/dock.py`: `build_dock_payload`(본품/추가옵션 판정·귀속 추정·복사 칩
  분해·저장 상태 반영, productClass 부재 시 금액 최대=본품 폴백), web-safe(DB만).
- 라우트 `POST /admin/naver-ingest/<link_id>/dock-state`(STAFF↑): checked/assigned_main
  부분 갱신, 귀속은 형제 본품 external_id·COMMON·null 만 허용(임의 문자열 거부).
  manifest 2종(STAFF_MUTATION) + ACTION_LABELS(`NAVER_DOCK_STATE_SET`) + audit coverage
  인벤토리 재생성.
- bootstrap 동봉: `_build_erp_order_bootstrap` 이 `structured_data.source ==
  NAVER_SMARTSTORE` 일 때만 `naver_origin` 을 실는다(일반 주문 링크 쿼리 0).
- 프론트(폼 무참조 additive): `naver_origin_dock.html`(pane+FAB+서랍 스켈레톤) ·
  `erp-naver-dock.css` · `erp-naver-dock.js`(문서 위임+싱글톤+마운트 감시 — fragment
  재실행 안전, 원본 문자열 전부 textContent 주입, 셸 폭 ResizeObserver 로 도킹↔서랍
  전환 — 뷰포트 MQ 금지, WDC split 열리면 서랍 모드 강제). 체크 즉시 저장, 실패 시
  화면 롤백. '확인 완료'=미확인 링크 전건 순차 review(기존 라우트 재사용).

**검증**: test_naver_dock.py 15 passed(판정·추정·폴백·저장·검증·감사·권한·bootstrap
동봉·비네이버 무렌더·**주문 mutation_version 불변**=폼 불가침 증거) + PG 레인 737 passed
(체인 왕복 포함, 로컬 5440 클러스터) + `alembic heads` 단일(`naverdock_00`) + smoke 322.

**밟은 함정**: audit coverage 인벤토리 드리프트(새 mutation route) —
`tools/harness/audit_coverage_scan.py` 재생성으로 해소.

**스테이징 실검증에서 잡은 버그 2개 (테스트가 못 잡는 부류 — 후속 도크류 작업 시 주의)**
1. `#erp-order-bootstrap` 은 `erp-order-shared.js` `_erpConsumeBootstrap` 이 **파싱 직후
   DOM 에서 제거**한다 — 다른 스크립트가 그걸 읽으면 레이스. 도크는 전용
   `#naver-origin-data` 태그를 따로 심는다(`e7157b5b`).
2. `#erpEditShell` 은 Bootstrap `.row` — 직계 자식에 `.row > * { width:100% }` 가 걸려
   position:fixed FAB 이 풀폭이 된다. `width:auto` 명시 필수(`291085bc`).

**스테이징 실검증(#4462, 2026-08-14)**: 1920 도킹(본품 묶음·복사 칩·체크 취소선) ·
체크 즉시 저장+새로고침 잔존 · 1366 FAB(우하단)+서랍 열림 · 귀속 드롭다운 경고색=미정만 ·
콘솔/네트워크/다이얼로그 무결. 검증용 체크는 원복(0/4).

### T15 사용자 결정 4건 (2026-08-18)

원장 재개 시점에 물어 확정한 것 — **재논의 금지**.

| # | 결정 | 근거 |
|---|---|---|
| 1 | 운영 켜기 안내는 **짧은 체크리스트**만 | 이미 클릭 단위 가이드가 있다(1~5단계). 중복 문서 대신 상단 체크리스트 5줄 |
| 2 | PR #92 **닫는다** | 승격 PR 이 둘이면 잘못 머지할 위험. #113 이 상위 집합 |
| 3 | 폰 '네이버 주문' 탭은 **나중에** | 모바일 nav 는 탭 목록·배지·렌더 3곳 동시 수정이라 회귀 위험. PC 흐름 안정이 먼저 |
| 4 | 취소 추적은 **연습 서버에서 미리 시험** | 진짜 취소를 기다리면 첫 실전이 곧 첫 시험. (T14-G 의 "실취소까지 대기" 결정을 뒤집음) |

#### T15-C 취소 추적 드릴 — 도구·실행 결과

**도구**: `scripts/maintenance/naver_claim_drill.py`. 저장된 원본 스냅샷에 `claimStatus` 만
얹어 상세 응답인 척 `refresh_claims()` 에 먹인다(스텁 클라이언트 — **네이버 호출 0회**).
`--apply` 는 백업 JSON(원본 스냅샷·triage_state·만든 알림 id)을 남기고 `--revert` 가 원복한다.
알림 삭제는 **event → user_state → notification 순**이다(`notification_events.user_state_id`
에 ondelete 가 없어 DB CASCADE 만 믿으면 삭제 순서로 FK 위반이 날 수 있다).

**스테이징 실행 결과 (2026-08-18, DB `railway @ 10.155.135.220`)**

- link 53(주문 있음)·link 120(주문 전) CANCEL_REQUEST 주입 → `{'refreshed': 2, 'claimed': 2,
  'notified': 8}`. 담당이 보류함이라 **활성 ADMIN 4명**(upperkill·perfgate_ci·qa_claude·
  claude_master)에게 각각 1건 — `_notify_targets` 의 ADMIN 승격 분기가 실제로 돈다.
- **fan-out 실측**: 알림 8건 각각 `notification_user_states` 1행(source `target_user`) +
  `notification_events` 8행. 알림센터 API(`/erp/api/notifications`) 최상단에 NAVER_ORDER_CLAIMED
  2건이 실제로 떴다(claude_master 기준, 미읽음).
- **중복 방지 실측**: 같은 상태로 재실행 → `notified: 0` (5분 폴링 중복 알림 없음).
- **화면**: 수집 이력에서 두 건 모두 `취소 요청` 배지, 트리아지 도크에
  "네이버 취소 요청 · 사유 … · 2026-08-18T14:06" + **"주문을 만들 수 없습니다"** 차단 문구.
- **원복 완료**: 스냅샷·triage_state 원값 복귀, 드릴 알림 8+4+4건 전부 삭제(잔여 0).

**드릴에서 드러난 사실 2가지**

1. **편집 화면 도크는 `structured_data['source'] == 'NAVER_SMARTSTORE'` 게이트**를 탄다.
   스테이징 주문 **#4461(link 53)** 은 이 표식이 없어(2026-08-13 초기 경로 산물, 링크 101개 중
   유일) 편집 화면에 도크가 아예 붙지 않는다 — 그 주문은 취소가 나도 **알림·관리자 이력에서만**
   보인다. 현재 승격 경로(`promote_link_to_order` → `map_group`)는 표식을 항상 넣으므로
   운영에서는 재발하지 않는다. 스테이징 잔재 1건이라 그대로 둔다.
2. 스테이징 link 39~49 는 **원래부터** CANCEL_DONE·RETURN_DONE 상태다(실데이터).
   그래서 그 집의 도크 `claim_label` 은 드릴 값이 아니라 원래 값으로 표시된다 —
   드릴 대상 선정 시 **클레임이 없는 링크**를 골라야 판정이 깨끗하다.

**남은 미검증 1가지**: 네이버 `last-changed-statuses` 변경 목록이 **취소를 실제로 실어 주는지**.
드릴은 변경 목록에 뜬 이후를 검증한다. 이건 실물 취소가 나야 확인된다(스테이징에서
`claim_sync.refreshed_at` 이 갱신되고 있으므로 재조회 배선 자체는 살아 있다).

## 운영 승격 (2026-08-18) — **PR #113 로 전환**

사용자 지시 **"전체 푸쉬"**: `deploy` 스냅샷 브랜치 `promo/full-2026-08-18`(= `fadb5ebc`)를
`production` 대상으로 올렸다 — https://github.com/lahomsystem/FOMS/pull/113
(production 대비 **256커밋 / 358파일**). 머지는 **사용자가 직접** 한다(내가 하지 않는다).

**왜 전체 푸쉬가 오히려 정합적인가**: 타 세션이 남긴 "AS-AXIS-01 운영 승격 차단" 사유는
*"`asaxis_00` 부모가 미승격 `naverdock_00` 이라 단독 cherry-pick 시 체인이 끊긴다"* 였다.
전체 푸쉬면 네이버 마이그레이션 4종이 함께 올라가 그 조건이 해소된다.

**체인**: 운영 계보 끝 `asfresh_00` → `naver_link_00` → `naver_triage_00` → `navercollect_00`
→ `naverdock_00` → `asaxis_00` (+ `orderreason_00`). 스냅샷 브랜치 `alembic heads` = 단일
`asaxis_00`. 스냅샷에서 `pre_push_smoke` exit 0 · APP_OK 확인.

**머지 후 사람 작업(순서 그대로)**: ① 운영 DB 계정 2개 생성(`create_naver_ingest_accounts.py`)
② 운영 `WORKER` 에 자격증명 5종 ③ **커머스API센터 IP 3개를 운영 WORKER static IP 로 교체**
(한도 3 = dev·운영 동시 운용 불가) ④ `FOMS_NAVER_SYNC_ENABLED=1` 후 "지금 수집" 1회 확인.

**PR #92 는 이 PR 로 대체**(예전 스냅샷) — **2026-08-18 사용자 결정으로 CLOSED**.

### 승격 충돌 해소 (2026-08-18, `08e5211e`)

PR #113 이 처음에 `CONFLICTING` 이었다 — 운영과 deploy 가 27곳 어긋나 있었다(같은 수정이
cherry-pick 사본으로 양쪽에 다른 SHA 로 들어온 탓). **사용자 지시: deploy 에 운영을 먼저
병합하고 운영 핫픽스는 무조건 보존**.

- 코드·템플릿 충돌 13건 — 운영 고유 변경은 전부 **구버전 시그니처**(deploy 가 상위 집합)임을
  파일별로 대조 확인 후 deploy 채택. 두 트리 실제 차이는 134파일 / +543 −16,592 였다.
- **마이그레이션 체인 재배열(이번 승격의 진짜 함정)**: 운영 DB 는 `asfresh_00` 에서 멈춰
  있는데 deploy 는 `asfresh_00` 을 `orderreason_00` **아래**에 두고 있었다. 그대로 올리면
  alembic 이 `asfresh_00` 위쪽만 실행하므로 **`orderreason_00`(주문 변경 사유 테이블)이
  운영에 영영 생성되지 않는다**. 운영 파일(`asfresh_00.down = senderphone_00`)을 채택하고
  `naver_link_00.down → asfresh_00`, `naver_triage_00.down → orderreason_00` 으로 재연결.
  최종 체인: `senderphone_00 → asfresh_00 → naver_link_00 → orderreason_00 → naver_triage_00
  → navercollect_00 → naverdock_00 → asaxis_00` (단일 head).
  **다음 승격에서도 같은 검사를 할 것** — "deploy 체인 순서 ≠ 운영이 실행할 순서".
- 하네스 인벤토리 4종 재생성(failopen 526·audit 183/미감사 0·mutation 65·state 41).
- 문서 충돌 7건은 양쪽 보존. 그 결과 `AI_STATUS` 상단 40줄이 5,440자로 불어 예산(4,000자)
  게이트가 red → 중복 4줄 제거 + 고유 4줄을 '## 최근 완료' 로 이관해 3,957자로 맞췄다.

**검증**: `alembic heads` 단일 · APP_OK · `pre_push_smoke` exit 0 · alembic/failopen/auth
게이트 39 passed. deploy 와 승격 브랜치를 같은 커밋(`08e5211e`)으로 맞췄고 PR #113 은
**MERGEABLE** 로 전환됐다.

## PR #92 상태 (2026-08-14)

새 운영 head(asfresh_00, PR #93) 기준으로 재구성 — 체인 `asfresh_00 → naver_link_00 →
naver_triage_00 → navercollect_00`, orderreason_00·모델 정합 제거(불필요해짐). 체크 green.
**T12·T13 은 아직 PR 미반영** — 스테이징 검증 후 얹는다. 승격 트리 `c:\tmp\foms-pnav`.

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

**잔여**: 대시보드 "담당 미지정" 뱃지 → **T11 에서 완료**.

## T11 — 대시보드 '담당 미지정' 뱃지 + T0 준비 안내서

**범위**
- `compute_unassigned_intake_order_ids()`(`dashboard_read_model.py`) — 보류함이 아직 owner 인
  수집 주문 id 집합. owner SSOT 는 `OrderAssignment`(active SALES), `structured_data` 투영 아님.
- DTO `is_unassigned_intake` → `dashboard_grid.html` 표 '담당' 칸 + 도면 창구 카드 '주문 담당'.
- `SOURCE_MARKER` 를 `mapping.py` 에서 `constants.py` 로 이동(대시보드도 읽는 값).
- `docs/guides/NAVER_INGEST_SETUP.md` — 시크릿 재발급·static IP·환경변수·확인을 클릭 단위로.

**설계 결정 2개(재개 시 되돌리지 말 것)**
1. **캐시 blob 밖에서 계산한다.** `compute_orders_attachment_assignee_maps` 는 TTL 120초
   캐시라 거기 넣으면 배정 후에도 뱃지가 최대 2분 남는다. 배정 즉시 사라져야 하는 표시다.
2. **수집 주문이 없는 페이지는 쿼리 0개.** `structured_data['source']` 선필터가 먼저라
   평상시 대시보드에 추가 비용이 없다(hot path 규칙).

**검증 결과 (2026-08-13 실행)**
- `python -m pytest tests/services/integrations/test_naver_unassigned_badge.py -q` → **7 passed** ✅
  (보류함 owner=뱃지 · 실담당자=뱃지 없음 · 일반 주문 제외 · 계정 부재 무해 · 수집 0건이면
  세션 `query` 호출 자체 없음(폭발 세션으로 실증) · DTO 전달 · 기본값 회귀 없음)
- `python -m pytest tests/services/integrations -q` → 112 passed ✅ /
  `-k "dashboard"` → 457 passed(에러 7건은 visual 레인 env 전제, 이 변경과 무관) ✅
- `APP_OK` ✅ / `pre_push_smoke` exit 0 (322 passed) ✅

**레인 함정**: SQLite 레인은 SALES 부분 유니크가 전체 유니크로 굳어 **owner 교체가 불가능**하다
(T10 함정과 동일). 그래서 테스트는 교체 대신 주문마다 최종 owner 로 만들어 비교한다.
