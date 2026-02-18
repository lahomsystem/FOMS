"""백업 API Blueprint.

POST /api/simple_backup - 백업 백그라운드 시작
GET /api/backup_status - 백업 상태 조회
"""
import os
import json
import threading
from flask import Blueprint, jsonify, session

from apps.auth import login_required, role_required, log_access
from simple_backup_system import SimpleBackupSystem

backup_bp = Blueprint('backup', __name__, url_prefix='')

# 백업 백그라운드 실행 상태 (타임아웃/연결 끊김 방지)
_backup_state = {"running": False, "result": None, "error": None}
_backup_state_lock = threading.Lock()


def _run_backup_job():
    """백그라운드에서 백업 실행 후 상태 갱신."""
    global _backup_state
    try:
        backup_system = SimpleBackupSystem()
        results = backup_system.execute_backup()
        success_count = sum(1 for r in results.values() if r["success"])
        with _backup_state_lock:
            _backup_state["running"] = False
            _backup_state["result"] = {
                "success_count": success_count,
                "total_tiers": 2,
                "results": results,
            }
            _backup_state["error"] = None
    except Exception as e:
        with _backup_state_lock:
            _backup_state["running"] = False
            _backup_state["result"] = None
            _backup_state["error"] = str(e)


@backup_bp.route('/api/simple_backup', methods=['POST'])
@login_required
@role_required(['ADMIN'])
def execute_simple_backup():
    """간단한 2단계 백업을 백그라운드에서 시작하고 즉시 응답 (타임아웃/ERR_CONNECTION_RESET 방지)."""
    global _backup_state
    try:
        with _backup_state_lock:
            if _backup_state["running"]:
                return jsonify({
                    "success": True,
                    "message": "이미 백업이 실행 중입니다. 1~2분 후 '백업 상태'를 새로고침하세요.",
                    "backup_started": False,
                    "backup_in_progress": True,
                })
            _backup_state["running"] = True
            _backup_state["result"] = None
            _backup_state["error"] = None
        thread = threading.Thread(target=_run_backup_job, daemon=True)
        thread.start()
        log_access("백업 백그라운드 시작", session.get("user_id"))
        return jsonify({
            "success": True,
            "message": "백업이 백그라운드에서 시작되었습니다. 1~2분 후 아래 '백업 상태'를 새로고침하세요.",
            "backup_started": True,
            "backup_in_progress": True,
        })
    except Exception as e:
        with _backup_state_lock:
            _backup_state["running"] = False
        log_access(f"백업 시작 실패: {str(e)}", session.get("user_id"))
        return jsonify({
            "success": False,
            "message": str(e),
        }), 500


@backup_bp.route('/api/backup_status')
@login_required
@role_required(['ADMIN'])
def check_backup_status():
    """백업 상태 확인 (백업 진행 중 여부 및 마지막 백업 결과 포함)."""
    global _backup_state
    try:
        backup_system = SimpleBackupSystem()
        status = {
            "tier1": {
                "path": backup_system.tier1_path,
                "exists": os.path.exists(backup_system.tier1_path),
                "latest_backup": None
            },
            "tier2": {
                "path": backup_system.tier2_path,
                "exists": os.path.exists(backup_system.tier2_path),
                "latest_backup": None
            }
        }
        for tier_name, tier_info in status.items():
            if tier_info["exists"]:
                try:
                    info_file = os.path.join(tier_info["path"], "backup_info.json")
                    if os.path.exists(info_file):
                        with open(info_file, "r", encoding="utf-8") as f:
                            tier_info["latest_backup"] = json.load(f)
                except Exception as e:
                    tier_info["error"] = str(e)
        with _backup_state_lock:
            backup_in_progress = _backup_state["running"]
            last_result = _backup_state["result"]
            last_error = _backup_state["error"]
        return jsonify({
            "success": True,
            "status": status,
            "backup_in_progress": backup_in_progress,
            "last_backup_result": last_result,
            "last_backup_error": last_error,
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e),
        }), 500
