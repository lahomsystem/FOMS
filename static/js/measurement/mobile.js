(function () {
    'use strict';

    function normalizeText(value) {
        return value == null ? '' : String(value).trim();
    }

    function formatPhone(value) {
        var digits = normalizeText(value).replace(/\D/g, '');
        if (!digits) return '-';
        if (digits.length === 11) return digits.replace(/(\d{3})(\d{4})(\d{4})/, '$1-$2-$3');
        if (digits.length === 10 && digits.slice(0, 2) === '02') return digits.replace(/(\d{2})(\d{4})(\d{4})/, '$1-$2-$3');
        if (digits.length === 10) return digits.replace(/(\d{3})(\d{3})(\d{4})/, '$1-$2-$3');
        if (digits.length === 9 && digits.slice(0, 2) === '02') return digits.replace(/(\d{2})(\d{3})(\d{4})/, '$1-$2-$3');
        return value;
    }

    function buildMapHref(address) {
        return 'https://map.kakao.com/?q=' + encodeURIComponent(normalizeText(address));
    }

    function initMeasurementMobile() {
        var root = document.querySelector('.erp-measurement-dashboard[data-erp-mobile-v2="true"]');
        if (!root) return;

        var measurementApi = window.MeasurementDashboardApi || {};
        var buildSavePayload = typeof measurementApi.buildSavePayload === 'function'
            ? measurementApi.buildSavePayload
            : null;
        if (!buildSavePayload) return;

        var focusOrder = new URLSearchParams(window.location.search).get('focus_order');
        if (focusOrder) {
            var focusCard = root.querySelector('[data-measurement-mobile-order-id="' + focusOrder + '"]');
            if (focusCard) {
                window.requestAnimationFrame(function () {
                    focusCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    focusCard.classList.add('is-focused');
                    window.setTimeout(function () {
                        focusCard.classList.remove('is-focused');
                    }, 2400);
                });
            }
        }

        function getCard(orderId) {
            return root.querySelector('[data-measurement-mobile-order-id="' + orderId + '"]');
        }

        function setStatus(card, message, isError) {
            var statusEl = card ? card.querySelector('[data-measurement-mobile-manager-status]') : null;
            if (!statusEl) return;
            statusEl.textContent = message || '';
            statusEl.classList.toggle('is-error', !!isError);
            statusEl.classList.toggle('is-success', !!message && !isError);
        }

        function syncManagerBadge(card, value) {
            var badge = card ? card.querySelector('[data-measurement-mobile-manager]') : null;
            var detailValue = card ? card.querySelector('[data-measurement-mobile-detail-manager]') : null;
            var visibleValue = card ? card.querySelector('[data-queue-card-field="manager"]') : null;
            if (badge) {
                badge.textContent = value || '담당 미지정';
                badge.classList.toggle('is-unassigned', !value);
            }
            if (detailValue) {
                detailValue.textContent = value || '-';
            }
            if (visibleValue) {
                var callLink = visibleValue.querySelector('[data-queue-card-call-link]');
                if (callLink) {
                    callLink.textContent = value || '-';
                } else {
                    visibleValue.textContent = value || '-';
                }
            }
        }

        function syncDesktopField(orderId, field, value) {
            var row = document.querySelector('tr.measurement-row[data-order-id="' + orderId + '"]');
            if (!row) return;

            if (field === 'manager') {
                var managerCell = row.querySelector('td.manager-cell');
                if (managerCell) managerCell.textContent = value || '-';
                row.dataset.manager = value || '';
                if (typeof window.scheduleApplyMeasurementManagerSortAndColors === 'function') {
                    window.scheduleApplyMeasurementManagerSortAndColors({ focusRow: row });
                }
                return;
            }

            var cell = row.querySelector('td[data-field="' + field + '"]');
            if (cell) {
                cell.textContent = field === 'phone' ? formatPhone(value) : (value || '-');
            }
        }

        function syncCardField(card, field, value) {
            if (!card) return;
            card.dataset[field] = value || '';

            if (field === 'manager') {
                syncManagerBadge(card, value);
                return;
            }

            if (field === 'phone') {
                var phoneNodes = card.querySelectorAll('[data-measurement-mobile-field="phone"]');
                phoneNodes.forEach(function (node) {
                    node.textContent = formatPhone(value);
                });
                card.querySelectorAll('[data-queue-card-field="phone"]').forEach(function (node) {
                    var callLink = node.querySelector('[data-queue-card-call-link]');
                    if (callLink) {
                        callLink.textContent = formatPhone(value);
                        if (value) {
                            callLink.setAttribute('href', 'tel:' + normalizeText(value).replace(/\D/g, ''));
                        }
                    } else {
                        node.textContent = formatPhone(value);
                    }
                });
                card.querySelectorAll('[data-measurement-mobile-call-link]').forEach(function (callLink) {
                    if (value) {
                        callLink.setAttribute('href', 'tel:' + normalizeText(value).replace(/\D/g, ''));
                    }
                });
            }

            if (field === 'address') {
                var addressNodes = card.querySelectorAll('[data-measurement-mobile-field="address"]');
                addressNodes.forEach(function (node) {
                    node.textContent = value || '-';
                });
                card.querySelectorAll('[data-queue-card-field="address"]').forEach(function (node) {
                    var mapLink = node.querySelector('[data-queue-card-map-link]');
                    if (mapLink) {
                        mapLink.textContent = value || '-';
                        if (value) mapLink.setAttribute('href', buildMapHref(value));
                    } else {
                        node.textContent = value || '-';
                    }
                });
                card.querySelectorAll('[data-measurement-mobile-map-link]').forEach(function (link) {
                    if (value) link.setAttribute('href', buildMapHref(value));
                });
            }

            card.querySelectorAll('[data-measurement-mobile-edit-trigger][data-field="' + field + '"]').forEach(function (trigger) {
                trigger.dataset.currentValue = value || '';
            });
        }

        async function saveField(orderId, isErp, field, value) {
            var payload = buildSavePayload(field, orderId, isErp, value);
            var response = await fetch(payload.url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'same-origin',
                body: JSON.stringify(payload.body)
            });
            var contentType = response.headers.get('Content-Type') || '';
            var data = contentType.indexOf('application/json') >= 0
                ? await response.json()
                : { success: false, message: '응답 형식을 확인할 수 없습니다.' };
            if (!data.success) {
                throw new Error(data.message || data.error || '저장에 실패했습니다.');
            }
        }

        var selects = Array.from(root.querySelectorAll('[data-measurement-mobile-manager-select]'));
        selects.forEach(function (select) {
            select.addEventListener('change', async function () {
                var orderId = select.dataset.orderId;
                var isErp = select.dataset.isErp === 'true';
                var prevValue = select.dataset.currentValue || '';
                var nextValue = normalizeText(select.value);
                var card = select.closest('.erp-measurement-mobile-card');

                if (!orderId || nextValue === prevValue) {
                    return;
                }

                select.disabled = true;
                setStatus(card, '담당자를 저장하는 중입니다...', false);

                try {
                    await saveField(orderId, isErp, 'manager', nextValue);
                    select.dataset.currentValue = nextValue;
                    syncCardField(card, 'manager', nextValue);
                    syncDesktopField(orderId, 'manager', nextValue);
                    setStatus(card, '담당자 배정이 저장되었습니다.', false);
                } catch (error) {
                    select.value = prevValue;
                    setStatus(card, String((error && error.message) || error || '저장 중 오류가 발생했습니다.'), true);
                } finally {
                    select.disabled = false;
                }
            });
        });

        var editSheetEl = document.getElementById('erp-measurement-mobile-edit-sheet');
        if (!editSheetEl || typeof bootstrap === 'undefined') return;

        var editForm = editSheetEl.querySelector('[data-measurement-mobile-edit-form]');
        var editLabel = editSheetEl.querySelector('[data-measurement-mobile-edit-label]');
        var editHint = editSheetEl.querySelector('[data-measurement-mobile-edit-hint]');
        var editError = editSheetEl.querySelector('[data-measurement-mobile-edit-error]');
        var editInput = editForm.querySelector('input[name="value"]');
        var editOrderIdInput = editForm.querySelector('input[name="order_id"]');
        var editFieldInput = editForm.querySelector('input[name="field"]');
        var editIsErpInput = editForm.querySelector('input[name="is_erp"]');
        var editSelect = editForm.querySelector('[data-measurement-mobile-manager-select-sheet]');
        var editSubmit = editSheetEl.querySelector('[data-measurement-mobile-edit-submit]');
        var editSheet = bootstrap.Offcanvas.getOrCreateInstance(editSheetEl);
        var activeTrigger = null;

        function setEditError(message) {
            editError.textContent = message || '';
            editError.classList.toggle('d-none', !message);
        }

        function setEditLoading(isLoading) {
            editSubmit.disabled = isLoading;
            editInput.disabled = isLoading;
            editSelect.disabled = isLoading;
            editSubmit.textContent = isLoading ? '저장 중...' : '저장';
        }

        function showInput(type, placeholder) {
            editInput.type = type || 'text';
            editInput.placeholder = placeholder || '';
            editInput.classList.remove('d-none');
            editSelect.classList.add('d-none');
        }

        function showSelect(currentValue) {
            editSelect.value = currentValue || '';
            editInput.classList.add('d-none');
            editSelect.classList.remove('d-none');
        }

        function openEditSheet(trigger) {
            activeTrigger = trigger;
            var field = trigger.dataset.field;
            var currentValue = trigger.dataset.currentValue || '';

            editOrderIdInput.value = trigger.dataset.orderId || '';
            editFieldInput.value = field;
            editIsErpInput.value = trigger.dataset.isErp || 'false';
            editInput.value = currentValue;
            setEditError('');

            if (field === 'phone') {
                editLabel.textContent = '연락처';
                editHint.textContent = '숫자와 하이픈 모두 입력할 수 있습니다.';
                showInput('tel', '010-0000-0000');
            } else if (field === 'address') {
                editLabel.textContent = '주소';
                editHint.textContent = '저장하면 주소 지오코딩이 다시 예약됩니다.';
                showInput('text', '주소를 입력하세요');
            } else {
                editLabel.textContent = '담당자';
                editHint.textContent = '실측 담당자를 빠르게 변경합니다.';
                showSelect(currentValue);
            }

            editSheet.show();
        }

        root.querySelectorAll('[data-measurement-mobile-edit-trigger]').forEach(function (trigger) {
            trigger.addEventListener('click', function () {
                openEditSheet(trigger);
            });
        });

        editSheetEl.addEventListener('hidden.bs.offcanvas', function () {
            activeTrigger = null;
            editForm.reset();
            editInput.classList.remove('d-none');
            editSelect.classList.add('d-none');
            setEditLoading(false);
            setEditError('');
        });

        editForm.addEventListener('submit', async function (event) {
            event.preventDefault();
            if (!activeTrigger) return;

            var orderId = editOrderIdInput.value;
            var field = editFieldInput.value;
            var isErp = editIsErpInput.value === 'true';
            var nextValue = editSelect.classList.contains('d-none')
                ? normalizeText(editInput.value)
                : normalizeText(editSelect.value);
            var card = getCard(orderId);

            setEditLoading(true);
            setEditError('');

            try {
                await saveField(orderId, isErp, field, nextValue);
                syncCardField(card, field, nextValue);
                syncDesktopField(orderId, field, nextValue);
                editSheet.hide();
            } catch (error) {
                setEditError(String((error && error.message) || error || '저장 중 오류가 발생했습니다.'));
            } finally {
                setEditLoading(false);
            }
        });
    }

    // entry 동적 로드 대응 readyState 분기 + fragment 스왑 재초기화(모든 리스너 root/시트 스코프라 per-DOM).
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initMeasurementMobile);
    } else {
        initMeasurementMobile();
    }
    if (!window.__FOMS_MEAS_MOBILE_BOUND) {
        window.__FOMS_MEAS_MOBILE_BOUND = true;
        document.addEventListener('foms:erp-shell-fragment-swapped', initMeasurementMobile);
    }
})();
