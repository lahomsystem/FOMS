# PC 퀘스트·세부 이름을 모바일 프로세스 이름으로 — 검토 보고서 (2026-09-30)

- 기준 HEAD: `c19afa6ad` (브랜치 `deploy`, 워킹트리의 남의 미커밋 변경은 읽지 않음)
- 브리프: `docs/plans/2026-09-30-pc-quest-mobile-process-names-brief.md`
- 범위: 읽기와 검토만. 앱 코드·테스트·템플릿·data 파일은 고치지 않았다.
- 표기: 경로:행은 이 HEAD 기준. 코드로 끝까지 확인하지 못한 것은 "추정".
- 목업: `C:\Users\USER\AppData\Local\Temp\claude\c--DEV-FOMS\f22773ee-d6da-496b-b473-3ca9a96f7aa5\scratchpad\pc-quest-mockup.html` (총괄이 Artifact 로 게시 예정)

---

## 0. 요약

**한 줄 결론**: PC 는 서버가 이미 보내는 모바일 이름(승인 버튼 이름표)을 안 쓰고 옛 퀘스트 제목과 "승인" 한 단어를 쓰고 있다. 표시 계층에서 단계 코드로 이름을 고르면 DB 이관 없이 PC 승인 버튼이 모바일 버튼과 같은 이름이 된다. 제목 자리는 펼치기 토글이라 동작 이름 대신 할 일 모양 말을 쓴다(5-1).

1. "모바일 프로세스 이름" 의 정본은 모바일 승인 버튼 이름표다(`foms/services/orders/quest_approve_cta.py:24-46`). 모바일 "현재 작업" 칸도 옛 제목을 찍고 있어 정본이 아니다(`templates/orders/partials/order_detail_mobile_v2.html:268`).
2. PC 승인 버튼은 단계와 상관없이 전부 "승인" 이다(`templates/orders/partials/dashboard_grid.html:181,207`, `static/js/orders/dashboard/erp-dashboard-quest.js:168`).
3. 퀘스트 제목은 DB 에 복사 저장된다(`foms/services/orders/erp_policy_quests.py:209-212`). json 만 고치면 옛 이름과 새 이름이 섞인다. 표시 계층(`foms/services/erp_quest_display.py:409`)에서 단계 코드로 골라야 기존 주문까지 바뀐다.
4. 단계 이름(`STAGE_LABELS`)과 파이프라인 label 은 저장값이자 필터 키라 바꾸지 않는다(`foms/services/orders/erp_policy_constants.py:14-69`, `foms/services/orders/dashboard_read_model.py:357-367`).
5. 하위 작업(`order_tasks`)은 어느 화면에도 안 보인다(templates·static/js 에서 `/tasks` 호출 0건). 이번 화면 변경 범위에서 뺀다.

---

## 1. 단계별 대조표

### 1-0. 용어 풀이 (쉬운 말)

| 말 | 뜻 |
|---|---|
| 퀘스트 | 주문 한 건에 붙은 "지금 할 일 카드". PC 주문 목록 "퀘스트" 칸의 펼침 버튼이 이것이다 |
| 합성 quest | DB 에 저장된 카드가 없을 때 화면이 템플릿으로 즉석에서 만든 카드(`foms/services/erp_quest_display.py:96-115`). 저장되지 않는다 |
| 승인 버튼 이름 | 카드의 버튼 글자. 모바일은 단계별 이름(`approve_label`, 예 "접수 확인"), PC 는 "승인" |
| 완료 배지 | 할 일이 끝난 카드에 붙는 초록 글자(`done_label`, 예 "접수 확인 완료", `quest_approve_cta.py:42-46`) |
| 재전이 버튼 | 승인은 끝났는데 단계가 안 넘어간 막다른 주문에서 다시 넘기는 버튼(`dashboard_grid.html:112,153`) |

### 1-1. 표 A — 단계 × 표면 대조표 (CEO mapping 전 행)

"모바일에 없음 — 새 문구" 는 모바일에도 없던 글자를 새로 만드는 줄이다.

| 단계 | 표면 | PC 지금 | 모바일 지금 | 제안 | 근거 경로:행 | 비고 |
|---|---|---|---|---|---|---|
| 공통 | 작업 큐 머리글·열 이름 | 열 제목 "퀘스트", 부제 "주문 처리 및 퀘스트 관리", 펼침 머리 "현재 단계 퀘스트" | 상세 칸 제목 "현재 작업" | 열 제목 "현재 작업", 부제 "주문별 현재 작업", 펼침 머리 "현재 작업" | `templates/orders/partials/dashboard_grid.html:14,56,134`; `templates/orders/partials/order_detail_mobile_v2.html:266` | 생산·시공 보드 머리글(`templates/production/partials/filters_grid.html:12,25`, `templates/construction/partials/filters_grid.html:12,25,117`)도 같이 |
| 공통 | 퀘스트 상태 배지 | "진행중"(노랑) / "완료"(초록) / 완료 quest 는 done_label | 상태 배지 없음. 끝난 quest 만 done_label(예 "고객 컨펌 완료") | "할 일"(노랑) / done_label(초록). "진행중 + 실측 완료" 처럼 어긋나 읽히는 조합을 없앤다 | `dashboard_grid.html:106-120,147`; `foms/services/orders/quest_approve_cta.py:42-46`; `order_detail_mobile_v2.html:296` | 모바일에 없음 — 새 문구("할 일") |
| 공통 | 승인 버튼(펼침 카드 안) | 단계와 상관없이 "승인" | 화면에 실제로 보이는 이름은 넷: 접수 확인·실측 완료·고객 컨펌 완료·CS 확인. 큐 카드 버튼(`templates/partials/shared/erp_mobile_queue_card_v2.html:309`)·상세 담당자 버튼(`order_detail_mobile_v2.html:313`)은 이름만, 상세 팀 버튼은 "{팀 코드} {이름}"(예 "CS 접수 확인", `:338`). "{이름} → {다음 단계} 전달" 하단 고정 버튼은 **실측 단계 + 담당자 방식에서만** 뜬다(`order_detail_mobile_v2.html:119` is_measure_stage, `:125-133` 조건, `:419` 문구). "생산 확인"·"AS 확인" 은 이름표 사전 값일 뿐 합성 quest 라 버튼으로 안 그려진다(`foms/services/orders/quest_approve_authz.py:201-202`, `foms/services/erp_quest_display.py:331-334`) | 단계를 넘기는 단계(접수·실측·고객컨펌)는 두 안을 나란히 사용자에게 보인다. 안 1 "{approve_label} → {다음 단계} 전달"(실측은 모바일 하단 버튼과 같은 글자, 접수·컨펌은 모바일에 없음 — 새 문구). 안 2 "{다음 단계} 단계로 넘기기"(모바일 스크린리더 설명 "{이름} — {다음 단계} 단계로 넘김" `erp_mobile_queue_card_v2.html:308` 과 같은 결, 모바일에 없음 — 새 문구). 기록만 하는 단계(CS)는 approve_label 만 | `dashboard_grid.html:181,207`; `static/js/orders/dashboard/erp-dashboard-quest.js:168`; `quest_approve_cta.py:24-32`; `order_detail_mobile_v2.html:119,125-133,313,338,419`; `erp_mobile_queue_card_v2.html:308-309` | 서버가 이미 approve_label·next_stage_label·advances_stage 를 payload 에 넣어 보낸다 — PC 가 안 쓸 뿐. 동작 이름은 이 버튼에만 쓰고 제목 자리(펼치기 토글)에는 쓰지 않는다(아래 "퀘스트 제목" 줄, 5-1) |
| 공통 | 펼침 카드 소제목 | "승인" | 없음(모바일은 소제목 없이 버튼만) | "누를 버튼" | `dashboard_grid.html:162`; 표 B "승인 줄" | 모바일에 없음 — 새 문구. 목업의 바뀐 뒤 쪽 소제목도 전부 이 말로 맞춤 |
| 공통 | 담당 팀 이름 | CS=라홈팀, 영업팀, 도면팀, 생산팀, 시공팀 | 영어 코드 그대로(예 "CS 접수 확인", "PRODUCTION 대기") | 한 벌로 통일: CS팀·영업팀·도면팀·생산팀·시공팀·출고팀 (PC·모바일·변경 이력 모두) | `foms/web/orders/dashboard.py:189-196`; `foms/web/construction/dashboard.py:64-71`; `foms/web/production/dashboard.py:84-91`; `foms/services/order_event_display.py:25-33`; `order_detail_mobile_v2.html:325,328,338`; `data/erp_quest_templates.json:193` | "라홈팀" 은 하우드 직원에게 틀린 이름. 최종 이름은 사용자 확인(6절 질문 1) |
| 공통 | 파이프라인 막대 | 주문접수·실측·도면·고객컨펌·생산·시공·CS·완료·AS처리 | 모바일 홈 타워 파이프라인도 같은 process_steps 라 같은 글자 | 그대로 둔다(이미 모바일과 같다). 바꾸게 되면 data-stage 키는 두고 step.display 로 보이는 글자만 | `foms/services/orders/dashboard_read_model.py:357-367`; `templates/orders/partials/dashboard_main.html:116-137`; `templates/orders/partials/dashboard_mobile_tower.html:124-133`; 선례 `templates/production/partials/dashboard_body.html:97,107` | label 은 필터 키(`STAGE_SQL_FILTER_MAP`)라 바꾸면 필터가 깨진다 |
| 공통 | 하위 작업(order_tasks) | 화면에 안 보임 | 화면에 안 보임 | 이번 범위에서 화면 변경 없음. data 정리 단계에서 이름·담당 팀만 지금 흐름에 맞춘다 | `data/erp_task_templates.json:6-59`; `foms/services/orders/erp_policy_tasks.py:205-240`; templates·static/js 에서 `/tasks` 호출 0건(grep) | VERIFY_INFO 담당 SALES vs 퀘스트 담당 CS, REQUEST_CONFIRM 담당 CS vs 수령 확정은 영업 — 어긋남 |
| 공통(태블릿) | 태블릿 시트 | "다음 할 일 — 주문 정보 확인 (승인: 라홈팀)", 버튼 "퀘스트 승인"/"승인 완료" | approve_label / done_label | "다음 할 일 — 접수 확인 (CS팀)", 버튼은 approve_label, 끝나면 done_label | `templates/orders/partials/tablet_dashboard_sheet.html:24-31,79-94` | |
| 공통 | 승인 뒤 알림(토스트) | "(체크) 승인 완료 — {단계} 단계로 이동", "승인 완료 — 남은 팀: …" | "{next_stage} 단계로 넘겼습니다."(재전이), "승인 완료 — {next_stage} 단계로 넘어갔습니다.", "{버튼 이름} 기록 완료.", "승인 완료 — 남은 팀: {missing_teams}" | "{approve_label} — {단계} 단계로 넘어갔어요", "남은 팀: {한글 팀 이름}". 알림 속 영어 팀 코드(모바일은 missing_teams 를 그대로 이어 붙여 "CS, SALES" 로 보임)와 단계 코드도 한글로 | `erp-dashboard-quest.js:69-81,117-126`; 모바일 `static/js/foms/erp-quest-approve.js:48-60`; 단계 이름은 `foms/api/quest.py:455,657` 에서 `CODE_TO_STAGE_NAME` 으로 한글(표에 없는 코드는 영어 그대로) | PC 는 팀 코드를 TEAM_LABELS 로 한글화(`erp-dashboard-quest.js:79`), 모바일은 안 함 |
| 공통 | 편집 폼·강제 단계 변경 select | "A. 주문접수 / C. 실측 / … / H. CS" (옛 문자 코드) | 없음(문자 없는 단계 이름) | 문자 떼고 "주문접수·실측·도면·고객컨펌·생산·시공·CS·완료" 로 | `templates/orders/partials/erp_order_tab.html:220-228`; `templates/orders/partials/erp_stage_override_modal.html:27-35`; `static/js/foms/tablet-measure-form.js:64-77` | value(코드)는 그대로, 보이는 글자만 |
| 주문접수(RECEIVED) | 퀘스트 제목(접힌 버튼·펼침 h5) | 주문 정보 확인 | 큐 카드 버튼 "접수 확인", 배지 "접수", 상세 "현재 작업" 은 옛 이름 "주문 정보 확인" | 접수 내용 확인하기(할 일 모양). 동작 이름 "접수 확인" 은 승인 버튼에만 | `data/erp_quest_templates.json:7`; `dashboard_grid.html:121-129`(펼치기만 하는 토글 버튼 안의 `<strong>`), `:140`; `quest_approve_cta.py:25,42-46`; `order_detail_mobile_v2.html:268` | 모바일에 없음 — 새 문구. 제목 자리에 "접수 확인" 을 넣으면 누르면 끝나는 버튼처럼 보이고, 끝난 뒤 완료 배지 "접수 확인 완료" 와도 헷갈린다(5-1). 저장 title 대신 단계 코드로 이름을 고르는 표시 계층 덮어쓰기 필요(저장값은 DB 에 복사돼 있음) |
| 주문접수(RECEIVED) | 승인 버튼 / 확인창 / 완료 배지 | "승인" / "주문 접수 확인을 마치고 실측 단계로 넘길까요?" / "접수 확인 완료" | "접수 확인"(큐 카드 `erp_mobile_queue_card_v2.html:309`) · 상세 팀 버튼 "CS 접수 확인"(`order_detail_mobile_v2.html:338`) / 같은 확인창 / "접수 확인 완료". 하단 고정 버튼 없음(실측 단계 전용 `:119,125-133`) | 안 1 "접수 확인 → 실측 전달" 또는 안 2 "실측 단계로 넘기기" / 확인창 그대로 / "접수 확인 완료" | `dashboard_grid.html:207`; `quest_approve_cta.py:25,36,42-46` | 버튼 글자 두 안 모두 모바일에 없음 — 새 문구 |
| 주문접수(RECEIVED) | 설명 | 살아 있는 PC 화면에 없음(json 에만 "온라인 플랫폼 또는 예약금 입금으로 … FOMS에 입력") | 없음 | 주문 내용(고객·연락처·주소·제품)을 확인하고 실측으로 넘겨요. | `data/erp_quest_templates.json:8`; `templates/orders/object.html:248`(라우트 없음) | 모바일에 없음 — 새 문구. "FOMS에 입력" 은 이미 끝난 일이라 틀림 |
| 실측(MEASURE) | 퀘스트 제목 | 실측 | 큐 카드 버튼 "실측 완료", 배지 "실측", 상세 "현재 작업" "실측" | 실측 결과 올리기(할 일 모양). 동작 이름 "실측 완료" 는 승인 버튼에만 | `data/erp_quest_templates.json:23`; `dashboard_grid.html:121-129`(토글 버튼); `quest_approve_cta.py:26,42-46`; `templates/partials/shared/erp_mobile_queue_card_v2.html:98-99`(단계 배지와 같은 말이라 제목 칩을 뺀 이유) | 모바일에 없음 — 새 문구. 제목이 단계 이름과 같아 정보가 없던 문제를 풀되, "실측 완료" 를 제목에 쓰면 완료 배지 "실측 완료"(`_done_label` 이 '완료' 로 끝나는 이름을 그대로 돌려줌)와 할 일이 같은 글자가 된다 |
| 실측(MEASURE) | 승인 버튼 / 확인창 | "승인"(담당자 방식) · 담당자 없으면 "담당자 지정 필요" · 권한 없으면 "(승인 권한 없음)" | "실측 완료"(카드) · "실측 완료 → 도면 전달"(상세 하단 고정 버튼 — 실측 + 담당자 방식에서만 뜸) | 안 1 "실측 완료 → 도면 전달"(모바일 하단 버튼과 같은 글자) 또는 안 2 "도면 단계로 넘기기". "담당자 지정 필요"·"(승인 권한 없음)" 은 "담당자를 먼저 정해 주세요"·"담당자만 누를 수 있어요" 로 | `dashboard_grid.html:172-185`; `quest_approve_cta.py:26,37`; `order_detail_mobile_v2.html:119,125-133,419` | 안 2 와 권한 안내 두 줄은 모바일에 없음 — 새 문구 |
| 실측(MEASURE) | 실측 대시보드 PC 버튼 | "도면 전달", 막히면 "이 주문의 실측 퀘스트는 팀 승인 방식이라…" | "실측 완료" / 태블릿 "실측 완료 → 도면 전달" | 안 1 "실측 완료 → 도면 전달" 또는 안 2 "도면 단계로 넘기기"(주문 목록과 같은 안으로). 막힘 문구는 "이 주문은 주문 목록의 현재 작업 칸에서 실측 완료를 눌러 주세요" | `foms/services/measurement/drawing_transfer_cta.py:7-8,33-37`; `templates/measurement/partials/tablet_split_body.html:160`; 버튼 매크로 `templates/partials/shared/status_select_options.html:139-148` | "도면 전달" 단독 이름은 도면팀의 도면 파일 전달과 겹친다(코드 주석이 경고). 안 1 도 "도면 전달" 글자를 품고 있어 겹침이 완전히 사라지지는 않는다(6절 질문 6) |
| 실측(MEASURE) | 설명 | 없음(json "영업팀 직접 방문 또는 고객 셀프 실측…") | 없음 | 현장을 재고 실측 내용을 올린 뒤 도면팀에 넘겨요. | `data/erp_quest_templates.json:24` | 모바일에 없음 — 새 문구 |
| 도면(DRAWING) | 퀘스트 칸 | 퀘스트 없음 → "도면 창구" 카드(작업중·확정 대기·수정 요청됨·완료, "지금: …", "별도 작업실 열기") | 카드 버튼 "도면 창구", 상세 "도면 작업" + "도면 창구 열기" | 카드 유지. 버튼 "별도 작업실 열기" → "도면 창구 열기"(모바일과 같게) | `dashboard_grid.html:225-325`(:256-266 배지, :281 제목); `order_detail_mobile_v2.html:351-356`; `foms/services/erp_quest_display.py:67` | json 제목 "도면 작성" 은 어디에도 안 보인다 — 바꿀 필요 없음 |
| 도면(DRAWING) | 하위 상태 이름 | 주문 그리드 "확정 대기"·"수정 요청됨", 도면 창구 막대 "확정대기"·"수정요청", 주문 상세 JS 배지 "확정 대기중" | 도면 카드 칩 "확정 대기"·"수정 요청됨", 도면 필터 칩 "수정요청" | "확정 대기"·"수정 요청됨" 한 벌 | `dashboard_grid.html:259,262`; 이름 출처 `foms/services/erp_display.py:547-548`(`_drawing_status_label`, `foms/web/drawing/workbench.py:171-173` 이 부름); `templates/drawing/partials/workbench_dashboard_body.html:54,60,108-109`; `static/js/orders/dashboard/erp-dashboard-detail-dom.js:371,378` | 같은 파일 안 select 는 이미 "확정 대기"·"수정 요청됨". "확정 대기중" 은 대시보드 JS(`erp-dashboard-entry.js:13` 이 로드)에 있지만 실제로 보이는 화면은 추정(실화면 미확인) |
| 고객컨펌(CONFIRM) | 퀘스트 제목 | 고객 컨펌 | 카드 버튼 "고객 컨펌 완료", 배지 "컨펌", 상세 "고객 컨펌" | 고객 컨펌 받기(할 일 모양). 동작 이름 "고객 컨펌 완료" 는 승인 버튼에만 | `data/erp_quest_templates.json:64`; `dashboard_grid.html:121-129`(토글 버튼); `quest_approve_cta.py:27,42-46`; `foms/services/erp_mobile_order_display.py:535` | 모바일에 없음 — 새 문구. "고객 컨펌 완료" 를 제목에 쓰면 완료 배지·재전이 버튼과 같은 글자가 된다 |
| 고객컨펌(CONFIRM) | 승인 버튼 / 재전이 / 완료 배지 | "승인" / 재전이 "고객 컨펌 완료" / "고객 컨펌 완료" | "고객 컨펌 완료"(카드에서 바로 `erp_mobile_queue_card_v2.html:309`, 상세 담당자 버튼 `order_detail_mobile_v2.html:313`). 하단 고정 버튼 없음(실측 단계 전용 `:119,125-133`) | 안 1 "고객 컨펌 완료 → 생산 전달" 또는 안 2 "생산 단계로 넘기기" / 재전이 그대로 / 완료 배지 그대로 | `dashboard_grid.html:112,114,181`; `quest_approve_cta.py:27,38`; `erp_mobile_queue_card_v2.html:260,300-310` | 버튼 글자 두 안 모두 모바일에 없음 — 새 문구 |
| 고객컨펌(CONFIRM) | 설명 | 없음(json "도면을 고객에게 전달하고… 도면팀 재작업") | 없음 | 고객에게 도면을 보여 주고 좋다고 하면 생산으로 넘겨요. | `data/erp_quest_templates.json:65,78-83` | 모바일에 없음 — 새 문구. "도면팀 → 생산팀 전달" 은 사라진 단계 |
| 생산(PRODUCTION) | 주문 그리드 퀘스트 칸 | "진행중" + 합성 quest "생산", 펼치면 "생산팀 (보드에서 진행)" | 생산 보드 배지 "제작대기"·"제작중", 버튼 "제작 시작"·"제작 완료". 상세 "현재 작업" "생산" | 합성 quest 대신 "제작대기" 또는 "제작중" 배지 + "생산 보드 열기" 링크(승인 칸 없음) | `dashboard_grid.html:128,208-210,327-328`; `erp_quest_display.py:96-101`; `foms/services/production_dashboard_display.py:147-162,286-294`; `foms/services/orders/quest_transition_service.py:65-75` | "생산 확인" 은 이름표 사전 값(`quest_approve_cta.py:28`)일 뿐 합성 quest 라 모바일에도 안 나온다(`quest_approve_authz.py:201-202`) — PC 에 새로 내밀지 않는다. "제작중" 판정에 run 조회 필요(성능 확인) |
| 생산(PRODUCTION) | 생산 대시보드 PC | "고객 컨펌 전" / "제작 시작" / "생산 중" | "고객 컨펌 전" 배지 / "제작 시작" / "제작중" | "생산 중" → "제작중" | `templates/production/partials/filters_grid.html:81-96`(:93); `production_dashboard_display.py:159,293`; `templates/production/partials/mobile_queue.html:58` | |
| 시공(CONSTRUCTION) | 주문 그리드 퀘스트 칸 | "-" | 시공 보드 배지 "시공대기"·"시공중"·"시공완료", 버튼 "시공 시작"·"시공 완료" | "시공대기" 또는 "시공중" 배지 + "시공 보드 열기" 링크 | `dashboard_grid.html:330`; `erp_quest_display.py:67`; `foms/services/construction_dashboard_display.py:391-401` | "시공 확인"(`quest_approve_cta.py:29`)은 어디에도 나올 수 없는 이름 — 정리 단계에서 지울지 판단 |
| 시공(CONSTRUCTION) | 시공 대시보드 PC | "시공 시작"·"시공 완료"·"재 업로드"·"AS 접수". 퀘스트 갈래와 "팀별 승인"·"승인" 은 닿지 않는 코드 | 같은 버튼 이름 | 그대로(이미 모바일과 같다). 닿지 않는 퀘스트 갈래는 정리 단계에서 삭제 | 보이는 버튼 `templates/construction/partials/filters_grid.html:73,79,85,93`; 닿지 않는 "팀별 승인"·"승인" `:139,154`; `construction_dashboard_display.py:462-497` | |
| CS | 퀘스트 제목 | CS/AS 접수 및 처리 | 버튼 "CS 확인"(상세로 이동), 배지 "CS", 상세 "현재 작업" 은 옛 이름 | CS 문의 확인하기(할 일 모양). 동작 이름 "CS 확인" 은 버튼에만 | `data/erp_quest_templates.json:129`; `dashboard_grid.html:121-129`(토글 버튼); `quest_approve_cta.py:30`; `erp_mobile_order_display.py:539` | 모바일에 없음 — 새 문구. AS 는 별도 축(`foms/services/orders/as_cycle_service.py:14-16`)이라 제목에서 뺀다 |
| CS | 승인 버튼 / 확인창 | "라홈팀 [승인]" / "CS 확인을 기록할까요? 단계는 CS 그대로" | "CS CS 확인"(팀 코드 + 이름, 추정) / 같은 확인창 | "CS 확인" 한 번만(팀 이름을 앞에 붙이지 않는다) / 확인창 그대로 + "완료 처리는 따로 해요" 한 줄 | `dashboard_grid.html:193,207`; `order_detail_mobile_v2.html:338`; `quest_approve_cta.py:94-103`; `foms/services/orders/complete_path_policy.py:150-166` | "완료 처리는 따로" 안내는 모바일에 없음 — 새 문구 |
| CS | 설명 | 없음(json "시공 완료 후 CS 접수 및 AS 처리") | 없음 | 설치 뒤 고객 문의를 확인해요. AS 는 AS 화면에서 따로 처리해요. | `data/erp_quest_templates.json:130,144-150` | 모바일에 없음 — 새 문구 |
| 완료(COMPLETED) | 퀘스트 칸 | "진행중" + 합성 quest "완료", 펼치면 "라홈팀 (보드에서 진행)" | 승인 버튼 없음. 상세 "현재 작업: 완료" | 초록 "완료" 배지 하나만(펼침 없음) | `data/erp_quest_templates.json:157`; `quest_approve_cta.py:23`; `dashboard_grid.html:119,208-210` | 끝난 주문에 할 일이 남은 것처럼 보이는 문제. "진행중" 표시는 코드로 판단(실화면 미확인, 추정) |
| AS처리(AS) | 퀘스트 칸 | "진행중" + 합성 quest "AS 작업", "라홈팀 (보드에서 진행)" | 버튼 없음(합성 quest 는 RECEIVED·CS 만 팀 계산 `foms/services/orders/quest_approve_authz.py:201-202`, 팀 방식이면 담당자 승인 False `foms/services/erp_quest_display.py:331-334`). 상세 "현재 작업" "AS 작업", AS 카드 배지 "AS접수·AS처리·AS완료" | 제목은 사용자가 고른다: "AS 작업"(모바일 상세에 실제로 보이는 이름) 또는 "AS 확인"(이름표 사전 값 `quest_approve_cta.py:31`, 화면에는 안 나옴). 여기에 "AS 화면 열기" 링크 | `data/erp_quest_templates.json:167`; `quest_approve_cta.py:31`; `order_detail_mobile_v2.html:268`; `as_mobile_order_card.html:92` | AS_RECEIVED·AS_COMPLETED 는 템플릿이 없어 "-"(`foms/services/orders/erp_policy_quests.py:15-22`) — "AS접수"·"AS완료" 배지로 채우는 안을 함께 제안 |

### 1-2. 표 B — 공통 표면 전수 (단계와 무관, PC 에 보이는 곳)

| 표면 | 보이는 글자 | 템플릿/JS | 서비스 | data/상수 |
|---|---|---|---|---|
| 퀘스트 제목 | `current_quest.title` | `dashboard_grid.html:128`(셀 버튼), `:140`(펼침 h5); `tablet_dashboard_sheet.html:27`; `tablet_workqueue_grid.html:66` | `foms/services/orders/dashboard_dto.py:59-66` → `erp_quest_display.py:381,409` | 저장 `sd.quests[].title`, 없으면 `erp_quest_templates.json stages.<CODE>.title` |
| 퀘스트 설명 | `description` | 살아 있는 PC 표면 없음. 죽은 `object.html:248`, 죽은 `static/js/orders/erp-order-shared.js:6063` 에만 | `erp_quest_display.py:410` | `stages.<CODE>.description` |
| 머리 글자 | "퀘스트", "주문 처리 및 퀘스트 관리", "현재 단계 퀘스트" | `dashboard_grid.html:56,14,134`; `production/partials/filters_grid.html:12,25`; `construction/partials/filters_grid.html:12,25,117` | 없음 | 템플릿에 직접 |
| 상태 배지 | "완료" / "진행중" | `dashboard_grid.html:117,119,147` | `all_approved` `erp_quest_display.py:137-179` | 템플릿에 직접 |
| 담당 팀 | 라홈팀·영업팀·실측팀·도면팀·생산팀·시공팀 | `dashboard_grid.html:157-159,193`; `tablet_dashboard_sheet.html:29` "(승인: 팀)" | `owner_team` `erp_quest_display.py:411`, 라홈 발주면 CS `:118-134` | `TEAM_LABELS` `foms/web/orders/dashboard.py:189-196` |
| 승인 줄 | "승인"(소제목 → 제안 "누를 버튼", 표 A), "{이름} 승인완료", "담당자 지정 필요", "승인완료", "(승인 권한 없음)", "(보드에서 진행)" | `dashboard_grid.html:162,172,176,197,184,212,210` | `approvable_teams` `foms/services/orders/quest_approve_authz.py:182-213` | 템플릿에 직접 |
| 승인 버튼 | "승인" | `dashboard_grid.html:181,207`; `erp-dashboard-quest.js:168` | 없음 | 템플릿에 직접 |
| 승인 확인창 | `approve_confirm` | `dashboard_grid.html:179,206` → `erp-dashboard-quest.js:16-17` | `quest_approve_cta.py:35-39,94-103` | 코드에 직접 |
| 재전이 버튼 | `retransition_label` | `dashboard_grid.html:112,153` | `quest_approve_cta.py:109` | `_QUEST_APPROVE_LABELS` `quest_approve_cta.py:24-32` |
| 완료 배지 | `done_label` | `dashboard_grid.html:114,147` | `quest_approve_cta.py:42-46` | 위와 같음 |
| 토스트 | "승인 완료 — {단계} 단계로 이동", "{단계} 단계로 넘겼습니다", "남은 팀: …" | `erp-dashboard-quest.js:69-81,117-126` | `data-stage-labels` `dashboard_main.html:197` | `erp_policy_constants.py:14-26` |
| 도면 상태 배지(주문 상세 JS) | "확정 대기중" | `static/js/orders/dashboard/erp-dashboard-detail-dom.js:371,378`(대시보드 entry 가 로드 `static/js/orders/erp-dashboard-entry.js:13`, 실제 노출 화면은 추정) | 없음 | JS 에 직접 |
| 옛 단계 표(JS) | "A. 주문접수 / C. 실측 / … / H. CS" | `static/js/orders/erp-order-shared.js:6019-6031` | 없음 | JS 에 직접. 쓰는 곳은 죽은 `erpRenderQuest`(`:6132`)와 그 안의 onclick 으로만 불리는 `erpApproveQuestTeam`(`:6104,6187`) 뿐 — 죽음(추정: 다른 진입 경로 grep 0건) |
| 단계 배지(그리드 열) | 주문접수…AS처리 | `dashboard_grid.html:101-102` | `_erp_get_stage` `foms/services/erp_display.py:448-463` | `STAGE_LABELS` |
| 파이프라인 막대 | 9칸 | `dashboard_main.html:116-137`(:129 라벨) | `dashboard_read_model.py:357-367` | 손으로 쓴 목록(키 = STAGE_LABELS 값) |
| 단계 필터 select | 주문접수…시공·AS처리 (CS·완료 없음) | `templates/orders/partials/dashboard_filters.html:20-28` | 없음 | 템플릿에 직접 |
| 팀 필터 select | 라홈팀… | `dashboard_filters.html:31-38` | 없음 | 템플릿에 직접 |
| 태블릿 시트 파이프 | 접수·실측·도면·고객컨펌·생산·시공·"CS / AS"·완료 | `static/js/foms/tablet-side-sheet.js:187-232` ← `dashboard_grid.html:7` | context_processors.py:421 | `STAGE_SEQUENCE` `foms/services/order_timeline_v3.py:20-29` |
| 태블릿 짧은 배지 | 접수·컨펌… | `tablet_workqueue_grid.html:55`; `tablet_dashboard_sheet.html:16`; `order_detail_split_panel.html:6` | `stage_badge_label` `erp_mobile_order_display.py:518-542` | 코드에 직접 |
| 태블릿 시트 버튼 | "퀘스트 승인" / "승인 완료" | `tablet_dashboard_sheet.html:79,84,87,91,94` | 없음 | 템플릿에 직접 |
| 편집 폼 단계 select | "A. 주문접수 / C. 실측 / … / H. CS / 완료" | `erp_order_tab.html:220-228`; 미러 `tablet-measure-form.js:64-77` | 없음 | 템플릿에 직접 |
| 강제 단계 변경 모달 | 같은 "A.~H." 글자 | `erp_stage_override_modal.html:27-35` (JS 표는 문자 없음 `static/js/orders/erp-stage-override.js:19-28`) | 없음 | 템플릿에 직접 |

문구 안에서 "퀘스트" 를 인용하는 곳(PC 에 보임):

- 완료 막힘 설명 "…주문 상세의 퀘스트 칸에서 …", "…대시보드 퀘스트 칸에서 승인하세요."(`complete_path_policy.py:150-153,159-166`, 사용 `status_select_options.html:73-75`)
- 승인 API 오류: "단독 퀘스트 승인이 아니라 전용 command…"(`foms/api/quest.py:363-366`), "도면 단계 퀘스트는 비활성화되었습니다."(`:101,157`), "퀘스트 수동 완료는 관리자만…"(`:709`)
- 변경 이력: "{팀}이 퀘스트를 승인했습니다"(`order_event_display.py:494-497`, CS 는 "상담팀"), 사건 이름 "퀘스트 승인·생성·수정·완료"(`:171-175`), 필드 "현재 퀘스트"(`:154`), 감사 로그(`foms/services/audit_message_display.py:226-228`)
- 푸시·알림톡이 퀘스트 제목이나 승인 이름을 인용하는 곳: 0건(foms 전체 grep)

### 1-3. 표 C — 모바일 이름 후보와 고른 이유

"고른 이름" 은 **누르는 승인 버튼**에 쓰는 이름이다. 제목 자리(펼치기 토글)는 5-1 대로 할 일 모양 말을 쓴다.

| 단계 | 모바일 단계 이름 | 모바일 할 일·버튼 이름 | 고른 이름 | 이유 |
|---|---|---|---|---|
| RECEIVED | 접수(배지·타임라인, `erp_mobile_order_display.py:531`, `order_timeline_v3.py:21`) / 주문접수(파이프라인) | 접수 확인(`quest_approve_cta.py:25`) | 접수 확인 | 큐 카드(`erp_mobile_queue_card_v2.html:309`)·상세 팀 버튼("CS 접수 확인", `order_detail_mobile_v2.html:338`)에서 쓰고 완료 배지도 "접수 확인 완료". 하단 고정 버튼은 없음 |
| MEASURE | 실측 | 실측 완료(`:26`), 하단 "실측 완료 → 도면 전달"(`order_detail_mobile_v2.html:419`, 실측 + 담당자 방식에서만) | 실측 완료 | 단계 이름 되풀이를 없앤다(`erp_mobile_queue_card_v2.html:98-99`) |
| DRAWING | 도면 | 도면 창구(`erp_mobile_queue_card_v2.html:324`), "도면 창구 열기"(`order_detail_mobile_v2.html:351-356`) | 도면 창구(카드 유지) | 승인 버튼이 없는 전용 명령 단계(`foms/api/quest.py:358-367`) |
| CONFIRM | 컨펌(배지) / 고객컨펌(타임라인·타워) | 고객 컨펌 완료(`quest_approve_cta.py:27`) | 고객 컨펌 완료 | 카드에서 바로 누르는 버튼과 같은 글자(`erp_mobile_queue_card_v2.html:260,300-310`) |
| PRODUCTION | 생산 / 하위 제작대기·제작중·제작완료 | 제작 시작·제작 완료(`production/partials/mobile_queue.html:53-76`) | 제작대기·제작중 배지 | "생산 확인"(`quest_approve_cta.py:28`)은 이름표 사전 값일 뿐 어디에도 안 나온다(합성 quest, `quest_approve_authz.py:201-202`) |
| CONSTRUCTION | 시공 / 하위 시공대기·시공중·시공완료 | 시공 시작·시공 완료(`construction/partials/mobile_queue.html:93-116`) | 시공대기·시공중 배지 | "시공 확인" 은 나올 수 없는 이름(`erp_quest_display.py:67`) |
| CS | CS (타임라인만 "CS / AS") | CS 확인(`quest_approve_cta.py:30`) | CS 확인 | AS 는 별도 축 |
| COMPLETED | 완료 | 없음(`quest_approve_cta.py:23`) | 완료(배지만) | 할 일이 없는 단계 |
| AS 계열 | AS접수·AS처리·AS완료(`as_mobile_order_card.html:92`) | 버튼 없음. 상세 "현재 작업" 은 "AS 작업"(`order_detail_mobile_v2.html:268`, json `:167`). "AS 확인"(`quest_approve_cta.py:31`)은 이름표 사전 값, 화면에는 안 나옴(`quest_approve_authz.py:201-202`, `erp_quest_display.py:331-334`) | 사용자 선택: "AS 작업" 또는 "AS 확인" | 모바일에서 실제로 보이는 이름은 "AS 작업" 하나. "AS 확인" 은 버튼 이름표 규칙과 결은 맞지만 누를 버튼이 없다 |

---

## 2. legacy 가 지금 흐름과 어긋난 곳

### 2-1. 단계별

**주문접수**
- 설명 "FOMS에 입력합니다" 는 이미 끝난 일이다. 주문은 `create_order` 로 생기는 순간 quest 가 심어진다(`data/erp_quest_templates.json:8`, `foms/services/orders/order_create.py:118-124`). "예약금 입금" 경로는 코드에서 확인 못 함(추정: 옛 운영 설명).
- 한 일에 이름이 넷: 제목 "주문 정보 확인", 단계 "주문접수", 버튼 "접수 확인", 배지 "접수"(`json:7`, `erp_policy_constants.py:15`, `quest_approve_cta.py:25`, `erp_mobile_order_display.py:531`).

**실측**
- `dynamic_team_rule` "라홈이면 CS팀으로 변경" 은 승인 팀까지 바뀌는 것처럼 읽히지만, 2026-09-13 부터 주관 팀 표시만 바뀌고 승인은 CS·영업 둘 다 된다(`json:46`, `erp_quest_display.py:118-134`). 이 필드는 코드가 안 읽는다.

**도면**
- 제목·설명 "스케치업으로 3D 도면 작성 → FOMS 업로드" 에 지금 흐름(담당 배정 → 마법사 업로드 → 도면 전달 → 전달 취소·수정 요청 → 영업 수령 확정)이 하나도 없다(`json:50-51`, `foms/api/drawing/erp_orders_draftsman.py:325-376`). 도면 quest 는 화면에서 숨겨지고 승인도 409.

**고객컨펌**
- `process_flow` 의 "채널톡/카톡/SMS 로 도면 전달" 과 "도면팀 → 생산팀 전달" 은 사라졌다. 지금은 공유 링크 + 알림톡, 승인하면 생산으로 자동 이동(`json:78-83`, `foms/api/quest.py:561-570`, `quest_transition_service.py:65-75`).

**생산**
- 생산 quest 는 만들지 않는데 PC 그리드는 합성 "생산" quest 와 "생산팀 (보드에서 진행)" 을 그린다. 실제 일은 생산 보드의 제작 시작·제작 완료다(`quest_transition_service.py:65-75`, `dashboard_grid.html:208-210`).

**시공**
- `fail_process` "철수 → 재생산 → 재방문" 순서는 지금 "시공 불가" 한 번 호출로 사유별 되돌림을 하는 방식과 다르다(`json:114-119`, `foms/api/construction/orders.py:609-703`). 코드가 안 읽는 필드.

**CS**
- 제목 "CS/AS 접수 및 처리" 와 "AS 필요 시 AS 대시보드 이동 …" 흐름은 AS 가 별도 축이 된 지금과 다르다. "AS main stage 복구 금지"(`json:129-150`, `foms/services/orders/as_cycle_service.py:14-16`).

**AS**
- AS 템플릿의 "AS 완료 후 CS 단계로 복귀"(next_stage CS) 전이는 존재하지 않는다(`json:167`, `foms/services/orders/state_axes.py:76-78`).

**완료**
- 완료 단계에 합성 quest 가 떠서 PC 에 "진행중 [완료]" + "(보드에서 진행)" 이 보인다 — 할 일이 없는 단계에 할 일처럼 보임(`json:157`, `dashboard_grid.html:119,208-210`, 추정: 실화면 미확인).

**공통**
- PC 승인 버튼은 모두 "승인" — 코드 주석이 이미 "한 이름으로 묶으면 눌렀을 때 무엇이 되는지 화면이 말해 주지 못한다" 고 적었는데 PC 만 남았다(`quest_approve_cta.py:21-22` vs `dashboard_grid.html:181,207`, `erp-dashboard-quest.js:168`).
- 팀 이름이 네 벌: 라홈팀(PC 대시보드 3곳)·상담팀(변경 이력)·CS팀(json)·CS(라홈팀/하우드팀)(사용자 관리 `foms/web/auth/routes.py:68-77`). 모바일은 영어 코드 그대로(`order_detail_mobile_v2.html:325,328,338`).
- 하위 작업 템플릿 담당 팀이 퀘스트와 어긋남: VERIFY_INFO 는 SALES(퀘스트는 CS), REQUEST_CONFIRM 은 CS(수령 확정은 영업만). 화면에는 안 보임(`data/erp_task_templates.json:6-38`).
- json 머리말의 A→H 문자 코드가 편집 폼·강제 단계 변경 select 에 아직 보인다("A. 주문접수 / C. 실측 …", B 는 없음)(`erp_order_tab.html:220-228`, `erp_stage_override_modal.html:27-35`).
- 도면 쪽 이름 어긋남(범위 이웃): 도면 카드 "수령 확인" vs 상세 "수령 확정"(`workbench.py:586`, `templates/drawing/partials/workbench_mobile_handoff.html:239`), 막대 "확정대기"·"수정요청" vs 카드 "확정 대기"·"수정 요청됨".
- 죽은 분기: 변경 이력 "'{quest_title}' 퀘스트를 승인했습니다" 는 쓰는 쪽이 없다(`order_event_display.py:499-502`, grep `quest_title` 은 읽는 1곳뿐).

### 2-2. 코드가 안 읽는 죽은 필드

`data/erp_quest_templates.json` 에서 코드가 읽는 키는 `title`·`description`·`owner_team`·`required_approvals`·`next_stage` 다섯 개뿐이다(읽기 입구 `foms/services/orders/erp_policy_data_access.py:101-132`, 소비자 `erp_policy_quests.py:15,25,36,136,182`).

| 죽은 필드 | 문제 |
|---|---|
| `process_flow`·`process_types`·`fail_process`·`fail_reasons`·`feedback_loop`·`special_features` | 옛 흐름 문서. 틀려도 동작 영향 없음, 읽는 사람만 헷갈림 |
| `dynamic_team_rule`·`notes`·`involved_teams`·`team_definitions` | 팀 규칙·이름이 실제 코드(`erp_quest_display.py:118-134`, `foms/web/orders/dashboard.py:189`)와 다름 |
| `code`(A~H)·`entry_conditions`·`is_final_process_stage`·`is_terminal` | 옛 문자 코드. B 는 없음(`foms/services/orders/state_axes.py:83`) |
| `sla_hours`(도면 48) | 실제 기준은 `data/erp_policy.json:4` `blueprint_sla_hours`(`erp_policy_tasks.py:77`) — 같은 값이 두 곳 |

### 2-3. 살아 있는 표면 vs 죽은 표면

| 표면 | 상태 | 근거 | 처리 |
|---|---|---|---|
| PC 주문 그리드 퀘스트 칸 | 살아 있음 | `dashboard_grid.html:103-333` | 이번 변경 대상 |
| `erp-dashboard-quest.js` 승인 칸 다시 그리기·토스트 | 살아 있음 | `erp-dashboard-quest.js:141-172,69-81,117-126` | 이번 변경 대상 |
| 태블릿 시트·태블릿 그리드 | 살아 있음 | `tablet_dashboard_sheet.html:24-94`, `tablet_workqueue_grid.html:66` | 이번 변경 대상 |
| 모바일 상세 "현재 작업"·큐 카드 aria-label | 살아 있음(같은 payload) | `order_detail_mobile_v2.html:268`, `erp_mobile_queue_card_v2.html:315` | 함께 바뀜 |
| `templates/orders/object.html` | 죽음(라우트 없음) | `tests/contracts/runtime/foms_namespace_surface_tests.py:1989` | 이름 안 바꿈, 정리 단계 삭제 후보 |
| `erp-order-shared.js` `erpRenderQuest` | 죽음(붙을 요소 0) | `static/js/orders/erp-order-shared.js:6046-6140`(:6120-6122 가드) | 삭제 후보 |
| 생산 `loadQuestDetail` | 죽음(추정: `#quest-collapse-*` 없음) | `templates/production/partials/scripts.html:380-419` | 삭제 후보 |
| 시공 대시보드 퀘스트 갈래 | 닿지 않음(DTO 가 current_quest 를 안 줌) | `construction/partials/filters_grid.html:97-163`, `construction_dashboard_display.py:462-497` | 삭제 후보 |
| 하위 작업 화면 | 없음 | `/api/orders/<id>/tasks` GET(`foms/api/tasks.py:203`)을 부르는 프런트 0건 | 화면 변경 없음 |
| 변경 이력 quest_title 분기 | 죽음 | `order_event_display.py:499-502`, 기록 쪽 `foms/api/quest.py:492-509` | 삭제 후보 |
| `dashboard_mobile_filters.html` | 어디서도 안 불림 | grep 0건 | 대상 아님 |
| `scripts/ops/erp_build_step_runner.py` 작업 템플릿 복제본 | 죽음(경로 `scripts/ops/data`) | `scripts/ops/erp_build_step_runner.py:595-626` | 삭제 후보 |

---

## 3. 바꿀 때 걸리는 것

### 3-1. 표 D — 위험과 대응 (CEO change_risks 전 항목)

| 위험 | 무엇이 깨지나 | 근거 | 대응 |
|---|---|---|---|
| quest title 이 DB 에 복사 저장 | json title 만 바꾸면 기존 주문은 옛 이름, 새 주문은 새 이름이 섞인다 | `erp_policy_quests.py:209-212`, `order_create.py:122`, `quest_transition_service.py:189`, `foms/api/quest.py:172-183,391-398` | 표시 계층에서 단계 코드로 이름을 고른다(`erp_quest_display.py:409`, `foms/api/quest.py:126-131`). 저장값은 감사 흔적으로 두고 DB 이관 안 함 |
| 강제 단계 되돌리기의 재개 | 옛 quest 를 그대로 복사 — json 만 바꾸는 방식이면 옛 이름이 계속 살아난다 | `foms/services/orders/stage_override.py:250-296` | 표시 덮어쓰기면 문제없음 |
| STAGE_LABELS·STAGE_NAME_TO_CODE·STAGE_SQL_FILTER_MAP 한글 값 | 저장값이자 키. quest.stage="실측", workflow.stage="고객컨펌" 매칭과 JSONB 필터가 깨진다 | `erp_policy_constants.py:14-69` | 이 사전은 절대 바꾸지 않는다 |
| 파이프라인 data-stage·필터 select value | 한글 라벨이 곧 서버 필터 키. 모바일 타워 링크도 `stage=step.label` | `dashboard_main.html:117-129`, `dashboard_filters.html:20-28`, `static/js/construction/dashboard.js:1274-1275` | 보이는 글자를 바꾸려면 production 대시보드처럼 `step.display` 를 따로(`production/partials/dashboard_body.html:97,107`) |
| 모바일 노출 조건이 title 비었는지로 판정 | 표시 이름표가 빈 문자열을 돌려주면 모바일 승인 버튼이 사라진다 | `order_detail_mobile_v2.html:263`, `erp_mobile_queue_card_v2.html:253` | 모르는 코드는 저장 title 로 떨어지게. 빈 문자열 금지 |
| PC·모바일 공용 payload | PC 만 바꾸려 해도 모바일 "현재 작업" 글자와 큐 카드 aria-label 이 함께 바뀐다 | `dashboard_dto.py:59`, `erp_mobile_order_display.py:844`, `erp_mobile_queue_card_v2.html:315` | 의도된 이득. 사용자에게 확인(6절 질문 8) |
| 완료·생산·시공 행을 배지로 | `resolve_current_quest` 가 None → 모바일 상세 "현재 작업" 칸도 사라짐. 생산 "제작중" 판정은 run 조회가 필요해 주문 대시보드 쿼리 증가 가능 | `erp_quest_display.py:67-68,96-101`, `production_dashboard_display.py:147-162` | pre_push_smoke 성능 가드·구간 계측으로 확인. 모바일 칸 변화 실화면 확인 |
| 확인창·토스트가 STAGE_LABELS 인용 | 단계 이름을 안 바꾸는 한 영향 없음 | `quest_approve_cta.py:83-103`, `dashboard_main.html:197` | 단계 이름 유지 |
| 제목 문자열 테스트 | 저장 title 이 그대로 나온다고 가정 | `tests/domains/test_erp_quest_display.py:345,354-356`, `tests/domains/test_auth_quest_read.py:133`, `tests/domains/test_measurement_drawing_transfer_cta.py:143`; 템플릿 코드 `tests/domains/test_tablet_t2_contract.py:1381` | 기대값 갱신 + "저장 title 이 옛 이름이어도 새 이름이 나온다" 테스트 추가 |
| 승인·완료·재전이 이름 테스트 | 버튼 글자 변경 시 단언 수정 | `test_erp_quest_display.py:238-388`, `tests/domains/test_quest_surfaces_retransition_and_team_buttons.py:93-131`, `tests/domains/test_confirm_to_production_display.py:110-242`(PC 그리드 185-199), `tests/visual/test_p1_mockup_structure.py:559` | 단계별로 함께 수정 |
| PC 그리드 고정 글자·클래스 핀 | "(승인 권한 없음)"·"(보드에서 진행)" 단언. 클래스·ID 핀은 유지해야 함 | `test_quest_surfaces_retransition_and_team_buttons.py:266,278,288-300,389`; `test_confirm_to_production_display.py:168-210` | 글자 단언만 바꾸고 `quest-collapse-`·`erp-quest-done`·`erp-btn-retransition`·`erp-btn-approve-assignee` 는 유지 |
| 실측·태블릿 문구 테스트 | 버튼 이름·막힘 문구·시트 문구 | 실측 버튼 이름 `tests/domains/test_measurement_drawing_transfer_cta.py:162`(`DRAWING_TRANSFER_LABEL == "도면 전달"`), 막힘 문구 `:315,324`, `tests/domains/test_measurement_drawing_transfer_button.py:55,79`("도면 전달" 단언); 확인창(바뀌지 않음) `test_measurement_drawing_transfer_button.py:56`; 태블릿 `tests/domains/test_tablet_dashboard_sheet_contract.py:192,207-208,242-257` | 5단계에서 함께 수정. `tests/domains/test_production_start_requires_confirm_quest.py:99` 는 STAGE_LABELS 로 만든 문구라 단계 이름을 안 바꾸면 안 깨진다 — 바꾸지 않음 |
| 팀 이름 사본 여러 곳 | 한 곳만 바꾸면 화면마다 또 갈린다. 팀 이름을 박은 테스트는 없음(`tests/domains/test_order_flag_permissions.py` 의 "라홈팀" 은 문서 문자열 `:5,114` 뿐) | 서버 사본 `foms/web/orders/dashboard.py:189`, `foms/web/construction/dashboard.py:64`, `foms/web/production/dashboard.py:84`; 진짜 JS 사본은 `erp-order-shared.js:6001-6011` 하나. `erp-dashboard-quest.js` TEAM_LABELS 는 사본이 아니라 서버 값을 받아 씀(`templates/orders/partials/dashboard_main.html:197` data-team-labels → `static/js/orders/dashboard/erp-dashboard-core.js:51`) | 도메인 상수 모듈 하나로 모으고 위치-고정 계약 테스트 추가 |
| 인라인 스타일 ratchet | `dashboard_grid.html` 이 이미 인라인 스타일을 많이 씀. 새로 넣으면 ratchet 테스트가 잡는다 | `dashboard_grid.html:54-66,334-377` | 새 배지·버튼은 `static/css/foundation/erp-pro.css` 클래스로 |
| json 죽은 필드·구조 정리 | data 파일·정책 변경. 캐시가 파일 수정 시각 기준이라 배포 없이 같은 프로세스에 바로 반영 | `erp_policy_data_access.py:101-132` | Spec 승인 뒤 |
| 작업 템플릿 복제본 | 경로가 `scripts/ops/data` 라 정본 영향 없는 죽은 코드. 안 지우면 문자열이 어긋난 채 남는다 | `scripts/ops/erp_build_step_runner.py:597-626` | 정리 단계에서 삭제 |

### 3-2. 문자열을 박은 테스트 목록 (파일:행)

| 분류 | 테스트 |
|---|---|
| 제목 | `tests/domains/test_erp_quest_display.py:345,354-356`; `tests/domains/test_auth_quest_read.py:133`; `tests/domains/test_measurement_drawing_transfer_cta.py:143` |
| 템플릿 코드 | `tests/domains/test_tablet_t2_contract.py:1381`(`o.current_quest.title`), `:1360`(열 이름 목록) |
| 승인·완료·재전이 이름 | `test_erp_quest_display.py:238,246,254-258,271,275,280,282,289-297,311,380,384,388`; `test_quest_surfaces_retransition_and_team_buttons.py:93,97,119,131`; `test_confirm_to_production_display.py:110,127,133,163,180,195,242`, PC 그리드 `:185-199`; `tests/visual/test_p1_mockup_structure.py:559` |
| 실측 버튼 이름·막힘 문구 | `tests/domains/test_measurement_drawing_transfer_cta.py:162`(`DRAWING_TRANSFER_LABEL == "도면 전달"`), `:315,324`(막힘 문구 단언); `tests/domains/test_measurement_drawing_transfer_button.py:55,79`("도면 전달" in html) |
| 확인창 | `test_erp_quest_display.py:241,261,279`; `test_quest_surfaces_retransition_and_team_buttons.py:95`; `test_measurement_drawing_transfer_button.py:56`(확인창, 바뀌지 않음) |
| 그리드 고정 글자 | `test_quest_surfaces_retransition_and_team_buttons.py:266,278,288,289,299,300,389` |
| 클래스·ID 핀(유지) | `test_confirm_to_production_display.py:168,179,194,196,199,208-210`; `test_quest_surfaces_retransition_and_team_buttons.py:264,276,287,298,383,441` |
| 태블릿 | `tests/domains/test_tablet_dashboard_sheet_contract.py:192,207-208,242-257` |
| 단계 키(바꾸지 않음) | `tests/domains/test_orders_pipeline_step_order.py:18-20`; `tests/domains/test_mobile_production_construction_actions.py:263,267-272`; `tests/visual/test_p1_mockup_structure.py:468`; `tests/contracts/runtime/foms_namespace_surface_tests.py:1843`; 한글 필터 키 조회 `test_confirm_to_production_display.py:92,191,207`, `test_unified_search_params.py:161,167`, `test_dashboard_control_tower.py:68-70`, `test_construction_dashboard_mobile.py:565`, `test_production_dashboard_mobile.py:161` |
| 생산 막힘 문구(바꾸지 않음) | `tests/domains/test_production_start_requires_confirm_quest.py:99` — STAGE_LABELS["CONFIRM"] 로 만든 문구라 단계 이름을 안 바꾸면 안 깨진다 |
| 팀 이름 | 팀 이름을 박은 테스트 없음(`tests/domains/test_order_flag_permissions.py` 의 "라홈팀" 은 문서 문자열 `:5,114` 뿐) |
| "A.~H." select | 단언하는 테스트 0건(grep `A\. 주문접수`) |

### 3-3. title 을 키로 쓰는 로직 전수 — 없음

| 위치 | 용도 | 판정 |
|---|---|---|
| `erp_quest_display.py:109,409` | 표시 전달 | 표시만 |
| `dashboard_grid.html:128,140` | PC 버튼·카드 제목 | 표시만 |
| `construction/partials/filters_grid.html:111,123` | 시공 대시보드 | 표시만(닿지 않는 갈래) |
| `tablet_dashboard_sheet.html:27`, `tablet_workqueue_grid.html:66` | 태블릿 | 표시만 |
| `order_detail_mobile_v2.html:128,263,268` | 모바일 "현재 작업" + 하단 버튼 조건 | 비어 있는지만 본다. 이름 바꿔도 안전 |
| `erp_mobile_queue_card_v2.html:253,315,352` | 카드 노출 조건·aria-label | 같음 |
| `object.html:247`, `erp-order-shared.js:6062` | 옛 화면 | 죽은 코드 |
| `order_event_display.py:499-502` | 변경 이력 문장 | 죽은 분기 |
| `_audit_quest` (`foms/api/quest.py:185,576`) | 감사 note | title 안 씀 |
| SQL·JSONB 검색, 알림 서비스 | — | quest title 참조 없음 |

quest 매칭은 전부 `quest.stage` 로 한다(`erp_policy_quests.py:68-74`, `quest_transition_service.py:116-122`, `foms/api/production/orders.py:391-393`). 그래서 title 을 표시 계층에서 덮어써도 동작은 바뀌지 않는다.

---

## 4. persona 별 장면

목업 파일의 persona 탭 이름과 같다. 목업: scratchpad `pc-quest-mockup.html`(게시 예정). 가상 고객명은 `CLAUDE-TEST-` 만 쓴다.

| 이름 | 팀 | 주로 여는 PC 화면 | 헷갈리는 순간 (전) | 바뀐 뒤 장면 (후) |
|---|---|---|---|---|
| 김상담 (CS 상담) | CS(라홈·하우드) | 주문 대시보드 `/erp/dashboard` 작업 큐, 주문접수·CS 행 | [진행중] [주문 정보 확인] → 펼치면 "현재 단계 퀘스트", 담당 팀 "라홈팀", "라홈팀 [승인]". 휴대폰에서는 같은 일이 "접수 확인" 이라 같은 일인지 헷갈린다 | [할 일] [접수 내용 확인하기] → 펼치면 "현재 작업", 설명 "주문 내용을 확인하고 실측으로 넘겨요", 담당 팀 "CS팀", 소제목 "누를 버튼", 버튼 안 1 "접수 확인 → 실측 전달" / 안 2 "실측 단계로 넘기기". 휴대폰 카드 버튼 "접수 확인" 과 앞 글자가 같다(휴대폰에는 "→ 실측 전달" 이 붙은 버튼이 없다 — 새 문구). CS 행은 "CS/AS 접수 및 처리" → 제목 "CS 문의 확인하기", 버튼 "CS 확인" |
| 박영업 (영업 실측 담당) | 영업(SALES) | 주문 대시보드 실측 행 + 실측 대시보드 | 주문 목록은 [실측] + [승인], 실측 대시보드는 [도면 전달], 휴대폰은 [실측 완료] — 같은 일에 이름이 넷, "도면 전달" 은 도면팀 일과 겹친다 | 주문 목록 제목 [실측 결과 올리기] → 버튼 안 1 [실측 완료 → 도면 전달](휴대폰 아래 큰 버튼과 같은 글자) / 안 2 [도면 단계로 넘기기], 실측 대시보드도 같은 안. 고객컨펌 행은 제목 [고객 컨펌 받기] → 버튼 안 1 [고객 컨펌 완료 → 생산 전달] / 안 2 [생산 단계로 넘기기](둘 다 휴대폰에 없는 새 문구), 권한 안내는 "담당자만 누를 수 있어요". 끝나면 완료 배지 "실측 완료"·"고객 컨펌 완료" 가 제목과 다른 글자라 할 일과 끝난 상태가 갈린다 |
| 이도면 (도면 담당) | 도면(DRAWING) | 주문 대시보드 도면 행 "도면 창구" 카드 + 도면 창구 막대 | 주문 목록 카드는 "확정 대기", 도면 창구 막대는 "확정대기", 버튼 "별도 작업실 열기" | 두 화면 모두 "확정 대기"·"수정 요청됨", 버튼 "도면 창구 열기"(휴대폰과 같은 이름). 도면은 승인 버튼이 없는 단계라 퀘스트를 되살리지 않는다 |
| 최생산 (생산 관리) | 생산(PRODUCTION) | 주문 대시보드 생산 행 + 생산 대시보드 | 주문 목록 [진행중] [생산] → "생산팀 (보드에서 진행)", 생산 보드 칸은 "생산 중", 막대는 "제작중" | 주문 목록 [제작대기] + [생산 보드 열기], 생산 보드 칸도 "제작중". 누를 수 없는 승인 칸이 사라진다 |
| 시공 줄을 보는 CS·관리자 (정시공 본인은 바뀌는 것 없음) | 시공(CONSTRUCTION)·출고 / CS·관리자 | 정시공: 시공 보드 `/erp/construction`·출고 `/erp/shipment` 만. 시공팀은 주문 대시보드 등 다른 `/erp/` 화면에 들어가면 출고 화면으로 튕겨 나간다(`foms/platform/http.py:267-282`). 주문 목록 시공 줄은 CS·관리자가 본다 | 주문 목록 시공 행은 "-" 만 보여 CS·관리자가 시공 상태를 모른다 | 주문 목록 시공 행에 [시공대기] 배지 + [시공 보드 열기](CS·관리자 화면). 정시공 본인 화면(시공 보드·출고)은 바뀌는 것 없음 — 시공 보드 버튼 이름(`templates/construction/partials/filters_grid.html:73,79,85,93`)은 휴대폰과 같아 그대로 |
| 한대표 (관리자) | 관리자(ADMIN) | 주문 대시보드 프로세스 맵 + 작업 큐 전체 | 완료 행이 [진행중] [완료] "라홈팀 (보드에서 진행)", CS 행이 "CS/AS 접수 및 처리", 팀 이름은 라홈팀·상담팀·CS팀이 섞임 | 완료 행은 초록 [완료] 하나, CS 행은 제목 [CS 문의 확인하기] + 버튼 [CS 확인], AS 행은 [AS 작업] 또는 [AS 확인](사용자 선택) + [AS 화면 열기], 팀 이름은 한 벌. 막대 9칸 이름과 숫자는 그대로 |

persona 근거: CS 팀 정의 `foms/web/auth/routes.py:69`, 영업 정규화 `foms/services/orders/order_mutation_policy.py:47`, 시공팀 강제 이동 `foms/platform/http.py:267-282`(시공 보드·출고·완료·이력 외 `/erp/` 는 출고 화면으로), 관리자 전체 범위 `foms/services/erp_permissions.py:109-110`. 누가 PC 를 주로 쓰는지는 근거 없음(추정).

---

## 5. 구현 단계 제안

### 5-1. 결정 기록 (CEO decisions 전 항목)

| 결정 | 이유 |
|---|---|
| "모바일 프로세스 이름" 의 정본은 모바일 승인 버튼 이름표 `_QUEST_APPROVE_LABELS` 와 완료 배지 `done_label` 로 정한다(`quest_approve_cta.py:24-46`) | 모바일 "현재 작업" 칸은 PC 와 같은 옛 quest title 을 찍고 있어(`order_detail_mobile_v2.html:268`) 정본이 될 수 없고, 큐 카드는 제목 칩을 "단계 배지와 같은 말 반복" 이라 뺐으며(`erp_mobile_queue_card_v2.html:98-99`), 버튼 이름이 가장 최신(09-17·09-23 사용자 요청 반영)이고 큐 카드·상세 버튼 두 곳(실측은 하단 고정 버튼까지 세 곳)에서 가장 많이 쓰인다. 단 "생산 확인"·"시공 확인"·"AS 확인" 은 사전에만 있고 화면에는 안 나온다(`quest_approve_authz.py:201-202`, `erp_quest_display.py:67,331-334`) |
| 모바일 동작 이름(접수 확인·실측 완료·고객 컨펌 완료·CS 확인)은 **실제 누르는 승인 버튼에만** 쓴다. 퀘스트 제목 자리에는 할 일 모양의 말을 쓴다: 접수 내용 확인하기·실측 결과 올리기·고객 컨펌 받기·CS 문의 확인하기. AS 는 "AS 작업"(모바일 상세에 실제로 보이는 이름)과 "AS 확인"(이름표 사전 값, 화면에 안 나옴) 중 사용자가 고른다 | PC 제목 자리는 펼치기만 하는 토글 버튼이다(`templates/orders/partials/dashboard_grid.html:121-129` data-bs-toggle=collapse 안의 `<strong>{{ title }}</strong>`). 여기에 "실측 완료" 같은 동작 이름을 넣으면 누르면 끝나는 버튼처럼 보인다. 또 완료 배지는 '완료' 로 끝나는 이름을 그대로 돌려줘서(`quest_approve_cta.py:42-46` `_done_label`) 제목 "실측 완료"(할 일)와 배지 "실측 완료"(끝남)가 같은 글자가 된다. 할 일 모양 제목 네 개는 모바일에 없음 — 새 문구. "실측/실측" 처럼 단계 이름을 되풀이하던 정보 없는 제목도 함께 없어진다. 다른 안(모바일 카드처럼 동작 버튼을 칸에 바로 꺼내고 토글은 "자세히")은 6절 질문 9 |
| 상태 배지 "진행중" 은 "할 일" 로 | "진행중 [실측 완료]" 는 끝났는지 헷갈린다. 모바일에는 이 배지가 없어 새 문구 |
| PC 펼침 카드 승인 버튼은 누르면 일어나는 일을 말한다: 단계를 넘기면 안 1 "{이름} → {다음 단계} 전달" 또는 안 2 "{다음 단계} 단계로 넘기기"(사용자 선택, 6절 질문 5), 기록만 하면 이름만. 펼침 카드 소제목 "승인" 은 "누를 버튼" 으로 | 서버가 이미 approve_label·next_stage_label·advances_stage 를 PC payload 에도 넣어 준다(`erp_quest_display.py:370-420` → `quest_approve_cta.py:60-140`). 모바일 "{이름} → {다음 단계} 전달" 은 실측 단계 + 담당자 방식의 하단 고정 버튼에서만 뜬다(`order_detail_mobile_v2.html:119,125-133,419`). 접수·컨펌에서는 안 1 도 모바일에 없음 — 새 문구이고, 모바일에 실제로 있는 글자는 카드 "접수 확인"(`erp_mobile_queue_card_v2.html:309`), 상세 "고객 컨펌 완료"(`order_detail_mobile_v2.html:313`), 상세 팀 버튼 "CS 접수 확인"(`:338`) 이다. 모바일도 같이 바꿀지는 6절 질문 10 |
| json 을 고치는 대신 표시 계층에서 단계 코드로 이름을 고른다(`erp_quest_display.py:409`, `foms/api/quest.py:126-131`) | title 이 DB 에 복사 저장돼 json 만 바꾸면 섞인다. title 을 키로 쓰는 로직은 없어(죽은 분기 `order_event_display.py:499-502` 뿐) 덮어써도 동작은 안 바뀐다. 저장값·단계 코드·DB 값은 그대로 |
| 파이프라인 막대 9칸 이름은 바꾸지 않는다 | 모바일 홈 타워가 같은 process_steps 를 써서 이미 같고(`dashboard_mobile_tower.html:124-133`), label 이 곧 필터 키. 줄일지는 사용자에게 묻는다 |
| 도면은 퀘스트를 되살리지 않고 "도면 창구" 카드 유지, 버튼만 "도면 창구 열기". 하위 상태는 "확정 대기"·"수정 요청됨" 으로 통일 | 도면은 전용 명령 단계라 승인 API 가 409(`foms/api/quest.py:358-367`) |
| 생산·시공 행은 가짜 quest 대신 보드 이름(제작대기·제작중 / 시공대기·시공중)과 "보드 열기" 링크. "생산 중" 은 "제작중" 으로 | 모바일 생산·시공 보드가 이 이름을 쓰고, "생산 확인"·"시공 확인" 은 이름표 사전 값일 뿐 어디에도 나오지 않는 이름(`quest_transition_service.py:65-75`, `quest_approve_authz.py:201-202`, `erp_quest_display.py:67`) |
| 완료 단계는 초록 "완료" 배지만 | 할 일이 없는 단계에 "진행중"·"(보드에서 진행)" 이 떠서 헷갈린다. 모바일도 버튼이 없다(`quest_approve_cta.py:23`) |
| CS 제목에서 AS 를 뺀다(제목 "CS 문의 확인하기", 버튼 "CS 확인") | AS 는 별도 축이고 파이프라인도 CS·AS처리가 따로(`foms/services/orders/as_cycle_service.py:14-16`, `dashboard_read_model.py:364-366`) |
| 실측 대시보드 "도면 전달" 버튼은 주문 목록 승인 버튼과 같은 안으로(안 1 "실측 완료 → 도면 전달" / 안 2 "도면 단계로 넘기기"). 막힘 문구의 개발 용어도 쉬운 말로 | "도면 전달" 단독은 도면팀 파일 전달과 겹친다(`drawing_transfer_cta.py:7-8`). 안 1 도 "도면 전달" 글자를 품어 겹침이 남는다 |
| 팀 이름은 "CS팀·영업팀·도면팀·생산팀·시공팀·출고팀" 한 벌을 잠정안으로 | "라홈팀" 은 하우드 직원에게 틀리고, 모바일은 "CS", json display_name 도 "CS팀". 최종은 사용자 확인 |
| 설명은 모바일에도 없으므로 펼침 카드에 짧은 한 줄 새 문구로 넣는 안을 제안 | 넣을지는 사용자에게 묻는다 |
| 하위 작업(order_tasks)은 이번 화면 변경 범위에서 뺀다 | 어느 화면에도 안 보인다. json 정리 단계에서 이름·담당 팀만 맞춘다 |
| 죽은 표면(object.html, erpRenderQuest, loadQuestDetail, 시공 퀘스트 갈래)은 이름을 바꾸지 않고 삭제 후보로 | 바꿔도 사용자 눈에 안 보이고 테스트 핀만 늘어난다 |
| 이번 작업은 검토 + 목업까지. 표시 계층만(1~5단계)은 짧은 Spec, json 구조 정리·API 응답 title 변경은 Spec 승인 뒤 | CLAUDE.md "코어 변경은 Spec → 승인" |

### 5-2. 단계

| 단계 | 할 일 | 바꿀 파일:행 | Spec |
|---|---|---|---|
| 0 | 이 보고서의 이름표와 6절 질문 답을 받아 짧은 Spec 로 확정. 표시 계층만 바꾸고 DB·단계 코드·필터 키는 그대로임을 명시 | — | 짧은 Spec(승인 필요) |
| 1 | 표시 이름 SSOT: `quest_approve_cta.py` 옆(예 `quest_display_names.py` 또는 같은 모듈)에 단계 코드 → {제목, 설명} 표. `build_current_quest_payload` 의 title/description 과 GET 응답을 이 표로 덮어쓴다. 표에 없는 코드는 저장 title 로(빈 문자열 금지) | `foms/services/erp_quest_display.py:409-410`; `foms/api/quest.py:126-131`; 테스트 `test_erp_quest_display.py:345,354-356`, `test_auth_quest_read.py:133` + 옛 저장 title 이어도 새 이름이 나오는 테스트 추가 | 짧은 Spec. 단 API 응답 title 변경은 API 계약이라 Spec 승인 뒤(CEO 설계) |
| 2 | 팀 이름 SSOT: TEAM_LABELS 세 사본과 이벤트 표·JS 사본을 도메인 상수 모듈 하나로. 모바일 팀 버튼과 모바일 승인 알림의 남은 팀(`static/js/foms/erp-quest-approve.js:59`)도 한글 이름 | `foms/web/orders/dashboard.py:189`; `foms/web/construction/dashboard.py:64`; `foms/web/production/dashboard.py:84`; `order_event_display.py:25-33`; 진짜 JS 사본 `erp-order-shared.js:6001-6011` 하나(`erp-dashboard-quest.js` TEAM_LABELS 는 서버 값을 받아 씀 — `dashboard_main.html:197` → `erp-dashboard-core.js:51`, 고칠 필요 없음); `order_detail_mobile_v2.html:325,328,338`; 위치-고정 계약 테스트 추가 | 짧은 Spec |
| 3 | PC 주문 그리드: 열 이름·머리글 "현재 작업", 상태 배지 "할 일"/done_label, 승인 버튼 approve_label(+ advances_stage 면 "→ {next_stage_label} 전달"), 권한 안내 두 줄 쉬운 말. JS 다시 그리기·토스트도 같은 글자. 클래스·ID 유지, 새 인라인 스타일 금지 | `dashboard_grid.html:14,56,106-120,134,147,172-212`; `erp-dashboard-quest.js:69-81,117-126,141-172`; `static/css/foundation/erp-pro.css` | 짧은 Spec |
| 4 | 생산·시공·완료 행: 완료는 초록 배지만, 생산은 제작대기/제작중 + 생산 보드 링크, 시공은 시공대기/시공중 + 시공 보드 링크. DTO 에 필요한 값만 추가, 구간 계측으로 쿼리 증가 측정, 모바일 "현재 작업" 칸 변화 확인 | `dashboard_grid.html:208-210,327-331`; `foms/services/orders/dashboard_dto.py:59-66`; `erp_quest_display.py:67-68,96-101` | 짧은 Spec(성능 측정 결과 첨부) |
| 5 | 주변 표면: 실측 대시보드 버튼·막힘 문구, 태블릿 시트, 생산 보드 "생산 중"→"제작중", 도면 창구 막대 "확정 대기"·"수정 요청됨", 주문 상세 JS 도면 배지 "확정 대기중"→"확정 대기", 편집 폼·강제 변경 select "A.~H." 떼기, CS 완료 막힘 문구 "퀘스트 칸"→"현재 작업 칸". 옛 JS 단계 표 `ERP_STAGE_LABELS` 는 죽은 코드라 이름을 안 바꾸고 6단계 삭제 후보 | `drawing_transfer_cta.py:33-37`; `tablet_dashboard_sheet.html:24-94`; `production/partials/filters_grid.html:93`; `workbench_dashboard_body.html:54,60`; `static/js/orders/dashboard/erp-dashboard-detail-dom.js:371,378`(노출 화면은 추정); `erp_order_tab.html:220-228`; `erp_stage_override_modal.html:27-35`; `tablet-measure-form.js:64-77`; `complete_path_policy.py:150-166`; 삭제 후보 `static/js/orders/erp-order-shared.js:6019-6031` | 짧은 Spec |
| 6 | 정리(별도 Spec): json title·description 을 새 이름으로 맞추고 죽은 필드 정리, `erp_task_templates.json` 이름·담당 팀 맞춤, 복제본·죽은 표면·죽은 분기 삭제, "시공 확인" 이름 삭제 검토 | `data/erp_quest_templates.json`; `data/erp_task_templates.json`; `scripts/ops/erp_build_step_runner.py:597-626`; `object.html`; `erp-order-shared.js:6046-6140`; `production/partials/scripts.html:380-419`; `construction/partials/filters_grid.html:97-163`; `order_event_display.py:499-502`; `quest_approve_cta.py:29` | Spec 승인 필요(data·정책 변경) |

### 5-3. 검증 (각 단계 공통)

- `python -c "import app; print('APP_OK')"`
- `pytest tests/domains/test_erp_quest_display.py tests/domains/test_quest_surfaces_retransition_and_team_buttons.py tests/domains/test_confirm_to_production_display.py tests/domains/test_auth_quest_read.py tests/domains/test_measurement_drawing_transfer_cta.py tests/domains/test_measurement_drawing_transfer_button.py tests/domains/test_tablet_dashboard_sheet_contract.py tests/domains/test_tablet_t2_contract.py tests/domains/test_orders_pipeline_step_order.py tests/domains/test_production_start_requires_confirm_quest.py tests/visual/test_p1_mockup_structure.py`
- JS 편집 시 `node --check <파일>`
- `scripts/ops/pre_push_smoke.ps1` exit 0 (파이프 뒤 exit 를 읽지 말 것)
- 실제 dev 서버에서 PC 그리드 9단계 실화면 + 모바일 상세 "현재 작업" 확인(실데이터 시드, 주입 행 금지)

---

## 6. 사용자에게 물을 것

1. 담당 팀 이름을 하나로 맞추려고 해요. "CS팀" 으로 부를까요, 지금 PC 처럼 "라홈팀" 으로 부를까요? (하우드 직원도 같은 팀이에요)
2. 주문 목록의 "퀘스트" 칸 이름을 모바일처럼 "현재 작업" 으로 바꿀까요?
3. 펼친 칸 안에 "무엇을 하는 단계인지" 짧은 설명 한 줄을 새로 넣을까요? (지금은 모바일에도 없어요)
4. 파이프라인 막대 이름(주문접수·고객컨펌·AS처리)은 모바일 홈과 이미 같아요. 그대로 둘까요, 모바일 카드처럼 "접수·컨펌" 으로 줄일까요?
5. 다음 단계로 넘기는 버튼 이름을 골라 주세요. 안 1 "실측 완료 → 도면 전달" 처럼 끝에 "전달" 을 붙이는 이름, 안 2 "도면 단계로 넘기기" 처럼 넘어갈 곳만 말하는 이름. 휴대폰에서 "→ 전달" 이 붙은 큰 버튼은 실측 단계에만 있어요. 접수·고객 컨펌 단계는 어느 안이든 새로 만드는 글자예요. 그리고 안 1 은 "도면 전달" 글자를 품고 있어서, 도면팀이 도면 파일을 넘기는 "도면 전달" 과 헷갈리는 문제가 새 이름에도 남아요.
6. 실측 대시보드의 "도면 전달" 버튼도 5번에서 고른 이름으로 바꿔도 될까요? (지금 이름은 도면팀의 "도면 전달" 과 똑같아요. 안 1 을 고르면 앞에 "실측 완료 →" 가 붙어 조금 나아지지만 "도면 전달" 글자는 그대로 남아요)
7. 생산·시공 단계 줄에 가짜 승인 칸 대신 "제작중"·"시공대기" 같은 보드 상태와 "보드 열기" 버튼을 보여 줄까요? (조회가 조금 늘 수 있어요)
8. 이 이름 바꾸기가 모바일 "현재 작업" 글자도 같이 바꾸는데 괜찮을까요?
9. 주문 목록의 제목 칸은 지금 누르면 펼쳐지기만 하는 버튼이에요. 어떻게 할까요? 가 안: 제목은 "실측 결과 올리기" 처럼 할 일로 쓰고, 끝내는 버튼은 펼친 안에만 둔다. 나 안: 휴대폰 카드처럼 끝내는 버튼("실측 완료")을 칸에 바로 꺼내 두고, 펼치는 버튼은 "자세히" 로 바꾼다.
10. PC 에 새로 생기는 버튼 이름(예 "접수 확인 → 실측 전달", "고객 컨펌 완료 → 생산 전달")을 휴대폰 버튼에도 똑같이 넣을까요, 휴대폰은 지금("접수 확인", "고객 컨펌 완료")대로 둘까요?
11. AS 단계 줄 제목을 "AS 작업"(휴대폰 상세에 지금 보이는 이름)으로 할까요, "AS 확인"(버튼 이름표에만 있고 화면에는 안 나오는 이름)으로 할까요?

---

## 7. 확인 못 한 것 (추정 목록)

| 항목 | 왜 모르나 | 확인 방법 |
|---|---|---|
| 스테이징·운영에 저장된 quest title 분포 | 로컬 dev DB 는 quest 2건(RECEIVED "주문 정보 확인", CONFIRM "고객 컨펌")뿐. 코드 주석상 수백 건 이상(`erp_policy_quests.py:149-150,159`) | 아래 SQL 을 스테이징에서 읽기 전용으로(이 보고서에서는 실행하지 않음) |
| 완료 행 "진행중 + 완료" 실화면 | 코드로만 판단(`dashboard_grid.html:119`, `erp_quest_display.py:159-161`) | dev 서버 실화면 |
| 모바일 CS 팀 버튼 "CS CS 확인" | `order_detail_mobile_v2.html:338` 조합으로 추정 | 모바일 상세 실화면 |
| AS 배지 색이 접수 색으로 칠해짐 | 색 표에 AS 코드 없음(`erp_mobile_order_display.py:498-515`) | 모바일 큐 실화면 |
| "완료 완료" 배지 가능성 | `_done_label(None, "완료")`(`quest_approve_cta.py:46`) | 완료 단계 quest 가 끝난 상태인 주문 조회 |
| 생산 "제작중" 판정 쿼리 비용 | 주문 대시보드에 run 조회 추가 시 | 구간 계측·perf-gate |
| 주문 상세 JS 도면 배지 "확정 대기중" 이 보이는 화면 | `erp-dashboard-detail-dom.js:371,378` 은 로드되지만 어느 화면에서 그려지는지 실화면 미확인 | dev 서버 주문 상세 |

저장 title 분포 조회 예시(실행하지 않음):

```sql
SELECT q->>'stage' AS stage, q->>'title' AS title, count(*) AS n
FROM orders o, jsonb_array_elements(o.structured_data->'quests') AS q
WHERE jsonb_typeof(o.structured_data->'quests') = 'array'
GROUP BY 1, 2
ORDER BY 1, 3 DESC;
```

---

## 다음 할 일

1. 6절 질문 11개의 답을 받는다.
2. 답을 반영해 0단계 짧은 Spec 를 쓰고 승인을 받는다.
3. 승인 뒤 1단계(표시 이름 SSOT)부터 5-3 검증 명령으로 하나씩 진행한다.

---

## 7. 사용자 결정 (2026-09-30)

- 퀘스트 제목은 **휴대폰 이름 그대로**: 접수 확인 · 실측 완료 · 고객 컨펌 완료 · CS 확인 · AS 확인(`quest_approve_cta.py:24-32` 이름표). 5-1 의 "할 일 모양 새 말" 안은 기각.
- 다음 단계로 넘기는 버튼은 **"{다음 단계} 단계로 넘기기"**(실측 단계로 넘기기 · 도면 단계로 넘기기 · 생산 단계로 넘기기). 휴대폰 하단 큰 버튼(`order_detail_mobile_v2.html:419`), 실측 대시보드 버튼(`drawing_transfer_cta.py:33-37`), 태블릿도 같은 글자로 바꾼다. 안 1("… → … 전달")은 기각.
- 팀 이름은 **CS팀** · 영업팀 · 도면팀 · 생산팀 · 시공팀 · 출고팀 한 벌.
- 목업 v2(간결판)를 기준 목업으로 삼는다. v1 은 근거 경로가 붙은 상세판.
