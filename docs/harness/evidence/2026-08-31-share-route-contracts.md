# 공유 링크 신규 라우트·자산 계약 + 인앱 브라우저 제약 조사 (T3)

- 조사 대상 워크트리: `c:\tmp\foms-s-kakaoshare` (브랜치 `session/kakaoshare`, base `ea55440f`)
- 조사 시점: 2026-08-31. 조사 중 T1/T2 가 동시에 편집 중이었으므로 "현재 상태" 항목은 그 시점 스냅샷이다.
- 원칙: 모든 판정에 `파일:줄` 또는 URL 근거를 붙였다. 근거 없이 쓴 것은 **추정** 이라고 명시했다.
- **줄 번호 주의**: `foms/api/share.py` 와 `templates/orders/share_*.html` 은 조사 중에도 T1/T2 가 편집하고 있었다. 그쪽 줄 번호는 2026-08-31 13:20 기준이며, 심볼 이름으로 다시 찾는 편이 안전하다. 테스트·하네스 쪽 줄 번호는 이번 작업에서 건드리지 않는 파일이라 안정적이다.

---

## 0. T1/T2 가 지금 당장 반영해야 할 것 (체크리스트)

1. **[T1·해소됨] `tests/domains/test_order_share_view.py::test_view_estimate_renders_snapshot_only` 이 13:20 시점에 빨강이었다**(`assert '견적서' in body` — 계약서 재구성으로 리터럴 소멸, 1 failed / 34 passed). **13:25 재실행에서 T1 이 테스트를 갱신해 47 passed 로 회복**했다. 남기는 이유: 같은 종류의 리터럴 계약(계좌번호 `461-082990-04-011`·고객명·금액 포맷)이 이 파일에 더 있으므로, 문구를 또 바꾸면 같은 자리에서 다시 빨강이 난다.
2. **[T1·PNG 저장 방식] `canvas.toBlob` + `<a download>` blob 저장은 카카오톡 인앱에서 실패한다.** 저장소 선례(`static/js/measurement/image-export.js:416-417`)가 이미 `canvas.toDataURL('image/png')` + `<a download>` 를 쓴다 — 그 선례를 그대로 복제하라. blob 은 WKWebView 미지원 버그가 열려 있다(§D2-5).
3. **[T1·해소됨] bundle 자산 누락** — 13:20 시점에 `share_bundle_view.html` 이 `foms-share-contract.css` / `share-contract.js` 를 안 실었다(계약서 마크업만 들어가고 스타일·PNG 저장·계좌 복사가 빠진 페이지). 13:25 확인 시 `share_bundle_view.html:15, 34` 로 둘 다 들어왔다. **bundle 은 단독 페이지와 자산 4종이 모두 같아야 한다**는 점을 회귀 기준으로 남긴다.
4. **[T1·미해소·핀 드리프트] `css/orders/foms-share-view.css` 핀이 아직 갈라져 있다**(13:25 재확인) — `share_view.html:14`·`share_bundle_view.html:14` 는 `?v=20260831a`, **`share_estimate_view.html:15` 만 `?v=20260825a`**. SW `staticCacheFirst` 는 `?v=` 포함 URL 전체를 캐시 키로 쓰므로(§B-3) 이 페이지만 옛 CSS 가 산다. 세 곳을 한 값으로 맞춰라.
   - 함께 확인한 나머지 핀은 정상 일치: `foms-share-contract.css` `20260831a`(`share_estimate_view.html:16`, `share_bundle_view.html:15`), `share-contract.js` `20260831a`(`:26`, `:34`), `share-view.js` `20260831a`(`share_view.html:25`, `share_bundle_view.html:33`).
5. **[T2·failopen] `foms/api/share.py` 에 `except Exception` 을 하나라도 새로 넣으면 `tests/domains/test_failopen_inventory.py` 가 빨강**이다(현재 share.py 등재 2건, `broad_total: 555`). 넣었다면 `python tools/harness/failopen_scan.py` 재생성 + 그 자리에 `logger.warning(..., exc_info=True)` 배선 필수(로거 없으면 `SWALLOW_BY_CONTROL_FLOW` 기준선 180 이 늘어 또 빨강).
6. **[T2·감사 액션] `record_file_access('FILE_DOWNLOAD', ...)` 선택은 정답이다** — `FILE_DOWNLOAD` 는 이미 라벨 맵에 있다(`foms/services/audit_message_display.py:267`). 새 액션 문자열(예: `SHARE_ZIP_DOWNLOADED`)을 `action='...'` 키워드 형태로 쓰면 `tests/domains/test_admin_audit_screen_readability_3.py:56` 이 빨강이다.
7. **[T2·헤더] `Content-Disposition` 에 ASCII `filename="..."` 폴백이 없다**(`foms/api/share.py:99-110` 은 `filename*=UTF-8''...` 단독). 구형 인앱 웹뷰 파서 대비 `attachment; filename="drawings.zip"; filename*=UTF-8''...` 병기를 권한다(RFC 6266 권장형). — **추정**(이 저장소에 실패 사례 근거는 없음).
8. **[T1·T2 공통·인쇄] `window.print()` 는 카카오톡 인앱(iOS WKWebView·Android WebView)에서 구현 자체가 없다.** 이것이 "저장 버튼 무반응"의 1순위 근본 원인이다(§D3). PC 보조 버튼으로만 남기고 모바일 주 경로에서 빼라.
9. **[T2·인앱 안내] `_is_kakao_inapp` 서버 판정(`foms/api/share.py:246-257`)은 맞는 축이다.** UA 토큰 `KAKAOTALK` 은 Android 에서 실측 확인됨. iOS 는 동일 토큰이라는 게 통설이나 **정확한 UA 전문 출처 미확보(추정)** — 폴백(개별 저장 목록)을 항상 함께 노출하라.
10. **[검증 사각] `/s/<token>` 도면·ZIP 경로는 로컬에서 검증 불가**(storage_type=local → 503, 실측 확인). 계약서(estimate) 경로는 **로컬에서 200 으로 렌더된다**(실측 확인, §E). ZIP 은 pytest 스텁(`FakeR2Storage`)으로만 검증 가능하다.
11. **[T1·정리 필요] 임시 파일 3개가 워킹트리에 남아 있다**(13:25 `git status`): `_tmp_contract.html`(247줄), `tests/domains/test_tmp_share_contract_dump.py`(62줄), `tests/domains/test_tmp_share_contract_smoke.py`. **`tests/domains/test_tmp_*.py` 는 파일명이 `test_*.py` 라 CI 본 스위트가 그대로 수집한다**(`.github/workflows/ci.yml:109` — `pytest --ignore=tests/visual --ignore=tests/harness`). 커밋 전 삭제하거나, 남길 거면 정식 계약 테스트로 승격하고 이름을 바꿔라. 파일 자체 docstring 도 "임시 파일이며 확인 후 삭제한다" 라고 적고 있다.

---

## A. 신규 GET 라우트가 통과해야 하는 계약

### A-1. 매니페스트·인벤토리 8종 판정표

| 매니페스트 | 강제 테스트 (파일:줄) | GET·비로그인 라우트도 대상? | 판정 |
|---|---|---|---|
| `foms_write_guard_manifest.json` | `tests/domains/test_write_guard.py:104-122` (`test_manifest_covers_every_mutation_route`) | **아니오** | 113~115줄에서 `set(rule.methods) & _MUTATION_METHODS` 로 POST/PUT/PATCH/DELETE 만 모은다. 런타임 가드도 `foms/services/request_write_guard.py:288-289` 에서 `if request.method not in _WRITE_METHODS: return None`. **등재 불필요** |
| `foms_order_mutation_policy_manifest.json` | `tests/domains/test_auth_enforcement.py:125-140` (`test_static_gate_every_mutation_route_classified`) | **아니오** | 131~133줄 동일한 mutation-method 필터. **등재 불필요** |
| `foms_audit_coverage_inventory.json` | `tests/domains/test_audit_coverage_inventory.py:56-79` (`test_inventory_matches_fresh_scan`, `test_unaudited_set_does_not_grow`) | **아니오** | 스캐너 `tools/harness/audit_coverage_scan.py:10-11` 명시: "**GET 전용 라우트는 대상이 아니다**". `WRITE_METHODS` 정의는 같은 파일 55줄. **등재 불필요** |
| `foms_audit_coverage_allowlist.json` | `tests/domains/test_audit_coverage_inventory.py:84-98` | **아니오** | 위와 동일 모집단. **등재 불필요** |
| `foms_api_error_leak_inventory.json` | `tests/domains/test_api_error_containment.py:153-181` (`test_no_raw_traceback_print_in_foms`, `test_response_str_e_leaks_do_not_grow`) | **예 (메서드 무관)** | 158~166줄이 `foms/**/*.py` 를 정규식 스캔한다(`traceback.print_exc`, `return jsonify(...str(e)...), 500`). **새 코드에 그 두 패턴을 넣지 않으면 그만** — 등재는 불필요 |
| `foms_failopen_inventory.json` | `tests/domains/test_failopen_inventory.py:154-160`(드리프트) · `164-166`(UNCLASSIFIED 0) · `205-208`(`_SWALLOW_BASELINE = 180`, 44줄) | **예 (메서드 무관)** | 스캐너 `tools/harness/failopen_scan.py:57-58` 이 `foms/` 전역 broad catch 를 센다. **새 `except Exception` 은 반드시 재생성 + 로거 배선.** 현재 share.py 등재는 493·913줄 2건(둘 다 `LOG_AND_CONTINUE`) |
| `foms_order_mutation_writer_inventory.json` | `tests/domains/test_rev_99.py:52` + 드리프트 테스트 | 시그널 기준(메서드 무관) | 스캐너 `tools/harness/order_mutation_writer_scan.py:59-72`: 시그널은 `flag_modified(_, "structured_data")` 와 `.mutation_version` 대입 **둘뿐**. ZIP 라우트는 주문 JSONB 를 안 쓰므로 **비저촉** |
| `foms_state_writer_inventory.json` | `tests/domains/test_state_guard.py:34` + 드리프트 테스트 | 시그널 기준(메서드 무관) | 스캐너 `tools/harness/state_writer_scan.py:56-58, 62-77`: `.erp_stage_code`/`.status`/`workflow['stage']`/`shipment['logistics_status']`/`workflow['hold']` 대입만. **비저촉** |
| `foms_deploy_checks.json` | `tests/harness/test_bugfix_packet_manifest.py:20, 26` | 아니오 | 124개 packet 의 고정 레지스트리(같은 파일 31~40줄 `EXPECTED_PACKETS`). 라우트 축이 아니다. **N/A** |

> 부수 확인: `url_map` 을 닫힌집합으로 검사하는 테스트는 저장소 전체에서 위 2종(`test_write_guard.py:113`, `test_auth_enforcement.py:131`)과 `test_rev_99.py:274`(`/api/foms/offline` 한정) 뿐이다. **GET 라우트를 등재 강제하는 매니페스트는 존재하지 않는다.**
> 비로그인 경로 allowlist(“이 path 는 로그인 면제” 목록) 도 없다 — 인증은 데코레이터 유무로 결정되고 `share_view_bp`(`foms/api/share.py:40`, 등록은 `foms/platform/blueprints.py:168`) 자체가 무인증 블루프린트다. 레이트리밋은 앱 기본값(`foms/services/rate_limit.py:53` — `5000 per day, 1200 per hour`)이 그대로 걸린다.

### A-2. 감사 라벨 게이트

- **RED 를 내는 테스트**: `tests/domains/test_admin_audit_screen_readability_3.py:56-59`
  ```python
  def test_every_emitted_action_has_business_label():
      missing = sorted(_emitted_action_codes() - set(ACTION_LABELS))
      assert not missing, f"라벨 없는 행위 코드: {missing}"
  ```
- 수집 규칙(`같은 파일 46-53줄`): `foms/**/*.py` 를 정규식 `action=['"]([A-Z][A-Z0-9_]+)['"]` 로 스캔한다.
  → **키워드 인자 형태만 잡힌다.** `record_file_access('FILE_DOWNLOAD', ...)` 같은 위치 인자는 이 게이트에 안 걸린다(그래도 화면 라벨을 위해 등재하는 게 맞다).
- 별도 강제: 같은 파일 `62-65줄` — `FILE_VIEW` · `FILE_DOWNLOAD` · `FILE_PRESIGNED` 3종은 반드시 라벨을 가져야 한다.
- **현재 등재된 파일 접근 계열 액션**(`foms/services/audit_message_display.py`):
  - `198`: `DRAWING_GATEWAY_FILE_UPLOADED` = "도면 창구 파일 업로드"
  - `216-219`: `FILE_UPLOADED`·`FILE_DELETED`·`FILE_RESTORED`·`FILE_UPLOAD_FINALIZED`
  - `244-247`: `SHARE_LINK_CREATED`·`SHARE_LINK_REVOKED`·`SHARE_SMS_SENT`·`SHARE_ALIMTALK_SENT`
  - `266-268`: `FILE_VIEW` = "파일 열람" · `FILE_DOWNLOAD` = "파일 다운로드" · `FILE_PRESIGNED` = "서명 URL 발급"
- 즉 **ZIP 일괄 저장에 새 액션 코드를 만들 필요가 없다** — `FILE_DOWNLOAD` 재사용이 무비용이다. T2 현재 구현(`foms/api/share.py:435-442`)이 그렇게 하고 있고, 주석에도 그 이유가 적혀 있다.
- `record_file_access` 시그니처: `foms/services/audit_writer.py:427-436`. `order_id` 는 **정수만** 넣어야 한다(465-469줄 — 비정수면 payload 에서 제외되고 조용히 사라진다).

### A-3. 네임스페이스 닫힌집합 게이트

- 실행 경로: `tests/domains/test_foms_namespace_imports.py`(얇은 aggregator, 12줄에서 `from tests.contracts.runtime.foms_namespace_surface_tests import *`) → CI `.github/workflows/ci.yml:128` + pre_push_smoke 서브셋에 등재.
- **flat 모듈 `foms/api/share.py` 에 함수를 더하는 것은 비저촉이다.** 닫힌집합 검사는 전부 *디렉토리* 단위다:
  - `foms_namespace_surface_tests.py:2361-2370` — `foms/api/` **top-level dirs** == allowlist (`_slg_iter_top_level_dirs`, 디렉토리만 순회)
  - 같은 파일 `2038-2044` — `foms/api/files` · `foms/api/measurement` 는 패키지여야 하고 flat twin(`foms/api/files.py`) 금지. `share.py` 는 대상 밖
  - `foms/api/share.py:9` 자체 docstring 이 같은 판정을 남겨 뒀다: "flat 모듈이다 — namespace 닫힌집합 게이트는 디렉토리만 검사하므로 비저촉(플랜 §0)"
- 신규 정적 자산도 안전: `foms_namespace_surface_tests.py:2024-2034`(SFC-B8 `.gitkeep` 강제)의 대상은 `static/js/{drawing,production,construction,cs,admin,auth}` 와 `static/css/{layout,components}` 뿐 — `static/css/orders/`·`static/js/orders/` 는 대상 밖이다.
- `2009-2021`(static taxonomy)도 "없어야 할 레거시 디렉토리" 와 "있어야 할 파일 5개" 만 본다 — 신규 파일 추가와 무관.

---

## B. 자산 `?v=` 핀 계약

### B-1. `?v=` 를 소스 리터럴로 검사하는 테스트 전수

핀 검사는 **전역 규칙이 아니라 자산별 명단**이다. 두 가지 형태가 있다.

**(a) 특정 자산의 핀 값을 통째로 못 박는 것** (값이 바뀌면 테스트도 같이 고쳐야 함)

| 파일:줄 | 대상 자산 |
|---|---|
| `tests/domains/test_erp_order_shared_form_scripts.py:71-93` | `erp-channel-push-confirm.js?v=20260821a`, `as-push-confirm.js?v=20260820a`, `erp-order-shared.js?v=20260829a`, `as-attachment-order.js?v=20260819a`, `erp-alimtalk-send.js?v=20260824b`, `erp-alimtalk-trace.js?v=20260824a`, **`erp-share.js?v=20260825a`**, **`erp-share.css?v=20260821a`**, `erp-stage-override.js?v=20260825a`, `erp-channel-push.css?v=20260824b`, `erp-items-master-detail.*`, `estimate-preview.js?v=20260720b` |
| 같은 파일 `227, 246, 1390-1391` | `erp-wdc-split.js`, `estimate-lifecycle.js`, `foms-form-field.css?v=20260821a`, `foms-mobile-surfaces.css?v=20260826a` |
| `tests/domains/test_drawing_collab_frontend_contract.py:44-45` | `erp-dashboard-detail-dom.js?v=20260814d`, `erp-dashboard-entry.js?v=20260814d` |
| `tests/domains/test_drawing_workbench_pc_dashboard.py:130` | `?v=20260728b` |
| `tests/domains/test_erp_add_order_autosave.py:161` | `erp-order-autosave.js?v=20260803a` |
| `tests/domains/test_construction_dashboard_mobile.py:591-593`, `tests/domains/test_erp_measurement_mobile_render.py:421-422` | `foms-v2-domain-heroes.css?v=20260712a` 외 |
| `tests/domains/test_erp_mobile_extra_input.py:52`, `tests/domains/test_erp_spec_calc_followup.py:227-228` | `foms-mobile-v3.css?v=20260826a`, `foms-form-field.css?v=20260821a` |
| `tests/domains/test_order_change_history_tab.py:204-205` | `order-change-history.js?v=20260821b`, `erp-edit-embedded.css?v=20260821a` |
| `tests/domains/test_mobile_select_ios_contract.py:52` | `foms-mobile-select.js?v=20260711a` (부재 어서션) |

**(b) 값은 안 보고 "핀이 있는지 / 저장소 전역에서 하나로 일치하는지" 만 보는 것**

| 파일:줄 | 성격 |
|---|---|
| `tests/domains/test_order_detail_drift_banner.py:202-220` | `_BANNER_ASSETS` 각각에 대해 `**/*.{html,js,py}` 를 뒤져 핀이 **정확히 1종**임을 강제 |
| `tests/domains/test_as_dashboard_schedule_link_render.py:231-247` | 동일 패턴, 대상은 `js/cs/as-dashboard.js`·`css/contexts/cs/as-dashboard-body.css` |
| `tests/domains/test_admin_audit_table_columns.py:106-111` | 지정 자산에 `?v=` 접미 존재 여부 |
| `tests/domains/test_as_timeline_wiring.py:672-677, 913-938, 1081-1085, 1153` | 각 링크에 `?v=` 존재 |
| `tests/domains/test_err_ux.py:226-241` | 스크립트 4종 `defer` + `?v=` 존재 |
| `tests/domains/test_erp_runtime_shell_js_contract.py:205-206`, `test_erp_spec_calc_followup.py:215-218`, `test_erp_spec_calc_phase3.py:236` | `?v=` 존재만 |

**공유 페이지 자산에 대한 판정**: `foms-share-view.css` · `share-view.js` · `foms-share-contract.css` · `share-contract.js` 를 이름으로 검사하는 테스트는 **저장소에 하나도 없다**(`grep -rn "foms-share-view\|share-view.js" tests/` → 0건).
→ **CI 가 핀 드리프트를 잡아 주지 않는다.** 그래서 §0-4 의 드리프트(`share_estimate_view.html:11` 만 `20260825a`)가 조용히 살아남는다. 필요하면 `test_order_detail_drift_banner.py:202` 패턴을 복제한 계약 테스트를 T1/T2 가 직접 추가하는 게 정답이다.

참고: `tests/visual/test_share_ui_contract.py` 는 이름이 비슷하지만 **ERP 쪽 공유 모달** 계약이다(`erp_share_modal.html`·`erp-share.js`·`erp-share.css`·`tablet-measure-form.js`). 고객 열람 페이지는 안 본다. 다만 이 파일은 본 스위트에서 `--ignore=tests/visual` 되고(`.github/workflows/ci.yml:109`) 별도 UI 레인(`ci.yml:173`)에서만 돌며 **pre_push_smoke 기본 서브셋에도 없다** → erp-share 자산을 건드리면 로컬 green + CI red 가 난다.

### B-2. 신규 CSS/JS 를 만들 때 등재가 필요한 곳

- **번들 목록**: 불필요. 공유 페이지는 ERP 셸을 안 쓴다(`share_*.html` 은 `{% extends %}` 없는 독립 문서). `templates/partials/shared/foms_p2_surface_bundle.html` · `layout_head.html` 은 무관.
- **서비스워커 프리캐시**: 불필요. `static/sw.js:31-35` 의 `STATIC_URLS` 는 `htmx.min.js`·`alpine.min.js`·`manifest.json` **3개뿐**이고, install 훅(`38-44줄`)이 그 3개만 `addAll` 한다. 신규 자산 등재 지점이 아니다.
- **perf 가드 G1/G2**: 별도 등재는 없지만 **allowlist 가 비어 있어서** 위반이 곧 실패다 — `tests/performance/test_perf_regression_guard.py:79`(`SYNC_SCRIPT_ALLOWLIST = frozenset()`), `82`(`CDN_SYNC_ALLOWLIST = frozenset()`). §C 참조.
- **G4(fragment 재실행 리스너)**: `FRAGMENT_REPLAYED_GLOBAL_LISTENER_BASELINE`(같은 파일 `87-104줄`)은 ERP 셸 fragment 로 재실행되는 JS 만 대상(`tools/perf/perf_scan.py:_collect_fragment_replayed_js_paths`). 공유 페이지 JS 는 대상 밖이다.
- **캐시 헤더**: `tests/performance/test_static_cache_headers.py:34-47` 이 "`?v=` 붙으면 max-age, 없으면 no-cache" 를 고정한다. 신규 파일 등재는 없고, **`?v=` 를 안 붙이면 no-cache 로 서빙**된다(성능은 손해, 기능은 정상).

### B-3. `static/sw.js` 가 `/s/<token>` 을 캐시하는가

**아니오. 페이지도 ZIP 도 캐시하지 않는다.** 근거는 `static/sw.js` fetch 핸들러(`63-104줄`):

1. `66줄` `if (req.method !== "GET") return;`
2. `76줄` `if (url.origin !== self.location.origin) return;` — 도면 이미지는 R2 교차출처라 **여기서 통과**(캐시 안 함)
3. `78-80줄` `isFileDeliveryRequest(url)` → `106-110줄`: `/api/files/` 로 시작하거나 `*.cloudflarestorage.com` 이거나 `X-Amz-Signature`/`Signature` 쿼리가 있으면 가로채지 않음
4. `82-94줄` `/static/` 접두일 때만 `staticCacheFirst`(css/js) / `staleWhileRevalidate`(그 외)
5. `96-99줄` `/api/foms/offline/queue` 만 networkFirst
6. `101-103줄` 확장자 `png|jpg|jpeg|webp|gif` 인 **same-origin** 요청만 `staleWhileRevalidate`

→ `/s/<token>`(HTML 내비게이션)·`/s/<token>/drawings.zip`(확장자 `.zip`) 은 어느 분기에도 안 걸려 SW 가 `respondWith` 를 부르지 않는다 = 네트워크 직행.

**배포 후 옛 자산 서빙 위험 판정**:
- **페이지 HTML**: 위험 없음(SW 미캐시, 서버 응답 그대로).
- **`/static/css/orders/*.css`, `/static/js/orders/*.js`**: **위험 있음**. `staticCacheFirst`(`193줄~`)가 `?v=` 를 포함한 **URL 전체를 캐시 키**로 쓴다. `?v=` 를 안 바꾸면 옛 파일이 계속 산다. 이것이 §0-4 의 핀 드리프트가 위험한 이유다.
- 단, 실제 고객은 ERP 를 방문한 적이 없어 SW 가 등록돼 있지 않을 가능성이 높다(`share_*.html` 에 SW 등록 코드 없음) — **직원이 자기 폰으로 QA 할 때 옛 자산을 볼 위험**이 실질적이다. 이 부분은 **추정**(고객 단말의 SW 등록 여부를 측정한 근거는 없음).

---

## C. perf 가드 G1~G4

전부 `tests/performance/test_perf_regression_guard.py`. 이 파일은 pre_push_smoke 기본 서브셋(`scripts/ops/pre_push_smoke.ps1:213`)과 CI(`.github/workflows/ci.yml:135`) 양쪽에 있다.

| 가드 | (a) 무엇을 검사하나 | (b) `templates/orders/share_*.html` 에도 적용되나 |
|---|---|---|
| **G1** `test_no_new_render_blocking_scripts` (`118-129줄`) | `_collect_sync_scripts()`(`60-71줄`)가 **`TEMPLATES.rglob("*.html")` = templates/ 전체**를 훑어 `defer`/`async`/`type=module` 이 없는 `<script src=...>` 를 모은다(`_is_render_blocking`, `36-45줄`). allowlist 는 `SYNC_SCRIPT_ALLOWLIST = frozenset()`(**79줄, 비어 있음**) → 하나라도 나오면 실패 | **예.** `rglob` 이라 `templates/orders/share_*.html`·`templates/orders/partials/share_*.html` 모두 포함. 신규 `<script src>` 에는 **반드시 `defer`** 를 붙여라(현재 `share_estimate_view.html:26`·`share_view.html:24-25`·`share_bundle_view.html:30-31` 은 전부 defer — OK) |
| **G2** `test_no_new_external_cdn_sync_scripts` (`131-141줄`) | 같은 수집 결과 중 키가 `cdn:` 인 것(= `src` 가 `http(s)://` 로 시작, `_script_key` `48-58줄`)만 추려 `CDN_SYNC_ALLOWLIST = frozenset()`(**82줄**)와 대조 | **예 (템플릿에 태그로 쓸 경우에만).** |
| **G3** `test_service_worker_networkfirst_has_timeout` (`143-155줄`) | `static/sw.js` 에 `networkFirst` 문자열이 있으면 `NETWORK_FIRST_TIMEOUT_MS` + `setTimeout` 을 요구 | 공유 페이지와 무관(sw.js 파일 하나만 본다). 단 §B-3 대로 sw.js 를 건드릴 일이 없으면 비저촉 |
| **G4** `test_fragment_replayed_global_listeners_are_guarded_or_frozen` (`165-186줄`) | `perf_scan._collect_fragment_replayed_js_paths()` 가 돌려주는 **ERP 셸 fragment 재실행 JS** 만 대상. 전역 리스너 수를 `FRAGMENT_REPLAYED_GLOBAL_LISTENER_BASELINE`(`87-104줄`)과 대조 | **아니오.** 공유 페이지는 fragment 스왑 대상이 아니다 |

### (c) html2canvas 를 CDN 에서 lazy-load 하면 G2 에 걸리는가 — **걸리지 않는다**

- G2 의 모집단은 **템플릿 안의 `<script src>` 태그**뿐이다(`_collect_sync_scripts`, `62-71줄`). JS 안에서 `document.createElement('script')` 로 만드는 것은 정규식 `_SCRIPT_TAG`(`33줄`)의 사정권 밖이다.
- 게다가 G2 실패 메시지 자체가 그 방식을 **해법으로 지목**한다(`139-140줄`): "해결: defer 부여, 또는 사용 시점 동적 로드(**html2canvas의 `_ensureHtml2canvas` 패턴**), 또는 self-host".
- 복제할 선례 2개(둘 다 같은 CDN URL `https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js`):
  - `static/js/measurement/image-export.js:6-34` (`ensureHtml2canvas`, 주석 10줄에 "perf guard G2" 명시)
  - `static/js/drawing/wizard.js:37, 95-110` (`_ensureHtml2canvas`, 주석 95줄에 같은 근거)
- CSP 도 막지 않는다 — 저장소 전체에서 `Content-Security-Policy` 헤더를 설정하는 코드가 **0건**(`grep -rn "Content-Security-Policy" foms/ templates/` → 없음).

---

## D. iOS / Android 인앱 브라우저 제약

### D-1. 저장소 안의 선례

**인앱 브라우저 감지**: `_is_kakao_inapp`(`foms/api/share.py:246-257`, T2 가 이번에 새로 넣은 것) **이전에는 저장소에 KAKAOTALK / in-app 감지 코드가 하나도 없었다**(`grep -rni "KAKAOTALK|inapp|in-app|인앱" static/js/ foms/ templates/` → 무관한 "in-app 알림" 3건뿐). 즉 **이번이 첫 선례**다.

**클립보드 폴백 (정본 패턴)**: `static/js/orders/erp-share.js:205-220`
```js
/** 클립보드 복사(secure context 불가 시 execCommand 폴백). */
... if (navigator.clipboard && navigator.clipboard.writeText) { ... }
```
같은 패턴이 5곳에 더 있다 — `static/js/channel/core.js:73, 87-88`, `static/js/foms/kv-copy.js:34-35`, `static/js/foms/tablet-measure-form.js:1930-1948`(가장 완성형: Clipboard API → 실패 시 `execCommand("copy")`), `static/js/orders/erp-order-shared.js:4992-5007`.

**PNG 저장 (정본 패턴)**: `static/js/measurement/image-export.js:414-419`
```js
const link = document.createElement('a');
link.download = labelYyMmDd + ' 실측 일정.png';
link.href = canvas.toDataURL('image/png');   // ← toBlob 아님
document.body.appendChild(link); link.click(); document.body.removeChild(link);
```
**`toDataURL` 을 쓰고 있다.** §D2-5·7 의 조사 결과와 정확히 일치한다 — T1 은 이걸 복제하면 된다.

**iOS 분기 선례**: `static/js/orders/erp-share.js` 의 sms 딥링크 — iOS 는 본문 구분자가 `&`(계약 테스트 `tests/visual/test_share_ui_contract.py:117-119` 가 `"iPhone" in js and "'&'" in js` 로 못 박음).

**`window.print()` 현재 사용처**: `templates/orders/share_estimate_view.html:28-32`(재작성 전) + `templates/orders/share_bundle_view.html:33-37`. **다른 대안 경로가 전혀 없었다** — 이것이 사용자 보고 "버튼 눌러도 무반응" 의 직접적 표면이다.

### D-2. 웹 조사 결과 (출처 URL 동반)

1. **iOS Safari/Chrome 의 zip 다운로드** — iOS 13 부터 Safari 에 네이티브 다운로드 매니저가 생겨 zip 이 파일 앱 "다운로드" 폴더에 저장되고, 탭하면 자동 압축 해제된다. `download` 속성도 iOS 13.0 에 WebKit 이 추가(WebKit 개발자 확인).
   - https://bugs.webkit.org/show_bug.cgi?id=167341
   - https://macmost.com/how-to-download-files-on-your-iphone-and-unzip-them-if-needed.html
   - iOS Chrome 은 애플 정책상 WebKit 엔진 강제라 동작이 Safari 와 동일: https://9to5mac.com/2023/02/07/new-iphone-browsers/
   - 알려진 한계: Content-Disposition 이 길면 Safari 에서만 파일명이 잘리는 버그 https://developer.apple.com/forums/thread/685138

2. **카카오톡 인앱 + `Content-Disposition: attachment`** — 카카오 데브톡 FAQ 기준 **HTTP 응답 헤더 방식(Content-Type/Content-Disposition/Content-Length)이 iOS·Android 양쪽에서 지원되는 유일한 공식 방식**이다(`<a download>` 는 Android 전용, dataURL 은 iOS 전용으로 갈림).
   - https://devtalk.kakao.com/t/topic/146168
   - 다만 Android 인앱에서 "다운로드 완료 토스트는 뜨는데 파일이 없다" 는 간헐 실패가 반복 보고됨(외부 브라우저에서는 정상): https://devtalk.kakao.com/t/pdf/126993 · https://devtalk.kakao.com/t/topic/146696 · https://devtalk.kakao.com/t/topic/139198
   - → **T2 의 헤더 방식은 옳은 선택이고, 그럼에도 "다른 브라우저로 열기" 안내와 개별 저장 폴백이 필수다.**

3. **`window.print()`** — 근본 원인: **Android WebView 와 iOS WKWebView 는 `window.print()` 를 기본 구현하지 않는다.** 브라우저 엔진 기능이 아니라 호스트 앱이 JS 호출을 가로채 Android `PrintManager` / iOS `UIPrintInteractionController` 에 연결해 줘야 뜬다. 카카오톡 인앱은 그 배선이 없는 일반 WebView 라 **아무 반응이 없는 게 정상 결과**다.
   - https://velog.io/@jmseb3/webview에서-window.print-대응하기
   - https://gist.github.com/brettwold/838c092329c486b6112c8ebe94c8007e
   - SFSafariViewController 는 공유 시트에 "프린트" 가 있어 수동 인쇄가 되지만, WKWebView(카카오톡 방식)는 그 UI 자체가 없다: https://medium.com/@jameskong_35184/migration-guide-from-sfsafariviewcontroller-to-wkwebview-in-swiftui-221013107556 · https://github.com/ionic-team/capacitor/discussions/7283

4. **`navigator.clipboard.writeText`** — MDN: 보안 컨텍스트(HTTPS) 필수, `clipboard-write` 권한 필요(Chromium 은 iframe 에 명시 위임), Safari/WebKit 계열은 **transient user activation** 시점에 즉시 호출해야 한다. 비동기 처리 뒤에 호출하면 활성화가 끊겨 `NotAllowedError`.
   - https://developer.mozilla.org/en-US/docs/Web/API/Clipboard_API
   - https://developer.mozilla.org/en-US/docs/Web/API/Clipboard/writeText
   - 실사례: https://github.com/dotnet/aspnetcore/issues/38211
   - 폴백 정본: 임시 `<textarea readonly>` → `select()`/`setSelectionRange()` → `document.execCommand('copy')` → 제거. iOS 함정: readonly 만으로 선택이 안 잡히는 경우가 있어 **contentEditable=true + readonly + setSelectionRange(0, len)** 조합이 필요하다는 보고. `execCommand` 는 Deprecated 라 최신 iOS 에서 불안정할 수 있음.
     https://dev.to/phuocng/clipboard-api-fallback-nh7 · https://developer.apple.com/forums/thread/724076
   - → **T1 의 계좌 복사는 클릭 핸들러 안에서 `navigator.clipboard.writeText` 를 `await` 없이 즉시 호출**해야 한다. 저장소 정본은 `static/js/foms/tablet-measure-form.js:1930-1948`.

5. **`canvas.toBlob` / `<a download>` blob 저장** — `download` 속성은 iOS 13.0 에 추가됐지만(위 167341), **WKWebView 는 `blob:` URL 을 `download` 앵커의 `href` 로 지원하지 않는 별도 미해결 버그가 있다**.
   - https://bugs.webkit.org/show_bug.cgi?id=216918
   - 카카오톡 인앱 실측 정리: **Blob 은 iOS/Android 인앱 모두 실패, `canvas.toDataURL()` 방식은 성공** — https://devtalk.kakao.com/t/topic/146168 · https://velog.io/@gaebaribari/카카오-인앱-브라우저-사진-다운
   - 대안: 새 탭에 열어 길게 눌러 저장, 또는 Web Share API `navigator.share({files})`(iOS 15+, 일부 iOS 16 환경에서 "사진에 저장" 이 빠지는 사례 보고) — https://blog.bitsrc.io/sharing-files-from-ios-15-safari-to-apps-using-web-share-c0e98f6a4971

6. **카카오톡 인앱 → 외부 브라우저 강제 열기**
   - **iOS**: `kakaotalk://web/openExternal?url=<encoded>` — 카카오 **공식 문서에는 미등재**, 데브톡/커뮤니티에서 공유되는 비공식 방식. 앱 업데이트로 막힐 수 있어 신뢰도 중간. https://devtalk.kakao.com/t/topic/77940 · https://burndogfather.com/271
   - **Android**: `intent://<url-without-scheme>#Intent;scheme=http;package=com.android.chrome;end` — 카카오 전용이 아니라 **Android OS 표준 Intent URI**. Chrome 설치 의존이지만 메커니즘 자체는 공식 스펙이라 iOS 보다 신뢰도 높음. https://burndogfather.com/271
   - **iOS 에는 Safari 를 강제로 여는 공식 스킴이 없다** — https://developer.apple.com/forums/thread/688562. 실무 대안은 "링크 복사 → 직접 붙여넣기 안내"(**추정**: 실무 관행).
   - 카카오톡 우상단 `…` > "다른 브라우저로 열기" 는 사용자가 쓸 수 있는 내장 UI(코드 불필요)지만 **developers.kakao.com 원문 근거는 미확보(추정)**.

7. **html2canvas PNG 다운로드 (카카오톡 인앱)** — 5번과 동일 결론. `toBlob()` + `<a download>` 는 실패 사례 다수, `toDataURL()` + `<a download>` 는 외부 브라우저·인앱·iOS·Android 전체에서 동일 코드로 동작 확인.
   - https://velog.io/@gaebaribari/카카오-인앱-브라우저-사진-다운

8. **User-Agent 토큰** — Android 는 UA 에 리터럴 `KAKAOTALK` 포함(최신형 `... Mobile Safari/537.36 KAKAOTALK/25.4.3 (INAPP)`, 구형 `...;KAKAOTALK 1908810`).
   - https://whatmyuseragent.com/apps/kakaotalk
   - iOS 도 같은 토큰이 들어간다는 게 통설이나 **정확한 iOS UA 전문 출처 미확보 → 추정**. 참고: https://github.com/stulle123/kakaotalk_analysis/blob/main/doc/WEBVIEW.md

### D-3. "저장 버튼 무반응" 근본 원인 순위

**1순위 — `window.print()` 가 카카오톡 인앱 웹뷰에 구현돼 있지 않다.**
- 근거(코드): 재작성 전 `templates/orders/share_estimate_view.html:28-32` 의 유일한 저장 경로가 `window.print()` 였고, 실패해도 예외조차 안 난다(호출 자체가 no-op). 대안 경로 0개.
- 근거(외부): §D2-3 — Android WebView/iOS WKWebView 는 호스트 앱이 배선하지 않으면 `window.print()` 가 아무 것도 안 한다.
- **반증/확인 방법**: 카카오톡 인앱에서 페이지를 열고 콘솔 접근이 안 되므로, 버튼 핸들러에 `try { window.print(); } catch(e){}` 대신 **화면에 보이는 상태 문구**(예: `[data-share-print-state]` 텍스트를 "인쇄 창을 여는 중…" 으로 바꾸기)를 넣어 배포한다. 문구가 바뀌는데 인쇄 창이 안 뜨면 → 핸들러는 돌았고 `print()` 가 무시된 것 = 1순위 확정. 문구조차 안 바뀌면 2순위로 넘어간다.

**2순위 — 클릭 핸들러 자체가 안 붙었다(JS 실행 실패).**
- 근거(코드): 재작성 전 핸들러가 인라인 `<script>` + `document.querySelector('[data-share-print]').addEventListener(...)` 였다. `share_estimate_view.html:29` 은 **옵셔널 체이닝이 없어** 요소가 없으면 `TypeError` 로 스크립트가 통째로 죽는다(`share_bundle_view.html:35` 는 `?.` 가 있어 안 죽음). 또 인앱 웹뷰의 구형 JS 엔진에서 문법 지원 차이가 나면 파일 전체가 파싱 실패한다.
- **반증/확인 방법**: 버튼에 `onclick` 이 아니라 **CSS `:active` 시각 피드백**을 주고, 동시에 서버로 1픽셀 비콘(`fetch('/s/<token>/ping')`)을 쏘는 임시 계측을 넣는다 — 비콘이 서버 로그에 찍히면 JS 는 살아 있는 것 = 2순위 배제. (읽기 전용 조사라 실제로 넣지는 않았다.)
- 보조 확인: PC 크롬에서 같은 페이지를 열어 버튼이 동작하면 "코드 결함" 이 아니라 "환경 제약" 쪽으로 무게가 실린다.

**3순위 — 저장은 시도됐으나 결과 파일이 인앱 샌드박스에 갇혀 사용자 눈에 안 보였다.**
- 근거(외부): §D2-2 — Android 카카오톡 인앱에서 "다운로드 완료 토스트는 뜨는데 파일이 없다" 는 반복 보고. §D2-5 — blob URL 다운로드가 WKWebView 에서 실패.
- **반증/확인 방법**: `window.print()` 를 완전히 제거하고 `toDataURL` PNG 저장으로 바꾼 뒤 같은 단말에서 재현한다. 그래도 파일이 안 보이면 3순위, 정상 저장되면 1순위였음이 확정된다. (1순위와 3순위는 이 한 번의 배포로 동시에 갈린다.)

> 순위 근거 요약: 1순위는 **코드에 대안 경로가 0개였다는 저장소 사실** + **외부 문서의 미구현 확인** 두 축이 모두 맞아떨어진다. 2순위는 코드 결함 가능성은 실재하나(`share_estimate_view.html:29` 옵셔널 체이닝 부재) 그 경우 bundle 페이지에서는 증상이 달라야 하는데 사용자 보고는 계약서 링크 기준이라 구분이 안 된 상태다. 3순위는 저장 시도가 있었다는 전제가 필요한데 `window.print()` 는 파일을 만들지 않으므로 논리적으로 후순위다.

---

## E. 로컬 검증 수단

### E-1. `/s/<token>` 을 로컬에서 열어 보는 가장 짧은 절차

토큰 생성 방식은 `tests/domains/test_order_share_view.py:96-99`(`_mk_share`) / `:248-254`(`_mk_estimate_share`) / `:375-381`(`_mk_bundle_share`) 를 그대로 따랐다. 아래 스니펫은 **실제로 실행해 200 을 확인**했다.

```bash
cd /c/tmp/foms-s-kakaoshare && pwd
# 1) 토큰 발급 (인메모리 SQLite — 실제 dev DB 를 쓰려면 DATABASE_URL 만 바꾼다)
DATABASE_URL="sqlite:///:memory:" SECRET_KEY="ci-secret-key" FLASK_ENV="testing" STORAGE_TYPE=local python - <<'PY'
import datetime
import app as appmod
from db import db_session, Base, engine
from models import Order
from foms.services import order_share as osvc

with appmod.app.app_context():
    Base.metadata.create_all(bind=engine)          # 인메모리일 때만 필요
    o = Order(received_date=datetime.date(2026, 8, 31), customer_name='임다슬',
              phone='010-0000-0000', address='서울', product='가구',
              status='ERPORDER', is_erp_order=True,
              structured_data={
                  'parties': {'customer': {'name': '임다슬', 'phone': '010-0000-0000'}},
                  'site': {'address_full': '서울시 강남구'},
                  'items': [{'product_name': '무몰딩', 'quantity': 2, 'price': 500000, 'color': '화이트'}],
                  'payment': {'deposit': 100000}})
    db_session.add(o); db_session.commit()
    snap = osvc.build_estimate_snapshot(o)          # estimate/bundle 은 스냅샷 필수
    row, token = osvc.create_share_token(db_session, o.id, 'estimate', snapshot=snap)
    db_session.commit()
    print('URL =', f'/s/{token}')
    print('status =', appmod.app.test_client().get(f'/s/{token}').status_code)
PY
```

- **브라우저로 실제 열어 보려면** 인메모리 SQLite 로는 안 된다(프로세스가 끝나면 사라짐). 로컬 dev DB(`.env` 의 `DATABASE_URL`)를 쓰고 `Base.metadata.create_all` 줄을 지운 뒤 위 스니펫으로 토큰만 뽑고, 별도로 `python run.py` 를 띄워 `http://localhost:5000/s/<token>` 을 연다.
- `kind` 는 `'drawing' | 'estimate' | 'bundle'`(`foms/services/order_share.py:185-186` 이 `SHARE_KINDS` 로 검증). **estimate/bundle 은 `snapshot=` 없이 발급하면 열람이 503** 이다(`foms/api/share.py:276-280`·`296-300`, 테스트 `test_order_share_view.py:447-465`).
- 실행 시 stale Flask 서버 함정 주의: 포트 5000 에 옛 프로세스가 살아 있으면 옛 템플릿을 서빙한다(PowerShell `Stop-Process` 로 정리).

### E-2. storage_type 이 r2/s3 가 아닐 때의 도면 경로 — **fail-closed 503 확정, 로컬 검증 불가**

**실측 결과** (위 스니펫과 같은 환경에서 kind 만 바꿔 실행):

```
storage_type = local
estimate status = 200   len 3876
drawing  status = 503
zip route exists = True
```
서버 로그: `ERROR foms.api.share 공유 열람 fail-closed: storage_type=local (r2/s3 아님, share_id=2)`

- 근거(코드): 열람 `foms/api/share.py:301-306`, ZIP `foms/api/share.py:391-396`. 둘 다 `if storage.storage_type not in ('r2','s3'): logger.error(...); return _error_page(_MSG_UNAVAILABLE, 503)`.
- 근거(테스트): `tests/domains/test_order_share_view.py:476-495`(`test_view_local_storage_fail_closed_503`, `test_view_all_presign_failures_503_not_blank`).
- **`estimate` kind 만 예외적으로 로컬에서 렌더된다** — `foms/api/share.py:274-291` 이 `get_storage()`(301줄) 호출 **이전에** `return render_template('orders/share_estimate_view.html', ...)` 로 빠져나가기 때문이다. **T1 의 계약서 작업은 로컬 브라우저 검증이 완전히 가능하다.**
- **`drawing`/`bundle`/ZIP 은 로컬 검증 불가**:
  - `foms/services/storage.py:142-204` 의 `_detect_storage_type()` — `STORAGE_TYPE=r2` 를 강제해도 R2 클라이언트 초기화가 실패하면 `local` 로 되돌아간다(`:50-54, :86, :101`).
  - 이 워크트리 `.env` 에 **R2_* 키가 0개**(`grep -c "R2_" .env` → 0).
  - → 실검증 경로는 두 가지뿐: **(a) pytest 스텁** — `tests/domains/test_order_share_view.py:26-50` 의 `FakeR2Storage` / `LocalStorage` / `BrokenPresignStorage` 를 `monkeypatch.setattr(share_routes, 'get_storage', ...)` 로 갈아끼운다. ZIP 은 여기에 `read_file_bytes(key) -> bytes` 를 추가한 스텁이 필요하다(`foms/services/storage.py:346` 시그니처). **(b) 스테이징 실서버** — `lahom-dev.up.railway.app` 에서 실제 토큰을 발급해 확인.

---

## 부록 — 조사 중 실행한 게이트 결과 (2026-08-31, 조사 시점)

```
pytest tests/performance/test_perf_regression_guard.py \
       tests/domains/test_failopen_inventory.py \
       tests/domains/test_audit_coverage_inventory.py \
       tests/domains/test_write_guard.py \
       tests/domains/test_admin_audit_screen_readability_3.py
→ 48 passed

pytest tests/domains/test_order_share_view.py \
       tests/domains/test_order_share_estimate.py \
       tests/visual/test_share_ui_contract.py
→ 1 failed, 34 passed
   FAILED tests/domains/test_order_share_view.py::test_view_estimate_renders_snapshot_only
   (test_order_share_view.py:283  assert '견적서' in body)
```

렌더 본문 실측(estimate, 로컬 storage): `'견적서' False` · `'계약서' True` · `'임다슬' True` · `'1,000,000' True` · `'461-082990-04-011' True` · `'share-contract.js' True` · `'foms-share-contract.css' True` · `'data-share-print' True` · `'인감' True` · `'company-stamp' True`.

### 스냅샷 화이트리스트 관련 주의 (T1)

- `build_estimate_snapshot`(`foms/services/order_share.py:79-160`)에 **계약번호·인감 경로·법적문구·안내문구 필드는 없다.** ERP 계약서 폼의 계약번호는 클라이언트가 조립한다(`static/js/orders/estimate-preview.js:973` — `날짜_전화뒷자리`).
  → 새 필드를 스냅샷에 추가하면 **이미 발급된 토큰에는 그 키가 없다**(Jinja 기본 `Undefined` — 빈 문자열로 렌더되며 예외는 안 난다; 저장소에 `StrictUndefined` 설정 없음 확인). 화면이 조용히 비는 것을 감수할지 판단이 필요하다.
- `factory2`(발주사 판정)는 **의도적으로 스냅샷에서 차단**돼 있다(`order_share.py:83-85`). 인감/로고 브랜드 분기는 `snap.company_info.name == '라홈시스템'` 으로 판정하는 기존 방식(`templates/orders/share_estimate_view.html` 헤더)을 그대로 써야 한다.
- 품목 행 키는 `_SNAPSHOT_ITEM_KEYS`(`order_share.py:38-41`) — `product_name, spec, color, option_detail, quantity, unit_price, amount`. 계약 테스트 `tests/domains/test_order_share_estimate.py:92` 가 상수에서 기대값을 유도하므로 상수만 고치면 red 가 안 난다.
