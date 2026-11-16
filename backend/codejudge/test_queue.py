"""Queued code checks. run_python is mocked, so these run without the WASI runtime."""
import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from background import exclusive
from common import ApiError
from courses.models import Course, CourseRun, Enrollment
from learning.models import Lesson, Module, Step
from .models import CodeProblem, CodeSubmission, TestCase as ProblemCase
from .tasks import judge_submission, practice_run

OK = {'status': 'ok', 'stdout': '5\n', 'stderr': ''}


class QueuedCodeCheckTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.student = User.objects.create_user(username='queue_student')
        cls.other = User.objects.create_user(username='queue_other')
        course = Course.objects.create(title='Python', is_published=True)
        cls.cohort = CourseRun.objects.create(course=course, title='Group', kind='cohort')
        cls.enrollment = Enrollment.objects.create(course=course, run=cls.cohort, student=cls.student)
        Enrollment.objects.create(course=course, run=cls.cohort, student=cls.other)
        module = Module.objects.create(course=course, title='M', is_published=True)
        lesson = Lesson.objects.create(course=course, module=module, title='L', is_published=True)
        cls.problem = CodeProblem.objects.create(course=course, title='Sum', statement='Add', max_attempts=3)
        ProblemCase.objects.create(problem=cls.problem, stdin='2\n3\n', expected='5', is_sample=True)
        Step.objects.create(lesson=lesson, title='Sum', kind='code', code_problem=cls.problem, is_published=True)

    def setUp(self):
        cache.clear()
        self.client.force_login(self.student)

    def send(self, submit=True):
        return self.client.post(f'/api/code/problems/{self.problem.id}/execute/?run_id={self.cohort.id}',
                                json.dumps({'code': 'print(5)', 'submit': submit, 'stdin': ''}), content_type='application/json')

    def poll(self, record_id):
        return self.client.get(f'/api/code/submissions/{record_id}/')

    def test_inline_mode_answers_with_verdict(self):
        with patch('codejudge.tasks.run_python', return_value=[OK]):
            response = self.send()
        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.json()['status'], response.json()['passed']), ('accepted', 1))

    def test_queued_submission_is_polled_by_its_owner_only(self):
        with patch.object(judge_submission, 'apply_async') as queued:
            response = self.send()
        self.assertEqual(response.status_code, 202)
        record_id = response.json()['id']
        self.assertEqual(queued.call_args.kwargs['expires'], 90)
        self.assertEqual(self.poll(record_id).json(), {'id': record_id, 'status': 'running'})
        self.assertEqual(self.send().status_code, 409)  # one pending check per student
        with patch('codejudge.tasks.run_python', return_value=[OK]):
            judge_submission(record_id)
        result = self.poll(record_id).json()
        self.assertEqual((result['status'], result['passed'], result['total']), ('accepted', 1, 1))
        self.client.force_login(self.other)
        self.assertEqual(self.poll(record_id).status_code, 404)
        self.client.logout()
        self.assertEqual(self.poll(record_id).status_code, 401)

    def test_check_that_waited_too_long_becomes_service_error(self):
        with patch.object(judge_submission, 'apply_async'):
            record_id = self.send().json()['id']
        CodeSubmission.objects.filter(pk=record_id).update(created_at=timezone.now() - timedelta(minutes=3))
        with patch('codejudge.tasks.run_python') as runner:
            judge_submission(record_id)
        runner.assert_not_called()
        self.assertEqual(self.poll(record_id).json()['status'], 'service_error')
        # A service error does not use up an attempt.
        with patch('codejudge.tasks.run_python', return_value=[OK]):
            self.assertEqual(self.send().status_code, 200)

    def test_sandbox_failure_is_reported_and_not_counted(self):
        with patch('codejudge.tasks.run_python', side_effect=ApiError('Изолированная среда временно недоступна', 503)):
            response = self.send()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(CodeSubmission.objects.get().status, 'service_error')

    def test_queued_practice_run(self):
        with patch.object(practice_run, 'apply_async') as queued:
            response = self.send(submit=False)
            self.assertEqual(response.status_code, 202)
            self.assertEqual(self.send(submit=False).status_code, 429)
        token = response.json()['run_token']
        url = f'/api/code/runs/{token}/'
        self.assertEqual(self.client.get(url).json(), {'status': 'running'})
        with patch('codejudge.tasks.run_python', return_value=[OK]):
            practice_run(*queued.call_args.args[0])
        self.assertEqual(self.client.get(url).json(), OK)
        self.assertFalse(CodeSubmission.objects.exists())
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.student)
        with patch('codejudge.tasks.run_python', return_value=[OK]):
            self.assertEqual(self.send(submit=False).json()['stdout'], OK['stdout'])  # finished run frees the slot

    def test_practice_sandbox_error_keeps_status_code(self):
        with patch('codejudge.tasks.run_python', side_effect=ApiError('Среда Python не установлена.', 503)):
            response = self.send(submit=False)
        self.assertEqual(response.status_code, 503)


class BackgroundTaskTests(SimpleTestCase):
    def test_exclusive_skips_overlapping_run(self):
        calls = []

        @exclusive(ttl=60)
        def job():
            calls.append(1)
            self.assertIsNone(job())  # nested call while the lock is held
            return 'done'
        self.assertEqual(job(), 'done')
        self.assertEqual(job(), 'done')
        self.assertEqual(len(calls), 2)

    def test_beat_schedule_points_at_registered_tasks(self):
        from django.conf import settings
        from config.celery import app
        app.loader.import_default_modules()
        for name, entry in settings.CELERY_BEAT_SCHEDULE.items():
            self.assertIn(entry['task'], app.tasks, name)
        self.assertEqual(app.amqp.router.route({}, 'codejudge.tasks.judge_submission')['queue'].name, 'judge')
