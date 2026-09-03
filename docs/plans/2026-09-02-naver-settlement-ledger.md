# 네이버 정산 대시보드 — 진행 원장 (2026-09-02)

- 워크트리: `c:/tmp/foms-s-settle-naver` · 브랜치 `session/settle-naver` · base `origin/deploy` 416a3acfc
- 격리 사유: 타 세션이 같은 정산 탭(`session/settle-tabs`·`settle-perf`·`settle-dash`) 수정 중
- 리서치 산출물: `docs/research/2026-09-02-naver-settlement/`

## Phase R — 리서치 (병렬 5축 + CEO 3인 종합)
| ID | 축 | 산출물 | 상태 |
|---|---|---|---|
| R1 | 네이버 정산 API 5종 규격 | 01-naver-settle-api-spec.md | DONE |
| R2 | 기존 정산 대시보드 구조·탭 추가 레시피 | 02-dashboard-architecture.md | DONE |
| R3 | 네이버 클라이언트·워커 전용 제약·영속 패턴 | 03-naver-client-architecture.md | DONE |
| R4 | 회계팀 사용자 페르소나 | 04-persona-accounting-team.md | DONE |
| R5 | 회계 프로그램 설계 전문가 페르소나 | 05-persona-design-expert.md | DONE |
| C1~C3 | CEO 3인 독립 판정(별도 탭 vs 업그레이드 vs 하이브리드) | 06-ceo-{1,2,3}.md | DONE (3인 전원 C 하이브리드, 채널 중립 네임스페이스) |
| S | 종합 스펙 + 플랜 → 사용자 승인 | docs/specs/2026-09-02-naver-settlement_SPEC.md | 작성 완료, 승인 대기 |

## Phase I — 구현 (승인 2026-09-02: C 하이브리드·탭명 "네이버 정산"·백필 90일·열람 ADMIN+회계팀)
계약서: `docs/plans/2026-09-02-naver-settlement-contracts.md`
| ID | 내용 | 담당 | 완료 기준 | 상태 |
|---|---|---|---|---|
| A1 | 모델 6개 + 마이그레이션 naversettle_00 | agent | 왕복 upgrade/downgrade + 단일 head + import app | DONE (PG 745 passed, 왕복 드리프트 0) |
| A2 | client.py 정산 5메서드 + settle_enums.py + quota 속성 + 단위 테스트 | agent | tests/services/integrations/test_naver_settle_client.py green | DONE (79 passed) |
| A3 | 팀 ACCOUNTING + 정책 2종 + 게이트 + 탭 등록 4 hunk + 파셜 + 렌더 계약(기존 갱신·신규) | agent | 정산 렌더 스위트 3종 green | DONE (502 passed, 계약 갱신 3건: api teams 튜플·예정 스캔 채널 제외·분석 블록 경계) |
| A4 | channel.js + settlement-channel.css | agent | node --check + 렌더 계약 자산 검사 | DONE (360 passed, DOM 셰임 스모크 26/26; 비율 단위 B2 대조 필요) |
| B1 | settle_sync.py + 워터마크 + 큐/태스크/스크립트/start.sh/플래그 + 테스트 7종 | agent | test_naver_settle_sync.py green | DONE (33 passed; 첫 적재는 retro 미집계, enqueue 중복=False) |
| B2 | settlement_channel.py 커널 + /api/settlement/channel + sync POST(manifest·감사) + API 테스트 | agent | test_settlement_channel_api.py + auth enforcement green | DONE (138 passed; 워터폴 차감 3단계 표시 방향 -1 — 스테이징 실측으로 부호 확인 필요) |
| C1 | 통합: 정산 5스위트+신규+계약 전수, ci.yml 등재, smoke, 커밋 | 총괄 | 전부 green | DONE — domains 6300 passed·services/perf/contracts 1745·smoke exit 0; 인벤토리 2종(failopen·ORM 우회) 재생성 커밋 |
| C2 | T0 재프로브(토큰 만료 후) → 403 지속 시 사용자 확인 | 총괄 | 5종 200 | DONE — 사용자가 앱에 [정산] 그룹 추가 후 19:11 재프로브 5종 전부 200(daily 7행·case 12·commission 27·vat daily 28·vat case 10). 부호 실측: commissionSettleAmount -950081·payHoldbackAmount -10053445(음수), 취소 행 수수료 + |
| C3 | deploy push → CI 전 워크플로 green → 스테이징 백필 90일 → 화면 QA | 총괄 | 숫자 3개 대조 | DONE — 백필 90일 OK(호출 220·행 5,593), 30일 창 대조 API=DB(daily 22행·정산 48,121,617·결제 180,945,500)=case 합, 화면 실데이터 QA 2회 통과(부호·입금채널 수정 반영). 잔여: production 승격 — push 37666b7c2, CI 4/4 green(18:50), 스테이징 web 배포·마이그레이션 naversettle_00 적용 확인, 화면 QA 1차 통과(탭 렌더·API 200·콘솔 0), 스테이징 users 41/54 → ACCOUNTING 완료. 잔여: T0 재프로브·백필 90일·실데이터 QA |
| v1.1 | 사용자 승인 2026-09-02(세 항목 전부). 계약서 `docs/plans/2026-09-02-naver-settlement-v1.1-contracts.md`, CSV 는 **5종**(settle_daily 포함) 결정 | — | — | RUNNING |
| T12 | 요약 탭 크로스 스트립 | agent | 계약서 §8.1 ①~⑤ | DONE — 스테이징 확인: 스트립 "정산 예정일 기준 · 네이버 정산 완료 ₩4,014만 정산 예정 ₩798만 예외 67건", dashboard.js 0줄 (착수 HEAD 0a54b25b5) |
| T13 | 실무 탭 네이버 정산 컬럼 + 정산상태→차감청구 + naversettle_01 인덱스(W1-C → W2-B) | agent | 계약서 §8.1 ①~⑦ | W1-C DONE 476768ef3(naver_settlement{status,settle_expect_date,settle_complete_date,amount}, amount 는 화면 미렌더) · W2-B DONE · 스테이징 확인: 12칸(…|차감청구|네이버 정산|액션), 핀 20260903a (착수 HEAD 0a54b25b5) |
| T14 | CSV 내보내기 5종 + 감사 라벨(W1-B 커널 → W2-A UI) | agent | 계약서 §8.1 ①~⑤ | W1-B DONE df734cc46(110칸, FILTER_FIELDS daily 계열은 type/q 불가) · W2-A DONE · 스테이징 확인: 드롭다운 5링크, settle_case CSV 200 attachment 497줄, vat_daily 29줄 (착수 HEAD 0a54b25b5) |

## Phase F — 후속 v1.2 (2026-09-03, 워크트리 `c:/tmp/foms-s-settle-followup` · 브랜치 `session/settle-followup` · base origin/deploy f86ce07ae)
계약(v1.2 — 별도 계약서 없음, 이 표가 정본):
- F1 미연결 2갈래: 예외 kind `UNMATCHED` = 링크 있음·`order_id` NULL(**워크벤치 대기**, 라벨 "워크벤치 대기(주문 미생성)", action `/admin/naver-ingest/triage?link_id=N`, `ref.link_id`) / kind `UNLINKED` = 링크 없음(**수집 전 주문**, 라벨 "수집 전 주문(링크 없음)", action `/admin/naver-ingest`). 갈래마다 `_EXCEPTION_CAP` 따로(한 상한을 나누면 많은 쪽이 적은 쪽을 표에서 밀어낸다). `kpi` 에 `unmatched_pending_count`·`unmatched_unlinked_count` 추가(합 = `unmatched_count`). 매칭률·스트립 정의 불변.
- F2 지급 보류 상세: `data.holdback` = `{rows[{date, settle_method_type, settle_method_label, pay_holdback, settlement_limit, amount, completed}], count, total{pay_holdback, settlement_limit, amount}}`. 두 컬럼 중 하나라도 0 이 아닌 일별 행만, 정산 예정일 내림차순. 재계산 없음(합계만, 부호 원본). KPI 타일 "보류·한도" 가 `role=button`·`aria-expanded` 토글 → `[data-settlement-ch-holdback-detail]` 패널(표 + tfoot 합계). 전역 리스너 추가 없음.
- 핀: 채널 2줄 20260902f → 20260903b(셸 4줄 20260903a 불변).

| ID | 내용 | 완료 기준 | 상태 |
|---|---|---|---|
| F1 | 예외 큐 미연결 2갈래(커널·JS·CSS·테스트) | test_settlement_channel_api.py 2갈래 green + 스테이징 예외 큐 문구 확인 | 구현 완료(총괄 직접) — 채널 스위트 325 passed, 스트립 질의 예산 5→6(갈래 2 질의). 잔여: 스테이징 문구 확인 |
| F2 | 지급 보류 일자별 상세 표(커널·JS·CSS·테스트) | 렌더 계약 green + 스테이징 표 확인 | 구현 완료(총괄 직접) — API 4·렌더 3 테스트 신규 green. 잔여: 스테이징 표 확인 |
| F3 | 운영 매칭률 관찰(읽기 전용 1회) | 원장에 숫자 기록 | DONE — 2026-09-03 07:56 KST 운영 DB(readonly): `naver_settle_case` NAVER 1,353행 **전부 UNMATCHED**(MATCHED 0·NA 0). 링크 없음 32행(32 상품주문, 6/4~9/3) · 링크 있음·order_id NULL 1,321행(1,314 상품주문, 6/5~9/3, 링크 측 order_id 도 전부 NULL). 보류: `settlement_limit_amount` 전 행 0, `pay_holdback_amount` 24행(6/19~8/27, 최대 -27,965,819 on 8/5; 양수 4행 = 앞선 보류와 같은 금액의 해제 짝: 6/19 -2,410,000↔8/27 +2,410,000, 6/30 -3,769,400↔7/16 +3,769,400) |
| F4 | 잔재 `c:/tmp/foms-s-settle-naver` 삭제 | 디렉토리 없음 | DONE — `rm -rf` 성공(잠금 해제됨) |
| F6 | **정산 화면 글자 크기 조절**(사용자 추가 요청 2026-09-03, 네이버 워크벤치 `.wb-fs` 패턴 이식) — 셸 탭줄 조절기(`data-settlement-fs*`, 단계 [1,1.15,1.3,1.5], localStorage `foms.settlement.fontScale`), 루트 CSS 변수 `--s-fs` 로 정산 3 CSS 의 font-size 137곳이 calc 로 흐름(조절기 2규칙만 고정), 기존 위임 클릭·mount 복원 재사용, 핀 셸 4줄+채널 2줄 → 20260903c. **사용자 지시로 CEO 워크플로(`settlement-v12-ceo`)가 수행**: CEO 설계 → W1 셸·JS / W2 CSS / W3 테스트 병렬 → 통합 검증 → 2판정 리뷰 → CEO 판정. 브리프 `docs/plans/2026-09-03-settlement-followup-brief.md` | `tests/domains/test_settlement_font_scale.py`(16) + 정산 렌더 3종 green + 스테이징 실화면(130%·새로고침 유지·150% 가로 스크롤 없음) | DONE(로컬) — **CEO 판정 ship**(차단 0, minor 7). 통합 검증 all_green(JS_OK·APP_OK·font 16·렌더 607·namespace+contracts 250·-k settlement 842·워크벤치 3·perf guard 5), CEO 독립 재실행 261. 총괄 직접: 게이트 881 passed·smoke PASSED, minor 5건(R1·R2·R3·R5·R7) 직접 반영 후 font+렌더 3종 399 passed. 잔여: push·CI·스테이징 실화면 |
| F6 후속(minor, 비차단) | R4 `role=group` 이 `role=tablist` 직계(집중 모드 버튼의 기존 결함과 동일) → tablist 를 탭 4개만 감싸는 안쪽 래퍼로 · R6 함수 시그니처·localStorage 리터럴 단정은 CEO 계약 §5③ 대로 유지(리팩터 시 완화) · 수용 리스크: 150% 에서 SVG 축 라벨 좌표가 JS 고정이라 겹칠 수 있음(스테이징 실화면에서 확인) | 렌더 계약 3종 + font_scale green, 스테이징 탭 키보드 순회 확인 | DONE(로컬) 2026-09-03 — 사용자 선택("작은 손질 2건 먼저"): R4 `.s-tabs` 안에 `.s-tabs-list[role=tablist]` 래퍼(탭 4개만), 집중 모드 버튼·조절기·메타는 밖 · R6 함수는 이름 수준(`function applyFontScale(`)·`FONT_KEY` 사용 횟수 ≥3 으로 완화. 수용 리스크(150% SVG 라벨)는 유지 |
| F5 | 게이트 전수 → push_own → CI 4/4 → 스테이징 QA → 원장·AI_STATUS | 전부 green | push 완료 — 세션 커밋 e432a3605(코드)·8fdc56a54(문서) → 원격 deploy `c7f5d7b4f`(cherry-pick 재작성), production 82d8b957d 불변. **스테이징 QA 11/13 PASS**(핀 20260903c 도달·조절기 1벌·+2회=130%·새로고침 유지·150% 잠금+가로 스크롤 없음·100% 복귀 잠금·보류 타일 role=button·상세 표 16행 합계 -118,463,095(= 사용자가 찾던 -1.2억, 전부 계좌 이체·한도 0)·예외 워크벤치 대기 50행(상한)+수집 전 0·[열기]→`/admin/naver-ingest/triage?link_id=229`). 실패 2건은 정산 무관 잡음: 새로고침 중 셸 프리페치 `ERR_ABORTED` 3건·`mobile-push.js` mobile-state fetch 중단 1건. CI: 아래 결정 기록 참조 |

## 결정 기록
- 2026-09-03 CEO 워크플로(F6) 리뷰 findings 전량(스펙 2·품질 5, 전부 minor, 두 리뷰 pass):
  - R1 test_settlement_font_scale.py:409 — 핀 "정확히 1개" 단정이 `_pins_for`(set) 라 값 종류만 잠근다 → findall 출현 횟수로 세기. **수정 예정(총괄)**
  - R2 test_settlement_font_scale.py:102 — `_SCALED_FONT_SIZE_MIN_TOTAL = 130` 수치 하한은 계약 밖 단정(정당한 CSS 정리에 거짓 red) → 파일별 ≥1 구조 검사로. **수정 예정(총괄)**
  - R3 dashboard.js:327 — 끝 단계에서 방금 누른 버튼이 disabled 되며 키보드 포커스가 body 로 떨어진다(워크벤치 원형과 같은 결함) → disabled 직전 형제 버튼으로 focus 이동. **수정 예정(총괄)**
  - R4 settlement_dashboard_body.html:101 — `role=group` 이 `role=tablist` 직계 자식(집중 모드 버튼이 이미 같은 위반) → tablist 를 tab 4개만 감싸는 안쪽 래퍼로 내리기. **후속 범위(기존 구조 손질)**
  - R5 test_settlement_font_scale.py:297 — 조절기 고정 px 정규식 `\d+px` 가 소수 px 를 못 본다 → `_FIXED_FONT_SIZE_RE` 공용. **수정 예정(총괄)**
  - R6 test_settlement_font_scale.py:322 — 함수 시그니처·localStorage 호출 리터럴 단정(구현 세부) → 이름 수준으로 완화. CEO 계약 §5③ 이 명시한 항목이라 **유지**(계약 소유자=총괄 판단: 이번 릴리스 유지, 리팩터 시 완화)
  - R7 dashboard.js:319 — `applyFontScale`·`stepFontScale` 한 줄 설명 부재 → 추가. **수정 예정(총괄)**
- 2026-09-03 스테이징 QA 2차(7e225d37c 도달 후, 핀 셸 20260903d·채널 20260903c): **14/15 PASS** — tablist 자식이 tab 4개뿐·조절기는 밖·←→ 순회 OK·콘솔 에러 0·글자 크기/보류 표/예외 2갈래 전부 유지. 실패 1 = 새로고침 중 끊긴 셸 프리페치 `ERR_ABORTED`(잡음). 1차 시도에서 핀이 옛 값으로 보인 것은 레플리카 롤링 중 옛 템플릿이 섞인 것(재실행 정상).
- 2026-09-03 후속 push: 문서 `987fc8956`(CI 3/3), R4·R6 `9197dfc49`, 셸 핀 d 범프 `7e225d37c`(세션 커밋 cc9629a0c·5bd860abd·0ffc7ba52). 승격 대상 세션 커밋 5개: e432a3605·8fdc56a54·cc9629a0c·5bd860abd·0ffc7ba52.
- 2026-09-03 deploy `c7f5d7b4f` CI **4/4 green**(FOMS CI 33696559878·Harness CI·PostgreSQL Lane·perf-gate staging). 잔여: 운영 승격(사용자 확인 후 `promote_own_to_production.py --shas`, 세션 커밋 e432a3605·8fdc56a54·문서 커밋), F6 후속 minor 2건(R4 tablist 구조·R6 계약 리터럴), 워크트리 `foms-s-settle-followup` 정리(승격 뒤).
- 2026-09-03 스테이징 실화면(upperkill, 1440×900): 기본 창(08-04~09-17) 미연결 484 = 워크벤치 대기 484·수집 전 0(수집 전 32행은 6월분이라 창 밖), 보류 표 16행 합계 -118,463,095 — 회계팀이 물은 "-1.2억" 은 8/5 -27,965,819·8/24 -15,030,828·8/10 -14,444,118 등 8월 지급 보류의 누적이며 해제(양수)는 8/27 +2,410,000 하나뿐. 스크린샷 scratchpad qa_fs_130/qa_holdback_detail/qa_exceptions.png
- 2026-09-03 통합 검증(워크플로): all_green, 수정 0 — JS_OK·APP_OK·font 16·렌더 607·namespace+contracts 250·-k settlement 842·워크벤치 3·perf guard 5. 총괄 직접 재실행: 게이트 881 passed·pre_push_smoke PASSED(377).
- 2026-09-02 T0 실측: 스테이징 워커 정산 5종 403 GW.AUTHN(주문 API는 OK). 토큰 잔여 약 18:58 KST 만료 후 재검증 필요. 앱 client_id 앞 4자 4RYv.
- 2026-09-02 계약 결정: _MOCKUP_LEFTOVERS "예정" 렌더 스캔은 기존 3 pane으로 한정(채널 탭은 "정산 예정일"이 정본 용어).
- 2026-09-02 사용자 지시: 고애희(id 41)·강은미(id 54)를 회계팀(ACCOUNTING)으로 배정. 실측: 운영 role MANAGER·team CS, 스테이징 STAFF·CS. 배정은 코드 배포 뒤(스테이징 → 운영 승격 시). team 변경은 principal-version 트리거로 세션 무효화(재로그인). 게이트 = ADMIN 또는 team=ACCOUNTING 인 MANAGER/STAFF.
- 2026-09-02 19:01 T0 재검증: 새 토큰으로도 정산 5종 403 → 앱 권한 문제 확정(토큰 캐시 문제 아님). 대사 배너 수정 b01f5b9a5 deploy push 완료.
- 2026-09-02 19:11 T0 통과. 부호 규약 실측 반영 fb69eb20d(워터폴 방향 -1 제거·수수료율 abs). 백필 90일(2026-06-04~) 스테이징 워커에서 실행.
- 2026-09-02 19:20 실측: settle/daily 기간 조회 1개월 이내 제한(400 LocalDatePeriod) → 28일 창 분할(DAILY_RANGE_MAX_DAYS). 스테이징 매칭률 0.6%는 스테이징 링크의 order_id 가 대부분 NULL(2074/2123)이라서 — 운영은 워크벤치 연결 비율에 따름.
- 2026-09-02 19:33 운영 승격 PR #278 생성(세션 커밋 16개 cherry-pick + 승격 트리 인벤토리 재생성). 충돌 2건 해소: ci.yml(운영에 docs-facing 단계 없음 → deploy 블록 수용), AI_STATUS·감사 인벤토리(운영 기준 ours). 승격 트리 게이트: APP_OK·단일 head·1037 passed·smoke 0. 잔여: PR 검사 → 머지 → 운영 worker 플래그·백필·users 41/54 회계팀.
- 2026-09-02 19:40 승격 트리 전체 스위트 green(PG 마이그레이션 체인 1 passed·domains 6294 passed). PR #278 MERGEABLE, 검사 4종(test·pg-lane·harness·perf-gate) 진행 중. **재개 절차(컴팩트 후)**: ① `gh pr view 278 --json mergeStateStatus,statusCheckRollup` 전부 SUCCESS 확인 ② `gh pr merge 278 --merge` ③ 운영 배포 확인(FOMS-PRODUCTION web/worker SUCCESS, alembic naversettle_00) ④ 운영 worker `railway variables --service worker --set FOMS_NAVER_SETTLE_SYNC_ENABLED=1 --skip-deploys`(prodlink 폴더) ⑤ `railway ssh -s worker -- python scripts/maintenance/run_naver_settle_sync.py --once --backfill-from 2026-06-04 --json` ⑥ 운영 DB users 41·54 team→ACCOUNTING(TESTCLR 0건 지문 확인 후) ⑦ 원장·AI_STATUS 갱신·docs push. v1.1 계약서는 P-v11-plan 에이전트가 `docs/plans/2026-09-02-naver-settlement-v1.1-contracts.md` 작성 중.
- 2026-09-02 19:41 **운영 반영**: PR #278 머지(2fb051171) → web·WORKER 배포 SUCCESS, alembic naversettle_00, 테이블 6종 확인. WORKER `FOMS_NAVER_SETTLE_SYNC_ENABLED=1`(--skip-deploys; 컨테이너 env 반영 여부 확인 중). 운영 users 41·54 team CS→ACCOUNTING(MANAGER 유지, security_logs USER_UPDATE 2행). 운영 백필 90일 실행 중.
- 2026-09-02 19:46 운영 백필 90일 OK(호출 223·행 5,593·run_id 1). 운영 화면 1회 측정(claude_master 해제→확인→재잠금): 4탭·동기화 OK·KPI 완료 40,137,790/예정 7,983,827/수수료 -11,112,166/보류 -121,711,717·대사 일치. **운영 매칭 0/495**: settle case 의 상품주문(7~8월 결제)이 external_order_links 에 있어도 order_id 가 NULL(COLLECTED 1882·LINKED 207, LINKED 는 9월 신규분) — 워크벤치로 연결된 주문이 정산되기 시작하면 자연 증가. WORKER 컨테이너에 FOMS_NAVER_SETTLE_SYNC_ENABLED 미반영 → 안전 확인(큐 비어 있음) 후 재배포 진행. ⚠️ 측정 1차 시도에서 eval 인용 실수로 운영 비밀번호 일부가 셸 출력에 노출(로컬 세션 한정) — 로테이션 권고.
- 2026-09-02 20:00 **Wave 3(총괄) 재개 절차**: W2-A 완료 보고 대기 → ① 셸 `settlement_dashboard_body.html`: 요약 pane `#foms-settle-kpis` 뒤 `{% if can_view_channel_settlement %}<div id="foms-settle-ch-strip" data-settlement-ch-strip hidden></div>{% endif %}`(한글 0), 기존 핀 4줄 20260902b→20260903a, 채널 핀 2줄 →20260902f(W2-A 보고값 확인) ② `python -m pytest tests/domains/test_docs_facing_registry.py` red 면 ci.yml docs-facing 서브셋에 신규 테스트 등재(CRLF) ③ 정산 전 스위트+contracts+namespace imports+audit 게이트+failopen/ORM 인벤토리 재생성 확인 ④ smoke → push_own_session_commits(--shas) → CI 4/4 → 스테이징 QA(요약 스트립·실무 12칸·CSV 다운로드 1회) ⑤ 원장·AI_STATUS 갱신 → docs push. 운영 승격은 사용자 확인 후.
- 2026-09-02 20:25 v1.1 Wave 3: 게이트 전수 8102 passed·smoke 0 → deploy push 2f6426ecb(9커밋: 스트립 커널/실무 백엔드/CSV 커널/실무 프론트/채널 표면+셸 hunk+핀). CI·스테이징 QA(스트립·12칸·CSV) 진행 중. 운영 승격은 사용자 확인 후.
- 2026-09-02 20:35 v1.1 스테이징 QA 통과(스트립·12칸·CSV 5종). CI 결과는 ci_v11 참조. **잔여**: v1.1 운영 승격(사용자 확인), 지급 보류 -1.2억 사유 확인(회계팀), claude_master 비번 로테이션 권고.
