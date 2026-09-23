/**
 * 실측 모바일 통합 목록 — 줄을 누르면 바텀시트로 그 주문 카드를 보여 준다.
 * 스펙: docs/specs/2026-09-23-measurement-mobile-unified-list_SPEC.md §3
 *
 * 카드를 새로 그리지 않는다: 숨은 원본 칸(data-meas-card-origin)의 카드 노드(id="meas-card-N",
 * render_queue_card_v2 결과)를 시트로 옮겼다가 닫을 때 제자리(주석 표식 자리)로 돌려놓는다.
 * 노드를 옮기므로 실측 완료 버튼·전화/지도 링크·타임라인·사진 미리보기 리스너가 그대로 산다.
 *
 * - 머리: "김OO 담당" + "2 / 4" + 이전·다음(같은 담당, 목록 순서) + 닫기.
 * - "실측 체크" 토글 = 그 줄의 체크 칸을 대신 누른다(같은 API). 상태는 foms:meas-glance:visit 로 따라간다.
 * - 뒤로 가기 = 시트 닫기: 열 때 history.pushState({measSheet}), popstate 로 닫는다. 셸(erp-shell.js)의
 *   popstate 가 같은 주소로 화면을 다시 읽지 않게, 시트 기록과 그 바로 앞 기록에 fomsShellKeep 표식을
 *   달고(셸이 건너뛴다) 시트를 닫은 뒤 앞 기록의 표식을 지운다.
 *   사진 미리보기(GlobalImageViewer)는 history 를 쓰지 않는다 — 열려 있으면 뒤로 가기가 미리보기만 닫는다.
 * - ?focus_order=N 딥링크: 그 담당 묶음을 펼치고 줄로 스크롤한 뒤 시트를 연다.
 */
(function () {
    'use strict';
    if (window.__FOMS_MEAS_GLANCE_SHEET_BOUND) return;
    window.__FOMS_MEAS_GLANCE_SHEET_BOUND = true;

    var OPEN_CLASS = 'foms-meas-sheet-open';
    var st = { id: null, card: null, marker: null, pushed: false, expectPop: false };

    function parts() { return window.FomsMeasSheetParts; }
    function sheetEl() { return document.querySelector('[data-meas-sheet]'); }
    function rowOf(id) { return document.querySelector('[data-meas-glance-row="' + String(id).replace(/"/g, '') + '"]'); }
    function inRow(id, sel) {
        var row = rowOf(id);
        return row ? row.querySelector(sel) : null;
    }
    function rowCheck(id) { return inRow(id, '[data-meas-visit-toggle]'); }
    function goOf(id) { return inRow(id, '[data-meas-glance-go]'); }
    function managerOf(row) {
        var grp = row && row.closest('[data-meas-glance-grp]');
        return grp ? grp.getAttribute('data-meas-glance-grp') || '' : '';
    }
    /** 같은 담당의 줄 전부(목록 순서). 한 담당이 두 묶음으로 갈려도 이어서 센다. */
    function siblingsOf(row) {
        var name = managerOf(row);
        var sec = row.closest('[data-meas-glance]');
        return Array.prototype.filter.call(sec.querySelectorAll('[data-meas-glance-row]'), function (r) {
            return managerOf(r) === name;
        });
    }

    function viewerOpen() {
        var v = document.getElementById('global-image-viewer');
        return !!v && v.style.display !== 'none' && v.getAttribute('aria-hidden') !== 'true';
    }
    function focusClose(sheet) {
        var btn = sheet && sheet.querySelector('.foms-meas-sheet__ibtn[data-meas-sheet-close]');
        if (btn) btn.focus({ preventScroll: true });
    }

    function syncCheck() {
        var sheet = sheetEl();
        var vc = sheet && sheet.querySelector('[data-meas-sheet-check]');
        if (!vc || !st.id) return;
        var btn = rowCheck(st.id);
        var on = !!btn && btn.getAttribute('aria-pressed') === 'true';
        vc.setAttribute('aria-pressed', on ? 'true' : 'false');
        vc.disabled = !btn || btn.disabled;
        var label = vc.querySelector('[data-meas-sheet-check-state]');
        if (label) label.textContent = on ? '다녀옴' : '아직';
    }

    /** 카드·체크 토글을 제자리로. */
    function putBack() {
        var sheet = sheetEl();
        var vc = sheet && sheet.querySelector('[data-meas-sheet-check]');
        var body = sheet && sheet.querySelector('[data-meas-sheet-body]');
        var slot = sheet && sheet.querySelector('[data-meas-sheet-slot]');
        if (vc && body && slot) body.insertBefore(vc, slot);
        if (st.card && st.marker && st.marker.parentNode) {
            st.marker.parentNode.insertBefore(st.card, st.marker);
            st.marker.parentNode.removeChild(st.marker);
        }
        var go = st.id ? goOf(st.id) : null;
        if (go) go.classList.remove('is-open');
        st.card = null;
        st.marker = null;
    }

    function fillBar(sheet, row) {
        var sibs = siblingsOf(row);
        var i = sibs.indexOf(row);
        var mgr = sheet.querySelector('[data-meas-sheet-mgr]');
        if (mgr) mgr.textContent = managerOf(row) + ' 담당';
        var pos = sheet.querySelector('[data-meas-sheet-pos]');
        if (pos) pos.textContent = (i + 1) + ' / ' + sibs.length;
        var prev = sheet.querySelector('[data-meas-sheet-step="-1"]');
        var next = sheet.querySelector('[data-meas-sheet-step="1"]');
        if (prev) prev.disabled = i <= 0;
        if (next) next.disabled = i < 0 || i >= sibs.length - 1;
    }

    /** 시트에 그 주문 카드를 보인다(기록은 건드리지 않는다). */
    function show(id, opts) {
        opts = opts || {};
        id = String(id);
        var sheet = sheetEl();
        var row = rowOf(id);
        var card = document.getElementById('meas-card-' + id);
        if (!sheet || !row || !card) return false;
        if (st.id !== id) {
            putBack();
            var marker = document.createComment('meas-card-' + id);
            card.parentNode.insertBefore(marker, card);
            var slot = sheet.querySelector('[data-meas-sheet-slot]');
            slot.appendChild(card);
            // 체크 토글·사진 칸(이미지 없으면 숨김)·넘김 표시 배치는 mobile-glance-sheet-parts.js.
            parts().decorate(card, sheet);
            st.card = card;
            st.marker = marker;
            st.id = id;
            var body = sheet.querySelector('[data-meas-sheet-body]');
            if (body) body.scrollTop = 0;
        }
        var go = goOf(id);
        if (go) go.classList.add('is-open');
        fillBar(sheet, row);
        syncCheck();
        sheet.hidden = false;
        document.documentElement.classList.add(OPEN_CLASS);
        parts().setInert(sheet, true);
        if (opts.focus !== false) focusClose(sheet);
        return true;
    }

    // 기록 도우미(stateWith·keepBase·unkeep·dropFocusParam)는 mobile-glance-sheet-parts.js.
    function stateWith(id) { return parts().stateWith(id); }
    function keepBase() { parts().keepBase(); }
    function unkeep() { parts().unkeep(); }

    function open(id) {
        var wasOpen = !!st.id;
        if (!show(id)) return false;
        try {
            if (!wasOpen) keepBase();
            window.history[wasOpen ? 'replaceState' : 'pushState'](stateWith(id), '');
            st.pushed = true;
        } catch (e) {
            st.pushed = false; // 기록 실패: 뒤로 가기로는 못 닫고 닫기 버튼만 쓴다
        }
        return true;
    }

    function close(fromPop) {
        var sheet = sheetEl();
        if (!st.id) return;
        var id = st.id;
        putBack();
        st.id = null;
        if (sheet) sheet.hidden = true;
        document.documentElement.classList.remove(OPEN_CLASS);
        parts().setInert(sheet, false);
        // 이전·다음으로 다른 묶음(접힘·다른 탭)의 줄에 왔을 수 있다 — 그 줄이 보이게 한 뒤 초점.
        var api = window.FomsMeasGlance || {};
        if (typeof api.reveal === 'function') api.reveal(id, { scroll: false });
        var go = goOf(id);
        if (go) {
            go.focus({ preventScroll: true });
            go.scrollIntoView({ block: 'nearest' });
        }
        if (!fromPop && st.pushed && window.history.state && window.history.state.measSheet) {
            st.expectPop = true;
            window.history.back();
        }
        st.pushed = false;
    }

    function step(dir) {
        var row = st.id ? rowOf(st.id) : null;
        if (!row) return;
        var sibs = siblingsOf(row);
        var next = sibs[sibs.indexOf(row) + dir];
        if (!next) return;
        var id = next.getAttribute('data-meas-glance-row');
        show(id, { focus: false });
        if (st.pushed) {
            try { window.history.replaceState(stateWith(id), ''); } catch (e) { /* 무시 */ }
        }
        var active = document.activeElement;
        if (!active || active.disabled || active === document.body) focusClose(sheetEl());
    }

    document.addEventListener('click', function (e) {
        var t = e.target;
        if (!t || typeof t.closest !== 'function') return;
        var go = t.closest('[data-meas-glance-go]');
        if (go) {
            if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.shiftKey) return;
            e.preventDefault();
            open(go.getAttribute('data-meas-glance-go'));
            return;
        }
        if (!st.id || !t.closest('[data-meas-sheet]')) return;
        if (t.closest('[data-meas-sheet-close]')) {
            e.preventDefault();
            close(false);
            return;
        }
        var stepBtn = t.closest('[data-meas-sheet-step]');
        if (stepBtn) {
            if (!stepBtn.disabled) step(Number(stepBtn.getAttribute('data-meas-sheet-step')) || 0);
            return;
        }
        if (t.closest('[data-meas-sheet-check]')) {
            var btn = rowCheck(st.id);
            if (btn && !btn.disabled) btn.click();
        }
    });

    document.addEventListener('foms:meas-glance:visit', function (e) {
        if (st.id && e.detail && String(e.detail.orderId) === st.id) syncCheck();
    });

    // 캡처 단계: 사진 미리보기의 Esc 처리(document 버블)보다 먼저 보고, 미리보기가 열려 있으면 시트는 그대로 둔다.
    document.addEventListener('keydown', function (e) {
        if (e.key !== 'Escape' || !st.id || viewerOpen()) return;
        if (document.querySelector('.offcanvas.show, .modal.show')) return;
        close(false);
    }, true);

    // 셸(erp-shell.js)의 popstate 는 fomsShellKeep 표식을 보고 건너뛴다. 여기서 시트를 닫고 표식을 지운다.
    window.addEventListener('popstate', function (e) {
        var state = e.state;
        if (st.expectPop) {
            st.expectPop = false;
            unkeep();
            return;
        }
        if (st.id) {
            if (viewerOpen()) {
                // 맨 위 층(미리보기)만 닫고 시트 기록은 되살린다.
                if (window.GlobalImageViewer && typeof window.GlobalImageViewer.close === 'function') {
                    window.GlobalImageViewer.close();
                }
                try { window.history.pushState(stateWith(st.id), ''); } catch (err) { st.pushed = false; }
                return;
            }
            if (state && state.measSheet) {
                show(state.measSheet, { focus: false });
            } else {
                close(true);
                unkeep();
            }
            return;
        }
        // 앞으로 가기로 시트 기록에 다시 들어왔다.
        if (state && state.measSheet && show(state.measSheet)) st.pushed = true;
    });

    function init() {
        // 프래그먼트 스왑으로 열린 시트가 통째로 사라졌으면 상태를 비운다.
        if (st.id && (!st.card || !document.documentElement.contains(st.card))) {
            st = { id: null, card: null, marker: null, pushed: false, expectPop: false };
            document.documentElement.classList.remove(OPEN_CLASS);
        }
        var sec = document.querySelector('[data-meas-glance]');
        if (!sec || sec.__fomsMeasSheetInit) return;
        sec.__fomsMeasSheetInit = true;
        // 새로고침 뒤 시트 기록 위에 있으면 그 시트를 되살린다(뒤로 가기가 헛돌지 않게). 줄이 없으면 기록만 정리.
        var hs = window.history.state;
        if (hs && typeof hs === 'object' && hs.measSheet && !st.id) {
            if (show(hs.measSheet)) st.pushed = true;
            else unkeep();
        }
        var api = window.FomsMeasGlance || {};
        var restored = api.restoredOrderId;
        delete api.restoredOrderId;
        var focus = '';
        try { focus = new URLSearchParams(window.location.search).get('focus_order') || ''; } catch (e) { focus = ''; }
        // 실측 완료 뒤 새로 읽기(제자리 복원)면 시트를 다시 열지 않는다 — 줄로 돌아온 것으로 충분하다.
        if (st.id || !/^\d+$/.test(focus) || restored || !rowOf(focus)) return;
        parts().dropFocusParam();
        if (typeof api.reveal === 'function') api.reveal(focus, { flash: true });
        open(focus);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
    document.addEventListener('foms:erp-shell-fragment-swapped', init);
})();
