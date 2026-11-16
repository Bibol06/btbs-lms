"""Brute-force protection for password login, independent of the Nginx rate limit.

Only failed attempts are counted. Three windows are checked:
- identifier + IP: stops one source guessing one account quickly;
- identifier alone: caps distributed guessing of one account (set higher, so a single
  attacker cannot lock the real owner out from a different network);
- IP alone: caps one source spraying many accounts.
A successful login clears the identifier + IP counter.
"""
import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac

from .models import RecoveryThrottle

logger = logging.getLogger('security')

WINDOW_SECONDS = 15 * 60
LIMITS = {
    'login-pair': 5,
    'login-account': 20,
    'login-ip': 50,
}
LOCKED_MESSAGE = 'Слишком много неудачных попыток входа. Попробуйте снова через 15 минут.'


def _key(kind, value):
    # Store only an HMAC of the identifier/IP, never the raw value.
    return kind + ':' + salted_hmac('btbs.login.limit', value).hexdigest()


def _keys(identifier, ip):
    account = identifier.strip().casefold()
    return {
        'login-pair': _key('login-pair', f'{account}|{ip}'),
        'login-account': _key('login-account', account),
        'login-ip': _key('login-ip', ip),
    }


def _active_count(row, now):
    if row is None or row.window_start <= now - timedelta(seconds=WINDOW_SECONDS):
        return 0
    return row.count


def is_locked(identifier, ip):
    now = timezone.now()
    keys = _keys(identifier, ip)
    rows = {row.key: row for row in RecoveryThrottle.objects.filter(key__in=keys.values())}
    for kind, key in keys.items():
        if _active_count(rows.get(key), now) >= LIMITS[kind]:
            logger.warning('login_locked', extra={'limit': kind, 'ip': ip})
            return True
    return False


def register_failure(identifier, ip):
    now = timezone.now()
    with transaction.atomic():
        for kind, key in _keys(identifier, ip).items():
            row, _ = RecoveryThrottle.objects.get_or_create(key=key, defaults={'window_start': now})
            row = RecoveryThrottle.objects.select_for_update().get(pk=row.pk)
            if row.window_start <= now - timedelta(seconds=WINDOW_SECONDS):
                row.window_start, row.count = now, 0
            row.count = min(row.count + 1, LIMITS[kind] + 1)
            row.save(update_fields=['window_start', 'count'])
    logger.info('login_failed', extra={'ip': ip})


def register_success(identifier, ip):
    RecoveryThrottle.objects.filter(key=_keys(identifier, ip)['login-pair']).delete()
