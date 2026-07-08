# 푸시 전 로컬 검증 (deploy/main)

`deploy` 또는 `main`에 **push하기 전**에 로컬에서 빠르게 돌리는 스모크 검증입니다. GitHub Actions 전체 CI를 대체하지 않습니다.

## UI 검증 정책 (모바일 ERP 활발 개발 단계)

**기본(푸시 전 필수):** PNG visual regression이 아니라 **구조 테스트**만 게이트로 사용합니다.

- `tests/visual/test_p1_mockup_structure.py` — 템플릿/매크로/셀렉터·워크플로우 계약
- `tests/visual/test_p1_mockup_png_baseline.py` — mockup ↔ 앱 클래스 parity (PNG 없음)
- `tests/visual/test_p1_mockup_chrome_parity.py` — Chrome 구조 parity

`pre_push_smoke.ps1` 기본 subset에 위 테스트가 포함됩니다. **템플릿/CSS 변경 시 `-Visual`·win32 PNG 커밋은 필수가 아닙니다.**

PNG 회귀(`-Visual`, win32 baseline 갱신)는 UI 안정기(릴리스 고정)에만 **선택**으로 사용합니다.

## Visual regression (선택, SSOT 참고)

UI가 안정된 뒤 전체 PNG 회귀가 필요할 때만:

1. **CSS/JS/템플릿 구현**
2. **win32 baseline 재생성** — `--update-snapshots` → `tests/visual/baseline/win32/*.png`
3. **win32 PNG 커밋**
4. **`pre_push_smoke.ps1 -Visual`** (선택)
5. **CI linux SSOT (선택)** — `workflow_dispatch`용 `.github/workflows/visual-baseline-linux.yml`만 수동 실행

> **주의:** Windows에서 `baseline/linux/` PNG를 재생성·커밋하지 마세요. Linux baseline은 CI SSOT입니다.

### win32 baseline 갱신 명령 (Win11)

```powershell
cd "C:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"
$env:TEMP = "C:\tmp"
$env:TMP = "C:\tmp"
$env:DATABASE_URL = "sqlite:///tests/visual/visual_local.sqlite"
python -m pytest tests/visual --update-snapshots -q
git add tests/visual/baseline/win32/*.png
```

갱신 후 diff PNG를 눈으로 확인한 뒤 커밋합니다.

### stale 감지 (근본 수정)

| 검사 | 스크립트 | 의미 |
|------|----------|------|
| win32 vs CSS 소스 | `python scripts/ops/visual_baseline_stale.py --check-win32-vs-sources` | visual 소스(`static/css/`, `static/js/`, `templates/`) 최신 커밋이 win32 PNG 커밋보다 **새로우면** stale — CSS만 바꾸고 PNG를 안 갱신한 경우를 잡음 |
| linux vs win32 (CI seed) | `python scripts/ops/visual_erp_linux_stale.py` | win32 ERP PNG를 커밋한 뒤 linux가 뒤처지면 CI seed 단계 실행 |
| pre-push 게이트 | `pre_push_smoke.ps1` (기본) | visual 경로 변경 시 **`test_p1_mockup_*` 구조 테스트**로 게이트 (PNG `-Visual` 필수 아님) |

## 언제 실행하나

- `deploy` / `main`으로 push 직전
- PR 머지 전 자신감 확인 (빠른 회귀 방지)
- CI에서 자주 깨지는 영역(배포 Dockerfile, import 계약, HTMX, visual asset) 변경 후
- **UI/CSS/레이아웃 변경 후**: 기본 subset만 (구조 테스트 `test_p1_mockup_*`). PNG `-Visual`은 선택

## 명령 (Win11 / PowerShell 5.x)

저장소 루트에서:

```powershell
powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1
```

PNG 전체 회귀가 필요할 때만 (선택):

```powershell
powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1 -Visual
```

### 머지 직전 전체 pytest (느림)

```powershell
powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1 -Full
```

`-Full`은 CI `test` job과 유사하게 `tests/visual` 제외 전체 pytest를 실행합니다. 수 분 이상 걸릴 수 있습니다.

### 로컬 visual regression (win32 baseline)

```powershell
powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1 -Visual
```

`-Visual`은 Playwright 기반 `tests/visual` 전체(PNG regression 포함)를 로컬에서 실행합니다. 약 30초~수 분.

- **선행조건**: `pip install playwright; python -m playwright install chromium`. 미설치 시 visual **FAIL**(silent skip 없음 — CSS 변경 게이트와 함께 사용 시).
- **env**: `TEMP/TMP=C:\tmp`, `DATABASE_URL=sqlite:///tests/visual/visual_local.sqlite`(live-server fixture가 파일 DB 공유)를 스크립트가 자동 설정.
- **visual DB**: `tests/visual/visual_local.sqlite`는 **git에 커밋하지 않음**(로컬 전용). `-Visual` 실행 시 스크립트가 기존 파일을 삭제한 뒤 pytest `visual_live_server` fixture가 스키마를 재생성합니다.

### visual DB 오류 복구 (login 실패 / UNIQUE / no such table: users)

증상: Playwright가 `/login?next=...`에 머무름, `IntegrityError`, `no such table: users`.

```powershell
cd "C:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"
Remove-Item -Force "tests\visual\visual_local.sqlite*" -ErrorAction SilentlyContinue
$env:TEMP = "C:\tmp"; $env:TMP = "C:\tmp"
$env:DATABASE_URL = "sqlite:///tests/visual/visual_local.sqlite"
python -m pytest tests/visual -q
```

OneDrive 잠금이 있으면 `TEMP`를 `C:\tmp`로 두고, 그래도 실패하면 레포를 OneDrive 밖 경로로 clone하거나 동기화 일시 중지 후 재시도합니다.
- **플랫폼 baseline**: 로컬은 `tests/visual/baseline/win32/`. CI `test` job은 Playwright PNG 회귀 없이 `test_p1_mockup_*` 구조 테스트만 실행합니다. linux SSOT refresh는 `visual-baseline-linux.yml` 수동 워크플로만 사용합니다.

`-Full -Visual`처럼 조합 가능합니다.

## 무엇을 검사하나

| 단계 | 설명 |
|------|------|
| Visual 게이트 | visual 경로 변경 감지 + win32 stale vs CSS 소스 → `-Visual` 필수 |
| 환경 | `DATABASE_URL=sqlite:///:memory:`, `SECRET_KEY=ci-secret-key`, `FLASK_ENV=testing` |
| APP import | `python -c "import app; print('APP_OK')"` |
| Harness | `tools/harness/verify_result.py --json` (있을 때) |
| Design SSOT | `tools/design/ssot_lint.py docs/design` (있을 때) |
| Pytest subset | Dockerfile 계약, namespace import, search overlay, HTMX fragment, staging mobile v2 / P1 mockup visual / P1 chrome parity (CSS 계약) |
| Visual regression (`-Visual`) | `tests/visual` Playwright PNG compare (win32 baseline) |

기본 subset 목표 시간: **약 2–5분**.

## 중요

- 이 스크립트는 **git push 시 자동 실행되지 않습니다.** 수동 실행입니다.
- Push 후 **GitHub Actions**가 전체 CI(visual regression 포함)를 계속 실행합니다.
- AI 에이전트에게 push마다 전체 테스트 suite 실행을 요청하지 마세요. **로컬에서 이 스크립트를 실행**하고, 실패 시에만 에이전트에게 수정을 요청하세요 (토큰·시간 절약).

## push 후: CI 감시·복구 게이트 (push 완료의 정의)

push 직후에는 **CI green 확인까지가 한 작업 단위**입니다. 아래를 실행해 GitHub Actions 완료를 감시합니다.

```powershell
python tools/harness/ci_watch.py
```

- 기본 대상은 **현재 HEAD · `deploy`** 브랜치입니다. production 승격 후에는 `python tools/harness/ci_watch.py HEAD production`.
- 종료 코드: **0**=전부 green / **1**=코드 실패(로그 분석 → 근본 수정 → `pre_push_smoke` → 재푸시) / **2**=자동 재실행 발동(기본 `--until-final` 모드가 내부 재폴링해 0·1로 수렴) / **3**=gh CLI 미설치·미인증(설치·`gh auth login` 후 재시도).
- 자동 복구: perf-gate **배포 대기 타임아웃**(healthz commit==SHA 확인 후 재실행), **TTFB/render tail flaky**(1회 재실행). **bytes 초과**는 데이터 가변 탭 가능성 때문에 예산 보정값을 *제안*만 하고 자동 상향하지 않습니다.
- 이 게이트는 3-도구 공통입니다: Claude Code는 `PostToolUse:Bash` 훅(`post_push_watch.py`), Cursor는 `afterShellExecution`+`afterAgentResponse` 훅이 push 감지 시 실행을 리마인드합니다. 로직 SSOT는 `tools/harness/ci_watch.py`이고 `scripts/ops/ci_watch_recover.sh`는 thin wrapper입니다.

## 실패 시

1. 스크립트 출력의 `[FAIL]` 단계 확인
2. win32 stale → 위 SSOT 워크플로 1–4단계 (`--update-snapshots`, PNG 커밋, `-Visual`)
3. 해당 pytest만 단독 실행: `python -m pytest -v tests/...`
4. 수정 후 스크립트 재실행 → exit 0 확인 후 push

## 관련

- CI 정의: `.github/workflows/ci.yml`
- Linux baseline runbook: `docs/runbooks/visual-regression-baselines.md`
- stale 정책 구현: `scripts/ops/visual_baseline_stale.py`
- 에이전트 요약: `AGENTS.md` § 푸시 전 로컬 검증
