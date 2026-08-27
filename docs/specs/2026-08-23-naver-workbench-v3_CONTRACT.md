# 네이버 수집 워크벤치 v3 — 구현 계약 (2026-08-23)

목업 정본: `docs/design/mockups/naver-workbench-v3.html` (브라우저로 열어 볼 것)
근거: 3CEO 토론(현장 가치·불가역 위험·비용 순서). 사용자가 지목한 통증 2개 =
**① 한 집 처리하려고 탭을 오간다 ② 행을 누를 때마다 페이지가 통째로 새로 뜬다.**

작업 위치: `c:\tmp\foms-s-naver-ingest` (브랜치 `session/naver-ingest`)
게이트: `FOMS_NAVER_WORKBENCH_ENABLED` + `FOMS_NAVER_WORKBENCH_COHORT`(스테이징 38 단독).
**게이트 OFF 경로(`templates/admin/naver_triage.html`)는 손대지 않는다** — 롤백 경로이자 기존 계약 테스트 green 유지선.

---

## 0. 절대 규칙 (어기면 사고)

1. **상세는 항상 한 집만 열린다.** 동시에 여러 집을 펼치는 UI 금지. 액션·모달 DOM id 는
   문서에 하나뿐이라는 전제가 코드 전반에 있다(중복되면 5번째 행 취소가 1번째 집에 나간다).
2. **모달 재진술 건수 == 서버가 처리할 건수.** pane 의 집은 반드시
   `_group_of_link`(주문번호 + `household_key` 전체)로 만든다. 큐 모집단으로 만들지 않는다.
3. **이력(all) 탭 행에는 액션 버튼·`data-link-id` 를 달지 않는다.** 불가역 mutation 라우트는
   전부 STAFF 까지 열려 있다 — 이력 행을 누를 수 있게 만들면 STAFF 가 과거 주문 전체에
   취소·발송 버튼을 갖는다.
4. **STAFF 응답에 이력 데이터·"전체 이력" 문자열이 0이어야 한다.** 탭을 숨기는 게 아니라
   컨텍스트를 만들지 않는다(현행 유지).
5. **벌크 대상 ⊆ 화면 목록.** 체크박스는 화면에 보이는 행에만 달리고, 서버로 보내는 집 키는
   그 행들에서만 나온다. `전부 선택`은 **현재 필터로 보이는 행**만 고른다.
6. 취소·반품 집, 취소한 집은 행부터 잠근다(체크박스 disabled + 액션 전부 닫힘).

---

## 1. 화면 구조 (목업과 1:1)

```
[스트립]  네이버 수집   N집 · 상품주문 M건            (우측: 마지막 수집 / 다음 수집)
[탭 2개]  처리 <N집>   |   이력 <70집> (ADMIN 전용)
[칩 4개]  전체 N집 · 발주확인 전 N집 · 추가결제·재결제 N집 · 취소·반품 N집
[벌크바]  (선택 0이면 숨김) N집 선택됨 [선택한 집 발주확인 보내기] [선택 해제]
[2단]     좌: 목록(한 집 한 줄, max-height 없음)   |   우: 상세(sticky)
```

- 탭 `place`·`claim` 은 **없어진다**. 같은 목록의 필터 칩으로 내려온다.
- 스트립의 `수집 상태` 버튼은 **제거**(바로 아래 이력 탭과 같은 곳을 가리키던 중복).

---

## 2. 서버 계약 — `foms/web/admin/naver_ingest.py`

### 2.1 탭

```python
WORKBENCH_TABS = ("work", "all")          # place·claim 제거
```

`_active_tab()`:
- `?tab=place` → `"work"` 로 정규화하고 **필터를 place 로 강제**(옛 주소·북마크 호환).
- `?tab=claim` → `"work"` + 필터 `claim`.
- `all` 은 기존대로 ADMIN 아니면 `work`.

### 2.2 필터

```python
WORKBENCH_FILTERS = ("all", "place", "rel", "claim")   # 기본 "all"
def _active_filter() -> str   # ?f= 를 읽어 정규화. 모르는 값은 "all".
```

판정 술어(집 dict 기준):
| 필터 | 조건 |
|---|---|
| `all` | 전부 |
| `place` | `place_pending and not claim_blocking and not canceled` |
| `rel` | `relation in ("ADDON","REPAY")` |
| `claim` | `claim_blocking or canceled` |

### 2.3 목록 모집단 — 새 함수 `_work_groups(db)`

**지금 두 목록이 따로 있어서 숫자가 어긋난다.** 하나로 합친다.

```python
def _work_groups(db) -> tuple[list[dict[str, Any]], bool]:
    """처리 탭 목록 = 확인 큐 ∪ 발주확인 전 집 (집 단위 병합).

    Returns:
        (집 목록, 조회 상한에 걸렸는지)
    """
```

- 원천 1 = 기존 `queue`(`_group_queue`, `COLLECTED|LINKED` + `reviewed_at IS NULL`)
- 원천 2 = 기존 `_place_groups(db)` (확인 완료돼 큐에서 빠졌지만 아직 발주확인 안 된 집)
- **집 키로 dedup**. 같은 집이 양쪽에 있으면 큐 쪽 dict 를 채택하고 `place_pending` 만 병합.
- 각 집 dict 가 반드시 갖는 키(템플릿·JS 가 이 이름을 쓴다):
  `id`(대표 link_id) · `link_ids` · `count` · `customer_name` · `product` · `extra_count` ·
  `created_at` · `relation` · `place_pending` · `claim_blocking` · `claim_label` · `canceled` ·
  `close_now` · `order_id` · `next_step` · `in_queue`(bool, 원천 1 출신인가)
- 정렬: 기존 큐 정렬(`created_at desc`) 유지. 원천 2 만 있는 집은 그 뒤에 같은 규칙으로.
- `truncated` 는 둘 중 하나라도 상한에 걸리면 True.

### 2.4 렌더 컨텍스트 (템플릿이 쓰는 이름 — 이 목록이 전부다)

```
active_tab            "work" | "all"
active_filter         "all" | "place" | "rel" | "claim"
work_groups           _work_groups() 결과 중 **현재 필터로 거른 것**
filter_counts         {"all": n, "place": n, "rel": n, "claim": n}   # 필터 전 전체에서 계산
group_count           len(전체 집)          # 목록 길이 = 칩 '전체'
actionable_count      손댈 수 있는 집 수     # **탭 배지**·nav 뱃지 = 같은 값 (2026-08-24 개정)
locked_count          group_count - actionable_count   # 스트립 '손대지 않음'
pending_count         sum(count)            # 스트립 "상품주문 M건"
work_truncated        bool
selected              _triage_pane(...) | None
selected_group        _group_of_link(...) 결과 (절대 규칙 2)
selected_household_claimed / member_rows / sales_users / cancel_reasons / can_view_history
history / ingest_status / failures         # 기존과 동일 (all 탭 + ADMIN 조건 유지)
```

**2026-08-24 2차 개정 — 한 줄에서 한 번만 말한다.** 상단 4줄(이름·탭·칩·도구)을 2줄로
접으면서, 집 수를 말하는 자리를 **탭 배지 하나**로 줄였다. 스트립과 탭 배지가 같은 수를
나란히 반복하면 어긋날 여지가 생기고, 한 줄에 붙으면 그 중복이 그대로 눈에 띈다. 어긋나지
않게 하는 가장 확실한 방법은 한 번만 말하는 것이다.

- 머리줄 = `네이버 수집` + 탭(집 수 소유) + **탭 배지가 말할 수 없는 사실**
  (`상품주문 N건` · `손대지 않음 M집`) + 글자 크기. 뒤 둘은 처리 탭의 사실이므로
  이력 탭에서는 내지 않는다.
- 도구줄 = 필터 칩(낱개 알약 + 숫자) + `정렬`(붙은 세그먼트) + `찾기`.
  칩과 정렬은 **모양으로** 가른다 — 둘 다 알약이면 한 줄에서 역할이 섞인다.
- 두 줄 모두 sticky. 고정 높이는 예전(탭+도구)과 같고 보이는 사실만 늘었다.

**2026-08-24 개정 — 숫자의 정의**: 스트립·탭 배지·nav 뱃지는 `group_count`(목록 길이)가
아니라 **`actionable_count`(손댈 수 있는 집)** 를 말한다. 취소·반품 집은 목록에 남지만 어떤
액션도 되지 않는데, 그 집까지 세면 담당자가 매일 아침 보는 업무량이 실제 처리 대상보다 크다
(2026-08-24 스테이징 실측: 확인 큐 72집 중 **13집(18%)**).

목록에서 지우지 않는 이유: STAFF 는 이력 탭이 없어(절대 규칙 3·4) '취소·반품' 칩이 유일한
조회 창구이고, 그 칩의 모집단도 이 목록이다. 지우면 다시 찾을 자리가 사라진다.

그래서 **목록은 그대로 두고 숫자만 쪼갠다**. 화면에 셋이 모두 라벨과 함께 보이고 산수가
맞아야 한다 — `actionable_count` + `locked_count` == `group_count` == `filter_counts["all"]`,
그리고 `locked_count` == `filter_counts["claim"]`. 술어는 `claim` 칩과 **같은 것**
(`_group_matches_filter(group, "claim")`)을 쓴다. 이것이 "한 화면 두 말"이 아닌 이유는
분해된 두 수가 같은 줄에 함께 있기 때문이다.

**제거되는 컨텍스트 키**: `claim_groups`, `place_groups`, `place_group_count`, `place_truncated`.

### 2.5 새 라우트 — pane 프래그먼트 (읽기 전용 GET)

```python
@admin_bp.route("/admin/naver-ingest/triage/pane")
@login_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def naver_ingest_triage_pane():
    """상세 pane 조각만 돌려준다 — 행을 눌러도 페이지를 통째로 다시 받지 않게."""
```

- 입력: `?link_id=<int>` (필수). 없으면 400.
- 게이트 OFF 사용자는 **404**(그 화면에는 이 경로가 없다).
- 응답: `templates/admin/partials/naver_workbench_pane.html` 렌더 결과 **조각만**
  (`<!doctype>`·레이아웃 없음). Content-Type text/html.
- pane 컨텍스트는 위 2.4 의 `selected*`·`member_rows`·`cancel_reasons`·`sales_users` 와
  **완전히 같은 방식**으로 만든다. 별도 계산 경로를 만들지 말 것(모집단이 갈라진다).
- mutation 이 아니므로 write manifest 등재는 하지 않는다. 감사 라벨도 없다.

---

## 3. 템플릿 계약

### 3.1 파일

- `templates/admin/naver_workbench.html` — 셸(스트립·탭·칩·벌크바·목록·모달 컨테이너)
- `templates/admin/partials/naver_workbench_pane.html` — **신설**. 상세 pane 전부
  (헤더 + 액션 5종 + 대조표 + 상품주문 표 + 관계 섹션 + 모달 3종).
  전체 렌더와 프래그먼트 응답이 **이 파일 하나**를 공유한다.

### 3.2 DOM 계약 (JS·테스트가 이 이름을 문다)

목록/셸:
| 선택자 | 뜻 |
|---|---|
| `#wb-queue` | 목록 컨테이너 |
| `a.wb-row[data-group-id][data-link-id][href]` | 집 한 줄. href 는 전체 페이지 폴백용으로 **유지** |
| `.wb-row[aria-current="true"]` | 지금 열린 집 (한 줄만) |
| `input.wb-pick[data-group-id]` | 벌크 체크박스. 잠긴 행에는 `disabled` |
| `#wb-bulk` / `#wb-bulk-n` / `#wb-bulk-submit` / `#wb-bulk-clear` / `#wb-pick-all` | 벌크 바 |
| `.wb-chip[data-filter][aria-pressed]` | 필터 칩 |
| `#wb-pane` | 상세 pane 루트. **프래그먼트 응답의 최상위 요소도 이것** |

pane 안(파셜):
| id | 뜻 |
|---|---|
| `#wb-create-order` / `#wb-modal-create` | 주문 만들기 |
| `#wb-confirm` / `#wb-modal-confirm` / `#wb-confirm-submit` | **발주확인 단건 (신설)** |
| `#wb-dispatch` / `#wb-modal-dispatch` / `#wb-dispatch-confirm` | 발송처리 |
| `#wb-cancel` / `#wb-modal-cancel` / `#wb-cancel-confirm` / `#wb-cancel-reason` / `#wb-cancel-detail` | 취소처리 |
| `#wb-review-done` | **확인 완료 — 큐에서 빼기 (모든 집으로 복원)** |
| `#wb-attach` / `#wb-detach` | 붙이기 / 되돌리기 |

- 기존 `#wb-claim-done` 은 `#wb-review-done` 으로 **이름을 바꾸고 모든 집에 낸다**.
- 기존 `#wb-place-submit`·`#wb-place-n`·`#wb-modal-place`·`#wb-place-confirm` 은
  벌크 바로 옮긴다: `#wb-bulk-submit`·`#wb-bulk-n`·`#wb-modal-bulk`·`#wb-bulk-confirm`.

### 3.3 액션 버튼 노출 규칙 (pane)

`locked = claim_blocking or canceled` 일 때 아래 4개 전부 `disabled`.

| 버튼 | 열리는 조건 | 잠길 때 title |
|---|---|---|
| 주문 만들기 | `not order_id and not locked` | 취소·반품/취소한 집/이미 주문 있음 사유 |
| **발주확인** | `place_pending and not locked` | `이미 발주확인이 끝났습니다` / 잠금 사유 |
| 발송처리 | `not locked and (not place_pending or close_now)` | `발주확인이 먼저입니다(발주확인 전 상품주문이 있습니다)` |
| 취소처리 | `not locked and not dispatched_at` | — (발송된 집은 버튼 자체를 내지 않는다) |
| 확인 완료 | **항상** (잠긴 집도 큐에서는 뺄 수 있어야 한다) | — |

안내 문구(목업 문장 그대로):
- 신규 + 발주확인 전 → `신규 집이라 발주확인이 먼저입니다. 발송처리는 실제 출고·시공 시점에 누르세요.`
- ADDON(`close_now`) + 발주확인 전 → `추가결제는 물건이 따로 나가지 않습니다 — 발주확인 없이 여기서 바로 발송처리를 보냅니다.`
  (REPAY 는 D1 개정 2026-08-24 로 이 가지에서 빠졌다 — 원 주문의 물건이 나중에 한 번 나간다.)
  머리 `물건이 따로 나가지 않습니다` 는 **고정 문자열**이다 — 계약 테스트가 이 문장으로 `close_now` 를 가른다.
- 취소한 집 → `이 집은 취소 완료입니다. 발주확인·발송처리·주문 만들기가 모두 닫혀 있습니다.`
- 발송처리 버튼 라벨은 `close_now` 와 **무관하게 항상 `발송처리`** (D1 개정 2026-08-27).
  모달 제목 `발송처리를 보내기 전에 확인하세요` · 확인 버튼 `발송처리 보내기` 도 무조건이다 —
  같은 호출인데 이름이 둘이면 사람이 다른 기능으로 읽는다(모달 본문은 이미 '발송처리' 어휘였다).
  `close_now` **술어·`can_dispatch` 게이트는 불변** — 바뀐 것은 라벨뿐이다.

---

## 4. JS 계약 — `static/js/admin/naver-workbench.js`

1. **전부 이벤트 위임으로 전환.** `document.getElementById(...).addEventListener` 단발 배선
   금지 — pane 이 교체되면 죽는다. `document.addEventListener('click', e => e.target.closest(...))`.
2. **행 클릭 = 부분 갱신.**
   - `a.wb-row` 클릭 → `preventDefault()` → `fetch('/admin/naver-ingest/triage/pane?link_id=N')`
   - 성공: `#wb-pane` 을 응답으로 **교체**, `aria-current` 이동, `history.pushState` 로 주소 갱신
   - 실패(네트워크·비200): `preventDefault` 를 되돌릴 수 없으므로 `location.href = row.href`
     로 폴백(진행이 막히면 안 된다)
   - 체크박스 클릭은 **행 열기가 아니다**(`closest('input.wb-pick')` 이면 즉시 return)
   - 갱신 중 중복 클릭 차단(요청 토큰 비교 — 늦게 온 응답이 새 선택을 덮지 않게)
3. **벌크**: 체크 변화마다 `#wb-bulk` 토글 + 건수 갱신. `전부 선택`은 **화면에 보이는
   `input.wb-pick:not([disabled])`** 만. 모달 문장에 집 수와 **상품주문 건수**를 함께 재진술.
4. **발주확인 단건**: `#wb-confirm-submit` → `POST /admin/naver-ingest/<link_id>/fulfillment`
   body `{action:'confirm'}` (기존 라우트). 성공 시 pane 재요청으로 갱신.
5. 취소·발송·주문 만들기·붙이기·되돌리기·확인 완료·재시도·지금 수집은 **기존 엔드포인트·
   기존 페이로드 그대로**. 배선 방식만 위임으로 바꾼다.
6. `fetch` 는 전부 `try/catch` + `data.success` 검증(프로젝트 규칙). CSRF 헤더 기존 방식 유지.
7. 인라인 스크립트 금지·jQuery 금지 유지.

---

## 5. CSS 계약 — `static/css/admin/naver-workbench.css`

- `.wb-queue` 의 `max-height: 640px; overflow:auto` **제거** — 페이지가 스크롤한다.
- `#wb-pane` 을 `position: sticky; top: 12px` (991.98px 이하에서는 해제, 1단으로 접히는 기존
  브레이크포인트 유지).
- 신규: `.wb-chips`/`.wb-chip`, `#wb-bulk`(선택 0이면 `display:none`), `.wb-pick`,
  `.wb-row--locked`(흐림 + 이름 취소선).
- 인라인 스타일 금지. 색은 기존 토큰/변수 체계를 따른다.
- **`?v` 핀 범프 필수**: `templates/admin/naver_workbench.html` 의 css·js 쿼리 두 곳
  `?v=20260823a` → `?v=20260823b`.

---

## 6. nav·이름 계약

| 자리 | 지금 | 바꿀 것 |
|---|---|---|
| `foms/services/menu_config.py:54` | `네이버 주문` | `네이버 수집` |
| `templates/partials/shared/layout_nav.html:85-87` | `네이버 수집` → dashboard | **삭제**(게이트 ON 이면 리다이렉트라 제자리 뛰기) |
| `layout_nav.html:88-94` | `수집 확인` → triage | `네이버 수집` 으로 개명, 뱃지 유지. 진입구는 이거 하나 |
| `naver_workbench.html:29-35` | `수집 상태` 버튼 | **삭제** |

**뱃지 숫자 일치**: nav 뱃지는 `처리 탭 목록 길이`(= `_work_groups` 결과 집 수)와 같아야 한다.
`foms/services/naver/triage_count.py` 를 그 정의로 맞추고 30초 캐시는 유지한다.
지금은 nav 67 · 탭 45 로 어긋난다.

---

## 7. 완료 기준 (각 작업자 공통)

- `python -c "import app; print('APP_OK')"`
- 담당 범위의 계약 테스트 green. 마크업이 바뀌어 깨진 테스트는 **삭제가 아니라 갱신**한다.
  단언이 지키던 뜻(모집단·권한·잠금)을 새 마크업에서 다시 표현할 것.
- 새로 추가할 계약 테스트(4번 작업자):
  1. 처리 탭 목록 길이 == 스트립/탭 배지 == `filter_counts["all"]`
  2. 칩 4종 각각의 필터 결과가 술어와 일치
  3. STAFF 응답에 `전체 이력`·이력 데이터 문자열 0 (기존 3건 유지)
  4. pane 프래그먼트 응답이 조각이다(`<html` 없음) + 게이트 OFF 404 + `link_id` 없으면 400
  5. pane 의 집 == `_group_of_link` 결과(모달 재진술 건수 == 서버 처리 건수)
  6. 잠긴 집(취소·클레임)에서 4버튼 disabled, 확인 완료만 열림
  7. 문서 전체에서 `id="wb-` 중복 0
  8. 이력 탭 행에 `data-link-id`·액션 버튼 0
