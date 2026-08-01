# AS 대시보드 개편 구현 플랜 — 구조화 타임라인 + 무상/유상 2단계 판정 (B안)

- 날짜: 2026-07-24
- 스펙(SSOT): `docs/specs/2026-07-24-as-dashboard-timeline-redesign-design.md`
- 상태: 구현 대기 (스펙 사용자 방향 승인 완료)

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:subagent-driven-development`.
> 각 Task는 독립 검증 가능한 산출물이다. TDD 순서(실패 테스트 작성 → 실패 확인 → 최소 구현 → 통과 확인 → 커밋)를 엄수하라. 코드 블록은 그대로 옮겨 쓸 수 있게 작성됐다("적절히 처리" 없음). Modify 스텝의 라인 번호는 착수 시점에 재확인하라(이 플랜 작성 이후 파일이 이동했을 수 있음).

---

## Goal

AS 내용을 통짜 문자열 덮어쓰기에서 **append-only 구조화 타임라인**으로 전환하고, **무상/유상 2단계 판정(추정→확정)**을 도입한다. 동시 편집 clobber 결함을 제거하고, 유상 건 식별·필터·매출 추적을 가능하게 하며, PC/모바일/무한스크롤 3표면을 단일 매크로(SSOT)로 통합한다.

## Architecture

- **데이터**: 신규 테이블 없음. `sd['shipment']`에 두 키 신설 — `as_log`(append-only 항목 리스트), `as_billing`(판정 dict). `as_content`/`as_content_2`는 신규 쓰기 퇴역, 읽기는 **lazy 마이그레이션**으로 흡수(대시보드 렌더 시 legacy 항목 변환, 최초 append 시 영구화).
- **API**: 기존 `erp_orders_as_bp`(url_prefix `/api/orders`)에 `POST as/log`·`PATCH as/log/<log_id>`·`POST as/billing` 추가. `POST as/register` 확장. 조회는 `erp_as_page_bp`(url_prefix `/erp`)에 `GET /as/timeline/<id>` fragment 추가(모바일 `card-detail` lazy 패턴 복제).
- **도메인 서비스**: `as_orders.py` 비대 방지를 위해 로그 도메인 로직은 신규 `foms/services/orders/as_log.py`로 분리.
- **렌더**: `render_as_content_tabs` 매크로 → `render_as_timeline` 매크로 교체. 앵커 고정(접수 원문/legacy) + 역시간순 스트림 + quick-add. 3표면(PC 확장 행·모바일 카드 상세·무한스크롤 청크) 자동 반영.
- **입력기**: `contenteditable` 폐기 → `<textarea>`. 리치툴바·2탭·autosave 경로 퇴역. `sales_delivery` 토글은 리치툴바에서 확장 행/모바일 상세 헤더로 이전.

## Tech Stack

Flask 2.3 · SQLAlchemy 2.0 (JSONB) · PostgreSQL 15+ · Jinja2 매크로 · Vanilla JS(document 위임 + `window.__FOMS_*_BOUND` 싱글톤) · pytest.

## Global Constraints (프로젝트 규약 — 전 Task 공통)

1. **structured_data 수정**: `copy.deepcopy` + `flag_modified` 필수. as_orders.py는 `_load_order_structured_data_for_update(order)`(무손실 로드) + `ensure_path(sd, "shipment")` 재사용.
2. **타임스탬프**: `from foms.services.datetime_kst import now_utc_naive` 사용. `datetime.datetime.now()` **금지**. as_orders.py:100 기존 위반은 T1에서 함께 수정.
3. **API 응답**: `{'success': True/False, ...}` 통일. 실패는 `{'success': False, 'message': ...}` + 상태코드(검증 400, 낙관/무결성 409, 서버 500).
4. **신규 함수**: docstring 필수, 타입힌트 필수, 50줄 이하, 한 가지 역할.
5. **프론트**: 인라인 스타일 금지(→ `as-dashboard-body.css`/`foms-as-mobile-card.css`), jQuery 금지(`querySelector`/`fetch`), fetch는 try/catch + `data.success` 검증, 신규 리스너는 document 위임 + `window.__FOMS_*_BOUND` 싱글톤 가드(perf 가드 G4).
6. **JS/자산 변경**: `?v=` 캐시 버스트 범프 + 참조 핀 전수 grep 후 치환 파일 전부 커밋(SW staticCacheFirst 함정).
7. **커밋**: 한글 메시지, UTF-8 파일 작성 후 `git commit -F <파일>` (`-m "한글"` 금지), 커밋 후 임시 파일 삭제.
8. **검증**: `.py` 편집 후 `python -c "import app; print('APP_OK')"` 통과 필수. 테스트는 `tests/domains/test_as_*.py` 패턴 모방(`_login_as_admin`/`_create_as_order`/`db_session`/`client`).
9. **성능**: billing 필터는 JSONB `->>` 등호 비교(hot path ILIKE 금지 준수), 머지 전 `EXPLAIN`으로 Seq Scan 없음 확인. fragment 바이트 예산: 타임라인 전체는 확장 시에만, 셀은 요약만 eager.

---

# Phase P1 — 무상/유상 (독립 배포 가능)

`as_log`와 무관하게 단독 배포 가능한 판정·필터·배지·KPI 레이어.

---

## T1 — `as_billing` 저장 헬퍼 + `as/register` 확장

접수 시 무상/유상 추정값을 `sd['shipment']['as_billing']`에 저장한다. 기본 `free`/`confirmed=false`. as_orders.py:100 datetime 위반 동시 수정.

### Files
- Modify `foms/api/cs/as_orders.py`:100 (`datetime.datetime.now()` → `now_utc_naive()`)
- Modify `foms/api/cs/as_orders.py`:73-74 (헬퍼 삽입 지점, `_confirmed_construction_worker_name` 뒤)
- Modify `foms/api/cs/as_orders.py`:259-317 (`api_as_register` 본문)
- Create `tests/domains/test_as_billing.py`

### Interfaces
Produces:
```python
def _default_as_billing() -> dict[str, object]: ...
def _coerce_billing_type(raw: object) -> str: ...          # → 'free'|'paid'|'undecided' (그 외 'free')
def _coerce_billing_amount(raw: object) -> int | None: ...  # 정수/None, 음수·비정수 ValueError
def _write_as_billing(sd: dict, *, billing_type: str, amount: int | None,
                      confirmed: bool, reason: str, user) -> dict: ...
```
Consumes: `ensure_path`, `now_utc_naive`, `_load_order_structured_data_for_update`, `flag_modified`, `sync_erp_flat_columns`.

`POST /api/orders/<id>/as/register` body 확장: `billing_type`(optional, 기본 'free'), `amount`(optional, paid일 때만 의미).

### Steps
- [ ] `tests/domains/test_as_billing.py`에 실패 테스트 작성: register가 billing을 저장하는지.
  ```python
  from db import db_session
  from models import Order
  # _login_as_admin / _create_as_order 는 test_erp_as_dashboard_tabs 패턴 복제(또는 conftest 공용 import)

  def test_register_defaults_free_unconfirmed(client):
      _login_as_admin(client)
      order = _create_as_order(status="CS")
      res = client.post(f"/api/orders/{order.id}/as/register", json={"as_content": "문틀 뒤틀림"})
      assert res.status_code == 200 and res.get_json()["success"] is True
      db_session.expire_all()
      billing = db_session.get(Order, order.id).structured_data["shipment"]["as_billing"]
      assert billing["type"] == "free"
      assert billing["confirmed"] is False
      assert billing["amount"] is None

  def test_register_paid_estimate_with_amount(client):
      _login_as_admin(client)
      order = _create_as_order(status="CS")
      res = client.post(f"/api/orders/{order.id}/as/register",
                        json={"as_content": "부품 교체", "billing_type": "paid", "amount": 50000})
      assert res.get_json()["success"] is True
      db_session.expire_all()
      billing = db_session.get(Order, order.id).structured_data["shipment"]["as_billing"]
      assert billing["type"] == "paid" and billing["amount"] == 50000 and billing["confirmed"] is False
  ```
- [ ] 실패 확인: `python -m pytest tests/domains/test_as_billing.py -q` (KeyError 'as_billing').
- [ ] as_orders.py:100 수정: `"started_at": datetime.datetime.now().isoformat(),` → `"started_at": now_utc_naive().isoformat(),`.
- [ ] `_confirmed_construction_worker_name` 뒤(라인 74 근처)에 헬퍼 4종 추가:
  ```python
  _AS_BILLING_TYPES = ("free", "paid", "undecided")


  def _default_as_billing() -> dict[str, object]:
      """as_billing 기본값(무상 추정·미확정)."""
      return {
          "type": "free",
          "confirmed": False,
          "amount": None,
          "reason": "",
          "decided_by": "",
          "decided_at": "",
      }


  def _coerce_billing_type(raw: object) -> str:
      """billing 유형을 허용 enum으로 정규화. 미허용/빈값은 'free'."""
      value = str(raw or "").strip().lower()
      return value if value in _AS_BILLING_TYPES else "free"


  def _coerce_billing_amount(raw: object) -> int | None:
      """금액을 0 이상 정수 또는 None으로 정규화. 음수/비정수는 ValueError."""
      if raw in (None, ""):
          return None
      try:
          amount = int(raw)
      except (TypeError, ValueError) as exc:
          raise ValueError("금액은 정수여야 합니다.") from exc
      if amount < 0:
          raise ValueError("금액은 0 이상이어야 합니다.")
      return amount


  def _write_as_billing(sd: dict, *, billing_type: str, amount: int | None,
                        confirmed: bool, reason: str, user) -> dict:
      """sd['shipment']['as_billing']를 기존값 병합 후 갱신하고 반환."""
      shipment = ensure_path(sd, "shipment")
      billing = _default_as_billing()
      existing = shipment.get("as_billing")
      if isinstance(existing, dict):
          billing.update(existing)
      billing["type"] = billing_type
      billing["amount"] = amount
      billing["confirmed"] = bool(confirmed)
      if reason:
          billing["reason"] = reason
      billing["decided_by"] = (user.name if user else "") or ""
      billing["decided_at"] = now_utc_naive().isoformat()
      shipment["as_billing"] = billing
      return billing
  ```
- [ ] `api_as_register`에서 `shipment["as_content"] = as_content` 직후(라인 279 근처)에 billing 시드 추가. 확정 아님이므로 `_write_as_billing`(decided_* 채움) 대신 순수 시드:
  ```python
          billing_type = _coerce_billing_type(data.get("billing_type") or "free")
          billing_amount = _coerce_billing_amount(data.get("amount")) if billing_type == "paid" else None
          billing = _default_as_billing()
          billing["type"] = billing_type
          billing["amount"] = billing_amount
          shipment["as_billing"] = billing
  ```
- [ ] 통과 확인: `python -m pytest tests/domains/test_as_billing.py -q` green + `python -c "import app; print('APP_OK')"`.
- [ ] 커밋: `feat: AS 접수 시 무상/유상 추정(as_billing) 저장 + datetime.now 위반 수정`.

---

## T2 — `POST /as/billing` 확정/전환 API

방문 후 판정을 확정하거나 유형을 전환한다. 전환 시 `reason` 필수. `decided_by`/`decided_at` 기록. (system 로그 자동 append는 P3/T14.)

### Files
- Modify `foms/api/cs/as_orders.py` (`api_as_schedule` 뒤, `__all__` 앞에 신규 라우트)
- Modify `foms/api/cs/as_orders.py`:400-407 (`__all__`에 `api_as_billing` 추가)
- Modify `tests/domains/test_as_billing.py`

### Interfaces
Produces: `POST /api/orders/<int:order_id>/as/billing` — body `{type, amount?, reason?}` → `{'success': True, 'billing': {...}}`.
- 전환 규칙: 기존 `confirmed=True`이고 유형이 바뀌는데 `reason`이 없으면 400.
Consumes: `_load_order_structured_data_for_update`, `_write_as_billing`, `_coerce_billing_type`, `_coerce_billing_amount`.

### Steps
- [ ] 실패 테스트 추가:
  ```python
  def test_billing_confirm_paid(client):
      _login_as_admin(client)
      order = _create_as_order(status="AS_RECEIVED")
      res = client.post(f"/api/orders/{order.id}/as/billing",
                        json={"type": "paid", "amount": 30000})
      assert res.status_code == 200 and res.get_json()["success"] is True
      db_session.expire_all()
      b = db_session.get(Order, order.id).structured_data["shipment"]["as_billing"]
      assert b["type"] == "paid" and b["confirmed"] is True and b["amount"] == 30000
      assert b["decided_by"] and b["decided_at"]

  def test_billing_transition_requires_reason(client):
      _login_as_admin(client)
      order = _create_as_order(status="AS_RECEIVED",
                               shipment_extra={"as_billing": {"type": "free", "confirmed": True}})
      res = client.post(f"/api/orders/{order.id}/as/billing", json={"type": "paid"})
      assert res.status_code == 400
      assert res.get_json()["success"] is False
  ```
- [ ] 실패 확인(404: 라우트 없음).
- [ ] `api_as_schedule` 뒤에 라우트 추가:
  ```python
  @erp_orders_as_bp.route("/<int:order_id>/as/billing", methods=["POST"])
  @login_required
  @erp_edit_required
  def api_as_billing(order_id):
      """AS 무상/유상 판정 확정·전환. 전환 시 reason 필수."""
      db = get_db()
      try:
          order = db.get(Order, order_id)
          if not order or order.status == "DELETED" or order.deleted_at is not None:
              return jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404

          data = request.get_json(silent=True) or {}
          new_type = _coerce_billing_type(data.get("type"))
          reason = str(data.get("reason") or "").strip()
          amount = _coerce_billing_amount(data.get("amount")) if new_type == "paid" else None

          user = get_user_by_id(session.get("user_id"))
          sd = _load_order_structured_data_for_update(order)
          prev = (sd.get("shipment") or {}).get("as_billing") or {}
          prev_type = str(prev.get("type") or "free")
          if prev.get("confirmed") is True and prev_type != new_type and not reason:
              return jsonify({"success": False, "message": "판정 전환 시 사유는 필수입니다."}), 400

          billing = _write_as_billing(
              sd, billing_type=new_type, amount=amount,
              confirmed=True, reason=reason, user=user,
          )
          order.structured_data = sd
          flag_modified(order, "structured_data")
          sync_erp_flat_columns(order, sd)
          db.add(SecurityLog(
              user_id=session.get("user_id"),
              message=f"주문 #{order_id} AS 비용 판정: {new_type}"))
          db.commit()
          _invalidate_shipment_asrec_caches("api_as_billing")
          return jsonify({"success": True, "billing": billing})
      except ValueError as e:
          db.rollback()
          return jsonify({"success": False, "message": str(e)}), 409
      except Exception as e:
          db.rollback()
          return jsonify({"success": False, "message": str(e)}), 500
  ```
- [ ] `__all__`에 `"api_as_billing",` 추가.
- [ ] 통과 확인 + `APP_OK`.
- [ ] 커밋: `feat: AS 무상/유상 판정 확정·전환 API (POST /as/billing)`.

---

## T3 — 접수 모달 UI (세그먼트 3값 + 경과 개월 배지 + 금액 점진 공개)

`#asReceiveModal`에 무상/유상 세그먼트(기본 무상 추정) + 유상 시 금액 입력(점진 공개) + 시공 후 N개월 경과 배지 추가. 제출 payload에 `billing_type`/`amount` 확장.

### Files
- Modify `templates/orders/partials/erp_order_tab.html`:527 (AS 내용 textarea 뒤, 상차일 wrap 앞에 세그먼트+금액 삽입)
- Modify `static/js/orders/erp-order-shared.js`:2815-2821 (`regPayload` 구성부)
- Modify `static/js/orders/erp-order-shared.js`:2771-2784 (initAsReceiveModal 배선: 세그먼트 토글·금액 공개·경과 개월 배지)

### Interfaces
Consumes(모달 → register): `regPayload.billing_type`('free'|'paid'|'undecided'), `regPayload.amount`(int, paid일 때만).
- 경과 개월 배지: `#erp-*` 시공 관련 날짜 input에서 계산. 날짜 없으면 `hidden`.

### Steps
- [ ] erp_order_tab.html 라인 527(AS 내용 `.mb-3` 닫힘) 뒤에 세그먼트 블록 삽입. **인라인 스타일 금지** — 클래스만:
  ```html
                  <div class="mb-3">
                      <label class="form-label fw-bold">비용 구분</label>
                      <span id="as-receive-since-badge" class="badge bg-secondary ms-2 d-none"></span>
                      <div class="btn-group w-100 as-receive-billing-seg" role="group" aria-label="AS 비용 구분">
                          <input type="radio" class="btn-check" name="as-receive-billing" id="as-billing-free" value="free" checked>
                          <label class="btn btn-outline-success" for="as-billing-free">무상(추정)</label>
                          <input type="radio" class="btn-check" name="as-receive-billing" id="as-billing-paid" value="paid">
                          <label class="btn btn-outline-warning" for="as-billing-paid">유상</label>
                          <input type="radio" class="btn-check" name="as-receive-billing" id="as-billing-undecided" value="undecided">
                          <label class="btn btn-outline-secondary" for="as-billing-undecided">미정</label>
                      </div>
                      <div class="mt-2 d-none" id="as-receive-amount-wrap">
                          <label class="form-label" for="as-receive-amount">예상 금액(원)</label>
                          <input type="number" min="0" step="1000" id="as-receive-amount" class="form-control" placeholder="선택 입력">
                      </div>
                  </div>
  ```
- [ ] erp-order-shared.js `initAsReceiveModal` 상단(라인 2776 근처, DOM 참조 뒤)에 세그먼트/배지 배선 추가:
  ```javascript
          const amountWrap = document.getElementById('as-receive-amount-wrap');
          const sinceBadge = document.getElementById('as-receive-since-badge');
          const billingRadios = () => Array.from(document.querySelectorAll('input[name="as-receive-billing"]'));
          function selectedBillingType() {
              const checked = billingRadios().find((r) => r.checked);
              return checked ? checked.value : 'free';
          }
          function syncBillingUi() {
              if (amountWrap) amountWrap.classList.toggle('d-none', selectedBillingType() !== 'paid');
          }
          billingRadios().forEach((r) => r.addEventListener('change', syncBillingUi));
          function refreshSinceBadge() {
              if (!sinceBadge) return;
              // 시공 완료/전달일 등 시공 관련 날짜에서 경과 개월 계산. 없으면 hidden.
              const dateEl = document.getElementById('erp-construction-date')
                  || document.querySelector('[data-erp-construction-date]');
              const raw = (dateEl && dateEl.value || '').trim();
              const base = raw ? new Date(raw) : null;
              if (!base || Number.isNaN(base.getTime())) { sinceBadge.classList.add('d-none'); return; }
              const months = Math.max(0, Math.round((Date.now() - base.getTime()) / (1000 * 60 * 60 * 24 * 30)));
              sinceBadge.textContent = `시공 후 ${months}개월 경과`;
              sinceBadge.classList.remove('d-none');
          }
  ```
  > 착수 시 `erp-construction-date`의 실제 id를 grep으로 확정하라(시공 완료일 필드). 못 찾으면 배지는 `d-none` 유지(판정 강제 아님, 스펙 5.1). 모달 표시 이벤트(`shown.bs.modal`)에 `refreshSinceBadge` 바인딩:
  ```javascript
          if (modalEl) {
              modalEl.addEventListener('shown.bs.modal', function () { syncBillingUi(); refreshSinceBadge(); });
          }
  ```
- [ ] `regPayload` 확장(라인 2815 근처):
  ```javascript
                  const regPayload = { as_content: content };
                  const billingType = selectedBillingType();
                  regPayload.billing_type = billingType;
                  if (billingType === 'paid') {
                      const amt = parseInt(document.getElementById('as-receive-amount')?.value || '', 10);
                      if (!Number.isNaN(amt) && amt >= 0) regPayload.amount = amt;
                  }
  ```
- [ ] 검증: gstack browse로 모달 열기 → 유상 선택 시 금액 노출 → 접수 후 as_billing 저장 확인(또는 T1/T2 pytest로 payload 계약 커버되므로 수동 스모크). `APP_OK` 불필요(순수 프론트).
- [ ] 커밋: `feat: AS 접수 모달 무상/유상 세그먼트 + 금액 점진 공개 + 경과 개월 배지`.

---

## T4 — 대시보드 billing 필터 + 배지 + KPI 5-pill

데스크톱 form + 모바일 offcanvas에 billing select 추가, read model에 billing 카운트 반영, 상태 셀 billing 배지(무상 확정 무배지), KPI 4→5 pill("유상 미확정").

### Files
- Modify `foms/services/as_dashboard_filters.py`:21-56 (`billing` 필드 추가)
- Modify `foms/services/as_dashboard_helpers.py`:143 근처 (`_as_billing_type_expr`/`_as_billing_confirmed_expr` 추가)
- Modify `foms/services/as_dashboard_read_model.py`:23-94 (paid_unconfirmed 버킷·카운트)
- Modify `foms/web/cs/as_dashboard.py`:139-266 (billing 필터 적용 + 컨텍스트 전달)
- Modify `foms/services/as_dashboard_display.py`:276-306 (`r.as_billing_badge` 세팅)
- Modify `templates/cs/partials/as_dashboard_body.html`:88-95(필터 select), 119-135(KPI pill), 237-242(상태 셀 배지)
- Modify `static/css/contexts/cs/as-dashboard-body.css`:218-223 (`repeat(4)`→`repeat(5)`) + billing 배지 클래스
- Modify `tests/domains/test_as_billing.py` (필터/배지 렌더 테스트)

### Interfaces
Produces:
```python
def _as_billing_type_expr(*, dialect_name='') -> ...        # lower(coalesce(shipment.as_billing.type,'free'))
def _as_billing_confirmed_expr(*, dialect_name='') -> ...   # lower(coalesce(shipment.as_billing.confirmed,'false'))
```
`AsDashboardFilters.billing: str` ∈ `{'', 'free','paid','undecided'}`.
`r.as_billing_badge: str | None` ∈ `{None,'paid','paid_unconfirmed','undecided'}`.
새 버킷 키: `paid_unconfirmed`(KPI pill, `?bucket=paid_unconfirmed`).

### Steps
- [ ] 실패 테스트 추가(필터 좁힘 + 배지 렌더):
  ```python
  def test_billing_filter_paid_only(client):
      _login_as_admin(client)
      _create_as_order(customer_name="유상건", shipment_extra={"as_billing": {"type": "paid", "confirmed": True}})
      _create_as_order(customer_name="무상건", shipment_extra={"as_billing": {"type": "free", "confirmed": True}})
      body = client.get("/erp/as?tab=incomplete&billing=paid").get_data(as_text=True)
      assert "유상건" in body and "무상건" not in body

  def test_billing_badge_free_confirmed_hidden(client):
      _login_as_admin(client)
      _create_as_order(customer_name="무상확정", shipment_extra={"as_billing": {"type": "free", "confirmed": True}})
      body = client.get("/erp/as?tab=incomplete").get_data(as_text=True)
      assert "erp-as-billing-badge" not in body  # 무상 확정 무배지
  ```
- [ ] 실패 확인.
- [ ] `as_dashboard_filters.py`: dataclass에 `billing: str` 추가 + 파서에서 화이트리스트 파싱:
  ```python
      billing: str
  # ...
      billing = (request.args.get('billing') or '').strip().lower()
      if billing not in ('free', 'paid', 'undecided'):
          billing = ''
  # return 에 billing=billing 추가
  ```
- [ ] `as_dashboard_helpers.py` `_as_visit_date_expr` 뒤에 billing exprs 추가:
  ```python
  def _as_billing_type_expr(*, dialect_name=''):
      """structured_data.shipment.as_billing.type 추출(기본 'free', 소문자)."""
      return func.lower(func.coalesce(
          cast(_json_text_expr('shipment', 'as_billing', 'type', dialect_name=dialect_name), String),
          'free',
      ))


  def _as_billing_confirmed_expr(*, dialect_name=''):
      """structured_data.shipment.as_billing.confirmed 추출(기본 'false', 소문자)."""
      return func.lower(func.coalesce(
          cast(_json_text_expr('shipment', 'as_billing', 'confirmed', dialect_name=dialect_name), String),
          'false',
      ))
  ```
- [ ] `as_dashboard_read_model.py` `build_as_tab_query_conditions`에 paid_unconfirmed 조건 추가:
  ```python
  from foms.services.as_dashboard_helpers import (
      # ...기존...
      _as_billing_type_expr,
      _as_billing_confirmed_expr,
  )
  # build_as_tab_query_conditions 내부:
      billing_type = _as_billing_type_expr(dialect_name=dialect_name)
      billing_confirmed = _as_billing_confirmed_expr(dialect_name=dialect_name)
      paid_unconfirmed_condition = and_(billing_type == 'paid', billing_confirmed != 'true')
      billing_filters = {
          'free': billing_type == 'free',
          'paid': billing_type == 'paid',
          'undecided': billing_type == 'undecided',
      }
  # return dict 에 두 키 추가:
      "paid_unconfirmed_condition": paid_unconfirmed_condition,
      "billing_filters": billing_filters,
  ```
  `build_as_tab_count_context`의 `incomplete_buckets`에 5번째 버킷 + summary 카운트 추가:
  ```python
  # 시그니처에 paid_unconfirmed_condition 파라미터 추가
      incomplete_buckets = {
          'visit_confirmed': and_(incomplete_non_sales_condition, ~as_pending_true, as_visit_date_present),
          'pending': and_(incomplete_non_sales_condition, as_pending_true),
          'unassigned': and_(incomplete_non_sales_condition, ~as_pending_true, ~as_visit_date_present),
          'paid_unconfirmed': and_(incomplete_non_sales_condition, paid_unconfirmed_condition),
      }
  # as_incomplete_summary 계산에 추가:
          ('paid_unconfirmed', incomplete_buckets['paid_unconfirmed']),
  ```
- [ ] `as_dashboard.py` 라우트: `_af.billing` 수신 + 필터 적용 + count context에 조건 전달.
  ```python
      billing_filter = _af.billing
      # as_tab_conditions 언팩에 추가:
      paid_unconfirmed_condition = as_tab_conditions["paid_unconfirmed_condition"]
      billing_filters = as_tab_conditions["billing_filters"]
      # build_as_tab_count_context(..., paid_unconfirmed_condition=paid_unconfirmed_condition)
      # billing 필터(탭 무관, 정렬 전 라인 267 근처):
      if billing_filter in billing_filters:
          query = query.filter(billing_filters[billing_filter])
  ```
  > `paid_unconfirmed` KPI pill은 `bucket=paid_unconfirmed`로 링크되며, 기존 라우트의 버킷 필터 블록(`if as_bucket: query = query.filter(incomplete_buckets[as_bucket])`, 라인 264-266)이 그대로 적용한다(버킷 dict에 키를 추가했으므로 별도 필터 불필요). read_model 게이트 `if tab != 'incomplete' or as_bucket not in incomplete_buckets`도 자동 커버. 렌더 컨텍스트에 `billing_filter=billing_filter` 전달.
- [ ] `as_dashboard_display.py` row 루프(라인 281 근처)에 배지 세팅 + 모듈 함수 추가:
  ```python
  def _as_billing_badge(billing) -> str | None:
      """상태 셀 billing 배지 종류. 무상(확정 여부 무관)은 None(무배지)."""
      b = billing if isinstance(billing, dict) else {}
      btype = str(b.get('type') or 'free').lower()
      if btype == 'paid':
          return 'paid' if b.get('confirmed') is True else 'paid_unconfirmed'
      if btype == 'undecided':
          return 'undecided'
      return None
  # 루프 안:
          r.as_billing_badge = _as_billing_badge(shipment.get('as_billing'))
  ```
- [ ] 템플릿: 필터 select 추가(라인 95 뒤, 검색 그룹 앞):
  ```html
          <div class="erp-pro-filter-group">
            <label class="erp-pro-filter-label">비용</label>
            <select class="erp-pro-select" name="billing">
              <option value="">전체</option>
              <option value="free" {% if billing_filter=='free' %}selected{% endif %}>무상</option>
              <option value="paid" {% if billing_filter=='paid' %}selected{% endif %}>유상</option>
              <option value="undecided" {% if billing_filter=='undecided' %}selected{% endif %}>미정</option>
            </select>
          </div>
  ```
  KPI pill 배열(라인 119-124)에 5번째 추가:
  ```html
            {'key': 'unassigned', 'label': '아직 미정'},
            {'key': 'paid_unconfirmed', 'label': '유상 미확정'}
  ```
  상태 셀(라인 237-242) 배지 아래 줄 추가:
  ```html
                <td class="erp-as-status-cell" data-order-id="{{ r.id }}">
                  <span class="erp-pro-badge {% if r.as_pending %}erp-pro-badge--pending{% elif r.status == 'AS_COMPLETED' %}erp-pro-badge--success{% else %}erp-pro-badge--info{% endif %}">
                    {% if r.as_pending %}미결{% else %}{{ STATUS.get(r.status, r.status) }}{% endif %}
                  </span>
                  {% if r.as_billing_badge %}
                  <span class="erp-as-billing-badge erp-as-billing-badge--{{ r.as_billing_badge }}">
                    {% if r.as_billing_badge == 'paid' %}유상{% elif r.as_billing_badge == 'paid_unconfirmed' %}유상?{% else %}미정{% endif %}
                  </span>
                  {% endif %}
                </td>
  ```
- [ ] CSS: `repeat(4, ...)` → `repeat(5, ...)`(라인 220) + billing 배지 클래스 추가(모달 세그먼트와 동일 계열):
  ```css
    .erp-as-summary-strip { grid-template-columns: repeat(5, minmax(0, 1fr)); }
    .erp-as-billing-badge {
      display: inline-block; margin-top: 2px;
      padding: 0 5px; border-radius: 4px;
      font-size: 0.68rem; font-weight: 700; line-height: 1.5;
    }
    .erp-as-billing-badge--paid { background: #f59f00; color: #fff; }
    .erp-as-billing-badge--undecided { background: #e9ecef; color: #495057; }
    .erp-as-billing-badge--paid_unconfirmed { background: #fff; color: #d9480f; border: 1px dashed #f59f00; }
  ```
  모바일 offcanvas billing select는 `as_mobile_controls.html`에 동일 select 추가(착수 시 파일 확인; 데스크톱 form과 name/option 동일).
  > CSS 변경이므로 `as_dashboard_body.html`의 `?v=20260712a`(라인 4)를 새 스탬프로 범프.
- [ ] 통과 확인: `python -m pytest tests/domains/test_as_billing.py -q` green + `APP_OK`.
- [ ] 커밋: `feat: AS 대시보드 billing 필터·배지·KPI 유상미확정 pill`.

---

## T5 — P1 검증 게이트

### Files
- (없음 — 검증만)

### Steps
- [ ] 기존 AS 테스트 10파일 green:
  ```
  python -m pytest tests/domains/test_as_content_safety.py tests/domains/test_as_dashboard_attachment_modal.py \
    tests/domains/test_as_dashboard_filters.py tests/domains/test_as_dashboard_mobile.py \
    tests/domains/test_as_toolbar_hydrate.py tests/domains/test_as_card_lazy.py \
    tests/domains/test_as_received_date_kst.py tests/domains/test_erp_as_dashboard_tabs.py \
    tests/domains/test_as_billing.py -q
  ```
- [ ] `python -c "import app; print('APP_OK')"`.
- [ ] `EXPLAIN` — billing 필터 Seq Scan 없음 확인(운영 DB 대상, 등호 비교이므로 인덱스 부담 낮음. 필요 시 `->>` 표현식 인덱스 제안만 기록, 신규 인덱스는 별도 마이그레이션으로):
  ```sql
  EXPLAIN SELECT 1 FROM orders
   WHERE lower(coalesce(structured_data->'shipment'->'as_billing'->>'type','free')) = 'paid'
     AND status IN ('AS','AS_RECEIVED','AS_COMPLETED');
  ```
- [ ] push 전 `powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` exit 0.
- [ ] 커밋(필요 시 문서/AI_STATUS 갱신): `chore: P1 검증 게이트 통과 기록`.

---

# Phase P2 — 타임라인 코어

---

## T6 — `as_log` 도메인 서비스

append/lazy 마이그레이션/렌더 뷰 정규화 헬퍼. 신규 파일(as_orders.py 비대 방지).

### Files
- Create `foms/services/orders/as_log.py`
- Create `tests/domains/test_as_log_service.py`

### Interfaces
Produces:
```python
AS_LOG_TYPES: frozenset[str]                       # 7종 고정 enum
def new_as_log_id() -> str                          # 'al_<epoch_ms>_<rand4>'
def coerce_client_log_type(raw: object) -> str      # system이면 ValueError, 미허용→'memo'
def build_as_log_entry(*, log_type, text, by, by_id) -> dict
def migrate_legacy_into_log(sd: dict) -> bool        # as_log 없고 as_content 있으면 legacy 시드
def append_client_log(sd, *, log_type, text, by, by_id) -> dict
def append_system_log(sd, *, text) -> dict
def build_as_timeline_view(sd: dict, *, recent_limit: int = 8) -> dict
def decorate_entry(entry: dict) -> dict                  # 렌더 파생 필드(API 단건 렌더도 재사용)
def format_relative_kst(ts: str | None) -> str
```
Consumes: `now_utc_naive`, `sanitize_as_content_html`, `format_datetime_kst`.

### Steps
- [ ] 실패 테스트 작성:
  ```python
  from foms.services.orders.as_log import (
      coerce_client_log_type, build_as_log_entry, migrate_legacy_into_log,
      append_client_log, build_as_timeline_view,
  )
  import pytest

  def test_client_type_rejects_system():
      with pytest.raises(ValueError):
          coerce_client_log_type("system")

  def test_client_type_defaults_memo():
      assert coerce_client_log_type("bogus") == "memo"
      assert coerce_client_log_type("call") == "call"

  def test_migrate_legacy_seeds_from_as_content():
      sd = {"shipment": {"as_content": "<div>옛 기록</div>", "as_content_2": "<div>탭2</div>"}}
      assert migrate_legacy_into_log(sd) is True
      log = sd["shipment"]["as_log"]
      assert len(log) == 2 and all(e["legacy"] is True for e in log)
      # 재호출은 no-op
      assert migrate_legacy_into_log(sd) is False

  def test_append_creates_reception_anchor_and_stream():
      sd = {"shipment": {}}
      append_client_log(sd, log_type="reception", text="접수", by="김", by_id=1)
      append_client_log(sd, log_type="call", text="통화함", by="김", by_id=1)
      view = build_as_timeline_view(sd)
      assert view["reception"]["text"] == "접수"
      assert view["stream"][0]["text"] == "통화함"  # 역시간순
      assert view["stream_total"] == 1
  ```
- [ ] 실패 확인(모듈 없음).
- [ ] `foms/services/orders/as_log.py` 작성:
  ```python
  """AS 타임라인 로그(as_log) 도메인 서비스.

  sd['shipment']['as_log'] append-only 리스트의 생성·정규화·lazy 마이그레이션과
  렌더용 뷰(앵커+스트림) 구성을 담당한다. API 라우트가 비대해지지 않도록 분리.
  """
  from __future__ import annotations

  import secrets
  import time
  from typing import Any

  from foms.services.as_content_safety import sanitize_as_content_html
  from foms.services.datetime_kst import format_datetime_kst, now_utc_naive, parse_datetime_utc

  AS_LOG_TYPES = frozenset({
      "reception", "call", "action", "material", "schedule", "memo", "system",
  })
  _CLIENT_TYPES = AS_LOG_TYPES - {"system"}
  _DEFAULT_TYPE = "memo"
  _TYPE_LABELS = {
      "reception": "접수", "call": "통화", "action": "방문/조치",
      "material": "자재", "schedule": "일정", "memo": "메모", "system": "시스템",
  }


  def new_as_log_id() -> str:
      """`al_<epoch_ms>_<rand4>` 형식의 항목 id."""
      return f"al_{int(time.time() * 1000)}_{secrets.token_hex(2)}"


  def coerce_client_log_type(raw: Any) -> str:
      """클라이언트 유형을 허용 enum으로 정규화. 'system'은 거부(ValueError), 미허용은 memo."""
      value = str(raw or "").strip().lower()
      if value == "system":
          raise ValueError("system 유형은 서버만 생성할 수 있습니다.")
      return value if value in _CLIENT_TYPES else _DEFAULT_TYPE


  def build_as_log_entry(*, log_type: str, text: str, by: str, by_id: int | None) -> dict[str, Any]:
      """as_log 항목 dict 생성. ts는 UTC naive ISO."""
      return {
          "id": new_as_log_id(),
          "ts": now_utc_naive().isoformat(),
          "by": by or "",
          "by_id": by_id,
          "type": log_type,
          "text": text,
          "edited_at": None,
          "edited_by": None,
      }


  def _legacy_entries_from_content(shipment: dict) -> list[dict]:
      """as_content/as_content_2를 읽기전용 legacy memo 항목으로 변환."""
      out: list[dict] = []
      for field, label in (("as_content", "이전 기록"), ("as_content_2", "이전 기록(탭2)")):
          html = sanitize_as_content_html(shipment.get(field))
          if not html:
              continue
          out.append({
              "id": new_as_log_id(),
              "ts": None,
              "by": "",
              "by_id": None,
              "type": "memo",
              "text": html,
              "legacy": True,
              "legacy_label": label,
              "edited_at": None,
              "edited_by": None,
          })
      return out


  def migrate_legacy_into_log(sd: dict) -> bool:
      """as_log가 비어있고 as_content가 있으면 legacy 항목으로 시드. 시드했으면 True."""
      shipment = sd.setdefault("shipment", {})
      existing = shipment.get("as_log")
      if isinstance(existing, list) and existing:
          return False
      seeded = _legacy_entries_from_content(shipment)
      shipment["as_log"] = seeded
      return bool(seeded)


  def append_client_log(sd: dict, *, log_type: str, text: str, by: str, by_id: int | None) -> dict:
      """수기 항목 append(최초 append 시 legacy 영구화). 반환=append된 항목."""
      migrate_legacy_into_log(sd)
      entry = build_as_log_entry(log_type=log_type, text=text, by=by, by_id=by_id)
      sd["shipment"]["as_log"].append(entry)
      return entry


  def append_system_log(sd: dict, *, text: str) -> dict:
      """시스템 이벤트 항목 append(서버 전용)."""
      migrate_legacy_into_log(sd)
      entry = build_as_log_entry(log_type="system", text=text, by="시스템", by_id=None)
      sd["shipment"]["as_log"].append(entry)
      return entry


  def format_relative_kst(ts: str | None) -> str:
      """UTC naive ISO → 상대 표기('N분 전'/'어제' 등). 없으면 빈 문자열."""
      dt = parse_datetime_utc(ts) if ts else None
      if dt is None:
          return ""
      now = parse_datetime_utc(now_utc_naive().isoformat())
      delta = (now - dt).total_seconds()
      if delta < 60:
          return "방금"
      if delta < 3600:
          return f"{int(delta // 60)}분 전"
      if delta < 86400:
          return f"{int(delta // 3600)}시간 전"
      if delta < 172800:
          return "어제"
      return f"{int(delta // 86400)}일 전"


  def decorate_entry(entry: dict) -> dict:
      """렌더용 파생 필드 추가(원본 불변, 얕은 복사). API 단건 렌더도 재사용(public)."""
      out = dict(entry)
      ts = entry.get("ts")
      out["ts_abs"] = format_datetime_kst(ts, "%Y-%m-%d %H:%M") if ts else ""
      out["ts_rel"] = format_relative_kst(ts)
      out["type_label"] = _TYPE_LABELS.get(entry.get("type"), "메모")
      out["is_system"] = entry.get("type") == "system"
      out["is_legacy"] = entry.get("legacy") is True
      out["is_edited"] = bool(entry.get("edited_at"))
      return out


  def build_as_timeline_view(sd: dict | None, *, recent_limit: int = 8) -> dict[str, Any]:
      """앵커(접수/legacy) + 역시간순 스트림 뷰. lazy 마이그레이션은 표시 시점 비파괴."""
      shipment = (sd or {}).get("shipment") or {}
      entries = shipment.get("as_log")
      reception: dict | None = None
      legacy: list[dict] = []
      stream: list[dict] = []
      if isinstance(entries, list) and entries:
          for e in entries:
              if not isinstance(e, dict):
                  continue
              if e.get("legacy") is True:
                  legacy.append(decorate_entry(e))
              elif e.get("type") == "reception" and reception is None:
                  reception = decorate_entry(e)
              elif e.get("type") == "reception":
                  stream.append(decorate_entry(e))  # 두 번째 접수 이후는 스트림
              else:
                  stream.append(decorate_entry(e))
      else:
          legacy = [decorate_entry(x) for x in _legacy_entries_from_content(shipment)]
      stream.sort(key=lambda x: x.get("ts") or "", reverse=True)
      total = len(stream)
      return {
          "reception": reception,
          "legacy": legacy,
          "stream": stream[:recent_limit],
          "stream_total": total,
          "has_more": total > recent_limit,
          "count": total + (1 if reception else 0) + len(legacy),
      }
  ```
- [ ] 통과 확인 + `APP_OK`.
- [ ] 커밋: `feat: AS 타임라인 로그 도메인 서비스(as_log) 신설`.

---

## T7 — `POST /as/log` + `PATCH /as/log/<log_id>`

항목 append + 본문 수정(작성자 본인/관리자). sanitize 적용. 응답에 렌더된 항목 HTML 포함.

### Files
- Modify `foms/api/cs/as_orders.py` (라우트 2종 + `__all__`)
- Create `templates/cs/partials/as_timeline_entry_partial.html`(단건 렌더 — 매크로 위임)
- Modify `tests/domains/test_as_log_service.py` 또는 Create `tests/domains/test_as_log_api.py`

### Interfaces
Produces:
- `POST /api/orders/<id>/as/log` body `{type, text}` → `{'success': True, 'entry': {...}, 'html': '<...>'}`.
- `PATCH /api/orders/<id>/as/log/<log_id>` body `{text}` → `{'success': True, 'entry': {...}, 'html': '<...>'}`. 작성자(`by_id==user.id`) 또는 관리자만, 아니면 403.
Consumes: `append_client_log`, `coerce_client_log_type`, `sanitize_as_content_html`, `render_template`(단건 매크로), `can_edit_erp`.

### Steps
- [ ] 실패 테스트(append·수정 권한·system 거부):
  ```python
  def test_log_append_returns_entry(client):
      _login_as_admin(client)
      order = _create_as_order()
      res = client.post(f"/api/orders/{order.id}/as/log", json={"type": "call", "text": "고객 통화"})
      data = res.get_json()
      assert res.status_code == 200 and data["success"] is True
      assert data["entry"]["type"] == "call" and "고객 통화" in data["entry"]["text"]

  def test_log_append_rejects_system_type(client):
      _login_as_admin(client)
      order = _create_as_order()
      res = client.post(f"/api/orders/{order.id}/as/log", json={"type": "system", "text": "x"})
      assert res.status_code == 400 and res.get_json()["success"] is False

  def test_log_patch_by_non_author_forbidden(client):
      # 작성자 아닌 비관리자 계정으로 PATCH → 403 (관리자/작성자만 허용)
      ...
  ```
- [ ] 실패 확인.
- [ ] `as_timeline_entry_partial.html` 작성(단건):
  ```html
  {% from 'cs/partials/as_card_macros.html' import render_as_timeline_entry %}
  {{ render_as_timeline_entry(entry) }}
  ```
- [ ] as_orders.py에 import 보강 + 라우트 2종 추가:
  ```python
  from flask import render_template
  from foms.services.orders.as_log import (
      append_client_log, coerce_client_log_type, decorate_entry,
  )


  @erp_orders_as_bp.route("/<int:order_id>/as/log", methods=["POST"])
  @login_required
  @erp_edit_required
  def api_as_log_append(order_id):
      """AS 타임라인 항목 append. body {type, text}."""
      db = get_db()
      try:
          order = db.get(Order, order_id)
          if not order or order.status == "DELETED" or order.deleted_at is not None:
              return jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404
          data = request.get_json(silent=True) or {}
          try:
              log_type = coerce_client_log_type(data.get("type"))
          except ValueError as ve:
              return jsonify({"success": False, "message": str(ve)}), 400
          text = sanitize_as_content_html(data.get("text"))
          if not text:
              return jsonify({"success": False, "message": "내용을 입력해주세요."}), 400
          user = get_user_by_id(session.get("user_id"))
          sd = _load_order_structured_data_for_update(order)
          entry = append_client_log(
              sd, log_type=log_type, text=text,
              by=(user.name if user else ""), by_id=(user.id if user else None))
          order.structured_data = sd
          flag_modified(order, "structured_data")
          sync_erp_flat_columns(order, sd)
          db.add(SecurityLog(user_id=session.get("user_id"), message=f"주문 #{order_id} AS 기록 추가"))
          db.commit()
          _invalidate_shipment_asrec_caches("api_as_log_append")
          html = render_template("cs/partials/as_timeline_entry_partial.html", entry=decorate_entry(entry))
          return jsonify({"success": True, "entry": entry, "html": html})
      except ValueError as e:
          db.rollback()
          return jsonify({"success": False, "message": str(e)}), 409
      except Exception as e:
          db.rollback()
          return jsonify({"success": False, "message": str(e)}), 500


  @erp_orders_as_bp.route("/<int:order_id>/as/log/<log_id>", methods=["PATCH"])
  @login_required
  @erp_edit_required
  def api_as_log_patch(order_id, log_id):
      """AS 타임라인 항목 본문 수정. 작성자 본인 또는 관리자만."""
      db = get_db()
      try:
          order = db.get(Order, order_id)
          if not order or order.status == "DELETED" or order.deleted_at is not None:
              return jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404
          text = sanitize_as_content_html((request.get_json(silent=True) or {}).get("text"))
          if not text:
              return jsonify({"success": False, "message": "내용을 입력해주세요."}), 400
          user = get_user_by_id(session.get("user_id"))
          is_admin = bool(user and (user.role or "").upper() == "ADMIN")
          sd = _load_order_structured_data_for_update(order)
          log = (sd.get("shipment") or {}).get("as_log") or []
          target = next((e for e in log if isinstance(e, dict) and e.get("id") == log_id), None)
          if target is None:
              return jsonify({"success": False, "message": "항목을 찾을 수 없습니다."}), 404
          if target.get("type") == "system" or target.get("legacy") is True:
              return jsonify({"success": False, "message": "수정할 수 없는 항목입니다."}), 400
          if not is_admin and target.get("by_id") != (user.id if user else None):
              return jsonify({"success": False, "message": "본인 또는 관리자만 수정할 수 있습니다."}), 403
          target["text"] = text
          target["edited_at"] = now_utc_naive().isoformat()
          target["edited_by"] = user.name if user else ""
          order.structured_data = sd
          flag_modified(order, "structured_data")
          db.add(SecurityLog(user_id=session.get("user_id"), message=f"주문 #{order_id} AS 기록 수정({log_id})"))
          db.commit()
          _invalidate_shipment_asrec_caches("api_as_log_patch")
          html = render_template("cs/partials/as_timeline_entry_partial.html", entry=decorate_entry(target))
          return jsonify({"success": True, "entry": target, "html": html})
      except ValueError as e:
          db.rollback()
          return jsonify({"success": False, "message": str(e)}), 409
      except Exception as e:
          db.rollback()
          return jsonify({"success": False, "message": str(e)}), 500
  ```
  > `render_as_timeline_entry` 매크로는 T9에서 정의된다 — T7과 T9는 매크로 시그니처를 공유하므로 순서상 T9의 단건 매크로를 먼저 스텁으로 추가하거나, T7·T9를 같은 브랜치에서 진행하라. `decorate_entry`는 T6의 public 헬퍼로 API 단건 렌더에 재사용한다.
- [ ] `__all__`에 `"api_as_log_append", "api_as_log_patch"` 추가.
- [ ] 통과 확인 + `APP_OK`.
- [ ] 커밋: `feat: AS 타임라인 항목 append/patch API`.

---

## T8 — `GET /erp/as/timeline/<id>` fragment + register 첫 reception 항목

PC 확장 행용 타임라인 fragment(모바일 card-detail lazy 패턴 복제). register가 접수 원문을 첫 `reception` 항목으로 저장.

### Files
- Modify `foms/web/cs/as_dashboard.py`:98-131 뒤(신규 라우트) + import
- Create `templates/cs/partials/as_timeline_partial.html`
- Modify `foms/api/cs/as_orders.py`:279 근처(register가 reception 항목 append)
- Modify `foms/services/as_dashboard_display.py`:276-306(`r.as_timeline_view` 세팅)
- Modify `tests/domains/test_as_card_lazy.py` 또는 Create `tests/domains/test_as_timeline_fragment.py`

### Interfaces
Produces:
- `GET /erp/as/timeline/<int:order_id>` → `as_timeline_partial.html`(text/html), AS 상태 아니면 404.
- register: 접수 시 `append_client_log(sd, log_type="reception", text=as_content, ...)`.
- `r.as_timeline_view: dict`(T6 `build_as_timeline_view` 결과) — 셀 요약·fragment 공용.
Consumes: `apply_as_dashboard_row_display_fields`, `can_edit_erp`, `build_as_timeline_view`.

### Steps
- [ ] 실패 테스트(fragment 렌더 + register reception):
  ```python
  def test_timeline_fragment_renders(client):
      _login_as_admin(client)
      order = _create_as_order(shipment_extra={"as_log": [
          {"id": "al_1", "ts": "2026-07-24T01:00:00", "type": "reception", "text": "문 처짐", "by": "김"}]})
      res = client.get(f"/erp/as/timeline/{order.id}")
      assert res.status_code == 200 and "문 처짐" in res.get_data(as_text=True)

  def test_register_creates_reception_log(client):
      _login_as_admin(client)
      order = _create_as_order(status="CS")
      client.post(f"/api/orders/{order.id}/as/register", json={"as_content": "경첩 불량"})
      db_session.expire_all()
      log = db_session.get(Order, order.id).structured_data["shipment"]["as_log"]
      assert any(e.get("type") == "reception" and "경첩 불량" in e.get("text", "") for e in log)
  ```
- [ ] 실패 확인.
- [ ] as_dashboard.py에 라우트 추가(card-detail 복제):
  ```python
  from foms.services.orders.as_log import build_as_timeline_view  # (display에서 이미 쓰면 생략 가능)

  @erp_as_page_bp.route('/as/timeline/<int:order_id>')
  @login_required
  def erp_as_timeline(order_id: int):
      """AS PC 확장 행용 타임라인 fragment lazy 렌더(모바일 card-detail 패턴 복제)."""
      db = get_db()
      order = (
          db.query(Order)
          .filter(Order.active_filter())
          .filter(Order.status.in_(['AS', 'AS_RECEIVED', 'AS_COMPLETED']))
          .filter(Order.id == order_id)
          .first()
      )
      if order is None:
          abort(404)
      apply_as_dashboard_row_display_fields([order], db, mobile_v2_active=False)
      # 더보기(full=1)면 스트림 전량으로 뷰 재구성(display 기본 recent_limit=8을 덮어씀).
      if request.args.get('full'):
          order.as_timeline_view = build_as_timeline_view(order.structured_data, recent_limit=9999)
      current_user = getattr(g, 'current_user', None)
      return render_template(
          'cs/partials/as_timeline_partial.html',
          r=order,
          can_edit_erp=can_edit_erp(current_user),
      )
  ```
  > `request`는 as_dashboard.py가 이미 import함(라인 3). `build_as_timeline_view`는 상단에서 import(위 코드 블록 참조).
- [ ] `as_timeline_partial.html` 작성(매크로 위임 — T9 매크로 사용):
  ```html
  {# AS 타임라인 단건 파셜 — PC 확장 행 lazy fetch가 이 파셜만 렌더. #}
  {% from 'cs/partials/as_card_macros.html' import render_as_timeline %}
  {{ render_as_timeline(r.id, r.as_timeline_view, can_edit_erp|default(false)) }}
  ```
- [ ] display 모듈 row 루프(라인 286 근처)에 뷰 세팅:
  ```python
  from foms.services.orders.as_log import build_as_timeline_view
  # 루프 안(as_content_html 유지 — legacy 폴백 렌더용):
          r.as_timeline_view = build_as_timeline_view(r.structured_data)
  ```
- [ ] register가 reception 항목 append(라인 279, `shipment["as_content"] = as_content` 유지하되 로그도 기록):
  ```python
          from foms.services.orders.as_log import append_client_log
          if as_content:
              append_client_log(
                  sd, log_type="reception", text=as_content,
                  by=(user.name if user else ""), by_id=(user.id if user else None))
  ```
  > `shipment["as_content"]` 쓰기는 P2 완료 시점(T12)까지 병행 유지(legacy 폴백/롤백 안전). reception 로그와 중복은 렌더 뷰에서 앵커=reception 우선이므로 문제 없음.
- [ ] 통과 확인 + `APP_OK`.
- [ ] 커밋: `feat: AS 타임라인 fragment 라우트 + 접수 첫 reception 항목`.

---

## T9 — `render_as_timeline` 매크로 + 3표면 교체

앵커 고정 + 역시간순 스트림 + quick-add + 최근 8개 더보기 매크로. 접힘 셀 요약. 3표면(PC 셀·모바일 카드 상세·무한스크롤) 교체.

### Files
- Modify `templates/cs/partials/as_card_macros.html`(매크로 3종 신설: `render_as_timeline`, `render_as_timeline_entry`, `render_as_timeline_cell`)
- Modify `templates/cs/partials/as_dashboard_body.html`:234-236(내용 셀 → 셀 요약 + 확장 트리거)
- Modify `templates/cs/partials/as_card_detail_partial.html`:12-17(content_tabs → timeline)
- Modify `templates/cs/partials/as_mobile_order_card.html`:230(legacy 카드 content_tabs → timeline; v2는 lazy 유지)

### Interfaces
Produces:
```
render_as_timeline(order_id, view, can_edit)        # 앵커+스트림+quick-add
render_as_timeline_entry(entry)                     # 단건(스트림/optimistic/patch 공용)
render_as_timeline_cell(order_id, view)             # PC 셀 요약(1줄 clamp + 배지)
```
Consumes: `view = r.as_timeline_view`(T6). 유형 칩 색은 CSS 클래스 `as-tl-chip--<type>`(T11).

### Steps
- [ ] `render_as_timeline_entry` 매크로(단건 — 스트림 항목·optimistic·PATCH 응답 공용):
  ```html
  {% macro render_as_timeline_entry(e) -%}
  <div class="as-tl-item{% if e.is_system %} as-tl-item--system{% endif %}{% if e.is_legacy %} as-tl-item--legacy{% endif %}"
       data-log-id="{{ e.id }}" data-log-type="{{ e.type }}">
    <div class="as-tl-item__meta">
      {% if e.is_system %}
      <i class="fas fa-gear as-tl-item__sysicon" aria-hidden="true"></i>
      {% else %}
      <span class="as-tl-chip as-tl-chip--{{ e.type }}">{{ e.type_label }}</span>
      {% endif %}
      {% if e.by %}<span class="as-tl-item__by">{{ e.by }}</span>{% endif %}
      {% if e.ts_abs %}<time class="as-tl-item__time" datetime="{{ e.ts }}" title="{{ e.ts_abs }} KST">{{ e.ts_rel or e.ts_abs }}</time>{% endif %}
      {% if e.is_legacy %}<span class="as-tl-item__legacy-label">{{ e.legacy_label }}</span>{% endif %}
      {% if e.is_edited %}<span class="as-tl-item__edited" title="{{ e.edited_at }} · {{ e.edited_by }}">(수정됨)</span>{% endif %}
    </div>
    <div class="as-tl-item__body">{{ e.text | safe }}</div>
  </div>
  {%- endmacro %}
  ```
- [ ] `render_as_timeline` 매크로(전체):
  ```html
  {% macro render_as_timeline(order_id, view, can_edit) -%}
  {% set v = view or {} %}
  <div class="as-timeline" data-order-id="{{ order_id }}">
    {# 앵커: 접수 원문(우선) 또는 legacy #}
    {% if v.reception %}
    <div class="as-timeline__anchor">{{ render_as_timeline_entry(v.reception) }}</div>
    {% elif v.legacy %}
    <div class="as-timeline__anchor as-timeline__anchor--legacy">
      {% for e in v.legacy %}{{ render_as_timeline_entry(e) }}{% endfor %}
    </div>
    {% endif %}
    {% if can_edit %}
    <form class="as-timeline__quick-add" data-order-id="{{ order_id }}">
      <div class="as-timeline__quick-row">
        <select class="as-timeline__type erp-pro-select" aria-label="유형">
          <option value="memo" selected>메모</option>
          <option value="call">통화</option>
          <option value="action">방문/조치</option>
          <option value="material">자재</option>
          <option value="schedule">일정</option>
        </select>
      </div>
      <textarea class="as-timeline__text erp-pro-input" rows="2" placeholder="기록 입력... (Ctrl/⌘+Enter로 추가)"></textarea>
      <button type="submit" class="btn btn-sm btn-primary as-timeline__submit">기록 추가</button>
    </form>
    {% endif %}
    <div class="as-timeline__stream">
      {% for e in v.stream %}{{ render_as_timeline_entry(e) }}{% endfor %}
    </div>
    {% if v.has_more %}
    <button type="button" class="btn btn-sm btn-link as-timeline__more" data-order-id="{{ order_id }}">이전 기록 더보기 ({{ v.stream_total - v.stream|length }})</button>
    {% endif %}
    {% if not v.reception and not v.legacy and not v.stream %}
    <div class="as-timeline__empty text-muted small">기록 없음 · 첫 기록을 남겨보세요.</div>
    {% endif %}
  </div>
  {%- endmacro %}
  ```
- [ ] `render_as_timeline_cell` 매크로(PC 셀 요약 — 접수 1줄 + 최근 1줄 + 배지):
  ```html
  {% macro render_as_timeline_cell(order_id, view) -%}
  {% set v = view or {} %}
  {% set anchor = v.reception or (v.legacy[0] if v.legacy else none) %}
  <div class="as-tl-cell" data-order-id="{{ order_id }}">
    {% if anchor %}
    <div class="as-tl-cell__anchor text-truncate">{{ anchor.text | striptags }}</div>
    {% endif %}
    {% if v.stream %}
    <div class="as-tl-cell__recent text-truncate">
      <span class="as-tl-chip as-tl-chip--{{ v.stream[0].type }}">{{ v.stream[0].type_label }}</span>
      {{ v.stream[0].text | striptags }}
    </div>
    {% endif %}
    {% if v.count %}
    <button type="button" class="as-tl-cell__expand" data-order-id="{{ order_id }}">타임라인 {{ v.count }}</button>
    {% else %}
    <span class="as-tl-cell__empty text-muted small">기록 없음 · 클릭해 첫 기록</span>
    {% endif %}
  </div>
  {%- endmacro %}
  ```
- [ ] `as_dashboard_body.html` import 라인(라인 2)에 신규 매크로 추가 + 내용 셀(라인 234-236) 교체:
  ```html
  {% from 'cs/partials/as_card_macros.html' import render_as_timeline_cell %}
  ...
                <td class="erp-as-content-cell" data-order-id="{{ r.id }}">
                  {{ render_as_timeline_cell(r.id, r.as_timeline_view) }}
                </td>
  ```
- [ ] `as_card_detail_partial.html` 라인 12-17 교체(content_tabs → timeline):
  ```html
  {% from 'cs/partials/as_card_macros.html' import render_as_construction_workers, render_as_timeline %}
  ...
  <div class="erp-as-mobile-card__detail-row erp-pro-order-card__row erp-pro-order-card__row--full">
    <span class="erp-as-mobile-card__detail-label">AS 타임라인</span>
    <div class="erp-as-mobile-card__content">
      {{ render_as_timeline(r.id, r.as_timeline_view, can_edit_erp|default(false)) }}
    </div>
  </div>
  ```
  > card-detail 라우트(erp_as_card_detail)도 `r.as_timeline_view`가 필요 — display 보강이 이미 세팅(T8). 확인.
- [ ] `as_mobile_order_card.html` legacy 카드(라인 230) content_tabs → timeline 교체(v2는 lazy details 유지, 무변경). import에 `render_as_timeline` 추가.
- [ ] 렌더 계약 테스트: 3표면에서 항목 텍스트가 나타나는지(`/erp/as`, `/erp/as/card-detail/<id>`, `/erp/as/timeline/<id>`).
- [ ] `APP_OK`(템플릿만이면 생략 가능하나 라우트 렌더 스모크).
- [ ] 커밋: `feat: render_as_timeline 매크로 + 3표면 교체`.

---

## T10 — JS 교체 (확장 행 + quick-add + 하이라이트 + sales_delivery 이전 + 퇴역)

`as-dashboard.js`를 타임라인 상호작용으로 교체. contenteditable 탭/리치툴바/autosave 경로 퇴역.

### Files
- Modify `static/js/cs/as-dashboard.js`:
  - 신설: 확장 행 lazy fetch(colspan=12, 싱글톤 가드), quick-add(textarea, Ctrl/⌘+Enter isComposing 가드, optimistic), 정적 하이라이트, sales_delivery 토글 이전(확장 행 헤더 + 모바일 상세 헤더)
  - 퇴역: 탭 전환(1131-1150), 리치 command(1152-1170), 리치 툴바 hydrate(1010-1053), autosave(2124-2182 중 contenteditable 경로), maybeApplyAsContentHighlight의 contenteditable 전제(524-559)
- Modify `templates/cs/partials/as_dashboard_body.html`:471(`?v=` 범프)

### Interfaces
Consumes: `POST /api/orders/<id>/as/log`(quick-add·optimistic), `GET /erp/as/timeline/<id>`(확장), `PATCH .../as/log/<log_id>`(항목 수정), `saveOrderFieldDirect(orderId,'sales_delivery',...)`(이전 토글 재사용).
Produces: `window.__FOMS_AS_TIMELINE_BOUND` 싱글톤 가드.

### Steps
- [ ] 확장 행 lazy fetch(PC 셀 `as-tl-cell__expand` 클릭 → 아래 full-width 행 삽입). document 위임 + 싱글톤:
  ```javascript
      if (!window.__FOMS_AS_TIMELINE_BOUND) {
        window.__FOMS_AS_TIMELINE_BOUND = true;

        document.addEventListener('click', function (e) {
          const btn = e.target.closest && e.target.closest('.as-tl-cell__expand');
          if (!btn) return;
          const orderId = btn.dataset.orderId;
          const row = btn.closest('tr[data-order-id]');
          if (!row || !orderId) return;
          const next = row.nextElementSibling;
          if (next && next.classList.contains('as-tl-expand-row')) { next.remove(); return; } // 토글
          const tr = document.createElement('tr');
          tr.className = 'as-tl-expand-row';
          tr.dataset.orderId = orderId;
          tr.innerHTML = '<td colspan="12"><div class="as-tl-expand-body" data-loading="1">'
            + '<div class="text-muted small py-2">불러오는 중...</div></div></td>';
          row.after(tr);
          fetch('/erp/as/timeline/' + encodeURIComponent(orderId), {
            headers: { Accept: 'text/html' }, credentials: 'same-origin',
          }).then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.text(); })
            .then((html) => { tr.querySelector('.as-tl-expand-body').innerHTML = html;
                              tr.querySelector('.as-tl-expand-body').dataset.loading = ''; })
            .catch(() => { tr.querySelector('.as-tl-expand-body').innerHTML =
              '<div class="text-danger small py-2">타임라인을 불러오지 못했습니다.</div>'; });
        });
  ```
- [ ] quick-add(optimistic, isComposing 가드):
  ```javascript
        async function submitQuickAdd(form) {
          const orderId = form.dataset.orderId;
          const textEl = form.querySelector('.as-timeline__text');
          const typeEl = form.querySelector('.as-timeline__type');
          const text = (textEl && textEl.value || '').trim();
          if (!orderId || !text) return;
          const stream = form.parentElement.querySelector('.as-timeline__stream');
          const submitBtn = form.querySelector('.as-timeline__submit');
          if (submitBtn) submitBtn.disabled = true;
          try {
            const res = await fetch('/api/orders/' + encodeURIComponent(orderId) + '/as/log', {
              method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin',
              body: JSON.stringify({ type: (typeEl && typeEl.value) || 'memo', text: text }),
            });
            const data = await res.json();
            if (!data.success) throw new Error(data.message || '기록 추가 실패');
            if (stream) stream.insertAdjacentHTML('afterbegin', data.html); // optimistic prepend
            textEl.value = '';
            if (typeEl) typeEl.value = 'memo'; // 저장 후 memo 리셋(스펙 5.5)
          } catch (err) {
            alert(String(err && err.message || err || '기록 추가 중 오류')); // 텍스트 보존
          } finally { if (submitBtn) submitBtn.disabled = false; }
        }
        document.addEventListener('submit', function (e) {
          const form = e.target.closest && e.target.closest('.as-timeline__quick-add');
          if (!form) return;
          e.preventDefault();
          submitQuickAdd(form);
        });
        document.addEventListener('keydown', function (e) {
          const textEl = e.target.closest && e.target.closest('.as-timeline__text');
          if (!textEl) return;
          if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && !e.isComposing && e.keyCode !== 229) {
            e.preventDefault();
            submitQuickAdd(textEl.closest('.as-timeline__quick-add'));
          }
        });
  ```
- [ ] "더보기"(`as-timeline__more`): 확장 fragment는 기본 최근 8개만 렌더. 더보기 클릭 시 `GET /erp/as/timeline/<id>?full=1`(T8 라우트가 이미 `full` 파라미터로 스트림 전량 재구성)로 body 교체 렌더:
  ```javascript
        document.addEventListener('click', function (e) {
          const more = e.target.closest && e.target.closest('.as-timeline__more');
          if (!more) return;
          const orderId = more.dataset.orderId;
          const body = more.closest('.as-tl-expand-body') || more.closest('.erp-as-mobile-card__content');
          if (!orderId || !body) return;
          fetch('/erp/as/timeline/' + encodeURIComponent(orderId) + '?full=1',
                { headers: { Accept: 'text/html' }, credentials: 'same-origin' })
            .then((r) => r.text()).then((html) => { body.innerHTML = html; }).catch(() => {});
        });
      }
  ```
- [ ] 정적 하이라이트: 검색어(`searchQueryCompact`)를 타임라인 정적 텍스트(`.as-tl-item__body`, `.as-tl-cell__anchor`)에 적용하는 신규 함수. 기존 contenteditable 전용 `applyAsContentHighlight`/`maybeApplyAsContentHighlight`는 정적 텍스트 노드 대상으로 축약(hasAttribute('contenteditable') 가드 제거, 대상 셀렉터를 `.as-tl-item__body, .as-tl-cell__anchor, .as-tl-cell__recent`로). fragment 주입 후 재적용:
  ```javascript
        function highlightTimelineStatic(root) {
          if (!searchQueryCompact) return;
          (root || document).querySelectorAll('.as-tl-item__body, .as-tl-cell__anchor, .as-tl-cell__recent')
            .forEach((el) => applyStaticHighlight(el)); // 기존 findCompactMatches/replaceNodeWithHighlightRanges 재사용
        }
  ```
  > 기존 하이라이트 텍스트노드 분해 로직(`collectHighlightTextNodes`/`replaceNodeWithHighlightRanges`)은 정적 요소에도 동작하므로 `applyAsContentHighlight`에서 `contenteditable` 전제만 제거해 `applyStaticHighlight`로 재명명 재사용. 확장/optimistic 주입 뒤 `highlightTimelineStatic(injectedRoot)` 호출.
- [ ] sales_delivery 토글 이전: 리치툴바 소속 `.as-sales-delivery-btn` 핸들러(1172-1208)는 유지하되 버튼 위치를 확장 행 헤더 + 모바일 상세 헤더로 이전(매크로 T9에 토글 버튼 추가). 핸들러의 `saveOrderFieldDirect(orderId,'sales_delivery',...)` + 탭 리다이렉트 로직은 재사용. **계약 테스트로 토글 보존 고정**(T13). 매크로 `render_as_timeline`에 토글 추가:
  ```html
      {% if can_edit %}
      <div class="as-timeline__header">
        <button type="button" class="btn btn-sm btn-outline-warning as-sales-delivery-btn" data-order-id="{{ order_id }}">☐ 영업/전달</button>
      </div>
      {% endif %}
  ```
  기존 핸들러에서 `getAsEditorContext(input)`(contenteditable 의존)을 orderId 기반으로 단순화 — `const orderId = btn.dataset.orderId;` 직접 사용.
- [ ] 퇴역: 탭 전환 리스너(1131-1150), 리치 command(1152-1170), 툴바 hydrate(1010-1053), autosave/contenteditable draft/flush 경로(bindAsContentAutosaveInputs·bindAsContentEditableInputs 중 contenteditable 관련, 1124-1182 등), `syncAsContentSearchTabs`·탭 상태 함수 삭제. `__fomsAsRebindLazyCard`(1062-1069)는 타임라인용으로 축소(하이라이트 재적용만). **삭제 범위는 grep으로 `as-content-input`/`as-tabbed-editor`/`as-rich` 참조 전수 확인 후 제거**.
- [ ] `?v=` 범프: `as-dashboard.js?v=20260704b` → 새 스탬프. 참조 핀 전수 grep:
  ```
  grep -rn "as-dashboard.js?v=" templates/ static/
  ```
  치환 파일 전부 커밋.
- [ ] gstack browse(SW 미등록 헤드리스)로 append→렌더→optimistic 확인.
- [ ] 커밋: `feat: AS 타임라인 JS(확장행·quick-add·정적 하이라이트) + 탭/툴바/autosave 퇴역`.

---

## T11 — CSS (타임라인/칩/배지/quick-add) + 인라인 제거 + `?v=` 범프

### Files
- Modify `static/css/contexts/cs/as-dashboard-body.css`(타임라인/칩/셀/quick-add 스타일 추가, 구 리치에디터/탭 스타일 라인 96-183 제거)
- Modify `static/css/components/foms-as-mobile-card.css`(모바일 타임라인 스타일)
- Modify `templates/cs/partials/as_dashboard_body.html`:4,8(`?v=` 범프)

### Steps
- [ ] 유형 칩 색(스펙 5.5: 접수=남색·통화=파랑·방문/조치=초록·자재=주황·일정=보라·메모=회색):
  ```css
    .as-tl-chip { display: inline-block; padding: 0 6px; border-radius: 10px;
      font-size: 0.7rem; font-weight: 700; line-height: 1.6; color: #fff; }
    .as-tl-chip--reception { background: #1e3a8a; }
    .as-tl-chip--call { background: #2563eb; }
    .as-tl-chip--action { background: #16a34a; }
    .as-tl-chip--material { background: #f59e0b; }
    .as-tl-chip--schedule { background: #7c3aed; }
    .as-tl-chip--memo { background: #6b7280; }
  ```
- [ ] 타임라인/앵커/스트림/시스템/legacy/quick-add/셀 스타일:
  ```css
    .as-timeline__anchor { border-left: 3px solid #1e3a8a; padding-left: 8px; margin-bottom: 8px; }
    .as-timeline__anchor--legacy { border-left-color: #cbd5e1; background: #f8fafc; }
    .as-tl-item { padding: 6px 0; border-bottom: 1px solid #f1f5f9; }
    .as-tl-item--system { background: #f8fafc; color: #64748b; }
    .as-tl-item--legacy { background: #f8fafc; }
    .as-tl-item__meta { display: flex; align-items: center; gap: 6px; font-size: 0.72rem; color: #64748b; }
    .as-tl-item__body { white-space: pre-wrap; font-size: 0.85rem; margin-top: 2px; }
    .as-tl-item__edited { color: #94a3b8; }
    .as-timeline__quick-add { display: flex; flex-direction: column; gap: 4px; margin: 8px 0; }
    .as-timeline__text { min-height: 44px; }   /* 인라인 min-height 제거분 이전 */
    .as-tl-cell__anchor { font-size: 0.82rem; }
    .as-tl-cell__recent { font-size: 0.78rem; color: #475569; }
    .as-tl-cell__expand { border: 0; background: none; color: #2563eb; font-size: 0.72rem; padding: 0; cursor: pointer; }
    .as-tl-expand-row > td { background: #fbfcfe; }
  ```
- [ ] 구 스타일 제거: `.as-rich-editor`·`.as-rich-toolbar`·`.as-content-tab-*`·`.as-sales-delivery-btn`(단, sales-delivery 버튼은 유지 필요 — 헤더로 이전했으므로 클래스 유지) 관련 라인 96-183 중 리치/탭 전용만 삭제. `mark.as-search-highlight`(185)는 유지(정적 하이라이트 재사용).
- [ ] `?v=` 범프(라인 4·8) + `grep -rn "as-dashboard-body.css?v=\|foms-as-mobile-card.css?v=" templates/` 핀 전수 치환.
- [ ] gstack browse 시각 확인.
- [ ] 커밋: `feat: AS 타임라인 CSS + 구 리치에디터/탭 스타일 제거`.

---

## T12 — `update_order_field` as_content 퇴역 + legacy 영구화 + 계약 테스트

`update_order_field`의 `as_content`/`as_content_2` allowlist 제거(신규 쓰기 차단). 최초 append 시 legacy 영구화(T6 `migrate_legacy_into_log`가 커버). legacy 보존·sales_delivery 보존 계약 테스트.

### Files
- Modify `foms/api/orders/field_update.py`:42-43, 58-59, 153-154, 233-234, 273-274, 317-318, 380-383, 492-493, 529-530(as_content/as_content_2 분기 제거)
- Modify `tests/domains/test_erp_as_dashboard_tabs.py`:313-335(`test_update_order_field_saves_secondary_as_content` → 거부 계약으로 재지정)
- Create/Modify `tests/domains/test_as_timeline_contract.py`(legacy 보존·sales_delivery 보존)

### Interfaces
Produces: `update_order_field`에서 `field == 'as_content'|'as_content_2'` → 400(허용 필드 아님).
- `sales_delivery`·`as_pending`·`as_blueprint`·날짜 필드는 현행 유지(무변경).

### Steps
- [ ] 계약 테스트 재지정(기존 저장 테스트 → 거부):
  ```python
  def test_update_order_field_rejects_as_content_2(client):
      _login_as_admin(client)
      order = _create_as_order()
      res = client.post("/api/update_order_field",
                        json={"order_id": order.id, "field_name": "as_content_2", "new_value": "x"})
      assert res.status_code == 400
      assert res.get_json()["success"] is False
  ```
- [ ] legacy 보존 계약(최초 append가 기존 as_content를 legacy로 흡수·보존):
  ```python
  def test_first_append_persists_legacy(client):
      _login_as_admin(client)
      order = _create_as_order(shipment_extra={"as_content": "<div>옛 접수 원문</div>"}, as_content_2=None)
      client.post(f"/api/orders/{order.id}/as/log", json={"type": "call", "text": "통화"})
      db_session.expire_all()
      log = db_session.get(Order, order.id).structured_data["shipment"]["as_log"]
      assert any(e.get("legacy") is True and "옛 접수 원문" in e.get("text", "") for e in log)
      assert any(e.get("type") == "call" for e in log)
  ```
- [ ] sales_delivery 토글 보존 계약(퇴역 후에도 update_order_field 경로 정상):
  ```python
  def test_sales_delivery_toggle_still_works(client):
      _login_as_admin(client)
      order = _create_as_order()
      res = client.post("/api/update_order_field",
                        json={"order_id": order.id, "field_name": "sales_delivery", "new_value": True})
      assert res.status_code == 200 and res.get_json()["success"] is True
      db_session.expire_all()
      assert db_session.get(Order, order.id).structured_data["shipment"]["sales_delivery"] is True
  ```
- [ ] 실패 확인.
- [ ] field_update.py에서 `as_content`/`as_content_2` 제거: `EDITABLE_*` allowlist(42-43), `STRUCTURED_SYNC_FIELDS`(58-59), normalized 분기(153-154), sanitize(233-234), 캐시 무효화 분기(273-274, 317-318), 저장 분기(380-383), 재조회 필드(492-493), extras_by_field(529-530). **grep `as_content` in field_update.py로 전수 제거 확인**, 잔존 참조 없음.
- [ ] 통과 확인 + `APP_OK`.
- [ ] 커밋: `refactor: update_order_field as_content 쓰기 퇴역 + legacy 영구화 계약`.

---

## T13 — P2 검증 게이트

### Steps
- [ ] 신규 pytest 전체:
  ```
  python -m pytest tests/domains/test_as_log_service.py tests/domains/test_as_log_api.py \
    tests/domains/test_as_timeline_fragment.py tests/domains/test_as_timeline_contract.py \
    tests/domains/test_as_billing.py -q
  ```
- [ ] 3표면 렌더 계약: `/erp/as`(셀 요약), `/erp/as/card-detail/<id>`(모바일 타임라인), `/erp/as/timeline/<id>`(확장) 모두 항목 텍스트 노출.
- [ ] 기존 AS 10파일 green(T5 명령).
- [ ] gstack browse E2E(SW 미등록 헤드리스): append → 렌더 → 항목 수정(PATCH) → 검색 하이라이트 → 확장 유지(무한스크롤 청크 append 후에도 확장 행 유지). console error 0 확인.
- [ ] `pre_push_smoke.ps1` exit 0 → push → `ci_watch` green(perf-gate 포함 `gh run list` 전수 확인).
- [ ] 커밋: `chore: P2 검증 게이트 통과 기록`.

---

# Phase P3 — 자동화·마무리

---

## T14 — 시스템 이벤트 자동 append 4곳

register/schedule/billing 전환/complete에 `append_system_log` 추가. 기존 `as_info`/`OrderEvent`는 병행 유지(불변).

### Files
- Modify `foms/api/cs/as_orders.py`(`api_as_register`·`api_as_schedule`·`api_as_complete`·`api_as_billing` 각 커밋 전 append)
- Modify `tests/domains/test_as_log_api.py`(이벤트 발생 계약)

### Interfaces
Consumes: `append_system_log(sd, text=...)`.
- register: "AS 접수됨" / schedule: "방문일 확정: <date>" / billing 전환: "무상→유상 전환: <사유>" / complete: "AS 완료".

### Steps
- [ ] 실패 테스트:
  ```python
  def test_schedule_appends_system_log(client):
      _login_as_admin(client)
      order = _create_as_order(shipment_extra={"as_log": []})
      client.post(f"/api/orders/{order.id}/as/schedule", json={"visit_date": "2026-08-01"})
      db_session.expire_all()
      log = db_session.get(Order, order.id).structured_data["shipment"]["as_log"]
      assert any(e.get("type") == "system" and "방문일 확정" in e.get("text", "") for e in log)
  ```
- [ ] as_orders.py 상단 import에 `append_system_log` 추가(T7의 `from foms.services.orders.as_log import ...` 라인에 병합).
- [ ] 각 라우트 커밋 전 append. billing 전환은 T2 라우트에서 `prev_type != new_type`일 때:
  ```python
  # api_as_billing: _write_as_billing 뒤
          if prev_type != new_type:
              label = {"free": "무상", "paid": "유상", "undecided": "미정"}
              append_system_log(sd, text=f"{label.get(prev_type, prev_type)}→{label.get(new_type, new_type)} 전환: {reason}")
  # api_as_schedule: sd 저장 전
          append_system_log(sd, text=f"방문일 확정: {visit_date}")
  # api_as_complete: sd 저장 전
          append_system_log(sd, text="AS 완료")
  # api_as_register: reception append 뒤
          append_system_log(sd, text="AS 접수됨")
  ```
  > register는 reception 수기 항목 + system "AS 접수됨" 둘 다(수기=본문, system=이벤트 로그). schedule/complete는 `sd` 로드가 이미 있으므로 그 dict에 append.
- [ ] 통과 확인 + `APP_OK`.
- [ ] 커밋: `feat: AS 시스템 이벤트 자동 기록 4곳(register/schedule/billing/complete)`.

---

## T15 — 모바일 프리셋 4종 + 과도기 힌트 배너

원탭 프리셋(부재중·조치 완료·재방문 필요·자재 필요) → textarea 초안 주입 + 유형 자동 설정 + focus(자동 전송 아님). 1회 dismissible 힌트 배너(localStorage).

### Files
- Modify `templates/cs/partials/as_card_macros.html`(`render_as_timeline` quick-add 위 프리셋 버튼 — 모바일만)
- Modify `static/js/cs/as-dashboard.js`(프리셋 클릭 → 초안 주입, 배너 dismiss)
- Modify `static/css/components/foms-as-mobile-card.css`(프리셋 버튼·배너 스타일)

### Interfaces
Produces: 프리셋 4종 `{부재중→call/"고객 부재중, 재연락 예정", 조치 완료→action/"방문 조치 완료", 재방문 필요→schedule/"재방문 필요", 자재 필요→material/"자재 발주 필요"}`.
- 배너 localStorage 키: `foms_as_timeline_hint_dismissed`.

### Steps
- [ ] 매크로 프리셋(모바일 표면에서만 노출 — CSS `d-md-none` 또는 상세 내부):
  ```html
      {% if can_edit %}
      <div class="as-timeline__presets d-md-none" aria-label="빠른 기록">
        <button type="button" class="as-tl-preset" data-type="call" data-text="고객 부재중, 재연락 예정">부재중</button>
        <button type="button" class="as-tl-preset" data-type="action" data-text="방문 조치 완료">조치 완료</button>
        <button type="button" class="as-tl-preset" data-type="schedule" data-text="재방문 필요">재방문 필요</button>
        <button type="button" class="as-tl-preset" data-type="material" data-text="자재 발주 필요">자재 필요</button>
      </div>
      {% endif %}
  ```
- [ ] JS 프리셋 배선(주입만, 자동 전송 금지):
  ```javascript
        document.addEventListener('click', function (e) {
          const preset = e.target.closest && e.target.closest('.as-tl-preset');
          if (!preset) return;
          const form = preset.closest('.as-timeline').querySelector('.as-timeline__quick-add');
          if (!form) return;
          const textEl = form.querySelector('.as-timeline__text');
          const typeEl = form.querySelector('.as-timeline__type');
          if (typeEl) typeEl.value = preset.dataset.type || 'memo';
          if (textEl) { textEl.value = preset.dataset.text || ''; textEl.focus(); } // 수기 수정 후 저장
        });
  ```
- [ ] 힌트 배너(1회, localStorage). as_dashboard_body.html 상단에 `#as-timeline-hint`(dismiss 버튼) 추가 + JS:
  ```javascript
        (function () {
          const banner = document.getElementById('as-timeline-hint');
          if (!banner) return;
          if (localStorage.getItem('foms_as_timeline_hint_dismissed') === '1') { banner.remove(); return; }
          banner.classList.remove('d-none');
          const dismiss = banner.querySelector('.as-timeline-hint__dismiss');
          if (dismiss) dismiss.addEventListener('click', function () {
            localStorage.setItem('foms_as_timeline_hint_dismissed', '1'); banner.remove();
          });
        })();
  ```
  배너 문구: "AS 내용이 이력 형식으로 바뀌었습니다. 기존 내용은 '이전 기록'에 그대로 있습니다."
- [ ] `?v=` 범프(JS·CSS) + 핀 전수 grep.
- [ ] 모바일 E2E(gstack browse, isMobile): 프리셋 탭 → 초안 주입 확인 → 수정 → 저장.
- [ ] 커밋: `feat: AS 모바일 프리셋 4종 + 과도기 힌트 배너`.

---

## T16 — 최종 게이트

### Steps
- [ ] `powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` exit 0(APP_OK·harness verify·SSOT lint·CI subset·구조 테스트).
- [ ] 전 AS 테스트 green(기존 10 + 신규: test_as_billing·test_as_log_service·test_as_log_api·test_as_timeline_fragment·test_as_timeline_contract).
- [ ] perf: fragment 바이트(타임라인 셀 요약만 eager, 확장은 lazy) · 대시보드 TTFB 측정 · billing 필터 `EXPLAIN` Seq Scan 없음.
- [ ] 심볼 이동 계약(erp_permissions/namespace/runtime): `python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py -q`(erp_orders_as_bp에 신규 라우트 등록 확인).
- [ ] push → `ci_watch` + `gh run list`(perf-gate 포함) green.
- [ ] `docs/AI_STATUS.md`·`docs/AI_CHANGELOG.md` 갱신.
- [ ] 커밋: `chore: AS 타임라인 개편 P3 최종 게이트 통과`.

---

## 부록 — 데이터 모델 참조(스펙 §3 복사)

`sd['shipment']['as_log']` (append-only):
```json
[{"id":"al_<ms>_<r4>","ts":"<utc naive iso>","by":"이름","by_id":123,
  "type":"reception|call|action|material|schedule|memo|system",
  "text":"<sanitize 통과 HTML>","edited_at":null,"edited_by":null}]
```
legacy 항목은 `"legacy": true`, `"legacy_label"` 추가·읽기 전용.

`sd['shipment']['as_billing']`:
```json
{"type":"free|paid|undecided","confirmed":false,"amount":null,
 "reason":"","decided_by":"이름","decided_at":"<iso>"}
```

## 범위 제외 (YAGNI, 스펙 §8)
음성 입력, 오프라인 큐 확장, 항목 단위 사진 첨부, 견적/청구 라인 연계, AS 별도 테이블(C안), 삭제 API. "최근 사용 유형 기억" 기각(저장 후 memo 리셋).
