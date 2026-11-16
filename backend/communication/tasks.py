from celery import shared_task

from background import exclusive


@shared_task
@exclusive(ttl=600)
def deadline_pass():
    """Close quiz attempts whose time ran out and persist deadline reminders."""
    from assessment.quiz_services import finalize_due_attempts
    from communication.management.commands.notification_worker import remind_deadlines
    finalize_due_attempts()
    remind_deadlines()
