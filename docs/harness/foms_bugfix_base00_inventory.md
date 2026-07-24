# BASE-00 — HEAD / test / symbol inventory

> 마스터플랜 `docs/plans/2026-07-22-foms-full-system-bug-audit-report.md` §5.2 BASE-00.
> 목적: 구현 baseline 고정 + HEAD drift 감사 + finding 심볼 재확인. **기능 수정 없음.**

## HEAD

- 구현 브랜치: `bugfix/full-system-remediation` (worktree `c:/tmp/foms-bugfix-remediation`, 격리)
- baseline HEAD: `357d8803` (deploy에서 분기)
- 문서 최초 baseline: `3c328837` → 이후 `a8e3b168`(모바일 secnav) → `357d8803`(생산 보드 가드 3종)

## HEAD drift 감사 (§1.3 / §1.4)

`git diff 3c328837..357d8803` core writer 변경:
- `foms/api/production/orders.py` (+256): 생산 보드 프로세스 가드 3종(전이 전제조건·보류 게이트·수정 제작) 추가. 신규 심볼: `_apply_production_hold_gate`, `_production_steps_edit_required`, `_can_edit_production_steps`, 라우트 `rework`/`change-ack`/`steps`/`defect`/`hold`.
- `foms/web/production/dashboard.py` (+10): 대시보드 파생.
- 그 외 auth/state/data/wizard/upload writer diff 0.

**영향 판정:** 생산 start/complete 함수 위치가 이동했으나 finding 무결:
- `api_production_start` = `foms/api/production/orders.py:169` (문서 :99 → 이동), `@erp_edit_required` 유지.
- `api_production_complete` = `:242` (문서 :207 → 이동), `@erp_edit_required` 유지.
- **P0-9 권한역전(생산팀이 `erp_edit_required`로 거부됨)·P1-3A/3B 유지.** STATE-PROD-01/STATE-PROD-ACTIONS-01/AUTH-01(production) packet 착수 시 이 신규 가드 3종과 병합 주의(새 hold/steps 로직을 STATE-PROD 원자 계약에 흡수).
- 라인번호는 §1.3대로 보조정보. 구현자는 파일+함수명으로 재탐색.

## STARTUP finding 재현 (P1-17 / STARTUP-*)

`python -c "import app; print('APP_OK')"` 실행 시 출력:
```
WDCalculator tables initialization completed
[AUTO-INIT] ERP flat-column readiness verified.
[AUTO-INIT] Backfilled ERP flat columns for 4 recent active ERP orders.
[AUTO-INIT] Admin user exists.
APP_OK
```
→ **import 시 schema init·데이터 backfill(4건 write)·admin 검사가 실제 실행됨** 확인. STARTUP-SCHEMA-01/BACKFILL-01/ADMIN-01/PURE-01 대상 실재. (로컬 configured DB, 운영 아님.)

## finding 심볼 spot-check (드리프트 무관 파일)

| finding | 심볼/경로 | 확인 |
|---|---|---|
| P0-10 | `foms/api/erp_estimates.py::create_order_estimate/update_estimate_api/delete_estimate` | 실재(문서 교정 반영) |
| P0-9 | `foms/services/erp_permissions.py::can_edit_erp`(:289) `ERP_EDIT_ALLOWED_TEAMS=("CS","SALES")`(:14) | 실재 |
| MEASURE | `_MINE_SCOPE_BY_TEAM["MEASURE"]="sales"`(:18)=리스트 필터 스코프 | 실재 |
| quest | `foms/api/quest.py:193` `not can_edit_erp` 이름 폴백 | 실재 |
| DESIGNER-RETIRE-01 | nav `url_for('designer.wdplanner_v2')` layout_nav.html:163 | 실재 |

## 다음

PACKET-HARNESS-00: `foms_bugfix_packet_tests.json`(124 packet SSOT)·`foms_deploy_checks.json`·`run_packet.ps1`/runner·harness test 생성. 이후 dependency 순서로 packet 실행.
