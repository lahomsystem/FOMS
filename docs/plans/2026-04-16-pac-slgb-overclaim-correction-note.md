# SLG-B2 / SLG-B7 overclaim correction note (PAC)

> Date: 2026-04-16  
> Authority: `docs/plans/2026-04-16-strict-final-canonical-tree-post-audit-correction-plan.md`

## Overturned claims

### SLG-B2 — `templates/partials/http_errors` as success path

Prior run records treated introducing `templates/partials/http_errors/*.html` as compatible with the “no `templates/errors`” closeout. **PAC reverses that:** global 404/500 must not be owned by Jinja templates under `templates/partials/http_errors/` (see spec decision lock §3.2). Final owner is **inline HTML** from `foms/platform/http.py` only.

### SLG-B7 — optional full `pytest tests -q`

Prior closeout allowed strict surface + clean-room without mandating full suite green. **PAC locks:** final closeout requires **`pytest tests -q` green** and clean-room **`-RunFullPytest`** (plan §3.4, §5.6).

## Replacement proof

- PAC-B3 removes `render_template("partials/http_errors/...")` and deletes `templates/partials/http_errors/`.
- PAC-B5 records full-suite + clean-room with `-RunFullPytest` as the authoritative closeout bundle.
