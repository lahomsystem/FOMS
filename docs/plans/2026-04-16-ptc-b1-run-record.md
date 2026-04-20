# PTC-B1 — Spec sync lock (run record)

> Batch: `PTC-B1` per `docs/plans/2026-04-16-strict-final-canonical-tree-physical-tree-code-convergence-plan.md`  
> Date: 2026-04-16  
> Scope: **Documentation only** — in-place dual controlling spec sync (no code moves, no proof contract edits in this batch).

## 1. Acceptance criteria (plan)

- [x] `docs/specs/2026-04-07-repo-structure-governance_SPEC.md` — §2.6 expanded with **Final root allowlist (exact set)**, `data/` + `FOMS_RUNTIME_OUTPUT_ROOT`, FR20 README homes, workspace-forbidden artifacts, dual-spec pointer to `2026-04-13` + PTC plan.
- [x] `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md` — §2.2 보충 규칙 aligned with runtime-output policy, §2.6.1 cross-ref, new **§2.2.3** FR20 README authoritative table, §2.5 PTC lock paragraph (seven categories vs §2.6.1 / §4.1).

## 2. Files touched

| Path | Change |
|------|--------|
| `docs/specs/2026-04-07-repo-structure-governance_SPEC.md` | §2.6.1–2.6.4 dual-spec lock; typo fix (「수렴」). |
| `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md` | `data/` + runtime root; §2.6.1 reference; §2.2.3 FR20; §2.5 PTC lock paragraph. |

## 3. Verification evidence (this batch)

Commands (PowerShell, repo root):

```text
python -c "import app; print('APP_OK')"
python tools/harness/verify_result.py --json
```

Result: `APP_OK`; `verify_result.py --json` → `"success": true`, `app_import.ok`: true.

**Not in scope for B1 (deferred to B2+):** `pytest tests/contracts/...`, full `pytest`, `strict_canonical_b12_clean_room.ps1`, workspace hygiene probe — per plan, proof hardening is **PTC-B2**.

## 4. GDM ultra-review loop (B1)

| Role | Finding | Severity | Status |
|------|-----------|----------|--------|
| **R1 Spec** | Dual-spec: root allowlist single source §2.6.1; `2026-04-13` §2.5 now explicitly defers final enumerated set to §2.6.1 + PTC §4.1; FR20 table matches plan §3.3/§4.2. | — | **PASS** |
| **R2 Physical-tree** | No tree mutation in B1; spec text matches plan §4.1 intent (no `apps/`/`services/`/`src/` at final root per §4.1 cross-ref). | — | **PASS** (docs-only) |
| **R3 Code-owner** | No application/package code changed. | — | **PASS** |
| **R4 Proof** | Contract tests / clean-room scripts unchanged this batch (intentional). | — | **PASS** (deferred B2) |

**GDM synthesis:** High = **0**, Medium = **0**. Batch acceptance for **spec-text sync** satisfied. Next: **PTC-B2** (proof hardening).

## 5. HEAD vs workspace

- **Committed intent:** Documentation edits above only; no unrelated revert performed.
- **Workspace:** Editor may show local untracked artifacts; B1 does not assert workspace hygiene green (PTC-B5).
