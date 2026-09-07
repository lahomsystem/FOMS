# 붙이기 후보 띠 '살아 있음 · 추가결제 신호' 오판 — 수정 브리프 (2026-09-07)

## 0. 한 줄

전부 취소된 집을 놓고 고를 때, 후보 표 ②열이 **후보 주문에 붙은 집**만 보고 `살아 있음 ·
추가결제 신호` 라고 적는다. 지금 붙이려는 집이 **전부 취소 완료**면 그 집은 옛 결제이고
관계는 **재결제(REPAY)** 다. 판정 축에 "지금 집"이 없다.

## 1. 운영 실데이터 (production, 2026-09-07 read-only 조회 · 확정 사실)

고객 이광헌 / 010-3380-7500 / 경기도 성남시 분당구 백현로 206 410동 1203호.
네이버 집 3개가 시간순으로 있다:

| 집(external_order_no) | 링크 id | 상태 | 붙은 주문 |
|---|---|---|---|
| `2026090640341021` | 2190~2196 (7건) | 전부 `CANCEL_DONE` | #5163 |
| `2026090658033751` | 2203~2208 (6건) | 전부 `CANCEL_DONE` | **없음(order_id NULL, COLLECTED)** ← 화면이 열고 있는 집 |
| `2026090758601671` | 2209~2214 (6건) | 전부 `PAYED`(살아 있음) | #5168 |

- `orders.id=5163` : `deleted_at = 2026-09-06 09:49:32` → **휴지통**(소프트 삭제).
- `orders.id=5168` : `deleted_at IS NULL`, `received_date 2026-09-07`.

그래서 세 번째 집(살아 있음)이 붙은 #5168 만 후보로 남고, 화면은 그 주문의 집 상태를
`살아 있음` 으로 찍은 뒤 `추가결제 신호` 를 권한다. **실제 관계는 재결제**다 —
지금 집(전부 취소)이 옛 결제이고 #5168 의 집이 새 결제다.

## 2. 근본 원인 (코드 앵커)

- `foms/services/integrations/naver_commerce/order_candidates.py:308` `RELATION_BY_CLAIM_CODE`
  = `{"all_done": "REPAY", "alive": "ADDON"}` — 입력이 **후보 주문 집의 claim_code 하나**다.
- 같은 파일 `:314` `recommended_relation(claim_code)` — 인자가 하나.
- 같은 파일 `:765` `_order_view(...)` 가 `facts["claim_code"]`(=후보 집) 로만 권고를 만든다.
- 템플릿 `templates/admin/partials/naver_workbench_pane.html:1019~1049` 가 같은 코드로
  ②열 칩·문구를 분기한다. `else` 가지가 `살아 있음 / N건 · **추가결제 신호**`.
- 검색 경로도 같은 모양이다: `templates/admin/partials/naver_workbench_seek.html:72`,
  `order_candidates._search_views`.
- 호출부: `foms/web/admin/naver_ingest.py:1515` (`_triage_pane` → `candidates`),
  `foms/web/admin/naver_ingest.py:5424` (다른 소비처 — 손대기 전에 읽을 것).

**같은 계열 선례**(반드시 읽을 것): `_naver_facts` 주석(:493~528)과 저장소 메모
"붙이기 후보 띠가 취소 집을 권했다" — 이웃 함수 `bulk_dispatch.find_unlinked_matches` 가
2026-09-02 에 **똑같이** 클레임 축 누락으로 고쳐졌다. 이번 것은 그 축이 "후보 쪽"에만
들어가고 "지금 집" 쪽에 없는 잔여분이다.

## 3. 고칠 판정 규칙 (계약)

지금 집의 집계 코드(`claim_aggregate_code` 결과, `current_claim_code`)와 후보 집의
코드(`candidate_claim_code`)를 **쌍으로** 본다:

| 지금 집 | 후보 집 | 권고 | 화면 문구 |
|---|---|---|---|
| `all_done` | 무엇이든 | `REPAY` | 지금 집이 옛 결제 — **재결제 신호** |
| `alive` | `all_done` | `REPAY` | 후보의 옛 결제가 취소됨 — **재결제 신호** |
| `alive` | `alive` | `ADDON` | 둘 다 살아 있음 — **추가결제 신호** |
| 그 밖(`partial`·`all_pending`·`all_mixed` 가 어느 쪽이든) | | `""` | 권하지 않음(사람이 본다) |

- 후보에 네이버 집이 아예 없으면(`link_count == 0`) 지금과 같이 `네이버 수집분 없음`.
- **칩(②열)이 "살아 있음"이라고 말할 때도, 권고가 REPAY 면 문구는 재결제여야 한다.**
  칩은 후보 집의 사실이고 권고는 쌍의 판정이다 — 둘을 한 낱말로 뭉개지 말 것.
- 판정은 **코드**로만 한다(한국어 라벨 `==` 비교 금지 — 2026-08-28 회귀 재발 방지).

## 4. 파일 소유권 (겹치면 안 됨)

| 워커 | 편집 허용 파일 |
|---|---|
| A(판정) | `foms/services/integrations/naver_commerce/order_candidates.py` |
| B(화면) | `templates/admin/partials/naver_workbench_pane.html`, `templates/admin/partials/naver_workbench_seek.html` |
| C(호출부) | `foms/web/admin/naver_ingest.py` |
| D(테스트) | `tests/services/integrations/test_naver_*.py` (신규 파일 우선) |

## 5. 완료 기준(검증 명령)

```bash
python -m pytest tests/services/integrations/ -q          # 전량 green (기준선 1689 passed)
python -c "import app; print('APP_OK')"
```

추가로 **음성 대조군 테스트 필수**:
- 지금 집 전부 취소 + 후보 살아 있음 → `REPAY` 권고, 화면에 `추가결제 신호` 문자열 **없음**.
- 지금 집 살아 있음 + 후보 살아 있음 → `ADDON` 유지(회귀 아님).
- 지금 집 살아 있음 + 후보 전부 취소 → `REPAY` 유지(기존 동작).
- 지금 집 `partial`/`all_pending` → 권고 `""`(버튼 강조 없음).

## 6. 함정

- CRLF 보존. 한글 주석 유지. `git` 명령 금지(총괄이 커밋).
- 템플릿 문구를 바꾸면 문자열을 물고 있는 계약 테스트가 빨개진다 — 바뀐 문구는 테스트도
  같이 고치되 **판정 축(코드)** 은 절대 문자열 비교로 되돌리지 말 것.
- `recommended_relation` 시그니처를 바꾸면 호출부 전부를 같이 고친다(현재 2곳 + 템플릿).
- 이 표의 권고는 `repay_reconcile.deposit_guidance` 의 '바꾸기/더하기'로 흘러 **고객
  청구액**까지 간다(2026-09-04 주석). 기본값을 아무렇게나 두지 말 것.
