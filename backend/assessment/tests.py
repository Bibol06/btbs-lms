import json
import tempfile
from datetime import timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from courses.models import Course, Enrollment
from learning.models import Lesson, LessonMaterial
from .models import Assignment, Submission, Quiz, Question, QuizAttempt, LessonProgress


class LearningCycleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.teacher = User.objects.create_user(username='teacher', role='teacher', password='Teacher-Private-2026')
        cls.other_teacher = User.objects.create_user(username='other_teacher', role='teacher')
        cls.student = User.objects.create_user(username='student', role='student')
        cls.other_student = User.objects.create_user(username='other_student', role='student')
        cls.admin = User.objects.create_user(username='admin', role='admin')
        cls.course = Course.objects.create(title='Course', teacher=cls.teacher, is_published=True)
        cls.lesson = Lesson.objects.create(course=cls.course, title='Lesson', content='Private lesson', is_published=True)
        Enrollment.objects.create(course=cls.course, student=cls.student)
        Enrollment.objects.create(course=cls.course, student=cls.other_student)
        cls.assignment = Assignment.objects.create(course=cls.course, title='Homework', is_published=True, max_attempts=2)
        cls.quiz = Quiz.objects.create(course=cls.course, title='Quiz', is_published=True, max_attempts=2, time_limit_sec=60)
        cls.question = Question.objects.create(quiz=cls.quiz, body='2+2?', options=['3', '4'], correct_index=1, position=1)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.temp.name)
        self.settings_override.enable()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.settings_override.disable)
        self.client.force_login(self.student)

    def send(self, url, data=None, method='post'):
        return getattr(self.client, method)(url, data=json.dumps(data if data is not None else {}), content_type='application/json')

    def start(self):
        return self.send(f'/api/study/quizzes/{self.quiz.id}/start/')

    def test_course_and_lesson_can_be_published_and_edited(self):
        self.client.force_login(self.teacher)
        r = self.send(f'/api/courses/teacher/{self.course.id}/', {'is_published': False}, 'patch')
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()['course']['is_published'])
        r = self.send(f'/api/learning/teacher/lessons/{self.lesson.id}/', {'title': 'Updated', 'is_published': False}, 'patch')
        self.assertEqual(r.status_code, 200)
        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.title, 'Updated')
        self.assertFalse(self.lesson.is_published)

    def test_other_teacher_and_student_cannot_edit_course_or_lesson(self):
        for user in [self.student, self.other_teacher]:
            self.client.force_login(user)
            self.assertEqual(self.send(f'/api/courses/teacher/{self.course.id}/', {'title': 'Hacked'}, 'patch').status_code, 403)
            self.assertEqual(self.send(f'/api/learning/teacher/lessons/{self.lesson.id}/', {}, 'delete').status_code, 403)

    def test_admin_can_manage_learning(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.send(f'/api/learning/teacher/courses/{self.course.id}/lessons/', {'title': 'Admin lesson'}).status_code, 201)
        self.assertEqual(self.client.get('/api/courses/teacher/').status_code, 200)

    def test_lesson_creation_uses_next_position(self):
        self.client.force_login(self.teacher)
        r = self.send(f'/api/learning/teacher/courses/{self.course.id}/lessons/', {'title': 'Second', 'is_published': True})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()['lesson']['position'], 2)
        self.assertTrue(r.json()['lesson']['is_published'])

    def test_invalid_lesson_url_and_publication_rejected(self):
        self.client.force_login(self.teacher)
        url = f'/api/learning/teacher/lessons/{self.lesson.id}/'
        self.assertEqual(self.send(url, {'video_url': 'javascript:alert(1)'}, 'patch').status_code, 400)
        self.assertEqual(self.send(url, {'is_published': 'false'}, 'patch').status_code, 400)

    def test_material_deletion_checks_owner_and_removes_file(self):
        m = LessonMaterial.objects.create(lesson=self.lesson, title='PDF', file=SimpleUploadedFile('test.pdf', b'%PDF-1.4 test'))
        path = Path(m.file.path)
        self.assertEqual(self.send(f'/api/learning/teacher/materials/{m.id}/', method='delete').status_code, 403)
        self.client.force_login(self.teacher)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.send(f'/api/learning/teacher/materials/{m.id}/', method='delete').status_code, 200)
        self.assertFalse(path.exists())
        self.assertFalse(LessonMaterial.objects.filter(pk=m.id).exists())

    def test_deleting_lesson_removes_files_and_progress(self):
        m = LessonMaterial.objects.create(lesson=self.lesson, title='PDF', file=SimpleUploadedFile('test.pdf', b'%PDF-1.4 test'))
        path = Path(m.file.path)
        LessonProgress.objects.create(lesson=self.lesson, student=self.student)
        self.client.force_login(self.teacher)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.send(f'/api/learning/teacher/lessons/{self.lesson.id}/', method='delete').status_code, 200)
        self.assertFalse(path.exists())
        self.assertEqual(LessonProgress.objects.count(), 0)

    def test_upload_signature_and_owner(self):
        url = f'/api/learning/teacher/lessons/{self.lesson.id}/materials/'
        self.assertEqual(self.client.post(url, {'file': SimpleUploadedFile('x.pdf', b'%PDF-1.4 x')}).status_code, 403)
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.post(url, {'file': SimpleUploadedFile('x.pdf', b'fake')}).status_code, 400)
        self.assertEqual(self.client.post(url, {'file': SimpleUploadedFile('x.pdf', b'%PDF-1.4 x')}).status_code, 201)

    def test_submit_grade_and_personal_result(self):
        url = f'/api/study/assignments/{self.assignment.id}/submit/'
        r = self.client.post(url, {'text_answer': 'My solution'})
        self.assertEqual(r.status_code, 201)
        sid = r.json()['submission']['id']
        self.client.force_login(self.teacher)
        r = self.send(f'/api/study/submissions/{sid}/grade/', {'score': 85, 'feedback': 'Good work'}, 'put')
        self.assertEqual(r.status_code, 200)
        self.client.force_login(self.student)
        a = self.client.get(f'/api/study/courses/{self.course.id}/').json()['assignments'][0]
        self.assertEqual(a['submissions'][0]['score'], 85)
        self.assertEqual(a['submissions'][0]['feedback'], 'Good work')

    def test_deadline_and_max_attempts(self):
        url = f'/api/study/assignments/{self.assignment.id}/submit/'
        for _ in range(2):
            self.assertEqual(self.client.post(url, {'text_answer': 'Solution'}).status_code, 201)
        self.assertEqual(self.client.post(url, {'text_answer': 'Third'}).status_code, 400)
        self.assignment.due_at = timezone.now() - timedelta(seconds=1)
        self.assignment.save()
        self.client.force_login(self.other_student)
        self.assertEqual(self.client.post(url, {'text_answer': 'Late'}).status_code, 400)

    def test_submission_validation_and_draft(self):
        url = f'/api/study/assignments/{self.assignment.id}/submit/'
        self.assertEqual(self.client.post(url, {}).status_code, 400)
        self.assertEqual(self.client.post(url, {'file': SimpleUploadedFile('bad.pdf', b'bad')}).status_code, 400)
        self.assignment.is_published = False
        self.assignment.save()
        self.assertEqual(self.client.post(url, {'text_answer': 'Answer'}).status_code, 404)

    def test_submission_file_is_private(self):
        r = self.client.post(f'/api/study/assignments/{self.assignment.id}/submit/', {'file': SimpleUploadedFile('answer.pdf', b'%PDF-1.4 example')})
        sid = r.json()['submission']['id']
        url = f'/api/study/submissions/{sid}/file/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(b''.join(response.streaming_content).startswith(b'%PDF-'))

        self.client.force_login(self.other_student)
        self.assertEqual(self.client.get(url).status_code, 403)
        own = self.client.get(f'/api/study/courses/{self.course.id}/').json()['assignments'][0]
        self.assertEqual(own['submissions'], [])
        self.client.force_login(self.teacher)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(b''.join(response.streaming_content).startswith(b'%PDF-'))

    def test_deleting_student_cleans_submission_files_after_commit(self):
        s = Submission.objects.create(assignment=self.assignment, student=self.student, attempt_no=1,
                                      file=SimpleUploadedFile('answer.pdf', b'%PDF-1.4 example'))
        path = Path(s.file.path)
        with self.captureOnCommitCallbacks(execute=True):
            self.student.delete()
            self.assertTrue(path.exists())
        self.assertFalse(path.exists())

    def test_grade_range_and_permission(self):
        s = Submission.objects.create(assignment=self.assignment, student=self.student, text_answer='A', attempt_no=1)
        url = f'/api/study/submissions/{s.id}/grade/'
        self.assertEqual(self.send(url, {'score': 100}, 'put').status_code, 403)
        self.client.force_login(self.other_teacher)
        self.assertEqual(self.send(url, {'score': 100}, 'put').status_code, 403)
        self.client.force_login(self.teacher)
        for score in [-1, 101, True, '10']:
            self.assertEqual(self.send(url, {'score': score}, 'put').status_code, 400)
        self.assertEqual(self.send(url, {'score': 0}, 'put').status_code, 200)

    def test_assignment_history_cannot_be_destroyed_or_rescaled(self):
        Submission.objects.create(assignment=self.assignment, student=self.student, attempt_no=1)
        self.client.force_login(self.teacher)
        url = f'/api/study/assignments/{self.assignment.id}/'
        self.assertEqual(self.send(url, method='delete').status_code, 400)
        self.assertEqual(self.send(url, {'max_score': 200}, 'patch').status_code, 400)
        self.assertEqual(self.send(url, {'is_published': False}, 'patch').status_code, 200)

    def test_quiz_creation_and_validation(self):
        self.client.force_login(self.teacher)
        url = f'/api/study/courses/{self.course.id}/quizzes/'
        data = {'title': 'New quiz', 'questions': [{'body': 'Question', 'options': ['A', 'B'], 'correct_index': 0}]}
        self.assertEqual(self.send(url, data).status_code, 201)
        data['questions'][0]['correct_index'] = 2
        self.assertEqual(self.send(url, data).status_code, 400)

    def test_correct_answers_not_exposed_and_attempt_resumes(self):
        summary = self.client.get(f'/api/study/courses/{self.course.id}/').json()
        self.assertNotIn('questions', summary['quizzes'][0])
        r = self.start()
        self.assertEqual(r.status_code, 200)
        self.assertNotIn('correct_index', r.json()['questions'][0])
        self.assertEqual(self.start().json()['attempt']['id'], r.json()['attempt']['id'])
        self.assertEqual(QuizAttempt.objects.count(), 1)

    def test_autosave_finish_and_idempotency(self):
        attempt = self.start().json()['attempt']
        url = f'/api/study/attempts/{attempt["id"]}/'
        data = {'answers': {str(self.question.id): 1}}
        self.assertEqual(self.send(url, data, 'patch').status_code, 200)
        self.assertEqual(self.start().json()['answers'], data['answers'])
        self.assertEqual(self.send(url, data).json()['attempt']['score'], 1)
        self.assertEqual(self.send(url, {'answers': {}}).json()['attempt']['score'], 1)
        self.assertEqual(QuizAttempt.objects.get().score, 1)

    def test_quiz_attempt_ownership_and_wrong_question(self):
        a = self.start().json()['attempt']
        url = f'/api/study/attempts/{a["id"]}/'
        self.assertEqual(self.send(url, {'answers': {'99999': 1}}).status_code, 400)
        self.assertEqual(self.send(url, {'answers': {str(self.question.id): True}}).status_code, 400)
        self.client.force_login(self.other_student)
        self.assertEqual(self.send(url, {'answers': {}}).status_code, 404)

    def test_late_answers_cannot_replace_saved_answers_after_timer(self):
        a = self.start().json()['attempt']
        QuizAttempt.objects.filter(pk=a['id']).update(deadline_at=timezone.now() - timedelta(seconds=1))
        result = self.send(f'/api/study/attempts/{a["id"]}/', {'answers': {str(self.question.id): 1}}).json()['attempt']
        self.assertEqual(result['status'], 'finished')
        self.assertTrue(result['auto_submitted'])
        self.assertEqual(result['score'], 0)

    def test_attempt_limit_and_quiz_window(self):
        for _ in range(2):
            a = self.start().json()['attempt']
            self.send(f'/api/study/attempts/{a["id"]}/', {'answers': {}})
        self.assertEqual(self.start().status_code, 400)
        self.client.force_login(self.other_student)
        self.quiz.opens_at = timezone.now() + timedelta(hours=1)
        self.quiz.save()
        self.assertEqual(self.start().status_code, 400)
        self.quiz.opens_at = None
        self.quiz.closes_at = timezone.now() - timedelta(seconds=1)
        self.quiz.save()
        self.assertEqual(self.start().status_code, 400)

    def test_quiz_history_is_immutable_but_can_unpublish(self):
        self.start()
        self.client.force_login(self.teacher)
        url = f'/api/study/quizzes/{self.quiz.id}/'
        self.assertEqual(self.send(url, {'title': 'Changed'}, 'patch').status_code, 400)
        self.assertEqual(self.send(url, method='delete').status_code, 400)
        self.assertEqual(self.send(url, {'is_published': False}, 'patch').status_code, 200)

    def test_progress_idempotent_and_unpublished_excluded(self):
        url = f'/api/study/lessons/{self.lesson.id}/complete/'
        self.assertEqual(self.send(url).json()['progress']['percent'], 100)
        self.send(url)
        self.assertEqual(LessonProgress.objects.count(), 1)
        self.assertEqual(self.send(url, {'completed': False}).json()['progress']['percent'], 0)
        self.lesson.is_published = False
        self.lesson.save()
        self.assertEqual(self.send(url).status_code, 404)

    def test_unenrolled_and_unpublished_course_block_study(self):
        Enrollment.objects.filter(student=self.student).delete()
        self.assertEqual(self.client.get(f'/api/study/courses/{self.course.id}/').status_code, 403)
        self.assertEqual(self.start().status_code, 403)
        Enrollment.objects.create(course=self.course, student=self.student)
        self.course.is_published = False
        self.course.save()
        self.assertEqual(self.client.get(f'/api/study/courses/{self.course.id}/').status_code, 403)
        self.assertEqual(self.send(f'/api/study/lessons/{self.lesson.id}/complete/').status_code, 403)

    def test_teacher_journal_uses_best_grade_and_has_no_student_access(self):
        Submission.objects.create(assignment=self.assignment, student=self.student, attempt_no=1, score=40)
        Submission.objects.create(assignment=self.assignment, student=self.student, attempt_no=2, score=90)
        url = f'/api/study/courses/{self.course.id}/report/'
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.teacher)
        report = self.client.get(url).json()
        row = next(s for s in report['students'] if s['student_id'] == self.student.id)
        self.assertEqual(row['assignments'][str(self.assignment.id)], 90)

    def test_guest_study_and_csrf(self):
        self.client.logout()
        self.assertEqual(self.client.get(f'/api/study/courses/{self.course.id}/').status_code, 401)
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.teacher)
        self.assertEqual(client.patch(f'/api/courses/teacher/{self.course.id}/', data='{}', content_type='application/json').status_code, 403)

    def test_case_insensitive_user_constraints(self):
        User = get_user_model()
        User.objects.create(username='MixedCase', email='Test@Example.com')
        for values in [{'username': 'mixedcase'}, {'username': 'another', 'email': 'test@example.com'}]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                User.objects.create(**values)

    def test_bad_login_does_not_crash(self):
        self.assertEqual(self.send('/api/auth/login/', {'username': [], 'password': {}}).status_code, 400)

    def test_admin_student_creation_validates_username_and_duplicate_email(self):
        self.client.force_login(self.admin)
        get_user_model().objects.create(username='email_owner', email='owner@example.com')
        url = '/api/auth/students/create/'
        self.assertEqual(self.send(url, {'username': 'new', 'email': 'OWNER@example.com', 'password': 'Private-password-2026'}).status_code, 409)
        self.assertEqual(self.send(url, {'username': 'bad name', 'email': 'valid@example.com', 'password': 'Private-password-2026'}).status_code, 400)
