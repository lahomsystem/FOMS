# 계정 셀프서비스 v1 — 가입 신청·승인 + 비밀번호 재설정 요청 큐 (2026-08-06)

## 배경·결정
- 현재: 계정 생성/삭제/재설정 전부 관리자 수동(/admin/users). /register 는 DB 사용자 0명일 때만 동작(부트스트랩 전용). 본인 비밀번호 "변경"은 /profile 에 이미 존재.
- 사용자 결정(2026-08-06): ① 셀프 가입 = **가입 신청 + 관리자 승인** 모델. ② 비밀번호 분실 = **재설정 요청 큐**(관리자가 기존 재설정 기능으로 처리, 인증 채널 추가 없음).
- 거절 = row 삭제(REJECTED 상태 보존 안 함, 재신청 허용).

## DB (마이그레이션 1개, downgrade 포함, 모델 import 금지 — 상수 동결 원칙)
1. `users.approval_status` — String(20) NOT NULL server_default `'ACTIVE'`. 값: `ACTIVE`/`PENDING`. 기존 행 전부 ACTIVE backfill.
2. 신규 테이블 `password_reset_requests`:
   - id PK / username_submitted String(64) NOT NULL(입력 원문)
   - user_id FK users.id ON DELETE SET NULL, nullable (매칭 시)
   - status String(20) NOT NULL default `PENDING` (`PENDING`/`DONE`/`DISMISSED`)
   - created_at DateTime NOT NULL — **now_utc_naive** (naive=UTC 규약)
   - handled_by_user_id FK users.id nullable / handled_at DateTime nullable
   - request_ip String(64) nullable (감사)
   - Index: (status, created_at)

## 라우트 (auth blueprint)
- `/register` 개방: username·name·password·confirm·희망 team(선택). 강도 검사 = `set_strong_password` chokepoint 그대로. user_count==0 → 기존 부트스트랩(ADMIN·ACTIVE) 유지. 그 외 → role=VIEWER·approval_status=PENDING·is_active=True. 성공 flash "관리자 승인 후 로그인 가능". ADMIN 전원에게 알림(Notification target_type=USER per admin + fan_out, 동일 트랜잭션).
- 로그인 게이트: **비밀번호 검증 통과 후** approval_status==PENDING 이면 "가입 승인 대기 중입니다" flash + 로그인 거부(비활성 계정 메시지와 구분, 소유자에게만 상태 노출).
- `/password-reset/request` GET+POST: username 입력. **존재 여부 무관 동일 성공 메시지**(계정 열거 방지). row 항상 생성(미매칭도 user_id=NULL 로 기록), 동일 user 의 PENDING 요청 있으면 중복 생성 생략. ADMIN 알림.
- 관리자:
  - `/admin/users/approve/<id>` POST: PENDING 만 대상, role·team 지정 후 ACTIVE 전환.
  - `/admin/users/reject/<id>` POST: PENDING 만 대상, 삭제(detach_user_references_for_delete 재사용).
  - `/admin/password-reset/<req_id>/handle` POST(action=done|dismiss): status·handled_by·handled_at 기록.
  - user_list 페이지에 가입 대기·재설정 요청 섹션 추가.

## 보안
- 가입 POST·재설정 요청 POST 에 전용 rate limit (limiter.limit 후킹, 기존 realtime.py 패턴). 예: register 5/hour·20/day, reset 5/hour (IP 키).
- CSRF: 공용 write guard 경로 확인 — pre-auth POST(/login 과 동일 취급) 허용 목록 정합 유지.
- 모든 이벤트 log_access 감사. 마지막 관리자 보호 로직 불변.

## 테스트
- 신규 tests/domains/test_auth_self_service.py: 신청→PENDING→로그인 차단→승인→로그인 성공 / 중복 아이디 / 약한 비번 거부 / 거절=삭제 / 부트스트랩(0명) 기존 동작 / reset 요청 열거 방지·row 생성·중복 생략·처리 전이 / ADMIN 알림 생성.
- 기존 회귀: test_bootstrap_admin, test_auth_enforcement, test_password_policy, test_user_delete.

## 비범위 (명시)
- 이메일/전화 컬럼·인증코드 재설정(Phase 2 후보), REJECTED 상태 보존, 승인 시 사용자 통지 채널.
