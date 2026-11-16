"""Short-lived CloudFront URLs, called only after normal LMS authorization."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from django.conf import settings
from botocore.signers import CloudFrontSigner
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


def signed_media_url(name, seconds=600):
    domain = settings.MEDIA_CDN_DOMAIN
    if not domain:
        return None
    if not name.startswith('_s3/') or '..' in name.split('/'):
        raise ValueError('Invalid CDN object key')
    if not settings.MEDIA_CDN_KEY_ID or not settings.MEDIA_CDN_PRIVATE_KEY_FILE:
        raise ValueError('CDN signing is not configured')
    key = serialization.load_pem_private_key(Path(settings.MEDIA_CDN_PRIVATE_KEY_FILE).read_bytes(), password=None)
    def sign(message):
        return key.sign(message, padding.PKCS1v15(), hashes.SHA1())
    url = 'https://' + domain + '/' + quote(name.removeprefix('_s3/'), safe='/')
    return CloudFrontSigner(settings.MEDIA_CDN_KEY_ID, sign).generate_presigned_url(url, date_less_than=datetime.now(timezone.utc) + timedelta(seconds=seconds))
