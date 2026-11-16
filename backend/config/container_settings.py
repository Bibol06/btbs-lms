"""Local Docker demo behind Nginx, published only on host loopback:8080."""
from .settings import *  # noqa: F403
DEBUG = False
ALLOWED_HOSTS = ['127.0.0.1', 'localhost']
CSRF_TRUSTED_ORIGINS = ['http://127.0.0.1:8080', 'http://localhost:8080']
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
