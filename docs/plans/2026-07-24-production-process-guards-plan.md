# 생산 보드 프로세스 가드 3종 — 실행 플랜 (2026-07-24)

승인된 범위: CEO advisor 분석(태블릿 생산 칸반) P1→P2→P3 순차 구현.
근본 원인: 상태 전이 API에 전제조건 없음 + 보류가 표시 전용 플래그.

## 진행 원장 (Progress Ledger)

- [x] P1: 전이 전제조건 가드 + 시트 버튼 조건 렌더 + confirm (검증 완료: 123 passed + APP_OK)
- [x] P2: 보류 게이트 (409 HOLD_ACTIVE + release_hold 재시도 플로우) (검증 완료: 128 passed)
- [x] P3: 수정 제작(rework) 엔드포인트 + 재제작 배지 (검증 완료: 159 passed)
- [x] 최종 코드리뷰 (2판정: 스펙 준수 전 항목 OK / 품질 Critical·Major 0, Minor 주석·payload 정합 4건 반영)
- [x] 동작검증 루프 (로컬 서버 + Playwright has_touch 태블릿 에뮬레이션, 28/28 PASS — 보류 게이트 거절/수락, INVALID_STAGE 409, rework 배지 생성·해제, 시트 조건 렌더)

리뷰 잔여 기록: 전이 API는 row lock 없음(동시 요청 시 이벤트 중복 가능) — 기존 start/complete 패턴 승계, 필요 시 with_for_update 별도 과제.

## 공통 컨텍스트 (모든 페이즈 필수 숙지)

### 스테이지 SSOT
`Order.erp_stage_code` (flat 컬럼, indexed). 버킷 매핑은 `foms/services/production_read_model.py:76-88`:
- 제작대기 = `('고객컨펌', 'CONFIRM')`
- 제작중 = `('생산', 'PRODUCTION')`
- 제작완료 = `('시공', 'CONSTRUCTION')`

가드는 반드시 이 IN-리스트와 동일하게 (레거시 한글 값 포함).

### 전이 API 위치
`foms/api/production/orders.py`:
- `api_production_start` L99-141 (응답 에러 키 = `message`)
- `api_production_complete` L144-210 (응답 에러 키 = `message`)
- `api_production_hold` L418-483 (응답 에러 키 = `error` — 혼용 주의, 기존 규약 유지)
- 보류 플래그: `sd['production']['hold']` = `{active, reason, at, by_name}`

### 호출처 전수 (3곳 — 이 외 없음, grep 검증됨)
1. `templates/production/partials/scripts.html:229-271` — PC 대시보드 `startProduction`/`completeProduction` (둘 다 confirm 있음)
2. `static/js/foms/tablet-production-kanban.js:48-100` — 태블릿 칸반 카드 버튼 (ACTIONS start/complete, confirm 있음)
3. `static/js/foms/tablet-domain-sheets.js:55-80, 527-540` — 태블릿 시트 `productionComplete` (**confirm 없음 — P1에서 추가**)

### 시트 라우트/템플릿
- 라우트: `foms/web/production/dashboard.py:397-439` `erp_production_tablet_sheet` — sheet dict에 현재 stage 없음 (P1에서 추가)
- 템플릿: `templates/production/partials/tablet_sheet.html:129-140` — 풋터 버튼 무조건 렌더 (P1에서 조건 렌더)
- 칸반 카드: `templates/production/partials/tablet_kanban_body.html:25-29` (열 정의), `L257-269` (move 버튼), `L188-193` (보류 배지)
- 승인 판정: `foms/services/production_dashboard_display.py:142-159` `_production_quest_sales_state(sd, stage_label)` — row 규약: 제작대기가 아니면 `is_sales_approved=True` (L187)

### 프로젝트 규약 (위반 시 재작업)
- JSONB 수정: `copy.deepcopy` + `flag_modified` (기존 코드 패턴 유지)
- 타임스탬프: `now_utc_naive()` (start/complete 계열) — `datetime.now()` 금지
- docstring + 타입힌트 필수 (신규 함수)
- **기존 JS/CSS 파일 수정 시 `?v=` 캐시버스터 범프 필수** (SW staticCacheFirst — 링크 핀 전수 grep 후 동반 범프)
- 인라인 스타일 금지 — CSS는 해당 컴포넌트 CSS 파일에
- bare except 금지, try/except pass 금지
- 검증 명령: `python -c "import app; print('APP_OK')"`

### 기존 테스트 (깨뜨리면 안 됨 / 확장 대상)
- `tests/domains/test_production_hold_api.py` — API 계약 테스트 패턴의 정본 (fixture/클라이언트 사용법 이 파일 따라할 것)
- `tests/domains/test_tablet_t2_contract.py:326-327` — kanban JS에 `/production/start`, `/production/complete` 문자열 존재 assert
- `tests/domains/test_tablet_domain_sheets_contract.py:63` — domain-sheets JS에 `/production/complete` 존재 assert
- `tests/domains/test_production_kanban_full_window.py`
- `tests/domains/test_production_dashboard_mobile.py`

---

## P1 — 전이 전제조건 가드 + 시트 조건 렌더 + confirm

### P1-a 서버 가드 (`foms/api/production/orders.py`)
- `api_production_start`: order 로드 후, `order.erp_stage_code not in ('고객컨펌', 'CONFIRM')` 이면
  `409` + `{"success": False, "code": "INVALID_STAGE", "message": "제작대기 상태에서만 제작을 시작할 수 있습니다."}`
- `api_production_complete`: `order.erp_stage_code not in ('생산', 'PRODUCTION')` 이면
  `409` + `{"success": False, "code": "INVALID_STAGE", "message": "제작중 상태에서만 제작을 완료할 수 있습니다."}`
- 가드는 mutation 이전, 404 체크 직후. 응답 키는 기존 규약(`message`) 유지.
- 판매 승인(is_sales_approved)은 서버 가드 비범위 (기존 UI 레벨 유지 — PC 어드민 플로우 보존).

### P1-b 시트 stage 공급 (`foms/web/production/dashboard.py`)
- sheet dict에 추가:
  - `'stage'`: erp_stage_code → 버킷 라벨('제작대기'|'제작중'|'제작완료'|'기타'). production_read_model 매핑과 동일 로직 — 기존 헬퍼 재사용 가능하면 재사용(`production_dashboard_display`에 stage label 산출 함수 존재), 없으면 소형 로컬 헬퍼.
  - `'is_sales_approved'`: `_production_quest_sales_state(sd, stage)` 재사용, row 규약 동일(제작대기 아니면 True).

### P1-c 시트 풋터 조건 렌더 (`templates/production/partials/tablet_sheet.html`)
- 보류 토글 버튼: 현행 유지 (모든 stage).
- primary 버튼 분기:
  - stage=='제작대기' and is_sales_approved → `제작 시작` (`data-tablet-sheet-action="production-start"`)
  - stage=='제작대기' and not approved → 버튼 대신 무채 라벨 `고객 컨펌 전` (칸반 `is-muted` 칩과 동일 문구)
  - stage=='제작중' → `생산 완료` (`production-complete`, 현행 action명 유지)
  - stage=='제작완료' → primary 없음 (P3에서 `수정 제작` 추가)
  - 기타 → primary 없음

### P1-d 시트 JS (`static/js/foms/tablet-domain-sheets.js`)
- `productionComplete`: fetch 전 `window.confirm("제작을 완료하시겠습니까? (상태가 제작완료로 변경됩니다)")` 추가.
- `productionStart(orderId)` 신설: confirm `"제작을 시작하시겠습니까? (상태가 제작중으로 변경됩니다)"` → POST `/production/start` → 성공 시 시트 닫고 reload (productionComplete와 동일 패턴, 에러 키 `message`).
- 액션 위임 분기에 `production-start` 추가.
- 이 파일을 링크하는 `?v=` 핀 전수 grep 후 범프.

### P1-e 테스트
- 신규 `tests/domains/test_production_transition_guard_api.py` (hold_api 테스트 패턴 준용):
  - CONFIRM 주문 → complete → 409 + code INVALID_STAGE, 상태 불변
  - PRODUCTION 주문 → complete → success, CONSTRUCTION 전이
  - PRODUCTION 주문 → start → 409
  - CONFIRM 주문 → start → success
  - 레거시 한글 stage('생산') → complete → success
- 계약 확장: `test_tablet_domain_sheets_contract.py`에 `production-start` 문자열 + confirm 존재 assert (기존 스타일 준용).
- 템플릿 계약: 시트 stage 분기 렌더 테스트(제작중 주문 시트 → 생산 완료 버튼, 제작대기 미승인 → 고객 컨펌 전) — 기존 시트 렌더 테스트 파일 있으면 거기 확장, 없으면 guard 테스트 파일에 추가.

### P1 완료 기준
`python -m pytest tests/domains/test_production_transition_guard_api.py tests/domains/test_production_hold_api.py tests/domains/test_tablet_domain_sheets_contract.py tests/domains/test_tablet_t2_contract.py -x -q` 전부 통과 + `import app` OK.

---

## P2 — 보류 게이트

### P2-a 서버 (`foms/api/production/orders.py`)
- start·complete 공통, INVALID_STAGE 가드 통과 직후:
  - `sd['production']['hold']['active']` truthy 이고 body `release_hold != True` →
    `409` + `{"success": False, "code": "HOLD_ACTIVE", "message": "보류 중인 주문입니다." (+사유 있으면 " (사유: X)"), "hold": {...현재 hold 객체}}`
  - `release_hold == True` → 같은 트랜잭션에서 hold 해제(`{active: False, reason: "", at: None, by_name: None}` — hold API 해제 형과 동일) + `OrderEvent PRODUCTION_HOLD_TOGGLED` payload `{active: False, via: "release_on_start"|"release_on_complete", ...}` 기록 후 전이 진행.
- 중복 로직은 모듈 내 소형 헬퍼로 (두 엔드포인트 공유).

### P2-b 프론트 3곳 공통 패턴 (HOLD_ACTIVE 재시도)
- 409 응답 `data.code === "HOLD_ACTIVE"` 이면:
  `confirm("보류 중인 주문입니다" + (사유) + "\n보류를 해제하고 진행할까요?")` → OK 시 동일 엔드포인트 재POST body `{release_hold: true}`.
- 적용: `tablet-production-kanban.js` `moveOrder`, `tablet-domain-sheets.js` `productionStart`/`productionComplete`, `scripts.html` `startProduction`/`completeProduction`.
- JS 파일 `?v=` 범프 (P1에서 이미 범프했으면 그 값 재사용 아님 — 이번 변경분으로 다시 범프).

### P2-c 테스트 (`test_production_transition_guard_api.py` 확장)
- hold active + start → 409 HOLD_ACTIVE, 상태·hold 불변
- hold active + start + release_hold → success, hold 해제됨, PRODUCTION 전이, HOLD_TOGGLED 이벤트 기록
- hold active + complete(PRODUCTION 주문) → 409 / release_hold → success
- hold 없는 주문 + release_hold:true → 정상 전이(무해)

### P2 완료 기준
P1 명령 동일 세트 통과 + `import app` OK.

---

## P3 — 수정 제작 (rework)

### P3-a 서버 신규 엔드포인트 (`foms/api/production/orders.py`)
- `POST /<int:order_id>/production/rework` (`@erp_edit_required` — start/complete와 동일 게이트)
- 가드: `erp_stage_code in ('시공', 'CONSTRUCTION')` 아니면 409 INVALID_STAGE `"제작완료 상태에서만 수정 제작을 시작할 수 있습니다."`; hold 게이트 P2와 동일(HOLD_ACTIVE/release_hold).
- body `{reason: str(선택), release_hold: bool(선택)}` — reason은 trim, 빈 값 허용.
- mutation (start와 동일 패턴: deepcopy, flag_modified, sync_erp_flat_columns, SecurityLog):
  - `wf.stage = "PRODUCTION"`, `order.status = "PRODUCTION"`, history note `"수정 제작 시작"` (+reason)
  - `sd['production']['rework'] = {active: True, reason, count: (기존 count or 0)+1, at: now_utc_naive().isoformat(), by_name}`
  - `OrderEvent PRODUCTION_REWORK_STARTED` payload `{reason, count, domain: "PRODUCTION_DOMAIN", action: "PRODUCTION_REWORK_STARTED", ...}`
- 응답: `{"success": True, "message": "수정 제작을 시작했습니다.", "new_status": "PRODUCTION"}` (에러 키 message 규약).
- `api_production_complete` 보강: rework.active 이면 완료 시 `active: False`로 갱신(count·마지막 기록 보존), history note `"제작 완료 (재제작)"`, 이벤트 payload에 `rework: true`.

### P3-b 태블릿 UI
- `tablet_kanban_body.html` L28 제작완료 열: `'move': 'rework', 'move_label': '수정 제작', 'move_icon': 'fa-rotate-left'` + move 버튼 분기에 rework 케이스 추가 (L257-269 블록).
- `tablet-production-kanban.js` ACTIONS에 `rework: {path: "/production/rework", confirm: "수정 제작으로 되돌리시겠습니까? (상태가 제작중으로 변경됩니다)"}` + confirm 후 `window.prompt("수정 제작 사유를 입력하세요. (선택)")` → body `{reason}` 전송(fetch body 지원하도록 moveOrder 소폭 확장). HOLD_ACTIVE 재시도 패턴 동일 적용.
- 카드 재제작 배지: `_prod.get('rework')` active 시 보류 배지(L188-193)와 동일 문법으로 `재제작` 칩(`foms-kanban-card__rework`, `fa-rotate-left`). HMI 색 예외(주의 상태) — 보류·지연과 구분되는 톤, 색은 해당 칸반 CSS 파일의 기존 팔레트 변수 준용.
- 시트: stage=='제작완료' → primary `수정 제작`(`data-tablet-sheet-action="production-rework"`, domain-sheets.js에 핸들러 — confirm+prompt+HOLD_ACTIVE 패턴 동일). 시트 상단 rework active 시 `재제작` 배지 + 사유 1줄(보류 배지/사유와 동일 문법). dashboard.py sheet dict에 `rework_active`/`rework_reason` 추가.
- CSS: 칸반/시트 배지 스타일 — 기존 `__hold` 스타일이 있는 CSS 파일에 추가. CSS·JS `?v=` 범프.

### P3-c 테스트 (`test_production_transition_guard_api.py` 확장 + 계약)
- CONSTRUCTION 주문 → rework → success, PRODUCTION 전이, rework {active:True, count:1}, 이벤트 기록
- rework → complete → CONSTRUCTION + rework.active False + count 보존
- 2회차 rework → count 2
- CONFIRM 주문 → rework → 409
- hold active → rework → 409 HOLD_ACTIVE / release_hold → success
- 계약: kanban JS `/production/rework` 문자열, 카드 `foms-kanban-card__rework` 렌더

### P3 완료 기준
P1 명령 세트 + 위 신규 테스트 통과 + `import app` OK.

---

## 최종 검증 (오케스트레이터 직접)

1. 페이즈별 git diff 직접 확인 + 테스트 직접 실행 (서브에이전트 보고 무신뢰)
2. 2판정 리뷰: (a) 스펙 준수 (b) 코드 품질 — 분리 판정
3. 동작검증 루프: 로컬 Flask + 태블릿 에뮬레이션(992+ landscape, pointer coarse)으로 실선 시나리오: 보류 설정 → 제작 시작(해제 confirm) → 완료 가드(제작대기에서 완료 시도 409) → rework → 재제작 배지 확인
4. `scripts/ops/pre_push_smoke.ps1` (push 시)
