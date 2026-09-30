# PC 퀘스트 이름 1단계 구현 브리프 (2026-09-30)

> 초안이다. CEO 가 고쳐도 된다(소유권 표를 바꾸면 겹침이 없게).

- 정본 Spec: `docs/specs/2026-09-30-pc-quest-mobile-names_SPEC.md` — **§5 1단계(A~G)만** 구현. 2단계(생산·시공·완료·AS 줄 모양)·3단계(정리)는 손대지 않는다.
- 근거 보고서: `docs/plans/2026-09-30-pc-quest-mobile-process-names-review.md` (§3-2 테스트 목록, §7 사용자 결정)
- 작업 트리: `c:\tmp\foms-s-pc-quest-names` (브랜치 `session/pc-quest-names`, base origin/deploy `e14054aad`). Bash 는 매번 `cd /c/tmp/foms-s-pc-quest-names && ...` 로 시작한다(cwd 가 리셋된다). 파일 경로도 이 트리 기준 절대경로. **`C:\DEV\FOMS` 는 절대 편집하지 않는다.**

## 이름표 (Spec §4 — 고정)

| 단계 | task_label (제목) | approve_label (버튼) | done_label |
|---|---|---|---|
| RECEIVED | 접수 확인 | 실측 단계로 넘기기 | 접수 확인 완료 |
| MEASURE | 실측 완료 | 도면 단계로 넘기기 | 실측 완료 |
| CONFIRM | 고객 컨펌 완료 | 생산 단계로 넘기기 | 고객 컨펌 완료 |
| CS | CS 확인 | CS 확인 | CS 확인 완료 |
| PRODUCTION / CONSTRUCTION / AS | 생산 확인 / 시공 확인 / AS 확인 | 이름표 그대로(기록만) | 지금 규칙 |

- `retransition_label` = `approve_label` (단계를 넘기는 stage 만, 아니면 빈 문자열 — 지금 규칙).
- 넘기기 버튼 글자는 `f"{next_stage_label} 단계로 넘기기"` 로 만든다(next_stage_label 은 STAGE_LABELS → 실측·도면·생산).
- 팀 이름: CS→CS팀, SALES→영업팀, MEASURE→실측팀, DRAWING→도면팀, PRODUCTION→생산팀, CONSTRUCTION→시공팀, SHIPMENT→출고팀. 정본 모듈 `foms/services/orders/team_labels.py` (`TEAM_LABELS`).

## 파일 소유권 (겹치지 않는다 — 남의 파일은 읽기만)

| 워커 | 편집 허용 파일 |
|---|---|
| W1 서버 | `foms/services/orders/quest_approve_cta.py`, `foms/services/erp_quest_display.py`, `foms/api/quest.py`, 새 `foms/services/orders/team_labels.py`, `foms/web/orders/dashboard.py`, `foms/web/construction/dashboard.py`, `foms/web/production/dashboard.py`, `foms/services/order_event_display.py`, `foms/services/measurement/drawing_transfer_cta.py`; 테스트 `tests/domains/test_erp_quest_display.py`, `tests/domains/test_auth_quest_read.py`, `tests/domains/test_measurement_drawing_transfer_cta.py`, 새 `tests/domains/test_quest_display_names.py`(Spec §6 새 테스트 ①②③), 새 팀 이름 사본 금지 계약 테스트(`tests/contracts/` 안 알맞은 곳) |
| W2 PC 화면 | `templates/orders/partials/dashboard_grid.html`, `static/js/orders/dashboard/erp-dashboard-quest.js`, `static/js/orders/erp-order-shared.js`(팀 이름 사본만), `templates/**/tablet_dashboard_sheet.html`, `templates/drawing/partials/workbench_dashboard_body.html`, `templates/production/partials/filters_grid.html`, `static/css/foundation/erp-pro.css`(필요할 때만), 위 JS 의 `?v=` 핀이 있는 파일(entry/템플릿 — grep 으로 찾아라); 테스트 `tests/domains/test_quest_surfaces_retransition_and_team_buttons.py`, `tests/domains/test_confirm_to_production_display.py`, `tests/domains/test_tablet_dashboard_sheet_contract.py`, `tests/domains/test_tablet_t2_contract.py`, `tests/domains/test_measurement_drawing_transfer_button.py`, `tests/visual/test_p1_mockup_structure.py`, 핀을 박은 테스트 |
| W3 휴대폰 | `templates/orders/partials/order_detail_mobile_v2.html`, `static/js/foms/erp-quest-approve.js`, `templates/partials/shared/erp_mobile_queue_card_v2.html`(필요할 때만), `templates/partials/shared/layout_scripts.html`(**erp-quest-approve.js 핀 한 줄만**); 휴대폰 관련 테스트(grep 으로 찾은 것 중 W1·W2 소유가 아닌 것) |

- 공유 한 줄 규칙: W2·W3 가 둘 다 필요한 파일이 나오면 편집하지 말고 최종 답에 "소유권 밖 필요" 로 적어라. 통합 검증자가 처리한다.
- 자산 핀: JS/CSS 를 고치면 그 자산의 `?v=` 핀을 올리고, `grep -rn "?v=<옛핀>" tests/ templates/ static/` 결과를 전부 같이 고친다. 새 핀 글자: `20260930a`(W2), `20260930b`(W3).
- 템플릿은 서버 payload(`approve_label`, `task_label`, `done_label`)를 쓴다. 템플릿에 이름을 새로 박지 마라(한 곳 정본).

## Spec §5 1단계 요약 (전문은 Spec)

- A(W1) `build_approve_cta` 에 `task_label` 추가, `approve_label` 을 넘기기 문구로, 코드 주석(:92-94) 갱신.
- B(W1) payload·GET 응답 title = `task_label or 저장 title`(빈 문자열 금지).
- C(W2) PC 그리드: 열 "현재 작업", 부제 "주문별 현재 작업", 펼침 머리 "현재 작업", "진행중"→"할 일", 버튼 글자 = approve_label, 소제목 "승인"→"담당", "담당자 지정 필요"→"담당자를 먼저 정해 주세요", "(승인 권한 없음)"→"(담당자만 누를 수 있어요)", 토스트 "X 단계로 넘겼습니다"·남은 팀 한글. 클래스·ID 유지, 새 인라인 스타일 금지.
- D(W1 서버 사본·W2 JS 사본) 팀 이름 한 벌.
- E(W3) 휴대폰 하단 큰 버튼의 " → {next} 전달" 꼬리 제거, 팀 버튼은 approve_label 만(팀은 한글 이름으로 확인창·배지에).
- F(W1 실측 CTA 상수, W2 태블릿 시트) 실측 버튼 "도면 단계로 넘기기", 막힘 문구, 태블릿 "현재 작업 — {title} ({팀})".
- G(W2) 도면 카드 버튼 "도면 창구 열기", 도면 창구 막대 "수정 요청됨"·"확정 대기"(data-status 는 그대로), 생산 보드 "생산 중"→"제작중".

## 워커 공통 규칙

- git 명령 금지(읽기 `git diff`·`git log` 만 허용). CRLF/LF 줄끝 보존(원래 파일 줄끝을 그대로).
- 테스트는 자기 소유 테스트만 `python -m pytest <files> -q -n 4` 로. docs 를 읽는 테스트를 새로 만들지 마라.
- JS 를 고치면 `node --check <file>`.
- 한글 문장에 한자 금지. 사용자 화면 문구는 Spec 글자 그대로.
- 끝나면 최종 답: 편집 파일 목록, 실행한 검증 명령과 결과 원문 끝줄, 소유권 밖 필요 항목.

## 검증 (통합 검증자)

```
cd /c/tmp/foms-s-pc-quest-names
python -c "import app; print('APP_OK')"
python -m pytest -n 8 -q
node --check static/js/orders/dashboard/erp-dashboard-quest.js static/js/foms/erp-quest-approve.js static/js/orders/erp-order-shared.js
python tools/harness/refresh_inventories.py   # 있으면. 없으면 *_scan.py 직접
```
