/**
 * 실측 이미지 저장 시트(모바일) — 만든 PNG 를 휴대폰 사진첩(아이폰 사진 앱 · 안드로이드 갤러리)에 넣는다.
 *
 * 왜 시트를 한 번 더 띄우나:
 *  - 공유(navigator.share)는 "방금 누른" 탭 효력(크롬 약 5초, 사파리는 더 짧을 수 있음)이 있어야 열린다.
 *    휴대폰에서 html2canvas 캡처·PNG 인코딩이 그 시간을 넘기면 NotAllowedError 로 조용히 막혔다.
 *    그래서 이미지를 **먼저 다 만든 뒤** 이 시트의 버튼 클릭 안에서 **첫 동작으로** 저장을 부른다.
 *  - 아이폰: 사진 앱에 넣는 길은 공유 창의 "이미지 저장"과 길게 눌러 "사진 앱에 추가" 둘뿐이다.
 *    <a download> 는 "파일" 앱으로 가고, 홈 화면 앱(PWA)에서는 아예 동작하지 않는다(WebKit 236943·275288).
 *  - 안드로이드: 공유 창에 "갤러리에 저장" 대상이 없다. <a download>(blob) 이 Download 폴더에 저장하고,
 *    갤러리의 "Download" 앨범에 보인다. 공유는 보조 버튼(카카오톡 등 보내기)으로만 둔다.
 *
 * 전역: window.FomsMeasSaveSheet.open({ file: File, downloadName: string })
 */
(function () {
    'use strict';
    if (window.FomsMeasSaveSheet) return;

    const ROOT_ID = 'foms-meas-save-sheet';
    const ua = navigator.userAgent || '';
    const IS_IOS = /iPhone|iPad|iPod/i.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    const IS_ANDROID = /Android/i.test(ua);
    // 앱 안 브라우저(카카오톡·안드로이드 웹뷰)는 blob 다운로드가 조용히 실패하고 공유도 없다.
    const IS_INAPP = /KAKAOTALK/i.test(ua) || (IS_ANDROID && /; wv\)/.test(ua));

    let current = null;

    function canShareFile(file) {
        try {
            return !!(navigator.share && navigator.canShare && navigator.canShare({ files: [file] }));
        } catch (e) {
            return false;
        }
    }

    function el(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text) node.textContent = text;
        return node;
    }

    function setMsg(text, tone) {
        if (!current) return;
        current.msg.textContent = text || '';
        current.msg.hidden = !text;
        current.msg.dataset.tone = tone || 'info';
    }

    /** 안드로이드·PC: blob 주소로 내려받는다(data: 주소는 크롬 2MB 한도에 걸려 조용히 실패할 수 있다). */
    function downloadBlob(file, name) {
        const link = document.createElement('a');
        link.href = current.url;
        link.download = name;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    }

    /** 공유 창. 반드시 클릭 핸들러의 첫 동작으로 부른다(앞에 await 를 두면 탭 효력이 사라진다). */
    function shareFile(file, doneText) {
        if (current.busy) return; // 공유 창이 뜨는 중 두 번 누르면 InvalidStateError — 무시한다.
        current.busy = true;
        const state = current;
        navigator.share({ files: [file] }).then(function () {
            setMsg(doneText, 'ok');
        }).catch(function (err) {
            const name = err && err.name;
            if (name === 'AbortError' || name === 'InvalidStateError') return; // 닫음·겹침 — 실패가 아니다.
            if (name === 'NotAllowedError') {
                setMsg('한 번 더 눌러 주세요.', 'warn');
                return;
            }
            setMsg(IS_IOS
                ? '저장하지 못했어요. 위 사진을 길게 눌러 "사진 앱에 추가"를 눌러 주세요.'
                : '저장하지 못했어요. 위 사진을 길게 눌러 "이미지 저장"을 눌러 주세요.', 'warn');
        }).then(function () {
            state.busy = false;
        });
    }

    function onPrimary() {
        if (!current) return;
        const file = current.file;
        if (IS_IOS) {
            if (canShareFile(file)) {
                shareFile(file, '공유 창에서 "이미지 저장"을 누르면 사진 앱에 들어가요.');
            } else {
                setMsg('이 화면에서는 바로 저장이 안 돼요. 위 사진을 길게 눌러 "사진 앱에 추가"를 눌러 주세요.', 'warn');
            }
            return;
        }
        if (IS_INAPP) {
            setMsg('이 앱 안에서는 바로 저장이 안 돼요. 위 사진을 길게 눌러 "이미지 저장"을 누르거나, 크롬·삼성 인터넷으로 열어 주세요.', 'warn');
            return;
        }
        if (current.busy) return; // 두 번 누르면 "(1)" 사본이 생긴다.
        current.busy = true;
        const state = current;
        downloadBlob(file, current.downloadName);
        setTimeout(function () { state.busy = false; }, 1500);
        setMsg(IS_ANDROID
            ? '저장을 시작했어요. 갤러리의 "Download(다운로드)" 앨범에서 볼 수 있어요. 안 보이면 사진을 길게 눌러 주세요.'
            : '다운로드 폴더에 저장했어요.', 'ok');
    }

    function onShare() {
        if (!current) return;
        shareFile(current.file, '');
    }

    function close() {
        if (!current) return;
        const state = current;
        current = null;
        document.removeEventListener('keydown', onKey, true);
        if (state.root.parentNode) state.root.parentNode.removeChild(state.root);
        document.documentElement.classList.remove('foms-meas-save-sheet-open');
        // 공유·다운로드가 파일을 비동기로 읽는다 — 바로 해제하면 저장이 빈 파일이 될 수 있다.
        setTimeout(function () { URL.revokeObjectURL(state.url); }, 60000);
        if (state.returnFocus && state.returnFocus.focus) {
            try { state.returnFocus.focus(); } catch (e) { /* 이미 사라진 버튼 */ }
        }
    }

    function onKey(e) {
        if (e.key === 'Escape') close();
    }

    function open(opts) {
        close();
        const file = opts.file;
        const url = URL.createObjectURL(file);

        const root = el('div', 'foms-meas-save-sheet');
        root.id = ROOT_ID;
        root.setAttribute('role', 'dialog');
        root.setAttribute('aria-modal', 'true');
        root.setAttribute('aria-labelledby', ROOT_ID + '-title');

        const card = el('div', 'foms-meas-save-sheet__card');
        const title = el('h2', 'foms-meas-save-sheet__title', '이미지가 준비됐어요');
        title.id = ROOT_ID + '-title';

        const frame = el('div', 'foms-meas-save-sheet__frame');
        const img = el('img', 'foms-meas-save-sheet__img');
        img.src = url;
        img.alt = opts.downloadName || '실측 일정 이미지';
        frame.appendChild(img);

        const primary = el('button', 'foms-meas-save-sheet__btn foms-meas-save-sheet__btn--primary',
            IS_IOS ? '사진 앱에 저장' : (IS_INAPP ? '저장 방법 보기' : (IS_ANDROID ? '갤러리에 저장' : '이미지 다운로드')));
        primary.type = 'button';
        primary.addEventListener('click', onPrimary);

        const acts = el('div', 'foms-meas-save-sheet__acts');
        acts.appendChild(primary);
        if (!IS_IOS && canShareFile(file)) {
            const share = el('button', 'foms-meas-save-sheet__btn', '카카오톡 등으로 보내기');
            share.type = 'button';
            share.addEventListener('click', onShare);
            acts.appendChild(share);
        }

        const hint = el('p', 'foms-meas-save-sheet__hint', IS_IOS
            ? '안 되면 위 사진을 길게 눌러 "사진 앱에 추가"를 누르세요.'
            : '안 되면 위 사진을 길게 눌러 "이미지 저장"을 누르세요.');
        const msg = el('p', 'foms-meas-save-sheet__msg');
        msg.setAttribute('role', 'status');
        msg.setAttribute('aria-live', 'polite');
        msg.hidden = true;

        const closeBtn = el('button', 'foms-meas-save-sheet__close', '닫기');
        closeBtn.type = 'button';
        closeBtn.addEventListener('click', close);

        card.appendChild(title);
        card.appendChild(frame);
        card.appendChild(acts);
        card.appendChild(msg);
        card.appendChild(hint);
        card.appendChild(closeBtn);
        root.appendChild(card);
        root.addEventListener('click', function (e) {
            if (e.target === root) close();
        });

        current = {
            root: root, msg: msg, file: file, url: url,
            downloadName: opts.downloadName || file.name,
            busy: false,
            returnFocus: opts.returnFocus || null
        };
        document.body.appendChild(root);
        document.documentElement.classList.add('foms-meas-save-sheet-open');
        document.addEventListener('keydown', onKey, true);
        try { primary.focus(); } catch (e) { /* 포커스 불가 환경 */ }
    }

    window.FomsMeasSaveSheet = { open: open, close: close };
})();
