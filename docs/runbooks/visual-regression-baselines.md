# Visual regression baselines (Linux SSOT)

## Problem

CI runs on **Ubuntu**; dev baselines were under `baseline/` (Windows captures). Same PNG + different OS → ~2–5% pixel diff → permanent FAIL at threshold `0.001`.

## Layout

| Path | Role |
|------|------|
| `tests/visual/baseline/linux/` | **CI compare SSOT** (12 PNG) |
| `tests/visual/baseline/win32/` | Windows local dev |
| `tests/visual/artifacts/` | Failure diffs (gitignored, CI artifact) |

Manifest: `VISUAL_BASELINE_NAMES` in `tests/visual/conftest.py`.

## Refresh Linux baselines

### GitHub Actions (recommended)

1. **Auto-seed on push to `deploy`** when `linux/` is incomplete — workflow `visual-baseline-linux.yml`
2. **Manual**: Actions → *Visual baseline (Linux)* → Run workflow

Commit message from bot includes `[skip ci]` to avoid infinite loops.

### Local Windows

```powershell
cd "C:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"
$env:DATABASE_URL = "sqlite:///tests/visual/visual_local.sqlite"
python -m pytest tests/visual/ --update-snapshots -q
```

Writes to `baseline/win32/` only.

## UI change checklist

1. Implement CSS/JS/template change
2. Run Linux baseline refresh (workflow or Ubuntu)
3. Commit `baseline/linux/*.png` in same PR or immediate follow-up
4. CI `visual` job must pass at `VISUAL_PIXEL_DIFF_THRESHOLD=0.001`

## Related

- `tests/visual/conftest.py` — compare, diff artifacts, CI gate
- `.github/workflows/ci.yml` — visual job + diff artifact upload
