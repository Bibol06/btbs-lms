import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings

from .models import SystemAuditEvent


@override_settings(DEBUG=True)
class DemoAdministratorSetupTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.owner = self.User.objects.create_user(username='owner', role='admin', password='OwnerPassword2026!')
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'access.json'
        self.path.write_text(json.dumps({'accounts': {'teacher': {'username': 'existing', 'password': 'preserve-me'}}}), encoding='utf-8')

    def setup_accounts(self):
        output = StringIO()
        call_command('setup_demo_admins', access_file=self.path, stdout=output)
        return output.getvalue()

    def test_separate_scopes_login_credentials_and_repeat_without_password_reset(self):
        output = self.setup_accounts()
        data = json.loads(self.path.read_text(encoding='utf-8'))['accounts']
        for key, scope in [('system_admin', 'system'), ('learning_admin', 'learning')]:
            record = data[key]
            user = self.User.objects.get(pk=record['id'])
            self.assertEqual((user.role, user.admin_scope, user.is_staff, user.is_superuser), ('admin', scope, False, False))
            self.assertTrue(self.client.login(username=record['username'], password=record['password']))
            self.assertEqual(self.client.get('/api/auth/me/').json()['admin_scope'], scope)
            self.assertEqual(self.client.get('/api/auth/system/status/').status_code, 200 if scope == 'system' else 403)
            self.assertNotIn(record['password'], output)
        self.assertEqual(data['teacher']['password'], 'preserve-me')
        self.setup_accounts()
        self.assertEqual(json.loads(self.path.read_text(encoding='utf-8'))['accounts'], data)
        self.assertEqual(SystemAuditEvent.objects.count(), 2)
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.check_password('OwnerPassword2026!'))
        self.assertEqual(self.owner.admin_scope, 'full')

    def test_collision_rolls_back_other_new_account_and_keeps_credentials(self):
        original = self.path.read_bytes()
        collision = self.User.objects.create_user(username='demo_learning_admin', role='student')
        with self.assertRaises(CommandError):
            self.setup_accounts()
        self.assertFalse(self.User.objects.filter(username='demo_system_admin').exists())
        collision.refresh_from_db()
        self.assertEqual(collision.role, 'student')
        self.assertEqual(self.path.read_bytes(), original)

    @override_settings(DEBUG=False)
    def test_production_cannot_create_demo_admins(self):
        with self.assertRaises(CommandError):
            self.setup_accounts()
        self.assertEqual(self.User.objects.count(), 1)
