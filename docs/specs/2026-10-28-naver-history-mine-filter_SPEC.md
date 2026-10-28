# 네이버 수집 이력 탭 — '내 담당만' 필터 (SPEC, 승인 대기)

작성 2026-10-28. 요청: "이력 탭(`/admin/naver-ingest/triage?tab=all`)을 영업이 담당 고객 결제 확인에 쓰게".

## 1. 지금 상태 (실측)

- 열람 권한은 **이미 열려 있다** — `e4a251ac8`(2026-09-07, 운영 반영). 판정 `_can_view_history`
  (`foms/web/admin/naver_ingest.py`): ADMIN + MANAGER/STAFF 중 팀 `ACCOUNTING`·`SALES`.
- 운영 web 배포 `84fda4c4e` 에 들어 있다. 운영 워크벤치 게이트 `FOMS_NAVER_WORKBENCH_COHORT=all`.
- 운영 영업팀 활성 계정: MANAGER 9 · STAFF 1 → 전원 탭 진입 가능.
- 이력 행에는 결제 요약(결제일·수단·할인)·금액이 이미 있다(`_payment_summary`).
- 빈 곳: 목록이 **전 직원의 모든 주문**이라 영업 사원이 자기 고객을 찾으려면 이름을 하나씩 쳐야 한다.

운영 데이터(2026-10-28 읽기 전용): 네이버 링크에 붙은 ERP 주문 290건 중 영업 담당(`order_assignments`
active SALES)이 있는 주문 270건. `order_assignments` 963행 — 작은 표라 새 인덱스 불필요.

## 2. 바꾸는 것

1. 이력 탭 칩 줄에 **'내 담당만'** 토글 칩을 단다. 주소 인자 `mine=1`.
2. 술어(SSOT 한 곳 `_history_mine_clause(user_id)`):
   `ExternalOrderLink.order_id IN (SELECT order_id FROM order_assignments WHERE active AND domain='SALES' AND user_id=:me)`.
   기존 필터와 같은 규약 — "해당 링크가 하나라도 있는 집"을 고르고, 뽑힌 집의 상품주문은 전부 싣는다.
3. `find` 와 똑같이 **목록·총계·쪽수·칩 숫자 전부**에 건다(`_link_rows`·`_status_group_counts`·
   `_place_pending_group_count`·`_dispatch_pending_group_count`·`_relation_group_count`).
   목록만 좁히고 칩이 전체를 말하는 함정(기존 주석의 실패 모양)을 피한다.
4. 칩·찾기 폼·지우기(×)·쪽 넘김 링크가 `mine` 을 **유지**한다(빠지면 다른 칩을 누르는 순간 조용히 풀린다).
5. 기본값: 영업팀(MANAGER/STAFF + team SALES) 이 이력 탭에 **인자 없이** 들어오면 `mine` 켜짐.
   칩을 눌러 끄면 `mine=0` 으로 전체를 본다. ADMIN·회계팀은 기본 꺼짐.
   - 칩은 담당 주문이 있을 수 있는 사람(영업팀 + ADMIN)에게만 보인다. 회계팀에는 안 보인다.
6. '내 담당만' 이 켜진 빈 결과: "내 담당 네이버 주문이 없어요" 문구.

## 3. 바꾸지 않는 것

- 권한(누가 탭을 여는지)·운영 손잡이(ADMIN 전용) 그대로.
- 처리(work) 탭·nav 배지 숫자 그대로.
- ERP 주문이 아직 없는 수집분(담당자도 없음)은 '내 담당만' 에서 안 보인다 — 끄면 보인다.

## 4. 검증

- 단위: 술어가 다른 사람 담당·released 배정·ERP 주문 없는 링크를 빼는지, 칩 숫자가 같은 술어로 좁혀지는지,
  영업팀 기본 켜짐 / `mine=0` 끔 / 회계팀 칩 없음.
- 성능 가드: `pre_push_smoke.ps1`(서브쿼리는 IN select — JSONB 안 탐).
- 스테이징 실화면: 영업 계정으로 이력 탭 → 기본 '내 담당만' → 끄기·칩 이동 시 유지.
