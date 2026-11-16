"""Settings for the explicitly started, temporary HTTPS demonstration."""
import re
import os

from .settings import *  # noqa: F403

SHARE_HOST = os.environ.get('LMS_SHARE_HOST', '')
if not re.fullmatch(r'[a-z0-9-]+\.trycloudflare\.com', SHARE_HOST):
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured('Запускайте внешнюю демонстрацию через Start-LMS-Share.ps1')

DEBUG = False
ALLOWED_HOSTS = ['127.0.0.1', 'localhost', SHARE_HOST]
CSRF_TRUSTED_ORIGINS = [f'https://{SHARE_HOST}']
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False
STATIC_ROOT = BASE_DIR.parent / '.local' / 'share-static'  # noqa: F405
ROOT_URLCONF = 'config.share_urls'
