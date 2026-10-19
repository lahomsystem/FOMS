"""CLIENT-IP-01: 프록시 뒤 손님 IP 신뢰 경계 계약(2026-10-19).

스테이징에서 같은 PC 의 연속 요청이 앱에서 요청마다 다른 ``remote_addr`` 로 보였다. 가장 강한
후보는 Railway 가 ``X-Forwarded-For`` 를 [손님, 중간 주소] 2개로 붙이는데 홉 1 설정이 오른쪽 끝
중간 주소를 고르는 것이다(설계서 ``docs/specs/2026-10-19-client-ip-behind-proxy_SPEC.md``).
이 파일은 다음을 고정한다.

* 헤더 모양·홉 수별로 ProxyFix 가 고르는 ``remote_addr`` 와, 믿기 어려울 때 남는 경고 사유.
* 증상 재현: 손님은 같고 중간 주소만 바뀌면 홉 1 은 IP 가 바뀌고 홉 2 는 고정 — 로그인 잠금까지.
* 경고는 사유 조합별 간격 제한, 로그에는 IP 앞 두 마디만.
* 홉 수 해석(지금 규칙 그대로 + 경고)·기동 INFO, ``X-Forwarded-Prefix`` 무시, ``X-Forwarded-Host`` 보류.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from flask import Flask, request, url_for

import foms.platform.client_ip_trust as client_ip_trust
from foms.platform.app_factory import apply_proxy_fix
from foms.platform.client_ip_trust import (
    TRUSTED_PROXY_HOPS_ENV,
    mask_ip,
    resolve_trusted_proxy_hops,
    wrap_client_ip_monitor,
    wrap_proxy_fix,
)
from tests.domains.test_login_rate_limit_lockout import (  # noqa: F401  autouse 픽스처 등록
    _THRESHOLD,
    _WRONG_PW,
    _reset_rate_limits,
    _restore_flask_limiter_handlers,
    _rows,
    _small_lockout_window,
)

_LOGGER = client_ip_trust.__name__

#: 손님(공인 주소여야 한다 — 문서용 대역 203.0.113.0/24 등은 ``is_global`` 이 False 라 못 쓴다).
CLIENT = "121.165.40.7"
#: 2026-03·09 Railway 보고에 나온 CDN 노드 주소들(Fastly·CDN77). 요청마다 바뀌는 오른쪽 끝 흉내.
EDGE_NODES = ("152.233.23.193", "152.233.23.194", "167.82.231.36", "140.248.75.140")
#: werkzeug 시험 클라이언트의 소켓 상대 주소(= Railway 내부 주소 자리).
PEER = "127.0.0.1"
PUBLIC_HOST = "lahom-dev.up.railway.app"


def _probe_app(monkeypatch: pytest.MonkeyPatch, hops: int | None) -> tuple[Flask, dict[str, Any]]:
    """실제 ``apply_proxy_fix`` 로 감싼 작은 앱과, 요청이 본 값을 담을 dict 를 만든다.

    :param monkeypatch: env 설정용.
    :param hops: ``FOMS_TRUSTED_PROXY_HOPS`` 값. ``None`` 이면 미설정.
    :return: ``(앱, captured)``. captured 에 remote_addr·script_root·host·url 이 담긴다.
    """
    if hops is None:
        monkeypatch.delenv(TRUSTED_PROXY_HOPS_ENV, raising=False)
    else:
        monkeypatch.setenv(TRUSTED_PROXY_HOPS_ENV, str(hops))
    app = Flask(__name__)
    apply_proxy_fix(app)
    captured: dict[str, Any] = {}

    @app.route("/probe")
    def probe() -> str:
        captured["remote_addr"] = request.remote_addr
        captured["script_root"] = request.script_root
        captured["host"] = request.host
        captured["url"] = url_for("probe")
        return "ok"

    return app, captured


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    """이 모듈 로거의 WARNING 이상 메시지만.

    :param caplog: pytest 로그 캡처.
    :return: 메시지 목록.
    """
    return [r.getMessage() for r in caplog.records if r.name == _LOGGER and r.levelno >= logging.WARNING]


# --------------------------------------------------------------------------
# 1. 헤더 모양 × 홉 수 → remote_addr 와 경고 사유
# --------------------------------------------------------------------------
_RAILWAY_TWO = {"X-Forwarded-For": f"{CLIENT}, {EDGE_NODES[0]}", "X-Real-IP": CLIENT}

_SHAPES = [
    # (id, 홉, 헤더, 기대 remote_addr, 기대 사유)
    ("one_entry_hop1", 1, {"X-Forwarded-For": CLIENT, "X-Real-IP": CLIENT}, CLIENT, ()),
    # Railway 실측 보고 모양 [손님, 중간 주소] + 지금 기본 홉 1 → 중간 주소를 고른다(증상의 뿌리).
    ("railway_two_hop1", 1, _RAILWAY_TWO, EDGE_NODES[0], ("xff_long", "real_ip_mismatch")),
    ("railway_two_hop2", 2, _RAILWAY_TWO, CLIENT, ()),
    # 홉 2 인데 항목이 1개면 ProxyFix 는 덮지 않는다 → 모든 손님이 공유하는 소켓 상대 주소.
    ("one_entry_hop2_peer", 2, {"X-Forwarded-For": CLIENT, "X-Real-IP": CLIENT}, PEER,
     ("xff_short", "real_ip_mismatch", "resolved_not_global")),
    ("no_xff", 1, {}, PEER, ("xff_missing", "resolved_not_global")),
    ("internal_rightmost", 1, {"X-Forwarded-For": f"{CLIENT}, 10.0.0.5"}, "10.0.0.5",
     ("xff_long", "resolved_not_global")),
    ("cgnat_only", 1, {"X-Forwarded-For": "100.64.3.4"}, "100.64.3.4", ("resolved_not_global",)),
    # CDN 주소는 공인이라 not_global 은 안 뜬다 — xff_long·real_ip_mismatch 가 잡는다.
    ("cdn_rightmost_hop1", 1, {"X-Forwarded-For": f"{CLIENT}, {EDGE_NODES[2]}", "X-Real-IP": CLIENT},
     EDGE_NODES[2], ("xff_long", "real_ip_mismatch")),
    # 엣지가 손님 헤더 뒤에 붙이기만 한다면: 위조한 왼쪽 값은 버려지고 경고는 xff_long.
    ("spoof_left_hop1", 1, {"X-Forwarded-For": f"6.6.6.6, {CLIENT}"}, CLIENT, ("xff_long",)),
    # IP 모양이 아닌 값도 ProxyFix 는 그대로 넣는다 → 경고(가린 값 invalid).
    ("garbage_entry", 1, {"X-Forwarded-For": "garbage"}, "garbage", ("resolved_not_global",)),
]


@pytest.mark.parametrize(
    "hops, headers, expected_addr, expected_reasons",
    [case[1:] for case in _SHAPES],
    ids=[case[0] for case in _SHAPES],
)
def test_header_shape_resolution_and_warning(
    monkeypatch, caplog, hops, headers, expected_addr, expected_reasons
):
    """모양별 ``remote_addr`` 와 경고 사유(없으면 경고 0건, 있으면 정확히 그 조합 1건)."""
    app, captured = _probe_app(monkeypatch, hops)
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        app.test_client().get("/probe", headers=headers)

    assert captured["remote_addr"] == expected_addr
    messages = _warnings(caplog)
    if not expected_reasons:
        assert messages == []
    else:
        assert len(messages) == 1, messages
        assert f"reasons={','.join(expected_reasons)} " in messages[0]


def test_garbage_entry_is_masked_as_invalid(monkeypatch, caplog):
    """IP 모양이 아닌 항목은 원문 대신 ``invalid`` 로 남는다."""
    app, _ = _probe_app(monkeypatch, 1)
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        app.test_client().get("/probe", headers={"X-Forwarded-For": "garbage"})
    (message,) = _warnings(caplog)
    assert "resolved=invalid" in message
    assert "garbage" not in message


# --------------------------------------------------------------------------
# 2. 증상 재현 — 손님은 같고 중간 주소만 바뀐다
# --------------------------------------------------------------------------
def test_rotating_edge_changes_remote_addr_with_one_hop_only(monkeypatch):
    """홉 1 이면 요청마다 IP 가 바뀌고(스테이징 증상), 홉 2 면 손님 IP 하나로 고정된다."""
    seen: dict[int, set[str]] = {}
    for hops in (1, 2):
        app, captured = _probe_app(monkeypatch, hops)
        client = app.test_client()
        seen[hops] = set()
        for edge in EDGE_NODES:
            client.get("/probe", headers={"X-Forwarded-For": f"{CLIENT}, {edge}", "X-Real-IP": CLIENT})
            seen[hops].add(captured["remote_addr"])

    assert seen[1] == set(EDGE_NODES)
    assert seen[2] == {CLIENT}


@pytest.mark.parametrize("hops, pair_locks", [(1, False), (2, True)], ids=["hop1", "hop2"])
def test_login_pair_lockout_follows_trusted_hops(client, app, monkeypatch, hops, pair_locks):
    """Railway 모양 헤더로 없는 아이디 로그인 실패: (아이디, IP) 잠금은 홉 수가 맞을 때만 걸린다.

    계정 카운터(IP 무관)는 임계를 높여 이 시험에서 비켜 둔다.
    """
    monkeypatch.setenv("FOMS_LOGIN_ACCOUNT_LOCKOUT_THRESHOLD", "50")
    monkeypatch.setattr(app, "wsgi_app", wrap_proxy_fix(app.wsgi_app, hops=hops))

    statuses = []
    for index in range(_THRESHOLD + 1):
        edge = EDGE_NODES[index % len(EDGE_NODES)]
        resp = client.post(
            "/login",
            data={"username": "ghost-proxy-user", "password": _WRONG_PW},
            headers={"X-Forwarded-For": f"{CLIENT}, {edge}", "X-Real-IP": CLIENT},
        )
        statuses.append(resp.status_code)

    if pair_locks:
        assert statuses == [200] * (_THRESHOLD - 1) + [429, 429], statuses
        locks = _rows("LOGIN_LOCKED")
        assert len(locks) == 1
        assert locks[0].detail["scope"] == "ip"
    else:
        assert statuses == [200] * (_THRESHOLD + 1), statuses
        assert _rows("LOGIN_LOCKED") == []


# --------------------------------------------------------------------------
# 3. 경고 내용과 간격 제한
# --------------------------------------------------------------------------
def test_warning_shows_shape_with_masked_ips_only(monkeypatch, caplog):
    """경고 한 줄로 모양(항목 수·위치·헤더 이름·Host 일치·엣지)을 알 수 있고 전체 IP 는 없다."""
    app, _ = _probe_app(monkeypatch, 1)
    headers = dict(_RAILWAY_TWO)
    headers.update({
        "X-Forwarded-Host": PUBLIC_HOST,
        "X-Railway-Edge": "railway/asia-southeast1-eqsg3a",
        "Cdn-Loop": "Fastly",
    })
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        app.test_client().get("/probe", base_url=f"https://{PUBLIC_HOST}", headers=headers)

    (message,) = _warnings(caplog)
    for expected in (
        "hops=1", "xff_count=2", "xff=[121.165.*.*, 152.233.*.*]",
        "resolved=152.233.*.*", "resolved_pos=xff[1]", "real_ip=121.165.*.*", "real_ip_pos=xff[0]",
        "peer=127.0.*.*", "host_eq_xfh=yes", "edge=railway/asia-southeast1-eqsg3a",
        "headers=[x-real-ip,cdn-loop,x-forwarded-host]", "path=/probe",
    ):
        assert expected in message, (expected, message)
    assert CLIENT not in message
    assert EDGE_NODES[0] not in message


def test_host_mismatch_is_reported(monkeypatch, caplog):
    """``Host`` 와 ``X-Forwarded-Host`` 가 다르면 ``host_eq_xfh=no`` — x_host 끄기 전 확인용."""
    app, _ = _probe_app(monkeypatch, 1)
    headers = dict(_RAILWAY_TWO, **{"X-Forwarded-Host": PUBLIC_HOST})
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        app.test_client().get("/probe", base_url="http://internal.railway", headers=headers)
    (message,) = _warnings(caplog)
    assert "host_eq_xfh=no" in message


def test_warning_is_throttled_per_reason_set(caplog):
    """같은 사유 조합은 간격 안에 1번만, 간격이 지나면 다시, 다른 조합은 따로 남는다."""
    now = [1000.0]

    def inner(environ: dict[str, Any], start_response: Any) -> list[bytes]:
        return [b"ok"]

    monitored = wrap_client_ip_monitor(inner, hops=1, interval=600.0, clock=lambda: now[0])
    internal = {"REMOTE_ADDR": "10.0.0.5", "HTTP_X_FORWARDED_FOR": "10.0.0.5"}
    missing = {"REMOTE_ADDR": PEER}

    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        for _ in range(3):
            assert monitored(dict(internal), None) == [b"ok"]
        assert len(_warnings(caplog)) == 1

        monitored(dict(missing), None)  # 다른 조합(xff_missing,resolved_not_global)
        assert len(_warnings(caplog)) == 2

        now[0] += 599.0
        monitored(dict(internal), None)
        assert len(_warnings(caplog)) == 2

        now[0] += 1.0
        monitored(dict(internal), None)
        assert len(_warnings(caplog)) == 3


@pytest.mark.parametrize(
    "value, expected",
    [
        ("121.165.40.7", "121.165.*.*"),
        (" 152.233.23.193 ", "152.233.*.*"),
        ("2406:5900:1::7", "2406:5900:*"),
        ("", "-"),
        (None, "-"),
        ("garbage", "invalid"),
        ("121.165.40.7:443", "invalid"),
    ],
)
def test_mask_ip(value, expected):
    """IP 는 앞 두 마디만, 빈 값은 ``-``, IP 모양이 아니면 ``invalid``."""
    assert mask_ip(value) == expected


# --------------------------------------------------------------------------
# 4. 홉 수 해석·기동 로그
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw, expected, warns",
    [
        (None, (1, "default"), False),
        ("", (1, "default"), False),
        ("2", (2, "env"), False),
        (" 2 ", (2, "env"), False),
        ("0", (0, "env"), False),
        ("abc", (1, "invalid"), True),
        ("-3", (0, "clamped"), True),
    ],
)
def test_resolve_trusted_proxy_hops(monkeypatch, caplog, raw, expected, warns):
    """지금까지와 같은 해석(미설정·오류 → 1, 음수 → 0)에 잘못된 값 경고만 더한다."""
    if raw is None:
        monkeypatch.delenv(TRUSTED_PROXY_HOPS_ENV, raising=False)
    else:
        monkeypatch.setenv(TRUSTED_PROXY_HOPS_ENV, raw)
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        assert resolve_trusted_proxy_hops() == expected
    assert bool(_warnings(caplog)) is warns


def test_apply_proxy_fix_logs_effective_config_once(monkeypatch, caplog):
    """기동 때 적용 홉 수와 출처가 INFO 1줄로 남는다(Deploy Logs 에서 실측 전 기본값임을 본다)."""
    monkeypatch.delenv(TRUSTED_PROXY_HOPS_ENV, raising=False)
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        apply_proxy_fix(Flask(__name__))
    infos = [r.getMessage() for r in caplog.records if r.name == _LOGGER and r.levelno == logging.INFO]
    assert infos == [
        "proxy trust: x_for=1 (FOMS_TRUSTED_PROXY_HOPS 미설정 → 기본값) x_proto=1 x_host=1 x_prefix=0"
    ]


# --------------------------------------------------------------------------
# 5. 홉 외 헤더 — X-Forwarded-Prefix 무시, X-Forwarded-Host 는 보류(아직 믿음)
# --------------------------------------------------------------------------
def test_forwarded_prefix_is_ignored(monkeypatch):
    """Railway 가 보내지 않는 ``X-Forwarded-Prefix`` 는 URL 생성에 반영되지 않는다."""
    app, captured = _probe_app(monkeypatch, 1)
    app.test_client().get("/probe", headers={"X-Forwarded-For": CLIENT, "X-Forwarded-Prefix": "/evil"})
    assert captured["script_root"] == ""
    assert captured["url"] == "/probe"


def test_forwarded_host_still_trusted_until_measured(monkeypatch):
    """``x_host`` 는 실측(``host_eq_xfh``) 전까지 그대로 믿는다 — 쓰기 Origin 검사가 ``request.host`` 를 쓴다."""
    app, captured = _probe_app(monkeypatch, 1)
    app.test_client().get(
        "/probe",
        base_url="http://internal.railway",
        headers={"X-Forwarded-For": CLIENT, "X-Forwarded-Host": PUBLIC_HOST},
    )
    assert captured["host"] == PUBLIC_HOST
