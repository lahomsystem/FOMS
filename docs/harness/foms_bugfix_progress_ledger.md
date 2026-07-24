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
- ✅ ASSIGNMENT-00 — `fd290ac5`. order_assignments(partial unique·claim/batch all-or-none/release·ID-only auth·legacy backfill), REV-00 helper 재사용. PG 22·전체 2419·alembic 단일(assignment_00). 실 AUTH enforcement=AUTH-01. scope note: 대량 backfill run은 BACKFILL runs.py wrap.
- ✅ SIDEFX-00 — `78650235`. domain_side_effect_outbox(7-domain one-of FK CHECK matrix·dedupe·lease·retention)+heartbeat, enqueue/purge repository(flat 모듈). PG 18·전체 2441·alembic 단일(sidefx_00). status=PENDING|PROCESSING|DONE|DEAD(WORKER 정렬). ORDER_IMPORT_ARTIFACT=ORDER-IMPORT-01 추가.
- ✅ SESSION-SIGNING-STATE-00 — `2973ba15`. security_signing_state·wam_entry_nonces 스키마·signing_key_format(HKDF 5-label golden)·prepare CLI(EMPTY→READY 등, activation 없음). PG+pure 53·alembic 단일(signing_state_00). activation=SECRET-01.
- ✅ SIDEFX-WORKER-01 — `53de4642`. outbox worker(SKIP LOCKED claim·lease·retry/DEAD·expiry·retention·heartbeat·readiness·handler registry). 무migration. PG worker 11·failopen inventory 재생성(499→500). 실 handler=하류.
- ✅ SESSION-SIGNING-SECRET-01 — `308db4d3`. signing_keys provider+RotatingSessionInterface(BRIDGE 기존세션 호환·강제로그아웃0), P0-22 deployed fail-fast(known-fallback 제거), P1-33 WAM nonce PG single-use, activate CLI 8종. PG+runtime 23·전체 2536(domains+contracts). 무migration.
- ✅ PTC allowlist fix — REV-CLEANUP·SIDEFX-WORKER 루트 toml이 test_ptc_committed_root_allowlist_exact red로 만든 것 수정. **교훈: 회귀=domains+contracts 둘 다.**
- ✅ AUTH-01 — `85ca1be7`. 권한 코어: order_mutation_policy SSOT + 150-route policy manifest(146 guard+4 exempt·unclassified 0) + app_factory before_request 가드(VIEWER 403·/api 403 JSON·ASSIGNMENT ID row·MEASURE→SALES) + production team-wide(P0-9). test 23·**전체 2559 정상사용자 무회귀**. 무migration.
- ✅ STATE-MODEL-00 — `4c251460`. state_axes.py(read_state_axes 다축·legacy_projection·classify·registry read)+audit(mirror/projection/ambiguity 분리)+fixture. 무migration(read-only 파생). test 38·APP_OK. STATE-CORE-00은 read_state_axes/legacy_projection 사용.
- ✅ CHANNEL-AUTH-01 — `f33d4a62`. P1-8: process_foms_command fail-open 제거(manager_id 누락 allow 금지)+PII 봉쇄. channel_identity.get_user_by_manager_id는 link.user.is_active까지 확인(canonical active User only), order_mutation_policy.user_can_read_order 신설(read 판정 단일 chokepoint), quick_actions는 PII 前 resolve+read scope. deny/미매핑/비활성/DB fault/미존재=단일 no-data(PII 0·order id 미노출). test_channel_auth 12·failopen inventory 재생성(broad-catch 제거)·전체 2646. 무migration.
- ✅ AUTH-FINANCE-01 — `c5bfe573`. P0-3 완결: AUTH-01 가드가 이미 settlement/cash/payment-confirm를 FINANCE_MUTATION(CS/SALES·viewer=False)로 enforce 확인(중복 route 체크 안 함=단일 chokepoint). UI finance control을 policy_can('FINANCE_MUTATION')로 은닉(completion_dashboard_body/scripts·tablet_completion_sheet·erp_order_tab[_mobile], 서버렌더 인라인·정적범프 불필요). test_auth_finance 37+cash 7=44·거부 시 event/log/sd 0·전체 2646. 무migration·정산 business 무변경.
- head=signing_state_00. **STATE-CORE-00 unblock 확정**(REV✅+SIDEFX✅+SIDEFX-WORKER✅+AUTH-01✅+STATE-MODEL-00✅). 32 packet 커밋 완료.

## ✅ 배치 완료 (5 packet·disjoint·회귀 2666 passed 0 failed)
- ✅ CREW-00 — `9a0fe459`. installation_workers/order_installation_assignments 스키마(crew_00 마이그레이션·down=signing_state_00·단일 head·up/down 라운드트립 PG 검증)+models.py 2모델+worker CRUD(in-use 409)+배정 registry(0..20·replace/release history·FOR UPDATE 직렬화)+linked user 검증(422)+picker/audit/backfill(자동승격 0). auth 영향 0·route 미배선(하류 SHIPMENT-REFERENCE-01). PG 17·§4.4 allowlist에 crew 등록. **→ SHIPMENT-REFERENCE-01 unblock.**
- ✅ STATE-CORE-00 — `1ab65f78`. order_transition_service.py 전이 정본 엔진(execute_order_mutation+state_axes+enqueue_side_effect 조립, expected-from 검증·actual-before snapshot·version·receipt·OrderEvent parity·tx내 outbox 롤백동조)+command registry+fixture. endpoint 미이관(하류)·무mig. domains+PG green. **→ STATE-PROD-01·STATE-DRAWING-01·STATE-AS-01·STATE-QUEST-01 unblock.**
- ✅ DELETE-CORE-00 — `4c95b647`. soft_delete.py(deleted_at projection만 set/clear·main/overlay axis 보존·structured_data['delete'] 메타·execute_order_mutation 원자·멱등 no-op). hard delete·status string 직접저장 금지·무mig(기존 deleted_at 재사용). domains green. **→ DELETE-BULK-01·DELETE-TRASH-01 unblock.**
- ✅ SIDEFX-RETENTION-01 — `af2ece4c`. tools/ops/purge_domain_side_effect_outbox.py(DONE 30d/DEAD 180d terminal만·PENDING/PROCESSING 0·dry-run 기본·batch1000·advisory·resume·Flask 미import)+runbook. worker daily RETENTION provider는 SIDEFX-WORKER-01에 기존(재구현 안 함). 무mig. PG green.
- ✅ AUTH-QUEST-READ-01 — `d360a5a0`. quest GET의 read-writes-DB(lazy-create+sd append+commit+updated_at+cache 무효화) 제거→비영속 표시 합성, creation은 mutation path 유지(STATE-QUEST-01 이관). 반복 GET version/event/JSONB 0. failopen inventory 재생성(quest.py 라인시프트·496 불변). 무mig. domains green. **→ AUTH-QUEST-01 unblock.**
- head=crew_00(CREW 마이그레이션). **37 packet 커밋 완료.**

## ✅ 배치 2 완료 (5 packet·disjoint·회귀 2692 passed 0 failed)
- ✅ ITEM-ID-00 — `f43b1518`. order_item_identities UUID registry(DB-global unique·item_index provenance·is_active tombstone·partial unique 슬롯당 활성1)+OrderAttachment/OrderScheduleDate.item_id nullable FK+audit(safe/ambiguous OUT_OF_RANGE·NEGATIVE_INDEX CSV)+backfill(lite·idempotent·resume·enforcement gate)+order_date_sync 연동. 마이그레이션 item_id_00(down=crew_00·단일 head). PG 13. **lite 패턴 승인**(runs.py 서명체인 과도, 형제 ASSIGNMENT/STATE-MODEL 선례). **→ head=item_id_00.**
- ✅ CALL-LOG-01 — `085c4f20`. CALL_LOGGED command(execute_order_mutation one-tx·version/receipt/OrderEvent·sd.calls append 1·same-key idempotent·orthogonal 축 불변). **근본수정**: legacy @erp_edit_required(canonical ERP_EDIT와 모순·MANAGER 오403) 제거→handler evaluate_policy(ERP_EDIT) enforce(@login_required 유지). policy SSOT 무변경(ERP_EDIT 재사용). test 13. **failopen inventory 재생성 포함(ITEM-ID order_date_sync + call_log 라인시프트 둘 다). ⚠️inventory 커플링: ITEM-ID-00+CALL-LOG-01은 production 승격 시 함께**(inventory가 두 source 라인 참조).
- ✅ STATE-AXES-REPAIR-00 — `6428aac4`. repair_order_state_axes.py(dry-run/apply/verify·audit safe bucket만·LEGACY_ALIAS·coverage 100%·manual CSV verifier). ambiguous 자동교정 0(§7.2)·endpoint 무변경. domains green. 무mig.
- ✅ QUEST-BACKFILL-00 — `6a753d41`. audit_order_quests(stage별 current 단일성 위반·모호 approval 분류)+backfill(safe만·approval 보존·coverage 100%). lazy create 복구 없음·모호 자동선택 0. quest 전이는 STATE-QUEST-01. PG green. 무mig(JSONB).
- ✅ HISTORY-01 — `c45315d9`. P1-16: 두 history mobile JS DOMContentLoaded-only→singleton guard+foms:erp-shell-fragment-swapped 리스너로 fragment swap 후 toggle/포커스 부활(G4 idempotent). ?v 범프 20260724a. shell 무변경. perf guard+p3 11 passed.
- head=item_id_00. **43 packet 커밋 완료.**

## 🎯 다음 후보 (신규 unblock)
- **STATE 패밀리**(STATE-CORE unblock): STATE-PROD-01·STATE-PROD-ACTIONS-01·STATE-DRAWING-01·STATE-AS-01·STATE-QUEST-01(+AUTH-QUEST-READ) — endpoint를 order_transition_service로 이관. 단 BACKFILL 선행(PRODUCTION-BACKFILL-00·QUEST-BACKFILL-00·AS-BACKFILL-00·DRAWING-REVISION-BACKFILL-00·CONSTRUCTION-BACKFILL-00) 확인.
- **DELETE 패밀리**(DELETE-CORE unblock): DELETE-BULK-01·DELETE-TRASH-01·DELETE-RETENTION-01.
- **ITEM-ID-00**(migration·models.py, head=crew_00 위로 체인) — 다음 마이그레이션 슬롯 단독.
- **SHIPMENT-REFERENCE-01**(CREW unblock·write_guard·pg), **AUTH-QUEST-01**(write_guard), **CALL-LOG-01·ERP-ESTIMATE-01**(REV+AUTH ready).
- 마이그레이션 packet은 여전히 순차(현 head=crew_00): ITEM-ID-00 등 한 번에 하나.
- ✅ SECRET-02 — `180adb40`. secret_literal_scan(AST literal 게이트, attribute/env-backed 제외로 SIGNING 경계)·check_deploy_secrets(배포 presence fail-fast)·allowlist. hygiene 22·APP_OK·회귀 0. → **SESSION-SIGNING-STATE-00 unblock**(deps SECRET-02✅+PGTEST✅+OPS-APPROVAL✅+CUTOVER✅).
- **SECRET-02 재스코프 확정**: 잔존 credential secret 0(SECRET-01 Kakao·SIGNING은 SESSION-SIGNING-SECRET-01, KAKAO_JS는 공개 클라키 유지). SECRET-02=literal 스캔 test + 배포 credential presence fail-fast(삭제된 qa_deploy_test 대체).
- head=assignment_00.
- ✅ REV-CLEANUP-01 — `cf94d028`. purge_order_mutation_receipts.py(retention 7·batch·dry-run 기본·advisory·resume·active 불변)·railway-cron toml. PG 6·lane 94·namespace 190·APP_OK. 무마이그레이션.
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
