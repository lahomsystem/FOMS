"""썸네일 재사용 확인의 404 는 정상 경로 — 오류 기록을 남기지 않는다(2026-10-01 운영 로그 잡음)."""

import pytest
from botocore.exceptions import ClientError

from foms.services import storage as storage_mod


class _Client:
    def __init__(self, error):
        self.error = error

    def head_object(self, **_kwargs):
        raise self.error

    def get_object(self, **_kwargs):
        raise RuntimeError("stop after head_object")


def _adapter(error):
    adapter = storage_mod.StorageAdapter.__new__(storage_mod.StorageAdapter)
    adapter.storage_type = "r2"
    adapter.bucket_name = "bucket"
    adapter.client = _Client(error)
    return adapter


def _client_error(code):
    return ClientError({"Error": {"Code": code, "Message": "x"}}, "HeadObject")


@pytest.mark.parametrize(
    ("error", "logged"),
    [
        (_client_error("404"), []),
        (_client_error("NoSuchKey"), []),
        (_client_error("403"), ["thumbnail generation"]),
        (TimeoutError("slow"), ["thumbnail generation"]),
    ],
)
def test_missing_thumbnail_is_not_logged(monkeypatch, error, logged):
    calls = []
    monkeypatch.setattr(storage_mod, "log_handled_exception", lambda where, **_kw: calls.append(where))

    try:
        _adapter(error).generate_thumbnail_from_storage_key("orders/1/photo.jpg")
    except RuntimeError:
        pass

    assert calls[: len(logged)] == logged
    assert "thumbnail generation" not in calls[len(logged):]
