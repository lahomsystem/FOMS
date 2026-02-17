# Evolution Experiment Log

가설을 검증한 실험 로그입니다. 성공/실패 모두 기록합니다.

## 실험 규칙
- 각 실험은 성공 기준(DoD), 중단 기준(Abort), 롤백 방법을 포함
- 실패 실험도 삭제하지 않고 교훈/재시도 조건 기록
- 재현 가능한 근거(커밋, PR, 벤치마크, 테스트 결과) 남김

## Experiments
| ID | Date | Hypothesis ID | Change | DoD | Abort Criteria | Rollback | Result | Metrics | Lessons |
|----|------|---------------|--------|-----|----------------|----------|--------|---------|---------|
| E-001 | YYYY-MM-DD | H-001 | 예: API 응답 유틸 도입 | 통합 테스트 통과 | 오류율 5% 초과 | revert commit | pass/fail | p95, error rate | |

