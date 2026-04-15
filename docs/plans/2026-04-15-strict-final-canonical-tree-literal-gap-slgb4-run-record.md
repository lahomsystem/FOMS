# SLG-B4 — Web absorption II (run record)

> 배치: `SLG-B4` (`docs/plans/2026-04-15-strict-final-canonical-tree-literal-gap-remediation-plan.md`)  
> 실행일: 2026-04-15

## 1. Scope / acceptance

- 레거시 ERP·유저·스토리지·엑셀 **중복 패키지** 제거: `foms/web/{erp,erp_as_page,erp_drawing_workbench,erp_shipment_page,user_pages,storage_dashboard,excel_import}` — 구현은 이미 `foms.platform.erp_blueprint`, `foms/web/cs/as_dashboard.py`, `drawing/workbench.py`, `shipment/dashboard.py`, `admin/{storage,excel_import}.py`에 존재.
- `/profile` → `foms/web/auth/routes.py` (`auth.profile`); 네비·관리 템플릿의 `user_pages.*` → `auth.profile` / `admin.change_logs` / `admin.security_logs`.
- §4.2 closed-set: `foms/web/channel/` 최소 패키지 추가 (allowlist의 `channel` 디렉터리 누락 보정).
- 계약 테스트: `foms.web.erp.hub`·구 `routes` 패키지 경로 제거; `cs.as_dashboard`, `drawing.workbench`, `shipment.dashboard` 기준으로 정렬.
- §4.3·§4.4 subtree drift(`chat`, `attachments_internal`, `erp_policy_internal`)는 **SLG-B5~B6** 대상 — 본 배치에서 해소하지 않음.

## 2. 증거

| 검증 | 결과 |
|------|------|
| `pytest tests/contracts/runtime/foms_namespace_surface_tests.py` | **180 passed, 2 failed** (`test_slg_literal_gap_foms_api_*`, `test_slg_literal_gap_foms_services_*` — 의도된 미해결) |
| `pytest … -k slg_literal_gap` | **9 passed, 2 failed** (동일) |
| `python -c "import app; print('APP_OK')"` | **APP_OK** |
| `python tools/harness/verify_result.py --json` | **success: true** |

## 3. 변경 요약

- 삭제: `foms/web/erp/`, `erp_as_page/`, `erp_drawing_workbench/`, `erp_shipment_page/`, `user_pages/`, `storage_dashboard/`, `excel_import/`.
- 추가: `foms/web/channel/__init__.py` (placeholder owner 패키지).
- `foms/web/auth/routes.py`: `profile` 라우트 (기존 `user_pages`와 동등 동작).
- 템플릿: `layout_nav.html`, `admin/admin.html`, `admin/security_logs.html` — `auth` / `admin` 엔드포인트.
- `tests/contracts/runtime/foms_namespace_surface_tests.py`: ERP 페이지·AS·출고·도면 모듈 경로 갱신; `namespaced_erp_display` 계약에 `_normalize_for_search` 반영; `test_strict_canonical_tools_taxonomy`에 `tools/ops/` 허용.

## 4. 3축 + GDM 감리 (요약)

| 축 | 결과 |
|----|------|
| A literal | 중복 7 디렉터리 제거; `foms/web/channel` 추가로 §4.2 리스트 일치(트리 상); API/services 2건은 다음 배치 — **High 0** (본 배치 범위) |
| B runtime | `erp_bp`는 `foms.platform.erp_blueprint`; blueprint 등록 경로 유지; APP_OK — **High 0** |
| C proof | 전체 계약 180/182 green; SLG 서브트리 2 fail은 계획된 잔여 — **High 0** |
| GDM | 흡수 II·프로필 이동·중복 트리 삭제와 계획서 일치 — **High 0** |

**Medium:** 0 (범위 내).

## 5. 다음

- `SLG-B5` — channel page/API split + attachments absorption (`foms/api/chat`, `attachments_internal` 정리).
