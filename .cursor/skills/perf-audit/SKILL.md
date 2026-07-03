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

## 치명적 안티패턴 (오판 방지 — 2026-07 사건)

스캐너는 **측정이 없는 정적 패턴 매처**다. finding은 "실측 후보"일 뿐, 수정 지시가 아니다.

- **코드 뜯기 전 반드시 실측**: `references/measurement-ladder.md`로 TTFB vs `X-FOMS-EPT-B7-RENDER-MS`(서버 렌더) 분리. 서버 렌더 작고 TTFB 큰 tail = **네트워크(한국↔싱가포르 단일리전)**지 코드 아님. 네트워크 tail을 코드로 못 고친다.
- **임계경로 inline `<script>`는 최적(zero-RTT)**. 단일 리전 고지연 경로에서 external+defer로 분리하면 RTT 워터폴 → DCL 회귀. 인라인을 "위반"으로 보고 분리 금지. (과거 이 오판으로 DCL 10s 회귀.)
- **finding 0 만들기 ≠ 빨라지기**(Goodhart). 스캐너 점수가 아니라 실측 TTFB/DCL를 목표로.

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
