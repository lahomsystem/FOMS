# 페르소나 검수 브리프 — 스테이징 실서버 (2026-09-20)

사용자 결정: 페르소나 검수는 로컬이 아니라 **스테이징 실서버**에서 한다. CEO 의 페르소나 브리프
(`docs/plans/2026-09-17-confirm-flow-ceo-design.json` 키 `brief_persona`)의 시나리오·보고 형식은 그대로 쓰되,
환경 절은 아래로 대체한다.

## 환경

- 스테이징: `https://lahom-dev.up.railway.app` — deploy `0cb601e7b` 가 배포돼 있다(자산 핀 `?v=20260920a` 확인됨).
  운영(`lahom-production`)은 **절대 접속하지 않는다.**
- 계정: `claude_master`(ADMIN). 비밀번호는 `C:\Users\USER\.claude\projects\c--DEV-FOMS\secrets\claude_master.json` 의 `staging.password`
  (파일을 읽어 쓰고, 값을 보고서·로그·프롬프트에 적지 않는다).
- 팀별 페르소나 계정은 `/admin/users` 화면(또는 `POST /admin/api/users`)로 만든다. 이름은 `claude_persona_<a|b|c>_<team>`,
  비밀번호는 아무거나(보고에 안 적음), 팀 SALES/CS/DRAWING/PRODUCTION/CONSTRUCTION, role STAFF. 끝나면 **비활성화**한다.
- 주문 시드: 고객명은 반드시 `CLAUDE-TEST-PERSONA-<A|B|C>-…`, 연락처 `010-0000-0000`(실발송 차단). 끝나면 앱 경로 soft delete(`POST /delete/<id>`)로 정리.
  단계별 주문이 필요하면 ERP 주문 등록 마법사로 만들고, 단계 이동은 실제 버튼/API 로 밟는다. 이다은 재현(승인 완료·CONFIRM 잔류)은
  관리자 강제 단계 변경(`POST /api/orders/<id>/workflow/stage-override`, `to_stage`·`reason`·`confirm:true`)으로 CONFIRM 에 두고
  `PUT /api/orders/<id>/quest/status`·승인 API 조합으로 만든다. 못 만들면 그 사실을 적는다.
- HTTP 레시피(메모리 `staging-e2e-http-harness`): 로그인 `POST /login`(username·password·`csrf_token` 폼 필드), 이후 모든 POST/PUT 은
  `X-CSRF-Token`(페이지 `<meta name="csrf-token">`) + `Referer`/`Origin` 같은 출처. 데스크톱 화면은 Chrome desktop UA, 모바일 화면은
  iPhone UA(`Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile/15E148`). ADMIN 이 ERP 주문을 만들 땐 `sales_owner_id`(활성 SALES 사용자) 필수.
- 검색어 에코 오탐: 존재/부재 판정은 `data-order-id` 행 블록 안에서만.
- 브라우저가 필요하면 gstack-browse 스킬(반복 QA 용). 스크린샷은 `C:\tmp\foms-s-confirm-flow\docs\harness\evidence\persona-<A|B|C>-*.png`.

## 규칙

- **편집 금지**(코드·템플릿·테스트). 허용: 읽기·grep·HTTP·브라우저·pytest(로컬 sqlite 레인).
- 보고 파일은 **자기 것 하나만**: `docs/plans/2026-09-20-persona-audit-<A|B|C>.md`. git 금지. `C:/DEV/FOMS` 금지.
- 지도(`docs/plans/2026-09-17-pipeline-map-scout.md`) 16건은 다시 세지 않는다 — 재현되면 등급만, 범위 밖이면 "범위 밖·재현됨".
- 화면 주장은 실제 HTML 응답/스크린샷으로. 합성 DOM 주입은 검수가 아니다.
- 스테이징에 남긴 것(계정·주문·run)은 전부 원상 복구하고 보고서 끝에 "정리 목록" 을 남긴다. 정리 못 한 것은 id 를 적는다.
- 응답 코드·본문·`erp_stage_code`(`GET /api/orders/<id>/structured` 또는 대시보드 행)를 원문으로 남긴다.

## 이번 배포가 약속하는 것 (검수 기준)

1. 고객 컨펌 승인(PC 그리드 [승인]·모바일 큐 카드 [고객 컨펌 완료]·모바일 상세) → 단계 PRODUCTION, `blueprint.customer_confirmed`, 응답 `auto_transitioned True`·`next_stage "생산"`. PC 는 확인창 문구 "고객 컨펌을 완료하고 생산 단계로 넘길까요?".
2. 승인 뒤 같은 버튼 재요청 → 409 `ALREADY_TRANSITIONED`, 생산 퀘스트가 생기지 않는다.
3. 생산 보드: 제작대기 = CONFIRM(호환) 또는 PRODUCTION∧run 없음, 제작중 = PRODUCTION∧run. 제작 시작 = run 발급(단계 그대로), 제작 취소 = run 종결(단계 그대로, 제작대기 복귀), 제작 완료 = CONSTRUCTION.
4. 이다은 재현(CONFIRM·담당자 승인 완료): PC 그리드·큐 카드·상세에 "고객 컨펌 완료" 배지(승인 버튼 없음), 생산 보드 제작대기에 [제작 시작] → 200 → PRODUCTION + run.
5. 도면 단계 승인은 여전히 409 `COMMAND_REQUIRED`(버튼 없음). 권한(DRAWING/PRODUCTION 팀이 컨펌 승인 → 403) 불변.
6. 타임라인에 "고객 컨펌 완료"·"제작 취소" 라벨.
