"""Helpers for periodic Celery tasks."""
import functools
import uuid

from django.core.cache import cache


def exclusive(ttl):
    """Skip a run while the previous one still holds the lock (needs the shared Redis cache).

    Beat fires on a fixed schedule; a slow pass must not overlap the next one.
    ttl is the upper bound for one pass, so a crashed worker cannot block forever.
    """
    def decorate(func):
        key = f'task-lock:{func.__module__}.{func.__name__}'

        @functools.wraps(func)
        def wrapped(*args, **kwargs):
            token = uuid.uuid4().hex
            if not cache.add(key, token, ttl):
                return None
            try:
                return func(*args, **kwargs)
            finally:
                if cache.get(key) == token:
                    cache.delete(key)
        return wrapped
    return decorate
