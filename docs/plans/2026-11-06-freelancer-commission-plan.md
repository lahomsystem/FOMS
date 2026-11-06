# 프리랜서 영업 수수료 — 실행 플랜 (FCOMM-01)

설계서 `docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md`(2판) · 진행 원장 `docs/plans/2026-11-06-freelancer-commission-ledger.md` · 검수 원장 `docs/plans/2026-11-06-freelancer-commission-review-ledger.md` 와 한 벌이다.

공통 규칙
- 작업 폴더: 세션 워크트리 `c:/tmp/foms-s-freelancer-commission`(브랜치 `session/freelancer-commission`, origin/deploy 기준). 메인 체크아웃은 건드리지 않는다.
- task 하나 = 한 세션 크기. 끝나면 그 자리에서 진행 원장 상태를 바꾸고 pathspec 커밋(`git commit -F <파일> -- <경로들>`).
- 모든 task 공통 완료 조건: `python -c "import app; print('APP_OK')"` 출력 `APP_OK` + 그 task 의 시험 green. push 전에는 `scripts/ops/pre_push_smoke.ps1` exit 0(파이프 뒤 exit 코드를 읽지 않는다 — `smoke && git push`).
- 새 코드는 새 모듈(`foms/services/sales_commission/`, `foms/api/sales_commission.py`, `foms/web/sales_commission.py`)에 둔다. 500줄 가까운 기존 파일(`context_processors.py`, `foms/api/cs/dashboard.py`, `erp_permissions.py`)에는 호출 한 줄만.
- JS 새 파일은 300줄 미만으로 나눈다. 인라인 스타일 금지(CSS 파일로). 쓰기 라우트는 `python tools/harness/refresh_inventories.py` 로 manifest 3종 갱신.
- 시험에 실제 요율·고객 정보·실명을 넣지 않는다.

## 0단계 — 없음

이미 있는 구멍 두 개(설계서 §6.4)는 사용자 결정 D19 로 T17 에서 같이 고친다.

## 1단계 — 계산·화면

### T1 프리랜서 설정 + 설정 화면
- 대상: `foms/services/sales_commission/settings.py`(load/save/검증/`is_freelancer`/맞출 이름 표, SystemSetting `sales_freelancer_settings`, version 409), `foms/web/admin/sales_freelancers.py` + `templates/admin/sales_freelancers.html` + `static/js/admin/sales-freelancers.js`, API `foms/api/admin/sales_freelancers.py`, 블루프린트 등록(뒤에 붙임), 정책·manifest.
- 완료 기준: `pytest tests/domains/test_sales_freelancer_settings.py -q` — 저장·409·맞출 이름 중복(다른 활성 사용자) 거부·STAFF/SALES 아님 거부·bp 범위·마감된 달 이하 적용 달 거부(마감 표 전이면 검사 생략 표시)·ADMIN 만 POST·회계 GET 허용.
- 경계: 사용자 관리 화면은 안 건드림.

### T2 inputs 표 + 마이그레이션
- 대상: `models.py` `SalesCommissionInput`, `migrations/versions/fcomm_00_sales_commission_inputs.py`(down_revision = 그때 origin/deploy head).
- 완료 기준: `pytest tests/postgres/test_migration_chain.py tests/postgres/test_delete_retention.py -q`(PG 레인, `FOMS_TEST_DATABASE_URL`) green + SQLite `pytest tests/domains -q -k sales_commission` green.
- 경계: FK `ondelete CASCADE`.

### T3 계산 함수 + 대상 조회
- 대상: `foms/services/sales_commission/calc.py`(순수: 주인·거래구분·대상·달·금액·세금), `foms/services/sales_commission/read_model.py`(평탄 칸 `erp_stage_code`·`erp_construction_date`·`erp_measurement_date`·`manager_name` 으로 후보를 좁힌 뒤 파이썬 판정).
- 완료 기준: `pytest tests/domains/test_sales_commission_calc.py -q` — 설계서 §11.1 표 중 마감·조정 사례를 뺀 전부. 순수 함수 시험은 DB 없이.
- 경계: 출고가 공식은 `erp_shipping_price_from_structured` 와 같되 취소 품목을 뺀다(D18) — 그 함수 자체는 바꾸지 않는다.

### T4 차감 보강
- 대상: `foms/services/settlement_deductions.py`(유효 판정 함수) → 6곳 교체, 취소 API, 차감 넣기·취소 `execute_order_mutation`, CS 단계 허용(핸들러 안), SALES 면 사람 필수, 프리랜서 `FINANCE_MUTATION` 거부, 알림 `SALES_COMMISSION_DEDUCTION` + P1 등록.
- 완료 기준: `pytest tests/domains/test_settlement_deductions.py tests/domains/test_settlement_aggregation.py tests/domains/test_settlement_rows_api.py -q` + 기존 `tests/domains/test_settlement_*` 전부 green + 동시 저장 시험(두 차감 겹침 둘 다 남음).
- 경계: `TARGET_STATUSES` 상수 안 건드림. 실무 탭 버튼·이력 글은 미룸.

### T5 수수료 탭 API
- 대상: `foms/api/sales_commission.py` — `GET rows`, `PUT inputs/<order_id>`(version), "본인 수정" 표시(`order_field_changes` 의 발주사·실측일·시공일·출고가, actor = 프리랜서).
- 완료 기준: `pytest tests/domains/test_sales_commission_api.py -q` — 권한 매트릭스(설계서 §11.2), 409, 표시 판정.

### T6 수수료 탭 화면
- 대상: `templates/cs/partials/settlement_commission_body.html`, 탭 버튼(`settlement_dashboard_body.html`), `static/js/settlement/commission*.js`(300줄 미만 여러 개), `static/css/settlement/settlement-commission.css`, 자산 핀.
- 완료 기준: `pytest tests/domains/test_settlement_commission_render.py tests/domains/test_settlement_dashboard_render.py -q` + `tests/harness/test_file_size_ratchet.py tests/harness/test_harness_drift_guard.py` green + docs-facing 목록 필요 시 `ci.yml` 갱신.

### T7 내 수수료 화면 + 발주사 선택지
- 대상: `foms/web/sales_commission.py` `/erp/my-commission`(서버 렌더), `templates/sales_commission/my_commission.html`, 서랍 링크(`erp_mobile_menu_drawer.html`), 발주사 선택지에 활성 프리랜서 맞출 이름(PC·모바일 주문 탭, 태블릿 실측 폼, 마법사, 불러오기 판정 `erp-order-shared.js:2211-2225`).
- 완료 기준: `pytest tests/domains/test_my_commission_page.py tests/domains/test_orderer_freelancer_option.py -q` — 본인만·`user_id` 무시·설정 밖 직원 거부, 발주사 = 맞출 이름일 때 알림톡 브랜드 HAUD·정산 구분 일반(D14 회귀).

### T8 1단계 스테이징 검수
- 방법: deploy 반영 뒤 스테이징 `claude_master` 로 회계 페르소나(PC)·프리랜서 페르소나(390px) 흐름. gstack browse. 실데이터 불가침 — 가상 주문 `CLAUDE-TEST-` 만.
- 완료 기준: 진행 원장에 화면 확인 결과·스크린샷 경로 기록, 발견 결함은 task 로.

## 2단계 — 마감·지급 (목표: 2026-12-10 전 스테이징 검수)

### T9 마감 표 + 서비스
- 대상: `models.py` `SalesCommissionClosing`, `migrations/versions/fcomm_01_sales_commission_closings.py`, `foms/services/sales_commission/closing.py`(대상 줄·오름차순·설정 행 FOR UPDATE·0 이하 거부·세금·지급 완료·마감 취소=삭제+감사, J9 굳힘).
- 완료 기준: `pytest tests/domains/test_sales_commission_closing.py -q` + PG 왕복.

### T10 마감 화면 + CSV + 실측일 기준 전환
- 대상: 탭에 마감·지급 완료·취소, `GET export.csv`(BOM·CRLF, 감사), 탭·내 수수료 화면의 basis 전환(D7).
- 완료 기준: `pytest tests/domains/test_sales_commission_export.py tests/domains/test_settlement_commission_render.py -q`.

### T11 2단계 스테이징 검수
- 완료 기준: 가상 주문으로 마감·지급 완료·취소·CSV 확인, 원장 기록. production 승격은 사용자 명시 요청 때만.

### T12 조정 줄 (2027-01-10 전)
- 대상: `closing.py` 에 이전 마감 주문 다시 계산 → ADJUST.
- 완료 기준: §11.1 마감 뒤 차감·시공비 정정·담당 변경 사례 green.

## 3단계 — 보기 범위 제한 (프리랜서를 새로 받기 전)

### T13 연결 표 + before_flush 훅 + 되채우기
- 대상: `OrderFreelancerLink` 모델·마이그레이션 `fcomm_02`, `foms/services/sales_commission/links.py`(훅 — `foms/services/order_date_sync.py` 꼴, Order 인스턴스·structured 변경만), `scripts/maintenance/backfill_freelancer_links.py`(드라이런 기본).
- 완료 기준: 훅 시험(PUT·실측 칸·자동 저장·오프라인 병합 경로에서 연결 갱신, `_DeriveShim` 점검 무영향) + PG 왕복.

### T14 문지기 + 허용 목록
- 완료 기준: `pytest tests/security/test_freelancer_gate.py -q` — 모든 URL 규칙 막힘 전수.

### T15 주문 단위 판정
- 완료 기준: 허용 endpoint 의 URL·query·본문 주문 번호마다 남의 주문 404 시험.

### T16 목록 강제 + 조각 전수 점검
- 완료 기준: `?mine=0`·쿠키 무력, 실측 판 HTML 남의 고객명 0, history_more 꺼짐 시험. 허용 화면 전수 점검 결과를 원장에 표로.

### T17 옆길 + 배정 알림
- 대상: 이미 있는 구멍 두 개(Socket.IO `join_room` 회원 확인, 채팅 파일 key 범위 — D19), 발주사 변경 거부, 프로필 이름 저장 거부, 수신자 함수 통합, 소켓 채팅 이벤트 거부, 프리랜서 지정 때 채팅 회원 해제·옛 알림 숨김, 메뉴, `SALES_ORDER_ASSIGNED`.
- 완료 기준: 설계서 §6.5 남은 시험 전부 green.

### T18 반증 재검수 + 실계정 QA
- 완료 기준: 반증 에이전트가 프리랜서 계정으로 남의 주문을 얻는 길 0건(원장 기록), 스테이징 프리랜서 계정 실화면 확인.
