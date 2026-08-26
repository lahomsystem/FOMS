# 네이버 필드 3건을 화면에 올린다 — 진행 원장 (2026-08-26)

> 근거: `docs/guides/NAVER_FIELD_INVENTORY.md` §3 우선순위 1~3
> 앞선 작업: `docs/plans/2026-08-26-naver-deposit-and-refresh-ledger.md`
> 작업 트리: `c:\tmp\nvfix` (브랜치 `tmp/naver-fix-20260825`)

셋 다 **원본 스냅샷에 이미 수집돼 있다**(281/281). 화면이 안 읽었을 뿐이라
**네이버로 나가는 호출은 0**이다.

| # | 필드 | 왜 |
|---|---|---|
| F-1 | `cancelDetailedReason` · `returnDetailedReason` | 고객이 직접 쓴 사유 원문. 실데이터가 `"일시불 재결제 예정"` — 재결제 판정의 결정적 근거인데 담당자가 이 한 줄을 보려고 판매자센터를 따로 열었다 |
| F-2 | `delivery.sendDate` · `deliveryStatus` | 발송처리를 우리가 눌러 놓고 그 결과 시각을 화면이 안 읽는다 |
| F-3 | `remain*` / `initial*` | 한 집에서 일부만 취소되면 "원래 몇 개였는지"를 화면이 말하지 못한다 |

## 진행

| # | 몫 | 상태 |
|---|---|---|
| A | 추출 3종 (`mapping.py`) + 테스트 17건 | **DONE** |
| B | 화면 표시 (pane · CSS · `naver_ingest.py`) + 테스트 12건 | **DONE** |
| C | 검증 → 커밋 → deploy → CI | **DONE** — `535d4244`, CI 4/4 green |
| D | 운영 승격 | **PENDING** |
| E | 스테이징 실화면 확인 | **PENDING** |

**CEO 감독은 안 붙였다.** 표시 전용이라 쓰기·돈 계산이 없어 앞 묶음과 위험 등급이 다르고,
그 시점 컨텍스트가 68% 였다. 대신 주 세션이 diff 를 직접 읽었고 두 몫이 각자 전량 스위트를
돌렸다(`5757 passed, 5 skipped` · smoke exit 0).

## 검증 기록

| 항목 | 결과 |
|---|---|
| import | `APP_OK` |
| 전량 | `5757 passed, 5 skipped in 1134.47s` |
| smoke | `=== PRE-PUSH SMOKE PASSED ===` |
| deploy CI | **4/4 green** (FOMS CI · PG Lane · Harness · perf-gate) |
| 자산 핀 | `20260826b` 3곳 일치 |

## 설계에서 못박은 것

**부분취소 판정의 함정** — `remain*`·`initial*` 는 **281/281 전 건에 다 있다**.
존재 여부로 판정하면 **모든 집이 부분취소로 보인다**. 그래서 `is_partial` 은
**초기값과 잔여값이 실제로 다를 때만** True 이고, 한쪽 값이 안 온 원본은 "모른다"로 두고
False 다(없는 값을 0 으로 채우면 화면이 "원래 0개"라고 거짓말한다).
`_known_int` 헬퍼가 "값이 온 것"과 "0"을 가른다.

**`reason` 과 `detailed_reason` 을 합치지 않는다** — 앞은 집계·판정에 쓰는 코드값이고
뒤는 사람이 쓴 문장이다. 기존 6키는 뜻도 값도 불변(회귀 테스트로 잠금).

**없는 값은 줄 자체를 안 낸다** — 빈 칸이나 `-` 로 채우면 화면이 거짓말을 한다.

## 알려진 사각 (A 가 넘긴 사실)

`_snapshot_projection`(`naver_ingest.py`)이 만드는 **얇은 문서**는 `cancel`·`currentClaim` 을
통째로 실어 `detailed_reason` 은 살아남지만, **`delivery` 와 `initial*`/`remain*` 은 없다**.
지금은 두 호출 다 통째 스냅샷을 읽으므로 무해하다. 나중에 **목록(얇은) 경로에서 F-2·F-3 를
부르면 조용히 빈 값이 된다** — 그때 투영에 경로를 더해야 한다.

배송 상태 라벨은 실데이터 확인분(`NOT_TRACKING`·`DIRECT_DELIVERY`)에 `DELIVERING`·
`DELIVERED` 만 더했다. 그 밖의 코드는 규율대로 **원문 그대로** 나온다(숨기지 않는다).

## 다음 세션이 이어받을 것

1. **필드 3건 운영 승격** — `535d4244` cherry-pick → `gh pr create --base production`.
   승격 절차·함정은 `docs/plans/2026-08-26-naver-deposit-and-refresh-ledger.md` §운영 승격 참고
   (의존 분류 → 인벤토리는 승격 트리에서 재생성 → PR).
2. **스테이징 실화면 확인** — 사유 원문 한 줄 · 발송 행 어긋남 칩 · 부분취소 `원래 N`.
   워크벤치 코호트가 `38` 이라 `claude_master`(58)로 보려면 잠시 `38,58` 로 열고 **원복**한다.
   재배포로 로그인 세션이 끊기니 다시 로그인해야 한다(그 전에 행을 세면 0 이 나와 오독한다).

## 범위 밖 (다음에)

- 사유 원문을 **R-1 후보 표의 `네이버 옛 결제` 열**까지 올리기.
  `order_candidates` 를 거쳐야 하는데 이번 두 몫 어느 쪽 파일도 아니라 뺐다 —
  판정이 실제로 일어나는 자리가 거기라 값어치는 가장 크다.
