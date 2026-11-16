import json
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .models import PasswordResetDelivery, RecoveryThrottle, SystemAuditEvent
from .recovery import deliver_reset_mail, GENERIC, INVALID
from .mail_setup import LOCAL_MESSAGE


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', PUBLIC_APP_URL='https://learn.example.test')
class PasswordRecoveryTests(TestCase):
    def setUp(self):
        self.public_directory = TemporaryDirectory()
        self.addCleanup(self.public_directory.cleanup)
        self.public_file = Path(self.public_directory.name) / 'public-url.json'
        public_override = override_settings(LMS_PUBLIC_URL_FILE=self.public_file)
        public_override.enable()
        self.addCleanup(public_override.disable)
        self.User = get_user_model()
        self.user = self.User.objects.create_user(username='recovery_student', email='student@example.test', password='PreviousPassword-2026!')

    def post(self, path, data, **extra):
        return self.client.post('/api/auth/password-reset/' + path, json.dumps(data), content_type='application/json', **extra)

    @override_settings(PUBLIC_APP_URL='', DEBUG=True,
        EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
        EMAIL_HOST='smtp.example.test', DEFAULT_FROM_EMAIL='sender@example.test')
    def test_smtp_uses_published_address_instead_of_local_origin(self):
        self.public_file.write_text(json.dumps({'url': 'https://btbs-example.trycloudflare.com',
            'source': 'temporary_share'}))
        response = self.post('', {'email': self.user.email}, HTTP_ORIGIN='http://127.0.0.1:5173')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PasswordResetDelivery.objects.get().base_url, 'https://btbs-example.trycloudflare.com')

    @override_settings(DEBUG=True, EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
        EMAIL_HOST='smtp.example.test', DEFAULT_FROM_EMAIL='sender@example.test')
    def test_smtp_never_sends_loopback_private_or_insecure_addresses(self):
        for base in ['', 'http://learn.example.test', 'https://localhost', 'https://127.0.0.1',
                     'https://192.168.1.5', 'https://[::1]', 'https://user:pass@example.test']:
            with self.settings(PUBLIC_APP_URL=base):
                self.assertEqual(self.post('', {'email': self.user.email}).status_code, 503)
        self.assertFalse(PasswordResetDelivery.objects.exists())

    def test_explicit_address_wins_and_unapproved_file_is_ignored(self):
        self.public_file.write_text(json.dumps({'url': 'https://btbs-example.trycloudflare.com',
            'source': 'temporary_share'}))
        self.assertEqual(self.post('', {'email': self.user.email}).status_code, 200)
        self.assertEqual(PasswordResetDelivery.objects.get().base_url, 'https://learn.example.test')
        from accounts.public_url import temporary_public_url
        for data in [{'url': 'https://attacker.example.test', 'source': 'temporary_share'},
                     {'url': 'https://btbs-example.trycloudflare.com'}, {'url': 'https://localhost', 'source': 'temporary_share'}]:
            self.public_file.write_text(json.dumps(data))
            self.assertEqual(temporary_public_url(), '')

    def test_publishing_and_stopping_only_clear_matching_temporary_address(self):
        from django.core.management import call_command, CommandError
        from accounts.public_url import temporary_public_url
        address = 'https://btbs-example.trycloudflare.com'
        call_command('publish_temporary_url', url=address, verbosity=0)
        self.assertEqual(temporary_public_url(), address)
        call_command('publish_temporary_url', url='https://another.trycloudflare.com', clear=True)
        self.assertEqual(temporary_public_url(), address)
        call_command('publish_temporary_url', url=address, clear=True)
        self.assertEqual(temporary_public_url(), '')
        with self.assertRaises(CommandError):
            call_command('publish_temporary_url', url='https://example.test')

    def request_link(self, language='en'):
        self.assertEqual(self.post('', {'email': self.user.email, 'language': language}).status_code, 200)
        self.assertEqual(deliver_reset_mail(), 1)
        url = next(line for line in mail.outbox[-1].body.splitlines() if line.startswith('https://'))
        query = parse_qs(urlsplit(url).fragment)
        return {k: query[k][0] for k in ['uid', 'token']}

    def test_same_response_for_known_unknown_inactive_and_unusable_email(self):
        inactive = self.User.objects.create_user(username='inactive', email='inactive@example.test', is_active=False)
        unusable = self.User.objects.create_user(username='unusable', email='unusable@example.test')
        unusable.set_unusable_password(); unusable.save()
        with patch('accounts.recovery.send_mail') as sending:
            for address in [self.user.email, 'missing@example.test', inactive.email, unusable.email]:
                result = self.post('', {'email': address})
                self.assertEqual(result.json(), {'message': LOCAL_MESSAGE, 'delivery_mode': 'local', 'configured': False})
                self.assertIn('no-store', result['Cache-Control'])
            sending.assert_not_called()
        self.assertEqual(PasswordResetDelivery.objects.count(), 1)

    def test_single_use_reset_rejects_old_password_and_invalidates_old_session(self):
        old_session = Client(); old_session.force_login(self.user)
        link = self.request_link()
        result = self.post('confirm/', {**link, 'password': 'NewSecurePassword_2026!', 'confirm_password': 'NewSecurePassword_2026!'})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.post('validate/', link).json()['error'], INVALID)
        self.assertEqual(self.post('confirm/', {**link, 'password': 'AnotherSecure_2026!', 'confirm_password': 'AnotherSecure_2026!'}).status_code, 400)
        self.assertEqual(old_session.get('/api/auth/me/').status_code, 401)
        self.assertFalse(self.client.login(username=self.user.username, password='PreviousPassword-2026!'))
        self.assertTrue(self.client.login(username=self.user.username, password='NewSecurePassword_2026!'))
        audit = SystemAuditEvent.objects.get(action='account.password_reset')
        self.assertEqual(audit.details, {})

    def test_expired_tampered_inactive_and_oversized_uids_rejected(self):
        link = self.request_link()
        future = default_token_generator._now() + timedelta(seconds=3601)
        with patch.object(default_token_generator, '_now', return_value=future):
            self.assertEqual(self.post('validate/', link).status_code, 400)
        for altered in [{}, {**link, 'token': ''}, {**link, 'uid': None}, {**link, 'token': link['token']+'x'}, {**link, 'uid': '!'}, {**link, 'uid': urlsafe_base64_encode(b'9'*60)}]:
            response = self.post('validate/', altered)
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()['error'], INVALID)
        self.user.is_active = False; self.user.save()
        self.assertEqual(self.post('validate/', link).status_code, 400)

    def test_password_validation_and_confirmation_keep_token_usable(self):
        link = self.request_link()
        for password, confirmation in [('short', 'short'), ('NewSecurePassword_2026!', 'different')]:
            self.assertEqual(self.post('confirm/', {**link, 'password': password, 'confirm_password': confirmation}).status_code, 400)
            self.assertEqual(self.post('validate/', link).status_code, 200)

    def test_password_spaces_are_preserved(self):
        link = self.request_link()
        password = '  SecurePasswordWithSpaces_2026!  '
        self.assertEqual(self.post('confirm/', {**link, 'password': password, 'confirm_password': password}).status_code, 200)
        self.user.refresh_from_db(); self.assertTrue(self.user.check_password(password))
        self.assertFalse(self.user.check_password(password.strip()))

    def test_per_email_and_per_ip_limits_survive_requests_without_disclosing_accounts(self):
        for _ in range(4):
            self.assertEqual(self.post('', {'email': self.user.email}).json()['message'], LOCAL_MESSAGE)
        self.assertEqual(PasswordResetDelivery.objects.count(), 3)
        self.assertNotIn(self.user.email, str(list(RecoveryThrottle.objects.values())))
        for _ in range(16):
            self.assertEqual(self.post('', {'email': 'missing@example.test'}).status_code, 200)
        self.assertEqual(self.post('', {'email': self.user.email}).status_code, 429)

    @override_settings(PUBLIC_APP_URL='', DEBUG=True)
    def test_untrusted_origin_cannot_poison_link_but_trusted_local_origin_is_used(self):
        self.post('', {'email': self.user.email}, HTTP_ORIGIN='https://attacker.test')
        self.assertEqual(PasswordResetDelivery.objects.latest('id').base_url, 'http://127.0.0.1:5173')
        self.post('', {'email': self.user.email}, HTTP_ORIGIN='http://localhost:5173')
        self.assertEqual(PasswordResetDelivery.objects.latest('id').base_url, 'http://localhost:5173')

    @override_settings(PUBLIC_APP_URL='', DEBUG=False)
    def test_production_requires_https_address(self):
        self.assertEqual(self.post('', {'email': self.user.email}).status_code, 503)
        self.assertEqual(PasswordResetDelivery.objects.count(), 0)

    def test_pending_mail_cancelled_if_credentials_change(self):
        self.post('', {'email': self.user.email})
        self.user.set_password('ChangedBeforeDelivery_2026!'); self.user.save()
        self.assertEqual(deliver_reset_mail(), 0)
        self.assertEqual(PasswordResetDelivery.objects.get().state, 'cancelled')

    def test_retry_smtp_failure_without_returning_secrets_to_client(self):
        self.post('', {'email': self.user.email})
        with patch('accounts.recovery.send_mail', side_effect=OSError('smtp-secret-example')):
            for _ in range(3):
                PasswordResetDelivery.objects.update(next_attempt_at=timezone.now()-timedelta(seconds=1))
                self.assertEqual(deliver_reset_mail(), 0)
        job = PasswordResetDelivery.objects.get()
        self.assertEqual((job.attempts, job.state), (3, 'failed'))

    def test_mail_is_localized_and_has_no_login_or_existing_password(self):
        for language, phrase in [('ru', 'восстановление пароля'), ('kk', 'құпиясөзді қалпына келтіру'), ('en', 'reset your password')]:
            self.request_link(language)
            self.assertIn(phrase, mail.outbox[-1].subject)
            self.assertNotIn('PreviousPassword-2026!', mail.outbox[-1].body)
            self.assertNotIn(self.user.username, mail.outbox[-1].body)

    def test_csrf_is_required_for_request_and_confirmation(self):
        csrf = Client(enforce_csrf_checks=True)
        for path in ['', 'validate/', 'confirm/']:
            self.assertEqual(csrf.post('/api/auth/password-reset/' + path, '{}', content_type='application/json').status_code, 403)

    def test_local_mail_backend_writes_preview_outside_public_media(self):
        with TemporaryDirectory() as directory, override_settings(EMAIL_BACKEND='accounts.private_files.LocalRecoveryMailBackend', EMAIL_FILE_PATH=directory):
            self.post('', {'email': self.user.email})
            self.assertEqual(deliver_reset_mail(), 1)
            files = list(Path(directory).glob('*.log'))
            self.assertEqual(len(files), 1)
            self.assertIn('https://learn.example.test/', files[0].read_text(encoding='utf-8'))
            self.assertEqual(PasswordResetDelivery.objects.get().state, 'preview')

    def test_public_mail_status_has_no_credentials_or_account_information(self):
        response = self.client.get('/api/auth/password-reset/status/')
        self.assertEqual(response.json(), {'delivery_mode': 'local', 'configured': False})
        self.assertIn('no-store', response['Cache-Control'])

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend', EMAIL_HOST='smtp.example.test', DEFAULT_FROM_EMAIL='BTBS <sender@example.test>')
    def test_smtp_response_is_identical_for_existing_and_missing_accounts(self):
        with patch('accounts.recovery.send_mail') as sending:
            for address in [self.user.email, 'missing@example.test']:
                self.assertEqual(self.post('', {'email': address}).json(), {'message': GENERIC, 'delivery_mode': 'smtp', 'configured': True})
            sending.assert_not_called()

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend', EMAIL_HOST='')
    def test_incomplete_smtp_configuration_is_reported_instead_of_promising_a_letter(self):
        self.assertEqual(self.post('', {'email': self.user.email}).status_code, 503)
        self.assertFalse(PasswordResetDelivery.objects.exists())

    @override_settings(DEFAULT_FROM_EMAIL='BTBS <sender@example.test>')
    def test_reset_link_is_sent_to_the_account_email_and_not_to_the_platform_sender(self):
        self.request_link()
        self.assertEqual(mail.outbox[-1].to, [self.user.email])
        self.assertEqual(mail.outbox[-1].from_email, 'BTBS <sender@example.test>')

    def test_zero_messages_accepted_is_a_delivery_failure(self):
        self.post('', {'email': self.user.email})
        with patch('accounts.recovery.send_mail', return_value=0):
            deliver_reset_mail()
        job = PasswordResetDelivery.objects.get()
        self.assertEqual((job.state, job.attempts), ('pending', 1))
