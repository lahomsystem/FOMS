# Incident Template

> 코딩 관련 장애를 동일한 품질로 분석/복구하기 위한 표준 템플릿입니다.
> 권장 사용: `incident-rca` 에이전트 + `14-incident-rca.mdc`.

## 1. Incident Summary
- Incident ID:
- Severity: `SEV-1 | SEV-2 | SEV-3 | SEV-4`
- Status: `Open | Mitigated | Resolved | Monitoring`
- Started At:
- Detected By:
- User Impact:

## 2. Scope and Blast Radius
- 영향 기능:
- 영향 사용자/트래픽:
- 데이터 손상 가능성:
- 규제/보안 영향:

## 3. Timeline
1. `[HH:MM]` 증상 최초 탐지
2. `[HH:MM]` 가설/조치
3. `[HH:MM]` 복구/검증

## 4. Hypothesis Board
| Hypothesis | Supporting Evidence | Contradicting Evidence | Decision |
|------------|---------------------|------------------------|----------|
|            |                     |                        | Keep/Reject |

## 5. Technical Investigation
- 관련 로그:
- 관련 코드 경로:
- 예외/에러 스택:
- 환경 변화(배포/env/dependency):
- 데이터베이스 상태:

## 6. Containment (Immediate)
- 임시 완화 조치:
- 적용 시각:
- 리스크:

## 7. Root Cause
- 근본 원인:
- 왜 사전에 탐지되지 않았는가:
- 어떤 조건에서 재현되는가:

## 8. Permanent Fix
- 변경 파일:
- 핵심 수정 내용:
- 왜 이 수정이 근본 원인을 제거하는가:

## 9. Validation
- 재현 테스트:
- 회귀 테스트:
- 모니터링 지표 확인:

## 10. Prevention
- 테스트 추가:
- Rule/Hook/Agent 개선:
- Runbook/문서 갱신:
- 오너/기한:

## 11. Postmortem Checklist
- [ ] Containment와 Permanent Fix를 구분해 기록했다.
- [ ] 기각한 가설과 근거를 기록했다.
- [ ] 재현 절차를 텍스트로 남겼다.
- [ ] 재발 방지 액션의 오너/기한을 지정했다.
