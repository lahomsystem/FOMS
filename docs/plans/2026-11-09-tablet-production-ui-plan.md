# 태블릿 생산 UI — 실행 플랜 (2026-11-09, 리뷰 반영판 · **사용자 승인 2026-11-09, 구현 진행 중**)

> 설계서 `docs/specs/2026-11-09-tablet-production-ui_SPEC.md`. 원장 `…-ledger.md`. 모든 task 는 origin/deploy 기준 세션 워크트리에서 "구현 → 검증 명령 → pathspec 커밋 → 원장 갱신". 한 task = 한 세션 안. 공통: `python -c "import app; print('APP_OK')"`, 바뀐 파일에 닿는 시험만(`grep -rl <파일> tests`), 전체는 push 직전 `scripts/ops/pre_push_smoke.ps1` 한 번. 인라인 스타일 0, `?v=` 핀은 자식·부모 함께, 실화면은 뷰포트 캡처(1280×800 생산팀 + 관리자·PC 대조군).

## P0 생산팀 첫 화면 (설계서 §12 — D10·D12·D13, P1 앞에)

| T | 할 일 | 대상 파일 | 완료 기준(검증) |
|---|---|---|---|
| T0-1 | 전체 주문 한 줄 + 착지(기기 무관) | `foms/services/production_home_read_model.py`(새), `production_dashboard_display.py`(공개 함수), `production_read_model.py`(`stage_codes` kwarg), `foms/web/production/dashboard.py`(`/production/home`), `templates/production/home.html`, `static/css/contexts/production/home.css`, `static/js/production/foms-production-home.js`, `post_auth_navigation.py`·`listing.py`·`auth/routes.py` | `tests/domains/test_production_home.py` 새 6 + `test_post_auth_navigation.py` 새 4 초록, 기존 생산 보드·착지 시험 초록, `APP_OK`. 스테이징 실화면 1280×800·800×1280 |
| T0-2 | 전체 화면 작업 시트(안 2) | `dashboard.py`(뷰 모델 함수 분리 + `/production/sheet/<id>`), `templates/production/sheet.html`(새), `home.css` 또는 `sheet.css`, 공정 JS(F2 ② 스코프 재작성) | 새 시험: 생산팀 200·전화·주소·도면 N·공정 5·불량 칩 4·인라인 style 0, 쿼리 수 단언. 카드 링크 교체 |
| T0-3 | 탭 "이번 주"(안 4) | `production_home_read_model.py`(출고·시공 요일 묶기), `home.html`(탭 2), 받은함 ACK 는 기존 API | 새 단언: 요일 6칸·오늘 굵게·바뀐 것 n·[확인했어요] POST 200 |
| T0-4 | 탭 "내 공정"(안 3) | `home.html`(탭 3), `foms-production-home.js`(탭 저장·[끝] POST) | 새 단언: 공정 5탭 숫자 = 첫 미완 공정 집계, POST 뒤 다음 탭으로 이동. 일의 양 칸 없음(D11) |

## P1 착지·권한 (F-01·F-02·F-07)

| T | 할 일 | 대상 파일 | 완료 기준(검증) |
|---|---|---|---|
| T1-1 | ~~생산팀 착지 = 생산 보드~~ → **T0-1 이 생산 홈 착지로 대신함(D12)**. 남은 것: 없음. (옛 글) 생산팀 착지 = 생산 보드(기기 무관). 세 곳을 한 함수로: `authenticated_home_url`, `post_auth_navigation.py:100-101`, `listing.py:158-159`; `auth/routes.py:585` switch_user 분기. 조건 `team==PRODUCTION and partner_org_id is None and not 프리랜서` | `foms/services/post_auth_navigation.py`, `foms/web/orders/listing.py`, `foms/web/auth/routes.py` | `tests/domains/test_post_auth_navigation.py` 에 사례 3(로그인·`/`·switch_user, PC UA 포함) 추가 → 초록. 협력사·프리랜서 홈 시험 그대로 초록 |
| T1-2 | 403 문구 + 상세 링크, 문서 진입 302 | `static/js/foms/fragment-loader.js:92-135`(status 전달·403 분기), `foms/web/orders/dashboard.py:641-642`(비편집자는 모바일 상세로 302) | `test_tablet_dashboard_sheet_contract.py` 초록 + 문구·링크 문자열 단언. 실화면: 생산팀 컨트롤타워 행 탭 → 문구 + [상세] 200 |
| T1-4 | **생산팀 금액 가리기(D7)** — 완료 보드 PC 표·태블릿 그리드·모바일 카드·CSV·KPI(미수 합계·정산 대기)와 모바일 상세 품목 금액을 팀 PRODUCTION 이면 서버에서 빼기(열·줄 제거, 값 미전송). 술어 1개(`foms/services/erp_permissions.py` 또는 settlement_channel_access 재사용) | `foms/web/cs/completion_dashboard.py`, `templates/cs/partials/completion_dashboard_body.html`·`tablet_completion_grid_body.html`·완료 모바일 카드, `foms/web/orders/dashboard.py:828`(모바일 상세 DTO), `templates/orders/partials/order_detail_mobile_v2.html`·`order_detail_mobile_products.html` | 새 시험: 생산팀 200 응답에 금액 숫자·열 머리글 0, CS 는 그대로. `test_p1_mockup_structure.py:194`(상세 셀렉터) 초록 |
| T1-3 | 세로 하단 탭 생산팀 분기 | `templates/partials/shared/erp_mobile_shell.html:48-56` | 기존 시험 없음 → 새 시험(렌더 후 PRODUCTION 첫 탭 production, 시공팀·기본 분기 불변). 800×1280 실화면 |

## P2 작업 시트 (F-03 일부·F-04·F-06·D5)

| T | 할 일 | 대상 파일 | 완료 기준 |
|---|---|---|---|
| T2-1 | 시트에 전화·주소 줄 + "상세 · 인쇄" 링크(인쇄는 T4-1 라우트, 그 전엔 숨김) + "생산 완료"→"제작 완료" | `foms/web/production/dashboard.py:408-468`(뷰 모델 2키), `templates/production/partials/tablet_sheet.html` | 새 시험 `tests/domains/test_production_tablet_sheet_fragment.py`: 생산팀 200, 전화·주소 문자열·`tel:`·`/erp/orders/<id>/mobile` 링크, **쿼리 수 단언**(시트 라우트 전용). `test_tablet_domain_sheets_contract.py` 초록 |
| T2-2 | 브리핑 목록 60vh 보정 + 핀 | `static/css/foundation/foms-tablet-production-kanban.css:926`, `foms-tablet-bundle.css`, `templates/partials/shared/layout_head.html` | `test_tablet_t2_contract.py` 보정 줄 단언 추가·초록, CSS 핀 시험(`test_tablet_rail_contract.py`·`test_tablet_as_compare_contract.py`·`test_shipment_change_alert_render.py`) 초록. 130% 실화면 닫기 밑 안 깔림 |
| T2-3 | 레일 화면 크기 단추(변형 rail, 브랜드 아래) | `templates/partials/shared/foms_ui_zoom_control.html`(변형 1), `templates/partials/shared/foms_tablet_rail.html`, `static/css/foundation/foms-tablet-rail.css` + 핀 | `test_tablet_rail_contract.py` 초록(72px·`__item`), 실화면 가로 80%→130%→100% 전환, 세로 손잡이와 같은 값, 130% 에서 단추 보임 |
| T2-4 | 실패 문구 통일(D5) | `static/js/foms/tablet-domain-sheets.js:110-134, 257-262`(핀 올림 — `tests/performance/test_entry_chain_parallel_contract.py:243-262` 가 출고 CHAIN 핀과 같아야 함), `static/js/production/foms-production-steps.js:263,296` | `test_tablet_domain_sheets_contract.py` confirm 문구 불변·핀 단언 초록. 네트워크 끊고 단추 → 새 문구 |

## P3 도면·공정·알림 (F-03·F-05·F-13)

| T | 할 일 | 대상 파일 | 완료 기준 |
|---|---|---|---|
| T3-1 | 공정 5체크 + 불량 블록을 시트 안에(스코프 JS 재작성) | `static/js/production/foms-production-steps.js`(루트 기준 스코프 객체, id 의존 제거, `loadSteps(id, root)` 를 시트 삽입 이벤트에서), `templates/production/partials/production_steps_sheet.html:15-35`(id → data-속성), `tablet_sheet.html`(블록) | `test_production_steps_api.py` 초록. 새 단언: 시트 fragment 에 `data-foms-prod-steps-sheet` 1·칩 4·id 중복 0, 가로 DOM 에 세로 오프캔버스와 공존해도 시트 목록이 채워짐(Playwright 1회). 실화면: 체크 → POST 200, 세로 바텀시트도 그대로 동작 |
| T3-2 | 도면 스트립 N장 + 기존 마운터로 뷰어 | `foms/web/production/dashboard.py:383-405`(이미지 전체 목록, `_PROD_SHEET_IMG_EXT` `:328`), `tablet_sheet.html`(갤러리 마크업), 마운터 로드 여부(`foms_mobile_queue_attachment_preview_bundle.html` 포함 확인, 아니면 로드 1줄) | 새 단언: 전달본 3장 → 썸네일 3, PDF 는 "파일 열기" 링크. 실화면(운영 또는 로컬 시드 — 스테이징 파일 깨짐): 탭 → 뷰어 "2 / 3"·넘기기 |
| T3-3 | 품목 취소 → 생산 변경 알림 | `foms/api/drawing/erp_orders_item_cancel.py`(`_mutate` 안 취소 적용 `:75-76` 뒤·커밋 `:91` 전 호출, 커밋 뒤 finalize), `foms/services/notifications/production_change.py`(`_KIND_LABEL` "품목 취소") | `test_production_change_notification.py` 새 사례(팀 3 row, `merge=False` 로 2건 → 2 row). `python tools/harness/refresh_inventories.py` 후 커밋(REV-99 lineno 핀) |

## P4 인쇄 (D8 — 포함)

| T | 할 일 | 대상 파일 | 완료 기준 |
|---|---|---|---|
| T4-1 | 작업지시서 인쇄 페이지 | 새 라우트(`foms/web/production/dashboard.py`, 권한 `_can_edit_production_steps` 재사용), 새 템플릿 `templates/production/print_sheet.html`, 새 CSS `static/css/contexts/production/print.css`(폴더도 새로), 인쇄 단추 JS 외부 파일(≤60줄), 시트 "인쇄" 링크 | 새 시험: 생산팀 200·도면팀 403·취소 품목 제외·도면 장수 = 쪽수·인라인 style/script 0. 갤럭시 탭 인쇄 미리보기 1회(사용자 기기) |

## P5 생산 첫 화면 다시 그리기 (설계서 §12.3 — D17·D18, 2026-11-10)
| # | 일 | 파일 | 시험 |
|---|---|---|---|
| T6-1 | 글자 크기 손잡이 + px 글자 배율 | `home.html`(조각 include), `home.css`·`sheet.css`(calc) | CSS 에 맨 px 글자 0 · 손잡이 표식 |
| T6-2 | 날짜 탭(안 3: 2주 띠 + 그날) | `production_home_read_model.py`(`production_home_days`), `home.py`(tab·day), `home_date.html`, `foms-production-home.js`(날 고르기) | 띠 13줄+2 · 막대 좌표 · 만들 것 순서 · 미리 보기 · `?day=` |
| T6-3 | 바뀐 것 탭 · 내 공정 "곧 올 것" · 머리 총계 | `home_changes.html`, `home_steps.html`, 읽기 모델(`incoming`·`total`) | 받은함·곧 올 것(보류 제외)·총계 |

## P6 리뷰·실화면 고침 (원장 §16 — 워커 리뷰 R1~R11 · 실화면 S1~S5, 2026-11-10) — DONE
| # | 일 | 파일 | 시험 |
|---|---|---|---|
| T7-1 | 탭 숫자 = 줄 수 · 보류는 생산 단계만 · 바뀐 것에 취소 주문 · 다시 받기는 직접 고른 날만 | `production_home_read_model.py`(`production_home_queue_key`·`auto`·`hidden`), `home.py`, `home.html`, `home_date.html` | 새 시험 6(코드만 되돌리면 실패) |
| T7-2 | 글자 키울 때 옆 시트 단추·주소 · 칸 폭 배율 · 바뀐 줄 두 줄 | `sheet.css`, `home.css` | CSS 규칙 단언 + 스테이징 실화면 100~150% |
| T7-3 | 작업 시트 뒤로 단추 "생산" + 온 곳으로 | `sheet.html`, `foms-production-sheet-page.js` | 파일 단언 |

## P7 태블릿 레일 "생산" = 첫 화면 (설계서 §12.4 — D19, 2026-11-10) — DONE
| # | 일 | 파일 | 시험 |
|---|---|---|---|
| T8-1 | 레일 생산 주소 = 첫 화면(볼 수 있는 사람) · 한 규칙 | `production/home_access.py`(신규), `foms_split_view.py`, `home.py` | 팀별 주소 · 문지기와 한 곳 · 시공팀 레일 · split 레일 그대로 |
| T8-2 | 강조 · 조각 이동 뒤 강조 | `foms_split_view.py`, `foms_tablet_rail.html`, `tablet-rail-nav.js` | 강조 id · JS 접두어 |
| T8-3 | 첫 화면 [보드] · 제목 줄 오른쪽 묶음 | `home.html`, `home.css` | 보드 링크 · 묶음 · 띠 글 |

## P8 운영 실측 고침 (원장 §17 M1~M4 — D20, 2026-11-11) — DONE(스테이징), 운영은 지시 때
| # | 일 | 파일 | 시험 |
|---|---|---|---|
| T9-1 | 바뀐 것은 생산 단계 주문만 | `production_home_read_model.py`(행 만들 때 alerts) | 도면 · 생산 · 완료 주문에 변경 하나씩 → 숫자 1 · 받은함 1 · 테두리 |
| T9-2 | 내 공정 · 곧 올 것 시공일 순 | 같은 파일(`_due_sort_key`) | 지난 날 → 앞날 → 없음 |
| T9-3 | 품목 글 두 줄 · 미리 보기 넓히기 · 단추 글 | `home.css`, 읽기 모델(`preview`), `home_date.html` | CSS 규칙 · 그 뒤 · 밀린 것 · 자기 자신 금지 |

## P9 운영 실측 2차 고침 (원장 §18 M4 나머지 · M5, 2026-11-11) — DONE(스테이징), 운영은 지시 때
| # | 일 | 파일 | 시험 |
|---|---|---|---|
| T10-1 | 미리 보기 6줄 채우기(뒤 장들 잇기 + 밀린 것) | `production_home_read_model.py`(`previews`), `home_date.html` | 다섯 경우 |
| T10-2 | 아래 단추 두 줄 | `home_date.html`, `home.css` | 단추 글 |

## P10 자잘한 정리 (원장 §19 M6 · 래칫 여유, 2026-11-11) — DONE(스테이징), 운영은 지시 때
| # | 일 | 파일 | 시험 |
|---|---|---|---|
| T11-1 | 긴 이름 말줄임 + 번호는 늘 보임 | `home_date.html`, `home.css` | 렌더 모양 · CSS 규칙 |
| T11-2 | 날짜 탭 읽기 모델 나누기 | `production_home_days.py`(신규), `production_home_read_model.py`, `home.py` | 글자까지 같은 옮기기 · 기존 시험 그대로 |
| T11-3 | 시험 파일 나누기 | `test_production_home_fixes.py`(신규), `test_production_home_tabs.py` | 시험 수 18 → 9 + 10 |

## P11 발주사 · 영업 담당 표기 (원장 §21 — D21, 2026-11-11) — DONE(스테이징), 운영은 지시 때
| # | 일 | 파일 | 시험 |
|---|---|---|---|
| T12-1 | 만들 것 줄에 발주사·담당 | `production_home_read_model.py`(`_by_line` → 11-11 `_by_parts`), `home_date.html`, `home_steps.html`, `home.css` | 네 경우 × 두 줄 · 작은 칸에 없음 · CSS 규칙 |

## P12 발주사 · 담당 글 시인성 (원장 §23, 2026-11-11 사용자 "전부 회색이라 구분이 안 돼") — DONE · 운영 PR #806(원장 §24)
| # | 일 | 파일 | 시험 |
|---|---|---|---|
| T13-1 | 글 한 덩이 → 조각(머리말 회색 작게 · 이름 굵게 · 발주사 진한 글자 · 담당 남색) | `production_home_read_model.py`(`_by_parts`), `home_date.html`, `home_steps.html`, `home.css`(핀 `20261111g`) | 조각 마크업 네 경우 × 두 줄 · CSS 색·굵기·줄바꿈 규칙 |

## P13 남은 자잘한 것 정리 (원장 §25, 2026-11-11 사용자 "남은 자잘한 것 정리" · D22) — DONE · 운영 PR #808(원장 §26)
| # | 일 | 파일 | 시험 |
|---|---|---|---|
| T14-1 | 곧 올 것 긴 이름 번호 · S3 작업 시트 머리 줄 · S4 옆 시트 닫기 단추 | `home_steps.html`, `home.css`(핀 `20261111h`), `sheet.css`(핀 `20261111a`) | `test_production_home_fixes.py` 3개 |
| T14-2 | R6 날짜 출처 한 곳 | `production_home_read_model.py` | `test_production_home_date_source.py` 2개 |
| T14-3 | D22 변경 알림 = 생산 진입 뒤 바뀐 것만 | `production_change_alerts.py` | `test_production_change_window_d22.py` 10개(정본 엔진 전이 포함) |

## 뒤로 미룸(기록)
- (11-11 P13 으로 닫음: R12 · R6 · S3 · S4 · 곧 올 것 긴 이름 번호.)
- 원장 §25 남은 구멍: 진입 이벤트 없이 단계가 바뀐 옛 주문(`field_update.py` 덮개 섞인 옛 길 · 직접 SQL)은 D22 바닥이 없어 옛 동작 · 전체 화면 시트 제목은 이름이 아주 길면 번호도 같이 줄 수 있음 · 날짜가 어긋난 옛 주문은 화면이 납작 열을 따름(정본 JSONB 와 다를 수 있음).
- 오프라인 저장, 출고 배정 쓰기(출고팀 STAFF 403 별건), AS→재제작, 생산 할 일 보드, 회사 지식 404, 공지·프로필 레일, QR 막대 위치, AS 행 시트 URL(별건 1줄), 다른 팀 태블릿 2차, 장별 "바뀐 도면".

## 원장 규율
- task 끝나면 그 자리에서 DONE/BLOCKED, 막히면 사유 적고 다음 task.
- 운영 반영은 스테이징 실화면 통과 뒤 사용자 명시 요청으로 cherry-pick 승격.

## P14 출고 탭 — 하루치 출고표 · 시공자 배정 (설계서 §14 — D23~D31, 승인 11-11)
| # | 일 | 파일 | 시험 |
|---|---|---|---|
| T14-1 | 출고팀 쓰기 열기 · 영업팀 막기(D31) | `erp_permissions.py`(`can_edit_shipment` + 데코레이터), `foms/api/shipment/settings.py`, `foms/api/shipment/recommendations.py`, `foms/web/shipment/dashboard.py`(화면 값) | 팀별 통과/403 |
| T14-2 | 묶음 · 사람별 집계 · 자수 나누기 | `foms/services/shipment/tablet_day_sheet.py`(신규), `dashboard.py`(`compute_team_remaining_units_for_date`) | 순서 · 번호 · 반씩 · AS 건수만 |
| T14-3 | 표(안 17) + 이름판 | `tablet_ship_grid.html`, `shipment-dashboard-columns.css`(또는 새 CSS), `static/js/shipment/tablet-ship-assign.js`(신규) | 템플릿 단언 + 스테이징 실화면 |
| T14-4 | 서랍 넓히기 + AS 정보 | `tablet_sheet.html`, `dashboard.py`(시트 값) | 조각 단언 |
| T14-5 | AS 넣기 목록 · 이미지 저장 | `tablet-ship-assign.js` 또는 새 JS, `dashboard_main.html`(위 줄) | 스테이징 실화면(읽기) |
| T14-6 | 협력사 희망 판 = 위 줄 단추로 내려오는 서랍(설계서 §14.8, D34) | `dashboard_main.html`(위 줄 단추 · 막), `partner_request_board.html` · `partner_request_chip.html`(회사 이름 칸), `static/js/shipment/partner-request-board.js`(칸 눌러 날짜), 새 작은 JS(여닫기), 태블릿 CSS | 템플릿 단언 + 로컬 준비물 서버 실화면 + 스테이징 오류 0 |
| T14-7 | AS 넣기 때 시공자 이름도 같이 · 취소 때 되돌림(설계서 §14.9, D35) | `foms/services/shipment/as_recommendation.py`(넣기 · 취소 · snapshot), 인벤토리 | 도메인 시험 + PG 레인 + 로컬 준비물 서버 |
| T14-8 | 출고표 날짜 = 위 줄 안 날짜 버튼 · 돋보기 · [더보기](설계서 §14.10, D38 안 28) | `dashboard_main.html`(위 줄), 태블릿 CSS, 새 작은 JS(띠 넘기기 · 더보기 · 돋보기) | 템플릿 단언 + 스테이징 실화면 |

## C13 시공 탭 첫 화면 + 상세 (설계서 §13.7 P13-1~5, D39~D42 — 이름 P13-n 은 설계서 단계 번호, 위 "P13 남은 자잘한 것" 과 다름) — 스테이징 완료 11-12

| 작업 | 할 일 | 파일 | 확인 |
|---|---|---|---|
| P13-1 | 날짜 띠 · 사람 색 공용 CSS + 날짜 JS 시공에서도 싣기 | `foms-tablet-day-strip.css`, 시공 `styles.html` · `dashboard_body.html` | 출고 화면 그대로 · 공용 시험 |
| P13-2 | 읽기 서비스(쿼리 A 날짜별 집 수 · B 그날 줄) | `foms/services/construction/tablet_first.py` | 대조군 3종 |
| P13-3 | 첫 화면 조각 + 위 줄 | `tablet_first_body.html`, `tablet-first.css`, `tablet_view.py`, 라우트 | 템플릿 · 모드 · 쿼리 수(10) |
| P13-4 | 상세 왼쪽 = 그날 집 · 돌아가기 · 옛 딥링크 · 찾기 · 단추 권한 | `tablet_workmode_body.html`, `tablet_view.py` | 권한 시험(되돌리면 실패) |
| P13-5 | 스테이징 실화면 · 성능 · 셸 교체 재실행 고침 | `construction/dashboard.js`(const → var) | 실화면 · 조각 −20% |
