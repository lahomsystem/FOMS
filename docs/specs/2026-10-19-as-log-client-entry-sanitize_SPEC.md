# AS 기록 수기 항목 정제를 저장 함수 한 곳으로 모으기 — SPEC (2026-10-19)

## 목적
AS 기록(`structured_data.shipment.as_log`)에 사람이 쓴 항목을 추가하는 모든 경로가 같은 정제를 거치게 한다. 지금은 정제를 호출부가 맡고 있어서, 새 경로가 생길 때마다 빠뜨릴 수 있다.

## 지금 구조
- 시스템 항목 `append_system_log`(`foms/services/orders/as_log.py:208`)는 함수 안에서 escape 한다 — "호출부마다 escape를 요구하는 대신 유일한 생성 지점에서 봉인한다" 는 주석대로.
- 수기 항목 `append_client_log`(`foms/services/orders/as_log.py:198`)는 docstring 이 "본문(호출자가 sanitize 완료)" 이라고 적고 정제를 호출부에 맡긴다.
- 호출부 4곳:
  - `foms/api/cs/as_orders.py:667` — 직원 AS 접수. 앞에서 `sanitize_as_content_html` 실행.
  - `foms/api/cs/as_orders.py:1164` — 직원 AS 기록 추가. `_clean_as_log_text` 가 정제.
  - `foms/services/orders/as_upload_anchor.py:96` — 고정 문구 상수.
  - `foms/services/partners/as_intake.py:68` — 협력사 AS 접수. strip·길이 자르기만 하고 정제 호출이 없다.
- 렌더는 항목 text 를 정제된 rich HTML 로 보고 그대로 출력한다(`templates/cs/partials/as_card_macros.html:70`).

## 변경
1. `append_client_log` 안에서 `sanitize_as_content_html(text)` 를 실행한 결과를 저장한다. 시스템 항목과 같은 "생성 지점 봉인" 이 된다.
   - 정제는 같은 입력에 같은 결과를 내므로(캐시 함수 `_sanitize_as_content_html_cached`), 이미 정제한 직원 경로에 다시 적용해도 내용이 바뀌지 않는다.
2. docstring 의 "호출자가 sanitize 완료" 를 "함수 안에서 정제한다" 로 바꾼다.
3. `tests/domains/test_as_timeline_contract.py:292` 의 주석("append_client_log 가 sanitize 한다")이 이제 사실이 되므로 그대로 두되, 계약 테스트에 실제 동작 단언을 추가한다.
4. 협력사 경로(`as_intake.py`)는 손대지 않는다 — 봉인 하나로 해결되는 것이 이 변경의 요점이다.

## 데이터
- 기존에 저장된 협력사 접수 항목은 이 변경으로 바뀌지 않는다. 운영 협력사 기능은 2026-10 신설이라 대상 행이 적다. 배포 뒤 운영에서 협력사 접수 항목 수를 개수만 확인하고(읽기), 있으면 같은 정제를 적용하는 일회성 정리를 별도 승인으로 진행한다.
- structured_data 를 고치게 되면 프로젝트 규약(`copy.deepcopy` → 수정 → 재대입 → `flag_modified`)을 따른다.

## 테스트
- `tests/domains/test_as_log_service.py` 에 추가:
  - `test_append_client_log_sanitizes_text` — 허용 목록 밖 태그가 든 본문을 넣으면 저장된 text 에 그 태그가 없다(무해 표지 `CLAUDE-TEST-` 사용).
  - `test_append_client_log_keeps_allowed_markup` — 허용된 서식(줄바꿈·굵게 등)은 그대로 남는다.
  - `test_append_client_log_idempotent_for_sanitized_input` — 이미 정제한 본문을 넣으면 결과가 입력과 같다.
- 협력사 경로 회귀: `tests/security/` 협력사 테스트에 "협력사 AS 접수 후 저장된 기록 text 가 정제 결과와 같다" 1건.
- 단일 파일 실행: `test_as_log_service.py` · `test_as_timeline_contract.py` · 협력사 테스트 파일.

## 영향·위험
- 성능: 정제는 캐시 함수라 접수 1건당 비용이 작다. 대시보드 렌더 경로는 바뀌지 않는다.
- 동작: 직원 경로 결과는 같다(같은 정제의 재적용). 협력사 접수 본문에서 허용 목록 밖 태그만 빠진다.
- 되돌리기: 함수 한 줄 변경이라 되돌리기 쉽다.

## 등급
`**C` — 서비스 함수 한 곳 변경 + 테스트. 배포는 deploy → 스테이징 확인 → 운영 승격(사용자 요청 시).
