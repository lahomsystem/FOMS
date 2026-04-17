# EPT-B5 — Subordinate / detail / legacy / descendant shell contract (run record)

**Status:** completed (2026-04-17)  
**Authoritative with:** `docs/specs/2026-04-17-erp-shell-fragment-contract_SPEC.md`, B1–B4 (do not redo R0–B4).

## Scope (locked)

### In

- **Tier B (B1 §8.2)** — 필수 subordinate / legacy:
  - `/erp/drawing-workbench/<int:order_id>` — list route만 B4; **detail** 본 배치.
  - `/edit/<int:order_id>` — GET 렌더에 `view=fragment|critical|heavy` + shell 헤더 계약 (POST/redirect/JSON 경로 변경 없음).
  - `/erp/orders/<int:order_id>` → `edit` + `open=erp-beta` 레거시 리다이렉트 — 동작·상태코드·쿼리 보존 검증.
- **Tier C (B1 §8.3)** — inventory 명시 descendant:
  - `/erp/shipment-settings` — `shipment/layout` 기반; body partial + dual-mode (B3/B4 패턴).
  - `/map_view` — **standalone 전체 HTML** 템플릿(`measurement/map_view.html`). `#main-content` 셸과 구조가 다름 → 본 배치에서는 **fragment 본문 분리 없이** 문서·run record에 **근거 기반 판정**으로 고정: 서버 핸들러는 기존 `render_template` 유지, **shell+view 요청이 와도 full document** 응답(헤더 계약 미적용). 클라이언트 `FRAGMENT_READY` 비포함으로 **fetch 스왑 대상 아님** (기존과 동일).

### Out

- Primary 9 `ERP_FRAGMENT_READY_PATHS` / `runtime-shell.js` 목록 **변경 금지**.
- DB migration / KPI·권한·필터 의미 변경.
- `map_view` 전면 레이아웃 통합(후속 배치).

## Acceptance

- Detail / edit GET / shipment-settings: `get_erp_shell_view_mode` + `wants_erp_shell_tab_body` + `apply_erp_shell_fragment_headers`; `view=fragment`+shell 시 본문 슬라이스 + `X-FOMS-ERP-FRAGMENT` / `X-FOMS-ERP-FRAGMENT-TIER`; critical/heavy = fragment 본문 동일(B3/B4).
- `view=fragment` **without** shell → full document (JS-off).
- 레거시 `GET /erp/orders/<id>` → `302`, Location에 `/edit/<id>` 및 `open=erp-beta` 유지.
- `map_view`: full document 유지; 테스트로 GET 200 + 위 판정 문서화.
- pytest + 문서(SPEC §보강 선택) + `ARCHIVE_INDEX` + 계획 §4.5 정합.

## Hard stop

- Primary 9 튜플·클라이언트 fetch 목록 변경.
- `map_view`를 근거 없이 제외만 하고 문서화 안 함.
- edit POST·redirect·XHR 응답 경로 깨뜨리기.
- subordinate fragment에 스크립트가 layout `{% block scripts %}`에만 있어 **의도적으로** 스왑 불가인 경우, **fetch 대상이 아님**을 전제로 본문만 분리(기존 전체 로드 UX 유지).

## Implementation notes

- `templates/drawing/workbench_detail.html` + `workbench_detail_fragment.html` → `drawing/partials/workbench_detail_body.html`.
- `templates/orders/edit_order.html` + `edit_order_fragment.html` → `orders/partials/edit_order_body.html` (스크립트는 `edit_order.html`의 `{% block scripts %}` 유지).
- `templates/shipment/settings.html` + `settings_fragment.html` → `shipment/partials/settings_body.html`.
- `foms/api/erp_map.py` `map_view`: docstring으로 B5 판정 명시.

## Verification (recorded)

```text
python -c "import app; print('APP_OK')"
python tools/harness/verify_result.py --json
pytest tests/domains/test_erp_shell_fragment_contract.py -q
```

**Result:** 41 passed (EPT-B5 케이스 포함).

## GDM super hard review

- Diff vs SPEC, B1 inventory Tier B/C; primary 상수 미변경; 레거시 리다이렉트 스모크.
