import csv
import io
import json
import re
from pathlib import Path
from django.test import TestCase
from django.contrib.auth import get_user_model
from courses.models import Course, CourseRun, Enrollment
from assessment.models import Assignment
from localization import translate, request_language


class LocalizedReportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.teacher = User.objects.create_user(username='report_locale_teacher', role='teacher', preferred_language='kk')
        cls.student = User.objects.create_user(username='report_locale_student', first_name='Сохранить', last_name='Студент')
        cls.course = Course.objects.create(teacher=cls.teacher, title='Курс', is_published=True)
        cls.offering = CourseRun.objects.create(course=cls.course, title='Группа', kind='cohort')
        Enrollment.objects.create(course=cls.course, run=cls.offering, student=cls.student)
        Assignment.objects.create(course=cls.course, title='Сохранить', is_published=True)

    def test_gradebook_localizes_headers_but_preserves_authored_titles_and_names(self):
        self.client.force_login(self.teacher)
        for language, header in [('kk', 'Студент'), ('en', 'Student'), ('ru', 'Студент')]:
            response = self.client.get(f'/api/study/courses/{self.course.id}/report.csv', {'run_id': self.offering.id, 'language': language})
            self.assertEqual(response.status_code, 200)
            rows = list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
            self.assertEqual(rows[0][0], header)
            self.assertIn('Сохранить', rows[0])
            self.assertEqual(rows[1][0], 'Студент Сохранить')

    def test_analytics_export_uses_account_preference_or_explicit_language(self):
        self.client.force_login(self.teacher)
        from courses.models import default_run
        Enrollment.objects.create(course=self.course, run=default_run(self.course), student=self.student)
        for language, period, name in [('', 'Кезең', 'Аты'), ('en', 'Period', 'First name'), ('ru', 'Период', 'Имя')]:
            response = self.client.get('/api/analytics/export/', {'kind': 'learners', 'language': language})
            self.assertEqual(response.status_code, 200)
            rows = list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
            self.assertEqual(rows[0][0], period)
            self.assertEqual(rows[1][0], name)
            self.assertEqual(rows[2][0], 'Студент Сохранить')
            self.assertEqual(rows[2][1], 'Курс')
            self.assertIn(translate('Самостоятельное обучение', language or 'kk'), [row[2] for row in rows[2:]])

    def test_localized_export_keeps_authorization(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(f'/api/study/courses/{self.course.id}/report.csv', {'language': 'en'}).status_code, 403)
        self.assertEqual(self.client.get('/api/analytics/export/', {'kind': 'sessions', 'language': 'kk'}).status_code, 403)

    def test_catalogs_match_and_preserve_interpolation_slots(self):
        root = Path(__file__).resolve().parents[2]
        client = json.loads((root / 'frontend/src/i18n/messages.json').read_text(encoding='utf-8'))
        server = json.loads((root / 'backend/locales/messages.json').read_text(encoding='utf-8'))
        self.assertEqual(client, server)
        self.assertGreater(len(client), 1500)
        for source, variants in client.items():
            self.assertEqual(len(variants), 2, source)
            slots = sorted(re.findall(r'\{\d+\}', source))
            for translated in variants:
                self.assertTrue(translated.strip(), source)
                self.assertEqual(sorted(re.findall(r'\{\d+\}', translated)), slots, source)

    def test_unknown_or_authored_text_is_not_translated(self):
        self.assertEqual(translate('Авторский текст и ответ ученика', 'en'), 'Авторский текст и ответ ученика')
        self.assertEqual(translate('Проверка работ', 'en'), 'Review work')
        from django.test import RequestFactory
        request = RequestFactory().get('/', {'language': 'unknown'})
        request.user = self.teacher
        self.assertEqual(request_language(request), 'kk')
