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
| v1.1 | 요약 스트립·실무 컬럼·CSV 4종 | — | 별도 승인 | PENDING |

## 결정 기록
- 2026-09-02 T0 실측: 스테이징 워커 정산 5종 403 GW.AUTHN(주문 API는 OK). 토큰 잔여 약 18:58 KST 만료 후 재검증 필요. 앱 client_id 앞 4자 4RYv.
- 2026-09-02 계약 결정: _MOCKUP_LEFTOVERS "예정" 렌더 스캔은 기존 3 pane으로 한정(채널 탭은 "정산 예정일"이 정본 용어).
- 2026-09-02 사용자 지시: 고애희(id 41)·강은미(id 54)를 회계팀(ACCOUNTING)으로 배정. 실측: 운영 role MANAGER·team CS, 스테이징 STAFF·CS. 배정은 코드 배포 뒤(스테이징 → 운영 승격 시). team 변경은 principal-version 트리거로 세션 무효화(재로그인). 게이트 = ADMIN 또는 team=ACCOUNTING 인 MANAGER/STAFF.
- 2026-09-02 19:01 T0 재검증: 새 토큰으로도 정산 5종 403 → 앱 권한 문제 확정(토큰 캐시 문제 아님). 대사 배너 수정 b01f5b9a5 deploy push 완료.
- 2026-09-02 19:11 T0 통과. 부호 규약 실측 반영 fb69eb20d(워터폴 방향 -1 제거·수수료율 abs). 백필 90일(2026-06-04~) 스테이징 워커에서 실행.
- 2026-09-02 19:20 실측: settle/daily 기간 조회 1개월 이내 제한(400 LocalDatePeriod) → 28일 창 분할(DAILY_RANGE_MAX_DAYS). 스테이징 매칭률 0.6%는 스테이징 링크의 order_id 가 대부분 NULL(2074/2123)이라서 — 운영은 워크벤치 연결 비율에 따름.
