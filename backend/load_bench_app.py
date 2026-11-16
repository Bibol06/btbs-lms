"""Shared pieces of the load probe: settings overrides and the timing WSGI wrapper.

Used in-process by load_probe_local.py (Waitress) and by Gunicorn workers via
load_bench_wsgi.py, so both servers serve the same disposable database the same way.
"""
import time

from django.conf import settings
from django.db import connection


def apply_overrides(test_name):
    assert test_name.startswith('test_btbs_load_')
    settings.DEBUG = False
    settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
    settings.MEDIA_STORAGE_MODE = 'local'
    settings.ALLOWED_HOSTS = ['127.0.0.1', 'testserver', 'proxy']
    settings.CACHES['default']['KEY_PREFIX'] = test_name


def timed(app):
    def timed_app(environ, start_response):
        started = time.perf_counter()
        sql = [0., 0]

        def measure(execute, statement, params, many, context):
            began = time.perf_counter()
            try:
                return execute(statement, params, many, context)
            finally:
                sql[0] += time.perf_counter() - began
                sql[1] += 1

        def headers(status, response_headers, exc_info=None):
            response_headers += [('X-Bench-App-Ms', str((time.perf_counter()-started)*1000)),
                                 ('X-Bench-Sql-Ms', str(sql[0]*1000))]
            return start_response(status, response_headers, exc_info)
        with connection.execute_wrapper(measure):
            return app(environ, headers)
    return timed_app
