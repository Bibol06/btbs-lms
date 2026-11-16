import tempfile
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.test import SimpleTestCase, override_settings
from cdn import signed_media_url


class CdnTests(SimpleTestCase):
    @override_settings(MEDIA_CDN_DOMAIN='')
    def test_disabled_uses_existing_s3_path(self):
        self.assertIsNone(signed_media_url('_s3/courses/course-1/video.mp4'))

    def test_signed_private_url_and_reject_staging(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'test.pem'
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
            with override_settings(MEDIA_CDN_DOMAIN='test.cloudfront.net', MEDIA_CDN_KEY_ID='TESTKEY', MEDIA_CDN_PRIVATE_KEY_FILE=str(path)):
                result = urlsplit(signed_media_url('_s3/courses/course-1/video.mp4'))
                self.assertEqual(result.path, '/courses/course-1/video.mp4')
                self.assertEqual(set(parse_qs(result.query)), {'Expires','Signature','Key-Pair-Id'})
                with self.assertRaises(ValueError): signed_media_url('_staging/private.mp4')
