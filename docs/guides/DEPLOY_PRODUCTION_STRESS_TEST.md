# Deploy vs Production ERP 스트레스 테스트

> **목적:** `lahom-dev`(deploy)와 `lahom-production`(운영)을 **동일 시나리오**로 반복 실행해 어느 쪽이 빠른지, 느린 **층**(서버 TTFB / DB / SW / JS)을 분리하고 개선 우선순위를 정한다.
>
> SSOT 측정 ladder: [`ERP_SLOWDOWN_RADAR.md`](ERP_SLOWDOWN_RADAR.md) · [`measurement-ladder.md`](../../.cursor/skills/perf-audit/references/measurement-ladder.md)

---

## 전제 (반드시 고정)

| 항목 | deploy (스테이징) | production (운영) |
|------|-------------------|-------------------|
| URL | `https://lahom-dev.up.railway.app` | `https://lahom-production.up.railway.app` |
| 브랜치 | `deploy` | `production` |
| DB | Railway staging PG | Railway production PG (별도 인스턴스) |

**비교 전제**

- 동일 ERP 계정 (`FOMS_STAGING_USERNAME` / `FOMS_STAGING_PASSWORD` — 운영 계정은 **read-only·낮은 concurrency** 권장)
- 동일 뷰포트: desktop **1920×1080** (모바일 테스트 시 **390×844** 별도 세션)
- 동일 탭 순서 (아래 § 시나리오 A)
- **헤드리스 Playwright/gstack browse 단독으로 SW 결론 내리지 않음** — Real Chrome(`cursor-ide-browser`) 필수

---

## MCP / 도구 스택

| 층 | 도구 | 역할 |
|----|------|------|
| L1 HTTP TTFB | `measure_erp_tab_switch.py`, `ept_b8_staging_http_evidence.py` | fragment GET wall-clock, B7 render 헤더 |
| L2 탭 스트레스 | `browser_tab_stress_compare.py` | shell `navigateByShell` 8회 + ABA 캐시 |
| L3 Real Chrome | **cursor-ide-browser** MCP | SW 등록, full refresh, CDP Profiler |
| L4 DB | **user-postgres** MCP | `get_top_queries`, `EXPLAIN ANALYZE` |
| L5 정적 잠재 | `perf_scan.py --radar --audit` | 8차원 amplifier / sw-cache 등 |

선택 추가: `@playwright/mcp` (`--browser=chrome`, **`--headless` 금지**)

---

## 시나리오 정의

### A. ERP shell 탭 라운드 (primary, 8회)

순서 (`browser_tab_stress_compare.py`와 동일):

1. `/erp/measurement`
2. `/erp/drawing-workbench`
3. `/erp/shipment`
4. `/erp/dashboard`
5. `/erp/measurement`
6. `/erp/shipment`
7. `/erp/dashboard`
8. `/erp/measurement`

**측정:** `foms:main-content-swapped` 이벤트까지 ms (클라이언트 체감 swap)

### B. A→B→A 캐시 워밍

- `dashboard → measurement → dashboard` (warm return)
- `measurement → dashboard → measurement`

**기대:** 2번째 A 방문이 fragment LRU 캐시 hit이면 dev/prod 모두 짧아야 함. prod만 길면 payload/서버; dev만 길면 인스턴스 spec.

### C. Full page refresh (Real Chrome only)

`/erp/dashboard`에서 **F5 / browser_reload 5회** — cold/warm navigation + SW intercept 관측.

### D. Fragment TTFB (서버만)

경로 (`measure_erp_tab_switch.py`):

- `/erp/dashboard?view=fragment`
- `/erp/measurement?view=fragment`
- `/erp/drawing-workbench?view=fragment`
- `/erp/shipment?view=fragment`

헤더: `X-FOMS-ERP-SHELL: 1`, `Accept: text/html`

---

## 실행 체크리스트

### 0. 환경 준비

```powershell
cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"
$env:FOMS_STAGING_USERNAME = "<username>"
$env:FOMS_STAGING_PASSWORD = "<password>"
# production HTTP 측정 시 deploy와 동일 계정이 양쪽 모두 유효한지 확인
```

Playwright (L2):

```powershell
pip install playwright
playwright install chromium
```

### 1. 원샷 오케스트레이션 (권장)

```powershell
powershell -NoProfile -File "scripts/ops/compare_deploy_production_stress.ps1"
```

결과 JSON: `docs/harness/evidence/stress-compare-<timestamp>.json`

### 2. 레이어별 수동 실행

**L1 — fragment TTFB (양쪽 URL)**

```powershell
python tools/perf/measure_erp_tab_switch.py `
  https://lahom-dev.up.railway.app `
  https://lahom-production.up.railway.app
```

**L2 — browser tab stress**

```powershell
python tools/perf/browser_tab_stress_compare.py `
  https://lahom-dev.up.railway.app `
  https://lahom-production.up.railway.app
```

**L1 보강 — primary + subordinate HTTP (환경별 1회)**

```powershell
$env:FOMS_STAGING_BASE_URL = "https://lahom-dev.up.railway.app"
powershell -NoProfile -File "tools/harness/ept_b8_staging_full_evidence.ps1"
# production은 BASE_URL만 바꿔 반복 (낮은 부하)
$env:FOMS_STAGING_BASE_URL = "https://lahom-production.up.railway.app"
powershell -NoProfile -File "tools/harness/ept_b8_staging_full_evidence.ps1"
```

**L3 — Real Chrome** → Cursor 프롬프트: [`prompts/deploy-production-stress-test.cursor.md`](prompts/deploy-production-stress-test.cursor.md)

**L4 — Postgres** (MCP `user-postgres`, 스트레스 직후)

- `get_top_queries` — `sort_by: mean_time`, `limit: 15`
- dashboard/search hot path `EXPLAIN (ANALYZE, BUFFERS)`

**L5 — 정적 radar**

```powershell
python tools/perf/perf_scan.py --radar --json
python tools/perf/perf_scan.py --audit
```

---

## 결과 JSON 스키마 (에이전트 출력 표준)

에이전트·스크립트는 아래 형식으로 한 파일에 merge한다.

```json
{
  "meta": {
    "run_id": "2026-07-02T10:00:00+09:00",
    "operator": "cursor-agent",
    "viewport": "1920x1080",
    "scenarios": ["A_tab_round", "B_aba", "C_full_refresh", "D_fragment_ttfb"]
  },
  "environments": {
    "deploy": {
      "base_url": "https://lahom-dev.up.railway.app",
      "layers": {
        "fragment_ttfb": {},
        "tab_stress": {},
        "real_chrome": {},
        "postgres_top_queries": []
      }
    },
    "production": {
      "base_url": "https://lahom-production.up.railway.app",
      "layers": {}
    }
  },
  "comparison": {
    "winner_by_layer": {
      "fragment_ttfb_median": "deploy|production|tie",
      "tab_swap_p95_ms": "deploy|production|tie",
      "full_refresh_median_ms": "deploy|production|tie"
    },
    "regressions": [
      {
        "layer": "fragment_ttfb",
        "path": "/erp/dashboard?view=fragment",
        "deploy_ms": 120,
        "production_ms": 450,
        "delta_ms": 330,
        "hypothesis": "query-scale | cache-cold | instance-spec",
        "next_step": "EXPLAIN dashboard query on production DB"
      }
    ]
  },
  "verdict": {
    "overall_faster": "deploy|production|inconclusive",
    "primary_bottleneck_dimension": "query-scale|sw-cache|interaction-debt|...",
    "safe_to_promote": false,
    "notes": ""
  }
}
```

---

## 느린 이유 분류 (8차원 → 조치)

| 증상 | dimension | 확인 | 조치 |
|------|-----------|------|------|
| fragment GET median ↑ | `query-scale` / `hot-compute` | TTFB + EXPLAIN + B7 render-ms | 인덱스, micro-cache, N+1 제거 |
| TTFB OK, swap ms ↑ | `interaction-debt` | Real Chrome Profiler, longtask | listener singleton, polling 제거 |
| refresh 후 스피너 | `sw-cache` | Chrome Application → SW | `static/sw.js` timeout+폴백 |
| prod만 bytes ↑ | `payload` | HTTP evidence bytes | pagination, HTML diet |
| dev만 느림 | (infra) | Railway metrics | staging 인스턴스 spec — 코드 regression 아님 |
| ABA warm return 느림 | `sw-cache` / client cache | devtools Network (disk cache) | runtime-shell LRU, SW policy |

**단정 금지:** “느리다 = 서버” — 반드시 TTFB vs swap ms 분리.

---

## production 안전 수칙

- **read-heavy** 시나리오만 (위 A–D). 대량 write·bulk API 금지.
- concurrency 1 (순차). k6/부하 MCP로 production 난사 금지.
- production DB `EXPLAIN ANALYZE`는 off-peak, `LIMIT` 있는 SELECT만.
- evidence JSON은 `docs/harness/evidence/` — **자격증명·쿠키 raw 값 저장 금지**.

---

## 개선 후 재검증

1. 코드 수정 → `python tools/perf/perf_scan.py --guard`
2. deploy push 전 → `scripts/ops/pre_push_smoke.ps1`
3. deploy에서 본 가이드 재실행 → regression 항목 0
4. 사용자 승인 후 production 승격 (에이전트 임의 production push 금지)

---

## 관련 파일

| 파일 | 설명 |
|------|------|
| `tools/perf/measure_erp_tab_switch.py` | fragment TTFB dual-env |
| `tools/perf/browser_tab_stress_compare.py` | shell tab stress dual-env |
| `tools/harness/ept_b8_staging_browser_metrics.py` | 단일 env Playwright 시나리오 |
| `tools/harness/ept_b8_staging_http_evidence.py` | primary/subordinate HTTP |
| `scripts/ops/compare_deploy_production_stress.ps1` | L1+L2 원샷 |
| `docs/guides/prompts/deploy-production-stress-test.cursor-new-window.md` | **Cursor 새 창** — COPY 붙여넣기 핸드오프 |
| `docs/guides/prompts/deploy-production-stress-test.cursor.md` | Cursor 에이전트 프롬프트 (MCP 상세) |
| `docs/guides/prompts/deploy-production-stress-test.next-llm-execution-prompt.md` | **Claude Code / Codex / 기타 LLM** 실행 프롬프트 |
