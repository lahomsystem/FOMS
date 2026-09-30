function renderBadges(alerts) {
          const a = alerts || {};
          const out = [];
          if (a.urgent) out.push('<span class="badge bg-danger me-1">긴급</span>');
          if (a.drawing_overdue) out.push('<span class="badge bg-danger me-1">도면48h</span>');
          if (a.measurement_d4) out.push('<span class="badge bg-warning text-dark me-1">실측D-4</span>');
          if (a.construction_d3) out.push('<span class="badge bg-warning text-dark me-1">시공D-3</span>');
          if (a.production_d2) out.push('<span class="badge bg-warning text-dark me-1">생산D-2</span>');
          return out.join('') || '<span class="text-muted small">경보 없음</span>';
        }

        // 승인 버튼 공통 전처리: 서버가 준 확인 문구(data-confirm)가 있으면 묻고, 연타를 막기 위해
        // 버튼을 잠근다. 고객 컨펌 승인은 이제 단계 전이(→생산)라 실수 클릭이 되돌리기 어렵다.
        function beginQuestApprove(btn) {
          if (btn && btn.disabled) return false;
          const confirmText = btn && btn.dataset ? btn.dataset.confirm : '';
          if (confirmText && !window.confirm(confirmText)) return false;
          if (btn) btn.disabled = true;
          return true;
        }
        /**
         * 업무 게이트 거부를 관리자 강제 진행으로 한 번만 다시 보낸다(ADMIN-OVERRIDE-01).
         * 뚫렸으면 새 응답을, 아니면 null 을 돌려주고 호출부가 원래 오류를 띄운다.
         */
        async function punchQuestApprove(orderId, body, data) {
          const ctl = window.FomsAdminOverride;
          if (!ctl || typeof ctl.retry !== 'function') return null;
          const again = await ctl.retry({
            url: `/api/orders/${orderId}/quest/approve`,
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: body,
            code: (data && data.code) || '',
            message: (data && (data.message || data.error)) || ''
          });
          return (again && again.ok && again.data && again.data.success) ? again.data : null;
        }

        function failQuestApprove(btn, data) {
          if (btn) btn.disabled = false;
          const detail = data && data.code ? ' (' + data.code + ')' : '';
          alert('처리하지 못했습니다: ' + ((data && (data.message || data.error)) || '알 수 없는 오류') + detail);
        }

        async function approveQuestTeam(orderId, team, btn) {
          if (!beginQuestApprove(btn)) return;
          try {
            const res = await fetch(`/api/orders/${orderId}/quest/approve`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ team: team })
            });
            let data = await res.json();

            if (!data.success) {
              const punched = await punchQuestApprove(orderId, { team: team }, data);
              if (!punched) {
                failQuestApprove(btn, data);
                return;
              }
              data = punched;
            }

            if (window.FOMS_ERP_SHELL && typeof window.FOMS_ERP_SHELL.invalidatePrimaryNavFragmentCache === 'function') {
              window.FOMS_ERP_SHELL.invalidatePrimaryNavFragmentCache();
            }

            let _toastMsg;
            if ((data.retransitioned || data.auto_transitioned) && data.next_stage) {
              _toastMsg = label(STAGE_LABELS, data.next_stage, data.next_stage) + ' 단계로 넘겼습니다';
            } else if (data.all_approved) {
              _toastMsg = '기록했습니다';
            } else {
              const missingTeams = data.missing_teams.map(t => label(TEAM_LABELS, t, t)).join(', ');
              _toastMsg = '기록했습니다 — 남은 팀: ' + missingTeams;
            }
            if (window.fomsFlashToast) { window.fomsFlashToast(_toastMsg); } else { alert(_toastMsg); }

            window.location.reload();
          } catch (err) {
            if (btn) btn.disabled = false;
            console.error('승인 실패:', err);
            alert('처리 중 오류가 발생했습니다.');
          }
        }

        async function approveQuestAssignee(orderId, btn) {
          if (!beginQuestApprove(btn)) return;
          try {
            const res = await fetch(`/api/orders/${orderId}/quest/approve`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({})
            });
            let data = await res.json();

            if (!data.success) {
              const punched = await punchQuestApprove(orderId, {}, data);
              if (!punched) {
                failQuestApprove(btn, data);
                return;
              }
              data = punched;
            }

            if (window.FOMS_ERP_SHELL && typeof window.FOMS_ERP_SHELL.invalidatePrimaryNavFragmentCache === 'function') {
              window.FOMS_ERP_SHELL.invalidatePrimaryNavFragmentCache();
            }

            let _toastMsg;
            if ((data.retransitioned || data.auto_transitioned) && data.next_stage) {
              _toastMsg = label(STAGE_LABELS, data.next_stage, data.next_stage) + ' 단계로 넘겼습니다';
            } else if (data.all_approved) {
              _toastMsg = '기록했습니다';
            }
            if (_toastMsg) {
              if (window.fomsFlashToast) { window.fomsFlashToast(_toastMsg); } else { alert(_toastMsg); }
            }

            window.location.reload();
          } catch (err) {
            if (btn) btn.disabled = false;
            console.error('승인 실패:', err);
            alert('처리 중 오류가 발생했습니다.');
          }
        }
