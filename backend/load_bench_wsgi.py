"""Gunicorn entry point for the load probe. Serves only the disposable test_btbs_load_* database."""
import logging
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
os.environ['SENTRY_DSN'] = ''
import django  # noqa: E402

django.setup()
from django.core.wsgi import get_wsgi_application  # noqa: E402
from django.db import connections  # noqa: E402

from config.proxy_wsgi import trusted_proxy  # noqa: E402
from load_bench_app import apply_overrides, timed  # noqa: E402

test_name = os.environ['LOAD_DB_NAME']
apply_overrides(test_name)
connections['default'].settings_dict['NAME'] = test_name
logging.disable(logging.CRITICAL)
application = trusted_proxy(timed(get_wsgi_application()))
