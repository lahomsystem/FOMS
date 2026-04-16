# PTC-B7 — Final dual-surface closeout (run record)

> Historical note: PTC final evidence는 이후 FAG tranche에서 재감리됐다. current final exactness truth는 `docs/plans/2026-04-16-fag-b4-run-record.md`를 따른다.

## Evidence (this workspace session)

| Gate | Result | Notes |
|------|--------|--------|
| `python -c "import app; print('APP_OK')"` | OK | After edits |
| `python tools/harness/verify_result.py --json` | OK | |
| `pytest tests/contracts/runtime/foms_namespace_surface_tests.py -q` | 185 passed | |
| `pytest tests -q` | 605 passed | Includes `test_ptc_physical_exactness.py` when present |
| `tools/harness/ptc_workspace_cleanup.ps1 -RecursePyCache` then `ptc_workspace_hygiene_probe.ps1 -RecursePyCache` | OK | `node_modules` / `venv` / `.venv` / `.claude/` excluded from recursive `__pycache__` scan |
| `strict_canonical_b12_clean_room.ps1 -Ref HEAD -RunFullPytest` | OK | See FAG evidence below |

## FAG tranche evidence (historical sync before FAG-B4)

PTC-B7 원래 기록 당시 `HEAD lag warning`은 PTC 파일들이 아직 uncommitted 상태였기 때문에 발생했다.
PTC 전체 tranche는 이후 커밋되었고, FAG tranche(FAG-B1, FAG-B2)가 추가되었다.

**현재 확정 상태 (FAG-B2 이후):**

| 축 | 상태 |
|---|---|
| HEAD | `891c1a68` (FAG-B2 커밋) |
| `pytest tests -q` | **607 passed** (FAG-B1에서 2개 新 gate 추가) |
| `ptc_workspace_hygiene_probe.ps1 -RecursePyCache` | **OK** |
| `data/ops_browser_qa.db` | **부재** (FAG-B2에서 제거) |
| `static/js/wdcalculator/README.md` | **부재** (FAG-B1에서 제거) |
| `docs/context/wdcalculator-static-js-chunk-map.md` | **존재** (FAG-B1에서 생성) |

이 시점 이후 clean-room 재실행과 final exactness re-audit은 `FAG-B4`에서 current `HEAD` 기준으로 다시 수행됐다.

## Dual-spec 1:1 GDM audit

- **R1 Spec:** Controlling specs `2026-04-07-repo-structure-governance_SPEC.md` and `2026-04-13-foms-modular-monolith-rebaseline_SPEC.md` were updated in PTC-B1; no new controlling spec file was introduced.
- **R2 Physical tree:** Root allowlist + `data/` policy enforced by `test_ptc_physical_exactness.py` (must be **committed** for `HEAD` proof).
- **R3 Code / README:** FR20 README batch + `PTC_RUNTIME_COMMON_INVENTORY.md`.
- **R4 Proof:** PAC/SLG gates retained in `foms_namespace_surface_tests.py` + clean-room script; workspace probe + cleanup documented.

**Manual:** Maintainer signs off that spec wording has **no unresolved conflict** before merge to production branches.

## Hard-stop checklist (plan §6.3)

- Not claiming code closeout while spec text conflicts remain.
- Not claiming workspace green without running cleanup when residue exists.
- Not using workspace-only cleanup to hide spec/code drift.
