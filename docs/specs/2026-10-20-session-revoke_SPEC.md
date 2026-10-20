# 로그아웃·비밀번호 변경·역할 변경·대리 로그인 뒤 세션 정리 — SPEC (2026-10-20)

## 목적
로그인 상태는 서명된 쿠키 하나(30일, 쓸 때마다 연장)에만 담겨 있고 서버 쪽에서 개별로 끊을 수단이 없다. 그래서 세 가지가 어긋난다.
1. 로그아웃해도 그 전에 복사된 같은 쿠키는 계속 로그인 상태다. 비밀번호를 바꿔도 다른 기기의 세션은 그대로다.
2. 역할을 낮춰도(ADMIN→STAFF) 네이버 워크벤치 5곳이 쿠키 안 `session['role']` 으로 관리자 분기를 해서 옛 역할로 동작한다.
3. 관리자가 다른 계정으로 전환(대리 로그인)한 세션은 그 관리자를 비활성화해도 살아 있다. 전환 중 한 일은 감사 기록에 대상 계정으로만 남는다.

## 지금 구조
- `_set_current_user`(`foms/platform/http.py`)가 요청마다 `users` 행을 다시 읽고, 없거나 비활성이면 `session.clear()` 한다. 버전 비교는 없다.
- 로그인(`foms/web/auth/routes.py` login)은 `user_id`·`username`·`role` 을 세션에 넣는다. 로그아웃은 `session.clear()` 뿐.
- 비밀번호 설정은 `set_strong_password`(`foms/services/security/password_policy.py`) 한 곳을 지난다(본인 변경·관리자 재설정·협력사·신규 가입).
- 대리 로그인: `switch_user` 가 `session['impersonating_from'] = 관리자 id` 를 넣고 `user_id` 를 대상으로 바꾼다. `_set_current_user` 는 대상만 본다.
- `session.get("role")` 읽기: `foms/web/admin/naver_ingest.py` 5곳(2342·2478·2485·5593·6543).

## 변경
### DB(마이그레이션 `session_rev_00`, 앞 `partner_02`)
- `users.session_version` INTEGER NOT NULL DEFAULT 0 — "이 계정의 모든 세션" 세대 번호.
- `users.revoked_session_ids` JSON(PG JSONB) NULL — 로그아웃한 세션 표지 목록 `[{"sid": 문자열, "at": 초}]`. 31일 지난 항목은 쓸 때 지우고 최대 200개.
- 둘 다 기본값이 있는 칸 추가라 표 재작성이 없다. 되돌리기는 칸 삭제.

### 새 모듈 `foms/services/security/session_guard.py`
- `pin_session(sess, user)` — 로그인 때 `sv`(= session_version)와 새 `sid`(무작위 12자)를 세션에 넣는다.
- `session_is_current(sess, user)` — `sv` 가 다르거나 `sid` 가 회수 목록에 있으면 False. **`sv` 가 없는 옛 세션은 0 으로 본다** — 배포 순간 전 직원이 로그아웃되지 않는다.
- `revoke_session(user, sid)` · `bump_session_version(user)`.

### 연결
- `_set_current_user`: 활성 확인 뒤 `session_is_current` 가 False 면 `session.clear()`. 요청 중에는 세션에 아무것도 새로 쓰지 않는다 — 폴링 응답이 쿠키를 다시 써서 방금 심은 값을 지우는 사고(SESSION-COOKIE-01, 2026-09-09)를 되풀이하지 않기 위해서다.
  대리 로그인 중이면 원 관리자 행도 읽어 없음·비활성·ADMIN 아님·`impersonator_sv` 불일치·회수 목록이면 끊는다(전환 세션에서만 1번 더 읽음).
- 로그인: `pin_session`.
- 로그아웃: 지금 세션의 `sid` 를 로그인 사용자(전환 중이면 원 관리자도) 회수 목록에 넣고 지운다 → **그 기기만** 끊긴다. 휴대폰과 PC 를 함께 쓰는 직원의 다른 기기는 그대로.
  `sid` 가 없는 옛 세션(배포 전 로그인)은 골라 끊을 수 없어 `session_version` +1 로 그 계정 세션을 모두 끊는다. 배포 뒤 첫 로그아웃 한 번만 해당한다.
- 비밀번호 설정(`set_strong_password`): `session_version` +1 → 그 계정의 모든 세션이 끊긴다. 본인이 프로필에서 바꾼 경우만 지금 세션을 새 번호로 다시 묶는다.
- 관리자 사용자 수정에서 역할·팀이 바뀌면 `session_version` +1.
- 대리 로그인: 전환 때 `impersonator_sv` 에 관리자 번호를 남기고 세션을 대상 번호로 묶는다. 복귀 때 관리자 번호로 다시 묶는다.
- `naver_ingest.py` 5곳: `session.get("role")` → 요청 사용자(`g.current_user`) 역할.
- 감사(`log_access`): 전환 세션에서 남기는 기록이면 `detail.impersonated_by = 원 관리자 id` 를 붙인다.

## 건드리지 않는 것
- 쿠키 수명(30일)·로그인 때 세션 재발급(SEC-56)·2단계 인증.
- 주문 이력(`order_field_changes.actor_user_id`)의 전환 표기 — 감사 기록만.

## 테스트
새 파일 `tests/domains/test_session_revoke.py`:
- 로그아웃 뒤 같은 쿠키로 `/profile` → 로그인 화면, 같은 사용자의 다른 세션은 그대로 200.
- 비밀번호 재설정 뒤 옛 세션 끊김, 본인 프로필 변경은 지금 세션 유지.
- 역할 변경 뒤 옛 세션 끊김. `sv` 없는 옛 세션은 그대로 통과하고 쿠키를 다시 쓰지 않음(배포 호환), 그 세션의 로그아웃은 복사본까지 끊음.
- 전환 중 관리자 비활성화 → 전환 세션 끊김, 관리자 비번 변경 → 끊김. 전환 중 감사 기록에 `impersonated_by`.
- `foms/` 안에 `session.get("role")` 읽기 0(래칫).
