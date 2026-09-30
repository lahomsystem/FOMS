# PC 퀘스트 이름 후속 문제 — 진단·수정 브리프 (2026-09-30)

> 초안이다. CEO 가 진단 뒤 확정한다. 사용자 승인: "운영 + 후속 문제 고치기" (2026-09-30).
> 원칙(CLAUDE.md): 근본 원인만 고친다. 알림을 **누가 받는지** 바꾸는 일은 사용자 결정이 필요한 동작 변경이다 — 진단이 끝나면 선택지를 정리해 CEO 가 `needs_user_decision` 으로 올리고, 확실한 버그(받아야 할 사람이 0명)만 이번에 고친다.

- 작업 트리 `c:\tmp\foms-s-pc-quest-names`(HEAD = origin/deploy `766cd6bad`). Bash 는 매번 `cd /c/tmp/foms-s-pc-quest-names && ...`. `C:\DEV\FOMS` 편집 금지.
- 3단계 운영 PR #473 이 검사 중이다. 이 브리프의 변경은 그와 별개 커밋이다.

## F1. 하우드 발주 도면 알림 수신자 0명 가능성

- 근거(3단계 CEO): `foms/api/drawing/erp_orders_drawing.py:66-92` `_drawing_notice_target` 이 'CS'·'HAUDD'·'SALES'·None 을 돌려준다. :417 근처에서 'HAUDD' → '하우드팀' 문구. 그런데 `foms/web/auth/routes.py` TEAMS 에 HAUDD 가 없다.
- 진단할 것: ① 알림 수신자를 고르는 resolver(메모리: 도면 전달 알림 target_team+이름 합집합 버그를 2026-09-30 고쳤다 — PR #460 계열)가 target_team='HAUDD' 를 받으면 누구를 고르는지(코드 경로:행) ② users 표에 team='HAUDD' 인 사용자가 있을 수 있는 경로(가입·관리자 화면·마이그레이션)가 있는지 ③ 로컬 dev DB(postgres MCP, SELECT 만)에서 team 값 분포 ④ 운영 측정은 하지 않는다(사용자 요청 없음). 스테이징 읽기는 claude_master 로 허용.
- 판정: 0명이 확실하고 "같은 CS 팀(라홈·하우드)이 받는다" 가 코드·문구의 의도와 맞으면 그 방향으로 고친다(예: HAUDD → CS 팀 수신 + 문구 유지). 의도가 불명확하면 수정하지 말고 선택지 2~3개를 쉬운 말로.

## F2. 승인 변경 이력에 팀 이름이 빠짐

- 근거: `foms/services/order_event_display.py` 의 QUEST_APPROVAL_CHANGED 분기는 `payload['team']` 을 읽는데, 기록하는 `foms/api/quest.py:514-525, 555-566` 은 team 키를 넣지 않는다 → "이 퀘스트를 승인했습니다" 로만 나온다.
- 고칠 것: 기록 쪽 payload 에 team(팀 코드) 을 넣고, 표시 쪽은 `team_label` 로 한글 이름. 옛 이력(team 없음)은 지금처럼 나오게(깨지지 않게). 담당자 방식 승인은 팀 대신 사람 이름이 맞는지 확인.
- 이력 문구도 1단계 이름과 맞춘다: "승인" 대신 버튼 이름(예 "실측 단계로 넘기기"·"CS 확인")을 쓸 수 있으면 쓴다 — payload 에 이미 있는 값만으로.

## F3. 남은 죽은 코드

- `templates/orders/object.html` 파일째 삭제: 라우트 0 확인, 이 파일을 읽는 테스트 4곳(`tests/contracts/runtime/foms_namespace_surface_tests.py:1989` 존재 단언, `test_attachment_preview_fullscreen.py:51,159`, `test_erp_order_shared_form_scripts.py:1555`, `test_mobile_production_construction_actions.py:268`)을 같이 정리. 테스트가 이 파일로 **다른 것**(첨부 미리보기 등)을 검증하고 있으면 그 검증을 살아 있는 템플릿으로 옮긴다 — 커버리지를 잃지 않게.
- 시공 `static/js/construction/dashboard.js` 의 `approveQuestTeam`·`loadQuestDetail`(3단계에서 시공 그리드 갈래를 지워 부르는 곳이 사라짐). 함정: `templates/construction/partials/scripts.html` 핀을 올리면 성능 가드가 기존 "script 3개" 빚을 잡아 smoke 가 빨개진다. 핀을 안 올리면 옛 기기는 옛 파일(죽은 코드 포함, 동작 같음)을 쓴다 — 무해. CEO 가 (a) 핀 없이 삭제 (b) 빚을 먼저 갚고 핀 (c) 두기 중 고르고 이유를 적는다.
- `templates/orders/partials/dashboard_grid.html` 의 "(보드에서 진행)" 갈래(2단계 뒤 닿지 않는 것으로 추정) — 닿지 않음을 조건으로 증명할 수 있으면 삭제, 아니면 둔다.

## 파일 소유권 초안 (CEO 확정)

| 워커 | 편집 허용 |
|---|---|
| W1 알림(F1) | `foms/api/drawing/erp_orders_drawing.py`, 알림 resolver 파일, 관련 테스트 — **needs_user_decision 이면 편집하지 않고 진단 보고만** |
| W2 이력(F2) | `foms/api/quest.py`, `foms/services/order_event_display.py`, 관련 테스트 |
| W3 정리(F3) | `templates/orders/object.html`, `static/js/construction/dashboard.js`(CEO 결정 시), `templates/orders/partials/dashboard_grid.html`, F3 테스트 |

## 공통

- git 쓰기 금지, 줄끝 보존, 한자 금지, 주석 최소. 새 import 는 모듈 맨 위.
- 자기 테스트 `-n 4`, JS 는 파일마다 `node --check`.
- 통합: `APP_OK`, `python -m pytest -q --ignore=tests/visual -p no:playwright -n 8`, 스캔 5종 `--check`(drift 면 그 스캔으로 재생성), `pre_push_smoke.ps1` exit 직접 읽기.
