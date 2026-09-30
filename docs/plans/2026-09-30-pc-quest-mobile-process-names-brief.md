# PC 퀘스트·세부 이름을 모바일 프로세스 이름으로 — 검토·목업 브리프 (2026-09-30)

> 이 문서는 **초안**이다. CEO 에이전트가 고쳐도 된다. 이번 작업은 **검토 + UI 목업**까지이고, 앱 코드 편집은 하지 않는다.

## 사용자 요청 (원문 요지)
- PC 화면의 **모든 단계**에서 퀘스트 이름과 세부(하위 작업·승인·설명) 이름을 **모바일에서 쓰는 프로세스 이름**으로 바꾼다.
- PC 퀘스트는 원시 legacy 부터 있던 것이라 지금 최신 흐름과 많이 다르다.
- 먼저 철저히 리뷰하고, 사용자 persona 별 UI 목업을 만든다.
- 사용자가 붙여 준 예: 주문 대시보드 표의 퀘스트 버튼 `<strong>주문 정보 확인</strong>`(RECEIVED 단계 quest title), 파이프라인 막대 `주문접수·실측·도면·고객컨펌·생산·시공·CS·완료·AS처리`.

## 앵커 (총괄이 먼저 찾은 것 — 출발점일 뿐, 전수 아님)
- quest 템플릿 원본: `data/erp_quest_templates.json` (version 2, "원본 Furniture Process 요구사항 기반 A→H") — 단계별 `title`·`description`·`process_flow`·`process_types` 가 legacy 문구.
  - RECEIVED `주문 정보 확인` / MEASURE `실측` / DRAWING `도면 작성` / CONFIRM `고객 컨펌` / PRODUCTION `생산` / CONSTRUCTION `시공` / CS `CS/AS 접수 및 처리` …
- 하위 작업 템플릿: `data/erp_task_templates.json` (예 `주문 정보 확인(고객/연락처/주소)`), `scripts/ops/erp_build_step_runner.py:603`.
- quest 해석·표시: `foms/services/erp_quest_display.py` (`resolve_current_quest` :49, `build_current_quest_payload` :371), `foms/services/orders/erp_policy_quests.py`, `foms/services/orders/quest_approve_cta.py`(승인 버튼 이름), `foms/services/orders/quest_transition_service.py`.
- 단계 이름 정본: `foms/services/orders/erp_policy_constants.py:14` `STAGE_LABELS`, 파이프라인 막대 `foms/services/orders/dashboard_read_model.py:357` `process_steps`.
- 모바일 쪽: `foms/services/erp_mobile_order_display.py` (`stage_badge_label` :518 짧은 표, 일정 라벨 :600~), `templates/orders/mobile_order_detail.html`, 모바일 홈 타워·큐(메모리: 기본은 타워, 같은 클래스).
- PC 퀘스트 표면: `templates/orders/partials/dashboard_grid.html:103~`, `templates/construction/partials/filters_grid.html:105~`, `templates/orders/object.html:131~`, `templates/production/partials/scripts.html:389`, `static/js/orders/dashboard/erp-dashboard-quest.js`, `static/js/construction/dashboard.js:874`. 실측·도면·출고·CS·AS 대시보드에도 있는지 전수 확인.
- persona 선행 자료: `docs/plans/2026-09-20-pipeline-persona-audit.md`, `docs/plans/2026-09-20-persona-audit-C.md`.

## 산출물
1. 검토 보고서: `docs/plans/2026-09-30-pc-quest-mobile-process-names-review.md`
   - 단계 × (PC 지금 이름 · 모바일 이름 · 제안 이름 · 근거 경로:행) 대조표 — 퀘스트 제목, 하위 작업, 승인 버튼, 설명, 완료 배지까지.
   - legacy 문구가 지금 흐름과 어긋나는 곳 목록(예: 흐름 설명이 옛 채널·옛 순서).
   - 바꿀 때 걸리는 것: 문자열을 박은 테스트, DB 에 복사된 quest 데이터(structured_data 안 title 저장 여부), 알림·로그 문구, 검색·필터 키.
   - 구현 단계 제안(Spec 필요 여부 — CLAUDE.md "코어 변경은 Spec → 승인").
2. UI 목업 HTML: scratchpad 의 `pc-quest-mockup.html` (총괄이 Artifact 로 게시). persona 별 PC 화면 전/후.

## 규칙
- 앱 코드·테스트·템플릿·data 파일 **편집 금지**(읽기만). 쓰기는 위 두 산출물 경로만.
- git 명령 금지(읽기 `git log`/`git show`/`git grep` 는 허용). 워킹트리에 다른 세션의 미커밋 변경(도면 마법사 등)이 있다 — 건드리지 않는다.
- 주장은 경로:행 근거와 함께. 추측은 "추정" 이라고 적는다.
- 사용자에게 보이는 문장은 한글, 한자 금지.
