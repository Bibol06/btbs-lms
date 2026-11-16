import json
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class RegistrationTests(TestCase):
    def test_registration_always_student(self):
        response = self.client.post('/api/auth/register/',
            data=json.dumps({
                'username': 'student_new',
                'email': 'studentnew@example.com',
                'password': 'TestPass-2026-Private',
                'role': 'admin',
                'is_superuser': True,
            }), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        user = get_user_model().objects.get(username='student_new')
        self.assertEqual(user.role, 'student')
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(self.client.get('/api/auth/me/').status_code, 200)

    def test_registration_duplicate_username(self):
        User = get_user_model()
        User.objects.create_user(username='taken', password='OldPass_909090')
        response = self.client.post('/api/auth/register/', data=json.dumps({
            'username': 'taken', 'email': 'another@example.com',
            'password': 'TestPass-2026-Private',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 409)

    def test_anonymous_cannot_list_users(self):
        self.assertEqual(self.client.get('/api/auth/users/').status_code, 401)

    def test_csrf_protection_blocks_registration_without_token(self):
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        response = client.post('/api/auth/register/', data=json.dumps({
            'username': 'blocked', 'email': 'blocked@example.com',
            'password': 'TestPass-2026-Private',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 403)


class ProfileTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.student = User.objects.create_user(username='profile_student', email='private@example.test')
        cls.teacher = User.objects.create_user(username='profile_teacher', role='teacher', first_name='Anna')
        from courses.models import Course, Enrollment
        cls.public = Course.objects.create(title='Public', teacher=cls.teacher, is_published=True)
        cls.private = Course.objects.create(title='Private', teacher=cls.teacher)
        Enrollment.objects.create(course=cls.private, student=cls.student)

    def test_profile_requires_authentication(self):
        self.assertEqual(self.client.get('/api/auth/profile/').status_code, 401)
        self.assertEqual(self.client.get(f'/api/auth/profiles/{self.student.id}/').status_code, 401)

    def test_edit_my_profile_cannot_change_permissions(self):
        self.client.force_login(self.student)
        response = self.client.patch('/api/auth/profile/', data=json.dumps({
            'first_name': 'Dana', 'last_name': 'Learner', 'bio': 'Learning Python',
            'organization': 'College', 'city': 'Almaty', 'role': 'admin', 'is_superuser': True,
            'email': 'changed@example.test', 'username': 'stolen',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['display_name'], 'Learner Dana')
        self.student.refresh_from_db()
        self.assertEqual(self.student.role, 'student')
        self.assertFalse(self.student.is_superuser)
        self.assertEqual(self.student.email, 'private@example.test')
        self.assertEqual(self.student.username, 'profile_student')
        self.assertEqual(self.student.bio, 'Learning Python')
        self.assertEqual(self.client.get('/api/auth/me/').json()['display_name'], 'Learner Dana')

    def test_public_profile_omits_email_enrollments_and_drafts(self):
        self.client.force_login(self.student)
        data = self.client.get(f'/api/auth/profiles/{self.teacher.id}/').json()
        self.assertNotIn('email', data)
        self.assertNotIn('learning', data)
        self.assertEqual([c['id'] for c in data['teaching_courses']], [self.public.id])
        self.client.force_login(self.teacher)
        other = self.client.get(f'/api/auth/profiles/{self.student.id}/').json()
        self.assertNotIn('email', other)
        self.assertNotIn('learning', other)
        own = self.client.get('/api/auth/profile/').json()
        self.assertEqual(len(own['teaching_courses']), 2)

    def test_profile_validation_and_no_edit_of_other_user(self):
        self.client.force_login(self.student)
        for fields in [{'bio': 'x' * 3001}, {'city': 22}, {'first_name': ['invalid']}]:
            self.assertEqual(self.client.patch('/api/auth/profile/', data=json.dumps(fields), content_type='application/json').status_code, 400)
        self.assertEqual(self.client.patch(f'/api/auth/profiles/{self.teacher.id}/', data='{}', content_type='application/json').status_code, 405)


class LanguagePreferenceTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.student = User.objects.create_user(username='locale_student', password='Locale-Test-2030', first_name='Сохранить')
        self.other = User.objects.create_user(username='locale_other', preferred_language='en')

    def patch(self, payload):
        return self.client.patch('/api/auth/preferences/', data=json.dumps(payload), content_type='application/json')

    def test_preferences_require_authentication(self):
        self.assertEqual(self.client.get('/api/auth/preferences/').status_code, 401)
        self.assertEqual(self.patch({'language': 'kk'}).status_code, 401)

    def test_all_three_languages_persist_without_changing_permissions(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get('/api/auth/preferences/').json()['language'], '')
        for language in ['kk', 'ru', 'en']:
            self.assertEqual(self.patch({'language': language, 'role': 'admin', 'user_id': self.other.id}).status_code, 200)
            self.student.refresh_from_db()
            self.assertEqual(self.student.preferred_language, language)
            self.assertEqual(self.student.role, 'student')
            self.assertEqual(self.student.first_name, 'Сохранить')
            self.assertEqual(self.client.get('/api/auth/me/').json()['preferred_language'], language)
        self.other.refresh_from_db()
        self.assertEqual(self.other.preferred_language, 'en')

    def test_language_is_private_and_survives_sign_in(self):
        self.client.force_login(self.student)
        self.patch({'language': 'kk'})
        self.assertEqual(self.client.get('/api/auth/profile/').json()['preferred_language'], 'kk')
        self.assertNotIn('preferred_language', self.client.get(f'/api/auth/profiles/{self.other.id}/').json())
        self.client.logout()
        data = self.client.post('/api/auth/login/', data=json.dumps({'username': 'locale_student', 'password': 'Locale-Test-2030'}), content_type='application/json').json()
        self.assertEqual(data['preferred_language'], 'kk')

    def test_invalid_language_never_changes_saved_preference(self):
        self.client.force_login(self.student)
        self.patch({'language': 'ru'})
        for value in ['kz', 'fr', '', None, 42, ['en'], {'code': 'en'}]:
            self.assertEqual(self.patch({'language': value}).status_code, 400)
        for payload in [[], 'en', None]:
            self.assertEqual(self.patch(payload).status_code, 400)
        self.student.refresh_from_db()
        self.assertEqual(self.student.preferred_language, 'ru')

    def test_language_cannot_be_written_through_public_profile(self):
        self.client.force_login(self.student)
        self.client.patch('/api/auth/profile/', data=json.dumps({'preferred_language': 'en', 'role': 'admin'}), content_type='application/json')
        self.student.refresh_from_db()
        self.assertEqual(self.student.preferred_language, '')
        self.assertEqual(self.student.role, 'student')

    def test_preferences_keep_csrf_protection(self):
        from django.test import Client
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.student)
        self.assertEqual(strict.patch('/api/auth/preferences/', data='{"language":"en"}', content_type='application/json').status_code, 403)
