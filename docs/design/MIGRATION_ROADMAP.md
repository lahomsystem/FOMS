`# FOMS 모바일·태블릿 리디자인 마이그레이션 로드맵

> 작성: 2026-05-28 | 짝 문서: `MOBILE_TABLET_REDESIGN_PLAN.md`, `MOBILE_TABLET_DESIGN_SYSTEM.md`, `COMPONENT_LIBRARY_MOBILE.md`
> 분류: P0 = 즉시(1주) / P1 = 단기(2~4주) / P2 = 중기(3개월)

각 PR은 다음 형식으로 기술:
- **명세**: 변경 대상 + 변경 의도
- **파일**: 수정·생성 파일 목록
- **검증**: 통과 기준
- **위험**: 회귀 가능 영역
- **추정**: 작업 시간 (실작업 기준, 검토 제외)

---

## P0 — 즉시 (약 7 작업일, 58h — v1.1)

> 비효율 결함 2건(AS paste, 768~991 nav 충돌) 제거 + 기존 모바일 카드 3종 gap patch + cohort 점진 출시. 환경변수 기본값 false 유지, user_id 화이트리스트로 Day 1~7 점진. Playwright baseline 필수.

### P0-00. **Foundation PR** — P0 진입 전 선행 (2회차 외부 LLM 평가 반영 + 4 agent 코드베이스 컨텍스트 검증)

> P0 본 작업 시작 전 5개 기반 항목을 선행. 각 항목은 **자기 완결적 sub-PR**로 LLM agent가 다른 컨텍스트 없이 즉시 실행 가능. P0-00E(SSOT lint)는 완료. 나머지 A~D는 병렬 가능(상호 의존 없음, 단 D의 캡처는 A의 cohort 미사용 default false 상태에서 수행).

**진행 현황**
- ✅ **P0-00E** SSOT lint 가드 — `tools/design/ssot_lint.py` + `tests/harness/test_design_ssot_lint.py` + `.github/workflows/ci.yml:30` 등록 완료
- ✅ **P0-00A** feature_flags.py — `foms/services/feature_flags.py` + `tests/domains/test_feature_flags.py`
- ✅ **P0-00B** OrderDraft 모델 + Alembic — `models.py:624` + `migrations/versions/add_order_drafts_table.py`
- ✅ **P0-00C** cleanup cron — `tools/cron/cleanup_order_drafts.py` + `railway-cron.toml` (Railway Cron 등록은 ops 1회)
- ✅ **P0-00D** Playwright 시각 baseline — `tests/visual/` 12 PNG + CI visual job

---

#### P0-00A. `foms/services/feature_flags.py` 계약 확정

**의존**: 없음. 병렬 가능.

**명세**: `os.getenv` 인라인 토글을 통합 헬퍼로 추출. 5개 flag 시그니처 + cohort 화이트리스트 지원.

**구현 단계**
1. **신규 `foms/services/feature_flags.py` 작성**
   - 참조: 본 문서 `Feature Flag Matrix (v1.1 확정)` 섹션에 초안 코드가 완성 상태로 존재. 그대로 옮기되 아래 시그니처 준수.
   - 함수 3개: `env_bool(key: str, default: bool = False) -> bool`, `env_id_list(key: str) -> set[int]`, `is_enabled_for_user(flag: str, user_id: int | None = None, cohort_key: str | None = None) -> bool`
   - flag 5개 (기본값): `ERP_MOBILE_V2_ENABLED=False`, `FOMS_DESIGN_TOKENS_V2_ENABLED=True`, `FOMS_WIZARD_NEW_ORDER_ENABLED=False`, `FOMS_INLINE_EDIT_ENABLED=False`, `FOMS_TABLET_SPLIT_VIEW_ENABLED=False`
   - cohort env 1개: `FOMS_V3_SHELL_COHORT=""` (comma-separated user id, ERP_MOBILE_V2와 AND)
2. **`foms/services/context_processors.py:78-97` 리팩토링**
   - `ERP_ORDER_ENABLED`, `ERP_MOBILE_V2_ENABLED`, `USE_DIRECT_UPLOAD` 3개 인라인 블록을 `from foms.services.feature_flags import env_bool, is_enabled_for_user`로 교체
   - `ERP_MOBILE_V2_ENABLED`만 `uid = current_user.id if current_user else None` guard 후 `is_enabled_for_user('ERP_MOBILE_V2_ENABLED', uid, cohort_key='FOMS_V3_SHELL_COHORT')` 사용. 나머지 2개는 `env_bool()` 사용
3. **신규 `tests/domains/test_feature_flags.py` 작성** (⚠ `tests/services/`가 아님 — 컨벤션 확인됨)
   - 패턴 참고: `tests/domains/test_erp_permissions.py` (SimpleNamespace + monkeypatch.setenv)
   - 케이스: `env_bool` true/false/대소문자/"1"/"on", `env_id_list` 빈값/단일/다중/공백 trim, `is_enabled_for_user` flag off / flag on + cohort 비어있음 / flag on + cohort에 id 있음 / flag on + cohort에 id 없음 / custom `cohort_key='FOMS_V3_SHELL_COHORT'`

**파일**
- 신규: `foms/services/feature_flags.py`
- 신규: `tests/domains/test_feature_flags.py`
- 수정: `foms/services/context_processors.py:78-97` (3개 블록 교체)

**검증**
- [ ] `pytest tests/domains/test_feature_flags.py -v` 통과 (≥ 8 케이스)
- [ ] `python -c "import app; print('APP_OK')"` 통과
- [ ] `pytest tests/ -q` 회귀 0
- [ ] Railway에 `ERP_MOBILE_V2_ENABLED=true` + `FOMS_V3_SHELL_COHORT="<cohort 비어있음>"` 설정 시 어떤 user도 새 셸 진입 불가 (cohort 빈 = 비활성, 안전 default)

**위험**: 기존 `context_processors.py` 의존 모듈 회귀 — 완화: 헬퍼 호출 결과가 기존 인라인 결과와 동일함을 단위 테스트로 명시.

**추정**: 3h

---

#### P0-00B. OrderDraft 모델 + Alembic 마이그레이션

**의존**: 없음. P0-00A와 병렬 가능.

**명세**: 모바일 wizard 자동저장용 임시 draft 저장. payload는 JSONB. TTL 7일.

**구현 단계**
1. **`models.py`에 직접 OrderDraft 추가** (⚠ `foms/models/order_draft.py` 별도 파일 만들지 말 것 — 프로젝트 컨벤션 단일 `models.py` + 단일 `Base`)
   - 위치: `OrderEstimate` 인근, 채널 로그 모델들(`ChannelDeliveryLog`, `ChannelInboundEventLog`)보다 앞. `models.py` 파일 말미가 아님.
   - 패턴 참고: `models.py:7` 의 `JSONColumn = JSON().with_variant(JSONB, 'postgresql')` 래퍼 사용 (SQLite 테스트 호환 필수)
   - import: `models.py` 상단 SQLAlchemy import에 `UniqueConstraint` 추가 필요
   - 필드: `id (Integer PK)`, `user_id (Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)`, `order_id (Integer, ForeignKey('orders.id', ondelete='CASCADE'), nullable=True, index=True)`, `draft_key (String(64), nullable=False)`, `step (Integer, nullable=False, default=1)`, `payload (JSONColumn, nullable=False, default=dict)`, `schema_version (Integer, nullable=False, default=1)`, `created_at (DateTime, default=datetime.datetime.now)`, `updated_at (DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)`, `expires_at (DateTime, nullable=False, index=True)` — cron이 `WHERE expires_at < now()` 로 삭제
   - 복합 unique: `UniqueConstraint('user_id', 'draft_key', name='uq_order_drafts_user_key')`
   - payload schema 검증: 본 문서 `부록 B. OrderDraft Payload JSON Schema (draft_v1)` 참조. 모델 단계에서는 schema 강제 없이 raw JSONB 저장.
2. **`migrations/env.py:29` import 추가**
   - 현재: `from models import Order, User, AccessLog, SecurityLog`
   - 변경 후: `from models import Order, User, AccessLog, SecurityLog, OrderDraft`
   - ⚠ 누락 시 autogenerate가 OrderDraft를 인식하지 못함
3. **Alembic 마이그레이션 생성**
   - 명령: `alembic revision --autogenerate -m "add order_drafts table"`
   - 생성 파일: `migrations/versions/XXXX_add_order_drafts_table.py`
   - 수동 검토: 마이그레이션 컬럼 패턴은 `migrations/versions/2fa571e611d9_*.py` 참조. JSONB는 `postgresql.JSONB()` 직접 사용 (`JSONColumn` 래퍼 X), `server_default=sa.text('now()')` for timestamps
   - `downgrade()`에 `op.drop_table('order_drafts')` 명시
4. **CRUD 통합 테스트 신규 `tests/domains/test_order_draft_model.py`**
   - 패턴: `tests/conftest.py:7`의 SQLite in-memory + `app` fixture 사용
   - 케이스: 신규 draft(`order_id=None`) 생성, 수정 draft(`order_id=<order.id>`) 생성, payload JSONB 라운드트립(deepcopy 검증), `(user_id, draft_key)` unique 충돌, `expires_at` 인덱스 사용 확인, user 삭제 시 CASCADE. SQLite 테스트에서는 FK cascade 검증 전 `PRAGMA foreign_keys=ON`을 명시.

**파일**
- 수정: `models.py` (말미 ~30줄 추가)
- 수정: `migrations/env.py:29` (1줄)
- 신규: `migrations/versions/XXXX_add_order_drafts_table.py`
- 신규: `tests/domains/test_order_draft_model.py`

**검증**
- [ ] `alembic upgrade head` 통과 (Railway DB 또는 로컬 PostgreSQL)
- [ ] `alembic downgrade -1` → `alembic upgrade head` 라운드트립 통과
- [ ] `pytest tests/domains/test_order_draft_model.py -v` 통과 (≥ 5 케이스)
- [ ] `python -c "import app; print('APP_OK')"` 통과
- [ ] `pytest tests/ -q` 회귀 0

**위험**
- Alembic 충돌(병행 PR) — 완화: P0 시작 전 단일 PR로 머지
- JSONColumn vs postgresql.JSONB 혼용 — 완화: 모델은 JSONColumn, 마이그레이션은 postgresql.JSONB (기존 컨벤션)
- `env.py:29` import 누락 — 완화: autogenerate 직후 `git diff migrations/versions/` 로 OrderDraft 컬럼이 모두 보이는지 확인

**추정**: 4h

---

#### P0-00C. OrderDraft cleanup cron + Railway Cron Service

**의존**: P0-00B (OrderDraft 모델 필요)

**명세**: 만료 OrderDraft daily 02:00 삭제. 기존 RQ 워커와 분리된 **Railway Cron Service**로 독립 실행.

**구현 단계**
1. **신규 디렉토리 `tools/cron/` 생성** (현재 없음)
2. **신규 `tools/cron/__init__.py`** (빈 파일, Python package)
3. **신규 `tools/cron/cleanup_order_drafts.py`**
   - DB 세션 패턴 참고: `scripts/maintenance/backfill_erp_stage_updated_at.py:22-86` (`app.app_context()` + `get_db()`)
   - 로거 패턴 참고: `workers/sketchup_parser_worker.py:62-70` (`logging.getLogger("cleanup_order_drafts")`)
   - dry-run 패턴: `--execute`가 없으면 default dry-run. `--dry-run`은 명시적 no-op alias로 허용. `--execute`가 있을 때만 삭제 수행 (`scripts/maintenance/backfill_erp_stage_updated_at.py:32` 패턴)
   - 핵심 쿼리: `db.query(OrderDraft).filter(OrderDraft.expires_at < datetime.datetime.now()).delete(synchronize_session=False)`
   - 로그 출력: `[cleanup_order_drafts] mode=dry-run|execute scanned=N deleted=M elapsed=Xs`
   - exit code: 성공 0, 예외 1 (Railway가 실패 알람용으로 사용)
4. **신규 `railway-cron.toml`** (Railway Cron Service 별도 등록)
   ```toml
   [build]
   builder = "nixpacks"
   [deploy]
   startCommand = "python tools/cron/cleanup_order_drafts.py --execute"
   cronSchedule = "0 17 * * *"   # UTC 17:00 = KST 02:00
   ```
   - Railway 대시보드에서 신규 서비스 생성 → Config Path: `railway-cron.toml` 지정
   - 환경변수: 기존 Worker와 동일 (`DATABASE_URL`, `SECRET_KEY` 등) 공유

**파일**
- 신규: `tools/cron/__init__.py`
- 신규: `tools/cron/cleanup_order_drafts.py`
- 신규: `railway-cron.toml`
- 신규: `tests/domains/test_cleanup_order_drafts.py` (dry-run 모드만 단위 테스트, fixture로 만료/미만료 draft 각 1개 생성 후 카운트 검증)

**검증**
- [ ] `python tools/cron/cleanup_order_drafts.py --dry-run` 로컬에서 로그 출력 확인 (DB 영향 0)
- [ ] `pytest tests/domains/test_cleanup_order_drafts.py -v` 통과
- [ ] Railway Cron Service 등록 후 다음날 02:00 첫 실행 로그에 `mode=execute scanned=N deleted=M` 확인
- [ ] 실 deleted 카운트 + DB 잔여 draft count 합 = 실행 전 total count

**위험**
- Railway Cron Service 미존재(아직 등록 안 됨) — 완화: railway-cron.toml 작성 후 사용자가 Railway 대시보드에서 신규 서비스 생성 + Config Path 설정(수동 1회)
- KST/UTC 시간대 혼동 — 완화: cronSchedule 옆에 주석으로 KST 환산 명시
- 대량 삭제 시 DB lock — 완화: `synchronize_session=False` + 1만건/배치 (현 단계 트래픽 가정상 불필요, P1 단계 재평가)

**추정**: 2h (cron + 테스트)

---

#### P0-00D. Playwright 시각 회귀 baseline (pytest-playwright)

**의존**: P0-00A (default false 상태에서 캡처). 가능 시 P0-00B 후 (DB 스키마 안정화)

**명세**: 모바일 3 viewport × 라이트/다크 = 6장 baseline. CI에서 매 PR 자동 diff. 다크모드는 현재 앱 미구현 → CSS 강제 주입(A안).

**구현 단계**
1. **`requirements.txt`에 추가**
   ```
   pytest-playwright==0.5.2
   ```
   - 설치 후 `playwright install chromium --with-deps` 1회 실행 필요 (CI에서도). PNG diff는 기존 의존성 `Pillow==10.1.0` 사용.
2. **신규 `tests/visual/__init__.py`** (빈)
3. **신규 `tests/visual/conftest.py`**
   - `pytest_addoption`으로 `--update-snapshots` bool option 등록. baseline 없거나 옵션이 true이면 baseline PNG 생성, 아니면 비교.
   - visual 전용 DB: pytest 시작 전에 `DATABASE_URL=sqlite:///tests/visual/visual_local.sqlite` 같은 **file-backed SQLite**를 주입. `sqlite:///:memory:` 금지(서버 thread와 test thread가 다른 connection을 잡으면 테이블/로그인 데이터가 안 보임).
   - root `tests/conftest.py`가 visual conftest보다 먼저 로드되므로, `tests/conftest.py:7`을 `os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")`로 조정해 사전 주입 env를 보존.
   - `live_server` fixture: file-backed SQLite에 `Base.metadata.create_all(bind=engine)` + admin test user seed 후 별도 thread에서 Flask `app.run(port=5001, use_reloader=False)` 기동
   - `dark_mode_page` fixture: page에 `page.add_init_script("document.documentElement.setAttribute('data-bs-theme', 'dark')")` 주입 (A안: CSS 강제 — 현재 앱 다크모드 미구현 회피)
4. **신규 `tests/visual/test_visual_regression.py`**
   - 캡처 대상 6장 (URL × viewport × theme 명시):

| # | URL | viewport | theme | 파일명 |
|---|---|---|---|---|
| 1 | `/` (`order_pages.index`) | 320×568 | light | `orders_320_light.png` |
| 2 | `/` (`order_pages.index`) | 320×568 | dark | `orders_320_dark.png` |
| 3 | `/` (`order_pages.index`) | 390×844 | light | `orders_390_light.png` |
| 4 | `/` (`order_pages.index`) | 390×844 | dark | `orders_390_dark.png` |
| 5 | `/` (`order_pages.index`) | 767×1024 | light | `orders_767_light.png` |
| 6 | `/` (`order_pages.index`) | 767×1024 | dark | `orders_767_dark.png` |

   - ⚠ URL은 단일(`/`)로 통일 — `foms/web/orders/listing.py`의 주문 목록 HTML route. `login_required`가 있으므로 visual fixture에서 admin test user 생성 후 `/login` POST를 먼저 수행.
   - 캡처 함수: `page.screenshot(path=baseline_dir / filename, full_page=True)`
   - 비교: `Pillow` 기반 자체 helper로 baseline PNG와 현재 PNG pixel diff 비율 계산(threshold=0.001 = 0.1%). Python `pytest-playwright`의 screenshot matcher에 의존하지 않음. helper는 `--update-snapshots` 옵션과 연동.
   - 최초 실행: baseline 없으면 자동 생성, 이후 실행은 비교
5. **신규 `tests/visual/baseline/` 디렉토리** (gitignore 제외 — 추적 필수, PNG 6장)
   - 로컬에서 PowerShell 기준 `$env:DATABASE_URL='sqlite:///tests/visual/visual_local.sqlite'; pytest tests/visual/ --update-snapshots` 1회 실행 → 6장 생성 → git add
6. **`.github/workflows/ci.yml`에 visual job 추가** (단, `test` job 통과 후 직렬 실행)
   - 위치: 현재 `test` job 아래 `visual` job 신설, `needs: test`
   - 핵심 step: `playwright install chromium --with-deps` + `pytest tests/visual/ -v`
   - env: `DATABASE_URL=sqlite:///tests/visual/visual_ci.sqlite`, `SECRET_KEY=ci-secret-key`, `FLASK_ENV=testing`, `ERP_MOBILE_V2_ENABLED=false` (cohort 미진입 = 기존 UI baseline)

**파일**
- 수정: `requirements.txt` (1줄 추가)
- 수정: `tests/conftest.py` (`DATABASE_URL` 기본값을 `setdefault`로 변경해 visual file-backed SQLite 허용)
- 신규: `tests/visual/__init__.py`, `tests/visual/conftest.py`, `tests/visual/test_visual_regression.py`
- 신규: `tests/visual/baseline/*.png` (6장)
- 수정: `.github/workflows/ci.yml` (visual job 추가)

**검증**
- [ ] 로컬 `$env:DATABASE_URL='sqlite:///tests/visual/visual_local.sqlite'; pytest tests/visual/ -v` 통과 (baseline 비교)
- [ ] baseline 6장 파일 존재 + git 추적
- [ ] CI에서 visual job 통과 (PR diff < 0.1%)
- [ ] cohort 비활성(기존 UI) 상태 baseline 확인 — 새 셸 활성 후 의도된 diff는 P0-01에서 baseline 갱신

**위험**
- pytest-playwright 첫 설치 실패(CI Chromium 의존성) — 완화: `--with-deps` 플래그 사용, Ubuntu 22.04 runner 명시
- 다크모드 미구현 → A안 CSS 강제로 dark token 미적용 영역은 light와 동일 → 사실상 5장 의미 baseline + 1장 동일 — 수용 가능(P0-07 디자인 토큰 v2 도입 후 진짜 dark baseline 갱신)
- 캡처 비결정성(폰트 로딩, animation) — 완화: `wait_until="networkidle"` + `prefers-reduced-motion: reduce` 강제

**추정**: 3h (설치 + 캡처 + CI)

---

#### P0-00E. SSOT lint 가드 ✅ **완료**

`tools/design/ssot_lint.py` + `tests/harness/test_design_ssot_lint.py` + `.github/workflows/ci.yml:30` step 등록 완료. 8개 패턴 범주: 구 P0 PR 개수 표현, 구 전체 PR 수 표현, 구 컴포넌트 개수 표현, 구 컴포넌트 범위 표현, 구 산출물 개수 표현, 구 shell flag 활성화 방식, 단일 환경변수 활성화 표현, 구 결함 개수 표현.

검증 통과: `python tools/design/ssot_lint.py docs/design` → SSOT lint passed: 13 files scanned. `pytest tests/harness/test_design_ssot_lint.py -q` → 4 passed.

---

**P0-00 총 추정**: 12h (P0-00A 3h + P0-00B 4h + P0-00C 2h + P0-00D 3h + P0-00E 완료). P0-01~07 합계 46h에 **추가**. P0 총 시간은 **58h ≈ 7 작업일** 유지(SSOT envelope).

**병렬 실행 가능 매트릭스**

| sub-PR | 의존 | 병렬 그룹 |
|---|---|---|
| P0-00A | 없음 | 그룹 1 (즉시) |
| P0-00B | 없음 | 그룹 1 (즉시) |
| P0-00C | P0-00B | 그룹 2 (B 완료 후) |
| P0-00D | P0-00A (권장) | 그룹 2 (A 완료 후) |
| P0-00E | 완료 ✅ | — |

2 agent 병렬: A(3h), B(4h) 동시 시작 → A 완료 시 D(3h) 시작, B 완료 시 C(2h) 시작. 직렬 합 12h, 병렬 critical path ≈ 6h(+리뷰 buffer 1h).

---

### PR P0-01. ERP_MOBILE_V2 활성화 + 충돌 해소

**명세** (cohort 점진 출시)
- `ERP_MOBILE_V2_ENABLED` 환경변수 **기본값 `false` 유지** (회귀 안전).
- Railway 환경변수만 `true` 설정. cohort 단위 점진 출시:
  - Day 1: 안중훈씨 (현장 영업) 단독 활성화 (`user_id == X`)
  - Day 3: 사무실 보조 5명 추가
  - Day 7: 전체 사용자
- 글로벌 `navbar-expand-md`(768) + ERP shell(992) 동시 활성 충돌 영역(768~991px) 해소.
- 모바일·태블릿에서 글로벌 nav 완전 숨김. ERP 셸이 단일 진입점.
- cohort 토글은 `foms/services/feature_flags.py` (§부록 참조) 의 `is_enabled_for_user()`로 제어.

**파일**
- 신규: `foms/services/feature_flags.py` (`is_enabled_for_user(flag, user_id, cohort_key=None)` 헬퍼)
- 수정: `foms/services/context_processors.py:85` (cohort 체크로 전환, 기본값은 false 유지)
- 수정: `templates/partials/shared/layout_nav.html:148` (모바일 visibility 조건)
- 신규: `static/css/foundation/erp-pro/13-foms-shell-bridge.css` (충돌 영역 룰)
- 수정: `templates/partials/shared/layout_nav.html:47` (인라인 style 위반 제거)
- 신규: Railway env `FOMS_V3_SHELL_COHORT` = `"3,17,42"` (user id 목록) — Day 1 시작값

**검증** (Acceptance Criteria)
- [ ] 320 / 390 / 768 / 1024 / 1280 / 1920px 5종 viewport에서 nav 중복 표시 없음
- [ ] cohort에 포함된 user는 새 셸, 미포함 user는 기존 UI (회귀 0)
- [ ] **Playwright 시각 회귀 baseline 6장 캡처** (모바일/태블릿/데스크톱 × 라이트/다크) + diff < 0.1%
- [ ] `python -c "import app; print('APP_OK')"` 통과
- [ ] `pytest tests/` 통과
- [x] **KPI 베이스라인 측정 시작**: `static/js/foms/rum-baseline.js` + `foms/api/foms_rum.py` → Railway structured logs (`FOMS_RUM_BASELINE_ENABLED`, default true)

**위험**
- cohort 토글 누락 시 외부 사용자 영향 — 완화: feature flag 통합 테스트 1개 필수
- 셸 활성화 사용자 화면이 비활성 사용자와 너무 달라 혼란 — 완화: 사용자 cohort 인터뷰

**추정**: 4시간 (Day 1 활성화) + cohort 추가 모니터링 2일

---

### PR P0-02. 도면 작업실 모바일 카드 **audit + gap patch**

> v1.0 명세 정정: 도면 모바일 카드는 **이미 존재**한다 (`workbench_dashboard_body.html:314` `erp-drawing-mobile-list`). 신규 구현이 아니라 audit + gap 보완.

**명세**
- 기존 `erp-drawing-mobile-list` (line 314~393) 정보 밀도·접근성 audit:
  - 표시 정보: 고객명·자가실측 배지·#ID·담당·상태 배지·다음 액션·최근 이벤트·대상 번호·파일 카운트·미확인 카운트·SLA 배지·내 할 일·담당자 변경·작업 열기 (충분)
  - 갭: ① 도면 thumbnail 16:9 카드 상단 부재 (현재 텍스트 chip만), ② 모바일 필터 offcanvas 부재 (AS 패턴 참고), ③ swipe action 부재 (P2로 미룸)
- v1.1 디자인 시스템(`--foms-*`) 적용은 P1-06 alias bridge로 후속 처리

**파일**
- **수정** (in-place): `templates/drawing/partials/workbench_dashboard_body.html:314-393` (thumbnail block 추가)
- 신규: `templates/drawing/partials/_mobile_filter_drawer.html` (AS `as_mobile_controls.html` 패턴 차용)
- 수정: `foms/api/drawing/` 디렉토리 내 기존 endpoint에 thumbnail_url 필드 추가 (또는 별도 모듈 신설)
- 신규: `static/css/components/foms-drawing-mobile-card.css` (thumbnail · 갭 보완만)

**검증**
- [ ] 기존 카드의 모든 정보가 그대로 표시됨 (회귀 0)
- [ ] 도면 thumbnail 표시 (없으면 placeholder)
- [ ] 모바일 필터 offcanvas 동작
- [ ] Playwright 시각 회귀 통과

**위험**
- 기존 카드 in-place 변경 — 회귀 가능. 완화: feature flag `FOMS_V3_DRAWING_THUMB_ENABLED` 별도 추가

**추정**: 1일 (v1.0 1.5일에서 단축)

---

### PR P0-03. AS 대시보드 모바일 카드 **audit + gap patch**

> v1.0 명세 정정: AS 모바일 카드도 **이미 존재** (`as_dashboard_body.html:364` `erp-pro-order-cards d-md-none`).

**명세**
- 기존 `erp-pro-order-card` 활용:
  - 표시 정보: #ID·상태 배지·고객명·자가실측·전화·시공자·AS 접수일·AS 방문일(인라인 date)·미결 토글 (충분)
  - 갭: ① 단계 색 배지가 v1.1 표준(`foms-stage-badge--cs`)과 불일치, ② 검색·필터(`as_mobile_controls.html`)와 카드 분리됨, ③ 항목별 첨부 썸네일 부재
- AS 접수 모달 자체는 P0-05에서 별도 처리

**파일**
- 수정 (in-place): `templates/cs/partials/as_dashboard_body.html:364-` (배지 표준화 + 첨부 썸네일 추가)
- 수정: `templates/cs/partials/as_mobile_controls.html` (검색·필터 → 카드 sticky 헤더로 통합)
- 신규: `static/css/components/foms-as-mobile-card.css` (갭 보완)

**검증**
- [ ] 기존 정보 유지 + 단계 색 배지 적용
- [ ] 영업·배송·미완료·완료 4탭 fragment 갱신 정상
- [ ] Playwright 회귀

**추정**: 0.5일 (v1.0 1.5일에서 단축)

---

### PR P0-04. 시공 대시보드 모바일 카드 **audit + gap patch**

> v1.0 명세 정정: 시공 모바일 카드도 **이미 존재** (`templates/construction/partials/dashboard_body.html:121` 인근에 모바일 큐 구현됨).

**명세**
- 기존 시공 모바일 큐 audit 후 갭 보완:
  - 권한 분리 (시공팀은 출고·시공만 visible) 동작 검증
  - 단계 색 배지 표준화
  - 도면·실측 사진 첨부 그리드 (현장에서 도면 확인 시나리오 S3)

**파일**
- 수정 (in-place): `templates/construction/partials/dashboard_body.html:121` 인근
- 신규: `static/css/components/foms-construction-mobile-card.css`

**검증**
- [ ] 시공팀 계정 로그인 시 권한 제한 동작
- [ ] 도면·사진 썸네일 표시
- [ ] Playwright 회귀

**추정**: 0.5일 (v1.0 1일에서 단축)

---

### PR P0-05. 카메라 직접 캡처 + AS 모달 재설계

**명세**
- 모든 `<input type="file" accept="image/*">`에 `capture="environment"` 자동 부착.
- AS 접수 모달의 paste-중심 UX → 카메라 우선 + paste 보조 역전.
- 모바일 사용자 80% 작동 시작.

**파일**
- 수정: `static/js/orders/erp-order-shared.js:728,2665-2733` (capture 속성 + AS 모달 마크업)
- 수정: `templates/orders/partials/erp_order_tab.html:351-357` (file input capture + 힌트 문구)
- 수정: `templates/orders/partials/edit_order_body.html:485`
- 수정: `templates/orders/add_order.html` (file input)
- 신규: `static/js/foms/photo-capture.js` (C12 컴포넌트 초안)

**검증**
- 안드로이드 Chrome / iOS Safari 실기기에서 카메라 다이얼로그 즉시 호출
- 데스크톱 Chrome에서 paste 동작 유지
- AS 모달 mobile width(390px)에서 sticky bottom CTA + 카메라 우선

**위험**
- 일부 PC 사용자가 paste 사라졌다고 오인 가능 → 데스크톱에서는 paste 버튼 visible 유지
- iOS Safari capture 동작 호환성 (15+ 지원)

**추정**: 1일

---

### PR P0-06. 폼 sticky bottom CTA + 터치 타깃 보정

**명세**
- `add_order.html` / `edit_order_body.html`의 저장/취소 버튼이 페이지 최하단 → **sticky bottom**.
- 폼 컨테이너에 `.foms-page-form` 클래스 부여 → `.erp-pro` 스코프 누락된 44px 룰 적용.
- 키보드 visible 시 visual viewport API로 sticky bar 위치 보정.

**파일**
- 수정: `templates/orders/add_order.html:357` (action bar sticky)
- 수정: `templates/orders/partials/edit_order_body.html:432`
- 신규: `static/css/components/foms-sticky-action-bar.css`
- 신규: `static/js/foms/visual-viewport.js`
- 수정: `static/css/foundation/erp-pro/09-mobile-erp-optimization.css:15` (`.foms-page-form` 추가)

**검증**
- 폼 페이지 모바일에서 키보드 올라와도 저장 버튼 visible
- 모든 input/button 44px 이상 (Lighthouse audit)
- 체크박스 터치 타깃 → wrapper로 확장 (44px clickable area)

**추정**: 1일

---

### PR P0-07. 다크모드 1차 토큰 (시각 회귀 방지)

**명세**
- `06-mobile-print-utilities.css:80`의 다크모드 tech-debt 시작.
- 신규 `--foms-*` 토큰 시스템 도입 + light/dark 스위치.
- `data-theme` 속성 + 사용자 설정 저장 (localStorage + `prefers-color-scheme`).

**파일**
- 신규: `static/css/foundation/foms-tokens.css` (단일 토큰 파일)
- 수정: `templates/partials/shared/layout_head.html` (theme 초기화 스크립트)
- 신규: `static/js/foms/theme.js`
- 신규: `templates/partials/shared/foms_theme_toggle.html` (드로어 내부)

**검증**
- `data-theme="dark"` 토글 시 셸·카드·폼 정상 다크 전환
- `prefers-color-scheme: dark` 자동 감지
- 사용자 명시 선택 시 localStorage 보존

**위험**
- 기존 `--erp-*` / `--wam-*` 토큰 잔존 — 1차에서는 신규 컴포넌트만 적용. P1에서 일괄 마이그레이션.

**추정**: 1일

---

### P0 총괄 (v1.1 보정, 2026-05-29 갱신)

| PR | v1.0 추정 | v1.1 보정 | 합계 |
|---|---|---|---|
| **P0-00 Foundation** (feature_flags + OrderDraft + cleanup worker + Playwright baseline) | — | **12h** (신규) | 12h |
| P0-01 cohort rollout + 충돌 해소 | 4h | 6h | 18h |
| P0-02 도면 카드 audit + gap patch | 12h | **8h** | 26h |
| P0-03 AS 카드 audit + gap patch | 12h | **4h** | 30h |
| P0-04 시공 카드 audit + gap patch | 8h | **4h** | 34h |
| P0-05 카메라 + AS 재설계 | 8h | 8h | 42h |
| P0-06 sticky CTA + 터치 | 8h | 8h | 50h |
| P0-07 다크모드 1차 (토큰 alias bridge) | 8h | 8h | 58h |
| **합계** | 60h | **58h ≈ 7 작업일** | |

권장 실행 순서: **00** (선행, 단일 PR) → 01 → (02·03·04 병렬) → 05 → 06 → 07. P0-00이 없으면 후속 PR이 미정의 기반에 의존하므로 반드시 우선.

---

## P1 — 단기 (2~4주차)

> 사용자 6대 요구 직접 대응. 핵심 UX 확장.

**진행 현황**
- ✅ **P1-01** Bottom nav 배지 — `context_processors.py:156-167`, `dashboard_counts.py`, `foms-bottom-nav.css`
- ✅ **P1-02** 검색 오버레이 — `foms/api/foms_search.py`, `foms_unified_search.py`, `foms_search_overlay.html`
- ✅ **P1-03** 신규 주문 마법사 — `foms/api/erp_order_draft.py`, `order_draft_service.py`, `templates/orders/wizard/`, `draft.js`/`wizard.js`
- ✅ **P1-04** 인라인 편집 — `erp_orders_structured.py` PATCH `/structured/fields`, `inline-edit.js`, `foms-inline-edit.css`
- ✅ **P1-05** 태블릿 split-view — `foms_split_shell.html`, `foms-split-view.css`, `split-shell.js`, `dashboard.py:737-744`
- ✅ **P1-06** 토큰 alias bridge — `foms-tokens.css` import + `--foms-bridge-erp-*` (legacy `--erp-*` literal 유지, 회귀 0)
- ✅ **P1-07** KV row macro — `templates/macros/foms_kv.html`, `foms-kv-row.css`, `channel/wam/_kv_list.html` alias

### PR P1-01. Bottom Nav 미처리 배지

**명세**
- Bottom nav 5탭에 stage별 미처리 건수 배지.
- 카운트 캐싱 (Redis 또는 in-memory, 30초 TTL).

**파일**
- 수정: `foms/services/context_processors.py` (`inject_foms_nav_badges`)
- 신규: `services/dashboard_counts.py` (stage_counts 함수)
- 수정: `templates/partials/shared/erp_mobile_bottom_nav.html`
- 신규: `static/css/components/foms-bottom-nav.css`

**검증**
- 로그인 후 5탭 배지 표시
- 주문 단계 변경 후 30초 내 배지 업데이트
- 페이지 로드 시간 < 100ms 영향

**추정**: 1일

---

### PR P1-02. 검색 풀스크린 오버레이

**명세**
- 헤더 검색 아이콘 탭 → 풀스크린 dialog.
- HTMX `hx-trigger="input delay:200ms"` 자동완성.
- 고객·주문·도면 3개 그룹 탭.
- 최근 검색 5건 localStorage.

**파일**
- 신규: `templates/partials/shared/foms_search_overlay.html`
- 수정: `foms/api/erp_orders_blueprint.py` 또는 신규 `foms/api/search.py` (통합 검색 endpoint)
- 신규: `static/css/components/foms-search-overlay.css`
- 신규: `static/js/foms/search.js`

**검증**
- 검색 응답 200ms 이내 (전화번호 hash index)
- 한글 자모 분리 검색 ("ㄱㅁㅇ" → "고명옥")
- 키보드 네비게이션 (↑↓ Enter)

**추정**: 2일

---

### PR P1-03. erporder 마법사 4-step + 자동저장

**명세** (v1.1 OrderDraft 계약 통합)
- 신규 주문 작성 흐름을 4-step wizard로 분리 (목업: `mobile-wizard-new-order.html`).
- 자동저장: input 1000ms debounce + blur 즉시 + `sendBeacon` (페이지 unload) + 5분 idle safety
- 복귀 시 토스트로 복구 제안. 충돌(409) 시 다이얼로그: "내 변경 / 다른 기기 / 병합"
- erporder 12필드 매핑: product_name / spec_rows[] (W·D·H 분리, 다중) / internal / color / option_detail / handle / misc / price / measurement_date / construction_date / extra_input / attachments[]

**OrderDraft 모델** (`models.py` 직접 확장 — P0-00B에서 생성, `foms/models/order_draft.py` 별도 파일 금지)
```python
class OrderDraft(Base):
    __tablename__ = 'order_drafts'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    order_id = Column(Integer, ForeignKey('orders.id', ondelete='CASCADE'), nullable=True, index=True)
    draft_key = Column(String(64), nullable=False)  # 'new.<uuid>' | 'edit.<order_id>'
    step = Column(Integer, nullable=False, default=1)
    payload = Column(JSONColumn, nullable=False, default=dict)  # draft_v1 schema (§부록 B)
    schema_version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, default=datetime.datetime.now)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)
    expires_at = Column(DateTime, nullable=False, index=True)

    __table_args__ = (UniqueConstraint('user_id', 'draft_key', name='uq_order_drafts_user_key'),)
```

**API 계약**

| Method | Path | 용도 | 응답 |
|---|---|---|---|
| `GET` | `/api/erp/order-draft?key=...` | 복귀 시 draft 조회 | `{success, draft: {payload, updated_at} | null}` |
| `PUT` | `/api/erp/order-draft` (header: `X-If-Match: <updated_at>`) | 자동저장 idempotent | `{success, updated_at}` 또는 `409 {success: false, error: 'CONFLICT', current: ...}` |
| `DELETE` | `/api/erp/order-draft?key=...` | 명시 폐기 (저장 완료 후) | `{success}` |

**TTL · 정리**
- 신규 draft: 7일, 매일 02:00 cron `tools/cron/cleanup_order_drafts.py` (P0-00C Railway Cron Service 재사용)
- 인라인 draft: 24시간
- 저장 완료 → 클라이언트 즉시 DELETE
- 사용자 비활성화 → CASCADE 즉시

**파일**
- 신규: `templates/orders/wizard/{step1_basic,step2_products,step3_schedule,step4_confirm,wizard_shell}.html`
- 신규: `foms/api/erp_order_draft.py` 또는 기존 `foms/api/erp_orders_structured.py` 확장
- 신규: `static/js/foms/wizard.js`, `static/js/foms/draft.js`
- 기존: `models.py`의 `OrderDraft` 모델 (P0-00B 선행 산출물)
- 신규: Alembic 마이그레이션 `migrations/versions/XXXX_add_order_drafts.py`
- 기존: `tools/cron/cleanup_order_drafts.py` + Railway Cron Service (P0-00C 선행 산출물)

**검증**
- [ ] 4-step 전환 시 입력 데이터 유지
- [ ] 페이지 이탈 → 재진입 시 복구 토스트
- [ ] PC + 모바일 동시 편집 → 409 다이얼로그
- [ ] step별 유효성 검증
- [ ] 모바일 키보드 visible 상태에서 다음/이전 버튼 작동
- [ ] cron job dry-run 통과

**위험**
- 기존 `add_order.html` 단일 폼과 병행 — feature flag `FOMS_WIZARD_NEW_ORDER_ENABLED` 점진 출시
- draft 충돌 정책의 사용자 인지 부담 — onboarding 한 줄 가이드

**추정**: 4일 (모델·migration·API·UI 포함)

---

### PR P1-04. 기존 주문 인라인 편집 (실측 시 워크플로우)

**명세** (v1.1 D07 재고 반영 — critical field 명시 저장)
- 수정 화면(`edit_order_body.html`) + 모바일 주문 상세를 인라인 편집 모드로 전환.
- CS 부서 등록 → 실측 시 영업·실측 담당자가 모바일에서 제품 세부 변경.
- **Non-critical field** (색상·옵션·손잡이·기타·내부·메모): tap → focus → blur 시 즉시 PATCH + 토스트 "저장됨"
- **Critical field** (금액·시공일·실측일·고객 연락처·주소): 명시 "저장" 버튼 + undo 5초 토스트 (실수 복구)
- 컴포넌트: C14 `<foms-product-item-accordion>` (다중 항목 + W·D·H 분리 + 펼침/접힘)

**파일**
- 수정: `templates/orders/partials/edit_order_body.html`
- 수정: `templates/orders/partials/erp_order_tab.html` (모바일 진입점 통합)
- 신규: `static/js/foms/inline-edit.js` (debounce + critical field 명시 저장)
- 수정: `foms/api/erp_orders_structured.py` (PATCH endpoint 기존 활용 + If-Match 헤더)
- 신규: `static/css/components/foms-inline-edit.css`

**검증**
- [ ] Non-critical 필드 blur 시 즉시 PATCH + 토스트
- [ ] Critical 필드 명시 저장 버튼 + undo 5초 동작
- [ ] 충돌 감지 (`updated_at` mismatch / 409) → 사용자 선택 다이얼로그
- [ ] structured_data JSONB 수정 시 `copy.deepcopy + flag_modified` 패턴 준수 (CLAUDE.md)
- [ ] 변경 이력 자동 기록

**위험**
- 기존 single-save UX와 다름 — feature flag `FOMS_INLINE_EDIT_ENABLED` 점진 출시
- 완화: 첫 진입 시 onboarding tooltip + critical field 시각적 차별화

**추정**: 3일

---

### PR P1-05. 태블릿 가로 split-view (1024px+)

**명세**
- 태블릿 가로 모드 master-detail split (목업: `tablet-split-view.html`).
- 좌 360px 마스터 리스트 + 우 fluid 상세.
- Bottom nav → 측면 탭(72px) 회전.
- Container query 기반 자동 활성화.

**파일**
- 신규: `templates/partials/shared/foms_split_shell.html`
- 신규: `templates/partials/shared/foms_side_tab.html`
- 신규: `templates/partials/shared/foms_master_list.html`
- 신규: `static/css/foundation/foms-split-view.css`
- 신규: `static/js/foms/split-shell.js` (carded URL 동기화)

**검증**
- 1024px 이상에서 split-view 자동 활성화
- 마스터 카드 클릭 → 우측 상세 fragment swap (HTMX)
- 가로↔세로 회전 시 레이아웃 무손실 전환
- 좌측 카드 활성 상태 visible (left border + bg)

**위험**
- 기존 페이지의 데스크톱 뷰와 별도 — A/B 토글 권장

**추정**: 3일

---

### PR P1-06. 통합 디자인 토큰 alias bridge (D09 재고)

**명세** (v1.1 D09 보정: 전면 치환 → alias bridge 3단계)

**Phase 1 (P0-07, 1주)**: 신규 `--foms-*` 토큰 파일 추가 + 기존 토큰을 alias로 매핑
```css
/* 01-intro-tokens.css */
:root {
  --erp-primary: var(--foms-color-brand-500);  /* alias 추가, 회귀 0 */
  --erp-success: var(--foms-color-success-500);
  ...
}
```

**Phase 2 (P1-06, 본 PR)**: 신규 코드에서 `--foms-*` 직접 사용. 기존 코드는 alias 유지.

**Phase 3 (P2)**: 기존 코드 점진 마이그레이션 (1년 timeline). 사용처별 PR 분할.

**파일**
- 신규: `static/css/foundation/foms-tokens.css` (single source of truth)
- 수정: `static/css/foundation/erp-pro/01-intro-tokens.css` (alias 매핑)
- 수정: `static/css/contexts/channel/tokens.css` (alias 매핑)
- 신규: `tools/design/migrate-tokens.py` (Phase 3용 dry-run 변환 스크립트)
- 신규: `tools/design/token-coverage-report.py` (현재 사용처 보고)

**검증**
- [ ] 시각 회귀 0 (Playwright snapshot diff, P0-01 baseline 대비)
- [ ] Lighthouse contrast audit AA 통과
- [ ] 다크모드 `data-theme="dark"` 토글 시 신규 컴포넌트 정상
- [ ] 기존 페이지 시각적 변화 없음 (alias 동작 확인)

**위험**
- Phase 1 alias 누락 시 부분 스타일 깨짐 — 완화: 토큰 coverage report 자동화
- 다크모드 텍스트 대비 부족 — 완화: alias bridge 시점에 contrast 자동 검증

**추정**: 3일 (Phase 2 본체) + Phase 1은 P0-07에서 흡수

---

### PR P1-07. KV Row macro + 딥링크 통합

**명세**
- WAM 전용 `wam-kv-list` macro → 공용 `foms_kv_row` 매크로 승격.
- `tel:`, `https://map.kakao.com/?q=`, `mailto:`, copy 딥링크 자동.
- 모든 주문 상세·카드에서 사용.

**파일**
- 신규: `templates/macros/foms_kv.html`
- 수정: `templates/channel/wam/_kv_list.html` (deprecated, alias)
- 수정: 주문 상세·카드 템플릿 일괄 (15개 파일)
- 신규: `static/css/components/foms-kv-row.css`

**검증**
- 전화번호 클릭 → 다이얼러
- 주소 클릭 → 카카오맵
- 복사 버튼 → clipboard API + 토스트
- 키보드 접근성 (Tab + Enter)

**추정**: 1.5일

---

### P1 총괄

| PR | 추정 | 합계 |
|---|---|---|
| P1-01 Bottom nav 배지 | 1일 | 1d |
| P1-02 검색 오버레이 | 2일 | 3d |
| P1-03 신규 주문 마법사 | 4일 | 7d |
| P1-04 인라인 편집 | 3일 | 10d |
| P1-05 태블릿 split-view | 3일 | 13d |
| P1-06 토큰 마이그레이션 | 3일 | 16d |
| P1-07 KV row 통합 | 1.5일 | 17.5d |
| **합계** | | **17.5 작업일 ≈ 3.5주** |

### P1 완료 게이트 (2026-05-30)

| 항목 | 결과 |
|---|---|
| PR P1-01~07 코드 | ✅ |
| P0 회귀 | pytest + visual 12 PASS |
| Flag default | wizard/inline/split OFF, mobile v2 cohort |
| UX smoke | `tests/visual/test_p1_mobile_ux_smoke.py` |
| SSOT stale | `ssot_lint.py` PASS |
| mockup/spec/code | C14 accordion · KV 15파일 manifest · split HTMX |

### P1 visual/mockup gate (2026-05-31)

> **Wiring gate와 분리** — 플래그·API·KV macro는 위 게이트; 아래는 mockup DOM/CSS·cohort 가시성만 검증.  
> DoD checklist: `docs/design/P1_VISUAL_DOD.md` (REDESIGN §6).

| 항목 | 결과 |
|---|---|
| C01 `foms_app_shell.html` | ✅ `erp_mobile_shell.html` alias |
| Mockup CSS bundle | ✅ `foms-shell.css` + chip/queue/detail-hero + drawing/as/shipment |
| Dashboard mobile v2 body | ✅ chips(전체·오늘·긴급·미처리·담당)·sort(최신·일정·금액)·urgent/other·mobile_chunk IO·R2 thumbs |
| Mobile order detail route | ✅ `/erp/orders/<id>/mobile` · KV 4섹션 · C07 lightbox · C14 read-only |
| Desktop chrome hide (mobile v2) | ✅ `foms-shell.css` `.erp-pro-header` / `.erp-pro-nav` |
| D09 token alias phase 2 | ✅ `10-erp-mobile-v2-shell.css` `:root` `--foms-*` bridge |
| Wizard deploy gap | ✅ `wizard-attachments.js` + `product-item.js` tracked |
| §6.3 / §6.5 surfaces | ✅ drawing 16:9 gallery + AS camera-first bar (cohort) |
| Structure tests | ✅ `test_p1_mockup_structure.py` + `test_p1_mockup_png_baseline.py` |
| Visibility gate | ✅ `test_p1_mockup_visual_gate.py` |
| Visual regression | ✅ `test_erp_mobile_v2_shell_regression.py` 6 baselines |
| **mockup PNG 390×844** | ⏳ backlog (Playwright vs `docs/design/mockups/`) |
| **Railway cohort 실측** | ⏳ `staging_mobile_v2_smoke.ps1` + 390px browser checklist |

---

## P2 — 중기 (3개월)

> 진화·혁신. 사용자 P3 추가 요구 또는 시장 차별화.

**진행 현황**
- ✅ **P2-01** HTMX vendor + `foms/api/fragment.py` + split master `detail_href`
- ✅ **P2-02** Alpine vendor + `foms_alpine_toast` + `alpine-store.js` + `foms_p2_surface_bundle.html`
- ✅ **P2-03** `static/sw.js` + `sync.js` + `foms/api/foms_offline.py`
- ✅ **P2-04** `lightbox.js` + queue card `data-foms-lightbox-src`
- ✅ **P2-05** `voice-input.js` (ko-KR, search overlay hook)
- ✅ **P2-06** `manifest.json` + `a2hs-prompt.js` + `layout_head` link
- ✅ **P2-07** `swipe-actions.js` + `haptic.js` + queue card swipe attrs
- ✅ **P2-08** `orientation-layout.js` + `foms-orientation-layout.css`

### PR P2-01. HTMX 2.0 + fragment swap (D06 재고: new surface only)

**명세** (v1.1 D06 보정)
- **기존 `erp-shell.js` fragment swap 흐름 변경 없음** — 회귀 회피
- HTMX는 **new surface only** 도입 — P1 신규 페이지(검색 오버레이, wizard, split-view)에만
- Bottom nav 탭 전환은 P3 (별도 큰 작업)까지 기존 방식 유지

**파일**
- 신규: `static/js/vendor/htmx.min.js` (2.0)
- 신규: `templates/partials/shared/htmx_layout.html` (new surface 진입점)
- 수정: `foms/api/erp_orders_blueprint.py` 또는 신규 `foms/api/fragment.py` (fragment endpoint)

**추정**: 5일

### PR P2-02. Alpine.js 도입

**명세**
- 신규 컴포넌트부터 Alpine.js 점진 도입.
- 인라인 상태 관리, 토스트, 모달, 폼 validation.

**추정**: 3일

### PR P2-03. Service Worker 오프라인

**명세**
- 최근 20건 큐 카드 캐시 (stale-while-revalidate).
- 이미지 캐시 (R2 thumbnail).
- 폼 입력 오프라인 큐 → 온라인 시 sync.

**파일**
- 신규: `static/sw.js`
- 신규: `static/manifest.json`
- 신규: `static/js/foms/sync.js`

**추정**: 4일

### PR P2-04. 사진 라이트박스 + pinch-zoom

**명세**
- 도면·사진 클릭 → 풀스크린 라이트박스.
- pinch-zoom (touch + wheel), 회전, 다운로드.
- swipe로 이전/다음 이미지.

**추정**: 3일

### PR P2-05. 음성 입력 (Web Speech API)

**명세**
- 메모·검색 입력에 음성 버튼.
- 한국어 STT 지원.

**추정**: 2일

### PR P2-06. PWA 매니페스트 + 앱 설치

**명세**
- A2HS (Add to Home Screen) 프롬프트.
- 아이콘·스플래시.

**추정**: 1일

### PR P2-07. 햅틱 + swipe action

**명세**
- 카드 swipe → 승인/반려.
- 버튼 press → vibrate 짧게.
- `prefers-reduced-motion` 존중.

**추정**: 2일

### PR P2-08. 자동 회전 감지 + 레이아웃 적응

**명세**
- 태블릿 가로↔세로 회전 즉시 감지.
- split-view ↔ 단일 컬럼 자동 전환.

**추정**: 1일

---

### P2 총괄

| PR | 추정 |
|---|---|
| P2-01 HTMX | 5일 |
| P2-02 Alpine | 3일 |
| P2-03 Service Worker | 4일 |
| P2-04 라이트박스 | 3일 |
| P2-05 음성 | 2일 |
| P2-06 PWA | 1일 |
| P2-07 햅틱 + swipe | 2일 |
| P2-08 회전 감지 | 1일 |
| **합계** | **21일 ≈ 4주** |

### P2 완료 게이트 (2026-05-31)

| 항목 | 결과 |
|---|---|
| PR P2-01~08 코드 | ✅ |
| P0+P1 회귀 | `test_p1_gate.py` + domain pytest PASS |
| `tests/domains/test_p2_gate.py` | 10 tests PASS (P2-01~08 contracts + offline flag + queue API) |
| `tests/domains/test_p2_htmx_fragment.py` | 4 tests PASS (vendor size, split href, fragment body, auth) |
| Visual regression | `tests/visual/` **15** parametrized cases PASS (legacy 6 + ERP v2 6 + P1 UX smoke 3) |
| P2 flag default | `FOMS_OFFLINE_SW_ENABLED` OFF; SW assets ship disabled until ops enable |
| SSOT stale | `python tools/design/ssot_lint.py docs/design` PASS |

---

## P3 — Bottom nav·이력·큐 액션 (코드 게이트 완료)

> P2에서 미룬 bottom-nav HTMX 전환 + 이력 검색 우선 UX + 모바일 큐 swipe API·라이트박스. **new surface / cohort** 원칙 유지.

**진행 현황**
- ✅ **P3-01** Bottom nav HTMX shell — `bottom-nav-shell.js`, `data-bottom-nav-htmx`, `FOMS_BOTTOM_NAV_HTMX_ENABLED`
- ✅ **P3-02** 이력 검색 우선 — `history_dashboard_body.html` sticky `#erp-history-search-q` + `history-mobile.js`
- ✅ **P3-03** 큐 swipe API — `foms/api/foms_queue_actions.py` `POST /api/foms/queue/<id>/action`
- ✅ **P3-04** 이력 첨부 라이트박스 — `history_dashboard_body.html` `data-foms-lightbox-gallery` (P2 `lightbox.js` 재사용)

### PR P3-01. Bottom nav HTMX fragment navigation

**명세**
- ERP mobile shell bottom nav: `data-foms-nav-id` per tab, `navigateBottomNavHtmx` when `FOMS_BOTTOM_NAV_HTMX_ENABLED`.
- 비활성 시 기존 full navigation; 활성 시 fragment swap + `foms:erp-shell-fragment-swapped` chrome sync.
- `erp_mobile_shell.html` exposes `data-bottom-nav-htmx`; script bundled in `foms_p2_surface_bundle.html`.

**파일**
- 수정: `templates/partials/shared/erp_mobile_bottom_nav.html`, `erp_mobile_shell.html`
- 신규: `static/js/foms/bottom-nav-shell.js`
- 수정: `templates/partials/shared/foms_p2_surface_bundle.html`, `foms/services/context_processors.py` (`flag_bottom_nav_htmx`)

**검증**
- [x] `test_p3_gate.py::test_p3_01_*` (assets + flag default OFF)
- [ ] cohort ON + flag ON 실기기 탭 전환 (ops)

**추정**: 2일 (코드 게이트 완료)

---

### PR P3-02. 이력 대시보드 검색 우선 (mobile)

**명세**
- 모바일 이력 shell: sticky 상단 검색 `#erp-history-search-q`, 필터 미적용·빈 목록 시 autofocus (`history-mobile.js`).
- 데스크톱 테이블 뷰 회귀 0.

**파일**
- 수정: `templates/orders/partials/history_dashboard_body.html`
- 신규: `static/js/foms/history-mobile.js`
- 수정: `foms_p2_surface_bundle.html` (script include)

**검증**
- [x] `test_p3_gate.py::test_p3_02_history_search_first_mobile`

**추정**: 1일 (코드 게이트 완료)

---

### PR P3-03. 모바일 큐 swipe action API

**명세**
- 카드 swipe → `approve` / `hold` JSON action; `swipe-actions.js` calls `POST /api/foms/queue/<order_id>/action`.
- Access log 기록; invalid action 400.

**파일**
- 신규: `foms/api/foms_queue_actions.py`
- 수정: `foms/platform/blueprints.py` (register blueprint)
- 수정: `static/js/foms/swipe-actions.js`, `templates/partials/shared/erp_mobile_queue_card.html` (`data-order-id`, `data-foms-swipe-action`)

**검증**
- [x] `test_p3_gate.py::test_p3_03_*`, `test_p3_04_swipe_js_calls_api`

**추정**: 1.5일 (코드 게이트 완료)

---

### PR P3-04. 이력 첨부 라이트박스 갤러리

**명세**
- 이력 모바일 카드 첨부 그리드에 `data-foms-lightbox-gallery` / `data-foms-lightbox-src` (P2-04 `FomsLightbox` 재사용).
- pinch-zoom·갤러리 swipe는 P2 lightbox와 동일 계약.

**파일**
- 수정: `templates/orders/partials/history_dashboard_body.html`

**검증**
- [x] `test_p3_gate.py::test_p3_05_history_lightbox_gallery`

**추정**: 0.5일 (코드 게이트 완료)

---

### P3 총괄

| PR | 추정 | 합계 |
|---|---|---|
| P3-01 Bottom nav HTMX | 2일 | 2d |
| P3-02 이력 검색 우선 | 1일 | 3d |
| P3-03 큐 swipe API | 1.5일 | 4.5d |
| P3-04 이력 라이트박스 | 0.5일 | 5d |
| **합계** | | **5 작업일** |

### P3 완료 게이트 (2026-05-31)

| 항목 | 결과 |
|---|---|
| PR P3-01~04 코드 | ✅ |
| `tests/domains/test_p3_gate.py` | **6** tests PASS |
| `FOMS_BOTTOM_NAV_HTMX_ENABLED` default | OFF (legacy full navigation until ops) |
| P2 lightbox reuse | history gallery attrs + `lightbox.js` contract |
| SSOT stale | `ssot_lint.py` PASS |

---

## 누락 페이지 P0 추가 작업 (선택)

위 7개 외에 다음 페이지의 모바일 카드 누락:
- 출고 (`shipment/partials/dashboard_main.html`) — `erp-mobile-card-table` 적용은 있으나 모바일 전용 필터·검색 부재. 1일.
- 이력 검색 (`orders/partials/history_dashboard_body.html`) — v2 카드 부분만, 검색 우선 화면 필요. 1.5일.

P0 작업 후 곧바로 진행 권장.

---

## 단계별 사용자 검증 (Cohort)

각 P0/P1 단계마다 다음 검증:

1. **P0 종료**: 안중훈씨 7일 사용 일지 + 인터뷰.
2. **P1-03/04 종료**: 사무실 보조 5명 신규 주문 입력 시간 측정 (목표: 5분→2분).
3. **P1-05 종료**: 도면팀 태블릿 가로 사용성 테스트.
4. **P2-01 종료**: Lighthouse mobile 점수 ≥ 90 확인.
5. **P2-03 종료**: 비행기 모드 시뮬레이션 5분 사용 가능 여부.

---

## Feature Flag Matrix (v1.1 확정 + P2/P3)

Rollout flag — 명명 규칙 `FOMS_<기능>_ENABLED` (도메인 prefix `ERP_*`은 v1.0 잔존 호환 유지). 썸네일 3종은 display helper에서 `env_bool` 직접 조회.

| 환경변수 | 기본값 | 토글 시점 | 의존성 |
|---|---|---|---|
| `ERP_MOBILE_V2_ENABLED` | **false 유지** | P0-01 (cohort 점진 출시) | 없음 |
| `FOMS_V3_SHELL_COHORT` | `""` (목록) | P0-01 — Day 1~7 점진 | ERP_MOBILE_V2 의존 |
| `FOMS_DESIGN_TOKENS_V2_ENABLED` | true | P0-07 (alias bridge) | 토큰 alias 유지 |
| `FOMS_WIZARD_NEW_ORDER_ENABLED` | false | P1-03 | OrderDraft 백엔드 필요 |
| `FOMS_INLINE_EDIT_ENABLED` | false | P1-04 | wizard 안정화 후 |
| `FOMS_TABLET_SPLIT_VIEW_ENABLED` | false | P1-05 | tokens v2 필요 |
| `FOMS_V3_DRAWING_THUMB_ENABLED` | false | P0-02 gap patch | drawing workbench mobile |
| `FOMS_V3_AS_THUMB_ENABLED` | false | P0-03 gap patch | AS dashboard mobile |
| `FOMS_V3_CONSTRUCTION_THUMB_ENABLED` | false | P0-04 gap patch | construction dashboard mobile |
| `FOMS_RUM_BASELINE_ENABLED` | **true** | P0-01 KPI | `rum-baseline.js` + `foms/api/foms_rum.py` |
| `FOMS_OFFLINE_SW_ENABLED` | false | P2-03 | Service Worker + `foms_offline` queue |
| `FOMS_BOTTOM_NAV_HTMX_ENABLED` | false | P3-01 | HTMX vendor + ERP mobile v2 cohort |

### 조합 매트릭스 (E2E 검증 필수)

| 시나리오 | MOBILE_V2 | TOKENS_V2 | WIZARD | INLINE | SPLIT |
|---|---|---|---|---|---|
| 현재 (pre P0) | ❌ | ❌ | ❌ | ❌ | ❌ |
| P0 종료 (cohort Day 7) | ✅ | ✅ | ❌ | ❌ | ❌ |
| P1 종료 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 비상 롤백 (wizard 문제) | ✅ | ✅ | ❌ | ✅ | ✅ |
| 부분 롤백 (split 문제) | ✅ | ✅ | ✅ | ✅ | ❌ |

각 조합은 Playwright E2E 시나리오로 검증. P0-01에 matrix 테스트 추가.

### 구현 위치

```python
# foms/services/feature_flags.py (신규)
def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ('true', '1', 'yes', 'y', 'on')

def env_id_list(name: str) -> set[int]:
    raw = os.getenv(name, '')
    return {int(x) for x in raw.split(',') if x.strip().isdigit()}

def is_enabled_for_user(flag: str, user_id: int | None = None, cohort_key: str | None = None) -> bool:
    """
    cohort 기반 점진 출시. 전역 flag가 true여도 cohort가 비어 있으면 비활성.
    예: is_enabled_for_user('ERP_MOBILE_V2_ENABLED', current_user.id, cohort_key='FOMS_V3_SHELL_COHORT')
    """
    enabled_key = flag if flag.endswith('_ENABLED') else f'{flag}_ENABLED'
    if not env_bool(enabled_key):
        return False
    base = flag[:-8] if flag.endswith('_ENABLED') else flag
    cohort = env_id_list(cohort_key or f'{base}_COHORT')
    if not cohort:
        return False
    return user_id is not None and user_id in cohort
```

```python
# foms/services/context_processors.py (수정)
@app.context_processor
def inject_foms_flags():
    current_user = getattr(g, 'current_user', None)
    uid = current_user.id if current_user else None
    return {
        'flag_mobile_v2':  is_enabled_for_user('ERP_MOBILE_V2_ENABLED', uid, cohort_key='FOMS_V3_SHELL_COHORT'),
        'flag_tokens_v2':  env_bool('FOMS_DESIGN_TOKENS_V2_ENABLED', True),
        'flag_wizard':     env_bool('FOMS_WIZARD_NEW_ORDER_ENABLED'),
        'flag_inline':     env_bool('FOMS_INLINE_EDIT_ENABLED'),
        'flag_split_view': env_bool('FOMS_TABLET_SPLIT_VIEW_ENABLED'),
        'flag_rum_baseline': env_bool('FOMS_RUM_BASELINE_ENABLED', True),
        'flag_offline_sw': env_bool('FOMS_OFFLINE_SW_ENABLED'),
        'flag_bottom_nav_htmx': env_bool('FOMS_BOTTOM_NAV_HTMX_ENABLED'),
    }
```

썸네일 3종 (`FOMS_V3_DRAWING_THUMB_ENABLED`, `FOMS_V3_AS_THUMB_ENABLED`, `FOMS_V3_CONSTRUCTION_THUMB_ENABLED`)은 `foms/services/{drawing,as,construction}_dashboard_display.py`에서 `env_bool`로 조회하며 템플릿 context에는 주입하지 않음.

문제 발생 시 cohort에서 user_id 제거 또는 환경변수 OFF로 즉시 롤백. 코드 revert 불필요.

---

## 측정 지표

각 P 단계별 측정:

| 지표 | P0 베이스라인 | P0 목표 | P1 목표 | P2 목표 |
|---|---|---|---|---|
| 모바일 DAU 비율 | 측정 시작 | +20% | +40% | +60% |
| 신규 주문 입력 시간 (모바일) | ~5분 | ~4분 | ~2분 | ~90초 |
| AS 첨부 성공률 (모바일) | ~10% | 80% | 95% | 99% |
| Lighthouse mobile 점수 | ~60 | 75 | 85 | 92+ |
| 페이지 LCP (mobile, p75) | ~3.5s | 2.5s | 2.0s | 1.5s |
| 페이지 INP (p75) | ~250ms | 200ms | 150ms | 100ms |
| 다크모드 사용률 | 0% | 측정 시작 | 측정 | 25%+ |

측정 도구: Railway logs + Web Vitals RUM + 사용자 인터뷰.

---

## 통합 timeline (v1.1)

| 주차 | 작업 | 비고 |
|---|---|---|
| W1 | P0 전체 (**58h**, P0-00 Foundation 포함) | cohort Day 1~7 점진 출시 |
| W2 | P1-01·06·07 (토큰·배지·KV) | 토큰 alias bridge Phase 2 |
| W3 | P1-02·05 (검색·split) | new surface (HTMX 미사용) |
| W4 | P1-03·04 (마법사·인라인) | P0-00 OrderDraft 기반 위에 API·UX 구현 |
| W5~6 | 누락 페이지 + cohort 인터뷰 (안중훈씨 1주 일지) + 버그 fix | KPI 베이스라인 측정 |
| W7~10 | P2 (HTMX·Alpine·SW·라이트박스) | new surface only |
| W11~12 | P2 (음성·PWA·햅틱·회전) + 최종 검증 | NPS·CSAT 설문 |

총 12주 ≈ 3개월. P0 종료 (cohort Day 7) = 사용 가능, P1 종료 = 사용자 6대 요구 충족, P2 종료 = 시장 차별화.

---

## 부록 A. v1.1 변경 이력

본 로드맵은 v1.0 작성 후 외부 LLM 평가·사용자 직접 지적을 받아 v1.1로 흡수됨. 주요 변경:

| 항목 | v1.0 | v1.1 |
|---|---|---|
| P0-01 rollout | 기본값 false→true 일괄 | **cohort 점진 출시 + Playwright baseline 필수** |
| P0-02/03/04 | 모바일 카드 "신규 구현" | **기존 카드 audit + gap patch** (도면 314, AS 364, 시공 121 라인에 이미 존재) |
| P0 총 시간 | 60h | **58h** (P0-00 +12h 포함, 순감 -2h) |
| API 경로 | `apps/api/erp/...` (가짜) | **`foms/api/...`** (실제 등록 경로, `blueprints.py:55` 참조) |
| Feature Flag | 추상 예시 | **5개 flag + 조합 matrix + cohort helper 구현 코드** |
| OrderDraft | "localStorage + sendBeacon" 문장만 | **모델·payload schema·API·If-Match 충돌·TTL·cron** 본문 통합 |
| D06 HTMX | 기존 fragment swap 일부 대체 | **new surface only** (기존 erp-shell.js 변경 없음) |
| D07 인라인 자동저장 | 모든 필드 자동저장 | **critical field 명시 저장 + undo 5초** |
| D09 토큰 단일화 | P1-06 일괄 치환 | **alias bridge 3 phase** (회귀 0) |

## 부록 B. OrderDraft Payload JSON Schema (draft_v1)

P1-03 구현 시 강제. erporder 12필드 + spec_rows 다중 매핑.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["schema_version", "step", "data"],
  "properties": {
    "schema_version": { "const": 1 },
    "step": { "type": "integer", "minimum": 1, "maximum": 4 },
    "data": {
      "type": "object",
      "properties": {
        "customer_name": { "type": "string" },
        "phone": { "type": "string", "pattern": "^[0-9-]+$" },
        "address": { "type": "string" },
        "orderer": { "type": "string" },
        "received_date": { "type": "string", "format": "date" },
        "items": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "product_name": { "type": "string" },
              "spec_rows": {
                "type": "array",
                "items": {
                  "type": "object",
                  "properties": {
                    "spec_width": { "type": "string" },
                    "spec_depth": { "type": "string" },
                    "spec_height": { "type": "string" }
                  }
                }
              },
              "internal": { "type": "string" },
              "color": { "type": "string" },
              "option_detail": { "type": "string" },
              "handle": { "type": "string" },
              "misc": { "type": "string" },
              "price": { "type": "string" },
              "measurement_date": { "type": "string" },
              "construction_date": { "type": "string" },
              "extra_input": { "type": "string" },
              "attachments": {
                "type": "array",
                "items": {
                  "type": "object",
                  "properties": {
                    "tmp_key": { "type": "string" },
                    "filename": { "type": "string" }
                  }
                }
              }
            }
          }
        },
        "schedule": {
          "type": "object",
          "properties": {
            "measurement_date": { "type": "string", "format": "date" },
            "measurement_time": { "type": "string" },
            "construction_date": { "type": "string", "format": "date" },
            "construction_time": { "type": "string" },
            "shipment_date": { "type": "string", "format": "date" },
            "sales_manager_id": { "type": "integer" },
            "construction_manager_id": { "type": "integer" }
          }
        }
      }
    }
  }
}
```
