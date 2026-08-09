# 시스템 전체 감사 로깅 (설계 스펙)

- 작성일: 2026-08-05 (2차 개정 — `**D` CEO 리뷰 + 3-agent 교차검수 반영, §9)
- 등급: `**D`
- 상태: **승인 완료(전 항목·권장 결정 5건) — Phase 1 파일럿 진행**
- 확정된 사용자 결정: ① 범위 = P0·P1·P2 전 항목 ② 설계 승인 후 구현 ③ §8 결정 5건 권장안 ④ Phase 1 완료 후 보고

## 1. 문제

ERP인데 "누가 언제 무엇을 바꿨나"에 답할 수 없는 3중 공백이 있다.

1. **프로덕션 앱 로깅 설정이 없다.** `basicConfig`는 `run.py`(로컬 dev)에만 있고
   gunicorn 경로(`app.py` → `foms/platform/app_factory.py`)에는 0건 — root=WARNING +
   핸들러 없음이라 INFO 전량 소실. 느린 요청 로그(`http.py:295`)·RUM 집계
   (`foms_rum.py:171`)가 운영에서 죽어 있고, `dashboard_cache.py:24`가 이 문제를
   주석으로 진단한 채 파일 하나만 국소 우회 중이다.
2. **DB 감사의 실체가 자유 텍스트 1컬럼이다.** `security_logs.message` — 대상 ID·필드·
   old/new 구조화 없음, 조회는 ILIKE뿐(`web/admin/audit.py:30`). `access_logs`는
   writer 0건 사문 테이블. `order_events`의 old→new 캡처는 화이트리스트 소수뿐.
3. **돈·파일·주문생성이 무음이다.** 금액 변경(예약금·할인·자유입력) 이력 0 — 실사고
   기발생(주문 4414 할인 11,060원 소실, `2026-07-31-full-promotion-prep-ledger.md:385`).
   첨부 hard delete 무기록, ERP 주력 생성 경로 `ORDER_CREATED` 없음, R2 presigned 발급 무기록.

## 2. 조사 확정 사실 (deep research + 2회 사실 대조 + 실증 — 재조사 금지)

- `log_access()`(`foms/web/auth/routes.py:48`, `auto_commit=True`)는 이름과 달리
  **SecurityLog**에 쓰고 `additional_data`는 버려진다. 실패 시 `print()`(`:56`).
- `_record_structured_events`(`foms/api/erp_orders_structured.py:392`)는 3종만 diff,
  payment 블록은 안 본다. 결제확인 토글(`:1082-1148`)은 **이미 deepcopy→재할당→
  flag_modified 정본 패턴**(`:1100,1122-1123`)이며 OrderEvent만 없다.
- **payment 실키 13개**: deposit·discount·free_input(자유 텍스트 "배송비 : 30,000")·
  cash_receipt·**balance_note(잔금 메모)**·확인 토글류 8키
  (`erp-order-shared.js:206-230`). **레거시 `payments`(복수형) 블록이 폴백으로 살아
  있다**(`erp-order-shared.js:89-92,116-118`, 서버 allowlist
  `structured_form_projection.py:52-53`) — 서버 extractor(`_extract_discount_amount`·
  `erp_deposit_amount_from_structured` 등)가 폴백을 처리한다.
- **출고가는 `totals.shipping_price` 파생값**(`structured_form_projection.py:160`).
  단 재계산은 전체저장 PUT(`erp_orders_structured.py:906`)·생성(`order_create.py:113`)
  **2곳뿐** — 인라인 PATCH·autosave·payment-confirm은 totals를 안 건드려 stale로 남는다.
  어느 쪽이든 독립 diff 대상 부적격.
- **`Order.shipping_fee`(flat, `models.py:69`)는 이미 감사된다** —
  `SHIPPING_FEE_CHANGED` OrderEvent(from/to payload, `web/admin/storage.py:29-30,
  292-296`). writer는 `_commit_storage_field`(`:291`)와 주문 복사 전파
  (`order_copy.py:160`)뿐. **T2 캡처 대상에서 제외**(중복 이벤트 방지).
- **[실증] `flag_modified`는 attribute history의 old를 파괴한다** — SQLAlchemy 2.0.23
  로컬 재현: 재할당만 → `deleted=[old]`, 직후 `flag_modified` → `deleted=()`
  (`state._modified_event(is_userland=True)`가 committed_state를 NO_VALUE로 덮음).
  정본 패턴(deepcopy→재할당→flag_modified) 포함 **전 writer에서 old 소실** —
  `get_history` 기반 before 설계는 불가. before는 DB에서 읽어야 한다.
- ERP draft 생성(`erp_orders_structured.py:1155,1190`)·`_create_session_draft`(`:1303`)·
  `_finalize_draft_state`(`:530`)는 `create_order()` 미경유 — 이벤트 0.
  마법사 선례 `erp_order_draft.py:510`은 create_order 경유이나 `_wizard_enabled`
  게이트(`:44-48`) 뒤 비주력.
- 첨부 삭제(`order_routes.py:298`)는 hard delete + R2 즉시삭제, R2 실패 `print()`(`:296`).
  `OrderAttachment` tombstone 컬럼 없음(`models.py:239-280`), 사용처 84파일·428회
  (프로덕션만 41파일·267회). `ATTACHMENT_ADDED/DELETED` 라벨만 존재
  (`order_event_display.py:172-173`), emit 0. 정답 패턴 = `blueprint_projection.py`
  (이벤트 + outbox `source_domain="ORDER_EVENT"`, one-of CHECK `models.py:2310`).
- **첨부 카운트 raw SQL 2곳**: `construction_read_model.py:134`·
  `production_read_model.py:207` — `with_loader_criteria` 미적용 경로.
  (`delete_retention.py:257`의 raw는 purge 용도 — 전량 조회가 정답, 치환 금지.)
- **첨부 실키는 canonical 분기로 통과**: `/view|download/orders/<id>/...`는
  `_deny_order_scope`만 타고 **OrderAttachment 행을 조회하지 않는다**
  (`files/routes.py:70-76`). row 조회 분기(`:79-88`, def `:49`)는 비정규 key 전용 —
  tombstone 차단은 canonical 분기에 storage_key lookup 추가 없이는 불가.
- 파일 라우트 무기록: view(:118)·presigned(:155)·download(:195). presigned 라우트는
  장수 이미지 뷰어 4파일의 소스 정적 단언(`test_file_url_lifecycle.py:76-79`)이 사용을
  막고 실프론트 호출자 0건 — 사문. 실열람은 `/view/` → `storage.get_download_url`
  (**StorageAdapter 메서드**, `storage.py:371`, 호출부 14곳 — 채널·WAM·admin 헬스체크
  포함) → 302. **로컬 스토리지는 `send_file` 직행(`routes.py:138-141`) — 미계측 경로.**
- **GET·abort 경로에 commit 없음** — teardown `close_db`(루트 `db.py:99-102`, 등록
  `platform/http.py:358`)는 close만. 감사 행은 본 트랜잭션에 태우면 소실.
- **커넥션 풀: pool 5 + overflow 5 = 프로세스당 10, pool_timeout 10초**(`db.py:52-55`),
  gunicorn gevent 2 worker. 요청 중 제2 커넥션 checkout은 풀 고갈·10초 tail 위험 —
  요청 경로 독립 커밋 선례는 `channel_security.py:107-110`(`engine.begin()`).
- 관리자 수정(`auth/routes.py:533`) from/to 없음. 타인 비번 재설정(`:505-515`)·
  `/register`(`:294-347`) 무기록. API 403(`order_mutation_policy.py:446`)·CSRF 차단
  (`request_write_guard.py:77`)은 logger만.
- `request_id` 발급·헤더·에러 페이로드는 있으나 로그 라인 주입 없음(`http.py:206,277,309`).
- **RedactionFilter는 root "로거"에 부착**(`error_logging.py:96`) — 로거 필터는 전파
  레코드에 무효. 핸들러 부착 필요.
- `run.py` basicConfig 제거 시 `tests/domains/test_run_startup_logging.py`(5 테스트,
  `run._get_startup_log_path` 등 직접 단언)가 red — 동반 개정 필수.
- **Alembic 체인은 빈 DB에서 실행 불가**(`tests/postgres/conftest.py:9-13` 명시 —
  create_all + stamp 부트스트랩). order_events "편입 마이그레이션"의 create 분기는
  어디서도 실행되지 않는 사문 코드가 된다.
- `order_events`: FK `ondelete='CASCADE'`(`models.py:775`), relationship
  `models.py:783`(backref 없음, `Order.events` 사용처 0). raw DDL 재생성 경로
  **`scripts/ops/erp_build_step_runner.py:329`**(CASCADE 포함 — FK drop 시 동기 수정
  필수). 단독 인덱스 3개.
- **OrderEvent 소비자 중 event_type 무필터 6곳**(`api/events.py:87,115`,
  `order_timeline_v3.py:192`, `erp_mobile_order_display.py:103,696`,
  `channel_wam_read_model.py:220`) — 신규 타입은 자동 노출되며 라벨 미등록 시
  "기타 변경". 필터 있는 소비자(shipment/production change_alerts)는 영향 0.
- retention: security_logs·order_events·notification_events·channel_delivery_logs
  purge 잡 0. 기존 잡 3종은 전부 다른 테이블.
- `user_deletion.py`: NULL 목록 `:28-40`(**11필드** — SecurityLog·OrderEvent·OrderTask·
  Notification 3필드·AccessLog·OrderAttachment·OrderEstimate·ChannelManagerLink 2필드),
  Chat 3종 hard delete `:42-46`.
- FAILOPEN `LOG_AND_CONTINUE`+`has_logging=False` 179건 게이트 green 통과.
  mutation writer `EXTERNAL` 22곳 baseline 핀.
- 복제 패턴: `order_date_sync.py` before_flush SSOT(등록 `foms/services/app_init.py:180-182`,
  좌표는 계약 테스트가 고정 — `foms_namespace_surface_tests.py:337,357`).
- **동시 세션 충돌 축**: 출고 알림 플랜 잔여 T6가 `order_date_sync.py`
  `_emit_construction_date_event` 영역과 `push_sender.py`를 수정 예정 —
  본 플랜은 **`order_date_sync.py` 무접촉**(가드 로직 복제, 별도 파일)으로 회피.

## 3. 설계 원칙

1. **이력 매체 기존 결정 유지**: `OrderEvent` + `structured_data`. 신규 로그 테이블
   없음 — 유일 예외는 사문 `access_logs` 부활(기존 테이블 재사용, **조회 화면 없음 —
   SQL 전용**을 명시적 한계로 수용).
2. **무음 봉합은 SSOT/chokepoint** — 쓰기는 before_flush, 파일 접근은 파일 라우트 3곳.
3. **감사 쓰기 2모드**:
   - 동승: mutation 라우트 — 본 트랜잭션 내 insert(비즈니스 rollback 시 동반 소멸이 정합).
   - 독립: GET·abort 경로 — **전용 소형 감사 engine**(pool 2·overflow 0·
     `pool_timeout` 0.5s) + `engine.begin()` Core INSERT 함수 1개(~15줄,
     `channel_security.py` 선례형). 실패 즉시 drop + 로그(fail-open). **T5·T6 공유.**
     주 engine 제2 checkout 금지(풀 고갈·10초 tail 방지).
4. 감사 쓰기 실패는 본 요청을 죽이지 않는다(로그 동반 fail-open).
5. **PII 마스킹**: 고객 전화·주소 원문 금지. 마스킹 필터는 **핸들러 레벨** 부착.
6. **성능**: hot path 추가 쿼리는 배치 1회, TTFB 예산 불변(상향 금지).

## 4. 워크스트림 설계

### Phase 1 — P0

#### T1 프로덕션 로깅 부트스트랩 (+ request_id 주입 통합, 구 T7 흡수)
- `foms/platform/logging_setup.py` 신설: 멱등 `configure_logging()` — root **INFO** +
  `StreamHandler(stderr)` + 포맷(`request_id` 토큰 포함).
- **핸들러에 필터 부착**: RedactionFilter + request_id Filter(항상 속성 주입,
  요청 밖 `-` — 서드파티 레코드 포맷 실패 방지). 로거 레벨
  `install_protected_logging`은 유지하되 커버리지 전제로 삼지 않는다.
- `run.py` basicConfig 제거 — configure_logging 단일 SSOT. `FOMS_STARTUP_LOG_PATH`
  opt-in 파일 핸들러 흡수. **`tests/domains/test_run_startup_logging.py` 동반 개정.**
- `dashboard_cache.py:24-42` 국소 우회 제거. pytest·alembic·tools/ 재초기화 no-op.

#### T2 금액 변경 이벤트 `PAYMENT_CHANGED` (before_flush SSOT)
- `foms/services/order_payment_sync.py` 신설 + `app_init.py` 등록 2줄.
  **`order_date_sync.py` 무접촉** — origin·재진입·rollback 가드 로직은 **복제**
  (동시 세션 충돌 회피가 재사용 이득보다 크다 — §2 충돌 축. 통합 리팩터는
  출고 알림 플랜 완료 후 별건).
- **before 출처 = DB 배치 1회**: before_flush에서 payment-diff 대상 dirty Order id를
  모아 `session.connection()`으로 flush 전 committed `structured_data`(payment 관련만)
  SELECT + `session.info` origin 캐시(다중 flush 대비). `get_history`는 쓰지 않는다
  (§2 실증 — flag_modified가 old 파괴). writer 패턴 계약·in-place 부정 테스트 불필요
  (DB before라 writer 무관 포착). bulk `update()`/raw SQL 우회는 mutation writer
  인벤토리 게이트 소관.
- **캡처**: `payment.deposit`·`discount`·`free_input`(원문 diff + 파싱 합계 병기)·
  `cash_receipt`·`balance_note`·`deposit_confirmed`/`balance_confirmed` 토글.
  old/new 산출은 **기존 서버 extractor 재사용**(`_extract_discount_amount`·
  `erp_deposit_amount_from_structured` 등 — 레거시 `payments` 폴백 자동 처리).
  **`Order.shipping_fee` 제외**(기존 `SHIPPING_FEE_CHANGED`가 감사 — 중복 금지).
  `totals.*` 제외(파생·stale).
- payload `{"field","from","to","source"}` 단일 타입(결정 ①). 정규화(숫자화·
  None/미존재 동일시), origin 복귀 시 취소, 트랜잭션당 field별 1건.
- **draft 억제**: `meta.draft` 주문은 이벤트 억제(자동저장 노이즈 차단, 승격 시점
  값이 초기값).
- **노출**: `order_event_display.py`에 라벨 `"PAYMENT_CHANGED": "금액 변경"` 등록.
  무필터 소비자 6곳(§2)의 노출은 **주문 열람 권한과 동일 범위라 수용**(금액은 이미
  주문 상세에서 열람 가능) — 명시 결정.
- 결제확인 토글 라우트 **편집 0줄**(이미 정본 패턴 — SSOT가 자동 포착).

#### T3 ERP 생성 경로 `ORDER_CREATED` 배선
- `_finalize_draft_state`에서 `ORDER_CREATED`(payload `via:"erp_draft"`, actor),
  draft 최초 생성 `ORDER_DRAFT_CREATED`(결정 ②). `create_order()` 리팩터 금지.

### Phase 2 — P1

#### T4 첨부 수명주기: 이벤트 + soft delete 전환
- `OrderAttachment` `deleted_at`/`deleted_by_user_id`(마이그레이션, downgrade 포함).
- **전역 기본 필터** `with_loader_criteria`(84파일 수동 필터 금지) + 휴지통/복구 opt-in.
- **raw SQL 2곳 명시 수정**: `construction_read_model.py:134`·
  `production_read_model.py:207`에 `AND deleted_at IS NULL` + lint 게이트에
  `FROM order_attachments` raw 패턴 검출(신규 우회 차단). `delete_retention.py`는 제외.
- **canonical 분기 tombstone 차단**: `files/routes.py` canonical key 경로에
  storage_key(+thumbnail_key) 기준 lookup 1쿼리 추가(주 세션 read) —
  없으면 삭제 첨부가 유예기간 내내 열람됨(§2). storage_key 인덱스 확인.
- 삭제 API: tombstone + `ATTACHMENT_DELETED` 이벤트 id를
  `source_domain="ORDER_EVENT"`로 STORAGE_DELETE outbox(one-of CHECK 준수,
  `thumbnail_key` 포함). R2 즉시삭제 제거.
- `ATTACHMENT_ADDED`/`META_UPDATED` emit + 라벨은 기존 등록분 사용.

#### T5 관리자 행위 구조화 + 접근거부 DB 기록
- field별 from→to 명시, 타인 비번 재설정 별도 기록(값 미기록), `/register` 기록,
  `log_access` 실패 print→logger.
- API 403·CSRF 차단 SecurityLog — §3-3 독립 모드 공유 헬퍼.
- dedupe (user_id or IP, endpoint) 60초 + 억제 카운트 + 캐시 상한/GC.
  프로세스당 캐시 감쇠 1/4은 v1 한계로 수용(Redis 승격 범위 밖).

#### T6 파일 접근 기록 — `access_logs` 부활
- **계측 지점 3곳 핀**: `files/routes.py` view(`:133`)·presigned(`:170`)·
  download(`:215`) 호출부 — `get_download_url` **메서드 내부 계측 금지**(호출부
  14곳: 채널·WAM·admin 헬스체크 오염). **로컬 스토리지 `send_file` 경로는 미계측**
  (운영은 R2 — 한계 명시).
- view는 (user, file_key) **10분 dedupe**(결정 ③). IP·UA·additional_data 저장.
- §3-3 독립 모드 공유 헬퍼. 실패 시 파일 응답 정상.
- 인덱스 마이그레이션 `(user_id, timestamp)`·`(timestamp)`. **조회 화면 없음 —
  SQL 전용**(한계 명시). 대량 export는 범위 밖(기존 SecurityLog 유지).

### Phase 3 — P2

#### T8 `security_logs` 구조화
- 컬럼 추가: `action`·`target_type`·`target_id`·`detail`(JSONB). `message` 유지.
  `log_access()` 확장(additional_data → detail 격납 — T6에서 이연된 결함 해소) +
  우선 호출부 전달. admin audit UI 필터(**`?v=` 범프**).
  `(target_type, target_id, timestamp)` 인덱스.

#### T9 감사 원장 수명주기 (retention + CASCADE 분리)
- **FK drop 마이그레이션 1건만**(`DROP CONSTRAINT IF EXISTS` 방어적) +
  **models.py 동기 수정**(ForeignKey 제거 + relationship 명시
  primaryjoin/foreign() — 수정 범위는 `models.py:783` 1곳) +
  **`erp_build_step_runner.py:329` raw DDL 동기 수정**(CASCADE 재생성 차단).
- ~~Alembic 편입 조건부 마이그레이션~~ **삭제** — create 분기는 사문 코드(§2
  부트스트랩 사실). 이후 변경은 실DB에서만 도는 정식 체인으로 충분.
- downgrade: 고아 존재 시 PG 제약 검증이 스스로 실패(fail-closed 공짜) —
  사전 카운트 안내 메시지만, 전용 차단 로직·전용 테스트 없음.
- retention purge `tools/ops/purge_audit_logs.py`(advisory lock + keyset, 기본
  dry-run): security_logs ≥2년·notification_events/channel_delivery_logs/
  access_logs ≥1년. order_events **purge 제외**. cron은 신설 대신
  **기존 receipt-purge cron에 `&&` 체이닝**(Railway 서비스 증설 없음 — 실패
  커플링 1건은 수용). FK drop 후 조인 `EXPLAIN` 확인.

#### T10 외부 관측 — Sentry
- `sentry-sdk[flask]`, DSN env-gated(없으면 no-op), `send_default_pii=False`.
- `before_send` = `_REDACTIONS` 패턴 기반 **재귀 dict 마스킹 워커 신설**
  (RedactionFilter 직접 재사용 불가) + 마스킹 계약 테스트.
- gunicorn `--access-logfile -`(Procfile·start.sh).
- **사용자 액션**: Sentry 프로젝트·DSN·Railway env(착수 시 안내 후 대기).

#### T11 잔여 구멍 수리
- `user_deletion.py`(결정 ⑤): NULL 목록 `:28-40` **11필드 전수 재분류**(감사 보존
  vs 실삭제 유지 — Chat 3종 `:42-46`은 유지). hard delete → 비활성화+익명화 표기.
- FAILOPEN `SWALLOW_BY_CONTROL_FLOW` disposition 분리 + 179건 무성장.
- `EXTERNAL` writer 22곳 중 CS/도면 경로 CANONICAL 전환 착수.

## 5. 성능·정책 제약 (설계 구속)

- before_flush diff: dirty Order만, dict 접근. **payment-dirty 존재 시에만 배치
  SELECT 1회**(같은 트랜잭션 커넥션 — 추가 checkout 없음).
- 독립 모드 감사 쓰기: 전용 소형 engine만 사용, 주 engine 제2 checkout 금지.
- 대시보드/리스트 TTFB 예산 불변. 신규 인덱스는 마이그레이션 + `EXPLAIN`.
- 인벤토리 게이트 5종: 원격 tip 클린 worktree 재생성(라인시프트 함정).
- 계약 테스트 위치: 도메인 `tests/domains/`, DB 왕복 `tests/postgres/`(T2·T4·T9 PG 필수).
- **동시 세션**: `order_date_sync.py`·`push_sender.py` 편집 금지(출고 알림 플랜
  소유). commit 전 reflog 확인.
- 커밋 워크스트림 단위, 한글 `git commit -F`, push는 deploy만.

## 6. 범위 밖

- 금액 변경의 화면 알림/배너(라벨 등록까지가 v1 — 무필터 소비자 노출은 §4 T2 수용).
- payment_sync ↔ date_sync 통합 리팩터(출고 알림 플랜 완료 후 별건).
- 대량 export AccessLog 통합, 인바운드 X-Request-ID 승계, OTel/JSON 로그,
  기존 security_logs 백필, EXTERNAL 전량 0화, dedupe Redis 승격, 로컬 스토리지 계측.
- production 승격(사용자 별도 지시).

## 7. 검증 기준

- `APP_OK` + `pre_push_smoke.ps1` exit 0 + `tests/postgres` 전수.
- T1: 유효 레벨·핸들러 필터·중복 초기화 no-op + 모듈 로거 비밀 문자열 마스킹 +
  request_id(요청 내/밖/서드파티 무사고) + `test_run_startup_logging` 개정 green.
- T2: 라우트 매트릭스(전체저장·인라인 PATCH·빠른수정·레거시 폼·결제토글) 각 1건 emit,
  no-op 0·왕복 0·draft 0·`SHIPPING_FEE_CHANGED` 경로 중복 0 + 라벨 렌더 확인.
- T3: draft 생성→자동저장 N회→승격 = DRAFT 1 + CREATED 1.
- T4: 마이그레이션 왕복 + 전역 필터 + raw SQL 2곳 카운트 정합 + canonical 분기
  tombstone 403 + outbox 등록·복구 + 유령 첨부 회귀(시공 카드·도면 뷰어).
- T5: from/to·비번 값 부재·403 연타 60초 1건+카운트 + rollback 주입 후 감사 행 잔존.
- T6: view 302·download 각 AccessLog 행(IP·UA) + dedupe + 실패 주입 시 응답 정상 +
  독립 engine 미가용 시 fail-open 로그.
- T8/T9: 마이그레이션 왕복(고아 downgrade는 PG 실패 확인 수준) + purge dry-run
  카운트 + hard purge 후 order_events 잔존 + runner DDL 재생성 시 FK 부재.
- T10: DSN 무설정 no-op + event dict 마스킹 + 스테이징 고의 예외 수신.
- 통합: 스테이징 Railway 로그 INFO+request_id 실출력(X-Request-ID 대조).

## 8. 확정된 결정 (사용자 승인 완료)

| # | 결정 | 확정 |
|---|---|---|
| ① | 금액 이벤트 | 단일 `PAYMENT_CHANGED`+field payload |
| ② | draft 생성 | `ORDER_DRAFT_CREATED` 별도 타입 |
| ③ | 파일 view 기록 | dedupe 창 10분 |
| ④ | order_events FK | drop + models·runner DDL 동기 수정 |
| ⑤ | 사용자 삭제 | 비활성화 전환 + 감사 actor 보존 |

## 9. 설계 리뷰 이력 (2026-08-05)

1. **1차 리뷰**: 사실 대조 18건(17 정확·1 수정), 적대 리뷰 C2·M6·m7 반영.
2. **`**D` CEO 리뷰(HOLD SCOPE) + 3-agent 교차검수**(반증·단순화·사실검증):
   - [실증·CRITICAL] `flag_modified`의 old 파괴 → T2 before를 `get_history`에서
     **DB 배치 SELECT**로 전면 교체(주 세션 재검증 완료).
   - [CRITICAL] 독립 모드 제2 커넥션 풀 고갈 → 전용 소형 감사 engine(pool 2·
     timeout 0.5s)으로 교체.
   - [MAJOR] 첨부 raw SQL 2곳·canonical 분기 tombstone 사각 → T4 절차 편입.
   - [MAJOR] 동시 세션(출고 알림 T6)과 `order_date_sync.py` 충돌 → T2 무접촉 복제.
   - [단순화] 구 T7을 T1에 흡수, T9 Alembic 편입·고아 차단 의식 삭제, cron 체이닝,
     T5 헬퍼 함수 1개(engine.begin 선례), 결제토글 라우트 편집 0줄, T6 log_access
     수정 이연(T8).
   - [사실] shipping_fee 기존 이벤트 발견(캡처 제외), balance_note 추가, 레거시
     payments 폴백 = extractor 재사용, 무필터 소비자 6곳 노출 수용 결정.
