"""Public delivery status contains no SMTP credentials or account lookup results."""
from email.utils import parseaddr

from django.conf import settings
from django.core.mail import EmailMessage, get_connection

LOCAL_MESSAGE = 'Запрос принят. Отправка писем на email пока не подключена. Обратитесь к администратору.'
SMTP_UNAVAILABLE = 'Отправка писем временно недоступна. Обратитесь к администратору.'


def send_recovery_mail(subject, message, from_email, recipient_list, fail_silently=False):
    connection = get_connection(fail_silently=fail_silently)
    try:
        connection.open()
        return EmailMessage(subject, message, from_email, recipient_list, connection=connection).send(fail_silently=fail_silently)
    finally:
        # SMTP acknowledgement is checked by send(); a QUIT error cannot undo it.
        try:
            connection.close()
        except Exception:
            pass


def delivery_info():
    smtp = settings.EMAIL_BACKEND == 'django.core.mail.backends.smtp.EmailBackend'
    sender = parseaddr(settings.DEFAULT_FROM_EMAIL)[1]
    configured = bool(settings.EMAIL_HOST and sender and '@localhost' not in sender
                      and not (settings.EMAIL_USE_TLS and settings.EMAIL_USE_SSL)) if smtp else False
    return {'delivery_mode': 'smtp' if smtp else 'local', 'configured': configured}
