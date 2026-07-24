# FOMS 버그감사 구현 진행원장

> SSOT: `docs/plans/2026-07-22-foms-full-system-bug-audit-report.md`. 브랜치 `bugfix/full-system-remediation` (격리 worktree `c:/tmp/foms-bugfix-remediation`).
> 규율: 각 packet = red test 먼저 → 근본수정 → green → diff 직접검증 → 커밋(`FOMS-Packet: <ID>` trailer). 구현은 SDD 서브에이전트 위임, 검증은 오케스트레이터 직접.

## 상태 범례
⬜ 미착수 · 🔵 진행 · ✅ 완료(로컬 green+diff검증) · ⏸ 차단(의존/결정 대기)

## Bootstrap 경계 (먼저)
- ✅ BASE-00 — HEAD/test/symbol 인벤토리 (`foms_bugfix_base00_inventory.md`), drift 감사 완료
- ✅ PACKET-HARNESS-00 — `28264fff`+`8a1194fd`. manifest(124)·deploy_checks·run_packet.ps1·validation(17 passed). 오케스트레이터 독립검증: packet124=report/backfill18 exact/cycle0(topo)/rev99-111/edge 7종 §5일치. seed-empty 결함→anti-preseed 교정.
  - **등록 규율**: 각 packet의 manifest append는 오케스트레이터가 직렬 수행(동시 편집 클로버 방지). 서브에이전트는 코드+테스트만.
  - **defer (deploy-time, 이번 packet 밖)**: completion/reissue/promotion evidence workflow(`reissue_packet_completion_evidence.yml` 등), Railway/GitHub collector, build-compat verifier(`verify_build_compatibility.py`)는 배포단계라 미구현 — manifest·runner·validation test만 착지. 각 packet은 자기 entry의 commands/created_tests/deploy_check_ids만 append.
- ⬜ OPS-ROUTE-01 — /debug-db·public ops 봉쇄 (독립 즉시 봉쇄)
- ⬜ API-ERROR-01 → REQUEST-LIMIT-01, FAILOPEN-01
- ⬜ PROXY-01 + REQUEST-LIMIT-01 → WRITE-GUARD-01
- ⬜ PGTEST-00 → REV-00
- ⬜ PGTEST-00 + WRITE-GUARD-01 → OPS-APPROVAL-00 → CUTOVER-MODE-01, BACKFILL-ARTIFACT-00

## 독립 즉시 봉쇄 (bootstrap과 병행 가능)
- ✅ FE-SYNTAX — `81296da6` (P0-6 `#`→`//` + parser CI, node PARSE_OK·pytest 2). manifest 등록 완료(`8a1194fd`).
- ✅ FE-XSS — `582af3bc` (P0-5 measurement 검색어 `|safe`→`tojson` 3파일 + test_measurement_search_xss 3 passed, Flask tojson hostile 중화 검증). 등록 완료.
- ✅ DESIGNER-RETIRE-01 — `75b00b65`. designer 3레이어+web/designer+templates+static+nav+blueprints 삭제(133파일), 죽은 테스트 43개+qa_deploy_test 제거. persistence/designer 유지(env.py·conftest ORM 매핑). test_designer_retired 13 passed, drawing/workbench 303·namespace 179 passed, APP_OK. tools/tests taxonomy allowlist 동반 수정(내 PACKET-HARNESS-00 회귀).
- ✅ MIG-WEB-RETIRE-01 — `7fa43775`. /admin/migration+run_web_migration+템플릿 삭제. test 4 passed, admin 회귀 green, APP_OK.
- ✅ PUSH-01 — `5dd0343d`. sw.js nested data.* 우선+top-level fallback+same-origin sanitize. test 5(node VM)·push/notif 146 passed, node --check OK, APP_OK.
- ✅ OPS-ROUTE-01 — `be6a5a51`. P0-18 /debug-db 삭제(404)·channel health 인증게이트(무인증 coarse+no-store, ADMIN detail private)·healthz status만. test 9(red7→green9)·channel/health 25·namespace 179, APP_OK. bearer/Railway ops-service 배포단계 분리.
- ✅ STORED-XSS-01 — `b9c70f7a`. P0-19/20/21/23 sink 봉쇄(order_link escape-first, index.html autoescape+pre-line, User.name textContent, change_logs createElement/addEventListener). sink manifest 13개, test 20 passed, order/security/drawing/event 754, APP_OK. events.py는 STORED-XSS 무접근(P0-23=change_logs 클라렌더).
- ✅ API-ERROR-01 — `81f90bae`. P1-28 http.py after_request 경계스크럽(handled str(e) 500 106곳 단일 choke), errorhandler(4xx 보존), error_logging.py(redaction+protected logger), print_exc 53→0. test 7(red→green), error/http/api 277·모듈 393, APP_OK. broad catch=FAILOPEN 소관.
- **SCALE-SKETCHUP-01 = N/A(auto no-op close)**.
- **교훈**: API-ERROR류 cross-cutting 스윕(print_exc 전파)은 파일겹침 필연 → 단독 wave. (이번엔 STORED-XSS와 events.py 안 겹쳐 무사, listing.py도 disjoint.)

## Bootstrap chain (진행)
- ✅ PROXY-01 — `<committed>`. rate_limit key-func raw XFF/X-Real-IP 파싱 제거→canonical remote_addr, hop `FOMS_TRUSTED_PROXY_HOPS` env. test 5(spoof red→green)·rate 23, APP_OK. Railway hop 실측 merge-gate.
- ✅ SURFACE-GATE-01 — `7ac3ee94`. P1-27 인라인 predicate→SSOT GATE 일원화(1024 소실 해소)+erp-order-cohort.js(pristine reload/dirty 동결+배너/keyboard flip 0). test 10(red9→green)·회귀 374, APP_OK.
- ✅ REQUEST-LIMIT-01 — `<committed>`. MAX_CONTENT_LENGTH 500MiB→50MiB, FomsRequest(form memory 1MiB/parts 1000/tempfile unlink), route body-cap manifest(telemetry2K/login16K/normal1M/excel10M/legacy50M), pre-handler 413/415 JSON, presigned 제외. test 19·회귀 73, APP_OK.
- ✅ WRITE-GUARD-01 — `dd2118ed`. 공용 CSRF(itsdangerous 세션바인딩)+Origin before_request 가드, manifest 149route(143+6exempt) url_map 전수, client layout_head 단일 choke(fetch/XHR/form/beacon), logout/switch POST전용. WRITE_GUARD_ENABLED=not TESTING. test 12 + **tests/domains 전체 2380 passed 0 failed**, APP_OK. holidays_kr_*.json gitignore.
- 🔵 FAILOPEN-01 — 단독 wave(cross-cutting, 무PG). deps API-ERROR ✅.

## ✅ PostgreSQL lane 확보 (갈림길 해소)
- 로컬 PostgreSQL 16.8 @localhost:5432 발견(dev DSN `postgresql://postgres:lahom@127.0.0.1:5432`, **커밋 파일엔 비번 금지 — env-driven**). test DB 생성/삭제 가능.
- ✅ PGTEST-00 — `bb9ec61d`. tests/postgres/(conftest 안전가드 localhost+foms_test_*, create_all 42테이블, xdist 격리), run_postgres_concurrency.ps1, CI postgres:16, smoke+safety 19 passed(dev env), 잔여 DB 0, opt-in skip. → **postgres=true 63개 packet 로컬 검증 경로 열림.**
- ✅ FAILOPEN-01 — `0a533f22`. broad catch 499 전수 AST 인벤토리(unclassified 0), LOG_AND_CONTINUE 463(로깅 28)/FAIL_CLOSED 19/INTENTIONAL 17, silent-pass 45 전량 해소. release gate static. test 10 + 전체 2390 passed 0 failed, APP_OK. API-ERROR 겹침 표기.
- ✅ OPS-APPROVAL-00 — `670f372e`. security_principal_versions+trigger·ops_approval_requests·target_audits, approval UI(재인증)·consume(FOR UPDATE one-time·cross-DB RESERVED)·control-root·reconciler, operations manifest 35op/9owner cli=null seed. PG 30 passed·전체 2390·마이그레이션 up/down·FAILOPEN/write-guard gate, APP_OK.
- ✅ SECRET-01 — `34c64503`. Kakao REST 키 env-only+require_kakao_rest_key() fail-fast, geocode_config/address/converter/SCheduler 리터럴 제거, JS키(공개)는 유지. FAILOPEN inventory 재생성(라인시프트). test 4·address 93·APP_OK·gate. **운영: Kakao 콘솔 외부 rotate 필수(git history 잔존).** → SECRET-02(다음).
- ✅ REV-00 — `52ac2749`. orders.mutation_version + order_mutation_receipts/read_resources, execute_order_mutation helper(FOR UPDATE·If-Match·idempotency·read-receipt). PG 12·전체 2394·alembic 단일(ops_approval_00→rev_00). 실 route 적용은 하류.
- ✅ CUTOVER-MODE-01 — `9f135a3e`. feature_cutover_fences(15 seed)/markers(irreversible trigger), build_compatibility.json+verify, mode manifest 15-row, transactional helper, CLI 4종(OPS-APPROVAL 토큰), security/cutover nested. PG 47·전체 2394·alembic 단일(feature_cutover_00). **defer: runtime_replica_heartbeats(배포배선), manifest prerequisite/affected 빈seed(family packet 채움).**
- ✅ BACKFILL-ARTIFACT-00 — `3f121d65`. DPAPI(win32crypt) key-envelope·AES-GCM payload·maintenance_backfill_runs(lease/checkpoint/state machine)·approval-scope, artifact_root guard, consume_backfill_apply/reauthorize. crypto 25(Windows DPAPI)+PG 10+ops 30·전체 2419·alembic 단일(backfill_artifact_00). BACKFILL 3 op cli=null(consumer가 채움).
- 🔵 ASSIGNMENT-00(마이그레이션·AUTH-01 선행, deps REV✅+BACKFILL✅) ∥ REV-CLEANUP-01(무마이그레이션·purge CLI, deps REV✅) — disjoint.
- head=backfill_artifact_00. 다음: SESSION-SIGNING chain(SECRET-02→STATE-00→SECRET-01)→AUTH-01, SIDEFX-00, STATE-MODEL-00.

## ⚠️ 진행 제약
- **마이그레이션 추가 packet은 순차 필수**(병렬 시 둘 다 현재 head revise→alembic multi-head 충돌). 각 subagent에 "현재 head를 revise" 지시. 현 head=rev_00_order_mutation.
- **SECRET-02 재스코프 필요**: §5.2가 삭제된 tests/qa_deploy_test.py 참조 + P0-22 fallback secret(app_factory:182·channel_security:34)은 SESSION-SIGNING-SECRET-01 소관과 겹침. 착수 전 경계 정리.
- **다음 (PG chain)**: CUTOVER-MODE-01(deps OPS-APPROVAL✅)·BACKFILL-ARTIFACT-00(deps OPS-APPROVAL✅) / REV-00→STATE-CORE-00·DATA-01·DELETE-CORE-00 / SECRET-02→SESSION-SIGNING chain→AUTH-01

## ✅ 부트스트랩 보안 경계 완성 (16 packet)
BASE-00·PACKET-HARNESS-00 + OPS-ROUTE-01·API-ERROR-01·FAILOPEN-01·REQUEST-LIMIT-01·PROXY-01·WRITE-GUARD-01·PGTEST-00 + 봉쇄 FE-SYNTAX·FE-XSS·MIG-WEB-RETIRE-01·DESIGNER-RETIRE-01·STORED-XSS-01·PUSH-01·SURFACE-GATE-01. SCALE-SKETCHUP-01=N/A.
- 하류 PG packet은 `pg_engine`(다중 커밋 세션)으로 SKIP LOCKED/FOR UPDATE 실경합 검증. 로컬 검증 시 FOMS_TEST_DATABASE_URL env 주입.

## 알려진 loose end (retention spec 담당, 지금 미수정 — 도달불가 죽은코드)
- foms/persistence/designer/repositories.py:339 함수지역 삭제모듈 import(도달불가), tools/designer/{generate_expected_json,run_calibration}.py dangling(오프라인).

## 완료 packet 로그
- FE-SYNTAX `81296da6`: erp-attachment-preview-open.js:205 Python주석 제거, tests/domains/test_static_js_syntax.py(node --check 전 static/js). 등록 pending.

## drift 주의
- 생산 packet(STATE-PROD-01/STATE-PROD-ACTIONS-01/AUTH-01 production, P0-9/P1-3): `foms/api/production/orders.py`가 357d8803에서 +256(hold/steps/rework 가드 3종) 드리프트. 착수 시 신규 가드를 원자계약에 흡수.

## 완료 packet 로그
(packet 완료 시 SHA·검증증거 기록)
