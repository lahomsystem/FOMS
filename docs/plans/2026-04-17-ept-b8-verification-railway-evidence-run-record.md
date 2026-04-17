# EPT-B8 — Verification + Railway / staging evidence (run record)

**Status:** **in progress** — **local verification gate complete**; **staging `session_staging` + `ept_b8_staging_http_evidence.py` 로 primary 9 행 full/warm(s) + B7(대시보드·출고·AS) 확보** (2026-04-17). **`/erp/orders/<id>`** 는 하네스가 **302 + Location** 만 검증(`allow_redirects=False`) — 리다이렉트 추적 시 로그인 URL로 잘못 수렴하던 오탐 제거(도구 2026-04-17 갱신). **Railway deployment ID** — §4 **After** / §4.3 (`railway deployment list`, 2026-04-17). **여전히 PENDING:** per-path **Cold** 열(또는 HAR), **click-to-paint / Performance API**, **primary↔subordinate 왕복 HAR**.  
**Authoritative inputs:** `docs/specs/2026-04-17-erp-shell-fragment-contract_SPEC.md`, B6/B7 run records, `docs/plans/2026-04-17-ept-b1-baseline-contract-run-record.md` §8 (inventory v2).  
**Explicit non-goals:** Re-open B7 §Deferred (DOM/row on-demand without semantic-preserving proof); query rewrite in this batch; code changes for performance unless fixing evidence collection only.

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
| Browser-like regression | **Partial** — pytest contract regression **done**; human/browser Performance evidence **PENDING** | **Partial** — HTTP 하네스 **full/warm(s)** + **B7 일부**; **click-to-paint** 는 **PENDING** |
| Primary 9 before/after | Template: §4 | **Partial** — §4 표 **full/warm + B7(3 route)** + **After Railway deployment ID**; **Before** baseline·**Cold 열** 은 **PENDING** |
| Subordinate/descendant inventory before/after | Template: §5 | **Partial** — Tier B/C **full_reload(s)**; `/erp/orders/<id>` 는 **302 B5 계약** 하네스로 정합(§5) |
| full / cold / warm / primary↔subordinate comparison | Procedure: §6 | **Partial** — §4 **full/warm**; **Cold(행별)·왕복** 은 **PENDING** |
| click-to-paint (or equivalent) | N/A locally | **PENDING** |
| Miss taxonomy filled when below target | N/A until staging numbers | **Required** when comparing |

---

## 3. Local verification gate (executed)

**Date:** 2026-04-17 (session). **Environment:** developer workstation, Windows, local DB.

| Command | Result |
|---------|--------|
| `python -c "import app; print('APP_OK')"` | `APP_OK` |
| `python tools/harness/verify_result.py --json` | `"success": true` |
| `pytest tests/domains/test_erp_shell_fragment_contract.py tests/domains/test_erp_runtime_shell_js_contract.py tests/domains/test_ept_b7_profile.py -q` | **47 passed** |

**Interpretation:** Shell fragment contract, runtime-shell JS contract, and EPT-B7 static/helper tests pass — **no code regression** detected by these suites. This satisfies the **automated** part of “APP_OK / verify_result / focused pytest / browser-like regression” only; **browser Performance / Railway RUM evidence** remains **out-of-band** until captured on staging.

---

## 4. Primary 9 — before/after evidence template (staging)

**Base URL:** `https://lahom-dev.up.railway.app`  
**HTTP harness capture (2026-04-17):** `tools/harness/ept_b8_staging_http_evidence.py` — `FOMS_STAGING_COOKIE='session_staging=…'` (full document GET; `full_reload_s` = no-cache 첫 GET, `warm_second_get_s` = 동일 URL 즉시 재GET). **MCP 보조:** §4.1 타임스탬프·mainFrame 200 스모크.

| Path | Full reload (s) | Cold nav (s) | Warm nav (s) | Notes |
|------|-----------------|--------------|--------------|-------|
| `/erp/dashboard` | 3.171 | — | 3.143 | B7: `erp_dashboard`, render **199.7** ms |
| `/erp/measurement` | 3.004 | — | 1.654 | B7 미부착(뷰 정책) |
| `/erp/drawing-workbench` | 2.121 | — | 3.166 | B7 미부착 |
| `/erp/production/dashboard` | 2.323 | — | 2.444 | B7 미부착 |
| `/erp/shipment` | 1.788 | — | 1.86 | B7: `erp_shipment_dashboard`, render **404.7** ms |
| `/erp/as` | 2.12 | — | 2.159 | B7: `erp_as_dashboard`, render **183.4** ms |
| `/erp/construction/dashboard` | 2.726 | — | 2.511 | B7 미부착 |
| `/erp/completion` | 0.919 | — | 0.923 | B7 미부착 |
| `/erp/history/` | 1.022 | — | 0.924 | B7 미부착 |

**Cold 열:** primary 9별 “첫 탭 방문” cold는 하네스 한 세션으로는 분리하기 어려움 — **§4.4** `cold_nav_proxy` 참고 또는 **HAR**.  
**Before:** commit hash / deploy id: *(baseline / prior Railway deploy — not captured this session; compare to B1 run record if needed)*  
**After (repo + Railway at HTTP evidence capture):** commit **`9541bfd516a8ac3fef7fc4d293723d830a0b9ab3`** — **Railway deployment ID:** **`38ff39ed-4c80-4276-bea0-3a9560f13b14`** (SUCCESS, **2026-04-17 11:09:28 +09:00**). **CLI 맥락:** workspace `lahomsystem's Projects` → project **FOMS-DEV** → environment **production** → service **FOMS** (`railway link` 후 `railway deployment list`).

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

```text
$env:FOMS_STAGING_COOKIE = 'session_staging=<DevTools에서 복사한 값>'
python tools/harness/ept_b8_staging_http_evidence.py --base https://lahom-dev.up.railway.app --order-id 2732 --json
```

성공 시 `final_url` 은 `/erp/...` 이어야 하며, B7이 붙은 뷰는 `b7_headers` 에 키가 나온다. `final_url` 이 `/login?next=...` 이면 쿠키 형식·만료를 다시 확인한다. **`/erp/orders/<id>`** 서브키는 `legacy_redirect_contract_ok`, `redirect_location`(302 계약)을 별도로 본다 — 전체 HTML 문서 시간은 **`/edit/<id>?open=erp-beta`** 와 동일 스코프로 취급.

### 4.4 `cold_nav_proxy` (동일 하네스 실행 — 참고용)

새 `requests.Session`으로 dashboard 착륙 후 첫 측정·출고 GET만 기록(탭 cold의 **프록시**).

| Step | Elapsed (s) | B7 (if any) |
|------|-------------|-------------|
| land `/erp/dashboard` | 2.695 | (dashboard 행 참고) |
| first GET `/erp/measurement` after dashboard | 2.989 | — |
| first GET `/erp/shipment` after dashboard | 1.792 | `erp_shipment_dashboard`, render **339.8** ms |

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
| `/erp/drawing-workbench/2732` | **Yes** | 1.699 | `final_url` ERP 상세 OK; B7 미부착 |
| `/edit/2732?open=erp-beta` | **Yes** | 1.418 | ERPbeta OK; B7 미부착 |
| `/erp/orders/2732` | **Yes (B5 contract)** | *(첫 응답 ms)* | **302 + `Location` → `/edit/2732?…erp-beta…`** 를 하네스가 **리다이렉트 미추적**으로 검증(구버전: `requests` 가 후속 홉에서 `/login?next=` 로 잘못 보고 stderr 1건). JSON: `legacy_redirect_contract_ok`, `redirect_location`. |

### Tier C / E (representative)

| Path | Smoke OK | full_reload (s) | Notes |
|------|----------|-----------------|-------|
| `/erp/shipment-settings` | **Yes** | 1.254 | ERP 출고 설정; B7 미부착 |
| `/map_view` (if reached) | — | — | not visited this session |
| `/regional_dashboard` etc. | — | — | optional per capacity |

### 5.1 Duration / header gap

§4 하네스로 **대부분** 채움. **`/erp/orders/<id>`** 는 **302 계약** 행으로 별도 필드 — 전체 문서 HTML 타이밍은 **`/edit/<id>?open=erp-beta`** 행과 동일 스코프로 보면 됨.

---

## 6. Procedure — navigation modes (for human or gstack browse)

1. **Full reload:** F5 or address bar Enter on each primary URL; record TTFB / load if DevTools Network export attached.
2. **Cold:** New private window or clear site data once; visit tab A then tab B first time — record shell swap latency (runtime-shell).
3. **Warm:** Repeat click between two primary tabs without reload; expect LRU / prefetch hit path.
4. **Primary ↔ subordinate:** From `/erp/dashboard`, navigate to a Tier B link; **Back** and shell tab again; verify URL + `#main-content` parity (no duplicate full page load if shell active).

### 6.1 Session status (2026-04-17)

- **Full navigation smoke:** all **primary 9** URLs opened via address-bar navigation; each **mainFrame 200** (MCP).
- **HTTP harness:** primary 9 **full/warm(s)** + **B7** 일부 + Tier B/C **full_reload(s)** — §4 표·§5·§4.4.
- **Warm/prefetch signal:** fragment `?view=fragment` XHR **200** sequences observed between shell navigations (see §4.1) — **not** a substitute for measured cold vs warm seconds.
- **Primary ↔ subordinate round-trip:** not formally timed; Tier B paths in §5.1 reachable from same session.
- **Remaining:** **Cold(행별)**, **click-to-paint**, **왕복 HAR** — §6.3–6.4 (배포 ID는 §4 **After** / §4.3).

### 6.3 Click-to-paint / Performance API (browser-only)

하네스는 **서버 왕복**만 측정한다. **click-to-first-meaningful-content** 는 다음 중 하나로 확보한다.

1. Chrome DevTools → **Performance** — shell 탭 클릭 ~ `#main-content` 안정 시점까지 녹화, **프레임/롱태스크** 스크린샷을 run record 부록에 첨부하거나 요약 ms 기입.
2. 콘솔: 탭 클릭 직후 `performance.mark('tab')` … 스왑 후 `performance.measure(...)` (인라인 스니펫은 한 세션에서만 사용; 결과 값을 §4 표 **Notes**에 기록).

### 6.4 Primary ↔ subordinate round-trip (측정)

**권장:** HAR 한 번에 `dashboard` → Tier B 링크 → **Back** → 동일 primary 탭 재선택까지 포함. 스크립트 단독으로는 히스토리/스크롤 복원을 재현하지 않으므로 **수동 HAR** 또는 gstack browse 시나리오가 정합에 유리하다.

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
- **Current:** §4 **duration + B7(3 primary)** + §5 **대부분 timing** + **Railway deployment ID(§4.3)**. **미완:** Cold 열·왕복·click-to-paint(§6). **Not** sufficient for B8 final acceptance or GDM §9.
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

*Next: optional HAR for Cold/왕복/click-to-paint; 하네스 최신본으로 `/erp/orders/<id>`는 `legacy_redirect_contract_ok` 확인; 상위 계획 §4.8·`AI_STATUS`·`ARCHIVE_INDEX` sync; **EPT-B9** only after B8 closeout.*
