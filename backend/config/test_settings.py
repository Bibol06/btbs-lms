"""Offline test defaults: never upload fixtures to the configured real S3 bucket."""
import os
os.environ['MEDIA_STORAGE_MODE'] = 'local'
os.environ['LMS_REDIS_URL'] = ''
os.environ['LMS_BACKUP_S3_BUCKET'] = ''
# Test failures and deliberate errors must never reach the real error tracker.
os.environ['SENTRY_DSN'] = ''
from .settings import *  # noqa: F403
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
MEDIA_CDN_DOMAIN = ''
# Keep test output readable: only errors from the app loggers.
LOGGING['root']['level'] = 'ERROR'  # noqa: F405
for _name in ('django', 'security'):
    LOGGING['loggers'][_name]['level'] = 'ERROR'  # noqa: F405
