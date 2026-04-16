# PTC workspace hygiene (PTC-B5 / plan §4.4)

## Contract

Recursive `__pycache__` scans **ignore** `node_modules/`, `venv/`, `.venv/` (third-party or env noise; not FOMS Python bytecode).

Forbidden at **repo root** (and repo-wide for `__pycache__` when using full cleanup):

| Residue | Rule |
|--------|------|
| `.gstack/` | absent at final audit |
| `.pytest_cache/` | absent at final audit |
| `.tmp_strict_tree_verify/` | absent at final audit (clean-room worktree scratch) |
| `__pycache__/` | absent at final audit (use recurse cleanup) |
| `*.db`, `*.dump` at repo root | absent |

Probe: `tools/harness/ptc_workspace_hygiene_probe.ps1`  
Optional full tree pycache: `-RecursePyCache`

## Cleanup sequence (final closeout)

1. Run tests if needed (`pytest tests -q`). This may recreate `.pytest_cache/`.
2. Run cleanup:
   ```powershell
   cd "C:\path\to\FOMS"
   powershell -NoProfile -File tools\harness\ptc_workspace_cleanup.ps1 -RecursePyCache
   ```
3. Re-run probe until exit code 0:
   ```powershell
   powershell -NoProfile -File tools\harness\ptc_workspace_hygiene_probe.ps1 -RecursePyCache
   ```

## Optional: keep pytest cache outside the repo

For a session, before pytest:

```powershell
$cache = Join-Path $env:USERPROFILE "FOMS-runtime\pytest-cache"
New-Item -ItemType Directory -Force -Path $cache | Out-Null
$env:PYTEST_ADDOPTS = "--override-ini=cache_dir=$cache"
python -m pytest tests -q
```

## `.gstack/`

Skills may create `.gstack/` under the repo when running certain flows. It is gitignored but must not remain for PTC workspace exactness. Delete via cleanup script or remove the folder manually before audit.
