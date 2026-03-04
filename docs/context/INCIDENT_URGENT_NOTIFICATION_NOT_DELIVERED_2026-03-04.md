# Incident: 긴급 알림 실시간 전달 실패

## 1. Incident Summary
- Incident ID: INCIDENT_URGENT_NOTIFICATION_NOT_DELIVERED_2026-03-04
- Severity: SEV-3 (부분 기능 장애 — 실시간 알림만 영향, DB 저장·폴링으로 우회 가능)
- Status: Mitigated
- Started At: 2026-03-04 (사용자 보고)
- Detected By: 사용자 (관리자 긴급 알림 발송 시 수신자에게 전달 안 됨)
- User Impact: 관리자가 긴급 알림을 보내도 사용자 화면에 실시간(경고음·오버레이)이 표시되지 않음. DB에는 저장되므로 새로고침·배지 폴링 시 확인 가능.

## 2. Scope and Blast Radius
- 영향 기능: 실시간 ERP 알림 (Socket.IO `erp_notification` 이벤트)
- 영향 사용자/트래픽: 관리자·매니저가 발송한 긴급 알림 수신자
- 데이터 손상 가능성: 없음 (DB 저장은 정상)
- 규제/보안 영향: 없음

## 3. Timeline
1. 사용자 보고: 관리자 긴급 알림 발송 시 사용자에게 전달 안 됨
2. 분석: emit_erp_notification_to_users → _SOCKETIO_INSTANCE / Redis / 다중 워커 경로 검토
3. 수정: 진단 로깅 추가, REDIS_URL 미설정 시 경고, API 응답에 realtime_sent 반영

## 4. Hypothesis Board
| Hypothesis | Supporting Evidence | Contradicting Evidence | Decision |
|------------|---------------------|------------------------|----------|
| _SOCKETIO_INSTANCE is None | Socket.IO 미초기화 시 emit 0 반환 후 종료 | - | Keep |
| REDIS_URL 미설정 + 다중 워커 | Procfile -w 2, Replica 2 → Redis 없으면 emit이 다른 워커/레플리카의 클라이언트에 도달 불가 | - | Keep |
| 클라이언트 room 미가입 | connect 시 join_room(user_{id}) 있음 | - | Reject |
| 이벤트/페이로드 불일치 | 서버 emit 'erp_notification', 클라이언트 on 'erp_notification' | - | Reject |

## 5. Technical Investigation
- 관련 로그: emit 시 None 반환 시 로그 없음 (수정 전)
- 관련 코드 경로: `services/realtime_notifications.py`, `app.py`, `apps/api/notifications.py`
- 환경: Railway Procfile `-w 2`, Redis MQ (REDIS_URL) 필요

## 6. Containment (Immediate)
- 없음. DB 저장·배지 폴링으로 알림 확인 가능.

## 7. Root Cause
- **직접 원인**: (1) Redis 미설정 시 다중 워커/레플리카에서 emit이 다른 워커의 클라이언트에 도달하지 못함. (2) _SOCKETIO_INSTANCE가 None일 때 조용히 0 반환하여 원인 파악 어려움.
- **재현 조건**: REDIS_URL 미설정 + gunicorn -w 2 이상 또는 Replica 2 이상

## 8. Permanent Fix
- **변경 파일**:
  - `services/realtime_notifications.py`: _SOCKETIO_INSTANCE None 시 경고 로그, emit 성공 시 정보 로그
  - `app.py`: REDIS_URL 미설정 시 Procfile -w 2 관련 경고 문구 강화
  - `apps/api/notifications.py`: realtime_sent 반환, 실시간 미전송 시 안내 메시지
- **핵심**: 진단 로깅으로 원인 추적 가능, Railway 배포 시 REDIS_URL 설정 필수 확인

## 9. Validation
- Railway 배포 후 REDIS_URL 설정 확인
- 관리자 알림 발송 → 수신자 브라우저에서 실시간 수신 확인
- realtime_sent < sent_count 시 응답 메시지에 "실시간 전송: N명" 표시 확인

## 10. Prevention
- **Runbook**: DEPLOY_NOTES에 "실시간 알림·채팅 동작을 위해 Web 서비스에 REDIS_URL 설정 필수" 명시
- **모니터링**: 로그 `[realtime] _SOCKETIO_INSTANCE is None` 발생 시 알림

## 11. Postmortem Checklist
- [x] Containment와 Permanent Fix를 구분해 기록했다.
- [x] 기각한 가설과 근거를 기록했다.
- [x] 재현 절차를 텍스트로 남겼다.
- [ ] 재발 방지 액션의 오너/기한을 지정했다.
