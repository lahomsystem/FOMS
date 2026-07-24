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

## 2차 라운드 (2026-07-24 사용자 피드백 P4~P8) — 진행 원장

- [x] Phase A = P4(보류 해제 confirm) + P5(사유 가시성) (165 passed)
- [x] Phase B = P6(제작 취소·완료 취소 rollback 2종) (174 passed)
- [x] Phase C = P7(보류 운영 가시성 KPI·D+n·임박 경고) + P8(PC 리스트 배지) (187 passed)
- [x] 최종 코드리뷰 2판정 (스펙 전 항목 OK / Critical·Major 0, Minor 5 중 음수 D+n 가드 즉시 반영) + 동작검증 루프 (Playwright 태블릿+PC 21/21 PASS — 해제 confirm 거절/수락, KPI 보류 필터, 취소·완료취소, rework 복원, PC 배지)

2차 리뷰 잔여 기록: (1) 라운드 배포 전 rework 완료 건은 completed_at 부재로 완료취소 시 재제작 배지 미복원(스테이징 하루치, 무시 가능) (2) 보류 당일 hold_days=0은 D+ 미표기(의도) (3) --foms-status-warning-text 토큰 미정의 fallback 이원화(기존 승계) (4) 다회 rework 사이클 회귀 테스트 없음(코드 불변식으로 안전 확인).

### 2차 공통 컨텍스트 (1차 공통 컨텍스트 + 아래)

- 1차 구현 완료 커밋: 357d8803 (전이 가드·보류 게이트·rework). 현재 워킹트리에 타 세션 미커밋 변경 존재(.claude/*, .mcp.json, docs/AI_STATUS.md, scripts/ops/clone_prod_to_deploy.ps1 등) — 절대 손대지 않는다.
- 캐시버스터 현재값: JS(tablet-domain-sheets.js·tablet-production-kanban.js)=20260724c, CSS(foms-tablet-production-kanban.css)=20260724a(번들 체인 foms-tablet-bundle.css→layout_head.html=20260724a). 수정 시 다음 값(d/b…)으로 범프 + 계약 테스트 리터럴 동기(test_tablet_domain_sheets_contract.py:33, test_tablet_t2_contract.py:644, test_tablet_rail_contract.py:162).
- KPI 타일: `foms/web/production/dashboard.py:281-` `_compute_tablet_prod_kpis`(enriched rows 파생, 신규 쿼리 금지), 마크업 tablet_kanban_body.html KPI 섹션(erp-pro-alerts, data-tablet-prod-kpi=line/load/delayed 상호배타 토글), 필터 predicate는 tablet-domain-sheets.js `applyProdFilter` L416-486 (카드 레벨 kpiOK 분기).
- PC 리스트: templates/production/partials/filters_grid.html — 단계 badge(td L59), 퀘스트 셀(L60-77), 고객 셀 부배지 문법(자가실측, L86-88 bootstrap badge). 행 `o`는 enriched dict, `o.structured_data` 직접 접근 가능(제품 셀 L95 패턴).
- hold 객체: `sd['production']['hold']` {active, reason, at(UTC iso, aware), by_name}. rework: {active, reason, count, at, by_name}.
- 오늘 날짜: `get_today_kst()`는 **date 반환** (.date() 호출 금지 — 메모리 함정).

### Phase A — P4 보류 해제 confirm + P5 사유 가시성

**A-1 (P4)** `static/js/foms/tablet-domain-sheets.js` `productionHold`:
- 해제 경로(isActive→비활성)에 `window.confirm("보류를 해제할까요?" + (사유 있으면 " (사유: X)"))` 추가. 사유는 버튼 인접 DOM이 아니라 **서버 렌더 데이터로**: tablet_sheet.html 보류 버튼에 `data-hold-reason="{{ order.hold_reason }}"` 속성 추가해 읽는다. 설정 경로(prompt)는 현행 유지.
- 계약 테스트: test_tablet_domain_sheets_contract.py에 "보류를 해제할까요" assert.

**A-2 (P5) 카드 사유 스트립** `templates/production/partials/tablet_kanban_body.html`:
- 기존 변경 알림 스트립(.foms-kanban-card__alert, L169-182) 문법 재사용. 카드 상단에 hold active 시 앰버 행(fa-pause, 라벨 "보류", detail=사유(없으면 '사유 미입력')), rework active 시 블루 행(fa-rotate-left, 라벨 "재제작 N회"(count), detail=사유). 신규 kind 클래스 `--hold`, `--rework`는 CSS에 좌보더+틴트 정의(변경 스트립과 동일 문법, HMI 색 예외 — 보류=앰버(--foms-status-warning-*), 재제작=블루(--foms-color-info-*)).
- 우상단 소형 배지(__hold/__rework)는 유지하되 rework 배지 텍스트를 "재제작{% if count>1 %} {{count}}회{% endif %}"로.

**A-3 (P5) 시트 사유 콜아웃** `templates/production/partials/tablet_sheet.html` + CSS:
- __hold-reason/__rework-reason 줄을 콜아웃로 승격: 배경 틴트+좌보더+font-size-base, 사유 부분 bold. 클래스 유지(계약 테스트 존재 가능 — grep 후 판단), 스타일만 강화. rework 콜아웃에 회차 병기.
- dashboard.py sheet dict에 `rework_count`(int) 추가, 시트 배지 "재제작 N회".
- CSS는 foms-tablet-production-kanban.css(시트 스타일 L1175 부근 __rework-badge 기존 블록 인접).

**A-4** 캐시버스터: JS d, CSS b(번들 체인 포함) + 계약 리터럴 3곳.
**A-5** 테스트: 시트 렌더(rework_count 병기), 카드 스트립 렌더(hold 사유 텍스트 노출), JS confirm 계약. 기존 가드 테스트 세트 전부 통과 유지.

### Phase B — P6 되돌리기 2종 (시트 전용, 의도적 마찰)

**B-1 서버** `foms/api/production/orders.py` (start 패턴 복제, deepcopy+flag_modified+sync_erp_flat_columns+SecurityLog, 에러 키 message):
- `POST /<id>/production/cancel`: 가드 stage in ('생산','PRODUCTION') 아니면 409 INVALID_STAGE "제작중 상태에서만 제작을 취소할 수 있습니다.". **hold 게이트 미적용**(후진 전이는 보류와 무관 — 보류 유지된 채 제작대기 복귀 허용, docstring에 명시). body {reason 선택, trim}. wf.stage="CONFIRM", status="CONFIRM", note "제작 취소 (제작대기 복귀)"(+" — reason"), OrderEvent `PRODUCTION_CANCELLED` {reason, domain, action}. 응답 {"success":True,"message":"제작을 취소했습니다. (제작대기 복귀)","new_status":"CONFIRM"}.
- `POST /<id>/production/uncomplete`: 가드 stage in ('시공','CONSTRUCTION') 아니면 409 "제작완료 상태에서만 완료 취소할 수 있습니다.". hold 게이트 미적용. wf.stage="PRODUCTION", status="PRODUCTION", note "완료 취소 (제작중 복귀)", OrderEvent `PRODUCTION_COMPLETE_REVERTED`. **rework 복원**: api_production_complete가 rework 해제 시 `rework["completed_at"]=now iso` 기록하도록 보강 → uncomplete는 rework dict에 completed_at 있고 active False면 active=True 복원+completed_at 삭제(회차 불변). 재제작 아니었으면 rework 무터치.
- 응답 후진 전이는 판매 승인 무관(제작대기 복귀 후 다시 시작하려면 기존 가드가 승인 UI 분기 적용).

**B-2 시트 UI** tablet_sheet.html + tablet-domain-sheets.js:
- 제작중 시트 풋터: [보류 토글] [제작 취소(ghost)] [생산 완료(pri)] / 제작완료 시트: [보류 토글] [완료 취소(ghost)] [수정 제작(pri)].
- ghost 버튼 클래스 `foms-prod-sheet__btn--ghost`(무채 아웃라인, CSS 신규 — 카드에는 미노출, 시트 전용 의도적 마찰).
- 핸들러: production-cancel = confirm "제작을 취소하고 제작대기로 되돌릴까요?" + prompt 사유(선택, 취소 null=중단) → POST {reason}; production-uncomplete = confirm "완료를 취소하고 제작중으로 되돌릴까요?" → POST {}. submitTransition 재사용(HOLD_ACTIVE 분기는 서버가 안 내므로 무해).
- 칸반 카드에는 추가하지 않는다(진행=카드, 되돌림=시트).

**B-3** 캐시버스터 JS e + 리터럴. 테스트: API 6케이스(cancel 성공/409, uncomplete 성공/409, rework 복원, rework 아닌 완료취소 무터치) + 시트 렌더 2 + JS 계약.

### Phase C — P7 보류 운영 가시성 + P8 PC 배지

**C-1 (P7) hold_days 파생** `foms/services/production_dashboard_display.py` `_enrich_one_production_order`:
- row에 `hold_active`(bool), `hold_days`(int|None — hold.at 파싱(UTC aware)→KST date 변환→get_today_kst()와 일수차, 파싱 실패·at 없음=None) 추가. 기존 행 규약 무파괴(추가만).
**C-2 (P7) 카드**: 보류 배지 텍스트 "보류 D+{{n}}"(hold_days 있을 때). **보류+임박 충돌 경고**: hold active AND (dday<=2 or 지연) → 카드 클래스 `is-held-imminent`, CSS 강경고(적색 좌보더 3px + 배지 danger 톤 전환 — 애니메이션 금지, HMI).
**C-3 (P7) KPI 타일**: `_compute_tablet_prod_kpis`에 `hold`(보류 카드 수) 추가. tablet_kanban_body KPI 행에 5번째 타일 "보류 {{n}}"(data-tablet-prod-kpi="hold", 기존 상호배타 토글 문법). applyProdFilter kpiOK에 `kpi==="hold" → card.classList.contains("is-held")` 분기.
**C-4 (P8) PC 배지** filters_grid.html:
- 단계 배지 셀(L59) 옆에: hold active 시 `<span class="badge bg-warning text-dark">보류{% if hold_days %} D+n{% endif %}</span>`(title=사유), rework active 시 `<span class="badge bg-info">재제작 N회</span>`. o.structured_data 직접 접근(제품 셀 패턴) + row hold_days 소비. PC 모바일 큐(mobile_queue.html)는 비범위.
**C-5** 캐시버스터(JS f, CSS c — 실변경 파일만) + 테스트: enrichment 단위(hold_days 파싱·None), KPI hold 카운트, 카드 D+n·is-held-imminent 렌더, PC grid 배지 렌더, 필터 계약(data-tablet-prod-kpi="hold" 존재).

## 3차 라운드 (2026-07-24 사용자 피드백: 시트 버튼 CSS·완료 이력·고정 바 공간) — 진행 원장

- [x] 1번 제작 취소 버튼 줄바꿈 CSS 수정 (nowrap + padding 축소, 실측 확인, CSS 20260724e)
- [x] Phase D = 고정 바 재배치 (a)+(b)+(c): KPI 5열 1줄 + pcbar·KPI 통합 + 필터 접기(localStorage 기억) + 열 캡 실측 확정 265(크롬 233→177px, page_scroll 없음, col_body +58px)
- [x] Phase E = 완료 이력: hold_history 보존(직접 해제+게이트 release 양경로) + 완료 카드/시트/PC 무채 이력 배지(재제작 N회·보류 이력)
- [x] 통합 리뷰(2판정: 스펙 대부분 OK / Major 1 B-1 hold 배지 active 가드 누락 + Minor 3 반영) + 동작검증 루프(재배치 실측 265·이력 API 흐름 13/13 PASS·B-1 재검증) + 커밋/푸시

3차 리뷰 반영: B-1(카드/시트 hold 이력 배지에 not active 가드 — 진행 유채와 무채 이력 상호배타), B-2(필터 토글 willOpen을 DOM __more.hidden 파생 — 스토리지 불가 환경 못닫힘 버그), B-3(테스트 docstring 265 방향 정정), B-4(api_production_hold docstring hold_history 보존 반영). 잔여 관찰: 재보류(active 연속) 시 원 사유 이력 없이 덮어씀(해제 경로만 스펙 범위), hold_history 20캡 미검증(스펙 밖).

### 3차 공통 컨텍스트

- 캐시버스터 현재값: JS(tablet-domain-sheets.js·tablet-production-kanban.js)=20260724e, CSS 체인=20260724e(foms-tablet-bundle.css @import→layout_head.html 링크→계약 리터럴 test_tablet_t2_contract.py:657·test_tablet_rail_contract.py:162). 1번 CSS 수정으로 이미 e까지 범프됨. 추가 변경 시 f로.
- **크롬 실측 근거(viewport 1280×800)**: pcbar 57px + KPI 112px(2줄) + 필터 64px = 크롬 233px(뷰포트 29%). KPI가 4열 grid([css:156] `repeat(4)`)라 5번째 보류 타일이 2줄로 줄바꿈.
- **열 body 캡 함정**: `.foms-kanban-col__body { max-height: calc(100dvh - 240px) }`([css:328]). 크롬을 줄이면 이 240 상수도 동반 하향해야 회수분이 실제 스크롤 영역으로 반영됨(안 하면 바닥 여백으로 죽음). 최종값은 오케스트레이터가 실측으로 미세조정.
- 열 헤더 sticky([css:295] `position:sticky;top:0`)는 이미 구현됨(스크롤 시 열 제목 유지).
- 필터 접기 상태 기억: `static/js/foms/tablet-density-toggle.js`의 localStorage+document위임+싱글턴가드(perf G4)+fragment-swap 복원 패턴 복제(신규 라이브러리 금지).

### Phase D — 고정 바 재배치 (a)+(b)+(c)

수정 대상: templates/production/partials/tablet_kanban_body.html(마크업 재그룹), static/css/foundation/foms-tablet-production-kanban.css(레이아웃), static/js/foms/tablet-domain-sheets.js 또는 신규 소형 js(필터 접기 배선), 캐시버스터.

**D-a (KPI 1줄)**: [css:156] `grid-template-columns: repeat(4, minmax(0,1fr))` → `repeat(5, minmax(0,1fr))`. 5타일 1줄. 992px 좁폭에서 타일 라벨/값 넘침 없는지(폰트·gap) 확인.

**D-b (pcbar+KPI 통합)**: pcbar 층(타이틀·서브·라벨인쇄 버튼)을 KPI 스트립과 한 줄로. 설계 방향: 상위 flex 컨테이너 = [타이틀블록(생산 보드·전체N)][KPI grid 5타일 flex:1][라벨 인쇄 버튼]. `flex-wrap` 폴백(극단 좁폭에서 안전 degrade — 현재 상태로 wrap). KPI 필터 기능(data-tablet-prod-kpi 5개) 전부 유지. 라벨 인쇄 버튼은 좁을 때 아이콘-only 허용. 마크업 재그룹은 코호트 게이트(body.erp-mobile-v2-layout + coarse landscape MQ) 스코프 유지, PC/폰 누출 금지.

**D-c (필터 접기)**: 검색 input 상시 노출. 상태 select·공장 select·변경 토글·초기화를 [필터 ▾] 토글 버튼 뒤로 접기(기본 접힘). 토글 클릭 시 펼침, 상태는 localStorage(`foms_tablet_prod_filters_open`)에 기억(density-toggle 패턴 복제). 접힘 시 활성 필터가 있으면 토글 버튼에 표식(예: 필터 N). fragment-swap 복원 리스너 포함. 배선은 tablet-domain-sheets.js에 추가(기존 applyProdFilter와 동일 파일 — 싱글턴 가드 확인) 또는 신규 파일.

**D-d (열 캡 동반 하향)**: [css:328] `calc(100dvh - 240px)`의 240을 크롬 축소분 반영해 잠정 하향(예상 크롬 ~90~120px → 240→약 120~150). **최종값은 오케스트레이터 실측 조정** — 브리프에선 잠정값 설정 + 주석에 "오케스트레이터 실측 확정" 명시.

**D-e 캐시버스터**: JS 변경 시 20260724e→f(핀 2곳+계약 리터럴), CSS 20260724e→f(번들 체인+리터럴 2곳).

**D-f 테스트**: 계약 — KPI 5열 grid CSS 문자열, 필터 토글 마크업(data-* + 검색 상시), 접기 JS 문자열(localStorage 키), 캐시버스터 리터럴. 기존 test_tablet_t2_contract/test_tablet_rail_contract/test_production_kanban_full_window 무파괴. 시각 실측(크롬 높이·카드 노출)은 오케스트레이터 동작검증.

**D 완료 기준**: 아래 3차 pytest 세트 통과 + import app APP_OK.

### Phase E — 완료 이력 (소실 방지 + 무채 배지)

수정 대상: foms/api/production/orders.py(hold 이력 보존), foms/services/production_dashboard_display.py(완료 이력 파생), foms/web/production/dashboard.py(sheet dict), templates/production/partials/tablet_kanban_body.html·tablet_sheet.html·filters_grid.html(무채 배지), static/css/foundation/foms-tablet-production-kanban.css, 캐시버스터.

**E-a (보류 이력 소실 방지)** `foms/api/production/orders.py`:
- hold 해제 경로 2곳 공통: (1) hold API 직접 해제(`api_production_hold` active=False) (2) 전이 게이트 `_apply_production_hold_gate` release. 해제로 hold를 초기화하기 전, 직전 active hold를 `sd['production']['hold_history']` 리스트에 append: `{reason, at(보류 시작), released_at(now iso), released_by(user.name)}`. hold_history는 최근 N(예: 20)건 캡.
- rework는 이미 count·completed_at 보존되므로 별도 이력 불필요(배지는 count 사용).

**E-b (완료 이력 파생)** `foms/services/production_dashboard_display.py` `_enrich_one_production_order`:
- row에 `rework_count`(int, production.rework.count or 0), `hold_history_count`(int, len(production.hold_history)) 추가. 기존 hold_active/hold_days 규약 유지.

**E-c (완료 카드 무채 배지)** tablet_kanban_body.html:
- 진행 배지(is-held/rework active 유채)는 현행 유지. 추가: **active가 아니면서** rework_count>0 → 무채 회색 배지 "재제작 N회"(이력), hold_history_count>0 → 무채 "보류 이력". 클래스 `foms-kanban-card__hist`(무채 tertiary 톤, HMI 규율 — 이력은 유채 아님). title에 상세.
- 즉 제작완료 열 카드에 진행 경보 대신 차분한 이력 배지.

**E-d (완료 시트 이력)** tablet_sheet.html + dashboard.py:
- sheet dict에 `rework_count`(이미 있음), `hold_history`(list) 추가. 시트에 active 아닌데 이력 있으면 무채 이력 섹션: "재제작 N회 · 최근 사유 X", "보류 이력 N건". 진행 콜아웃(유채)과 구분.

**E-e (PC 리스트 이력)** filters_grid.html:
- 단계 셀에 완료 건(active 아님) + rework_count>0 → 무채 badge "재제작 N회". (보류 이력은 선택 — PC 공간 고려, rework만 필수.)

**E-f CSS**: `foms-kanban-card__hist`·시트 이력 섹션 무채 스타일(--foms-text-tertiary/surface-muted). 캐시버스터 동반.

**E-g 테스트**: hold 해제 시 hold_history append(API 단위 — 직접 해제·release 양경로), 완료 카드 무채 배지 렌더(active=False+count>0), 파생 단위(hold_history_count), 시트 이력 렌더. 기존 세트 무파괴.

**E 완료 기준**: 3차 pytest 세트 통과 + APP_OK.

### 3차 pytest 세트
`python -m pytest tests/domains/test_production_transition_guard_api.py tests/domains/test_production_hold_api.py tests/domains/test_tablet_domain_sheets_contract.py tests/domains/test_tablet_t2_contract.py tests/domains/test_tablet_rail_contract.py tests/domains/test_production_kanban_full_window.py tests/domains/test_production_dashboard_mobile.py tests/domains/test_production_dashboard_query_count.py -q` 전부 통과 + import app APP_OK.

## 4차 라운드 (2026-07-24 사용자 피드백: 제작취소 잔존·통합바 2줄·전체화면) — 진행 원장

- [x] F-1 = 제작 취소 깨끗한 되돌림: cancel 시 rework/hold active 정리(이력 보존) + 제작 이력(workflow.history PRODUCTION) 있으면 재승인 없이 제작 시작 가능. 동작검증 8/8(제작 시작 버튼 유지·배지 정리·hold_history 보존)
- [x] F-2 = 라벨 인쇄 버튼 제거 → 통합 바 [lead][KPI] 1줄, 크롬 kanban_top 177→117px
- [x] F-3 = 전체화면 토글: 크롬 접어 칸반 최대(실측 캡 90), 플로팅 복원 버튼(exit hidden JS 제어), localStorage 기억. 실측 중 버그 2개 잡음(exit 안보임→못빠져나옴, 캡 60 과소 페이지스크롤)
- [x] 통합 리뷰(스펙 3건 OK / Critical·Major 0, Minor 1 CSS 주석 240→265 정정) + 동작검증 루프(전체화면 실측·F-1 8/8) + 커밋/푸시

### 4차 공통 컨텍스트

- 커밋 61b14e30(3차)까지 배포됨. 캐시버스터 현재값: JS(tablet-domain-sheets.js)=20260724h, CSS 체인=20260724f(bundle @import→layout_head.html→계약 리터럴 t2:675·rail:162). 변경 시 다음 값으로.
- **제작 취소 승인 판정 근본 원인**: `foms/services/production_dashboard_display.py` `_production_quest_sales_state`(L157-180)는 제작대기 stage에서만 quest 승인 판정, `_enrich_one_production_order` L220은 `is_sales_approved if stage_label=='제작대기' else True`. cancel(제작중→CONFIRM 복귀)은 quest 미변경이라 미승인 건은 "고객 컨펌 전" 재표시 + 재시작 버튼 소실. uncomplete(완료→제작중)는 제작중이라 무관.
- cancel 엔드포인트: orders.py:511-603. `_append_hold_history`(orders.py:102) 재사용 가능.
- 통합 상단 바: tablet_kanban_body.html L41-95(pcbar=[lead][KPI][actions]), 라벨 버튼 L88-94. CSS pcbar L94-146.
- 전체화면 토글 상태 기억: tablet-density-toggle.js 패턴(localStorage+document위임+싱글턴+fragment-swap 복원). 필터 접기(foms_tablet_prod_filters_open)가 이미 tablet-domain-sheets.js에 있으니 동일 파일에 추가.

### Phase F-1 — 제작 취소 깨끗한 되돌림 (서버)

**F-1a** `foms/services/production_dashboard_display.py` `_production_quest_sales_state`:
- 제작대기 판정 진입부에, **workflow.history에 PRODUCTION('생산'/'PRODUCTION') stage 기록이 있으면 `return True, None`**(제작 이력 = 이미 컨펌·제작된 건 → 취소 후 복귀라도 재시작 허용). 소급 자동 커버(마커 불필요). 그 다음 기존 quest 판정.

**F-1b** `foms/api/production/orders.py` `api_production_cancel`:
- CONFIRM 복귀 mutation에 진행 플래그 정리 추가(sd deepcopy 흐름 안): `production.rework.active=False`(count·reason·at 보존), `production.hold.active` truthy면 `_append_hold_history(production, user.name)` 후 hold 초기화({active:False,reason:"",at:None,by_name:None}). production dict 없으면 스킵. **uncomplete는 무변경**(제작중 복귀라 rework active 복원이 옳음).
- OrderEvent payload에 정리 사실 반영(선택).

**F-1c 테스트**: cancel 후 (1) is_sales_approved 판정 — history에 PRODUCTION 있으면 제작대기여도 True(제작 시작 버튼), (2) rework active False·count 보존, (3) hold active였으면 hold_history append+해제, (4) 신규 미승인 건(history 무 PRODUCTION)은 여전히 False.

### Phase F-2 — 라벨 인쇄 제거 + F-3 전체화면 토글 (프론트)

**F-2** tablet_kanban_body.html:
- pcbar `__actions` div(라벨 인쇄 버튼) 제거. CSS `foms-prod-pcbar__actions`·`__label` 관련 규칙 정리(사용처 없으면 제거). 통합 바가 [lead][KPI] 2요소 → 1줄 안정.

**F-3** 전체화면 토글:
- 마크업(tablet_kanban_body.html): 통합 바(또는 필터 바)에 전체화면 토글 버튼 `data-tablet-prod-fullscreen`(fa-expand, "전체화면"). 전체화면 시 표시할 플로팅 복원 버튼 `data-tablet-prod-fullscreen-exit`(fa-compress, board 우상단, 기본 hidden).
- CSS: `.tablet-prod-board.is-fullscreen`에서 `.foms-prod-pcbar`·`.tablet-prod-filter` display:none, `.foms-kanban` max-height 확대(크롬 없으니 `calc(100dvh - 약 40px)`), 플로팅 복원 버튼 표시(position 고정, 터치타깃 48px, 무채). 열 body 캡도 전체화면 시 `calc(100dvh - 약 60px)`로(복원 버튼 여백). 코호트 게이트 스코프.
- JS(tablet-domain-sheets.js): 토글/복원 배선(localStorage `foms_tablet_prod_fullscreen`, is-fullscreen 클래스 토글, aria, fragment-swap 복원). 필터 접기 패턴 복제. 싱글턴 가드 기존 커버.
- 캐시버스터: JS h→i, CSS f→g(변경 파일 따라). 계약 리터럴 동기.

**F-2/F-3 테스트**: 라벨 버튼 마크업 부재, 전체화면 토글 마크업(data-* + 복원 버튼), JS 배선(localStorage 키·is-fullscreen), CSS(.is-fullscreen 크롬 숨김). 캐시버스터 리터럴.

### 4차 완료 기준
`python -m pytest tests/domains/test_production_transition_guard_api.py tests/domains/test_production_hold_api.py tests/domains/test_tablet_domain_sheets_contract.py tests/domains/test_tablet_t2_contract.py tests/domains/test_tablet_rail_contract.py tests/domains/test_production_kanban_full_window.py tests/domains/test_production_dashboard_mobile.py tests/domains/test_production_dashboard_query_count.py -q` 전부 통과 + import app APP_OK.

## 5차 라운드 (2026-07-24 사용자 피드백: 필터 바 단순화) — 진행 원장

- [x] Phase G = 필터 바 재구성: [필터] 토글·필터 접기 제거(상시 노출), 상태 select 제거(검색=전체 조건), 공장 select를 검색 앞, 변경 버튼 상시 노출. 동작검증(마크업 순서 [공장][검색][변경][초기화][전체화면]·토글/상태/접이 부재 확인)
- [x] 커밋/푸시 (단순 UI 재배치 — diff+동작검증으로 검증, 별도 리뷰 생략)

### 5차 공통 컨텍스트
- 커밋 cb2cdda9(4차)까지 배포. 캐시버스터 현재값: JS=20260724i, CSS 체인=20260724h. 변경 시 다음 값(j/i).
- 3차 D-c 필터 접기가 이번에 롤백됨. 관련 JS 함수(readFiltersOpen·writeFiltersOpen·activeAdvancedFilterCount·syncFilterToggle·restoreFilterCollapse·filter-toggle 위임·부트/스왑 복원) + 마크업(filter__more·filter-toggle·status select) + CSS(filter__toggle·__more·__toggle-badge) 전부 제거.

### Phase G — 필터 바 재구성 (프론트만)
사용자 요구 4개:
1. [필터] 토글 버튼 제거 — 검색창 넓으니 불필요, 필터 항목 상시 노출(필터 접기 __more 롤백).
2. 검색창 제일 앞(좌측)에 공장 선택(전체/1공장/2공장) select 배치.
3. 상태 select(제작대기/제작중/제작완료) 제거 — 검색은 무조건 전체 조건(전 열 대상). applyProdFilter에서 status 필터 분기 제거.
4. 변경 버튼 상시 노출.

새 필터 바 순서: `[공장 select 전체/1/2][검색 input][변경 N 토글][초기화][전체화면 토글]`.

- 마크업(tablet_kanban_body.html L95-131): filter-toggle 버튼·filter__more div·status select 제거, 공장 select를 검색 앞, 변경·초기화 상시(접이 밖), 전체화면 유지.
- JS(tablet-domain-sheets.js): 필터 접기 함수·위임·복원 전부 제거. applyProdFilter/resetProdFilter의 status 참조 제거(L447·521·572·800). 공장·검색·변경·KPI 필터·전체화면은 유지.
- CSS: filter__toggle·__more·__toggle-badge 규칙 제거, 필터 바 레이아웃(공장 앞) 정리.
- 캐시버스터: JS i→j, CSS h→i(변경 파일 따라) + 계약 리터럴 동기.
- 테스트: 필터 접기 계약(test_tablet_domain_sheets_contract.py) 제거/치환 — 검색 상시·공장 앞·변경 상시·status 부재·필터토글 부재 검증. t2/rail CSS 리터럴 동기.

### 5차 완료 기준
`python -m pytest tests/domains/test_production_transition_guard_api.py tests/domains/test_production_hold_api.py tests/domains/test_tablet_domain_sheets_contract.py tests/domains/test_tablet_t2_contract.py tests/domains/test_tablet_rail_contract.py tests/domains/test_production_kanban_full_window.py tests/domains/test_production_dashboard_mobile.py tests/domains/test_production_dashboard_query_count.py -q` 전부 통과 + import app APP_OK.

### 2차 완료 기준 (각 Phase 공통)
`python -m pytest tests/domains/test_production_transition_guard_api.py tests/domains/test_production_hold_api.py tests/domains/test_tablet_domain_sheets_contract.py tests/domains/test_tablet_t2_contract.py tests/domains/test_tablet_rail_contract.py tests/domains/test_production_kanban_full_window.py tests/domains/test_production_dashboard_mobile.py -q` 전부 통과 + `import app` APP_OK.

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
