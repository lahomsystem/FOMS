"""DELETE-AXIS: 주문 ``deleted_at`` 저장 규약(naive UTC 고정폭) 계약 테스트.

정본은 :mod:`foms.services.orders.soft_delete` 의 ``_DELETED_AT_FORMAT``
(``%Y-%m-%d %H:%M:%S``, naive UTC)이다. 읽는 쪽(:func:`format_datetime_kst` 의
``assume_utc_if_naive=True``)이 그 규약을 전제하고 +9 시간을 더하므로, 쓰는 자리가
KST 나 컨테이너 로컬 ISO 를 넣으면 화면이 **9시간 미래**를 말하거나 문자열 desc
정렬이 어긋난다(운영 휴지통 308건 중 246건 KST · 28건 ISO ``T`` 실측).

여기서는 두 가지를 고정한다.

1. **인벤토리 게이트** — 주문 ``deleted_at`` 에 값을 쓰는 프로덕션 파일 집합이
   정확히 4개다. 새 파일이 제 규약으로 쓰기 시작하면 빨갛게 된다. 줄 번호는 박지
   않는다(줄밀림 red 방지). 모집단은 ``foms/``·``tools/``·``scripts/`` 전체와
   저장소 루트 최상위 ``*.py`` 다 — 게이트의 뜻이 "쓰는 자리가 늘면 red" 인 이상
   사각이 있으면 안 된다.
2. **동작 계약** — 정본 아닌 세 경로(페이지 일괄 삭제 · 드래프트 폐기 · cron
   draft 정리)가 실제로 저장한 문자열이 정본 형식·정본 기준축인지 라우트/함수를
   태워 확인하고, 읽는 쪽으로 왕복시켜 화면 낱말까지 맞는지 본다.
3. **실행 형태 스모크** — cron 스크립트를 pytest 의 ``sys.path`` 가 아니라 실제
   실행 형태(별도 프로세스)로 돌려 ``ModuleNotFoundError`` 가 없음을 본다.
"""

from __future__ import annotations

import datetime
import json
import os
import pathlib
import re
import subprocess
import sys

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.datetime_kst import format_datetime_kst, now_kst, now_utc_naive
from models import Order, User
from tools.cron.cleanup_order_drafts import run_erp_draft_orders

# 정본 형식: 고정폭 naive UTC. ``T`` 도 마이크로초도 없다.
CANONICAL_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")

# 주문 ``deleted_at`` 에 값을 쓰는 자리를 고르는 정규식 4종.
#   1) ``order.deleted_at = ...`` 속성 대입
#   2) ``setattr(order, 'deleted_at', ...)``
#   3) raw SQL 의 ``deleted_at=:param``
#   4) 스탬프를 만드는 지역 변수 ``deleted_at = ...``
_WRITE_PATTERNS = (
    re.compile(r"\.deleted_at\s*=(?!=)"),
    re.compile(r"setattr\(\s*[A-Za-z_][\w.]*\s*,\s*['\"]deleted_at['\"]"),
    re.compile(r"deleted_at\s*=\s*:"),
    re.compile(r"^\s*deleted_at\s*=(?!=)"),
)

# 다른 축이라 모집단에서 뺀다.
#   * ``attachment.deleted_at`` = ``OrderAttachment.deleted_at``(DateTime 컬럼이라
#     문자열 규약이 아예 없다 — foms/api/files/order_routes.py).
#   * ``entry["deleted_at"]`` / ``locked["deleted_at"]`` = ``structured_data`` 안의
#     ``shipment.as_log[]`` 축(AS 로그 항목의 자기 삭제 표식). dict 키 대입이라 위
#     정규식 1~4 에 애초에 안 걸리지만 왜 뺐는지를 남겨 둔다.
#   * ``= None`` 은 복원(clear)이라 형식 규약과 무관하다
#     (foms/web/orders/trash.py 의 휴지통 복원).
#   * ``deleted_at = Column(...)`` 은 스키마 선언이지 값을 쓰는 자리가 아니다
#     (``models.py`` 의 Order·OrderAttachment 컬럼 정의). 모집단에 저장소 루트
#     최상위 ``*.py`` 를 넣으면서 정규식 4번에 걸리기 시작해 명시적으로 뺀다.
_ATTACHMENT_AXIS_RE = re.compile(r"\battachment\.deleted_at\b")
_CLEAR_RE = re.compile(r"\.deleted_at\s*=\s*None\s*$")
_COLUMN_DECL_RE = re.compile(r"deleted_at\s*=\s*Column\(")

# 일회성 교정 도구(tools/ops/backfill_*.py)는 **파일 집합 게이트에서만** 뺀다.
# 새 삭제 시각을 찍는 자리가 아니라 이미 적힌 값을 정본 형식으로 옮겨 적는
# 자리라서, 늘어나면 안 되는 "쓰는 경로" 모집단과 성격이 다르다. 대신 아래
# 음성 대조군에는 그대로 걸어 둔다 — 교정 도구가 KST/ISO 를 도로 심으면 red.
_BACKFILL_TOOL_PREFIX = "tools/ops/backfill_"

# 음성 대조군: 이 낱말이 쓰기 줄에 하나라도 있으면 규약이 다시 갈라진 것이다.
_FORBIDDEN = ("now_kst(", "datetime.now(", ".isoformat()")

_EXPECTED_WRITERS = {
    "foms/api/erp_orders_structured.py",
    "foms/services/orders/soft_delete.py",
    "foms/web/orders/listing.py",
    "tools/cron/cleanup_order_drafts.py",
}


def _repo_root() -> pathlib.Path:
    """저장소 루트(tests/domains/<file> 기준 2단계 위)."""
    return pathlib.Path(__file__).resolve().parents[2]


def _population(root: pathlib.Path) -> list[pathlib.Path]:
    """게이트 모집단 — ``foms/``·``tools/``·``scripts/`` 전체 + 루트 최상위 ``*.py``.

    ``tests/``·``migrations/``·``docs/`` 는 프로덕션 쓰기 경로가 아니라 뺀다.

    Args:
        root: 저장소 루트.

    Returns:
        훑을 파이썬 파일 경로 목록.
    """
    files: list[pathlib.Path] = []
    for base in ("foms", "tools", "scripts"):
        base_dir = root / base
        if base_dir.is_dir():
            files.extend(sorted(base_dir.rglob("*.py")))
    files.extend(sorted(root.glob("*.py")))
    return files


def _collect_deleted_at_writes() -> dict[str, list[str]]:
    """모집단에서 주문 ``deleted_at`` 에 값을 쓰는 줄을 모은다.

    Returns:
        {저장소 상대경로(posix): [해당 줄 내용, ...]} 매핑.
    """
    root = _repo_root()
    found: dict[str, list[str]] = {}
    for path in _population(root):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if not any(pat.search(line) for pat in _WRITE_PATTERNS):
                continue
            if (
                _ATTACHMENT_AXIS_RE.search(line)
                or _CLEAR_RE.search(line)
                or _COLUMN_DECL_RE.search(line)
            ):
                continue
            rel = path.relative_to(root).as_posix()
            found.setdefault(rel, []).append(stripped)
    return found


class TestDeletedAtWriteInventory:
    """쓰는 자리 전수 게이트(줄 번호 무관)."""

    def test_writer_file_set_is_exactly_four(self) -> None:
        """주문 deleted_at 에 값을 쓰는 파일이 정확히 4개다(새 파일이 늘면 red)."""
        found = _collect_deleted_at_writes()
        writers = {
            rel for rel in found if not rel.startswith(_BACKFILL_TOOL_PREFIX)
        }
        assert writers == _EXPECTED_WRITERS, found

    def test_no_kst_or_iso_on_write_lines(self) -> None:
        """음성 대조군 — 쓰기 줄에 now_kst(·datetime.now(·.isoformat() 이 없다."""
        offenders: list[str] = []
        for rel, lines in _collect_deleted_at_writes().items():
            for line in lines:
                if any(token in line for token in _FORBIDDEN):
                    offenders.append(f"{rel}: {line}")
        assert offenders == [], offenders


# ---------------------------------------------------------------------------
# 동작 계약 — 실제로 저장된 문자열을 본다
# ---------------------------------------------------------------------------
def _make_admin(username: str) -> User:
    """일괄 삭제/드래프트 폐기 권한(ADMIN)을 가진 사용자를 만든다."""
    user = db_session.query(User).filter_by(username=username).first()
    if user is None:
        user = User(
            username=username,
            password=generate_password_hash("admin"),
            role="ADMIN",
            team="CS",
            name="Delete Axis Admin",
        )
        db_session.add(user)
        db_session.commit()
    return user


def _login(client, username: str) -> None:
    """폼 로그인 경유 세션 로그인(role 가드까지 실제로 태운다)."""
    _make_admin(username)
    client.post(
        "/login",
        data={"username": username, "password": "admin"},
        follow_redirects=True,
    )


def _make_order(status: str = "RECEIVED") -> Order:
    """일괄 삭제 대상 주문 1건."""
    order = Order(
        received_date="2026-09-07",
        customer_name="삭제축",
        phone="010-0000-0000",
        address="서울",
        product="침대",
        status=status,
        is_erp_order=True,
        structured_data={"workflow": {"stage": status}},
    )
    db_session.add(order)
    db_session.commit()
    return order


def _assert_canonical_utc_stamp(value: str) -> datetime.datetime:
    """저장된 문자열이 정본 형식이고 기준축이 UTC 임을 확인하고 파싱해 돌려준다.

    Args:
        value: ``Order.deleted_at`` 에 실제로 저장된 값.

    Returns:
        파싱된 naive UTC datetime.
    """
    assert isinstance(value, str), value
    assert "T" not in value, value
    assert CANONICAL_RE.match(value), value
    stamp = datetime.datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    # 기준축이 UTC 다: now_utc_naive() 와 5분 이내.
    assert abs((stamp - now_utc_naive()).total_seconds()) < 300, value
    # KST 가 아니다: now_kst() 벽시계와 9시간 가까이 벌어져 있다.
    kst_wall = now_kst().replace(tzinfo=None)
    assert 8.5 * 3600 < (kst_wall - stamp).total_seconds() < 9.5 * 3600, value
    return stamp


def _assert_reads_back_as_now(value: str) -> None:
    """읽는 쪽으로 왕복하면 지금 KST 벽시계와 같은 낱말이 된다(사용자 증상 회귀 차단).

    Args:
        value: ``Order.deleted_at`` 에 저장된 값.
    """
    rendered = format_datetime_kst(value, "%m-%d %H:%M")
    now = now_kst()
    # 분 경계 깜빡임을 피하려고 ±1분까지 허용한다(9시간 어긋남은 그래도 잡힌다).
    allowed = {
        (now + datetime.timedelta(minutes=delta)).strftime("%m-%d %H:%M")
        for delta in (-1, 0, 1)
    }
    assert rendered in allowed, (rendered, sorted(allowed))


class TestBulkActionDeleteStamp:
    """페이지 일괄 삭제(``POST /bulk_action``)."""

    def test_bulk_delete_writes_canonical_utc(self, client, app) -> None:
        """일괄 삭제가 KST 대신 naive UTC 고정폭을 저장한다(9시간 미래 회귀 차단)."""
        _login(client, "delete_axis_bulk")
        order_id = _make_order().id

        resp = client.post(
            "/bulk_action",
            data={"action": "delete", "selected_order": [str(order_id)]},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303), resp.status_code

        db_session.expire_all()
        order = db_session.get(Order, order_id)
        _assert_canonical_utc_stamp(order.deleted_at)
        _assert_reads_back_as_now(order.deleted_at)


class TestDraftDiscardStamp:
    """드래프트 폐기(``POST /api/orders/erp/draft/discard``)."""

    def test_discard_writes_canonical_utc(self, client, app) -> None:
        """드래프트 폐기가 ISO ``T`` 대신 정본 고정폭을 저장한다."""
        _login(client, "delete_axis_discard")
        structured = {
            "entity_type": "order_structured",
            "schema_version": 1,
            "parties": {"customer": {"name": "폐기대상", "phone": "010-5"}},
            "site": {"address_full": "인천", "address_main": "인천", "address_detail": ""},
            "schedule": {},
            "items": [],
        }
        created = client.post(
            "/api/orders/erp/draft/autosave",
            data=json.dumps({"draft_token": "tok-delete-axis", "structured_data": structured}),
            content_type="application/json",
        )
        order_id = created.get_json()["order_id"]
        assert order_id

        discard = client.post(
            "/api/orders/erp/draft/discard",
            data=json.dumps({"draft_token": "tok-delete-axis"}),
            content_type="application/json",
        )
        assert discard.get_json()["success"] is True

        db_session.expire_all()
        order = db_session.get(Order, order_id)
        _assert_canonical_utc_stamp(order.deleted_at)
        _assert_reads_back_as_now(order.deleted_at)


class TestCronDraftCleanupStamp:
    """48시간 지난 draft 정리 cron(``run_erp_draft_orders``)."""

    def test_cron_soft_delete_writes_canonical_utc(self, app) -> None:
        """cron 이 ISO ``T`` 대신 정본 고정폭을 저장한다(now/threshold 축은 그대로).

        ``now``/``threshold`` 는 ``created_at``/``structured_updated_at``(컨테이너
        로컬 ``datetime.now`` 기본값)과 견주는 선별 기준이라 UTC 로 바꾸지 않았다 —
        여기서는 선별이 여전히 먹는지와 스탬프만 UTC 인지를 함께 본다.
        """
        stale = datetime.datetime.now() - datetime.timedelta(hours=100)
        order = Order(
            received_date="2026-06-01",
            received_time="10:00",
            customer_name="묵은 초안",
            phone="000-0000-0000",
            address="-",
            product="ERP Order",
            status="DRAFT",
            is_erp_order=True,
            structured_data={"meta": {"draft": True}},
            structured_updated_at=stale,
            created_at=stale,
        )
        db_session.add(order)
        db_session.commit()
        order_id = order.id

        scanned, deleted = run_erp_draft_orders(execute=True, session=db_session)
        assert scanned >= 1 and deleted >= 1

        db_session.expire_all()
        refreshed = db_session.get(Order, order_id)
        assert refreshed.status == "DELETED"
        _assert_canonical_utc_stamp(refreshed.deleted_at)
        _assert_reads_back_as_now(refreshed.deleted_at)


class TestCronScriptRunsAsAScript:
    """cron 스크립트는 저장소 루트가 ``sys.path`` 에 없는 채로 돈다."""

    def test_cleanup_order_drafts_has_no_import_error(self) -> None:
        """실제 실행 형태로 한 번 돌려 ``ModuleNotFoundError`` 가 없음을 본다.

        왜 이 스모크가 따로 필요한가: 위 :class:`TestCronDraftCleanupStamp` 는
        pytest 가 저장소 루트를 ``sys.path`` 에 얹은 뒤 함수를 import 해 부른다.
        그래서 이 파일이 ``foms.*`` 를 물어도 초록이다. 실제 Railway cron 은
        ``python tools/cron/cleanup_order_drafts.py`` 라 ``sys.path[0]`` 가
        ``tools/cron`` 이고 저장소 루트가 없다 — 그 형태를 한 번도 재지 않았다.

        ``DATABASE_URL`` 이 없으면 ``main()`` 이 예외를 잡아 exit 1 이므로
        returncode 가 아니라 stderr 문자열로 판정한다.
        """
        env = dict(os.environ)
        # 부모 PYTHONPATH 가 루트를 얹고 있으면 이 스모크가 거짓 초록이 된다.
        env.pop("PYTHONPATH", None)
        env["PYTHONIOENCODING"] = "utf-8"  # Windows cp949 파이프 디코드 사고 방지
        result = subprocess.run(
            [sys.executable, "tools/cron/cleanup_order_drafts.py", "--dry-run"],
            cwd=str(_repo_root()),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=120,
        )

        assert "ModuleNotFoundError" not in (result.stderr or ""), result.stderr
