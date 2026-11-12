# 태블릿 생산 UI 설계 세션 — 원장 (2026-11-09)

지시서: `docs/plans/2026-11-09-tablet-production-ui-meta-prompt.md`. 이 원장은 그 §7 의 원장이다.

## 0. 시작 상태

- 시작 HEAD: origin/deploy `ea4376ea1` (메인 체크아웃 `C:/DEV/FOMS` 와 같음, ahead/behind 0/0, 2026-11-09 측정).
- 워크트리: `c:/tmp/foms-s-tablet-prod-ui`, 브랜치 `session/tablet-prod-ui`(base origin/deploy). 세션 워크트리 14개 활성(권장 3) — 정리는 이 세션 범위 밖.
- 로컬 환경: PostgreSQL 5432 떠 있음(`furniture_orders`), 포트 5000~5010 비어 있음, `.env` 에 `ERP_MOBILE_V2_ENABLED`·`FOMS_V3_SHELL_COHORT`·`DATABASE_URL` 없음, Playwright 설치됨.
- 총괄 모델: Fable 5.1(이 세션). effort 는 하네스 설정값(`/effort status` 는 세션 안에서 못 부름 — 사용자가 확인).

## 1. 사용자 결정 (질문 창 답, 2026-11-09)

- **D0** 진행 방식: 새 세션이 아니라 **이 세션에서 바로 시작**(메타프롬프트 §0.1 복붙 대신).
- **D1 (Q1) 기종**: **갤럭시 탭**. 가로 약 1280×800 CSS px 기준. 세로로 돌리면 폰 화면(992 미만).
- **D2 (Q2) 사람·계정**: **사람마다 계정, 사람마다 태블릿**. "사람마다 [확인]"(생산 변경 알림) 구조 그대로 쓸 수 있다.
- **D3 (Q3) 볼 범위**: "생산, 출고, 시공 일정도 봐야 되고, 고객이름, 주소, 전화번호 등 다 볼 수 있어야 돼" → 레일을 생산만으로 좁히지 않는다. 생산·출고·시공(일정 읽기)은 필수, 고객 이름·주소·전화는 **가리지 않는다**. 금액은 지시 없음 → 지금 그대로(설계서에서 "그대로 둠"으로 명시). 실측·AS·완료·이력·계산기 탭을 뺄지는 설계서 제안으로 남기고 사용자 승인 때 묻는다.
- **D4 (Q4) 지금 방식**: 구두·전화 + 카톡 발주방 글(PUSH) + 종이 출력(작업지시서·도면). **태블릿에서 인쇄도 필요할 수 있다** → 목업 후보에 F8 "작업지시서·도면 인쇄" 추가(브라우저 인쇄 CSS 재사용 여부는 코드로 확인).
- **D5 (Q5) 공장 환경**: 장갑 끼고 쓴다 · 와이파이 안정 · **가끔 연결이 얼어요** → 터치 타깃을 48px 아래로 내리지 않고 확인 창을 줄인다. 연결이 얼었을 때 "마지막 화면 유지 + 다시 연결되면 보냄"은 설계서에 범위 판단(오프라인 저장은 큰 일 — 최소안: 실패 시 재시도 안내·입력 보존).
- **D6 (Q6) 다른 사용자**: "생산만 · 시공팀·CS·영업 · 출고팀 · 도면팀" 전부 선택 → 모든 팀이 태블릿을 쓸 수 있다고 읽는다. 목업 1순위는 생산, 다른 팀 태블릿 표면은 **전수 점검(결함 목록)에 넣되** 목업은 2차(플랜 뒷 단계). "생산만"이 함께 선택된 점은 승인 때 한 줄로 되묻는다.

## 2. 재측정 (사실 카드 §2 와 다른 값만)

- 지시서 §2.3 "태블릿 CSS 체인 `foms-tablet-bundle.css` ← `foms-mobile-surfaces.css`" 는 옛 구조 — 지금은 `layout_head.html:271` 이 `foms-tablet-bundle.css?v=20261109a` 를 따로 싣고 surfaces 에는 태블릿 레이어가 없다(워커 B, 시험 `test_tablet_t2_contract.py:109-110` 고정).
- 지시서 §2.3 "시트 [보류] 꺼져 있음" → 틀림(H3 뒤집힘). 시트 머리 주석이 낡았을 뿐.
- 지시서 H9 전제 "90vh" → 태블릿 CSS 에 없음. 미보정은 변경 모달 목록 `60vh` 하나(실화면 130% 에서 확인).
- 워커 C 로컬 "생산 단계 0건" vs 총괄 측정 `erp_stage_code='PRODUCTION'` 5건(2건 DELETED·3건 items 0) — 열이 다름. 로컬 DB 는 어차피 QA 에 못 쓴다(도면 0·품목 0). 실화면은 스테이징으로 했다.
- 스테이징 코호트: 이날 만든 생산팀 계정이 바로 태블릿 표면(레일·칸반·마커 ready)을 받음 → 스테이징 `FOMS_V3_SHELL_COHORT` 는 전체. 운영 값은 미확인.
- **측정 함정 2개(다음 세션용)**: ① Playwright `full_page=True` 캡처는 문서 높이가 폭을 넘는 순간 `orientation: portrait` 가 되어 태블릿 규칙이 풀린다(출고 화면이 PC 크롬으로 찍혔다) — 뷰포트 캡처만 판정에 쓴다. ② 가로 생산 보드 DOM 에는 숨은 레거시 `#erp-grid` 행이 칸반보다 앞에 있어, `#erp-grid tr, .foms-kanban-card` 같은 합친 셀렉터로 "첫 카드"를 고르면 숨은 행을 눌러 기본 fragment 403 이 난다(1024 대조군의 403 은 이 탓, 결함 아님).
- 지시서 줄 번호 정정(리뷰 ③): 계정 팀 목록 "생산팀" `auth/routes.py:85`(TEAMS :81-91) · `foms_scr` 기준 `feature_flags.py:177`, `foms_vw` 판정 `:229-271` · `build_split_side_items` 는 `foms_split_view.py:129` · 도면 TRANSFERRED 막힘 `orders.py:807-828`(제작 시작)·`:1055-1060`(수정 제작) · 시트 뷰 `dashboard.py:408-468`, 썸네일 `:383-405`.
- 워커 D 는 띄우지 않았다 — 하네스(`scratchpad/tablet_shot.py`)를 총괄이 만들고 5모드 사전 스윕 + 보강 2회를 직접 돌렸다(비용·자격증명 노출 둘 다 줄임). 판정은 총괄이 PNG 를 직접 봤다.

## 3. 워커 보고 (원문 그대로 붙임)

### 3.A 권한·라우트
보고 원문: `2026-11-09-tablet-production-ui-worker-A.md`(Fable 5.1 high, 65 도구 호출, 10.5분). 핵심: 생산팀은 `can_edit_erp` 밖 → 컨트롤타워 시트(자체 라우트)·AS 표 행(기본 fragment) 403, `/edit/<id>` 는 302 `/`+flash, 이력 시트는 200. 출고 배정 API 는 CS/SALES 데코레이터라 생산팀·출고팀 STAFF 모두 403(부수 발견). 모바일 하단 탭에 '생산' 없음. 로그인 착지는 `Sec-CH-UA-Mobile` 판정 → 태블릿은 `/` 레거시 목록일 가능성(추정).

### 3.B 태블릿 표면·게이트·기능표
보고 원문: `2026-11-09-tablet-production-ui-worker-B.md`(Fable 5.1 high, 63 도구 호출, 13.1분). 핵심: 태블릿 가로에서 생산팀이 못 하는 일 = 공정 5단계 체크·불량 보고(모바일 바텀시트 전용) · 도면 여러 장 보기(시트는 첫 1장) · 고객 연락처·주소(카드·시트 모두 없음 — 사용자 D3 와 충돌) · 서버 필터·정렬·내 것 토글 · 제작 취소·완료 취소는 시트에서만 · 출고 배정 없음. 역방향 격차: 보류 토글·변경 확인·묘비·KPI 탭·전체화면은 태블릿에만. 태블릿 CSS 체인은 `foms-tablet-bundle.css`(surfaces 아님). JS 래칫은 .js 300줄 + 기준선 목록, `tablet-production-kanban.js` 남은 줄 109. 공정 체크 시트는 include + 버튼 1개로 가로에서도 동작(JS 전역 로드).

### 3.C 단계 흐름·알림
보고 원문: `2026-11-09-tablet-production-ui-worker-C.md`(Fable 5.1 high, 68 도구 호출, 11.7분). 핵심: 생산 접점은 고객컨펌·생산·시공 3단계 + AUTO_PRODUCTION_D2 할 일. 출고 겹축·출고 2주 판은 생산 화면에 안 보임. AS → 재제작 경로 없음(시공 불가 `product_defect` 와 [수정 제작]만). 품목 일부 취소는 알림이 안 감. 도면 바로 반영은 합치기 없이 매번 폰 push. 발주 PUSH 는 채널톡 방이라 FOMS 알림 밖. 상차일 = 시공일 같은 키.

### 3.D 실화면 수집(총괄 직접)
- 하네스 `scratchpad/tablet_shot.py`(모드 tablet 1280×800 · tablet_s 1024×768 · portrait 800×1280 · pc · pc80, `--zoom` 으로 배율 흉내), 로그인 상태 `state_prod.json`(생산팀 STAFF `claude_test_prod`, 스테이징에서 이날 생성)·`state_master.json`(claude_master).
- 스윕: 모집단 31 경로 × tablet·portrait, 대조군 7 경로 × tablet_s·pc·master, 보강 14+5+3 장(뷰포트 캡처). 결과 표·PNG 는 `scratchpad/shots/*/results.jsonl`·`*.png`.
- 판정 전수표: `2026-11-09-tablet-production-ui-inventory.md`(화면 24 × 잣대 6 = 144 칸, 대조군 4). 결함 F-01~F-20.

## 4. 가설 판정 (H1~H12)

| # | 판정 | 근거 |
|---|---|---|
| H1 | **확인됨(실화면)** — 기전은 조건부 | 컨트롤타워 시트는 자체 라우트지만 `can_edit_erp` 검사로 403(`foms/web/orders/dashboard.py:653-654`), AS 표 행만 기본 fragment 403(`fragment.py:72`), 이력 시트 200. 403 때 시트 문구 "내용을 불러오지 못했습니다"(권한 안내 없음) |
| H2 | **확인됨(코드+실화면)** — 가로 시트 단추 = 보류·완료 취소·수정 제작/제작 시작뿐, 세로 바텀시트에만 공정 5체크 | `tablet_sheet.html`·`tablet-domain-sheets.js`·`tablet_kanban_body.html` 에 `production/steps`·`defect`·`data-foms-prod-steps-open` 없음. 시트 마크업은 `mobile_queue.html:113` 에만. JS `foms-production-steps.js` 는 `dashboard_body.html:161` 전역 로드 → include + 버튼이면 동작 |
| H3 | 뒤집힘(코드, 워커 A) | `tablet_sheet.html:176-182` [보류] 에 disabled 없음, `tablet-domain-sheets.js:204-245` 가 hold API 호출. 머리 주석 ":6 보류 disabled" 가 낡음 |
| H4 | 확인됨(코드) · 실화면 일부 | 시트 `drawing_thumb` 는 첫 1장(`dashboard.py:383-407`), 칸반엔 도면 열기 없음, 바뀐 도면 구분 없음. 스테이징 도면 파일이 깨져(4103 썸네일 로드 실패, 4082 는 전달본 0·첨부 2) 뷰어 실동작은 못 봄 → 운영 재확인 |
| H5 | 확인됨(실화면) | 800×1280 에서 레일 숨김·칸반 숨김·모바일 큐 카드. 하단 탭에 '생산' 없음(F-07) |
| H6 | 해소(사용자 D2) | 사람마다 계정·태블릿 → "사람마다 확인" 구조 그대로. 운영 생산팀 계정은 사용자가 만든다 |
| H7 | 확인됨(실화면) | 출고 태블릿 판·시트 읽기 200, 배정 쓰기 403. 생산 카드엔 출고 배정 상태 없음(워커 C) |
| H8 | 사용자 D3 로 좁히지 않음 | 생산·출고·시공 필수. 실측·AS·완료·이력·계산기 빼기는 승인 때 질문(F-18) |
| H9 | **확인됨(실화면 130%)** — 전제 90vh 는 틀림 | 90vh 전제는 틀림(시트는 top/bottom 고정). 칸반 열·전체화면·변경 모달은 `/zoom` 보정됨(시험 고정). 미보정: 변경 모달 목록 `max-height: 60vh`(`foms-tablet-production-kanban.css:926`) → 130% 잘림 가능(추정). 배율 손잡이가 가로 레일 모드에서 둘 다 숨어 **가로에서는 배율을 못 바꿈**(추정) |
| H10 | 조건부(코드, 워커 B) | PC 에만 있는 것: 서버 필터(단계·팀·긴급·경보·검색 UI)·정렬·고객 연락처·주소 열·첨부 모달 여러 장. "일괄 선택·관리자 되돌림"은 PC 에도 없음(함수만). 역방향 격차(태블릿에만): 보류 토글·변경 확인·묘비·KPI 탭·전체화면 |
| H11 | 확인됨(코드, 워커 A·C 일치) | 시트 규격 표·총 자수·카드 자수·KPI 이번 주 자수 모두 `active_items`(`dashboard.py:199,317,427,447`) → `drop_cancelled`. 원본 세는 곳은 "취소 품목 N개" 배지만(의도) |
| H12 | 확인됨(코드, 워커 C) | 카드 빨간 표시는 요청자 본인의 `PRODUCTION_CHANGE_ACK` 만 봄(`production_change_alerts.py:121-130`), 벨은 [확인]과 무관(본인 read 만). 사람마다 계정(D2)이면 설계 그대로 맞음 |

## 5. 리뷰 finding (전량, 받는 즉시)

- 리뷰어 ② 단순화: 원문 `2026-11-09-tablet-production-ui-review-2.md`(Fable 5.1 high, 15 도구 호출, 7.2분). 요지: 바뀐 칸 18개 중 남김 6(F1 ③·F2 ①·F2 ③·F6 ①·F7 ①·D5 문구), 줄임 5(F2 ④·F2 ⑤·F7 ②·F-13·시험/CSS 재사용), 지움·미룸 7(F1 ①·F1 ②·F2 ②·F3 새 JS·F6 ②·F7 ③·F8·T5-3). 새로 만드는 것 10개 중 남는 것 = 60vh 보정 1개(+인쇄는 미룸). 플랜 17 → 8 task, P1~P3. 질문 5개 모두 설계자가 정해도 됨.
- 리뷰어 ① 반증: 원문 `2026-11-09-tablet-production-ui-review-1.md`(Fable 5.1 high, 79 도구 호출, 10.2분). 깨짐 7(F2 ③ 공정 JS 는 document 전역 6곳이라 "1곳 일반화" 불성립 · 가로 DOM 에 세로 오프캔버스가 먼저 있어 id·data 중복 · 카드 "공정 n/5" 단추는 세로 시트를 연다 · 착지는 `listing.py:158`·`post_auth_navigation.py:100-101` 두 곳이 직접 dashboard · 읽기 전용 시트에 승인 단추 잔존 · F-13 호출 지점 `:46` 은 해시 헬퍼, 60초 합치기가 품목 2개를 덮어씀 · §9 쿼리 수 시험은 대시보드만), 조건부 9, 버팀 18. 전수표 #19 ② 는 △(모바일 상세는 취소 품목을 라벨 붙여 보여 줌).
- 리뷰어 ③ 사실 검증: 원문 `2026-11-09-tablet-production-ui-review-3.md`(Fable 5.1 high, 44 도구 호출, 10.7분). 틀림 14(착지 3곳·공정 시트 줄 `:15-35`·JS 경로 `static/js/production/`·F-13 호출 지점·시험 3개 역할 오귀속·카드 스트립 위치 `:184-197`·시트 단추 목록에 [제작 취소]·지시서 줄 번호 3), 모호 13(줄 번호 어긋남·confirm 수·터치 계약 44/48·시공팀 키 `shipment.construction_workers`). 설계서 §3·§5~§9 나머지 경로·숫자(JS 줄 수·래칫·상한 300·공정 5·불량 4)는 맞음.

### 6.3 리뷰어 ③ 반영
- 틀림 14 중 반영판(6.1·6.2)에서 이미 고친 4(착지 3곳·JS 경로·F-13 지점·읽기 전용 시트→문구) 빼고 나머지 전부 설계서·플랜에 파이썬 치환으로 반영(설계서 18/18·플랜 8/8 치환 성공). 지시서 줄 번호 3건은 §2 재측정에 추가: `auth/routes.py:85`(TEAMS :81-91), `feature_flags.py:177`(`WIDE_SURFACE_MIN_PX`)·`:229-271`(`wants_mobile_width_surfaces`), `foms_split_view.py:129`(`build_split_side_items`), `orders.py:807-828`·`:1055-1060`(TRANSFERRED 막힘).

## 6. 총괄 재확인·반영

### 6.1 리뷰어 ② 재확인(코드로 직접)
- `templates/partials/shared/foms_ui_zoom_control.html` 있음(변형 bar/drawer, `data-foms-ui-zoom-ctl`), `ui-zoom.js:43` 은 로드 때 `querySelectorAll('[data-foms-ui-zoom-ctl]')` — 레일은 레이아웃 소유(로드 때 있음)라 include 가 먹음 → **F1 ① 은 "지움" 대신 "include 1줄 + 레일 변형 CSS 몇 줄"로 줄임**(사용자 D5 장갑·세로로 돌려 정하라는 건 공장에서 번거로움, 가로 손잡이는 남긴다 — 총괄 판단).
- `static/js/foms/erp-attachment-preview-open.js:147,163-167` `galleryFilesFromNodes` → `GlobalImageViewer.open(files, idx)` 확인, 로드 지점 `foms_mobile_queue_attachment_preview_bundle.html:4`(모바일 큐 번들) → 생산 페이지에 이미 실리는지 T3-1 에서 확인. 뷰어 counter "n / N" `layout-scripts-core.js:262-264` 확인 → **F3 새 JS 지움, F2 ④ 글 두 개 지움 수용**.
- `fragment-loader.js:92-100` renderError 는 status 를 모름(`:124` throw) → "문구만"도 status 전달 1줄 필요. **F7 ② 는 읽기 전용 렌더 대신 403 문구로 줄임**(Q-D 삭제).
- `tablet_sheet.html:6,9,169` "생산 완료" 확인 → 세로·설계서와 같은 "제작 완료"로 글 통일(계약 시험은 confirm 문구만 고정).
- `production_change.py:138` 기본 라벨 "주문 변경" 확인 → **F-13 은 호출 1줄로 줄임**(라벨 "주문 변경"이 생산 사람에게 충분한지는 실화면에서 한 번 더 본다).
### 6.2 리뷰어 ① 재확인(코드로 직접)
- `static/js/production/foms-production-steps.js:56,159,162,191-194` 전부 `document.querySelector`, `:18,275` 전역 `currentOrderId`, `:309` capture `stopImmediatePropagation` 확인 → **F2 ③ 은 "스코프 객체로 재작성"**(루트 `[data-foms-prod-steps-sheet]` 기준, id 제거, 시트 삽입 때 `loadSteps(id, root)`). 파일 경로도 설계서의 `static/js/foms/` 가 아니라 `static/js/production/` — 고침.
- `listing.py:158-159`·`post_auth_navigation.py:100-101` 직접 `url_for('erp_dashboard.erp_dashboard')` 확인 → **착지 분기는 세 곳**(+ `auth/routes.py:585` switch_user). PC 마우스도 생산 보드로(기기 무관, 총괄 결정).
- `production_change.py:148-156` merge 가 title/message 덧쓰기 확인 → **F-13 은 `merge=False` + 라벨 추가**, 삽입은 `_mutate` 안 `:78` 뒤(REV-99 인벤토리 lineno 주의).
- F7 ② 는 6.1 대로 "문구만"이라 승인 단추 잔존(R1 #8)은 해당 없음. 단 `Sec-Fetch-Dest: document` 302(R1 #10)는 생산팀이면 모바일 상세로.
- F1 ① 배율 단추 위치 = 레일 **브랜드 바로 아래**(130% 에서도 보임, R1 #17).
- **수용 안 함**: F2 ② "상차 → 시공" 이름 바꾸기 — 값은 같은 키지만 공장 말로는 상차가 맞을 수 있다(KPI 도 "오늘 상차"). 이름은 두고 "시공팀" 추가만 지운다. F8 인쇄 — 사용자 D4 "필요할 수 있어"라 **지우지 않고 승인 질문으로**(지금 할지·뒤로 미룰지). Q-A 금액 — 돈 노출은 사장님 몫이라 질문 유지. Q-B·Q-C·Q-E 는 리뷰어 판정대로 설계자가 정함(지금처럼·그대로·별건).

### 6.4 목업·발행
- 워커 E(Fable 5.1 xhigh, 71+21 도구 호출, 약 32분): `docs/design/mockups/tablet-production-ui.html`(1,294줄, 자급자족, 가짜 데이터, 한자 0, 실명 0, 1280/400 가로 스크롤 0). 리뷰 반영 수정 1회(레일 배율 단추 위로 · 카드 "공정 n/5" 삭제 · 시트 "시공팀"·"1/3"·"바뀐 도면" 삭제 · 링크 "상세" 하나 · F3 오버레이 삭제 · F6 QR 그대로 · F7 문구 · 질문 2개). 총괄이 프레임 6장을 1400 폭에서 직접 렌더해 확인.
- Artifact(비공개, 사용자만): https://claude.ai/artifact/1otSBdYuZ2PhD4ai4zRyor — 껍데기 벗긴 판 `scratchpad/tablet-production-ui.artifact.html`(저장소 판과 본문 동일).
- 스테이징 시험 계정 `claude_test_prod`(id 101) 비활성화 완료(11-09 12:26 생성 → 같은 날 비활성).

## 8. 사용자 승인·추가 결정 (2026-11-09 질문 창)
- **D7 (Q-A) 금액**: "생산팀에겐 가려요" → 완료 보드(PC·태블릿 그리드·모바일 카드·KPI 미수 합계)와 모바일 주문 상세의 품목 금액을 생산팀 계정에서 숨긴다(서버 분기, 값도 안 보냄). 플랜 T1-4 로 추가.
- **D8 (Q-F) 인쇄**: "이번에 같이" → F8 작업지시서 인쇄 포함, 시트 링크 "상세 · 인쇄". 플랜 P4 는 조건부 아님.
- **D9 진행**: "설계 승인, 구현 시작" → 이 워크트리에서 P1 부터 task 단위 구현·시험·커밋. 운영 반영은 따로 묻는다.


## 9. 작업자 시안 넷 (2026-11-09, 사용자 요청 "지금 구현된 태블릿 UI 말고 작업자 persona 로 목업 몇 가지 더")

- 파일 `docs/design/mockups/tablet-production-ui-alternatives.html`(612줄, 자급자족, 가짜 데이터). Artifact https://claude.ai/artifact/MD4PMbNiiKwF7mfuZLfuwk (비공개, Version 1). 색·글꼴·틀 축소 방식은 앞 시안과 같은 토큰.
- 안 1 **오늘 할 일**: 시공일 순 큰 카드 한 줄(118px×5), 공정 5칸을 카드 안에, 바뀐 주문은 붉은 띠 + 한 줄. 레일·KPI·칸반 없음. 데이터는 칸반 목록 + steps GET + 변경 알림.
- 안 2 **도면 먼저 작업 화면**: 전체 화면, 도면 6할(넘기기 72px·썸네일·PDF) + 고객(전화·주소·실측·출고)·만들 것·공정 5줄(누가 몇 시)·불량/보류·제작 완료(검수 전 회색)·위 막대 [인쇄]. 설계서 F2·F3 내용과 같고 배치만 다름. 시트 라우트 뷰 모델 2키 + 템플릿 1장.
- 안 3 **내 공정 줄**: 공정 5탭(사람마다 저장), 그 공정에 와 있는 줄 + 아직 앞 공정인 것 흐리게, 오른쪽 [엣지 끝] 96px·불량·보류·다음 사람. 단위는 공정마다 다름(재단·엣지 판 장수, 도장 면·색, 조립 장, 검수 품목). 판 장수는 ERP 에 없음.
- 안 4 **일정과 바뀐 것**: 요일 6칸에 출고·시공, 오른쪽 받은함(변경 4종 + 품목 취소) 사람마다 [확인했어요]. 브리핑 모달 대신 상시 받은함. 쓰기는 ACK 하나.
- 승인된 설계서와 관계: 설계서 = 기존 레일+시트를 생산팀이 쓸 수 있게, 넷 = 생산팀 전용 첫 화면. 함께 갈 수 있음(레일 생산 탭이 연다). 안 2 가 셋의 공통 바닥.
- 묻는 것: Q-G 공장 사람 유형(주문 단위 / 공정 단위 / 섞임) → 안 1 과 안 3 중 첫 화면 · Q-H 판 장수 데이터(도면팀 입력 / 품목 수로 시작) · Q-I 첫 화면 구성(한 장 / 할 일+이번 주 탭 둘 / 설계서대로만).
- 사용자 답(11-09, 질문 창): Q-G·Q-I → **"첫 화면은 전체 주문을 볼 수 있게"** = D10. Q-H → **"일의 양은 안 보여도 돼요"** = D11.
- 반영: 안 1 을 "전체 주문 — 시공일 순 한 줄"로 고침(날짜 머리줄, 왼쪽 큰 글자 = 지금 단계 "엣지 중/도면 기다림/시공 중", 위 세 칸 전체/생산 중/바뀐 것 + 찾기, 카드 100px). 안 3 줄에서 판 장수 칸 삭제. 안 2 돌아가기 글 "전체 주문". 고르기 절에 D10·D11 기록. Artifact Version 2(같은 URL).
- 아직 안 정한 것: 안 3·안 4 를 첫 화면 탭으로 둘지 레일에서만 열지 · 승인된 설계서(레일+시트 P1~P4)와 이 첫 화면의 구현 순서.

### 8.1 추가 결정(11-09, 작업자 시안 뒤)
- **D10** 생산팀 첫 화면 = 전체 주문 한 줄(시공일 순, 단계 표시). 오늘만/내 공정만이 아님.
- **D11** 일의 양(판 장수 등 ERP 에 없는 값)은 보이지 않음. 새 입력 칸 없음.
- **D12** (11-09 질문 창) "첫 화면으로 바꿔 바로 구현": 설계서에 생산팀 전용 첫 화면(안 1 전체 주문 한 줄) + 전체 화면 작업 시트(안 2)를 넣고, P1 착지를 이 화면으로 바꿔 구현 시작. 기존 레일·옆 시트 고치기(금액 가림·403 문구·인쇄 등)는 그 뒤 이어서.
- **D13** (11-09 질문 창) 안 3(내 공정 줄)·안 4(일정과 바뀐 것)는 첫 화면 위 탭 "전체 주문 | 이번 주 | 내 공정"으로. 레일은 생산팀에겐 뒤로.

## 10. 구현 진행 (P0 — 설계서 §12)

- **T0-1 DONE (2026-11-09)** 생산 홈 `GET /erp/production/home` + 착지(기기 무관). 새 파일: `foms/services/production_home_read_model.py`, `foms/web/production/home.py`(dashboard.py 가 501줄로 500줄 래칫에 걸려 같은 Blueprint 에 라우트만 분리), `templates/production/home.html`, `static/css/contexts/production/home.css`, `static/js/production/foms-production-home.js`(77줄), `tests/domains/test_production_home.py`(6). 고친 파일: `production_read_model.py`(`stage_codes` kwarg), `production_dashboard_display.py`(`build_production_home_enriched_rows`), `post_auth_navigation.py`(`is_production_home_user`·`production_home_url`, legacy `/` 분기), `orders/listing.py`, `auth/routes.py`(switch_user), `test_post_auth_navigation.py`(+4), `docs/harness/foms_failopen_inventory.json`(routes.py 줄 번호만).
- 검증: `APP_OK` · 새 시험 10 초록 · 바뀐 모듈에 닿는 시험 784 + 래칫·write-guard·프리랜서 문지기·REV-99·namespace 초록(visual 스위트는 file-backed sqlite 필요 — 환경 사유로 제외). 실화면(로컬 렌더 → Playwright): 1280×800 터치(레일 + 카드 100px 4칸), 800×1280 터치(모바일 셸 + 카드 두 줄), 1440×900 PC(상단 메뉴 + 같은 목록) 모두 설계대로. 세로 하단 탭에 생산이 없는 것은 T1-3 그대로.
- 알게 된 것: 시공팀 계정은 전역 문지기가 먼저 302(출고 화면)라 403 단언이 아니라 "200 아님"으로 둠 · `Order` 시드엔 `received_date`·`product`·`manager_name` 이 있어야 안전 · `g.current_user` 가 같은 사람이면 착지 판정이 추가 쿼리 0.
- 다음: T0-2 전체 화면 작업 시트(`/erp/production/sheet/<id>`), 카드 링크 교체.
- 첫 시안(`tablet-production-ui.html`)의 D7·D8 전 글("아직 정하지 않았어요"·"묻고 싶은 것" 2문항·F2 링크 "상세")을 결정으로 고치고 Artifact Version 2 로 재발행(같은 URL). T0-1 코드 커밋 `676c9d8cc`.
- **T0-1b DONE (11-09)** 사용자 지시 "날짜별로 접었다 펼 수 있게 like 모바일 실측 탭" → 실측 탭(`measurement/partials/mobile_list.html`·`mobile-glance-tabs.js`)의 말 그대로: 머리줄 단추 `aria-expanded`·`is-closed`·꺾쇠 회전·[모두 펼치기/접기]·펼침 수. 처음엔 오늘·내일만 펼침(실측 탭은 전부 접지만 생산은 오늘 일이 바로 보여야 해서 둘만 펼침 — 설계자 판단). 거르면 맞는 묶음 자동 펼침. 로컬 Playwright 로 접기·모두 펼치기·탭 전환 확인(5→0→1 접힘, 생산 중 탭에서 묶음 4 숨김·줄 4). 시험 25 초록.
- **T0-2 DONE (11-09)** 전체 화면 작업 시트 `GET /erp/production/sheet/<id>`(`foms/web/production/home.py`). 뷰 모델은 새 서비스 `foms/services/production_sheet_view.py` 로 옮긴 옆 시트 헬퍼(`_prod_sheet_*` 이름 그대로, dashboard.py 346줄로 줄어듦) + `full=True` 키(전화·주소·실측/시공·시공팀·도면 전체(이미지/파일)·공정 5줄 누가·몇 시·최근 불량). 템플릿 `templates/production/sheet.html`, CSS `static/css/contexts/production/sheet.css`, JS `static/js/production/foms-production-sheet-page.js`(도면 넘기기·전역 뷰어·공정 체크 POST·불량 칩 POST, 실패 글 §8 한 가지). 단추는 옆 시트와 같은 `data-tablet-sheet-action` 계약 — `tablet-domain-sheets.js` 의 document 클릭 게이트에 `[data-foms-prod-sheet-page]` 안이면 코호트 무관 1줄, 핀 20260921a→20261109a(칸반·출고 CHAIN·계약 시험 상수 함께). 홈 카드 링크를 이 라우트로. 글 "생산 완료"→"제작 완료"(이 페이지만). 가로 태블릿은 본문 높이를 화면에 맞추고 오른쪽만 스크롤(도면 늘 보임).
- 검증: 새 시험 6(`test_production_sheet_page.py`: 도면 2+PDF 1·tel·지도·시공팀·공정 5·불량 4·단추·금액 0·쿼리 ≤14·옆 시트 불변·인라인 0) + 관련 1,013 초록. 로컬 Playwright: 다음 도면 → "도면 2 / 2", 불량 칩 4 펼침, 서버 없이 공정 체크 → "연결이 끊겼어요…" 글. 1280×800·800×1280·1440×900 실화면 설계대로.
- 미룸: [인쇄] 링크는 T4-1 라우트 뒤 · "제작 완료"는 공정 5/5 전에도 눌림(옆 시트와 같음 — 막는 건 새 규칙이라 넣지 않음, 시안 글과 다름) · 세로 하단 탭 "생산" 없음은 T1-3.
- 다음: T0-3 탭 "이번 주"(안 4), T0-4 탭 "내 공정"(안 3).

## 11. 스테이징 반영 (2026-11-09, 사용자 선택 "스테이징에 올려 탭으로 먼저 보기")

- origin/deploy 가 그 사이 6커밋 앞서 있어 `session_worktree.py sync` 로 리베이스(AI_STATUS 충돌 2회 — 상류 판 + 이 세션 줄, 40줄 예산이 3,985/4,000 이라 가장 오래된 진행 중 줄(2026-09-29 할 일 묶음)을 '2026-09-08 상단 정리' 보관으로 내림). 두 번째 sync 는 ledger 밖 커밋이라 refuse → `--allow-foreign`(이 세션 커밋 확인 뒤).
- smoke 1차 FAIL: `test_state_guard` — `listing.py` 착지 3줄로 상태 쓰기 목록 줄 번호(371·372→374·375)만 밀림, `refresh_inventories` 는 안 잡아 `state_writer_scan.py` 직접 실행 → chore 커밋. smoke 2차 PASS(17,113 passed · 776 skipped · 3분 24초).
- 푸시: `deploy` 1880ce572 → **a680a3d07**(이 세션 커밋 5: 366b76cb0 T0-1 · 75bd1beef 문서 · 7e3030bdf 날짜 접기 · d9e04a67f T0-2 · a680a3d07 chore). 운영 반영 없음. CI·Railway 배포 확인은 아래 줄에.
- 배포 확인: `check_deploy_drift` staging a680a3d0 SUCCESS. 스테이징 실화면(관리자 쿠키, 1280×800 터치, Playwright `staging_home_check.py`): 홈 200 · 태블릿 마커 ready · 레일 · 날짜 33묶음 · 주문 110 · 가로 스크롤 없음 · 4xx 0 · JS 오류 0. 첫 카드 → 시트 200(공정 5·칩 4·tel·보류 단추, 도면 기다림 주문이라 제작 단추 없음 — 맞음). 세로 800×1280 하단 탭 있음. 긴급 알림 창(`#foms-urgent-alert`)이 화면을 덮어 DOM 에서만 치우고 찍음(읽음 처리 안 함).
- **스테이징 실데이터에서 본 것 ①** 시공일이 139일 지난 "도면 기다림" 주문이 첫 묶음, 33묶음 대부분이 지난 날짜(닫히지 않은 옛 주문). → **D14(설계자, 11-09)**: 시공일이 7일 넘게 지난 주문은 맨 아래 "지난 시공일 (7일 넘음)" 한 묶음(접힘)으로, 일주일 안에 지난 것은 급한 일이라 제자리. `production_home_groups(rows, today)` + 시험 1. ② 스테이징 도면 그림은 깨짐(알려진 스테이징 파일 문제, 코드 아님). ③ 한 주문의 "바뀐 것"이 "시공일 변경 미정 → 미정" 같은 줄을 여러 개 보임 — 알림 데이터 그대로(별건).
- CI: `ci_watch` a680a3d0 deploy **ALL GREEN**(출력 파일의 `CI_WATCH_EXIT=0` 로 확인). D14 묶음 고침은 뒤이어 smoke → deploy 푸시.
- **T0-3·T0-4 DONE (11-09)** 첫 화면 위 탭 셋 "전체 주문 | 이번 주 | 내 공정"(`?tab=all|week|steps`, D13). **이번 주**(안 4): 월~토 요일 칸(일요일은 일이 있을 때만 7칸)에 시공일 기준 주문 — 출고·시공은 같은 날짜 키(상차 = 시공일, 출고 보드도 `extract_all_construction_dates` 로 같은 날짜를 씀)라 한 칸에 단계 색(생산 전/생산 중/제작 완료/바뀐 것)으로 가름, ◀ ▶ 주 넘기기(`?week=월요일`), 오른쪽 받은함 = 미확인 변경(주문마다 한 장) + 취소 주문(묘비, `collect_production_tombstones`), [확인했어요] = 기존 change-ack(`tablet-domain-sheets.js` 게이트 예외를 `[data-foms-prod-home]` 까지, 핀 20261109b 네 곳). **내 공정**(안 3): 공정 5탭(마지막 탭 localStorage `foms-prod-step-tab`), 그 공정이 첫 미완인 제작 중 주문만 줄로(이름·품목·시공일, 일의 양 없음 D11), [<공정> 끝] 72px = POST steps 뒤 새로고침, 보류는 단추 없이 '보류', 제작 대기·검수 끝은 줄 밖 숫자. 파일: `production_home_read_model.py`(`production_home_week`·`production_home_inbox`·`production_home_step_queues`), `home.py`(tab·week), `home.html` + 파셜 3(`home_all/home_week/home_steps.html`), `home.css`, `foms-production-home.js`(190줄).
- 검증: 새 시험 6(`test_production_home_tabs.py`: 요일 칸 배치·묘비 받은함·공정 탭 숫자·보류 단추 없음·tab 값 방어·주 묶음 규칙·게이트·핀 lockstep·인라인 0) + 관련 74 초록. 로컬 Playwright: 엣지 탭 클릭 → 선택·보임·저장, 서버 없이 [끝] → 실패 글. 1280×800·800×1280 설계대로.
- 푸시 2: deploy a680a3d07 → 91e8bd020(D14) → **d271756c9**(T0-3·T0-4). smoke 17,120 PASS. `check_deploy_drift` staging d271756c SUCCESS. 스테이징 실화면: `?tab=week` 200(요일 6칸, 이번 주 일 0 — 옛 데이터, 받은함 30 + [확인했어요] 30), `?tab=steps` 200(재단 3·엣지 0…, 보이는 줄 cut, [끝] 1), 4xx 0·JS 오류 0. CI 는 `ci3.log` 로 감시 중.
- CI: d271756c9 deploy **ALL GREEN**(`ci3.log` `CI_WATCH_EXIT=0`).

### 8.2 추가 결정(11-09 저녁)
- **D15** (사용자, 질문 창) "차례대로 하고. 도장 공정은 우리 공장에 없으니 삭제." → 공정은 **재단·엣지·조립·검수 4단계**. 순서 = 도장 삭제 → P1 → P2·P3 → P4. 옛 주문의 `production.steps` 에 남은 `paint` 항목은 읽을 때 걸러 낸다(저장 데이터 이행 없음, POST 는 모르는 key 거부 그대로).
- **D15 DONE (11-09)** 도장 삭제: `foms/api/production/orders.py` `_PRODUCTION_STEP_DEFS` 4단계 + `_normalize_production_steps`(정의 밖 key 제외·빠진 단계 미완 채움, 새 리스트) 를 GET·POST 응답에, POST 는 옛 목록에 단계가 없으면 추가(StopIteration 방지). 저장 목록·run 스냅샷은 손대지 않음(감사 비교 보존). `mobile_queue.html` "공정 n/5" → n/4(옛 paint 는 세지 않음, 진행바 25%). 첫 화면·시트·탭은 `PRODUCTION_HOME_STEP_DEFS` 4단계라 자연히 걸러짐. CSS 공정 칸 290px·탭 4열. 시험: `test_production_steps_api.py` 4단계 + 옛 paint 숨김·미수정·400 사례, 이 세션 시험 5→4. 시안 그림의 도장 칸은 옛 그림(문서만).
- 푸시 3: deploy d271756c9 → **24292e056**(8e2022e8f D15 도장 삭제 + 24292e056 상태 쓰기 목록 줄 번호 chore — orders.py 줄 이동으로 smoke 1차 FAIL `test_state_guard`, `state_writer_scan.py` 직접 실행 뒤 2차 PASS 17,121). CI `ci4.log` 감시 중.
- CI: 24292e056 deploy **ALL GREEN**(`ci4.log`). 스테이징 `?tab=steps` 공정 4탭 확인.
- **P1 DONE (11-09 저녁)** — T1-1 은 T0-1 이 대신. **T1-2** `fragment-loader.js` 가 HTTP status 를 넘겨 403 이면 "이 주문은 보기만 할 수 있어요." + [상세](`/erp/orders/<id>/mobile`, URL 에서 id), 다시 시도 단추 없음; 핀 20260711b→20261109a(`layout_scripts.html`). `erp_dashboard_tablet_sheet` 문서 진입은 `can_edit_erp` 아니면 모바일 상세로 302. **T1-3** `erp_mobile_shell.html` 생산팀(협력사 아님) 분기: 아래 탭 생산·출고·시공·대시보드, 생산 탭은 생산 홈으로, 생산팀만 `_primary_ids` 순서로 다시 세움(다른 팀 출력 불변 — `-%}` 로 줄바꿈 먹음, `test_freelancer_menus` 초록). **T1-4(D7)** 술어 `can_view_order_amounts(user)`(`erp_permissions.py`, 생산팀만 False, 사용자 없음=가리지 않음) → 완료 보드 `_completion_row(with_amounts)`·KPI 미수 합계 칸·열 3·시트 금액 절·차감 금액·CSV 열 3, 모바일 상세 품목 금액·금액 절(값도 서버에서 뺌). 시험 `test_production_team_p1.py` 10. 관련 401 + t2 계약 초록.
- 다음: P2(옆 시트 전화·주소·링크, 60vh 보정, 레일 배율 단추, 실패 문구) → P3(옆 시트 공정 블록·도면 스트립, 품목 취소 알림) → P4 인쇄.
- 푸시 4: deploy 24292e056 → **44a1459b6**(P1). smoke 17,131 PASS. CI `ci5.log` 감시 중.
- CI(P1 44a1459b6): 시험 워크플로 3개 success, **perf-gate(staging) 1개 failure** — "배포 미완(healthz≠44a1459b)"(Railway 배포 전에 돌아 수렴 실패, `ci_watch` exit 1). 배포 확인 뒤 `gh run rerun 42600335437 --failed` 로 재실행.
- **P2 DONE (11-09 밤)** — **T2-1** 옆 시트(`tablet_sheet.html`) 머리 아래 연락처(전화 글자+[전화] tel:, 주소+[지도] 카카오, 실측·시공·시공팀, [상세] 모바일 상세), 뷰 모델은 `build_production_sheet_view(full=True)`; 단추 글 "생산 완료"→"제작 완료"(`test_production_transition_guard_api` 갱신). **F2 ③·F3(앞당김)** 도면 전달본 전부 스트립(이미지 + PDF "열기"), 뷰어 폴백이 전 장을 넘김. **F2 ②(T3-1 앞당김)** 공정 4칸+불량 칩을 옆 시트 카드로 — 스코프 재작성 대신 전체 화면 시트와 **같은 루트·같은 JS**(`foms-production-sheet-page.js` 를 루트마다 1회 묶고 `foms:erp-shell-fragment-swapped` 때 다시 묶음), id 없음, 칸반 body 가 `sheet.css`·그 JS 를 실음. **T2-2** `foms-tablet-production-kanban.css` 60vh → `calc(60vh / var(--foms-ui-zoom, 1))`, 번들 kanban b·rail g, `layout_head` 번들 g(계약 시험 3곳 리터럴 갱신). **T2-3** `foms_ui_zoom_control.html` 변형 `rail`, `foms_tablet_rail.html` 브랜드 아래 include, `foms-tablet-rail.css` 세로 3단. **T2-4** `tablet-domain-sheets.js` catch 4곳·`foms-production-steps.js` 2곳 → "연결이 끊겼어요. 다시 연결되면 한 번 더 눌러 주세요."(핀 domain-sheets c 네 곳 + 계약 상수, steps js 20261109a). 시험 `test_production_side_sheet_p2.py` 7.
- 푸시 5: deploy 44a1459b6 → **b6473f9c9**(P2). smoke 17,139 PASS. CI `ci6.log` 감시 중, P1 perf-gate 재실행(42600335437) 진행 중.
- **남은 것(컴팩트 뒤 이어서)**: ① b6473f9c9 CI green·`check_deploy_drift` staging 배포 확인 → 스테이징에서 칸반 카드 탭 → 옆 시트에 연락처·공정 4칸·도면 스트립 뜨는지 Playwright 확인(`staging_home_check.py` 꼴, 긴급 알림 창은 DOM 에서 치움) ② perf-gate 재실행 결과(배포 전 타이밍 실패였음) ③ **P3 남은 것 = T3-3 품목 취소 → 생산 변경 알림**(`foms/api/drawing/erp_orders_item_cancel.py` `_mutate` 안 취소 적용 뒤·커밋 전 `apply_production_change_alert(kind="item_cancel", merge=False)` + `production_change.py` `_KIND_LABEL` "품목 취소", 시험 `test_production_change_notification.py`, REV-99 lineno 핀 → `refresh_inventories`/`state_writer_scan.py` 뒤 커밋) ④ **P4 T4-1 인쇄** `GET /erp/production/print/<id>`(새 템플릿 `production/print_sheet.html`, CSS `contexts/production/print.css`, 권한 `_can_edit_production_steps`, 도면 장마다 1쪽, 공정 빈 칸 4) + 시트 두 곳 [인쇄] 링크 ⑤ 운영 반영은 사용자 명시 요청 때만(cherry-pick 승격).
- 스테이징 P2 확인(b6473f9c, CI 4개 모두 green·perf-gate 포함): 생산 칸반 레일에 화면 크기 손잡이 1, 카드 탭 → 옆 시트에 연락처·tel·상세·공정 4칸·불량 칩 4(JS 묶임), 브리핑 목록 max-height 480px(=60vh 보정). 변경 브리핑 창이 카드를 가려 [닫기] 뒤 탭.
- **T3-3 DONE (11-09 밤)** `erp_orders_item_cancel.py` `_mutate` 안 취소 적용 뒤 `apply_production_change_alert(sess, order, "item_cancel", "<품목> 취소 · 사유", merge=False)`(실패해도 취소는 진행), 커밋 뒤 `finalize_production_change_alert`. `_KIND_LABEL["item_cancel"]="품목 취소"`. 품목 이름은 방금 붙은 `cancel.at == at_iso` 로 찾음. 시험 `test_item_cancel_kind_has_label_and_never_merges`(팀 3 × 2 row).
- **T4-1 DONE** `GET /erp/production/print/<id>`(`home.py`, 권한 생산 홈과 같음) → 단독 `production/print_sheet.html`(머리·고객·전화·주소·발주사·실측/시공·시공팀 / 규격 표(취소 품목 제외, 확인 칸) / 특이사항 / 공정 빈 칸 4 / 최종 도면 장마다 1쪽, PDF 는 글로만), CSS `contexts/production/print.css`(@page A4, 화면은 종이 모양 미리보기), JS `foms-production-print.js`(8줄, [인쇄]·`?auto=1`). 시트 두 곳에 [인쇄](새 탭). 시험 `test_production_print_sheet.py` 4. 뷰 모델에 `orderer_name`.
- 푸시 6: deploy b6473f9c9 → **9585e17b1**(T3-3·T4-1). smoke 17,145 PASS. CI `ci7.log` 감시 중. **설계서 P0~P4 전부 스테이징 반영.** 운영 반영은 사용자 명시 요청 때 이 세션 커밋만 cherry-pick 승격(`promote_own_to_production.py`).
- 스테이징 확인(9585e17b 배포 SUCCESS): 전체 화면 시트에 [인쇄] 링크 1, `/erp/production/print/<id>` 200(도면 없는 주문이라 1쪽). CI 는 `ci7.log`. **다음은 사용자 선택: 갤럭시 탭 실기기 검수 → 운영 승격(cherry-pick) 또는 고칠 것.**
- CI(9585e17b1) **ALL GREEN**(`ci7.log`). 사용자 선택(11-09 밤): **여기서 멈추고 검토** — 세션 종료. 재개 시 이 원장 §8.1~§11 + 설계서 §12 + 메모리로.

## 12. 운영 반영·실측 (2026-11-09 밤, 사용자 "운영에 올리고 마스터계정으로 실측해봐 실제 데이터로")
- 승격: 이 세션 커밋 15개(366b76cb0~9585e17b1 + chore a680a3d07, 원장 커밋 2개는 deploy 에만) `promote_own_to_production.py --shas --allow-incomplete`(완전성 판정은 문서·핀·시험 차이만이라 거짓 양성, 파일 내용 대조 40 같음·34 새 파일·5 다름). 충돌: `test_post_auth_navigation.py` 1곳(운영 판 + 착지 시험 2개만 더함), `AI_STATUS.md` 5회(운영 쪽 유지). 인벤토리 3종 승격 트리에서 재생성 → 변화 없음. APP_OK · 관련 시험 621 · smoke **17,136 passed**(3분 55초).
- PR #784 → 검사 4개 모두 성공(test 5분 59초 · pg-lane · harness · perf-gate) → 머지 **production 87aa0ec42** → healthz 20:43 그 커밋(Railway 배포 확인). `check_deploy_drift` 는 로컬 ref 가 낡아 "1f8434b2 — 0커밋 뒤" 라 했지만 healthz 가 정본.
- 운영 실측(claude_master id 57, 잠금 해제 → 측정 → 재잠금 확인 `is_active=False`, 읽기만·직렬·로그아웃 302): 로그인 302, 홈 all/week/steps 200(TTFB 539·419·331ms), 전체 화면 시트 200(공정 4·칩 4·tel·[인쇄]·보류 단추, 금액 글 없음), 인쇄 200(1쪽, 도장 없음), 옆 시트 조각 200(공정 4·인쇄 링크), 칸반 200, 세로 하단 탭 있음, 4xx 0 · JS 오류 0. PNG 는 스크래치패드 `shots/prod_home/` 에만(실제 고객 정보).
- **운영 실데이터에서 본 결함 ④ (고침)**: 첫 화면이 "지난 시공일 300건" 한 묶음 · 날짜 1 · 이번 주 0 · 내 공정 0. 원인 = `PRODUCTION_KANBAN_MAX_ROWS` 300 캡을 **시공일 오름차순**으로 잘라 옛 미종결 주문(300+)만 남고 최근·앞날이 통째로 빠짐(스테이징은 110건이라 안 드러남). 고침 `build_production_home`: 7일 안·앞날·미정은 전부, 지난 것은 최근부터 남는 자리만, 밀린 수는 머리줄 "더 오래된 N건은 안 보여요"(`past_hidden`). 시험 1(캡 3). 커밋은 deploy 에(아래 푸시 7). **운영 재승격은 사용자 지시 때.**
- 푸시 7: deploy ceacbd52b → **6a6e6d2c5**(원장 커밋 2 + 캡 고침 567d7fbcf + §12 기록). smoke 17,150 PASS · CI ALL GREEN(`ci8.log`) · 스테이징 healthz 6a6e6d2c 뒤 실화면 홈 200 · 주문 110 · 4xx 0 · JS 0.
- **캡 고침 운영 재승격(사용자 "캡 고침도 운영에 올리기")**: 567d7fbcf 하나만 `origin/production` 위 손 cherry-pick(바탕 3파일 md5 운영과 같음) → APP_OK · 홈 시험 26 · smoke **17,137 PASS** → PR #785(검사 4개 성공) → 머지 **production 8c361144a** → healthz 21:51 그 커밋, `check_deploy_drift` 일치 SUCCESS. 운영 첫 화면 재실측은 안 함(계정 잠김 유지, 사용자 지시 때 1회).
- **운영 첫 화면 재실측(사용자 지시 1회, 8c361144a 뒤, 잠금 해제 → 홈 세 탭만 읽기 → 재잠금 확인)**: 전체 탭 날짜 묶음 28(첫 묶음 11/2 월 = 7일 안), 주문 300 = 최근·앞날 215 + 지난 85, 지난 묶음 머리줄 "더 오래된 231건은 안 보여요", 전체 300 · 생산 중 52 · 바뀐 것 214. 이번 주 탭 시트 링크 73(고침 전 0), 내 공정 탭 3(고침 전 0). TTFB 539·694·358ms, 4xx 0 · JS 0, 로그아웃 302. **결함 ④ 운영에서 닫힘.** 알아둘 것: 머리 숫자 "전체 300" 은 읽은 행 수(실제 531)라 캡에 걸리면 총계가 아니다 — 필요하면 count 를 머리에(미룸).
- 다음(사용자 선택): 갤럭시 탭 실기기 검수 → 생산팀 운영 계정 만들기(사용자) → 미룸 목록(플랜 "뒤로 미룸").

## 13. 시공 탭 (2026-11-10, 사용자 요청 "태블릿 시공 탭 > ① 글자 크기 조절 ② 이유 없이 빈 공간 없이 ③ 첫 화면은 날짜별로 시공을 한눈에 — 사용자 persona 로 목업")
- 지금 화면(스테이징 실화면 1280×800 터치, `scratchpad/staging_cons_shot.py`): `/erp/construction/dashboard` 가 태블릿 가로면 `tablet_workmode_body.html` 3분할 — 왼쪽 "오늘 시공" 300px(칩 오늘·내일·주간·전체) · 가운데 도면 뷰어 500px · 오른쪽 "작업 확인" 320px, 각 칸 `100dvh` 고정. 오늘 0건이면 세 칸이 전부 빈 글("오늘 시공 일정이 없습니다 / 선택된 시공 건이 없습니다 / 작업 확인")이라 화면 전체가 빈 공간(②). 주간·전체 칩을 눌러도 날짜 머리줄이 없어 어느 날인지 안 보임(③). 제목 줄이 없어 다른 탭의 "글자 − 100% +"(`foms_font_scale_control.html`, `FS_TABS` 에 `/erp/construction` 은 이미 있음) 가 안 붙음(①) — 레일의 −/100%/+ 는 화면 전체 배율이라 다른 것. 세로는 폰 화면(카드 목록, 하단 탭) 그대로.
- 시안 셋 `docs/design/mockups/tablet-construction-tab.html` + Artifact https://claude.ai/artifact/D9VTecyDjrfvVwnm3DiAbC (지어낸 이름·주소만). 셋 다 제목 줄에 글자 손잡이·전체/1팀/2팀 칸·[다시 받기], 집 한 줄을 누르면 지금 작업 화면(도면·전화·내비·시공 시작·완료 사진·서명)이 그대로 열림(그 화면은 안 바꿈).
  - **안 1 날짜별 한 줄**: 날짜 머리줄(오늘 펼침, 접기·펴기 = 실측 탭·생산 홈) 아래 시간 순 72px 줄(시간 · 이름·품목 · 구 이름 크게+주소 · 팀·출고·도면 · [열기]). 없는 날은 점선 한 줄, 먼 날·날짜 없음은 접힘 → 빈 칸 없음. 생산 홈 날짜 묶음 코드 재사용.
  - **안 2 두 주 달력판**: 월~일 × 2주 격자, 칸 안 색 띠 = 팀, 오늘 칸 굵은 테두리, ◀ ▶ 2주 넘기기, 아래 범례 + 날짜 없음·지난 2주 끝난 것. 단점 솔직히 적음: 없는 날 칸은 비어 보임(정보이긴 함).
  - **안 3 오늘 크게 + 날짜 띠**: 왼쪽 오늘 큰 카드(전화·내비·열기) + 그 아래 "내일" 작은 줄, 오른쪽 앞으로 2주 날짜 띠(없는 날 44px 한 줄). 오늘 0건이면 "다음 시공" 카드가 올라와 비지 않음.
- 로컬 렌더(`scratchpad/shot_cons_mock.py`, Playwright file://): 세 틀 1280×800 안에서 넘치는 요소 0.
- **D16 (사용자, 11-10)** 시공팀은 1팀·2팀처럼 나뉘어 나간다 → 시공 첫 화면에 팀 칸(전체/1팀/2팀) 넣기. 첫 화면 모양(안 1·2·3)은 **보류**("이건 놔두고") — 출고 탭 시안 뒤에 같이 고름.
- 다음: 시공 첫 화면 모양 선택 → 설계서 §13 → 구현(T5-1 제목 줄+글자 손잡이 → T5-2 첫 화면 → T5-3 작업 화면을 "주문 하나" 모드로).

## 14. 출고 탭 — 생산팀 첫 화면 (2026-11-10, 사용자 "출고 탭도 생산팀 persona 로 첫 화면 대시보드 목업")
- 지금 화면(스테이징 실화면 `scratchpad/staging_ship_shot.py`): `/erp/shipment` 태블릿 가로 = 관리자 배정 판 — 제목 줄(날짜 고르기·검색·40/48/56·AS 추천·출고 확정), KPI 네 칸(총 자수·건수·시공팀·미배정), 왼쪽 14일 목록(잔여 자수 0.0/190), 오른쪽 `tablet_ship_grid.html` 표(시공일·고객·발주사·제품·자수·도면담당, 행 탭 = 배정 시트). 글자 손잡이 없음. 포장(`foms-packing.js` B6)·상차 완료→출발 보고(P6)는 세로 폰 카드에만 있고 가로엔 없음. 0건이면 표에 "데이터가 없습니다" + KPI 0 네 칸.
- 생산팀이 출고에서 하는 일 = 포장 체크 + 상차 완료(출발 보고). 배정은 관리자 일이라 첫 화면에서 뺌(권한으로 가름: 생산팀 계정만 새 첫 화면, 관리자·출고 담당은 지금 화면 그대로).
- 시안 셋 `docs/design/mockups/tablet-shipment-tab.html` + Artifact https://claude.ai/artifact/RGqce6utfL5ZkGK2f2ivcB (지어낸 이름·주소만) — 셋 다 제목 줄 글자 손잡이·빈 칸 없음·날짜별·금액 없음, 단추는 [포장]=패킹 바텀시트·[상차 완료]=출발 보고 그대로, 자수는 출고판 값(W÷300 합) 그대로.
  - **안 1 오늘 상차판**: 위 날짜 띠(14일, 건수·자수) → 그날을 시공팀(차)별 칸으로, 카드마다 포장 막대 + [포장]·[상차 완료](포장 끝나야 초록), 누락 칩(미입고·파손·수량 부족), 미배정은 오른쪽 좁은 칸, 아래 줄 오늘 5건·자수·포장 끝·상차 완료.
  - **안 2 날짜별 한 줄(출고판)**: 생산 홈·시공 안 1 과 같은 날짜 머리줄(접기·펴기, 오른쪽 자수/용량 막대), 안에서 팀(차) 작은 머리줄, 줄 맨 왼쪽 큰 숫자 = 자수, 위 세 칸 전체/포장 남음/누락.
  - **안 3 2주 자수 한눈에 + 그날 목록**: 지금 틀(왼쪽 날짜·오른쪽 그날)을 살려 왼쪽 14줄을 자수/용량 막대(넘치면 붉게)로, 오른쪽은 배정 표 대신 포장·상차 목록, KPI 네 칸은 제목 줄 한 줄로.
- 로컬 렌더 `scratchpad/shot_ship_mock.py`: 안 3 오른쪽 줄 가로 넘침 8 → `minmax(0,1fr)`+`min-width:0`, 왼쪽 줄 50→48px 로 고침 뒤 0.
- 다음: 사용자 선택(출고 안 1·2·3, 자수/용량 막대를 생산팀에게도 보일지, 상차 완료 = 출발 보고 그대로인지) + 시공 첫 화면 선택 → 설계서 §13·§14 → 구현.

## 15. 생산 첫 화면 다시 그리기 (2026-11-10, 사용자 "계속 잘못 말하고 있는데, 가장 최우선 과제는 생산이야. 생산팀 persona 로 목업 만들어 봐")
- **D17 (사용자)** 최우선은 **생산** 화면. 앞서 말한 세 가지(① 글자 크기 조절 ② 이유 없는 빈 공간 없이 ③ 첫 화면은 날짜별로 시공을 한눈에)는 생산 첫 화면에 먼저 적용한다. 시공 탭(§13)·출고 탭(§14) 시안은 생산 뒤로 미룸(선택 보류 그대로).
- 지금 생산 첫 화면에서 본 것(운영 재실측 화면, 11-09): 접힌 날짜 머리줄 28개가 64px 씩 서서 첫 화면이 거의 빈 줄, 오늘 묶음은 지난 6줄 아래, 글자 손잡이 없음(`home.html` 에 `foms_font_scale_control` 미포함 — 생산 칸반 `dashboard_body.html` 에만), "내 공정" 3줄 아래 전부 빈 화면, "이번 주" 카드는 이름만·"도면 기다…" 잘림. 읽은 300건 중 생산팀이 손댈 것(제작 대기+생산 중)은 52건, 나머지 대부분 도면 기다림(하루 12~16건 중 9~12건).
- 시안 셋 `docs/design/mockups/tablet-production-home-v2.html` + Artifact https://claude.ai/artifact/V8gZG9Nw47F8co9LCbDfcs (지어낸 이름만). 공통: 제목 줄 글자 손잡이, 접는 줄 없음, 생산팀 것(제작 대기·만드는 중·제작 완료)은 공정 4칸과 크게·도면 기다림은 작게(D10 전체 주문은 유지), 집을 누르면 지금 작업 시트.
  - **안 1 날짜 띠**: 시공일 하루 = 가로 한 줄(92px). 왼쪽 날짜 칸(오늘 파랑, 만들 것 n · 기다림 n) → 만들 것 카드(공정 4칸) → 줄 끝 남는 자리에 도면 기다림 이름. 없는 날 점선 한 줄, 다음 주 한 줄 요약, 지난 시공일·시공일 없음은 위 알약. 처음엔 세로 요일 칸판으로 그렸다가 일이 적은 날 칸 가운데가 비어(②에 어긋남) 가로 줄로 바꿈.
  - **안 2 날짜 기둥 + 빽빽한 줄**: 지금 줄 목록을 접지 않고 왼쪽 날짜 기둥 + 줄 50px(한 화면 11줄), 도면 기다림은 날짜마다 점선 한 줄. 가장 적게 바뀌고 가장 빠름.
  - **안 3 2주 띠 + 그날**: 왼쪽 13일 색 막대(완료·만드는 중·대기·도면 기다림)와 "만들 것 / 전체", 오른쪽 고른 날 큰 줄 + 도면 기다림 세 칸 격자 + 내일 미리 보기.
- 로컬 렌더 `scratchpad/shot_prod2_mock.py`: 세 틀 넘침 0(안 2 줄 52→50px 로 맞춤).
- 같이 고칠 것(시안 글에 적음): "내 공정" 빈 화면, 머리 숫자 "전체 300" → 실제 총계.
- **D18 (사용자, 11-10) "3안으로"** — 생산 첫 화면 = 안 3(2주 띠 + 그날). 도면 기다림을 작게 두는 것도 안 3 그대로.
- **P5 DONE (11-10)** 설계서 §12.3 고침 · 플랜 P5.
  - T6-1 글자: `home.html` 제목 줄에 `foms_font_scale_control.html`(열쇠 `/erp/production` 은 `FS_TABS` 에 이미 있음). `home.css` 54곳 · `sheet.css` 45곳 px 글자 → `calc(Npx * var(--foms-fs, 1))`(sheet.css 핀 20261110a, 칸반 body·sheet.html·시험 리터럴 lockstep). 띠 너비 `min(42%, calc(316px * fs))`, 띠 칸도 배율, 띠 sticky 위치는 `--fph-bar-h`(JS 가 제목 줄 높이를 잼 — 줄이 접혀도 안 겹침).
  - T6-2 날짜 탭: `production_home_days`(지난 7일 · 오늘+10일 · 그 뒤 = 13줄, 아래 지난 시공일·시공일 없음 → 장 15개, 막대는 SVG x/width, 만들 것 순서 = 바뀐 것 → 만드는 중(공정 많이 간 것) → 제작 대기, 미리 보기 = 뒤로 만들 것이 있는 첫 날 6줄까지). `home.py` 탭 `date|steps|changes|all`(기본 date, 옛 `week` 는 date 로), `?day=`. `home_date.html`(큰 줄 `fph-dr` · 작은 칸 `fph-wi`), JS 날 고르기(보이기/숨기기 + 주소·[다시 받기] 갱신, 209줄).
  - T6-3: "이번 주" 탭 삭제(`home_week.html`·`production_home_week`) → 받은함은 `home_changes.html` "바뀐 것" 탭(2열), 내 공정 줄 아래 "곧 올 것"(`incoming` = 앞 공정 줄에서 보류 뺀 것, 재단은 제작 대기), 머리 "전체 N건" = `stats['total']`(실제 총계). "전체 주문" 줄 목록은 탭 "찾기"(`?tab=all`).
  - 검증: 새·고친 시험(`test_production_home_tabs.py` 8 · `test_production_home.py`) + 생산·태블릿 계약 618 초록. 로컬 렌더(`scratchpad/shot_home_v3.py`, 시드 111건): 1280×800 터치 띠 316×713 · 가로 넘침 없음 · 날 고르기 · 글자 130%(띠 411px, 겹침 없음) · 800×1280(띠 가로 흐름) · 작업 시트 글자 100/130/150% 넘침 없음.
- 푸시 8: deploy a22c13cc5 → **2aa413f2f**(197b14c1a P5 구현 + 문서). smoke 17,160 PASS. 스테이징(healthz 2aa413f2 뒤, `scratchpad/staging_home_v3_check.py`, 관리자 쿠키 1280×800 터치): 날짜 탭 200 · 띠 15칸 · 글자 [+] 두 번 → 120%(띠 316→379px, 가로 넘침 없음) → 100% 되돌림 · 내 공정 재단 3 + 곧 올 것 2 · 바뀐 것 30 · 찾기 110줄 · 세로 OK · 4xx 0 · JS 0.
- **스테이징 실데이터에서 본 것 ⑤ (고침)**: 스테이징은 앞날 주문이 없어(95건 지난 시공일 · 15건 시공일 없음) 띠 13줄이 전부 0 / 0, 첫 장이 "오늘 · 이 날은 시공이 없어요" 빈 화면. → 처음 여는 장은 오늘이 비었으면 일이 있는 가장 가까운 장(오늘 뒤 → 그 뒤 → 지난 7일 → 지난 시공일 → 시공일 없음). 직접 고른 날(`?day=`)은 비어도 그대로. 시험 6줄.
- 푸시 9: deploy 2aa413f2f → **d3cf1652d**(빈 첫 화면 고침). smoke 17,160 PASS · CI 초록(`ci_watch` target d3cf1652). 스테이징(healthz d3cf1652 뒤) 재확인: 처음 열린 장 `past`(지난 시공일 95건 · 만들 것 4) · 글자 120% 가로 넘침 없음 · 내 공정 재단 3 + 곧 올 것 2 · 세로 큰 줄 4 / 작은 칸 91 · 4xx 0 · JS 0.
- 다음: 운영 승격은 사용자 지시 때(대상 197b14c1a · d3cf1652d, 문서 커밋은 AI_STATUS `--ours`). 시공 탭(§13)·출고 탭(§14) 모양 선택은 보류 그대로.

## 16. 운영 승격 3차 · 워커 리뷰 (2026-11-10, 사용자 "운영에 올리고 실측" → "지휘는 니가 하고 워커들은 opus, effort 는 니가 분배해")
- 승격 가지 `promote/tablet-home-v3`(origin/production f152e47af 위, 이 세션 커밋 12개 = 코드 197b14c1a · d3cf1652d + 문서 10개, `AI_STATUS.md` 4회 `--ours`). 파일 내용 대조: 코드 15개 모두 운영 = 내 바탕, 새 파일 5. 인벤토리 scan 3종 변화 없음 · APP_OK · 생산 홈 시험 39 · smoke 17,147 PASS → **PR #791**, 검사 4개(test · pg-lane · harness · perf-gate) 통과.
- 워커 배치(opus): ① 코드 리뷰(노력 높음, 읽기 전용) ② 스테이징 작업 시트 글자 100·120·150% 실화면(노력 중간, 읽기 전용). 합치기는 두 보고를 총괄이 직접 확인한 뒤.
- **리뷰 finding 전량(워커 ①, 받은 즉시 기록). 운영 반영을 막는 것 없음(워커 판정) — R1·R2·R3 은 총괄이 코드로 다시 확인.**
  - **R1** `production_home_read_model.py` `production_home_counts.making` vs 공정 줄: run 없는 보류(제작 대기 보류 · 도면 단계 보류)는 `now` 가 없어 탭 숫자에서 빠지는데 보류 갈래가 재단 줄에 넣는다 → 탭 1 · 재단 3. `production_home_stage` 가 보류면 단계와 상관없이 `prod` 라 도면 단계 보류가 "만들 것" 큰 줄·재단 줄에 선다. (돌려서 확인) → 고침: 탭 숫자 = 공정 줄 합, 보류 갈래는 생산 단계일 때만.
  - **R2** `home.html` · `home.py`: "바뀐 것" 탭 숫자에 취소 주문(묘비)이 안 든다 — 묘비 쿼리가 changes 탭에서만 돈다. 첫 화면엔 "바뀐 것 0", 묘비는 탭을 열어야 보임. (돌려서 확인) → 고침: 묘비를 모든 탭에서 세어 숫자에 더함(쿼리 1회).
  - **R3** `home.html` [다시 받기] 주소가 자동으로 고른 장을 굳힌다: 자동 `recent` → `?day=recent` 로 박혀 다음 날 오늘 주문이 생겨도 지난 7일이 열림. 반대로 `?day=<오늘>` 을 직접 연 뒤 오늘이 비면 day 가 빠져 다른 날로 튐. (돌려서 확인) → 고침: `production_home_days` 가 `auto` 를 돌려주고 템플릿은 직접 고른 값만 붙임.
  - **R4** `home_date.html` "도면 기다림 n" 에 컨펌 기다림이 섞임(`wait_rows` = 도면·컨펌·알 수 없는 단계). (돌려서 확인) → 글자를 "도면·컨펌 기다림" 으로.
  - **R5** 지난 시공일 장: 살아 있는 주문이 캡을 다 채우면 단추 "지난 시공일 0건" + "이 날은 시공이 없어요" + "더 오래된 200건은 안 보여요" 가 같이 나옴. 단추 숫자는 읽은 수뿐. (돌려서 확인) → `note` 가 있으면 '없어요' 숨김, 단추에 안 읽은 수 같이.
  - **R6** 장 나누기는 `structured_data.schedule.construction.date`, 캡 나누기는 `Order.erp_construction_date` 열 — 둘이 어긋난 옛 데이터(직접 SQL 로 고친 것)에서만 장이 달라짐. (공간 있을 때는 돌려서 확인, 캡 찼을 때는 추정) → **미룸**(저장 때 `sync_erp_flat_columns` 가 맞춤).
  - **R7** `sheet.html` 뒤로 단추 글자가 "전체 주문" 이고 고른 날을 잃음(홈 자동 장으로 감). (추정) → 글자 바꾸고 들어온 홈 주소로 돌아가게.
  - **R8** 칸 폭은 고정인데 글자만 커짐: `.fph-dr` 의 도면 칸 92px(150% 에서 "도면 12장" 잘림), `.fph-qr` 시공일 칸 150px(두 줄), `sheet.css` 도면 파일 칸 112×80. (추정 — 글자 폭 어림) → 워커 ② 실화면 결과와 묶어 판정.
  - **R9** `home.css` 죽은 선택자 `.fph-inbox__h`(지운 `home_week.html` 전용, 참조 0). → 두 줄 삭제.
  - **R10** 시험 빈 곳: R1 탭 숫자=줄 수, R2 묘비 숫자, R3 다시 받기 `href`, R5 `past_hidden>0` + 읽은 지난 주문 0, 라우트에서 캡 넘칠 때 "전체 N건"·안내 글, 날짜 탭 줄 클래스 `is-w/is-f/is-p` 와 막대 색 짝.
  - **R11** JS `history.replaceState(null, …)` 가 global-nav 가 넣은 `{gnav}` 기록 값을 지움(뒤로 가기 때 다시 읽기로 넘어갈 뿐, 영향 작음, 추정) → `history.state` 를 넘김.
  - 워커가 확인하고 괜찮았던 것: 330건 시드에서 띠·단추 합 300(=캡) · "전체 330건" · 안 보임 30 일치, 탭별 쿼리 9·9·10·9회(행 수와 무관, N+1 없음), 날짜 탭 HTML 약 260KB(330건), 날짜 경계(지난 7일 = 오늘-7~오늘-1, 그 뒤 = 오늘+11~, 전부 KST), 빈 목록·이상한 날짜 예외 없음, `?day=`·`?tab=` 이상한 값 200 + 아는 열쇠로, 협력사 403, CSS 133곳 문법(괄호·중첩 calc·다른 속성 변화 없음, 남은 px 글자 0), `node --check`, 지운 것의 남은 참조 0, 핀 `20261110a` 일치, 인라인 style 없음.
- **실화면 finding 전량(워커 ②, 스테이징 d3cf1652d, 주문 둘 = 제작중·제작대기, 쓰기 단추 안 누름, JS 오류 0 · 4xx 0).** 전체 화면 시트는 태블릿 가로·세로·PC × 100·120·150% 모두 넘침 0 · 잘림 0 · 겹침 0. 칸반 옆 시트(400px)는 태블릿 가로에서만 열림(세로·PC 는 카드 0장 — 원래 그런 게이트). 글자 손잡이는 생산 홈에만 보이고 저장 열쇠가 `erp-production` 하나라 홈에서 정한 값이 칸반 옆 시트에도 든다.
  - **S1** 옆 시트 바닥 단추 줄 `.foms-prod-sheet__foot`(`foms-tablet-production-kanban.css:1211`, 줄바꿈 없음): 단추 셋인 주문(보류 / 제작 취소 / 제작 완료)에서 [제작 완료]가 140% 11px · 150% 40px 밖으로 잘림, 시트 안 가로 스크롤. 130% 까지는 괜찮음. (스크린샷으로 확인 — 총괄도 `land_fs150_side_doing_bottom.png` 직접 봄) 단추 글자는 원래 토큰(`--foms-font-size-base`)이라 전부터 배율을 따랐지만, 태블릿에서 배율을 바꿀 손잡이가 이번에 처음 생겨 드러남.
  - **S2** 옆 시트 주소 칸 `.foms-prod-sheet__contact-text`(`sheet.css:229`, `word-break: keep-all`): 띄어쓰기 없는 긴 주소가 150% 에서 [지도] 단추 밑으로 30px 들어감(130~140% 는 칸만 넘고 안 가림). (스크린샷으로 확인)
  - **S3** 전체 화면 시트 태블릿 가로 150% + 제품 이름 긴 주문: 머리 줄이 두 줄로 접혀 페이지 높이 865px(화면 800) — [제작 시작] 이 한 번 더 내려야 다 보임. 100% 에서도 809px 였던 것. (스크린샷으로 확인, 가벼움)
  - **S4** (원래 있던 것) 옆 시트 머리 "#번호 · 상차 날짜" 끝이 닫기 단추와 100% 에서 20×10px 겹침, 130% 이상 0. 이번 변경 탓 아님.
- **총괄 판정(11-10)**: S1·S2 는 이번에 손잡이를 달면서 닿을 수 있게 된 결함 → 고쳐서 같이 올린다(`sheet.css` 에 바닥 줄 `flex-wrap` · 주소 `overflow-wrap`). R8 도 같이(큰 줄 도면 칸 · 내 공정 시공일 칸 폭을 배율 따라). S3·S4 는 미룸. **PR #791 은 합치기 전에 P6 고침을 같은 PR 에 더한다** — 운영 실측은 요청 1건당 1회라 고친 판을 한 번에 재는 쪽이 맞다.
- **P7 D19 구현(11-10) — 커밋 1d1183fed · 25dfe7d54**: 워커(opus, 노력 중간)가 레일 주소·강조·[보드]·시험 7개를 만듦. 워커 판단 둘(총괄이 diff 로 확인하고 받아들임): ① 켜진 프리랜서는 레일 생산이 보드 그대로(문지기 허용 목록에 첫 화면 없음 — `test_freelancer_menus.py` 3건이 알려 줌) ② 조각 이동 뒤 강조를 위해 `tablet-rail-nav.js` 가 `data-foms-rail-match` 를 먼저 봄(핀 20261110a). split 셸 레일은 마우스 좁은 창 전용이라 안 바꿈. 총괄이 더한 것: [보드] 는 온전한 페이지 이동(`data-foms-erp-no-shell`), S5(바뀐 줄 품목 줄 두 줄), 제목 줄 오른쪽 묶음 `.foms-prod-home__tools`(글자 120% 에서 [다시 받기] 혼자 둘째 줄로 떨어져 한 줄이 비던 것 — 스테이징 스크린샷으로 봄, DOM 흉내로 100·120·150% 미리 확인), 띠 묶음 줄 '· 없음' 뺌(막대에 닿음).
- 푸시 11: deploy dbfaa199d → **1d1183fed**. smoke 17,174 PASS. 스테이징(healthz 1d1183fed, `scratchpad/prod_home_v3_check.py` 를 `FOMS_CHECK_TARGET=staging` 으로 연습 실행 — 운영 실측과 같은 스크립트): 레일 생산 주소 `/erp/production/home` · 강조 · [보드] → `/erp/production/dashboard`(카드 67, 레일 생산 강조 유지) → 레일 생산 → 첫 화면 · 탭 `날짜 | 내 공정 1 | 바뀐 것 30 | 찾기 | 보드` · 처음 열린 장 `past`(만들 것 2 · 도면·컨펌 기다림 48 — R1 로 도면 단계 보류 2건이 기다림으로) · 글자 150% 가로 넘침 없음 · 내 공정 150% 시공일 한 줄 · 세로 OK · 4xx 0 · JS 0.
- 처리: R1~R5 · R7 · R9~R11 은 고침 묶음(P6)으로 워커에게, R8 은 워커 ② 결과와 운영 실측(글자 120%)을 보고, R6 미룸. 운영에는 생산팀 계정이 아직 없어 PR #791 은 그대로 합치고 고침은 deploy 에 먼저 올린 뒤 운영은 지시 때.
- **P6 고침(11-10) — 커밋 dbfaa199d**: 워커(opus, 노력 중간)가 R1~R5 · R7 · R9~R11 을 고치고 시험 6개를 더함(시험을 뺀 코드만 되돌리면 6개 실패 — 음성 대조군 확인). 총괄이 diff 11파일을 직접 읽고 S1(`.foms-prod-sheet__foot { flex-wrap: wrap }`) · S2(주소 `overflow-wrap: anywhere`) · R8(큰 줄 도면 칸 `calc(92px * fs)` · 내 공정 시공일 칸 `calc(150px * fs)` · 도면 파일 칸 폭 배율 + `min-height`)을 더함. 핀 home.css · home JS · sheet.css `20261110b`, sheet-page JS `20261110a`. 관련 시험 51 → smoke 17,167 PASS → **푸시 10: deploy d3cf1652d → dbfaa199d**, 스테이징 healthz dbfaa199d.
- **고침 뒤 스테이징 재측정(워커 ②, 같은 두 주문 · 새 핀 실림 확인 · 쓰기 없음 · JS 0 · 4xx 0)**: S1 넘침 0/0/11/40px → 0/0/0/0(150% 는 두 줄, [제작 완료] 온전) **닫힘** · 100% 는 px 까지 전과 같음(회귀 없음) · S2 겹침 14/41/30px → 0 **닫힘** · 시트 안 가로 스크롤 없음 · 전체 화면 시트 150% 전과 같음 · 큰 줄 도면 칸 92 → 138px 잘림 없음 · 내 공정 150% 시공일 한 줄 · [재단 끝] 온전. 도면 파일 칸은 그 칸이 있는 주문이 없어 못 잼.
  - 달라진 점(가벼움): 단추 셋 주문은 130%·140% 에서도 바닥 단추가 두 줄(바닥 줄 약 60px 높아짐).
  - **S5 (새로 보임)** 날짜 탭 큰 줄 150%: 이름 칸이 416 → 200px 로 좁아져 바뀐 줄의 "시공일 변경 6/29 → …" 가 새 날짜 앞에서 말줄임(100% 는 다 보임). (스크린샷으로 확인) → 바뀐 줄은 품목 줄을 두 줄까지 허용.
- **D19 (사용자, 11-10 "스크린샷은 수정 전 UI 인데" → 질문 창 "누구나 새 첫 화면")**: 태블릿 레일의 "생산" 은 지금 누구에게나 옛 생산 보드(`/erp/production/dashboard`, `ERP_PRIMARY_NAV_PATHS`)로 간다 — 새 첫 화면은 주소를 직접 쳐야 보였고 운영엔 생산팀 계정이 없어 아무도 못 봄. 결정: 태블릿에서는 새 첫 화면을 볼 수 있는 사람이면 누구나 "생산" → `/erp/production/home`, 옛 보드는 첫 화면 제목 줄 [보드] 로, PC 는 그대로. 워커(opus, 노력 중간)에게 맡김. PR #791 은 이것까지 넣고 합친다.

## 17. 운영 반영 3차 · 실측 (2026-11-10, PR #791)
- 푸시 12: deploy 1d1183fed → **29a983085**(25dfe7d54 제목 줄 묶음 + 문서). smoke 17,174 PASS · CI ALL GREEN(`ci15.log` target 29a98308). 스테이징 연습 실행(운영 실측과 같은 스크립트): 띠 글 잘림 0 · 글자 150% 넘침 0 · 레일 생산 → 첫 화면 → [보드](카드 67) → 레일 생산 → 첫 화면 · 4xx 0 · JS 0.
- **운영 PR #791 → 49190ca46**: 승격 가지 `promote/tablet-home-v3`(이 세션 커밋 19개 = 코드 5개 197b14c1a · d3cf1652d · dbfaa199d · 1d1183fed · 25dfe7d54 + 문서 14개). D19 가 건드린 파일 5개도 운영 = 내 바탕(대조 SAME). 승격 트리 smoke 17,161(D19 까지) + 관련 129, 검사 4개(test · pg-lane · harness · perf-gate) 통과 → merge → 운영 healthz 49190ca46(105초) · `check_deploy_drift --target production` 일치.
- **운영 실측(사용자 "운영에 올리고 실측" 1회, claude_master id 57 잠금 해제 → 읽기만 → 재잠금 `is_active=False` 확인 · 로그아웃 302)**. `scratchpad/prod_home_v3_check.py`, 1280×800 터치 + 800×1280, 화면 안 클릭은 날 고르기·글자 손잡이·[보드]·레일뿐(쓰기 단추 안 누름, 페이지가 보낸 것은 `POST /api/foms/rum` 뿐). 스크린샷은 스크래치패드에만.
  - 첫 화면(날짜 탭) 200 · 읽기 1.36초 · TTFB 743ms. 머리 "전체 548건", 탭 `날짜 | 내 공정 4 | 바뀐 것 218 | 찾기 | 보드`. 레일 생산 주소 `/erp/production/home` · 강조.
  - 띠(만들 것 / 전체): 지난 7일 29/80 · 오늘 3/14 · 11/11 6/19 · 11/12 1/12 · 11/13 3/13 · 11/14 1/6 · 11/15 0/0 · 11/16 1/12 · 11/17 2/8 · 11/18 1/7 · 11/19 0/0 · 11/20 0/2 · 그 뒤 1/16. 아래 "지난 시공일 82건 +248" · "시공일 없음 29건".
  - 처음 열린 장 = 오늘: 시공 14건 · 만들 것 3 · 도면·컨펌 기다림 11, 큰 줄 3 + 작은 칸 11 + 내일 미리 보기 6줄 — 화면을 다 씀(내용 바닥 1268px / 화면 800px).
  - 글자: 이름 20 → 24px(120%) → 30px(150%), 가로 넘침 없음, 이름·작은 칸·띠·도면 칸 잘림 0(품목 줄 말줄임만 2 → 5). 150% 에서 제목 줄은 두 줄(탭 줄 + 오른쪽 묶음).
  - 내 공정 200 · 0.71초: 재단 4 · 엣지 0 · 조립 0 · 검수 0, 곧 올 것(제작 대기) 56. 150% 에서 시공일 한 줄 · 넘침 0.
  - 바뀐 것 200 · 0.92초: 받은함 218장(페이지 높이 18,404px). 찾기 200 · 0.64초: 300줄 · 묶음 27. [보드] → 옛 보드 카드 102 · 레일 생산 강조 유지 → 레일 생산 → 첫 화면. 세로(800×1280) 띠 가로 흐름 · 넘침 없음. 4xx 0 · JS 오류 0.
- **운영 실데이터에서 본 것(스테이징 110건에서는 안 보임) — 다음 고침 후보**
  - **M1 "바뀐 것 218"이 신호 구실을 못 함**: 받은함 대부분이 도면 기다림 단계 주문의 "도면 재전달" · "시공일 변경" — 생산팀이 아직 손댈 일이 없는 주문. 그래서 오늘 장의 도면·컨펌 기다림 칸 11개가 전부 빨간 테두리(바뀜)다. 운영엔 [확인했어요] 를 누를 생산팀 계정이 없어 계속 쌓임. → 권고: 바뀐 것(숫자·받은함·빨간 테두리)은 생산 단계(제작 대기~검수 끝) 주문만. **사용자 결정 필요.**
  - **M2 내 공정 줄 순서가 시공일 순이 아님**: 재단 줄이 11/5 · 11/17 · 10/31 · 10/27 순 — 읽기 모델이 7일 안 주문(오름차순) 뒤에 지난 주문(최근부터)을 붙인 순서 그대로다. → 줄과 "곧 올 것" 을 시공일 빠른 순으로.
  - **M3 글자 150% 에서 큰 줄 품목·치수 글이 10자쯤에서 잘림**(이름 칸 200px). 생산팀에겐 치수가 중요. → 바뀐 줄만이 아니라 모든 큰 줄의 품목 줄을 두 줄까지.
  - **M4 한가한 날 장은 아래가 빔**: 11/18(내용 바닥 462px) · 11/19(245px, 시공 0) · 11/20(283px) · 그 뒤(523px). 미리 보기가 "뒤로 만들 것이 있는 첫 날"만 보고 "그 뒤" 묶음은 안 봄. → 미리 보기를 "그 뒤" 까지, 그래도 없으면 밀린 것(지난 7일 만들 것)을 보여 줌.
  - 참고: 아래 단추 "지난 시공일 82건 +248" 의 "+248" 은 뜻이 바로 안 읽힐 수 있음(장 머리줄에는 "더 오래된 248건은 안 보여요" 가 있음).
- **D20 (사용자, 11-10 질문 창 "4가지 고치기" · "만들 주문만")**: 바뀐 것(탭 숫자 · 받은함 · 빨간 테두리 · 정렬 · 찾기 거르기)은 생산 단계 주문(제작 대기~검수 끝)만. 도면·컨펌 기다림과 제작 완료 주문의 변경은 치지 않는다. 취소 주문 묘비는 그대로.
- **P8 DONE (11-11) — 커밋 5b92031ca**: 워커(opus, 노력 중간)가 M1~M4 + 단추 글을 고치고 시험 3개를 더하고 단언 4개를 고침(코드만 되돌리면 7개 실패 — 음성 대조군). 총괄이 diff 6파일을 직접 읽음. M1 = 행을 만들 때 `home_view != 'prod'` 면 alerts 를 비움(받은함이 `home_alerts` 를 읽어서 `has_changes` 만 끄면 빠짐 — 워커가 찾음). M2 = `_due_sort_key`(시공일 빠른 순 · 없음 맨 뒤 · 같은 날 주문 번호). M3 = `.fph-dr__pr` 두 줄 말줄임 한 규칙. M4 = 미리 보기 후보를 그 뒤 묶음까지, 없으면 지난 7일 만들 것("밀린 것"), 자기 자신은 안 닮. 단추 글 "지난 시공일 N건 · M건 더". 읽기 모델 484줄(래칫 500). 핀 home.css `20261111a`.
- 푸시 13(bafb8fbb9 문서, 빠른 길 3,698 PASS · CI 초록) · **푸시 14: deploy bafb8fbb9 → 5b92031ca**. smoke 17,177 PASS. 스테이징(healthz 5b92031ca, 같은 점검 스크립트): 탭 `날짜 | 내 공정 1 | 바뀐 것 1 | 찾기 | 보드` — 바뀐 것 30 → 1(받은함 1장), 네 탭 200 · 레일 · [보드] 흐름 그대로 · 글자 150% 넘침 0 · 4xx 0 · JS 0. 스테이징은 앞날 주문이 없어 M2(줄 순서) · M3(두 줄) · M4(미리 보기)는 시험으로만 확인 — 실데이터 확인은 운영에 올린 뒤.
- **R12 (조사만, 미룸)** 변경 알림의 기준선(`production_change_alerts.py:103-144` `compute_window_start`): 내 마지막 [확인했어요] 시각 → 없으면 마지막 "생산 쪽 단계 진입" 이벤트 → 없으면 `erp_stage_updated_at` → `created_at`. "생산 쪽" 목록(52-54줄)에 고객컨펌이 들어 있어 **컨펌 기다림 동안 생긴 변경은 제작 대기로 넘어오는 순간 한꺼번에 바뀐 것으로 뜬다**(도면 → 컨펌 때는 기준선이 새로 잡혀 도면 때 것은 버려짐). 생산 단계 주문이면 `erp_stage_updated_at` 이 곧 진입 시각이라 싸게 고칠 수 있지만, 이 모듈은 생산 보드 · 작업 시트 · 모바일이 같이 써서 홈만 다르게 잡으면 알림 수가 어긋난다 → 정할 일로 남김.
- 남은 것: P8 운영 반영(지시 때) · R12 · R6 · S3 · S4 · 시공 탭(§13) · 출고 탭(§14) 모양 선택 · 갤럭시 탭 실기기 검수(사용자) · 운영 생산팀 계정(사용자).

## 18. 운영 반영 4차 · 실측 (2026-11-11, PR #792 — 사용자 "운영에 올리고 실측")
- 푸시 15(a59742e4c 문서, 빠른 길 3,698 PASS). 코드 커밋 5b92031ca 의 CI 4종은 `gh run list` 로 직접 조회해 전부 success(`ci_watch` 는 아직 안 올린 문서 커밋을 대상으로 잡아 "워크플로 없음 — green 취급" 을 냈다 — 거짓 초록, 직접 조회로 다시 확인).
- **운영 PR #792 → d26294e79**: 승격 가지 `promote/tablet-home-m1m4`(origin/production 49190ca46 위, 이 세션 커밋 3개 = 코드 5b92031ca + 문서 bafb8fbb9 · a59742e4c, `AI_STATUS.md` 1회 `--ours`). 파일 내용 대조 6개 SAME. 승격 트리 smoke 17,164 + harness 174, 검사 4개 통과 → merge → 운영 healthz d26294e79(60초) · drift 일치.
- **운영 실측(사용자 요청 1회, claude_master 잠금 해제 → 읽기만 → 재잠금 `is_active=False` 확인 · 로그아웃 302)**. 같은 스크립트를 스테이징에서 먼저 연습 실행. 4xx 0 · JS 오류 0 · 쓰기 단추 안 누름.
  - 첫 화면 200 · 읽기 1.14초 · TTFB 464ms. 탭 `날짜 | 내 공정 4 | 바뀐 것 21 | 찾기 | 보드`, 머리 "전체 548건".
  - **M1 닫힘**: 바뀐 것 218 → **21**, 받은함 21장 = 제작 대기 20 + 재단 중 1(도면 기다림 0). 오늘 장 도면·컨펌 기다림 칸 13개 빨간 테두리 0(전에는 11개 전부). 받은함 페이지 높이 18,404 → 1,472px.
  - **M2 닫힘**: 재단 줄 시공일 10/27 · 10/31 · 11/5 · 11/17(전 11/5 · 11/17 · 10/31 · 10/27). 곧 올 것도 10/27 · 10/27 · 10/28 · 10/29 · 10/30 · 10/31 · 11/2 · 11/3… 오름차순.
  - **M3 닫힘**: 품목 줄 말줄임 100% 2 → 0 · 120% 5 → 0 · 150% 5 → 0. 스크린샷으로 치수(W × D × H)와 바뀐 내용("시공일 변경 미정 → 11/11")이 다 보이는 것 확인.
  - **M4 덜 닫힘**: 띠의 모든 장에 미리 보기가 달림. "그 뒤" 장 내용 바닥 523 → 1071px(밀린 것 = 지난 7일 만들 것 27 중 6줄). 11/18 462 → 586 · 11/19 245 → 369 · 11/20 283 → 407 · 11/21 369px — 뒤에 만들 것이 "그 뒤" 1건뿐이라 미리 보기가 한 줄이고 화면 아래 절반은 여전히 빔. 밀린 것은 "뒤에 만들 것이 하나도 없을 때"만 달리게 해서 이 날들에는 안 달림. → 다음 후보: 미리 보기가 6줄에 못 미치면 밀린 것으로 채움.
  - 띠: 지난 7일 27/81 · 오늘 6/19 · 11/12 1/12 · 11/13 3/13 · 11/14 1/6 · 11/15 0/0 · 11/16 1/11 · 11/17 2/8 · 11/18 1/7 · 11/19 0/0 · 11/20 0/2 · 11/21 0/0 · 그 뒤 1/16. 오늘 장: 만들 것 6(바뀐 줄 먼저) + 도면·컨펌 기다림 13 + 내일 미리 보기.
  - 새로 본 것(가벼움) **M5**: 아래 단추 "지난 시공일 95건 · 248건 더" 가 칸 폭을 넘어 두 줄("더" 만 아랫줄). → 글을 줄이거나 단추 글자를 한 단계 작게.
  - 글자 150%: 넘침·잘림 0. 바뀐 줄은 "시공일 변경 미정 →" / "11/11 · 품목…" 두 줄로 바뀐 내용이 다 보임. [보드] → 카드 102 · 레일 강조 → 레일 생산 → 첫 화면. 세로 OK.
- **P9 DONE (11-11, 사용자 질문 창 "남은 두 가지 바로 고치기") — 커밋 771345be4**: 같은 워커(opus, 노력 중간, 앞 맥락 이어서)가 고침, 총괄이 diff 5파일 직접 읽음. M4 나머지 = 장마다 `preview` 하나 대신 묶음 목록 `previews`: 뒤 장들(그 뒤 포함)의 만들 것을 띠 순서로 이어 6줄까지(`PREVIEW_MAX_ROWS`), 한 장에서만 왔으면 제목 = 그 장 제목, 여러 장이면 "다음에 만들 것 n"(n = 뒤 장들 합계) + 줄마다 시공일, 6줄에 못 미치면 남은 자리만큼 "지난 7일 만들 것 n · 밀린 것". 지난 7일 장에는 밀린 것 없음, 아래 두 장에는 미리 보기 없음. M5 = 아래 단추 `지난 시공일 N건<small>M건 더</small>`(일부러 두 줄, `.fph-sf small`). 시험: 미리 보기 다섯 경우 + 단추 글(코드만 되돌리면 4개 실패). 핀 home.css `20261111b`. **래칫 주의: 읽기 모델 495줄 · `test_production_home_tabs.py` 498줄 — 다음 고침 때는 파일을 나눠야 한다.**
- 푸시 16(8c296b71c 문서) · **푸시 17: deploy 8c296b71c → 771345be4**. smoke 17,177 PASS · CI 4종 success(`gh run list` 직접 조회). 스테이징(healthz 771345be4): 네 탭 200 · 탭 `날짜 | 내 공정 1 | 바뀐 것 1 | 찾기 | 보드` · 레일 · [보드] 흐름 · 세로 · 4xx 0 · JS 0. 스테이징은 앞날 주문·안 읽은 지난 주문이 없어 미리 보기 채우기와 두 줄 단추는 시험으로만 확인 — 실데이터 확인은 운영에 올린 뒤(지시 때).
- 남은 것: P9 운영 반영(지시 때) · R12(변경 알림 기준선) · R6 · S3 · S4 · 시공 탭(§13) · 출고 탭(§14) 모양 선택 · 갤럭시 탭 실기기 검수(사용자) · 운영 생산팀 계정(사용자).

## 19. 운영 반영 5차 · 실측 (2026-11-11, PR #793 — 사용자 "운영에 올리고 실측")
- 푸시 18(9f1ac2177 문서, 빠른 길 3,698 PASS · CI ALL GREEN).
- **운영 PR #793 → a5cd34057**: 승격 가지 `promote/tablet-home-m4m5`(origin/production d26294e79 위, 이 세션 커밋 3개 = 코드 771345be4 + 문서 8c296b71c · 9f1ac2177, `AI_STATUS.md` 1회 `--ours`). 파일 내용 대조 5개 SAME. 승격 트리 smoke 17,164 + harness 174, 검사 4개 통과 → merge → 운영 healthz a5cd34057(60초) · drift 일치.
- **운영 실측(사용자 요청 1회, claude_master 잠금 해제 → 읽기만 → 재잠금 `is_active=False` 확인 · 로그아웃 302, 스테이징 연습 실행 먼저)**. 4xx 0 · JS 오류 0 · 쓰기 단추 안 누름.
  - 첫 화면 200 · 읽기 1.33초 · TTFB 591ms · "전체 550건" · 탭 `날짜 | 내 공정 4 | 바뀐 것 21 | 찾기 | 보드`.
  - **M4 닫힘**: 띠의 13장 모두 미리 보기 6줄. 내용 바닥 11/19 369 → 837 · 11/20 407 → 875 · 11/21 369 → 837 · 11/15 381 → 849px(화면 800) — 가장 적은 장도 화면을 채움. 가까운 날은 "다음에 만들 것 n"(오늘 10 · 11/12 9 · 11/13 6), 11/14부터는 "다음에 만들 것 n" + "지난 7일 만들 것 27 · 밀린 것", 11/18~11/21 은 "11/22 뒤 만들 것 1" + 밀린 것 5줄, "그 뒤" 장은 밀린 것 6줄. 지난 7일 장은 "오늘 만들 것 6" 만, 아래 두 장은 없음.
  - **M5 닫힘**: 아래 단추 "지난 시공일 93건" + 작은 글 "250건 더", 두 단추 158×48 같은 높이 · 넘침 없음(스크린샷으로 확인).
  - 그대로인 것: 바뀐 것 21(제작 대기 20 · 재단 중 1) · 재단 줄 10/27 · 10/31 · 11/5 · 11/17 · 글자 120·150% 가로 넘침 0 · [보드] 카드 102 · 레일 흐름 · 세로.
  - 새로 본 것(가벼움) **M6**: 글자 150% 에서 큰 줄 이름 1개가 칸(200px)을 넘어 잘림(긴 상호 이름, 말줄임표 없이 잘림 — `.fph-dr__nm` 은 flex 라 `text-overflow` 가 안 먹음). 100·120% 는 0.
- **P10 DONE (11-11, 사용자 질문 창 "남은 자잘한 것 정리") — 커밋 bdd6fa2da**: 워커(opus, 노력 중간)가 함, 총괄이 diff 를 직접 읽고 옮긴 코드가 글자까지 같은 것을 `diff` 로 확인. ① M6: 날짜 장 큰 줄 이름을 안쪽 `<b>` 로 감싸 긴 이름은 말줄임표, 주문 번호는 늘 보임(`.fph-dr__nm b { min-width: 0; overflow: hidden; text-overflow: ellipsis }` · `small { flex-shrink: 0 }`). 다른 이름 칸(내 공정 줄 · 받은함)은 줄이 넘어가는 구조라 손대지 않음. 곧 올 것(`.fph-nx b`)은 말줄임은 되지만 번호가 b 안이라 아주 긴 이름이면 번호도 숨을 수 있음(미룸). ② 래칫 여유: 날짜 탭 읽기 모델을 `foms/services/production_home_days.py`(153줄)로 옮김 — 원래 파일 495 → 359줄, import 는 한 방향(새 모듈 → 원래 모듈, 재수출 없음). 시험은 리뷰 고침 묶음 9개를 `tests/domains/test_production_home_fixes.py`(219줄)로 — 원래 파일 498 → 308줄, 시험 수 18 → 9 + 10(새 이름 말줄임 시험 1). 핀 home.css `20261111c`.
- 푸시 19(ef5bf76aa 문서, CI ALL GREEN) · **푸시 20: deploy ef5bf76aa → bdd6fa2da**. smoke 17,178 PASS · CI 4종 success(직접 조회). 스테이징(healthz bdd6fa2da): 네 탭 200 · 레일 · [보드] 흐름 · 세로 · 4xx 0 · JS 0. 이름 칸(`scratchpad/name_ellipsis_check.py`): 100% · 150% 에서 굵기 800 · 크기 20/30px 그대로, 번호가 칸 안. 이 브라우저 DOM 에서만 이름을 길게 바꿔 보니 150% 에서 이름 말줄임 · 번호 보임(스크린샷으로 확인 — 실제 긴 이름은 운영에만 있어 운영 확인은 올린 뒤). 스캔이 `docs/harness/foms_audit_coverage_inventory.json` 한 줄(다른 세션 파일 `channel_push.py` 줄 번호 158 → 183)을 바꿨지만 이번 일과 무관해 되돌림(HEAD 그대로 CI 초록).
- 남은 것: P10 운영 반영(지시 때) · R12(변경 알림 기준선) · R6 · S3 · S4 · 곧 올 것 긴 이름일 때 번호 · 시공 탭(§13) · 출고 탭(§14) 모양 선택 · 갤럭시 탭 실기기 검수(사용자) · 운영 생산팀 계정(사용자).

## 20. 운영 반영 6차 · 실측 (2026-11-11, PR #794 — 사용자 "운영에 올리고 실측")
- 푸시 21(054289c01 문서, 빠른 길 3,698 PASS · CI ALL GREEN).
- **운영 PR #794 → 209442eae**: 승격 가지 `promote/tablet-home-tidy`(origin/production a5cd34057 위, 이 세션 커밋 3개 = 코드 bdd6fa2da + 문서 ef5bf76aa · 054289c01, `AI_STATUS.md` 1회 `--ours`). 파일 내용 대조: 기존 7개 SAME · 새 파일 2개. 승격 트리 smoke 17,165 + harness 174, 검사 4개 통과 → merge → 운영 healthz 209442eae(75초) · drift 일치.
- **운영 실측(사용자 요청 1회, claude_master 잠금 해제 → 읽기만 → 재잠금 `is_active=False` 확인 · 로그아웃 302, 스테이징 연습 실행 먼저)**. 4xx 0 · JS 오류 0 · 쓰기 단추 안 누름.
  - **M6 닫힘**: 글자 150% 에서 이름 칸 잘림 1 → 0, 말줄임표가 붙은 이름 1개, 주문 번호가 칸 밖으로 나간 줄 0. 100·120% 는 말줄임 0(전과 같은 모양).
  - 파일을 나눈 뒤에도 그대로: "전체 550건" · 탭 `날짜 | 내 공정 4 | 바뀐 것 21 | 찾기 | 보드` · 띠 13장 모두 미리 보기 6줄(가장 적은 장 내용 바닥 837px) · 아래 단추 "지난 시공일 93건 / 250건 더" · 내 공정 · 받은함 21 · 찾기 300줄 · [보드] 카드 103 · 레일 흐름 · 세로 · 글자 120·150% 가로 넘침 0.
  - 읽기 시간: 첫 화면 1.71초 · TTFB 996ms(배포 직후 첫 요청 — 앞 세 번은 464~743ms), 다른 탭 0.62~0.83초.
- 남은 것: R12(변경 알림 기준선) · R6 · S3 · S4 · 곧 올 것 긴 이름일 때 번호 · 시공 탭(§13) · 출고 탭(§14) 모양 선택 · 갤럭시 탭 실기기 검수(사용자) · 운영 생산팀 계정(사용자).

## 21. 발주사 · 영업 담당 표기 (2026-11-11, 사용자 "태블릿 생산 탭 메인 > 발주사, 영업 담당 표기")
- 푸시 22(e4fadd7a2 문서 — 원장 §20 · AI_STATUS, CI 초록).
- **D21 (사용자)** 생산 첫 화면 만들 것 줄에 발주사와 영업 담당을 보인다.
- **P11 (11-11) — 커밋 35254bf33(표기) · 223f4d407(잘림 고침) · 8f8a16577(낱말 단위 줄바꿈)**: 워커(opus, 노력 중간, 앞 맥락 이어서)가 표기를 넣고 총괄이 diff 를 직접 읽음. 값은 행에 이미 있는 `orderer_name`(발주사 — 주문한 사람 buyer 가 아님) · `manager_name`(없으면 `-`)이라 쿼리 추가 없음. 글 규칙은 읽기 모델 `_by_line` 한 곳: `발주 <발주사> · 담당 <영업 담당>`, 빈 쪽은 빼고 둘 다 없으면 요소를 안 그림. 자리: 날짜 탭 큰 줄(`fph_row` — 그날 만들 것 · 미리 보기 · 밀린 것)과 내 공정 줄의 **이름 오른쪽**, 묶음 `.fph-dr__ln` / `.fph-qr__ln` 이 `flex-wrap` 이라 자리가 모자라면 그 글만 다음 줄로. 작은 칸(도면·컨펌 기다림 · 제작 완료) · 곧 올 것 · 받은함 · 찾기 탭은 그대로. 긴 이름 말줄임(M6)은 그대로(기존 시험 통과). 시험: 네 경우(둘 다 · 발주사만 · 담당만 · 둘 다 없음) × 큰 줄 · 내 공정 줄 + 작은 칸에 없음(템플릿·`-` 조건을 하나씩 되돌리면 실패).
- 스테이징 실화면(`scratchpad/by_line_check.py`, 지난 시공일 장 큰 줄 2 · 재단 줄 1, 글 길이 15자): 100% 는 이름과 같은 줄 · 줄 높이 그대로(74px) · 잘림 없음. **150% 에서 두 번 고침** — ① 다음 줄로 내려간 글이 "담당 정…" 으로 말줄임 → 말줄임을 빼고 줄이 넘어가게(223f4d407), ② "담당 정다 / 슬" 처럼 이름 가운데서 끊김 → `word-break: keep-all` 로 낱말 단위(8f8a16577). 둘 다 스크린샷으로 봄. 핀 home.css `20261111f`.
- 푸시 23~25: deploy → 35254bf33 → 223f4d407 → (8f8a16577 올리는 중). 그 사이 다른 창이 deploy 에 커밋을 세 번 올려(겹치는 파일 없음) 전체 smoke 통과 뒤 뒤처짐 — 최신 deploy 위로 다시 옮기고 관련 시험 뒤 푸시. smoke 17,183 PASS(35254bf33 바탕) · 17,18x PASS(223f4d407 바탕).
- 남은 것: 8f8a16577 스테이징 150% 재확인 · 운영 반영(지시 때 — 운영엔 발주사·담당 표기 없음) · R12 · R6 · S3 · S4 · 곧 올 것 긴 이름일 때 번호 · 시공 탭(§13) · 출고 탭(§14) · 갤럭시 탭 실기기 검수(사용자) · 운영 생산팀 계정(사용자).

## 22. 운영 반영 7차 · 실측 (2026-11-11, PR #801 — 사용자 "운영에 올리고 실측")
- 푸시 26: deploy → 68f3f5622(8f8a16577 낱말 단위 줄바꿈 + 문서). smoke 17,218 PASS. 스테이징 150% 재확인: 발주사·담당 글이 다음 줄로 내려가 "발주 ○○ · 담당" / "이름" 으로 낱말 단위(스크린샷으로 봄), 잘림 0.
- **CI 사고(바로 고침)**: 68f3f5622 의 CI 는 다른 창 푸시(9d355f570)에 밀려 취소됐고, 그 최신 커밋의 Harness CI 가 `test_ai_status_head_budget` 로 실패 — `AI_STATUS.md` 상단이 4,002자(예산 4,000). 내 줄(+5자)과 다른 창 줄이 합쳐지며 넘음(각자 로컬에서는 통과). → 내 줄을 줄인 53beb3a0e 푸시(빠른 길 3,708 PASS), 최신 deploy(87fde7289) CI 3종 success 를 `gh run list` 로 확인. 교훈: 다른 창이 같은 시각에 AI_STATUS 를 고치면 합친 뒤에만 넘는다 — 내 줄은 늘리지 말고 줄여서 올릴 것.
- **운영 PR #801 → 0d500fb5e**: 승격 가지 `promote/tablet-home-byline`(origin/production 90de073da 위, 이 세션 커밋 5개 = 코드 35254bf33 · 223f4d407 · 8f8a16577 + 문서 e4fadd7a2 · 68f3f5622, `AI_STATUS.md` 2회 `--ours`, 53beb3a0e 는 AI_STATUS 뿐이라 뺌). 내 파일 7개 운영 = 내 바탕. 승격 트리 smoke 17,200 + harness 174, 검사 4개 통과 → merge → 운영 healthz 0d500fb5e(120초) · drift 일치.
- **운영 실측(사용자 요청 1회, claude_master 잠금 해제 → 읽기만 → 재잠금 `is_active=False` 확인 · 로그아웃 302, 스테이징 연습 실행 먼저)**. 4xx 0 · JS 오류 0 · 쓰기 단추 안 누름.
  - 발주사·담당 글(100%): 띠 15장을 다 열어 큰 줄 139줄 전부에 글이 있고 전부 이름과 같은 줄, 잘림 0 · 칸 밖 0, 가장 긴 글 21자. 작은 칸에는 0. 오늘 장 12줄(만들 것 6 + 미리 보기 6) 줄 높이 그대로(스크린샷으로 확인).
  - 150%: 오늘 장 12줄 모두 다음 줄로 내려가고 잘림 0 · 칸 밖 0 · 가로 넘침 없음. 긴 이름 말줄임 1 · 번호 칸 밖 0(M6 그대로).
  - 내 공정: 재단 4줄 모두 글 있음 · 잘림 0.
  - 그대로: "전체 550건" · 탭 `날짜 | 내 공정 4 | 바뀐 것 22 | 찾기 | 보드` · 가장 적은 장 내용 바닥 821px · [보드] 카드 103 · 레일 흐름 · 세로. 첫 화면 1.11초 · TTFB 473ms.
- 남은 것: R12(변경 알림 기준선) · R6 · S3 · S4 · 곧 올 것 긴 이름일 때 번호 · 시공 탭(§13) · 출고 탭(§14) 모양 선택 · 갤럭시 탭 실기기 검수(사용자) · 운영 생산팀 계정(사용자).

## 23. 발주사 · 담당 글 시인성 (2026-11-11, 사용자 "발주 담당이 전부 회색으로 돼 있어 구분이 안 돼 > UI 시인성 개선 해 봐")
- 원인: §21 에서 넣은 글이 `발주 ○○ · 담당 ○○` 한 덩이 · 회색 한 색(`--fph-text3`) · 보통 굵기라 아래 품목 줄(회색)과도, 발주사와 담당 서로도 안 갈렸다.
- 시안 3개를 실제 `home.css` + 지어낸 이름으로 그려 견줌(`scratchpad/by_preview/make.py`, 100% · 150%): A 이름만 굵고 진하게 / **B 발주사 진한 글자 · 담당 남색** / C B + 세로 금. C 는 담당만 있는 줄에 금이 혼자 남고 선이 하나 더 는다 → **B 채택**(칩 · 테두리 · 그림 없이 글자 색 · 굵기만 — 새 그림 · 칩은 "복잡 · 시인성 낮음" 으로 거절된 전례).
- 구현 — 커밋 34f4de251(총괄 직접, 작은 손질): 읽기 모델 `_by_line`(글) → `_by_parts`(조각 `k` · `label` · `name`), 템플릿 두 곳이 `<span class="fph-by is-o|is-m"><i>머리말</i> 이름</span>` 으로 그림. CSS: 머리말 12px 회색 · 이름 700 · 발주사 `--fph-text` · 담당 `--fph-brand-dark`, 조각 사이 틈 14px(가운뎃점 뺌), 묶음은 `inline-flex` + `flex-wrap`. 내 공정 줄은 `.fph-qr__who span`(한 줄 말줄임 · 회색)이 조각에도 걸려 `.fph-qr__who .fph-by` 로 따로 풂. 날짜 큰 줄 이름 크기는 14px 그대로. 핀 home.css `20261111g`.
- 시험: 조각 마크업 네 경우(둘 다 · 발주사만 · 담당만 · 둘 다 없음) × 큰 줄 · 내 공정 줄, CSS 규칙(이름 굵기 · 색 둘 · 머리말 회색 12px · 줄바꿈 · 내 공정 줄 풀기). 관련 시험 50 통과.
- 푸시 29: deploy 0eaaf596e → **34f4de251**. smoke 17,279 PASS + harness 174(`smoke_push29.log` SMOKE_EXIT=0).
- 스테이징 실화면(healthz 34f4de251, `scratchpad/by_color_check.py`, 1280×800 터치, 같은 스크립트로 배포 전 값도 잼): 핀 `20261111g`. 조각 색 — 발주사 rgb(20,23,28) · 담당 rgb(74,85,184) · 머리말 rgb(107,115,128) 12px, 굵기 700. 100%: 날짜 큰 줄 2줄 모두 이름과 같은 줄 · 줄 높이 74 · 87px(배포 전과 같음), 내 공정 1줄 96px(같음). 150%: 다음 줄로 내려가고 조각 잘림 0 · 칸 밖 0 · 가로 넘침 없음, 줄 높이 182 → 151px(조각이 한 줄에 들어가 한 줄 줆). 4xx 0 · JS 오류 0 · 로그아웃 302. 스크린샷으로 100% · 150% · 내 공정 확인.
- 남은 것: 운영 반영은 지시 때(운영 139줄에서 100% 한 줄 유지 여부는 운영 실측 때 봄 — 스테이징 글은 13자, 운영 최장 21자). 그 밖은 §22 와 같음.

## 24. 운영 반영 8차 · 실측 (2026-11-11, PR #806 — 사용자 "운영에 올리고 실측")
- 스테이징 문서 푸시 30: deploy 34f4de251 → de593fb34(빠른 길 3,708 PASS, CI 3종 초록). 코드 커밋 34f4de251 CI 4종(FOMS CI · PG Lane · Harness CI · perf-gate) 초록.
- **운영 PR #806 → ccf54f688**: 승격 가지 `promote/tablet-by-color`(이 세션 커밋 3개 = 코드 34f4de251 + 문서 b0e58f9f8 · de593fb34, `AI_STATUS.md` 는 `--ours`). 파일 내용 대조: 내 파일 9개 모두 운영 = 내 바탕. 승격 트리 APP_OK · scan 3종 변화 없음 · smoke 17,211 + harness 174. smoke 사이 운영에 다른 세션 PR #805(cs_agent, 겹치는 파일 없음)가 들어와 `origin/production` 위로 rebase → 관련 시험 50 통과 → 검사 4개(test · pg-lane · harness · perf-gate) 통과 → merge → 운영 healthz ccf54f688(50초) · drift 일치.
- **운영 실측(사용자 요청 1회, claude_master 잠금 해제 → 읽기만 → 재잠금 `is_active=False` 확인 · 로그아웃 302, 스테이징 연습 실행 먼저)**. `prod_v3_measure6.log`. 4xx 0 · JS 오류 0 · 쓰기 단추 안 누름(페이지가 보낸 것은 `POST /api/foms/rum` 뿐).
  - 조각 색(100%, 띠 15장 다 열어 봄): 큰 줄 77줄 전부에 글 · 조각 154개 — 발주사 77개 rgb(20,23,28) · 담당 77개 rgb(74,85,184), 굵기 700 · 14px, 머리말 rgb(107,115,128) 12px. 전부 이름과 같은 줄(77/77) · 잘림 0 · 칸 밖 0 · 조각 잘림 0, 가장 긴 글 19자. 줄 높이 74px 43줄 · 87px 34줄(품목 글 두 줄) — 색 고침으로 늘어난 줄 없음. 작은 칸에는 0.
  - 150%: 오늘 장 12줄 모두 다음 줄 · 잘림 0 · 조각 잘림 0 · 가로 넘침 없음(줄 높이 151px 7 · 184px 5). 긴 이름 말줄임 1 · 번호 칸 밖 0.
  - 내 공정: 재단 1줄 · 조각 2개 색 맞음(15px) · 잘림 0.
  - 그 밖: "전체 133건"(다른 세션의 적체 주문 일괄 완료로 550 → 133) · 탭 `날짜 | 내 공정 1 | 바뀐 것 9 | 찾기 | 보드` · 받은함 9(제작 대기 8 · 재단 중 1) · [보드] 카드 24 · 레일 흐름 · 세로 OK. 첫 화면 1.12초 · TTFB 444ms. 스크린샷으로 오늘 장 확인.
- 남은 것: §22 와 같음(R12 · R6 · S3 · S4 · 곧 올 것 긴 이름 번호 · 시공 탭 · 출고 탭 모양 선택 · 갤럭시 탭 실기기 검수 · 운영 생산팀 계정).

## 25. 남은 자잘한 것 정리 · D22 (2026-11-11, 사용자 "남은 자잘한 것 정리")
- 운용: 총괄이 항목을 둘로 갈라 워커 2명(opus)에게 같은 워크트리에서 겹치지 않는 파일로 동시에 맡김 — ① 화면 손질 3건(노력 중간) ② R6 → 이어서 R12(같은 워커에게 맥락 유지). 워커 보고는 주장으로 다루고 총괄이 diff 직접 읽기 · 시험 다시 실행(관련 1,311 통과) · 스테이징 고치기 전/뒤 실측으로 받아들임.
- **D22(사용자 결정, 질문 창 "제작 대기 뒤 바뀐 것만")**: 07-22 설계는 "생산 파이프라인 진입 후 변경만" 이고 파이프라인에 고객컨펌이 들어 있어, 컨펌 기다림 동안의 변경이 생산 단계로 넘어온 뒤에도 '바뀜' 으로 남았다(운영 11-11 오늘 장 제작 대기 6줄 중 4줄 빨간 테두리). 이제 생산 진입 뒤 바뀐 것만. 컨펌 대기 주문 자체의 알림은 그대로. 첫 화면 · 보드 · 작업 시트 공통.
- **R12 구현 — 커밋 8ac7562f7**(워커, 노력 높음): 총괄이 낸 안("`STAGE_CHANGED` 중 to=생산")은 부족했다 — 컨펌 → 생산의 흔한 두 길이 `STAGE_CHANGED` 를 안 남긴다(고객 컨펌 끝 = `CUSTOMER_CONFIRMED`, 컨펌에서 바로 제작 시작 = `PRODUCTION_STARTED`, 강제 변경 = `STAGE_OVERRIDE`). 워커가 단계를 바꾸는 길을 전부 `파일:줄` 로 확인해 네 이벤트를 다 보게 했고, 진입을 "to 가 생산·시공이고 from 이 그 밖" 으로 잡아 완료 취소(시공 → 생산)가 알림을 지우지 않게 함. `erp_stage_updated_at` 은 제작 완료 · 수정 제작 때도 갱신돼 바닥으로 안 씀. `PROD_STAGES` 그대로. 렌더 전 304 키는 같은 이벤트 목록(`PRODUCTION_CHANGE_EVENT_TYPES`)을 써서 같이 넓어짐. 기존 변경 알림 시험은 하나도 안 깨짐(고친 단언 0). 새 시험 10개 — 코드만 되돌리면 5개 실패.
- **R6 구현 — 커밋 1fa0792ee**(워커): 리뷰 주장 맞음 — SQL 캡 · 정렬은 납작 열 `erp_construction_date`, 행 `construction_date` 는 `production_dashboard_display.py:211` 이 JSONB 에서 읽음. 어긋난 주문 재현: 앞날이라 읽어 온 주문이 지난 시공일 장에 서고 그 날짜 장은 0건. 고침 = `build_production_home` 안에서 이미 읽은 `orders` 로 행 날짜를 납작 열로 덮어씀(쿼리 추가 없음, 보드 · 시트 행 모양 그대로).
- **화면 손질 3건 — 커밋 e22db669b**(워커): ① 곧 올 것 `<b><i>이름</i> <small>#번호</small></b>` + `.fph-nx b` flex(M6 방식). ② S3 원인 둘 — 몸통 높이가 `100dvh - 64px` 로 박혀 있는데 머리 줄은 73px(100% 의 9px), 머리 줄이 `flex-wrap` 이라 150% 에서 단추가 둘째 줄(129 · 173px) → 가로 태블릿 블록에서 페이지를 세로 flex, 머리 줄 `nowrap`, 몸통 `flex: 1`. ③ S4 `.foms-tablet-sheet--headless .foms-prod-sheet__titlebar { padding-right: 36px }`. 핀 home.css `20261111h` · sheet.css `20261111a`.
- 푸시 32: deploy 4f2c5817c → **8ac7562f7**(e22db669b · 1fa0792ee · 8ac7562f7). smoke 17,295 PASS + harness 174(`smoke_push32.log` SMOKE_EXIT=0), smoke 사이 다른 창 문서 커밋 2개(겹침 없음) 위로 rebase 뒤 관련 시험 41 통과.
- **스테이징 실화면(healthz 8ac7562f7, `scratchpad/tidy_check.py` — 배포 전에 같은 스크립트로 먼저 잼)**
  - 작업 시트 페이지 높이: 100% 809 → **800px**, 150% 865 → 800px, 150% + 긴 품목 909 → 800px. 머리 줄 73px 한 줄(전 129 · 173px), 가로 넘침 없음. 오른쪽 칸 안의 [제작 시작] 은 전처럼 그 칸을 내려야 보임(페이지가 한 번 더 내려가던 것만 없앰).
  - 옆 시트 머리 글과 닫기 단추 겹침: 100% 20×8px → **0**, 150% 0. 스크린샷으로 확인.
  - 곧 올 것(이 브라우저 DOM 에 긴 이름을 넣어 봄): 150% 에서 이름 171px 말줄임 · 번호 칸 안(전에는 구조상 같이 잘림).
  - D22: 탭 "바뀐 것 1 → 0" · 빨간 테두리 줄 1 → 0. 그 주문(#4096)의 이벤트를 `/api/orders/<id>/events` 로 읽어 확인 — 시공일 변경 2건은 08-06, 생산 진입은 09-21(`CUSTOMER_CONFIRMED` CONFIRM → PRODUCTION)과 09-22(`STAGE_OVERRIDE` COMPLETED → PRODUCTION) → 진입 전 변경이라 안 뜨는 것이 맞음. 옛 기준선은 06-23 `STAGE_CHANGED` MEASURE → CONSTRUCTION 이었다. 양성 대조(진입 뒤 변경은 뜬다)는 스테이징에 쓰면 실제 직원 방으로 알림이 갈 수 있어 시험(정본 엔진 전이 포함)으로만.
  - 4xx 0 · JS 오류 0 · 로그아웃 302.
- 워커가 남긴 구멍(받아들임): ① 상설 이력에도 같은 바닥이 먹어 컨펌 때 변경은 작업 시트의 조용한 이력에서도 빠짐(한 규칙 유지 — 생산팀은 넘어온 때의 최종 내용만 보면 됨) ② 생산 → 컨펌 → 다시 생산인 주문은 첫 생산 기간의 미확인 변경도 사라짐 ③ 진입 이벤트 없이 단계가 바뀐 옛 주문은 옛 동작 ④ R6 은 "같은 출처" 이지 "맞는 날짜" 가 아님(정본은 JSONB).
- 남은 것: 운영 반영(지시 때) · 시공 탭(§13) · 출고 탭(§14) 모양 선택 · 갤럭시 탭 실기기 검수(사용자) · 운영 생산팀 계정(사용자).

## 26. 운영 반영 9차 · 실측 (2026-11-11, PR #808 — 사용자 "운영에 올리고 실측")
- 스테이징 문서 푸시 33: deploy 8ac7562f7 → d9af01cb4(빠른 길 3,708 PASS, CI 3종 초록). 코드 커밋 8ac7562f7 CI 4종 초록.
- **운영 PR #808 → ab7fd3be0**: 승격 가지 `promote/tablet-tidy-d22`(이 세션 커밋 5개 = 코드 e22db669b · 1fa0792ee · 8ac7562f7 + 문서 b8af04006 · d9af01cb4, `AI_STATUS.md` 는 `--ours`). 파일 내용 대조: 내 파일 13개 모두 운영 = 내 바탕. 승격 트리 APP_OK · scan 3종 변화 없음 · 관련 시험 1,309 · smoke 17,282 + harness 174 → 검사 4개 통과 → merge → 운영 healthz ab7fd3be0(40초) · drift 일치.
- **운영 실측(사용자 요청 1회, claude_master 잠금 해제 → 읽기만 → 재잠금 `is_active=False` 확인 · 로그아웃 302 ×2, 스테이징 연습 실행 먼저)**. `prod_v3_measure7.log` · `prod_tidy_measure1.log`. 4xx 0 · JS 오류 0 · 쓰기 단추 안 누름(페이지가 보낸 것은 `POST /api/foms/rum` 뿐). 시트 화면 두 주소(`/production/sheet/<id>` · `/production/tablet-sheet/<id>`)는 서버 쓰기가 없는 것을 코드로 먼저 확인.
  - 작업 시트(제작 대기 1 · 제작 중 1): 페이지 높이 100% · 150% · 긴 품목 모두 **800px**, 머리 줄 73px 한 줄, 가로 넘침 없음.
  - 옆 시트 머리 글과 닫기 단추 겹침: 100% · 150% 모두 **0**.
  - 곧 올 것 23줄: 번호 전부 칸 안. 150% 에서 긴 이름(이 브라우저 DOM 에 넣음)은 이름만 184px 말줄임 · 번호 보임.
  - **D22: "바뀐 것" 9 → 7**(받은함 제작 대기 8 → 6 · 재단 중 1 → 1), 큰 줄 빨간 테두리 28 → 20(미리 보기 겹침 포함). **오늘 장의 빨간 4줄은 그대로다** — 총괄이 질문 창에서 "오늘 제작 대기 6줄 중 4줄이 컨펌 때 변경 때문" 이라고 한 것은 확인 없이 한 추정이었고 틀렸다. 그 4줄은 `시공일 변경 미정 → 11/11` 3건(같은 발주사, 연속 번호) · `11/16 → 11/11` 1건으로, 생산으로 넘어온 뒤 시공일이 정해지거나 당겨진 것으로 보인다(생산팀이 알아야 하는 변경). 이벤트 시각을 직접 읽어 확인한 것은 아니다(마스터 계정은 요청 1건당 1회). 생산 진입 길은 코드로 다시 셈 — 엔진 명령 중 바깥에서 생산으로 들어오는 것은 `CUSTOMER_CONFIRM` · `PRODUCTION_START` · 일반 상태 변경(`STAGE_CHANGED`)뿐이고 강제 변경은 `STAGE_OVERRIDE` — 넷 다 바닥으로 센다.
  - 그대로: "전체 133건" · 탭 `날짜 | 내 공정 1 | 바뀐 것 7 | 찾기 | 보드` · 발주사·담당 78줄 전부 한 줄 · 잘림 0 · 첫 화면 1.2초.
- **남은 7건 원인 확인(사용자 "남은 7건 원인 확인" — 운영 계정 1회 더, 읽기만 · 재잠금 `is_active=False` 확인 · 로그아웃 302)**. `scratchpad/prod_d22_verify.py`(스테이징 연습 먼저) — 받은함 7건의 `/api/orders/<id>/events` 를 읽어 단계 이동 · 시공일 변경 시각만 견줌(`prod_d22_verify1.log`, 이름 · 번호 · 글 안 찍음).
  - 7건 모두 생산 진입 바닥이 선다 — **전부 `CUSTOMER_CONFIRMED` CONFIRM → PRODUCTION**(바닥 없음 0). `STAGE_CHANGED` 로 생산에 들어온 주문은 하나도 없었다(워커가 찾은 것이 운영 데이터로 확인됨).
  - 시공일 변경 알림 6건: 전부 생산 진입 **뒤**의 변경이 1건씩 있다(예: 진입 11-06 → 변경 11-10). 진입 전 변경이 있던 2건(1건 · 4건)은 그 부분이 가려짐 — D22 동작 확인.
  - 도면 알림 1건: 도면 이력 시각은 이벤트가 아니라 `structured_data` 에 있어 이 길로는 못 가름(같은 창을 쓰므로 코드상 진입 뒤). 그 주문의 진입 전 시공일 변경 1건은 가려짐.
  - 덧: 이 7건은 파이프라인 진입 `STAGE_CHANGED` 가 없어(도면 → 컨펌도 다른 이벤트) 옛 기준선이 이미 `erp_stage_updated_at`(= 생산 진입 시각)이었다. 즉 운영에서 R12 가 실제로 문 것은 2건(9 → 7)이고, 코드 읽기로 적은 "한꺼번에 뜬다" 는 운영에서는 드문 길이었다.
- 교훈: 결정 질문에 넣는 근거는 확인한 것만. 운영 숫자의 원인을 추정으로 말하지 말고, 모르면 "원인은 아직 안 봤다" 고 적는다.
- 남은 것: (원하면) 남은 7건의 이벤트 시각 확인 · 시공 탭(§13) · 출고 탭(§14) 모양 선택 · 갤럭시 탭 실기기 검수(사용자) · 운영 생산팀 계정(사용자).

## 27. 출고 탭 다시 — 메인 미션은 출고 스케줄 짜기 (2026-11-11, D23 · D24)
- 시공 탭 첫 화면 모양: 사용자 "시공 탭은 더 미룰게요" — §13 시안 그대로 보류(D16 팀 칸만 확정).
- **D23(사용자)** "출고탭은 다시 목업 만들어야 돼 > 출고 작업은 생산에서 다 준비 해 > 출고 탭의 메인 미션은 출고 스케쥴을 짜는거야" — §14 시안 3개(생산팀 포장 · 상차 화면)는 전제가 틀려 버린다. 총괄이 persona 를 가정해 그렸다가 틀린 두 번째(첫 번째는 D17).
- **D24(사용자, 질문 창)** 스케줄 짜기에서 정하는 것 = 누가 가는지(팀 · 차 배정) · 몇 시에 어떤 순서로 · 어느 날 나갈지(날짜 옮기기) · 협력사 희망일 확정, 넷 다. "보통 오전/오후 2타임으로 시공 진입한다. 한 집에 제품이 많으면 여러 명의 시공자가 배정될 수 있다." 짜는 사람 = 출고 담당, **권한은 출고 · 관리자 · CS 팀**.
- 지금 화면 사실 조사(워커 opus, 읽기 전용 — 총괄이 실화면 `shots/staging_ship/ship_land.png` 와 견줌)
  - 출고일이 따로 없다 — 출고는 시공일 그날(`foms/web/shipment/dashboard.py:416-425`). 주문에 저장하는 것은 `sd.shipment` 의 `construction_workers`(최대 10명) · `construction_time`(글 200자) · `site_extra`(색 메모) 셋뿐(`foms/services/shipment/writer.py:36-40`). 차 · 순서 · 출고 확정 칸은 없다.
  - 시간 칸이 둘로 갈려 있다: `sd.schedule.construction.time`(오전/오후/종일 — 시공일 API · 협력사 판) vs `sd.shipment.construction_time`(배정 시트의 09:00 같은 글). 태블릿 표는 뒤쪽만 보인다.
  - 용량은 시공자 한 사람마다(`construction_workers[{name, capacity, off_dates}]`, 기본 10 — `erp_shipment_settings.py:99-133`), 하루 용량 = 쉬지 않는 사람의 합(처음 데이터 16명 · 190). 넘쳐도 경고만(`shipment_read_model.py:159-160`).
  - 쓰기 권한이 엇갈린다: 배정(`POST /api/erp/shipment/update/<id>`)은 `erp_edit_required` = ADMIN · CS · SALES 만 → **출고팀은 403**, 협력사 희망일 확정 · 되돌리기는 출고팀 STAFF · MANAGER 도 됨(`erp_permissions.py:366-397`). D24 대로면 배정도 출고팀에 열어야 한다.
  - 우리 주문의 날짜 옮기기는 출고 화면에 없다(주문 화면 `POST /api/orders/<id>/construction-schedule`, 바꾸면 도면 · 생산팀 알림). 끌어 놓기는 협력사 희망 판에만. [출고 확정] 단추는 동작 없음("백엔드 미구현", `dashboard_main.html:97-101`).
  - 태블릿 배정 시트는 시공자를 한 명만 고르고(PC 에서 넣은 여러 명을 덮음) 저장 뒤 페이지를 통째로 다시 읽는다. 버전 검사 값도 안 보낸다(`tablet-domain-sheets.js:459-488`).
  - 생산 단계와 출고는 데이터로 안 묶여 있다(단계로 거르지 않음). 금액 칸은 없다. 글자 손잡이는 PC 머리줄에만 있고 태블릿은 그 머리줄을 숨긴다.
- 새 시안 3개(워커 opus 가 그림, `docs/design/mockups/tablet-shipment-schedule.html`): 안 1 2주 띠 + 그날 판(오전/오후 묶음 + 시공자 현황) · 안 2 한 주 판(날짜를 옆으로 나란히, 아래 정하기 줄) · 안 3 정할 것부터(할 일 줄 + 정하기 화면). 셋 다 포장 · 상차 단추 없음 · 금액 없음 · 글자 손잡이.
- 시안 렌더(`scratchpad/shot_ship_sched.py`, 1280×800 틀 셋): 틀 밖 넘침 0 · "…" 로만 보이는 칸 0 · 12px 미만 글자 0 · 페이지 가로 넘침 0(1340 · 390폭). 총괄이 그림 3장을 직접 봄. 지어낸 숫자는 세 안이 서로 맞음(아직 안 정한 것 5 · 협력사 희망일 3 · 시공일 바뀜 2).
- **시안이 실제와 다른 점(총괄 확인)**: ① 시안은 6팀 · 하루 6~7건인데 운영은 하루 시공 6~19건(11-11 실측 띠) · 설정의 시공자 16명쯤(용량 합 190) — 안 2(한 주 판)는 실제 양에서 칸이 넘쳐 칸 안을 밀어 봐야 한다. ② 시안은 두 팀이 간 집의 자수를 반씩 나눴지만 지금 코드는 **팀마다 전부** 뺀다(`foms/web/shipment/dashboard.py:351-359`) — 사용자에게 물을 것. ③ 용량은 하루 하나(오전/오후 따로 아님) 그대로.
- 다음: 사용자 선택(안 1·2·3, 자수 세는 법) → 설계서(권한 D24 · 날짜 옮기기 · 시간 칸 하나로 · 시공자 여러 명 · 버전 검사) → 승인 → 구현. 쓰기 권한 · API 가 바뀌는 코어 변경이라 Spec 먼저.
- 푸시 36: deploy 30570cdcd → **a57c47dee**(시안 + 원장 §27). smoke 17,342 PASS. FOMS CI · PG Lane 초록, **Harness CI 실패는 내 커밋 탓이 아님** — 바로 앞 다른 창 커밋 30570cdcd 가 `foms/services/order_payment_sync.py` 를 520줄로 키워 500줄 래칫에 걸림(그 커밋 자체의 Harness CI 도 실패). 남의 파일이라 손대지 않고 사용자에게 알림.
- **사용자 선택(11-11 질문 창)**: 모양 = "상관없음" → 총괄 추천 **안 1(2주 띠 + 그날 판)** 으로 진행(실제 양 — 하루 6~19건 · 시공자 16명쯤 — 에서 아래로 내려 보면 되는 틀, 생산 첫 화면과 같음). **D25 자수 세기 = 반씩 나눠 셈**(한 집에 여러 명이면 사람 수로 똑같이 나눔 — 지금은 사람마다 전부 뺌).
- 설계서 §14 초안: 사실 조사한 워커에게 이어 맡김(코어 변경 — 권한 · 쓰기 API · 용량 계산 — 이라 Spec → 승인 → 구현).
- **사용자가 안 1~3 을 물림(11-11)**: "PC 출고 탭 스타일로 네가 좀 더 창의적으로 해서 시안을 3종 더" → 총괄이 PC 표 느낌의 새 방식 셋(도장 찍는 출고표 · 시공자 시간표 · 한 장 출고표)을 글로 알리자 **"마음에 안 드니까 PC 출고 탭 스타일을 네가 좀 더 개선해서 출고 담당자의 persona 로 다시 시안을 3종 더"** — 새 방식이 아니라 **매일 쓰는 PC 출고 탭을 바탕에 두고 다듬은 화면**을 원함(전례: 새 그림 · 칩 · 요약 상자는 "복잡 · 시인성 낮음" 으로 거절). 도장 · 시간표 · 한 장 안은 그리다 버림(파일 지움). 위 "안 1 로 진행" 은 무효, 설계서 §14 초안도 쓰지 않음(워커가 인터럽트에 멈춤 — 모양이 정해진 뒤 다시).
- PC 출고 탭 실화면을 스테이징에서 찍어 봄(`scratchpad/pc_ship_shot.py`, 1700×950, 6/29 20줄): 위 줄(검색 · 기준 날짜 · [조회] · [AS일정 추천] · 글자 손잡이 · [컬럼 폭 초기화] · 파란 [이미지 저장] · [설정]) → 빨간 "시공일이 변경된 건" 띠 → 왼쪽 "날짜별 시공"(파란 건수 동그라미 · 주말 노랑) + "날짜별 잔여 시공" → 표 10칸(상세 · 고객 · 대리점 · 제품 · 규격(W/300) · 현장주소 · 시공시간 · 도면담당자 · 시공자(회색 고치는 칸) · 담당자).
- **새 시안 3개 `docs/design/mockups/tablet-shipment-schedule-pc-improved.html`**(워커 opus, 총괄 설계): 셋 다 PC 뼈대 그대로(위 줄 · 빨간 띠 · 왼쪽 날짜별 시공 + 오른쪽 표), 막대 · 색 이름표 없이 글자와 숫자만(넘치면 숫자 빨강), 칸 순서는 출고 담당이 보는 순서 `시간 → 어디 → 누구 → 무엇 → 자수 → 시공자 → 현장 메모`, 자수는 사람 수로 나눔(D25).
  - **안 7 지금 출고표 그대로, 잘 보이게**: 날짜 목록 줄에 `자수 55.0 / 60 · 배정 2` 글자, 표는 오전/오후 소계 줄 + 정렬 `시간순 | 시공자별 | 지역별`, 줄을 누르면 그 아래 정하기 줄(시공자 단추 + 남은 자수 · 오전/오후 · 다른 날로 · 메모 · [저장]), 표 맨 아래 시공자별 합계 한 줄.
  - **안 8 시공자별 출고표**: 표를 시공자 묶음으로(머리줄 `박성민 (큰 조) · 2집 · 11.1 / 20 · 남 8.9`, 넘치면 빨강), 맨 위 빨간 "배정 필요" 묶음, 고른 줄은 아래 흰 띠에서 정함.
  - **안 9 2주 표 + 그날 출고표**: 왼쪽을 `날짜 | 오전 | 오후 | 자수/용량 | 남은 사람 | 배정 | 옮기면` 요약표로 키움, 오른쪽 표에서 집을 체크하고 왼쪽 날을 눌러 옮김(옮긴 뒤 자수를 미리 보임), 아래 협력사 희망일 표.
  - 렌더(`scratchpad/shot_ship_sched_pc.py`): 틀 밖 넘침 0 · "…" 칸 0 · 13px 미만 글자 0 · 페이지 가로 넘침 0. 총괄이 그림 3장을 직접 봄. 워커가 덜어 낸 것: 위 줄 숫자 세 칸(같은 내용이 빨간 띠 · 목록에 이미 있음).
- 푸시 37: deploy fe9848d3f → **181820c73**(안 7~9 + 원장). smoke 17,342 PASS, CI 3종 초록(다른 창이 `order_payment_sync.py` 를 479줄로 줄여 Harness CI 도 초록).
- **D26(사용자, 11-11 — 안 7~9 도 물림)** "다 마음에 안들어. 출고는 시공자 배정이 핵심이야. 심플하고 직관적인 ui. 출고스케쥴 담당자 persona 로 깊게 고민하고 목업제작. as스케줄도 같이 짜는거 잊지마". 세 번 틀린 까닭(총괄 반성): 매번 **주문 줄이 주인공이고 시공자는 그 줄의 칸 하나**였다(안 1~3 카드 · 안 7~9 표). 날짜 옮기기 · 협력사 희망일 · 만드는 상태 · 정렬 · 합계 · 변경 띠를 한 화면에 같이 올려 무엇이 핵심인지 안 보였다. AS 는 "AS 추천 단추" 로만 다뤘다.
- 다시 잡은 persona: 담당자의 머릿속에는 표가 아니라 사람이 있다 — "내일 누구를 어디로 보내지?". 시공자는 하루 오전 한 집 · 오후 한 집(2타임), 큰 집은 두 사람이 함께, AS 도 같은 사람이 시공 가는 길에 들른다(그날 잡힌 AS + 날짜 없는 AS). 확인할 것은 셋: 안 정한 집 · AS 가 없는가 / 넘친 사람이 없는가 / 누가 비었는가. 다 되면 출고표를 보내고 끝.
- 4차 시안 방향(`docs/design/mockups/tablet-shipment-assign.html`, 워커가 그리는 중): **시공자가 주인공**, 큰 덩어리 셋 이하(위 줄 · 배정할 것 · 시공자 판), 색 셋(파랑 · 빨강 · 주황 AS), 집 한 덩이 = 동네 · 고객 · 자수뿐, 위 줄 = 날짜 넘기기 · `남은 집 n · AS n` · [출고표 보내기] 뿐. 날짜 옮기기 · 협력사 희망일은 뒤로(작은 글 한 줄). 안 10 시공자 판(줄 = 사람, 칸 = 오전/오후) · 안 11 시공자 카드(사람마다 한 장) · 안 12 집 줄 · 사람 줄.
- 4차 시안 렌더(`scratchpad/shot_ship_assign.py`): 틀 밖 넘침 0 · 잘린 글 0 · 13px 미만 글자 0 · 페이지 가로 넘침 0. 총괄이 그림 3장을 직접 봄 — 셋 다 덩어리 셋 이하 · 집 덩이 = 동네 · 고객 · 자수 · 색 셋. 지어낸 사람 10명(실제 설정은 16명쯤 — 안 10 은 줄을 46px 로 줄이면 16명이 한 화면, 62px 면 아래로 조금 밀어 봄). 워커가 더한 것: 고른 집을 넣으면 넘치는 사람 칸의 "여기" 옆에 빨간 `넣으면 넘침`. 열린 질문: AS 를 그 사람 하루 자수에 셀지(시안은 안 셈).
- **안 10~12 도 물림(11-11, "이번에도 아니에요")**. 무엇이 아닌지 물었으나 답 없음("상관없음"), AS 는 **"AS 전담 기사가 있고, 간간히 시공팀이 AS 도 간다"**. 이어 사용자가 **엑셀 "출고일지" 그림**을 보내며 **"이 엑셀표를 참고로 PC 출고 스타일을 만들었어. PC 출고의 동작 프로세스, 함수 등도 파악해서 생각해서 목업 만들어"**(D27). 그림에는 실제 고객 이름 · 전화 · 주소가 있어 저장소 · 문서 · 워커에게 옮기지 않고 구조만 적는다.
  - 출고일지 구조: 제목 "YYYY년 M월 D일 출고일지", 칸 `번호 | 대리점 | 제품명 | 규격 | 현장주소 | 고객 연락처 | 시공시간 | 영업 담당자 | 시공자`, 한 줄 = 한 건, **줄이 시공자 순으로 모임**(한 사람 2~3줄), 전부 가운데 맞춤 · 검은 금. **AS 줄 = 대리점 칸 "AS" + 대리점~현장주소 주황 바탕**, 규격 칸에 할 일 — 시공자 묶음 안의 AS(시공시간 칸에 "원시공자 ○○")와 **맨 아래 AS 전담 기사 한 사람의 AS 5줄**("오전 일찍" · "4시 이전"). 파란 표시 칸(제품명 · 규격 · 주소, 규격에 "낮은 …")과 분홍 줄(먼 지방, 시공자 칸에 지역 이름). 그날 26줄(시공 20 + AS 6), 시공자 14명쯤.
  - 총괄이 네 번 틀린 까닭(확정): 출고 담당자에게 화면은 **출고일지 한 장**이고 일은 **맨 끝 시공자 칸을 채우는 것**인데, 표를 버리거나(안 1~3 · 10~12) 표에 딴것을 얹었다(안 7~9). persona 를 내 머리로 지어내지 말고 **그 사람이 지금 쓰는 종이부터 달라고 했어야** 한다.
- **PC 출고 탭 동작(총괄이 코드로 확인 — `static/js/shipment/shipment-dashboard.js` 1,409줄)**: 시공자 · 시공시간 · 도면담당자 칸은 글자 입력 + [불러오기] 목록(`showSavedDropdown` — 시공자는 이름 옆에 그날 맡은 건수 `getAssignedWorkerCountMap`), 여러 명은 칸 안에 줄 추가(`buildShipmentTextRow`). **칸을 벗어나면 바로 저장**(`saveShipmentField` → `POST /api/erp/shipment/update/<id>`, 주문 · 칸별 대기 줄 `runQueuedShipmentSave`), 저장 뒤 **줄이 다시 정렬되고 시공자 칸이 사람마다 다른 옅은 색**(`applyShipmentWorkerSortAndColors` — AS 여부 → 첫 시공자 → 담당자 → 주문 번호, `PASTEL_COLORS`). 시공시간 미리 값 둘 "오전 8시" · "오후 1시"(2타임). 현장 메모는 색 고르는 줄(`site_extra`). [AS일정 추천] 은 그날 출고 건마다 근처의 날짜 없는 AS 를 창에 띄워 반영/취소(`loadRecommendations` · `postApply` · `postCancel`). [이미지 저장] 은 화면 값으로 번호 칸을 붙인 깨끗한 표를 새로 그려 `시공일정_날짜.png`(`image-export.js` — 시공팀에 보내는 출고일지). 화면 표의 AS 줄은 제품 칸에 분홍 테두리 상자 + 빨간 AS 딱지(엑셀의 주황 줄과 다름). "AS 전담" 을 따로 다루는 코드는 없다.
- 5차 시안(`docs/design/mockups/tablet-shipment-daily-sheet.html`, 워커가 그리는 중): **엑셀 출고일지 그대로**(제목 · 칸 순서 · 가운데 맞춤 · 검은 금 · 주황 AS · 파랑 · 분홍), 표 밖은 위 줄 하나, **누르는 곳은 시공자 칸뿐**(없으면 빨간 점선 "누르기", 있으면 PC 처럼 사람 색), 누르면 바로 저장 · 줄이 시공자 순으로 모임, 맨 아래 주황 점선 "＋ 날짜 없는 AS n건". 다른 것은 이름을 어디서 누르나 하나 — 안 13 칸에서 뜨는 이름판 · 안 14 오른쪽 시공자 줄 · 안 15 아래 시공자 띠(+ AS 넣기 서랍 연 모습).
- 푸시 38 은 안 올라감: smoke 가 `tests/contracts/runtime/test_db_leak_trace.py::test_closed_session_is_silent` 1건으로 실패(`smoke_push38.log` SMOKE_EXIT=1 — 문이 막아 푸시 안 됨). 내 커밋(시안 HTML + 원장)과 무관: `install_db_leak_trace` 가 죽은 엔진의 `id()` 를 `_installed_engines` 에 남겨 두어 새 엔진이 같은 번호를 받으면 `False` 를 돌려주는 **번호 재사용 흔들림**(다른 세션 모듈 — 손대지 않고 사용자에게 알림). 덤: Git Bash 에서 `cd /c/tmp/…` 뒤 그 파일만 따로 돌리면 `_ROOT` 가 소문자 `c:\` 로 잡혀 `checkout_at=-` 로 늘 실패(드라이브 글자 대소문자) — 내 셸에서만 나는 일.
- **D28(사용자, 11-11 — 5차 시안을 그리는 중에)** "as내용은 주절주절 표현할필요없이 as 건 누르면 as정보를 as탭에서 받아 모달또는 drawer방식으로 보여주면될듯" · "스케줄 표 스타일을 심플하게 지키고 세부정보는 클릭 또는 터치 시 띄워주면 될 듯". → 표는 출고일지 칸 이름 · 순서 그대로 두되 칸 안 글을 줄임(AS 는 규격 칸에 한 마디, 품목 여럿이면 `외 n` + 합친 자수, 주소는 아파트 이름까지, 고객은 이름만), **줄을 누르면 오른쪽 서랍에 세부정보**(주소 전체 · 전화 · 품목 · AS 는 AS 탭의 접수 내용 · 사진 · 기록 + [AS 탭에서 열기]). 시공자 칸만 예외(이름 고르기). 워커에게 덧붙여 지시 — 안 15 는 AS 줄을 누른 "AS 정보" 서랍 모습으로.
- **지금 상태(11-11 밤, 컨텍스트 정리 전 기록)**: 운영 = PR #808 까지(ab7fd3be0 뒤 다른 세션 커밋 포함). deploy = 181820c73(안 7~9 까지 올라감). **로컬에만 있는 것**: 커밋 7fc17aa19(안 10~12 `tablet-shipment-assign.html` + 원장) — smoke 가 남의 흔들리는 시험으로 실패해 아직 안 올림, 그리고 커밋 안 한 원장 덧글(D27 · D28 · PC 동작 조사). 워커 `ship-mock` 이 `docs/design/mockups/tablet-shipment-daily-sheet.html`(안 13~15) 을 그리는 중 → 나오면 총괄이 그림(`scratchpad/mock_shots/sheet_a13~15.png`)을 직접 보고 → 커밋(시안 + 원장) → smoke → 푸시 → 사용자에게 그림 3장 + 질문(모양 선택). 고른 뒤: 설계서 §14(권한 D24 출고 · 관리자 · CS, 자수 사람 수로 나눔 D25, AS 전담 · 세부 서랍 D27 · D28, 날짜 옮기기 · 협력사 희망일은 뒤로) → 승인 → 구현. 시공 탭은 보류.
- **5차 시안 렌더 결과(11-11, 워커 opus · 총괄이 그림 3장 직접 확인)**: `docs/design/mockups/tablet-shipment-daily-sheet.html`(308줄, 지어낸 이름 · 주소만). 세 안 모두 표는 출고일지 그대로(제목 · 칸 9개 순서 · 검은 금 · 주황 AS · 파랑 · 분홍 · 시공자 칸 사람 색)이고 줄 높이 46px 한 줄 — 제품명은 첫 품목 + `외 n`, 규격은 합친 자수 한 숫자, AS 규격은 한 마디(`레일 교체` · `경첩 조정`), 주소는 아파트 이름까지, 고객은 이름만. 넘침 0 · 잘린 글 0 · 13px 미만 글자 0 · 가로 넘침 없음(워커 측정), 1280×800 에서 안 13 · 14 는 14줄, 안 15 는 13줄. **안 13** = 시공자 칸을 누르면 칸 옆에 이름판(사람마다 그날 건수 · 자수, 쉬는 사람 흐림, AS 전담 따로, [직접 쓰기] · [비우기]) · **안 14** = 오른쪽에 시공자 줄이 늘 보임(줄 누르고 이름 누르기) · **안 15** = 아래에 시공자 띠 + AS 줄 ⑫ 를 누른 모습(오른쪽 340px `AS 정보` 서랍 — `AS 탭에서 가져온 내용` · 접수 내용 · 접수 며칠째 · 사진 자리 2 · 지난 기록 · [AS 탭에서 열기] · [전화]). 세부 서랍(D28)과 주황 점선 `＋ 날짜 없는 AS` 줄 · [AS 넣기 4] 는 세 안 공통. 알려 둘 것: 안 15 서랍은 표 위에 얹혀 열려 있는 동안 오른쪽 칸(시공자 포함)을 가린다. 열린 질문: 이름을 어디서 누를지(칸 옆 이름판 / 오른쪽 줄 / 아래 띠) · 분홍(지방) 줄 시공자 칸에 지역 이름을 쓸지 사람을 고를지 · AS 를 그 사람 하루 자수에 셀지.
- **D29(사용자, 11-11 — 5차 시안을 보고)** "다 맘에 안들어 너무 엑셀 스타일이야 / 스타일을 좀 주고, 본문의 주황 파랑컬러는 다 빼" · "같은 시공자끼리 색상 들어가서 묶이는것만 놔둬". → 뼈대(하루치 한 장 · 칸 9개 순서 · 한 줄 = 한 건 · 시공자 순 · 시공자 칸 누르기 · 줄 누르면 서랍)는 그대로 두고, **엑셀 생김새**(검은 격자선 · 회색 머리칸 · 전부 가운데 맞춤 · 글자 띄운 제목 줄)와 **본문 칠**(AS 주황 · 파랑 · 분홍)을 버린다. 남기는 색은 **시공자 칸의 사람 색 묶음** 하나. 5차 질문 창 두 개(이름 누르는 곳 · 세부정보 창)는 답 없이 닫혀 권고안(칸 옆 이름판 · 오른쪽 서랍)으로 둠. 색 질문 창도 답 없이 닫혔고 사용자가 채팅으로 직접 적음 — 질문 창보다 채팅 글이 답이다.
- **6차 시안(11-11, 워커 opus · 총괄이 그림 5장 직접 확인)**: `docs/design/mockups/tablet-shipment-styled-sheet.html`(지어낸 이름 · 주소만, 5차와 같은 14줄). 공통: 위 줄(날짜가 제목 · `14건` · 알약 `시공자 없음 3` · [AS 넣기 4] · [이미지 저장]), 표는 세로 선 없이 가는 가로 선만 · 왼쪽 맞춤 · 제품명과 규격이 굵게, AS 는 대리점 칸의 검은 `AS` 딱지 하나, 시공자 없는 칸은 빨간 점선 `＋ 시공자`, 같은 시공자 줄은 시공자 칸 색 덩어리가 위아래로 붙어 한 덩어리, 맨 아래 `＋ 날짜 없는 AS 4건 — 이 날에 넣기`. **안 16 가는 줄**(흰 카드 하나 · 줄 45px · 14줄 다 보임) · **안 17 시공자 묶음 카드**(묶음마다 카드 · 13줄) · **안 18 줄 전체 옅은 색**(줄 바탕에 사람 색 22%) + 안 16 누른 모습 둘(② 시공자 칸 이름판 · ⑫ AS 줄 `AS 정보` 서랍). 워커 측정: 다섯 장 넘침 0 · 잘린 글 0 · 13px 미만 0 · 가로 넘침 0. 설계와 달라진 것: 줄 높이 46 → 45(14줄을 한 화면에), 규격 칸 84 → 92(`손잡이 교체` 가 안 들어가서).
- 푸시 39: deploy 181820c73 → **f1321697c**(5차 시안 + 원장, 7fc17aa19 · 62e5c0ebd 포함). smoke 17,357 PASS(`smoke_push39.log` SMOKE_EXIT=0 — 푸시 38 의 흔들리는 시험은 이번엔 통과). f1321697c 의 FOMS CI 는 다른 창의 뒤이은 푸시로 취소됨 → 그 커밋을 포함한 19dcb2f91 에서 FOMS CI · PostgreSQL Lane · Harness CI 모두 초록.
- **D30(사용자, 11-11 질문 창)** 6차 시안 모양 = **"안 17 시공자 묶음 카드"**. 6차 시안 푸시 40: deploy → **a6c5e468a**(smoke 17,357 PASS · CI 3종 초록 · 스테이징 배포 일치).
- **설계서 §14 초안(11-11, 승인 대기)**: 워커(opus)가 서버 쪽 사실 11항목을 조사, 총괄이 권한 · 자수 계산 · 태블릿 그리드 · 시트 · AS 넣기 머리말을 코드로 확인. 뼈대: 주소 · 줄 · 저장 API 는 그대로 두고 `tablet_ship_grid.html`(6칸 → 9칸 묶음 카드)과 `tablet_sheet.html`(세부 서랍)만 바꿈 + 이름판 JS + 출고팀 쓰기 열기(`erp_edit_required` 가 정책 `SHIPMENT_EDIT` 보다 좁아 출고팀 403 이던 것) + 자수 나누기(D25, PC 잔여 숫자도 바뀜). 구현 전 확인 3건(AS 넣기 뒤 이름 표시 · 출고팀의 AS 조각 읽기 · 숨은 PC 표의 이미지 저장)은 설계서 §14.7.
- **설계서 §14 승인 · D31(사용자, 11-11 질문 창)**: 설계 = **"이대로 만들기"**, 영업팀 권한 = **"영업팀은 막기"**(출고 · 관리자 · CS 만 고침, 영업팀은 PC 포함 보기만). 설계서 초안 푸시 41: deploy → **0efcf0cbd**(smoke PASS · CI 3종 초록 · 스테이징 배포 일치). 구현 순서 P14-1(권한) · P14-2(집계 · 자수 나누기) → P14-3(표 · 이름판) → P14-4(서랍) → P14-5(AS 넣기 · 이미지 저장).
- **P14-1 · P14-2 구현(11-11, 워커 opus 둘 동시 · 총괄이 diff 와 시험 362개 직접 확인)**
  - P14-1 권한: `can_edit_shipment`(관리자 · CS팀 · 출고팀 STAFF · MANAGER) + `shipment_edit_required` 를 `erp_permissions.py` 에. 배정 저장 API 와 AS 추천 4종의 문지기를 이것으로 바꿈. **워커가 물어 온 것(총괄 결정)**: 정책 `SHIPMENT_EDIT` 는 물류 상태(`field_update.py:485`) · logistics 전이(`production/orders.py:1771`) · 변경 확인(change-ack) · 보관(`storage.py:136`) 네 곳도 같이 써서, 팀 목록을 직접 바꾸면 영업팀이 그 네 곳까지 막힌다 → D31 은 출고 탭 배정만의 결정이므로 **새 정책 `SHIPMENT_ASSIGN`**(CS · SHIPMENT, 문지기 = `can_edit_shipment`)을 만들어 5개 API 만 옮기고 `SHIPMENT_EDIT` 는 그대로 둠. 매니페스트는 만드는 도구가 없어 그 5줄만 고침. 화면 값: `can_edit_shipment` 는 라우트가 헬퍼에서 넘김(템플릿 안 계산 삭제), 주문 수정 링크 · 시공일 변경 [확인] 은 옛 판정 그대로 `can_edit_order_here`(안 나누면 영업팀이 쓸 수 있는 링크를 잃고 출고팀에게 저장 안 되는 링크가 생김). 영업팀에게 닫히는 곳 = PC 출고 표 편집 칸 · AS 추천 · 모바일 줄 수정 · 태블릿 시트 [배정 적용]. 새 시험 54개(헬퍼 팀 줄을 옛 규칙으로 되돌리면 12개 실패).
  - P14-2 집계: 새 순수 함수 `foms/services/shipment/tablet_day_sheet.py` `build_tablet_day_sheet`(묶음 = 시공자 없음 → 설정 순 → 그 밖 이름 순, 묶음 안 AS 뒤, 번호 이어짐, 사람별 `건수 · 자수` — 자수는 줄 자수 ÷ 시공자 수, AS 는 건수만, 넘침 · 쉬는 날, 사람 색 번호). `compute_team_remaining_units_for_date` 도 나눠 셈. 새 시험 14개(나누기를 되돌리면 5개 실패). 아직 라우트 · 템플릿에 잇지 않음(P14-3).
  - **총괄이 틀린 것**: 승인 질문에 "PC 출고 탭의 남은 자수 숫자도 같이 바뀐다"고 적었으나 틀림 — 그 함수를 부르는 곳은 태블릿 시트뿐이고 PC 패널은 날짜별 합계(`compute_shipment_panel_aggregates`)라 안 바뀐다. 사용자에게 바로잡아 알렸고 설계서 §14.3 을 고침. 또 사람 색 번호는 묶음 순서라 PC(이름 순)와 다를 수 있음(설계서에 적음).
  - 남은 걸림: 시공일 변경 [확인] 단추는 출고팀에게 원래부터 안 보임(API 는 통과) — 이번 범위 밖.
- **P14-3 구현 · 스테이징 실측(11-11, 워커 opus · 총괄이 코드 · 그림 · 실화면 확인)** — 커밋 05c88e63e(rebase 뒤 **b9492208f**), 푸시 43: smoke 17,457 PASS · CI 4종 초록 · 스테이징 배포 일치.
  - `tablet_ship_grid.html` 9칸 묶음 카드, `tablet-ship-assign.js`(296줄) 이름판, `tablet-day-sheet.css`(문지기 안에만), 옛 6칸 · KPI 4칸 규칙 삭제, 라우트가 `build_tablet_day_sheet` 를 넘김. 시공자 칸은 `<button>` 이라 `tablet-side-sheet.js` 가 줄 누름으로 안 본다(그 파일 무수정). 다시 받기 = `FOMS_ERP_SHELL.navigateByShell(…, {bypassCache:true})`.
  - 실화면(`scratchpad/ship_day_check.py`, 1280×800 터치, 스테이징 6/1 장 19줄): 머리 9칸 순서 일치 · 카드 6 · 시공자 칸 단추 19(없음 14) · `AS` 딱지 6 · PC 표 숨음 · 본문 칠 0 · 가로 넘침 0. 이름판 화면 안(17명) · 줄 누름 → 시트 428px. **실제 저장**(시공자 없는 줄에 이름 넣기 → 비우기): `POST /api/erp/shipment/update/<id>` 2번, 둘째 저장이 첫 응답의 버전으로 통과(409 없음), 닫으면 다시 받아 원래대로(없음 14 그대로). 화면 오류 0 · 4xx 0.
  - 시험 도구 함정: 긴급 알림 창 DOM 을 지워도 `foms-urgent-alert.js` 의 키 가두기는 남아 Esc 가 먹지 않는다 → `/erp/api/notifications/pending-urgent` 를 빈 응답으로 바꿔 놓고 재야 한다. 스테이징 출고 데이터는 2026-06 근처에 있다(오늘 날짜엔 0줄).
  - 본 것: 표 폭 890px(왼쪽에 예전부터 있던 `날짜별 남은 자수` 띠 260px — 시안에는 없었음)이라 주소 209px · 제품명 142px 로 잘림. 시공일 변경 배지가 붙은 줄은 높이 91px, 그 [확인] 글자 12.16px.
- **D32(사용자, 11-11 질문 창)** 왼쪽 날짜 띠 = **"단추로 여닫기"**. 평소엔 숨기고 위 줄 [날짜별 남은 자수] 단추로 여닫음(연 상태는 그 태블릿에 기억). 구현: `tablet-ship-capstrip.js`(50줄) · 띠는 뿌리에 `is-ship-cap-open` 이 붙었을 때만 보임 · [확인] 글자 13px. 닫힌 표 폭 1150px(주소 270px).
- **P14-4 세부 서랍(11-11, 워커 opus)**: `tablet_sheet.html` 을 세부정보 서랍으로 — 고객 · 전화([전화 걸기]) · 주소 전체([지도]) · 대리점 · 영업 담당 · 품목 전부(이름 · 규격 · 자수) · 시공자(읽기 + `시공자는 표의 시공자 칸에서 골라요`) · 시공시간(`오전 8시` · `오후 1시` · 직접 + `영업 메모: 오전`) · 현장 메모 · [저장]. 팀 라디오 · [배정 적용] 삭제. **저장은 시간 · 메모만 보내고 `construction_workers` 는 안 보낸다**(이름판에서 고친 값을 덮지 않게 — 되돌리면 시험 실패). 단추 이름을 `shipment-save` 로 바꿈(옛 JS 를 띄워 둔 태블릿이 새 서랍에서 빈 시공자를 보내 지우는 것을 막음) + JS 핀을 그 파일이 실리는 네 곳에서 같이 올림. AS 줄이면 `AS 정보`: 접수일 · 접수 원문은 서버가 바로, `AS 탭 기록` 은 `/erp/as/timeline/<id>?readonly=1` 조각을 시트가 열린 뒤 불러 붙임(`tablet-ship-sheet.js` 116줄, 실패 문구 · [다시 불러오기]), 붙인 조각의 비용 칸은 지움(D7), [AS 탭에서 열기]. 팀별 잔여 계산은 이 라우트에서 더 안 부름.
  - 참고(남의 것): `tests/performance/test_mine_trgm_index_contract.py` 를 혼자 돌리면 `no such table: system_settings` 로 1건 실패 — 깨끗한 origin/deploy(60711132a) 사본에서도 같음(전체 시험에서는 통과). 내 변경과 무관.
- **P14-4 스테이징 실측 · P14-5(11-11)** — 푸시 44: deploy → **fa67b29bb**(smoke PASS · CI 4종 초록 · 스테이징 배포 일치).
  - 실화면(`scratchpad/ship_day_check2.py`, 스테이징 6/1 장): 날짜 띠 평소 숨음(표 1150px · 주소 칸 270px) → 단추로 열면 890px · 새로 고쳐도 열린 채 → 다시 닫힘. 일반 줄 서랍: 전화 1 · 지도 1 · 라디오 0 · 단추 `오전 8시`/`오후 1시`/`직접`/`취소`/`저장` · 금액 0 · 최소 글자 13px · 넘침 0. AS 줄 서랍: `AS 정보` · AS 탭 기록 불러 붙음 · [AS 탭에서 열기] · 쓰기 칸 0 · 금액 0. 화면 오류 0 · 4xx 0. 본 것: AS 기록 안 최소 글자 11.52px.
  - P14-5(워커 opus): 불러 붙인 AS 기록 글자를 출고 서랍 안에서만 13px 이상으로(AS 탭 CSS 무수정, 재 측정 최소 13px). 태블릿 위 줄 = `40 48 56` · [날짜별 남은 자수] · [AS 넣기](기존 AS 추천 창 그대로, 글자만) · [이미지 저장](`js-shipment-export-trigger` → 기존 `image-export.js`). 늘 꺼져 있던 [출고 확정](서버 기능 없음)은 뺌. 숨겨진 PC 표에서도 그림이 만들어짐(지어낸 14줄로 내려받아 확인 — 줄 14 · 묶음 머리). 
  - **확인 못 한 것(설계서 §14.7 ①)**: AS 넣기(`apply`)는 ID 배정만 복사하고 AS 주문의 이름 배열(`construction_workers`)은 안 쓴다(`crew/assignments.py` `replace_workers` 확인). 추천 창의 `will_apply_workers` 는 출고건의 이름 배열을 보여 주므로, 넣은 뒤 AS 줄 시공자 칸이 비어 보일 수 있다(PC 도 같은 동작). 스테이징에서 넣기를 누르면 AS 일정이 실제로 바뀌어 누르지 않음 → 사용자 결정 필요(넣을 때 이름도 같이 넣게 고칠지).
- **D33(사용자, 11-12)** 운영 승격을 고른 뒤 "협력사 일정" → 질문 창 답 **"태블릿 목업에는 협력사 관련 기능이 없었는데, 목업 만들어봐"**. 운영 승격은 시안 결정 뒤로 미룸(승격 미리 점검만: 출고 탭 커밋 4개가 건드린 파일 38개 중 34개는 운영 판과 내용이 같고, 다른 4개 = 정책 매니페스트(남의 AS 도면 줄) · 원장 · 설계서(내 문서 커밋 미승격) · `layout_head.html`(남의 긴급 알림 핀) — 모두 내 변경과 다른 덩어리).
  - 사실(11-12): 협력사 희망 판(`partner_request_board.html`)은 `dashboard_main.html` 196~198줄, 시공일 변경 배너 바로 아래에서 **태블릿에도 PC 판 그대로** 그려진다(확정 대기 1건 이상일 때만, 태블릿 손질 없음 · 끌어 놓기는 HTML 끌기라 손가락으로 안 될 수 있음). 스테이징은 확정 대기 0건이라 판이 안 떠 실화면 확인 못 함(`scratchpad/prb_tablet_probe.py`, 오류 0 · 4xx 0 · 저장 0).
  - **7차(협력사) 시안** `docs/design/mockups/tablet-shipment-partner.html`(워커 opus · 총괄이 그림 7장 직접 확인 · 넘침 0, Artifact 비공개 게시): a0p 지금(PC 판이 표 위에 그대로 — 이름 단추 23px · 잘림 4 · 숫자 10.5px) · 안 19 위 줄 [협력사 희망 5] → 오른쪽 서랍 목록 → 정하기(날짜 7×2 · 남은 자수 · 시간 · 5초 되돌리기) · 안 20 표 위 낮은 한 줄 판(손가락 크기, 누르면 작은 창, 끌기 없음) · 안 21 표 그 줄 → 세부 서랍 맨 위 "시공일 정하기"(이대로 확정 · 다른 날로). 워커가 본 약점: 서랍이 표 오른쪽 세 칸을 가림(19 · 21) · 띠가 표를 4줄 밀어냄(20) · 21 서랍에 [이대로 확정]과 [저장]이 같이 있어 헷갈릴 수 있음 · 지금 실제 표 고객 칸이 좁아 `협력사 희망 · 확정 대기` 글이 잘릴 수 있음(실화면 미확인).
- **D34(사용자, 11-12 질문 창)** 안 19~21 대신 **"협력사 희망 버튼 누르면 pc용 메뉴를 상단 drawer drop방식으로 열어주게 목업만들어봐"** → 7차 시안에 **안 22** 추가(a22 닫힘 · a22b 위 줄 아래에서 내려오는 서랍 = PC 판과 같은 구성 · 14칸은 7×2 · 이름 단추 50px · 회사 이름은 이름 아래 · 주말 칸 칠 없음 · 표는 안 밀리고 반투명 막 · a22c 이름 누르면 PC 정하기 창 · 날짜는 판 칸을 눌러 바꿈 · 5초 되돌리기). 10장면 넘침 0, 새 3장면 잘림 · 13px 미만 · 44px 미만 0(워커 측정, 총괄 재실행 · 그림 직접 확인). 약점: 열면 표가 464px 까지 가려짐 · 정하기 창이 판 밖 · 기록 줄을 가림.
- **P14-6 구현(11-12, 워커 opus · 총괄이 diff · 시험 · 그림 직접 확인)** 설계서 §14.8 안 22: 위 줄 [협력사 희망 N · 내일 n](`partner_request_drop_button.html`), 판은 한 벌 — 태블릿 코호트(같은 MQ + `body.erp-mobile-v2-layout`)에서 평소 숨김, 뿌리 `is-prb-drop-open` 이면 위 줄 아래 고정 서랍 + 막 + [닫기 ▴](`tablet-prb-drop.js` 54줄 — 위 줄 아랫변 · 뿌리 폭을 재서 배율로 나눠 CSS 변수로), 7칸 × 2줄 · 이름 단추 50px · 13px 이상 · 칠 없음, 회사 이름은 칩 안 span(PC 글은 `이름 (회사)` 그대로). 정하기 창이 열린 채 다른 날 칸을 누르면 날짜만 바뀜(PC 도) + 창 안내 한 줄(총괄 추가), 기록 `옮김` 꼬리표 태블릿 칠 없앰(총괄 추가). Esc 는 창 먼저 · 다음에 서랍.
  - 시험: 새 `tests/domains/test_shipment_tablet_partner_drop.py` 11개(되돌리면 6개 실패), 관련 7파일 92 passed, 바꾼 자산 언급 시험 193 passed, `node --check` 통과, 판 JS 278줄(300 래칫 안).
  - 실화면(로컬 준비물 서버 — 스테이징은 확정 대기 0건, 협력사 주문을 만들면 실제 방 알림 위험): 1280×800 터치, 가짜 희망 3건. 처음 판 숨김 · 단추 44px · 열면 서랍 윗변 = 위 줄 아랫변 107 · 표 안 밀림(136 그대로) · 이름 단추 50px · 최소 13px · 다른 칸 누르면 11-13 → 11-16 · [확정] 뒤 1초 [되돌리기] = confirm 요청 0번(대조군 5초 = 1번) · 막 · Esc · [닫기] · 단추 닫힘 · 80% 배율 위치 맞음 · PC 1440 은 판 그대로(단추 · 막 숨김) · 우리 코드 오류 0.
- **D35(사용자, 11-12 질문 창)** 다음 할 일 = "AS 넣기 이름 먼저" → 확인: 이름판으로 출고 줄에 `철수` → AS 넣기 → `applied_workers=[]` · AS 이름 없음 · 번호 배정 없음(번호 배정은 AS 넣기 · 취소 말고 쓰는 곳 0 — 늘 비어 있음, PC · 운영 같음). 질문 창 답 **"이름도 같이 넣기"**(덮어쓰기, 취소 때 되돌림, 그 사이 손으로 바꾼 이름은 그대로) → 설계서 §14.9 · 플랜 T14-7.
- **P14-7 구현(11-12, 워커 opus · 총괄이 diff · 시험 202개 직접 확인)** 설계서 §14.9: `as_recommendation.py` 넣기 = 출고 이름(writer `build_shipment_settings_patch` 정규화)이 있으면 같은 AS 쓰기(`as_sd_mutator`) 안에서 `apply_shipment_settings` 로 AS 이름을 바꿈, snapshot `previous_names` · `applied_names`, 응답 `applied_workers` = 이름. 취소 = AS 이름이 `applied_names` 와 같을 때만 되돌림(그 사이 바뀌었으면 그대로, 409 없음), 옛 snapshot 은 안 건드림. 번호 배정 · 방문일 · 알림 그대로.
  - 시험: 새 8개(실제 흐름 = `/api/erp/shipment/update` → `/apply` → `/cancel` HTTP, `get_today_kst`), 서비스를 되돌리면 7 실패 · 취소 비교를 빼면 1 실패(대조군 둘 다 확인). PG 레인 `tests/postgres/test_shipment_writer.py` 4 passed(임시 PG 17). 인벤토리 `foms_order_mutation_writer_inventory.json` 줄 번호만(183→219, 191→227, CANONICAL 그대로).
  - 남은 것(워커 보고): AS 이름 변경은 필드 변경 원장(`record_field_changes`)에 안 남음(출고 주문 `AS_RECOMMENDATION_APPLIED` 이벤트만) · 취소 비교는 순서까지 같아야 함.
- **D35-b(사용자, 11-12 질문 창 "바뀐 칸 기록도 남기기") 구현(워커 opus · 총괄이 diff · 시험 472개 확인)** AS 넣기 · 취소로 AS 이름이 실제로 바뀌면 `_write_ship_recommendations` mutation 안 · 같은 tx 에서 `diff_structured` 중 `shipment.construction_workers` 경로만 `record_field_changes`(이름판 저장과 같은 점 경로 · 라벨 "시공 인원"), 넣기 · 취소 API 의 `SecurityLog.detail` 에 `change_set` · `change_count`(행 0 이어도 열쇠). 응답 모양 그대로. 주문 화면 이력 API(`/api/orders/<id>/field-changes`)에 같은 라벨로 나옴(시험). 새 시험 6개, 원장 쓰기를 막으면 3 실패(행 있어야 하는 것 전부). 인벤토리 줄 번호만(219→239, 227→257).
  - 남은 것(워커 보고): 이력 탭의 그 줄 [되돌리기]로 AS 이름만 되돌리면 출고 쪽 추천 snapshot 과 어긋날 수 있음(이름판 저장 행과 같은 동작, 범위 밖).
- **운영 반영 PR #815(876184151, 11-12 사용자 "운영에 올리고 확인")** 이 세션 코드 커밋 8개(P14-1~7 · D35-b · KST 시험 고침) cherry-pick + 이 세션 문서(시안 1~7차 · 플랜)를 deploy 판으로 맞춘 커밋 1개. 파일 내용 대조: 코드 파일 43/48 이 첫 수정 직전 deploy 판 = 운영 판, 나머지 = 이 세션 문서 · 남의 다른 덩어리(정책 매니페스트 AS 도면 줄 · `layout_head.html` 긴급 알림 핀) · 생성 인벤토리. 충돌은 이 세션 원장 · 설계서뿐(deploy 판으로). 가지 위 시험 928 passed · writer 스캔 무변경 · APP_OK, PR CI 4종 초록. 뒤이어 남의 PR #814 가 합쳐져 운영 = c94ca978(내 것 포함 확인).
  - 운영 실측(claude_master 1회 · 보기만 · 쓰기 요청은 route 로 막음, `scratchpad/prod_ship_check.py`, 스테이징 연습 먼저): 오늘 21줄 · 시공자 칸 단추 21 · [협력사 희망 21] 44px · 판은 평소 숨김 · 누르면 위 줄 아래로 내려온 서랍(그림으로 확인: 7칸 × 2줄 · 이름 단추 큼 · 판 밖 8 · 기록 · [닫기 ▴]) · Esc 로 닫힘(뒤이은 이름판 누름이 막에 안 걸림) · 이름판 화면 안 · Esc 닫힘 · 줄 서랍 399px · 금액 0 · 날짜 띠 여닫기 · 화면 오류 0 · 4xx 0 · 쓰기 요청 0. 재잠금 (57, 'ADMIN', False).
  - **총괄 실수**: 측정 스크립트가 `offsetParent` 로 보임을 판정해 고정 위치 서랍을 '안 보임'으로 잼 → 정하기 창 열기 · 칸 눌러 날짜 바꾸기 단계를 운영에서 건너뜀(로컬 준비물 서버에서만 확인됨). 다음 실측은 `getComputedStyle(display)` · rect 로 판정.
  - 운영에서 본 것: 서랍 머리 안내 글이 PC 그대로 "주문을 누르거나 다른 날로 끌어 놓으면" — 태블릿은 끌기가 안 될 수 있어 글이 맞지 않음(후속 후보).
- **운영 실측 2회차(11-12, 사용자 "운영 정하기 창 다시 보기" — claude_master 1회 · 보기만 · 쓰기 route 차단)**: 보임 판정을 computed display · rect 로 고친 `prod_ship_check.py`(`ONLY_PRB=1`). 서랍 position fixed · 윗변 130 = 위 줄 아랫변 130 · 높이 504 · 폭 1208 · 칸 14(7열) · 이름 단추 21개 최소 44px · 최소 글자 13px · 가로 넘침 0 · 막 보임 · 표 윗변 258 그대로. 이름 누름 → 정하기 창 화면 안 · 맨 위 · 날짜 있음 · 안내 줄 있음, 다른 날 칸 누름 → 날짜 바뀜 · 창 그대로, Esc1 = 창만 닫힘 · Esc2 = 서랍 닫힘. 쓰기 요청 0 · 막힌 쓰기 0 · 오류 0 · 4xx 0. 재잠금 (57, 'ADMIN', False).
- **D36(사용자, 11-12 질문 창)** 안내 글 고치기 대신 **"날짜를 1줄 띠로 만들어서 직관적으로 넘길 수 있게 > 목업 띄워"** → 8차 시안(같은 파일, 워커 opus · 총괄이 그림 직접 확인): 안 23 한 주씩 넘기는 띠(7칸 · ◀ ▶ · 밀기 · 주 점 2개) · 안 24 날짜 칩 14개 한 줄 + 고른 날 카드 목록 · 안 25 14칸 한 줄 통째(84px, 넘치면 밀기). 데이터는 운영과 비슷하게 판 안 21 · 판 밖 8. 15장면 넘침 0, 새 5장면 잘림 · 13px 미만 · 44px 미만 0.
- **D37(사용자, 11-12 질문 창 — 총괄이 잘못 알아들음)** 안 23~25(협력사 판 날짜 띠)를 보고 **"아니 협력사말고 전체 출고일정 보기편하게 날짜별 버튼을 만들라고"** — D36 의 '날짜 1줄 띠'는 협력사 판이 아니라 출고표 본문 날짜 고르기였음(지금 운영 태블릿은 위 줄 날짜 입력칸뿐). → 9차 시안 `docs/design/mockups/tablet-shipment-date-strip.html`(워커 opus · 총괄이 그림 직접 확인): 안 26 위 줄 아래 14일 버튼 한 줄(날짜 · 요일 · N건 · 남은 N/넘침, ◀ ▶ 일주일씩, [달력]) · 안 27 한 주 넓은 버튼 + 지난주/다음주 · 안 28 위 줄 안에 7개(줄 안 늘림, 나머지 [더보기]). 버튼 값은 이미 있는 `construction_panel_dates` · `remaining_panel_dates` 만. 4장면 넘침 0 · 잘림 · 13px 미만 · 44px 미만 0.
