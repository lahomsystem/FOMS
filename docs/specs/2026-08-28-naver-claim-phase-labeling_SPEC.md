# 네이버 클레임 **단계 축** 도입 — "취소 요청" vs "취소 완료" 구분 표기

- 작성 2026-08-28 · 격리 워크트리 `c:\tmp\nvclaim` (base `bf662993` = origin/deploy tip)
- 발단: 이명관 건(ERP 주문 `#4998`, `external_order_links.id=79`)이 네이버에서 **취소 요청**
  상태인데 워크벤치 관계 표가 `전부 취소` 로만 표기.
- 조사 산출물: `_investigation/{A_claim_pipeline,B_api_fields,C_surfaces,D_live_data,CEO_VERDICT}.md`
  (커밋하지 않는다.)

## 0. 사용자 결정 (2026-08-28 · AskUserQuestion)

| 질문 | 선택 |
|---|---|
| 범위 | **글자 + 폐기 버튼까지** — (가) 후보표 표기 + (나) 유령 띠·soft delete 안전 결함 |
| 확정 전 건의 유령 목록 노출 | **보여주되 '확정 전' 표시 + 접기 버튼 잠금** |
| 색 | **노란색 토큰을 새로 만든다** (이 화면의 2색 규칙을 깨는 결정 — 사용자 명시 선택) |
| 시점 | **다음 작업으로 지금 시작** — 핫픽스 아님, 스펙 → 승인 → 구현 |

## 1. 사실 (검증된 것만)

### 1.1 구분 데이터는 이미 저장돼 있다

운영 DB 읽기전용 전수(`transaction_read_only=on` 확인, 주 세션 직접 재실행):

```
productOrderStatus / claimStatus      건수
PAYED              / (없음)            68
DELIVERING         / (없음)            51
RETURNED           / RETURN_DONE       25
CANCELED           / CANCEL_DONE       15
PAYED              / CANCEL_REQUEST     1   ← link 79 / order 4998
```

`link 79`: `cancelApprovalDate` 없음 · `cancelCompletedDate` 없음 → 승인 전 요청.
`orders.id=4998` 의 `status = 'MEASURE'`.
`triage_state.claim_sync.last_status` 와 `raw_snapshot` 은 160건 전수 일치(드리프트 0).
→ **재수집·재조회 불필요. 결함은 읽는 쪽에 있다.**

### 1.2 결함 지점

| # | 위치 | 무엇이 잘못됐나 |
|---|---|---|
| D1 | `order_candidates.py:218` | `if str(claimStatus or "").strip():` — 값의 **내용을 안 본다**. `CANCEL_REQUEST`·`CANCEL_DONE`·`CANCEL_REJECT`(거부=주문 살아 있음)·`RETURN_*`·`EXCHANGE_*` 가 전부 같은 칸 → `전부 취소` |
| D2 | `ghost_orders.py:46-53` | D1 과 **글자 그대로 같은** truthiness 복사본 |
| D3 | `ghost_orders.py:110-112` + `naver_workbench.html:111` | `claim_kind` 는 `"취소"`/`"반품"` 뿐인데 템플릿이 `{{ row.claim_kind }} 완료` 로 **" 완료"를 무조건 덧붙인다** |
| D4 | `naver_ingest.py:2737-2741` | 그 유령 목록이 **soft delete 허가증**. 승인 전 취소 + `RECEIVED` 면 폐기 버튼이 열린다 |
| D5 | `naver_workbench_pane.html:614·618` | Jinja 가 **한국어 라벨을 `==` 로 비교**. 라벨만 바꾸면 두 분기가 죽고 취소 건이 전부 `else`(살아 있음)로 떨어진다 |
| D6 | `naver_workbench_pane.html:772-776` | 클레임이 있으면 `"고객이 이미 처리했습니다. 할 일 없음."` 단정 — 승인 전 요청에는 **거짓말** |
| D7 | `static/css/admin/naver-workbench.css` | `.wb-cand__claim--alive` 는 템플릿에만 있고 **CSS 규칙이 없다**(회색 추락 중) |

D4 는 오늘 노출 0이다: 문제 건이 `MEASURE`(폐기는 `RECEIVED` 만) + 운영 `CANCEL_REJECT` 0건.
**내일 확률은 0이 아니다** — 그래서 (가)와 같은 변경으로 닫는다.

### 1.3 이미 맞게 동작하는 것 — 건드리지 않는다

- `mapping.py:192-212` `CLAIM_STATUS_LABELS` 15종(`취소 요청`/`취소 처리중`/`취소 완료`/`취소 거부` …)
- `mapping.py:362-365` `BLOCKING_CLAIM_STATUSES` — 거부·철회를 뺀 잠금 화이트리스트
- `claim_watch.py:180` 알림 제목 — 이미 `네이버 취소 요청 — …` 로 정확히 나간다
- pane 헤더 배지 · 큐 · ERP 도크 — `claim.label` 사용, 이미 정확

## 2. 설계 — 단계(phase) 축을 SSOT 한 곳에 만들고, 뭉갠 술어 2벌을 갈아 끼운다

### 2.1 `mapping.py` — 단계 사전 + `extract_claim` 에 키 1개

```python
#: 클레임 **단계**. 라벨(무엇)과 잠금(막을까)에 이어 세 번째 축이다 —
#: "네이버가 이미 확정했나, 아직 요청 상태인가". 승인 전 취소를 '완료'라고 적으면
#: 화면이 사람에게 거짓말을 하고, 그 거짓말이 주문 폐기 버튼까지 연다(2026-08-28).
CLAIM_PHASE_REQUESTED = "requested"   # 접수됐고 네이버가 아직 확정 안 함
CLAIM_PHASE_PROGRESS  = "in_progress" # 처리 중(수거중 등) — 아직 확정 아님
CLAIM_PHASE_DONE      = "done"        # 네이버가 확정
CLAIM_PHASE_REJECTED  = "rejected"    # 거부·철회 = 주문은 살아 있다
CLAIM_PHASE_OTHER     = "other"       # 클레임이지만 위 넷 어디도 아님

CLAIM_PHASES = { ... }   # CLAIM_STATUS_LABELS 15키와 1:1
```

배정(15키 전수):

| phase | 상태 |
|---|---|
| `requested` | `CANCEL_REQUEST` · `CANCEL_REQUESTED` · `RETURN_REQUEST` · `RETURN_REQUESTED` · `EXCHANGE_REQUEST` |
| `in_progress` | `CANCELING` · `COLLECTING` · `COLLECT_DONE` |
| `done` | `CANCEL_DONE` · `RETURN_DONE` · `EXCHANGE_DONE` |
| `rejected` | `CANCEL_REJECT` · `RETURN_REJECT` · `EXCHANGE_REJECT` |
| `other` | `PURCHASE_DECISION_HOLDBACK` |

`COLLECT_DONE` 을 `done` 에 넣지 않는다 — 수거가 끝난 것이지 반품이 확정된 게 아니다.
모르는 상태는 `""`(빈 문자열) — **`done` 으로 추락시키지 않는다**(모르면 파괴적 동작을 안 연다).

`extract_claim()` 반환에 `"phase"` 추가. **기존 키는 하나도 안 바꾼다.**

계약 테스트: `set(CLAIM_PHASES) == set(CLAIM_STATUS_LABELS)` (기존 `BLOCKING ⊆ LABELS` 옆에).

### 2.2 `order_candidates.py::_naver_facts` — D1·D5 수정

- 링크마다 `extract_claim(snapshot)` **1회**. `_detailed_reason()` 의 별도 호출을 이 결과로 대체
  (지금 같은 파일이 `:166` 에서 이미 부르고 `status`/`label` 을 버리고 있다 — 추가 조회 0).
- 카운터를 3개로: `done` · `pending`(`requested`+`in_progress`) · `alive`.
  **`rejected` 와 빈 상태는 `alive`** — 거부는 주문이 살아 있다는 뜻이다(현 결함 수정).
- 새 키 **`claim_code`**(코드 축) + 기존 `claim_label`(표시 축) 동시 반환. 템플릿은 **코드로만
  분기**한다(D5). 한국어 문자열 비교를 없애는 게 이 항목의 목적이다.

| `claim_code` | 조건 | `claim_label`(화면 글자) |
|---|---|---|
| `""` | 링크 0건 | `""` |
| `alive` | `done=0 · pending=0` | `살아 있음` |
| `partial` | `alive>0` 이고 (`done>0` 또는 `pending>0`) | `일부 취소` |
| `all_done` | `alive=0 · pending=0 · done>0` | `전부 취소 완료` |
| `all_pending` | `alive=0 · done=0 · pending>0` | `전부 취소 요청 — 확정 전` |
| `all_mixed` | `alive=0 · done>0 · pending>0` | `전부 취소 — 확정 전 포함` |

후보 행에 `naver_claim_code` · `naver_pending_count` 를 추가로 싣는다
(`repay_reconcile.py:132·143` 의 투영에도 같이 넣는다 — 빠뜨리면 재결제 화면만 옛 축을 본다).

### 2.3 `ghost_orders.py` — D2·D3, 그리고 사용자 Q2

- `_claim_of()` → `_claim_phase_of()`. 모집단 판정은 **`done` 또는 `pending` 인 링크**를 클레임으로
  센다. `rejected` 는 **클레임으로 안 센다** → 거부된 주문이 유령 목록에서 빠진다(현 결함 수정).
- 유령 = 지금처럼 `클레임 링크 수 == 전체 링크 수`. **확정 전 건도 목록에 남는다**(Q2 선택).
- 행에 필드 추가:
  - `claim_phase`: `"done"` · `"pending"` · `"mixed"`
  - `claim_text`: 서버가 만든 **완성 문구** — `"취소 완료"` · `"취소 요청 — 확정 전"` ·
    `"반품 완료"` · `"취소 — 확정 전 포함"`. 템플릿의 `" 완료"` 하드코딩을 없앤다(D3).
- `can_discard = (status in DISCARDABLE_STATUSES) and claim_phase == "done"`.
- `discard_block`: 확정 전이면 `"네이버가 아직 취소를 확정하지 않았습니다 — 확정 후에 접으세요"`.
- `find_repay_candidate_links():173` — 동작 **의도적 불변**(확정 전 집도 짝 후보에서 제외 유지).
  단 `rejected` 는 이제 후보에 포함된다(같은 술어 교체의 부수 효과, 옳은 방향). 범위 (다)는 제외.

### 2.4 `naver_ingest.py` 폐기 라우트 — D4 이중 가드

목록 기반 허가는 유지하고, 그 **뒤에** 한 줄 더 둔다:

```python
if target.get("claim_phase") != "done":
    return jsonify({"success": False, "data": None,
                    "error": "네이버가 아직 취소를 확정하지 않았습니다 — 확정 후에 접으세요."}), 400
```

목록 계산이 나중에 바뀌어도 파괴적 동작이 조용히 열리지 않게 한다.
**신규 라우트가 아니므로** manifest 2종·감사 라벨·audit coverage 계약은 해당 없음(기존 등재분 유지).

### 2.5 템플릿

| 파일:라인 | 변경 |
|---|---|
| `naver_workbench_pane.html:610-624` | 한국어 `==` → `cand.naver_claim_code` 코드 분기. 뱃지 클래스 `--dead`/`--pending`/`--part`/`--alive` |
| `naver_workbench_pane.html:772-776` | `claim_code` 가 `all_pending`·`all_mixed` 면 `"할 일 없음"` 대신 → `"옛 주문 <b>취소 요청</b> — 네이버가 아직 확정하지 않았습니다. 확정 전에는 재결제로 정리하지 마세요."` (D6) |
| `naver_workbench.html:111` | `{{ row.claim_kind }} 완료` → `{{ row.claim_text }}`, 확정 전이면 `wb-ghost__claim--pending` |
| `naver_workbench.html:22·703` | `?v=` 핀 범프(아래 §2.7) |

### 2.6 CSS — 노랑 토큰 신설 (사용자 Q3)

`static/css/admin/naver-workbench.css`:

```css
/* 이 화면의 강조색 3종. 파랑 = 되돌릴 수 있는 것(선택·필터·열린 집),
   빨강 = 되돌릴 수 없는 것(취소·반품 확정), 노랑 = 아직 확정 안 난 것(네이버 승인 대기).
   2026-08-28 이전에는 파랑·빨강 2종이었고 "이 6개만 쓴다"고 적혀 있었다. 승인 전 취소를
   확정과 같은 빨강으로 칠하면 담당자가 확정된 것으로 읽고 주문을 접는다 — 그래서 3종으로 늘렸다. */
--wb-warn: #a16207;        /* 텍스트 — 흰 배경 대비 4.5:1 이상 */
--wb-warn-soft: #fef6e0;
--wb-warn-line: #f0d79a;
```

신규·수정 규칙:
- `.wb-cand__claim--pending` — 노랑 배경·테두리·글자
- `.wb-cand__claim--alive` — **규칙 신설**(D7. 지금 없어서 회색 추락 중)
- `.wb-ghost__claim--pending` — 노랑 글자
- 이 파일의 **모든 `font-size` 는 `calc(Npx * var(--wb-fs, 1))`** 여야 한다
  (`test_naver_workbench_v3_followup.py:455-473` 계약. 고정 px 쓰면 즉시 red)

### 2.7 자산 핀

`naver_workbench.html:22·703` 의 `?v=20260827b` → **`?v=20260828a`**.
`sw.js:82-89` 가 `/static/` 전체를 staticCacheFirst 로 캐시하므로 범프 없으면 옛 CSS 가 서빙된다.
동반 수정: `tests/services/integrations/test_naver_workbench_async_result.py:406`
(`markup.count("?v=20260827b") == 2` → 새 값).

## 3. 테스트

### 3.1 신규 — 음성 대조군 (지금 **0건**이라 결함이 살아남았다)

`test_naver_candidate_evidence.py` · `test_naver_ghost_orders.py` 의 입력은 전수
`CANCEL_DONE`/`RETURN_DONE` 뿐이다. `CANCEL_REQUEST`·`CANCEL_REJECT`·`EXCHANGE_*` 를 이 두
화면에 흘려 보는 테스트가 하나도 없다(grep 0건).

| # | 입력 | 기대 |
|---|---|---|
| N1 | 후보표 · `CANCEL_REQUEST` 만 | `claim_code == "all_pending"` · 화면에 `확정 전` · `--pending` 클래스 |
| N2 | 후보표 · `CANCEL_REJECT` 만 | `claim_code == "alive"` (거부 = 주문 살아 있음) |
| N3 | 후보표 · `CANCEL_DONE` + `CANCEL_REQUEST` | `claim_code == "all_mixed"` |
| N4 | 유령 · `CANCEL_REQUEST` + 주문 `RECEIVED` | 목록에 **뜬다** · `can_discard is False` · `claim_text` 에 `확정 전` |
| N5 | N4 주문에 폐기 POST | **400** + 확정 전 문구 |
| N6 | 유령 · `CANCEL_REJECT` 만 | 유령 목록에서 **빠진다** |
| N7 | 양성 유지(회귀 방어) · `CANCEL_DONE` + `RECEIVED` | 여전히 `can_discard is True` · 폐기 200 |
| N8 | `mapping` 계약 | `set(CLAIM_PHASES) == set(CLAIM_STATUS_LABELS)` |

### 3.2 수정이 필요한 기존 계약 (문자열 정확 일치)

`test_naver_candidate_evidence.py:91·106·123·158·209` · `test_naver_ghost_orders.py:94·118·208` ·
`test_naver_repay_reconcile.py:462` · `test_naver_workbench_relation.py:159·174-175` ·
`test_naver_workbench_async_result.py:406` · `test_naver_return_axis.py:57-79`.

**라벨 문자열을 바꾸는 변경이므로, 위 단언들이 red 로 도는 것이 정상이다.** 초록으로 만들려고
라벨을 되돌리지 마라 — 단언 쪽을 새 문구로 옮긴다.

### 3.3 검증 명령 (전부 `cd /c/tmp/nvclaim && pwd &&` 로 시작)

```
python -c "import app; print('APP_OK')"
python -m pytest tests -k naver -q
python -m pytest tests/contracts tests/domains -q
scripts/ops/pre_push_smoke.ps1        # exit 0 아니면 push 금지
```
스테이징 화면 확인: 스테이징에도 `CANCEL_REQUEST` 1건이 있다(census). 워크벤치에서
① 후보표 뱃지가 `전부 취소 요청 — 확정 전`(노랑) ② 유령 띠 문구 ③ 폐기 버튼 잠김 — 3점 확인.

## 4. 범위 밖 (명시적으로 안 한다)

- **잠금 축(`BLOCKING_CLAIM_STATUSES`)** — `CANCEL_REQUEST` 로 주문 만들기·발주확인을 막는 건
  지금이 옳다. 손대지 않는다. (이 결정이 "거부를 살아 있음으로 돌렸는데 실제로는 취소였다"는
  최악 시나리오를 구조적으로 막는다 — 표기만 바꾸고 잠금은 그대로 두므로.)
- 필터 칩 · 탭 카운트 · 정렬 · 회색줄 — `blocking` boolean 축 그대로.
- 반품 요청/완료 분기 심화 — 운영 `RETURN_REQUEST` **0건**이라 실데이터 증명 불가.
- 부분 취소 케이스 — 운영 0건.
- `claim_watch` 알림 문구 — 이미 정확하다.
- 재결제 짝 후보 규칙 변경(범위 (다)) — 오늘 실효과 0건. 원장에만 남긴다.
- 마이그레이션 0 · 네이버 API 호출 0 · 신규 라우트 0.

## 5. 모르는 것 (정직하게)

- `CANCEL_REQUEST → CANCEL_DONE` 전이를 **누가** 만드는지(자동 승인 여부) 네이버 공식 문서
  근거가 저장소에 없다. `CANCELING`·`CANCEL_REQUESTED`·`CANCEL_REJECT` 실관측 0건.
- 그래서 `phase` 배정은 **낱말 뜻과 실관측 1건**에 기댄다. 틀렸을 때의 손해는
  "유령 정리가 며칠 늦어진다"쪽이고, 파괴적 동작은 `done` 에서만 열리므로 회복 가능하다.
- ~~착수 전 읽기전용 SQL 1회~~ **완료(2026-08-28, 운영 읽기전용)**:
  `productOrder.claimStatus` 보유 41 · `order.claimStatus` 보유 **0** ·
  `cancel` 블록 16 · `return` 블록 25 · **블록만 있고 `productOrder.claimStatus` 가 없는 행 0**
  (전체 164). → `_claim_phase_of` 는 `productOrder.claimStatus` 만 보면 되고 **폴백이 필요 없다**.
  (`extract_claim` 의 3단 폴백은 그대로 둔다 — 그건 더 넓은 소비자를 위한 것이다.)

## 6. 작업량

코드 3파일(`mapping.py` · `order_candidates.py` · `ghost_orders.py`) + 라우트 1(`naver_ingest.py`)
+ 템플릿 2 + CSS 1 + 핀 2곳 · 기존 계약 테스트 ~9곳 수정 · 신규 테스트 8개.
