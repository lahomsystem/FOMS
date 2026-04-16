# PTC-B6 — `runtime/common` code exactness (run record)

## Scope

- File-by-file keep/move/merge decisions for `static/js/runtime/*` and `foms/services/common/*` per plan §4.5.
- This tranche: **documentation of decisions** + existing `test_ptc_physical_exactness.py` inventory gates (no mass moves — would require import/template churn).

## Delivered

- `docs/context/PTC_RUNTIME_COMMON_INVENTORY.md` — per-file **keep** rationale; `business_calendar.py` **explicit exception** tied to rebaseline item 16.

## Verification

- `pytest tests/contracts/runtime/test_ptc_physical_exactness.py -q` (inventory tests).

## GDM

**High = 0, Medium = 0** — inventory matches §4.5 ledgers; no rationale-free keep.
