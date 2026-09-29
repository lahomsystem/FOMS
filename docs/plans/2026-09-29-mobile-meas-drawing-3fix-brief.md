# 모바일 실측·도면 3건 브리프 (2026-09-29, 초안 — CEO가 고칠 수 있다)

워크트리: `c:/tmp/foms-s-s0929-093058` (branch `session/s0929-093058`, base origin/deploy `dfb6763b7`).
운영 화면: https://lahom-production.up.railway.app/erp/measurement (모바일 v2 셸).

## T1. 실측 탭 최초 로딩 = 모든 담당자 그룹 접힘
- 증상: 실측 탭을 열면 첫 담당자 그룹(최진호)만 펼쳐져 있다. 사용자 요구: 처음엔 **모두 접힌 채** 로딩.
- 앵커:
  - `templates/measurement/partials/mobile_list.html:15-23` (`_gv_open` 네임스페이스·closed 카운트·open_names)
  - `templates/measurement/partials/mobile_list.html:52` (모두 펼치기/접기 라벨)
  - `templates/measurement/partials/mobile_list.html:58` `_g_open = _gv_mine or (_gv_open.any_me and _is_me) or ((not _gv_open.any_me) and loop.first)`
  - `static/js/measurement/mobile-glance-tabs.js` — `saveOpen`/localStorage `STORE_KEY` 복원 경로가 있다. 복원이 첫 로딩을 다시 펼치는지 확인할 것.
- 경계: `_gv_mine`(내 담당만 보기, 그룹 1개) 모드는 접기 버튼 자체가 없다 → 그대로 펼침 유지. `is-me`(로그인 사용자 본인 그룹) 자동 펼침도 "모두 접힘" 요구에 포함되는지 판단(요구 문장 "최초 모든 카드 닫아서" → 본인 그룹도 닫는 쪽이 기본값 후보).
- 사용자가 이번 화면에서 직접 펼친 상태를 새로고침 뒤 기억하는 동작(localStorage)을 유지할지: "최초" = 탭 진입 시. 판단 근거를 보고.
- 테스트: `grep -rn "meas-glance\|_g_open\|loop.first" tests/` 로 이 동작을 못박은 테스트를 찾아 갱신.

## T2. 도면 탭 "주문 변경" 말풍선 — 실측 담당자에게 필요한가
- 앵커: `templates/drawing/partials/workbench_mobile_handoff.html:175-200` (`foms-drawing-thread__tag` 주문 변경 · `__changes` · `data-dw-order-change-ack` 확인 버튼), PC 대응 `templates/drawing/partials/workbench_detail_body.html:999-1004`, JS `static/js/drawing/order-change-banner.js:77,156`, API `/api/orders/<id>/drawing/ack-order-change`.
- 질문: 이 정보(주문 변경 diff + "이 주문 변경 N줄 확인")는 도면팀이 확인할 정보. 실측 담당자(모바일로 도면 탭을 보는 현장 인력)가 보거나 눌러야 하나?
- 조사: 이 말풍선·확인 버튼을 누가 보는지(역할/팀 게이트), ack API 권한(누가 누르면 무엇이 바뀌는지 — 도면팀 알림 해제 등), 실측 담당자가 누르면 도면팀 확인이 **대신 처리되어 버리는** 위험이 있는지. 메모리 참고: `project_drawing_alert_grades` (도면팀 알림 3등급).
- 결정 후보: (a) 도면팀(및 관리자)만 확인 버튼 노출, 실측 담당자에겐 읽기 전용 또는 숨김 (b) 그대로. 권한 서버 가드 변경은 코어(Auth/API) → Spec 승인 필요, 템플릿 노출 조건만이면 UI.

## T3. 도면 상세 모바일 하단 액션바에 가려진 정보
- 앵커: `templates/drawing/partials/workbench_detail_body.html:1551` `.dw-mobile-action-bar{% if erp_mobile_v2_enabled %} d-none{% endif %}` 와 CSS `:235-270`; v2 셸 쪽 하단 버튼(도면 전달·수정요청·수령 확정·전달 취소·긴급 호출)은 `workbench_mobile_handoff.html` / `static/css/components/foms-drawing-mobile.css`.
- 스크린샷: 하단 고정 버튼줄 바로 위에 파랑·노랑·초록 색 막대 조각(버튼 또는 칩 줄의 위쪽 가장자리)이 비쳐 보인다 → 콘텐츠 마지막 줄이 고정 바 뒤로 들어가 있다(스크롤 하단 여백 부족 추정). 날짜 `2026-09-28 07:49:33` 이 있는 카드 바로 아래.
- 할 일: 가려진 요소가 **무엇인지** 특정(템플릿 행 번호·클래스·문구), 원인(padding-bottom/safe-area/고정 바 높이) 특정, 수정안.

## 파일 소유권 (겹치지 않게)
| 워커 | 편집 허용 |
|---|---|
| W1 (T1) | `templates/measurement/partials/mobile_list.html`, `static/js/measurement/mobile-glance-tabs.js`, 그 JS `?v=` 핀을 가진 템플릿 한 줄, T1 관련 tests |
| W2 (T2) | `templates/drawing/partials/workbench_mobile_handoff.html`, `workbench_detail_body.html` 999-1010 구간만, `static/js/drawing/order-change-banner.js`, 도면 라우트 컨텍스트 python(노출 플래그 추가 시), T2 tests |
| W3 (T3) | `static/css/components/foms-drawing-mobile.css`, `workbench_detail_body.html` 의 `<style>` 230-275 구간·1551 액션바 구간, CSS 핀 한 줄, T3 tests |

## 공통 규칙
- `cd /c/tmp/foms-s-s0929-093058 && pwd` 로 시작. 메인 트리 `c:/DEV/FOMS` 편집 금지. git 명령(commit/stash/checkout) 금지. CRLF/LF 원래대로 보존.
- 인라인 스타일 금지(ratchet), jQuery 금지. 한글 출력 UTF-8.
- 정적 자산 편집 시 `?v=` 핀 올리고 `grep -rn "?v=<옛핀>" tests/ templates/` 로 복제 핀까지 갱신(@import 자식이면 부모 번들 핀도).
- JS 편집 시 `node --check <파일>`.
- 검증: `python -c "import app; print('APP_OK')"` + 관련 pytest.
