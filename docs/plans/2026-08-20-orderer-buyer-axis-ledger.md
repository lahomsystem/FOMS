# ORDERER-AXIS-01 진행 원장

스펙: `docs/specs/2026-08-20-orderer-buyer-axis-split_SPEC.md` (사용자 전체 승인 2026-08-20)
worktree: `c:/tmp/foms-s-nvphone` · 브랜치 `session/nvphone` (base `origin/deploy` 9a932aa8)

| task | 내용 | 완료 기준 | 상태 | SHA |
|---|---|---|---|---|
| T1 | 수집 매핑: 발주사=라홈, 사람=`parties.buyer` | 수집 테스트 green + 신규 계약 | PENDING | |
| T2 | 백필 `tools/ops/split_orderer_buyer_axis.py` | 5경우 계약 green + 스테이징 dry-run→execute→0건 | PENDING | |
| T3 | 검색에 `buyer.name/phone` 추가 | 주문자 이름·번호 검색 green(3건) | PENDING | |
| T4 | 감사 경로+라벨 (`buyer.*`·`customer.phone2`, orderer.name 라벨 정정) | 라벨 게이트 green | PENDING | |
| T5 | 상세 화면 '주문자' 행 | 수집 주문만 렌더(2건) | PENDING | |
| T6 | 라홈 소비자 회귀 4건 | 알림톡 LAHOM·도면 lahom·CS 팀·`_is_lahom_like_orderer` | PENDING | |

공통 종료 절차: `pre_push_smoke.ps1` exit 0 → `push_own_session_commits.py` → `gh run list` 전 워크플로 확인.
