"""Liveness/readiness probe for Docker, the load balancer and uptime monitors.

Returns only ok/fail per dependency: no versions, hostnames or error text are exposed.
"""
import logging
import uuid

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)


def _database():
    with connection.cursor() as cursor:
        cursor.execute('SELECT 1')
        return cursor.fetchone() == (1,)


def _cache():
    key, value = 'health:probe', uuid.uuid4().hex
    cache.set(key, value, 10)
    return cache.get(key) == value


@never_cache
@require_GET
def health(request):
    checks = {}
    for name, probe in (('database', _database), ('cache', _cache)):
        try:
            checks[name] = 'ok' if probe() else 'fail'
        except Exception:
            logger.exception('health_check_failed', extra={'dependency': name})
            checks[name] = 'fail'
    healthy = all(state == 'ok' for state in checks.values())
    return JsonResponse({'status': 'ok' if healthy else 'fail', 'checks': checks}, status=200 if healthy else 503)
