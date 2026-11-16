import json
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from assessment.models import Assignment, GradeReview, Submission
from communication.models import Announcement, Comment, Conversation, Discussion, Message, Participant
from courses.models import Course, Enrollment, default_run
from learning.models import Lesson


class IdentityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.teacher = User.objects.create_user(username='identity_teacher', first_name='Алия', last_name='Сейтенова', role='teacher')
        cls.student = User.objects.create_user(username='identity_student', first_name='Думан', last_name='Нурланов')
        # A course teacher can have the platform's default student role.
        cls.tutor = User.objects.create_user(username='identity_tutor', first_name='Ерлан', last_name='Омаров')
        cls.admin = User.objects.create_superuser(username='identity_admin', first_name='Бибол', last_name='Жайлыбаев')
        cls.course = Course.objects.create(title='Names', teacher=cls.teacher, is_published=True)
        cls.cohort = default_run(cls.course)
        cls.cohort.teachers.add(cls.tutor)
        cls.enrollment = Enrollment.objects.create(course=cls.course, run=cls.cohort, student=cls.student)
        cls.assignment = Assignment.objects.create(course=cls.course, title='Work', is_published=True)
        cls.submission = Submission.objects.create(assignment=cls.assignment, enrollment=cls.enrollment, student=cls.student, attempt_no=1, reviewer=cls.tutor)
        GradeReview.objects.create(submission=cls.submission, reviewer=cls.admin, action='returned', feedback='Fix')
        cls.lesson = Lesson.objects.create(course=cls.course, title='Lesson', is_published=True)
        discussion = Discussion.objects.create(lesson=cls.lesson, run=cls.cohort)
        Comment.objects.create(discussion=discussion, author=cls.student, body='Question')
        Comment.objects.create(discussion=discussion, author=cls.tutor, body='Answer')
        cls.conversation = Conversation.objects.create(enrollment=cls.enrollment)
        Participant.objects.create(conversation=cls.conversation, user=cls.teacher)
        Message.objects.create(conversation=cls.conversation, author=cls.student, body='Hi')
        Message.objects.create(conversation=cls.conversation, author=cls.tutor, body='Hello')
        Announcement.objects.create(course=cls.course, run=cls.cohort, author=cls.admin, title='News', body='Welcome', is_published=True)

    def test_names_and_separate_roles_across_learning_and_communication(self):
        self.client.force_login(self.teacher)
        suffix = f'?run_id={self.cohort.id}'
        study = self.client.get(f'/api/study/courses/{self.course.id}/{suffix}').json()
        work = study['assignments'][0]['submissions'][0]
        self.assertEqual((work['student'], work['student_role_label']), ('Нурланов Думан', 'Студент'))
        self.assertEqual((work['reviewer'], work['reviewer_role_label']), ('Омаров Ерлан', 'Преподаватель'))
        self.assertEqual((work['reviews'][0]['reviewer'], work['reviews'][0]['reviewer_role_label']), ('Жайлыбаев Бибол', 'Владелец платформы'))
        queue = self.client.get('/api/study/review-queue/').json()['works'][0]
        self.assertEqual(queue['student'], work['student'])
        comments = self.client.get(f'/api/communication/lessons/{self.lesson.id}/discussion/{suffix}').json()['comments']
        self.assertEqual({(c['author'], c['author_role_label']) for c in comments}, {('Нурланов Думан', 'Студент'), ('Омаров Ерлан', 'Преподаватель')})
        messages = self.client.get(f'/api/communication/conversations/{self.conversation.id}/messages/').json()['messages']
        self.assertEqual(messages[1]['author_role_label'], 'Преподаватель')
        news = self.client.get(f'/api/communication/courses/{self.course.id}/announcements/{suffix}').json()['announcements'][0]
        self.assertEqual((news['author'], news['author_role_label']), ('Жайлыбаев Бибол', 'Владелец платформы'))

    def test_admin_and_profile_keep_name_role_and_login_separate(self):
        self.client.force_login(self.admin)
        me = self.client.get('/api/auth/me/').json()
        self.assertEqual((me['display_name'], me['role_label'], me['username']), ('Жайлыбаев Бибол', 'Владелец платформы', 'identity_admin'))
        profile = self.client.get('/api/auth/profile/').json()
        self.assertEqual(profile['display_name'], me['display_name'])
        users = self.client.get('/api/auth/users/').json()['users']
        self.assertEqual(next(u for u in users if u['id'] == self.admin.id)['role_label'], 'Владелец платформы')
        self.client.force_login(self.tutor)
        self.assertEqual(self.client.get('/api/auth/me/').json()['role_label'], 'Преподаватель')
        self.tutor.refresh_from_db()
        self.assertEqual(self.tutor.role, 'student')

    def test_registration_saves_names_but_ignores_forged_roles(self):
        data = {'username': 'new_person', 'email': 'new@example.test', 'password': 'R7-strong-2026!secret',
                'first_name': ' Аружан ', 'last_name': ' Садыкова ', 'role': 'admin', 'role_label': 'Владелец платформы'}
        response = self.client.post('/api/auth/register/', data=json.dumps(data), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual((response.json()['display_name'], response.json()['role_label']), ('Садыкова Аружан', 'Студент'))
        self.assertEqual(get_user_model().objects.get(username='new_person').role, 'student')
        for invalid in ([], None, 'a' * 151):
            data['first_name'] = invalid
            self.assertEqual(self.client.post('/api/auth/register/', data=json.dumps(data), content_type='application/json').status_code, 400)

    def test_example_name_update_preserves_login_password_role_and_existing_names(self):
        User = get_user_model()
        empty = User.objects.create_user(username='demo_peer', password='Original-Pass-2026')
        named = User.objects.create_user(username='demo_teacher', first_name='Existing', role='teacher')
        old_password = empty.password
        for _ in range(2):
            call_command('set_example_names', stdout=StringIO())
        empty.refresh_from_db(); named.refresh_from_db()
        self.assertEqual((empty.first_name, empty.last_name), ('Аружан', 'Садыкова'))
        self.assertEqual((empty.username, empty.password, empty.role), ('demo_peer', old_password, 'student'))
        self.assertEqual(named.first_name, 'Existing')
