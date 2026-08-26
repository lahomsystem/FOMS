# CI 속도·위생 개선 진행 원장 (2026-08-26)

감리 근거: 멀티에이전트 정밀 감리(A 프로파일러 / B 워크플로 / C 테스트코드 / D 정상성 판정 / CEO 총괄).
보고서 원본은 세션 스크래치패드에 있고, 결론과 실측치는 아래에 옮겨 적는다.

## 배경 실측

| 항목 | 값 |
|---|---|
| FOMS CI median (2026-07-23) | 4.93분 |
| FOMS CI median (2026-08-26 수정 전) | 14.07분 (32일간 단조 증가 +0.231분/일) |
| `Run tests` 스텝 (수정 전) | 839초 = job 908초의 92% |
| 그중 PBKDF2 600,000 해싱 | 676초 (73%) |
| 그중 매 테스트 83테이블 DDL | 146초 (17%) |
| 실제 테스트 로직 | 92~98초 (11%) |
| 큐 대기 | p50/p90/max 전부 0초 (러너 부족 아님) |

분해 합이 총시간을 오차 2%로 재구성 → 숨은 병목 없음.

## P0 (완료, deploy 반영됨)

| ID | 내용 | 상태 | 결과 |
|---|---|---|---|
| P0-1 | 테스트 레인 PBKDF2 완화 (`DEFAULT_PBKDF2_ITERATIONS = 10`) | DONE `d9731236` | `Run tests` 839초 → 354초 |
| P0-2 | 봉인 계약 5건 (`tests/domains/test_password_kdf_contract.py`) | DONE `d9731236` | 패치 무효화 시 빨강 확인 |
| P0-3 | 전 워크플로 `timeout-minutes` (7파일) | DONE `01fd8e97` | 기본 6시간 → 15~30분 |
| P0-4 | 승격 PR(base=production)도 본 스위트·하네스 검증 | DONE `01fd8e97` | ci.yml·harness-ci.yml PR 필터에 production 추가 |

**P0 후 실측**: FOMS CI 14.07분 → **7.18분**, 전 워크플로 green.

## P1·P2 (이번 작업)

| ID | 내용 | 완료 기준 | 상태 |
|---|---|---|---|
| T1 | `node --check` 148 spawn → 1프로세스 배치 파싱 | 해당 테스트 12.5초 → 2초 이하, 깨진 JS 를 여전히 검출(고의 파손 1건으로 빨강 확인) | PENDING |
| T2 | pytest 설정 파일 신설 (pytest.ini SSOT) | 설정 파일 존재 + CI 명령과 로컬 명령이 같은 옵션으로 동작 | PENDING |
| T3 | 스키마 세션 스코프화 + `after_create` 시드 재실행 | 전체 스위트 실패 집합이 T3 이전과 **완전 동일**, `Run tests` −100초 이상 | PENDING |
| T4 | pytest-xdist 병렬 (`-n auto --dist loadfile`) | 3회 연속 결과 집합 동일(순서 의존 없음), CI `Run tests` 추가 감소 | PENDING |
| T5 | docs 카브아웃 paths 필터 | 문서 전용 커밋에 무거운 잡 미실행 + 문서를 읽는 계약 테스트 8파일은 여전히 실행 | PENDING |
| T6 | `ci_watch.py` cancelled→green 오판 수정 | cancelled 런에 exit 0 을 주지 않음(단위 검증) | PENDING |
| T7 | rum-daily 상시 red(28.6%) 정리 | 근본 원인 수정 후 연속 성공, 또는 실패 조건 명시 | PENDING |
| T8 | Actions 캐시 위생 (6.96GB/10GB) | 축출 위험 해소 | PENDING |

## 후속

| ID | 내용 | 상태 |
|---|---|---|
| F1 | production 승격 (P1 완료 후, 사용자 재확인 필수) | PENDING |
| F2 | `docs/AI_STATUS.md` + `docs/harness/policy/DECISIONS.md` 기록 | PENDING |
| F3 | 1주일 뒤 효과 재측정 (기울기가 다시 양수인지) | PENDING |

## 기각 (재제안 금지 — 근거)

- **`concurrency: cancel-in-progress`** — `ci_watch.py` 가 cancelled 를 green 으로 오판(이미 4건 발생) + 커밋 단위 cherry-pick 승격 정책상 커밋마다 green 이 필요. P0-1 이후 실익도 소멸.
- **변경 파일 기반 선택 실행** — 트리 전수 스캐너 테스트 8종이 폭발 반경 매핑 불가. FOMS 의 과거 CI red 사고가 전부 "폭발 반경 밖"이었다.
- **larger runner** — 큐 대기 0초이고 public repo 라 이미 4 vCPU 무료.
- **matrix 샤딩** — `tests/domains` 가 99% 라 불균형, 판정면만 4배.
- **`requirements-ci.txt` 분리** — 운영 드리프트 전례(solapi).
- **테스트 삭제·스킵으로 시간 줄이기** — 프로젝트 정책 금지.
