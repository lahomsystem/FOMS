# PC 퀘스트 이름 3단계 — 정리 구현 브리프 (2026-09-30)

> 초안이다. CEO 가 코드와 대조해 확정한다(소유권 겹침 금지). 사용자 승인: "3단계 시작" (2026-09-30).

- 정본 Spec: `docs/specs/2026-09-30-pc-quest-mobile-names_SPEC.md` §5 **3단계** + 1·2단계에서 넘긴 잔여.
- 1단계 운영 PR #468, 2단계 deploy `202303781`(운영 PR #471 진행 중). 작업 트리 `c:\tmp\foms-s-pc-quest-names`(HEAD = origin/deploy `e766367bc`). Bash 는 매번 `cd /c/tmp/foms-s-pc-quest-names && ...`. `C:\DEV\FOMS` 편집 금지.
- 원칙: 사용자 화면에 보이는 이름은 1·2단계 이름표와 같게. 동작(API·전이·권한·필터 키·DB 값) 변화 0. 안 쓰는 코드는 **호출처 0 을 grep 으로 증명한 뒤** 지운다.

## 대상 (CEO 가 전수 확인·가감)

1. **태블릿 두 화면** — `templates/orders/partials/tablet_workqueue_grid.html:66`, `templates/orders/partials/tablet_dashboard_sheet.html:7` 가 아직 `current_quest.title`("생산 확인"·"완료"·"AS 확인")을 쓴다. 주문 목록과 같게 `board_state` 가 있으면 그 글자(배지·링크), 없으면 1단계 제목. 2단계에서 되돌린 태블릿 시트 라우트의 `production_run_ids`(`foms/web/orders/dashboard.py` 태블릿 시트)를 이제 쓴다(주문 1건 = 최대 1회 조회).
2. **편집 화면 퀘스트 카드** — `static/js/orders/erp-order-shared.js` 의 퀘스트 카드 "승인" 버튼·확인창·`erpRenderQuest` 등. 살아 있으면 1단계 이름(approve_label·task_label·team_label)으로, 죽었으면(호출처 0) 삭제.
3. **죽은 표면 삭제** — `templates/orders/object.html` 퀘스트 칸·`TEAM_LABELS` 사본(:154, 라우트 유무 확인), 시공 보드 그리드의 닿지 않는 `elif o.current_quest` 갈래(`templates/construction/partials/filters_grid.html:96-163`), `foms/services/order_event_display.py:499-502` 죽은 분기, `scripts/ops/erp_build_step_runner.py:597-626` 작업 템플릿 복제본.
4. **팀 이름 남은 곳** — `foms/api/drawing/erp_orders_drawing.py:412` `"라홈팀" if target_team == 'CS'` → `team_label`. `data/erp_quest_templates.json` 의 "라홈팀". 권한 안내 문구의 "라홈팀/하우드팀"은 실제 조직 설명이라 두는 게 기본 — CEO 판단.
5. **설정 파일 이름 맞춤** — `data/erp_quest_templates.json` 단계별 `title` 을 이름표와 같게(RECEIVED 접수 확인 …), 코드가 안 읽는 필드(process_flow·process_types·fail_process·notes 등 — **읽는 코드 0 을 grep 으로 증명한 것만**) 정리. `data/erp_task_templates.json` 이름·담당 팀 맞춤. 새 주문에 저장되는 title 이 바뀌는 것이므로 저장 title 을 단언하는 테스트 확인.
6. **편집 폼·강제 단계 변경 select** 의 "A. 주문접수 / C. 실측 …" 접두 제거(`erp_order_tab.html:220-228`, `erp_stage_override_modal.html:27-35`) — value 는 그대로.
7. **이름표 사전의 쓰이지 않는 이름** — `_QUEST_TASK_LABELS` 의 "생산 확인"·"시공 확인"이 2단계 뒤 어디에 보이는지 확인. 안 보이면 둘지 뺄지 CEO 가 정하고 이유를 적는다(뺄 때 `approve_label`·`done_label`·재전이 영향 확인).

## 함정

- `templates/construction/partials/scripts.html` 핀을 건드리면 성능 가드가 기존 "script 3개" 빚을 잡아 smoke 가 빨개진다(2단계 통합 검증자 실측). 시공 JS 는 이번에 고치지 않는 게 기본.
- 자산 핀: JS/CSS 를 고치면 `?v=` 를 올리고 핀 단언 테스트를 같이. 새 핀 글자 `20260930e`(W2), `20260930f`(W3). `erp-order-shared.js` 는 `asset_url()` 내용 해시 방식인지 먼저 확인.
- 태블릿 계약 테스트 2종은 핫 파일이다(세션 worktree 안이라 괜찮다).
- 새 import 는 모듈 맨 위(층 래칫). docs 를 읽는 테스트를 새로 만들지 않는다.
- 로컬 dev DB 에 시드했으면 끝나고 앱 경로(`POST /delete/<id>`)로 지운다.

## 파일 소유권 초안 (CEO 확정)

| 워커 | 편집 허용 |
|---|---|
| W1 서버·데이터 | `foms/**` 파이썬, `data/erp_quest_templates.json`, `data/erp_task_templates.json`, `scripts/ops/erp_build_step_runner.py`, 서버 테스트 |
| W2 PC 화면 | `templates/orders/object.html`, `templates/construction/partials/filters_grid.html`, `templates/orders/partials/erp_order_tab.html`, `templates/**/erp_stage_override_modal.html`, `static/js/orders/erp-order-shared.js`, 핀 파일, PC 테스트 |
| W3 태블릿 | `templates/orders/partials/tablet_workqueue_grid.html`, `templates/orders/partials/tablet_dashboard_sheet.html`, 태블릿 테스트 |

## 통합 검증

```
cd /c/tmp/foms-s-pc-quest-names
python -c "import app; print('APP_OK')"
python -m pytest -q --ignore=tests/visual -p no:playwright -n 8
# 인벤토리: 스캔 5종 --check (refresh_inventories.py 는 --check 가 없고 재생성까지 한다)
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/ops/pre_push_smoke.ps1   # exit 직접 읽기
```
