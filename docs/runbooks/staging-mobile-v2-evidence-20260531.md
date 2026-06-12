# Staging Mobile v2 Evidence — 2026-05-31

> Runbook for P1 visual/mockup gap re-verification on Railway staging (`lahom-dev`).

## Preconditions

| Variable | Value |
|---|---|
| `ERP_MOBILE_V2_ENABLED` | `true` |
| `FOMS_V3_SHELL_COHORT` | `all` (or pilot user id) |
| Base URL | `https://lahom-dev.up.railway.app` |

## Automated smoke

```powershell
powershell -NoProfile -File scripts/ops/staging_mobile_v2_smoke.ps1
powershell -NoProfile -File scripts/ops/staging_mobile_v2_smoke.ps1 -BaseUrl "https://lahom-dev.up.railway.app"
```

Expected: `foms-mobile-surfaces.css`, `foms-shell.css`, `mobile-queue-scroll.js`, `wizard-attachments.js` return HTTP 2xx.

Local (no creds):

```powershell
pytest tests/visual/test_staging_mobile_v2_assets.py -q
```

## Manual checklist (390×844)

- [ ] Login cohort user → `/erp/dashboard`
- [ ] Chip strip: 전체, **오늘**, 긴급, 미처리, **담당: {name}**
- [ ] Sort chips: 최신순, 일정순, **금액순**
- [ ] Queue card attachment thumbs (when order has image attachments)
- [ ] Infinite scroll loads next page (`mobile_chunk=1` network request)
- [ ] FAB visible; legacy `.erp-pro-header` hidden on mobile v2
- [ ] `/erp/orders/<id>/mobile` — 고객 정보, 일정, 제품(C14), 금액, attach grid
- [ ] Other ERP tabs show `foms-mobile-v2-tab-notice` with link to home

## Deploy evidence

- [ ] P1 visual layer commit `d329e300`+ on deploy branch
- [ ] `scripts/ops/verify_mobile_v2_rollout.ps1` PASS locally
- [ ] Screenshot or notes filed in cohort diary (INDEX #13)

## Known gaps (Phase 1)

- Pixel-perfect PNG baseline vs `docs/design/mockups/` — backlog
- 8-tab full mockup parity — legacy mobile partials + tab notice only
- AS modal: upload button present; dedicated camera-first capture — partial (`as_mobile_v2_camera_bar`)
