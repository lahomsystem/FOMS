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

1. **CI visual job** (`ci.yml`) — `linux/` 비어 있으면 같은 job에서 `--update-snapshots` 후 compare (자동)
2. **수동 갱신**: Actions → *Visual baseline (Linux)* → Run workflow

Bot 커밋 메시지는 `[skip ci]`를 포함해 무한 루프를 막는다. `deploy` branch protection이 bot push를 막으면 artifact를 받아 수동 커밋한다.

### Local Windows

```powershell
cd "C:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"
$env:DATABASE_URL = "sqlite:///tests/visual/visual_local.sqlite"
python -m pytest tests/visual/ --update-snapshots -q
```

Writes to `baseline/win32/` only.

## UI change checklist

정본 워크플로는 **`docs/guides/PRE_PUSH_SMOKE.md` § Visual regression 정본 워크플로** 를 따릅니다.

1. Implement CSS/JS/template change (`static/css/`, `static/js/`, `templates/`)
2. **Windows:** `pytest tests/visual/ --update-snapshots` → commit `baseline/win32/*.png`
3. **Pre-push:** `pre_push_smoke.ps1 -Visual` (exit 0)
4. Push → CI visual job refreshes `baseline/linux/` when win32 ERP PNGs are newer
5. CI `visual` job must pass at `VISUAL_PIXEL_DIFF_THRESHOLD=0.001`

## Related

- `tests/visual/conftest.py` — compare, diff artifacts, CI gate
- `.github/workflows/ci.yml` — visual job + diff artifact upload
