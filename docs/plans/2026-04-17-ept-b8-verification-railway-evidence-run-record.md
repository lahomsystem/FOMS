# EPT-B8 — Verification + Railway / staging evidence (run record)

**Status:** **in progress** — **local gate + 스테이징 HTTP·브라우저 실측 1회** (2026-04-17, `FOMS_STAGING_COOKIE` / Playwright 로그인) — **근거:** `docs/harness/evidence/2026-04-17-ept-b8-staging-http-evidence.json` (**`g1_shared_layout` 포함**), `2026-04-17-ept-b8-browser-erp_shell_tab_swap.json`, `…-g1_document_nav.json`, `…-primary_subordinate_roundtrip.json`, `…-navigation-dashboard.json`. **`/erp/orders/<id>`** 는 **302 + Location** 검증 유지. **Railway deployment ID** — §4.3 기존 값(이 캡처에서 CLI 재확인 없음). **여전히 PENDING:** primary 9 **행별 Cold** 열, **shell 탭 클릭→LCP**(현재는 fragment RT·문서 FCP만), **왕복 HAR**, **Before/After 배포 쌍** 엄격 정리.  
**Authoritative inputs:** `docs/specs/2026-04-17-erp-shell-fragment-contract_SPEC.md`, B6/B7 run records, `docs/plans/2026-04-17-ept-b1-baseline-contract-run-record.md` §8 (inventory v2).  
**Explicit non-goals:** Re-open B7 §Deferred (DOM/row on-demand without semantic-preserving proof); query rewrite in this batch; code changes for performance unless fixing evidence collection only.

### PENDING checklist (B8 closeout — do not invent numbers)

1. Primary 9 table **Cold** column (per-path first tab / HAR or isolated session).
2. **Before** deploy baseline vs **After** (HTTP JSON는 **After** 스냅샷; **Before** 행은 B1·이전 캡처와 명시 대조 필요 시).
3. **Shell 탭 click → LCP / meaningful paint** — fragment 응답 ms(`erp_shell_tab_swap`)는 **있음**; **LCP는 별도**(§6.3 문서 네비 FCP와 혼동 금지).
4. **primary ↔ subordinate** — Playwright **문서 Back** ms **캡처됨** (`primary_subordinate_roundtrip`); **HAR**(shell/popstate)은 여전히 권장.
5. **G1** `g1_shared_layout` — **HTTP JSON에 반영됨** (2026-04-17 캡처).
6. **G2** — optional: Network에서 `rel=prefetch` 관찰; 미첨부 시 계획서대로 비차단.
7. §6 **cold vs warm** — full/warm·cold_nav_proxy·브라우저 일부 **숫자 있음**; **행별 Cold**는 미완.

---

## 1. Scope (locked)

### In

1. **Automated regression (repo, local):** `APP_OK`, `verify_result.py --json`, focused domain pytest for shell + runtime-shell contracts (+ B7 profile asset test file).
2. **Evidence design:** Structured **before/after** placeholders for **primary 9** (`SPEC` §2 / B1 §8.1) and **subordinate/descendant inventory** (B1 §8.2–8.5), aligned with 상위 계획 §4.8.
3. **Navigation modes to capture on staging** (same user session, authenticated): full reload, cold tab navigation (first visit to tab in session or cache cleared), warm tab navigation (repeat), primary ↔ subordinate round-trip (e.g. dashboard → subordinate URL from B1 §8.2–8.3, back).
4. **Metrics (browser):** Performance API or equivalent — e.g. `performance.now()` around shell tab click until `#main-content` swap observable, optional `Largest Contentful Paint` / long tasks where available; **click-to-first-meaningful-content** and **post-fragment-settled** as separate rows if tooling allows.
5. **Server correlation:** Where available, response headers — e.g. `X-FOMS-EPT-B7-ROUTE`, `X-FOMS-EPT-B7-RENDER-MS` (B7) for `/erp/dashboard`, `/erp/as`, `/erp/shipment`; micro-cache logs `[DashCache]` / app logs; **not** a substitute for browser RUM.
6. **Shortfall taxonomy:** If targets missed, classify root cause as **`HTML` | `query` | `render` | `asset` | `prefetch miss`** (plan §4.8) with one-line evidence each.

### Out

- Query / ORM / index changes (defer to register).
- Claiming B7 Deferred items “done” without new semantic-preserving proof.
- Declaring **EPT-B9** final audit complete inside this document.
- **Final** B8 closeout without **at least one** staging/prod-like authenticated capture set (see §Hard stop).

---

## 2. Acceptance (plan §4.8 mapping)

| Criterion | Local (this repo) | Staging / prod-like |
|-----------|-------------------|----------------------|
| APP_OK / verify_result / focused pytest | **Done** — see §3 | N/A |
| Browser-like regression | **Partial** — pytest contract regression **done**; human/browser Performance evidence **PENDING** | **Partial** — HTTP **+** Playwright JSON(탭 스왑·G1·왕복·`/erp/dashboard` navigation+FCP); shell **LCP**는 미종 |
| Primary 9 before/after | Template: §4 | **Partial** — §4 표 **2026-04-17 HTTP 재캡처** + **After Railway ID(§4.3)**; **Before**·**Cold 열** **PENDING** |
| Subordinate/descendant inventory before/after | Template: §5 | **Partial** — Tier B/C **full_reload(s)** (2026-04-17 JSON); `/erp/orders/<id>` **302 B5** |
| full / cold / warm / primary↔subordinate comparison | Procedure: §6 | **Partial** — full/warm·`cold_nav_proxy`·**문서 Back ms**; **행별 Cold·HAR** **PENDING** |
| click-to-paint (or equivalent) | N/A locally | **Partial** — 문서 로드 **FCP** (`navigation` 시나리오); shell 탭은 **fragment RT ms** (LCP 아님) |
| Miss taxonomy filled when below target | N/A until staging numbers | **Required** when comparing |

---

## 3. Local verification gate (executed)

**Date:** 2026-04-17 (session). **Environment:** developer workstation, Windows, local DB.

| Command | Result |
|---------|--------|
| `python -c "import app; print('APP_OK')"` | `APP_OK` |
| `python tools/harness/verify_result.py --json` | `"success": true` |
| `pytest tests/domains/test_erp_shell_fragment_contract.py tests/domains/test_erp_runtime_shell_js_contract.py tests/domains/test_ept_b7_profile.py tests/domains/test_global_nav_runtime_js_contract.py -q` | **50 passed** (동일 세션 기준; `HEAD` 재실행 권장) |

**Interpretation:** Shell fragment contract, runtime-shell JS contract, and EPT-B7 static/helper tests pass — **no code regression** detected by these suites. **Staging:** HTTP + Playwright JSON under `docs/harness/evidence/` (2026-04-17) — 상세는 §4·§6.

---

## 4. Primary 9 — before/after evidence template (staging)

**Base URL:** `https://lahom-dev.up.railway.app`  
**HTTP harness (2026-04-17 재실행, `FOMS_STAGING_COOKIE` + `--include-g1`):** `docs/harness/evidence/2026-04-17-ept-b8-staging-http-evidence.json` (`full_reload_s` = no-cache 첫 GET, `warm_second_get_s` = 동일 세션 즉시 재GET). **G1:** 같은 파일 키 `g1_shared_layout`.

| Path | Full reload (s) | Cold nav (s) | Warm nav (s) | Notes |
|------|-----------------|--------------|--------------|-------|
| `/erp/dashboard` | 3.106 | — | 1.793 | B7: `erp_dashboard`, render **190.0** ms |
| `/erp/measurement` | 2.951 | — | 1.62 | B7 미부착 |
| `/erp/drawing-workbench` | 2.118 | — | 2.339 | B7 미부착 |
| `/erp/production/dashboard` | 2.288 | — | 2.356 | B7 미부착 |
| `/erp/shipment` | 1.841 | — | 1.828 | B7: `erp_shipment_dashboard`, render **335.6** ms |
| `/erp/as` | 2.383 | — | 2.323 | B7: `erp_as_dashboard`, render **197.8** ms |
| `/erp/construction/dashboard` | 2.928 | — | 2.63 | B7 미부착 |
| `/erp/completion` | 0.936 | — | 0.915 | B7 미부착 |
| `/erp/history/` | 1.025 | — | 0.909 | B7 미부착 |

**Cold 열:** primary 9별 “첫 탭 방문” cold는 하네스 한 세션으로는 분리하기 어려움 — **§4.4** `cold_nav_proxy` 참고 또는 **HAR**.  
**Before:** commit hash / deploy id: *(baseline / prior Railway deploy — compare to B1 run record if needed)*  
**After (Railway at HTTP evidence):** **Railway deployment ID:** **`38ff39ed-4c80-4276-bea0-3a9560f13b14`** (SUCCESS, **2026-04-17 11:09:28 +09:00**). **CLI 맥락:** workspace `lahomsystem's Projects` → project **FOMS-DEV** → environment **production** → service **FOMS** (`railway link` 후 `railway deployment list`). **JSON 근거는 위 경로 파일(커밋됨).**

### 4.1 Request timestamp reference (MCP, ordering only — not wall-clock ms)

Monotonic timestamps from `browser_network_requests` **mainFrame** row per path (same session):  
`/erp/dashboard` 1776389522623 → `/erp/measurement` 1776389534512 → `/erp/drawing-workbench` 1776389542830 → `/erp/production/dashboard` 1776389550799 → `/erp/shipment` 1776389557981 → `/erp/as` 1776389564460 → `/erp/construction/dashboard` 1776389571581 → `/erp/completion` 1776389579671 → `/erp/history/` 1776389584837.

**Prefetch / fragment (XHR 200) observed in-session:** e.g. after loads, `.../erp/dashboard?view=fragment`, `.../erp/measurement?view=fragment`, `.../erp/drawing-workbench?view=fragment`, `.../erp/production/dashboard?view=fragment` — consistent with runtime-shell warm/prefetch behavior (not a substitute for §6 cold/warm matrix).

### 4.2 Automated HTTP capture (duration + B7 headers) — `tools/harness/ept_b8_staging_http_evidence.py`

Cursor browser MCP는 **응답 헤더·duration**을 내보내지 않는다. 스테이징에서 **동일 쿠키**로 재현 가능한 수치를 얻으려면 하네스를 사용한다.

**준비:** 스테이징 앱은 쿠키 이름이 **`session_staging`** 이다 (`foms/platform/app_factory.py`). 반드시 **`이름=값`** 형태로 넣는다 — **값만** 넣으면 인증 실패하고 `final_url`이 전부 `/login?next=...` 가 된다.

- **권장:** Network 탭 → 문서 요청 → **Request Headers → `Cookie:`** 줄 전체 복사.  
- **Application 탭만 쓸 때:** `session_staging` 행의 **Value** 를 복사한 뒤 접두어를 붙인다 — 예: `'session_staging=eyJ...전체...'`.

**실행 (PowerShell 5.x, repo 루트):**

**A) 자동 로그인 → 쿠키 설정 → HTTP 하네스 (권장):** 환경에만 자격 증명을 둔다 (커밋 금지).

```text
$env:FOMS_STAGING_USERNAME = '<스테이징 ID>'
$env:FOMS_STAGING_PASSWORD = '<스테이징 비밀번호>'
powershell -NoProfile -File .\tools\harness\ept_b8_staging_full_evidence.ps1
```

또는 한 단계씩: `python tools/harness/ept_b8_staging_session_from_login.py` 가 stdout에 `session_staging=...` 한 줄을 출력 → 이를 `FOMS_STAGING_COOKIE`에 넣고 `ept_b8_staging_http_evidence.py` 실행. 변수 템플릿은 `tools/harness/ept_b8_staging_env.example` 참고.

**B) 수동 (DevTools 쿠키 복사):**

```text
$env:FOMS_STAGING_COOKIE = 'session_staging=<DevTools에서 복사한 값>'
python tools/harness/ept_b8_staging_http_evidence.py --base https://lahom-dev.up.railway.app --order-id 2732 --json
```

**브라우저 Performance (선택):** Playwright 설치 후 `python tools/harness/ept_b8_staging_browser_metrics.py` — `--scenario navigation|erp_shell_tab_swap|g1_document_nav|primary_subordinate_roundtrip` (마지막은 `--order-id` 기본 2732) — navigation/paint/longtask 또는 클릭·왕복 프록시 JSON (동일 env 자격 증명). 미설치 시 stderr에 SKIP 안내만 출력.

성공 시 `final_url` 은 `/erp/...` 이어야 하며, B7이 붙은 뷰는 `b7_headers` 에 키가 나온다. `final_url` 이 `/login?next=...` 이면 쿠키 형식·만료를 다시 확인한다. **`/erp/orders/<id>`** 서브키는 `legacy_redirect_contract_ok`, `redirect_location`(302 계약)을 별도로 본다 — 전체 HTML 문서 시간은 **`/edit/<id>?open=erp-beta`** 와 동일 스코프로 취급.

### 4.4 `cold_nav_proxy` (동일 하네스 실행 — 참고용)

새 `requests.Session`으로 dashboard 착륙 후 첫 측정·출고 GET만 기록(탭 cold의 **프록시**).

| Step | Elapsed (s) | B7 (if any) |
|------|-------------|-------------|
| land `/erp/dashboard` | 2.762 | (dashboard 행 참고) |
| first GET `/erp/measurement` after dashboard | 3.071 | — |
| first GET `/erp/shipment` after dashboard | 1.923 | `erp_shipment_dashboard`, render **431.8** ms |

**출력 JSON 필드 의미 (표에 옮길 때):**

| Run record 열 | 하네스 매핑 |
|---------------|-------------|
| Full reload (s) | `primary.<path>.full_reload_s` — `Cache-Control: no-cache` 단일 GET |
| Warm nav (s) | `primary.<path>.warm_second_get_s` — 직후 동일 URL 두 번째 GET (같은 `requests.Session`) |
| Cold nav (s) | **별도**: `cold_nav_proxy` — 새 Session으로 dashboard 착륙 후 measurement·shipment **첫** GET 지연(탭 전환 프록시). primary 9 전 행을 채우려면 **수동** cold 시나리오(탭 순서 고정) 또는 HAR 권장 |
| B7 | 각 row `b7_headers`: `X-FOMS-EPT-B7-ROUTE`, `X-FOMS-EPT-B7-RENDER-MS` (대상 뷰에 B7이 연결된 경우만; 미연결 뷰는 빈 객체) |
| Subordinate | `subordinate` 맵 — `full_reload_s`, `final_url`, `b7_headers` |

**한계:** **click-to-paint** / **LCP** / **Performance API** 는 이 스크립트에 없음 → 브라우저 **DevTools Performance** 또는 콘솔에서 `performance.getEntriesByType('navigation')` 등 **수동** 기록 (§6.3).

### 4.3 Railway deployment ID (서비스 메타)

로컬 CLI: `railway login` → `railway link` (프로젝트·환경·서비스) → `railway deployment list` — 최신 **SUCCESS** 행의 UUID를 **After** 줄에 기입.

**2026-04-17 캡처:** `38ff39ed-4c80-4276-bea0-3a9560f13b14` | SUCCESS | 2026-04-17 11:09:28 +09:00 — 링크: **FOMS-DEV** / **production** / **FOMS**.

HTTP 응답 헤더의 `x-railway-request-id` / CDN edge 표시는 **요청 추적용**이며 **배포(Deployment) ID와 동일하지 않음**.

---

## 5. Subordinate / descendant inventory — evidence template (staging)

Source: B1 §8.2–8.5. Minimum: smoke + one timing row per tier representative.

**Representative order id (staging data):** `2732` (visible on 도면작업실 큐).

### Tier B (required subordinate)

| Path | Smoke OK | full_reload (s) | Timing notes |
|------|----------|-----------------|--------------|
| `/erp/drawing-workbench/2732` | **Yes** | 1.722 | `final_url` ERP 상세 OK; B7 미부착 |
| `/edit/2732?open=erp-beta` | **Yes** | 1.565 | ERPbeta OK; B7 미부착 |
| `/erp/orders/2732` | **Yes (B5 contract)** | 0.922 *(302 첫 홉)* | **302 + `Location` → `/edit/2732?…erp-beta…`** (`legacy_redirect_contract_ok: true`). 전체 문서 타이밍은 `/edit/2732?open=erp-beta` 행 참고. |

### Tier C / E (representative)

| Path | Smoke OK | full_reload (s) | Notes |
|------|----------|-----------------|-------|
| `/erp/shipment-settings` | **Yes** | 1.261 | ERP 출고 설정; B7 미부착 |
| `/map_view` (if reached) | — | — | not visited this session |
| `/regional_dashboard` etc. | — | — | optional per capacity |

### 5.1 Duration / header gap

§4 하네스로 **대부분** 채움. **`/erp/orders/<id>`** 는 **302 계약** 행으로 별도 필드 — 전체 문서 HTML 타이밍은 **`/edit/<id>?open=erp-beta`** 행과 동일 스코프로 보면 됨.

### 5.2 G1 shared-layout — HTTP `g1_shared_layout` (2026-04-17)

전 경로·수치는 **`2026-04-17-ept-b8-staging-http-evidence.json`** 의 `g1_shared_layout` — 예: `/` **2.346** s, `/trash` **1.792** s, `/metropolitan_dashboard` **3.601** s (모두 200).

---

## 6. Procedure — navigation modes (for human or gstack browse)

1. **Full reload:** F5 or address bar Enter on each primary URL; record TTFB / load if DevTools Network export attached.
2. **Cold:** New private window or clear site data once; visit tab A then tab B first time — record shell swap latency (runtime-shell).
3. **Warm:** Repeat click between two primary tabs without reload; expect LRU / prefetch hit path.
4. **Primary ↔ subordinate:** From `/erp/dashboard`, navigate to a Tier B link; **Back** and shell tab again; verify URL + `#main-content` parity (no duplicate full page load if shell active).

### 6.1 Session status (2026-04-17)

- **Full navigation smoke:** all **primary 9** URLs opened via address-bar navigation; each **mainFrame 200** (MCP, 이전 세션).
- **HTTP harness (쿠키 세션, 재캡처):** primary 9 **full/warm** + **B7(대시보드·출고·AS)** + Tier B/C + **`g1_shared_layout`** — §4·§5·§4.4·§5.2; **근거:** `docs/harness/evidence/2026-04-17-ept-b8-staging-http-evidence.json`.
- **Playwright (로그인 env, 동일 날):**
  - `erp_shell_tab_swap`: **click → fragment 응답 ~1699.89 ms** (`…/erp/measurement?view=fragment`) — `2026-04-17-ept-b8-browser-erp_shell_tab_swap.json` (LCP 아님).
  - `g1_document_nav`: **layout-global-nav → `/trash` full 문서 ~3108.88 ms** — `…-g1_document_nav.json`.
  - `primary_subordinate_roundtrip`: **Back → `/erp/dashboard` ~676.81 ms** (`navigation_entry_last.type`: `back_forward`) — `…-primary_subordinate_roundtrip.json`.
  - `navigation` `/erp/dashboard`: **FCP startTime ~2164 ms** (first-contentful-paint), navigation duration ~2246 ms — `…-navigation-dashboard.json` (로그인 후 첫 문서 로드; shell 탭 클릭과 동일 아님).
- **Warm/prefetch signal:** fragment `?view=fragment` **200** — §4.1 참고; **cold 행별** 표는 여전히 미완.
- **Remaining:** **Cold(행별)**, **shell 탭 전용 LCP**, **왕복 HAR** — §6.3–6.4.

### 6.3 Click-to-paint / Performance API (browser-only)

하네스는 **서버 왕복**만 측정한다. **click-to-first-meaningful-content** 는 다음 중 하나로 확보한다.

1. Chrome DevTools → **Performance** — shell 탭 클릭 ~ `#main-content` 안정 시점까지 녹화, **프레임/롱태스크** 스크린샷을 run record 부록에 첨부하거나 요약 ms 기입.
2. 콘솔: 탭 클릭 직후 `performance.mark('tab')` … 스왑 후 `performance.measure(...)` (인라인 스니펫은 한 세션에서만 사용; 결과 값을 §4 표 **Notes**에 기록).

**2026-04-17 자동 캡처 (부분):** `erp_shell_tab_swap` → **fragment fetch** ms; `navigation`+`/erp/dashboard` → **문서** FCP·navigation (shell 탭 클릭과 **다른 이벤트**). **LCP** 별도 항목은 아직 없음.

### 6.4 Primary ↔ subordinate round-trip (측정)

**권장:** HAR 한 번에 `dashboard` → Tier B 링크 → **Back** → 동일 primary 탭 재선택까지 포함. 스크립트 단독으로는 히스토리/스크롤 복원을 재현하지 않으므로 **수동 HAR** 또는 gstack browse 시나리오가 정합에 유리하다.

**보조 (자동화):** `python tools/harness/ept_b8_staging_browser_metrics.py --scenario primary_subordinate_roundtrip [--order-id 2732]` — 측정값은 **`back_to_dashboard_ms`** (full document `go_back`); **shell 탭 클릭·fragment swap**과 동일하지 않음.

---

## 7. Shortfall taxonomy (when metrics miss target)

| Tag | When to use |
|-----|-------------|
| `HTML` | Response bytes / DOM weight; compare transfer size |
| `query` | DB time in logs; slow ORM (defer rewrite to register) |
| `render` | High `X-FOMS-EPT-B7-RENDER-MS` or server CPU on Jinja |
| `asset` | CSS/JS blocking waterfall; 404 / slow static |
| `prefetch miss` | Cold path; LRU miss; hover not warmed |

---

## 8. Hard stop (compliance)

- **Do not** mark this run record **closed / complete** until **staging (or prod-like) authenticated evidence** includes **filled duration columns** (or attached DevTools/HAR), **B7 headers** where required, and **§6 modes** — or items are **waived** with approver and date.
- **Current (2026-04-17):** §4·§5·§5.2 **숫자 갱신** + **HTTP JSON** + **Playwright 4종 JSON** + **Railway ID(§4.3, 기존)**. **미완:** primary 9 **Cold 열**, **shell 전용 LCP**, **왕복 HAR**, **Before/After 배포 쌍** 엄격화, **G2** 네트워크 관찰(선택). **B8 최종 closeout / EPT-B9**는 상위 계획 §4.8 체크리스트와 대조 후 결정.
- **Do not** reverse B7 §Deferred without new SPEC-grade rationale.
- **Do not** merge semantic-breaking “fixes” to hit numbers.

---

## 9. GDM review checkpoint (when staging evidence exists)

**Gate:** Execute only **after** B8 acceptance criteria (including §6 Performance + B7 header capture) are met per plan. **EPT-B9** is **out of scope** until then.

- [ ] Local §3 still green on latest `HEAD`.
- [ ] §4 primary 9 table filled for before/after deploy **including** duration + B7 where applicable.
- [ ] §5 inventory smoke representative set complete **including** timing notes.
- [ ] §6 modes exercised at least once each **with** measured rows.
- [ ] §7 used if any primary metric regresses vs B1 baseline (`ept-b1` §2 table) or project target.

---

*Next: optional HAR for Cold/왕복/click-to-paint; 상위 계획 §4.8·`AI_STATUS`·`ARCHIVE_INDEX` sync; **EPT-B9** only after B8 closeout.*
