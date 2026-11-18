"""AI 클라이언트 SSL 문맥 — web(gevent 워커)에서만 표준 ``ssl`` 문맥으로(운영 web 2026-11-18 실측 · D253).

SDK 기본 SSL 문맥(truststore)의 소켓은 ``do_handshake(block)`` 을 부르는데 gevent 가 바꾼 ``SSLSocket.do_handshake()`` 는 인자를
받지 않는다 — gevent 로 도는 운영 web 에서 모든 AI 호출이 1초 안에 연결 오류로 죽어 물어보기가 답을 못 했다. 바깥 호출 없음.
"""

from __future__ import annotations

import ssl
import subprocess
import sys

import anthropic
import pytest

from foms.services.cs_agent import brain


def test_worker_process_keeps_the_sdk_default_client(monkeypatch):
    monkeypatch.setenv(brain.KEY_ENV, "sk-test-not-a-real-key")
    monkeypatch.setattr(brain, "_gevent_ssl", lambda: False)
    made = []
    monkeypatch.setattr(anthropic, "DefaultHttpxClient", lambda **kw: made.append(kw))
    client = brain._default_client()  # noqa: SLF001
    try:
        assert isinstance(client, anthropic.Anthropic) and made == []  # 지금 길 그대로 — 우리 쪽 http 클라이언트를 만들지 않는다
    finally:
        client.close()


def test_gevent_process_gets_a_standard_ssl_context(monkeypatch):
    monkeypatch.setenv(brain.KEY_ENV, "sk-test-not-a-real-key")
    monkeypatch.setattr(brain, "_gevent_ssl", lambda: True)
    real, seen = anthropic.DefaultHttpxClient, []

    def spy(**kw):
        seen.append(kw)
        return real(**kw)

    monkeypatch.setattr(anthropic, "DefaultHttpxClient", spy)
    client = brain._default_client()  # noqa: SLF001
    try:
        assert isinstance(client, anthropic.Anthropic) and len(seen) == 1
        context = seen[0]["verify"]
        assert type(context) is ssl.SSLContext  # truststore 문맥(다른 클래스)이 아니다
        assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname is True  # 검증은 그대로 한다
    finally:
        client.close()


def test_gevent_ssl_is_false_here_and_true_in_a_patched_process():
    assert brain._gevent_ssl() is False  # noqa: SLF001 — 시험 · WORKER 프로세스는 gevent 로 바꾸지 않는다
    pytest.importorskip("gevent")  # 개발 PC(Windows)에는 gevent 가 없다 — CI · 운영 이미지에는 있다
    code = ("from gevent import monkey; monkey.patch_all(); "
            "from foms.services.cs_agent import brain; print(brain._gevent_ssl())")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert out.stdout.strip().splitlines()[-1] == "True", out.stderr[-400:]
