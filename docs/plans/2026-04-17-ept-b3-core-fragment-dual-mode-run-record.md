# EPT-B3 Core 4 — full/fragment dual-mode 정렬 — Run Record
> 배치: **EPT-B3** | 상태: **동결 (완료)** | 상위: `2026-04-17-erp-fast-page-and-tab-navigation-execution-plan.md` §4.3 | 전제: EPT-R0 / B1 / B2 동결

## 1. Scope (재진술)
- 대상은 **`ERP_FRAGMENT_READY_PATHS` 네 경로만** (`/erp/dashboard`, `/erp/measurement`, `/erp/shipment`, `/erp/as`). **확대 금지 (여전히 4개).**
- 서버가 `X-FOMS-ERP-SHELL: 1` + `view ∈ {fragment,critical,heavy}` 일 때 **동일 핸들러·동일 비즈니스 조립(micro-cache slice 포함)**으로 partial HTML을 내고, **full GET(JS off)** 은 기존과 같이 **전체 문서** 유지.
- B3는 **secondary 5 primary에 shell fetch를 붙이지 않음** (B2 safe-nav 유지).

## 2. Acceptance
- [x] `get_erp_shell_view_mode` / `wants_erp_shell_tab_body` / `apply_erp_shell_fragment_headers`로 요청 모드가 코드에 명시된다.
- [x] `view=fragment|critical|heavy` + shell 헤더 시 **동일 partial 계열** + `X-FOMS-ERP-FRAGMENT: 1` + **`X-FOMS-ERP-FRAGMENT-TIER`** (값: fragment/critical/heavy).
- [x] **B3**에서 critical/heavy는 **fragment와 동일 템플릿·동일 컨텍스트**(바이트 동등, orders 대표 검증)로 응답; tier 헤더만 구분 (향후 partial 분리 훅).
- [x] micro-cache DTO 조립은 **view tier와 무관**(핸들러 단일 경로 유지).
- [x] `FRAGMENT_READY` 튜플 길이 **4 유지**, focused pytest·SPEC §3·§9 보강.

## 3. Stop rule / Hard stop
- `FRAGMENT_READY_PATHS`를 5개 이상으로 늘리기 → **금지**.
- secondary primary에 shell fetch / fragment 응답 신규 구현 → **금지** (B4 이후).
- full vs fragment vs tier 간 **KPI/행/필터 의미 불일치** → **금지**.
- migration / schema / 전체 HTML cache → **금지**.

## 4. 설계 요약
| 항목 | 내용 |
|------|------|
| 모드 판별 | Shell 헤더 + `view` 쿼리; `erp_shell_http.get_erp_shell_view_mode` |
| Partial 트리거 | `wants_erp_shell_tab_body` (= fragment \| critical \| heavy) |
| 응답 헤더 | `X-FOMS-ERP-FRAGMENT`, `X-FOMS-ERP-FRAGMENT-TIER` |
| 템플릿 (B3) | 네 코어 모두 기존 fragment partial과 동일 (single truth) |
| Cache | `dashboard_cache` slice 키는 기존 필터·user fingerprint 유지; tier 미포함 |

## 5. 건드린 파일
- `foms/services/common/erp_navigation_contract.py`, `erp_shell_http.py`
- `foms/web/orders/dashboard.py`, `measurement/dashboard.py`, `shipment/dashboard.py`, `cs/as_dashboard.py`
- `docs/specs/2026-04-17-erp-shell-fragment-contract_SPEC.md`, 본 파일, `ARCHIVE_INDEX.md`, 상위 계획 §4.3
- `tests/domains/test_erp_shell_fragment_contract.py`

## 6. 검증
```text
python -c "import app; print('APP_OK')"
python tools/harness/verify_result.py --json
pytest tests/domains/test_erp_shell_fragment_contract.py -q
```

## 7. GDM super hard review (EPT-B3)
| 역할 | High | Medium | 메모 |
|------|------|--------|------|
| Semantic-preservation | 0 | 0 | critical/heavy = 동일 본문(orders) 검증 |
| Architecture | 0 | 0 | SSOT `erp_shell_http` + tier 헤더 |
| Cache / fragment 경계 | 0 | 0 | 조립 경로 단일; tier는 응답 메타만 |
| **Synthesis** | **0** | **0** | **EPT-B4** 진행 가능 |

---

*Hard stop: §3 위반 시 배치 중단.*
