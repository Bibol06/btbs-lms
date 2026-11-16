import json
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts import login_guard
from accounts.models import RecoveryThrottle

PASSWORD = 'Guarded_Login_2026!'


# Many logins per test: a fast hasher keeps the suite quick; the guard logic is hasher-independent.
@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class LoginGuardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username='GuardedUser', email='guarded@example.test', password=PASSWORD)

    def sign_in(self, password, identifier='GuardedUser', ip='198.51.100.10'):
        return self.client.post('/api/auth/login/', json.dumps({'username': identifier, 'password': password}),
                                content_type='application/json', REMOTE_ADDR=ip)

    def fail(self, times, **kwargs):
        for _ in range(times):
            self.assertEqual(self.sign_in('wrong-password', **kwargs).status_code, 401)

    def test_locks_after_five_failures_even_with_correct_password(self):
        self.fail(5)
        response = self.sign_in(PASSWORD)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()['error'], login_guard.LOCKED_MESSAGE)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_lock_is_case_insensitive_for_identifier(self):
        self.fail(5, identifier='guardeduser')
        self.assertEqual(self.sign_in(PASSWORD, identifier='GUARDEDUSER').status_code, 429)

    def test_owner_from_another_ip_is_not_locked_by_one_attacker(self):
        self.fail(5, ip='203.0.113.66')
        self.assertEqual(self.sign_in(PASSWORD, ip='198.51.100.20').status_code, 200)

    def test_account_wide_limit_stops_distributed_guessing(self):
        for n in range(4):
            self.fail(5, ip=f'203.0.113.{n + 1}')
        self.assertEqual(self.sign_in(PASSWORD, ip='198.51.100.30').status_code, 429)

    def test_ip_limit_stops_password_spraying(self):
        for n in range(10):
            self.fail(5, identifier=f'nobody{n}@example.test')
        self.assertEqual(self.sign_in(PASSWORD).status_code, 429)

    def test_success_resets_pair_counter(self):
        self.fail(4)
        self.assertEqual(self.sign_in(PASSWORD).status_code, 200)
        self.client.logout()
        self.fail(4)
        self.assertEqual(self.sign_in(PASSWORD).status_code, 200)

    def test_lock_expires_after_window(self):
        self.fail(5)
        later = timezone.now() + timedelta(seconds=login_guard.WINDOW_SECONDS + 1)
        with mock.patch('accounts.login_guard.timezone.now', return_value=later):
            self.assertEqual(self.sign_in(PASSWORD).status_code, 200)

    def test_raw_identifier_and_ip_are_not_stored(self):
        self.fail(1)
        stored = ' '.join(RecoveryThrottle.objects.values_list('key', flat=True))
        self.assertNotIn('guardeduser', stored.casefold())
        self.assertNotIn('198.51.100.10', stored)


class HealthEndpointTests(TestCase):
    def test_reports_ok_without_details(self):
        response = self.client.get('/api/health/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok', 'checks': {'database': 'ok', 'cache': 'ok'}})
        self.assertIn('no-store', response['Cache-Control'])

    def test_database_failure_returns_503(self):
        with mock.patch('health._database', side_effect=RuntimeError('db down')):
            response = self.client.get('/api/health/')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['checks']['database'], 'fail')
        self.assertNotIn('db down', response.content.decode())

    def test_only_get(self):
        self.assertEqual(self.client.post('/api/health/').status_code, 405)
