# 네이버 정산 API 대시보드 — 리서치 공용 브리프 (2026-09-02)

## 목표
FOMS `/erp/settlement` 정산 대시보드(탭 3개: 요약·실무·분석)에 네이버 커머스 API 정산 데이터를 붙인다.
사용자 요구: (1) 네이버 정산 API 5종으로 얻을 수 있는 **모든** 데이터를 보여주고, 기존 탭처럼 그래프 시각화까지.
(2) **결정 필요**: 탭 바 맨 오른쪽에 "네이버 정산" 별도 탭 vs 기존 3탭에 네이버 데이터를 녹여 업그레이드.
회계팀 사용자 페르소나 + 회계 프로그램 설계 전문가 페르소나로 deep research 후 판단.

## 작업 트리 (읽기 전용 — 리서치 단계에서는 소스 편집 금지)
- 경로: `c:/tmp/foms-s-settle-naver` (브랜치 `session/settle-naver`, base `origin/deploy` 416a3acfc)
- 산출물 위치: `docs/research/2026-09-02-naver-settlement/` (이 디렉토리에만 파일 생성)

## 기존 정산 대시보드 파일
- 라우트: `foms/web/cs/settlement_dashboard.py`, API: `foms/api/cs/settlement.py`
- 집계: `foms/services/settlement_aggregation.py`, 행: `foms/services/settlement_rows.py`
- 템플릿: `templates/cs/settlement_dashboard.html`, `templates/cs/partials/settlement_dashboard_body.html`, `templates/cs/partials/settlement_operations_body.html`
- JS: `static/js/settlement/dashboard.js`, `static/js/settlement/operations.js`
- CSS: `static/css/settlement/settlement-dashboard.css`, `static/css/settlement/settlement-operations.css`
- 테스트: `tests/domains/test_settlement_*.py`
- 스펙·원장: `docs/specs/2026-08-31-settlement-dashboard_SPEC.md`, `docs/plans/2026-08-31-settlement-dashboard-impl-ledger.md`, `docs/design/settlement-dashboard-research-2026-08/`
- 최근 커밋: 796d26982(폭·높이 개편·집중 모드), 0784ea5e3(aging 1요청), 7c09a312e(실무 탭), 8a5d0650b(탭 3개 셸)

## 기존 네이버 커머스 연동
- `foms/services/integrations/naver_commerce/` (client.py=인증·호출, accounts.py, constants.py, ingest.py, backfill.py, watermark.py, claim_watch.py ...)
- 관리 화면: `foms/web/admin/naver_ingest.py`, 워크벤치 템플릿 `templates/admin/naver_*`
- 워커: `tasks.py` / `scripts/maintenance/run_naver_*.py`

## 알려진 제약 (메모리에서 — 검증 필요 시 코드로 확인)
- 네이버 API 호출은 **WORKER 단일 서비스에서만** (네이버 IP 화이트리스트 3슬롯 = Railway static egress IP 3개와 정확히 일치. web 서비스에서 직접 호출 금지).
- 규격 정본 = `https://apicenter.commerce.naver.com/llms.txt` + 공식 Discussions. 문서에 없는 규칙이 Discussions에 있다. 질의 창구 없음 → 모르면 NOT IN DOCS + 안전측.
- 스테이징도 실계정(실데이터 접근). 읽기 전용 API라 발송 위험은 없음.
- 프론트: 인라인 스타일 금지, jQuery 금지, fetch try/catch + data.success, Jinja→JS는 data-* + safeJsonParse. 공용 부품은 container query.
- 백엔드: 함수 50줄·docstring·타입힌트, API 응답 `{'success','data','error'}`.

## 네이버 정산 API 5종 (승인 완료)
- GET /v1/pay-settle/settle/case — https://apicenter.commerce.naver.com/llms/get-v1-pay-settle-settle-case.md
- GET /v1/pay-settle/settle/commission-details — https://apicenter.commerce.naver.com/llms/get-v1-pay-settle-settle-commission-details.md
- GET /v1/pay-settle/settle/daily — https://apicenter.commerce.naver.com/llms/get-v1-pay-settle-settle-daily.md
- GET /v1/pay-settle/vat/case — https://apicenter.commerce.naver.com/llms/get-v1-pay-settle-vat-case.md
- GET /v1/pay-settle/vat/daily — https://apicenter.commerce.naver.com/llms/get-v1-pay-settle-vat-daily.md

## 산출물 규칙
- 한글로 작성(코드·API 필드명은 원문). 사실은 출처(파일:라인 또는 URL) 표기. 추정은 "추정"이라고 명시.
- 파일 하나당 하나의 주제. 결론을 맨 위 10줄 안에.
