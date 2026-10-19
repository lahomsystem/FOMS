"""naive UTC 시각이 화면에 9시간 이르게 찍히던 회귀 방지 — 알림톡 최근 발송·공유 링크 이력."""
import pathlib
import re
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="node not on PATH")


def _helper_src(rel: str) -> str:
    src = (ROOT / rel).read_text(encoding="utf-8")
    m = re.search(r"(?:const|var) _KST_FMT = .*?\n    function _toKstMinute\(value\) \{.*?\n    \}\n", src, re.S)
    assert m, rel
    return m.group(0)


@pytest.mark.parametrize("rel", ["static/js/orders/erp-alimtalk-send.js", "static/js/orders/erp-share.js"])
def test_naive_utc_rendered_as_kst(rel):
    script = _helper_src(rel) + """
    console.log(JSON.stringify([
        _toKstMinute('2026-10-19T03:05:00.123456'),
        _toKstMinute('2026-10-19T15:30:00'),
        _toKstMinute('2026-10-19T12:00:00+09:00'),
        _toKstMinute(''),
        _toKstMinute('garbage-value-xx')
    ]));
    """
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, encoding="utf-8", check=True).stdout
    assert out.strip() == (
        '["2026-10-19 12:05","2026-10-20 00:30","2026-10-19 12:00","","garbage-value-xx"]'
    )


@pytest.mark.parametrize("rel", ["static/js/orders/erp-alimtalk-send.js", "static/js/orders/erp-share.js"])
def test_no_raw_slice_of_server_timestamps(rel):
    src = (ROOT / rel).read_text(encoding="utf-8")
    for field in ("sent_at", "created_at", "first_viewed_at"):
        assert not re.search(field + r"[^\n;]*\.slice\(0, 16\)", src), field
