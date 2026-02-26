
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

@files_bp.route('/presigned-urls/<path:storage_key>', methods=['GET'])
@login_required
def presigned_urls(storage_key):
    """R2/S3 직접 링크용 presigned URL 반환. 미리보기/다운로드 시 앱 경유 없이 최단 경로."""
    try:
        if '..' in storage_key or storage_key.startswith('/'):
            return jsonify({'success': False, 'message': '비정상적인 경로입니다.'}), 400

        storage = get_storage()
        if storage.storage_type in ['r2', 's3']:
            url = storage.get_download_url(storage_key, expires_in=3600)
            if not url:
                return jsonify({'success': False, 'message': '파일을 찾을 수 없습니다.'}), 404
            return jsonify({'success': True, 'view_url': url, 'download_url': url})

        return jsonify({
            'success': True,
            'view_url': build_file_view_url(storage_key),
            'download_url': build_file_download_url(storage_key),
        })
    except Exception as e:
        print(f"presigned-urls 오류: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


@files_bp.route('/download/<path:storage_key>', methods=['GET'])
@login_required
def download(storage_key):
    """공용 파일 다운로드. R2/S3에서는 presigned URL에 ResponseContentDisposition(attachment)을 넣어 새 창에서도 다운로드되게 함."""
    try:
        if '..' in storage_key or storage_key.startswith('/'):
            return jsonify({'success': False, 'message': '비정상적인 경로입니다.'}), 400

        storage = get_storage()
        if storage.storage_type in ['r2', 's3']:
            filename = os.path.basename(storage_key)
            if not filename:
                filename = 'download'
            filename_safe = filename.replace('"', "'")
            disposition = f'attachment; filename="{filename_safe}"'
            url = storage.get_download_url(storage_key, expires_in=3600, response_content_disposition=disposition)
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
