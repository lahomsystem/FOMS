# 시스템 전체 감사 로깅 (설계 스펙)

- 작성일: 2026-08-05 (동일 자 설계 리뷰 반영 개정 — §9)
- 등급: `**C`
- 상태: **승인 대기**
- 확정된 사용자 결정: ① 범위 = **P0·P1·P2 전 항목(11개 워크스트림)** ② 방식 = **설계 승인 후 구현**

## 1. 문제

ERP인데 "누가 언제 무엇을 바꿨나"에 답할 수 없는 3중 공백이 있다.

1. **프로덕션 앱 로깅 설정이 없다.** `basicConfig`는 `run.py`(로컬 dev)에만 있고
   gunicorn 경로(`app.py` → `foms/platform/app_factory.py`)에는 0건 — root=WARNING +
   핸들러 없음이라 INFO 전량 소실. 느린 요청 로그(`http.py:295`)·RUM 집계
   (`foms_rum.py:171`)가 운영에서 죽어 있고, `dashboard_cache.py:24`가 이 문제를
   주석으로 진단한 채 파일 하나만 국소 우회 중이다.
2. **DB 감사의 실체가 자유 텍스트 1컬럼이다.** `security_logs.message` — 대상 ID·필드·
   old/new 구조화 없음, 조회는 ILIKE뿐(`web/admin/audit.py:30`). `access_logs`는
   writer 0건 사문 테이블. `order_events`의 old→new 캡처는 화이트리스트 5종뿐.
3. **돈·파일·주문생성이 무음이다.** 금액 변경(예약금·할인·자유입력) 이력 0 — 실사고
   기발생(주문 4414 할인 11,060원 소실, 로그 부재로 산술 역추론으로만 증명,
   `docs/plans/2026-07-31-full-promotion-prep-ledger.md:385`). 첨부 hard delete 무기록,
   ERP 주력 생성 경로 `ORDER_CREATED` 없음, R2 presigned 발급 무기록.

## 2. 조사 확정 사실 (2026-08-05 deep research + 사실 대조 검증 완료 — 재조사 금지)

- `log_access()`(`foms/web/auth/routes.py:48`, 시그니처에 `auto_commit=True`)는 이름과
  달리 **SecurityLog**에 쓰고, `additional_data` 파라미터는 본문에서 버려진다.
  실패 시 `print()` 삼킴(`:56`).
- `_record_structured_events`(`foms/api/erp_orders_structured.py:392`)는
  urgent·실측일·owner_team 3종만 diff. payment 블록은 아예 안 본다.
  결제확인 토글(`:1082-1148`)은 현재 상태 덮어쓰기만, OrderEvent 0.
- **payment 실키**: `structured_data.payment` = deposit·discount·free_input(자유 텍스트
  "배송비 : 30,000" 형식)·cash_receipt·확인 토글류 13키. **출고가는 payment 키가 아니라
  `totals.shipping_price` 파생값**(`structured_form_projection.py:160`, 매 저장 시
  `totals` pop 후 전량 재계산 `:132`). **`Order.shipping_fee`는 structured_data 밖
  flat 컬럼**(`models.py:69`, writer는 `web/admin/storage.py:202`).
- ERP draft 생성(`erp_orders_structured.py:1155,1189`, `:1303`)과 승격
  (`_finalize_draft_state:530`)은 `create_order()` 미경유 — 이벤트·SecurityLog 0.
  `templates/orders/add_order.html:775`가 이 엔드포인트 고정.
  **선례**: 마법사 경로 `foms/api/erp_order_draft.py:510`은 이미 `create_order()` 경유.
- 첨부 삭제(`foms/api/files/order_routes.py:298`)는 `db.delete` + R2 즉시삭제,
  R2 실패는 `print()`(`:296`). `OrderAttachment`에 tombstone 컬럼 없음
  (`models.py:239-280`), 사용처 **84파일·428회**. `ATTACHMENT_ADDED/DELETED` 라벨은
  `order_event_display.py:172-173`에 정의만, emit 0. 정답 패턴은
  `blueprint_projection.py`(이벤트 + `domain_side_effect_outbox`, one-of FK
  `source_domain="ORDER_EVENT"` — `models.py:2310` CHECK).
- 파일 라우트(`foms/api/files/routes.py`) view(:118)·presigned(:155)·download(:195)
  전부 무기록. **presigned 라우트는 프론트 계약 테스트가 사용 금지**
  (`tests/domains/test_file_url_lifecycle.py:76-79`) — 사실상 사문. 실제 열람은
  `/view/`가 내부에서 presigned 발급 후 302(`:133-136`).
- **파일 GET 라우트·before_request abort 경로에는 commit이 없다** — teardown
  `close_db`(`db.py:99-102`)는 close만(암묵 rollback). 감사 행을 본 트랜잭션에만
  태우면 이 경로에서 전량 소실된다.
- 관리자 수정(`auth/routes.py:533`)은 "사용자 #N 정보 수정" 한 줄 — from/to 없음.
  타인 비번 재설정(`:505-515`)·최초 관리자 등록(`:294-347`) 무기록.
  API 403(`order_mutation_policy.py:446`)·CSRF 차단(`request_write_guard.py:77`)은 logger만.
- `request_id`는 발급·헤더·에러 페이로드까지 있으나 로그 라인 주입 없음
  (`http.py:206,277,309`).
- **`install_protected_logging`(`error_logging.py:96`)은 RedactionFilter를 root
  "로거"에 단다** — Python logging 의미론상 로거 필터는 자식 로거에서 전파된
  레코드에 적용되지 않는다. 지금은 root 핸들러가 없어 잠복 중이나, root 핸들러를
  켜는 순간 모듈 로거 레코드가 마스킹 없이 방류된다. **필터는 핸들러에 달아야 한다.**
- retention: `security_logs`·`order_events`·`notification_events`·`channel_delivery_logs`
  전부 purge 잡 0(기존 잡 3종은 전부 다른 테이블). `order_events`는
  `ForeignKey('orders.id', ondelete='CASCADE')`(`models.py:775`)로 주문 purge 시 동반
  소멸 + Alembic 미편입(`erp_build_step_runner.py:327` raw DDL + `create_all`) +
  단독 인덱스 3개.
- `user_deletion.py:29-40`이 SecurityLog·OrderEvent·AccessLog·OrderAttachment 등의
  actor를 일괄 NULL — "누가" 사후 소거.
- FAILOPEN-01: `LOG_AND_CONTINUE` 445건 중 `has_logging=False` **179건** 게이트 green 통과.
- mutation writer `EXTERNAL` 22곳 baseline 핀.
- 복제 패턴: `order_date_sync.py` before_flush SSOT(등록은
  `register_date_sync_listener()`, 호출은 `app_init.py:180-182` — "pure listener
  wiring, no DB write" 계약). 단 date는 물질화된 `schedule_dates` 행에서 before를
  얻는다 — **payment는 그런 projection 테이블이 없어 before 출처가 다르다**(§4 T2).

## 3. 설계 원칙

1. **이력 매체는 기존 결정 유지**: `OrderEvent` + `structured_data`(알림톡 플랜 명문화).
   신규 로그 테이블 신설 없음 — 유일한 예외는 **사문 `access_logs` 부활**(기존 테이블 재사용).
2. **무음 경로 봉합은 라우트별 emit이 아니라 SSOT/chokepoint** — 쓰기는 before_flush,
   파일 접근은 presigned 발급 지점.
3. **감사 쓰기 2모드** (리뷰 C1 반영):
   - **동승 모드**: mutation 라우트 — 본 트랜잭션 내 insert, 별도 커밋 금지
     (비즈니스 rollback 시 감사도 함께 사라지는 게 정합).
   - **독립 모드**: GET·abort(403/CSRF)·teardown 경로 — 커밋이 없는 경로이므로
     **전용 단명 세션**으로 즉시 커밋. `log_access(auto_commit=...)`를 이 구분에 맞게
     정비. 진행 중 비즈니스 트랜잭션을 중간 커밋으로 clobber하는 것 금지.
4. 감사 쓰기 실패는 본 요청을 죽이지 않는다(로그 동반 fail-open, AGENTS.md 준수).
5. **PII 마스킹**: 고객 전화·주소 로그 원문 금지(`010****6730`). 마스킹 필터는
   **핸들러 레벨** 부착(리뷰 C2).
6. **성능**: hot path 추가 쿼리 배치 1회, before_flush diff는 dirty Order만.
   대시보드/리스트 TTFB 예산 불변(상향 금지).

## 4. 워크스트림 설계

### Phase 1 — P0

#### T1 프로덕션 로깅 부트스트랩
- `foms/platform/logging_setup.py` 신설: 멱등 `configure_logging()` — root **INFO** +
  **`StreamHandler(stderr)`**(stdout은 하네스 JSON·pytest 캡처 오염 — 리뷰 m1) + 포맷.
- **필터는 핸들러에 부착**: RedactionFilter + request_id Filter(T7)를 새 핸들러에 단다.
  로거 레벨 `install_protected_logging`은 유지(직접 기록 경로 방어)하되 커버리지
  전제로 삼지 않는다.
- **`run.py`의 `basicConfig(force=True)` 제거** — `configure_logging()` 단일 SSOT
  (리뷰 m2. 가드 방식이면 dev에서 새 포맷 영원히 미적용). `FOMS_STARTUP_LOG_PATH`
  opt-in 파일 핸들러는 configure_logging으로 흡수.
- `dashboard_cache.py:24-42` 국소 우회 제거. pytest·alembic·tools/ 스크립트에서
  재초기화 no-op 확인.
- 효과 검증: 스테이징 Railway 로그에 `req_duration`·`foms_rum` INFO 실출력.

#### T2 금액 변경 이벤트 `PAYMENT_CHANGED` (SSOT)
- `order_payment_sync.py` 신설, `app_init.py`의 date_sync 등록 지점 옆에 리스너 등록.
- **캡처 목록(사실 검증 반영)**: `payment.deposit`(예약금) · `payment.discount`(할인) ·
  `payment.free_input`(자유 텍스트 — 원문 diff + 파싱 합계 병기) ·
  `payment.cash_receipt` · `payment.deposit_confirmed`/`balance_confirmed` 토글 ·
  **`Order.shipping_fee` flat 컬럼**(structured_data 밖 — 별도 attribute diff).
  **출고가(`totals.shipping_price`)는 독립 diff 대상에서 제외**(매 저장 재계산되는
  파생값 — 잡으면 중복 이벤트), payload 참고값으로만 병기.
- **before 값 출처(리뷰 M1)**: `get_history(order, 'structured_data')`의 old 스냅샷.
  이는 **writer가 재할당 패턴(deepcopy → 수정 → 재할당 + flag_modified)을 지킬 때만**
  old가 남는다 — 프로젝트 CLAUDE.md 필수 패턴이므로 계약으로 명문화하고,
  in-place 수정·`query().update()`·raw SQL 우회는 **부정 계약 테스트**로 고정
  (잡히면 해당 writer를 재할당 패턴으로 수정).
- payload: `{"field": "discount", "from": 11060, "to": 0, "source": "<endpoint>"}` —
  단일 타입 + field 구분(결정 ①). 정규화(숫자화·None/미존재 동일시), origin 기억·
  복귀 취소·재진입 가드는 date_sync 코드 재사용.
- **draft 억제(리뷰 M6)**: `meta.draft` 상태 주문은 payment 이벤트 억제 — 자동저장
  최초 입력(None→값) 노이즈 차단. 승격 시점 값이 초기값.
- 소비자(화면 알림)는 범위 밖 — 이벤트 기록까지가 v1.

#### T3 ERP 생성 경로 `ORDER_CREATED` 배선
- `_finalize_draft_state`에서 `ORDER_CREATED` emit(payload `via: "erp_draft"`, actor).
  draft 최초 생성은 `ORDER_DRAFT_CREATED`(결정 ②).
- `create_order()` 경유 리팩터는 하지 않는다(경로 차이 회귀 위험 — 마법사
  `erp_order_draft.py:510` 선례는 참고만, 이식 범위가 다르다). 직접 emit이 국소적.

### Phase 2 — P1

#### T4 첨부 수명주기: 이벤트 + soft delete 전환
- `OrderAttachment`에 `deleted_at`/`deleted_by_user_id` 추가(마이그레이션, downgrade 포함).
- **조회 필터는 전역 기본값(리뷰 M3)**: 사용처 84파일·428회 — 호출부별 수동 필터는
  deny-list 회귀 선례의 재생산. `with_loader_criteria` 전역 리스너(또는 공용
  `active_attachments()` 헬퍼 + 사용처 lint 게이트)로 기본 제외, 휴지통/복구 화면만
  명시 opt-in.
- 삭제 API: tombstone + `ATTACHMENT_DELETED` OrderEvent → 그 이벤트 id를
  `source_domain="ORDER_EVENT"`로 `STORAGE_DELETE` outbox 등록(one-of CHECK 준수,
  신규 domain 추가 금지 — 리뷰 m4). payload에 `thumbnail_key` 포함. R2 즉시삭제 제거.
- `_deny_file_access`(`files/routes.py:79-88`): tombstone 행은 **접근 차단**(복구는
  DB 행 기준이라 파일 접근 불필요 — outbox 유예 내 복구 시 재개).
- `ATTACHMENT_ADDED`/`META_UPDATED` emit: `order_routes.py:88-191` + `direct_upload.py:161`.

#### T5 관리자 행위 구조화 + 접근거부 DB 기록
- 사용자 수정: role/team/is_active/username field별 from→to 명시(메시지 문자열,
  T8에서 컬럼 승격). 타인 비번 재설정 별도 기록(값 절대 미기록). `/register` 기록.
  `log_access` 실패 print → logger.
- API 403·CSRF/Origin 차단 SecurityLog — **독립 모드 세션**(§3-3, abort 경로 무커밋).
- 폭주 방어: (user_id or IP, endpoint) 60초 dedupe + 억제 반복 횟수 카운트 기록 +
  캐시 상한/GC. **프로세스당 캐시라 4프로세스 환경에서 감쇠 1/4**(리뷰 m3) —
  v1 한계로 명시 수용, Redis 승격은 범위 밖.

#### T6 파일 접근 기록 — `access_logs` 부활 (chokepoint 방식)
- **계측 지점은 라우트가 아니라 R2 presigned 발급 chokepoint**(리뷰 M4 — presigned
  라우트는 계약 테스트가 사용 금지한 사문 경로, 실제 열람은 `/view/` 302).
  `get_download_url` 호출부(view·download·presigned 공통)에서 기록.
- `view` 폭주 제어: (user, file_key) 단위 시간창 dedupe(예: 10분) — 인라인 이미지
  반복 로드가 테이블을 폭주시키지 않게. 결정 ③은 "view 기록 여부"에서
  "**dedupe 창 크기**"로 재정의.
- 기존 컬럼 그대로 + `additional_data` 실제 저장(`log_access` 결함 수정), IP·UA 기록.
- **독립 모드 세션**(GET 경로 무커밋 — §3-3). 실패 시 파일 응답 정상(fail-open 로그).
- 인덱스 마이그레이션: `(user_id, timestamp)` + `(timestamp)`.
- 대량 export(엑셀·지역 출고)는 이미 SecurityLog 기록 있음 — AccessLog 통합은 범위 밖.

#### T7 request_id 로그 주입
- `logging.Filter`를 **T1 핸들러에 부착** — `g.request_id` 없으면 `-`. 서드파티
  레코드에 속성 미존재로 포맷 실패하지 않게 필터가 항상 속성 주입(방어적 setattr).
- 인바운드 `X-Request-ID` 승계는 범위 밖.

### Phase 3 — P2

#### T8 `security_logs` 구조화
- 컬럼 추가: `action`·`target_type`·`target_id`·`detail`(JSONB, old/new).
  `message`는 사람용 요약 유지(기존 행 백필 없음).
- `log_access()` 확장 + 관리자·권한·금액 호출부 우선 전달. admin audit UI
  action/target 필터(**템플릿/JS 변경 시 `?v=` 범프** — SW staticCacheFirst).
- trgm 유지, `(target_type, target_id, timestamp)` 인덱스 추가.

#### T9 감사 원장 수명주기 (retention + CASCADE 분리)
- **CASCADE 분리(결정 ④)**: DB FK drop + **models.py도 동기 수정**(ForeignKey 제거 시
  `OrderEvent.order` relationship에 명시 `primaryjoin`/`foreign()` 필요 — create_all
  테스트 레인과 스키마 드리프트 금지, 리뷰 M2). downgrade는 고아 이벤트
  (purge된 주문 참조) 존재 시 **차단**(사전 카운트 후 안내) — 무손실 왕복 불가함을
  명시. hard purge 스크립트에 이벤트 보존 확인 추가.
- `order_events` Alembic 편입: 현 스키마 반영 조건부 마이그레이션(기존 DB=no-op,
  신규 DB=create) + 이후 변경은 정식 체인.
- retention purge 잡(receipt-purge 패턴: advisory lock + keyset 배치, 기본 dry-run):
  `security_logs`(≥2년)·`notification_events`(≥1년)·`channel_delivery_logs`(≥1년)·
  `access_logs`(≥1년). `order_events`는 **purge 제외**. cron 등록은
  `railway-cron-receipt-purge.toml` 복제.

#### T10 외부 관측 — Sentry
- `sentry-sdk[flask]`, DSN은 Railway env(하드코딩 금지), 없으면 완전 no-op.
  `send_default_pii=False`.
- **`before_send`는 RedactionFilter 재사용 불가**(문자열 필터 vs event dict — 리뷰 M5):
  `_REDACTIONS` 패턴 기반 **재귀 dict 마스킹 워커 신설** + 마스킹 계약 테스트.
  logging 통합 브레드크럼도 이 워커를 거친다.
- gunicorn `--access-logfile -`(Procfile·start.sh 양쪽).
- **사용자 액션 필요**: Sentry 프로젝트 생성·DSN 발급·Railway env 등록(T10 착수 시 안내).

#### T11 잔여 구멍 수리
- `user_deletion.py`: actor NULL 소거 중단 — **사용자 hard delete API의 의미가
  "삭제→비활성화(익명화 표기)"로 바뀐다. 결정 ⑤로 승인 필요**(리뷰 m7).
  NULL 대상 리스트(`:29-47`) 전수 재분류: 감사 보존(SecurityLog·OrderEvent·AccessLog·
  OrderAttachment) vs 실삭제 유지(Chat 3종) 명시.
- FAILOPEN 게이트: `LOG_AND_CONTINUE`+`has_logging=False`를 `SWALLOW_BY_CONTROL_FLOW`
  disposition으로 분리, baseline 179건 무성장(감소만 허용).
- `EXTERNAL` writer 22곳 중 CS/도면 경로 우선 CANONICAL 전환(전량 0은 별도 플랜).

## 5. 성능·정책 제약 (설계 구속)

- before_flush diff는 `session.dirty` 중 Order만, dict 수준 접근(추가 쿼리 0).
  `Order.shipping_fee`는 attribute history로 별도 감지.
- 감사 쓰기 모드는 §3-3의 2모드 구분을 따른다 — GET/abort 경로에서 본 세션
  중간 커밋 금지, mutation 경로에서 별도 세션 남발 금지.
- 대시보드/리스트 TTFB 예산 불변. 신규 인덱스는 마이그레이션 + `EXPLAIN` 확인.
- 인벤토리 게이트 5종은 편집 후 **원격 tip 클린 worktree에서 재생성**(라인시프트
  함정, 수기 병합 금지).
- 계약 테스트 위치: 도메인 로직 = `tests/domains/`, DB 왕복·트리거 = `tests/postgres/`
  (T2·T4·T9는 PG 레인 필수).
- 커밋은 워크스트림 단위 분리, 한글 메시지 `git commit -F`, push는 deploy만.

## 6. 범위 밖

- 금액 변경의 화면 알림/배너(이벤트 기록까지가 v1).
- 대량 export의 AccessLog 통합(기존 SecurityLog 기록 유지).
- 인바운드 `X-Request-ID` 승계, OpenTelemetry/구조화 JSON 로그 전환.
- 기존 `security_logs` 행 백필, `EXTERNAL` writer 전량 0화, dedupe 캐시 Redis 승격.
- production 승격(스테이징 검증까지, 승격은 사용자 별도 지시).

## 7. 검증 기준

- `python -c "import app; print('APP_OK')"` + `pre_push_smoke.ps1` exit 0 + `tests/postgres` 전수.
- T1: 로거 유효 레벨·핸들러 필터 부착·중복 초기화 no-op 계약 테스트 +
  **마스킹 테스트(모듈 로거로 비밀 문자열 기록 → 핸들러 출력에서 마스킹 확인)**.
- T2: 실 라우트별(전체저장·인라인 PATCH·빠른수정·레거시 폼·admin shipping_fee) 1건씩
  emit, no-op 0건, 왕복 0건, draft 0건 + **부정 테스트(in-place 수정·bulk update 우회
  탐지)**.
- T3: draft 생성→자동저장 N회→승격에서 DRAFT 1건 + CREATED 1건.
- T4: 마이그레이션 왕복 + 삭제 후 전역 필터로 목록 제외·row 잔존·outbox 등록·복구 +
  유령 첨부 회귀(시공 카드·도면 뷰어).
- T5: from/to 포함, 비번 값 부재(부정), 403 연타 60초 1건+카운트, **rollback 경로에서
  감사 행 잔존**(독립 모드 검증).
- T6: view 302·download 각각 AccessLog 행(IP·UA·additional_data), dedupe 창 동작,
  기록 실패 주입 시 파일 응답 정상.
- T7: 요청 내 request_id·밖 `-`·속성 없는 서드파티 레코드 무사고.
- T8/T9: 마이그레이션 왕복(T9는 고아 시 downgrade 차단 확인) + purge dry-run 카운트 +
  hard purge 후 order_events 잔존.
- T10: DSN 무설정 no-op + 스테이징 고의 예외 1건 수신 + event dict 마스킹 계약 테스트.
- T1/T7 통합: 스테이징 Railway 로그 INFO+request_id 실출력(실브라우저 1회,
  X-Request-ID 헤더 ↔ 로그 대조).

## 8. 승인 시 확정할 결정

| # | 결정 | 권장 |
|---|---|---|
| ① | 금액 이벤트: 단일 `PAYMENT_CHANGED`+field payload vs 필드별 타입 | **단일 타입** |
| ② | draft 최초 생성: `ORDER_DRAFT_CREATED` 별도 vs 승격 시 1건만 | **별도 타입** |
| ③ | 파일 view 기록 dedupe 창 크기 | **10분**(폭주 방지·감사 가치 균형) |
| ④ | `order_events` FK: drop+plain 컬럼 vs 유지+purge 시 아카이브 이동 | **FK drop** (models 동기 수정 포함) |
| ⑤ | 사용자 삭제 의미 변경: hard delete → 비활성화+감사 actor 보존 | **변경** (감사 무결성 우선) |

## 9. 설계 리뷰 이력 (2026-08-05)

- 사실 대조: 18개 주장 중 17개 정확, 1개 수정(T2 payment 키 목록 — §2·T2 반영).
- 적대 리뷰 CRITICAL 2(GET 경로 감사 소실·root 로거 필터 무효) — §3-3 2모드·핸들러
  부착으로 반영. MAJOR 6(before 출처·FK 왕복·필터 전역화·chokepoint·Sentry 워커·
  draft 노이즈) 전부 본문 반영. 리뷰어 지적 중 핵심 4건(무커밋 teardown·totals 파생·
  shipping_fee flat·root 로거 필터)은 코드 직독으로 재확인함.
