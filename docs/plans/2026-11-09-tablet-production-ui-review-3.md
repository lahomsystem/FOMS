# 리뷰어 ③ 사실 검증 — 보고 원문 (2026-11-09)

> 원장 §5 의 본문. 리뷰어(Fable 5.1 high, 읽기 전용, HEAD `ea4376ea1`) 보고를 그대로 붙였다. 대상은 **리뷰 반영 전 설계서·플랜**이라 일부 항목(착지 3곳·JS 경로·F-13 호출 지점·읽기 전용 시트)은 반영판에서 이미 고쳐졌다. 총괄 반영은 원장 §6.3.

## 틀림 14건 — 한 줄 요약
착지 흐름(F7 ①)·공정 시트 줄 번호(38-68 → 파일이 37줄)·JS 경로(`static/js/production/`)·품목 취소 호출 지점(:46 은 해시 함수)·시험 3개의 역할(하단 탭·쿼리 수·핀 동기 모두 그 시험이 안 봄)·카드 스트립 위치·시트 단추 목록이 실제 코드와 다르다.

| 문서 | 위치 | 적힌 것 | 실제 | 판정 | 고칠 글 |
|---|---|---|---|---|---|
| SPEC | §5 F7 ① | `authenticated_home_url` 팀 분기로 `/` 재리다이렉트도 함께 | `listing.py:159-160` 하드코딩, `resolve_post_login_redirect`(`post_auth_navigation.py:82-102`) `:100-101` 하드코딩 | 틀림 | 바꿀 곳 3곳을 한 판정 함수로 |
| SPEC·플랜 | §5 F2 ③ / T2-3 | `production_steps_sheet.html:38-68` | 파일 37줄. 목록 `:15-17`, 불량 블록·칩 `:19-35` | 틀림 | `:15-35` |
| 플랜 | T2-3 | `static/js/foms/foms-production-steps.js` | `static/js/production/foms-production-steps.js`(345줄, 래칫 기준선 등재) | 틀림 | 경로 수정 |
| SPEC | §5 F2 ③ | `closest(...)` 1곳 일반화 | 전역 조회 7곳: `getElementById(SHEET_ID)` :52, 목록 :56, 머리글 :159, 불량 4개 :191-194 | 틀림 | 루트 1개 잡고 하위 7개 조회를 루트 기준으로 |
| SPEC·플랜 | §7 / T4-4 | 호출 `erp_orders_item_cancel.py:46` 뒤 | :46 은 `_hashes()`. 취소 적용 `_mutate` 안 `:75-76`, 커밋 `:91`. 알림은 커밋 전 호출 계약 | 틀림 | `_mutate` 안 `:76` 뒤(커밋 전) |
| SPEC | §7 | 카드 스트립 `tablet_kanban_body.html:220-236` 꼴 | 종류별 행 `:184-197`(아이콘 분기 :185), 모달 `:376-378` | 틀림 | `:184-197` · `:376-378` |
| SPEC | §9 | `test_admin_override_ui.py`·`test_entry_chain_parallel_contract.py`(핀 동기) | 태블릿 번들·CSS 핀 단언 없음. 번들 핀 보는 시험 = `test_tablet_t2_contract.py`·`test_tablet_rail_contract.py`·`test_tablet_as_compare_contract.py`·`test_shipment_change_alert_render.py` | 틀림 | 시험 이름 교체 |
| SPEC·플랜 | §9 / T1-4 | `test_production_dashboard_mobile.py`(하단 탭) | 그 파일은 큐·그리드·스크립트 배선만. `_primary_ids` 단언 시험 0개 | 틀림 | 새 시험 |
| SPEC·플랜 | §9 / T2-1·T2-4 | `test_production_dashboard_query_count.py` 로 카드·시트 쿼리 | ADMIN+fragment, v2 env 미설정 → 칸반 미렌더. SQL 문 수 delta ≤2. 칸반 env 켜는 시험 = `test_production_kanban_full_window.py:42-43`. 시트는 어느 시험도 안 봄 | 틀림 | 칸반 = full_window 에 단언, 시트 = 새 시험 |
| SPEC·전수표 | §5 F2 / #7 | 단추 [보류]/[제작 시작]/[제작 완료]/[완료 취소]/[수정 제작] | `tablet_sheet.html:176-203`: 보류·보류 해제 / 제작대기: 제작 시작 / 제작중: **제작 취소**+**생산 완료** / 제작완료: 완료 취소+수정 제작 | 틀림 | [제작 취소] 추가, '생산 완료' |
| SPEC | §5 F7 ② | `can_edit=False` 렌더 | 컨텍스트 이름 `can_edit_erp`(`dashboard.py:672`), 템플릿은 분기 없이 무조건 렌더 | 틀림 | (반영판에서 문구만으로 바꿈) |
| 전수표·지시서 | F-18 / §2.3 | `foms_split_view.py:137 build_split_side_items` | def 는 `:129` | 틀림 | `:129` |
| 지시서 | §2.2 | "생산팀" `auth/routes.py:80` | `:85`(TEAMS :81-91) | 틀림 | `:85` |
| 지시서 | §2.3 | `foms_scr` `:175`, `foms_vw` `:210` | `WIDE_SURFACE_MIN_PX` `:177`; `wants_mobile_width_surfaces` `:229-271` | 틀림 | `:177` · `:229-271` |

## 모호(줄 번호 어긋남·표현)

| 문서 | 위치 | 적힌 것 | 실제 | 고칠 글 |
|---|---|---|---|---|
| SPEC·플랜 | F2 / T2-1 | `dashboard.py:408-467` | 408-468 | `:408-468` |
| SPEC·플랜·전수표 | F2 ④ / T3-1 / F-05 | `_prod_sheet_drawing_thumb` 383-407 | 383-405 | `:383-405` |
| SPEC | F6 ① | 시공팀 분기 `:50` | `:48-50`, 기본 else `:54-56` | `:48-50` |
| 플랜 | T5-3 | `layout_nav.html:235-237` | 조건 `:236`, include `:237-238` | `:236-239` |
| SPEC | F1 ③·§9 | `test_tablet_t2_contract.py:416-426` 에 60vh 줄 | 416-423 은 265px 캡 시험. pcbar 인쇄 금지 426-438 | 새 test 함수 · `:426-438` |
| SPEC | §3 | `orders.py:826-842` | 고객컨펌 분기 `:813-828`, 409 `:829-831` | `:813-831` |
| 지시서 | §2.1 | TRANSFERRED 막힘 `:805`, `:1053` | `:807-812`·`:823-828`, 수정 제작 `:1055-` | `:807-828` · `:1055-1060` |
| SPEC | §8 | confirm 5회 | window.confirm 4 + 사유 시트 1(제작 취소) + 보류 재시도 1 | 표현 고침 |
| SPEC | §8 | 터치 48px·입력 16px 계약 | 계약은 행 48 / 타깃 44 / 입력 16(:23-55). 48 은 실측 | 행 48 / 타깃 44 위에서 새 단추 48 |
| SPEC | §9 자산 핀 | 자식 CSS 3개 | `foms-tablet-side-sheet.css` 만 `components/` | 경로 병기 |
| 플랜 | T5-1 | `static/css/contexts/production/print.css` | 폴더 없음 | 새 폴더 명시 |
| 플랜 | T1-1 | `test_post_auth_navigation*.py` | 단일 파일 | 파일명 고정 |
| SPEC·플랜·전수표 | F2 ② / T2-1 / #10 | 시공팀 데이터원 미정 | `sd['shipment']['construction_workers']`(`foms/web/shipment/dashboard.py:241,279,352`), 쿼리 0 | 키 확정 |

## 맞음(요약)
SPEC §3·§5~§9 의 나머지 경로:행(`post_auth_navigation.py:31-44`, `dashboard.py:627-660`·`:653-654`, `fragment.py:72`, kanban css :926, domain-sheets :110-134·:257-262·:296-350·:204-245, `erp_mobile_shell.html:50-57`, `mobile_queue.html:96·100·113`, `erp_order_label` :878-880, t2 :109-110, rail :110-123·:60-64, t0 :207-213, `layout_nav.html:68`, ui-zoom 키, `auth/routes.py:585-586`, as_dashboard_body :297, card-detail :153, mobile 상세 :828, tel·지도 :139·:150, fragment-loader 403 문구 :96-97, 마커 :22, PROD_STAGES·ACK·apply·TARGET_TEAMS·kinds·60초, active_items 4곳, tablet_sheet :176-182·:6, dashboard_body :161, viewer open :110, drawing-review 패턴, TRANSFER hotfix :414·585, 번들 import, 계약 문자열), 플랜의 신규 3파일·실존 파일·시험 파일 전부 맞음, 지시서 §2 의 주요 줄 번호·JS 줄 수 맞음.

## 숫자 재확인
JS 줄 수(kanban 191 · steps 345 · side-sheet 479 · domain-sheets 820 …) 맞음. 래칫 기준선에 `tablet-production-kanban.js` 없음(여유 109), `foms-production-steps.js` 등재. `PRODUCTION_KANBAN_MAX_ROWS = 300`. 공정 5·불량 4 글자 맞음.

## 확인 못 한 것
실화면 판정·실제 착지 경로(런타임)·새 JS 의 게이트(대상 없음).
