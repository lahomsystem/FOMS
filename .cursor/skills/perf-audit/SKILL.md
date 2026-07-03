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

## 측정 사다리 v2 (2026-07 검증)

정적 스캐너가 놓친 진짜 병목 4종을 실측으로 잡은 순서(상세: `references/measurement-ladder.md`):

1. **wire 실측**: `curl -H 'Accept-Encoding: gzip,br'` 로 `Content-Encoding`·`Cache-Control` 직접 확인. requests 라이브러리는 압축을 해제한 뒤 바이트를 보므로 "압축 없음" 오판을 냈다 — 실제 br/gzip 작동 중.
2. **서버 vs 네트워크 분리**: TTFB vs `X-FOMS-EPT-B7-RENDER-MS`(서버 렌더). 렌더 작고 TTFB 큰 tail = 네트워크(한국↔싱가포르).
3. **클라 탭스왑**: in-page `foms:erp-shell-fragment-swapped` 이벤트 타이밍(클릭→이벤트 delta). CLI 왕복 오버헤드 배제. 실측탭 5,827ms→21ms 사건이 여기서 잡혔다.
4. **DB EXPLAIN**: `railway variables --service Postgres` 의 `DATABASE_PUBLIC_URL`로 운영 EXPLAIN(읽기전용). 생산탭 JSONB path 풀스캔 1,894행→59행.
5. **캐시**: 운영 로그 `[DashCache] result=miss` 반복 = 통무효화(invalidate_all) 폭풍 신호.

## 기규명 사실 (재조사 금지)

- tail p95 5-10s = 한국↔싱가포르 경로(**코드 아님**). 네트워크 tail은 코드로 못 고친다.
- 압축은 **br/gzip 작동 중**(진단툴이 해제 후 바이트를 봐서 오판했을 뿐).
- layout 인라인 `<script>`는 **의도된 zero-RTT**(external+defer 분리 시 RTT 워터폴 → DCL 회귀).
- fragment script 재실행은 **entry singleton 이 표준**(`erp-dashboard-entry.js`/`measurement-entry.js`).
- 무효화 필요 판정 기준 = "그 family의 **캐시된 slice DTO 내용물**에 mutation 데이터가 들어있는가". post-cache 보강은 무관 → 통무효화 불필요.
- 상세 웨이브 계획: `docs/plans/2026-07-03-erp-tab-perf-fix-waves-plan.md`.

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
