# EPT-B1 Baseline + Contract Freeze — Run Record
> 배치: **EPT-B1** (초기 동결 + **2026-04-17 재동결**) | 상태: **완료** (코드·문서·테스트 + 9 primary baseline 스키마 + inventory v2) | 상위: `2026-04-17-erp-fast-page-and-tab-navigation-execution-plan.md` | 동결 입력: `2026-04-17-ept-r0-resume-audit-freeze-run-record.md`

## 1. Scope (재진술)
- Railway staging **사전 실측** 수치를 authoritative baseline으로 고정 — **9개 primary 전체**에 대해 표 스키마를 잠그고, 기존 4개 URL은 **이전 측정값 유지**, 나머지 5개는 **동일 프로토콜로 재측정 시 채움** (`PENDING`).
- Shell / fragment / heavy **요청 계약**은 기존 SPEC + Python 상수 + pytest를 **재사용** (변경 없음).
- **Micro-cache 유지** 결정은 기존 플래그·SPEC 그대로.
- Route·query·history·canonical URL 매트릭스: SPEC + 본 문서 **inventory v2**.
- GET 필터/페이지네이션 **shell 가로채기 목표 범위**: SPEC §5 (구현은 EPT-B2+).
- **Authoritative ERP HTML GET inventory v2**: R0 `url_map` v1 + 템플릿 `url_for` / 문자열 링크 / 서버 `redirect` 스캔으로 동결 (§8).

## 2. Staging baseline (9 primary — 계획서 §2.1·잠금판 정합)
로그인 후 동일 쿠키로 반복 GET한 기록. **재측정 시 본 표 갱신.**

| URL | 1회차 total | 2회차 total | 1회차 starttransfer | 2회차 starttransfer | 응답 크기 (bytes) |
|-----|-------------|-------------|---------------------|---------------------|-------------------|
| `/erp/dashboard` | 3.79s | 2.34s | 3.43s | 1.97s | 1,007,853 |
| `/erp/measurement` | 3.38s | 1.91s | 3.18s | 1.89s | 168,798 |
| `/erp/shipment` | 2.09s | 2.06s | 1.95s | 2.00s | 216,120 |
| `/erp/as` | 2.71s | 2.46s | 2.32s | 2.32s | 1,102,349 |
| `/erp/drawing-workbench` | PENDING | PENDING | PENDING | PENDING | PENDING |
| `/erp/production/dashboard` | PENDING | PENDING | PENDING | PENDING | PENDING |
| `/erp/construction/dashboard` | PENDING | PENDING | PENDING | PENDING | PENDING |
| `/erp/completion` | PENDING | PENDING | PENDING | PENDING | PENDING |
| `/erp/history/` | PENDING | PENDING | PENDING | PENDING | PENDING |

**재동결 메모**
- 상단 4행: 기존 B1 실측 **그대로 유지** (중복 측정으로 덮어쓰지 않음).
- 하단 5행: **Railway staging**에서 동일 측정 프로토콜로 채운다. 값이 없으면 `PENDING` 유지 — **근거 없는 숫자 기입 금지**.
- **운영 증거**: EPT-B7·B8에서 before/after 재수집. 본 표는 **구현 전·중 기준선 스키마**로서 잠금판 9 primary와 정렬됨.

## 3. 산출물 (기존 + 재동결)
| 산출물 | 경로 |
|--------|------|
| 계약 SPEC | `docs/specs/2026-04-17-erp-shell-fragment-contract_SPEC.md` (§9 인벤토리 포인터 추가) |
| 상수 SSOT | `foms/services/common/erp_navigation_contract.py` — **여전히 4 canonical path** (EPT-B2~B4에서 9탭 확장 시 SPEC과 동기화) |
| 계약 테스트 | `tests/domains/test_erp_shell_fragment_contract.py` |
| R0 동결 | `docs/plans/2026-04-17-ept-r0-resume-audit-freeze-run-record.md` |
| **본 문서** | **9행 baseline + inventory v2** |

## 4. 검증 명령 (고정)
```text
python -c "import app; print('APP_OK')"
python tools/harness/verify_result.py --json
pytest tests/domains/test_erp_shell_fragment_contract.py -q
```

## 5. 건드린 파일 / 금지 경계 (재동결)
- **재동결에서 변경**: 본 run record, SPEC §9 한 절, 상위 계획서 §4.1 체크박스.
- **금지**: DB migration, 비즈니스 쿼리·필터·KPI 의미 변경, 라우트 URL 변경, fragment 응답 로직 변경(후속 배치), `erp_navigation_contract` **값** 임의 확장(9탭은 EPT-B2+SPEC).

## 6. GDM review (B1 초기)
- **Semantic-preservation**: 동작 변경 없음(상수·문서·테스트만).
- **Architecture**: `erp_navigation_contract.py` 단일 SSOT.
- **UX/navigation**: SPEC에 history·GET fallback 명시.
- **Ops/evidence**: baseline 표는 계획서 이관; 최종 closeout은 EPT-B7 Railway 증거 필수.
- **Synthesis**: High/Medium 0 — EPT-B2 진행 가능.

## 7. GDM super hard review (B1 재동결, 2026-04-17)

| 역할 | High | Medium | 비고 |
|------|------|--------|------|
| Semantic-preservation | 0 | 0 | 문서·SPEC 포인터만; 런타임 코드 미변경 |
| Architecture | 0 | 0 | 인벤토리 v2는 B1 SSOT; 상수 4탭은 R0 truth 유지 |
| Route-inventory | 0 | 0 | `url_map` + 템플릿·redirect 교차 검증 |
| UX/navigation | 0 | 0 | baseline 9행 스키마만 추가; URL 의미 변경 없음 |
| Ops/evidence | 0 | 0 | 5행 PENDING 명시 — 스테이징 미접속 시 숫자 조작 안 함 |
| **Synthesis** | **0** | **0** | **EPT-B2** 진행 가능 |

---

## 8. Authoritative inventory v2 (EPT-B1 동결)

**방법**: R0 **inventory v1** (`app.url_map` GET, `/erp/api/*` 제외) + 템플릿 `url_for('erp_*` / `order_edit` / `dashboards` 일부) 및 `foms/web` `redirect`/`url_for` 스캔 + 본 섹션에서 **합집합·분류**.

**제외하지 않음**: explicit exclusion 없이 목록에 들어간 HTML GET은 상위 계획 **“전부 범위”** 원칙과 충돌 시 **계획서·DECISIONS**로만 축소 가능 (본 B1에서 임의 제외 없음).

### 8.1 Tier A — 잠금판 9 primary (`/erp/*` HTML GET)

| Path | Endpoint (검증 시점) | 비고 |
|------|----------------------|------|
| `/erp/dashboard` | `erp_dashboard.erp_dashboard` | fragment 계약·테스트 존재 |
| `/erp/measurement` | `erp_measurement_dashboard.erp_measurement_dashboard` | 동상 |
| `/erp/drawing-workbench` | `erp_drawing_workbench.erp_drawing_workbench_dashboard` | shell·FAST_PATHS 미편입 (R0 truth) |
| `/erp/production/dashboard` | `erp_production_page.erp_production_dashboard` | 동상 |
| `/erp/shipment` | `erp_shipment_page.erp_shipment_dashboard` | fragment 계약·테스트 존재 |
| `/erp/as` | `erp_as_page.erp_as_dashboard` | 동상 |
| `/erp/construction/dashboard` | `erp_construction_page.erp_construction_dashboard` | 동상 |
| `/erp/completion` | `erp_completion_page.erp_completion_dashboard` | 동상 |
| `/erp/history/` | `erp_history.history_dashboard` | 동상 |

### 8.2 Tier B — 잠금판 필수 subordinate / legacy (HTML GET)

| Path | Endpoint | 비고 |
|------|----------|------|
| `/erp/drawing-workbench/<int:order_id>` | `erp_drawing_workbench.erp_drawing_workbench_detail` | `tab=` 등 query |
| `/edit/<int:order_id>` | `order_edit.edit_order` | `?open=erp-beta` 등 |
| `/erp/orders/<int:order_id>` | `order_edit.redirect_legacy_erp_order_detail` | 레거시 리다이렉트 |

### 8.3 Tier C — `url_map` 기준 ERP 관련 HTML·도구 (primary 외 GET)

| Path | Endpoint | 출처 |
|------|----------|------|
| `/erp/shipment-settings` | `erp_shipment.erp_shipment_settings` | 출고 설정 HTML; `shipment` partial 링크 |
| `/map_view` | `erp_map.map_view` | `measurement`/`as` 등 **redirect**·지도 링크 |

**서버 redirect (스캔)** — 동일 사용자 세션에서 HTML GET으로 연결됨:
- `foms/web/measurement/dashboard.py` → `erp_map.map_view` (날짜·검색 유지)
- `foms/web/cs/as_dashboard.py` → `erp_map.map_view`
- `foms/web/drawing/workbench.py` → `erp_drawing_workbench.erp_drawing_workbench_dashboard`
- `foms/web/orders/edit.py` → `order_edit.edit_order` (legacy `erp/orders/<id>`)
- `foms/web/auth/routes.py` → `erp_shipment_page.erp_shipment_dashboard`

### 8.4 Tier D — ERP JSON/API (HTML fragment 대상 아님, 계약·증거 범위)

| Path prefix / pattern | 비고 |
|-------------------------|------|
| `/erp/api/notifications`, `/erp/api/notifications/badge`, `/erp/api/users`, `/erp/api/users/list` | 알림·멘션 |
| `/erp/api/notifications/send`, read/delete 등 | 일부 POST — 스모크 시 메서드 구분 |
| `/api/erp/measurement/route`, `/api/erp/measurement/summary` | 측정 API |
| `/api/erp/shipment-settings` | JSON GET |

### 8.5 Tier E — 실측·도면·주문과 연결된 **비-`/erp/` prefix** HTML GET (전수 원칙)

템플릿에서 `order_edit`, `dashboards.*` 로 진입 가능. **잠금판 9 primary와 별개**이나, 브라우저 직접 열기·딥링크 가능한 **동일 제품 대면**으로 인벤토리에 포함.

| Path | Endpoint | 비고 |
|------|----------|------|
| `/regional_dashboard` | `dashboards.regional_dashboard` | measurement 레거시 |
| `/metropolitan_dashboard` | `dashboards.metropolitan_dashboard` | 동상 |
| `/self_measurement_dashboard` | `dashboards.self_measurement_dashboard` | 동상 |

---

## 9. 스캔 근거 (재현)

- **url_map**: `python -c "from app import app; ..."` (GET, `/erp/` 비-API, `/edit`, `/map_view`, `/regional_*`, `/metropolitan_*`, `/self_measurement_*`).
- **템플릿**: `templates/**/*.html` 에서 `url_for('erp_*')`, `url_for('order_edit.*')`, `"/erp/` 문자열.
- **redirect**: `foms/web/**/*.py` 에서 `redirect.*erp` / `url_for('erp_` / `url_for('erp_map` / `order_edit`.

---

*본 문서는 EPT-B1의 authoritative baseline + inventory **v2** SSOT이다. R0를 대체하지 않으며, R0 v1과 합치되게 유지한다.*
