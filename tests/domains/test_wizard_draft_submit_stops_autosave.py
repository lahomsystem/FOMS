"""등록 성공 뒤 초안이 되살아나지 않는다 (WIZ-SEND-01 후속).

증상: 마법사에서 주문을 등록하면 초안 행이 서버에서 지워지는데, 곧바로 이어지는
페이지 이동의 ``pagehide`` keepalive 저장이 같은 draft_key 로 PUT 을 한 번 더 쏜다.
``upsert_draft`` 는 없으면 INSERT 라 방금 지운 초안이 되살아난다 — 주문을 등록할
때마다 유령 초안이 1건씩 쌓였다.

근본 원인은 "제출이 끝났는데 자동저장이 계속 살아 있다"는 것이므로, 저장 경로를
막는 게 아니라 **제출 성공을 클라이언트가 알고 저장을 끄게** 한다.

계약은 두 겹이다. 소스 계약은 진입점 4곳(flush·scheduleSave·keepaliveSave·submitOrder)
이 그대로 있는지를 보고, node 가 있는 환경에서는 실제로 fetch 를 세어 회귀를 잡는다.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DRAFT_JS = ROOT / "static/js/foms/draft.js"


def test_submit_success_closes_every_autosave_path() -> None:
    """제출 성공 표시가 저장 진입점 4곳 모두를 닫는다(한 곳만 막으면 새어 나간다)."""
    js = DRAFT_JS.read_text(encoding="utf-8")
    # 제출 성공 시에만 표시한다 — 실패한 제출은 초안을 계속 지켜야 한다.
    assert "if (res.ok && data && data.success)" in js
    assert "self._markSubmitted()" in js
    # 진입점 4곳.
    assert "if (!self.draftKey || self._submitted)" in js, "flush·keepaliveSave 가드"
    assert js.count("if (!self.draftKey || self._submitted)") == 2
    assert "if (self._submitted) {" in js, "scheduleSave 가드"
    # 남은 예약도 끈다(디바운스·idle 타이머가 살아 있으면 그대로 되살린다).
    assert "clearTimeout(this._debounceTimer)" in js
    assert "clearTimeout(this._idleTimer)" in js


def test_shell_pins_bumped_draft_js() -> None:
    """draft.js 를 고쳤으므로 `?v=` 핀이 올라가 있어야 한다(SW staticCacheFirst)."""
    shell = (ROOT / "templates/orders/wizard/wizard_shell.html").read_text(encoding="utf-8")
    assert "js/foms/draft.js') }}?v=20260901a" not in shell, "draft.js 핀 미범프"
    assert "js/foms/draft.js') }}?v=2026" in shell


@pytest.mark.skipif(shutil.which("node") is None, reason="node 없음 — 소스 계약만 검증")
def test_no_put_after_successful_submit_in_node() -> None:
    """실제 거동: 제출 성공 뒤 flush·keepalive 를 불러도 PUT 이 0 회다."""
    harness = textwrap.dedent(
        """
        global.window = {};
        global.document = { addEventListener: function () {} };
        global.navigator = { onLine: true };

        var puts = 0;
        var submits = 0;
        global.fetch = function (url, opts) {
          var method = (opts && opts.method) || "GET";
          if (method === "PUT") { puts += 1; }
          if (String(url).indexOf("/submit") !== -1) { submits += 1; }
          return Promise.resolve({
            ok: true,
            json: function () {
              return Promise.resolve({ success: true, updated_at: "2026-09-02T00:00:00" });
            },
          });
        };

        require(DRAFT_JS_PATH);
        var Client = global.window.FomsDraftClient;
        var root = { getAttribute: function () { return "new.abcdef"; } };
        var client = new Client(root, {
          getPayload: function () { return { schema_version: 1, step: 4, data: {} }; },
          getStep: function () { return 4; },
        });

        client.flush().then(function () {
          var before = puts;
          return client.submitOrder().then(function () {
            // 등록 성공 뒤 이탈 시점 저장이 다시 시도되는 상황.
            client.scheduleSave();
            return client.flush().then(function () {
              console.log(JSON.stringify({
                puts_before_submit: before,
                puts_after_submit: puts - before,
                submits: submits,
              }));
              // 수정 전 코드는 idle 타이머(5분)를 남겨 프로세스가 안 끝난다.
              // 대조군에서 "빨강" 대신 "행"이 되지 않도록 여기서 명시적으로 끝낸다.
              process.exit(0);
            });
          });
        });
        """
    ).replace("DRAFT_JS_PATH", json.dumps(str(DRAFT_JS)))

    result = subprocess.run(
        ["node", "-e", harness], capture_output=True, text=True, timeout=60, cwd=str(ROOT)
    )
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout.strip().splitlines()[-1])
    assert out["puts_before_submit"] == 1, "제출 전에는 정상 저장돼야 한다"
    assert out["submits"] == 1
    assert out["puts_after_submit"] == 0, "제출 성공 뒤 PUT 이 나갔다 — 초안이 되살아난다"
