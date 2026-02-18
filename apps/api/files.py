
from flask import Blueprint, jsonify, redirect, send_file, request
from apps.auth import login_required
from services.storage import get_storage
import os
import traceback


def build_file_view_url(storage_key: str) -> str:
    """파일 미리보기 URL 생성 (files_bp /api/files/view 경로)"""
    return f"/api/files/view/{storage_key}"


def build_file_download_url(storage_key: str) -> str:
    """파일 다운로드 URL 생성 (files_bp /api/files/download 경로)"""
    return f"/api/files/download/{storage_key}"


files_bp = Blueprint('files', __name__, url_prefix='/api/files')

@files_bp.route('/view/<path:storage_key>', methods=['GET'])
@login_required
def view(storage_key):
    """공용 파일 미리보기(인라인)"""
    try:
        if '..' in storage_key or storage_key.startswith('/'):
            return jsonify({'success': False, 'message': '비정상적인 경로입니다.'}), 400

        storage = get_storage()
        if storage.storage_type in ['r2', 's3']:
            url = storage.get_download_url(storage_key, expires_in=3600)
            if not url:
                return jsonify({'success': False, 'message': '파일을 찾을 수 없습니다.'}), 404
            return redirect(url)

        file_path = os.path.join(storage.upload_folder, storage_key)
        if not os.path.exists(file_path):
            return jsonify({'success': False, 'message': '파일을 찾을 수 없습니다.'}), 404
        return send_file(file_path, as_attachment=False)
    except Exception as e:
        print(f"파일 미리보기 오류: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500

@files_bp.route('/download/<path:storage_key>', methods=['GET'])
@login_required
def download(storage_key):
    """공용 파일 다운로드"""
    try:
        if '..' in storage_key or storage_key.startswith('/'):
            return jsonify({'success': False, 'message': '비정상적인 경로입니다.'}), 400

        storage = get_storage()
        if storage.storage_type in ['r2', 's3']:
            url = storage.get_download_url(storage_key, expires_in=3600)
            if not url:
                return jsonify({'success': False, 'message': '파일을 찾을 수 없습니다.'}), 404
            return redirect(url)

        file_path = os.path.join(storage.upload_folder, storage_key)
        if not os.path.exists(file_path):
            return jsonify({'success': False, 'message': '파일을 찾을 수 없습니다.'}), 404
        return send_file(file_path, as_attachment=True)
    except Exception as e:
        print(f"파일 다운로드 오류: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500
