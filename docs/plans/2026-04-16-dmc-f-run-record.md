# DMC-F — Dashboard micro-cache 1:1 plan parity (run record)

**계획서:** `docs/plans/2026-04-16-dashboard-micro-cache-execution-plan.md`  
**갭 동결:** `docs/plans/2026-04-16-dmc-f1-gap-freeze.md`  
**F7 로컬 증거:** `docs/plans/2026-04-16-dmc-f7-local-evidence.md`

## 구현 요약 (코드)

| 영역 | Slice / 동작 |
|------|----------------|
| Orders | `summary_counts`, `attachment_assignee_maps`, **`order_detail_payload_assembly`** (`build_order_detail_payload_map`, TTL `TTL_PAYLOAD_ASSEMBLY`) |
| Measurement | **`measurement_panel_assembly`** (DTO: `panel_summary_stat_cards`, `panel_row_ids`, `panel_fallback_supplement_ids`), **`measurement_product_items_build`** (`product_items_by_id`, `main_table_fallback_row_ids`) |
| Shipment | **`panel_aggregates`**, **`shipment_panel_derived_template_payloads`** (`construction_panel_dates`, `remaining_panel_dates`); 테이블 ORM rows 비캐시 (§3.1.2) |
| 공통 | `get_or_compute_dashboard_slice` — **info** 로그: `result=hit|miss|bypass`, **`compute_ms`** (히트 시 0) |

## 검증 (2026-04-16 실행)

- `python -c "import app; print('APP_OK')"` → `APP_OK`
- `python tools/harness/verify_result.py --json` → `success: true`
- `pytest tests/domains/test_dashboard_cache.py tests/domains/test_dashboard_micro_cache_http_fallback.py tests/domains/test_erp_order_detail_preload.py` → green
- `pytest tests/domains/test_erp_order_detail_preload.py::test_erp_dashboard_includes_preloaded_order_detail_payload tests/domains/test_erp_measurement_mobile_render.py tests/domains/test_erp_mobile_layout_and_shipment.py` → green

## 미완 (계획 §4.5 / §5 일부)

- Railway·prod에서 **HTTP latency** before/after 및 **원문 `[DashCache]` 로그** — `docs/plans/2026-04-16-dmc-f7-railway-evidence.md`에 운영자 캡처 필요 (`DMC-C2`는 CLI 미인증 시 blocked). 로컬 pytest로 대체 불가.

## 후속 closeout 기록

- `docs/plans/2026-04-16-dmc-c-closeout-run-record.md` — DMC-C1~C5 요약 (local green, Railway pending).

## 이전 문서

- DMC-B6 시점 기록: `docs/plans/2026-04-16-dmc-b6-run-record.md` (본 F 트랜치에서 slice·로그·증거 범위 확장)
