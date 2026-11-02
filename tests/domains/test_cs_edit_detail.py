"""[수정하기] '왜 고쳤나요(자세히)' · 사진(설계서 17.6.1 (a) · (b) · (f) 시험 1 ~ 4 · 8 · 10 — 사장님 결정 D94).

① 이유 · 사진이 없어도 · 저장이 실패해도 [보내기]는 그대로 ② 자세한 이유(가림 뒤 저장 · 손님 정보 꼴 400 · 1,000자 · '고침' 아닌 줄
409 · 24시간 · 다른 직원 403 · ADMIN 됨 · CSRF) ③ 사진(이름만 바꾼 PDF · 글 · HEIC · GIF 거절 · 6장째 · 5MB · 픽셀 · 같은 사진 ·
EXIF 위치 없음 · key 꼴 · 응답에 URL 없음) ④ 보기 라우트(ADMIN · 올린 직원 24시간 · no-store · nosniff · 지운 사진 404)
⑤ 지우기(직원이 지운 사진은 바로 저장소에서) ⑥ 마이그레이션. 요청 크기 manifest · 밤 지우기 배선 · 화면 · JS 는
``test_cs_edit_detail_wiring.py``, 학습 재료는 ``test_cs_edit_learning.py``.

채널톡 · 저장소는 가짜(네트워크 없음), 그림은 Pillow 로 만든 합성 그림, 글은 손으로 꾸민 합성 글만(전화 꼴 숫자는 실행 때
만든다 — 공개 저장소). 시각은 2026-11 KST(11-02 월).
"""

from __future__ import annotations

import datetime
import importlib.util
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from itsdangerous import URLSafeSerializer
from PIL import Image
from sqlalchemy import CheckConstraint

from db import db_session
from foms.api import cs_agent_edit_detail as edit_api
from foms.services.cs_agent import edit_detail, edit_photos
from foms.services.cs_agent import settings as st
from foms.services.cs_agent.edit_detail_settings import DETAIL_FIELD, PHOTOS_FIELD
from foms.services.request_write_guard import _CSRF_SALT, _CSRF_SESSION_KEY
from foms.web import cs_agent_send as edit_web
from models import CsAgentTurn, CsAgentTurnPhoto, SecurityLog, SystemSetting
from tests.domains.test_cs_drafting import channel  # noqa: F401 — fixture
from tests.domains.test_cs_send import FakeSender, fresh, posted, press, switches, user
from tests.domains.test_cs_send_parts import login, ready  # noqa: F401 — fixture
from tests.support.cs_agent_fakes import at, keys  # noqa: F401 — fixture

ROOT = Path(__file__).resolve().parents[2]
API = "/api/cs-agent/turns"
EDITED = "합성 고친 답입니다."
DETAIL = "지식의 선반 깊이 값과 다르게 안내했어요\n다음엔 깊이 표를 먼저 봐 주세요"
PHONE = "-".join(("010", "7" * 4, "3" * 4))  # 꾸민 전화 꼴(실행 때 만든다)
SENT_AT = at(2, 9, 1)
SOON, LATER = at(2, 12), at(3, 9, 2)  # 보낸 뒤 3시간 · 보낸 때부터 24시간 넘음
AFTER_UPLOAD = at(3, 12, 1)  # SOON 에 올린 사진의 24시간 뒤


# ── 재료 ─────────────────────────────────────────────────────────────────
class FakeStore:
    """비공개 저장소 대역(R2 꼴) — 올린 바이트를 메모리에 두고, 지운 key 를 적는다."""

    storage_type = "r2"

    def __init__(self, *, delete_ok=True):
        self.objects, self.deleted, self.delete_ok = {}, [], delete_ok

    def put_private_bytes(self, key, data, content_type):
        self.objects[key] = (data, content_type)
        return True

    def read_file_bytes(self, key):
        found = self.objects.get(key)
        return found[0] if found else None

    def delete_file(self, key):
        if not self.delete_ok:
            return False
        self.objects.pop(key, None)
        self.deleted.append(key)
        return True


def picture(color=(200, 30, 30), size=(64, 48), fmt="JPEG", **save):
    out = io.BytesIO()
    Image.new("RGBA" if fmt == "PNG" and save.pop("alpha", False) else "RGB", size, color).save(out, format=fmt, **save)
    return out.getvalue()


def gps_jpeg():
    """위치 정보(GPS) · 기기 이름이 든 합성 JPEG."""
    exif = Image.Exif()
    exif[0x010F] = "SyntheticCam"
    exif[0x8825] = {1: "N", 2: (37.0, 30.0, 0.0), 3: "E", 4: (127.0, 0.0, 0.0)}
    data = picture(exif=exif.tobytes())
    assert dict(Image.open(io.BytesIO(data)).getexif().get_ifd(0x8825))  # 음성 대조 — 넣은 위치가 정말 있다
    return data


def person(**kwargs):
    """합성 직원 — 번호만 들고 다닌다(요청이 끝나면 세션이 닫혀 줄이 떨어진다)."""
    return SimpleNamespace(id=user(**kwargs).id)


def detail_on(*, photos=True, detail=True):
    switches()
    row = db_session.get(SystemSetting, st.SETTINGS_KEY)
    row.setting_value = {**row.setting_value, DETAIL_FIELD: detail, PHOTOS_FIELD: photos}
    db_session.commit()


@pytest.fixture
def store(monkeypatch):
    fake = FakeStore()
    monkeypatch.setattr(edit_detail, "get_storage", lambda: fake)
    return fake


@pytest.fixture
def clock(monkeypatch):
    """API · 화면 라우트의 '지금' — 처음은 보낸 뒤 3시간."""
    now = {"value": SOON}
    monkeypatch.setattr(edit_api, "now_kst", lambda: now["value"])
    monkeypatch.setattr(edit_web, "now_kst", lambda: now["value"])
    return now


def sent_edited(app, channel_, staff, chat="uc-1"):
    """고쳐 보낸 차례 — 끝난 꼴 '고침' · 보낸 직원 · 보낸 때."""
    turn_id = posted(channel_, chat)
    assert press(app, channel_, turn_id, staff.id, FakeSender(channel_), mode="edited", text=EDITED).code == "sent"
    row = fresh(turn_id)
    assert (row.outcome, row.sent_by_user_id) == ("edited", staff.id)
    return turn_id


def post_detail(client, turn_id, detail):
    return client.post(f"{API}/{turn_id}/edit-detail", json={"detail": detail})


def post_photo(client, turn_id, data, *, no_personal=True, name="a.jpg"):
    return client.post(f"{API}/{turn_id}/edit-photos", content_type="multipart/form-data",
                       data={"photo": (io.BytesIO(data), name), "no_personal": "1" if no_personal else "0"})


def photos(turn_id):
    db_session.expire_all()
    return db_session.query(CsAgentTurnPhoto).filter_by(turn_id=turn_id).order_by(CsAgentTurnPhoto.seq).all()


# ── ① 보내기는 그대로 ────────────────────────────────────────────────────
def test_sending_never_waits_for_the_detail_and_a_failed_save_leaves_the_sent_reply(app, client, ready, store, clock):
    staff = person()
    detail_on()
    login(client, staff)
    turn_id = posted(ready)
    html = client.get(f"/cs-agent/turns/{turn_id}/edit?c=uc-1").get_data(as_text=True)
    assert "data-cs-detail" in html and "data-cs-detail-file" in html and "edit-detail.js" in html
    assert post_detail(client, turn_id, DETAIL).status_code == 409  # 보내기 전에는 저장할 곳이 없다
    sender = FakeSender(ready)
    assert press(app, ready, turn_id, staff.id, sender, mode="edited", text=EDITED).code == "sent"
    failed = post_detail(client, turn_id, f"손님 번호 {PHONE}")
    assert failed.status_code == 400 and failed.get_json()["data"]["field"] == "detail_private"
    row = fresh(turn_id)
    assert (row.send_state, row.outcome, row.edit_detail_masked, len(sender.calls)) == ("sent", "edited", None, 1)


def test_the_section_is_absent_when_switched_off_and_photos_need_a_cloud_store(client, ready, monkeypatch):
    staff = person()
    login(client, staff)
    turn_id = posted(ready)
    detail_on(detail=False)
    assert "data-cs-detail" not in client.get(f"/cs-agent/turns/{turn_id}/edit?c=uc-1").get_data(as_text=True)
    detail_on()
    local = FakeStore()
    local.storage_type = "local"  # 로컬 저장소(static/uploads — 누구나 여는 정적 경로)면 사진 칸을 끈다
    monkeypatch.setattr(edit_detail, "get_storage", lambda: local)
    html = client.get(f"/cs-agent/turns/{turn_id}/edit?c=uc-1").get_data(as_text=True)
    assert "data-cs-detail" in html and "data-cs-detail-file" not in html and 'data-photos="0"' in html
    assert "data-cs-detail" not in client.get(f"/cs-agent/turns/{turn_id}/send?c=uc-1").get_data(as_text=True)


# ── ② 자세한 이유 ────────────────────────────────────────────────────────
def test_the_detail_is_saved_masked_overwritten_and_audited_without_text(app, client, ready, store, clock):
    staff = person()
    detail_on()
    turn_id = sent_edited(app, ready, staff)
    login(client, staff)
    ok = post_detail(client, turn_id, DETAIL)
    assert ok.status_code == 200 and ok.get_json()["data"]["code"] == "saved"
    row = fresh(turn_id)
    assert (row.edit_detail_masked, row.edit_detail_by) == (DETAIL, staff.id) and row.edit_detail_at is not None
    assert post_detail(client, turn_id, "줄 바꿈 있는 새 이유\n둘째 줄").status_code == 200
    assert fresh(turn_id).edit_detail_masked == "줄 바꿈 있는 새 이유\n둘째 줄"  # 마지막 글이 정본
    logs = db_session.query(SecurityLog).filter_by(action="CS_AGENT_EDIT_DETAIL").all()
    assert len(logs) == 2 and all(DETAIL not in (log.message or "") + json.dumps(log.detail, ensure_ascii=False)
                                  for log in logs)


@pytest.mark.parametrize("text, field", [
    (f"손님 번호 {PHONE} 로 다시 연락", "detail_private"),
    ("서울시 가상구 가상로 123 현장이에요", "detail_private"),
    ("가" * (edit_detail.MAX_DETAIL + 1), "detail"),
    (123, "detail"),
], ids=["phone", "address", "over_1000", "not_text"])
def test_personal_info_or_overlong_details_are_refused_and_not_saved(app, client, ready, store, clock, text, field):
    staff = person()
    detail_on()
    turn_id = sent_edited(app, ready, staff)
    login(client, staff)
    refused = post_detail(client, turn_id, text)
    assert refused.status_code == 400 and refused.get_json()["data"]["field"] == field
    assert fresh(turn_id).edit_detail_masked is None


def test_only_edited_turns_their_sender_within_a_day_or_an_admin_may_write(app, client, ready, store, clock):
    staff, other, admin = person(), person(name="other"), person(role="ADMIN", team=None, name="admin")
    detail_on()
    as_is = posted(ready, "uc-2")
    assert press(app, ready, as_is, staff.id, FakeSender(ready)).code == "sent"  # 그대로 보냄
    turn_id = sent_edited(app, ready, staff)
    login(client, staff)
    assert post_detail(client, as_is, DETAIL).status_code == 409
    login(client, other)
    assert post_detail(client, turn_id, DETAIL).get_json()["data"]["code"] == "not_yours"
    clock["value"] = LATER
    login(client, staff)
    late = post_detail(client, turn_id, DETAIL)
    assert (late.status_code, late.get_json()["data"]["code"]) == (403, "too_late")
    login(client, admin)
    assert post_detail(client, turn_id, DETAIL).status_code == 200  # ADMIN 은 보관 기간 안 언제나
    login(client, person(role="STAFF", team="SALES", name="sales"))
    assert post_detail(client, turn_id, DETAIL).status_code == 403  # 상담 직원 · 관리자만
    client.get("/logout")
    with client.session_transaction() as sess:
        sess.clear()
    assert post_detail(client, turn_id, DETAIL).status_code == 401


def test_writes_need_csrf(app, client, ready, store, clock):
    staff = person()
    detail_on()
    turn_id = sent_edited(app, ready, staff)
    login(client, staff)
    app.config["WRITE_GUARD_ENABLED"] = True
    try:
        blocked = post_detail(client, turn_id, DETAIL)
        assert blocked.status_code == 403 and blocked.headers.get("X-Write-Guard") == "blocked"
        assert post_photo(client, turn_id, picture()).headers.get("X-Write-Guard") == "blocked"
        seed = os.urandom(16).hex()
        with client.session_transaction() as sess:
            sess[_CSRF_SESSION_KEY] = seed
        csrf = URLSafeSerializer(app.secret_key, salt=_CSRF_SALT).dumps(seed)
        passed = client.post(f"{API}/{turn_id}/edit-detail", json={"detail": DETAIL}, headers={"X-CSRF-Token": csrf})
        assert passed.status_code == 200
    finally:
        app.config.pop("WRITE_GUARD_ENABLED", None)
    assert store.objects == {}


# ── ③ 사진 ───────────────────────────────────────────────────────────────
def _heic() -> bytes:
    return b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1heic" + b"\x00" * 64


@pytest.mark.parametrize("data, name, code", [
    (b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\ntrailer\n%%EOF", "a.jpg", "photo_format"),  # 이름만 바꾼 PDF
    ("합성 글 파일".encode("utf-8"), "a.png", "photo_format"),
    (_heic(), "a.heic", "photo_format"),
    (picture(fmt="GIF"), "a.gif", "photo_format"),
    (b"", "a.jpg", "photo_empty"),
    (b"\xff\xd8" + b"\x00" * edit_photos.MAX_BYTES, "a.jpg", "photo_size"),  # 5MB 넘음(머리 · 꼴보다 먼저)
    (picture(fmt="PNG", size=(8000, 6000), color=(0, 0, 0)), "a.png", "photo_size"),  # 픽셀 4천만 넘음(압축 폭탄)
], ids=["renamed_pdf", "text_file", "heic", "gif", "empty", "over_5mb", "pixel_bomb"])
def test_files_that_are_not_small_jpeg_png_webp_are_refused(app, client, ready, store, clock, data, name, code):
    staff = person()
    detail_on()
    turn_id = sent_edited(app, ready, staff)
    login(client, staff)
    refused = post_photo(client, turn_id, data, name=name)
    assert refused.status_code == 400 and refused.get_json()["data"]["code"] == code
    assert photos(turn_id) == [] and store.objects == {}


def test_a_sixth_photo_and_the_same_photo_twice_are_refused(app, client, ready, store, clock):
    staff = person()
    detail_on()
    turn_id = sent_edited(app, ready, staff)
    login(client, staff)
    first = picture(color=(10, 20, 30))
    assert post_photo(client, turn_id, first).status_code == 200
    same = post_photo(client, turn_id, first)
    assert (same.status_code, same.get_json()["data"]["code"]) == (409, "photo_same")
    for shade in range(4):
        assert post_photo(client, turn_id, picture(color=(40 + shade * 40, 90, 90), fmt="WEBP"),
                          name="b.webp").status_code == 200
    sixth = post_photo(client, turn_id, picture(color=(250, 250, 0)))
    assert (sixth.status_code, sixth.get_json()["data"]["code"]) == (409, "photo_full")
    assert [p.seq for p in photos(turn_id)] == [1, 2, 3, 4, 5] and len(store.objects) == 5


def test_a_saved_photo_has_no_location_a_private_key_and_no_url_in_the_reply(app, client, ready, store, clock):
    staff = person()
    detail_on()
    turn_id = sent_edited(app, ready, staff)
    login(client, staff)
    reply = post_photo(client, turn_id, gps_jpeg(), name="홍길동_uc-1_현장.jpg")
    body = reply.get_data(as_text=True)
    assert reply.status_code == 200 and reply.get_json()["data"]["seq"] == 1
    assert "http" not in body and "cs-agent/edit-photos" not in body and "/photos/" not in body and "url" not in body
    (photo,) = photos(turn_id)
    assert edit_photos.KEY_PATTERN.fullmatch(photo.storage_key) and photo.storage_key.startswith(
        f"cs-agent/edit-photos/{turn_id}/")
    assert "uc-1" not in photo.storage_key and "홍길동" not in photo.storage_key and "현장" not in photo.storage_key
    stored, content_type = store.objects[photo.storage_key]
    assert content_type == "image/jpeg" and b"Exif" not in stored and b"SyntheticCam" not in stored
    assert dict(Image.open(io.BytesIO(stored)).getexif()) == {}
    assert (photo.no_personal, photo.desc_state, photo.uploaded_by) == (True, "pending", staff.id)
    log = db_session.query(SecurityLog).filter_by(action="CS_AGENT_PHOTO_ADD").one()
    assert photo.storage_key not in json.dumps(log.detail) + (log.message or "")


def test_transparent_pictures_stay_png_and_unchecked_photos_are_never_described(app, client, ready, store, clock):
    staff = person()
    detail_on()
    turn_id = sent_edited(app, ready, staff)
    login(client, staff)
    assert post_photo(client, turn_id, picture(fmt="PNG", alpha=True, color=(0, 0, 0, 0)), no_personal=False,
                      name="a.png").status_code == 200
    (photo,) = photos(turn_id)
    assert (photo.content_type, photo.storage_key[-4:], photo.no_personal, photo.desc_state) == (
        "image/png", ".png", False, "skipped")


def test_photos_follow_their_switch(app, client, ready, store, clock):
    staff = person()
    detail_on(photos=False)
    turn_id = sent_edited(app, ready, staff)
    login(client, staff)
    off = post_photo(client, turn_id, picture())
    assert (off.status_code, off.get_json()["data"]["code"]) == (409, "photo_off") and store.objects == {}


# ── ④ 보기 라우트 · ⑤ 지우기 ─────────────────────────────────────────────
def test_only_admins_and_the_uploader_within_a_day_may_view_with_no_store(app, client, ready, store, clock):
    staff, other, admin = person(), person(name="other"), person(role="ADMIN", team=None, name="admin")
    detail_on()
    turn_id = sent_edited(app, ready, staff)
    login(client, staff)
    assert post_photo(client, turn_id, picture()).status_code == 200
    view = f"/cs-agent/turns/{turn_id}/photos/1"
    mine = client.get(view)
    assert mine.status_code == 200 and mine.mimetype == "image/jpeg" and mine.data[:2] == b"\xff\xd8"
    assert mine.headers["Cache-Control"] == "private, no-store" and mine.headers["X-Content-Type-Options"] == "nosniff"
    login(client, other)
    assert client.get(view).status_code == 403
    clock["value"] = AFTER_UPLOAD - datetime.timedelta(minutes=2)
    login(client, staff)
    assert client.get(view).status_code == 200  # 올린 때부터 24시간 안
    clock["value"] = AFTER_UPLOAD
    assert client.get(view).status_code == 403  # 올린 직원도 24시간 뒤에는 못 본다
    login(client, admin)
    assert client.get(view).status_code == 200
    assert client.get(f"/cs-agent/turns/{turn_id}/photos/2").status_code == 404
    login(client, person(role="STAFF", team="SALES", name="sales"))
    assert client.get(view).status_code == 403


def test_a_deleted_photo_is_gone_from_storage_at_once_and_then_404(app, client, ready, store, clock):
    staff, other = person(), person(name="other")
    detail_on()
    turn_id = sent_edited(app, ready, staff)
    login(client, staff)
    assert post_photo(client, turn_id, picture()).status_code == 200
    (photo,) = photos(turn_id)
    key = photo.storage_key
    login(client, other)
    assert client.delete(f"{API}/{turn_id}/edit-photos/1").status_code == 403 and key in store.objects
    login(client, staff)
    gone = client.delete(f"{API}/{turn_id}/edit-photos/1")
    assert gone.status_code == 200 and gone.get_json()["data"]["photos"] == []
    assert store.deleted == [key] and key not in store.objects
    (photo,) = photos(turn_id)
    assert photo.storage_key is None and photo.purged_at is not None
    assert client.get(f"/cs-agent/turns/{turn_id}/photos/1").status_code == 404
    assert client.delete(f"{API}/{turn_id}/edit-photos/1").status_code == 404
    assert post_photo(client, turn_id, picture()).get_json()["data"]["seq"] == 2  # 지운 사진 자리는 다시 쓸 수 있다


def test_a_failed_storage_delete_keeps_the_row_for_a_retry(app, client, ready, monkeypatch, clock):
    staff = person()
    detail_on()
    fake = FakeStore(delete_ok=False)
    monkeypatch.setattr(edit_detail, "get_storage", lambda: fake)
    turn_id = sent_edited(app, ready, staff)
    login(client, staff)
    assert post_photo(client, turn_id, picture()).status_code == 200
    assert client.delete(f"{API}/{turn_id}/edit-photos/1").status_code == 502
    (photo,) = photos(turn_id)
    assert photo.storage_key and photo.purged_at is None


# ── ⑥ 마이그레이션 ───────────────────────────────────────────────────────
def test_csagent_05_chains_onto_csagent_06_matches_the_model_and_keeps_one_head():
    path = ROOT / "migrations" / "versions" / "csagent_05_turn_edit_detail.py"
    spec = importlib.util.spec_from_file_location("csagent_05_unit", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert (module.revision, module.down_revision) == ("csagent_05", "csagent_06")
    source = path.read_text(encoding="utf-8")
    assert "import models" not in source and "from models" not in source
    turns = CsAgentTurn.__table__.c
    for name, type_, nullable, _default in module.TURN_COLUMNS:
        assert turns[name].nullable is nullable and type(turns[name].type).__name__ == type(type_).__name__, name
    table = CsAgentTurnPhoto.__table__
    for name, type_, nullable, _default in module.COLUMNS:
        column = table.c[name]
        assert column.nullable is nullable and type(column.type).__name__ == type(type_).__name__, name
        assert getattr(column.type, "length", None) == getattr(type_, "length", None), name
    checks = {c.name: str(c.sqltext) for c in table.constraints if isinstance(c, CheckConstraint)}
    assert checks[module.DESC_STATE_CHECK] == module.in_check("desc_state", module.DESC_STATES)
    assert checks[module.SEQ_CHECK] == module.seq_check() and module.SEQ_MAX == edit_detail.SEQ_MAX
    assert [fk.target_fullname for fk in table.c.turn_id.foreign_keys] == ["cs_agent_turns.id"]
    indexes = {i.name: tuple(c.name for c in i.columns) for i in table.indexes}
    assert all(indexes[name] == columns for name, columns in module.INDEXES)
    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    assert script.get_heads() == ["csagent_05"]


def test_the_view_window_is_one_day():
    assert edit_detail.WINDOW == datetime.timedelta(hours=24) and edit_photos.MAX_PHOTOS == 5
    assert edit_photos.MAX_BYTES == 5 * 1024 * 1024
