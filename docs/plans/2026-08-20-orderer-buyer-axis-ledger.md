# ORDERER-AXIS-01 진행 원장

스펙: `docs/specs/2026-08-20-orderer-buyer-axis-split_SPEC.md` (사용자 전체 승인 2026-08-20)
worktree: `c:/tmp/foms-s-nvphone` · 브랜치 `session/nvphone` (base `origin/deploy` 9a932aa8)

| task | 내용 | 완료 기준 | 상태 | SHA |
|---|---|---|---|---|
| T1 | 수집 매핑: 발주사=라홈, 사람=`parties.buyer` | 수집 테스트 green + 신규 계약 | DONE | |
| T2 | 백필 `tools/ops/split_orderer_buyer_axis.py` | 5경우 계약 green + 스테이징 dry-run→execute→0건 | 코드 DONE / 스테이징 execute 대기 | |
| T3 | 검색에 `buyer.name/phone` 추가 | 주문자 이름·번호 검색 green(3건) | DONE | |
| T4 | 감사 경로+라벨 (`buyer.*`·`customer.phone2`, orderer.name 라벨 정정) | 라벨 게이트 green | DONE | |
| T5 | 상세 화면 '주문자' 행 | 수집 주문만 렌더(2건) | DONE | |
| T6 | 라홈 소비자 회귀 4건 | 알림톡 LAHOM·도면 lahom·CS 팀·`_is_lahom_like_orderer` | DONE | |

## 스테이징 백필 (T2) — 보류

사용자 결정 2026-08-20: **코드 먼저 push**, 기존 7건 백필은 나중에 다시 판단한다.
dry-run 실측(스테이징): `links_scanned=30 orders_touched=7 changed=27`
(주문 4467·4462·4466·4461·4477·4473 = 발주사→라홈 + buyer 이동, 4242 = 발주사 이미 라홈이라
buyer 이동만. 링크 30 vs 주문 7 = 한 주문에 상품주문 여러 개 — `already_split=23` 은 같은
주문의 두 번째 링크부터다.)

실행 명령: `DATABASE_URL=<staging> python tools/ops/split_orderer_buyer_axis.py --execute`
(재실행 시 `changed=0` 이어야 정상.)

**메모**: 백필·복구 스크립트는 감사 원장(structured_diff)을 거치지 않는다. 변경 이력에
남기려면 별도 배선이 필요하다 — 지금은 스크립트 실행 로그가 근거다.

공통 종료 절차: `pre_push_smoke.ps1` exit 0 → `push_own_session_commits.py` → `gh run list` 전 워크플로 확인.
