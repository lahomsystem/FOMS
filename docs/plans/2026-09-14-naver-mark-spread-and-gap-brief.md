# 네이버 마크 전파 + 수집·주문 대조 화면 브리프 (초안)

작성: 2026-09-14 · 브랜치 `deploy` · 선행 `docs/plans/2026-09-13-naver-channel-mark-impl-brief.md`
선행 산출물: 채널 마크 매크로·CSS·DTO 필드는 이미 운영에 있다(production `a5c987816`).

## 0. 사용자 요청 (2026-09-13~14)

1. `https://lahom-production.up.railway.app/` (전체 주문 목록)에도 네이버 마크를 붙인다.
2. `https://lahom-production.up.railway.app/erp/measurement` (실측 탭)에도 붙인다.
3. 네이버 수집분과 ERP 주문을 대조해 **주문이 만들어지지 않은 건**을 찾는다.
   **추가결제·재결제는 제외.** 사용자 결정: 모집단은 "주문이 없는 건 전부"를 사유별로 갈라서 보여준다.

## 1. 이미 있는 것 (다시 만들지 마라)

- 매크로 `templates/partials/shared/channel_mark.html` — `channel_mark(channel_source)`.
  `'NAVER'` 일 때만 인라인 SVG 를 내고, 아니면 **빈 문자열**(공백 한 칸도 안 남는다).
- CSS `static/css/components/foms-channel-mark.css` (`.foms-channel-mark`, height/width 1.25em).
  현재 링크는 `templates/orders/partials/dashboard_styles.html` 한 곳뿐이다(핀 `?v=20260913a`).
- DTO 필드 `channel_source` — `foms/services/orders/dashboard_dto.py:97`.
  판정 축은 **출처 하나**: `structured_data['source'] == SOURCE_MARKER`.
  `LINKED_MARKER_KEY`(`naver_linked`)는 출처가 아니다 — **절대 쓰지 마라**.
- 계약 테스트 `tests/domains/test_dashboard_channel_mark.py` (표면 전수 6곳을 못박는다).
  표면이 늘면 이 테스트의 `SURFACES` 에 **반드시 추가**한다.

## 2. 실측 앵커

### 2.1 `/` 전체 주문 목록
| 무엇 | 위치 |
|---|---|
| 라우트 | `foms/web/orders/listing.py:142` `index()` |
| 행 준비 — `order_display_data` 에 속성을 직접 붙인다 | `foms/web/orders/listing.py:250-257`(`orderer_name` 이 그 본보기) |
| 고객 셀(라홈 로고 자리) | `templates/orders/index.html:877-880` |
| 레이아웃 | `{% extends parent_template|default("orders/layout.html") %}` — `dashboard_styles.html` 을 **안 싣는다** |

### 2.2 `/erp/measurement` 실측
| 무엇 | 위치 |
|---|---|
| 라우트 | `foms/web/measurement/dashboard.py:172` `erp_measurement_dashboard()` |
| PC 목록 행 루프 | `templates/measurement/partials/dashboard_main.html:820-830` (`r.customer_name`, `r.structured_data`, `r.is_erp_order` 가 이미 행에 있다) |
| 모바일 히어로 | `templates/measurement/partials/mobile_list.html:44` |
| 태블릿 카드 | `templates/measurement/partials/tablet_split_body.html:66` |

### 2.3 CSS 배달 — 지금 방식으론 두 화면에 안 실린다
`dashboard_styles.html` 은 `templates/orders/partials/dashboard_main.html:138` 한 곳에서만 include 된다.
`/` 와 `/erp/measurement` 는 그 경로를 안 탄다. 컴포넌트 CSS 의 전역 관례는
`templates/partials/shared/layout_head.html`(예: `:241-250` 에 `foms-sticky-action-bar.css` 등).

### 2.4 대조 화면이 들어갈 자리
네이버 워크벤치가 이미 탭 셸을 갖고 있다 — `처리`(work) · `이력`(all).
- 라우트 `foms/web/admin/naver_ingest.py:1815` `naver_ingest_triage()` → 게이트 ON 이면 `_render_workbench(db)` (`:2230`)
- 탭 정규화 `:2575` 부근, 템플릿 탭 마크업 `templates/admin/naver_workbench.html:33-42`
- 권한: `@role_required(["ADMIN","MANAGER","STAFF"])`, 이력 탭은 `_can_view_history()`

## 3. 대조 규칙 — 운영 실측으로 확정한 것 (2026-09-14, 읽기 전용 1회)

정본 테이블 `external_order_links`(`models.ExternalOrderLink`). 쓰는 컬럼:
`channel, external_id, order_id, external_order_no, sync_status, relation,
product_order_status, claim_status, group_key, recipient_phone_digits, payment_amount, raw_snapshot`

### 3.1 순진한 질의는 틀린다
`order_id IS NULL AND relation='NEW'` → 운영 **1,899건**. 그런데 **`relation` 으로는 추가결제를 못 거른다** —
상품명이 그대로 `추가결제` 인 **279건이 `relation='NEW'`** 다. 사용자가 빼라고 한 바로 그것이 통과한다.
갈라야 하는 축은 `relation` 이 아니라 **`raw_snapshot->productOrder->>productClass` 와 상품명**이다.

### 3.2 확정 분류 (운영 실측치)

| 분류 | 술어 | 운영 건수 |
|---|---|---|
| **빠짐 후보** | 아래 `살아있는 본품` + ERP 에 같은 `recipient_phone_digits` 주문이 **없음** | **93** (91집 · 9,038만원) |
| **붙이기 대상** | `살아있는 본품` + 같은 전화의 ERP 주문이 **있음** | 227 |
| 부가 라인 | `productClass = '추가구성상품'` **또는** 상품명 `= '추가결제'` | 1,080 |
| 종결 | `product_order_status IN ('CANCELED','RETURNED')` 또는 클레임 확정 | 444 |
| (합) | | 1,899 |

`살아있는 본품` 술어:
```sql
channel='NAVER' AND order_id IS NULL AND relation='NEW'
AND product_order_status='PURCHASE_DECIDED'
AND coalesce(claim_status,'')=''                    -- 빈 문자열이다. IS NULL 로 쓰면 0건이 나온다
AND raw_snapshot->'productOrder'->>'productClass' IN ('조합형옵션상품','단일상품')
AND coalesce(payment_amount,0) > 0
```

### 3.3 함정 (전부 이번 실측에서 실제로 밟았다)
1. **`claim_status` 는 NULL 이 아니라 빈 문자열**이다. `IS NULL` 로 쓰면 1,400건이 0건이 된다.
2. **`relation` ≠ 추가/재결제 축.** 상품명 `추가결제` 279건이 `NEW` 다.
3. **`order_id IS NULL` 에는 "지워진 주문"도 섞인다**(`ON DELETE SET NULL`). `sync_status` 를 같이 봐야 한다.
   운영 실측에서는 전량 `COLLECTED` 였다.
4. **227건은 빠진 게 아니다.** 2026-09-01 백필이 5~8월 과거 주문을 끌어온 것이고, 그 주문들은 ERP 에
   수동 입력돼 이미 있다(링크만 없다). 320건 중 216묶음이 2026-08 이전 주문번호다.
   이걸 안 가르면 화면이 "빠진 주문 320건"이라고 거짓말한다.
5. 전화 대조는 **휴리스틱**이다(같은 번호 ≠ 같은 주문). 그래서 93은 **하한**이고, 화면 문구는
   "후보"라고 말해야 한다. 단정하는 문구 금지.
6. 형제 대조: 빠짐 후보 320건은 같은 `group_key` 형제 중 주문을 가진 것이 **하나도 없다**(집 통째 부재).

## 4. 파일 소유권 표 (겹치면 안 된다)

| 워커 | 편집 허용 | 금지 |
|---|---|---|
| **W1 대조 서비스** | 신규 `foms/services/integrations/naver_commerce/order_gap.py`, 신규 `tests/domains/test_naver_order_gap.py` | 라우트·템플릿·CSS 전부 |
| **W2 마크 전파** | `foms/web/orders/listing.py`, `templates/orders/index.html`, `foms/web/measurement/dashboard.py`, `templates/measurement/partials/dashboard_main.html`, `templates/measurement/partials/mobile_list.html`, `templates/measurement/partials/tablet_split_body.html`, `templates/partials/shared/layout_head.html`, `tests/domains/test_dashboard_channel_mark.py` | 워크벤치·대조 서비스 |
| **W3 대조 화면** | `foms/web/admin/naver_ingest.py`, `templates/admin/naver_workbench.html`, `static/css/naver/naver-workbench.css`(있으면), 신규 `templates/admin/partials/naver_gap_pane.html` | W1·W2 소유 파일 전부 |

W3 는 W1 의 서비스를 **호출만** 한다. 계약(아래)이 고정이라 파일이 아직 없어도 호출부를 쓸 수 있다.

### 4.1 W1 ↔ W3 고정 계약
```python
# foms/services/integrations/naver_commerce/order_gap.py
GAP_MISSING = "missing"      # 빠짐 후보
GAP_ATTACHABLE = "attachable"  # 붙이기 대상(ERP 에 이미 있음)
GAP_EXTRA = "extra"          # 부가 라인(추가구성·추가결제)
GAP_CLOSED = "closed"        # 취소·반품 확정

def summarize_order_gap(db) -> dict:
    """분류별 건수·금액 합계. {'missing': {'count': 93, 'amount': 90383500}, ...}"""

def list_order_gap(db, *, bucket: str, limit: int = 200, offset: int = 0) -> list[dict]:
    """행 목록. 각 행 키:
    link_id, external_order_no, collected_date, product_name, payment_amount,
    recipient_name_masked, naver_status, bucket
    """
```
- **개인정보**: 수취인 이름은 마스킹해서 낸다(`홍*동`). 전화번호·주소는 **행에 싣지 않는다**
  (raw_snapshot 은 관리자 전용이라는 모델 docstring 계약).
- 네이버 HTTP 를 내지 않는다 — DB 만 읽는다(WORKER 단일 출구 계약).

## 5. 검증 명령

```bash
cd "C:/DEV/FOMS"
python -c "import app; print('APP_OK')"; echo "EXIT=$?"
python -m pytest tests/domains/test_naver_order_gap.py tests/domains/test_dashboard_channel_mark.py -q; echo "EXIT=$?"
python -m pytest tests/domains/test_dashboard_control_tower.py tests/domains/test_dashboard_cache.py tests/harness/ -q; echo "EXIT=$?"
```
종료 코드를 파이프 뒤에서 읽지 마라.

## 6. 워커 공통 규칙

- `cd "C:/DEV/FOMS" && pwd` 로 시작. **git 명령 전면 금지**(총괄 몫). 워킹트리를 여러 창이 공유한다.
- 소유권 밖 파일은 읽기만. 줄끝(CRLF/LF)은 **편집 전 상태 그대로** 유지하고, 편집 후
  `git` 없이 바이트로 확인한다(파일을 파이썬으로 쓰면 줄끝이 뒤집혀 전량 재작성 diff 가 난다 — 2026-09-13 실사고).
- 인라인 `style="` 금지(ratchet). jQuery 금지. UTF-8. 한글 UI, 한자 금지.
- 치환 스크립트는 앵커 개수를 먼저 세고 기대와 같을 때만 파일을 쓴다. 파일별 수정 자리 수를 보고한다.
- 표면을 늘리면 `test_dashboard_channel_mark.py` 의 `SURFACES` 를 같이 늘린다(W2 몫).

## 7. 이 브리프는 초안이다

CEO 는 §3 술어와 §4.1 계약을 정밀화해도 된다. §4 파일 경계만 유지한다.
