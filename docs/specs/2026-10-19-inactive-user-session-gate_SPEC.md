# 비활성 계정의 세션을 요청 시작 한 곳에서 끊기 — SPEC (2026-10-19)

## 목적
계정을 비활성화(퇴사 처리)하면 그 계정의 기존 세션이 모든 경로에서 즉시 무효가 되게 한다. 지금은 활성 여부를 `login_required` 장식이 확인하므로, 장식 대신 핸들러 안에서 사용자를 확인하는 경로·쓰기 정책 가드·실시간 연결은 각자 확인해야 한다.

## 지금 구조
- 요청마다 `_set_current_user`(`foms/platform/http.py:217-229`)가 세션의 user_id 로 사용자를 읽어 `g.current_user` 에 넣는다. 활성 여부는 보지 않는다.
- `login_required`(`foms/web/auth/routes.py:310-313`)는 `g.current_user` 를 재사용하며 `not user.is_active` 면 세션을 비우고 로그인으로 보낸다.
- 쓰기 정책 판정 `evaluate_policy`(`foms/services/orders/order_mutation_policy.py:323-396`)는 활성 여부를 보지 않는다. 읽기 판정 `user_can_read_order` 는 본다.
- 실시간 연결 처리기(`foms/api/channel/socketio_handlers.py:21-36`)는 세션 user_id 존재만 본다.

## 변경
1. `_set_current_user` 에서 읽은 사용자가 없거나 `is_active` 가 False 면 `g.current_user = None` 으로 두고 `session.clear()` 한다. 승인 대기(PENDING) 계정도 같은 규칙으로 다룰지 구현 때 `login_required` 의 현재 동작과 맞춘다.
   - 그러면 장식이든 핸들러 안 확인이든 `g.current_user` 를 보는 모든 경로가 같은 결과를 받는다. `login_required` 의 기존 확인은 이중 방어로 남긴다.
   - SESSION-COOKIE-01 주석(2026-09-09 사고)대로, 활성 사용자의 정상 요청에서는 세션을 새로 쓰지 않는다. 비활성일 때만 세션을 비운다.
2. `evaluate_policy` 1단계에서 사용자가 없거나 비활성이면 거부(401)한다 — 1번과 같은 규칙을 정책 엔진 자체에도 둬서 엔진을 직접 부르는 경로가 같은 답을 받게 한다.
3. 실시간 연결 처리기 connect 에서 user_id 로 사용자를 조회해 없거나 비활성이면 연결을 거부한다(협력사 거부와 같은 자리).
4. 비활성 사용자의 마지막 활동 시각 갱신(`_touch_last_seen`)은 1번 덕분에 자동으로 멈춘다 — 별도 수정 없음, 테스트로 고정한다.

## 테스트
새 파일 `tests/domains/test_inactive_user_session_gate.py`(정책 가드·쓰기 가드를 켠 픽스처 사용):
- 활성 사용자로 세션을 만든 뒤 비활성화 → 장식 경로·핸들러 안 확인 경로·정책 가드를 거치는 쓰기 경로가 모두 로그인 요구(302 또는 401)로 바뀐다.
- 같은 경로에 활성 사용자 대조군 — 정상 응답.
- 실시간 연결: 비활성 사용자 세션 → 연결 거부, 존재하지 않는 user_id 세션 → 연결 거부, 활성 사용자 → 연결 성공(flask_socketio test client).
- 비활성 사용자 요청 뒤 last_login 이 바뀌지 않는다.
- 기존 단일 파일 회귀: `tests/domains/test_auth_enforcement.py` · `tests/domains/test_session_cookie_stability.py` · `tests/domains/test_auth_impersonation.py` · `tests/security/test_partner_gate.py`.

## 영향·위험
- 요청당 DB 조회 수는 그대로다(이미 `get_user_by_id` 를 부른다). 실시간 연결에만 조회 1회가 는다.
- 대리 로그인 세션: 대상 계정이 비활성이면 끊긴다(의도). 대리 주체 관리자의 활성 재확인은 별도 SPEC 으로 다룬다.
- 인증 코어 변경 → 이 SPEC 승인 후 구현. 배포는 deploy → 스테이징에서 테스트 계정 비활성화 시나리오 확인 → 운영 승격(사용자 요청 시).

## 등급
`**B` — 인증 경계 변경, 여러 진입점에 걸친 회귀 확인 필요.
