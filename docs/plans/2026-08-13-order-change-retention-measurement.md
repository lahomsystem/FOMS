# 주문 변경 원장 보존 실측 (ORDER-RETENTION-00 / T8)

- 측정: 2026-08-13, 운영 DB(`FOMS-PRODUCTION` / `DATABASE_PUBLIC_URL`) **읽기 전용** 조회
- 대상: `order_field_changes` (ORDER-DIFF-01, 운영 반영 2026-08-11 21:56 KST~)
- 사용자 결정(2026-08-13): "**하루 몇 줄 쌓이는지 먼저 재고 그 숫자로 기준 정한다**",
  완전 삭제는 어떤 안에서도 하지 않는다(헤더 `security_logs` 는 영구 보존).

## 1. 실측값

| 지표 | 값 |
|---|---|
| 누적 행 | 577 (2026-08-11 21:56 ~ 08-13 02:28 UTC) |
| **완전한 하루(08-12)** | **445행 / 저장 묶음 52건** |
| 최근 24시간 | 430행 |
| 저장 묶음당 변경 | 평균 7.8 · p95 21 · 최대 25 |
| 테이블 크기 | 296 kB (본체 112 kB + 인덱스 152 kB) → **약 526 B/행** |
| 비교: `security_logs` | 25,760행 / 23 MB (누적 전체) |
| 주문 수 | 3,786 |

가장 많이 바뀌는 경로 상위: `totals.shipping_price`(37) · `totals.contract_total`(37) ·
`totals.items_total`(35) · `items.*.price`(33) · `totals.final_amount`(32) ·
`items.*.spec`(31) · `items.*.spec_rows`(30).
→ `totals.*` 가 상위를 덮는다. **서버 재계산 파생값**이라는 §ORDER-REASON-00 판정과 일치한다.

## 2. 증가 추정

- 445행/일 × 365 = **연 162,000행 ≈ 85 MB**(인덱스 포함, 현 행당 크기 기준)
- 3년 누적 ≈ 49만 행 / 250 MB. PostgreSQL 에서 조회가 느려지는 규모가 아니다
  (인덱스 3종이 `path_template`·`order_id`·`change_set_id` 를 덮는다).

## 3. 사유 요구 빈도 (실측)

현재 판정 규칙을 운영 데이터에 그대로 적용하면:

> **저장 묶음 74건 중 48건(65%)이 사유를 요구한다 = 하루 약 34회.**

"중요한 변경일 때만"이라는 결정에 비해 높다. 원인은 실제 업무 저장의 다수가 품목 단가나
일정을 함께 건드리기 때문이다(위 경로 분포와 같은 이유). 좁힐 수 있는 후보:

| 안 | 내용 | 예상 빈도 |
|---|---|---|
| A (현행) | 금액 입력·일정·단계·품목 구성 전부 | 65% |
| B | 일정은 **확정 이후 변경만**(RECEIVED 단계 저장 제외) | 대략 절반 이하 |
| C | 금액은 **변동폭 임계 초과**(예: 5% 또는 5만원)만 | 30~40% 추정 |

B·C 는 추가 구현이 필요하다(단계·변동폭 판정). 지금은 A 로 배포돼 있다.

## 4. 보존안 (완전 삭제 없음)

| 안 | 내용 | 3년 후 크기 | 장단 |
|---|---|---|---|
| 1 무기한 | 지금 그대로 | ~250 MB | 구현 0. 조회 성능은 인덱스가 감당 |
| 2 요약 압축 | 24개월 지난 change set 은 **묶음 1행 요약**으로 접고 상세 행 삭제 | ~60 MB | 감사 헤더(`security_logs`)와 요약은 남는다. 필드 단위 소급 질의는 24개월까지만 |
| 3 콜드 아카이브 | 12개월 지난 행을 별도 테이블/파일로 옮기고 본 테이블에서 제거 | ~85 MB | 조회 경로가 둘로 갈린다(운영 화면은 12개월, 그 이전은 아카이브) |

**권고: 안 1 유지 + 12개월 뒤 재측정.** 실측 증가율이 연 85 MB 로 작고, 압축·아카이브는
지금 넣으면 쓰이지도 않는 코드 경로를 감사 원장에 얹는 것이다. 다만 **기준선(이 문서)을
남겨** 두어 나중에 옮길 때 판단 근거가 있게 한다.

## 5. 재측정 방법(그대로 반복 가능)

```bash
# 스크래치패드 디렉토리에서(저장소 링크 오염 금지)
railway link --project FOMS-PRODUCTION
railway variables --service Postgres --json > pgvars.json
# psycopg2 conn.set_session(readonly=True) 로 접속 후:
#   SELECT date_trunc('day',created_at)::date, count(DISTINCT change_set_id), count(*)
#   FROM order_field_changes GROUP BY 1 ORDER BY 1;
#   SELECT pg_size_pretty(pg_total_relation_size('order_field_changes'));
```
