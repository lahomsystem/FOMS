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
2. **`create_order()` 는 주소가 있으면 GEOCODE outbox 를 무조건 예약한다**
   (`foms/services/orders/order_create.py:203-207`). production 에 SIDEFX 서비스가 없어 행이 쌓인다.
   → `skip_geocode: bool = False` 파라미터 추가 + 수집 경로는 True + 네이버 좌표 직접 주입.
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
| T0 | 선행(사람 손): 시크릿 재발급 · 시스템 계정 2개 · WORKER static IP 등록 | — | BLOCKED | — |
| T2 | `ExternalOrderLink` 모델 + alembic 마이그레이션 | — | DONE | `naver_link_00` (`down_revision=senderphone_00`) |
| T3 | `naver_commerce/client.py` (토큰 캐시·조회·재시도·백오프) | — | DONE | 테스트 24 green |
| T4 | 매핑 + `create_order()` 연동 + `skip_geocode` | T2, T3 | PENDING | — |
| T5 | WORKER 폴링 루프 + 게이트 + rq enqueue 경로 | T4 | PENDING | — |
| T1 | Railway WORKER static IP 실검증 (`--once --dry-run`) | T0, T3 | PENDING | — |
| T6 | 관리 화면 (수집 이력·수동 실행·배지) | T4, T5 | PENDING | — |
| T7 | 앱 인증 만료 D-7 알림 | T2 | PENDING | — |

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

**진행 메모**: 2026-08-13 사용자 확인 — **셋 다 미완료**. 코드 task 는 T0 없이 진행 가능하므로
T2 부터 착수했다. T1(실 API 검증)은 T0 완료 후에만 가능하므로 그때까지 BLOCKED.

---

## T2 — `ExternalOrderLink` 모델 + 마이그레이션

**범위**: `models.py` 신규 테이블 + `migrations/versions/` 신규 리비전 (down_revision = `auditlife_00`).

컬럼: `id` PK / `channel` / `external_id` / `order_id` FK→orders.id nullable /
`external_order_no` / `raw_snapshot` JSONB / `sync_status`(`LINKED`·`PENDING_REVIEW`·`FAILED`) /
`failure_reason` / `created_at` / `updated_at`.
**`UNIQUE (channel, external_id)`** — 동시 실행 레이스 방어의 본체(앱 체크로는 못 막음).
워터마크 저장 위치도 이 task 에서 확정(기존 `system_setting` 계열 재사용 여부 조사 후 결정).

**체인**: `down_revision = 'senderphone_00'` (원격 tip 기준). 원격 체인은
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

## T4 — 매핑 + `create_order()` 연동 + `skip_geocode`

**범위**
- `create_order()` 에 `skip_geocode: bool = False` 추가 (기본값 False = 기존 호출자 무변경).
- 수집 매핑 모듈: 스펙 §3.6 표 그대로. `takingAddress` 는 버린다(반품 수거지).
  `status='RECEIVED'` 고정, `structured_data['source']='NAVER_SMARTSTORE'`,
  `structured_data['orderer']` 에 주문자 보존(주문자≠수취인 실재).
- 좌표 직접 주입: `lat`/`lng`/`geocode_status='success'`/`geocoded_at`/`address_hash`.
- 매핑 실패는 **주문을 만들지 않고** `ExternalOrderLink.sync_status='PENDING_REVIEW'` 로 남긴다.
- mutation manifest 2종 등재.

**완료 기준**
- fixture(네이버 실응답 구조 스냅샷) → 주문 1건 생성 테스트 green.
- **같은 fixture 재실행 시 주문 0건 추가**(멱등) — UNIQUE 위반이 아니라 정상 skip.
- `geocode_outbox` 행 0건 (skip_geocode 경로).
- 기존 `create_order` 호출자 회귀 없음: `python -m pytest tests/ -k "order_create or order_import" -q` green.
- manifest 게이트: `python -m pytest tests/ -k "mutation_writer or mutation_policy" -q` green.

---

## T5 — WORKER 폴링 루프 + 게이트 + rq enqueue

**범위**
- `scripts/maintenance/run_naver_order_sync.py` — `run_notification_escalation.py` 패턴 그대로
  (`--loop --interval --json --once --dry-run`, app 1회 부팅, 실패가 본체를 안 죽임).
- `start.sh` 의 `USE_RQ_WORKER=1` 분기 안, `FOMS_ESCALATION_LOOP_ENABLED` 옆에
  `FOMS_NAVER_SYNC_ENABLED` 게이트로 백그라운드 서브셸 추가(기본 off).
- 워터마크: 성공한 구간 끝까지만 전진(유실 방지). 실패는 구간 단위 재시도.
- web "지금 수집" = `foms/services/jobs/queue.py` 경유 `default` 큐 enqueue **만**.

**완료 기준**
- 게이트 off → 루프 미기동 / on → 주기 실행 (`--once --dry-run` 로컬 확인).
- **web 경로에서 `api.commerce.naver.com` 으로 직접 나가지 않음을 테스트로 고정**
  (web blueprint 임포트 그래프에 naver client HTTP 호출 없음 — 계약 테스트).
- `bash -n start.sh` 통과.

---

## T1 — Railway static IP 실검증 (T0·T3 이후)

**완료 기준**: WORKER 컨테이너에서
`python scripts/maintenance/run_naver_order_sync.py --once --dry-run --json`
→ 토큰 발급 성공 + 변경분 조회 성공(HTTP 200, 건수 로그). 주문 생성 없음(dry-run).

---

## T6 — 관리 화면

**범위**: 수집 이력 목록(성공/보류/실패 필터) · "지금 수집" 버튼(enqueue) · 워터마크·마지막 성공 시각 표시 ·
주문 상세 "네이버 수집" 배지 + 원본 스냅샷 보기(**관리자 전용**) · `naver_unassigned` owner 주문의 "담당 미지정" 뱃지.
인라인 스타일 금지(`erp-pro.css`), jQuery 금지, `fetch` + `data.success` 검증.

**완료 기준**: 스테이징 실주문 1건 수집 → 화면에서 확인 → 재실행 시 중복 0건.
CSS/JS 수정 시 `?v=` 범프(SW staticCacheFirst 함정).

---

## T7 — 앱 인증 만료 알림

**완료 기준**: 만료 D-7 시점 알림 1건 발송 확인(테스트로 시각 주입). 알림 미발송 시 API 가 조용히 죽는다 — 리스크 표 1순위.

---

## 공통 종료 절차 (매 task)

1. `python -c "import app; print('APP_OK')"`
2. 해당 task 완료 기준 명령 실행 → 출력 확인
3. `pwsh scripts/ops/pre_push_smoke.ps1` exit 0
4. UTF-8 파일로 커밋 메시지 작성 → `git commit -F <파일> -- <경로들>` (동시 세션 레이스 방어)
5. 이 원장 Task 표 상태·커밋 SHA 갱신
6. push 는 `deploy` 만. push 후 `gh run list --branch deploy` 로 전 워크플로 green 확인
