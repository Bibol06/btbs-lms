from celery import shared_task

from background import exclusive


@shared_task
@exclusive(ttl=300)
def deliver_recovery_mail():
    from accounts.recovery import deliver_reset_mail
    return deliver_reset_mail()
