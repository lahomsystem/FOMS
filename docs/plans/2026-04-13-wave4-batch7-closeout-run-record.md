# Wave 4 Batch W4-B7 — High-risk defer register + closeout (full)

> **batch ID:** W4-B7  
> **risk axis:** docs / handoff  
> **closeout type:** **full** — W4-B2~B6 code batches 정상 완료 후 실행  
> **실행일:** 2026-04-14

## Scope lock

- **허용:** 본 run record, `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md` §5 참고 자료, `docs/ARCHIVE_INDEX.md`, `docs/AI_STATUS.md` 갱신.  
- **금지:** runtime, blueprints, normative spec 본문 변경.

## Wave 4 execution summary

| Batch | 결과 |
|-------|------|
| W4-B0 | Readiness + queue lock (pilot `cs`) |
| W4-B1 | Pilot contract freeze (`cs`) |
| W4-B2 | `foms/web/cs/completion_dashboard` + legacy shim |
| W4-B3 | `templates/cs/completion_dashboard.html` + legacy extends |
| W4-B4 | Dashboard winner **`production`** (vs `construction`) |
| W4-B5 | `foms/web/production/dashboard.py` + legacy shim |
| W4-B6 | `templates/production/*` + legacy thin wrappers |

## High-risk defer register

| Surface | Current owner | Why not Wave 4 mainline | Next wave | Unblock condition | Shell/shared hotspot |
|---------|---------------|-------------------------|-----------|-------------------|----------------------|
| drawing | `apps.erp_drawing_workbench` | 2-route cluster + shared drawing partials | Wave 4+ / Wave 5 | page-first contract freeze + shell inventory | `erp_dashboard_scripts_drawing` 등 |
| shipment-dashboard | `apps.erp_shipment_page` | Tier 3 giant template + dedicated static | Wave 5+ | dual-lane 분리 확정 | layout + heavy JS |
| shipment-settings | `apps.api.erp_shipment_settings` | HTML + API dual-lane | Wave 5+ | settings/API 경계 정리 | settings 폼 + API |
| as | `apps.erp_as_page` | giant dashboard | Wave 5+ | scope 승인 | editor/map |
| construction | `apps.erp_construction_page` | **W4-B4 loser** — 의도적 defer (production 승자 소비) | **Wave 4 continuation** | `foms/web/construction` + template namespace 배치 승인 | mine 필터 / 시공 큐 |
| main ERP shell | `apps.erp_dashboard` + layout partials | Wave 4 freeze list | Wave 5 | shell chunk governance | `layout`, `erp_beta_js` |
| regional dashboards | `apps.dashboards` + `regional_dashboard.html` | freeze | Wave 5+ | 별도 검토 | regional shell |

## W4-B4 loser disposition

| Context | disposition |
|---------|-------------|
| construction | **deferred** — 다음 dashboard canonicalization 후보로 shortlist 상단 |

## spec §2.9 example-context disposition matrix (Wave 4 종료 시점)

| Context | disposition |
|---------|-------------|
| CS (completion) | **in-scope** — canonical `foms/web/cs` + `templates/cs/` |
| production | **in-scope** — canonical `foms/web/production` + `templates/production/` |
| construction | **deferred** — loser; 다음 continuation |
| drawing | **deferred** |
| shipment-dashboard | **deferred** |
| shipment-settings | **deferred** (dual-lane 분리) |

## Wave 4 continuation shortlist (ordered)

1. `construction` — `foms/web/construction` + `templates/construction/`  
2. `drawing` — detail+dashboard cluster 정리  
3. `shipment-dashboard` / `shipment-settings` — 분리 유지하며 페이지 슬라이스  
4. `as` — 대형 대시보드

## Wave 5 boundary note

- Shared shell: `layout.html`, `erp_dashboard.html`, `erp_beta_js.html`, `erp_sub_nav`, `erp_mobile_shell`, `regional_dashboard.html` — **Wave 4에서 비개입 유지**; Wave 5 large-file / shell governance와 연계.
- Giant inline in `production/partials/scripts.html` 등 — **Wave 5** decomposition 후보.

## Partial closeout reason

- **해당 없음** — early stop 없음.

## Direction Lock (10문항)

| # | 답 | 한 줄 근거 |
|---|-----|------------|
| 1 | yes | Wave 4 SoT가 cs·production에 명확히 잠김 |
| 2 | yes | defer 레지스터에 merge-back 후보 명시 |
| 3 | yes | 문서-only |
| 4 | yes | continuation은 chunk 단위로 나열 |
| 5 | yes | 본 배치 파일 증가 없음 |
| 6 | N/A | |
| 7 | N/A | 본 배치는 AI_STATUS·ARCHIVE만 보강 |
| 8 | yes | |
| 9 | yes | |
| 10 | yes | 기능 변경 없음 |

## Verification

| 검사 | 결과 |
|------|------|
| docs-only | ✅ |
| defer row에 next wave + unblock | ✅ |
| Wave 5 vs continuation 분리 | ✅ |

## Spec / archive reference

- `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md` §5에 Wave 4 run record 목록 추가됨.
- `docs/ARCHIVE_INDEX.md`에 Wave 4 엔트리 추가됨.

## Triple-audit follow-up (post closeout, engineering)

W4-B7 이후 병렬 리뷰에서 지적된 **`foms/web/production/dashboard.py` 생산 대시보드 집계**를 정리함 (Wave 4 범위: 동일 canonical 파일 내 국소 수정).

| 이슈 | 조치 |
|------|------|
| KPI에 `measurement_d4` / `construction_d3` 미반영 | `kpis` 루프에서 해당 플래그 증가 |
| 프로세스 맵 배지(imminent/overdue)가 현재 페이지 50건만 반영 | 필터 전체 `kpi_rows`와 동일 집합으로 집계 |
| `order_by(None)` 체인 뒤 페이지 목록 정렬 불명확 | `total_orders = len(kpi_rows)`로 정렬 제거 COUNT 제거; 페이지 로드 전 `order_by(created_at.desc())` 복구 |
| 단일 뷰 함수 과다 길이 | 헬퍼 분리 + `PRODUCTION_DASHBOARD_PAGE_SIZE` 상수 |

검증: `python -c "import app; print('APP_OK')"`, `python tools/harness/verify_result.py --json`, `pytest tests/test_foms_namespace_imports.py tests/test_menu_config.py`.
