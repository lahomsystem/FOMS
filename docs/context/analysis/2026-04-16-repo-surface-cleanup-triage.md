# 2026-04-16 Repo Surface Cleanup Triage

## 목적
- FOMS 저장소에서 "이미 용도 폐기됐거나", "일회성으로 남았거나", "생성 경로를 바로잡아야 하는" 파일을 `삭제 / 보관-재분류 / 유지` 3등급으로 고정한다.
- 제품 코드 자체가 아니라 문서, 하네스 산출물, 테스트 보조 자산, 로컬 런타임 산출물을 구분해 false cleanup을 막는다.

## 분류 기준
- `삭제`: 참조 0, 대체 경로 존재, 또는 생성 경로 자체가 잘못돼 있어 root cause fix 후 제거 가능한 항목
- `보관-재분류`: 바로 삭제하면 의미 손실 위험이 있어 canonical owner, archive home, retention policy를 먼저 정해야 하는 항목
- `유지`: 현재 계약, 테스트, 하네스, 세션 복원 흐름이 실제로 사용 중인 항목

## A. 삭제 후보

### A1. tracked 또는 canonical cleanup 대상
| 경로 | 판정 | 근거 | 후속 액션 |
|------|------|------|-----------|
| `docs/context/SHELL_GUARD_LOG.md` | 삭제 | `.claude/hooks/guard_shell.py`가 아직 구 경로를 기록하지만, Cursor 쪽 canonical은 이미 `docs/harness/logs/SHELL_GUARD_LOG.md`를 사용한다. 동일 역할의 새 canonical이 존재한다. | `.claude/hooks/guard_shell.py`를 canonical 경로로 바꾼 뒤 old-path 파일 제거 |
| `tools/research_center/.tmp_sources_pretty.json` | 삭제 | 코드/README는 `sources.json`, `self_upgrade_manifest.json`만 공식 입력으로 본다. `.tmp_sources_pretty.json` 참조 0건이다. | tracked temp 파일 제거 |
| `tests/harness/load/final_soak_summary.json` | 삭제 | 참조 0건. 런타임 기본 output은 `last_trace_summary.*`가 owner다. | tracked 결과 스냅샷 제거 |
| `tests/harness/load/final_soak_summary.txt` | 삭제 | 참조 0건. `final_soak_summary.json`과 동일한 일회성 결과물이다. | tracked 결과 스냅샷 제거 |

### A2. workspace residue 클래스
| 경로/패턴 | 판정 | 근거 | 후속 액션 |
|------|------|------|-----------|
| `.pytest_cache/` | 삭제 | 테스트 실행 부산물이며 repo truth가 아니다. | cleanup script/probe로 정리 |
| `**/__pycache__/` | 삭제 | Python 런타임 캐시이며 repo truth가 아니다. | cleanup script/probe로 정리 |
| `tests/harness/load/results/` | 삭제 | load harness 결과 폴더이며 source contract가 아니다. | 결과는 repo 밖 또는 ignore 유지 |
| `docs/harness/runtime/.post_task_qc_debounce.json` | 삭제 | hook runtime idempotency/debounce state이며 세션 산출물이다. | cleanup 대상 유지 |
| `docs/harness/runtime/.session_stop_idempotency.json` | 삭제 | hook runtime state 파일이다. | cleanup 대상 유지 |
| `docs/harness/logs/.hook_raw_once`, `HOOK_RAW_DUMP.txt`, `HOOK_PAYLOAD_DEBUG.jsonl`, `HOOK_RUNTIME_LOG.txt` | 삭제 | raw hook debug/log 산출물이며 `DECISIONS.md`에서도 cleanup 허용 범주다. | raw/debug output으로 유지, repo truth로 취급 금지 |

## B. 보관-재분류 후보
| 경로/그룹 | 판정 | 근거 | 권장 방향 |
|------|------|------|-----------|
| `docs/context/2026-04-16-project-delta-analysis-eb01c5d7-to-4c3aaffb.md` | 보관-재분류 | 참조 0건, `ARCHIVE_INDEX` 미등재, one-off 분석 메모 성격이 강하다. | `docs/context/analysis/` 하위로 이동해 archive-class로 명시하거나 삭제 여부를 별도 결재 |
| `docs/context/COMPACT_CHECKPOINT.md` + `docs/harness/runtime/COMPACT_CHECKPOINT.md` | 보관-재분류 | 둘 다 참조가 남아 있고 역할도 다르다. 지금은 "context handoff"와 "runtime checkpoint"가 공존한다. | canonical owner를 하나로 고정하고 나머지는 historical alias 또는 retire |
| `docs/plans/` 내 low-ref 미인덱스 조기 계획 문서군 | 보관-재분류 | early-March 계획 문서 중 ref가 낮고 `ARCHIVE_INDEX` 미등재인 파일이 다수 있다. | `living / archived / disposable` 3분류 후 archive bucket 정리 |
| `.cursor/skills/**`, `.agents/skills/gstack/**` | 보관-재분류 | repo 표면적의 가장 큰 비제품 비중이지만, 실제 도구 체인과 연결돼 있어 blind delete 불가 | vendored skill retention policy 또는 external mirror 정책 필요 |
| `backups/**` | 보관-재분류 | 역사 보존 가치는 있으나 repo 시각적 복잡도를 크게 늘린다. | 보존 정책/외부 저장소 이전 여부를 별도 결정 |
| `docs/context/manual-artifacts/**` | 보관-재분류 | manual artifact bucket이며 active source는 아니지만 historical reference 가능성이 있다. | archive-only 선언 또는 외부 문서 저장소 이전 검토 |

## C. 유지 보호 후보
| 경로/그룹 | 판정 | 근거 |
|------|------|------|
| `docs/AI_STATUS.md`, `docs/AI_CHANGELOG.md`, `docs/harness/runtime/SESSION_LOG.md`, `docs/harness/runtime/EDIT_LOG.md`, `docs/harness/runtime/COMPACT_CHECKPOINT.md` | 유지 | `docs/harness/policy/DECISIONS.md`가 context memory/runtime state로 유지 결정을 명시한다. |
| `tests/support/**/*.js` | 유지 | WDCalculator contract test가 실제로 모두 참조한다. 겉보기에 커 보여도 active fixture다. |
| `tests/domains/test_foms_namespace_imports.py` | 유지 | runtime namespace contract의 compatibility entrypoint다. |
| `tests/harness/load/last_trace_summary.json`, `tests/harness/load/last_trace_summary.txt` | 유지 | `foms_150_realistic.js`가 기본 output path로 실제 사용한다. |
| `tests/harness/load/session_cookies.example.txt` | 유지 | local cookie bootstrap 예시 템플릿이다. |
| `tests/harness/load/session_cookies.txt`, `tests/harness/load/loadtest_users.txt` | 유지-로컬 | ignored local operator input이며 blanket delete 대상이 아니다. repo truth는 아니지만 load harness는 실제로 사용한다. |
| `docs/context/wdcalculator-static-js-chunk-map.md` | 유지 | current FAG/PTC closeout 근거 문서로 active reference가 있다. |
| `docs/context/PTC_RUNTIME_COMMON_INVENTORY.md` | 유지 | low-ref이지만 current canonical-tree closeout 근거로 사용된다. |

## 테스트 관점 결론
- 지금 조사 범위에서 "즉시 삭제 가능한 tracked 테스트 파일"은 찾지 못했다.
- `tests/support/*.js` 54개는 collected contract 테스트가 직접 사용한다.
- 정리 우선순위는 테스트 삭제보다 `문서/로그/temp/result`와 `generator path correction`이 맞다.

## 우선순위 요약
1. `.claude/hooks/guard_shell.py`의 old-path 생성 경로 수정
2. tracked temp/result 파일 제거
3. workspace residue cleanup 자동화 유지
4. one-off 분석 문서 및 low-ref 계획 문서 archive policy 정리
5. vendored skills / backups / manual-artifacts는 별도 retention tranche로 분리
