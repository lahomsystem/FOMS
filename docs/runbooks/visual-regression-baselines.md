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

### GitHub Actions (수동만)

1. **PNG 회귀 CI는 비활성** — `ci.yml`에는 Playwright visual job 없음. UI 게이트는 `test_p1_mockup_*` 구조 테스트.
2. **linux baseline 갱신(선택)**: Actions → *Visual baseline (Linux)* → `workflow_dispatch`

Bot 커밋 메시지는 `[skip ci]`를 포함해 무한 루프를 막는다. `deploy` branch protection이 bot push를 막으면 artifact를 받아 수동 커밋한다.

### Local Windows

```powershell
cd "C:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"
$env:DATABASE_URL = "sqlite:///tests/visual/visual_local.sqlite"
python -m pytest tests/visual/ --update-snapshots -q
```

Writes to `baseline/win32/` only.

## UI change checklist

정본 워크플로는 **`docs/guides/PRE_PUSH_SMOKE.md` § UI 검증 정책** 을 따릅니다.

1. Implement CSS/JS/template change (`static/css/`, `static/js/`, `templates/`)
2. **Pre-push:** `pre_push_smoke.ps1` (구조 테스트 `test_p1_mockup_*` 포함)
3. **PNG 회귀(선택, UI 안정기):** win32 `--update-snapshots` → `pre_push_smoke.ps1 -Visual`
4. **linux SSOT(선택):** `visual-baseline-linux.yml` workflow_dispatch

## Related

- `tests/visual/conftest.py` — compare, diff artifacts, CI gate
- `.github/workflows/ci.yml` — `test` job 구조 테스트만 (PNG visual job 없음)
- `.github/workflows/visual-baseline-linux.yml` — 수동 linux baseline refresh
