"""Single-use Django reset tokens, queued mail and persistent request limits."""
from datetime import timedelta
from urllib.parse import urlencode, urlsplit

from django.conf import settings
from django.contrib.auth import get_user_model, logout
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.validators import validate_email
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.http import require_POST, require_GET

from common import api, body, text, ApiError
from .models import PasswordResetDelivery, RecoveryThrottle, SystemAuditEvent
from .mail_setup import delivery_info, LOCAL_MESSAGE, SMTP_UNAVAILABLE
from .mail_setup import send_recovery_mail as send_mail
from .public_url import external_https_url, temporary_public_url

GENERIC = 'Если этот email зарегистрирован, мы отправим ссылку для восстановления пароля.'
INVALID = 'Ссылка недействительна или срок её действия истёк. Запросите новую.'


def private_response(data, status=200):
    response = JsonResponse(data, status=status)
    response['Cache-Control'] = 'no-store'
    response['Referrer-Policy'] = 'no-referrer'
    return response


def credential_stamp(user):
    return salted_hmac('btbs.recovery.credentials', f'{user.pk}:{user.email}:{user.password}', algorithm='sha256').hexdigest()


def allow(key, limit, seconds):
    now = timezone.now()
    with transaction.atomic():
        row, _ = RecoveryThrottle.objects.get_or_create(key=key, defaults={'window_start': now})
        row = RecoveryThrottle.objects.select_for_update().get(pk=row.pk)
        if row.window_start <= now - timedelta(seconds=seconds):
            row.window_start, row.count = now, 0
        allowed = row.count < limit
        row.count = min(row.count + 1, limit + 1)
        row.save(update_fields=['window_start', 'count'])
    return allowed


def throttle_key(kind, value):
    return kind + ':' + salted_hmac('btbs.recovery.limit', value).hexdigest()


def reset_base_url(request):
    configured = settings.PUBLIC_APP_URL
    origin = request.headers.get('Origin', '')
    base = configured or temporary_public_url() or (origin if origin in settings.CSRF_TRUSTED_ORIGINS else '')
    if not base and settings.DEBUG:
        base = 'http://127.0.0.1:5173'
    try:
        parts = urlsplit(base)
    except ValueError:
        raise ApiError('Администратору нужно настроить адрес платформы для восстановления пароля.', 503)
    if not base or parts.scheme not in ['https', 'http'] or not parts.netloc or parts.username or parts.password or parts.query or parts.fragment:
        raise ApiError('Администратору нужно настроить адрес платформы для восстановления пароля.', 503)
    if (not settings.DEBUG or delivery_info()['delivery_mode'] == 'smtp') and not external_https_url(base):
        raise ApiError('Для восстановления пароля нужен HTTPS-адрес платформы.', 503)
    return base.rstrip('/')


@require_GET
def reset_delivery_status(request):
    return private_response(delivery_info())


@require_POST
@api
def request_reset(request):
    values = body(request)
    email = text(values, 'email', 254, required=True).strip()
    validate_email(email)
    delivery = delivery_info()
    if delivery['delivery_mode'] == 'smtp' and not delivery['configured']:
        return private_response({'error': SMTP_UNAVAILABLE}, 503)
    base = reset_base_url(request)
    if not allow(throttle_key('request-ip', request.META.get('REMOTE_ADDR', '')), 20, 3600):
        return private_response({'error': 'Слишком много запросов. Попробуйте позже.'}, 429)
    if allow(throttle_key('email', email.casefold()), 3, 900):
        user = get_user_model().objects.filter(email__iexact=email, is_active=True).first()
        if user and user.has_usable_password():
            language = values.get('language', 'ru')
            PasswordResetDelivery.objects.create(user=user, credential_stamp=credential_stamp(user), base_url=base,
                language=language if language in ['ru', 'kk', 'en'] else 'ru', next_attempt_at=timezone.now())
    return private_response({'message': GENERIC if delivery['delivery_mode'] == 'smtp' else LOCAL_MESSAGE, **delivery})


def token_user(values, lock=False):
    uid, token = values.get('uid'), values.get('token')
    if not all(isinstance(value, str) and 0 < len(value) <= 100 for value in [uid, token]):
        raise ApiError(INVALID)
    try:
        pk = int(urlsafe_base64_decode(uid).decode())
        if not 0 < pk <= 2**63-1:
            raise ValueError()
        users = get_user_model().objects
        user = (users.select_for_update() if lock else users).get(pk=pk, is_active=True)
    except (ValueError, UnicodeError, OverflowError, get_user_model().DoesNotExist):
        raise ApiError(INVALID)
    if not user.has_usable_password() or not default_token_generator.check_token(user, token):
        raise ApiError(INVALID)
    return user


@require_POST
@api
def validate_reset(request):
    if not allow(throttle_key('token-ip', request.META.get('REMOTE_ADDR', '')), 60, 900):
        return private_response({'error': 'Слишком много запросов. Попробуйте позже.'}, 429)
    token_user(body(request))
    return private_response({'valid': True})


@require_POST
@api
def confirm_reset(request):
    if not allow(throttle_key('confirm-ip', request.META.get('REMOTE_ADDR', '')), 30, 900):
        return private_response({'error': 'Слишком много запросов. Попробуйте позже.'}, 429)
    values = body(request)
    password = values.get('password')
    if not isinstance(password, str) or not password or len(password) > 256:
        raise ApiError('Введите новый пароль длиной до 256 символов')
    if password != values.get('confirm_password'):
        raise ApiError('Пароли не совпадают')
    with transaction.atomic():
        user = token_user(values, lock=True)
        validate_password(password, user=user)
        user.set_password(password)
        user.save(update_fields=['password'])
        PasswordResetDelivery.objects.filter(user=user, state='pending').update(state='cancelled')
        from analytics.models import SessionRecord
        SessionRecord.objects.filter(user=user, ended_at__isnull=True).update(ended_at=timezone.now(), end_reason='password_reset')
        SystemAuditEvent.objects.create(actor=user, target=user, action='account.password_reset')
    if request.user.is_authenticated and request.user.pk == user.pk:
        logout(request)
    return private_response({'message': 'Пароль изменён. Войдите с новым паролем.'})


def deliver_reset_mail(limit=10):
    now = timezone.now()
    delivered = 0
    for _ in range(limit):
        with transaction.atomic():
            job = PasswordResetDelivery.objects.select_for_update(skip_locked=True).filter(state='pending', next_attempt_at__lte=now).select_related('user').order_by('id').first()
            if not job:
                break
            user = job.user
            if (not user.is_active or not user.has_usable_password() or not user.email
                    or job.created_at < now-timedelta(hours=1) or not constant_time_compare(job.credential_stamp, credential_stamp(user))):
                job.state = 'cancelled'
                job.save(update_fields=['state'])
                continue
            query = urlencode({'page': 'reset-password', 'uid': urlsafe_base64_encode(force_bytes(user.pk)), 'token': default_token_generator.make_token(user)})
            url = f'{job.base_url}/#{query}'
            titles = {'ru': 'BTBS — восстановление пароля', 'kk': 'BTBS — құпиясөзді қалпына келтіру', 'en': 'BTBS — reset your password'}
            bodies = {
                'ru': 'Для смены пароля откройте ссылку:\n{url}\n\nСсылка действует один час и используется один раз. Если вы не запрашивали смену пароля, проигнорируйте это письмо.\n\nBTBS',
                'kk': 'Құпиясөзді өзгерту үшін сілтемені ашыңыз:\n{url}\n\nСілтеме бір сағат жарамды және бір рет қолданылады. Құпиясөзді өзгертуді сұрамаған болсаңыз, бұл хатты елемеңіз.\n\nBTBS',
                'en': 'Open this link to set a new password:\n{url}\n\nThe link expires in one hour and can be used once. If you did not request a password reset, you can ignore this email.\n\nBTBS',
            }
            job.attempts += 1
            try:
                count = send_mail(titles[job.language], bodies[job.language].format(url=url), settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False)
                if count != 1:
                    raise RuntimeError('Mail backend did not accept the message')
            except Exception:
                job.state = 'failed' if job.attempts >= 3 else 'pending'
                job.next_attempt_at = now + timedelta(minutes=2 ** job.attempts)
            else:
                job.state, job.sent_at = ('sent' if delivery_info()['delivery_mode'] == 'smtp' else 'preview'), now
                delivered += 1
            job.save(update_fields=['attempts', 'state', 'sent_at', 'next_attempt_at'])
    RecoveryThrottle.objects.filter(window_start__lt=now-timedelta(days=2)).delete()
    PasswordResetDelivery.objects.filter(created_at__lt=now-timedelta(days=7)).delete()
    return delivered
