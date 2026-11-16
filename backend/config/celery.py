"""Celery application. Without LMS_CELERY_BROKER_URL tasks run inline (Windows dev, tests)."""
import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
app = Celery('btbs')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
