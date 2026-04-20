# Wave 1 Batch W1-B2 — Ambiguous top-level `src/` + deploy 텍스트 분류
> batch ID: **W1-B2**  
> risk axis: **filesystem taxonomy / classification (문서 + 최소 README)**  
> 실행일: 2026-04-13

## 1. 요약
- 루트 `src/`를 **non-product track / tooling-adjacent**로 고정했다. Flask canonical tree와 혼동되지 않도록 `src/README.md`를 추가했다.
- `runtime.txt` 내용(`python-3.11.9`)은 저장소 내 **코드 참조가 없고**, Heroku/Railway 관례적 **런타임 힌트**로 본다. Wave 1에서는 **루트 유지·위치 freeze** (이동 없음).

## 2. `runtime.txt` 소비자 확인
| 검사 | 결과 |
|------|------|
| `Dockerfile`, `railway.toml`, `Procfile`, `start.sh` 문자열 검색 | `runtime.txt` 직접 참조 **없음** |
| ripgrep repo | 계획/run record 외 **참조 없음** |
| 판정 | **문서화된 힌트 파일**로 유지. `.python-version`과 목적이 겹칠 수 있으나 삭제/이동은 소비자 불명확으로 Wave 1에서 하지 않음. |

## 3. `src/` 분류 근거
- 파일 확장자·구조가 **React Native/TS 클라이언트** (`AppNavigator.tsx`, `screens/*`, `db/*.ts`).
- Flask 앱 본체와 디렉터리 공유 없음.

## 4. Decision: delete / merge / extend / add
- **add:** `src/README.md` (필수 최소 entrypoint)
- **extend:** Wave 1 taxonomy 문서와 정합

## 5. Direction Lock (요약)
- 단일 risk axis: 분류·문서만, 코드 이동 없음.

## 6. 검증
| 검사 | 결과 |
|------|------|
| docs-only + `src/README.md` | 예 |
| product tree로의 오해 소지 | README로 감소 |

## 7. Stop condition
- **미발동.**

## 8. 산출물
- `docs/plans/2026-04-13-wave1-batch2-src-classification-run-record.md`
- `src/README.md`
