"""Interactive local setup: secrets never appear in arguments, chat, or logs."""
from datetime import datetime, timezone
from email.utils import formataddr
import getpass
import json
import os
import re
import shutil
import smtplib
import socket
import ssl
import sys
import unicodedata

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.mail.backends.smtp import EmailBackend
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from dotenv import set_key

from accounts.private_files import restrict


def safe_failure(exc, stage, port):
    """Never include SMTP text: it can contain addresses or authentication data."""
    code = getattr(exc, 'smtp_code', None)
    raw = getattr(exc, 'smtp_error', b'')
    if isinstance(raw, bytes):
        raw = raw.decode('ascii', errors='ignore')
    enhanced = re.search(r'\b[245]\.\d{1,3}\.\d{1,3}\b', str(raw))
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        kind = 'authentication'
    elif isinstance(exc, ssl.SSLCertVerificationError):
        kind = 'certificate'
    elif isinstance(exc, (TimeoutError, socket.timeout)):
        kind = 'timeout'
    elif isinstance(exc, smtplib.SMTPServerDisconnected):
        kind = 'disconnected'
    elif isinstance(exc, smtplib.SMTPException):
        kind = 'smtp_rejected'
    else:
        kind = 'network'
    return {'stage': stage, 'port': port, 'kind': kind, 'error_type': type(exc).__name__,
            'smtp_code': code if isinstance(code, int) else None,
            'status': enhanced.group() if enhanced else None}


class Command(BaseCommand):
    help = 'Configure Gmail SMTP locally with a hidden app-password prompt and a test email to the sender.'

    def add_arguments(self, parser):
        parser.add_argument('--sender', required=True)
        parser.add_argument('--port', type=int, choices=[465, 587])
        parser.add_argument('--password-stdin', action='store_true', help='Read once from a private pipe used by the local masked setup window.')

    def handle(self, *args, **options):
        sender = options['sender'].strip()
        validate_email(sender)
        if sender.rsplit('@', 1)[-1].lower() not in ['gmail.com', 'googlemail.com']:
            raise CommandError('This setup helper is for Gmail. Other SMTP providers use backend/.env.')
        if not options['password_stdin'] and not sys.stdin.isatty():
            raise CommandError('Run this command in an interactive local terminal. Do not send the password in chat.')
        if options['password_stdin'] and sys.stdin.isatty():
            raise CommandError('Запустите окно настройки почты. Не вводите секрет в открытой строке терминала.')
        self.stdout.write('Настройка почты BTBS через Gmail')
        self.stdout.write(f'Отправитель: {sender}. Тестовое письмо отправим только на этот же ящик.')
        if not options['password_stdin']:
            self.stdout.write('Создайте пароль приложения BTBS в Google и вставьте его ниже. Ввод скрыт.')
        raw_password = sys.stdin.readline(256) if options['password_stdin'] else getpass.getpass('Пароль приложения Google: ')
        password = ''.join(c for c in raw_password if not c.isspace() and unicodedata.category(c) != 'Cf')
        raw_password = None
        if len(password) != 16 or not password.isascii() or not password.isalnum():
            raise CommandError(f'Нужен 16-символьный пароль приложения Google. Получено символов без пробелов: {len(password)}. Настройки не менялись.')
        local = settings.BASE_DIR.parent / '.local'
        ports = [options['port']] if options['port'] else [465, 587]
        accepted, selected_port = False, None
        for port in ports:
            connection, stage = None, 'connect_login'
            self.stdout.write(f'Подключение к Gmail: порт {port}, защищённое соединение…')
            try:
                connection = EmailBackend(host='smtp.gmail.com', port=port, username=sender, password=password,
                    use_tls=port == 587, use_ssl=port == 465, timeout=30, fail_silently=False)
                connection.open()
                stage = 'send'
                count = EmailMessage('BTBS — проверка отправки писем',
                    'Это проверка подключения почты BTBS.\n\nПисьма восстановления будут приходить каждому пользователю на email его аккаунта LMS. '
                    'Этот ящик используется только как отправитель.\n\nПароль аккаунта LMS не менялся.\n\nBTBS',
                    formataddr(('BTBS', sender)), [sender], connection=connection).send(fail_silently=False)
                if count != 1:
                    raise CommandError('Gmail не подтвердил принятие письма. Настройки не менялись.')
                accepted, selected_port = True, port
                self.stdout.write('Gmail подтвердил принятие тестового письма.')
                break
            except (OSError, smtplib.SMTPException) as exc:
                diagnostic = safe_failure(exc, stage, port)
                local.mkdir(parents=True, exist_ok=True)
                (local / 'mail-setup-diagnostic.json').write_text(json.dumps({
                    'at': datetime.now(timezone.utc).isoformat(), **diagnostic}), encoding='utf-8')
                details = f"Этап: {'подключение и вход' if stage == 'connect_login' else 'отправка письма'}; порт: {port}; причина: {diagnostic['kind']}"
                if diagnostic['smtp_code'] is not None:
                    details += f"; SMTP: {diagnostic['smtp_code']}"
                if diagnostic['status']:
                    details += f"; статус: {diagnostic['status']}"
                if (stage == 'connect_login' and port != ports[-1]
                        and diagnostic['kind'] in ['network', 'timeout', 'disconnected']):
                    self.stdout.write(details + '. Пробуем другой защищённый порт.')
                    continue
                reason = {
                    'authentication': 'Google отклонил доступ. Проверьте пароль приложения и двухэтапную аутентификацию.',
                    'certificate': 'Не прошла проверка сертификата. Проверьте дату Windows и сертификаты системы.',
                    'timeout': 'Сервер не ответил вовремя.',
                    'disconnected': 'Соединение с Gmail оборвалось.',
                    'smtp_rejected': 'Gmail отклонил подключение или письмо.',
                    'network': 'Не удалось связаться с Gmail.',
                }[diagnostic['kind']]
                raise CommandError(reason + ' ' + details + '. Настройки не менялись.') from None
            finally:
                if connection is not None:
                    try:
                        if accepted:
                            connection.close()
                        else:
                            raw = connection.connection or connection._partial_connection
                            if raw is not None:
                                raw.close()
                    except Exception:
                        if accepted:
                            self.stdout.write('Соединение завершилось с ошибкой после принятия письма; отправка уже подтверждена.')
        if not accepted:
            raise CommandError('Тестовое письмо не принято. Настройки не менялись.')
        env_file = settings.BASE_DIR / '.env'
        if not env_file.is_file():
            raise CommandError('backend/.env is missing. Configuration was not written.')
        backup_dir = local / 'private-mail-config' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
        backup_dir.mkdir(parents=True, exist_ok=False)
        restrict(backup_dir, directory=True)
        shutil.copy2(env_file, backup_dir / 'backend.env')
        restrict(env_file)
        staged_env = backup_dir / 'configured.env'
        shutil.copy2(env_file, staged_env)
        restrict(staged_env)
        values = {'EMAIL_BACKEND': 'django.core.mail.backends.smtp.EmailBackend', 'EMAIL_HOST': 'smtp.gmail.com',
            'EMAIL_PORT': str(selected_port), 'EMAIL_USE_TLS': str(selected_port == 587), 'EMAIL_USE_SSL': str(selected_port == 465), 'EMAIL_TIMEOUT': '30',
            'EMAIL_HOST_USER': sender, 'EMAIL_HOST_PASSWORD': password, 'DEFAULT_FROM_EMAIL': formataddr(('BTBS', sender))}
        try:
            for name, value in values.items():
                set_key(str(staged_env), name, value)
            restrict(staged_env)
            os.replace(staged_env, env_file)
            restrict(env_file)
        except Exception:
            shutil.copy2(backup_dir / 'backend.env', env_file)
            restrict(env_file)
            raise CommandError('Could not save SMTP settings. The previous settings were restored.') from None
        (local / 'mail-configured.json').write_text(json.dumps({'configured_at': datetime.now(timezone.utc).isoformat(),
            'provider': 'gmail', 'test_accepted': True}), encoding='utf-8')
        self.stdout.write('Настройки сохранены локально. Gmail принял тестовое письмо. Проверьте входящие и спам.')
        self.stdout.write('Для применения настроек нужно перезапустить backend LMS и службу писем.')
