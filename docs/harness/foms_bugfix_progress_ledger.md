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
- 🔵 DESIGNER-RETIRE-01 — 서브에이전트 a9683fd9(designer/*+services/designer+blueprints.py+nav 삭제, persistence 유지판정). investigation 완료.
- 🔵 MIG-WEB-RETIRE-01 — 서브에이전트 ad26ba82(/admin/migration+run_web_migration+템플릿 삭제).
- ⬜ STORED-XSS-01, PUSH-01, SURFACE-GATE-01, OPS-ROUTE-01
- **SCALE-SKETCHUP-01**: DESIGNER-RETIRE-01로 sketchup 삭제→대상 소멸. auto-N/A(no-op close) 예정, DESIGNER 착지 후 report/manifest 반영.

## 완료 packet 로그
- FE-SYNTAX `81296da6`: erp-attachment-preview-open.js:205 Python주석 제거, tests/domains/test_static_js_syntax.py(node --check 전 static/js). 등록 pending.

## drift 주의
- 생산 packet(STATE-PROD-01/STATE-PROD-ACTIONS-01/AUTH-01 production, P0-9/P1-3): `foms/api/production/orders.py`가 357d8803에서 +256(hold/steps/rework 가드 3종) 드리프트. 착수 시 신규 가드를 원자계약에 흡수.

## 완료 packet 로그
(packet 완료 시 SHA·검증증거 기록)
