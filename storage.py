"""
Quest 2: 스토리지 추상화 계층
로컬 저장소와 클라우드 스토리지(R2/S3)를 추상화하여 나중에 쉽게 전환 가능하도록 구현
로컬: 기본적으로 로컬 저장소 사용
Railway: R2 환경 변수가 있으면 자동으로 R2 사용
"""
import os
import io
import shutil
from flask import current_app
from werkzeug.utils import secure_filename
from datetime import datetime

# 클라우드 스토리지 사용 시에만 import
try:
    import boto3
    from botocore.exceptions import ClientError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False

# 이미지 처리 (썸네일 생성)
try:
    from PIL import Image
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False


class StorageAdapter:
    """스토리지 추상화 - 로컬 또는 클라우드 스토리지 사용 (자동 감지)"""
    
    def __init__(self):
        # 자동 감지 로직
        self.storage_type = self._detect_storage_type()
        
        if self.storage_type in ['r2', 's3']:
            if not BOTO3_AVAILABLE:
                print("[WARNING] boto3가 설치되지 않았습니다. 로컬 저장소로 폴백합니다.")
                print("[INFO] 클라우드 스토리지를 사용하려면: pip install boto3")
                self.storage_type = 'local'
                self.upload_folder = os.getenv('UPLOAD_FOLDER', 'static/uploads')
                os.makedirs(self.upload_folder, exist_ok=True)
                return
            
            # 클라우드 스토리지 설정
            if self.storage_type == 'r2':
                # Cloudflare R2 설정
                self.account_id = os.getenv('R2_ACCOUNT_ID')
                self.access_key_id = os.getenv('R2_ACCESS_KEY_ID')
                self.secret_access_key = os.getenv('R2_SECRET_ACCESS_KEY')
                self.bucket_name = os.getenv('R2_BUCKET_NAME')
                
                # Endpoint Logic: Prefer explicit R2_ENDPOINT, else construct from Account ID
                self.endpoint_url = os.getenv('R2_ENDPOINT')
                if not self.endpoint_url and self.account_id:
                     self.endpoint_url = f"https://{self.account_id}.r2.cloudflarestorage.com"

                # R2 설정 검증
                if not all([self.endpoint_url, self.access_key_id, self.secret_access_key, self.bucket_name]):
                    missing = []
                    if not self.endpoint_url: missing.append('R2_ENDPOINT (or R2_ACCOUNT_ID)')
                    if not self.access_key_id: missing.append('R2_ACCESS_KEY_ID')
                    if not self.secret_access_key: missing.append('R2_SECRET_ACCESS_KEY')
                    if not self.bucket_name: missing.append('R2_BUCKET_NAME')
                    
                    print(f"[WARNING] R2 환경 변수가 누락되었습니다: {', '.join(missing)}")
                    print("[INFO] 로컬 저장소로 폴백합니다.")
                    self.storage_type = 'local'
                    self.upload_folder = os.getenv('UPLOAD_FOLDER', 'static/uploads')
                    os.makedirs(self.upload_folder, exist_ok=True)
                    return
            else:
                # AWS S3 설정
                self.access_key_id = os.getenv('AWS_ACCESS_KEY_ID')
                self.secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY')
                self.bucket_name = os.getenv('S3_BUCKET_NAME')
                self.region_name = os.getenv('AWS_REGION', 'ap-northeast-2')
                self.endpoint_url = None
                
                # S3 설정 검증
                if not all([self.access_key_id, self.secret_access_key, self.bucket_name]):
                    print("[WARNING] S3 환경 변수가 누락되었습니다. 로컬 저장소로 폴백합니다.")
                    self.storage_type = 'local'
                    self.upload_folder = os.getenv('UPLOAD_FOLDER', 'static/uploads')
                    os.makedirs(self.upload_folder, exist_ok=True)
                    return
            
            # S3 클라이언트 초기화 (R2는 S3 API 호환)
            try:
                self.client = boto3.client(
                    's3',
                    endpoint_url=self.endpoint_url if self.storage_type == 'r2' else None,
                    aws_access_key_id=self.access_key_id,
                    aws_secret_access_key=self.secret_access_key,
                    region_name='auto' if self.storage_type == 'r2' else self.region_name
                )
                print(f"[INFO] [OK] {self.storage_type.upper()} 스토리지가 활성화되었습니다.")
            except Exception as e:
                print(f"[ERROR] 클라우드 스토리지 초기화 실패: {e}")
                print("[INFO] 로컬 저장소로 폴백합니다.")
                self.storage_type = 'local'
                self.upload_folder = os.getenv('UPLOAD_FOLDER', 'static/uploads')
                os.makedirs(self.upload_folder, exist_ok=True)
        else:
            # 로컬 저장소 (개발용)
            self.upload_folder = os.getenv('UPLOAD_FOLDER', 'static/uploads')
            os.makedirs(self.upload_folder, exist_ok=True)
            print(f"[INFO] 로컬 저장소를 사용합니다: {self.upload_folder}")
    
    def _detect_storage_type(self):
        """
        스토리지 타입 자동 감지
        우선순위:
        1. STORAGE_TYPE 환경 변수가 명시적으로 설정된 경우 -> 해당 타입 사용
        2. Railway 환경 감지 + R2 환경 변수 모두 있는 경우 -> r2 자동 사용
        3. 그 외 -> local (로컬 개발 환경)
        """
        # 1. 명시적으로 설정된 경우 (최우선)
        explicit_type = os.getenv('STORAGE_TYPE', '').lower()
        if explicit_type in ['local', 'r2', 's3']:
            if explicit_type == 'local':
                return 'local'
            elif explicit_type == 'r2':
                print("[INFO] STORAGE_TYPE=r2로 명시적으로 설정되었습니다.")
                return 'r2'
            elif explicit_type == 's3':
                print("[INFO] STORAGE_TYPE=s3로 명시적으로 설정되었습니다.")
                return 's3'
        
        # 2. Railway 환경 감지
        is_railway = any([
            os.getenv('RAILWAY_ENVIRONMENT'),
            os.getenv('RAILWAY_SERVICE_NAME'),
            os.getenv('RAILWAY_PROJECT_ID')
        ])
        
        if is_railway:
            # Railway 환경에서 R2 환경 변수 확인
            r2_account_id = os.getenv('R2_ACCOUNT_ID')
            r2_endpoint = os.getenv('R2_ENDPOINT')
            r2_access_key = os.getenv('R2_ACCESS_KEY_ID')
            r2_secret_key = os.getenv('R2_SECRET_ACCESS_KEY')
            r2_bucket = os.getenv('R2_BUCKET_NAME')
            
            # Endpoint나 Account ID 중 하나만 있어도 OK
            if (r2_endpoint or r2_account_id) and r2_access_key and r2_secret_key and r2_bucket:
                print("[INFO] [RAILWAY] Railway 환경에서 R2 환경 변수가 감지되었습니다.")
                print("[INFO] [OK] Cloudflare R2를 자동으로 사용합니다.")
                return 'r2'
            else:
                # Railway 환경이지만 R2 환경 변수가 없음
                missing = []
                if not r2_account_id: missing.append('R2_ACCOUNT_ID')
                if not r2_access_key: missing.append('R2_ACCESS_KEY_ID')
                if not r2_secret_key: missing.append('R2_SECRET_ACCESS_KEY')
                if not r2_bucket: missing.append('R2_BUCKET_NAME')
                
                print("[WARNING] [RAILWAY] Railway 환경이지만 R2 환경 변수가 설정되지 않았습니다.")
                print(f"[WARNING] 누락된 환경 변수: {', '.join(missing)}")
                print("[WARNING] 로컬 저장소를 사용합니다. (재배포 시 파일이 삭제될 수 있음)")
                print("[INFO] 영구 저장을 원하면 Railway 대시보드에서 R2 환경 변수를 설정하세요.")
                return 'local'
        
        # 3. 기본값: 로컬 (로컬 개발 환경)
        return 'local'
    
    def upload_file(self, file_obj, filename, folder='uploads'):
        """파일 업로드 (공통 인터페이스)"""
        if self.storage_type in ['r2', 's3']:
            return self._upload_to_cloud(file_obj, filename, folder)
        else:
            return self._upload_to_local(file_obj, filename, folder)
    
    def upload_chat_file(self, file_obj, filename, message_id, generate_thumbnail=True):
        """채팅 파일 업로드 (썸네일 생성 포함)"""
        file_type = self._get_file_type(filename)
        folder = f"chat/{message_id}"
        
        # 파일 업로드
        result = self.upload_file(file_obj, filename, folder)
        if not result.get('success'):
            return result
        
        key = result.get('key')
        # upload_file()이 생성한 고유 파일명(타임스탬프 포함)을 썸네일 키에도 사용해야
        # 로컬/클라우드 모두에서 경로 충돌/불일치 문제가 없다.
        unique_filename = result.get('filename') or (key.rsplit('/', 1)[-1] if key else filename)

        # 이미지/동영상인 경우 썸네일 생성
        thumbnail_url = None
        thumbnail_key = None
        if file_type in ['image', 'video'] and generate_thumbnail and PILLOW_AVAILABLE:
            thumbnail_key = f"{folder}/thumb_{unique_filename}"
            thumbnail_url = self._generate_thumbnail(file_obj, unique_filename, folder, file_type, key)
        
        return {
            'success': True,
            'key': key,
            'url': result.get('url'),
            'thumbnail_url': thumbnail_url,
            'thumbnail_key': thumbnail_key,
            'file_type': file_type
        }

    def generate_thumbnail_from_storage_key(self, storage_key):
        """기존 업로드 파일(storage_key)에서 썸네일을 생성해 반환"""
        if not PILLOW_AVAILABLE:
            return {'success': False, 'message': 'Pillow unavailable'}

        filename = storage_key.rsplit('/', 1)[-1] if '/' in storage_key else storage_key
        file_type = self._get_file_type(filename)
        if file_type != 'image':
            return {'success': False, 'message': 'Thumbnail is only supported for images'}

        folder = storage_key.rsplit('/', 1)[0] if '/' in storage_key else ''
        thumbnail_key = f"{folder}/thumb_{filename}" if folder else f"thumb_{filename}"

        # 이미 썸네일이 있으면 재사용
        try:
            if self.storage_type in ['r2', 's3']:
                self.client.head_object(Bucket=self.bucket_name, Key=thumbnail_key)
                return {
                    'success': True,
                    'thumbnail_key': thumbnail_key,
                    'thumbnail_url': self._get_public_url(thumbnail_key) if self._is_public_bucket() else self.get_download_url(thumbnail_key)
                }
            else:
                thumb_path = os.path.join(self.upload_folder, thumbnail_key)
                if os.path.exists(thumb_path):
                    return {
                        'success': True,
                        'thumbnail_key': thumbnail_key,
                        'thumbnail_url': f"/static/uploads/{thumbnail_key}"
                    }
        except Exception:
            pass

        try:
            if self.storage_type in ['r2', 's3']:
                obj = self.client.get_object(Bucket=self.bucket_name, Key=storage_key)
                file_obj = io.BytesIO(obj['Body'].read())
            else:
                source_path = os.path.join(self.upload_folder, storage_key)
                if not os.path.exists(source_path):
                    return {'success': False, 'message': 'Source file not found'}
                with open(source_path, 'rb') as f:
                    file_obj = io.BytesIO(f.read())

            thumb_url = self._generate_thumbnail(file_obj, filename, folder, file_type, storage_key)
            if not thumb_url:
                return {'success': False, 'message': 'Thumbnail generation failed'}

            return {
                'success': True,
                'thumbnail_key': thumbnail_key,
                'thumbnail_url': thumb_url
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': f'기존 파일 썸네일 생성 실패: {str(e)}'
            }
    
    def get_download_url(self, key, expires_in=3600):
        """다운로드 URL 생성 (서명된 URL)"""
        if self.storage_type in ['r2', 's3']:
            try:
                url = self.client.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': self.bucket_name, 'Key': key},
                    ExpiresIn=expires_in
                )
                return url
            except ClientError as e:
                print(f"다운로드 URL 생성 오류: {e}")
                return None
        else:
            # 로컬: 직접 경로 반환
            return f"/static/uploads/{key}"
    
    def delete_file(self, key):
        """파일 삭제"""
        if self.storage_type in ['r2', 's3']:
            try:
                self.client.delete_object(Bucket=self.bucket_name, Key=key)
                return True
            except ClientError:
                return False
        else:
            try:
                file_path = os.path.join(self.upload_folder, key)
                if os.path.exists(file_path):
                    os.remove(file_path)
                return True
            except Exception:
                return False
    
    def _upload_to_cloud(self, file_obj, filename, folder):
        """클라우드 스토리지에 업로드"""
        try:
            # 고유한 파일명 생성
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            unique_filename = f"{timestamp}_{secure_filename(filename)}"
            key = f"{folder}/{unique_filename}"
            
            # Content-Type 설정
            content_type = self._get_content_type(filename)
            
            # 파일 업로드
            file_obj.seek(0)  # 파일 포인터 리셋
            self.client.upload_fileobj(
                file_obj,
                self.bucket_name,
                key,
                ExtraArgs={'ContentType': content_type}
            )
            
            # URL 생성
            url = self._get_public_url(key) if self._is_public_bucket() else self.get_download_url(key)
            
            return {
                'success': True,
                'key': key,
                'url': url,
                'filename': unique_filename
            }
        except ClientError as e:
            return {
                'success': False,
                'error': str(e),
                'message': f'클라우드 스토리지 업로드 실패: {str(e)}'
            }
    
    def _upload_to_local(self, file_obj, filename, folder):
        """로컬 저장소에 업로드"""
        try:
            # 폴더 생성
            target_folder = os.path.join(self.upload_folder, folder)
            os.makedirs(target_folder, exist_ok=True)
            
            # 고유한 파일명 생성
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            unique_filename = f"{timestamp}_{secure_filename(filename)}"
            file_path = os.path.join(target_folder, unique_filename)
            
            # 파일 저장 (Werkzeug FileStorage 또는 일반 file 객체 모두 지원)
            file_obj.seek(0)
            if hasattr(file_obj, 'save'):
                # Werkzeug FileStorage 객체
                file_obj.save(file_path)
            else:
                # 일반 file 객체
                with open(file_path, 'wb') as f:
                    shutil.copyfileobj(file_obj, f)
            
            return {
                'success': True,
                'key': f"{folder}/{unique_filename}",
                'url': f"/static/uploads/{folder}/{unique_filename}",
                'filename': unique_filename,
                'path': file_path
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': f'로컬 저장소 업로드 실패: {str(e)}'
            }
    
    def _generate_thumbnail(self, file_obj, filename, folder, file_type, storage_key=None):
        """썸네일 생성 (이미지/동영상)"""
        try:
            if file_type == 'image' and PILLOW_AVAILABLE:
                # 이미지 썸네일
                # NOTE:
                # - 일부 런타임/스토리지 스트림에서 PIL 처리 중 원본 stream 이 닫혀
                #   "I/O operation on closed file"가 발생할 수 있다.
                # - 원본을 bytes로 복제한 메모리 스트림으로 처리해 안정성을 높인다.
                file_obj.seek(0)
                source_bytes = file_obj.read()
                source_stream = io.BytesIO(source_bytes)

                with Image.open(source_stream) as img:
                    # PIL의 lazy loading으로 인한 stream 의존성을 제거
                    img.load()

                    # RGBA/P 모드 이미지는 JPEG 저장 시 오류가 날 수 있어 RGB로 변환
                    if img.mode not in ('RGB', 'L'):
                        img = img.convert('RGB')

                    img.thumbnail((300, 300), Image.Resampling.LANCZOS)

                    # 썸네일 저장
                    thumbnail_bytes = io.BytesIO()
                    img_format = (img.format or '').upper()
                    if img_format == 'PNG':
                        img.save(thumbnail_bytes, format='PNG')
                        thumb_content_type = 'image/png'
                    else:
                        img.save(thumbnail_bytes, format='JPEG', quality=85)
                        thumb_content_type = 'image/jpeg'

                thumbnail_bytes.seek(0)
                thumbnail_filename = f"thumb_{filename}"
                thumbnail_key = f"{folder}/thumb_{filename}"
                
                if self.storage_type in ['r2', 's3']:
                    # 클라우드에 썸네일 업로드
                    self.client.upload_fileobj(
                        thumbnail_bytes,
                        self.bucket_name,
                        thumbnail_key,
                        ExtraArgs={'ContentType': thumb_content_type}
                    )
                    return self._get_public_url(thumbnail_key) if self._is_public_bucket() else self.get_download_url(thumbnail_key)
                else:
                    # 로컬에 썸네일 저장
                    target_folder = os.path.join(self.upload_folder, folder)
                    os.makedirs(target_folder, exist_ok=True)
                    thumbnail_path = os.path.join(target_folder, thumbnail_filename)
                    with open(thumbnail_path, 'wb') as f:
                        f.write(thumbnail_bytes.getvalue())
                    return f"/static/uploads/{folder}/{thumbnail_filename}"
            
            elif file_type == 'video':
                # 동영상 썸네일 (ffmpeg 필요 - 나중에 구현)
                # 현재는 None 반환
                return None
                
        except Exception as e:
            print(f"썸네일 생성 오류: {e}")
            return None
    
    def _get_file_type(self, filename):
        """파일 타입 반환 (image, video, file)"""
        ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        image_exts = ['jpg', 'jpeg', 'png', 'gif', 'webp']
        video_exts = ['mp4', 'mov', 'avi', 'mkv', 'webm']
        
        if ext in image_exts:
            return 'image'
        elif ext in video_exts:
            return 'video'
        else:
            return 'file'
    
    def _get_content_type(self, filename):
        """파일 확장자로 Content-Type 결정"""
        ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        content_types = {
            'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
            'png': 'image/png', 'gif': 'image/gif',
            'webp': 'image/webp',
            'mp4': 'video/mp4', 'mov': 'video/quicktime',
            'avi': 'video/x-msvideo', 'mkv': 'video/x-matroska',
            'webm': 'video/webm',
            'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'xls': 'application/vnd.ms-excel',
            'pdf': 'application/pdf',
            'doc': 'application/msword',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        }
        return content_types.get(ext, 'application/octet-stream')
    
    def _get_public_url(self, key):
        """Public URL 반환 (Public bucket인 경우)"""
        if self.storage_type == 'r2':
            # R2 Public URL
            return f"https://pub-{self.account_id}.r2.dev/{key}"
        elif self.storage_type == 's3':
            # S3 URL
            return f"https://{self.bucket_name}.s3.{self.region_name}.amazonaws.com/{key}"
        return None
    
    def _is_public_bucket(self):
        """Public bucket 여부 확인 (간단한 체크)"""
        # 실제로는 bucket policy를 확인해야 하지만, 여기서는 환경 변수로 제어
        return os.getenv('STORAGE_PUBLIC', 'false').lower() == 'true'


# 전역 인스턴스
_storage_instance = None

def get_storage():
    """스토리지 인스턴스 가져오기 (싱글톤 패턴)"""
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = StorageAdapter()
    return _storage_instance
