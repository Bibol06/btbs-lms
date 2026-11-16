"""Offline test defaults: never upload fixtures to the configured real S3 bucket."""
import os
os.environ['MEDIA_STORAGE_MODE'] = 'local'
os.environ['LMS_REDIS_URL'] = ''
os.environ['LMS_BACKUP_S3_BUCKET'] = ''
from .settings import *  # noqa: F403
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
MEDIA_CDN_DOMAIN = ''
