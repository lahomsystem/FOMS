# 네이버 반품 완료 표기(R-5) — 진행 원장 (2026-08-28)

앞 원장 `docs/plans/2026-08-28-naver-claim-phase-ledger.md` 의 **R-5** 를 닫는 작업.
격리 워크트리 `c:\tmp\nvclaim` (브랜치 `session/naver-claim-phase`).
기반: deploy `70fdbb3f` (클레임 단계 축 `2b9c6efd` 포함, 운영 승격 `811cf70e`/PR #180 완료).

## 문제 (운영 실측 25건, 예외 0)

`RETURN_DONE` 25건이 상세 pane 에서 이렇게 그려진다:

```
반품 진행 | 수거 완료 2026-08-26 09:17 | 회수 방법 RETURN_INDIVIDUAL | 환불 예정 2026-09-04 | 환불 대기 환불처리완료
```

끝난 반품인데 네 군데가 틀렸다 — ① 제목 고정 문자열 `반품 진행`(`pane:172`)
② `환불 대기 환불처리완료` 자기모순(`pane:183-184`, `refundStandbyStatus` 가 25건 전부
`환불처리완료` 단일값) ③ `환불 예정` 미래형(`pane:180`) ④ `RETURN_INDIVIDUAL` 영문 상수
노출(`pane:177`, `collectDeliveryMethod` 라벨 맵 부재).

근원은 하나다: `extract_return_axis`(`mapping.py:515`)가 `claimStatus` 를 **한 번도 안 읽고**,
끝났음을 말할 수 있는 유일한 값 `returnCompletedDate` 를 읽는 코드가 저장소에 **0곳**이다
(전수 grep). 운영 25건 전부 그 값을 갖고 있다.

## 설계 (2026-08-28 사용자 승인)

승인 내용: **R-5 네 가지 + R-6(교환 누출)까지 함께** · 회수 방법 라벨 `자사 회수` ·
환불 대기 줄은 **단계별 분기** · 끝난 반품의 `환불 예정` 은 **반품 완료로 정리**
("환불 예정이 며칠인지 우리가 알 필요는 없다").

| # | 자리 | 바꾸는 것 |
|---|---|---|
| D1 | `mapping.COLLECT_METHOD_LABELS` (신설) | `RETURN_INDIVIDUAL` → `자사 회수`. 모르는 값은 **원문 유지**(다른 라벨 맵과 같은 규율) |
| D2 | `mapping.extract_return_axis` | `claimStatus` 를 읽는다(= `extract_claim` 과 같은 입력·같은 함수라 값이 어긋날 수 없다). 키 추가: `phase` · `kind_label` · `progress_title` · `return_completed_at`(`returnCompletedDate`) · `collect_method_label` · `refund_done` · `refund_expected_pending`. 원문 `collect_method`·`refund_expected_at` 은 **그대로 둔다** |
| D3 | `mapping.extract_return_axis` `known` | `return_completed_at` 도 "사실 있음"에 포함 |
| D4 | `naver_ingest._return_axis_view` | `return_completed_at` 도 KST 문자열로 변환 |
| D5 | `naver_workbench_pane.html` | 제목 = `{종류} {단계}` · 회수 방법은 라벨 · 완료 시각 줄 추가 · `환불 예정` 은 완료 전에만 · 환불 대기 줄은 완료면 `환불 완료` |

### 제목 표 (D5)

| 단계 | 반품 | 교환 |
|---|---|---|
| `done` | `반품 완료` | `교환 완료` |
| `rejected` | `반품 거부` | `교환 거부` |
| 그 외(요청·수거중·수거 완료) | `반품 진행` | `교환 진행` |

종류는 `claimType` 이 판정한다(`EXCHANGE` → 교환, 나머지 → 반품). 이것이 R-6 을 닫는다 —
지금까지 교환 블록 값이 고정 문자열 `반품 진행` 이름으로 떴다(`cancel` 을 뺀 이유와 같은 형태의
누출이 교환 방향으로 남아 있었다).

`rejected` 행은 승인 4문항에 없던 **덤**이다. 같은 줄의 같은 결함(제목이 상태를 두고 거짓말)이라
한 줄로 닫히므로 넣었다 — 원치 않으면 이 행만 빼면 된다.

### 환불 줄 (D5)

- 완료 + `refundStandbyStatus` 가 아는 완료값(`환불처리완료`) → **`환불 완료`** (값 재출력 없음)
- 그 외 값이 있으면 → 기존대로 `환불 대기 <값>` (모르는 값을 완료로 읽지 않는다)
- `환불 예정 <날짜>` 는 **완료 전에만** 낸다. 완료 건은 `반품 완료일 <시각>` 이 대신한다

**범위 밖(그대로 둔다)**: R-1·R-2·R-3·R-4·R-7·R-8.

## Task

| # | 항목 | 완료 기준 | 상태 |
|---|---|---|---|
| T1 | 조사 — 코드·실데이터 대조 | `extract_return_axis`·pane·라이브 실측 25건 확인 | DONE |
| T2 | 설계 승인 | 사용자 승인 1회 | DONE (R-6 포함으로 확대) |
| T3 | 구현 D1~D5 | `python -c "import app; print('APP_OK')"` | PENDING |
| T4 | 테스트 — 추출 단위 + pane 표시, **음성 대조군 `COLLECT_DONE` 포함** | 새 테스트가 수정 전 코드에서 red · 수정 후 green | PENDING |
| T5 | 회귀 검증 | `-k naver` green · `tests/contracts tests/domains` green · `pre_push_smoke.ps1` exit 0 | PENDING |
| T6 | 스테이징 실화면 | lahom-dev 에서 `RETURN_DONE` 링크 pane 이 `반품 완료` · 자기모순 문구 0 | PENDING |
| T7 | deploy 푸시 + CI | `gh run list --commit <SHA>` 로 **전 워크플로 나열** green | PENDING |

## 규율

- **음성 대조군 필수**: 유령·후보표 테스트 입력이 전부 `done` 양성이라 결함이 오래 살았다.
  `COLLECT_DONE`(진행 중) 짝을 넣지 않으면 "제목을 통째로 지우는" 오수정이 통과한다.
- CSS·JS 를 건드리면 `naver_workbench.html:22·706` 의 `?v=` 를 범프하고
  `test_naver_workbench_async_result.py:406` 의 카운트 단언도 같이 고친다.
- `"CI green"` 판정은 `ci_watch --quick` 이 아니라 `gh run list --commit <SHA>` 전 워크플로 나열.
