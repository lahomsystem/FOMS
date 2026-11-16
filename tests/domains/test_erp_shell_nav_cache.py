"""ERP 셸 스왑 · 캐시 동작(2026-11-16 폰 실측 5건) — 가짜 문서로 erp-shell.js 를 돌려 센다.

- 표식: 링크 자신의 ``view=queue`` 가 조각 요청에 남고, 셸 표식은 ``foms_shell`` 로 간다. 서버는 그 요청에 큐를 그린다.
- 만료 줄도 ETag 를 남겨 If-None-Match 를 보낸다(304 면 그 html 로 스왑).
- 온전한 페이지 이동 뒤에도 pagehide 씨앗으로 If-None-Match 를 보낸다(다른 사용자 씨앗은 지운다).
- 같은 곳 스왑 중 다시 누름(비행 중 · 긴 작업 동안 줄 선 누름)은 요청 · 스왑을 늘리지 않는다.
- 첫 웜업은 보이는 아래 탭 순서(아래 탭이 없는 태블릿 · PC 는 예전 PRIMARY 앞 3개).

음성 대조군: 표식을 예전 ``set('view', 'fragment')`` 로 되돌린 사본은 표식 판정에서 실패해야 한다.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.common import erp_navigation_contract as enc
from models import User

ROOT = Path(__file__).resolve().parents[2]
SHELL_JS = ROOT / "static" / "js" / "runtime" / "erp-shell.js"
SIM_JS = ROOT / "tests" / "support" / "erp_shell_nav_cache_node_checks.js"
_NEW_MARKER = "fetchUrl.searchParams.set(SHELL_FRAGMENT_PARAM, 'fragment');"
_OLD_MARKER = "fetchUrl.searchParams.set('view', 'fragment');"


def _run(shell_js: Path | None = None) -> dict:
    node = shutil.which("node")
    assert node, "node must be on PATH for the erp-shell nav cache simulation"
    env = dict(os.environ)
    if shell_js is not None:
        env["FOMS_SIM_SHELL_JS"] = str(shell_js)
    proc = subprocess.run(
        [node, str(SIM_JS)], cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", timeout=120, env=env
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
    return json.loads(proc.stdout)


@pytest.fixture(scope="module")
def sim() -> dict:
    return _run()


def test_link_view_param_survives_fragment_fetch(sim: dict) -> None:
    assert enc.ERP_SHELL_FRAGMENT_QUERY_PARAM == "foms_shell"
    assert sim["marker"]["fetched"] == ["/erp/dashboard?view=queue&foms_shell=fragment"]
    assert sim["marker"]["pushed"] == ["/erp/dashboard?view=queue"]


def test_negative_control_old_marker_clobbers_view(tmp_path: Path) -> None:
    src = SHELL_JS.read_text(encoding="utf-8")
    assert src.count(_NEW_MARKER) == 1, "표식 문장이 바뀌었다 — 대조군 치환을 갱신하라"
    copy = tmp_path / "erp-shell.js"
    copy.write_text(src.replace(_NEW_MARKER, _OLD_MARKER), encoding="utf-8")
    fetched = _run(copy)["marker"]["fetched"]
    assert fetched == ["/erp/dashboard?view=fragment"], fetched


def test_expired_entry_revalidates_with_if_none_match(sim: dict) -> None:
    last = sim["stale"]["calls"][-1]
    assert last == {"url": "/erp/shipment?foms_shell=fragment", "inm": '"e:/erp/shipment"'}
    assert sim["stale"]["lastSwap"] == "<div>/erp/shipment?foms_shell=fragment</div>"


def test_seed_survives_full_navigation_but_not_user_switch(sim: dict) -> None:
    seed = sim["seed"]
    assert seed["same"]["inm"] == '"e:/erp/shipment"'
    assert seed["sameSwap"] == "<div>/erp/shipment?foms_shell=fragment</div>"
    assert seed["other"]["inm"] is None
    assert seed["keysAfterOther"] <= 1  # 다른 사용자 씨앗은 지워지고 남는 건 그 사용자 자신의 것뿐


def test_repeat_tap_to_same_destination_is_merged(sim: dict) -> None:
    assert sim["dedupe"]["afterInflight"] == {"fetches": 1, "swaps": 1, "samePromise": True}
    assert sim["dedupe"]["afterQueued"] == {"fetches": 1, "swaps": 1}


def test_prewarm_follows_visible_bottom_nav_then_falls_back(sim: dict) -> None:
    assert sim["prewarm"]["phone"] == [
        "/erp/construction/dashboard?foms_shell=fragment",
        "/erp/shipment?foms_shell=fragment",
        "/erp/as?foms_shell=fragment",
    ]
    assert sim["prewarm"]["pc"] == [
        "/erp/measurement?foms_shell=fragment",
        "/erp/drawing-workbench?foms_shell=fragment",
        "/erp/production/dashboard?foms_shell=fragment",
    ]


def _login_v2(client, monkeypatch) -> None:
    user = User(
        username="shell_marker_v2",
        password=generate_password_hash("x"),
        role="ADMIN",
        team="CS",
        name="shell_marker_v2",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    client.set_cookie("foms_ptr", "coarse", domain="localhost")
    client.set_cookie("foms_vw", "narrow", domain="localhost")


@pytest.mark.parametrize(
    ("query", "tower"),
    [
        ("foms_shell=fragment", True),
        ("view=queue&foms_shell=fragment", False),
        ("view=fragment", True),  # 예전 표식(bottom-nav-shell.js · 예전 리다이렉트)도 그대로 받는다
    ],
)
def test_server_reads_marker_and_keeps_view_queue(client, monkeypatch, query: str, tower: bool) -> None:
    _login_v2(client, monkeypatch)
    resp = client.get(f"/erp/dashboard?{query}", headers={"X-FOMS-ERP-SHELL": "1"})
    assert resp.status_code == 200
    assert resp.headers.get("X-FOMS-ERP-FRAGMENT") == "1"
    body = resp.get_data(as_text=True)
    assert ('aria-label="모바일 홈 컨트롤 타워"' in body) is tower, query
    assert ('aria-label="모바일 홈 대시보드"' in body) is (not tower), query
