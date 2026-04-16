# DMC-F1 Gap freeze (plan vs code)

**Authoritative plan:** `docs/plans/2026-04-16-dashboard-micro-cache-execution-plan.md` §1.2 / §3.1.1.

## Frozen gaps (file / remedy)

| Area | Gap | Remedy |
|------|-----|--------|
| Orders | `attach_order_detail_payloads` full compute every request | Cache `build_order_detail_payload_map` as slice `order_detail_payload_assembly`, TTL `TTL_PAYLOAD_ASSEMBLY`, fingerprint = user + filters + page + sorted order ids |
| Measurement | Slice names / DTO vs plan bullets implicit | Panel compute returns explicit JSON keys: `panel_summary_stat_cards`, `panel_row_ids`, `panel_fallback_supplement_ids`; product slice returns `product_items_by_id` + `main_table_fallback_row_ids`; slice renames per plan |
| Shipment | Only `panel_aggregates`; template lists built uncached | Add slice `shipment_panel_derived_template_payloads` for `construction_panel_dates` + `remaining_panel_dates` after `selected_date` finalization; fingerprint includes aggregate key suffix + worker_settings hash + date filters |
| All | hit/miss only | `get_or_compute_dashboard_slice` logs `compute_ms` (0 on hit, measured on miss/bypass) |
| Docs | §4/§5 checkboxes stale | Sync after implementation; run record + F7 evidence |

## Non-goals (unchanged)

- ORM rows in Redis; template/HTML cache; migration/schema/template structure edits.
