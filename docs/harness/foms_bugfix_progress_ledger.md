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
- ⬜ STORED-XSS-01, PUSH-01, SURFACE-GATE-01
- **SCALE-SKETCHUP-01 = N/A(auto no-op close)**: DESIGNER-RETIRE-01로 sketchup parse 대상 소멸. §5상 optional·no-op close 그룹이라 그래프 재구성 불필요, 미구현 종료.

## Bootstrap 다음 wave (독립, off BASE-00)
- ⬜ OPS-ROUTE-01(debug.py+blueprints+ops surface), API-ERROR-01, PROXY-01(app_factory 경합→API-ERROR와 순차), PGTEST-00(test infra)

## 알려진 loose end (retention spec 담당, 지금 미수정 — 도달불가 죽은코드)
- foms/persistence/designer/repositories.py:339 함수지역 삭제모듈 import(도달불가), tools/designer/{generate_expected_json,run_calibration}.py dangling(오프라인).

## 완료 packet 로그
- FE-SYNTAX `81296da6`: erp-attachment-preview-open.js:205 Python주석 제거, tests/domains/test_static_js_syntax.py(node --check 전 static/js). 등록 pending.

## drift 주의
- 생산 packet(STATE-PROD-01/STATE-PROD-ACTIONS-01/AUTH-01 production, P0-9/P1-3): `foms/api/production/orders.py`가 357d8803에서 +256(hold/steps/rework 가드 3종) 드리프트. 착수 시 신규 가드를 원자계약에 흡수.

## 완료 packet 로그
(packet 완료 시 SHA·검증증거 기록)
