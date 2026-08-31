# 네이버 이력 탭 상태 칸 재설계 — 구현 계획 + 진행 원장

- **작성**: 2026-08-30
- **대상 화면**: `/admin/naver-ingest/triage?tab=all` (이력 탭, ADMIN 전용 · 읽기 전용 표)
- **목업(승인됨)**: `docs/design/mockups/naver-triage-status-column.html` + `…--table.html`
- **결정**: B안 — 상태 칸을 축별 줄로 가른다(1줄 FOMS · 2줄 네이버 파이프 · 예외 줄은 있을 때만)
- **기준 브랜치**: `origin/deploy` (022c6c49 기준으로 조사). 작업 트리는 최신 `deploy` 를 받은 뒤 시작한다.

---

## 1. 왜 고치나 (사용자 요구)

1. 재결제·추가결제 상태가 이력 탭에 **아예 없다** — `ExternalOrderLink.relation` 이 이력 행에 실리지 않는다.
2. 발송처리 축이 **통째로 없다** — `triage_state.fulfillment.dispatched_at` 도, 네이버 `delivery.sendDate` 도 이력 표에서 안 읽는다.
3. 발주확인은 "전"만 표시하고 **완료는 무표시**라, 화면 규칙을 외운 사람만 읽는다.

부수 효과로 다음이 화면에서 사라져 있던 것도 함께 올라온다: 부분 발송·부분 발주확인, 발송/발주확인 실패,
발송기한 초과, 클레임 확정 여부(phase), 고스트(결제 전부 취소인데 ERP 주문 생존).

## 2. 절대 지킬 것

- **네이버 API 호출 0건**. 표시값은 전부 이미 저장된 컬럼·`raw_snapshot`·`triage_state` 에서 나온다.
- **이력 행에 mutation 을 붙이지 않는다**(절대 규칙 3). 버튼·`data-link-id` 금지, 평범한 링크만.
  불가역 라우트는 STAFF 까지 열려 있어서 이력 행이 조작면이 되면 과거 주문 전체가 사정권에 든다.
- **집(묶음) 단위 셈**을 깨지 않는다. 숫자는 전부 집 단위(`grouping.py` / `_history_group_key`).
- 표시 라벨은 기존 매핑 상수(`CLAIM_STATUS_LABELS`·`PLACE_STATUS_LABELS`·`DELIVERY_STATUS_LABELS`)를 우선 쓰고,
  화면 전용 문구만 새로 만든다.

## 3. 손댈 파일

| 파일 | 무엇 |
|---|---|
| `foms/web/admin/naver_ingest.py` | `_link_rows()`(284행~) 에 축 필드 싣기 · 새 집계 함수 · `_history_view()`(1637행~) 칩 술어·counts |
| `templates/admin/naver_workbench.html` | 이력 칩(621~640행) · 이력 표 상태 칸(686~700행) |
| `static/css/admin/naver-workbench.css` | `.wb-st*` 3줄 격자 + container query · 파이프 |
| `templates/admin/naver_workbench.html` 22·792행 | 자산 `?v=` 핀 범프(CSS·JS 두 줄 함께) |
| `tests/services/integrations/…` | 신규 계약 테스트 + 핀 문자열 잠근 기존 테스트 2곳 갱신 |

## 4. 알려진 함정 (착수 전 읽을 것)

1. **`td` 는 컨테이너가 못 된다.** `display: table-cell` 은 inline-size containment 를 무시한다.
   목업에서 실측으로 확인했다(칸 306px 인데 `@container` 미발동). 반드시 안쪽 블록 래퍼에 `container-type` 을 건다.
   접힘 기준은 **뷰포트가 아니라 칸 폭**이다 — 같은 부품이 처리 탭·도크(폭 358)에도 실린다.
2. **고객명 열이 짜부라지면 글자가 세로로 선다.** 좁은 폭에서 열을 짜내지 말고 표를 `min-width` + 가로 스크롤로 넘긴다.
3. **자산 핀 문자열을 테스트가 잠근다.** `?v=20260829a` 를 올리면
   `test_naver_origin_cleanup.py:313`(`markup.count("?v=20260829a") == 2`)와
   `test_naver_workbench_async_result.py:406` 이 같이 red 가 된다 — 같은 커밋에서 함께 고친다.
4. **`mismatch`(우리만 보냄) 는 칩으로 만들 수 없다.** 판정이 `raw_snapshot` 파생값이라 SQL 로 못 거른다.
   쪽을 자른 뒤 파이썬으로 세면 `history.total`·`pages` 가 거짓말이 된다(캡 뒤 파이썬 분류 함정).
   **행 배지로만** 둔다.
5. **옛 수집 화면(`templates/admin/naver_ingest.html`)은 손대지 않는다.** 게이트가 켜지면 리다이렉트로 닫히는 화면이고,
   `test_naver_admin_surface.py:217` 이 그 화면의 옛 라벨(`수집됨(생성 전) 2주문`)을 잠그고 있다.
   워크벤치만 새 어휘로 간다 — 두 화면이 다른 말을 쓰는 기간이 생기는 것은 의도된 것이며 이 원장에 적어 둔다.
   → **기간과 갈리는 낱말 전부를 §10.9 에 명시했다.** 끝 날짜는 아직 없다(사람이 정할 항목).
6. **N+1·JSONB 스캔 금지.** 발송 판정은 이미 메모리에 있는 페이지 링크로 계산한다(추가 쿼리 0).
   새 칩 술어(`발송처리 남음`)는 JSONB 를 타므로 부분 인덱스 식과 **정확히 일치**해야 한다.

## 5. 새 어휘 (목업 확정본)

| 축 | 값 |
|---|---|
| FOMS | `받아옴` · `주문 만듦` · `확인 필요` · `받기 실패` · `주문 접음` · `주문 살아 있음`(고스트) |
| 관계 | `신규 결제`(회색) · `추가결제 → #N` · `재결제 → #N` · `기존 주문 후보 N건` · `재결제 짝 → #N` |
| 네이버 단계 | 끝남 `발주확인 완료`/`발송처리 완료` · 지금 차례 `발주확인 할 차례`/`발송처리 할 차례` · 아직 `발송처리`(회색 이름만) · 실패 `발주확인 실패`/`발송처리 실패` · 부분 `발주확인 2/3`·`발송처리 1/2` · 어긋남 `네이버 기록 없음` · 해당 없음 `네이버 처리 없음`(한 칸) |
| 취소·반품 | `취소 요청 · 확정 전` · `반품 수거중 · 확정 전` · `취소 완료 MM-DD` · `반품 완료 MM-DD` · `취소 거부` · `교환 요청 · 확정 전` · `구매확정 보류` |
| 옛 결제 | `취소 완료 MM-DD` · `아직 살아 있음`(빨강) |
| 칩 | `전체` · `받아옴 · 주문 전` · `주문 만듦` · `확인 필요` · `받기 실패` · `발주확인 남음 · 취소 포함` · **신규** `발송처리 남음` · **신규** `추가결제 · 재결제` |

> **구현 결과와 갈린 자리**: `취소 완료 MM-DD`·`취소 거부 MM-DD` 의 **날짜는 안 나온다** —
> 확정 날짜의 유일한 출처가 네이버 `returnCompletedDate`(반품 축)인데 취소 스냅샷에는 그 필드가
> 없다(§10.7 레인 T · §10.8-2 · 계약 §3.3 갈림표). `반품 완료 08-26` 은 나온다.
> `주문 살아 있음`(고스트)·`기존 주문 후보 N건`·`재결제 짝 → #N`·`옛 결제` 줄은 §7 범위 밖이다.

색 규칙: 빨강=지금 봐야 함 / 주황=다음 차례 / 초록=끝남 / 회색=끝났고 손댈 것 없음 / 보라=돈 관계.
**모든 색에 글자 라벨을 함께** 둔다(색맹 대비 — 기존 결정 4 유지).

---

## 6. 진행 원장

상태: `PENDING` / `DOING` / `DONE` / `BLOCKED`. 각 task 는 **완료 기준 명령이 통과해야** DONE 이다.

> **상태 갱신은 §10 이 정본이다.** 아래 각 task 의 상태 줄은 2026-08-30 수정 라운드 뒤의 값이고,
> 그때 **실제로 돌린 명령과 꼬리 출력**은 §10.1 표에 원문으로 붙였다. 안 돌린 명령의 결과는 적지 않는다.

### T1 — 이력 행에 축 필드 싣기 · 상태 `DONE` (2026-08-30)

`foms/web/admin/naver_ingest.py::_link_rows()` 가 만드는 집 dict 에 다음을 더한다.

- `relation` (집 대표 링크의 `ExternalOrderLink.relation`), `related_order_id`
- `place_done_count` / `place_total` (집 안 링크 중 발주확인 완료 수 — `_place_view(link)["confirmed"]`)
- `dispatch` : `_dispatch_view(link)` 를 집 단위로 접은 값
  (`done_count`·`total`·`ours_at`·`naver_at`·`mismatch`·`failed`·`skipped`)
- `claim_phase` (`mapping.CLAIM_PHASES` 로 라벨과 함께)
- `shipping_due` (`_place_view(link)["shipping_due"]` 중 가장 이른 값)

**완료 기준**
```
python -m pytest tests/services/integrations/test_naver_workbench.py -q
python -c "import app; print('APP_OK')"
```
새 필드가 실제로 값을 갖는지 확인하는 단위 테스트 1개를 T6 에서 붙인다. 이 단계에서는 기존 테스트가 green 이면 통과.

**결과(2026-08-30)**: `85 passed in 2.40s` · `APP_OK`. 축 필드는 `_history_group_axes()` 로 뽑아 냈고,
`related_order_id` 는 **관계를 정한 멤버**에서 나온다(계약 §2.2 갱신). 원문은 §10.1.

### T2 — 집 단위 발송·발주확인 집계 · 상태 `DONE` (2026-08-30)

부분 상태를 만들 수 있는 것은 집계뿐이다. `_link_rows()` 안에서 **이미 읽은 링크로만** 센다(추가 쿼리 0).

- 발주확인: `2/3` 처럼 `완료수/전체수`. 전부면 `발주확인 완료`.
- 발송: 같은 규칙. 하나라도 남으면 `발송처리 N/M`.
- 실패: `triage_state.fulfillment.last_error` 가 있으면 실패 상태가 이긴다(작업별 라벨은 `FULFILLMENT_ACTION_LABELS`).
- 어긋남: 집 안에 `mismatch` 링크가 하나라도 있으면 `네이버 기록 없음`.
- 해당 없음: 취소 확정·수집 실패 집은 파이프 대신 `네이버 처리 없음` 한 칸.

**완료 기준**
```
python -m pytest tests/services/integrations/ -q -k "workbench or fulfillment or dispatch"
```
+ 새 집계 함수 단위 테스트(부분 2/3, 전부 완료, 실패 우선, 해당 없음 4케이스)가 green.

**결과(2026-08-30)**: `331 passed, 707 deselected in 6.91s`. 판정표는 템플릿이 아니라 서버
(`_history_place_step`·`_history_dispatch_step`)로 옮겼다(사람 결정 6). **다만 4케이스 중
`실패 우선`(fail 축 렌더)은 아직 단언이 없다 — §10.3 의 남은 구멍.**

### T3 — 상태 칸 마크업 교체 · 상태 `DONE` (2026-08-30)

`templates/admin/naver_workbench.html` 686~700행의 배지 나열을 목업의 3줄 격자로 바꾼다.
축 줄은 라벨(`FOMS`/`네이버`/`취소·반품`/`옛 결제`) + 값. **예외 줄은 값이 있을 때만** 낸다.

**완료 기준**
```
python -m pytest tests/services/integrations/test_naver_workbench.py tests/services/integrations/test_naver_workbench_history_open.py tests/services/integrations/test_naver_workbench_history_detail.py -q
```
+ 이력 행에 `data-link-id`·`<button>` 이 없다는 계약 테스트가 여전히 green (절대 규칙 3).

**결과(2026-08-30)**: `106 passed in 2.76s`. 상태 칸은 3줄 격자 + 2칸 파이프로 교체됐고
`옛 결제` 줄은 §7 범위 밖이라 안 냈다.

### T4 — CSS + 자산 핀 · 상태 `DONE` (2026-08-30)

`static/css/admin/naver-workbench.css` 에 `.wb-st`(격자)·`.wb-st__k`·`.wb-st__v`·`.wb-pipe*` 추가.
컨테이너는 **안쪽 래퍼**(`.wb-st-wrap { container-type: inline-size }`), 접힘 기준 330px.
`templates/admin/naver_workbench.html` 22·792행의 `?v=20260829a` 를 같은 값으로 함께 범프하고,
핀 문자열을 잠근 테스트 2곳(`test_naver_origin_cleanup.py:313`, `test_naver_workbench_async_result.py:406`)을 같은 커밋에서 갱신한다.

**완료 기준**
```
python -m pytest tests/services/integrations/test_naver_origin_cleanup.py tests/services/integrations/test_naver_workbench_async_result.py -q
```
+ 인라인 스타일 0(프로젝트 규칙) · CSS·JS 핀이 같은 값.

**결과(2026-08-30)**: `47 passed in 0.98s`. 핀은 네 자리 모두 `?v=20260830a`
(템플릿 22·897행 · `test_naver_origin_cleanup.py:321` · `test_naver_workbench_async_result.py:406`).
JS 핀 행이 792 → 897 로 밀렸다 — 계약 §7 갱신함.

### T5 — 칩 어휘 교체 + 새 칩 2종 · 상태 `DONE` (2026-08-30)

621~640행 칩 라벨을 §5 표대로 바꾸고, 새 칩 둘을 더한다.

- `발송처리 남음` : 서버 술어 필요. JSONB(`triage_state`) 를 타므로 **부분 인덱스 식과 정확히 일치**시키고,
  `EXPLAIN` 에 Seq Scan 이 없어야 한다.
- `추가결제 · 재결제` : `relation in ('ADDON','REPAY')` — 컬럼이라 그대로 센다.
- **`네이버 기록 없음` 칩은 만들지 않는다**(함정 4). 행 배지로만.

칩 숫자는 표 총계와 같은 **집 단위**여야 한다 — 링크 행으로 세면 부분이 전체보다 커 보인다(2026-08-19 실화면 사고).

**완료 기준**
```
python -m pytest tests/services/integrations/test_naver_admin_surface.py tests/services/integrations/test_naver_workbench.py -q
```
+ 새 칩 숫자가 집 단위임을 잠그는 테스트 1개 · `EXPLAIN` 결과를 이 원장에 붙인다.

**결과(2026-08-30)**: `115 passed in 3.16s`. 칩 낱말은 `_HISTORY_STATUS_CHIP_SPECS` 파생이고
템플릿은 `history.status_chips` 를 돈다(사람 결정 4). `추가결제·재결제` 는 처리 탭 칩과
가운뎃점 표기를 맞췄다. `EXPLAIN` 은 §10.6 — **스캔 노드 줄이 잘려 있다(§10.2 미확정)**.

### T6 — 계약 테스트 신규 · 상태 `DONE` (2026-08-30, 남은 구멍은 §10.3)

새 파일 `tests/services/integrations/test_naver_history_status_axes.py`:

1. 추가결제·재결제 집에 관계 배지와 상대 주문번호가 나온다.
2. 발주확인·발송처리 완료가 **글자로** 나온다(무표시 규칙 부활 방지).
3. 부분 발송(1/2)·부분 발주확인(2/3)이 나온다.
4. 우리 기록만 있고 네이버가 침묵하면 `네이버 기록 없음` 이 나온다.
5. 취소 확정 집은 파이프 대신 `네이버 처리 없음` 한 칸.
6. 클레임 `phase` 가 미확정/확정을 가른다.
7. 이력 행에 버튼·`data-link-id` 가 없다(절대 규칙 3 회귀 방지).
8. 칩 라벨과 행 배지가 **같은 낱말**을 쓴다(한 화면 두 이름 방지).

**완료 기준**
```
python -m pytest tests/services/integrations/test_naver_history_status_axes.py -q
```
전 케이스 green. 새 테스트가 `docs/` 를 읽으면 `ci.yml` 서브셋에 등재한다(CI-DOCSCOPE-01).

**결과(2026-08-30)**: `24 passed in 1.03s`. 새 테스트는 `docs/` 를 **읽지 않아** 등재 불필요
(`-k "docscope or docs"` → `2 passed, 1036 deselected`). 잠근 것과 **남은 구멍 4종은 §10.3**.

### T7 — 성능 확인 · 상태 `DONE` (EXPLAIN·가드) / TTFB 항목만 `BLOCKED` — §10.2

이력 탭은 페이지당 집 단위로 자른다. 추가 쿼리가 0인지, JSONB 칩 술어가 인덱스를 타는지 본다.

**완료 기준** *(2026-08-30 갱신 — 계약 §4.3 과 맞췄다)*
- `EXPLAIN` 출력에 **`ix_external_order_link_dispatch_pending` 이름이 뜬다.**
  "Seq Scan 없음" 으로 물으면 인덱스가 무시돼도 통과한다.
- 이력 탭 TTFB 를 변경 전후로 재고, 회귀 없음을 원장에 기록.
- `python -m pytest tests/performance/test_perf_regression_guard.py -q` exit 0.

**결과(2026-08-30)**: 가드 `5 passed in 0.17s`. 실 PG 17.9 에서 인덱스 2벌 생성 확인(§10.6).
**인덱스 이름이 뜨는 줄은 원장에 안 남았다** — §10.2. TTFB 측정은 배포본이 없어 `BLOCKED`.

### T8 — 전체 검증 · 커밋 · 스테이징 배포 · 상태 `BLOCKED` (검증은 통과, 커밋·배포는 사람 몫 — §10.4)

**완료 기준**
```
python -m pytest tests/services/integrations/ -q
python tools/harness/verify_result.py --json
pwsh -File scripts/ops/pre_push_smoke.ps1     # exit 0 아니면 push 금지
```
+ `deploy` push 후 `gh run list` 로 **커밋별 전 워크플로**가 green 인지 확인(ci_watch 는 1개만 본다).
+ 스테이징 실화면에서 목업의 20케이스 중 실데이터로 재현되는 것을 눈으로 확인.

**결과(2026-08-30)**: 검증 3종 전부 통과 — `1038 passed in 16.91s` · `verify_result.py --json`
`"success": true` · `pre_push_smoke.ps1` `=== PRE-PUSH SMOKE PASSED ===` (exit 0).
**커밋·푸시·배포·눈 확인은 안 했다** — 공유 트리라 사람 몫이다. 상세 §10.4.

---

## 7. 범위 밖 (이번에 안 한다)

- **production 승격** — 사용자 명시 요청 시에만.
- 처리 탭(work) 행 배지 통일 — 같은 어휘로 맞추면 좋지만 별건. 이력 탭이 먼저다.
- 옛 수집 화면(`naver_ingest.html`) 라벨 — 함정 5.
- 반품 축(수거 완료·환불 예정)을 **칩**으로 거르기 — 행 표시까지만.

## 8. 기록

| 날짜 | 내용 |
|---|---|
| 2026-08-30 | 목업 확정(B안), 예외 20케이스·좁은 폭·배지 말투·칩 말투까지 합의. 본 계획서 작성. 코드 미착수. |
| 2026-08-30 (1차 구현) | 에이전트 9 · 계약 동결 → CEO 착수 게이트(`FIX_FIRST`) → 4레인 병렬 → 통합 → CEO 2판정. **두 판정 모두 `FAIL`.** findings 전량은 §9. |
| 2026-08-30 (수정 라운드) | §9 findings 전량 소화. blocker 1(부분 인덱스 마이그레이션 신설·CAST 조건식) · major 2(어긋남 경고 시각 · 클레임 날짜·사유 표시) · minor 7. 사람이 내린 결정 7건(§10.5)에 따라 임의 축소 없이 목업대로 냈다. 검증 결과·남은 것은 §10. **커밋·푸시는 안 했다 — 공유 트리라 사람이 한다.** |

---

## 9. 워크플로 실행 결과 (2026-08-30) — 리뷰 findings 전량
실행: 에이전트 9 · 계약 동결 → CEO 착수 게이트 → 4레인 병렬 → 통합 → CEO 2판정.
워크트리 `C:/tmp/foms-naver-status` · 브랜치 `feat/naver-history-status` (origin/deploy 827c44db 기준).

**사람이 직접 돌린 검증**: `import app` → APP_OK / `pytest tests/services/integrations/` → **1029 passed**.

### CEO 착수 게이트 — 판정 `FIX_FIRST`
1. **부분 인덱스 조건식이 실제 쿼리와 글자가 다르다 — CAST 누락 (계약 §4.3)**
   - 왜: 계약이 스스로 '글자까지 같아야 한다'고 못 박아 놓고, 실은 두 조각이 다르다. C:/tmp/foms-naver-status 에서 계약의 파이썬 술어를 그대로 렌더한 결과는 coalesce(CAST((external_order_links.triage_state -> 'fulfillment') ->> 'dispatched_at' AS VARCHAR), '') = '' 인데, 계약의 CREATE INDEX 조건식에는 CAST 가 없다. models.py:17 의 JSONColumn 이 JSON().with_variant(JSONB,'postgresql') 라 베이스 타입이 JSON 이고, 그래서 CAST 없는 .astext 를 쓸 수도 없다(AttributeError 로 확인). 조건식이 안 맞으면 PostgreSQL 이 부분 인덱스를 증명하지 못해 통째로 무시한다. 더 나쁜 것은 계약 §4.5 가 'Seq Scan 이 나오면 선택도 문제다, 술어를 비틀지 마라'라고 미리 적어 둔 점이다 — 레인은 인덱스가 안 먹는 진짜 이유를 못 보고 T7 을 그 문장으로 닫는다.
   - 고칠 방법: 마이그레이션에 손으로 SQL 을 적지 말고, 술어를 실제로 렌더해서(compile(dialect=postgresql, literal_binds=True)) 나온 문자열을 그대로 인덱스 조건식에 붙여라(끝에 ::varchar 가 붙는 모양). 그리고 T7 완료 기준을 'Seq Scan 없음'이 아니라 'EXPLAIN 출력에 ix_external_order_link_dispatch_pending 이름이 뜬다'로 바꿔라 — 없음 판정은 인덱스가 무시돼도 통과한다.
2. **관계 배지의 주문번호를 관계를 정한 멤버가 아니라 대표(lead) 링크에서 뽑는다 (계약 §2.2)**
   - 왜: relation 은 '멤버 중 ADDON 이 하나라도 있으면 ADDON'인데 related_order_id 는 lead['order_id'](금액 최대 링크)에서 뽑는다. 서로 다른 링크다. foms/web/admin/naver_ingest.py:2587~2594 의 기존 주석이 '백필 전 데이터는 형제 일부만 값이 있을 수 있어 멤버 전체를 본다 … 둘이 섞이면 ADDON 을 대표로 적는다'라고 명시한다 — 섞인 집은 실재한다. lead 가 NEW 형제면 화면은 '추가결제 → #(엉뚱한 주문번호)'를 찍고, lead 에 order_id 가 없으면 '추가결제 → #None' 이 찍힌다. 계약 §2.1 이 클레임 축에 대해서는 '라벨은 A 링크, 단계는 B 링크에서 뽑으면 화면이 거짓말한다'고 같은 규율을 이미 적어 놨는데 관계 축에만 그 규율이 빠졌다. 사용자 요구 1번(재결제·추가결제를 명확히)의 핵심 숫자이고, 사람이 눌러서 그 주문으로 들어간다.
   - 고칠 방법: §2.2 를 고쳐라 — relation 을 결정한 바로 그 멤버의 order_id 를 related_order_id 로 쓴다. 그리고 §3.1 에 None 일 때의 화면 규칙을 적어라(화살표와 번호를 아예 안 낸다, 배지 낱말만). 레인 D 계약 테스트에 '관계는 ADDON 인데 대표가 NEW 인 섞인 집' 케이스를 하나 넣어라.
3. **한 화면에서 같은 축을 세 낱말로 부른다 — §9-8 계약 테스트가 그대로는 쓸 수 없다**
   - 왜: 계약 §2.4 는 HISTORY_STATUS_CHIPS 와 HISTORY_FOMS_LABELS 를 '한 벌'이라 부르지만 실제로는 두 벌이고 값이 갈린다: 칩 '받아옴 · 주문 전' vs 배지 '받아옴'. 네이버 축은 더 심하다 — 새 칩 '발주확인 남음 · 취소 포함' vs 새 파이프 '발주확인 할 차례' vs 같은 페이지 처리 탭 칩 '발주확인 전'(templates/admin/naver_workbench.html:279). 새 칩 '추가결제 · 재결제' 는 처리 탭 칩 '추가결제·재결제'(같은 279행)와 가운뎃점 띄어쓰기까지 다르다. 이 상태로는 §9 의 8번 계약 테스트('칩 라벨과 행 배지가 같은 낱말')를 쓸 수 없고, 레인 D 는 통과하도록 몰래 약하게 쓰거나 red 로 막힌다. 어휘 통일이 이번 작업의 명시 목표(요구 3번)인데 그 목표를 검증할 수단이 사라진다.
   - 고칠 방법: §2.4 에서 칩 라벨을 배지 낱말에서 파생하도록 고쳐라 — 칩 = 배지 낱말 + 선택적 꼬리(예: '받아옴' + ' · 주문 전'). §9-8 을 '모든 칩 라벨은 대응하는 배지 낱말로 시작한다'로 다시 써서 검증 가능하게 만들어라. 네이버 축은 칩과 파이프가 같은 동사를 쓰도록 하나로 정하고(둘 중 하나로), 처리 탭과의 전면 통일은 §8 대로 미루되 가운뎃점 표기만은 지금 맞춰라.
4. **목업에 있는데 조용히 빠진 표시가 §8 제외 목록에 없다 (임의 축소)**
   - 왜: 목업 확정본은 클레임 줄에 날짜와 사유를 단다 — '취소 완료 08-26'(E14), '반품 완료 08-26'(E13), '취소 거부 08-26'(E15), '단순 변심 · 환불 예정 08-30'(E12), '색상·사이즈 변경 · 수거중'(E16), '정산 지연'(E18). 계획서 §5 어휘표도 '취소 완료 MM-DD'로 적혀 있다. 그런데 계약 §3.3 은 라벨+꼬리+색만 정의하고 날짜·사유를 아예 안 다루며, §8 제외 목록에도 없다. §10 은 '목업 대비 벗어난 자리 3곳'이라고 세는데 실제로는 그보다 많다. 게다가 이 값들은 mapping.py:501~547 의 extract_claim(detailed_reason)과 mapping.py:670~730 의 반품 축 뷰(return_completed_at·refund_expected_at·collect_completed_at)에서 추가 쿼리 0으로 나온다 — 순수 파싱이라 뺄 기술적 이유가 없다. 레인은 계약만 보고 코딩하므로 이대로 가면 승인된 화면보다 조용히 빈약한 화면이 나온다.
   - 고칠 방법: 클레임 줄의 날짜·사유를 실을지 뺄지 지금 정하고 §3.3(실으면 필드·형식·출처)이나 §8(빼면 이유)에 적어라. 실는 쪽을 권한다 — 쿼리 비용이 0이고 목업이 이미 승인됐다. §10 의 '3곳'을 실제 개수로 고쳐라.
5. **레인 착수 순서와 레인별 자기검증 수단이 없다 — 공유 트리 하나 + 커밋 금지 조합에서 깨진다**
   - 왜: 파일 배분 자체는 직접 열어 확인한 결과 겹치지 않는다(naver_ingest.py / naver-workbench.css / naver_workbench.html + 핀 2줄 / 신규 테스트 1개). 그런데 심볼 의존이 한 방향으로 걸려 있다: 레인 C 템플릿은 레인 A 가 아직 안 쓴 HISTORY_STATUS_CHIPS 와 새 행 필드를 읽고, 레인 D 테스트는 A·C 가 둘 다 들어와야 초록이 된다. 네 레인이 같은 트리에서 동시에 돌고 커밋으로 경계를 나눌 수도 없으니, C 와 D 의 완료 기준 명령은 남의 미완성 때문에 red 로 뜬다. 그 red 를 자기 것으로 오인한 레인이 남의 파일에 상수를 만들어 넣는 순간 배분이 무너진다(계약 §0 이 경고한 바로 그 실패 모양이다).
   - 고칠 방법: 레인 A 를 먼저 완주시키고(§2.4 상수 + §2.2 필드) 그다음 B/C/D 를 병렬로 돌려라. 그럴 수 없으면 레인마다 '남의 미완성과 무관하게 판정되는 명령'으로 완료 기준을 다시 써라(예: 레인 B 는 CSS 파일의 클래스 존재만, 레인 C 는 템플릿 렌더 대신 소스 문자열 계약만). 그리고 red 를 만났을 때 남의 파일을 고치지 말고 멈추라는 규칙을 §6 에 한 줄 적어라.

통과 판정 메모:
- 사용자 요구 세 가지는 전부 화면에 오른다 — ① relation 배지 + 상대 주문번호(§2.2·§3.1) ② 발송 파이프 칸 + 시각 + 발송기한(§2.3-C·§3.2) ③ FOMS 축 5상태를 색이 아니라 글자로(§2.3-A·§3.1). 이 축에서는 통과다.
- 되돌릴 수 없는 조작은 새로 생기지 않는다. 새로 붙는 것은 GET 링크(칩·페이저·주문번호)뿐이고, 계약이 인용한 읽기 전용 계약 테스트 3종이 실재함을 확인했다 — tests/services/integrations/test_naver_workbench.py:677·741, tests/services/integrations/test_naver_workbench_v3_contract.py:516(tbody 안 <button·data-link-id·class="btn 전부 0).
- 주인 없는 red 는 없다(직접 확인). 이력 탭 상태 칸의 옛 낱말을 잠근 테스트는 저장소에 없다. tests/services/integrations/test_naver_workbench_row_truth.py:127 의 '발주확인 전' 은 ?tab=work 라 이번 변경과 무관하고, tests/services/integrations/test_naver_admin_surface.py:217 의 '수집됨(생성 전) 2주문' 은 계약 주장대로 옛 화면 /admin/naver-ingest 를 친다. 옛 화면도 _link_rows 를 쓰지만 새 필드를 안 읽으므로 무해하다.
- 칩 숫자의 단위는 안전하다. 기존 _status_group_counts(naver_ingest.py:226)·_place_pending_group_count(:266)이 이미 group_by(gk).count() 모양이고 계약의 새 두 함수도 같은 모양이다. mismatch 를 칩에서 뺀 판단(§4.1)은 옳다 — raw_snapshot 파생값이라 SQL 로 못 거르고, 쪽을 자른 뒤 파이썬으로 세면 total·pages 가 거짓이 된다.
- 다만 칩 숫자는 전역이고 history.total 은 필터 적용값이다(기존 동작). 이번에 필터 파라미터가 2개에서 4개로 늘어 칩을 겹쳐 거는 일이 흔해진다 — 두 칩을 함께 누르면 목록 길이가 어느 칩 숫자와도 안 맞는다. 회귀는 아니지만 원장에 알려진 어긋남으로 남겨라.
- '발송처리 남음' 술어는 취소 집뿐 아니라 FAILED·PENDING_REVIEW 수집분도 센다(발송 기록이 없으므로). 그 행들은 화면에서 '네이버 처리 없음'으로 뜨는데 칩 꼬리는 '· 취소 포함'뿐이라 라벨과 모집단이 살짝 갈린다. 옆 칩 6번도 같은 성질이라 회귀는 아니다 — 원장에 적어라.
- 부분 인덱스를 (channel, group_key) 에 걸었는데 집계 키는 coalesce(nullif(group_key,''), nullif(external_order_no,''), 'link:'||id) 다(foms/services/integrations/naver_commerce/grouping.py:31). 컬럼 인덱스가 그 GROUP BY 를 그대로 받지 못할 수 있다. blocking 1번을 고쳐도 인덱스가 안 먹을 수 있으니 판정은 반드시 EXPLAIN 에 인덱스 이름이 뜨는지로 하라.
- 처리 탭이 '발주확인 전'/'발주확인 완료'로 남는 동안 이력 탭은 '발주확인 할 차례'가 된다. 두 탭은 같은 URL 의 같은 페이지다 — §8 의 연기 결정은 받아들이되, 언제 통일할지 기한을 원장에 적어라. 안 적으면 영구히 두 말이 된다.
- 마이그레이션이 CREATE INDEX(CONCURRENTLY 아님)라 배포 중 external_order_links 쓰기를 잠깐 막는다. 현재 규모(목업 기준 수백 집)면 무시할 수준이지만 수집 워커와 겹치면 재시도가 뜬다. naverfail_00 선례와 같은 모양이니 그대로 가도 되나, 알고는 있어라.
- down_revision 을 착수 시점 alembic heads 로 잡으라는 §4.3 의 지시는 옳다. 승격 체인 전제는 하루면 낡는다 — 문서에 값을 못 박지 않은 것이 정확한 판단이다.
- §6 의 레인 C 행 번호는 실제와 조금 어긋난다(칩 619~657, 표머리 659~666, 상태 td 688~700, 페이저 753~768). 표는 6열이 아니라 8열이고 빈 목록 colspan 이 8 이다. 취향 문제라 blocking 은 아니지만, 레인이 행 번호를 믿고 자르면 다친다 — 번호 대신 앵커 문자열로 적는 편이 낫다.

### 통과 상태

- 통합 에이전트 전체 스위트: 6641 passed, 596 skipped (남은 red: 없음)

### CEO 최종 판정 — 스펙 준수 (사용자 요구·목업 어휘·계획서 함정 6개·읽기 전용·집 단위) → `FAIL`

> 사용자 요구 3가지는 화면에 다 올라왔고 읽기 전용·집 단위도 지켜졌으나, 계약이 못 박은 부분 인덱스 마이그레이션이 통째로 빠져 이력 탭을 열 때마다 인덱스 없는 JSONB 전수 스캔이 돕니다(함정 6 위반). 목업의 클레임 날짜·사유는 서버가 계산해 놓고 화면에 안 냅니다.

- **blocker** `C:/tmp/foms-naver-status/migrations/versions/`
  - 무엇: 계약 §4.3·§4.4·§6(레인 A)이 산출물로 명시한 마이그레이션 `naverdisp_00_history_chip_indexes.py` 가 존재하지 않는다. `git status migrations/` 는 비어 있고, `grep -rn ix_external_order_link migrations/versions/` 에 `ix_external_order_link_dispatch_pending`·`ix_external_order_link_relation_pair` 가 없다. 그런데 `foms/web/admin/naver_ingest.py:2137 _history_view()` 는 칩이 걸렸든 안 걸렸든 `_dispatch_pending_group_count(db)` 를 **매 렌더마다** 부르고(호출 지점 1683행, 이력 탭 진입 시 항상), 그 술어 `_dispatch_pending_clause()`(319행)는 `triage_state->'fulfillment'->>'dispatched_at'` 와 `raw_snapshot->'delivery'->>'sendDate'` 두 JSONB 경로를 탄다. 인덱스가 없으므로 `external_order_links` 전수 Seq Scan 이 확정이다 — 계획서 함정 6(N+1·JSONB 스캔 금지)과 T7 완료기준(`EXPLAIN` 에 Seq Scan 없음)이 둘 다 미충족이고, 원장에 EXPLAIN 원문도 없다. 옆 칩 `발주확인 남음` 은 같은 이유로 일부러 컬럼(`place_order_status`)만 보게 만들어져 있어(289행 docstring: "JSONB 로 필터하면 인덱스 없는 스캔이 되고, 그건 이 저장소의 hot path 금지 규칙") 새 칩만 그 규율 밖에 있다. SQLite 레인이라 테스트는 이 구멍을 못 잡는다(green 이 근거가 안 된다).
  - 고칠 방법: 계약 §4.3·§4.4 의 CREATE INDEX 두 벌을 담은 `migrations/versions/naverdisp_00_history_chip_indexes.py` 를 `naverfail_00_fulfillment_error_index.py` 와 같은 모양(PostgreSQL 아니면 return, IF NOT EXISTS, downgrade 포함)으로 만든다. `down_revision` 은 착수 시점 `python -m alembic heads` 로 확인해 붙인다. 조건식은 손으로 적지 말고 `_dispatch_pending_clause().compile(dialect=postgresql.dialect(), compile_kwargs={'literal_binds': True})` 렌더 결과를 그대로 넣어 CAST 모양까지 일치시킨다(그 문자열은 이미 `_dispatch_pending_clause` docstring 에 적혀 있다). 그 뒤 실 PG 에서 `EXPLAIN` 을 떠 Seq Scan 부재를 확인하고 원문을 원장 T7 에 붙인다. 선택도가 낮아 플래너가 Seq Scan 을 고르면 계약 §4.5 대로 술어를 비틀지 말고 EXPLAIN 원문과 행 수를 원장에 붙여 판단을 받는다.
- **major** `C:/tmp/foms-naver-status/templates/admin/naver_workbench.html`
  - 무엇: 목업이 확정한 취소·반품 줄의 날짜·사유가 화면에 안 나온다. 서버는 `foms/web/admin/naver_ingest.py` 의 `_history_member_axes()`·`_history_claim()` 에서 `claim_reason`·`claim_done_text`·`claim_refund_expected_text`·`claim_collect_done_text`·`claim_refund_done` 을 계산해 집 dict 에 싣고, docstring 에 "목업 확정본의 `반품 완료 08-26` · `단순 변심 · 환불 예정 08-30` 이 이 값들이다 — 2026-08-30 CEO 지적 4" 라고 적어 두었다. 그런데 템플릿 상태 칸(781~835행)은 `{{ row.claim_label }}{{ claim_tail }}` 만 찍는다 — `grep -n "claim_reason|claim_done_text|claim_refund|claim_collect_done_text" templates/admin/naver_workbench.html` 결과 0건. 결과: 화면은 `취소 완료`·`반품 완료` 로만 나오고 목업의 `취소 완료 08-27`(153행)·`반품 완료 08-26`(264행)·`단순 변심 · 환불 예정 08-30`(252행)·`수거 완료 08-25 · 환불 완료`(264행)·`색상·사이즈 변경 · 수거중`(301행) 이 전부 빠졌다. 서버 필드 5개는 아무도 안 읽는 죽은 값이 됐다. 동결 계약 §3.3 표도 이 꼬리들을 안 적었고 §10 '목업 대비 벗어난 자리' 3곳에도 등재되지 않아, 목업과 화면이 말없이 갈린 자리다.
  - 고칠 방법: 둘 중 하나를 골라 명시적으로 닫는다. (a) 목업대로 낸다 — 취소·반품 `.wb-st__v` 안에 배지 뒤로 `.wb-st__when` 을 붙여 `claim_done_text`(확정 시), `claim_reason`·`claim_refund_expected_text`·`claim_collect_done_text`·`claim_refund_done` 을 계약 §3 의 '값이 있을 때만 낸다' 규칙으로 조립하고, 레인 D 에 계약 테스트를 1개 더한다. (b) 이번 범위에서 뺀다 — 계약 §8 표와 §10 기록에 '클레임 날짜·사유 꼬리 제외'를 근거와 함께 등재하고, `_history_member_axes`·`_history_claim` 에서 그 5개 필드를 지운다(계산만 하고 안 쓰는 값을 남겨 두면 다음 사람이 화면에 이미 있다고 오독한다).
- **minor** `C:/tmp/foms-naver-status/templates/admin/naver_workbench.html`
  - 무엇: 계약 §2.4 는 "템플릿은 `HISTORY_STATUS_CHIPS` 를 그대로 돌려 칩을 낸다" 고 못 박았는데, 템플릿 640~648행은 `[('COLLECTED','받아옴 · 주문 전'), ('LINKED','주문 만듦'), ('PENDING_REVIEW','확인 필요'), ('FAILED','받기 실패')]` 를 손으로 두 벌째 적는다. 서버 상수는 칩 렌더에 전혀 안 쓰인다(`grep -rn HISTORY_STATUS_CHIPS` 결과 파이썬·테스트만 히트). 상수 자신의 주석이 경고한 실패 모양("손으로 두 벌 적으면 칩만 '받아옴 · 주문 전', 배지만 '받아옴' 으로 조용히 갈린다")과 정확히 같은 구조다. 다만 `test_naver_history_status_axes.py:521` 이 상수의 라벨이 렌더된 칩 줄에 있는지를 물어 드리프트는 red 로 잡히므로 조용한 실패는 아니다.
  - 고칠 방법: 뷰가 `history` 컨텍스트에 `status_chips=HISTORY_STATUS_CHIPS` 를 실어 주고 템플릿이 `{% for key, label in history.status_chips %}` 로 돌게 바꾼다. 그대로 두기로 한다면 계약 §2.4 의 문장을 '템플릿은 같은 낱말을 찍고 테스트가 상수와 대조한다'로 고쳐 문서와 코드를 맞춘다.
- **minor** `C:/tmp/foms-naver-status/docs/plans/2026-08-30-naver-history-status-contract.md`
  - 무엇: 동결 계약과 코드가 갈렸는데 계약서가 안 고쳐졌다. §0 은 "이름을 바꿔야 할 근거가 나오면 코드를 고치기 전에 이 문서를 먼저 고치고 네 레인에 알린다" 를 규율로 둔다. 실제 갈린 자리: ① §2.2 `related_order_id` = `lead["order_id"]` 인데 구현(`_history_relation`)은 관계를 정한 그 멤버에서 뽑는다(구현 쪽이 옳다 — 섞인 집에서 대표가 NEW 형제일 수 있다) ② §2.4 의 `HISTORY_STATUS_CHIPS` 는 라벨을 손으로 적은 튜플인데 구현은 `_HISTORY_STATUS_CHIP_SPECS` 에서 파생시킨다 ③ §2.1·§2.2 에 없는 클레임 필드 5종이 추가됐다.
  - 고칠 방법: 계약 §2.1·§2.2·§2.4 를 구현된 규칙으로 갱신하고, §10 기록 표에 '2026-08-30 구현 중 확정한 3건'을 근거와 함께 한 줄씩 남긴다. 이 문서가 다음 작업의 정본이므로 지금 안 고치면 다음 세션이 계약을 읽고 lead 기준으로 되돌린다.
- **minor** `C:/tmp/foms-naver-status/docs/plans/2026-08-30-naver-history-status-column-ledger.md`
  - 무엇: 진행 원장이 착수 전 상태 그대로다. T1~T8 이 전부 `PENDING` 이고 §8 기록 표에는 '코드 미착수' 한 줄뿐인데 코드는 전부 들어와 있다. T5 완료기준의 'EXPLAIN 결과를 이 원장에 붙인다', T7 의 'TTFB 변경 전후 기록', 함정 5 가 요구한 '두 화면이 다른 말을 쓰는 기간을 이 원장에 적어 둔다' 가 모두 비어 있다. compaction 이나 세션 교대가 나면 무엇이 끝났는지 판정할 근거가 없다.
  - 고칠 방법: T1~T6 을 완료 기준 명령과 실행 결과(이 트리에서 `tests/services/integrations/` 1029 passed · 신규 15 passed · `APP_OK` · perf guard 5 passed)와 함께 DONE 으로 갱신하고, T7 은 인덱스 마이그레이션과 EXPLAIN 이 붙을 때까지 BLOCKED 로 남긴다. §8 기록에 목업 대비 미구현(클레임 날짜·사유)과 옛 수집 화면 어휘 분기 기간을 명시한다.
- **minor** `C:/tmp/foms-naver-status/tests/services/integrations/test_naver_origin_cleanup.py`
  - 무엇: 계약 §6 은 이 파일을 '핀 문자열 한 줄씩만 고친다(다른 줄을 건드리면 레인 D 와 부딪친다)' 로 배분했는데, 실제 diff 는 `_link()` 헬퍼에 `collected_at` 파라미터 추가 + `datetime` import + 호출 2곳 수정까지 들어갔다(318행 핀 외 4자리). 변경 자체는 타당해 보인다 — `created_at` 이 같은 눈금에 떨어질 때만 뒤집히는 간헐 실패를 못 박는 수정이고 docstring 에 이유가 적혀 있다. 다만 레인 배분 밖이라 계약의 '파일 겹치면 병렬이 깨진다' 규율에 걸린다.
  - 고칠 방법: 계약 §6 레인 C 항목에 '`_link()` 의 `collected_at` 고정(간헐 실패 교정)'을 예외로 등재하거나, 이 변경을 별도 커밋으로 갈라 어느 레인 산출물인지 이력에 남긴다. 코드를 되돌릴 필요는 없다.

### CEO 최종 판정 — 코드 품질 (근본원인·성능·프로젝트 규칙·테스트 실효성·죽은 코드/중복) → `FAIL`

> 계약이 요구한 부분 인덱스 마이그레이션이 통째로 빠져 이력 탭이 열릴 때마다 JSONB 무인덱스 전체 스캔이 돈다(저장소 hot path 금지 규칙 위반) — 여기에 발송 어긋남 경고가 다른 링크의 시각을 찍는 결함, 아무도 안 읽는 반품축 필드 6종과 칩 라벨 이중 관리가 더 있다.

- **blocker** `C:/tmp/foms-naver-status/foms/web/admin/naver_ingest.py:319,354,2188`
  - 무엇: 계약 §4.3·§4.4가 요구한 마이그레이션(naverdisp_00_history_chip_indexes)이 존재하지 않는다. git status에 새 마이그레이션 없음, `python -m alembic heads`는 merge_drawq_naverfail 그대로, 인덱스 이름 ix_external_order_link_dispatch_pending·ix_external_order_link_relation_pair는 계약 문서와 _dispatch_pending_clause 독스트링에만 나온다(있지도 않은 산출물을 '글자까지 같아야 한다'고 설명하는 독스트링이다). 그런데 _history_view는 ?tab=all 렌더마다 조건 없이 _dispatch_pending_group_count(db)를 부르고, 그 술의는 coalesce(triage_state->'fulfillment'->>'dispatched_at','')='' AND coalesce(raw_snapshot->'delivery'->>'sendDate','')='' 를 external_order_links 전체에 건 뒤 coalesce(nullif(group_key,''),nullif(external_order_no,''),'link:'||id)로 GROUP BY 한다 — 건당 수 KB짜리 JSONB를 전 행 풀어 보는 무인덱스 스캔+집계다. 바로 옆 _place_pending_clause 독스트링이 '**JSONB 로 필터하면 인덱스 없는 스캔이 되고, 그건 이 저장소의 hot path 금지 규칙이다(T16-B)**'라고 못 박아 둔 그 규칙이고, CLAUDE.md 성능 절의 'hot path 쿼리: JSONB 인덱스 없이 금지'와도 정면으로 부딪힌다.
  - 고칠 방법: 두 부분 인덱스를 담은 alembic 리비전을 추가한다(down_revision은 착수 시점 heads=merge_drawq_naverfail 확인 후 부착, PostgreSQL 전용 실행은 naverfail_00 모양을 따른다). 조건식은 손으로 적지 말고 str(_dispatch_pending_clause().compile(dialect=postgresql.dialect(), compile_kwargs={'literal_binds': True}))로 뽑아 CAST(... AS VARCHAR) 형태 그대로 붙인다. 그다음 계약 §4.5대로 EXPLAIN 원문과 행 수를 원장에 남긴다 — Seq Scan이 나와도 술어를 인덱스에 맞춰 비틀지 말 것(칩 숫자와 행 표시가 갈린다).
- **major** `C:/tmp/foms-naver-status/templates/admin/naver_workbench.html:830 (+ foms/web/admin/naver_ingest.py:506 _history_dispatch)`
  - 무엇: 발송 어긋남 경고가 **어긋나지 않은 링크의 시각**을 찍는다. _history_dispatch는 ours_at을 전 멤버 중 최솟값으로, mismatch를 any()로 접는데, 템플릿은 그 둘을 한 문장에 붙여 '우리 발송 {dispatch_ours_at} · 네이버 기록 없음'을 낸다. 직접 호출로 재현: members=[{ours 16:02, naver 없음(mismatch)}, {ours 09:00, naver 12:03}] → {'ours_at':'2026-08-26 09:00','mismatch':True}. 화면은 '우리 발송 2026-08-26 09:00 · 네이버 기록 없음'이라 적는데 그 09:00 발송은 네이버가 기록한 건이다. 워커가 링크를 건별로 처리하고 네이버가 일부만 기록하면 실제로 나오는 모양이고, 되돌릴 수 없는 호출의 유실 자리를 가리키는 문장이라 틀린 시각의 값이 특히 나쁘다. 계약이 클레임 축에 대해 경고한 '라벨은 A 링크, 단계는 B 링크' 함정을 발송 축에서 그대로 밟았다.
  - 고칠 방법: _history_dispatch에 mismatch_ours_at = min(view['ours_at'] for view in views if view['mismatch'] and view['ours_at']) 를 따로 집계해 행에 싣고, 경고 줄은 그 값만 쓴다. 아니면 경고 줄에서 시각을 떼고 '네이버 기록 없는 발송 N건'으로 바꾼다.
- **major** `C:/tmp/foms-naver-status/foms/web/admin/naver_ingest.py:405 (_history_member_axes) · 604~712 (_history_group_axes)`
  - 무엇: 아무도 안 읽는 필드 6종과 그것을 만드는 링크당 파싱이 남았다. _history_member_axes가 링크마다 _return_axis_view(link)를 부르고(extract_return_axis 순회 1회 + format_datetime_kst 3회), 그 결과가 행 dict의 claim_kind·claim_reason·claim_done_text·claim_refund_expected_text·claim_collect_done_text·claim_refund_done 으로 나간다. templates/*.html·static/js 전수 grep 결과 이 6개를 읽는 자리가 **한 곳도 없다**(템플릿이 실제로 읽는 클레임 필드는 claim_label·claim_phase·claim_blocking 뿐이고, claim_kind는 _history_naver_axis가 claim dict로 쓰지 행 필드로 쓰지 않는다). 계약 §2.1·§2.2 목록에도 없는, 추가됐다가 배선되지 않은 값이다. 쪽당 50집 × 멤버 수만큼 헛일이 붙는다.
  - 고칠 방법: _history_member_axes에서 _return_axis_view 호출과 claim_reason·claim_*_at 4종을 걷어내고, _history_claim·_history_group_axes의 대응 키도 지운다. 반품 축 표시를 나중에 실을 계획이면 그때 함께 넣는다(지금은 계약 §8이 범위 밖으로 뺀 자리다).
- **major** `C:/tmp/foms-naver-status/foms/web/admin/naver_ingest.py:92-105 · templates/admin/naver_workbench.html:639`
  - 무엇: 칩 낱말이 두 벌로 관리된다. 서버에 _HISTORY_STATUS_CHIP_SPECS → HISTORY_STATUS_CHIPS 를 만들고 주석에 '칩 라벨이 배지 낱말에서 파생돼야… 손으로 두 벌 적으면 조용히 갈린다'라고 적어 놓았는데, 정작 템플릿은 {% for key, label in [('COLLECTED','받아옴 · 주문 전'), ('LINKED','주문 만듦'), ('PENDING_REVIEW','확인 필요'), ('FAILED','받기 실패')] %} 로 같은 네 낱말을 손으로 다시 적는다. _history_view는 HISTORY_STATUS_CHIPS를 컨텍스트에 넣지도 않는다 — 전수 grep 결과 이 상수의 소비자는 계약 테스트와 독스트링뿐이라, 만든 SSOT를 만들자마자 우회한 꼴이고 계약 §2.4('템플릿은 HISTORY_STATUS_CHIPS 를 그대로 돌려 칩을 낸다')와도 어긋난다. 테스트가 두 벌의 일치를 물어 주는 덕에 지금 당장 갈리지는 않지만, 그건 SSOT가 아니라 드리프트 감시다.
  - 고칠 방법: _history_view 반환에 'status_chips': HISTORY_STATUS_CHIPS 를 넣고 템플릿 루프를 `{% for key, label in history.status_chips %}` 로 바꾼다(href·aria-pressed 로직은 그대로). 그러면 상수가 실제 SSOT가 되고 테스트는 회귀 감시로 남는다.
- **minor** `C:/tmp/foms-naver-status/tests/services/integrations/test_naver_history_status_axes.py`
  - 무엇: 테스트 자체는 헛 테스트가 아니다 — 실제 라우트를 열어 td.wb-hist__status 를 클래스로 집고 태그를 벗겨 낱말로 단언하며, 존재하지 않는 FK id를 쓰지 않고 실제 Order 행을 만들어 붙인다(15개 전부 통과, 통합 스위트 1029개도 통과 확인). 다만 화면에서 가장 센 주장을 하는 새 분기들이 통째로 비어 있다: foms_state=='closed'(soft delete된 주문을 '주문 만듦'이라 말하지 않는다), fail 축 렌더 전부('발주확인 실패'·'발송처리 실패'·.wb-st__warn·cancel/return 특례), dispatch_moot→'발송 안 함', shipping_due_over_days→'발송기한 N일 지남'·'네이버 자동 취소 가능', dispatch_naver_at 부속 문구('네이버 확인됨'/'판매자센터에서 직접'). fail_reason 픽스처는 읽기전용 테스트에서 만들어만 두고 아무 단언도 걸지 않는다.
  - 고칠 방법: 위 5개 분기에 각각 케이스를 더한다. 특히 closed(주문 status='DELETED' 또는 deleted_at 세팅)와 dispatch_moot는 판정표에서 순서가 앞서는 자리라 조용히 뒤집혀도 아무도 모른다.
- **minor** `C:/tmp/foms-naver-status/foms/web/admin/naver_ingest.py:532 (_history_shipping_due)`
  - 무엇: 같은 값의 두 파생 중 하나만 파싱 실패를 방어한다. over_days는 try/except (TypeError, ValueError)로 감쌌지만 shipping_due_text = due[5:] 는 무조건 슬라이스다. 직접 호출로 확인: due='20260902' → {'shipping_due_text': '902', 'shipping_due_over_days': 0} → 화면에 '발송기한 902'가 찍힌다. 못 읽는 값을 '지났다'고 단정하지 않겠다는 except의 의도가 옆 필드에서 새는 셈이다.
  - 고칠 방법: 날짜를 한 번만 파싱해서 성공했을 때만 두 값을 만든다 — parsed = date.fromisoformat(due) 성공 시 text = parsed.strftime('%m-%d'), 실패하면 text도 '' 로 두고 원문은 shipping_due에만 남긴다.
- **minor** `C:/tmp/foms-naver-status/templates/admin/naver_workbench.html:730-786`
  - 무엇: 계약 §2.3-B·C의 판정표(발주확인 5줄·발송 8줄)가 Jinja {% set %} 사슬 약 50줄로 템플릿에 들어갔다. 재료(place_done_count·dispatch_*·fail·dispatch_moot)는 이미 전부 행에 실려 있어 서버에서 계산할 수 있는데도 그렇다. 결과는 (1) 이 판정을 HTML 문자열 매칭 말고는 시험할 방법이 없고 (2) naver-workbench.css 주석이 같은 부품을 처리 탭(220px)·도크(358px)에도 실을 것이라고 명시해 두었는데, 그때 이 사슬이 다른 템플릿으로 복사되면 '같은 판정을 두 곳이 각자 계산'하는 상태가 된다. 지금은 아직 한 벌이라 중복은 아니지만 그렇게 되기 직전의 모양이다.
  - 고칠 방법: _history_group_axes가 place_state/place_text/dispatch_state/dispatch_text 를 계산해 행에 싣고, 템플릿은 상태 키→클래스 대응만 남긴다(계약 §5의 '레인 C가 매핑'은 클래스 대응을 뜻하고 판정 자체를 뜻하지 않는다). 그러면 판정표가 파이썬 단위 테스트로 직접 잠긴다.
- **minor** `C:/tmp/foms-naver-status/tests/services/integrations/test_naver_origin_cleanup.py:69-113,185-190`
  - 무엇: 계약 §6이 '핀 문자열 한 줄만' 고치라고 배분한 파일에 collected_at 파라미터 신설과 호출부 2곳 변경이 함께 들어왔다. 변경 내용 자체는 타당하다(read_at = max(refreshed_at, created_at)이라 created_at을 안 못 박으면 두 링크가 같은 밀리초 눈금에 떨어질 때만 판정이 뒤집혀 간헐 실패가 된다 — 증상 덮기가 아니라 결정성 확보다). 다만 이번 변경과 인과가 없는 수정이 아무 표시 없이 딸려 왔고, 원장에도 안 적혔다.
  - 고칠 방법: 이 파일 변경을 별도 커밋으로 떼고 커밋 메시지에 '이번 변경과 무관한 간헐 실패 결정화'라고 밝힌다. 그대로 둘 거면 원장 §기록에 한 줄 남긴다.
- **minor** `C:/tmp/foms-naver-status/templates/admin/naver_workbench.html:833`
  - 무엇: '네이버 자동 취소 가능' 경고 줄은 계약 §3.2 부속 문구 표(5줄)에 없는 신규 문장이고, shipping_due_over_days > 0 하나로 발동한다. 네이버가 발송기한 초과 건을 실제로 자동 취소하는지에 대한 근거(상수·문서 참조·테스트) 가 코드 어디에도 없다. 운영자가 이 문장을 보고 판매자센터 확인을 건너뛸 수 있는 종류의 주장이다.
  - 고칠 방법: 근거 문서(NAVER_FIELD_INVENTORY 등) 링크를 주석에 달고 계약 §3.2 표에 등재하거나, 근거가 없으면 문장을 빼고 '발송기한 N일 지남' 배지만 남긴다.
- **minor** `C:/tmp/foms-naver-status/foms/web/admin/naver_ingest.py:558 (_history_foms_state) · templates/admin/naver_workbench.html:661`
  - 무엇: 있는 것을 없을 수도 있다고 가정하는 방어 코드가 두 곳 있다. (1) getattr(order, 'status', '') / getattr(order, 'deleted_at', None) — 둘 다 models.py:33,35의 실제 컬럼이라 getattr 기본값은 영영 안 쓰이고, 컬럼명이 바뀌면 예외 대신 조용히 'linked'로 떨어진다. (2) {{ history.dispatch_pending_count or 0 }} — _history_view가 항상 채우는 키다. 둘 다 '없을 리 없는 것'에 대한 미봉책이라 나중에 진짜 결함을 삼킨다.
  - 고칠 방법: order.status / order.deleted_at 로 직접 접근하고(order is None 가드는 유지), 템플릿의 or 0 을 뺀다.

---

## 10. 수정 라운드 (2026-08-30) — 실행 결과 · 남은 것

§9 의 findings(착수 게이트 5 + 최종 2판정 FAIL) 를 닫는 라운드다. **커밋·푸시는 하지 않았다** —
여러 에이전트가 `C:/tmp/foms-naver-status` 한 트리를 공유해서 커밋은 사람이 한다.

### 10.1 이번 라운드에서 **실제로 돌린** 명령과 꼬리 출력

전부 `cd C:/tmp/foms-naver-status && pwd && <명령>` 으로 돌렸다 — 워크트리 cwd 는 턴 경계에서
리셋되고, `C:/DEV/FOMS` 에서 돌면 그 트리엔 네이버 코드가 없어 **가짜 초록**이 난다.

| task | 명령 | 꼬리 출력(원문) |
|---|---|---|
| 공통 | `python -c "import app; print('APP_OK')"` | `APP_OK` |
| T1 | `python -m pytest tests/services/integrations/test_naver_workbench.py -q` | `85 passed in 2.40s` |
| T2 | `python -m pytest tests/services/integrations/ -q -k "workbench or fulfillment or dispatch"` | `331 passed, 707 deselected in 6.91s` |
| T3 | `python -m pytest tests/services/integrations/test_naver_workbench.py tests/services/integrations/test_naver_workbench_history_open.py tests/services/integrations/test_naver_workbench_history_detail.py -q` | `106 passed in 2.76s` |
| T4 | `python -m pytest tests/services/integrations/test_naver_origin_cleanup.py tests/services/integrations/test_naver_workbench_async_result.py -q` | `47 passed in 0.98s` |
| T5 | `python -m pytest tests/services/integrations/test_naver_admin_surface.py tests/services/integrations/test_naver_workbench.py -q` | `115 passed in 3.16s` |
| T6 | `python -m pytest tests/services/integrations/test_naver_history_status_axes.py -q` | `24 passed in 1.03s` |
| T7 | `python -m pytest tests/performance/test_perf_regression_guard.py -q` | `5 passed in 0.17s` |
| T8 | `python -m pytest tests/services/integrations/ -q` | `1038 passed in 16.91s` |
| T8 | `python tools/harness/verify_result.py --json` | `"success": true` · `"app_import": {… "ok": true, "exit_code": 0 …}` |
| T8 | `pwsh -File scripts/ops/pre_push_smoke.ps1` | `324 passed, 1 warning in 13.33s` → `[OK] Pytest subset (18 targets)` → `=== PRE-PUSH SMOKE PASSED ===` (exit 0) |
| 부수 | `python -m pytest tests/postgres/test_migration_chain.py -q` | `1 skipped in 0.11s` — **이 환경에 PG 레인이 없다**(`FOMS_TEST_DATABASE_URL` 미설정) |
| 부수 | `python -m alembic heads` | `naverdisp_00 (head)` — **단일 head** |
| 문서 | `python -m pytest tests/services/integrations/ -q -k "docscope or docs"` | `2 passed, 1036 deselected in 0.43s` |

새 계약 테스트는 `docs/` 를 **읽지 않는다**(모듈 docstring 이 경로를 언급할 뿐이다) —
`ci.yml` 서브셋 등재(CI-DOCSCOPE-01)는 필요 없다. 계약 §6 의 판단 그대로다.

### 10.2 T7 성능 — 어디까지 확정됐고 무엇이 안 됐나

**확정된 것**

- 부분 인덱스 2벌이 **실 PostgreSQL 17.9** 에 실제로 만들어졌다(`pg_indexes` 원문 — 10.6).
  조건식의 `CAST(… AS VARCHAR)` 모양까지 술어 렌더 결과와 같다.
- 새 마이그레이션 `naverdisp_00` 의 `upgrade()` 가 **실 PG 에서 진짜로 돌았다**
  (`create_all` → `alembic stamp merge_drawq_naverfail` → `alembic upgrade head` 경로라
  인덱스를 `create_all` 이 만든 것이 아니다).
- 성능 가드 `tests/performance/test_perf_regression_guard.py` → `5 passed`.

**미확정 1건 — 승격 전에 반드시 닫아라**

원장에 붙은 `EXPLAIN (ANALYZE, BUFFERS)` 원문이 **잘려 있다**. 남아 있는 것은
`Aggregate → Group → Sort` 세 노드까지이고 마지막 줄이 `rows=6000 loop` 에서 끊긴다 —
**그 아래 스캔 노드가 없다**(10.6 그대로). 계약 §4.3 이 정한 판정선은
"`EXPLAIN` 출력에 `ix_external_order_link_dispatch_pending` 이름이 뜬다" 인데,
**이 원장 텍스트만으로는 그 줄을 확인할 수 없다.**
EXPLAIN 레인의 결론 문장은 "두 부분 인덱스 모두 실제로 먹는다 · Seq Scan 없음" 이지만,
그 결론을 떠받치는 줄이 여기 없다 — 결론만 근거로 승격하지 마라.
클러스터는 이미 지워졌다(직접 확인: `C:/tmp/pgexplain5442` 없음 · 포트 5442 닫힘).
**EXPLAIN 을 1회 재현해 스캔 노드 줄을 이 절에 붙이는 것**이 T7 의 마지막 한 칸이다(재현 절차 10.6).

**미실행 1건 (`BLOCKED`)**

이력 탭 **TTFB 변경 전후 측정**. 코드가 아직 커밋도 안 된 상태라 스테이징 배포본이 없고,
로컬에는 이 화면을 대표할 실데이터가 없다. **배포 후 실화면에서** 재고 그 값을 여기 적는다.

### 10.3 T6 계약 테스트 — 잠근 것과 **남은 구멍**

`tests/services/integrations/test_naver_history_status_axes.py` = 24 케이스, 전부 green.
단언은 실제 라우트를 열어 `td.wb-hist__status` 를 **클래스로** 집고 태그를 벗겨 **낱말로** 건다
(행 dict 키로 걸지 않는다 — 이번 라운드에 클레임 필드 이름이 바뀌었다, 계약 §10.2).

이번 라운드에 **새로 닫은 것**: 섞인 집의 관계 번호 · 번호 없는 관계 배지 ·
어긋남 경고 시각 2케이스 · 클레임 확정 날짜/수거·환불 꼬리 · 미확정 사유·환불 예정 ·
날짜도 사유도 없는 클레임(배지만) · 칩 라벨이 서버 상수를 따라감 ·
클레임 없는 링크에서 `_return_axis_view()` 미호출 · `발송기한 N일 지남`(+ `네이버 자동 취소 가능` 부재).

**아직 안 닫힌 것** — §9 의 CEO 최종 판정(코드 품질) minor 가 지적했고 이번에도 남았다:

| 안 잠근 분기 | 왜 위험한가 |
|---|---|
| `foms_state == "closed"` → `주문 접음` | 판정표에서 `linked` 보다 **앞선** 자리다. 조용히 뒤집히면 접힌 주문이 `주문 만듦` 으로 살아 있는 것처럼 보인다 |
| fail 축 렌더 전부 — `발주확인 실패` · `발송처리 실패` · `.wb-st__warn` 사유 줄 · cancel/return 특례(`{action_label} 실패 · `) | 파이프 색과 경고 줄을 동시에 정하는 분기다. `fail_reason` 픽스처는 517행에서 **만들기만** 하고 단언이 없다 |
| `dispatch_moot` → `발송 안 함` | 여기가 뒤집히면 `발송처리 할 차례`(주황)가 되어 **되돌릴 수 없는 호출**을 부른다 |
| 발송 부속 문구 `네이버 확인됨` / `판매자센터에서 직접` | 두 문장이 서로 반대 사실을 말한다 |

직접 확인: 위 여섯 낱말을 `test_naver_history_status_axes.py` 에서 `grep` 하면 **0건**이다.

### 10.4 T8 — 왜 `BLOCKED` 인가

검증은 전부 통과했다(10.1). 남은 것은 **사람 몫**이다:

1. **커밋·푸시 안 함**(지시대로). 공유 트리라 에이전트가 커밋하면 남의 WIP 을 삼킨다.
   커밋할 때는 `git commit -F <메시지파일> -- <경로>` 로 **경로를 지정**한다.
   신규(untracked) 파일: `migrations/versions/naverdisp_00_history_chip_indexes.py` ·
   `tests/services/integrations/test_naver_history_status_axes.py` ·
   `docs/design/mockups/naver-triage-status-column.html` · `…--table.html` ·
   본 원장 · 동결 계약 문서.
   수정(tracked) 파일: `foms/web/admin/naver_ingest.py` · `templates/admin/naver_workbench.html` ·
   `static/css/admin/naver-workbench.css` · `tests/services/integrations/test_naver_origin_cleanup.py` ·
   `tests/services/integrations/test_naver_workbench_async_result.py` ·
   `docs/harness/foms_failopen_inventory.json`.
2. `deploy` push 뒤 `gh run list` 로 **커밋별 전 워크플로**가 green 인지 확인한다 —
   `ci_watch` 는 1개만 본다. 특히 새 마이그레이션이 있으므로 **PG 레인(MIGCHAIN-01)** 을 본다:
   `CREATE INDEX` 의 `WHERE` 안 `CAST(… AS VARCHAR)` 가 immutable 로 받아들여지는지는 거기서 확정된다.
3. 스테이징 실화면에서 목업 20케이스 중 **실데이터로 재현되는 것**을 눈으로 확인한다.
4. **production 승격은 범위 밖**(사용자 명시 요청 시에만).

### 10.5 사람이 내린 결정 7건 (에이전트가 다시 고르지 않는다)

1. 클레임 날짜·사유는 **목업대로 화면에 낸다**(CEO 가 준 (a)안). 빼는 선택지는 없다.
2. 발송 어긋남 경고 시각은 **어긋난 링크의 시각만** 쓴다(별도 집계).
3. `_return_axis_view()` 는 **클레임이 있는 멤버에만** 부른다(전 링크 파싱 금지).
4. 칩 라벨은 **서버 상수 단일 출처**로 만든다(템플릿이 두 벌째 적지 않는다).
5. `네이버 자동 취소 가능` 문구는 **지운다** — 근거가 코드 어디에도 없다.
   배지 `발송기한 N일 지남` 은 사실이니 남긴다.
6. 발주확인·발송 판정표는 **서버로 옮긴다**(템플릿 `{% set %}` 사슬 제거).
7. `test_naver_origin_cleanup.py` 의 `collected_at` 변경은 **되돌리지 않는다** —
   계약 §6 에 예외로 등재했다.

### 10.6 EXPLAIN 증거 (실 PostgreSQL 17.9) — 레인 원문 그대로

> **아래는 EXPLAIN 레인이 남긴 원문이다. 마지막 코드 블록이 `rows=6000 loop` 에서 잘려 있고
> 스캔 노드가 없다 — 10.2 의 미확정 1건이 바로 이 자리다.** 재현하려면 이 절의 "레인 구성" 을
> 그대로 따르면 된다(클러스터는 검증 후 지웠다: `C:/tmp/pgexplain5442` 없음 · 포트 5442 닫힘 —
> 이 원장을 쓰면서 직접 확인).

실 PostgreSQL 17.9 에서 떴다. 결론: **두 부분 인덱스 모두 실제로 먹는다. Seq Scan 없음.**

#### 레인 구성 (그대로 재현 가능)
- 기존 로컬 5440 클러스터는 **깨져 있어 못 썼다** — 원장 423줄에 이미 기록된 함정이 그대로 재현.
  `CREATE DATABASE` → `could not open file "base/1/4171"`, `TEMPLATE template0` 우회도
  `could not open file "base/4/pg_filenode.map"` (template0 까지 소실). 코드 무관, 클러스터 파손.
- 그래서 `initdb` 로 격리 클러스터를 새로 만들었다: `C:/tmp/pgexplain5442`, 포트 5442, PG 17.9.
  (주의: `pg_ctl start` 를 샌드박스 안에서 하면 forked backend 가 `0xC0000142`
  STATUS_DLL_INIT_FAILED 로 죽는다 — 서버는 샌드박스 밖에서 띄워야 한다.)
- throwaway DB `foms_test_explain_da4217f065` → `Base.metadata.create_all`
  → `alembic stamp merge_drawq_naverfail` → `alembic upgrade head`.
  즉 **naverdisp_00 의 upgrade() 가 실 PG 에서 진짜로 돌았다**(create_all 이 만든 게 아니다).
- 검증 후 클러스터 정지 + 데이터 디렉토리 삭제 완료(잔재 0, 포트 해제 확인).

#### 인덱스가 실제로 만들어졌는지 (pg_indexes 원문)
```
ix_external_order_link_dispatch_pending | CREATE INDEX ... USING btree (channel, group_key) WHERE (((COALESCE((((triage_state -> 'fulfillment'::text) ->> 'dispatched_at'::text))::character varying, ''::character varying))::text = ''::text) AND ((COALESCE((((raw_snapshot -> 'delivery'::text) ->> 'sendDate'::text))::character varying, ''::character varying))::text = ''::text))
ix_external_order_link_relation_pair    | CREATE INDEX ... USING btree (channel, group_key) WHERE ((relation)::text = ANY ((ARRAY['ADDON'::character varying, 'REPAY'::character varying])::text[]))
```

#### 대상 쿼리 (`_dispatch_pending_group_count()` 가 실제로 내는 SQL, literal_binds 렌더)
```sql
SELECT count(*) AS count_1
FROM (SELECT coalesce(nullif(external_order_links.group_key, ''), nullif(external_order_links.external_order_no, ''), 'link:' || CAST(external_order_links.id AS VARCHAR)) AS gk
FROM external_order_links
WHERE external_order_links.channel = 'NAVER' AND coalesce(CAST(((external_order_links.triage_state -> 'fulfillment') ->> 'dispatched_at') AS VARCHAR), '') = '' AND coalesce(CAST(((external_order_links.raw_snapshot -> 'delivery') ->> 'sendDate') AS VARCHAR), '') = '' GROUP BY coalesce(nullif(external_order_links.group_key, ''), nullif(external_order_links.external_order_no, ''), 'link:' || CAST(external_order_links.id AS VARCHAR))) AS anon_1
```

#### 시드 (실데이터 모양 흉내)
50,000 링크 / 그중 발송처리 전 6,000 (12%) / heap 18 MB / 부분 인덱스 256 kB.
발송 완료 행엔 `raw_snapshot.delivery.sendDate` + `triage_state.fulfillment.dispatched_at` 을,
미발송 행엔 둘 다 없게 넣었다. `ANALYZE` 후 측정.

#### EXPLAIN (ANALYZE, BUFFERS) — 50k 행, 발송처리 남음 칩  ★본 판정★
```
 Aggregate  (cost=8.35..8.36 rows=1 width=8) (actual time=5.445..5.447 rows=1 loops=1)
   Buffers: shared hit=1440
   ->  Group  (cost=8.32..8.34 rows=1 width=32) (actual time=4.699..5.349 rows=3001 loops=1)
         Group Key: (COALESCE(NULLIF((external_order_links.group_key)::text, ''::text), NULLIF((external_order_links.external_order_no)::text, ''::text), ('link:'::text || ((external_order_links.id)::character varying)::text)))
         Buffers: shared hit=1440
         ->  Sort  (cost=8.32..8.33 rows=1 width=32) (actual time=4.698..4.868 rows=6000 loop
```

> ⚠ **여기서 원문이 끊긴다.** `Sort` 아래의 스캔 노드(인덱스 이름이 뜨는 줄)가
> 원장에 남지 않았다 — 10.2 참조. 이 잘림은 문서화 과정에서 생긴 것이고, 아래 문장을 지우거나
> 없는 줄을 채워 넣지 않았다.


### 10.7 레인이 남긴 것 (원문 요약 — 판단이 필요한 자리)

**레인 M (마이그레이션)**

- 계약 §4.3 조건식 갱신 필요 → **이 라운드에서 계약을 고쳤다**(CAST 포함, 계약 §4.3·§10.1-1).
  계약 §4.4(relation) 는 렌더 결과와 일치해 손댈 것이 없었다.
- 실 PG `upgrade→downgrade` 왕복은 **레인 M 시점에는 미검증**이었다.
  그 뒤 EXPLAIN 레인이 실 PG 17.9 에서 `upgrade head` 를 돌렸다(10.6). `downgrade` 왕복은 여전히
  CI PG 레인이 처음 확인한다.
- 런타임 predicate 매칭 실측: psycopg2 클라이언트 사이드 바인딩이라 `''` 가 리터럴로 전개될
  것으로 **코드 독해상** 보이지만 실 PG `EXPLAIN` 으로 확인하지 않았다 — 10.2 재현 때 함께 본다.
- `git commit/push` 안 함. 신규 마이그레이션은 untracked 로 남겼다.

**레인 S (서버 + 템플릿)**

- 행 dict 의 클레임 필드가 `claim_badge_text`·`claim_tail_text` 두 개로 줄었다
  (`claim_label`·`claim_phase` 는 유지). 계약 §10.2 에 등재했다.
- 목업 E16 꼬리의 `수거중` 조각은 내지 않는다 — 파생할 필드가 없고 `claimStatus=COLLECTING` 이면
  이미 배지 라벨이다. 계약 §3.3 갈림표에 등재했다.
- 계약 문서 갱신 요청 4건(행 필드 2종 축소 · 배지 확정 날짜 · 사유 출처 `claim_reason_text` ·
  `collected_at` 예외) → **전부 계약에 반영했다**(§2.2·§3.3·§6·§10).

**레인 T (계약 테스트)**

- **취소 확정 집은 확정 날짜도 `환불 완료` 도 못 낸다.** 꼬리 재료가 전부
  `_return_axis_view` → `mapping.extract_return_axis` 에서 오는데 그 함수의
  `RETURN_BLOCK_KEYS = ("returnInfo","return","exchange")` 가 `cancel` 블록을 **일부러 뺀다**
  (취소 블록의 환불 필드가 반품 진행으로 새어 스테이징 344 링크 중 50건이
  "취소 완료 배지 + 반품 진행 본문" 이던 결함 때문). 취소 완료 시각을 담는 네이버 필드
  `cancelCompletedDate` 는 `docs/specs/2026-08-28-naver-claim-phase-labeling_SPEC.md:33` 에
  실물로 언급돼 있으나 저장소에서 읽는 코드가 0곳이다.
  → 없는 값을 지어내지 않는 **현재 동작**을 테스트로 잠갔고, 계약 §3.3 갈림표·§10.1-6 에 등재했다.
  완전히 목업대로 가려면 취소 전용 완료시각 파생이 필요하다 — **별건**(10.8-2).
- 부수 관측: `_render_workbench` 는 `?tab=all` 에서도 `_pane_context(...)` 를 부르므로 처리 큐에
  확인 안 된 건이 있으면 이력 탭 진입 시 pane 이 **링크 1건**의 반품 축을 판다.
  "이력 탭에서 반품 축 파싱 0회" 는 정확히는 **"이력 표가 0회"** 다.
- `_link()` 픽스처에 `return_block`·`reviewed` 인자를 더했다(레인 T 산출물).
- `git commit/push` 하지 않았다.

### 10.8 알려진 어긋남 — 승격 전에 사람이 읽을 것

1. **옛 수집 화면과 워크벤치가 다른 낱말을 쓴다** — 함정 5. 기간과 낱말은 10.9.
2. **취소 확정 건의 날짜·환불 완료 미표시** — 10.7 레인 T. 계약 §3.3 갈림표에 등재됨.
   닫으려면 `cancelCompletedDate` 파생을 서버에 새로 넣어야 한다(이번 범위 밖).
3. **칩 숫자는 전역, `history.total` 은 필터 적용값**이다(기존 동작). 이번에 필터 파라미터가
   2개 → 4개로 늘어 칩을 겹쳐 거는 일이 흔해진다 — 두 칩을 함께 누르면 목록 길이가
   **어느 칩 숫자와도 안 맞는다**. 회귀는 아니지만 사람이 헷갈릴 자리다.
4. **`발송처리 남음` 칩 모집단에 FAILED·PENDING_REVIEW 수집분도 든다**(발송 기록이 없으므로).
   그 행들은 화면에서 `네이버 처리 없음` 으로 뜨는데 칩 꼬리는 `· 취소 포함` 뿐이라 라벨과
   모집단이 살짝 갈린다. 옆 칩 6번도 같은 성질이라 회귀는 아니다.
5. **`delivery` 경로 어긋남 1개(수용)** — 파이썬 `extract_delivery` 는
   `productOrder.delivery` → `order.delivery` 로 내려가지만 SQL 은 **최상위만** 본다.
   수집 파이프라인이 저장하는 모양은 최상위라 실데이터는 같다(계약 §4.3).
6. **`CREATE INDEX` 는 `CONCURRENTLY` 가 아니다** — 배포 중 `external_order_links` 쓰기를 잠깐 막는다.
   현재 규모면 무시할 수준이지만 수집 워커와 겹치면 재시도가 뜬다. `naverfail_00` 선례와 같은 모양이다.
7. **`down_revision = merge_drawq_naverfail` 은 2026-08-30 기준값**이다. 승격 체인 전제는 하루면
   낡는다 — 승격 직전에 `python -m alembic heads` 로 다시 확인한다.

### 10.9 두 화면이 다른 말을 쓰는 기간 (함정 5 — 명시)

**시작**: 이 변경이 `deploy`(스테이징)에 배포되는 시점.
**끝**: 옛 수집 화면(`templates/admin/naver_ingest.html`)이 닫히거나 어휘가 통일되는 시점.
**끝 날짜는 아직 없다 — 사람이 정할 항목이다.** 안 정하면 영구히 두 말이 된다(CEO 지적).

갈리는 낱말(실측):

| 자리 | 옛 수집 화면 / 처리 탭 | 워크벤치 이력 탭 |
|---|---|---|
| 수집 상태 | `수집됨(생성 전) N주문` (`naver_ingest.html:90,146`) | 칩 `받아옴 · 주문 전 N주문` · 배지 `받아옴` |
| 생성 상태 | `생성됨` (`naver_ingest.html:84`) | `주문 만듦` |
| 발주확인 진행 | `발주확인 전` (처리 탭 칩 `naver_workbench.html:278`, 행 배지 `:451`, 옛 화면 `:100,161`) | 파이프 `발주확인 할 차례` / `발주확인 N/M` / `발주확인 완료` |
| 발송 | (없음 — 옛 화면·처리 탭에 발송 축이 없다) | 파이프 `발송처리` / `발송처리 N/M` / `발송처리 완료` / `발송 안 함` |

**맞춰 둔 것**: `추가결제·재결제` 는 처리 탭 칩(`:279`)과 **가운뎃점 표기를 지금 통일했다**
(띄어쓰기 없음). 같은 화면에 같은 낱말이 두 표기로 있으면 눈이 다른 것으로 읽는다.

**왜 지금 통일하지 않았나**: 옛 화면은 게이트가 켜지면 리다이렉트로 닫히는 화면이고,
`tests/services/integrations/test_naver_admin_surface.py:217` 이 그 화면의 옛 라벨
(`수집됨(생성 전) 2주문`)을 잠그고 있다. 처리 탭 통일은 이력 탭과 다른 술어(작업 대상 vs 표 필터)를
건드리므로 **별건**이다(§7 범위 밖).


## 11. CEO 재판정 (2026-08-30 · 2차) — 결과와 남은 minor 전량

### 코드 품질 (근본원인·성능·프로젝트 규칙·테스트 실효성·죽은 코드/중복) → `PASS_WITH_NOTES`

> 1차 blocker 1 + major 3 은 전부 실제로 닫혔다(마이그레이션 단일 head·조건식 글자 일치를 직접 렌더로 대조, 어긋남 경고는 함수 직접 호출로 mismatch_ours_at=16:02 vs ours_at=09:00 재현, `_return_axis_view` 는 claim_label 있을 때만 호출+양성 대조군 테스트, 칩은 상수 monkeypatch 로 화면이 따라오는 것까지 확인) — 남은 것은 minor 7건뿐이라 PASS_WITH_NOTES. 다만 두 건은 방금 고친 결함이 다른 자리에서 되살아난 것이다: 클레임 날짜 `[5:10]` 무방비 슬라이스(원문 'PENDING_REFUND_2026' → 배지 `반품 완료 NG_RE` 재현)와 발송 축의 아무도 안 읽는 행 필드 3종, 그리고 '판정은 전부 서버' 라고 적어 놓고 §3.2 부속 문구 사슬이 템플릿에 남은 주석 드리프트. 검증 꼬리 원문: `python -m pytest tests/services/integrations/ -q` → `1038 passed in 17.90s`, `python -c "import app; print('APP_OK')"` → `APP_OK`, `python -m alembic heads` → `naverdisp_00 (head)`.

닫힌 것으로 확인: 9건
- (닫힘) blocker — 부분 인덱스 마이그레이션 부재: migrations/versions/naverdisp_00_history_chip_indexes.py 신설 확인. `python -m alembic heads` → `naverdisp_00 (head)` 단일 head, down_revision=merge_drawq_naverfail 실재(merge_drawqueue_naverfail_heads.py), PostgreSQL 전용 가드 + downgrade 존재, models live import 없음. 조건식은 내가 직접 렌더해 대조 — `_dispatch_pending_clause()` literal_binds 렌더 = `coalesce(CAST(((external_order_links.triage_state -> 'fulfillment') ->> 'dispatched_at') AS VARCHAR), '') = '' AND coalesce(CAST(((external_order_links.raw_snapshot -> 'delivery') ->> 'sendDate') AS VARCHAR), '') = ''` 이고 마이그레이션 문자열은 테이블 수식어만 뗀 동일 글자다.
- (닫힘) major — 어긋남 경고가 다른 링크 시각을 찍던 결함: `_history_dispatch` 에 `mismatch_ours_at` 별도 집계 신설(naver_ingest.py:550-560), 템플릿 경고 줄이 `row.dispatch_mismatch_ours_at` 만 쓴다(naver_workbench.html:797). 직접 호출 재현 — members=[{ours 16:02, naver 없음, mismatch}, {ours 09:00, naver 12:03}] → `{'ours_at': '2026-08-26 09:00', 'mismatch_ours_at': '2026-08-26 16:02'}`. 옛 코드였으면 화면이 09:00 을 찍는다.
- (닫힘) major — 죽은 반품축 필드 6종 + 링크당 파싱: `_return_axis_view` 는 `summary['claim_label']` 이 있을 때만 부른다(naver_ingest.py:448, 없으면 `_EMPTY_RETURN_AXIS` 자리값). 행 dict 에서 claim 원재료 6종을 걷어내고 `claim_badge_text`·`claim_tail_text` 로 접었다. 계측 테스트(test_links_without_a_claim_never_parse_the_return_axis)가 monkeypatch 카운터 + 같은 모집단 안 양성 대조군까지 갖췄다.
- (닫힘) major — 칩 낱말 이중 관리: `_history_view` 가 `status_chips: HISTORY_STATUS_CHIPS` 를 컨텍스트에 싣고(naver_ingest.py:2374) 템플릿은 `{% for key, label in history.status_chips %}` 로 돈다. 상수를 monkeypatch 로 **바꿔** 화면이 따라오는지 무는 테스트(test_chip_labels_follow_the_server_constant)까지 있어 드리프트 감시가 아니라 단일 출처 증명이다.
- (닫힘) minor — `_history_shipping_due` 무방비 슬라이스: 날짜를 한 번만 파싱하고 실패하면 표시값도 빈 값(naver_ingest.py:585-594).
- (닫힘) minor — 판정표 템플릿 이관: `_history_place_step`·`_history_dispatch_step`·`_history_claim_text` 로 서버가 (상태 키, 낱말) 을 만들고 템플릿엔 §2.3-B·C 사슬이 남지 않았다. 서버·템플릿 이중 판정 없음(같은 판정을 두 곳이 각자 계산하는 자리 0건).
- (닫힘) minor — `네이버 자동 취소 가능` 문구 제거: 템플릿 전수 grep 0건이고 부재를 무는 테스트(test_shipping_due_overrun_says_only_the_fact_we_can_prove)가 있다. `발송기한 N일 지남` 배지는 남았다.
- (닫힘) minor — 방어 코드 2종: `getattr(order, 'status'/'deleted_at')` → 직접 접근(naver_ingest.py:621), 템플릿 `dispatch_pending_count or 0` 제거(현재 `or 0` grep 0건).
- (닫힘) minor — test_naver_origin_cleanup.py `collected_at` 변경: 계약 §6(619-620줄)에 예외 1건으로 등재됨(사람 결정 7).

남은 findings:

- **minor** `C:/tmp/foms-naver-status/tests/services/integrations/test_naver_history_status_axes.py`
  - 무엇: 1차 minor(새 분기 테스트 공백)가 그대로 남았다 — 원장 §10.3 이 스스로 '아직 안 닫힌 것' 으로 적어 두었고 내가 grep 으로 재확인했다: `주문 접음`(foms_state=='closed') 0건 · `발주확인 실패`/`발송처리 실패`/`.wb-st__warn` 사유 줄/cancel·return 특례 0건 · `발송 안 함`(dispatch_moot) 0건 · `네이버 확인됨`/`판매자센터에서 직접` 0건. `fail_reason` 픽스처는 517행에서 만들기만 하고 단언이 없다(읽기전용 테스트가 쓸 뿐). 특히 dispatch_moot 는 뒤집히면 `발송처리 할 차례`(주황)가 되어 되돌릴 수 없는 호출을 부르는 자리고, closed 는 판정표에서 linked 보다 앞서 조용히 뒤집힌다.
  - 고칠 방법: 네 분기에 케이스를 더한다 — (1) Order.status='DELETED' 또는 deleted_at 세팅 후 `주문 접음`, (2) fail_reason+fail_action='confirm'/'dispatch' 로 파이프 낱말과 `.wb-st__warn` 사유 줄, cancel/return 이면 `{action_label} 실패 · ` 접두, (3) 발송 0건 + claim_status='CANCEL_REQUEST' 로 `발송 안 함`, (4) dispatch_naver_at 있고 ours_at 있음/없음 두 갈래로 `네이버 확인됨`/`판매자센터에서 직접`.

- **minor** `C:/tmp/foms-naver-status/foms/web/admin/naver_ingest.py`
  - 무엇: 이번 라운드가 `_history_shipping_due` 에서 고친 '무방비 슬라이스' 가 새로 들어온 클레임 날짜 3종에 그대로 재현된다(654-656행 `row['claim_done_at'][5:10]`·`claim_refund_expected_at[5:10]`·`claim_collect_done_at[5:10]`). 이 값들의 생산자 `_dispatch_time_text`(1236-1249행)는 독스트링에 '못 읽으면 원문'이라고 명시하고 실제로 `format_datetime_kst(...) or text` 로 원문을 흘린다. 직접 호출 재현: 원문 'PENDING_REFUND_2026' → 배지 `반품 완료 NG_RE`, '즉시환불처리됨' → `반품 완료 리됨`, '26/08/2026 09:00' → `반품 완료 /2026`(수거·환불 꼬리도 같은 모양으로 샌다). 사람 결정 1(클레임 날짜를 화면에 낸다)이 만든 새 자리이고, `_history_shipping_due` 는 같은 위험을 '한 번만 파싱하고 실패하면 빈 값' 으로 이미 해결해 뒀는데 규율이 옆 함수로 안 넘어갔다.
  - 고칠 방법: `_history_claim` 에서 슬라이스하지 말고 `MM-DD` 파생을 파싱 성공에만 건다 — 예: `_dispatch_time_text` 옆에 `_month_day(text)` 를 두고 `datetime.datetime.strptime(text[:16], '%Y-%m-%d %H:%M')` 성공 시에만 `%m-%d` 를 돌려주고 실패하면 빈 문자열(원문은 배지에 안 싣는다). `_history_shipping_due` 와 같은 '한 번만 파싱, 실패하면 표시 안 함' 규율로 통일.

- **minor** `C:/tmp/foms-naver-status/foms/web/admin/naver_ingest.py`
  - 무엇: 닫힌 major(아무도 안 읽는 행 필드)가 발송 축에서 재발했다. `_history_pipe_fields` 가 행에 싣는 `dispatch_done_count`(833) · `dispatch_total`(834) · `dispatch_moot`(841) 과 `_history_group_axes` 의 `shipping_due`(902)를 읽는 자리가 저장소 전체에 없다 — templates/·static/js/·tests/ 뿐 아니라 `--include=*.py` 전수 grep 도 naver_ingest.py 밖에서 0건이다(place_done_count·place_total 은 테스트 661-688 이 읽으므로 살아 있다). 바로 옆 894-896행 주석이 클레임 축에 대해 '원재료를 행에 또 실으면 아무도 안 읽는 값이 되고, 다음 사람이 화면에 이미 있다고 오독한다' 라고 규율을 적어 놓고 발송 축에서는 그 규율을 안 지킨다 — 같은 커밋 안에서 자기모순이다.
  - 고칠 방법: `_history_pipe_fields` 반환에서 `dispatch_done_count`·`dispatch_total`·`dispatch_moot` 를 빼고(세 값 다 함수 안에서 `_history_dispatch_step` 인자로만 쓰인다), `_history_group_axes` 의 `shipping_due` 원문도 뺀다. 지우기 싫으면 place_* 처럼 '재료와 판정이 어긋나지 않는다' 를 무는 계약 테스트를 붙여 소비자를 만든다.

- **minor** `C:/tmp/foms-naver-status/templates/admin/naver_workbench.html`
  - 무엇: 724행 주석이 '여기 남는 것은 **상태 키 → CSS 클래스 대응**뿐이다(계약 §5)' 라고 단언하는데 사실이 아니다. 바로 아래 758-769행에 계약 §3.2 부속 문구 표(5줄)가 `{% elif %}` 우선순위 사슬로 살아 있고(`fail_action in ('confirm','dispatch') and fail.at` → `dispatch_state=='done' and naver_at and ours_at` → … → `over_days > 0 and dispatch_state != 'done'`), 797행 경고 줄에도 `fail_action in ('cancel','return')` 특례 판정이 있다. 사람 결정 6 은 §2.3-B·C 판정표만 서버로 옮기라고 했으니 사슬이 남은 것 자체는 범위 안이지만, 주석이 '판정은 전부 서버' 라고 말해 버려서 다음 사람이 템플릿에 판정이 없다고 오독한다 — 1차 판정이 지적했던 '있지도 않은 산출물을 설명하는 독스트링' 과 같은 종류다. 그리고 CSS 주석이 예고한 대로 이 부품이 처리 탭(220px)·도크(358px)에 실리면 이 사슬이 복사돼 판정 두 벌이 된다.
  - 고칠 방법: 둘 중 하나. (a) 주석을 사실대로 고친다 — '§2.3-B·C 판정표는 서버, §3.2 부속 문구·경고 접두는 아직 여기' 라고 적고 남은 자리를 명시. (b) `_history_pipe_fields` 에 `when_kind`·`when_text` 를 더해 §3.2 표까지 서버로 옮기고 템플릿엔 `when_kind` → 클래스 대응만 남긴다(그러면 주석이 그대로 참이 되고 부속 문구도 파이썬 단위 테스트로 잠긴다).

- **minor** `C:/tmp/foms-naver-status/templates/admin/naver_workbench.html`
  - 무엇: 1차 minor(있는 것을 없을 수도 있다고 가정하는 방어 코드)를 `getattr`·`or 0` 에서는 걷어냈는데 새 상태 칸에 같은 모양이 다시 들어왔다. 727행 `{% set fail = row.fail or {} %}` — `_history_fail` 은 실패가 없어도 네 키가 다 있는 비어 있지 않은 dict 를 항상 돌려주므로(naver_ingest.py:520-526) `or {}` 는 영영 안 쓰인다. 728행 `fail.get('action') or ''`, 760·771·790행 `fail.get('at')`·`fail.get('reason')`·`fail.get('action_label')` 도 같은 이유로 항상 존재하는 키다. 지금은 무해하지만 나중에 `fail` 계약이 깨져도 화면이 조용히 '실패 없음' 으로 떨어져 진짜 결함을 삼킨다 — 1차에 지적된 실패 모양 그대로다.
  - 고칠 방법: `{% set fail = row.fail %}` 로 바꾸고 `fail.action`·`fail.at`·`fail.reason`·`fail.action_label` 로 직접 읽는다(키가 사라지면 렌더가 터져서 계약 위반이 드러나야 한다).

- **minor** `C:/tmp/foms-naver-status/static/css/admin/naver-workbench.css`
  - 무엇: 1192행 `.wb-st__note` 는 죽은 규칙이다 — 바로 위 주석이 '격자 **아래** 보조 줄 두 종' 이라고 두 개를 예고하지만 실제로 마크업이 쓰는 것은 `.wb-st__warn` 하나뿐이다. templates/·static/js/·tests/ 전수 grep 0건. 계약 §5 표에도 `.wb-st__when` 은 있으나 이 클래스의 소비자가 없다.
  - 고칠 방법: `.wb-st__note` 규칙과 '두 종' 주석을 지운다(나중에 회색 보조 줄이 실제로 생기면 그때 함께 넣는다).

- **minor** `C:/tmp/foms-naver-status/docs/plans/2026-08-30-naver-history-status-column-ledger.md`
  - 무엇: 1차 착수 게이트가 T7 완료 기준을 'Seq Scan 없음' 이 아니라 'EXPLAIN 출력에 ix_external_order_link_dispatch_pending 이름이 뜬다' 로 바꾸라고 못 박았는데, §10.6 에 남은 EXPLAIN 원문은 `Sort ... rows=6000 loop` 에서 잘려 **스캔 노드(인덱스 이름이 뜨는 줄)가 없다**. 원장 스스로 '⚠ 여기서 원문이 끊긴다' 라고 밝혀 놓았는데도 같은 절 머리글은 '두 부분 인덱스 모두 실제로 먹는다. Seq Scan 없음' 이라고 단정한다 — CEO 가 미리 경고한 '없음 판정은 인덱스가 무시돼도 통과한다' 가 그대로 남은 자리다. 코드(조건식 글자 일치·인덱스 컬럼 순서)는 내가 렌더해서 맞는 것을 확인했고 남은 plan 조각의 cost=8.32 도 인덱스 사용을 시사하지만, CEO 가 세운 완료 기준의 증거 자체는 원장에 없다.
  - 고칠 방법: 격리 PG 클러스터를 §10.6 레인 구성 그대로 다시 세워 `EXPLAIN (ANALYZE, BUFFERS)` 전문을 끝까지 남기고, 스캔 노드 줄에 `Index Scan using ix_external_order_link_dispatch_pending` / `Bitmap Index Scan on ix_external_order_link_relation_pair` 가 실제로 뜨는지 확인해 원문을 붙인다. 못 붙이면 §10.6 머리글의 '두 인덱스 모두 먹는다' 단정을 '미확정' 으로 낮추고 PG 레인(MIGCHAIN-01) 결과를 완료 기준으로 옮긴다.

### 스펙 준수 (사용자 요구·목업 어휘·계약 준수·읽기 전용·집 단위·문서 정합) → `PASS_WITH_NOTES`

> 1차 blocker·major 전부 실제로 닫혔다(부분 인덱스는 내가 실 PG 17.9 에서 재현해 Index Scan 두 벌·Seq Scan 0 확인, 목업 클레임 날짜·사유는 렌더 문자열로 확인) — 남은 것은 원장에 EXPLAIN 스캔 노드 줄 붙이기·미단언 분기 4종·`수거 완료` 중복 표기 minor 3건뿐이다.

닫힌 것으로 확인: 13건
- (닫힘) blocker(부분 인덱스 마이그레이션 부재) — migrations/versions/naverdisp_00_history_chip_indexes.py 존재. down_revision='merge_drawq_naverfail' 이 실제 부모이고 `python -m alembic heads` → `naverdisp_00 (head)` 단일 head. 조건식이 렌더 결과와 글자까지 일치(직접 렌더: coalesce(CAST(((external_order_links.triage_state -> 'fulfillment') ->> 'dispatched_at') AS VARCHAR), '') = '' AND coalesce(CAST(((external_order_links.raw_snapshot -> 'delivery') ->> 'sendDate') AS VARCHAR), '') = ''). 실 PG 17.9 에서 upgrade·downgrade 왕복 확인 + EXPLAIN 에 `Index Scan using ix_external_order_link_dispatch_pending`·`Bitmap Index Scan on ix_external_order_link_relation_pair`, Seq Scan 0개 — 내가 직접 재현했다(원장 기록만 잘려 있다, 위 finding 1)
- (닫힘) major(목업 확정 클레임 날짜·사유 미표시) — 서버 `_history_claim_text()` 가 조립하고 템플릿 781~835행이 `claim_badge_text`·`claim_tail_text` 를 찍는다. 실제 라우트 렌더 테스트가 목업 문자열을 그대로 잠금: `반품 완료 08-26` + `수거 완료 08-25 · 환불 완료`(E13), `수거중 · 확정 전` + `단순 변심 · 환불 예정 08-30`(E12). 죽은 필드 6종은 멤버 dict 로 내려가 전부 소비된다
- (닫힘) major(발송 어긋남 경고가 정상 링크의 시각을 찍음) — `_history_dispatch()` 가 `mismatch_ours_at` 을 어긋난 링크만으로 따로 집계하고 템플릿이 그 값만 쓴다. 테스트 2건(695·728행)이 형제의 09:00 이 새지 않는지, 시각이 없으면 문장만 내는지 확인
- (닫힘) major/minor(칩 라벨 두 벌 관리) — `_history_view()` 가 `status_chips: HISTORY_STATUS_CHIPS` 를 싣고 템플릿이 `{% for key, label in history.status_chips %}` 로 돈다. 상수를 monkeypatch 하면 화면이 따라 흔들리는 테스트(866행)로 SSOT 확인
- (닫힘) major(아무도 안 읽는 반품축 필드·링크당 파싱) — `_return_axis_view()` 는 `summary['claim_label']` 이 있을 때만 부르고 없으면 `_EMPTY_RETURN_AXIS` 를 쓴다. 미호출 테스트(901행) 존재
- (닫힘) minor(판정표 템플릿 {% set %} 사슬) — `_history_place_step`·`_history_dispatch_step`·`_history_naver_axis`·`_history_pipe_fields` 로 서버 이전. 계약 §2.3-B/C 표와 구현 순서가 한 줄씩 일치하고, 옮기면서 목업 낱말이 바뀐 곳 없음(발주확인 완료/발주확인 완료 N/M/발주확인 N/M/발주확인 할 차례/발주확인 실패/발송처리/발송처리 할 차례/발송처리 N/M/발송처리 완료/발송처리 실패/발송 안 함/네이버 기록 없음/네이버 처리 없음 전수 대조)
- (닫힘) minor(근거 없는 `네이버 자동 취소 가능` 문구) — 워크벤치 이력 칸에서 제거. 부재를 단언하는 테스트(973행) + 계약 §3.2 에 근거와 함께 등재
- (닫힘) minor(방어 코드 2종) — `getattr(order,'status','')` → `order.status`/`order.deleted_at`(order is None 가드만 유지), 템플릿 `or 0` 제거. `_history_shipping_due` 는 날짜를 1회만 파싱해 `발송기한 902` 재현 결함 제거
- (닫힘) minor(계약서 미갱신) — 계약 §2.2(관계 멤버 기준 related_order_id)·§2.4(칩 파생·템플릿 루프)·§3.3(클레임 꼬리 표 + 목업 갈림표 6줄)·§6(collected_at 예외)·§10.1(구현 중 확정 12건) 전부 갱신됨
- (닫힘) minor(원장 미갱신) — T1~T7 DONE/T8 BLOCKED 로 갱신, §10.1 에 실제 명령과 꼬리 출력 표, §10.9 에 두 화면 어휘 분기 기간 명시. 내가 재실행해 수치 일치 확인: tests/services/integrations `1038 passed in 17.20s` · 신규 계약 테스트 `24 passed in 1.04s` · perf guard `5 passed in 0.16s` · `APP_OK` · pre_push_smoke `324 passed` → `=== PRE-PUSH SMOKE PASSED ===`. 5440 클러스터 파손(`could not open file "base/1/4171"`)·`C:/tmp/pgexplain5442` 부재 주장도 실제와 일치
- (닫힘) minor(collected_at 레인 이탈) — 계약 §6 619행에 예외 1건으로 등재. 되돌리지 않음(사람 결정 7 대로)
- (닫힘) 읽기 전용 유지 확인 — 이력 행 마크업에 `<button`·`data-link-id`·`class="btn`·`<form` 0건(모달 닫기 버튼은 표 밖). 칩 숫자 집 단위 확인 — `_dispatch_pending_group_count`·`_relation_group_count` 둘 다 `group_by(key_col).count()`, 링크 3건짜리 집이 `1주문` 으로 세지는 테스트(594행) 존재
- (닫힘) 사용자 요구 3가지 화면 유지 확인 — ① 관계 배지(추가결제/재결제 → #N, 섞인 집·번호 없음 케이스 포함) ② 발송 축 파이프 + 어긋남/기한 ③ `발주확인 완료` 를 글자로 표기

남은 findings:

- **minor** `C:/tmp/foms-naver-status/docs/plans/2026-08-30-naver-history-status-column-ledger.md`
  - 무엇: T7 이 `DONE (EXPLAIN·가드)` 로 적혀 있는데, T7 자신이 정한 완료 기준("EXPLAIN 출력에 ix_external_order_link_dispatch_pending 이름이 뜬다")을 뒷받침하는 줄이 원장에 없다. §10.6 의 EXPLAIN 원문은 `Sort ... rows=6000 loop` 에서 끊겨 스캔 노드가 빠져 있고, 그 위에 결론 문장 "두 부분 인덱스 모두 실제로 먹는다. Seq Scan 없음" 만 남아 있다(§10.2 가 스스로 '미확정 1건'으로 표시). 원장은 거짓을 적지는 않았지만(잘림을 명시했다), 상태 줄과 결론 문장이 근거보다 앞서 있다. 내가 직접 재현해 보니 결론 자체는 사실이었다 — PG 17.9(포트 5441)에 throwaway DB 를 만들어 create_all → `alembic stamp merge_drawq_naverfail` → `alembic upgrade head`(naverdisp_00 실행 확인) → 50,000행 시드(12% 발송 전) → ANALYZE → EXPLAIN.
  - 고칠 방법: §10.6 의 잘린 블록을 아래 재현 원문으로 교체하고 §10.2 의 '미확정 1건'을 닫는다(사실은 이미 참이므로 문서만 고치면 된다). 발송처리 남음 칩: `Aggregate (cost=8.35..8.36) (actual time=4.992..4.995 rows=1 loops=1)` → `Group (rows=3001)` → `Sort (rows=6000, quicksort 193kB)` → `Index Scan using ix_external_order_link_dispatch_pending on external_order_links (cost=0.28..8.31 rows=1) (actual time=0.023..3.188 rows=6000 loops=1)` / `Index Cond: ((channel)::text = 'NAVER'::text)` / `Buffers: shared hit=633` / `Execution Time: 5.075 ms`. 추가결제·재결제 칩: `HashAggregate (rows=1501)` → `Bitmap Heap Scan on external_order_links (rows=2500)` → `Bitmap Index Scan on ix_external_order_link_relation_pair (actual time=0.158..0.158 rows=2500)` / `Execution Time: 1.554 ms`. **두 계획 모두 Seq Scan 0개.** 덧붙여 원장에 '미검증'으로 남아 있던 downgrade 왕복도 같은 클러스터에서 확인했다: `alembic downgrade -1` → 인덱스 2벌 사라짐(0) → `alembic upgrade head` → 다시 2벌. 검증용 DB 는 삭제했다.

- **minor** `C:/tmp/foms-naver-status/tests/services/integrations/test_naver_history_status_axes.py`
  - 무엇: 1차 minor(테스트 실효성)가 이번에도 안 닫혔다 — 원장 §10.3 이 스스로 '아직 안 닫힌 것'으로 적어 둔 그대로다. 직접 grep 확인: `발송 안 함`(dispatch_moot) 0건 · `주문 접음`(foms_state=='closed') 0건 · `네이버 확인됨` 0건 · 실패 축 렌더(발주확인 실패/발송처리 실패/.wb-st__warn 사유 줄/cancel·return 특례) 단언 0건. 517행이 `fail_reason="배송방법 코드 거부", fail_action="dispatch"` 픽스처를 만들어 두고도 읽기전용 단언만 건다. 계약 §9 의 21개 필수 목록에는 이 넷이 없어 계약 위반은 아니지만, 판정 순서상 `closed` 는 `linked` 보다, `dispatch_moot` 는 `발송처리 할 차례`(주황)보다 앞서는 자리라 조용히 뒤집히면 되돌릴 수 없는 호출을 부른다. 또 결정 6(판정표 서버 이전)의 명분이 '파이썬 단위 테스트로 직접 잠긴다' 였는데, `_history_place_step`·`_history_dispatch_step`·`_history_foms_state` 를 직접 부르는 테스트는 0건이라 그 명분은 아직 실현되지 않았다.
  - 고칠 방법: 네 분기에 케이스를 하나씩 더한다: ① 주문 status='DELETED'(또는 deleted_at) 집 → 배지 `주문 접음` ② 발송 0건 + 클레임 진행 집 → 파이프 2칸이 `발송 안 함`(skip) ③ fail_action='confirm'/'dispatch' 집 → 파이프 `발주확인 실패`/`발송처리 실패` + `.wb-st__warn` 에 사유, fail_action='cancel' 집 → `{action_label} 실패 · {reason}` ④ dispatch done + naver_at + ours_at → `네이버 확인됨`, ours_at 없음 → `판매자센터에서 직접`. 렌더 낱말 단언(현 방식)을 유지하되, 판정표 세 함수는 파이썬에서 직접 호출하는 표 테스트를 별도로 붙이면 결정 6 의 명분이 실제로 닫힌다.

- **minor** `C:/tmp/foms-naver-status/foms/web/admin/naver_ingest.py`
  - 무엇: `_history_claim_text()` 가 COLLECT_DONE 집에서 같은 낱말을 한 줄에 두 번 적는다 — 배지 `수거 완료 · 확정 전` + 작은 글자 `수거 완료 08-25`(테스트 815행이 이 출력을 그대로 잠갔다). 계약 §3.3 갈림표가 목업 E16 꼬리의 `수거중` 을 뺀 근거가 정확히 이것이다: "claimStatus=COLLECTING 이면 그 낱말은 이미 배지 라벨이다 — 내면 한 줄에 두 번 적힌다". 같은 규칙이 COLLECT_DONE 에는 적용되지 않았다. 목업에 COLLECT_DONE 케이스가 없어 어휘 위반은 아니지만, 계약이 스스로 세운 규칙과 화면이 갈린 자리다(다른 낱말은 전부 목업과 일치 확인).
  - 고칠 방법: `_history_claim_text()` 에서 `수거 완료 {MM-DD}` 조각을 만들 때 배지 라벨이 이미 `수거 완료` 면 날짜만 남긴다(예: 배지 `수거 완료 · 확정 전` + 꼬리 `08-25`), 또는 그 조각을 아예 빼고 계약 §3.3 갈림표에 한 줄로 등재한다. 어느 쪽이든 테스트 815행의 기대값을 함께 고친다.

### 사람이 직접 돌린 검증 (2026-08-30)

- `python -c "import app"` → `APP_OK`
- `pytest tests/services/integrations/ -q` → **1038 passed**
- `python -m alembic heads` → `naverdisp_00 (head)` — **단일 head**


## 12. EXPLAIN 스캔 노드 원문 (2026-08-30 · CEO2 스펙 심사자 재현) — T7 종결 근거

§10.6 의 EXPLAIN 원문이 `Sort ... rows=6000` 에서 잘려 **스캔 노드 줄이 빠져 있었다**.
T7 완료 기준("EXPLAIN 출력에 인덱스 이름이 뜬다")을 뒷받침하는 줄이 없던 자리다. 실 PG 17.9
격리 클러스터에서 재현한 원문을 붙인다.

### 발송처리 남음 칩 (`_dispatch_pending_group_count`)

```
Aggregate  (cost=8.35..8.36) (actual time=4.992..4.995 rows=1 loops=1)
  ->  Group  (rows=3001)
        ->  Sort  (rows=6000, quicksort 193kB)
              ->  Index Scan using ix_external_order_link_dispatch_pending on external_order_links
                    (cost=0.28..8.31 rows=1 width=32) (actual time=0.023..3.188 rows=6000 loops=1)
                    Index Cond: ((channel)::text = 'NAVER'::text)
                    Buffers: shared hit=633
Execution Time: 5.075 ms
```

**핵심: `Index Scan` 아래에 `Filter:` 줄이 아예 없다.** JSONB 술어 두 개가 통째로 부분 인덱스
조건식에 흡수됐다는 뜻 — PostgreSQL 이 술어 함의를 증명했다. CAST 모양이 어긋났다면 여기서
`Filter:` 가 뜨거나 Seq Scan 으로 떨어진다.

### 추가결제·재결제 칩 (`_relation_group_count`)

```
HashAggregate  (rows=1501)
  ->  Bitmap Heap Scan on external_order_links  (rows=2500)
        ->  Bitmap Index Scan on ix_external_order_link_relation_pair
              (cost=0.00..79.07 rows=2505 width=0) (actual time=0.158..0.158 rows=2500 loops=1)
Execution Time: 1.554 ms
```

### 대조군·규모 확인

- **5배 규모(250k 행)**: 두 계획 모두 그대로 `Index Scan`, `Filter` 없음, **Seq Scan 0개**.
  (`Index Scan using ix_external_order_link_dispatch_pending ... rows=30000 loops=1`)
- **음성 대조군**: 인덱스를 강제로 끄면 계획이 바뀌는 것까지 대조했다 — 인덱스가 실제로
  선택된 것이지 우연히 빠른 것이 아니다.
- **upgrade → downgrade 왕복**: 같은 클러스터에서 `alembic downgrade -1` → 인덱스 2벌 사라짐(0)
  → `alembic upgrade head` → 다시 2벌. 원장에 "미검증" 으로 남아 있던 자리가 닫혔다.
- 검증용 DB·클러스터는 삭제했다(잔재 0).

**판정**: T7 = DONE. 근거는 이 절의 스캔 노드 줄과 `Filter` 부재다.

## 13. minor 정리 라운드 (2026-08-30 · 사람이 직접 수정)

CEO 재판정이 남긴 minor 8건을 사람이 직접 닫았다.

| # | 무엇 | 어떻게 |
|---|---|---|
| 1 | 클레임 날짜 `[5:10]` 무방비 슬라이스 재발 | `_history_month_day()` 신설 — `date.fromisoformat` 으로 읽히는 값만 자른다. 못 읽으면 빈 문자열(화면이 조각을 통째로 안 낸다) |
| 2 | 아무도 안 읽는 행 필드 재발 | `dispatch_done_count`·`dispatch_total`·`dispatch_moot`·`shipping_due` 를 행에서 뺐다(전수 grep 으로 소비자 0 확인) |
| 3 | `수거 완료` 가 한 줄에 두 번 | 날짜를 배지로 올리고 꼬리에서 뺀다 — `수거 완료 08-25 · 확정 전`. 중복을 잠그고 있던 계약 테스트도 새 계약으로 옮겼다 |
| 4 | 템플릿 `{% elif %}` 부속 문구 표 5줄이 남아 있었다 | `_history_pipe_note()` 로 서버 이관, 행에 `pipe_note_kind`·`pipe_note_text`. 템플릿은 종류→CSS 클래스만 옮긴다 |
| 5 | `{% set fail = row.fail or {} %}` 불필요 방어 재발 | `_history_fail` 은 항상 네 키를 채워 준다 — `row.fail.reason` 직접 접근으로 바꿨다 |
| 6 | `.wb-st__note` 죽은 CSS 규칙 | 규칙 삭제 + "보조 줄 두 종" 주석을 사실대로 고침 |
| 7 | 원장 EXPLAIN 에 스캔 노드 줄 없음 | §12 에 원문 첨부(위) |
| 8 | 미단언 분기 4종 | §13 아래 테스트 절 참고 |

**사람이 직접 돌린 검증**: `import app` → `APP_OK` · `pytest tests/services/integrations/ -q` → **1044 passed**

> 정정(2026-08-30 CEO 최종 검수): 이 줄에 처음 적힌 `1038 passed` 는 이 라운드에서 나올 수 없는
> 숫자였다 — 미단언 분기 테스트 6개를 더해 놓고 앞 절(§11 시점)의 값을 옮겨 적었다.
> **라운드마다 숫자를 새로 뽑는다. 앞 절에서 복사하지 않는다.**


## 14. 취소 축 확정 날짜 (2026-08-30) — 목업 대비 마지막 빈자리

**증상**: 목업 확정본의 `취소 완료 08-27` · `취소 완료 08-26 · 환불 완료` 가 화면에서
배지 한 낱말(`취소 완료`)로 줄어 있었다.

**원인**: 클레임 꼬리 재료가 전부 `extract_return_axis` 에서 오는데, 그 함수의
`RETURN_BLOCK_KEYS = ('returnInfo','return','exchange')` 는 `cancel` 을 **일부러 뺀다**.
취소 블록의 환불 필드가 반품 진행으로 새어 스테이징 344 링크 중 50건이 "취소 완료 배지 +
반품 진행 본문" 이던 결함(2026-08-27 CEO A1)을 고친 자리다. 그래서 순수 취소 건은
`return_completed_at`·`refund_done` 이 영영 빈 값이었다.

**고친 방향**: 반품 축에 `cancel` 을 도로 넣지 **않는다** — 고친 누출을 되살리는 짓이다.
축을 하나 더 둔다.

- `mapping.extract_cancel_axis()` 신설 — `cancel` 블록만 읽는다(`CANCEL_BLOCK_KEYS`).
  `cancelCompletedDate` · `cancelApprovalDate` · `refundStandbyStatus` → `refund_done`.
  `cancelCompletedDate` 는 운영 `CANCEL_DONE` 15건이 실제로 갖고 있는 값인데
  (`docs/specs/2026-08-28-naver-claim-phase-labeling_SPEC.md` §1.1) 읽는 코드가 0곳이었다.
- `_history_member_axes` 가 **클레임 종류가 취소일 때만** 이 축을 본다.
  `claim_done_at` · `claim_refund_done` 이 축을 따라간다.
- 승인 전 요청 건(운영 link 79)은 두 날짜가 다 없어 빈 값 → 화면이 날짜 조각을 안 낸다.

**잠근 것**(`test_naver_history_status_axes.py`):
- `test_settled_cancel_household_shows_the_cancel_date_and_refund` — 날짜·환불 완료가 뜨고,
  **그 집에 반품 낱말(`수거 완료`)이 안 뜬다**(누출 재발 감시).
- `test_cancel_request_without_approval_shows_no_date` — 승인 전에는 날짜를 안 낸다.

**검증**: `import app` → APP_OK · `tests/services/integrations` + perf guard → **1051 passed**.


## 15. CEO 최종 검수 (2026-08-30 · 3차) — 판정과 처리

### 스펙 준수 (목업 어휘 · 사용자 요구 3가지 · 어휘 단일성 · 읽기 전용 · 문서 정합) → `PASS_WITH_NOTES` (ship_ready=True)

> 코드는 검증 전부 초록(APP_OK · integrations 1046 passed · pre_push_smoke exit 0 · alembic 단일 head naverdisp_00)이고 목업 미구현분은 §8·§3.3 에 근거가 있어 스테이징 배포는 안전하다 — 다만 계약서가 이번 라운드의 취소 축을 아직 "안 하기로 한 일"로 적고 있어(다음 라운드가 되돌릴 자리) 문서 4건을 같은 푸시에 함께 고쳐라.

- **major** `C:/tmp/foms-naver-status/docs/plans/2026-08-30-naver-history-status-contract.md`
  - 무엇: 계약서가 이번 라운드의 핵심 변경과 정면으로 반대되는 말을 하고 있다. §3.3 갈림표 381행이 「목업 E14 `취소 완료 08-26` → 실화면 `취소 완료`」로, 근거를 「확정 날짜의 유일한 출처가 returnCompletedDate(반품 축)다. 취소 확정 스냅샷에는 그 필드가 없다」로 못 박았고 §10.1 표 736행(#6)도 「확정 날짜는 returnCompletedDate 하나에서만 온다 → 취소 확정·거부에는 날짜가 안 붙는다」로 확정 기록해 두었다. 그런데 커밋 928f2706 이 mapping.extract_cancel_axis(cancelCompletedDate·refundStandbyStatus)를 신설하고 _history_member_axes 가 kind=='CANCEL' 일 때 그 축을 쓰도록 바꿔, 화면은 이제 목업대로 `취소 완료 08-26` + `환불 완료` 를 낸다 — test_settled_cancel_household_shows_the_cancel_date_and_refund(테스트 파일 1097행)가 그 문자열을 그대로 잠그고 있고 실행해서 초록을 확인했다. 계약서를 정본으로 읽는 다음 사람은 이 동작을 계약 위반으로 보고 되돌릴 수 있다(원장 §14 는 맞게 적혀 있으나 계약서는 §14 를 모른다). 커밋 928f2706 의 --stat 에 계약서가 없다 = 두 번째 커밋이 계약서를 건드리지 않았다.
  - 고칠 방법: §3.3 갈림표에서 E14 줄을 지우고(이제 목업과 일치한다), E15 `취소 거부` 줄의 근거를 `returnCompletedDate 부재`가 아니라 `거부 스냅샷에 cancelCompletedDate 가 없다`로 다시 쓴다. §10.1 표에 #13 으로 취소 축 신설(반품 축에 cancel 을 도로 넣지 않는 이유 포함)을 추가하고, 원장 §10.8-2 「취소 확정 건의 날짜·환불 완료 미표시 … 이번 범위 밖」도 닫는다.
- **minor** `C:/tmp/foms-naver-status/docs/plans/2026-08-30-naver-history-status-contract.md`
  - 무엇: §2.2 「집(그룹) dict 에 더하는 것 — 템플릿이 읽는 것」 표가 실제 행 dict 과 다르다. 표에 아직 `dispatch_done_count`·`dispatch_total`·`dispatch_moot`·`shipping_due` 네 줄이 남아 있는데 원장 §13-2 가 그 넷을 행에서 뺐다(코드 확인: _history_pipe_fields·_history_group_axes 가 싣는 키에 없다. shipping_due 는 멤버 dict 475행에만 남는다). 반대로 이번에 새로 생긴 행 필드 `pipe_note_kind`·`pipe_note_text`(_history_pipe_note)는 표에 한 줄도 없다. 같은 문서 §5 CSS 계약 표 553행은 `.wb-st__note` 를 클래스 계약으로 올려 두었으나 그 규칙은 §13-6 에서 CSS 에서 삭제됐다(grep: naver-workbench.css 에 wb-st__note 0건).
  - 고칠 방법: §2.2 표에서 죽은 네 줄을 지우고 pipe_note_kind·pipe_note_text 두 줄을 더한다(값 예: `"when"`/`"발송기한 09-02"`, `"over"`/`"발송기한 2일 지남"`). §5 표에서 `.wb-st__note` 행을 지운다.
- **minor** `C:/tmp/foms-naver-status/docs/plans/2026-08-30-naver-history-status-column-ledger.md`
  - 무엇: §13(minor 정리 라운드) 끝의 「사람이 직접 돌린 검증: pytest tests/services/integrations/ -q → 1038 passed」는 그 라운드 상태에서 나올 수 없는 숫자다 — 재실행 없이 앞 라운드 숫자를 옮겨 적었다. 산술로 확인했다: HEAD 에서 그 스위트는 1046 passed 이고 신규 계약 파일은 32 케이스(직접 실행·collect-only 확인) → 다른 파일 몫이 1014. aed62a0e 시점 그 파일은 30 케이스(git show 로 확인)이므로 §13 라운드 직후 값은 1044 여야 한다. 1038 은 §11 시점(파일 24 케이스, 원장이 「신규 계약 테스트 24 passed」로 스스로 적은 그 상태)의 값 1014+24 와 정확히 일치한다. 즉 §13 이 미단언 분기 테스트 6개를 더해 놓고 그 전 숫자를 검증란에 적었다.
  - 고칠 방법: §13 의 검증 줄을 실제 재실행 값으로 바꾼다(현재 트리 기준 `1046 passed`). 라운드마다 숫자를 새로 뽑고, 앞 절에서 복사하지 않는다.
- **minor** `C:/tmp/foms-naver-status/docs/plans/2026-08-30-naver-history-status-column-ledger.md`
  - 무엇: 이미 닫힌 항목 2개가 원장 앞쪽에 미해결로 그대로 남아 있어, 위에서부터 읽는 사람이 승격 차단 사유로 오독한다. ① §10.2 「미확정 1건 — 승격 전에 반드시 닫아라 … EXPLAIN 원문이 잘려 있다 … 결론만 근거로 승격하지 마라」 → §12 가 스캔 노드 원문을 붙여 닫았다(§11 findings 의 고칠 방법도 '§10.2 의 미확정 1건을 닫는다' 였는데 §12 추가만 하고 §10.2 본문은 안 고쳤다). ② §10.8-2 「취소 확정 건의 날짜·환불 완료 미표시 … 이번 범위 밖」 → §14 가 닫았다.
  - 고칠 방법: §10.2 의 '미확정 1건' 블록을 '→ §12 에서 닫힘'으로 바꾸고, §10.8 목록 2번을 지우거나 '§14 에서 닫힘'으로 표시한다.
- **minor** `C:/tmp/foms-naver-status/docs/design/mockups/naver-triage-status-column--table.html`
  - 무엇: 목업 20케이스를 훑은 결과 화면에 아직 없는 것은 전부 §8·§4.1·§3.2·§3.3 에 근거와 함께 등재돼 있는데(옛 결제 축 E3·E4, 재결제 짝 E14, 기존 주문 후보 E17, 고스트 E19, 네이버 기록 없음 칩, 네이버 자동 취소 가능 warn, 배지 낱말 4곳), 딱 한 종류만 어디에도 없다: 격자 아래 회색 보조 줄(`.note`) 3건 — E2 `발주확인 뒤 바로 닫은 건`, E13 `금액만 환급`, E17 `추가결제·재결제 고르기`. 계약 §5 가 `.wb-st__note` 를 「이번 라운드 소비처 0 — 옛 결제 줄이 쓸 자리」라고만 적어 뒀는데 목업에서 그 세 줄이 붙은 행에는 옛 결제 줄이 없다(옛 결제 줄이 있는 E3·E4 는 `.warn` 을 쓴다) — 근거가 사실과 안 맞고, 이번에 그 CSS 규칙까지 지워져 흔적도 사라졌다. 화면 동작에는 영향이 없다(전부 부연 문구).
  - 고칠 방법: 계약 §8 '이번에 안 싣는 것' 표에 「목업 `.note` 회색 보조 줄 3건(E2·E13·E17) — 파생 출처가 각각 CLOSE_NOW_RELATIONS·반품 금액환급 성질·다음 할 일 힌트로 축이 셋이라 별건」 한 줄을 넣고, §5 의 `.wb-st__note` 설명(옛 결제 줄이 쓸 자리)은 삭제한다.

### 코드 품질 → `PASS_WITH_NOTES` (ship_ready=True)

> 취소 축 분리는 옛 누출을 되살리지 않았고(직접 호출로 확인) 새 함수는 전부 50줄·타입힌트·docstring을 지켰다 — 다만 실패 시각만 KST 변환을 안 거쳐 같은 칸에 9시간 어긋난 시각이 뜨고, 죽은 필드 4종이 다시 생겼다.

- **major** `foms/web/admin/naver_ingest.py:534`
  - 무엇: `_history_fail` 이 실패 시각을 `str(last_error_at)[:16].replace('T',' ')` 로 만든다. 그 값은 `fulfillment.py:523` 이 `now_utc_naive().isoformat()` 로 쓴 **UTC** 다. 같은 상태 칸의 다른 시각(발송·어긋남 경고)은 전부 `_dispatch_time_text` 로 KST 로 펴진다. 실제로 돌려 확인: `2026-08-30T02:15:33` 한 값이 파이프 옆 문구에는 `2026-08-30 02:15`, 발송 파서로는 `2026-08-30 11:15` — 한 칸 안에서 같은 모양의 두 시각이 9시간 어긋난다. 이번 라운드가 없앤 '무방비 슬라이스' 도 이 자리에 그대로 남아 있다(새 코드의 마지막 1곳).
  - 고칠 방법: `"at": _dispatch_time_text(state.get("last_error_at"))` 로 바꾼다 — 시각 파서를 한 벌로 만들면 슬라이스와 시간대가 동시에 해결된다. 옆 화면(`_failure_rows`, 2398줄)도 같은 원문 슬라이스라 함께 본다.
- **minor** `foms/web/admin/naver_ingest.py:914`
  - 무엇: 행에 실렸는데 읽는 곳이 없는 필드가 다시 4종 생겼다: `dispatch_ours_at`·`dispatch_naver_at`(914-915), `shipping_due_text`·`shipping_due_over_days`(985-986). 워크벤치 템플릿·구 `templates/admin/naver_ingest.html`·`naver-workbench.js`·테스트 전수 대조로 확인했고, 이 값들은 `_history_pipe_note` 가 `dispatch`/`due` 원본 dict 에서 직접 읽는다. 바로 그 자리 주석이 '읽는 곳 없는 값을 남기면 다음 사람이 화면에 있다고 오독한다' 고 적혀 있고, `shipping_due*` 옆 주석은 '화면이 읽는 것은 아래 둘뿐' 이라고 사실과 반대로 말한다. 덤으로 `sync_status` 도 상태 칸 재설계로 두 템플릿 모두에서 읽는 곳이 사라졌다(구 화면은 `statuses` 를 쓴다).
  - 고칠 방법: 네 필드를 `_history_pipe_fields`·`_history_group_axes` 반환에서 뺀다(집계 dict 안에는 그대로 두면 된다). `sync_status` 는 구 템플릿 대조 후 함께 정리.
- **minor** `foms/web/admin/naver_ingest.py:470`
  - 무엇: 취소 축은 갈랐는데 `claim_refund_expected_at`(470)·`claim_collect_done_at`(472)은 종류와 무관하게 **반품 축**에서 온다. 스냅샷에 `cancel` 과 `return`/`exchange` 블록이 함께 있으면 취소 집에 반품 낱말이 뜬다 — in-process 로 재현했다: `_history_claim_text` → `('취소 완료 08-26', '수거 완료 08-25 · 환불 완료')`. 2026-08-27 에 고친 누출의 거울상이다(방향만 반대). 그런 스냅샷이 실데이터에 있는지는 관측 근거를 못 찾았다.
  - 고칠 방법: `cancel` 이 잡힌 멤버는 두 값도 취소 축 기준으로 준다(취소 블록에 대응 값이 없으면 빈 문자열). 즉 `claim_done_at` 과 같은 `if cancel else` 분기를 두 줄에도 건다.
- **minor** `tests/services/integrations/test_naver_history_status_axes.py:1123`
  - 무엇: 새 취소 축 테스트 2개 중 `test_cancel_request_without_approval_shows_no_date` 는 옛 코드에서도 초록이다. `extract_cancel_axis` 를 빈 값 반환으로 바꾼 플러그인으로 돌려 확인했다 — 빨강은 `test_settled_cancel_household_shows_the_cancel_date_and_refund` 1개뿐이고 이쪽은 통과한다(회귀 감시가 아니라 지어내기 방지 가드다). 또 반품 축에는 '클레임 없는 링크는 파싱하지 않는다' 계측 테스트(908줄)가 있는데 취소 축의 게이트(`kind == 'CANCEL'` 일 때만)를 잠그는 대응 테스트가 없다.
  - 고칠 방법: 취소 축에도 908줄과 같은 모양의 계측 테스트를 둔다(반품 종류 링크에서 `extract_cancel_axis` 호출 0회 + 취소 링크 1회 양성 대조군). 게이트가 풀리면 그때 빨강이 된다.
- **minor** `migrations/versions/naverdisp_00_history_chip_indexes.py`
  - 무엇: 부분 인덱스 조건식이 `_dispatch_pending_clause()` 렌더 결과와 글자까지 같아야 한다고 파일 두 곳이 못 박았는데, 그것을 지키는 테스트가 없다(`grep dispatch_pending tests/` 0건). 지금은 실제로 일치한다 — postgresql 방언으로 렌더해 대조 확인했다. 술어를 한 글자만 손대면 PostgreSQL 이 인덱스를 통째로 무시하고, 그때 나오는 Seq Scan 은 원인이 안 보인다.
  - 고칠 방법: 렌더한 조건식이 마이그레이션의 `DISPATCH_SQL`·`RELATION_SQL` 에 들어 있는지 확인하는 계약 테스트 1개(테이블 수식어만 제거해 비교).
- **minor** `foms/web/admin/naver_ingest.py:1162`
  - 무엇: `_history_member_axes` 를 `_link_rows` 안에 넣어서, 워크벤치 게이트가 꺼진 사용자용 구 화면(`naver_ingest_dashboard` → `templates/admin/naver_ingest.html`)도 링크마다 `extract_claim` 1회 추가·`claim_kind`·`claim_reason_text`·`_dispatch_view`(`extract_delivery`)를 치른다. 그 템플릿이 읽는 필드를 전수로 뽑아 확인했는데 새 축 필드는 하나도 안 쓴다.
  - 고칠 방법: 축 계산을 이력 탭 경로에서만 켠다(`_link_rows(..., with_axes=False)` 기본값 또는 `_history_view` 전용 분기). 취소 축 자체는 이미 클레임·취소 건에만 도는 것을 확인했다.

### 처리 결과 (사람이 직접)

| findings | 처리 |
|---|---|
| major · 계약서가 취소 축을 "안 하기로 한 일"로 적음 | 계약서 **§15** 신설 — 앞 절보다 우선. §3.3·§10.1 뒤집힘을 명시 |
| major · 실패 시각만 UTC 원문 슬라이스(같은 칸 9시간 어긋남) | `_dispatch_time_text` 로 통일(2곳). 계약 테스트로 잠금 |
| minor · 취소 축 거울상 누출(환불예정·수거완료가 반품 축) | 취소로 판정된 멤버는 반품 조각을 빈 값으로. 두 블록 동시 스냅샷 테스트 추가 |
| minor · 죽은 행 필드 4종 재발 | `dispatch_ours_at`·`dispatch_naver_at`·`shipping_due_text`·`shipping_due_over_days` 제거 |
| minor · 취소 축 게이트 계측 테스트 없음 | `test_cancel_axis_is_parsed_only_for_cancel_claims` 추가(음성·양성 대조군) |
| minor · 마이그레이션 조건식 일치 테스트 없음 | `test_partial_index_condition_matches_the_rendered_predicate` 추가 |
| minor · 원장 §13 검증 숫자가 앞 절 복사(1038) | **정정 완료** — 실제 재실행 값으로 바꾸고 재발 방지 규칙 명시 |
| minor · 계약서 §2.2/§5 표가 코드와 어긋남 | §15.2·§15.3 에서 정정 |
| minor · 목업 `.note` 3건 미등재 | §15.4 에 근거와 함께 등재 |
| minor · 옛 수집 화면도 축 파싱을 치름 | **수용** — 게이트를 걸면 집 조립까지 두 갈래가 되어 그 화면이 500(18 red, 되돌림). 근거는 §15.5 |


## 16. 스테이징 배포 (2026-08-30) — 완료

- 푸시: `032b43d0..9d19da0b` → `origin/deploy` (커밋 3개)
- **리베이스**: 푸시 직전 origin/deploy 가 9커밋 앞서 있었다(타 세션). 리베이스 충돌 4건은
  **전부 자산 `?v` 핀뿐** — 기능 의존 아님. 타 세션이 `20260830b` 까지 올려서 내 몫을
  `20260830c` 로 범프했다(템플릿 2줄 + 핀 잠근 테스트 2곳 = 4자리).
- **리베이스 후 재검증**(리베이스 전 초록은 근거가 안 된다):
  `APP_OK` · `alembic heads` 단일 `naverdisp_00` · `tests/services/integrations` + perf guard
  **1079 passed** · `pre_push_smoke.ps1` **exit 0**.
- **CI 전 워크플로 green**(`gh run list --branch deploy` 로 전수 — deploy 는 이 4개가 전부):
  FOMS CI · FOMS PostgreSQL Lane · Harness CI · perf-gate (staging) 모두 `completed/success`.

### 남은 일

1. **운영 승격** — 사용자 명시 요청 시에만. 승격 시 `naverdisp_00` 마이그레이션의
   `down_revision`(`merge_drawq_naverfail`)이 **운영 계보에 있는지 먼저 확인**할 것.
   부모가 없으면 부팅이 파산한다.
2. **스테이징 실화면 확인** — 목업 20케이스 중 실데이터로 재현되는 것을 눈으로 대조.
3. 계약서 **§15 가 정본**이다(앞 절과 충돌하면 §15 우선). 다음 세션이 §3.3 을 읽고
   취소 축을 되돌리지 않도록 이 줄을 남긴다.


### 16.1 운영 승격 PR (2026-08-30)

- PR **#198** — https://github.com/lahomsystem/FOMS/pull/198
  브랜치 `promo/naver-status-20260830` · 워크트리 `C:/tmp/promo-naver-status`
- **내 세션 커밋 3개만 cherry-pick**(deploy HEAD 전체 머지 아님):
  상태 칸 재설계 · 취소 축 · UTC 시각 버그.
  cherry-pick 충돌 4건은 전부 자산 `?v` 핀뿐(운영 `20260830a` vs 내 `c`) — 기능 의존 아님.
- 승격 트리에서 직접 검증: `APP_OK` · `alembic heads` 단일 `naverdisp_00` ·
  `tests/services/integrations` + perf guard **1066 passed** · `pre_push_smoke` exit 0.
- **PR 체크 전 green · mergeState `CLEAN`**: test 15m59s · pg-lane 2m13s · harness 1m22s · perf-gate 1m11s.
  본 스위트(15분)가 승격 PR 에서 **실제로 돌았다** — 과거 승격 PR 이 실측 체크 2종만 돌던 구멍이 이번엔 없었다.
- **머지는 사람이 누른다.** 머지 뒤 운영 실화면 1회 확인이 완료 정의다.


## 17. 스테이징 실화면 대조 (2026-08-31) — 목업 20케이스

코호트를 잠깐 넓혀서(`FOMS_NAVER_WORKBENCH_COHORT=38,58` → 확인 → `38` 복원) `claude_master` 로
`/admin/naver-ingest/triage?tab=all` 을 실데이터로 열었다. 자산 핀 `?v=20260830c` 확인,
상태 칸 블록 50개 렌더. 칩: 전체 131 · 받아옴·주문 전 120 · 주문 만듦 12 · 확인 필요 0 ·
받기 실패 0 · 발주확인 남음 6 · 발송처리 남음 60 · 추가결제·재결제 2.

본 페이지 1~3 + `status=LINKED` + `place=PENDING` + `rel=ADDON_REPAY` 를 전부 받아
상태 칸 텍스트를 뽑아 목업 어휘와 대조했다.

### 17.1 실데이터로 재현된 케이스 (화면 낱말이 목업과 일치)

| 케이스 | 실화면에서 뽑은 줄 |
|---|---|
| E2 추가결제 | `FOMS 주문 만듦 · 추가결제 → #4242` / `발주확인 완료 2/2` `발송처리 완료 2/2` `2026-08-20 08:44 · 네이버 확인됨` |
| E3 재결제 | `FOMS 주문 만듦 · 재결제 → #4485` / `발주확인 완료 6/6` `발송처리 완료 6/6` |
| E8 판매자센터 직접발송 | `발송처리 완료 5/5` `2026-08-28 15:11 · 판매자센터에서 직접` (최다 유형) |
| E13 반품 완료 | `반품 완료 08-25` `배송 오류·지연 · 수거 완료 08-25 · 환불 완료` |
| E14 취소 확정 | `네이버 처리 없음` + `취소 완료 08-27` `단순 변심 · 환불 완료` |
| E1 아래줄 | `발송처리 할 차례` + `발송기한 09-17` (기한 표기 정상, 미래 날짜) |
| E12·E19 어휘 | `발송 안 함` — 취소 확정 집에서 발송 축이 닫힌 모양 |
| 집계 표기 | `N/N` 형식이 발주확인·발송처리 양쪽에서 정상(E5·E6 의 부분 표기와 같은 틀) |

관계 축 3종(`신규 결제` · `추가결제 →` · `재결제 →`)이 전부 실물로 확인됐다 —
**사용자 지적 1(재결제·추가결제 표시 부재)이 실데이터에서 닫힌 것을 눈으로 봤다.**
발송처리 축도 완료/할 차례/안 함 3상 전부 재현 — 지적 2 닫힘. 발주확인 완료가 명시로 뜬다 — 지적 3 닫힘.

### 17.2 실데이터가 없어 못 본 케이스 (결함 아님 · 미검증으로 남긴다)

E4 옛 결제 살아있음 · E5 부분 발송 · E6 부분 발주확인 · E7 네이버 기록 없음 ·
E9 발주확인 실패 · E10 발송처리 실패 · E11 발송기한 초과 · E12 반품 진행(수거중) ·
E15 취소 거부 · E16 교환 요청 · E17 확인 필요 · E18 구매확정 보류 · E19 고스트 · E20 수집 실패.

E17·E20 은 칩이 `0주문` 이라 모집단 자체가 비어 있음을 화면이 스스로 말한다.
나머지는 계약 테스트(`test_naver_history_status_axes.py`)가 함수 단위로 잠근 자리다.

### 17.3 대조에서 확인한 어긋남 2건 (둘 다 이미 알려진 것 · 회귀 아님)

1. **`발주확인 남음 · 취소 포함` 칩 6건이 전부 취소 확정 집이다** — 열어 보면 6행 모두
   `네이버 처리 없음` + `취소 완료`. §10.8-4 가 적어 둔 모집단 성질이 실데이터에서 그대로 나왔다.
   칩 꼬리 `· 취소 포함` 이 그 사실을 말하고 있어 라벨과 모집단이 어긋나지는 않는다.
2. **발송 시각 형식이 목업과 다르다** — 목업 E8 은 `08-27 14:40`, 화면은 `2026-08-28 15:11`.
   `_dispatch_time_text` 가 `%Y-%m-%d %H:%M` 로 고정한 값이고 계약 §15 가 정본이므로 위반이 아니다.
   (목업 쪽이 짧게 적힌 것. 바꾸려면 별건.)

목업의 회색 보조줄 3건(E2 `발주확인 뒤 바로 닫은 건` · E13 `금액만 환급` · E17 `추가결제·재결제 고르기`)은
계약 §15.4 가 **별건으로 뺀 것**이라 이번 대조 대상이 아니다.

### 17.4 코호트 원복 확인

`FOMS_NAVER_WORKBENCH_COHORT` 를 `38` 로 되돌렸다(확인: railway variables 조회 = `38`).


## 18. 운영 승격 완료 (2026-08-31)

### 18.1 PR 이 세 번 다시 팠다 — 왜

승격 PR 은 `#198` → `#199` → **`#200`(머지됨)** 순으로 다시 팠다. 코드는 같고 base 만 바뀌었다.

| PR | base | 왜 죽었나 |
|---|---|---|
| #198 | `5acef038` | 머지 직전 `#197` 이 운영에 들어가 자산 `?v` 핀 4자리 충돌 → `DIRTY` |
| #199 | `4be86ab2` | 새로 판 직후 `#196` 이 머지돼 `foms_failopen_inventory.json` 충돌 |
| **#200** | `d6f1c84e` | **머지 완료** `639feabe` (2026-08-30 23:54Z) |

- 두 번 다 **충돌은 코드가 아니었다** — 자산 핀(내 `20260830c` 유지)과 생성물 인벤토리뿐.
  인벤토리는 운영 것을 취한 뒤 **승격 트리에서 3종 재생성**해 별도 `chore` 커밋으로 올렸다.
- `git push --force-with-lease` 는 가드가 막는다. 리베이스 뒤에는 **새 브랜치를 판다**
  (`promo/naver-status-20260831` → `…-20260831b`).
- 교훈: 운영이 하루에 두 번 앞설 수 있다. **PR 을 열어 두고 기다리는 시간이 곧 충돌 확률**이다.

### 18.2 PR #200 체크 (전 green)

`test` 14m19s · `pg-lane` 2m22s · `harness` 1m39s · `perf-gate` 1m23s — 전부 pass, `CLEAN` 상태에서 머지.
승격 트리 자체 검증도 리베이스 후 재실행했다: `APP_OK` · `alembic heads` 단일 `naverdisp_00` ·
`tests/services/integrations` + perf guard **1080 passed** · `pre_push_smoke` exit 0.

### 18.3 운영 실화면 확인 (완료 정의 충족)

- 배포 도착 확인: `lahom-production` `/static/css/admin/naver-workbench.css?v=20260830c` 에
  `.wb-st-wrap` 규칙 존재 + `/login` 200(마이그레이션 `naverdisp_00` 통과, 부팅 정상).
- `claude_master`(production id 57) **잠금 해제 → 1회 조회 → 재잠금**. 재잠금은 로그인 200 오라클로 확인.
- `/admin/naver-ingest/triage?tab=all` 200 · 상태 칸 50블록 · 자산 핀 `20260830c`.
  칩: 전체 58 · 받아옴·주문 전 20 · 주문 만듦 38 · 확인 필요 0 · 받기 실패 0 ·
  발주확인 남음 3 · 발송처리 남음 30 · **추가결제·재결제 12**.
- 운영 실데이터에서 뽑은 줄(스테이징보다 관계 축이 훨씬 두껍다):
  - `FOMS 주문 만듦 · 재결제 → #4915` / `발주확인 완료 2/2` `발송처리 완료 2/2` `2026-08-30 11:15 · 네이버 확인됨`
  - `FOMS 주문 만듦 · 추가결제 → #4978` / `발주확인 완료` `발송처리 완료` `2026-08-28 14:56 · 네이버 확인됨`
  - `발송 안 함` + `취소 완료 08-28` `주문 실수 · 환불 완료`
  - `발송처리 할 차례` + `발송기한 09-17`
- **사용자 지적 3가지가 운영 실데이터에서 닫힌 것을 확인했다** — 관계 축 12주문이 실제로 뜨고,
  발송처리 축 3상이 전부 나오며, 발주확인 완료가 명시로 보인다.

### 18.4 남은 것

- (선택·별건) 처리 탭(work) 행 배지를 같은 어휘로 통일 — 이번 범위 밖.
- 목업 회색 보조줄 3건(계약 §15.4) — 별건.
- 운영에서 아직 못 본 케이스는 스테이징 §17.2 목록과 같다(데이터가 없어서지 결함이 아니다).


## 19. 처리 탭 배지 어휘 통일 (2026-08-31)

§16 '남은 일 3' 로 미뤄 뒀던 별건. 사용자가 **낱말만 맞추는 범위**를 골랐다.

### 19.1 무엇이 어긋나 있었나

처리 탭(work)과 이력 탭(all)이 **같은 사실을 다른 말로** 쓰던 자리는 하나뿐이었다.

| 자리 | 처리 탭(전) | 이력 탭 | 처리 탭(후) |
|---|---|---|---|
| 행 배지 | `발주확인 전` | `발주확인 할 차례` | `발주확인 할 차례` |
| 필터 칩 | `발주확인 전` | `발주확인 남음 · 취소 포함` | `발주확인 할 차례` |

나머지는 이미 같았다 — `발주확인 완료` · `발송기한 MM-DD` · `취소 완료` · 클레임 배지(같은 원천).

### 19.2 맞추지 않은 것과 그 이유

- **필터 칩 라벨을 이력 칩과 같은 말로 만들지 않았다.** 처리 칩은 **작업 대상**(취소·반품 제외),
  이력 칩은 표를 거르는 술어(취소 포함)라 모집단이 다르다. 같은 라벨을 쓰면 한 화면에서 두 숫자가
  어긋나 보인다(템플릿 670행 주석이 이미 그 이유를 적어 두었다). 처리 칩은 **행 배지와 같은 말**로만
  맞췄다.
- **관계 배지(`추가결제`/`재결제`)에 화살표·상대 주문번호를 달지 않았다.** 이력은 `추가결제 → #4978`
  까지 내지만 처리 탭 집(`_group_queue`)에는 상대 주문 id 가 없다 — 서버 필드 추가가 필요해 범위 밖.
  신규를 빈 문자열로 주는 규약도 이력(`NEW` 고정)과 일부러 다르다(코드 106~109행 주석: **두 규약을
  서로 옮기지 마라**).
- **발송처리 축을 처리 탭 행에 달지 않았다.** 결정 D4(전부 달면 배지가 배경이 된다)와 충돌한다.
- **옛 화면 2개는 건드리지 않았다** — `naver_ingest.html` · `naver_triage.html` 은 옛 어휘를 유지한다
  (§10.9 · `test_naver_admin_surface.py:217`). 서버 `_place_view` 라벨(`발주확인 전`)도 그 화면들이
  쓰므로 그대로 뒀다 — 이번 변경은 **워크벤치 템플릿 안의 글자만**이다.

### 19.3 손댄 자리와 검증

`templates/admin/naver_workbench.html` 5자리(칩 라벨 · 행 배지 · 그 낱말을 가리키는 주석 3개) +
낱말을 잠근 테스트 2곳(`test_naver_workbench.py` 칩 라벨 · `test_naver_workbench_row_truth.py` 행 배지).
CSS·JS 무변경이라 자산 `?v` 핀은 그대로다(`20260830c`).

검증: `tests/services/integrations/` **1082 passed** · `APP_OK` · `pre_push_smoke` exit 0.

### 19.4 운영 승격 — 대기 (사용자 결정 2026-08-31)

낱말 통일 커밋은 **스테이징(deploy)에만** 있다. deploy CI 전 워크플로 green
(FOMS CI · PostgreSQL Lane · Harness CI · perf-gate 4/4).

**다음 네이버 작업과 함께 몰아서 승격한다** — 사용자 결정. 이유: 2026-08-30~31 하루에 운영이
세 번 앞섰고(#197 · #196 · 내 #200), 승격 PR 을 자주 파면 그때마다 자산 핀·인벤토리 충돌을
다시 푼다(§18.1). 낱말 하나를 위해 그 왕복을 치르지 않는다.

승격할 때 가져갈 커밋: `e845a7fd`(deploy 에서는 push_own 이 만든 사본 SHA).
같이 볼 것 — 이 커밋은 템플릿 글자와 테스트 2곳뿐이라 마이그레이션·자산 핀 의존이 없다.
