# ERP Beta & Measurement Logic Extraction Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `code-refactoring-refactor-clean` to execute this plan.

**Goal:** Extract separate Blueprint (`apps/erp_beta.py`) for all `/erp/...` routes and related logic from `app.py`.

**Architecture:**
- Create `apps/erp_beta.py` with `erp_beta_bp`.
- Move specific helpers and template filters related to ERP.
- Register blueprint in `app.py`.
- Resolve dependencies (auth, db, models).

**Tech Stack:** Flask, SQLAlchemy

---

### Task 1: Create Blueprint Module

**Files:**
- Create: `c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\apps\erp_beta.py`

**Steps:**
1.  Create the file with necessary imports from `flask`, `db`, `models`, and `apps.auth`.
2.  Define `erp_beta_bp = Blueprint('erp_beta', __name__)`.

### Task 2: Migrate Helper Functions & Filters

**Files:**
- Modify: `c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\apps\erp_beta.py`
- Modify: `c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\app.py`

**Steps:**
1.  Move these template filters if they are primarily used in ERP (otherwise duplicate or import):
    - `split_count`
    - `split_list`
    - `strip_product_w`
    - `spec_w300`
    - `format_phone`
    - `spec_w300_value` (helper)
    - Helpers like `load_holidays_for_year`, `get_manager_name_for_sort`, `normalize_worker_name` needed for dashboards.

### Task 3: Migrate Routes

**Files:**
- Modify: `c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\apps\erp_beta.py`
- Modify: `c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\app.py`

**Steps:**
1.  Move the following route handlers:
    - `erp_dashboard`
    - `erp_measurement_dashboard`
    - `erp_shipment_dashboard`
    - `erp_shipment_settings`
    - `erp_as_dashboard`
    - `api_erp_shipment_settings_get`
    - `api_erp_shipment_settings_save`
    - `api_erp_shipment_update`
    - `api_erp_measurement_update`
    - `api_erp_measurement_route`
    - `api_map_data`
    - `api_generate_map`
2.  Ensure `@login_required` uses the one from `apps.auth` (or checks session).
3.  Ensure `role_required` is imported if used.

### Task 4: Register Blueprint & Cleanup

**Files:**
- Modify: `c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\app.py`

**Steps:**
1.  Register `erp_beta_bp` in `app.py`.
2.  Remove all moved code from `app.py`.

### Task 5: Update Templates

**Files:**
- Modify: `c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\templates\layout.html`
- Modify: `c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\templates\erp_dashboard.html`
- Modify: `c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\templates\erp_measurement_dashboard.html`
- Modify: `c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\templates\erp_shipment_dashboard.html`
- Modify: `c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\templates\erp_as_dashboard.html`

**Steps:**
1.  Search and replace `url_for('erp_dashboard')` -> `url_for('erp_beta.erp_dashboard')` etc.
