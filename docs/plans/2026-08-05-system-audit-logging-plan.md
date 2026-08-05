# 실행 플랜 — 시스템 전체 감사 로깅 (2026-08-05, `**C`)

스펙: `docs/specs/2026-08-05-system-audit-logging-design.md` (리뷰 반영 개정판)
원장: `docs/plans/2026-08-05-system-audit-logging-ledger.md`
브랜치: `deploy` (push는 세션 커밋만, production 승격은 사용자 별도 지시)

공통 규칙: 각 task = 구현 → 검증(완료 기준) → 한글 커밋(`git commit -F`) → 원장 갱신.
`.py` 편집 후 `APP_OK`. 인벤토리 게이트 걸리면 원격 tip 클린 worktree 재생성.
테스트 위치: 도메인 = `tests/domains/`, DB 왕복 = `tests/postgres/`.

---

## Phase 1 — P0

### T1 프로덕션 로깅 부트스트랩
- 파일: `foms/platform/logging_setup.py`(신설) · `foms/platform/app_factory.py` ·
  `foms/services/common/dashboard_cache.py`(국소 패치 제거) · `run.py`(**basicConfig
  제거** — configure_logging 단일 SSOT, `FOMS_STARTUP_LOG_PATH` 흡수)
- 절차: 멱등 `configure_logging()` — root INFO + **StreamHandler(stderr)** + 포맷.
  **RedactionFilter + request_id Filter를 핸들러에 부착**(로거 부착은 전파 레코드에
  무효 — 스펙 §2). pytest·alembic·tools/ 재초기화 no-op.
- **완료 기준**: 계약 테스트(유효 레벨 INFO·핸들러 필터 부착·중복 초기화 no-op·
  모듈 로거 비밀 문자열 → 핸들러 출력 마스킹) green + 로컬 기동 INFO 확인 + `APP_OK`.

### T2 `PAYMENT_CHANGED` before_flush SSOT
- 파일: `foms/services/order_payment_sync.py`(신설, date_sync 동형) ·
  `foms/services/app_init.py`(리스너 등록 — `:180-182` date_sync 옆) ·
  `foms/api/erp_orders_structured.py`(결제확인 토글 이력 보강)
- 캡처: `payment.deposit`·`discount`·`free_input`(원문+파싱 합계)·`cash_receipt`·
  확인 토글 2종 + **`Order.shipping_fee` flat 컬럼**(attribute history).
  `totals.shipping_price`는 파생 참고값만(독립 diff 금지 — 매 저장 재계산).
- before 출처: `get_history(order, 'structured_data')` old 스냅샷 — 재할당 패턴 계약.
  origin 기억·복귀 취소·재진입 가드 date_sync 재사용. **`meta.draft` 주문 억제**.
- **완료 기준**: 계약 테스트 — 전체저장/인라인 PATCH/빠른수정/레거시 폼/admin
  shipping_fee 각 1건, no-op 0·왕복 0·draft 0 + **부정 테스트(in-place·bulk update
  우회 탐지)**. `tests/postgres` green.

### T3 ERP 생성 `ORDER_CREATED` 배선
- 파일: `foms/api/erp_orders_structured.py`(`_finalize_draft_state:530`·draft
  POST`:1155`·`_create_session_draft:1303`)
- 절차: 승격 시 `ORDER_CREATED`(payload `via`, actor), 생성 시 `ORDER_DRAFT_CREATED`.
  `create_order()` 리팩터 금지(마법사 선례 `erp_order_draft.py:510`는 참고만).
- **완료 기준**: draft 생성→자동저장 N회→승격에서 DRAFT 1건 + CREATED 1건(자동저장
  0건) 계약 테스트 + 타임라인 라벨 확인.

### T-CP1 Phase 1 검증·커밋
- **완료 기준**: `pre_push_smoke` exit 0 → deploy push → `gh run list` 해당 커밋
  전 워크플로 green(ci_watch 단독 판정 금지) → 스테이징 Railway 로그
  `req_duration`·`foms_rum` INFO 실출력 눈 확인.

## Phase 2 — P1

### T4 첨부 수명주기 (soft delete + 이벤트)
- 파일: `models.py`(OrderAttachment 컬럼 + 전역 필터) · 마이그레이션(downgrade) ·
  `foms/api/files/order_routes.py` · `foms/api/files/direct_upload.py` ·
  `foms/api/files/routes.py`(`_deny_file_access` tombstone 차단) · 휴지통/복구 opt-in
- 절차: `deleted_at`/`deleted_by_user_id` → **`with_loader_criteria` 전역 기본 필터**
  (호출부별 수동 필터 금지 — 84파일·428회 규모) → 삭제 API tombstone +
  `ATTACHMENT_DELETED` 이벤트 id를 `source_domain="ORDER_EVENT"`로 STORAGE_DELETE
  outbox(one-of CHECK 준수, 신규 domain 금지, `thumbnail_key` 포함) → R2 즉시삭제
  제거 → `ATTACHMENT_ADDED`/`META_UPDATED` emit.
- **완료 기준**: 마이그레이션 왕복 + 계약 테스트(전역 필터 제외·row 잔존·outbox
  등록·복구·이벤트) + 유령 첨부 회귀(시공 카드·도면 뷰어·대시보드) green.

### T5 관리자 행위 구조화 + 접근거부 기록
- 파일: `foms/web/auth/routes.py` · `foms/services/orders/order_mutation_policy.py` ·
  `foms/services/request_write_guard.py` · 독립 모드 감사 세션 헬퍼(신설,
  `error_logging.py` 옆)
- 절차: field별 from→to 메시지, 비번 재설정 별도 기록(값 미기록), `/register` 기록,
  `log_access` 실패 print→logger. 403/CSRF SecurityLog는 **전용 단명 세션**(abort
  경로 무커밋). dedupe (user_id or IP, endpoint) 60초 + 억제 카운트 + 캐시 상한/GC.
- **완료 기준**: from/to 포함·비번 값 부재(부정)·403 연타 60초 1건+카운트 +
  **rollback 주입 후 감사 행 잔존**(독립 모드) 계약 테스트.

### T6 `access_logs` 부활 (chokepoint)
- 파일: `foms/api/files/routes.py`(presigned 발급 공통 지점) ·
  `foms/web/auth/routes.py`(`log_access` additional_data 결함 수정) · 인덱스 마이그레이션
- 절차: `get_download_url` 호출부 공통 기록(view 302·download·presigned) —
  view는 (user, file_key) 10분 dedupe(결정 ③ 창 크기). 독립 모드 세션. IP·UA 저장.
- **완료 기준**: view·download 각각 AccessLog 행(IP·UA·additional_data) + dedupe 동작 +
  기록 실패 주입 시 파일 응답 정상(fail-open 로그) 계약 테스트.

### T7 request_id 로그 주입
- 파일: `foms/platform/logging_setup.py`(Filter — 항상 속성 주입, 요청 밖 `-`)
- **완료 기준**: 요청 내 request_id·밖 `-`·서드파티 레코드 무사고 단위 테스트.

### T-CP2 Phase 2 검증·커밋
- **완료 기준**: T-CP1 절차 + 스테이징 실브라우저 1회(파일 다운로드 → AccessLog 행,
  X-Request-ID ↔ 로그 대조).

## Phase 3 — P2

### T8 `security_logs` 구조화
- 파일: `models.py` · 마이그레이션 · `log_access` 확장 · 우선 호출부(관리자·권한·금액) ·
  `foms/web/admin/audit.py` + 템플릿(**JS/템플릿 변경 시 `?v=` 범프**)
- **완료 기준**: 마이그레이션 왕복 + 구조화 저장 계약 테스트 + 미전달 호출부
  하위호환 green + audit 필터 스테이징 확인.

### T9 감사 원장 수명주기
- 파일: 마이그레이션(FK drop + **models.py 동기 수정** — ForeignKey 제거 시
  `OrderEvent.order` relationship에 명시 primaryjoin/foreign()) ·
  `tools/ops/purge_audit_logs.py`(신설, receipt-purge 패턴) ·
  `tools/ops/apply_delete_retention.py`(이벤트 보존 확인) · cron toml ·
  order_events Alembic 편입(기존 DB no-op·신규 DB create 조건부)
- 함정: downgrade는 고아 이벤트 존재 시 차단(사전 카운트 안내). FK drop 후 조인
  EXPLAIN. purge 기본 dry-run + advisory lock + keyset.
- **완료 기준**: 마이그레이션 왕복(고아 시 downgrade 차단 확인) + hard purge 후
  order_events 잔존 + purge dry-run 카운트 + `tests/postgres` 전수.

### T10 Sentry + gunicorn access log
- 파일: `requirements.txt` · `foms/platform/app_factory.py`(env-gated init,
  `send_default_pii=False`) · **`before_send` 재귀 dict 마스킹 워커 신설**
  (`_REDACTIONS` 재사용 — RedactionFilter 직접 재사용 불가) · `Procfile`/`start.sh`
  (`--access-logfile -`)
- **사용자 액션**: Sentry 프로젝트 생성·DSN 발급·Railway env 등록(착수 시 안내 후 대기).
- **완료 기준**: DSN 무설정 완전 no-op 테스트 + event dict 마스킹 계약 테스트 +
  스테이징 고의 예외 1건 수신·PII 부재 + access log 출력 확인.

### T11 잔여 구멍 수리
- 파일: `foms/services/user_deletion.py`(NULL 리스트 `:29-47` 전수 재분류 — 감사
  보존 vs Chat 실삭제 유지, **결정 ⑤ 승인 전제**) · `tools/harness/failopen_scan.py` +
  인벤토리·계약 테스트(`SWALLOW_BY_CONTROL_FLOW` 분리·179 무성장) ·
  EXTERNAL writer CS/도면 경로 CANONICAL 전환
- **완료 기준**: 사용자 삭제 후 감사 actor 보존 테스트 + 신규 disposition 게이트
  green + EXTERNAL 22→감축(인벤토리 재생성).

### T-CP3 최종 검증
- **완료 기준**: `verify_result.py --json` + `pre_push_smoke` exit 0 + 전 워크플로
  green + `docs/AI_STATUS.md` 갱신 + 원장 전 task DONE. production 승격은 하지 않는다.
