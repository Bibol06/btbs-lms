import json

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.test import TestCase
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode


class LoginIdentifierTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username='LearnerLogin', email='learner@example.test', password='Before_Reset_2026!')

    def sign_in(self, identifier, password='Before_Reset_2026!'):
        return self.client.post('/api/auth/login/', json.dumps({
            'username': identifier, 'password': password}), content_type='application/json')

    def test_username_email_case_and_keyboard_whitespace(self):
        for identifier in ['LearnerLogin', 'learnerlogin', 'learner@example.test', ' LEARNER@EXAMPLE.TEST ']:
            response = self.sign_in(identifier)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['id'], self.user.pk)
            self.assertEqual(self.client.get('/api/auth/me/').json()['id'], self.user.pk)
            self.client.logout()

    def test_reset_then_sign_in_with_email_and_new_password(self):
        password = '  After_Reset_2026!  '
        link = {'uid': urlsafe_base64_encode(force_bytes(self.user.pk)),
            'token': default_token_generator.make_token(self.user)}
        response = self.client.post('/api/auth/password-reset/confirm/', json.dumps({
            **link, 'password': password, 'confirm_password': password}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.sign_in(self.user.email).status_code, 401)
        self.assertEqual(self.sign_in(self.user.email, password.strip()).status_code, 401)
        self.assertEqual(self.sign_in(self.user.email, password).status_code, 200)

    def test_unknown_wrong_inactive_and_unusable_accounts_have_same_error(self):
        expected = {'error': 'Неверный логин или пароль'}
        for identifier, password in [('missing@example.test', 'wrong'), (self.user.email, 'wrong')]:
            response = self.sign_in(identifier, password)
            self.assertEqual((response.status_code, response.json()), (401, expected))
        self.user.is_active = False
        self.user.save()
        self.assertEqual(self.sign_in(self.user.email).json(), expected)
        self.user.is_active = True
        self.user.set_unusable_password()
        self.user.save()
        self.assertEqual(self.sign_in(self.user.email).status_code, 401)

    def test_ambiguous_email_shaped_username_does_not_select_either_account(self):
        other = get_user_model().objects.create_user(username=self.user.email,
            email='other@example.test', password='Other_Password_2026!')
        for password in ['Before_Reset_2026!', 'Other_Password_2026!']:
            self.assertEqual(self.sign_in(other.username, password).status_code, 401)
        self.assertEqual(self.sign_in(self.user.username).status_code, 200)

    def test_invalid_fields_and_missing_csrf_are_rejected(self):
        for identifier in ['', '  ', None, 123]:
            self.assertEqual(self.sign_in(identifier).status_code, 400)
        from django.test import Client
        response = Client(enforce_csrf_checks=True).post('/api/auth/login/', json.dumps({
            'username': self.user.email, 'password': 'Before_Reset_2026!'}), content_type='application/json')
        self.assertEqual(response.status_code, 403)
