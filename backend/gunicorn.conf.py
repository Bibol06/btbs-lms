"""Gunicorn settings for the Linux container. Gunicorn loads ./gunicorn.conf.py by default.

Port 8000 is reachable only from Nginx inside the compose network, so the proxy is trusted.
Several processes sidestep the GIL that capped single-process Waitress (see PERFORMANCE_INVESTIGATION_RU.md).
"""
import multiprocessing
import os

wsgi_app = os.getenv('GUNICORN_APP', 'config.proxy_wsgi:application')
bind = os.getenv('GUNICORN_BIND', '0.0.0.0:8000')
worker_class = 'gthread'
workers = int(os.getenv('GUNICORN_WORKERS') or multiprocessing.cpu_count())
threads = int(os.getenv('GUNICORN_THREADS', '4'))
# Code checks run inside the request for up to 20 s; the worker must outlive them.
timeout = int(os.getenv('GUNICORN_TIMEOUT', '60'))
graceful_timeout = 30
keepalive = 5
# Recycle workers periodically so slow memory growth cannot accumulate.
max_requests = 2000
max_requests_jitter = 200
worker_tmp_dir = '/dev/shm'
forwarded_allow_ips = '*'
secure_scheme_headers = {'X-FORWARDED-PROTO': 'https'}
errorlog = '-'
accesslog = None  # Nginx already logs requests
