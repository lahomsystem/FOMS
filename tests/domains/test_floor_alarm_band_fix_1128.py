"""생산 현장 알람 화면 결함 고침(2026-11-28 실화면 sim-e) — 띠 소리 0회 · 띠가 화면 밖으로 나감 · 보류 풀린 뒤 카드 '보류' 남음.

1. 김재단이 보류 멈춤 창을 안 누른 채 박반장이 보류를 풀면 띠 소리 0회(먼저 누르면 1회). 실측: 서버가 띠를 닫기보다 먼저 보냈고,
   띠 소리는 다른 소리가 울리는 중이면 건너뛴다(urgent-sound.js play). 고침 = 서버 닫기 먼저(test_production_floor_alarm_stops) +
   화면은 닫기를 받는 그 자리에서 이 창의 긴급 창을 뺀다(공용 창 dismiss — 탭 사이 통로는 비동기).
2. 992px 이상 머리 줄은 한 줄로 막혀(nowrap) 띠가 그 줄에 서면 옆으로 밀려 화면 밖(1280 폭 614 ~ 900px 넘침, [확인] 화면 밖).
3. 닫기 · 생산 알람을 받으면 도면 판 받아 오기 한 번(보류 풀림 · 막힘이 30초 받아 오기를 안 기다리게).
틀(가짜 DOM · 소리 기록)은 test_floor_alarm_js 의 것을 그대로 쓴다.
"""

from __future__ import annotations

import re

from tests.domains.test_floor_alarm_js import FLOOR_CSS, _floor, _read, _sound


def test_띠_소리는_다른_소리가_울리는_중이면_건너뛰고_그친_뒤면_울린다() -> None:
    """11-28 띠 소리 0회의 화면 쪽 사슬 — 안 누른 멈춤 소리가 울리는 중에 띠가 오면 건너뛴다(끊지 않음, 설계 그대로).
    그래서 서버는 닫기를 먼저 보내고(test_production_floor_alarm_stops), 화면은 닫기를 받자마자 창 · 소리를 그친다(아래 시험)."""
    r = _sound(r"""
loadSources(); await unlock();
const S = window.FOMSUrgentSound;
S.start('PRODUCTION_FLOOR_STOP_HOLD');
const n = stats.voices.length;
S.play('PRODUCTION_FLOOR_NOTICE_HOLD_RELEASED');
const during = stats.voices.length - n;
S.stop();
S.play('PRODUCTION_FLOOR_NOTICE_HOLD_RELEASED');
out({during, after: last()});
""")
    assert r["during"] == 0
    assert r["after"]["type"] == "triangle" and r["after"]["freqs"] == [660] and r["after"]["len"] == 0.5


def test_서버가_닫으면_이_창의_긴급_창을_바로_빼고_띠_소리는_그_뒤_도면_판은_한_번_받아_온다() -> None:
    """닫기(floor_closed)를 받는 그 자리에서 공용 창의 dismiss 를 부른다 — 탭 사이 통로(BroadcastChannel)는 비동기라 같은 묶음으로 온
    띠보다 늦게 닿을 수 있다(그러면 띠 소리를 건너뛰거나, 울린 띠 소리를 창 닫기의 stop 이 끊는다). 생산 알람 값이면 도면 판 받아 오기를
    한 번(보류 풀림 · 막힘이 30초 받아 오기를 안 기다리게), 생산 알람이 아닌 긴급(음성 대조군)은 안 부른다."""
    r = _floor(r"""
const seq = [];
window.FOMSUrgentAlert.dismiss = (id) => seq.push('dismiss ' + id);
window.FOMSUrgentSound.play = (n) => seq.push('play ' + n);
window.__FOMS_PROD_PARTS_BOUND = {syncTick: (f) => seq.push('sync' + (f === undefined ? '' : ':' + f))};
loadSources(); await flush();
sock.erp_notification({urgent: false, floor_closed: true, notification_ids: [71]});
sock.erp_notification(Object.assign(N(72, 5, '보류가 풀렸어요 — 다시 작업하세요', '정하늘'), {urgent: false, floor_notice: true}));
sock.erp_notification(U(73, 'PRODUCTION_FLOOR_STOP_HOLD', 5, {urgent: true}));
sock.erp_notification({urgent: true, notification_id: 80, notification_type: 'URGENT_CALL', title: '긴급 호출'});
out({seq, posts, shows: shows.map(s => s.notification_id)});
""")
    assert r["seq"] == ["dismiss 71", "sync", "play band", "sync", "sync"]
    assert r["posts"] == [["foms-urgent", {"type": "ack", "notification_id": "71"}]]  # 다른 탭은 지금처럼 통로로
    assert r["shows"] == [73]


def test_띠는_머리_줄_줄_배치_밖에_서고_보일_때만_아래_자리를_비운다() -> None:
    """11-28 실측 결함 — 992px 이상 머리 줄은 한 줄로 막혀(nowrap) 띠가 그 줄에 서면 옆으로 밀려 화면 밖(1280 폭 614 ~ 900px 넘침).
    띠는 줄 배치 밖(absolute)에서 머리 줄 아래 한 줄 전체로 서고, 머리 줄은 띠가 보일 때만 그 높이만큼 아래 여백을 늘린다."""
    css = re.sub(r"/\*.*?\*/", "", _read(FLOOR_CSS), flags=re.S)
    band = re.search(r"\n\.foms-floor-band \{([^}]*)\}", css).group(1)
    assert "position: absolute" in band and "bottom: 8px" in band and "height: var(--foms-floor-band-h, 68px)" in band
    assert "flex: 1 0 100%" not in css and "order: 99" not in css  # 줄바꿈을 가정한 옛 자리
    assert ".foms-prod-home__bar, .foms-prod-page__bar { --foms-floor-band-h: 68px; }" in css
    for bar, gap in (("foms-prod-home__bar", 10), ("foms-prod-page__bar", 8)):  # 머리 줄 아래 여백 8 + 띠 + 그 머리 줄의 줄 틈
        assert (f".{bar}:has(> .foms-floor-band:not([hidden])) {{ padding-bottom: calc(8px + var(--foms-floor-band-h) + {gap}px); }}"
                in css)
    # 띠가 서는 머리 줄은 sticky(띠의 기준 상자) · 992px 이상에서 nowrap 인 채 그대로(띠가 숨으면 머리 줄은 띠 없던 때와 같다)
    home, sheet = _read("static/css/contexts/production/home.css"), _read("static/css/contexts/production/sheet.css")
    assert re.search(r"\.foms-prod-home__bar \{\s*position: sticky;", home) and re.search(r"\.foms-prod-page__bar \{\s*position: sticky;", sheet)
    assert ".foms-prod-home__bar { flex-wrap: nowrap; }" in home and ".foms-prod-page__bar { flex-wrap: nowrap; flex-shrink: 0; }" in sheet
