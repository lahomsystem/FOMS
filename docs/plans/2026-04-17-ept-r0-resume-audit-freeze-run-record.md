# EPT-R0 Resume audit + freeze — Run Record
> 배치: **EPT-R0** | 상태: **동결 완료** (저장소 truth 기준) | 상위: `2026-04-17-erp-fast-page-and-tab-navigation-execution-plan.md`

## 1. Scope / acceptance / stop rule (R0 재진술)

**Scope**
- 최종 잠금판 계획서·`AGENTS.md`·선행 B1 기록(`2026-04-17-ept-b1-baseline-contract-run-record.md`)과 **현재 코드/라우트/테스트**를 대조한다.
- **구현 추가 없음**: 감사·분류·인벤토리·갭·다음 배치 순서만 확정한다.

**Acceptance**
- 아래 §3–§7 산출물이 **파일·라우트·테스트 단위**로 채워져 있다.
- **Authoritative ERP HTML GET inventory**가 `app.url_map` 기준 1차 동결되었다 (§6).
- 10~20% 선행분과 **중복 구현 위험**이 식별되었다 (§2, §8).

**Stop rule**
- R0에서 비즈니스 로직·라우트 URL·DB·fragment 동작을 **변경하지 않는다**.
- `unrelated` dirty worktree 가정: **revert 금지** — 본 문서는 현재 tree 기준 truth만 기록한다.

---

## 2. 요약 (진행률 10~20% 매핑)

| 구간 | 판정 | 근거 |
|------|------|------|
| **EPT-B1** (baseline + contract) | **완료 (디스크 기준)** | `docs/specs/2026-04-17-erp-shell-fragment-contract_SPEC.md`, `foms/services/common/erp_navigation_contract.py`, `tests/domains/test_erp_shell_fragment_contract.py`, `docs/plans/2026-04-17-ept-b1-baseline-contract-run-record.md` 존재. |
| **EPT-B2** (shell) | **부분** | `static/js/erp/runtime-shell.js` 존재; **FAST_PATHS = 4탭만** (`dashboard|measurement|shipment|as`). 5개 secondary primary는 shell 비참여. |
| **EPT-B3** (core fragmentization) | **부분** | 4개 뷰가 `view=fragment` + `X-FOMS-ERP-SHELL` 시 fragment 응답·헤더 확인됨(테스트). **critical/heavy 분리·크기 목표 미검증.** |
| **EPT-B4–B9** | **미착수/미closeout** | 문서·증거·9면 baseline·secondary shell 편입 없음. |

**선행 10~20%의 정체**: B1 계약 동결 + B2/B3의 **4탭 한정** MVP. 잠금판의 **9 primary + 전수 인벤토리 + subordinate contract**까지는 **아직 아님**.

---

## 3. Completed items (저장소 truth)

| 영역 | 항목 | 경로/비고 |
|------|------|-----------|
| SPEC | Shell/fragment/heavy/micro-cache 계약 문서 | `docs/specs/2026-04-17-erp-shell-fragment-contract_SPEC.md` |
| SSOT | 탭 경로·헤더·view 상수 | `foms/services/common/erp_navigation_contract.py` (`ERP_CANONICAL_TAB_PATHS` = **4 paths**) |
| HTTP | Shell 요청 판별 헬퍼 | `foms/services/common/erp_shell_http.py` (import 경로는 소비처 참조) |
| 테스트 | 상수·fragment 스모크(4탭) | `tests/domains/test_erp_shell_fragment_contract.py` |
| 클라이언트 | 동일 출처 fast-tab shell (4 path) | `static/js/erp/runtime-shell.js` |
| 로드 | shell 스크립트 포함 여부 | `templates/partials/shared/layout_scripts.html` (프로젝트 관례에 맞게 로드) |
| B1 기록 | Staging baseline 표 (4 URL) | `docs/plans/2026-04-17-ept-b1-baseline-contract-run-record.md` |

---

## 4. Partial items

| ID | 설명 | 증거 |
|----|------|------|
| P1 | **Secondary 5개 primary**가 `ERP_CANONICAL_TAB_PATHS` / `FAST_PATHS` / `data-foms-erp-fast-tab`에 **미포함** | `erp_navigation_contract.py`, `runtime-shell.js`, `templates/partials/shared/erp_sub_nav.html` |
| P2 | **critical / heavy** view 모드: 상수·SPEC에는 있으나 **라우트에서 분기·응답 분리 미완**으로 가정 | `VIEW_CRITICAL`, `VIEW_HEAVY` 사용처 grep 시 핵심 대시보드에 미연결 |
| P3 | **popstate**: `fomsErpShell` 시 **full reload** — warm back·cache 친화 미완 | `runtime-shell.js` L172–176 |
| P4 | **B1 baseline 표**: 잠금판 **9 primary** 중 5개 URL에 대한 staging 행 **부재** | B1 run record §2는 4행만 |
| P5 | 계획서 `## 4. Steps` 체크박스가 모두 `[ ]` — **문서 상태와 디스크 완료도 불일치** 가능 | `2026-04-17-erp-fast-page-and-tab-navigation-execution-plan.md` §4 |

---

## 5. Untouched items (본 tranche 목표 대비)

- **EPT-B4**: drawing-workbench, production, construction, completion, history 의 shell 참여·fragment 계약 정렬.
- **EPT-B5**: `/erp/drawing-workbench/<id>`, `/edit/<id>?open=erp-beta`, `/erp/orders/<id>` return-state / shell 하위 계약.
- **EPT-B6–B7**: prefetch, HTML diet, page-scoped assets, shipment/as **profiling** 및 운영 증거.
- **EPT-B8–B9**: Railway 전면 증거, semantic diff 0 closeout.

---

## 6. Authoritative ERP HTML GET inventory (v1 — `app.url_map` 동결)

로컬에서 `import app` 후 `GET` 규칙을 수집했다 (개발 설정 경고는 무시). **브라우저에서 직접 열 수 있는 HTML**과 **JSON/API**를 구분한다.

### 6.1 Primary shell 대상 (계획서 § 범위 1)

| Path | Endpoint | 비고 |
|------|----------|------|
| `/erp/dashboard` | `erp_dashboard.erp_dashboard` | fragment **구현됨** (테스트) |
| `/erp/measurement` | `erp_measurement_dashboard.erp_measurement_dashboard` | fragment **구현됨** |
| `/erp/drawing-workbench` | `erp_drawing_workbench.erp_drawing_workbench_dashboard` | shell **미편입** (FAST_PATHS 외) |
| `/erp/production/dashboard` | `erp_production_page.erp_production_dashboard` | shell **미편입** |
| `/erp/shipment` | `erp_shipment_page.erp_shipment_dashboard` | fragment **구현됨** |
| `/erp/as` | `erp_as_page.erp_as_dashboard` | fragment **구현됨** |
| `/erp/construction/dashboard` | `erp_construction_page.erp_construction_dashboard` | shell **미편입** |
| `/erp/completion` | `erp_completion_page.erp_completion_dashboard` | shell **미편입** |
| `/erp/history/` | `erp_history.history_dashboard` | shell **미편입** |

### 6.2 Subordinate / legacy (계획서 § 범위 2)

| Path | Endpoint | 비고 |
|------|----------|------|
| `/erp/drawing-workbench/<int:order_id>` | `erp_drawing_workbench.erp_drawing_workbench_detail` | 상세 |
| `/edit/<int:order_id>` | `order_edit.edit_order` | GET/POST |
| `/erp/orders/<int:order_id>` | `order_edit.redirect_legacy_erp_order_detail` | 레거시 리다이렉트 |

### 6.3 Shell-linked descendant / 설정형 HTML (B1 인벤토리 확장 후보)

대시보드·내비 링크로 진입 가능한 **동일 인증 맥락 HTML** (전수는 템플릿 링크 감사로 보강).

| Path | Endpoint | 분류 |
|------|----------|------|
| `/erp/shipment-settings` | `erp_shipment.erp_shipment_settings` | ERP 설정 HTML |
| `/map_view` | `erp_map.map_view` | 지도 뷰 HTML (대시보드 등에서 링크) |

### 6.4 JSON / API (본 tranche **증거·계약은 포함**, “HTML fragment 대상”과 구분)

- `/api/erp/measurement/route`, `/api/erp/measurement/summary`
- `/api/erp/shipment-settings` (GET)
- `/erp/api/notifications`, `/erp/api/notifications/badge`, `/erp/api/users`, `/erp/api/users/list`

---

## 7. Mandatory discovery (B1에서 동결 예정인 “전수”에 대한 R0 메모)

- 본 §6은 **`url_map` 1차 동결**이다.
- 계획서 **Mandatory discovery rule**에 따라, 다음 배치(B1 재검 또는 전용 스크립트)에서:
  - `templates/**/*.html` 의 `href="/erp/...` , `url_for(...)` , `redirect(...)` 를 기계적으로 스캔해 §6에 **누락 링크**를 합친다.
  - explicit exclusion이 없으면 **전부 범위**에 넣는다.

### 7.1 R0 샘플 스캔 (템플릿·JS 문자열, 비전수)

다음은 `templates/`에서 `/erp/` 문자열 일부를 샘플 grep한 힌트다. **authoritative set은 §6 + 전체 스크립트**로 v2 동결한다.

- `/erp/completion` — `layout_scripts.html` 위젯 링크
- `/erp/construction/dashboard` — `construction/partials/scripts.html` 리다이렉트
- `/erp/drawing-workbench/<id>?tab=requests` — 주문 대시보드 partial
- 알림·멘션 API: `/erp/api/notifications*`, `/erp/api/users*`, `/erp/api/users/list` (§6.4)

---

## 8. Gap vs 잠금판 (핵심)

| 잠금판 요구 | 현재 truth |
|-------------|------------|
| 9 primary shell / fast navigation | **4개만** 계약·JS·테스트에 반영 |
| canonical URL + full/fragment 동일 비즈니스 결과 | 4탭에 대해 테스트 존재; 확장 미검증 |
| critical/heavy fragment | 상수만; **페이지 분리 미완** |
| 서브페이지 return-state | 미구현 |
| Railway 9면 + subordinate 증거 | **미수집** (B1 표는 4면만) |

---

## 9. 다음 배치 순서 (고정 순서 유지 — R0 이후)

> **주의**: 디스크상 **EPT-B1 산출물은 이미 존재**하므로, 다음 작업은 “계획서 §4.1 체크박스 갱신 + **9 primary baseline 행 추가** + 인벤토리 템플릿 스캔”으로 **B1을 재동결**한 뒤, 순서대로 진행하는 것이 중복을 막는다.

1. **EPT-B1** — baseline·contract **재확인**: 9 URL staging baseline 행 추가, authoritative inventory v2(템플릿 스캔), 계획서 §4.1 `[x]` 정합.
2. **EPT-B2** — `FAST_PATHS`·계약·네비를 **9 primary**로 확장; popstate/warm back 설계 반영.
3. **EPT-B3** — core 4탭에 critical/heavy + 운영 크기 증거.
4. **EPT-B4** — secondary 5탭 fragment/shell 편입.
5. **EPT-B5** — subordinate 3경로 + §7 inventory descendants.
6. **EPT-B6** — prefetch.
7. **EPT-B7** — HTML diet + profiling.
8. **EPT-B8** — 검증 + Railway 증거.
9. **EPT-B9** — GDM closeout.

---

## 10. GDM super hard review (R0)

| 역할 | High | Medium | 메모 |
|------|------|--------|------|
| Semantic-preservation | 0 | 0 | R0는 코드 미변경 |
| Architecture | 0 | 0 | 4탭 SSOT vs 9탭 요구 갭 명시 |
| Route-inventory | 0 | 0 | §6 `url_map` 기반 |
| UX/navigation | 0 | 1 | **M**: popstate reload만 있음 — **후속 B2** |
| Ops/evidence | 0 | 1 | **M**: 9면 baseline·Railway 미완 — **후속 B1/B8** |
| **Synthesis** | **0** | **0** (Medium은 차기 배치 스코프로 승격) | R0 **종료**, EPT-B1 재동결 진행 가능 |

---

## 11. 검증 (R0)

```text
python -c "import app; print('APP_OK')"
```

(본 세션에서 실행 확인됨.)

---

*본 문서는 `EPT-R0`의 authoritative “resume freeze”. 구현은 본 문서와 `2026-04-17-ept-b1-baseline-contract-run-record.md`를 함께 기준으로 이어간다.*
