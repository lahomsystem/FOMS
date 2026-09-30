# PC 퀘스트 이름 2단계 — 생산·시공·완료·AS 줄 모양 구현 브리프 (2026-09-30)

> 초안이다. CEO 가 코드와 대조해 고친다(소유권은 겹치지 않게).

- 정본 Spec: `docs/specs/2026-09-30-pc-quest-mobile-names_SPEC.md` §5 **2단계**. 1단계는 운영 PR #468(deploy `d488d3135`)로 끝났다.
- 목업 v2(사용자가 고른 기준): https://claude.ai/artifact/Pxd7cWsqa42ZjfQi5z3VBH — 생산·관리자 탭.
- 작업 트리 `c:\tmp\foms-s-pc-quest-names`(브랜치 `session/pc-quest-names`, HEAD `70c09d72d` = origin/deploy). Bash 는 매번 `cd /c/tmp/foms-s-pc-quest-names && ...`. `C:\DEV\FOMS` 편집 금지.

## 목표 (주문 대시보드 "현재 작업" 칸)

| 단계 | 지금 | 바뀐 뒤 |
|---|---|---|
| 생산 | 노랑 "할 일" + 합성 퀘스트 "생산" + "생산팀 (보드에서 진행)", 또는 `dashboard_grid.html:333-335` "생산 중" | 배지 "제작대기" 또는 "제작중" + 링크 "생산 보드 열기" |
| 시공 | "-" (`resolve_current_quest` 가 None, `erp_quest_display.py:67`) | 배지 "시공대기" 또는 "시공중" + 링크 "시공 보드 열기" |
| 완료 | 노랑 "할 일" + 합성 "완료" + "CS팀 (보드에서 진행)" | 초록 "완료" 배지 하나 |
| AS처리 | "할 일" + "AS 작업"(또는 AS 확인) + "(보드에서 진행)" | 노랑 "할 일" + 제목 "AS 확인" + 링크 "AS 화면 열기". "(보드에서 진행)" 없음 |

- 판정은 각 보드가 이미 쓰는 규칙을 재사용한다: 생산 `foms/services/production_dashboard_display.py:147-162,286-294`(제작대기/제작중 = 생산 run), 시공 `foms/services/construction_dashboard_display.py:391-401`. 규칙을 새로 만들지 않는다.
- 같은 PR 에서 **시공·생산 보드 그리드**의 옛 퀘스트 글자도 1단계 이름으로: `templates/construction/partials/filters_grid.html:12,117`, `templates/production/partials/filters_grid.html:12,25,84`("주문 처리 및 퀘스트 관리"·"퀘스트"·"현재 단계 퀘스트"·"진행중"·"팀별 승인"·"승인완료"·"승인").
- 휴대폰 상세 "현재 작업" 칸·큐 카드도 같은 값(배지·링크)을 쓰게 할지 CEO 가 정한다 — 원칙: PC 와 휴대폰이 같은 말을 쓴다(사용자 결정 2). 합성 quest 를 없애 휴대폰 칸이 통째로 사라지면 안 된다.

## 성능 (필수)

- 주문 대시보드는 perf-gate 대상이다. 생산 run·시공 상태를 **줄마다 조회하면 안 된다**(N+1). 보이는 페이지의 주문 id 로 한 번에 모아 읽는다.
- JSONB 를 새로 읽으면 TOAST 비용이 크다(메모리: 구간 이름 거짓말·TOAST 53배). 이미 읽은 `structured_data` 를 재사용하거나 필요한 열만.
- 통합 검증자는 바꾸기 전/후 `/erp/dashboard` 서버 구간 시간을 로컬에서 재어 숫자로 보고한다(추정 금지). `scripts/ops/pre_push_smoke.ps1` 성능 가드 exit 0.

## 파일 소유권 초안 (CEO 확정)

| 워커 | 편집 허용 |
|---|---|
| W1 서버 | `foms/services/erp_quest_display.py`, `foms/services/orders/dashboard_dto.py`, 새 모듈 1개(예 `foms/services/orders/board_state_display.py`), `foms/services/erp_mobile_order_display.py`(휴대폰 payload 가 필요하면), 서버 테스트 |
| W2 PC 화면 | `templates/orders/partials/dashboard_grid.html`, `templates/construction/partials/filters_grid.html`, `templates/production/partials/filters_grid.html`, `static/css/foundation/erp-pro.css`(새 배지·링크 클래스, 인라인 스타일 금지), PC 테스트 |
| W3 휴대폰 | `templates/orders/partials/order_detail_mobile_v2.html`, `templates/partials/shared/erp_mobile_queue_card_v2.html`, 휴대폰 테스트 |

- 공유 계약(payload 키 이름)은 CEO 가 정해 세 워커에 같은 글자로 준다. 예: `o.board_state = {"kind": "production"|"construction"|"completed"|"as", "label": "제작중", "tone": "info", "link_url": ..., "link_label": "생산 보드 열기"}`.
- 자산 핀: CSS/JS 를 고치면 `?v=` 핀 올리고 핀 박은 테스트 같이. 새 핀 글자 `20260930c`(W2), `20260930d`(W3).

## 워커 공통 규칙

- git 쓰기 금지, 줄끝 보존, 한자 금지, 새 설명 주석 최소(사용자 "심플·미니멀"), 틀린 옛 주석만 고친다.
- 자기 테스트 `-n 4`, JS 는 파일마다 `node --check`.
- 새 import 는 모듈 맨 위(층 래칫).
- 최종 답: 편집 파일, 검증 명령과 결과 끝줄 원문, 소유권 밖 필요 항목.

## 통합 검증

```
cd /c/tmp/foms-s-pc-quest-names
python -c "import app; print('APP_OK')"
python -m pytest -q --ignore=tests/visual -p no:playwright -n 8
python tools/harness/refresh_inventories.py   # quest/dto 줄이 밀리면
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/ops/pre_push_smoke.ps1   # exit 0 을 직접 읽는다
```
