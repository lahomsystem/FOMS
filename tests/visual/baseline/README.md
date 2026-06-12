# Visual regression baselines (P0-00D)

| Directory | Platform | Role |
|-----------|----------|------|
| `linux/` | Ubuntu (GitHub Actions) | **CI SSOT** — compare target for `visual` job |
| `win32/` | Windows dev | Local Playwright captures |
| `darwin/` | macOS | Optional local captures |

Do not store PNGs in this root folder. `resolve_baseline_dir()` in `conftest.py` selects a platform subdir.

## Refresh Linux baselines (canonical)

1. Actions → **Visual baseline (Linux)** → Run workflow, or
2. Push to `deploy` triggers auto-seed when `linux/` is incomplete (see `.github/workflows/visual-baseline-linux.yml`).

Local (Windows): `pytest tests/visual/ --update-snapshots` writes to `baseline/win32/`.
