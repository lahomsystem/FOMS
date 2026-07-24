# FOMS 버그감사 구현 진행원장

> SSOT: `docs/plans/2026-07-22-foms-full-system-bug-audit-report.md`. 브랜치 `bugfix/full-system-remediation` (격리 worktree `c:/tmp/foms-bugfix-remediation`).
> 규율: 각 packet = red test 먼저 → 근본수정 → green → diff 직접검증 → 커밋(`FOMS-Packet: <ID>` trailer). 구현은 SDD 서브에이전트 위임, 검증은 오케스트레이터 직접.

## 상태 범례
⬜ 미착수 · 🔵 진행 · ✅ 완료(로컬 green+diff검증) · ⏸ 차단(의존/결정 대기)

## Bootstrap 경계 (먼저)
- ✅ BASE-00 — HEAD/test/symbol 인벤토리 (`foms_bugfix_base00_inventory.md`), drift 감사 완료
- 🔵 PACKET-HARNESS-00 — core 산출물 4종 로컬 green (커밋 대기): `docs/harness/foms_bugfix_packet_tests.json`(124 packet SSOT), `docs/harness/foms_deploy_checks.json`(§8.2.1 CUTOVER_* 4종), `tools/tests/run_packet.ps1`, `tests/harness/test_bugfix_packet_manifest.py`(17 passed). APP_OK 회귀0·run_packet BASE-00 exit0·packet124/backfill18/rev99-111 검증.
  - **defer (deploy-time, 이번 packet 밖)**: completion/reissue/promotion evidence workflow(`reissue_packet_completion_evidence.yml` 등), Railway/GitHub collector, build-compat verifier(`verify_build_compatibility.py`)는 배포단계라 미구현 — manifest·runner·validation test만 착지. 각 packet은 자기 entry의 commands/created_tests/deploy_check_ids만 append.
- ⬜ OPS-ROUTE-01 — /debug-db·public ops 봉쇄 (독립 즉시 봉쇄)
- ⬜ API-ERROR-01 → REQUEST-LIMIT-01, FAILOPEN-01
- ⬜ PROXY-01 + REQUEST-LIMIT-01 → WRITE-GUARD-01
- ⬜ PGTEST-00 → REV-00
- ⬜ PGTEST-00 + WRITE-GUARD-01 → OPS-APPROVAL-00 → CUTOVER-MODE-01, BACKFILL-ARTIFACT-00

## 독립 즉시 봉쇄 (bootstrap과 병행 가능)
- ✅ FE-SYNTAX — `81296da6` (P0-6 `#`→`//` 근본수정 + parser CI 신설, node PARSE_OK·pytest 2 passed). manifest created_tests 등록만 PACKET-HARNESS-00 착지 후.
- ⬜ MIG-WEB-RETIRE-01, FE-XSS, STORED-XSS-01, DESIGNER-RETIRE-01, PUSH-01, SURFACE-GATE-01

## 완료 packet 로그
- FE-SYNTAX `81296da6`: erp-attachment-preview-open.js:205 Python주석 제거, tests/domains/test_static_js_syntax.py(node --check 전 static/js). 등록 pending.

## drift 주의
- 생산 packet(STATE-PROD-01/STATE-PROD-ACTIONS-01/AUTH-01 production, P0-9/P1-3): `foms/api/production/orders.py`가 357d8803에서 +256(hold/steps/rework 가드 3종) 드리프트. 착수 시 신규 가드를 원자계약에 흡수.

## 완료 packet 로그
(packet 완료 시 SHA·검증증거 기록)
