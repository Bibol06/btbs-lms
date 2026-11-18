"""Isolated QA / e2e environment: its own database, local media, no S3, Redis, Sentry or real mail.

    DB_NAME=lms_qa python manage.py runserver 127.0.0.1:8100 --settings=config.qa_settings

Process environment wins over backend/.env (load_dotenv does not override), so the
values below are forced here and the working .env is never edited.
"""
import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_QA = _ROOT / '.local' / 'qa'
os.environ['DB_NAME'] = os.environ.get('QA_DB_NAME', 'lms_qa')
os.environ['MEDIA_STORAGE_MODE'] = 'local'
os.environ['MEDIA_ROOT'] = str(_QA / 'media')
os.environ['LMS_REDIS_URL'] = ''
os.environ['LMS_CELERY_BROKER_URL'] = ''
os.environ['LMS_BACKUP_S3_BUCKET'] = ''
os.environ['LMS_BACKUP_DIR'] = str(_QA / 'backups')
os.environ['SENTRY_DSN'] = ''
os.environ['DJANGO_DEBUG'] = 'True'
os.environ['MEDIA_CDN_DOMAIN'] = ''
os.environ.setdefault('DJANGO_SECRET_KEY', 'qa-only-not-a-secret-0123456789abcdefghijklmnopqrstuv')

from .settings import *  # noqa: E402,F403
from .settings import DATABASES

if not DATABASES['default']['NAME'].startswith('lms_qa'):
    raise RuntimeError('qa_settings may only use a database whose name starts with lms_qa')

ALLOWED_HOSTS = ['127.0.0.1', 'localhost', 'testserver']
CSRF_TRUSTED_ORIGINS = ['http://127.0.0.1:5174', 'http://localhost:5174', 'http://127.0.0.1:8100']
MEDIA_CDN_DOMAIN = ''
EMAIL_BACKEND = 'django.core.mail.backends.filebased.EmailBackend'
EMAIL_FILE_PATH = str(_QA / 'mail')
LMS_DEMO_ACCESS_FILE = _QA / 'demo-access.json'
LMS_QA_ACCESS_FILE = _QA / 'qa-accounts.json'
