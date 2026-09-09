# FOMS 시스템 전체 개발 검토 프롬프트 — 진행 원장 (2026-09-06)

> 총괄 세션이 쓴다. 워크플로 결과·검증 출력·판정을 기록한다. 브리프: `docs/plans/2026-09-06-foms-system-review-brief.md` · 산출물: `docs/plans/2026-09-06-foms-system-review-prompt.md`

## 실행 정보
- 브랜치 `deploy` · 시작 HEAD `094682d57`(워커 시점 `c38ae6225`, 통합·마감 시점 `58275b7e5` — 타 세션 커밋으로 이동) · 워킹트리 `C:/DEV/FOMS`(읽기 전용 워크플로라 격리 워크트리 미사용)
- Workflow run `wf_fa95e552-808` · 저널 `subagents/workflows/wf_fa95e552-808/journal.jsonl` · 에이전트 15명 기동, 13명 완료, 2명 실패(세션 사용 한도)
- 실측: 88분 · 서브에이전트 토큰 약 306만 · 도구 호출 510회
- 구조: CEO 설계(1) → 차원 워커 8 병렬 → 통합자(1) → 리뷰어 2(스펙/품질) → CEO 판정(1) → [fix 라운드 통합자(1) + 재판정(1) = 세션 한도로 실패 → 총괄이 직접 반영]

## 단계 상태
| 단계 | 상태 | 비고 |
|---|---|---|
| 브리프 작성 | DONE | 사실 카드 §2 는 총괄이 직접 잼. 자체 앵커 검사 ANCHOR_BAD 0 · HANJA 0 |
| CEO 설계 | DONE | 차원 8개 확정(질문 5·앵커 12~16·명령 6·함정 5), 리뷰 기준 스펙 9·품질 9 |
| 차원 감사 D1~D8 | DONE | 8/8 회수. 판정 전부 **조건부**. 리스크 5~6·결핍 5~6·필요 5·사소 12~15 씩 |
| 통합(프롬프트 작성) | DONE | 332줄(긴 줄) · 백틱 앵커 303개 검사 0 실패 · 한자 0 |
| 리뷰 2판정 | DONE | 스펙 = fix(높음 1·중간 1·낮음 4) · 품질 = ship(중간 1·낮음 7, 앵커 221곳 대조 0 불일치·명령 30개 실행) |
| CEO 판정 | DONE | 1차 = fix 4건(3축 문장·⑥ 문항 / §5 태그 / 수치 셈법 / lacking 스키마) |
| fix 라운드 | DONE(총괄 직접) | 워크플로 fix 통합자·재판정이 "session limit · resets 5am" 으로 실패 → 총괄이 파이썬 치환 스크립트로 fix 4건 + 낮음 항목 전부 반영 |
| 총괄 무신뢰 검증 | DONE | 아래 기록 |
| 실행 준비(ready to go) | DONE | 프롬프트 §0.1 복붙용 시작 프롬프트 + Workflow 스크립트 `docs/plans/2026-09-06-foms-system-review-workflow.js`(`node --check` 통과) |
| 커밋 | DONE | 로컬 커밋(deploy, 푸시 안 함) — 브리프·프롬프트·워크플로 스크립트·원장 4파일 pathspec |

## 새 세션 실행(ready to go)
- 시작 프롬프트: 프롬프트 문서 §0.1 의 코드 블록을 새 세션 첫 메시지로 붙인다.
- 실행 스크립트: `docs/plans/2026-09-06-foms-system-review-workflow.js` — 프롬프트 §7 의 단계(CEO 1 → 워커 8 병렬 → 통합 1 → 리뷰 2 → CEO 판정, fix 1회)를 Workflow 도구용으로 옮김. 워커 스키마는 §7.3(`prior_observations` 포함), 통합자만 보고서·원장 2파일 쓰기.
- 예상 규모: 이번 프롬프트 제작 워크플로 실측 기준 에이전트 13~15명·약 90분·서브에이전트 토큰 약 300만. 사용 한도가 새벽 5시(Asia/Seoul)에 풀리므로 그 뒤 시작.
- 산출물: `docs/plans/2026-09-06-foms-system-review-report.md` + `docs/plans/2026-09-06-foms-system-review-report-ledger.md`. 완료 기준은 프롬프트 §8.

## 반영한 수정 (CEO fix 4 + 리뷰어 낮음)
1. §4 머리말에 3축 문장(부족한 것=`lacking` · 더 필요한 것=`needed` · 적합성=`verdict.fit`) + D1~D8 핵심 질문마다 ⑥ [더 필요한 것] 문항.
2. §5 관측 항목 44개 머리에 `[리스크|결핍|리스크+결핍 · 심각도 · 시점]` 태그(워커 JSON 값 복원, 병합 항목은 `리스크+결핍`) + 머리말에 태그 뜻·"초안은 실행 대상 아님" 문장.
3. 셈법 없는 수치에 명령 원문 병기 또는 "(셈법 미기재·재측정 필요)" 표기: 9,879건 47% · 19건 중 11건 · 보안 테스트 74 · 도달 불가 39/floating 20/권고 24 · 지연 import 473 · 200커밋 평균 4.5 · lazy 마이그레이션 114 · 핀 163/136(52파일 90곳으로 통일, 넓은 셈법 병기) · window 전역 467(214·273·749 는 재측정) · 메모리 164파일 4,610줄 · FOMS_ 25 vs 14 두 셈법.
4. §7.3 `lacking` 스키마를 `system_risks` 와 같은 필드로 명시 + `prior_observations`·`가설` 값 추가 사실 명기.
5. 사실 정정: ci.yml 트리거(push main/deploy + PR, production 은 PR 필터) · 수집 테스트 9,879(c38ae6225)→9,913(58275b7e5) · pip 명령 `||` 우선순위 · §7.1 스니펫 실행 시점 · D3 두 번째 항목 헤드라인을 시스템 수준으로.
6. 한국어 낱말 복원: split-brain·ratchet·opt-in·readiness·lease·expand-only·advisory·standalone → 한글 앞세우고 원어는 괄호 1회.
7. 길이 기준 추가(§6·§8: 600줄·한 줄 600자·100KB) + 긴 줄 펼치기(열린 질문 (a)~(l) 20항목, 명령 8차원 사슬, 부록 A 8차원, 더 필요한 것 ①~⑤ 40항목).

## 총괄 검증 기록
- 앵커 실존 스니펫(브리프 §6, 산출물에 실행): `ANCHOR_BAD 0` · `HANJA 0`.
- 구조: 섹션 10개(§0~§8 + 부록 A) · 줄 555(600 이하) · 최장 줄 896자 · 137,891 바이트 · ⑥ 문항 8 · 태그 44 · 하위 항목 ①~⑤ 40.
- 표본 앵커 직접 대조(11곳, 전부 일치): `foms/services/rate_limit.py:58-70`(swallow_errors·memory 폴백) · `start.sh` `&` 5줄(25·36·48·59·72) · `docs/AI_STATUS.md:68`(Railway Config as Code 폐기) · `app.py:24`(`_hash_internal` 몽키패치) · `foms/platform/blueprints.py:115`(Registration sequence frozen) · `tests/conftest.py:26-28`(PBKDF2 10회) · `foms/api/health.py:7-10`(순수 liveness) · `CLAUDE.md:48`(`apps/api/`) · `docs/ARCHIVE_INDEX.md:3` · `foms/persistence/main/models.py:3`(`from models import *`) · `.github/workflows/ci.yml:3-11`(production 은 pull_request 필터).
- 문서 읽는 계약 테스트: `tests/domains/test_docs_facing_registry.py` + `tests/contracts/runtime/test_ptc_physical_exactness.py` → `10 passed in 0.90s`.
- 저장소 변경: 신규 3파일(브리프·프롬프트·원장)만. 타 세션 미추적 파일(`.claude/skills/*`·`.env.bak-20260828`·`2026-09-04-as-legacy-stage-cleanup-plan.md`)은 손대지 않음.

## 워커 판정 요약(8/8 조건부)
| 차원 | 한 줄 |
|---|---|
| D1 스택·의존성 | 프레임워크 계열은 살아 있고 상향 차단 요소 4곳뿐이나 현재 핀이 패치 창 밖·잠금/분리/스캔/버전 정본 0 → 이번 분기 메이저 상향 패킷 + 거버넌스 층 |
| D2 아키텍처 | 네임스페이스·동결 계약은 살아 있으나 계층 방향 강제 0(services→web 8·api→web 53·models 직접 225파일), 분해 거버넌스 2026-04-15 정지 |
| D3 데이터 | JSONB 정본 + 사본 동기화를 사람이 하는 구조로 두 달 4번 사고; alembic 체인·감사·오프사이트 백업은 갖춤, RPO/RTO 숫자·복원 리허설 0 |
| D4 테스트·CI | CI 2분 안팎·초록(브리프 "14분+" 낡음), 47% 가 HTTP 실검증; CI 빨강 19건 중 11건 자가 유발, 보안 레인 0, 함정 지식이 저장소 밖 |
| D5 프론트 | 130k 줄 JS 를 계약 테스트·수동 날짜 핀·SW 캐시로 버팀; 9일 4번 같은 핀 사고, 셸 3벌 게이트 행렬, 커밋 22.6% 가 핀을 건드림 |
| D6 보안 | 쓰기 권한 SSOT·고급 통제는 실재, 읽기 최소권한·CVE 스캔·CSP·로그인 잠금·PII 정책 0, 레이트리미터 무로그 fail-open |
| D7 운영 | 워커 1대 무감독 루프 5개·경보 경로 0·배포 정본이 저장소 밖(toml 사문)·롤백 문서/훈련 0 |
| D8 개발 시스템 | 하네스는 실제로 막고 있음(셸 가드 deny 70/주) 그러나 정책 정본 4벌 드리프트(apps/)·색인 2026-06-17 정지·스킬 4종 미추적·온보딩 경로 0 |
