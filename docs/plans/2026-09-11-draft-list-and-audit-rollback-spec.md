# Spec — 초안 목록 화면 + 감사 로그 rollback 구멍 (2026-09-11)

선행: `docs/plans/2026-09-11-erporder-channel-push-missing-order-ledger.md`
상태: **승인 대기**. 코어 변경(API·Auth 경로)이라 구현 전 승인을 받는다.

---

## T1 — 감사 기록 실패가 호출자의 트랜잭션을 통째로 되감는다

### 현상

`foms/web/auth/routes.py:107-120` `log_access` 의 except 분기가 `db.rollback()` 을 부른다.
이 `db` 는 **호출자의 세션**이다. 감사 행 1건을 못 쓰면 호출자가 쌓아둔 변경이 전부 사라진다.

가장 나쁜 자리는 초안 등록이다(`foms/api/erp_order_draft.py:660-679`):

```
create_order(...)                 # flush 만
promote_draft_attachments(...)    # flush 만
delete_draft(db, uid, draft_key)
log_access(..., auto_commit=False, ...)   # ← 여기서 실패하면 위 셋이 전부 rollback
db.commit()                               # 빈 트랜잭션을 커밋
return {"success": True, "data": {"order_id": new_order.id}}, 200
```

화면은 **200 + order_id** 를 받아 주문 목록으로 이동하는데 DB 에는 주문이 없다.
결과 상태가 2026-09-10 사고의 DB 관측(초안 생존 + 주문 없음)과 구분되지 않는다.
다만 그날 운영 로그에 `[LOG ERROR] SecurityLog 기록 실패` 는 0건이라 **이번 사고의 원인은 아니다.**
호출부는 131곳이고 `auto_commit=False` 로 호출자 트랜잭션에 얹는 자리가 이 구멍에 노출된다.

### 고칠 방향

fail-open 자체는 유지한다(감사 실패가 원 요청을 죽이면 안 된다는 판단은 옳다).
바꾸는 것은 **실패 범위**다 — 감사 행만 되감고 호출자 것은 건드리지 않는다.

```
sp = db.begin_nested()          # SAVEPOINT
try:
    db.add(log); db.flush()
    sp.commit()
except Exception:
    sp.rollback()               # 감사 행만 사라진다
    logger.warning("[LOG ERROR] ...", exc_info=True)
else:
    if auto_commit:
        db.commit()
```

- `auto_commit=True` 경로(감사가 트랜잭션을 소유)는 지금과 같다.
- `auto_commit=False` 경로는 호출자 변경이 살아남는다.
- 바깥 세션 자체가 죽은 경우(연결 끊김)는 savepoint 도 실패한다 — 그때만 지금처럼 넓게 되감고 로그를 남긴다.

### 변경 파일

`foms/web/auth/routes.py` (`log_access` 한 함수). 호출부 131곳 무변경.

### 검증

- 신규 계약: 감사 add 가 터지도록 주입 → ① 호출자가 flush 한 행이 commit 뒤에도 살아 있다
  ② `[LOG ERROR]` 가 남는다 ③ 응답은 여전히 성공(fail-open 유지).
- 음성 대조군: 정상 경로에서 감사 행이 실제로 쓰인다(`auto_commit` 양쪽).
- PG 레인에서 savepoint 동작 확인(`tests/postgres/`). SQLite 는 FK 미강제라 판정 축으로 쓰지 않는다.
- `pre_push_smoke.ps1` + `python -c "import app; print('APP_OK')"`.

---

## T2 — 작성 중인 초안 목록

### 왜

초안은 7일 뒤 조용히 사라지고(`new.*` TTL 7일) 사용자가 스스로 찾을 길이 없다.
초안 라우트는 5개인데(`foms/api/erp_order_draft.py:263·287·418·448·547`) **목록이 없다.**
2026-09-02·09-03 두 건은 그렇게 사라져 복구가 불가능했다.
진입 자체는 이미 지원된다 — `/add?key=<draft_key>&wizard=1&step=<n>`
(`foms/web/orders/listing.py:502-512`).

### API

`GET /api/erp/order-draft/list`

- 게이트: 기존 초안 라우트와 동일(`login_required` + ADMIN/MANAGER/STAFF + `_require_wizard()`).
- 대상: **본인 소유**(`user_id`) · `order_id IS NULL` · `expires_at > now` 만. 최신순, 최대 20건.
- 응답 `{"success": true, "data": {"drafts": [...]}}`, 각 행:
  `draft_key`, `step`, `updated_at`, `expires_at`, `customer_name`, `address`,
  `items_count`, `files_count`, `has_send_history`(발송했는데 등록 안 한 초안 표시용).
- 고객명·주소는 `payload` 에서 뽑되 없으면 `null` — 초안은 어느 칸이든 비어 있을 수 있다.

### 화면

모바일 주문 목록 상단에 **"작성 중인 주문 N건"** 한 줄. 누르면 시트가 열리고 행마다
`고객명 · 단계 n/4 · 마지막 저장 시각 · 만료까지 n일`. 발송 이력이 있는 초안은
**"발송함 · 등록 전"** 배지를 단다(이번 사고 축). 행을 누르면
`/add?key=<draft_key>&wizard=1&step=<step>` 으로 들어가 이어서 쓴다.
N=0 이면 줄 자체를 그리지 않는다.

삭제는 이번 범위에서 **뺀다**(DELETE 라우트는 이미 있지만, 목록에서 지우는 UI 는 오조작 위험이
있어 별건으로 본다).

### 변경 파일

- `foms/api/erp_order_draft.py` — 목록 라우트 1개 추가
- `foms/services/order_draft_service.py` — 목록 조회 함수 1개
- 목록 템플릿 + `static/js/foms/` 시트 JS + `static/css/components/foms-wizard.css`
- 자산 핀 범프

### 검증

- 라우트 계약: 게이트 3종 · 남의 초안 제외 · 만료분 제외 · `order_id` 있는 행 제외 · 응답 모양.
- 화면 계약: N=0 이면 미노출 · 배지 · 링크 형식 · 인라인 스타일 금지(ratchet).
- `node --check` + `tests/domains/test_static_js_syntax.py`
  (`pre_push_smoke` 32개 타깃에 없다 — 2026-09-11 실측).
- `pre_push_smoke.ps1` + `APP_OK`.

---

## 순서

T1 먼저(작고 독립적, 회귀 위험이 큰 자리) → T2. 둘 다 deploy 푸시 → CI green → 승격은 사용자 확인.
