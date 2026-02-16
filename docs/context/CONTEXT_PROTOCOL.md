# 컨텍스트 엔지니어링 상세 프로토콜

> 이 문서는 `08-context-engineering.mdc`의 상세 버전입니다.
> alwaysApply Rule에는 핵심만 남기고, 여기에 전체 프로토콜을 기록합니다.
> 필요 시 `@docs/context/CONTEXT_PROTOCOL.md`로 참조하세요.

## 세션 시작: 점진 로딩 (Progressive Loading)

모든 파일을 한꺼번에 읽지 않는다. 상황에 따라 점진적으로 로드한다.

### 1순위 (항상)
- `docs/context/COMPACT_CHECKPOINT.md` -- **있으면** 최우선 읽기 (컨텍스트 압축 후 복원)
- `docs/CURRENT_STATUS.md` -- 프로젝트 전체 상태

### 2순위 (이어지는 작업일 때)
- `docs/context/TASK_REGISTRY.md` -- 진행 중 작업이 있는지 확인

### 3순위 (설계 변경/충돌 시)
- `docs/context/DECISIONS.md` -- 이전 결정사항 확인 (최근 5개만)

### 로드하지 않는 것
- `SESSION_LOG.md`, `EDIT_LOG.md` -- Hooks가 자동 관리, AI가 읽을 필요 없음

## 토큰 절약 전략

### 파일 읽기
| 파일 크기 | 전략 |
|----------|------|
| 500줄 이상 | Grep/SemanticSearch로 필요 구간만 탐색 |
| 300줄 이하 | 전체 Read 허용 |
| 여러 파일 동시 | subagent(explore)에 위임, 결과 요약만 수신 |
| 이미 읽은 파일 | 불확실하면 해당 구간만 재확인 (전체 재읽기는 피함) |

### 응답 작성
- 기존 파일 수정: StrReplace로 변경 부분만 (전체 Write 금지, 신규 파일 제외)
- 설명: 핵심만 간결하게
- 이전 대화 내용 반복 금지

### Subagent 활용
- 탐색/분석 → subagent에 위임, 결과 요약만 메인에 반환
- 대규모 수정 → subagent에 위임, 메인 컨텍스트 오염 방지
- 코드 리뷰 → 별도 subagent, 리뷰 결과만 보고

## 기억 영속화

### 자동 (Hooks - .cursor/hooks.json에 구성 완료)
| 훅 | 스크립트 | 동작 |
|----|---------|------|
| `sessionStart` | `session_start.py` | 세션 로그 시작, SESSION_LOG.md 업데이트 |
| `afterFileEdit` | `track_edits.py` | 편집 기록 EDIT_LOG.md에 자동 저장 (최근 50개) |
| `preCompact` | `pre_compact.py` | 압축 직전 COMPACT_CHECKPOINT.md 자동 생성 |
| `stop` | `session_stop.py` | 세션 종료 기록, 편집 파일 목록 반영 |
| `beforeShellExecution` | `guard_shell.py` | 위험 명령 자동 차단 (rm -rf, DROP TABLE 등) |

### 수동 (AI가 처리)
- 중요 결정 → `docs/context/DECISIONS.md`에 기록
- 작업 상태 → `docs/context/TASK_REGISTRY.md` 업데이트
- 세션 요약 → `docs/CURRENT_STATUS.md` 업데이트
- 핵심 지식 → `memory` MCP 지식 그래프에 저장 (선택)

## 세션 종료

```
1. docs/CURRENT_STATUS.md 업데이트 (변경 사항 + 다음 할 일)
2. docs/context/TASK_REGISTRY.md 업데이트 (작업 상태 변경)
3. 중요 결정이 있었으면 DECISIONS.md에 기록
4. memory MCP로 핵심 사항 저장 (선택)
```

## 컨텍스트 예산 참고

| 항목 | 예상 토큰 | 절약 방법 |
|------|----------|----------|
| 시스템 프롬프트 + Rules | ~2,000-3,000 | alwaysApply 최소화 |
| 파일 1개 (500줄) | ~3,000-5,000 | 필요 구간만 |
| 대화 기록 (10턴) | ~20,000-40,000 | 새 세션 분리 |
| Subagent 결과 | ~1,000-3,000 | 요약만 반환 |
| **효과적 작업 공간** | **~80,000-120,000** | 위 전략으로 확보 |

## 이 문서의 업그레이드

이 프로토콜은 `10-self-upgrade.mdc`에 따라 지속 개선됩니다.
반복 문제 발생 시, 새 패턴 발견 시, 사용자 피드백 시 업데이트합니다.
