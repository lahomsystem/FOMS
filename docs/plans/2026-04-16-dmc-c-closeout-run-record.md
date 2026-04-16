# DMC-C — Dashboard micro-cache 최종 마감 (local + docs sync)

**Authoritative plan:** `docs/plans/2026-04-16-dashboard-micro-cache-execution-plan.md`  
**선행:** `docs/plans/2026-04-16-dmc-f-run-record.md`, `docs/plans/2026-04-16-dmc-f7-local-evidence.md`

## DMC-C1 — Local truth re-verify (2026-04-16)

| 검증 | 결과 |
|------|------|
| `python -c "import app; print('APP_OK')"` | `APP_OK` |
| `python tools/harness/verify_result.py --json` | `success: true` |
| `pytest tests/domains/test_dashboard_cache.py tests/domains/test_dashboard_micro_cache_http_fallback.py tests/domains/test_erp_order_detail_preload.py -q` | **15 passed** |
| `git diff HEAD -- migrations/ templates/` | **변경 없음** (스키마·템플릿 구조 diff 없음) |

**코드 요약 (변경 없음 재확인):** `dashboard_cache.py`; orders `order_detail_payload_assembly`; measurement `measurement_panel_assembly`, `measurement_product_items_build`; shipment `panel_aggregates`, `shipment_panel_derived_template_payloads`; `[DashCache] ... compute_ms`.

## DMC-C2 — Railway / prod-like evidence

**상태:** `BLOCKED` — 로컬 `railway` CLI 미인증 (`Unauthorized`). 운영 로그·p50/p95는 **저장소에 추정 삽입 없음**.  
**후속:** `docs/plans/2026-04-16-dmc-f7-railway-evidence.md`에 운영자가 원문 로그를 붙인 뒤 계획서 §4.5·§5 Railway 항목을 `[x]`로 전환.

## DMC-C3 — Docs sync

- 본 run record 신규.
- `2026-04-16-dmc-f7-railway-evidence.md` 신규 (PENDING 템플릿만, 수치 없음).
- `AI_STATUS` — DMC-F/C local truth·Railway pending 반영.
- 계획서 §4.5·§5 — Railway 실측 행은 **증거 없이 [x]로 바꾸지 않음** (의미 변경 없음).

## DMC-C4 — Final GDM audit (요약)

|Reviewer|결과|
|--------|-----|
| Semantic-preservation | 코드 변경 없음(문서만); 로컬 테스트 green — **OK** |
| Ops-evidence | Railway 원문 미수집 — **Medium 남음** (운영 증거 pending) |
| Docs-sync | plan / local evidence / 본 record 정합 — **OK** (Railway 행은 의도적 [ ]) |

**종합:** **Full operational closeout 불가** (Railway 증거 미첨부). **Local implementation + test closeout** 가능.

## DMC-C5 — Commit-ready (권장 스테이징 범위)

워킹 트리에 DMC 무관 변경(예: `.claude`, 백업 삭제, 기타 docs)이 섞일 수 있음. **Dashboard micro-cache tranche만** 커밋하려면 예시:

- `foms/services/common/dashboard_cache.py`
- `foms/web/orders/dashboard.py`, `foms/web/measurement/dashboard.py`, `foms/web/shipment/dashboard.py`
- `foms/api/files/direct_upload.py`, `order_routes.py`, `foms/api/drawing/*.py`, `erp_orders_structured.py`, `quest.py`, `foms/services/order_date_sync.py`
- `tests/domains/test_dashboard_cache.py`, `test_dashboard_micro_cache_http_fallback.py`
- `docs/plans/2026-04-16-dashboard-micro-cache-execution-plan.md`, `dmc-*`, `dmc-c-closeout-run-record.md`, `dmc-f7-railway-evidence.md`, `ARCHIVE_INDEX.md`, `AI_STATUS.md`, `AI_CHANGELOG.md` (필요 시만)

커밋 메시지는 UTF-8 파일 + `git commit -F` (Win11 규칙).
