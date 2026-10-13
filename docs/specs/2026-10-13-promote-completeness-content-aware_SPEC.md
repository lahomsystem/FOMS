# 승격 완전성 검사: 파일 내용 기준 판정 (SPEC)

- 날짜: 2026-10-13
- 대상: `tools/harness/promote_completeness.py`, `tools/harness/promote_own_to_production.py`
- 등급: 하네스 코어 변경 → 승인 후 구현

## 1. 문제

production 승격 때마다 완전성 검사가 "의존 커밋 N개 누락"(INCOMPLETE, exit 2)을 낸다. 실제로는 그 내용이 이미 production 에 들어가 있다. 그러면 세션은 사용자에게 "같이 올릴까요?"를 묻고, 사용자는 맥락 없이 수십 개짜리 목록을 받는다.

실제 사례(2026-10-13, deploy `ff9b265b7` 프리셋 위치 수정):

- 검사 결과: 의존 6개 누락. 그 6개를 넣으면 다시 44개 누락.
- 실제 상태: production 의 `static/js/drawing/wizard.js` 는 `ff9b265b7~1` 과 diff 0이었다. 실제로 다른 곳은 `templates/drawing/wizard.html` 등 3파일의 자산 핀 한 줄(`?v=20261012r` 와 `?v=20261012d`)뿐이었다.
- cherry-pick 은 그 핀 줄에서만 충돌했다.

## 2. 근본 원인

현재 알고리즘(모듈 docstring 3단계)은 `git cherry` patch-id 만으로 "production 에 이미 있음"을 판정한다. production 에 들어가는 경로는 여러 가지다.

- 여러 커밋을 묶은 promo PR
- 충돌을 해결한 cherry-pick
- tree 를 맞추는 병합 승격(메모리 `project_deploy_production_tree_identical_merge`)
- 자산 핀만 다르게 올린 PR

이 경로로 들어가면 patch-id 가 원본 커밋과 달라진다. 그래서 내용은 같아도 `+`(누락)로 분류된다. SHA·patch-id 는 "그 패치가 그대로 들어갔는가"를 묻고, 승격이 실제로 알아야 하는 것은 "대상 파일의 바탕이 같은가"이다.

## 3. 변경

### 3.1 파일 단위 바탕 비교 (새 1차 판정)

pending 승격 SHA 마다, 그 SHA 가 건드린 파일 F 각각에 대해 두 blob 을 비교한다.

- `base_ref:F`
- `<가장 오래된 pending SHA>~1:F` (deploy 에서 승격 직전 바탕)

파일마다 다음 셋 중 하나로 분류한다.

| 분류 | 조건 | 의미 |
|---|---|---|
| `same` | blob 해시 동일 | 바탕이 같다. 이 파일 때문에 누락으로 칠 커밋은 없다 |
| `pin_only` | 다른 줄이 모두 자산 핀(`?v=<토큰>`) 차이 | 바탕은 같고 핀만 다르다 |
| `differs` | 그 밖 | 실제 내용이 다르다 |

파일이 한쪽에만 있는 경우(추가·삭제)는 `differs` 로 둔다.

### 3.2 누락 후보 축소

- 기존 patch-id 후보 탐색(`_file_range_shas` + `git cherry`)은 `differs` 파일에만 돌린다.
- `same`·`pin_only` 파일을 건드린 후보 커밋은 `already_equivalent` 로 옮기고, 사유 `content_same` 을 붙인다.
- 그 결과 `missing` 은 내용이 실제로 다른 파일에 걸린 커밋만 담는다.

### 3.3 판정과 exit 코드

- 모든 파일이 `same`/`pin_only` 이면 complete(exit 0).
- `differs` 가 있으면 지금처럼 그 파일 기준 missing 목록을 내고 incomplete(exit 2).
- exit 코드의 뜻(0/1/2)은 바꾸지 않는다. 호출자 호환을 지킨다.

### 3.4 핀 충돌 자동 처리 (`promote_own_to_production.py`)

- cherry-pick 충돌 파일이 모두 3.1 에서 `pin_only` 였다면 자동으로 해결한다.
  - 충돌 hunk 의 핀 토큰을 `max(production 토큰, 승격 커밋 토큰)` 으로 정한다. 핀은 날짜와 접미사 문자열이라 사전순 최대가 최신이다.
  - 그 뒤 `cherry-pick --continue` 를 실행한다.
- 핀이 아닌 줄이 하나라도 충돌하면 지금처럼 exit 3 으로 끝내고 worktree 를 보존한다. "충돌 = 타 세션 의존 신호, 임의 해결 금지" 규칙은 그대로이고, 핀 줄만 예외로 둔다.
- 핀 패턴과 함께 움직여야 하는 테스트 단언(예: `tests/domains/test_drawing_wizard_autosave_guard.py:135` 의 `?v=` 문자열)도 같은 규칙으로 처리한다.

### 3.5 출력 형식

맨 첫 줄에 판정 한 줄을 내고, 상세는 그 아래에 둔다.

```
판정: 올려도 됨 — 대상 4파일 중 바탕 같음 1 · 핀만 다름 3 · 내용 다름 0
```

```
판정: 진짜 누락 2개 — 내용 다른 파일: foms/x.py
  + a673bc88 feat(partner): …  (foms/x.py)
  ...
```

`--json` 출력에는 파일 분류 `files_status: {path: same|pin_only|differs}` 를 더한다. 기존 키는 유지한다.

## 4. 범위 밖

- deploy 전체 merge 승격 경로("전체 푸쉬")
- `session_commit_ledger` 의 세션 SHA 수집 방식
- CLAUDE.md 문구. 판정은 도구가 하고, 문장 규칙은 추가하지 않는다.

## 5. 검증

- `tests/harness/test_promote_completeness.py` 에 임시 git 저장소 픽스처로 4가지 경우를 추가한다.
  1. 의존 커밋을 squash 해 다른 patch-id 로 production 에 반영 → complete(0), `content_same`
  2. 핀 줄만 다름 → complete(0), `pin_only`
  3. 실제 내용 다름 → incomplete(2), missing 이 그 파일 커밋만 담는다
  4. 파일 추가·삭제 → `differs`
- `tests/harness/test_promote_own_to_production.py` 에 2가지 경우를 추가한다.
  1. 핀 충돌만 있음 → 자동 해결, max 토큰
  2. 핀이 아닌 줄의 충돌 → exit 3, worktree 보존
- 회귀 재현: 2026-10-13 사례를 `--base-ref 56653699 --shas ff9b265b7` 로 다시 돌려 complete 와 "핀만 다름 3"이 나오는지 확인한다.
- 실행 명령: `python -m pytest -q tests/harness/test_promote_completeness.py tests/harness/test_promote_own_to_production.py` 와 `pre_push_smoke.ps1` exit 0.

## 6. 위험

- `same` 판정은 "파일 내용이 같다"이지 "동작이 같다"가 아니다. 다른 파일에 숨은 의존(예: JS 가 부르는 새 API)은 이전처럼 잡지 못한다. 이건 지금 patch-id 방식에도 없는 보장이다.
- 핀 자동 해결이 잘못된 토큰을 고르면 기기 캐시가 늦게 갱신될 뿐 기능 오류는 아니다. max 규칙으로 되돌아가는 일은 막는다.
