# FOMS Phase 1 Baseline Matrix
> 작성일: 2026-04-07
> 상태: 실행 문서
> 목적: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`의 Step 1을 실제 작업 순서와 증빙 기준으로 고정한다.
> 최신 실행 기록: `docs/plans/2026-04-07-phase1-baseline-run-record.md`

## 1. 원칙
- 이 문서는 구조 개편 착수 전 baseline을 고정하는 실행 체크리스트다.
- 이 문서의 완료 기준을 통과하기 전에는 `Step 2: 루트 hygiene 정리`에 착수하지 않는다.
- baseline은 "현재 구조에서 재현 가능한 정상 상태"를 뜻한다.
- staging 검증은 필수지만 단독 기준이 아니다. 로컬 baseline과 staging smoke를 함께 본다.
- 로컬 Windows 환경에서는 `gunicorn`의 Unix 의존성(`fcntl`) 때문에 production web 부팅 경로를 100% 재현할 수 없으므로, web/worker 최종 신뢰 기준은 staging smoke로 보완한다.

## 2. 실행 순서
1. baseline 대상 계약을 잠근다.
2. 로컬 공통 baseline을 수집한다.
3. web smoke checklist를 수행한다.
4. worker smoke checklist를 수행한다.
5. staging smoke checklist를 수행한다.
6. Go / No-Go를 기록한다.
7. Go일 때만 `Step 2: 루트 hygiene 정리`로 넘어간다.

## 3. Baseline Lock 대상
다음 계약은 Phase 1 동안 변경하지 않는다.

- `app:app`
- `start.sh`
- `Procfile`
- `railway.toml`
- `Dockerfile`
- `alembic.ini`
- `migrations/`
- `db.py`
- `models.py`
- `wdcalculator_db.py`
- `wdcalculator_models.py`
- `templates/`
- `static/`
- `.cursor/hooks.json`
- `tools/harness/*`
- `tests/harness/*`
- `docs/harness/bundles/HARNESS_BUNDLE_*.md`

## 4. Phase 1 Baseline Matrix
| 영역 | 확인 항목 | 실행 방법 / 증빙 | 기대 결과 | 실패 시 조치 |
|------|-----------|------------------|-----------|--------------|
| 공통 | import baseline | `python -c "import app; print('APP_OK')"` | `APP_OK` 출력 | 구조 개편 착수 금지 |
| 공통 | harness baseline | `python tools/harness/verify_result.py --json` | 종료코드 0, 주요 기준 통과 | 구조 개편 착수 금지 |
| 공통 | 테스트 baseline | `python -m pytest -q` 또는 승인된 subset | 승인된 범위 green | 실패 원인 분리 전 착수 금지 |
| 공통 | git cleanliness baseline | `git status --short` 기록 | 기존 dirty 상태를 인지하고 신규 오염 없음 | 신규 생성물 정리 |
| web | staging 로그인 진입 | 브라우저로 staging 접속 | 로그인 페이지 정상 렌더링 | web smoke 실패로 기록 |
| web | 정적 자산 로딩 | 네트워크 탭/브라우저 로그 확인 | 주요 CSS/JS 200, 치명 오류 없음 | 원인 분석 후 Stop |
| web | 핵심 공개 UI | 로그인 화면, 경고 배너, 버튼/입력창 노출 확인 | 기본 UI usable | 원인 분석 후 Stop |
| worker | worker 기동 계약 | Railway worker 서비스 설정/로그 확인 | worker 프로세스가 정상 기동 | worker smoke 실패로 기록 |
| worker | Redis/env parity | worker가 필요한 env 주입 여부 확인 | web/worker 필수 env parity 확인 | env drift 수정 전 Stop |
| staging | web runtime 계약 | staging에서 실제 접근 확인 | 운영과 유사한 경로에서 정상 응답 | Step 2 진입 금지 |
| staging | post-change smoke 재사용성 | 본 문서를 재실행 가능한지 확인 | 같은 체크리스트로 반복 검증 가능 | 문서 보정 후 재시도 |

## 5. 로컬 Baseline 체크리스트
### 5.1 필수 명령
PowerShell 기준:

```powershell
python -c "import app; print('APP_OK')"
python tools/harness/verify_result.py --json
python -m pytest -q
git status --short
```

### 5.2 기록할 것
- 실행 시각
- 성공/실패 여부
- 실패 시 에러 전문
- 현재 브랜치
- 재현 조건

### 5.3 판정 규칙
- `APP_OK` 실패 시 즉시 No-Go
- `verify_result.py --json` 실패 시 즉시 No-Go
- 테스트 실패가 기존 알려진 실패인지, 신규 실패인지 구분되지 않으면 No-Go

## 6. Web Smoke Checklist
### 6.1 목적
- 구조 개편 전후에 web 경로가 최소한 동일하게 살아 있는지 본다.
- 로컬이 아니라 staging 결과를 최종 신뢰 기준으로 삼는다.

### 6.2 최소 체크
- [ ] staging URL 진입 시 응답이 온다.
- [ ] 로그인 페이지로 리다이렉트 또는 진입이 정상이다.
- [ ] 로그인 폼의 ID/비밀번호 입력창이 렌더링된다.
- [ ] 로그인 버튼이 활성 상태다.
- [ ] 콘솔에 치명적인 JS 에러가 없다.
- [ ] 주요 정적 자산(CSS/JS)이 200으로 내려온다.

### 6.3 선택 체크
테스트 계정이 있을 때만 수행:
- [ ] 로그인 성공 후 첫 landing page 진입
- [ ] 대시보드 또는 주문 메인 화면 진입
- [ ] 주문 상세 진입
- [ ] 첨부/업로드 UI 노출
- [ ] 상태 변경 또는 저장 동작 1건

## 7. Worker Smoke Checklist
### 7.1 목적
- 구조 개편이 worker 진입 계약과 env parity를 깨지 않는지 확인한다.

### 7.2 최소 체크
- [ ] Railway에 worker 서비스가 존재한다.
- [ ] worker 시작 명령이 현재 계약과 일치한다.
- [ ] `USE_RQ_WORKER=1` 또는 동등 계약이 유지된다.
- [ ] `REDIS_URL`이 worker에 주입된다.
- [ ] worker 부팅 로그에 즉시 치명 오류가 없다.

### 7.3 가능하면 추가 체크
- [ ] 큐 대기 작업 1건 처리 확인
- [ ] 실패 작업이 있으면 기존 이슈인지 신규 이슈인지 분리

## 8. Staging Smoke Checklist
### 8.1 기준 환경
- URL: `https://lahom-dev.up.railway.app/`
- 목적: production과 가장 유사한 web runtime 검증

### 8.2 필수 체크
- [ ] staging 홈 또는 루트 접근 가능
- [ ] 인증이 필요한 경우 로그인 페이지로 정상 유도
- [ ] 첫 화면이 깨지지 않고 렌더링
- [ ] 브라우저 콘솔 치명 오류 없음
- [ ] 네트워크 상 주요 정적 자산 200 확인
- [ ] 구조 개편 전 baseline과 비교해 명백한 regression 없음

### 8.3 인증 후 체크
승인된 테스트 계정이 있을 때만:
- [ ] 로그인 성공
- [ ] 핵심 읽기 플로우 1개
- [ ] 핵심 쓰기 플로우 1개
- [ ] 업로드/다운로드 관련 핵심 플로우 1개
- [ ] 로그아웃 또는 세션 유지 정상

## 9. Go / No-Go 판정
### Go
다음을 모두 만족할 때만 Go:
- 로컬 공통 baseline 통과
- web smoke 필수 항목 통과
- worker smoke 필수 항목 통과 또는 "현재 worker 미사용"이 명시됨
- staging smoke 필수 항목 통과

### Conditional Go
다음을 만족하면 Conditional Go:
- 로컬 baseline 통과
- staging web smoke 통과
- worker는 현재 무관하거나 별도 환경 제약으로 즉시 검증 불가
- 단, Step 2는 "루트 hygiene만" 허용하고 boot/runtime 파일은 계속 동결

### No-Go
다음 중 하나라도 있으면 No-Go:
- `APP_OK` 실패
- `verify_result.py --json` 실패
- staging 첫 화면 또는 로그인 진입 실패
- worker 계약 불명확
- baseline 실패가 기존 이슈인지 신규 이슈인지 분리 불가

## 10. Step 2 진입 조건
아래가 모두 충족될 때만 `루트 hygiene 정리` 시작:
- [ ] 본 문서의 Go 또는 승인된 Conditional Go 판정
- [ ] 루트에서 제거할 대상 inventory 완료
- [ ] 제거 대상이 import/runtime/deploy에서 참조되지 않음 확인
- [ ] boot-critical / persistence / harness 경로는 계속 untouched

## 11. Step 2에서 허용되는 것
- 로그/덤프/스크래치/비교 산출물 정리
- README와 inventory성 문서 보정
- git tracked local/generated 파일 정리

## 12. Step 2에서 금지되는 것
- `app.py` 경로/내용 리팩터
- `start.sh`, `Procfile`, `railway.toml`, `Dockerfile` 수정
- `db.py`, `models.py`, `wdcalculator_*` 수정
- `tools/harness/*`, `.cursor/hooks.json`, `tests/harness/*` 수정
- `templates/`, `static/`, `migrations/` 이동

## 13. 실행 기록 템플릿
```markdown
# Phase 1 Run Record
- 일시:
- 브랜치:
- 실행자:
- staging URL:

## Local Baseline
- APP_OK:
- verify_result:
- pytest:
- git status:

## Web Smoke
- 결과:
- 비고:

## Worker Smoke
- 결과:
- 비고:

## Staging Smoke
- 결과:
- 비고:

## Verdict
- Go / Conditional Go / No-Go:
- 근거:
- 다음 단계:
```
