# AS Shipment Dashboard Regression Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Restore shipment dashboard behavior so AS orders are grouped by AS visit date and show readable AS text without raw HTML, while preserving the current AS data contract.

**Architecture:** Extend the existing `order_schedule_dates` read model with `kind='as_visit'` instead of re-coupling AS to `scheduled_date`. Keep sanitized HTML storage in AS workflows, but convert it to plain text only for shipment-dashboard rendering.

**Tech Stack:** Flask, SQLAlchemy, Jinja2, existing `OrderScheduleDate` normalization, pytest

---

### Task 1: Add Regression Tests First

**Files:**
- Create: `tests/test_shipment_dashboard_regression.py`
- Reference: `services/order_date_sync.py`
- Reference: `apps/erp_shipment_page.py`
- Reference: `services/as_content_safety.py`

**Step 1: Write an order factory for tests**

```python
from models import Order


def make_order(**overrides):
    data = {
        "received_date": "2026-03-19",
        "customer_name": "테스터",
        "phone": "010-0000-0000",
        "address": "서울시 강남구 테스트로 1",
        "product": "테스트 제품",
        "status": "RECEIVED",
        "is_erp_beta": True,
        "structured_data": {},
    }
    data.update(overrides)
    return Order(**data)
```

**Step 2: Write failing test for `as_visit` date normalization**

```python
def test_collect_order_schedule_date_specs_includes_as_visit():
    order = make_order(
        status="AS_RECEIVED",
        structured_data={"schedule": {"as_visit": {"date": "2026-03-21"}}},
    )

    specs = collect_order_schedule_date_specs(order)
    pairs = {(spec["kind"], spec["date"]) for spec in specs}

    assert ("as_visit", "2026-03-21") in pairs
```

**Step 3: Run the test to verify it fails**

Run: `pytest tests/test_shipment_dashboard_regression.py -q`

Expected: FAIL because `collect_order_schedule_date_specs()` does not currently emit `as_visit`.

**Step 4: Write failing test for shipment dashboard date selection**

```python
def test_extract_dashboard_target_dates_uses_as_visit_for_as_orders():
    order = make_order(
        status="AS",
        scheduled_date="2026-03-25",
        structured_data={
            "schedule": {
                "construction": {"date": "2026-03-25"},
                "as_visit": {"date": "2026-03-21"},
            }
        },
    )

    assert extract_dashboard_target_dates(order) == {"2026-03-21"}
```

**Step 5: Write failing test for shipment AS content text rendering**

```python
def test_as_content_html_to_text_strips_tags():
    html = "<div><b>경첩</b> 교체</div><div><font color='red'>긴급</font></div>"

    text = as_content_html_to_text(html)

    assert "경첩" in text
    assert "긴급" in text
    assert "<div>" not in text
    assert "<font" not in text
```

**Step 6: Add one route-level failing test for `/erp/shipment`**

```python
def test_shipment_route_uses_as_visit_for_as_orders(login):
    db = get_db()
    as_order = make_order(
        status="AS_RECEIVED",
        customer_name="AS고객",
        structured_data={"schedule": {"as_visit": {"date": "2026-03-21"}}},
    )
    normal_order = make_order(
        status="CONFIRM",
        customer_name="일반고객",
        structured_data={"schedule": {"construction": {"date": "2026-03-25"}}},
    )

    db.add_all([as_order, normal_order])
    db.commit()
    sync_order_dates(as_order, db)
    sync_order_dates(normal_order, db)
    db.commit()

    response = login.get("/erp/shipment?date=2026-03-21")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "AS고객" in body
    assert "일반고객" not in body
```

**Step 7: Run the full new test file**

Run: `pytest tests/test_shipment_dashboard_regression.py -q`

Expected: FAIL on the new helpers/behavior.

---

### Task 2: Normalize `as_visit` Into `OrderScheduleDate`

**Files:**
- Modify: `services/order_date_sync.py`
- Test: `tests/test_shipment_dashboard_regression.py`

**Step 1: Add `as_visit` extraction to `collect_order_schedule_date_specs()`**

```python
as_visit_dates = set()
if isinstance(getattr(order, "structured_data", None), dict):
    sd = order.structured_data
    schedule = sd.get("schedule") or {}
    as_visit = schedule.get("as_visit") or {}
    visit_date = (as_visit.get("date") or "").strip()
    if visit_date:
        for d in visit_date.split(","):
            if d.strip():
                nd = _normalize_date_str(d.strip())
                if nd not in as_visit_dates:
                    specs.append({
                        "kind": "as_visit",
                        "date": nd,
                        "source": "structured_schedule",
                        "item_index": None,
                    })
                    as_visit_dates.add(nd)
```

**Step 2: Keep construction sync behavior unchanged in this task**

Do not add any sync from `as_visit` back to `scheduled_date` or `construction`. Also do not try to scrub historical `construction` rows from AS orders in this change.

**Step 3: Run targeted test**

Run: `pytest tests/test_shipment_dashboard_regression.py -q`

Expected: the `collect_order_schedule_date_specs_includes_as_visit` test now passes.

---

### Task 3: Split Shipment Date Logic Between AS and Construction

**Files:**
- Modify: `apps/erp_shipment_page.py`
- Test: `tests/test_shipment_dashboard_regression.py`

**Step 1: Add explicit helpers near the top of the file**

```python
AS_SHIPMENT_STATUSES = ("AS", "AS_RECEIVED", "AS_COMPLETED")


def is_as_order(order):
    return getattr(order, "status", None) in AS_SHIPMENT_STATUSES


def extract_dashboard_target_dates(order):
    target_kind = "as_visit" if is_as_order(order) else "construction"
    dates = set()
    if getattr(order, "schedule_dates", None) is not None:
        for row in order.schedule_dates:
            if row.kind == target_kind and row.date:
                dates.add(str(row.date))
        if dates:
            return dates

    if target_kind == "as_visit":
        schedule = ((order.structured_data or {}).get("schedule") or {}) if getattr(order, "structured_data", None) else {}
        visit = (schedule.get("as_visit") or {}).get("date") or ""
        return {part.strip() for part in str(visit).split(",") if part and part.strip()}

    return extract_all_construction_dates(order)
```

**Step 2: Update panel query to use status+kind matched pairs**

Use a single join but filter with paired conditions:

```python
rows_query = rows_query.join(OrderScheduleDate, Order.id == OrderScheduleDate.order_id)
rows_query = rows_query.filter(
    or_(
        and_(Order.status.in_(AS_SHIPMENT_STATUSES), OrderScheduleDate.kind == "as_visit"),
        and_(Order.status.notin_(AS_SHIPMENT_STATUSES), OrderScheduleDate.kind == "construction"),
    )
)
```

Apply the same rule to `panel_query`.

**Step 3: Replace panel counting/search-auto-move loops**

Where the file currently calls `extract_all_construction_dates(order)`, switch to the new `extract_dashboard_target_dates(order)`.

**Step 4: Keep `remaining_panel_dates` capacity math unchanged**

Do not switch `assigned_workers_by_date` / `spec_units_by_date` to AS visit dates in this change. Limit the behavioral fix to the left date-count panel, row list filtering, and search auto-move.

**Step 5: Remove AS fallback to `scheduled_date/as_received_date/as_completed_date` from shipment-date resolution**

AS shipment inclusion should depend on `as_visit` only.

**Step 6: Run tests**

Run: `pytest tests/test_shipment_dashboard_regression.py -q`

Expected: the date-selection regression tests pass.

---

### Task 4: Convert AS HTML To Shipment-Friendly Plain Text

**Files:**
- Modify: `services/as_content_safety.py`
- Modify: `apps/erp_shipment_page.py`
- Modify: `templates/erp_shipment_dashboard.html`
- Test: `tests/test_shipment_dashboard_regression.py`

**Step 1: Add a plain-text helper in `services/as_content_safety.py`**

```python
def as_content_html_to_text(value):
    sanitized = sanitize_as_content_html(value)
    if not sanitized:
        return ""

    soup = BeautifulSoup(sanitized, "html.parser")
    return soup.get_text("\n", strip=True)
```

**Step 2: Precompute `r.as_content_text` in `apps/erp_shipment_page.py`**

```python
shipment = sd.get("shipment") or {}
r.as_content_text = as_content_html_to_text(shipment.get("as_content") or "")
```

**Step 3: Update the template to render only the precomputed text**

```jinja2
<div style="white-space: pre-wrap;">{{ r.as_content_text if r.as_content_text else 'AS 내용 없음' }}</div>
```

**Step 4: Run tests**

Run: `pytest tests/test_shipment_dashboard_regression.py -q`

Expected: HTML-to-text regression test passes.

---

### Task 5: Deploy, Backup, And Backfill Existing `as_visit` Dates

**Files:**
- Reuse: `scripts/backup_order_schedule_dates.py`
- Reuse: `scripts/backfill_phase4_dates.py`
- Reuse: `scripts/restore_order_schedule_dates.py`
- Reference: `services/order_date_sync.py`

**Step 1: Deploy code first and ensure all web/worker processes run the new code**

Do not run backfill while old processes are still alive, because a legacy save path can rewrite `order_schedule_dates` without `as_visit`.

**Step 2: Back up the current read model**

Run: `python scripts/backup_order_schedule_dates.py`

Expected: backup JSON created successfully.

**Step 3: Run dry-run on a known impacted order**

Run: `python scripts/backfill_phase4_dates.py --dry-run --order-id <영향 주문 ID> --verbose`

Expected: diff output shows orders whose desired rows now include `("as_visit", "...")`.

Do not use `--only-missing` for this rollout.

**Step 4: Run a targeted apply on the same impacted order**

Run: `python scripts/backfill_phase4_dates.py --order-id <ID> --verbose`

Expected: one order updated successfully.

**Step 5: Run full apply**

Run: `python scripts/backfill_phase4_dates.py --verbose`

Expected: finishes with `failed: 0`.

**Step 6: Define rollback**

If backfill result is wrong:

Run: `python scripts/restore_order_schedule_dates.py --input <backup.json> --apply RESTORE`

---

### Task 6: Final Verification And GDM Review

**Files:**
- Modify: `progress.md` (optional session log update)
- Reference: `docs/specs/2026-03-19-as-shipment-dashboard-regression-fix.md`

**Step 1: Import smoke**

Run: `python -c "import app; print('APP_OK')"`

Expected: `APP_OK`

**Step 2: Run targeted tests**

Run: `pytest tests/test_shipment_dashboard_regression.py -q`

Expected: PASS

**Step 3: Check recent lint errors**

Run `ReadLints` on:
- `services/order_date_sync.py`
- `apps/erp_shipment_page.py`
- `services/as_content_safety.py`
- `templates/erp_shipment_dashboard.html`
- `tests/test_shipment_dashboard_regression.py`

Expected: no new actionable errors

**Step 4: Manual smoke**

1. Log in
2. Set an AS order’s `AS 방문일`
3. Open `/erp/shipment?date=<AS방문일>`
4. Confirm the AS order is shown on that date
5. Confirm AS content is readable text, not raw HTML tags
6. Confirm non-AS construction orders still appear by construction date
7. Confirm remaining capacity/worker panel numbers did not unexpectedly change because of AS visit dates

**Step 5: GDM closeout**

Document:
- what was found
- what changed
- why this fix keeps the Phase 4 architecture intact

---

### Notes
- Do **not** reintroduce `as_visit_date -> scheduled_date` synchronization.
- Do **not** switch shipment dashboard to `|safe` HTML rendering.
- Do **not** touch the user’s existing `apps/erp_as_page.py` changes.
- Do **not** create a git commit unless the user explicitly asks for one.
