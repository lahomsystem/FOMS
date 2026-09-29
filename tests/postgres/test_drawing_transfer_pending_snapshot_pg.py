"""리뷰 P2 — 작업실 대기 전달(transfer-pending)의 버전 스냅샷 쓰기가 남의 커밋을 지우지 않는다.

예전에는 ``perform_drawing_transfer`` 가 커밋(잠금 해제)한 **뒤** ``snapshot_and_clear_pending``
이 잠금 없이 다시 읽고, 시트마다 R2 에 업로드한 다음 ``structured_data`` 를 통째로 되써
커밋했다(버전도 안 올렸다). 그 업로드 틈에 커밋된 수정요청·폼 저장이 사라졌다. 지금은 스냅샷을
전달의 REV-00 엔진 쓰기에 실어(``prepare_structured``) 한 트랜잭션·버전 +1 한 번이다.

가짜 스토리지가 첫 업로드 순간 연결 B 의 쓰기를 띄운다. 고친 코드는 행 잠금을 쥔 채 업로드하므로
B 는 A 의 커밋을 기다렸다가 그 위에 쓰고, 두 변경이 모두 남는다. 고치기 전 코드(1c2562737)에서는
이 테스트가 "스냅샷 쓰기가 B 의 커밋을 지웠다"로 빨갛다.
"""
from __future__ import annotations

import copy
import threading

from sqlalchemy.orm.attributes import flag_modified

import foms.api.drawing.wizard as wizard_api
from models import Order
from tests.postgres.test_drawing_route_row_lock_pg import (  # noqa: F401 — pg_app 는 픽스처
    _HOLD_SECONDS,
    _call_route,
    _final,
    _seed,
    _session,
    pg_app,
)


class _SnapshotWindowStorage:
    """스냅샷 업로드 첫 호출에서 연결 B 의 쓰기를 띄우고 잠시 기다리는 가짜 스토리지.

    예전 코드는 이 업로드를 전달 커밋(잠금 해제) **뒤**에 해서 B 가 곧바로 커밋했고, 업로드
    전에 떠 둔 옛 dict 로 structured_data 를 되써 B 를 지웠다. 고친 코드는 잠금을 쥔 채
    업로드하므로 B 는 A 의 커밋까지 기다렸다가 그 위에 쓴다.
    """

    def __init__(self, pg_engine, order_id, mutate):
        self.pg_engine, self.order_id, self.mutate = pg_engine, order_id, mutate
        self.thread = None

    def upload_file(self, file_obj, filename, folder="uploads"):
        if self.thread is None:
            started, done = threading.Event(), threading.Event()
            self.thread = threading.Thread(
                target=_concurrent_write,
                args=(self.pg_engine, self.order_id, self.mutate, started, done))
            self.thread.start()
            assert started.wait(5.0)
            done.wait(_HOLD_SECONDS * 1.5)  # 잠겨 있으면 여기서 시간만 흐른다
        return {"success": True, "key": f"{folder}/{filename}"}

    def delete_file(self, key):
        return True


def _concurrent_write(pg_engine, order_id, mutate, started, done):
    """연결 B: 잠금을 얻는 대로 쓰기(+버전)하고 곧바로 커밋한다."""
    s = _session(pg_engine)
    try:
        started.set()
        o = s.query(Order).filter(Order.id == order_id).with_for_update().one()
        sd = copy.deepcopy(o.structured_data)
        mutate(sd)
        o.structured_data = sd
        flag_modified(o, "structured_data")
        o.mutation_version = (o.mutation_version or 0) + 1
        s.commit()
    finally:
        s.close()
        done.set()


def test_transfer_pending_snapshot_does_not_erase_concurrent_commit(pg_engine, pg_app,
                                                                     monkeypatch):
    """리뷰 P2 — 작업실 대기 전달의 스냅샷 쓰기가 그 사이 커밋된 남의 쓰기를 지우지 않는다."""
    oid, _sales, drafter = _seed(pg_engine, stage="CONFIRM", drawing_status="PENDING",
                                 history=[])
    s = _session(pg_engine)
    try:
        o = s.query(Order).filter(Order.id == oid).one()
        sd = copy.deepcopy(o.structured_data)
        sd["drawing_current_files"] = []
        sd["drawing_wizard"] = {
            "sheets": [{"id": "s-1", "name": "시트1", "objects": []}],
            "pending": {"s-1": {"key": f"orders/{oid}/drawing_wizard/exports/p1.png",
                                "filename": "p1.png", "sheet_name": "시트1"}},
        }
        o.structured_data = sd
        flag_modified(o, "structured_data")
        s.commit()
    finally:
        s.close()

    def _b_form_save(sd):
        sd["parties"]["customer"]["name"] = "B고객"

    storage = _SnapshotWindowStorage(pg_engine, oid, _b_form_save)
    monkeypatch.setattr(wizard_api, "get_storage", lambda: storage)
    out = {}
    _call_route(pg_app, drafter, f"/api/orders/{oid}/drawing-wizard/transfer-pending", {}, out)
    assert storage.thread is not None, "스냅샷 업로드가 일어나지 않았다"
    storage.thread.join(15.0)
    assert out["status"] == 200, out
    sd, version = _final(pg_engine, oid)
    assert sd["parties"]["customer"]["name"] == "B고객", "스냅샷 쓰기가 B 의 커밋을 지웠다"
    assert sd["drawing_status"] == "TRANSFERRED"
    assert sd["drawing_wizard"]["pending"] == {}
    assert [v["sheet_id"] for v in sd["drawing_wizard"]["versions"]] == ["s-1"]
    assert version == 3  # 1(생성) → A 전달+스냅샷 +1 → B +1
