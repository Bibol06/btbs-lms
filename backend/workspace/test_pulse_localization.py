from django.contrib.auth import get_user_model
from django.test import TestCase

from content_localization import attach_content_translations
from courses.models import Course, CourseRun, Enrollment
from learning.models import Lesson, Module
from .models import LessonPulse


class LessonPulseLocalizationTests(TestCase):
    source = 'Покажите пример с отрицательными числами.'

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.teacher = User.objects.create_user(username='pulse_teacher', role='teacher')
        cls.tutor = User.objects.create_user(username='pulse_tutor', role='teacher')
        cls.admin = User.objects.create_user(username='pulse_admin', role='admin')
        cls.student = User.objects.create_user(username='pulse_student', first_name='Думан', last_name='Нурланов')
        cls.peer = User.objects.create_user(username='pulse_peer')
        cls.course = Course.objects.create(teacher=cls.teacher, title='Course', is_published=True, content_translation='localized')
        cls.group_a = CourseRun.objects.create(course=cls.course, kind='cohort', title='A')
        cls.group_b = CourseRun.objects.create(course=cls.course, kind='cohort', title='B')
        cls.group_a.teachers.add(cls.tutor)
        cls.enrollment = Enrollment.objects.create(course=cls.course, run=cls.group_a, student=cls.student)
        cls.other_enrollment = Enrollment.objects.create(course=cls.course, run=cls.group_b, student=cls.peer)
        module = Module.objects.create(course=cls.course, title='Module', is_published=True)
        cls.lesson = Lesson.objects.create(course=cls.course, module=module, title='Lesson', is_published=True)
        cls.pulse = LessonPulse.objects.create(lesson=cls.lesson, enrollment=cls.enrollment, choice='example', note=cls.source)

    def endpoint(self, cohort=None):
        return f'/api/workspace/lessons/{self.lesson.id}/pulse/?run_id={(cohort or self.group_a).id}'

    def test_teacher_admin_and_group_tutor_receive_prepared_note_variants(self):
        for actor in [self.teacher, self.admin, self.tutor]:
            with self.subTest(role=actor.username):
                self.client.force_login(actor)
                response = self.client.get(self.endpoint())
                self.assertEqual(response.status_code, 200)
                note = response.json()['notes'][0]
                self.assertEqual(note['note'], self.source)
                self.assertEqual(note['_text']['note'], {
                    'ru': self.source,
                    'kk': 'Теріс сандармен мысал көрсетіңіз.',
                    'en': 'Show an example with negative numbers.',
                })
                self.assertEqual(note['_content_kind'], 'lesson_feedback')
                self.assertNotIn('student', note['_text'])
        self.pulse.refresh_from_db()
        self.assertEqual(self.pulse.note, self.source)

    def test_student_editor_keeps_original_text_and_does_not_get_other_notes(self):
        self.client.force_login(self.student)
        data = self.client.get(self.endpoint()).json()
        self.assertFalse(data['can_manage'])
        self.assertEqual(data['note'], self.source)
        self.assertNotIn('_text', data)
        self.assertNotIn('notes', data)
        response = self.client.put(self.endpoint(), {'choice': 'example', 'note': self.source}, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['note'], self.source)
        self.pulse.refresh_from_db()
        self.assertEqual(self.pulse.note, self.source)

    def test_original_course_policy_preserves_known_russian_and_english_notes(self):
        self.course.content_language = 'en'
        self.course.content_translation = 'original'
        self.course.save(update_fields=['content_language', 'content_translation'])
        self.client.force_login(self.teacher)
        note = self.client.get(self.endpoint()).json()['notes'][0]
        self.assertEqual(note['note'], self.source)
        self.assertNotIn('_text', note)
        self.pulse.note = 'Please explain sum([-1, 2]) using Python.'
        self.pulse.save(update_fields=['note'])
        note = self.client.get(self.endpoint()).json()['notes'][0]
        self.assertEqual(note['note'], self.pulse.note)
        self.assertNotIn('_text', note)

    def test_unknown_note_is_never_partially_translated(self):
        self.pulse.note = 'Новый вопрос: объясните sum([-1, 2]) и Python API.'
        self.pulse.save(update_fields=['note'])
        self.client.force_login(self.teacher)
        note = self.client.get(self.endpoint()).json()['notes'][0]
        self.assertEqual(note['note'], self.pulse.note)
        self.assertNotIn('_text', note)

    def test_translations_do_not_reveal_notes_from_another_group(self):
        LessonPulse.objects.create(lesson=self.lesson, enrollment=self.other_enrollment, choice='hard', note='Можете помочь?')
        self.client.force_login(self.tutor)
        response = self.client.get(self.endpoint())
        self.assertEqual(response.json()['total'], 1)
        self.assertNotContains(response, 'Can you help?')
        self.assertEqual(self.client.get(self.endpoint(self.group_b)).status_code, 403)
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(self.endpoint(self.group_b)).status_code, 403)

    def test_generic_private_notes_remain_original_even_when_text_has_a_variant(self):
        payload = {'note': self.source, 'notes': [{'note': self.source}],
            'messages': [{'_content_kind': 'lesson_feedback', 'note': self.source}]}
        attach_content_translations(payload, course_id=self.course.id)
        self.assertNotIn('_text', payload)
        self.assertNotIn('_text', payload['notes'][0])
        self.assertNotIn('_text', payload['messages'][0])
