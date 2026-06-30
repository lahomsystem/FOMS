---
name: perf-guard
description: Block FOMS deploy when code changes can repeat post-deploy ERP slowdown (2026-06 incidents). Use for /perf-guard, pre-push deploy veto, or verifying diff does not add render-blocking scripts, SW regressions, hot-path DB/query risks, or shared-surface amplifiers.
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

Hot-path B-layer (new diff): `general-ilike`, `loop-db-query`, `shell-polling`, `shared-inline-script`.

## Escapes (review required)

`# perf-ok`, `SYNC_SCRIPT_ALLOWLIST` / `CDN_SYNC_ALLOWLIST` in `tests/performance/test_perf_regression_guard.py`.

## Output (Korean)

**판정: 배포 가능 | 배포 금지** — command, exit, incident class (Amplifier/Masking/Scale cliff), file:line, fix.

Root-cause fix only. SSOT: `docs/guides/PERFORMANCE_GUARDRAILS.md`, `docs/guides/ERP_SLOWDOWN_RADAR.md`.
