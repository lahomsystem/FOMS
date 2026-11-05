"""거래명세서 양식 정보 — 공급자(우리) · 공급받는자(협력사) 블록 · 입금 계좌 · 안내 문구(설계서 §5.8).

저장소가 공개라 사업자번호 · 계좌 같은 값은 코드에 두지 않고 SystemSetting 한 줄(:data:`SETTINGS_KEY`)에 둔다. ADMIN 이
관리 화면에서 넣는다. 모양::

    {"supplier": {name, ceo, biz_no, address, biz_type, biz_item, phone, accounts, doc_prefix,
                  pay_deadline, tax_notice, caution},
     "receivers": {"<협력사 id>": {ceo, address, biz_type, biz_item, doc_prefix}}}

공급받는자의 상호 · 등록번호는 협력사 정보(``PartnerOrg.name`` · ``biz_reg_no``)를 그대로 쓴다. 발행한 명세서는 그때 값을
``groups`` 옆 스냅샷으로 갖지 않고 이 값을 읽는다 — 양식 정보는 금액이 아니라서 바뀌면 옛 명세서에도 새 값이 보인다.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from sqlalchemy.orm.attributes import flag_modified

from models import SystemSetting

SETTINGS_KEY = "partner_statement_profile"
DEFAULT_PREFIX = "HD"
DEFAULT_DEADLINE = "출고 전날 16:00"
#: 세금계산서 안내를 비워 두면 쓰는 글(사용자 결정 2026-11-05 — 달마다 한 번).
DEFAULT_TAX_NOTICE = "세금계산서는 달마다 말일 기준으로 한 번에 발행합니다."

#: (이름, 화면 이름, 최대 글자 수, 여러 줄)
SUPPLIER_FIELDS: tuple[tuple[str, str, int, bool], ...] = (
    ("name", "상호", 60, False),
    ("ceo", "성명(대표자)", 30, False),
    ("biz_no", "등록번호", 20, False),
    ("address", "주소", 120, False),
    ("biz_type", "업태", 40, False),
    ("biz_item", "종목", 40, False),
    ("phone", "전화", 30, False),
    ("accounts", "입금 계좌(한 줄에 하나)", 300, True),
    ("doc_prefix", "문서번호 머리(영문 대문자)", 6, False),
    ("pay_deadline", "입금 기한", 40, False),
    ("tax_notice", "세금계산서 안내", 300, True),
    ("caution", "주의 문구", 300, True),
)
RECEIVER_FIELDS: tuple[tuple[str, str, int, bool], ...] = (
    ("ceo", "성명(대표자)", 30, False),
    ("address", "주소", 120, False),
    ("biz_type", "업태", 40, False),
    ("biz_item", "종목", 40, False),
    ("doc_prefix", "이 협력사 문서번호 머리(영문 대문자, 비우면 공급자 것)", 6, False),
)
_PREFIX_RE = re.compile(r"^[A-Z]{1,6}$")


class ProfileError(ValueError):
    """화면에 그대로 보일 수 있는 거부 이유. ``status`` 는 HTTP 코드."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _text(value: Any, limit: int, multiline: bool) -> str:
    text = str(value if value is not None else "")
    if multiline:
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
        return "\n".join(line for line in lines if line)[:limit]
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _clean(raw: Any, fields) -> dict[str, str]:
    raw = raw if isinstance(raw, dict) else {}
    return {name: _text(raw.get(name), limit, multiline) for name, _label, limit, multiline in fields}


def _row(db) -> Optional[SystemSetting]:
    return db.get(SystemSetting, SETTINGS_KEY)


def load_profile(db) -> dict[str, Any]:
    """저장한 양식 정보(없는 칸은 빈 글 · 기본값) + ``version``."""
    row = _row(db)
    value = row.setting_value if row is not None and isinstance(row.setting_value, dict) else {}
    supplier = _clean(value.get("supplier"), SUPPLIER_FIELDS)
    supplier["doc_prefix"] = supplier["doc_prefix"] or DEFAULT_PREFIX
    supplier["pay_deadline"] = supplier["pay_deadline"] or DEFAULT_DEADLINE
    supplier["tax_notice"] = supplier["tax_notice"] or DEFAULT_TAX_NOTICE
    receivers = value.get("receivers") if isinstance(value.get("receivers"), dict) else {}
    return {"supplier": supplier,
            "receivers": {str(k): _clean(v, RECEIVER_FIELDS) for k, v in receivers.items()},
            "version": int(row.version or 1) if row is not None else 0}


def receiver_block(profile: dict[str, Any], org: Any) -> dict[str, str]:
    """공급받는자 블록 — 상호 · 등록번호는 협력사 정보, 나머지는 양식 정보."""
    extra = profile["receivers"].get(str(org.id)) or _clean({}, RECEIVER_FIELDS)
    return {"name": org.name or "", "biz_no": org.biz_reg_no or "", **extra}


def doc_prefix_for(profile: dict[str, Any], org_id: Any) -> str:
    """문서번호 머리 — 협력사마다 정한 것, 없으면 공급자 것(사용자 결정 2026-11-05: 협력사마다 다르게)."""
    own = (profile["receivers"].get(str(org_id)) or {}).get("doc_prefix") or ""
    return own or profile["supplier"]["doc_prefix"]


def save_profile(db, org_id: int, raw: Any, *, base_version: Any) -> tuple[int, list[str]]:
    """공급자 블록 + 이 협력사 공급받는자 블록 저장 → ``(새 version, 바뀐 칸 이름)``. 커밋은 부르는 쪽.

    화면이 본 ``base_version`` 과 지금 version 이 다르면 409(그사이 다른 사람이 저장함).
    """
    raw = raw if isinstance(raw, dict) else {}
    supplier = _clean(raw.get("supplier"), SUPPLIER_FIELDS)
    supplier["doc_prefix"] = supplier["doc_prefix"].upper() or DEFAULT_PREFIX
    if not _PREFIX_RE.match(supplier["doc_prefix"]):
        raise ProfileError("문서번호 머리는 영문 대문자 1~6자로 적어 주세요(예: HD).")
    receiver = _clean(raw.get("receiver"), RECEIVER_FIELDS)
    receiver["doc_prefix"] = receiver["doc_prefix"].upper()
    if receiver["doc_prefix"] and not _PREFIX_RE.match(receiver["doc_prefix"]):
        raise ProfileError("이 협력사 문서번호 머리는 영문 대문자 1~6자로 적어 주세요(예: RD). 공급자 것을 쓰려면 비워 두세요.")
    row = db.query(SystemSetting).filter(SystemSetting.setting_key == SETTINGS_KEY).with_for_update().first()
    current = int(row.version or 1) if row is not None else 0
    try:
        base = int(base_version or 0)
    except (TypeError, ValueError):
        base = -1
    if base != current:
        raise ProfileError("그사이 다른 사람이 양식 정보를 저장했습니다. 화면을 새로 고친 뒤 다시 고쳐 주세요.", 409)
    before = load_profile(db)
    old_receiver = before["receivers"].get(str(org_id)) or _clean({}, RECEIVER_FIELDS)
    changed = [f"supplier.{k}" for k, v in supplier.items() if before["supplier"].get(k) != v]
    changed += [f"receiver.{k}" for k, v in receiver.items() if old_receiver.get(k) != v]
    value = dict(row.setting_value) if row is not None and isinstance(row.setting_value, dict) else {}
    receivers = dict(value.get("receivers") or {})
    receivers[str(org_id)] = receiver
    value.update({"supplier": supplier, "receivers": receivers})
    if row is None:
        row = SystemSetting(setting_key=SETTINGS_KEY, description="협력사 거래명세서 양식 정보", version=1)
        db.add(row)
    else:
        row.version = current + 1
    row.setting_value = value
    flag_modified(row, "setting_value")
    db.flush()
    return int(row.version), changed
