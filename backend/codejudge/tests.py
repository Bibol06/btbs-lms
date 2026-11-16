import json
from unittest import skipUnless
from django.contrib.auth import get_user_model
from django.test import TestCase, SimpleTestCase
from courses.models import Course, CourseRun, Enrollment
from learning.models import Module, Lesson, Step
from .models import CodeProblem, TestCase as ProblemCase, CodeSubmission
from .runner import run_python, runtime_path


@skipUnless(runtime_path().is_file(), 'Run manage.py setup_code_runner to enable WASI integration tests')
class SandboxTests(SimpleTestCase):
    def test_real_python_and_math(self):
        result = run_python('import math\na=int(input()); b=int(input()); print(a+b); print(math.isqrt(16))', ['2\n3\n'])[0]
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['stdout'], '5\n4\n')

    def test_loop_is_bounded(self):
        result = run_python('while True: pass', [''])[0]
        self.assertIn(result['status'], ['limit_exceeded', 'time_limit'])

    def test_host_files_and_environment_are_not_visible(self):
        result = run_python("import os\nprint(os.environ.get('DJANGO_SECRET_KEY'))\nprint(open('/etc/passwd').read())", [''])[0]
        self.assertEqual(result['stdout'].strip(), 'None')
        self.assertEqual(result['status'], 'runtime_error')

    def test_output_is_bounded(self):
        result = run_python("print('x'*100000)", [''])[0]
        self.assertEqual(result['status'], 'output_limit')
        self.assertLessEqual(len(result['stdout']), 8192)


@skipUnless(runtime_path().is_file(), 'Run manage.py setup_code_runner to enable WASI integration tests')
class CodeWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.teacher = User.objects.create_user(username='code_teacher', role='teacher')
        cls.student = User.objects.create_user(username='code_student')
        cls.other = User.objects.create_user(username='code_other')
        cls.course = Course.objects.create(title='Python', teacher=cls.teacher, is_published=True)
        cls.cohort = CourseRun.objects.create(course=cls.course, title='Group', kind='cohort')
        cls.enrollment = Enrollment.objects.create(course=cls.course, run=cls.cohort, student=cls.student)
        module = Module.objects.create(course=cls.course, title='Python', is_published=True)
        lesson = Lesson.objects.create(course=cls.course, module=module, title='Sum', is_published=True)
        cls.problem = CodeProblem.objects.create(course=cls.course, title='Sum', statement='Add two numbers', max_attempts=2)
        ProblemCase.objects.create(problem=cls.problem, stdin='2\n3\n', expected='5', is_sample=True)
        ProblemCase.objects.create(problem=cls.problem, stdin='-4\n7\n', expected='3', is_sample=False, position=2)
        cls.step = Step.objects.create(lesson=lesson, title='Sum', kind='code', code_problem=cls.problem, is_published=True)

    def setUp(self):
        self.client.force_login(self.student)

    def url(self, action=''):
        return f'/api/code/problems/{self.problem.id}/{action}?run_id={self.cohort.id}'

    def send(self, code, submit=True):
        return self.client.post(self.url('execute/'), json.dumps({'code': code, 'submit': submit, 'stdin': '1\n2\n'}), content_type='application/json')

    def test_grading_and_hidden_cases(self):
        detail = self.client.get(self.url()).json()
        self.assertEqual(len(detail['problem']['samples']), 1)
        response = self.send('a=int(input()); b=int(input()); print(a+b)')
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result['status'], 'accepted')
        self.assertEqual(result['passed'], 2)
        self.assertNotIn('stdout', result['details'][1])
        self.assertNotIn('stderr', result['details'][1])
        progress = self.client.get(f'/api/learning/courses/{self.course.id}/structure/?run_id={self.cohort.id}').json()['progress']
        self.assertEqual(progress['percent'], 100)

    def test_practice_does_not_grade_or_consume_attempt(self):
        response = self.send('print(123)', submit=False)
        self.assertEqual(response.json()['stdout'], '123\n')
        self.assertEqual(CodeSubmission.objects.count(), 0)

    def test_attempt_limit_and_privacy(self):
        self.assertEqual(self.send('print(0)').json()['status'], 'rejected')
        self.assertEqual(self.send('print(0)').json()['status'], 'rejected')
        self.assertEqual(self.send('print(0)').status_code, 400)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url()).status_code, 403)
        self.assertEqual(self.send('print(0)').status_code, 403)

    def test_unpublished_step_blocks_execution(self):
        self.step.is_published = False
        self.step.save()
        self.assertEqual(self.send('print(0)').status_code, 404)

    def test_problem_keys_only_for_editor_and_freeze_after_submission(self):
        detail = self.client.get(self.url()).json()
        self.assertIsNone(detail['editor'])
        self.assertNotIn('test_cases', detail['problem'])
        self.send('print(0)')
        self.client.force_login(self.teacher)
        detail = self.client.get(self.url()).json()
        self.assertFalse(detail['editor']['can_edit'])
        self.assertEqual(len(detail['editor']['test_cases']), 2)
        response = self.client.patch(self.url(), json.dumps({'title': 'Edited'}), content_type='application/json')
        self.assertEqual(response.status_code, 400)
