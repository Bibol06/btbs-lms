import logging
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.db import DatabaseError, transaction
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(user_logged_in, dispatch_uid='analytics_login')
def login_record(sender, request, user, **kwargs):
    from .tracking import touch_session
    try:
        with transaction.atomic():
            touch_session(request, login=True, user=user)
    except DatabaseError:
        logger.exception('Login analytics unavailable')


@receiver(user_logged_out, dispatch_uid='analytics_logout')
def logout_record(sender, request, user, **kwargs):
    from .tracking import finish_session
    if request is None:
        return
    try:
        with transaction.atomic():
            finish_session(request)
    except DatabaseError:
        logger.exception('Logout analytics unavailable')
