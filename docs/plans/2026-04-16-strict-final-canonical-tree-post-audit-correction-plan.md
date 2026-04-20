# Strict Final Canonical Tree — Post-Audit Correction Plan

> 작성일: 2026-04-16
> 상위 기준: `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md` §2.2.1, `docs/plans/2026-04-15-strict-final-canonical-tree-100-percent-execution-plan.md`
> 직전 실행 기준: `docs/plans/2026-04-15-strict-final-canonical-tree-literal-gap-remediation-plan.md`, `docs/plans/2026-04-15-strict-final-canonical-tree-literal-gap-slgb7-run-record.md`

## 1. Purpose

이 문서는 `SLG-B7` closeout 이후 2026-04-16 hard audit에서 확인된 **remaining strict-literal drift**를 바로 교정하기 위한 후속 실행계획이다.

이번 후속 tranche의 목표는 아래 둘을 동시에 만족시키는 것이다.

1. `§2.2.1 Final canonical tree`와 **실제 물리 구조 / runtime contract / proof gate**를 다시 1:1로 맞춘다.
2. `SLG-B7` closeout이 놓친 false-green 경로를 닫고, **full `pytest tests -q` green**까지 closeout proof로 승격한다.

## 2. Current Findings Register

### 2.1 `PAF-C1` — Channel page endpoint drift

`/chat` page owner는 `foms/web/channel/routes.py`인데, page callers 일부가 여전히 legacy endpoint string `chat.chat`, `chat.chat_scripts_js`를 사용한다.

대표 live evidence:

- `templates/partials/shared/layout_nav.html`
- `templates/channel/chat.html`
- full `pytest tests -q` outside sandbox 기준 `BuildError: Could not build url for endpoint 'chat.chat'`

결론: package move는 끝났지만 **page endpoint contract reroute**가 덜 끝났다.

### 2.2 `PAF-E1` — Global error handling plan drift

기존 literal-gap plan은 `404/500`을 `foms/platform/http.py` inline helper로 고정했지만, 실제 closeout은 `templates/partials/http_errors/*.html`을 새 full-page template owner로 사용했다.

대표 evidence:

- `foms/platform/http.py`
- `templates/partials/http_errors/error_404.html`
- `templates/partials/http_errors/error_500.html`
- `SLG-B2` / `SLG-B7` run record

결론: `templates/errors`는 없어졌지만, **forbidden global error template detour**가 새 경로에 남았다.

### 2.3 `PAF-S1` — `templates/partials/shared/` overbroad proof

스펙은 `templates/partials/shared/`에 **cross-context partial only**를 허용하지만, 현재 테스트와 closeout은 `erp_*.html` 대량 존재를 green 신호로 사용한다.

대표 evidence:

- spec §2.2.1 보충 규칙: `templates/partials/shared/`는 cross-context partial만 허용
- `tests/contracts/runtime/foms_namespace_surface_tests.py`
- `templates/partials/shared/erp_construction_*`
- `templates/partials/shared/erp_dashboard_*`
- `templates/partials/shared/erp_completion_*`
- `templates/partials/shared/erp_measurement_*`
- `templates/partials/shared/erp_production_*`

결론: `shared` subtree가 합법 경로 안의 **context-specific sink**로 남아 있고, proof layer가 그 drift를 통과시키고 있다.

### 2.4 `PAF-P1` — Closeout proof too weak

`SLG-B7`는 `pytest tests/contracts/runtime/foms_namespace_surface_tests.py` + clean-room green으로 closeout을 선언했지만, hard audit에서 full suite는 여전히 red였다.

대표 evidence:

- `SLG-B7` run record에서 full `pytest tests -q`는 optional
- 2026-04-16 재검증에서 outside sandbox 기준 full `pytest tests -q` 실패

결론: 앞으로는 **full suite green 없이 strict-literal closeout 선언 불가**다.

## 3. Decision Lock

### 3.1 Channel page endpoint contract

`/chat` human-facing page는 `channel` context 안의 page lane이며, page endpoint string은 아래 둘로 고정한다.

- `channel_chat_pages.chat`
- `channel_chat_pages.chat_scripts_js`

금지:

- `url_for('chat.chat')`
- `url_for('chat.chat_scripts_js')`

주의:

- `foms.api.channel.blueprint.py`의 `chat_bp`는 JSON/API surface용으로만 유지한다.
- page endpoint와 API blueprint 이름을 다시 섞지 않는다.

### 3.2 Global HTTP error handling

404/500의 final owner는 template가 아니다.

허용:

- `foms/platform/http.py` 내부 helper-generated inline HTML response

금지:

- `templates/errors/*`
- `templates/partials/http_errors/*`
- `render_template("errors/...")`
- `render_template("partials/http_errors/...")`

### 3.3 `templates/partials/shared/` exact allowlist

closeout 시 `templates/partials/shared/`에 남아도 되는 파일은 아래 exact allowlist뿐이다.

- `layout_head.html`
- `layout_nav.html`
- `layout_flash.html`
- `layout_scripts.html`
- `erp_mobile_shell.html`
- `erp_mobile_shell_header.html`
- `erp_mobile_bottom_nav.html`
- `erp_mobile_menu_drawer.html`
- `erp_mobile_queue_card.html`
- `erp_sub_nav.html`

이 외 `erp_*.html`은 모두 아래 둘 중 하나여야 한다.

1. 해당 `templates/<context>/partials/` 아래의 context-owned file로 이동
2. 이미 context-owned canonical이 있으면 wrapper 없이 retire

### 3.4 Full-suite proof precedence

이번 후속 tranche부터 final closeout proof는 아래 4개를 모두 요구한다.

1. `python -c "import app; print('APP_OK')"`
2. `python tools/harness/verify_result.py --json`
3. `pytest tests/contracts/runtime/foms_namespace_surface_tests.py`
4. `pytest tests -q`

clean-room은 위 4개를 대체하지 못한다. final closeout에서는 `tools/harness/strict_canonical_b12_clean_room.ps1 -Ref HEAD -RunFullPytest`를 요구한다.

## 4. Correction Target Ledger

### 4.1 Channel caller reroute

수정 대상:

- `templates/partials/shared/layout_nav.html`
- `templates/channel/chat.html`
- 기타 `chat.chat*` string caller 전수

canonical target:

- `channel_chat_pages.chat`
- `channel_chat_pages.chat_scripts_js`

### 4.2 Error handler remediation

삭제 대상:

- `templates/partials/http_errors/error_404.html`
- `templates/partials/http_errors/error_500.html`
- `templates/partials/http_errors/`

canonical target:

- `foms/platform/http.py` inline helper

### 4.3 Shared partial redistribution map

`templates/partials/shared/` -> final target:

- `erp_as_mobile_controls.html` -> `templates/cs/partials/as_mobile_controls.html`
- `erp_completion_scripts.html` -> `templates/cs/partials/completion_scripts.html`
- `erp_completion_styles.html` -> `templates/cs/partials/completion_styles.html`

- `erp_construction_filters.html` -> `templates/construction/partials/filters.html`
- `erp_construction_filters_grid.html` -> `templates/construction/partials/filters_grid.html`
- `erp_construction_mobile_filters.html` -> `templates/construction/partials/mobile_filters.html`
- `erp_construction_mobile_queue.html` -> `templates/construction/partials/mobile_queue.html`
- `erp_construction_modals.html` -> `templates/construction/partials/modals.html`
- `erp_construction_scripts.html` -> `templates/construction/partials/scripts.html`
- `erp_construction_styles.html` -> `templates/construction/partials/styles.html`

- `erp_dashboard_filters.html` -> `templates/orders/partials/dashboard_filters.html`
- `erp_dashboard_grid.html` -> `templates/orders/partials/dashboard_grid.html`
- `erp_dashboard_mobile_filters.html` -> `templates/orders/partials/dashboard_mobile_filters.html`
- `erp_dashboard_mobile_queue.html` -> `templates/orders/partials/dashboard_mobile_queue.html`
- `erp_dashboard_modals.html` -> `templates/orders/partials/dashboard_modals.html`
- `erp_dashboard_scripts.html` -> `templates/orders/partials/dashboard_scripts.html`
- `erp_dashboard_scripts_attachments.html` -> `templates/orders/partials/dashboard_scripts_attachments.html`
- `erp_dashboard_scripts_core.html` -> `templates/orders/partials/dashboard_scripts_core.html`
- `erp_dashboard_scripts_detail_dom.html` -> `templates/orders/partials/dashboard_scripts_detail_dom.html`
- `erp_dashboard_scripts_drawing.html` -> `templates/orders/partials/dashboard_scripts_drawing.html`
- `erp_dashboard_scripts_gateway.html` -> `templates/orders/partials/dashboard_scripts_gateway.html`
- `erp_dashboard_scripts_quest.html` -> `templates/orders/partials/dashboard_scripts_quest.html`
- `erp_dashboard_styles.html` -> `templates/orders/partials/dashboard_styles.html`
- `erp_beta_js.html` -> `templates/orders/partials/beta_js.html`
- `erp_beta_tab.html` -> `templates/orders/partials/beta_tab.html`
- `erp_estimate_pane.html` -> `templates/orders/partials/estimate_pane.html`
- `erp_history_detail_content.html` -> `templates/orders/partials/history_detail_content.html`

- `erp_measurement_mobile_dates.html` -> retire wrapper, keep `templates/measurement/partials/mobile_dates.html`
- `erp_measurement_mobile_filters.html` -> retire wrapper, keep `templates/measurement/partials/mobile_filters.html`
- `erp_measurement_mobile_list.html` -> retire wrapper, keep `templates/measurement/partials/mobile_list.html`

- `erp_production_filters.html` -> retire wrapper, keep `templates/production/partials/filters.html`
- `erp_production_filters_grid.html` -> retire wrapper, keep `templates/production/partials/filters_grid.html`
- `erp_production_mobile_filters.html` -> retire wrapper, keep `templates/production/partials/mobile_filters.html`
- `erp_production_mobile_queue.html` -> retire wrapper, keep `templates/production/partials/mobile_queue.html`
- `erp_production_modals.html` -> retire wrapper, keep `templates/production/partials/modals.html`
- `erp_production_scripts.html` -> retire wrapper, keep `templates/production/partials/scripts.html`
- `erp_production_styles.html` -> retire wrapper, keep `templates/production/partials/styles.html`

## 5. Fixed Batch Order

### 5.1 `PAC-B0` — Authoring / truth freeze

docs-only.

필수 산출물:

- 본 계획서
- 2026-04-16 hard audit findings freeze
- `SLG-B7` false-green axis 분리 기록

검증:

- no code change
- `APP_OK`

### 5.2 `PAC-B1` — Proof freeze for post-audit gaps

docs/tests/tooling only. test red 허용.

필수 작업:

- `tests/contracts/runtime/foms_namespace_surface_tests.py`에 아래 gate 설계/freeze
  - no `url_for('chat.chat')`
  - no `url_for('chat.chat_scripts_js')`
  - no `templates/partials/http_errors/`
  - no `render_template("partials/http_errors/...")`
  - `templates/partials/shared/` child file set == §3.3 exact allowlist
- `tools/harness/strict_canonical_b12_clean_room.ps1`에 아래 요구를 문서화
  - forbid `templates/partials/http_errors`
  - compare `templates/partials/shared/` child file set == §3.3 exact allowlist
  - final mode는 `-RunFullPytest`가 closeout 기준
- `SLG-B2`의 `partials/http_errors` detour success record와 `SLG-B7`의 “full pytest optional” closeout claim을 함께 overturn하는 correction note 준비

검증:

- red 허용
- focused pytest + `APP_OK`

### 5.3 `PAC-B2` — Channel page endpoint correction

code batch.

필수 작업:

- `chat.chat` / `chat.chat_scripts_js` page callers 전수 제거
- page callers를 `channel_chat_pages.chat`, `channel_chat_pages.chat_scripts_js`로 교체
- focused page render tests green
- full suite red 핵심 원인인 `BuildError` cluster 제거

검증:

- `rg -n "chat\\.chat|chat\\.chat_scripts_js" templates foms` -> 0
- focused pytest
- `APP_OK`

### 5.4 `PAC-B3` — Inline HTTP error finalization

code batch.

필수 작업:

- `foms/platform/http.py`에 helper-generated inline HTML response 구현
- `render_template("partials/http_errors/...")` 제거
- `templates/partials/http_errors/` 전체 삭제
- 관련 test / build-info / docs 증거 정렬

검증:

- `rg -n "partials/http_errors|render_template\\(\"partials/http_errors" foms templates tests` -> 0
- focused pytest
- `APP_OK`

### 5.5 `PAC-B4` — Shared partial redistribution

code batch.

필수 작업:

- §4.3 ledger대로 context-specific partial 이동 / wrapper retire
- callers를 새 context-owned partial로 갱신
- `templates/partials/shared/`를 §3.3 exact allowlist로 축소

검증:

- `templates/partials/shared/` file set == §3.3
- focused pytest
- `APP_OK`

### 5.6 `PAC-B5` — Final proof hardening + closeout correction

docs/tests/tooling batch.

필수 작업:

- `PAC-B1` gate들을 최종 green으로 land
- `pytest tests -q`를 closeout 필수 조건으로 run record / docs에 반영
- `SLG-B2` / `SLG-B7` overclaim correction note 작성
- `docs/AI_STATUS.md`는 새 closeout 증거로만 갱신

closeout acceptance:

- no `chat.chat` / `chat.chat_scripts_js` page caller
- no `templates/partials/http_errors`
- `templates/partials/shared/` exact allowlist only
- `python -c "import app; print('APP_OK')"` green
- `python tools/harness/verify_result.py --json` green
- `pytest tests/contracts/runtime/foms_namespace_surface_tests.py` green
- `pytest tests -q` green
- `tools/harness/strict_canonical_b12_clean_room.ps1 -Ref HEAD -RunFullPytest` green
- clean-room script가 `templates/partials/shared/` exact allowlist compare를 실제 수행

## 6. Review Loop

각 code batch 직후 아래 감리를 모두 수행한다.

### 6.1 reviewer A — literal tree / spec reviewer

확인 항목:

- `partials/http_errors` 같은 새 detour가 남아 있지 않은가
- `templates/partials/shared/` exact allowlist 밖 파일이 남아 있지 않은가
- context-owned partial이 다시 shared wrapper로 남지 않았는가

### 6.2 reviewer B — runtime / endpoint reviewer

확인 항목:

- `/chat` page caller가 모두 `channel_chat_pages.*`를 사용하는가
- API `chat_bp`와 page endpoint가 다시 섞이지 않았는가
- full pytest에서 page-render / nav / WDCalculator / ERP dashboard 회귀가 사라졌는가

### 6.3 reviewer C — proof reviewer

확인 항목:

- strict tests가 새 drift를 실제로 잡는가
- clean-room이 `partials/http_errors`와 shared allowlist drift를 놓치지 않는가
- full suite green이 run record에 실제 증거로 남았는가

### 6.4 stop rule

다음 중 하나라도 참이면 다음 batch로 넘어가면 안 된다.

- High 1개 이상
- Medium 1개 이상
- strict tests green인데 full `pytest tests -q` red
- clean-room green인데 §3.2 / §3.3 금지 상태가 실제 디스크에 남아 있음
- run record가 plan과 다른 remediation path를 성공으로 기록함

## 7. First-Turn Operator Prompt

다음 LLM은 첫 턴에 아래를 먼저 고정한다.

1. 이번 tranche는 post-audit correction이며, `SLG-B7`을 다시 검증 없이 신뢰하지 않는다.
2. 시작 배치는 `PAC-B1`이다.
3. `/chat` page endpoint는 `channel_chat_pages.*`만 합법이다.
4. 404/500은 inline helper만 합법이며, `partials/http_errors`는 금지다.
5. `templates/partials/shared/`는 §3.3 exact allowlist만 허용한다.
6. final closeout은 full `pytest tests -q` green 없이는 불가다.

## 8. Non-Negotiable Notes

- 이번 문서는 `§2.2.1`을 느슨하게 해석하기 위한 문서가 아니다.
- `partials/http_errors`를 새 합법 경로로 재정의하면 실패다.
- context-owned partial이 이미 존재하는데 shared wrapper를 남겨두는 것은 실패다.
- `tests/contracts/runtime/foms_namespace_surface_tests.py`가 다시 `len(shared.glob("erp_*.html")) >= ...` 같은 count-based green을 사용하면 실패다.
- `SLG-B7`의 기존 green 증거는 historical evidence일 뿐, 이번 correction tranche의 completion proof가 아니다.
