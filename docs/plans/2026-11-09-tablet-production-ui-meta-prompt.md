# FOMS 태블릿 UI 최종 구현 — 생산 페르소나 설계·목업 세션 지시서 (2026-11-09)

> FOMS 총괄 개발자가 설계 세션 에이전트에게 건네는 지시서다. 이 파일만 읽고 시작한다. 필요한 메모리 내용은 §2·§6 에 옮겨 두었다. 경로는 저장소 루트 기준 상대 경로이고, 줄 번호는 `origin/deploy` `ea4376ea1`(2026-11-09 측정, 메인 체크아웃과 같음) 기준이다.
> 저장소는 공개(PUBLIC)다. 목업·문서에 실제 고객 이름·전화·주소를 넣지 않는다. 이 파일은 커밋하지 않는다(사용자가 시키면 그때).

## 0. 이 문서를 받는 에이전트에게

사용자 요청(2026-11-09, 원문):

> "테블릿 버전 UI 최종 구현
> 1. 이제 일부 인원이 테블릿으로 작업 예정이다.
> 2. 생산 인원이 주로 테블릿을 사용할 것으로 니가 생산 persona로 업무에 필요한 모든 UI를 생각 해 봐
> 3. 일단 생산 입장에서 현재 UI 모두 체크 해서 완성 ui 목업 만들어 띄워
> 4. 회사 전체 workflow 단계 고려 해야 돼
> 5. fable 5.1 xhigh를 기본으로 니가 병렬 에이전트 및 main effort/model 알아서 설정 해 테스크에 맞게"

- 이번 세션의 결과물(§7): **생산 페르소나 기준 현재 UI 전수표 + 결함 목록 + 완성 목업(태블릿 가로 프레임 묶음, 사용자가 바로 볼 수 있게 띄움) + 설계서 + 실행 플랜·원장**. 저장소 앱 코드는 고치지 않는다. 구현은 승인 뒤 플랜의 task 로 다음 세션들이 한다.
- 등급 `**C`(며칠). 태블릿 표면은 이미 2026-07 에 한 번 지어졌다(§2.3) — 이번 일은 "없는 것을 새로 짓기"가 아니라 **생산 사람이 하루 일을 태블릿 하나로 끝낼 수 있는지 전수로 재고, 빈 곳만 채우는 목업**이다. 기존 화면을 그대로 두고 바꿀 칸만 바꾼다(§6 규칙 1).
- 모델·병렬: 총괄 Fable 5.1 effort xhigh. 워커·리뷰어 구성은 §5 표대로 Agent 도구로 띄운다(Workflow 도구는 사용자가 "워크플로"라고 말할 때만).
- 기준 커밋: 메인 체크아웃 `C:/DEV/FOMS` 는 여러 창이 같이 쓴다. 미커밋 파일(목업·perf 증적·시각 시험 산출물)이 많으니 건드리지 않는다. `git fetch` 뒤 `python tools/harness/session_worktree.py create` 로 origin/deploy 기준 워크트리를 만들어 그 안에서 읽고 쓴다. 이 지시서는 워크트리의 같은 경로로 복사한다. 원장 §0 에 시작 HEAD 를 적고, 다시 잰 값이 다르면 "재측정: 값 — 명령"으로 병기한다.
- `docs/AI_STATUS.md` 상단 40줄은 읽는다. 설계서가 승인되면 '진행 중'에 한 줄 넣는다(상단 4,000자 예산은 시험이 강제).

### 0.1 새 세션 시작 프롬프트(복붙용)

새 세션(저장소 `C:/DEV/FOMS`)의 첫 메시지로 아래를 그대로 붙인다.

```text
**C FOMS 태블릿 UI 최종 구현 — 생산 페르소나 설계·목업 세션을 시작해.
유일한 컨텍스트 = C:/DEV/FOMS/docs/plans/2026-11-09-tablet-production-ui-meta-prompt.md — 먼저 전부 읽어(필요한 메모리는 §2·§6 에 옮겨 뒀다).
먼저 git fetch 뒤 session_worktree.py create 로 origin/deploy 기준 워크트리를 만들고 그 안에서 일해. 메인 체크아웃은 다른 창 것이니 건드리지 마.
결과물 = 전수표 + 결함 목록 + 태블릿 목업 묶음(Artifact 로 띄워) + 설계서 + 플랜·원장(§7). 앱 코드 수정·패키지 설치·push 는 하지 마(목업은 docs/design/mockups 만).
순서 = §4. 병렬 에이전트는 §5 표대로(총괄 Fable 5.1 xhigh — 시작 전에 /effort status 로 확인, 워커·리뷰어는 Agent 호출에 model·effort 를 넣어).
운영 DB 읽기는 나에게 한 번씩 허락받아(스테이징은 자유). 고객 개인정보 원문·비밀값은 출력·저장 금지.
완료 기준 = §8 전부. 시작하자마자 §9 의 남은 질문을 쉬운 한글로 질문 창에 물어(설명은 창 안에).
```

## 1. 페르소나·임무

너는 **FOMS 태블릿 UI 설계 책임자**다. 가구 주문 ERP(FOMS)의 단계 흐름(접수 → 실측 → 도면 → 고객컨펌 → 생산 → 시공 → CS/완료 → AS)과 그 안에서 생산팀이 맡는 자리를 안다.

### 1.1 주 페르소나 — 생산팀 직원(공장, 태블릿)

- 누구·어디서: 공장 작업대 옆. 손에 먼지·장갑. 태블릿은 거치대 또는 들고 봄. 마우스 없음(`pointer: coarse`). 대부분 가로로 들고 쓴다고 가정하되 세로로 돌리는 순간도 있다(§2.3 — 세로는 폰 화면으로 떨어진다).
- 지금(2026-10-27 운영 실측): **생산팀 계정 0명**. 생산 단계 주문 56건. 최근 180일 생산 동작은 영업 관리자 한 사람이 [제작 시작]을 4번 누른 것이 전부(생산 보드 [확인] 0번). 즉 생산팀은 지금 ERP 를 안 쓰고 종이·카톡(발주방 PUSH 글)으로 일할 가능성이 크다 — 사용자에게 확인(§9 Q4).
- 하루에 해야 할 일(가설 — 실측·사용자 답으로 확정):
  1. 오늘 만들 것 보기: 제작대기·제작중 주문, 상차일·시공일 순, 급한 것(D-2 이내·지연) 먼저.
  2. 주문 하나를 열어 **최종 도면**을 크게 보기(핀치 줌, 치수 읽기, 시트 여러 장 넘기기), 품목·규격·자수·특이사항 읽기, 취소된 품목은 빼기.
  3. [제작 시작] → 공정 5단계 체크(재단·엣지·도장·조립·검수) → [제작 완료]. 불량이 나면 사유 4종(자재 불량·가공 오류·파손·기타)으로 보고. 못 만들 사정이면 [보류]+사유. 다시 만들어야 하면 [수정 제작].
  4. 바뀐 것 알아채기: **도면 바뀜(바로 반영)**·시공일 변경·주문 취소·품목 일부 취소 → 카드의 빨간 표시를 보고 [확인].
  5. 다음 단계에 넘기기: 제작 완료 = 출고팀·시공팀이 가져갈 수 있는 상태. 상차일(`load_md`)이 언제인지, 출고 배정이 됐는지 읽기.
  6. 그 밖: 알림 벨·공지 보기, 회사 지식 물어보기(있다면), 화면 크기(70~130%) 맞추기.
- 보면 안 되거나 필요 없는 것(가설): 금액(출고가·잔금·정산), 고객 전화번호(연락은 CS·영업 몫), 실측·AS·완료·이력 탭, 견적 계산기. 레일에 9탭이 다 나오는 지금(§2.3)이 맞는지 사용자 결정(§9 Q3).

### 1.2 부 페르소나 — 같은 태블릿을 들 수 있는 사람

- 사용자 원문 "일부 인원"이 생산만인지는 미정(§9 Q6). 도면팀(태블릿 갤러리·시트, 2026-07-27 설계), 출고팀(태블릿 컬럼), 시공팀(작업 모드), CS(완료 그리드·AS 대조)는 이미 전용 표면이 있다. 이번 전수 점검의 **대조군**으로 각 1화면씩만 같은 잣대로 찍어 "생산만 빠진 것"과 "태블릿 전체가 빠진 것"을 가른다.

### 1.3 판단 기준

"화면이 몇 장 늘었나"가 아니다. **생산 사람이 PC·종이·카톡 없이 태블릿 하나로 1.1 의 1~6 을 끝낼 수 있는가, 그리고 회사 단계 흐름(상류 고객컨펌·도면, 하류 출고·시공)과 어긋나는 곳이 0인가**다.

## 2. 사실 카드 (origin/deploy `ea4376ea1`, 2026-11-09 총괄 측정 — 설계 때 다시 확인)

### 2.1 회사 전체 단계 흐름

- 단계 11종·한글 이름·기본 담당 팀: `foms/services/orders/erp_policy_constants.py:14-41`. 생산(`PRODUCTION`)의 앞은 고객컨펌(`CONFIRM`, 영업), 뒤는 시공(`CONSTRUCTION`, 시공팀). 출고는 단계가 아니라 **겹축**(`shipment.logistics_status`: NONE·MEASURED·REGIONAL_MEASURED·SCHEDULED·SHIPPED_PENDING, `foms/api/production/orders.py:1729`, 쓰기 권한은 출고 쪽 `SHIPMENT_EDIT`).
- 단계마다 퀘스트(승인 팀)·설명: `data/erp_quest_templates.json` — 생산 퀘스트 "생산 확인", 승인 팀 PRODUCTION, 다음 단계 CONSTRUCTION. 생산 할 일 템플릿 "생산 착수/일정 확정" 기한 = 시공일 −2 영업일(`data/erp_task_templates.json:41-47`).
- 생산 보드 버킷 3종 = 제작대기·제작중·제작완료(read model, `foms/services/production_dashboard_display.py`). 출고 대기는 버킷이 아니라 카드의 시공 D-day 칩.
- 생산 시작 조건: 고객컨펌 퀘스트 승인(`tests/domains/test_production_start_requires_confirm_quest.py`) + 도면이 `TRANSFERRED`(영업 수령 확정 전)면 [제작 시작]·[수정 제작] 막힘(`foms/api/production/orders.py:805`, `:1053`; 보드 배지 '도면 수정 중' 2026-09-29).
- 생산 단계에서 도면팀이 고치면 **영업 확인 없이 바로 최종**(2026-10-27 결정, `docs/specs/2026-10-27-drawing-team-production-fix_SPEC.md`). 생산 변경 알림 종류 4: `construction_date`·`drawing`·`drawing_hotfix`·`cancelled`(`foms/services/notifications/production_change.py:118`), 받는 팀 `("CS","SALES","PRODUCTION")`(`:44`), 대상 단계 고객컨펌·생산·시공(`production_change_alerts.PROD_STAGES`). 카드 빨간 표시는 **사람마다** [확인](`/production/change-ack`).
- 도면 확정 때 품목 일부 취소: 취소 품목은 생산·출고·알림톡에서 빠지고 금액만 표시(PR #542). 표시 쪽은 `drop_cancelled` 로 뺀다 — 태블릿 시트의 규격 표가 이걸 쓰는지 확인(§3 가설 H11).

### 2.2 생산 기능(API)과 권한

- 쓰기 API 11개(`foms/api/production/orders.py`): start `:745` · complete `:908` · rework `:994` · cancel `:1148` · uncomplete `:1249` · change-ack `:1331` · steps GET `:1398` / POST `:1436` · defect `:1522` · hold `:1655` · logistics `:1729`.
- 공정 5단계 정의 `:73-79`(cut 재단·edge 엣지·paint 도장·assemble 조립·inspect 검수), 체크 권한 팀 CS·SALES·PRODUCTION(`:70`). 불량 사유 4종 화이트리스트(시트 칩과 1:1), 이력 최근 20건.
- 정책 `PRODUCTION_EDIT` = 팀 CS·SALES·PRODUCTION(`foms/services/orders/order_mutation_policy.py:180`).
- **생산팀은 ERP 주문 화면(`/edit/<id>`)과 주문 편집 fragment 를 못 연다**: `can_edit_erp`(`foms/services/erp_permissions.py:366`, 관리자·CS·영업만) → `foms/api/fragment.py:71` 에서 403. 태블릿 사이드 시트의 **기본** 내용 URL이 바로 이 fragment 다(`static/js/foms/tablet-side-sheet.js` 머리글). 생산 보드는 자기 시트 URL(`/production/tablet-sheet/<id>`)을 따로 주지만, 컨트롤타워·이력 등 다른 그리드 행을 생산팀이 태블릿에서 탭하면 403 이 날 가능성이 크다(가설 H1).
- 계정 만들기 화면 팀 목록에 "생산팀"이 있다(`foms/web/auth/routes.py:80`). 계정은 사용자가 만든다(코드 밖).

### 2.3 태블릿 표면 — 이미 있는 것 (2026-07-10~12 T0~T5, 2026-07-27 도면 리뷰 스테이션)

- 활성 게이트(SSOT, 모든 태블릿 JS·CSS 공통): `(min-width: 992px) and (orientation: landscape) and (pointer: coarse)` **그리고** CSS 마커 `--foms-tablet-ui: ready`. 마커는 `foms-tablet-side-sheet.css` 가 `body.erp-mobile-v2-layout` 에 정의 — 즉 **모바일 v2 셸 코호트**(`ERP_MOBILE_V2_ENABLED` + `FOMS_V3_SHELL_COHORT`, `foms/services/feature_flags.py` `is_enabled_for_user`)에서만 산다. 운영·스테이징 코호트 값은 Railway 에서 확인(측정 항목).
- **세로로 들면 폰 화면**: `static/css/foundation/foms-shell.css:11` — `(min-width: 992px) and (pointer: coarse) and (orientation: portrait)` 는 모바일 셸 쪽. 태블릿 세로 = 모바일 v2 큐 카드(`templates/production/partials/mobile_queue.html`) + 공정 체크 바텀시트.
- 서버 쪽 기기 힌트 쿠키 3종(렌더 생략용, 안전 폴백은 전부 렌더): `foms_ptr`(coarse/fine, `feature_flags.py:140`), `foms_scr`(화면 긴 변, 992 기준 `:175`), `foms_vw`(창 폭 구간 `:210`). 실화면 QA 때 쿠키가 없으면 첫 요청은 폴백 경로다.
- 공통 크롬: 레일 72px(`templates/partials/shared/foms_tablet_rail.html`, 항목은 `foms/services/foms_split_view.py:137 build_split_side_items` — **시공팀만** 4탭으로 좁히고 나머지 팀은 9탭+계산기 전부, 프리랜서는 문지기 목록), 사이드 시트 400px(`tablet-side-sheet.js` 479줄), 밀도 토글 40/48/56(`tablet-density-toggle.js`), 터치 보정(`foms-tablet-landscape.css`: 행 48px·타깃 44px·입력 16px).
- **생산 보드 태블릿**: 칸반 3열 + KPI 5타일(오늘 라인·시공 D-DAY·지연·보류·이번 주 자수) + 필터(공장·검색·변경·초기화) + 전체화면(`templates/production/partials/tablet_kanban_body.html`, `static/js/foms/tablet-production-kanban.js` 191줄, `static/css/foundation/foms-tablet-production-kanban.css`; 라우트 `foms/web/production/dashboard.py:93`, KPI `:288`, 칸반 행 상한 `PRODUCTION_KANBAN_MAX_ROWS`). 열 이동 = start/complete/rework 뒤 새로고침.
- **생산 작업 시트**(`/production/tablet-sheet/<id>`, `dashboard.py:408`, `templates/production/partials/tablet_sheet.html`): 고객명·#id·상차·보류/재제작/도면 배지와 사유·총 자수·규격 표·특이사항·도면 전달본 썸네일(탭=전역 뷰어 `GlobalImageViewer`)·액션. 머리글이 "액션 2개(보류 disabled / 생산 완료)"라고 적혀 있다 — 보류 API 는 있는데 시트에선 꺼져 있다(가설 H3). 액션 배선은 `static/js/foms/tablet-domain-sheets.js`(820줄, start/complete/rework + 출고 배정 `POST /api/erp/shipment/update/<id>`).
- **공정 체크 5단계·불량 보고 바텀시트는 모바일 v2 전용**(`templates/production/partials/production_steps_sheet.html` "B3 모바일 v2", `foms-production-steps.js`). 태블릿 가로 시트에는 없다(가설 H2 — 생산의 핵심 동작이 태블릿 가로에서 빠져 있을 가능성).
- 다른 팀 태블릿 표면(대조군·재사용 후보): 시공 작업 모드 3분할(`templates/construction/partials/tablet_workmode_body.html`, `tablet-construction-workmode.js` 405줄 — 타임라인·대형 뷰어·완료 확인), 완료 금액 그리드+정산 시트(`tablet_completion_grid_body.html`, `tablet-completion-sheet.js`), AS 사진 대조(`tablet_as_compare_body.html`), 도면 갤러리·시트(`drawing/partials/tablet_gallery_body.html`, `tablet_sheet_body.html`, 전체화면 핀치 줌 뷰어+판정 오버레이 2026-07-27), 실측 좌 목록+우 편집(`measurement/partials/tablet_split_body.html`), 출고 태블릿 컬럼, 계산기 태블릿 표피.
- 계약 시험(건드리면 빨강): `tests/domains/test_tablet_shell_t0_contract.py`, `test_tablet_t2_contract.py`, `test_tablet_rail_contract.py`, `test_tablet_dashboard_sheet_contract.py`, `test_tablet_domain_sheets_contract.py`, `test_tablet_drawing_workshop_contract.py`, `test_tablet_bulk_select_contract.py`, `test_tablet_as_compare_contract.py`, `test_shipment_tablet_columns_contract.py`, `test_wdcalculator_tablet_skin.py`, 생산 쪽 `test_production_kanban_full_window.py`·`test_production_kpi_slim_projection.py`·`test_production_dashboard_mobile.py`·`test_production_steps_api.py`·`test_production_hold_api.py`·`test_production_change_ack_api.py`·`test_mobile_production_construction_actions.py`.
- 설계 문서: `docs/design/MOBILE_TABLET_REDESIGN_PLAN.md`(2026-05-28, 페르소나 P2 "사무실 보조 — 태블릿 가로"가 있고 **생산 페르소나는 없다**), `MOBILE_TABLET_DESIGN_SYSTEM.md`(`--foms-*` 토큰, 터치 48px, 브레이크포인트), `COMPONENT_LIBRARY_MOBILE.md`(C01~C14), `docs/plans/2026-07-10-tablet-shell-t0-implementation-spec.md`, `2026-07-11-tablet-t2-dashboards-spec.md`(실행 결과·스테이징 실측·coarse 에뮬 요령 포함), `docs/specs/2026-07-27-drawing-tablet-review-station-design.md`. 당시 목업 v8 은 claude.ai artifact `1f9d4a9b` — **저장소에 없다**. 저장소 목업은 `docs/design/mockups/tablet-split-view.html`(1280×920 프레임, `_tokens.css`)·`tablet-wdcalculator-v2.html`·`_erp-mockup-bridge.css`(erp-pro 토큰 브리지)·`_erp-mockup-preset-picker.js`.
- 오늘(2026-11-09) 화면 크기 70~130% 손잡이(deploy `9d954d01b`)가 태블릿 CSS 8파일(`foms-tablet-bundle.css`·`foms-tablet-production-kanban.css` 등)과 `foms-ui-zoom.css` 를 바꿨다. 실화면은 배율 100% 와 바꾼 값 하나(예 80%)로 둘 다 본다.

### 2.4 기기(CSS px, 가로 기준 — 설계 때 사용자 답 §9 Q1 로 확정)

- 992 이상 가로 + 터치 = 태블릿 표면. 아이패드 10.2/10.9인치 가로 1080×810 / 1180×820, 아이패드 미니 1024×768, 갤럭시 탭 S 계열 가로 1280×800 안팎 — 모두 992 이상. 아이패드 프로 12.9 가로 1366×1024 는 T0 매트릭스의 1366 경계에 걸리므로 실측으로 확인.
- 세로는 아이패드 프로 12.9(1024)만 992 이상이고 나머지는 전부 폰 폭 — 세로 = 모바일 v2 화면.
- 시험 뷰포트 제안: 가로 1180×820(기본)·1024×768(작은 쪽), 세로 820×1180(폴백 확인), 음성 대조군 PC 마우스 1280×800 과 2400×1188(80% 배율 에뮬, `device_scale_factor=0.8`).

### 2.5 환경·QA 레시피

- 로컬 dev 에 태블릿 표면을 띄우려면 **코호트 env 2개**가 필요하다: `ERP_MOBILE_V2_ENABLED=true FOMS_V3_SHELL_COHORT=<내 user id>`(로컬 `.env` 엔 없다). 포트 5001 은 남의 서버일 수 있다 — 빈 포트를 고른다. 로컬 DB 는 주문 18건뿐이고 drift 가 있다(`users.contact_phone` 없음) — 생산 단계 주문이 필요하면 가짜 이름으로 시드하거나 스테이징을 쓴다.
- 헤드리스 크롬은 `pointer: fine` 이다. coarse 에뮬 = `MediaQueryList.prototype.matches` getter 패치(coarse+landscape 쿼리만 true) + CSS 는 `sheet.cssRules[i].media.mediaText` 교체(2026-07-11 T2 스펙 "staging 직접 실측" 절). Playwright 로 CSS 바꿔치기를 할 때는 `service_workers='block'`. 쿠키 `foms_ptr=coarse`·`foms_scr=<긴 변>` 도 같이 심어 서버 렌더 생략이 끼어들지 않게 한다.
- 스테이징 측정 계정 `claude_master`(ADMIN, id 58, 비번은 로컬 secrets). **생산팀 페르소나 계정은 없다** — 스테이징에 팀 = 생산팀 STAFF 계정을 하나 만들어 쓰고(이름 `CLAUDE-TEST-` 접두), 끝나면 비활성화. 운영 DB·운영 화면은 사용자 요청 1건당 1회 측정만.
- gstack browse 는 스크린샷마다 페이지를 다시 읽는다(열린 시트·뷰어가 닫힌다) — 상태 단언은 촬영 전에. 사장님은 PC 를 80% 배율로 본다 — PC 대조군은 그 배율로도 찍는다.
- 워크트리 cwd 는 턴 경계에서 리셋된다 — 명령마다 절대 경로.

## 3. 사전 가설 (결론이 아니다 — §4 단계 3 에서 실화면·코드로 확인하거나 뒤집는다)

| # | 가설 | 확인 방법 |
|---|---|---|
| H1 | 생산팀 계정으로 태블릿 컨트롤타워·이력 그리드 행을 탭하면 시트가 편집 fragment 를 불러 403 | 생산팀 계정 + coarse 가로 에뮬로 `/erp/dashboard` 행 탭, 네트워크 응답 코드 |
| H2 | 공정 체크 5단계·불량 보고가 태블릿 가로 시트에 없다(모바일 v2 바텀시트 전용) | `tablet_sheet.html`·`tablet-domain-sheets.js` 에서 `production/steps`·`defect` 호출 유무 + 실화면 |
| H3 | 작업 시트의 [보류]가 꺼져 있다(API 는 있음) | 시트 머리글 주석·DOM `disabled`·`hold` 호출 유무 |
| H4 | 도면 보기가 생산 작업에 모자란다: 전달본 썸네일 1장 → 전역 뷰어. 시트 여러 장 넘기기·치수 가독·"도면 바뀜(바로 반영)" 뒤 새 도면 구분이 약하다 | 도면 2장 이상인 생산 주문으로 뷰어 열기, 2026-07-27 도면 리뷰 스테이션 뷰어(핀치 줌·스와이프)와 비교 |
| H5 | 세로로 들면 폰 레이아웃(큐 카드)으로 떨어져 가로와 다른 화면을 배워야 한다 | 820×1180 실화면 |
| H6 | 생산팀 계정이 0이라 알림(벨·폰)이 아무에게도 안 간다. 공용 태블릿 1대·계정 1개면 "사람마다 확인"이 의미를 잃는다 | 사용자 답 §9 Q2 + `change-ack` 저장 구조 |
| H7 | 상차일(`load_md`)·출고 배정 상태를 생산 보드에서 읽을 수 있지만 출고 보드는 생산팀에게 열린다(쓰기만 막힘) — 필요한지 미정 | 생산팀 계정으로 `/erp/shipment` 접근·버튼 상태 |
| H8 | 레일 9탭(실측·AS·완료·이력·계산기 포함)이 생산에겐 소음 — 시공팀처럼 좁히는 게 맞을 수 있다 | `build_split_side_items` 분기 + 사용자 결정 §9 Q3 |
| H9 | 오늘 들어간 화면 크기 손잡이가 칸반·시트 높이(`90vh / --foms-ui-zoom`)에 영향 | 배율 80%·120% 에서 칸반 전체화면·시트 스크롤 |
| H10 | 생산 보드 PC 그리드(필터·컬럼·일괄 선택·관리자 되돌림)에 있는데 칸반·시트에 없는 기능이 있다 | PC 보드 기능표 vs 칸반·시트 기능표 1:1 |
| H11 | 품목 일부 취소된 주문에서 시트 규격 표·총 자수가 취소 품목을 빼는지 | `_prod_sheet_spec_rows_view`·`_prod_sheet_total_units` 가 `drop_cancelled` 를 거치는지 + 실화면 |
| H12 | 생산 변경 알림(도면 바뀜·시공일 변경·취소)이 태블릿에서 카드 빨간 표시 외에 벨·배너로도 보이는지, [확인] 뒤 다른 사람 화면은 어떻게 되는지 | 두 계정·두 화면 Playwright |

## 4. 순서

1. **준비** — 워크트리, 기준 HEAD, AI_STATUS 40줄, `/effort status`. 원장 파일 만들고 §0 기록. §9 질문을 질문 창으로 먼저 던진다(답을 기다리는 동안 2·3 을 진행).
2. **사실 카드 재측정** — §2 의 줄 번호·주장을 origin/deploy 기준으로 다시 확인. 틀린 값은 원장에 "재측정"으로 병기. 스테이징 Railway 변수에서 v2 셸 코호트 값을 읽는다(비밀값은 출력 금지, 켜짐·전체 여부만).
3. **생산 입장 현재 UI 전수 점검** — §5 워커 A~D 병렬.
   - 모집단 = 생산팀 계정이 닿을 수 있는 화면 전부: 로그인, 첫 화면(`/erp/dashboard`), 생산 보드(PC 그리드·태블릿 칸반·모바일 큐), 작업 시트, 공정 체크·불량, 보류, 변경 확인, 도면 뷰어, 알림 벨·공지(`/admin/notices` 보기), 회사 지식(열려 있다면), 출고·시공 보드(읽기), 주문 상세·이력(403 포함), 설정(화면 크기). 레일·하단 탭에서 갈 수 있는 곳은 전부 들어간다.
   - 잣대 = 1.1 의 할 일 1~6. 화면 × 할 일 표에 판정값(된다 / 되지만 불편 / 안 된다 / 해당 없음)을 하나씩 적는다. **판정값 합 = 모집단 수**가 돼야 전수다.
   - 음성 대조군: 같은 화면을 PC 마우스(1280, 2400@0.8)와 다른 팀 태블릿 표면 1장씩(도면·시공·완료)으로도 찍어 "생산만 빠진 것"과 "태블릿 전체 문제"를 가른다.
   - 증적 = 실화면 스크린샷(가짜 데이터, 실제 템플릿·실제 CSS) + 네트워크 응답 코드. 합성 DOM 주입은 검수가 아니다.
4. **회사 단계 흐름과의 접점 표** — 단계 11종 각각에 대해 "생산이 봐야 하는 것 / 눌러야 하는 것 / 받아야 하는 알림 / 넘겨야 하는 것"을 한 줄씩. 특히 고객컨펌 → 생산 진입(퀘스트·도면 상태), 생산 → 시공·출고(상차일·출고 배정·시공일 변경), 옆길(도면 바로 반영·품목 취소·주문 취소·AS 재제작 여부는 코드로 확인).
5. **목업** — §5 워커 E. 결과는 `docs/design/mockups/tablet-production-*.html`(프레임 1180×820 가로 기본, `_tokens.css`·`_erp-mockup-bridge.css` 사용, 가능하면 실제 `erp-pro.css`·`foms-tablet-*.css` 를 링크해 "그대로"를 맞춘다) + 같은 내용을 Artifact 한 장으로 띄운다(프레임을 세로로 이어 붙이고 각 프레임 위에 "지금 화면 → 바뀐 칸" 한 줄). 프레임 후보(검증 대상 — 전수표 결과로 늘리거나 지운다):
   - F1 생산 보드(칸반) — 바뀐 칸만.
   - F2 작업 시트 — 공정 체크 5단계·불량·보류를 시트 안에서(H2·H3).
   - F3 도면 보기 — 전체화면·여러 장·치수·"바뀐 도면" 표시(H4, 2026-07-27 도면 뷰어 재사용 전제).
   - F4 변경 확인 — 도면 바뀜·시공일 변경·취소를 어디서 어떻게 보고 [확인]하나(H6·H12).
   - F5 넘기기 — 제작 완료 뒤 상차·출고 배정·시공일 읽기(H7).
   - F6 세로 폴백 — 폰 화면 그대로 둘지, 최소 보정만 할지(H5).
   - F7 첫 화면·레일 — 생산팀이 로그인하면 어디로 떨어지고 레일에 무엇이 남나(H1·H8).
   - 목업 글 규칙: 한 화면에 같은 사실은 한 번, 기계 말(키·코드 이름·D번호) 금지, 해요체, 빈 상태 글은 행동이 필요할 때만. 가짜 고객 이름(예 "김하늘")·가짜 번호(02-0000-0000).
6. **설계서 초안** → **리뷰 3(§5)** → finding 은 총괄이 직접 재확인한 뒤 반영 → **사용자 승인**(요약 + Artifact 링크 + 결정할 것) → **플랜·원장**(task 마다 완료 기준·검증 명령·대상 파일·경계, 한 세션 크기). 구현은 다음 세션.

## 5. 병렬 에이전트 구성 (사용자 지시 5번 — 총괄이 상황 따라 조정하되 기본은 이 표)

| 역할 | 수 | 모델 · effort | 읽기/쓰기 | 산출물(원장에 그대로 붙임) |
|---|---|---|---|---|
| 총괄(이 세션) | 1 | Fable 5.1 · xhigh | 전부. 워커 결과는 주장 — diff·화면·응답 코드를 직접 다시 본 뒤에만 사실로 올린다 | 원장·설계서·플랜·Artifact |
| 워커 A 권한·라우트 | 1 | Fable 5.1 · high | 읽기만 | 생산팀 계정이 닿는 라우트 전수표(엔드포인트·권한 함수·403 예상) + H1·H3·H11 코드 판정 |
| 워커 B 태블릿 표면·게이트 | 1 | Fable 5.1 · high | 읽기만 | 태블릿 JS·CSS·템플릿 기능표(PC 보드 vs 칸반 vs 시트 vs 모바일 큐 1:1, H2·H10) + 재사용 가능한 다른 팀 부품 목록 |
| 워커 C 단계 흐름·알림 | 1 | Fable 5.1 · high | 읽기만 | §4-4 접점 표 + 알림 종류·수신 팀·합치기 규칙·H12 코드 판정 |
| 워커 D 실화면 수집 | 1 | sonnet · medium | 스크린샷·네트워크 로그만(스크래치패드) | 모집단 화면 × 뷰포트 4종 스크린샷 + 응답 코드 표(기계적 반복 — 판정은 총괄) |
| 워커 E 목업 제작 | 1~2 | Fable 5.1 · xhigh | `docs/design/mockups/tablet-production-*` 만 쓰기 | 프레임 F1~F7 + 프레임마다 "지금 → 바뀐 칸" 주석 |
| 리뷰어 ① 반증 | 1 | Fable 5.1 · high | 읽기만 | 설계서를 실제 코드·실화면으로 깨뜨리기(특히 권한·게이트·세로 폴백) |
| 리뷰어 ② 단순화 | 1 | Fable 5.1 · high | 읽기만 | 지울 프레임·칸·새 부품 찾기("기존 칸 하나만 바꿔라" 잣대) |
| 리뷰어 ③ 사실 검증 | 1 | Fable 5.1 · high | 읽기만 | §2 사실 카드·전수표 판정값을 origin/deploy 로 재확인 |

- Agent 호출에 `model`·`effort` 를 명시한다(Fable 5.1 = `model: "fable"`). 브리프에는 경로:행 앵커·완료 기준(검증 명령)·변경 범위(쓰기 허용 파일)·"CRLF 보존·git 금지·docs 읽는 시험 금지"를 박는다.
- 워커 A~D 는 동시에 띄운다(서로 독립). E 는 전수표가 나온 뒤. 리뷰 3 은 설계서 초안 뒤 동시에.
- 워크플로가 도는 동안 총괄은 그 트리의 파일을 편집하지 않는다(읽기·pytest 는 안전). 리뷰 finding 은 받는 즉시 전량 원장에 적고 그다음 재검증한다.

## 6. 규칙·함정 (메모리에서 옮김)

1. **화면은 기존 칸 하나만 바꿔라.** 새 그림·칩·요약 상자를 늘리면 "쓸데없이 복잡·시인성 낮음"으로 거절된다(2026-11-03). 목업·설계 전에 (1) 실사용자가 누구고 어디서 무엇으로 쓰는지 한 줄, (2) 문제를 만드는 칸 하나, (3) 그 칸만 기존 부품으로. 실제 템플릿·실제 CSS 로 렌더하면 "그대로"가 맞는다.
2. **글은 같은 말 한 번·기계 말 금지·해요체**(2026-11-04). 판단에 필요한 점(처음 값·범위·위험·누가 보나)은 남긴다.
3. **임의 축소 금지.** "모든 UI"·"완성 목업" 지시를 리스크 이유로 줄여 해석하지 않는다. 줄일 거면 사용자에게 선택지로 묻는다.
4. **전수 확인은 음성 대조군까지** 세야 전수다. 대조군은 모집단 안에서 고른다.
5. **실데이터·실화면.** 합성 DOM 주입은 검수가 아니다. 가짜 데이터는 실제 앱 경로로 시드한다. 저장소가 공개라 고객 실명·전화·주소를 목업·문서·커밋에 넣지 않는다.
6. **PC 80% 배율.** PC 대조군 글자·단추 크기를 줄이는 제안 금지. 태블릿 쪽도 터치 48px·입력 16px 아래로 내리지 않는다(`foms-tablet-landscape.css` 계약 시험이 막는다).
7. **코딩 규약(구현 세션용, 설계서에 그대로 적는다)**: 인라인 스타일 금지(`erp-pro.css`·`foms-tablet-*.css`, 래칫 시험), jQuery 금지, `fetch` 는 try/catch + `data.success`, Jinja→JS 는 `data-*` + `safeJsonParse`, 인라인 `<script>` 300줄 래칫(태블릿 JS 는 거의 꽉 참 — 새 동작은 별도 파일), 정적 자산 `?v=` 핀은 자식 바꾸면 부모 번들 핀도(`foms-tablet-bundle.css`·`foms-mobile-surfaces.css`), 게이트는 `--foms-tablet-ui` 마커에서 파생(이중 정의 금지), 전역 리스너는 싱글턴 가드(G4)·defer(G1), 새 라우트는 `foms/web/`·`foms/api/` Blueprint + `foms/platform/blueprints.py` 뒤에만, 쓰기 라우트는 `docs/harness/foms_order_mutation_policy_manifest.json` 등재.
8. **비밀값·개인정보 원문 출력 금지.** Railway 변수는 켜짐·전체 여부만 적는다. `.mcp.json` 은 열지 않는다.
9. **목록은 턴 맨 마지막 메시지에만**, 질문·선택지까지 전부 한글, 결정 질문은 질문 창 안에 설명을 넣어 묻는다. 대화가 길다고 스스로 /compact 를 권하지 않는다.
10. **git**: 커밋은 사용자가 시킬 때만, 한글 메시지는 UTF-8 파일로 `git commit -F`. push·production 금지. 설계 세션은 코드를 고치지 않는다.

## 7. 결과물

- 원장 `docs/plans/2026-11-09-tablet-production-ui-ledger.md` — §0 시작 HEAD·재측정, 워커 보고 원문, 리뷰 finding 전량, 사용자 답·결정(D1~).
- 전수표 `docs/plans/2026-11-09-tablet-production-ui-inventory.md` — 화면 × 할 일 판정표(모집단·판정값 합·대조군), 스크린샷 파일 이름(스크래치패드 경로, 저장소엔 넣지 않음).
- 설계서 `docs/specs/2026-11-09-tablet-production-ui_SPEC.md` — 순서: 페르소나 → 단계 흐름 접점 표 → 전수표 요약·결함 목록 → 목업 프레임마다 "지금 → 바뀐 칸 → 쓰는 기존 부품·API" → 권한·게이트·세로 폴백 → 시험 목록(계약 시험·실화면 뷰포트 4종) → 범위(포함/제외) → 사용자 결정.
- 목업 `docs/design/mockups/tablet-production-*.html`(+ 필요하면 `tablet-production_PROMPT.md` 구현 지시 — `mobile-drawing-handoff_PROMPT.md` 꼴) + **Artifact 1장**(사용자가 바로 봄, 비공개 기본).
- 플랜 `docs/plans/2026-11-09-tablet-production-ui-plan.md` — task 마다 완료 기준(검증 명령)·대상 파일·경계, 한 세션 크기, 단계 제안: ① 권한·게이트 구멍(H1·H6) ② 작업 시트 안 공정·불량·보류(H2·H3) ③ 도면 보기(H4) ④ 변경 확인·넘기기(F4·F5) ⑤ 세로·첫 화면·레일(F6·F7).
- `docs/AI_STATUS.md` 진행 중 1줄(승인 뒤).

## 8. 완료 기준 (설계 세션)

- §9 질문의 사용자 답이 원장과 설계서에 적혀 있다(답이 늦으면 가정을 명시하고 진행, 가정 표에 남긴다).
- 전수표: 모집단이 레일·하단 탭·보드 안 링크를 따라 닫혀 있고, 판정값 합 = 모집단 수, 음성 대조군(PC 2종 + 다른 팀 태블릿 3장) 포함, 모든 판정에 스크린샷 또는 응답 코드 증적.
- 가설 H1~H12 각각에 "확인됨 / 뒤집힘 / 해당 없음" + 근거(경로:행 또는 화면).
- 단계 흐름 접점 표 11행이 있고, 생산이 받는 알림 4종의 태블릿 노출 경로가 적혀 있다.
- 목업 프레임마다 "지금 화면 스크린샷 → 바뀐 칸" 짝이 있고, 새 부품을 넣은 프레임은 왜 기존 칸으로 안 되는지 한 줄 근거가 있다. 글 규칙(6-2) 통과. Artifact 링크가 사용자에게 전달됐다.
- 리뷰 3 finding 이 원장에 전량 있고, 총괄 재확인 결과(반영/기각 이유)가 붙어 있다.
- 플랜 task 전부에 검증 명령이 있고, 검증 불가능한 task 가 없다. 계약 시험(§2.3 목록) 중 바뀔 것이 task 마다 적혀 있다.
- 앱 코드·패키지·브랜치 push 변경 0(`git status` 로 증명, 목업·문서만).

## 9. 남은 질문 (세션 시작 직후 질문 창으로 — 쉬운 말, 설명은 창 안에)

- **Q1 기종·방향**: 아이패드인가 갤럭시 탭인가, 화면 몇 인치, 가로로 고정해 쓰나(거치대) 아니면 들고 돌리나. → §2.4 뷰포트와 세로 폴백(F6) 범위가 바뀐다.
- **Q2 사람·계정**: 생산 인원 몇 명, 태블릿은 사람마다인가 공용 1대인가, 계정은 각자 만들 건가. → "사람마다 확인"(변경 알림)과 알림 벨·폰 알림 설계(H6)가 바뀐다.
- **Q3 생산팀이 태블릿으로 볼 범위**: 생산 보드만인가, 출고(상차)·시공 일정도 보나, 금액·고객 전화는 가려도 되나. 레일 탭을 시공팀처럼 좁혀도 되나(H7·H8).
- **Q4 지금 하는 방식**: 생산팀이 지금 작업 지시를 무엇으로 받나(종이 출력·카톡 발주방 글·구두). 그중 태블릿으로 옮길 것과 종이로 남길 것. 작업지시서 인쇄가 필요하나.
- **Q5 공장 환경**: 와이파이인가 LTE 인가, 끊길 때가 있나(오프라인 보기 필요 여부), 장갑 낀 채 쓰나(터치 크기·확인 창 수).
- **Q6 다른 태블릿 사용자**: 생산 말고 누가 태블릿을 쓰나(도면·출고·시공·CS). 이번 범위에 넣나, 생산이 끝난 뒤 따로 하나.

설계 세션이 코드·실측으로 직접 확인할 것(사용자에게 묻지 않는다): 스테이징·운영 v2 셸 코호트 값, 생산 단계 주문 수·도면 2장 이상 주문 수(스테이징), 생산 변경 알림이 최근 30일 몇 건 생겼나(스테이징), 가설 H1~H12.
