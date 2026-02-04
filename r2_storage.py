import boto3
import os
from botocore.exceptions import NoCredentialsError
from werkzeug.utils import secure_filename
import uuid

# Configuration
R2_ENDPOINT = os.getenv('R2_ENDPOINT')
R2_ACCESS_KEY_ID = os.getenv('R2_ACCESS_KEY_ID')
R2_SECRET_ACCESS_KEY = os.getenv('R2_SECRET_ACCESS_KEY')
R2_BUCKET_NAME = os.getenv('R2_BUCKET_NAME', 'foms-bucket')

def get_r2_client():
    if not R2_ENDPOINT or not R2_ACCESS_KEY_ID or not R2_SECRET_ACCESS_KEY:
        print("R2 Configuration missing. Falling back to local storage (if compatible).")
        return None
    
    return boto3.client(
        's3',
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        region_name='auto'  # Cloudflare R2 uses 'auto'
    )

def upload_file_to_r2(file_obj, folder='uploads'):
    """
    Uploads a file-like object to Cloudflare R2.
    Returns the public URL (or key) if successful, None otherwise.
    """
    s3 = get_r2_client()
    if not s3:
        return None

    try:
        # Generate unique filename to prevent overwrites
        original_filename = secure_filename(file_obj.filename)
        ext = os.path.splitext(original_filename)[1]
        unique_filename = f"{uuid.uuid4().hex}{ext}"
        object_key = f"{folder}/{unique_filename}"

        # Upload
        s3.upload_fileobj(
            file_obj,
            R2_BUCKET_NAME,
            object_key,
            ExtraArgs={'ContentType': file_obj.content_type}
        )
        
        # Construct Public URL (Assuming a public domain is mapped or using R2.dev)
        # Verify if user has a custom domain or we should use R2.dev link?
        # For now, return the object key or a constructed URL based on endpoint.
        # If R2_PUBLIC_DOMAIN is set, use it.
        public_domain = os.getenv('R2_PUBLIC_DOMAIN')
        if public_domain:
             return f"{public_domain}/{object_key}"
        
        # Fallback: Return key (application needs to know how to serve it, or generate presigned url)
        return object_key

    except Exception as e:
        print(f"R2 Upload Error: {e}")
        return None

def generate_presigned_url(object_key, expiration=3600):
    """Generate a presigned URL to share an S3 object"""
    s3 = get_r2_client()
    if not s3:
        return None
    try:
        response = s3.generate_presigned_url('get_object',
                                             Params={'Bucket': R2_BUCKET_NAME,
                                                     'Key': object_key},
                                             ExpiresIn=expiration)
        return response
    except Exception as e:
        print(f"Presigned URL Error: {e}")
        return None
