from django.contrib.auth import get_user_model
from django.test import TestCase

from content_localization import attach_content_translations
from courses.models import Course, Enrollment, default_run
from learning.models import Lesson, Module
from .models import Comment, Discussion


class DiscussionLocalizationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.teacher = User.objects.create_user(username='discussion_teacher', role='teacher')
        cls.admin = User.objects.create_user(username='discussion_admin', role='admin')
        cls.student = User.objects.create_user(username='discussion_student')
        cls.peer = User.objects.create_user(username='discussion_peer')
        cls.outsider = User.objects.create_user(username='discussion_outsider', role='teacher')
        cls.course = Course.objects.create(teacher=cls.teacher, title='Основы Python', is_published=True, content_translation='localized')
        cls.cohort = default_run(cls.course)
        for user in [cls.student, cls.peer]:
            Enrollment.objects.create(course=cls.course, run=cls.cohort, student=user)
        module = Module.objects.create(course=cls.course, title='Module', is_published=True)
        cls.lesson = Lesson.objects.create(course=cls.course, module=module, title='Lesson', is_published=True)
        cls.discussion = Discussion.objects.create(lesson=cls.lesson, run=cls.cohort)
        cls.root = Comment.objects.create(discussion=cls.discussion, author=cls.student,
            body='Вопрос группы A: можно ли решать эту задачу через sum?')
        cls.reply = Comment.objects.create(discussion=cls.discussion, author=cls.peer, parent=cls.root, body='Можете помочь?')

    def surfaces(self, actor):
        self.client.force_login(actor)
        home = self.client.get('/api/workspace/home/')
        queue = self.client.get('/api/workspace/questions/?state=all')
        discussion = self.client.get(f'/api/communication/lessons/{self.lesson.id}/discussion/?run_id={self.cohort.id}')
        for response in [home, queue, discussion]:
            self.assertEqual(response.status_code, 200, response.content)
        discussion = discussion.json()
        return [home.json()['questions'][0], queue.json()['questions'][0],
                discussion['threads'][0]['root'], discussion['comments'][0]], discussion

    def test_home_queue_thread_and_legacy_comment_use_identical_variants(self):
        for actor in [self.teacher, self.admin]:
            with self.subTest(role=actor.role):
                rows, discussion = self.surfaces(actor)
                for row in rows:
                    self.assertEqual(row['id'], self.root.id)
                    self.assertEqual(row['body'], self.root.body)
                    self.assertEqual(row['_content_kind'], 'discussion_comment')
                    self.assertEqual(row['_text']['body'], rows[0]['_text']['body'])
                    for language in ['ru', 'kk', 'en']:
                        self.assertIn('sum', row['_text']['body'][language])
                # Both the question-bank-style list and nested replies share the contract.
                reply = discussion['threads'][0]['replies'][0]
                self.assertEqual(reply['_text']['body']['en'], 'Can you help?')
                self.assertEqual(reply['_text']['body'], discussion['comments'][1]['_text']['body'])
                self.assertEqual(rows[1]['_text']['course']['en'], 'Python fundamentals')
        self.root.refresh_from_db()
        self.assertEqual(self.root.body, 'Вопрос группы A: можно ли решать эту задачу через sum?')

    def test_student_and_teacher_read_the_same_comment_text(self):
        rows, _ = self.surfaces(self.teacher)
        self.client.force_login(self.student)
        response = self.client.get(f'/api/communication/lessons/{self.lesson.id}/discussion/?run_id={self.cohort.id}').json()
        self.assertEqual(response['threads'][0]['root']['_text']['body'], rows[0]['_text']['body'])

    def test_english_course_original_policy_applies_on_every_surface(self):
        self.course.content_language = 'en'
        self.course.content_translation = 'original'
        self.course.save(update_fields=['content_language', 'content_translation'])
        rows, discussion = self.surfaces(self.teacher)
        for row in [*rows, *discussion['threads'][0]['replies'], *discussion['comments']]:
            self.assertNotIn('body', row.get('_text', {}))
        self.assertEqual(rows[0]['body'], self.root.body)
        self.assertEqual(discussion['threads'][0]['replies'][0]['body'], self.reply.body)

    def test_unprepared_comment_falls_back_to_original_everywhere(self):
        self.root.body = 'Новый вопрос: why does print("Hello") return None?'
        self.root.save(update_fields=['body'])
        rows, _ = self.surfaces(self.teacher)
        for row in rows:
            self.assertEqual(row['body'], self.root.body)
            self.assertNotIn('body', row.get('_text', {}))

    def test_redaction_never_exposes_original_or_translated_hidden_body(self):
        self.reply.is_hidden = True
        self.reply.save(update_fields=['is_hidden'])
        self.client.force_login(self.student)
        response = self.client.get(f'/api/communication/lessons/{self.lesson.id}/discussion/?run_id={self.cohort.id}').json()
        for reply in [response['threads'][0]['replies'][0], response['comments'][1]]:
            self.assertTrue(reply['is_redacted'])
            self.assertEqual(reply['body'], 'Комментарий скрыт модератором')
            self.assertNotIn('body', reply.get('_text', {}))
        _, staff = self.surfaces(self.teacher)
        self.assertFalse(staff['comments'][1]['is_redacted'])
        self.assertEqual(staff['comments'][1]['body'], self.reply.body)

    def test_hidden_questions_and_other_groups_remain_inaccessible(self):
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get('/api/workspace/questions/?state=all').json()['questions'], [])
        self.assertEqual(self.client.get(f'/api/communication/lessons/{self.lesson.id}/discussion/?run_id={self.cohort.id}').status_code, 403)
        self.root.is_hidden = True
        self.root.save(update_fields=['is_hidden'])
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get('/api/workspace/questions/?state=all').json()['questions'], [])

    def test_comment_marker_cannot_opt_private_messages_into_translation(self):
        private = {'messages': [{'body': 'Private thread', 'comments': [
            {'_content_kind': 'discussion_comment', 'body': 'Можете помочь?'}]}]}
        attach_content_translations(private, course_id=self.course.id)
        self.assertNotIn('_text', private['messages'][0]['comments'][0])
