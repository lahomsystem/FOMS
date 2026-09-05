# 정산탭 CFO 리뷰 — 멀티 에이전트 브리프 (2026-09-04)

> 워크플로 에이전트(CEO·워커 4·검증 4·비평 1)에게 건네는 **유일한 컨텍스트 원본**이다. 세션 히스토리는 붙이지 않는다.
> 리뷰 프롬프트 본문(역할·검사 축 A~H·출력 형식)은 같은 폴더의
> `2026-09-04-settlement-tab-cfo-review-prompt.md` 다. **먼저 그 파일을 끝까지 읽는다.**

## 0. 환경 (절대 규칙)

- 워크트리: `C:/tmp/foms-s-settle-cfo` · 브랜치 `session/settle-cfo` · base origin/deploy `7100e2aa1`.
  코드를 읽거나 pytest 를 돌릴 때는 **반드시 이 디렉토리**에서 한다(`cd C:/tmp/foms-s-settle-cfo && pwd && ...`).
  `C:/DEV/FOMS` 로 가지 말 것 — 다른 세션이 같은 탭을 편집 중이라 결과가 오염된다.
- 셸: bash. 파이썬 출력 인코딩: pytest·스크립트 앞에 `PYTHONIOENCODING=utf-8` 를 붙인다(cp949 가짜 red 방지).
- **읽기 전용 감사다.** 워크트리 파일 편집·git 명령(commit·stash·checkout 포함)·운영 쓰기·스테이징 데이터 생성 전부 금지.
  유일한 쓰기 대상은 산출물 폴더 `OUT` 이다.
- `OUT = C:/Users/USER/AppData/Local/Temp/claude/c--DEV-FOMS/558da516-4f75-426b-91eb-06c5f335e7f1/scratchpad/cfo`
  (이미 존재). 임시 스크립트·응답 JSON·스크린샷도 전부 여기.
- 응답(최종 텍스트·산출 파일)은 한글. 코드·명령·에러 문자열은 원문.
- 비밀번호·토큰·DB URL 원문을 산출물이나 최종 텍스트에 **절대 적지 않는다**.

## 1. 접속 자원

| 자원 | 위치·방법 | 규칙 |
|---|---|---|
| 스테이징 웹 | `https://lahom-dev.up.railway.app` | 조회·화면 확인 허용. [지금 동기화]·[받아오기] 버튼은 **누르지 않는다**(워커 큐를 점유하고 다른 세션 QA 를 방해) |
| 측정 계정 | `C:/Users/USER/.claude/projects/c--DEV-FOMS/secrets/claude_master.json` 의 `staging` 키(`base`·`password`·`user_id`), 사용자명은 최상위 `username` | ADMIN. 로그인은 `POST {base}/login` form(`username`·`password`), CSRF 불요, **desktop User-Agent 필수**, 성공 오라클 = 302. 2026-09-04 확인: 302·strip API 200 |
| 스테이징 DB | `OUT/staging_db_url.txt` (PostgreSQL URL 한 줄) | **SELECT 만.** SQLAlchemy 로 `create_engine(url).connect().execution_options(postgresql_readonly=True)` 를 쓴다. 쓰기 SQL 은 어떤 이유로도 금지 |
| 운영 DB | `OUT/production_db_url.txt` | **W2(축 B)·W3(축 D) 만, 각자 읽기 전용 1회 배치.** 같은 `postgresql_readonly=True`. 결과는 숫자만 기록. 운영 웹 화면 조작·로그인 금지 |
| 헤드리스 브라우저 | `B="$HOME/.claude/skills/gstack/browse/dist/browse"` → `$B goto URL` · `$B snapshot -i` · `$B fill @eN "값"` · `$B click @eN` · `$B text` · `$B console` · `$B network` · `$B screenshot OUT/x.png` · `$B viewport 1440x900` · `$B js "..."` | 2026-09-04 로그인 페이지 도달 확인. 로그인 뒤 `/erp/settlement` 진입, 채널 탭은 탭 버튼 클릭. 매 화면마다 `console`·`network` 를 같이 본다 |
| 워커 컨테이너 프로브 | 필요 시만. 격리 폴더 `C:/tmp/foms-dev-link`(FOMS-DEV 링크 완료)에서 `railway ssh -s worker -- echo B64 \| base64 -d \| python -` | 이번 감사에서는 원칙적으로 불필요. 쓰면 읽기 전용 프로브만 |

스테이징 현황(2026-09-04 strip API): `coverage_from 2025-10-01`, `coverage_to 2026-09-18`, `last_ok_at 2026-09-03T20:38:53`, `rev 14`, `rolling_days 30`, `vat_available_to 2026-08-31`, `status OK`, `stale false`.

## 2. 워커 4명 — 축 배정과 산출물 소유권

| 워커 | 축 | 산출 파일(이 워커만 쓴다) | 전용 도구·데이터 |
|---|---|---|---|
| W1 정확성·기간귀속 | A(3중 대사)·C(축·월말 경계) | `OUT/findings_w1.md`, `OUT/w1_*.json` | 스테이징 API·CSV·스테이징 DB |
| W2 완전성·운영 | B(빠진 날·보류 해제 짝·창 경계)·F(동기화 신선도·실패 경로) | `OUT/findings_w2.md`, `OUT/w2_*` | 스테이징 DB + **운영 DB 읽기 1회**(월별 분포·날짜 구멍·보류 짝), `settle_sync.py` 코드 독해 |
| W3 존재·통제 | D(미매칭 채권 금액)·E(권한·감사·마스킹·쓰기 경로·비번 로테이션) | `OUT/findings_w3.md`, `OUT/w3_*` | 스테이징 API(권한별 403 표는 계정이 하나뿐이므로 **코드 경로 + 테스트 계약**으로 판정하고 실측은 claude_master 1건), **운영 DB 읽기 1회**(미매칭 금액·aging), 감사 로그 테이블 |
| W4 표시·부채 | G(라벨·CSV·150%·다크)·H(성능·EXPLAIN·부채·핀 사슬) + **pytest 스위트 1회** | `OUT/findings_w4.md`, `OUT/w4_*`, 스크린샷 `OUT/w4_*.png` | gstack browse, `EXPLAIN` 은 스테이징 DB, `PYTHONIOENCODING=utf-8 python -m pytest tests/domains -k settlement -q -p no:cacheprovider`(워크트리에서, 결과 첫·끝 줄 기록) |

- 워커는 자기 산출 파일만 쓴다. 다른 워커 파일을 읽어도 되지만 고치지 않는다.
- **findings 파일은 축 하나 끝날 때마다 즉시 갱신**한다(중간에 죽어도 남게). 최종 반환 전에 파일이 완성돼 있어야 한다.
- 각 발견에는 반드시 `근거` 가 붙는다: `파일:라인` / 재현 명령 / 실측 숫자(응답 JSON 경로) 중 하나 이상. 화면 결함은 스크린샷 경로.
- **음성 대조군**: "누락 없음"·"부호 정상"·"403 정상" 류 주장에는 반대 표본(있어야 할 것이 있고, 없어야 할 것이 없음)을 같이 적는다.

## 3. 검증자 4명(워커별 1:1) — 반박 임무

- 입력: 해당 워커의 `findings_wN.md`. 출력: `OUT/verify_wN.md` (이 파일만 쓴다).
- 심각도 FAIL·WARN 발견 **전건**을 하나씩 **반박하려고** 시도한다: 재현 명령을 다시 돌리고, SQL 을 다시 던지고, 코드 라인을 다시 읽는다. 판정은 CONFIRMED / REFUTED / UNVERIFIABLE + 근거.
- 워커가 "PASS" 라고 한 축도 표본 하나씩 골라 정말 PASS 인지 찔러본다(거짓 초록 검사).
- 워커의 재무 영향 금액이 실측인지 추정인지 구분해 적는다.
- 편집·쓰기 규칙은 워커와 동일(읽기 전용, 운영 DB 는 W2·W3 검증자만 1회).

## 4. 비평자 1명 — 빠진 것 찾기

- 입력: 프롬프트의 축 A~H 검사 항목 전부 vs `findings_w*.md`·`verify_w*.md`. 출력: `OUT/critic.md`.
- 항목별로 "수행됨 / 근거 약함 / 미수행" 을 표로. 미수행 항목 중 30분 안에 스스로 확인할 수 있는 것은 직접 확인해 결과를 적는다(같은 규칙).

## 5. CEO — 설계와 최종 판정

- **설계 단계**: 프롬프트·브리프를 읽고 워커 4명에게 줄 **구체 검사 목록**(SQL 초안·API 호출 조합·음성 대조군·통과 기준·예상 함정)을 워커별로 작성한다. 이름·파일 경로·축 배정은 이 브리프대로 고정. 워커가 서로의 결과에 의존하지 않도록 자른다.
- **판정 단계**: `findings_w*.md`·`verify_w*.md`·`critic.md` 를 전부 읽고, 프롬프트 "출력 형식" 7항목 그대로 **`OUT/settlement_cfo_review.md`** 를 쓴다. REFUTED 된 발견은 결함 목록에서 빼고 NOT-A-DEFECT 로 옮긴다. UNVERIFIABLE 은 "확인 못 한 항목" 으로. 재무 영향은 실측/추정을 구분해 적는다. 한 줄 결론은 "9월 마감 가능 여부" 로 시작한다.

## 6. 알려진 함정 (조사 시간 아끼기)

- `get_today_kst()` 는 `date` 를 반환한다(`.date()` 호출 금지). naive timestamp 는 UTC 규약(`now_utc_naive`).
- 정산 게이트는 ADMIN 또는 team=ACCOUNTING(MANAGER/STAFF). `MANAGER` role override 를 우회하려고 `Policy.gate="module:function"` 필드를 신설한 상태 — 엔진·핸들러·`policy_can` UI 가 같은 답을 내야 한다.
- 회계팀은 CS 동등 업무 권한(`team_has_capability`, alias `ACCOUNTING→CS`). 팀 문자열 직접 비교 게이트가 있으면 회계팀만 조용히 403.
- `naver_settle_sync_runs` 의 RUNNING 잔류(운영 10·11, 스테이징 8)는 결정된 사항 — 재보고 금지. 단 "잘린 백필이 남긴 빈 구간이 배너로 안 잡힌다"는 별개 축(B-4)이다.
- 감사 로그의 두 번째 위치 인자가 행위자. 정산 export 로그가 행위자를 남기는지 코드로 확인(`_log_export`).
- `X-FOMS-ERP-SHELL` 헤더 없이 `/erp/settlement` 를 부르면 전체 페이지가 온다(프래그먼트 측정은 헤더 필수).
- CSV 는 `EXPORT_KINDS`(5종)+`SHEET_KINDS`(시트) 두 레지스트리. `test_every_model_column_is_exported` 가 모델 컬럼 소진을 강제한다.
- 워커 프로세스는 `app.py` 를 import 하지 않아 세션 훅(캐시 무효화·버전 카운터)이 없다.
- `.alert` 는 5초 뒤 자동으로 닫힌다 — 화면의 안내 문구를 볼 땐 로드 직후 `text` 를 찍는다.
- 스테이징 셸 프리페치 `ERR_ABORTED`·`mobile-push.js` mobile-state fetch 중단은 정산 무관 잡음(이전 QA 에서 확인). 결함으로 올리지 말 것.

## 7. 반환 계약(StructuredOutput)

워커·검증자·비평자·CEO 모두 최종 텍스트 대신 스키마대로 반환한다(워크플로가 강제). 스키마는 워크플로 스크립트에 있다.
반환 전에 자기 산출 파일이 디스크에 있어야 한다 — 파일이 없으면 총괄이 결과를 폐기한다.
