---
name: perf-guard
description: FOMS deploy veto — deploy 직후 ERP 느려짐 재발 차단 (/perf-guard, pre-push gate, perf_scan --guard).
---

# Perf Guard — Deploy Veto

**North Star:** deploy 직후 전체 ERP 느려짐 재발 방지. TTFB OK ≠ deploy OK. **uncertain = 배포 금지.**

## 4-Layer Gate (skip none)

1. `python tools/perf/perf_scan.py --guard [--base origin/deploy] [--json]`
2. Diff trigger matrix + manual checklist — read `references/trigger-matrix.md`, `references/manual-checklist.md`
3. `powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1`
4. production 승격 전 perf-audit + staging 실측 (guard alone ≠ production OK)

## Proven auto rules (G1–G4)

| G | rule | blocks |
|---|------|--------|
| G1 | render-blocking-script | sync `<script src>` |
| G2 | cdn-sync-script | CDN without defer |
| G3 | sw-no-cache-fetch / sw-network-first-no-timeout | SW cache/timeout |
| G4 | fragment-replayed-global-listener | unguarded global listener |

Hot-path B-layer (new diff): `general-ilike`, `loop-db-query`, `shell-polling`, `shared-inline-script`, `broad-cache-invalidation`.

## 2026-07 감사 이식 규칙 (신규 4종)

| rule | 잡는 것 | 근본 처방 |
|------|--------|----------|
| `fragment-multi-script` | `*scripts*.html` fragment 에 `<script src>` 2+ (셸 스왑마다 재실행) | entry singleton 1개로 통합(`erp-dashboard-entry.js`) |
| `broad-cache-invalidation` | `invalidate_all_dashboard_slice_caches()` 통무효화(Tier A allowlist 제외) | 티어 무효화 helper(전 탭 miss 폭풍 차단) |
| `jsonb-path-filter` | `structured_data[...]` + `.filter/.in_/cast` 무인덱스 path 필터 | flat sync 컬럼(`erp_stage_code`)+인덱스+EXPLAIN |
| `mobile-queue-row-no-batch` | `build_mobile_queue_order_row(...)` batch_ctx 미전달 N+1 | `build_mobile_queue_batch_context` 후 batch_ctx 전달 |

기존 부채는 `tools/perf/baseline_debt.json`에 격리 — guard는 net-new만 veto.

## Escapes (review required)

`# perf-ok`, `SYNC_SCRIPT_ALLOWLIST` / `CDN_SYNC_ALLOWLIST` in `tests/performance/test_perf_regression_guard.py`.

## Output (Korean)

**판정: 배포 가능 | 배포 금지** — command, exit, incident class (Amplifier/Masking/Scale cliff), file:line, fix.

Root-cause fix only. SSOT: `docs/guides/PERFORMANCE_GUARDRAILS.md`, `docs/guides/ERP_SLOWDOWN_RADAR.md`.
