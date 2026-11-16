import json
from copy import deepcopy
from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth import get_user_model
from courses.models import Course
from content_localization import attach_content_translations, content_text, content_catalog, safe_variants


class ContentLocalizationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.teacher = get_user_model().objects.create_user(username='content_owner', role='teacher')
        cls.other = get_user_model().objects.create_user(username='content_other', role='teacher')
        cls.public = Course.objects.create(teacher=cls.teacher, title='Основы Python', description='Изучение языка Python с нуля', is_published=True, content_translation='localized')
        cls.private = Course.objects.create(teacher=cls.teacher, title='Демо: копия курса BTBS', content_translation='localized')
        cls.english = Course.objects.create(teacher=cls.teacher, title='English: Python API', content_language='en', content_translation='original')

    def test_public_response_exposes_variants_only_on_visible_fields(self):
        response = self.client.get('/api/courses/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        row = next(row for row in data['courses'] if row['id'] == self.public.id)
        self.assertEqual(row['title'], 'Основы Python')
        self.assertEqual(row['_text']['title']['en'], 'Python fundamentals')
        self.assertNotIn(self.private.title, json.dumps(data, ensure_ascii=False))
        self.assertNotIn('Можете помочь?', json.dumps(data, ensure_ascii=False))
        self.assertNotIn('_content_translations', data)
        self.public.refresh_from_db()
        self.assertEqual(self.public.title, 'Основы Python')

    def test_private_course_permissions_are_unchanged(self):
        self.client.force_login(self.teacher)
        owner = self.client.get('/api/courses/teacher/').json()
        self.assertTrue(any(row['id'] == self.private.id and '_text' in row for row in owner['courses']))
        self.client.force_login(self.other)
        other = self.client.get('/api/courses/teacher/').json()
        self.assertNotIn(self.private.title, json.dumps(other, ensure_ascii=False))
        self.assertEqual(self.client.get(f'/api/courses/teacher/{self.private.id}/').status_code, 403)

    def test_english_course_never_translates_lessons_or_questions(self):
        data = {'course': self.english.title, 'lessons': [{'title': 'Question', 'content': 'Use input() and print(). Keep API and Python.', 'questions': [{'body': 'Сколько будет 2 + 2?', 'options': ['Ответы пропадут', 'Система проверит сохранённые ответы'], 'correct_index': 1}]}]}
        original = deepcopy(data)
        attach_content_translations(data, course_id=self.english.id)
        self.assertEqual(data['_course_policy'], {'language': 'en', 'mode': 'original'})
        self.assertEqual(data['lessons'], original['lessons'])
        self.assertNotIn('_text', data['lessons'][0]['questions'][0])

    def test_step_heading_and_curriculum_share_the_course_language_policy(self):
        from learning.models import Module, Lesson, Step
        self.client.force_login(self.teacher)
        for course in [self.public, self.english]:
            with self.subTest(mode=course.content_translation):
                module = Module.objects.create(course=course, title='Module', is_published=True)
                lesson = Lesson.objects.create(course=course, module=module, title='Lesson', is_published=True)
                step = Step.objects.create(lesson=lesson, title='Решите задачу на Python', content='print("Hello")', is_published=True)
                detail = self.client.get(f'/api/learning/steps/{step.id}/')
                structure = self.client.get(f'/api/learning/courses/{course.id}/structure/')
                self.assertEqual(detail.status_code, 200)
                self.assertEqual(structure.status_code, 200)
                heading = detail.json()['step']
                outline = structure.json()['modules'][0]['lessons'][0]['steps'][0]
                self.assertEqual(heading.get('_text', {}).get('title'), outline.get('_text', {}).get('title'))
                self.assertEqual(heading['content'], 'print("Hello")')
                if course.content_translation == 'localized':
                    self.assertEqual(heading['_text']['title']['en'], 'Solve a Python problem')
                else:
                    self.assertNotIn('_text', heading)

    def test_same_text_in_different_courses_does_not_share_translation(self):
        data = {'courses': [{'id': self.public.id, 'title': 'Основы Python'}, {'id': self.english.id, 'title': 'Основы Python'}]}
        attach_content_translations(data)
        self.assertIn('_text', data['courses'][0])
        self.assertNotIn('_text', data['courses'][1])

    def test_names_code_answers_feedback_and_conversations_stay_original(self):
        data = {key: 'Можете помочь?' for key in ['display_name', 'username', 'student', 'author', 'teacher', 'reviewer', 'text_answer', 'feedback', 'comment', 'note', 'code', 'starter_code', 'stdin', 'expected', 'file_name', 'file_url']}
        data['messages'] = [{'body': 'Можете помочь?'}]
        data['questions'] = [{'student': 'Нурланов Думан', 'body': 'Вопрос группы A: можно ли решать эту задачу через sum?'}]
        original = deepcopy(data)
        attach_content_translations(data, course_id=self.public.id)
        for key in original:
            self.assertEqual(data[key], original[key])
        self.assertNotIn('_text', data)

    def test_prepared_learning_variants_keep_indices_and_original_values(self):
        data = {'questions': [{'body': 'Что случится после окончания таймера?', 'options': ['Ответы пропадут', 'Система проверит сохранённые ответы'], 'correct_index': 1}]}
        attach_content_translations(data, course_id=self.public.id)
        q = data['questions'][0]
        self.assertEqual(q['_text']['options'][0]['en'], 'Answers will be lost')
        self.assertEqual(q['correct_index'], 1)
        self.assertEqual(q['body'], 'Что случится после окончания таймера?')
        self.assertEqual(q['options'][1], 'Система проверит сохранённые ответы')

    def test_bad_variants_cannot_translate_technical_terms_or_inline_code(self):
        source = 'BTBS Python API sum print("Hello")'
        with patch('content_localization.content_catalog', return_value={source: {'en': 'BTBS Python API sum print("Hello") explained', 'kk': 'BTBS Питон API sum print("Hello")', 'ru': 'BTBS Python API sum print("Привет")'}}):
            self.assertEqual(set(safe_variants(source)), {'en'})

    def test_export_requires_explicit_course_policy(self):
        self.assertEqual(content_text('Пример задержки проверки', 'en', self.public), 'Overdue review example')
        self.assertEqual(content_text('Пример задержки проверки', 'en', self.english), 'Пример задержки проверки')
        self.assertEqual(content_text('Question', 'ru', self.english), 'Question')
        self.assertEqual(content_text('Question', 'kk'), 'Question')

    def test_course_language_settings_are_validated_and_owned(self):
        self.client.force_login(self.teacher)
        for values in [{'content_language': 'invalid'}, {'content_language': ['en']}, {'content_translation': 'automatic'}, {'content_translation': True}]:
            self.assertEqual(self.client.patch(f'/api/courses/teacher/{self.public.id}/', json.dumps(values), content_type='application/json').status_code, 400)
        self.assertEqual(self.client.patch(f'/api/courses/teacher/{self.public.id}/', json.dumps({'content_language': 'en', 'content_translation': 'original'}), content_type='application/json').status_code, 200)
        self.public.refresh_from_db()
        self.assertEqual(self.public.content_language, 'en')
        self.assertEqual(self.public.teacher_id, self.teacher.id)

    def test_course_copy_preserves_language_and_translation_mode(self):
        self.client.force_login(self.teacher)
        response = self.client.post(f'/api/workspace/courses/{self.english.id}/clone/', json.dumps({'title': 'English copy'}), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        copy = Course.objects.get(title='English copy')
        self.assertEqual((copy.content_language, copy.content_translation), ('en', 'original'))

    def test_default_course_preserves_original_and_catalog_has_three_variants(self):
        self.assertEqual(self.english.content_translation, 'original')
        self.assertGreaterEqual(len(content_catalog()), 121)
        for variants in content_catalog().values():
            self.assertEqual(set(variants), {'ru', 'kk', 'en'})

    def test_no_public_dictionary_endpoint(self):
        self.assertEqual(self.client.get('/api/locales/content.json').status_code, 404)
