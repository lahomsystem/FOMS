# 실행 플랜 — 시스템 전체 감사 로깅 (2026-08-05, `**D`)

스펙: `docs/specs/2026-08-05-system-audit-logging-design.md` (2차 개정판)
원장: `docs/plans/2026-08-05-system-audit-logging-ledger.md`
브랜치: `deploy` (push는 세션 커밋만, production 승격은 사용자 별도 지시)

공통: 각 task = 구현(위임) → 검증(완료 기준) → 한글 커밋(`git commit -F`) → 원장 갱신.
`.py` 편집 후 `APP_OK`. 인벤토리 게이트는 원격 tip 클린 worktree 재생성.
테스트 위치: 도메인 `tests/domains/`, DB 왕복 `tests/postgres/`.
**동시 세션 금지 파일**: `order_date_sync.py`·`push_sender.py`(출고 알림 플랜 소유).
commit 전 reflog 확인(타 세션 레이스).

---

## Phase 1 — P0

### T1 프로덕션 로깅 부트스트랩 (+ request_id, 구 T7 흡수) — **파일럿**
- 파일: `foms/platform/logging_setup.py`(신설) · `foms/platform/app_factory.py` ·
  `foms/services/common/dashboard_cache.py`(국소 패치 제거) · `run.py`(basicConfig
  제거·`FOMS_STARTUP_LOG_PATH` 흡수) · `tests/domains/test_run_startup_logging.py`(개정)
- 절차: 멱등 `configure_logging()` — root INFO + StreamHandler(**stderr**) + 포맷
  (`[%(request_id)s]` 토큰). **핸들러에** RedactionFilter + request_id Filter 부착
  (Filter는 항상 속성 주입, 요청 밖 `-`). pytest·alembic·tools/ 재초기화 no-op.
- **완료 기준**: 신규 계약 테스트(유효 레벨 INFO·핸들러 필터 2종 부착·중복 초기화
  no-op·모듈 로거 비밀 문자열 → 출력 마스킹·request_id 요청 내/밖/서드파티 무사고) +
  `test_run_startup_logging` 개정 green + 로컬 기동 INFO 육안 + `APP_OK`.

### T2 `PAYMENT_CHANGED` before_flush SSOT
- 파일: `foms/services/order_payment_sync.py`(신설 — date_sync 가드 **복제**, 무접촉) ·
  `foms/services/app_init.py`(등록 2줄) · `foms/services/order_event_display.py`(라벨) ·
  테스트(domains + postgres)
- 절차: before_flush에서 payment-diff 대상 dirty Order id 수집 →
  `session.connection()` 배치 1회 SELECT로 flush 전 committed payment 확보(
  `get_history` 금지 — flag_modified가 old 파괴, 스펙 §2 실증) → `session.info`
  origin 캐시 → diff·emit. 캡처: deposit·discount·free_input(원문+파싱 합계)·
  cash_receipt·balance_note·확인 토글 2종. old/new는 기존 extractor 재사용
  (`payments` 레거시 폴백 자동). **shipping_fee·totals 제외.** draft(`meta.draft`) 억제.
  결제토글 라우트 편집 0줄.
- **완료 기준**: 라우트 매트릭스(전체저장·인라인 PATCH·빠른수정·레거시 폼·결제토글)
  각 1건 emit + no-op 0·왕복 취소 0·draft 0·admin shipping_fee 경로 PAYMENT_CHANGED
  0(기존 SHIPPING_FEE_CHANGED만) + 라벨 "금액 변경" 렌더. `tests/postgres` green.

### T3 ERP 생성 `ORDER_CREATED` 배선
- 파일: `foms/api/erp_orders_structured.py`(`:530`·`:1155`·`:1303`)
- **완료 기준**: draft 생성→자동저장 N회→승격 = `ORDER_DRAFT_CREATED` 1 +
  `ORDER_CREATED` 1(자동저장 0) 계약 테스트 + 타임라인 라벨.

### T-CP1 Phase 1 검증·커밋·푸시
- **완료 기준**: `pre_push_smoke` exit 0 → deploy push → `gh run list` 전 워크플로
  green → 스테이징 Railway 로그 `req_duration`·`foms_rum` INFO + request_id 실출력.

## Phase 2 — P1

### T4 첨부 수명주기 (soft delete + 이벤트)
- 파일: `models.py`(컬럼+전역 필터) · 마이그레이션(downgrade) ·
  `foms/api/files/order_routes.py` · `direct_upload.py` ·
  `foms/api/files/routes.py`(**canonical 분기 storage_key tombstone lookup**) ·
  `foms/services/construction_read_model.py:134`·`production_read_model.py:207`
  (**raw SQL `AND deleted_at IS NULL`**) · lint 게이트(`FROM order_attachments` raw 검출) ·
  휴지통/복구 opt-in
- 절차: tombstone 컬럼 → `with_loader_criteria` 전역 필터 → 삭제 API tombstone +
  `ATTACHMENT_DELETED` 이벤트 id로 STORAGE_DELETE outbox(`source_domain="ORDER_EVENT"`,
  thumbnail_key 포함) → R2 즉시삭제 제거 → ADDED/META_UPDATED emit.
  `delete_retention.py` raw는 치환 금지.
- **완료 기준**: 마이그레이션 왕복 + 전역 필터 제외·row 잔존·outbox·복구 + raw SQL
  2곳 카운트 정합 + canonical 분기 삭제 첨부 403 + 유령 첨부 회귀(시공 카드·도면
  뷰어·대시보드) green.

### T5 관리자 행위 구조화 + 접근거부 기록
- 파일: `foms/web/auth/routes.py` · `order_mutation_policy.py` ·
  `request_write_guard.py` · **공유 독립 감사 헬퍼(신설: 전용 소형 engine pool 2·
  overflow 0·timeout 0.5s + `engine.begin()` Core INSERT 함수 1개 — T6 공유)**
- 절차: field별 from→to, 비번 재설정 별도 기록(값 미기록), `/register` 기록,
  `log_access` print→logger. 403/CSRF SecurityLog 독립 모드. dedupe
  (user_id or IP, endpoint) 60초 + 카운트 + 캐시 상한/GC.
- **완료 기준**: from/to 포함·비번 값 부재(부정)·403 연타 60초 1건+카운트 +
  rollback 주입 후 감사 행 잔존 + 감사 engine 미가용 주입 시 요청 정상(fail-open 로그).

### T6 `access_logs` 부활 (파일 접근)
- 파일: `foms/api/files/routes.py`(view `:133`·presigned `:170`·download `:215`
  **3곳 핀** — `get_download_url` 메서드 내부 계측 금지) · 인덱스 마이그레이션 ·
  T5 공유 헬퍼 재사용
- 절차: 3곳에서 AccessLog(IP·UA·additional_data) — view는 (user, file_key) 10분
  dedupe. 로컬 `send_file` 경로 미계측(한계 명시). 조회 화면 없음 — SQL 전용.
- **완료 기준**: view 302·download 각 행 생성 + dedupe + 실패 주입 시 파일 응답
  정상 계약 테스트.

### T-CP2 Phase 2 검증·커밋·푸시
- **완료 기준**: T-CP1 절차 + 스테이징 실브라우저(파일 다운로드 → AccessLog 행,
  X-Request-ID ↔ 로그 대조).

## Phase 3 — P2

### T8 `security_logs` 구조화
- 파일: `models.py` · 마이그레이션 · `log_access` 확장(additional_data → detail 격납) ·
  우선 호출부 · `web/admin/audit.py`+템플릿(**`?v=` 범프**)
- **완료 기준**: 마이그레이션 왕복 + 구조화 저장 + 미전달 호출부 하위호환 +
  audit 필터 스테이징 확인.

### T9 감사 원장 수명주기
- 파일: FK drop 마이그레이션 1건(`DROP CONSTRAINT IF EXISTS`, downgrade는 고아 시
  PG 자체 실패 — 사전 카운트 안내만) · `models.py:775,783`(FK 제거 + relationship
  primaryjoin/foreign()) · **`scripts/ops/erp_build_step_runner.py:329`**(raw DDL
  CASCADE 제거) · `tools/ops/purge_audit_logs.py`(신설) ·
  `apply_delete_retention.py`(이벤트 보존 확인) ·
  **기존 receipt-purge cron toml에 `&&` 체이닝**(신설 금지)
- **완료 기준**: 마이그레이션 왕복 + hard purge 후 order_events 잔존 + purge
  dry-run 카운트 + runner DDL 재생성 시 FK 부재 + FK drop 후 조인 EXPLAIN +
  `tests/postgres` 전수.

### T10 Sentry + gunicorn access log
- 파일: `requirements.txt` · `app_factory.py`(env-gated) · before_send 재귀 마스킹
  워커(신설) · `Procfile`/`start.sh`(`--access-logfile -`)
- **사용자 액션**: Sentry 프로젝트·DSN·Railway env(착수 시 안내 후 대기).
- **완료 기준**: DSN 무설정 no-op + event dict 마스킹 계약 + 스테이징 고의 예외
  수신·PII 부재 + access log 출력.

### T11 잔여 구멍 수리
- 파일: `user_deletion.py`(`:28-40` 11필드 재분류, Chat `:42-46` 유지) ·
  `failopen_scan.py`+인벤토리·테스트(`SWALLOW_BY_CONTROL_FLOW`·179 무성장) ·
  EXTERNAL CS/도면 경로 CANONICAL 전환
- **완료 기준**: 삭제 후 감사 actor 보존 + 신규 disposition 게이트 green +
  EXTERNAL 감축(인벤토리 재생성).

### T-CP3 최종 검증
- **완료 기준**: `verify_result.py --json` + smoke exit 0 + 전 워크플로 green +
  `docs/AI_STATUS.md` 갱신 + 원장 전 task DONE. production 승격 안 함.
