# EPT-B8 — Verification + Railway / staging evidence (run record)

**Status:** **in progress** — **local verification gate complete**; **Railway / staging / prod-like browser evidence = PENDING** (see §Hard stop below).  
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
| Browser-like regression | **Partial** — pytest contract regression **done**; human/browser Performance evidence **PENDING** | **Required** for full acceptance |
| Primary 9 before/after | Template: §4 | **PENDING** — fill after capture |
| Subordinate/descendant inventory before/after | Template: §5 | **PENDING** |
| full / cold / warm / primary↔subordinate comparison | Procedure: §6 | **PENDING** |
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

**Base URL:** `https://<staging-host>` (replace). **Session:** authenticated ERP user (role consistent with B1 baseline protocol).

| Path | Full reload (s) | Cold nav (s) | Warm nav (s) | Notes |
|------|-----------------|--------------|--------------|-------|
| `/erp/dashboard` | | | | B7: `X-FOMS-EPT-B7-*` |
| `/erp/measurement` | | | | |
| `/erp/drawing-workbench` | | | | |
| `/erp/production/dashboard` | | | | |
| `/erp/shipment` | | | | B7 headers |
| `/erp/as` | | | | B7 headers |
| `/erp/construction/dashboard` | | | | |
| `/erp/completion` | | | | |
| `/erp/history/` | | | | trailing slash |

**Before:** commit hash / deploy id: `________________`  
**After:** commit hash / deploy id: `________________`

---

## 5. Subordinate / descendant inventory — evidence template (staging)

Source: B1 §8.2–8.5. Minimum: smoke + one timing row per tier representative.

### Tier B (required subordinate)

| Path | Smoke OK | Timing notes |
|------|----------|----------------|
| `/erp/drawing-workbench/<id>` | | |
| `/edit/<id>?open=erp-beta` | | |
| `/erp/orders/<id>` (redirect) | | |

### Tier C / E (representative)

| Path | Smoke OK | Notes |
|------|----------|-------|
| `/erp/shipment-settings` | | |
| `/map_view` (if reached) | | full-document-only; shell swap N/A |
| `/regional_dashboard` etc. | | optional per capacity |

---

## 6. Procedure — navigation modes (for human or gstack browse)

1. **Full reload:** F5 or address bar Enter on each primary URL; record TTFB / load if DevTools Network export attached.
2. **Cold:** New private window or clear site data once; visit tab A then tab B first time — record shell swap latency (runtime-shell).
3. **Warm:** Repeat click between two primary tabs without reload; expect LRU / prefetch hit path.
4. **Primary ↔ subordinate:** From `/erp/dashboard`, navigate to a Tier B link; **Back** and shell tab again; verify URL + `#main-content` parity (no duplicate full page load if shell active).

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

- **Do not** mark this run record **closed / complete** until **staging (or prod-like) authenticated evidence** rows in §4–§5 are filled **or** explicitly documented as **waived** with approver and date.
- **Do not** reverse B7 §Deferred without new SPEC-grade rationale.
- **Do not** merge semantic-breaking “fixes” to hit numbers.

---

## 9. GDM review checkpoint (when staging evidence exists)

- [ ] Local §3 still green on latest `HEAD`.
- [ ] §4 primary 9 table filled for before/after deploy.
- [ ] §5 inventory smoke representative set complete.
- [ ] §6 modes exercised at least once each.
- [ ] §7 used if any primary metric regresses vs B1 baseline (`ept-b1` §2 table) or project target.

---

*Next: after staging evidence attachment, update 상위 계획 §4.8 checkboxes, `ARCHIVE_INDEX`, `AI_STATUS`, and optionally open EPT-B9.*
