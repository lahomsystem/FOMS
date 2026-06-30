---
name: perf-audit
description: FOMS ERP Slowdown Radar — 8차원 broad 탐색 (/perf-audit, perf_scan --audit · --radar, production 전 필수).
---

# Perf Audit — ERP Slowdown Radar

**North Star:** guard catches **new** diff regressions; audit clears **latent** mines + proves staging before production.

## Workflow

1. `python tools/perf/perf_scan.py --audit [--json]`
2. `python tools/perf/perf_scan.py --radar [--json]` — 8-dimension summary
3. Deep checklist — read `references/erp-slowdown-radar.md`
4. Hot paths — `references/measurement-ladder.md` (TTFB → EXPLAIN → Chrome SW → tab swap)

`--audit` exit 0 (advisory) but **high findings = deploy 리스크**.

## 8 Dimensions

amplifier · render-block · interaction-debt · sw-cache · query-scale · payload · hot-compute · io-bound

Prioritize user-visible × frequency. Audit blind spot: use full `--audit` (includes fragment listener scan).

## When mandatory

- weekly baseline
- production 승격 전
- large shared partial / SW / dashboard change
- post-incident recurrence prevention

## Output (Korean)

Command exits, radar top findings by dimension, deploy risk, measurement gaps, safe fix order.

After fixes: rerun perf-guard + pre_push_smoke. SSOT: `docs/guides/ERP_SLOWDOWN_RADAR.md`.
