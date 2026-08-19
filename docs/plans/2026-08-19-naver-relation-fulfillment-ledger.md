# NAVER-INGEST-02 진행 원장 — 관계 판별 + 발주확인·발송처리

- 스펙: `docs/specs/2026-08-19-naver-order-relation-and-fulfillment_SPEC.md`
- 선행 프로젝트: NAVER-INGEST-01 (원장 `docs/plans/2026-08-13-naver-order-ingest-ledger.md` — T15 까지 완료)
- 작업 위치: `c:\tmp\foms-s-naver-ingest` (브랜치 `session/naver-ingest`) · 푸시는 **deploy 만**
- 상태 범례: `PENDING` / `IN_PROGRESS` / `DONE` / `BLOCKED` / `N/A`

## 재개 규칙

1. 이 파일의 Task 표에서 첫 `PENDING` 을 찾는다.
2. 의존 열의 선행 task 가 `DONE` 인지 확인한다.
3. 막히면 `BLOCKED` + 사유를 적고 **다음 독립 task 로 전진**한다.
4. task 단위로: 구현 → 검증(완료 기준 명령 실행) → 커밋 → 이 표 갱신.
5. 착수 전 `git fetch` + `origin/deploy` 리베이스 + `python -m alembic heads` 단일 확인.

## 게이트 (이걸 통과 못하면 해당 task 는 시작하지 않는다)

| 게이트 | 내용 | 막는 task | 현재 |
|---|---|---|---|
| G1 권한 | 커머스API 앱에 주문/배송 그룹 권한 | T16-G, T16-H | **통과 (2026-08-19)** — API그룹 `주문 판매자 · 모든 리소스 유형`(주문조회·발주/발송처리·취소·교환) |
| G2 배송코드 | 자사 직접배송의 `deliveryMethod` 코드 | T16-G | `DIRECT_DELIVERY` 유력 — **실호출 1건 검증 필요**(구매확정·정산 시점 변화 확인 포함) |
| G3 Q3 | 재결제 시 원 주문 취소 표시 방식 | T16-D 마무리 | 미확정 (실건 보고 결정) |

G2 는 문서만으로 끝내지 않는다 — 직접 전달은 배송 추적이 없고 **자동 구매확정 기준이 택배와
달라 정산 시점이 바뀔 수 있다**. 스테이징 실호출 1건으로 확인한 뒤 T16-G 를 확정한다.

## Task 표

| Task | 내용 | 의존 | 상태 | 완료 기준(검증 명령/관찰) |
|---|---|---|---|---|
| T16-A | `placeOrderStatus` 읽기 표시(이력·확인 큐·대조 pane) | — | **DONE** `1d7b6056` | 단위 4 + 화면 2 green · 스테이징 눈 확인(39집 중 21집 '발주확인 전', 완료건 무배지, pane '발주확인 완료 · 발송기한') · 콘솔 0 |
| T16-B | `relation`(NEW/ADDON/REPAY) + `place_order_status` 컬럼 + 마이그레이션 + 백필 + '발주확인 전' 필터 | T16-A | **DONE** `6f9724d0` | PG17 왕복 green · PG 레인 737 green · 필터 계약 4 green · 스테이징 눈 확인(버튼 21집, 필터 시 21행 전부 배지, status×place 조합 3행) |
| T16-C | 기존 주문 후보 조회(전화 digits·이름·주소, 180일·5건) | T16-B | **DONE** | 계약 9 green(수취인/주문자 전화·이름+주소·무관 제외·soft delete·기간 밖·자기 자신·깨진 원본·기존 링크 수) |
| T16-D | 확인 큐/도크에 후보 표시 + '이 주문에 붙이기' UI | T16-C | PENDING | 스테이징 실건(소액 단독 집)으로 붙이기 눈 확인, erporder 폼 무변경 |
| T16-E | attach 라우트(멱등·취소 가드·감사·되돌리기) | T16-B | PENDING | 계약 테스트: 2회 호출 동일 결과 · blocking ADDON 차단 · 권한 · 감사 이벤트 · 되돌리기 |
| T16-F | 추가결제 `extra_payments` 기록 + 표시 | T16-E | PENDING | 기록 후 출고가·잔금 계산 불변(계약 테스트), 되돌리기 시 항목 제거 |
| T16-G | 발주확인·발송처리 client + WORKER enqueue | G2 | PENDING | 스텁 테스트(멱등·실패 사유 노출) + 스테이징 `DIRECT_DELIVERY` 실호출 1건 성공 + 판매자센터 표시·구매확정 예정일 확인 |
| T16-H | 버튼 노출 규칙(신규=발주확인 / 추가결제=확인 후 발송) | T16-G | PENDING | 관계별 버튼 노출 계약 테스트 + 스테이징 눈 확인 |

**권한 없이도 되는 범위**: T16-A ~ T16-F (네이버에 쓰지 않는다).

## 공통 완료 조건 (모든 task)

- `python -c "import app; print('APP_OK')"`
- 해당 도메인 테스트 green (`python -m pytest tests/services/integrations -q`)
- push 직전 `scripts/ops/pre_push_smoke.ps1` exit 0
- push 후 `gh run list` 로 워크플로 **전체** green 확인(ci_watch 는 1개만 본다)
- 새 mutation route 는 auth policy manifest 2종 등재 필수(NAVER-INGEST-01 에서 밟은 함정)

## 되돌리기

- T16-B 마이그레이션: `downgrade` 포함, 컬럼 제거로 원복.
- T16-E attach: 링크 `order_id=NULL` + `relation='NEW'` + `sync_status='COLLECTED'` 복귀,
  `extra_payments` 항목 제거까지 한 tx.
- T16-G 쓰기: 네이버 쪽은 되돌릴 수 없다 — 그래서 멱등 기록과 확인 게이트가 필수다.

## 기록

- 2026-08-19: 스펙 작성. Q1(추가결제=기록만) 확정. 진행 순서 = 권한 확인 → 스펙 수정 → 계획서 검토 → 구현.
- 2026-08-19: **G1 권한 게이트 통과** — 앱 API그룹 `주문 판매자 · 모든 리소스 유형` 확인(발주/발송처리 포함).
  G2 배송코드는 `DIRECT_DELIVERY` 로 좁혔고 실호출 검증만 남았다.
- 2026-08-19: **T16-A 범위 조정** — '발주확인 전' **필터**는 T16-B 로 옮긴다.
  `placeOrderStatus` 는 `raw_snapshot`(JSONB) 안이라 SQL 필터를 걸려면 인덱스 없는 JSONB
  스캔이 된다(hot path 규칙 위반). T16-B 마이그레이션에 `place_order_status` 컬럼을
  `relation` 과 함께 넣고 인덱스로 필터를 건다. 표시는 이미 원본을 푸는 경로에 얹으므로
  추가 비용 0.
- 2026-08-19: T16-A DONE. 스테이징 실데이터에 `NOT_YET` 과 완료건이 **둘 다** 존재해 판별이
  실제로 갈린다는 것까지 확인(최은혜 집 = 발주확인 완료, 배지 없음).
- 2026-08-19: T16-B DONE. 스테이징 마이그레이션·백필 확인(필터가 컬럼 기반인데 21집이 그대로
  잡힌다 = 과거 수집분 백필 성공). 수집 상태 축과 겹쳐 걸린다(`status=LINKED&place=PENDING` → 3집).
