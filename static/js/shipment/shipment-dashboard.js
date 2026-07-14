// Shipment 대시보드 모듈 (Batch 5: dashboard_main.html inline → static 이동, verbatim).
// erp-shell activateScripts가 fragment swap마다 이 src를 재실행한다(기존 inline과 동일 동작).
// Jinja 게이트(can_edit_shipment)·주입값(selected_date)은 #shipment-dashboard-config의 data-*로 전달한다.
var __shipDashCfgEl = document.getElementById('shipment-dashboard-config');
var __shipDashCanEdit = !!(__shipDashCfgEl && __shipDashCfgEl.dataset.canEdit === 'true');
var __shipDashSelectedDate = (__shipDashCfgEl && __shipDashCfgEl.dataset.selectedDate) || '';

    (function () {
      const STORAGE_KEYS = {
        construction_time: 'erp_shipment_construction_time_list',
        drawing_manager: 'erp_shipment_drawing_manager_list',
        construction_workers: 'erp_shipment_construction_workers_list',
        site_extra: 'erp_shipment_site_extra_list',
        vehicle: 'erp_shipment_vehicle_list',
        trip: 'erp_shipment_trip_list'
      };
      const MAX_SAVED = 20;

      function loadSavedList(key) {
        try {
          const raw = localStorage.getItem(key);
          if (!raw) return [];
          const arr = JSON.parse(raw);
          return Array.isArray(arr) ? arr : [];
        } catch (e) { return []; }
      }

      function saveToList(key, value) {
        if (!value || !value.trim()) return;
        let arr = loadSavedList(key);
        arr = [value.trim()].concat(arr.filter(function (x) { return x !== value.trim(); }));
        arr = arr.slice(0, MAX_SAVED);
        try { localStorage.setItem(key, JSON.stringify(arr)); } catch (e) { }
      }

      function getMergedList(key) {
        var local = loadSavedList(STORAGE_KEYS[key] || key);
        if (window.__erpShipmentSettings && window.__erpShipmentSettings[key]) {
          var server = window.__erpShipmentSettings[key];
          if (Array.isArray(server)) {
            var seen = {};
            var merged = [];
            server.forEach(function (v) {
              var s = '';
              if (key === 'construction_workers' && v && typeof v === 'object') {
                s = String(v.name || v.text || '').trim();
              } else if (v && v.text) {
                s = String(v.text).trim();
              } else {
                s = String(v).trim();
              }
              if (s && !seen[s]) { seen[s] = true; merged.push(s); }
            });
            local.forEach(function (v) { var s = String(v).trim(); if (s && !seen[s]) { seen[s] = true; merged.push(s); } });
            return merged;
          }
        }
        return local;
      }

      function normalizeWorkerName(val) {
        return String(val || '').trim().toLowerCase();
      }

      function getAssignedWorkerCountMap() {
        var map = {};
        document.querySelectorAll('input[data-field="construction_workers"]').forEach(function (inp) {
          var v = normalizeWorkerName(inp.value);
          if (v) map[v] = (map[v] || 0) + 1;
        });
        return map;
      }

      function fillDatalist(id, key) {
        const list = document.getElementById(id);
        if (!list) return;
        list.innerHTML = '';
        const arr = getMergedList(key);
        var countMap = key === 'construction_workers' ? getAssignedWorkerCountMap() : null;
        arr.forEach(function (v) {
          var val = (v && typeof v === 'object' && v.text) ? v.text : String(v);
          if (!val) return;
          var opt = document.createElement('option');
          opt.value = val;
          if (countMap) {
            var n = countMap[normalizeWorkerName(val)] || 0;
            opt.textContent = n >= 1 ? val + ' ' + n : val;
          } else {
            opt.textContent = val;
          }
          list.appendChild(opt);
        });
      }

      function refreshWorkerDatalist() {
        fillDatalist('datalist-construction-workers', 'construction_workers');
      }

      var PASTEL_COLORS = ['#B8D4E3', '#FFE5CC', '#E8D5E9', '#D5E9D5', '#F0D5D5', '#D5D5E9', '#FFF0D5', '#D5E9E5', '#F5D5E5', '#E9E5D5'];
      var WORKER_DEFAULT_BG = '#E9ECEF';

      function getFirstWorkerFromRow(tr) {
        var list = tr.querySelector('.shipment-workers-list');
        if (!list) return '';
        var inputs = list.querySelectorAll('input[data-field="construction_workers"]');
        for (var i = 0; i < inputs.length; i++) {
          var v = String(inputs[i].value || '').trim();
          if (v) return v;
        }
        var views = list.querySelectorAll('.worker-view');
        for (var i = 0; i < views.length; i++) {
          var v = String(views[i].textContent || '').trim();
          if (v) return v;
        }
        return '';
      }
      function workerKeyForSort(tr) {
        var w = getFirstWorkerFromRow(tr);
        return (w && w.toLowerCase()) || 'ZZZ';
      }

      function applyShipmentWorkerSortAndColors() {
        var tbody = document.querySelector('.shipment-table tbody');
        if (!tbody) return;
        var rows = Array.prototype.slice.call(tbody.querySelectorAll('tr.shipment-row'));
        if (!rows.length) return;
        rows.sort(function (a, b) {
          var asA = parseInt(a.dataset.as, 10) || 0;
          var asB = parseInt(b.dataset.as, 10) || 0;
          if (asA !== asB) return asA - asB;
          var wA = workerKeyForSort(a);
          var wB = workerKeyForSort(b);
          if (wA !== wB) return wA.localeCompare(wB);
          var mA = (a.dataset.manager || '').trim() || 'ZZZ';
          var mB = (b.dataset.manager || '').trim() || 'ZZZ';
          if (mA !== mB) return mA.localeCompare(mB);
          return (parseInt(a.dataset.orderId, 10) || 0) - (parseInt(b.dataset.orderId, 10) || 0);
        });
        // 정렬된 .shipment-row 를 재배치하되, 각 (AS여부|팀) 그룹 첫 행 앞에 서버가 심은
        // 그룹 헤더(.shipment-grp-row)를 다시 끼운다. 헤더는 코호트 태블릿(목업 06)에서만
        // 보이고 PC 에선 display:none — 재배치는 PC 표시에 무영향(행 순서=서버 정렬 동일).
        // 키 = "<as>|<팀 소문자>"(dashboard_main.html data-grp-key 와 정합). idempotent.
        var grpHeadByKey = {};
        Array.prototype.forEach.call(tbody.querySelectorAll('tr.shipment-grp-row'), function (h) {
          grpHeadByKey[h.getAttribute('data-grp-key') || ''] = h;
        });
        var lastGrpKey = null;
        rows.forEach(function (tr) {
          var gk = ((parseInt(tr.dataset.as, 10) || 0)) + '|' + (getFirstWorkerFromRow(tr) || '').trim().toLowerCase();
          if (gk !== lastGrpKey) {
            lastGrpKey = gk;
            if (grpHeadByKey[gk]) tbody.appendChild(grpHeadByKey[gk]);
          }
          tbody.appendChild(tr);
        });
        var workerList = [];
        rows.forEach(function (tr) {
          var w = getFirstWorkerFromRow(tr);
          var key = w ? w.toLowerCase() : '';
          if (key && workerList.indexOf(key) === -1) workerList.push(key);
        });
        rows.forEach(function (tr) {
          var td = tr.querySelector('td.shipment-worker-cell');
          if (!td) return;
          var w = getFirstWorkerFromRow(tr);
          var key = w ? w.toLowerCase() : '';
          var idx = key ? workerList.indexOf(key) : -1;
          var color = idx >= 0 ? PASTEL_COLORS[idx % PASTEL_COLORS.length] : WORKER_DEFAULT_BG;
          td.style.setProperty('--worker-bg-color', color);
          td.style.backgroundColor = color;
          td.style.color = '#000000';
          td.setAttribute('data-worker-bg-color', color);
        });
      }
      function scheduleApplyShipmentWorkerSortAndColors() {
        setTimeout(applyShipmentWorkerSortAndColors, 0);
      }
      function applyInitialWorkerCellColorsFromData() {
        document.querySelectorAll('.shipment-worker-cell[data-worker-bg-color]').forEach(function (td) {
          var bg = td.getAttribute('data-worker-bg-color');
          var text = td.getAttribute('data-worker-text-color');
          if (bg) { td.style.setProperty('--worker-bg-color', bg); td.style.backgroundColor = bg; }
          if (text) td.style.color = text;
        });
      }
      applyInitialWorkerCellColorsFromData();

      fetch('/api/erp/shipment-settings').then(function (r) { return r.json(); }).then(function (data) {
        if (data && data.success && data.settings) window.__erpShipmentSettings = data.settings;
        fillDatalist('datalist-construction-time', 'construction_time');
        fillDatalist('datalist-drawing-manager', 'drawing_manager');
        fillDatalist('datalist-construction-workers', 'construction_workers');
        fillDatalist('datalist-vehicle', 'vehicle');
        fillDatalist('datalist-trip', 'trip');
        applyShipmentWorkerSortAndColors();
      }).catch(function () {
        fillDatalist('datalist-construction-time', 'construction_time');
        fillDatalist('datalist-drawing-manager', 'drawing_manager');
        fillDatalist('datalist-construction-workers', 'construction_workers');
        fillDatalist('datalist-vehicle', 'vehicle');
        fillDatalist('datalist-trip', 'trip');
      });
      var shipmentTableEl = document.querySelector('.shipment-table');
      if (shipmentTableEl) {
        shipmentTableEl.addEventListener('blur', function (e) {
          if (e.target && e.target.getAttribute && e.target.getAttribute('data-field') === 'construction_workers') {
            scheduleApplyShipmentWorkerSortAndColors();
          }
        }, true);
      }

      function showSavedDropdown(anchor, listKey, onSelect) {
        var existing = document.getElementById('shipment-saved-dropdown');
        if (existing) existing.remove();
        var list = (typeof getMergedList === 'function' ? getMergedList(listKey) : loadSavedList(STORAGE_KEYS[listKey] || listKey));
        var countMap = listKey === 'construction_workers' ? getAssignedWorkerCountMap() : null;
        if (!list || list.length === 0) {
          var rect = anchor.getBoundingClientRect();
          var div = document.createElement('div');
          div.id = 'shipment-saved-dropdown';
          div.className = 'dropdown-menu show shipment-saved-dropdown';
          div.style.cssText = 'position:fixed;left:' + rect.left + 'px;top:' + (rect.bottom + 2) + 'px;z-index:1050;min-width:160px;';
          var span = document.createElement('span');
          span.className = 'dropdown-item text-muted';
          span.textContent = '저장된 값이 없습니다.';
          div.appendChild(span);
          document.body.appendChild(div);
          function closeEmpty() { div.remove(); document.removeEventListener('click', closeEmpty); }
          setTimeout(function () { document.addEventListener('click', closeEmpty); }, 10);
          setTimeout(function () { closeEmpty(); }, 2500);
          return;
        }
        var rect = anchor.getBoundingClientRect();
        var div = document.createElement('div');
        div.id = 'shipment-saved-dropdown';
        div.className = 'dropdown-menu show shipment-saved-dropdown';
        div.style.cssText = 'position:fixed;left:' + rect.left + 'px;top:' + (rect.bottom + 2) + 'px;z-index:1050;max-height:200px;overflow:auto;min-width:120px;';
        list.forEach(function (v) {
          var val = (v && typeof v === 'object' && v.text) ? v.text : String(v || '');
          if (!val) return;
          var a = document.createElement('a');
          a.className = 'dropdown-item';
          a.href = '#';
          if (countMap) {
            var n = countMap[normalizeWorkerName(val)] || 0;
            if (n >= 1) {
              a.innerHTML = val + ' <span class="text-primary">' + n + '</span>';
            } else {
              a.textContent = val;
            }
          } else {
            a.textContent = val;
          }
          a.addEventListener('click', function (e) { e.preventDefault(); onSelect(val); div.remove(); });
          div.appendChild(a);
        });
        document.body.appendChild(div);
        function close() { div.remove(); document.removeEventListener('click', close); }
        setTimeout(function () { document.addEventListener('click', close); }, 10);
      }

      var shipmentSaveQueue = Object.create(null);

      function getShipmentSaveQueueKey(orderId, field) {
        return String(orderId) + '::' + String(field);
      }

      function runQueuedShipmentSave(orderId, field) {
        var queueKey = getShipmentSaveQueueKey(orderId, field);
        var state = shipmentSaveQueue[queueKey];
        if (!state) return Promise.resolve();

        state.pending = true;
        state.queued = false;
        var payload = {};
        var version = state.version;
        var value = state.value;
        payload[field] = value;

        return fetch('/api/erp/shipment/update/' + orderId, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
          body: JSON.stringify(payload)
        }).then(function (r) {
          return r.json().catch(function () { return {}; }).then(function (data) {
            if (!r.ok || !data || !data.success) {
              throw new Error((data && data.message) || ('HTTP ' + r.status));
            }
            return data;
          });
        }).then(function (data) {
          if (state.version === version) {
            var key = document.querySelector('[data-order-id="' + orderId + '"][data-field="' + field + '"]');
            if (key && key.dataset.key) {
              saveToList(STORAGE_KEYS[key.dataset.key.replace('erp_shipment_', '')] || key.dataset.key, Array.isArray(value) ? value[0] : value);
            }
          }
        }).catch(function (err) {
          console.error('shipment field save failed', { orderId: orderId, field: field, error: err });
        }).finally(function () {
          state.pending = false;
          if (state.version !== version || state.queued) {
            runQueuedShipmentSave(orderId, field);
          }
        });
      }

      function saveShipmentField(orderId, field, value) {
        var queueKey = getShipmentSaveQueueKey(orderId, field);
        var state = shipmentSaveQueue[queueKey];

        if (!state) {
          state = { pending: false, queued: false, version: 0, value: null };
          shipmentSaveQueue[queueKey] = state;
        }

        state.value = value;
        state.version += 1;
        state.queued = true;

        if (state.pending) return Promise.resolve();
        return runQueuedShipmentSave(orderId, field);
      }

      function closeShipmentInlineEditors(exceptNode) {
        document.querySelectorAll('.shipment-edit-list.show-add-actions, .shipment-address-block.show-add-actions').forEach(function (el) {
          if (exceptNode && el.contains(exceptNode)) return;
          el.classList.remove('show-add-actions');
        });
      }

      function initAddButtonToggle() {
        document.querySelectorAll('.shipment-edit-list, .shipment-address-block').forEach(function (el) {
          if (el._addToggleBound) return;
          el._addToggleBound = true;
          el.addEventListener('click', function (e) {
            if (e.target.closest('button') || e.target.closest('input') || e.target.closest('select')) return;
            var isOpen = el.classList.contains('show-add-actions');
            closeShipmentInlineEditors(el);
            if (isOpen) el.classList.remove('show-add-actions');
            else el.classList.add('show-add-actions');
          });
        });
      }

      function collectSiteExtra(ul) {
        var lines = [];
        ul.querySelectorAll('li.shipment-site-extra-row').forEach(function (li) {
          var inp = li.querySelector('.site-extra-input');
          var sel = li.querySelector('.site-extra-color');
          if (!inp) return;
          var text = inp.value.trim();
          var color = (sel && sel.value) ? sel.value : 'black';
          lines.push({ text: text, color: color });
        });
        return lines;
      }

      function saveSiteExtraFromUl(ul, orderId) {
        var lines = collectSiteExtra(ul).filter(function (x) { return x.text; });
        saveShipmentField(orderId, 'site_extra', lines);
      }

      document.querySelectorAll('.site-extra-view').forEach(function (view) {
        view.addEventListener('click', function () {
          var li = view.closest('li');
          if (!li) return;
          li.classList.remove('has-value');
          li.classList.add('editing');
          var inp = li.querySelector('.site-extra-input');
          if (inp) { inp.focus(); }
        });
      });

      document.querySelectorAll('.site-extra-input').forEach(function (inp) {
        var li = inp.closest('li');
        var ul = li && li.parentElement;
        var orderId = ul && ul.dataset.orderId;
        var viewSpan = li && li.querySelector('.site-extra-view');
        if (!orderId) return;
        inp.addEventListener('blur', function () {
          var val = inp.value.trim();
          var sel = li.querySelector('.site-extra-color');
          var c = (sel && sel.value) ? sel.value : 'black';
          if (viewSpan) {
            viewSpan.textContent = val;
            viewSpan.className = 'site-extra-view site-extra-color-' + c;
          }
          if (val) { li.classList.add('has-value'); li.classList.remove('editing'); }
          else { li.classList.remove('has-value'); li.classList.add('editing'); }
          saveSiteExtraFromUl(ul, orderId);
          if (val) saveToList(STORAGE_KEYS.site_extra, val);
        });
      });

      document.querySelectorAll('.line-remove-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
          var li = btn.closest('li');
          var ul = li && li.parentElement;
          var orderId = ul && ul.dataset.orderId;
          if (!orderId) return;
          li.remove();
          saveSiteExtraFromUl(ul, orderId);
        });
      });

      document.querySelectorAll('.site-extra-color').forEach(function (sel) {
        var li = sel.closest('li');
        var ul = li && li.parentElement;
        var orderId = ul && ul.dataset.orderId;
        var inp = li && li.querySelector('.site-extra-input');
        if (!inp || !orderId) return;
        sel.addEventListener('change', function () {
          var c = sel.value || 'black';
          inp.dataset.color = c;
          inp.className = inp.className.replace(/\bsite-extra-color-\w+\b/g, '') + ' site-extra-color-' + c;
          saveSiteExtraFromUl(ul, orderId);
        });
      });

      document.querySelectorAll('.shipment-btn-load-saved-site-extra-row').forEach(function (btn) {
        btn.addEventListener('click', function (e) {
          e.preventDefault();
          e.stopPropagation();
          var li = btn.closest('li');
          var ul = li && li.parentElement;
          var orderId = ul && ul.dataset.orderId;
          var input = li ? li.querySelector('.site-extra-input') : null;
          var viewSpan = li ? li.querySelector('.site-extra-view') : null;
          var sel = li ? li.querySelector('.site-extra-color') : null;
          if (!input || !orderId) return;
          showSavedDropdown(btn, 'site_extra', function (v) {
            input.value = v;
            var c = (sel && sel.value) ? sel.value : 'black';
            if (viewSpan) { viewSpan.textContent = v; viewSpan.className = 'site-extra-view site-extra-color-' + c; }
            if (v) { li.classList.add('has-value'); li.classList.remove('editing'); }
            saveSiteExtraFromUl(ul, orderId);
            if (v) saveToList(STORAGE_KEYS.site_extra, v);
          });
        });
      });

      document.querySelectorAll('.btn-add-site-extra').forEach(function (btn) {
        btn.addEventListener('click', function () {
          var orderId = btn.dataset.orderId;
          var ul = btn.closest('ul');
          if (!ul) return;
          var li = document.createElement('li');
          li.className = 'shipment-site-extra-row d-flex gap-1 align-items-center flex-wrap editing';
          li.dataset.color = 'black';
          li.innerHTML = '<span class="site-extra-view site-extra-color-black"></span>' +
            '<button type="button" class="btn btn-sm btn-outline-danger line-remove-btn" title="삭제">&times;</button>' +
            '<div class="site-extra-edit d-flex gap-1 align-items-center flex-wrap flex-grow-1">' +
            '<input type="text" class="form-control form-control-sm shipment-input site-extra-input flex-grow-1 site-extra-color-black" data-key="erp_shipment_site_extra" data-color="black" placeholder="추가 주소" style="min-width: 80px;">' +
            '<select class="form-select form-select-sm site-extra-color" style="width: 70px; flex-shrink: 0;" title="글자색">' +
            '<option value="black" selected>검정</option><option value="red">빨강</option><option value="blue">파랑</option><option value="green">초록</option><option value="orange">주황</option><option value="purple">보라</option><option value="brown">갈색</option><option value="navy">남색</option></select>' +
            '<button type="button" class="btn btn-sm btn-outline-secondary shipment-btn-load-saved-site-extra-row" data-order-id="' + orderId + '" title="저장된 주소 불러오기"><i class="fas fa-list"></i></button>' +
            '<button type="button" class="btn btn-sm btn-outline-danger btn-remove-site-extra" title="삭제">&times;</button></div>';
          ul.insertBefore(li, btn.closest('li'));
          var viewSpan = li.querySelector('.site-extra-view');
          var newInp = li.querySelector('.site-extra-input');
          viewSpan.addEventListener('click', function () { li.classList.remove('has-value'); li.classList.add('editing'); newInp.focus(); });
          newInp.addEventListener('blur', function () {
            var val = newInp.value.trim();
            var sel = li.querySelector('.site-extra-color');
            var c = (sel && sel.value) ? sel.value : 'black';
            viewSpan.textContent = val;
            viewSpan.className = 'site-extra-view site-extra-color-' + c;
            if (val) { li.classList.add('has-value'); li.classList.remove('editing'); } else { li.classList.remove('has-value'); li.classList.add('editing'); }
            saveSiteExtraFromUl(ul, orderId);
            if (val) saveToList(STORAGE_KEYS.site_extra, val);
          });
          li.querySelector('.line-remove-btn').addEventListener('click', function () { li.remove(); saveSiteExtraFromUl(ul, orderId); });
          li.querySelector('.site-extra-color').addEventListener('change', function () {
            var c = this.value || 'black';
            newInp.dataset.color = c;
            newInp.className = newInp.className.replace(/\bsite-extra-color-\w+\b/g, '') + ' site-extra-color-' + c;
            saveSiteExtraFromUl(ul, orderId);
          });
          li.querySelector('.shipment-btn-load-saved-site-extra-row').addEventListener('click', function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            showSavedDropdown(this, 'site_extra', function (v) {
              newInp.value = v;
              viewSpan.textContent = v;
              if (v) { li.classList.add('has-value'); li.classList.remove('editing'); }
              saveSiteExtraFromUl(ul, orderId);
              if (v) saveToList(STORAGE_KEYS.site_extra, v);
            });
          });
          li.querySelector('.btn-remove-site-extra').addEventListener('click', function () { li.remove(); saveSiteExtraFromUl(ul, orderId); });
        });
      });

      document.querySelectorAll('.btn-remove-site-extra').forEach(function (btn) {
        btn.addEventListener('click', function () {
          var li = btn.closest('li');
          var ul = li && li.parentElement;
          var orderId = ul && ul.dataset.orderId;
          if (!orderId) return;
          li.remove();
          saveSiteExtraFromUl(ul, orderId);
        });
      });
      function getShipmentEditList(node) {
        return node && node.closest('.shipment-edit-list[data-order-id][data-field]');
      }

      function getShipmentEditField(list) {
        return list ? String(list.dataset.field || '') : '';
      }

      function getShipmentEditListKey(list) {
        return list ? String(list.dataset.listKey || list.dataset.field || '') : '';
      }

      function getShipmentEditStorageKey(list) {
        return list ? String(list.dataset.storageKey || '') : '';
      }

      function getShipmentEditOrderId(list) {
        return list ? String(list.dataset.orderId || '') : '';
      }

      function isShipmentSingleValueList(list) {
        return !!(list && list.dataset.single === 'true');
      }

      function trimShipmentEditValue(value) {
        return String(value || '').trim();
      }

      function getShipmentEditValues(list) {
        var field = getShipmentEditField(list);
        var values = [];
        if (!list || !field) return values;
        list.querySelectorAll('input[data-field="' + field + '"]').forEach(function (input) {
          var value = trimShipmentEditValue(input.value);
          if (value) values.push(value);
        });
        return values;
      }

      function syncShipmentTextRowState(row) {
        if (!row) return '';
        var input = row.querySelector('.shipment-text-input');
        var view = row.querySelector('.shipment-text-view');
        var list = getShipmentEditList(row);
        var value = trimShipmentEditValue(input ? input.value : '');
        if (view) view.textContent = value;
        if (value) {
          row.classList.add('has-value');
          row.classList.remove('editing');
          row.classList.remove('is-empty');
        } else {
          row.classList.remove('has-value');
          row.classList.remove('editing');
          row.classList.toggle('is-empty', isShipmentSingleValueList(list));
          if (!isShipmentSingleValueList(list)) {
            row.classList.add('editing');
          }
        }
        return value;
      }

      function saveShipmentEditList(list) {
        var orderId = getShipmentEditOrderId(list);
        var field = getShipmentEditField(list);
        if (!orderId || !field) return;
        if (isShipmentSingleValueList(list)) {
          var input = list.querySelector('.shipment-text-input');
          saveShipmentField(orderId, field, trimShipmentEditValue(input ? input.value : ''));
        } else {
          saveShipmentField(orderId, field, getShipmentEditValues(list));
        }
        if (field === 'construction_workers') {
          refreshWorkerDatalist();
          scheduleApplyShipmentWorkerSortAndColors();
        }
      }

      function saveShipmentEditRowValue(list, row) {
        var value = syncShipmentTextRowState(row);
        var storageKey = getShipmentEditStorageKey(list);
        if (value && storageKey && STORAGE_KEYS[storageKey]) {
          saveToList(STORAGE_KEYS[storageKey], value);
        }
        saveShipmentEditList(list);
      }

      function escapeShipmentEditHtml(value) {
        return String(value || '')
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;')
          .replace(/"/g, '&quot;');
      }

      function getShipmentEditViewClass(field) {
        if (field === 'construction_workers') return 'shipment-text-view worker-view';
        if (field === 'drawing_managers') return 'shipment-text-view drawing-manager-view';
        return 'shipment-text-view';
      }

      function buildShipmentTextRow(list, value) {
        var field = getShipmentEditField(list);
        var orderId = getShipmentEditOrderId(list);
        var datalistId = list.dataset.datalistId || '';
        var emptyPlaceholder = list.dataset.emptyPlaceholder || '';
        var placeholder = list.dataset.placeholder || '';
        var escapedValue = escapeShipmentEditHtml(value || '');
        var li = document.createElement('li');
        li.className = 'shipment-text-row' + (trimShipmentEditValue(value) ? ' has-value' : ' editing');
        li.innerHTML =
          '<span class="' + getShipmentEditViewClass(field) + '"' +
          (emptyPlaceholder ? ' data-empty-placeholder="' + escapeShipmentEditHtml(emptyPlaceholder) + '"' : '') +
          '>' + escapedValue + '</span>' +
          '<div class="shipment-text-edit input-group input-group-sm flex-nowrap">' +
          '<input type="text" class="form-control form-control-sm shipment-text-input"' +
          ' data-order-id="' + orderId + '"' +
          ' data-field="' + field + '"' +
          ' value="' + escapedValue + '"' +
          ' placeholder="' + escapeShipmentEditHtml(placeholder) + '"' +
          (datalistId ? ' list="' + escapeShipmentEditHtml(datalistId) + '"' : '') +
          '>' +
          '<button type="button" class="btn btn-sm btn-outline-secondary shipment-btn-load-saved-text-row" title="저장된 값 불러오기"><i class="fas fa-list"></i></button>' +
          '<button type="button" class="btn btn-sm btn-outline-danger btn-remove-shipment-text-row" title="삭제">&times;</button>' +
          '</div>';
        return li;
      }

      if (!window.__shipmentDashboardDocListenersBound) {
        window.__shipmentDashboardDocListenersBound = true;

        document.addEventListener('click', function (e) {
          closeShipmentInlineEditors(e.target);
        });

        document.addEventListener('mousedown', function (e) {
          if (!e.target.closest('.btn-remove-shipment-text-row, .shipment-btn-load-saved-text-row')) return;
          var row = e.target.closest('.shipment-text-row');
          if (row) row.dataset.skipBlurSave = '1';
        }, true);

        document.addEventListener('click', function (e) {
          var view = e.target.closest('.shipment-text-row .shipment-text-view');
          if (view) {
            var row = view.closest('.shipment-text-row');
            var input = row && row.querySelector('.shipment-text-input');
            if (row && input) {
              e.preventDefault();
              e.stopPropagation();
              row.classList.remove('has-value');
              row.classList.remove('is-empty');
              row.classList.add('editing');
              input.focus();
            }
            return;
          }

          var addBtn = e.target.closest('.btn-add-shipment-text-row');
          if (addBtn) {
            var list = getShipmentEditList(addBtn);
            if (!list) return;
            e.preventDefault();
            e.stopPropagation();
            var row = buildShipmentTextRow(list, '');
            var actionsRow = addBtn.closest('.actions-on-hover');
            list.insertBefore(row, actionsRow || null);
            var input = row.querySelector('.shipment-text-input');
            if (input) input.focus();
            return;
          }

          var removeBtn = e.target.closest('.btn-remove-shipment-text-row');
          if (removeBtn) {
            var list = getShipmentEditList(removeBtn);
            var row = removeBtn.closest('.shipment-text-row');
            if (!list || !row) return;
            e.preventDefault();
            e.stopPropagation();
            if (isShipmentSingleValueList(list)) {
              var input = row.querySelector('.shipment-text-input');
              if (input) input.value = '';
              syncShipmentTextRowState(row);
            } else {
              row.remove();
            }
            saveShipmentEditList(list);
            return;
          }

          var loadBtn = e.target.closest('.shipment-btn-load-saved-text-row');
          if (loadBtn) {
            var list = getShipmentEditList(loadBtn);
            var row = loadBtn.closest('.shipment-text-row');
            var input = row && row.querySelector('.shipment-text-input');
            if (!list || !row || !input) return;
            e.preventDefault();
            e.stopPropagation();
            showSavedDropdown(loadBtn, getShipmentEditListKey(list), function (value) {
              input.value = value;
              saveShipmentEditRowValue(list, row);
              input.focus();
            });
          }
        });

        document.addEventListener('blur', function (e) {
          if (!e.target.matches || !e.target.matches('.shipment-text-input')) return;
          var input = e.target;
          var row = input.closest('.shipment-text-row');
          var list = getShipmentEditList(input);
          if (!row || !list) return;
          if (row.dataset.skipBlurSave === '1') {
            row.dataset.skipBlurSave = '';
            return;
          }
          saveShipmentEditRowValue(list, row);
        }, true);
      }

      function mountShipmentDashboardSurface() {
        if (!document.querySelector('.shipment-table')) return;
        initAddButtonToggle();
      }

      if (!window.__shipmentDashboardSwapListenerBound) {
        window.__shipmentDashboardSwapListenerBound = true;
        document.addEventListener('foms:main-content-swapped', mountShipmentDashboardSurface);
      }
      mountShipmentDashboardSurface();

      document.querySelectorAll('.shipment-btn-load-saved-site-extra').forEach(function (btn) {
        btn.addEventListener('click', function (e) {
          e.preventDefault();
          e.stopPropagation();
          var orderId = btn.dataset.orderId;
          var ul = btn.closest('ul');
          if (!ul) return;
          showSavedDropdown(btn, 'site_extra', function (v) {
            var li = document.createElement('li');
            li.className = 'shipment-site-extra-row d-flex gap-1 align-items-center flex-wrap has-value';
            li.dataset.color = 'black';
            var escaped = (v + '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            li.innerHTML = '<span class="site-extra-view site-extra-color-black">' + escaped + '</span>' +
              '<button type="button" class="btn btn-sm btn-outline-danger line-remove-btn" title="삭제">&times;</button>' +
              '<div class="site-extra-edit d-flex gap-1 align-items-center flex-wrap flex-grow-1">' +
              '<input type="text" class="form-control form-control-sm shipment-input site-extra-input flex-grow-1 site-extra-color-black" data-key="erp_shipment_site_extra" data-color="black" value="' + escaped + '" placeholder="추가 주소" style="min-width: 80px;">' +
              '<select class="form-select form-select-sm site-extra-color" style="width: 70px; flex-shrink: 0;" title="글자색">' +
              '<option value="black" selected>검정</option><option value="red">빨강</option><option value="blue">파랑</option><option value="green">초록</option><option value="orange">주황</option><option value="purple">보라</option><option value="brown">갈색</option><option value="navy">남색</option></select>' +
              '<button type="button" class="btn btn-sm btn-outline-secondary shipment-btn-load-saved-site-extra-row" data-order-id="' + orderId + '" title="저장된 주소 불러오기"><i class="fas fa-list"></i></button>' +
              '<button type="button" class="btn btn-sm btn-outline-danger btn-remove-site-extra" title="삭제">&times;</button></div>';
            var lastLi = ul.querySelector('li.address-row-actions');
            ul.insertBefore(li, lastLi);
            var viewSpan = li.querySelector('.site-extra-view');
            var newInp = li.querySelector('.site-extra-input');
            li.querySelector('.site-extra-input').addEventListener('blur', function () {
              var val = newInp.value.trim();
              var sel = li.querySelector('.site-extra-color');
              var c = (sel && sel.value) ? sel.value : 'black';
              viewSpan.textContent = val;
              viewSpan.className = 'site-extra-view site-extra-color-' + c;
              if (val) li.classList.add('has-value'); else li.classList.remove('has-value');
              saveSiteExtraFromUl(ul, orderId);
            });
            li.querySelector('.site-extra-color').addEventListener('change', function () {
              var c = this.value || 'black';
              newInp.dataset.color = c;
              newInp.className = newInp.className.replace(/\bsite-extra-color-\w+\b/g, '') + ' site-extra-color-' + c;
              viewSpan.className = 'site-extra-view site-extra-color-' + c;
              saveSiteExtraFromUl(ul, orderId);
            });
            li.querySelector('.line-remove-btn').addEventListener('click', function () { li.remove(); saveSiteExtraFromUl(ul, orderId); });
            li.querySelector('.shipment-btn-load-saved-site-extra-row').addEventListener('click', function (ev) {
              ev.preventDefault();
              ev.stopPropagation();
              showSavedDropdown(this, 'site_extra', function (v) {
                newInp.value = v;
                viewSpan.textContent = v;
                if (v) li.classList.add('has-value');
                saveSiteExtraFromUl(ul, orderId);
                if (v) saveToList(STORAGE_KEYS.site_extra, v);
              });
            });
            li.querySelector('.btn-remove-site-extra').addEventListener('click', function () { li.remove(); saveSiteExtraFromUl(ul, orderId); });
            saveSiteExtraFromUl(ul, orderId);
          });
        });
      });
    })();

    if (__shipDashCanEdit) {
    window.__shipmentAsRecPageDate = __shipDashSelectedDate;
    (function shipmentAsRecommendUi() {
      var CHUNK = 5;
      window.__shipmentAsRecModalEl = window.__shipmentAsRecModalEl || null;
      window.__shipmentAsRecMapModalEl = window.__shipmentAsRecMapModalEl || null;
      window.__shipmentAsRecNeedsReload = false;
      var shipmentAsRecMapModalInstance = null;
      window.__shipmentAsRecMapLeaflet = window.__shipmentAsRecMapLeaflet || null;
      var shipmentAsRecMapGen = 0;
      var shipmentAsRecLeafletPromise = null;
      var shipmentAsRecRouteCache = new Map();

      function adoptModalFromMain() {
        var main = document.getElementById('main-content');
        if (!main) return;
        var fresh = main.querySelector('#shipmentAsRecommendModal');
        if (!fresh) return;
        var prev = window.__shipmentAsRecModalEl;
        if (prev && prev !== fresh && prev.parentNode) {
          prev.remove();
        }
        document.body.appendChild(fresh);
        window.__shipmentAsRecModalEl = fresh;
        var freshMap = main.querySelector('#scheduleMapModal');
        if (freshMap) {
          var prevMap = window.__shipmentAsRecMapModalEl;
          if (prevMap && prevMap !== freshMap && prevMap.parentNode) {
            resetShipmentAsRecMap();
            shipmentAsRecMapModalInstance = null;
            prevMap.remove();
          }
          document.body.appendChild(freshMap);
          window.__shipmentAsRecMapModalEl = freshMap;
        }
      }

      adoptModalFromMain();

      function collectTargetOrderIds() {
        var tbody = document.querySelector('#shipment-dashboard-table tbody') || document.querySelector('.shipment-table tbody');
        if (!tbody) return [];
        var rows = tbody.querySelectorAll('tr.shipment-row[data-order-id]');
        var ids = [];
        rows.forEach(function (tr) {
          if (String(tr.getAttribute('data-as') || '0') !== '0') return;
          var id = parseInt(tr.getAttribute('data-order-id'), 10);
          if (id) ids.push(id);
        });
        return ids;
      }

      function escHtml(s) {
        return String(s == null ? '' : s)
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;')
          .replace(/"/g, '&quot;');
      }

      function routeCacheKey(a, b, c, d) {
        return [a, b, c, d].map(function (v) {
          return Number(v).toFixed(6);
        }).join(',');
      }

      function ensureLeaflet() {
        if (window.L) return Promise.resolve();
        if (shipmentAsRecLeafletPromise) return shipmentAsRecLeafletPromise;
        shipmentAsRecLeafletPromise = new Promise(function (resolve, reject) {
          if (!document.getElementById('shipment-as-rec-leaflet-css')) {
            var link = document.createElement('link');
            link.id = 'shipment-as-rec-leaflet-css';
            link.rel = 'stylesheet';
            link.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
            link.crossOrigin = '';
            document.head.appendChild(link);
          }
          var script = document.getElementById('shipment-as-rec-leaflet-js');
          if (!script) {
            script = document.createElement('script');
            script.id = 'shipment-as-rec-leaflet-js';
            script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
            script.crossOrigin = '';
            document.head.appendChild(script);
          }
          script.addEventListener('load', function () { resolve(); }, { once: true });
          script.addEventListener('error', function () { reject(new Error('Leaflet 로드 실패')); }, { once: true });
        });
        return shipmentAsRecLeafletPromise;
      }

      function getMapModal() {
        return window.__shipmentAsRecMapModalEl || document.getElementById('scheduleMapModal');
      }

      function resetShipmentAsRecMap() {
        if (window.__shipmentAsRecMapLeaflet) {
          try {
            window.__shipmentAsRecMapLeaflet.remove();
          } catch (e) { /* ignore */ }
          window.__shipmentAsRecMapLeaflet = null;
        }
      }

      function getFreshScheduleMapContainer() {
        var container = document.getElementById('scheduleMapContainer');
        if (!container) return null;
        if (container._leaflet_id) {
          var clone = container.cloneNode(false);
          container.parentNode.replaceChild(clone, container);
          container = clone;
        }
        container.replaceChildren();
        return container;
      }

      function openShipmentAsRecMap(refAddr, refLat, refLng, tgtLat, tgtLng, tgtAddr, tgtName, scoreText) {
        adoptModalFromMain();
        var modalEl = getMapModal();
        var routeInfoEl = document.getElementById('scheduleMapRouteInfo');
        if (!modalEl || !routeInfoEl || typeof bootstrap === 'undefined') return;
        routeInfoEl.innerHTML = '<div class="text-center text-muted py-3"><div class="spinner-border spinner-border-sm me-2" role="status"></div>경로 계산 중...</div>';
        var myGen = ++shipmentAsRecMapGen;

        ensureLeaflet().then(function () {
          if (!window.L || myGen !== shipmentAsRecMapGen) return;
          if (!shipmentAsRecMapModalInstance) {
            shipmentAsRecMapModalInstance = bootstrap.Modal.getOrCreateInstance(modalEl);
          }
          var onShown = function () {
            modalEl.removeEventListener('shown.bs.modal', onShown);
            if (myGen !== shipmentAsRecMapGen) return;
            resetShipmentAsRecMap();
            var container = getFreshScheduleMapContainer();
            if (!container) return;
            var map = L.map(container).setView([refLat, refLng], 11);
            window.__shipmentAsRecMapLeaflet = map;
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
              maxZoom: 19,
              attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" rel="noopener">OpenStreetMap</a>'
            }).addTo(map);
            L.circleMarker([refLat, refLng], {
              radius: 9,
              color: '#c0392b',
              weight: 2,
              fillColor: '#ff6b6b',
              fillOpacity: 0.95
            }).addTo(map).bindPopup(escHtml(refAddr));
            L.circleMarker([tgtLat, tgtLng], {
              radius: 9,
              color: '#2e7d32',
              weight: 2,
              fillColor: '#4caf50',
              fillOpacity: 0.95
            }).addTo(map).bindPopup('<strong>' + escHtml(tgtName) + '</strong><br>' + escHtml(tgtAddr));
            map.fitBounds(L.latLngBounds([[refLat, refLng], [tgtLat, tgtLng]]), { padding: [50, 50], maxZoom: 14 });

            function bumpMapSize() {
              if (myGen !== shipmentAsRecMapGen || window.__shipmentAsRecMapLeaflet !== map) return;
              try {
                map.invalidateSize({ animate: false });
              } catch (e) { /* ignore */ }
            }
            map.whenReady(bumpMapSize);
            requestAnimationFrame(function () {
              bumpMapSize();
              setTimeout(bumpMapSize, 120);
              setTimeout(bumpMapSize, 400);
            });

            var cacheKey = routeCacheKey(refLat, refLng, tgtLat, tgtLng);
            var routePromise = shipmentAsRecRouteCache.has(cacheKey)
              ? Promise.resolve(shipmentAsRecRouteCache.get(cacheKey))
              : fetch(
                '/api/calculate_route?start_lat=' + encodeURIComponent(refLat) +
                '&start_lng=' + encodeURIComponent(refLng) +
                '&end_lat=' + encodeURIComponent(tgtLat) +
                '&end_lng=' + encodeURIComponent(tgtLng)
              ).then(function (res) {
                if (res.status === 429) throw new Error('RATE_LIMIT');
                return res.json();
              }).then(function (json) {
                if (json && json.success) shipmentAsRecRouteCache.set(cacheKey, json);
                return json;
              });

            routePromise.then(function (routeJson) {
              if (myGen !== shipmentAsRecMapGen || window.__shipmentAsRecMapLeaflet !== map) return;
              if (routeJson && routeJson.success && routeJson.data &&
                  routeJson.data.route_coords && routeJson.data.route_coords.length > 0) {
                var routeData = routeJson.data;
                var line = L.polyline(routeData.route_coords, {
                  color: '#ff4757',
                  weight: 5,
                  opacity: 0.8
                }).addTo(map);
                try {
                  map.fitBounds(line.getBounds(), { padding: [50, 50], maxZoom: 14 });
                } catch (e) { /* ignore */ }
                bumpMapSize();
                setTimeout(bumpMapSize, 200);
                var summ = routeData.summary || {};
                var distT = summ.distance_text != null ? summ.distance_text : (routeData.distance_km + 'km');
                var durT = summ.duration_text != null ? summ.duration_text : ((routeData.duration_min || 0) + '분');
                var tollT = summ.toll_text != null ? summ.toll_text : '—';
                routeInfoEl.innerHTML =
                  '<div class="schedule-map-route-info">' +
                  '<h6><i class="fas fa-car-side me-1"></i> 경로 정보</h6>' +
                  '<div class="mb-1"><strong>출발:</strong> ' + escHtml(refAddr) + '</div>' +
                  '<div class="mb-1"><strong>도착:</strong> ' + escHtml(tgtAddr) + '</div>' +
                  '<div class="mb-1"><strong>거리:</strong> ' + escHtml(distT) + '</div>' +
                  '<div class="mb-1"><strong>소요시간:</strong> ' + escHtml(durT) + '</div>' +
                  '<div><strong>통행료:</strong> ' + escHtml(tollT) + '</div>' +
                  '</div>';
                return;
              }
              throw new Error((routeJson && routeJson.error) ? String(routeJson.error) : 'ROUTE_FAIL');
            }).catch(function (err) {
              if (myGen !== shipmentAsRecMapGen) return;
              var msg = (err && err.message === 'RATE_LIMIT')
                ? '요청 한도에 도달했습니다. 잠시 후 다시 시도해 주세요.'
                : '자동차 경로를 계산하지 못했습니다. 직선거리를 참고해 주세요.';
              var hint = scoreText
                ? ('<p class="mb-0 small mt-2">직선거리 참고: ' + escHtml(scoreText) + '</p>')
                : '';
              routeInfoEl.innerHTML =
                '<div class="alert alert-warning mb-0" role="alert">' +
                '<strong>경로 계산 실패</strong>' +
                '<p class="mb-0 small">' + escHtml(msg) + '</p>' +
                hint +
                '</div>';
            });
          };
          modalEl.addEventListener('shown.bs.modal', onShown, { once: true });
          shipmentAsRecMapModalInstance.show();
        }).catch(function (err) {
          routeInfoEl.innerHTML =
            '<div class="alert alert-warning mb-0" role="alert">' +
            '<strong>지도 로드 실패</strong>' +
            '<p class="mb-0 small">' + escHtml(err && err.message ? err.message : '지도 모듈을 불러오지 못했습니다.') + '</p>' +
            '</div>';
        });
      }

      function getModal() {
        return window.__shipmentAsRecModalEl || document.getElementById('shipmentAsRecommendModal');
      }

      function setStatus(msg) {
        var el = document.getElementById('shipment-as-rec-status');
        if (el) el.textContent = msg || '';
      }

      function showProgress(pct) {
        var wrap = document.getElementById('shipment-as-rec-progress');
        var bar = wrap && wrap.querySelector('.progress-bar');
        if (!wrap || !bar) return;
        if (pct == null) {
          wrap.classList.add('d-none');
          return;
        }
        wrap.classList.remove('d-none');
        bar.style.width = Math.min(100, Math.max(0, pct)) + '%';
      }

      function refreshShipmentFragment() {
        var shell = window.FOMS_ERP_SHELL;
        if (shell && typeof shell.navigateByShell === 'function') {
          return shell.navigateByShell(
            window.location.pathname + window.location.search + window.location.hash,
            { bypassCache: true }
          );
        }
        window.location.reload();
        return Promise.resolve();
      }

      function hydrateAsRecRichPreviews(payload, rootEl) {
        if (!rootEl) return;
        var targets = (payload && payload.targets) || [];
        targets.forEach(function (t) {
          (t.recommendations || []).forEach(function (r) {
            var key = String(t.order_id) + '-' + String(r.as_order_id);
            var el = rootEl.querySelector('[data-asrec-rich="' + key + '"]');
            if (!el) return;
            if (r.as_content_html) {
              el.innerHTML = r.as_content_html;
              el.classList.remove('asrec-rich-preview--plain');
            } else if (r.as_content_text) {
              el.textContent = r.as_content_text;
              el.classList.add('asrec-rich-preview--plain');
            }
          });
        });
      }

      function renderAll(payload) {
        var groupsEl = document.getElementById('shipment-as-rec-groups');
        var emptyEl = document.getElementById('shipment-as-rec-empty');
        var linkedWrap = document.getElementById('shipment-as-rec-linked');
        var linkedBody = document.getElementById('shipment-as-rec-linked-body');
        if (!groupsEl) return;
        var targets = (payload && payload.targets) || [];
        if (!targets.length) {
          groupsEl.innerHTML = '';
          if (emptyEl) emptyEl.classList.remove('d-none');
          if (linkedWrap) linkedWrap.classList.add('d-none');
          return;
        }
        if (emptyEl) emptyEl.classList.add('d-none');
        var linkedHtml = '';
        targets.forEach(function (t) {
          (t.linked_as_schedules || []).forEach(function (L) {
            linkedHtml +=
              '<div class="d-flex flex-wrap align-items-center gap-2 border rounded px-2 py-1 mb-1">' +
              '<span>AS #' + escHtml(L.as_order_id) + ' ' + escHtml(L.customer_name) + '</span>' +
              '<span class="text-muted">' + escHtml(L.applied_date) + '</span>' +
              '<button type="button" class="btn btn-sm btn-outline-danger js-shipment-as-rec-cancel" ' +
              'data-shipment-order-id="' + escHtml(t.order_id) + '" data-as-order-id="' + escHtml(L.as_order_id) + '" ' +
              'data-as-info-id="' + escHtml(L.as_info_id != null ? L.as_info_id : '') + '">삭제</button>' +
              '</div>';
          });
        });
        if (linkedBody) linkedBody.innerHTML = linkedHtml || '<span class="text-muted">없음</span>';
        if (linkedWrap) linkedWrap.classList.toggle('d-none', !linkedHtml);

        var html = '';
        targets.forEach(function (t) {
          var recs = t.recommendations || [];
          var recCount = recs.length;
          var collapseId = 'asrec-m-' + String(t.order_id);
          html += '<div class="card mb-3 asrec-target-group border">';
          html += '<button type="button" class="card-header py-2 px-3 d-lg-none btn btn-light w-100 text-start border-0 rounded-0 d-flex justify-content-between align-items-center" data-bs-toggle="collapse" data-bs-target="#' + collapseId + '" aria-expanded="false">';
          html += '<span class="text-primary"><strong>출고 #' + escHtml(t.order_id) + '</strong> · ' + escHtml(t.customer_name) + ' · ' + escHtml(t.address) + ' · 추천 ' + recCount + '건</span>';
          html += '<span class="text-muted small">펼침</span>';
          html += '</button>';
          html += '<div class="card-header py-2 d-none d-lg-block border-bottom-0 bg-white">';
          html += '<span class="text-primary"><strong>출고 #' + escHtml(t.order_id) + '</strong> ';
          html += escHtml(t.customer_name) + ' <span class="small">' + escHtml(t.address) + '</span></span>';
          if (t.message) html += '<div class="small text-warning mt-1">' + escHtml(t.message) + '</div>';
          html += '</div>';
          html += '<div id="' + collapseId + '" class="collapse asrec-target-detail"><div class="card-body py-2 border-top">';
          if (t.message) {
            html += '<div class="d-lg-none small text-warning mb-2">' + escHtml(t.message) + '</div>';
          }
          html += '<div class="text-muted small d-lg-none mb-2">' + escHtml(t.address) + '</div>';
          if (!recs.length) {
            html += '<div class="text-muted small">추천 후보가 없거나 주소/경로 조건을 만족하지 않습니다.</div>';
          }
          recs.forEach(function (r) {
            var workersLabel = (r.will_apply_workers && r.will_apply_workers.length)
              ? escHtml(r.will_apply_workers.join(', '))
              : '시공자 공란으로 적용';
            var disabled = r.linked_from_shipment_order_id ? 'disabled' : '';
            var badge = '';
            if (r.linked_from_shipment_order_id) {
              badge = '<span class="badge bg-secondary ms-1">이미 추가됨</span>';
            }
            var targetLat = Number(t.lat);
            var targetLng = Number(t.lng);
            var recLat = Number(r.lat);
            var recLng = Number(r.lng);
            var canOpenMap = Number.isFinite(targetLat) && Number.isFinite(targetLng) && Number.isFinite(recLat) && Number.isFinite(recLng);
            var richKey = String(t.order_id) + '-' + String(r.as_order_id);
            html += '<div class="border rounded p-2 mb-2 small" data-as-order-id="' + escHtml(r.as_order_id) + '">';
            html += '<div class="row g-2 align-items-stretch">';
            html += '<div class="col-12 col-md-6 asrec-card-meta">';
            html += '<div class="fw-bold">AS #' + escHtml(r.as_order_id) + ' ' + escHtml(r.customer_name) + badge + '</div>';
            html += '<div class="text-muted">' + escHtml(r.address) + '</div>';
            html += '<div class="mt-2">현재 방문일: <span class="js-asrec-visit">' + escHtml(r.current_visit_date || '(없음)') + '</span></div>';
            html += '<div>' + escHtml(r.score_text || '') + '</div>';
            html += '<div class="mt-1">적용 시 시공자: ' + workersLabel + '</div>';
            html += '<div class="js-asrec-err text-danger mt-1"></div>';
            html += '<div class="d-flex flex-wrap align-items-center gap-2 mt-2">';
            html += '<button type="button" class="btn btn-sm btn-primary js-shipment-as-rec-apply" ' + disabled + ' ';
            html += 'data-shipment-order-id="' + escHtml(t.order_id) + '" data-as-order-id="' + escHtml(r.as_order_id) + '" ';
            html += 'data-as-info-id="' + escHtml(r.as_info_id != null ? r.as_info_id : '') + '" ';
            html += 'data-already-scheduled="' + (r.already_scheduled ? '1' : '0') + '">';
            html += (r.linked_from_shipment_order_id ? '다른 출고에 연결됨' : '추가') + '</button>';
            if (canOpenMap) {
              html += '<button type="button" class="btn btn-sm btn-outline-info js-shipment-as-rec-map" ';
              html += 'data-ref-lat="' + escHtml(targetLat) + '" data-ref-lng="' + escHtml(targetLng) + '" ';
              html += 'data-ref-address="' + escHtml(t.address) + '" data-ref-name="' + escHtml(t.customer_name) + '" ';
              html += 'data-lat="' + escHtml(recLat) + '" data-lng="' + escHtml(recLng) + '" ';
              html += 'data-address="' + escHtml(r.address) + '" data-name="' + escHtml(r.customer_name) + '" ';
              html += 'data-score-text="' + escHtml(r.score_text || '') + '"><i class="fas fa-map"></i> 지도</button>';
            }
            html += '</div>';
            html += '</div>';
            html += '<div class="col-12 col-md-6 asrec-card-content">';
            html += '<div class="border rounded bg-light h-100 p-2">';
            html += '<div class="erp-pro-input as-content-input asrec-rich-preview js-asrec-rich-preview" ';
            html += 'contenteditable="false" tabindex="-1" role="region" aria-readonly="true" aria-label="AS 내용" ';
            html += 'data-asrec-rich="' + escHtml(richKey) + '"></div>';
            html += '</div></div>';
            html += '</div></div>';
          });
          html += '</div></div></div>';
        });
        groupsEl.innerHTML = html;
        hydrateAsRecRichPreviews(payload, groupsEl);
        if (payload && payload.warnings && payload.warnings.length) {
          setStatus('참고 알림 ' + payload.warnings.length + '건 (경로 계산 한도·화면 기준일 불일치 등)');
        }
      }

      function mergeTargets(acc, batch) {
        var tg = (batch && batch.targets) || [];
        tg.forEach(function (t) {
          acc.push(t);
        });
        return acc;
      }

      function loadRecommendations() {
        var modal = getModal();
        if (!modal || typeof bootstrap === 'undefined') return;
        var ids = collectTargetOrderIds();
        var inst = bootstrap.Modal.getOrCreateInstance(modal);
        inst.show();
        if (!ids.length) {
          setStatus('');
          showProgress(null);
          var emptyA = document.getElementById('shipment-as-rec-empty');
          var groupsA = document.getElementById('shipment-as-rec-groups');
          var linkedA = document.getElementById('shipment-as-rec-linked');
          if (emptyA) emptyA.classList.remove('d-none');
          if (groupsA) groupsA.innerHTML = '';
          if (linkedA) linkedA.classList.add('d-none');
          return;
        }
        var emptyB = document.getElementById('shipment-as-rec-empty');
        if (emptyB) emptyB.classList.add('d-none');
        setStatus('추천을 불러오는 중…');
        showProgress(5);
        var chunks = [];
        for (var i = 0; i < ids.length; i += CHUNK) {
          chunks.push(ids.slice(i, i + CHUNK));
        }
        var merged = { targets: [], partial: false, warnings: [] };
        var step = 0;
        function runChunk() {
          if (step >= chunks.length) {
            showProgress(100);
            setTimeout(function () { showProgress(null); }, 400);
            setStatus(chunks.length > 1 ? '조회 완료 (' + chunks.length + '회 분할 요청)' : '');
            renderAll(merged);
            return;
          }
          var part = chunks[step];
          fetch('/api/erp/shipment/as-recommendations', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
            body: JSON.stringify({
              order_ids: part,
              selected_date: (function () {
                var sd = window.__shipmentAsRecPageDate;
                if (sd == null || sd === '') return null;
                var s = String(sd).trim();
                return s || null;
              })(),
            }),
          })
            .then(function (r) {
              return r.json().then(function (data) {
                if (!r.ok || !data || !data.success) {
                  throw new Error((data && data.message) || 'HTTP ' + r.status);
                }
                return data;
              });
            })
            .then(function (data) {
              mergeTargets(merged.targets, data);
              if (data.partial) merged.partial = true;
              if (data.warnings && data.warnings.length) {
                merged.warnings = merged.warnings.concat(data.warnings);
              }
              step += 1;
              showProgress((step / chunks.length) * 100);
              runChunk();
            })
            .catch(function (err) {
              showProgress(null);
              setStatus('오류: ' + (err && err.message ? err.message : String(err)));
            });
        }
        runChunk();
      }

      function postApply(shipmentOrderId, asOrderId, asInfoId, force) {
        return fetch('/api/erp/shipment/as-recommendations/apply', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
          body: JSON.stringify({
            shipment_order_id: shipmentOrderId,
            as_order_id: asOrderId,
            as_info_id: asInfoId === '' || asInfoId == null ? null : parseInt(asInfoId, 10),
            force: !!force,
          }),
        }).then(function (r) {
          return r.json().then(function (data) {
            return { ok: r.ok, status: r.status, data: data };
          });
        });
      }

      function postCancel(shipmentOrderId, asOrderId, asInfoId) {
        return fetch('/api/erp/shipment/as-recommendations/cancel', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
          body: JSON.stringify({
            shipment_order_id: shipmentOrderId,
            as_order_id: asOrderId,
            as_info_id: asInfoId === '' || asInfoId == null ? null : parseInt(asInfoId, 10),
          }),
        }).then(function (r) {
          return r.json().then(function (data) {
            return { ok: r.ok, status: r.status, data: data };
          });
        });
      }

      if (!window.__shipmentAsRecDocListenersBound) {
        window.__shipmentAsRecDocListenersBound = true;

        document.addEventListener('hidden.bs.modal', function (ev) {
          if (ev.target && ev.target.id === 'scheduleMapModal') {
            resetShipmentAsRecMap();
          }
        });

        document.addEventListener('click', function (ev) {
        var openBtn = ev.target.closest && ev.target.closest('#shipment-as-recommend-btn, [data-shipment-as-recommend-open]');
        if (openBtn) {
          ev.preventDefault();
          adoptModalFromMain();
          loadRecommendations();
          return;
        }

        var cancelBtn = ev.target.closest && ev.target.closest('.js-shipment-as-rec-cancel');
        if (cancelBtn) {
          ev.preventDefault();
          if (!window.confirm('이 AS 일정 연결을 삭제할까요?')) return;
          var csid = parseInt(cancelBtn.getAttribute('data-shipment-order-id'), 10);
          var caid = parseInt(cancelBtn.getAttribute('data-as-order-id'), 10);
          var cinfo = cancelBtn.getAttribute('data-as-info-id');
          postCancel(csid, caid, cinfo).then(function (res) {
            if (res.ok && res.data && res.data.success) {
              window.__shipmentAsRecNeedsReload = true;
              refreshShipmentFragment();
              return;
            }
            window.alert((res.data && res.data.message) || '삭제 실패');
          });
          return;
        }

        var modalRoot = ev.target.closest && ev.target.closest('#shipmentAsRecommendModal');
        if (!modalRoot) return;

        var mapBtn = ev.target.closest && ev.target.closest('.js-shipment-as-rec-map');
        if (mapBtn) {
          ev.preventDefault();
          var refLat = Number(mapBtn.getAttribute('data-ref-lat'));
          var refLng = Number(mapBtn.getAttribute('data-ref-lng'));
          var tgtLat = Number(mapBtn.getAttribute('data-lat'));
          var tgtLng = Number(mapBtn.getAttribute('data-lng'));
          if (!Number.isFinite(refLat) || !Number.isFinite(refLng) || !Number.isFinite(tgtLat) || !Number.isFinite(tgtLng)) {
            return;
          }
          openShipmentAsRecMap(
            mapBtn.getAttribute('data-ref-address') || '',
            refLat,
            refLng,
            tgtLat,
            tgtLng,
            mapBtn.getAttribute('data-address') || '',
            mapBtn.getAttribute('data-name') || '',
            mapBtn.getAttribute('data-score-text') || ''
          );
          return;
        }

        var applyBtn = ev.target.closest && ev.target.closest('.js-shipment-as-rec-apply');
        if (applyBtn && !applyBtn.disabled) {
          ev.preventDefault();
          var row = applyBtn.closest('[data-as-order-id]');
          var errEl = row ? row.querySelector('.js-asrec-err') : null;
          if (errEl) errEl.textContent = '';
          var sid = parseInt(applyBtn.getAttribute('data-shipment-order-id'), 10);
          var aid = parseInt(applyBtn.getAttribute('data-as-order-id'), 10);
          var infoRaw = applyBtn.getAttribute('data-as-info-id');
          var force = false;
          if (applyBtn.getAttribute('data-already-scheduled') === '1') {
            if (!window.confirm('이미 방문일이 있는 AS입니다. 출고 일정으로 덮어쓸까요?')) {
              return;
            }
            force = true;
          }
          postApply(sid, aid, infoRaw, force).then(function (res) {
            if (res.ok && res.data && res.data.success) {
              applyBtn.disabled = true;
              applyBtn.textContent = '추가 완료';
              window.__shipmentAsRecNeedsReload = true;
              refreshShipmentFragment();
              return;
            }
            var msg = (res.data && res.data.message) || '';
            if (res.status === 409 && msg.indexOf('force') >= 0) {
              if (window.confirm(msg + '\n\n강제로 덮어쓸까요?')) {
                return postApply(sid, aid, infoRaw, true).then(function (res2) {
                  if (res2.ok && res2.data && res2.data.success) {
                    applyBtn.disabled = true;
                    applyBtn.textContent = '추가 완료';
                    window.__shipmentAsRecNeedsReload = true;
                    refreshShipmentFragment();
                  } else if (errEl) {
                    errEl.textContent = (res2.data && res2.data.message) || '적용 실패';
                  }
                });
              }
              return;
            }
            if (errEl) errEl.textContent = msg || '적용 실패';
          });
          return;
        }
      }, true);

        document.addEventListener('foms:main-content-swapped', function () {
          if (!document.querySelector('#shipment-dashboard-table')) return;
          adoptModalFromMain();
          scheduleShipmentAsRecPrewarm();
          var el = window.__shipmentAsRecModalEl;
          if (el && el.classList.contains('show') && window.__shipmentAsRecNeedsReload) {
            window.__shipmentAsRecNeedsReload = false;
            loadRecommendations();
          }
        });
      }

      function scheduleShipmentAsRecPrewarm() {
        var ids = collectTargetOrderIds();
        if (!ids.length) return;
        var key = 'shipment-asrec-prewarm:' + window.location.pathname + window.location.search + ':' + ids.join(',');
        try {
          if (sessionStorage.getItem(key) === '1') return;
        } catch (e) { /* ignore */ }
        function run() {
          var chunks = [];
          for (var i = 0; i < ids.length; i += CHUNK) {
            chunks.push(ids.slice(i, i + CHUNK));
          }
          var idx = 0;
          function next() {
            if (idx >= chunks.length) {
              try {
                sessionStorage.setItem(key, '1');
              } catch (e) { /* ignore */ }
              return;
            }
            var part = chunks[idx];
            fetch('/api/erp/shipment/as-recommendations/prewarm', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
              body: JSON.stringify({
                order_ids: part,
                selected_date: (function () {
                  var sd = window.__shipmentAsRecPageDate;
                  if (sd == null || sd === '') return null;
                  var s = String(sd).trim();
                  return s || null;
                })(),
              }),
            }).finally(function () {
              idx += 1;
              next();
            });
          }
          next();
        }
        if (typeof window.requestIdleCallback === 'function') {
          window.requestIdleCallback(function () { run(); }, { timeout: 8000 });
        } else {
          window.setTimeout(run, 1600);
        }
      }

      scheduleShipmentAsRecPrewarm();
    })();
    }

    document.querySelectorAll('.js-shipment-export-trigger').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var exportBtn = document.getElementById('btn-export-image');
        if (exportBtn) {
          exportBtn.click();
        }
      });
    });
