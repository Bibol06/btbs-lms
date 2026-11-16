from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from courses.models import Course, CourseRun, Enrollment
from learning.models import Lesson, Module, Step, StepProgress
from .models import Assignment, Submission, Quiz, Question, QuizAttempt
from codejudge.models import CodeProblem, CodeSubmission


class StudentReportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.teacher = User.objects.create_user(username='detail_teacher', role='teacher')
        cls.tutor = User.objects.create_user(username='detail_tutor', role='teacher')
        cls.student = User.objects.create_user(username='detail_student', first_name='Dana')
        cls.peer = User.objects.create_user(username='detail_peer')
        cls.course = Course.objects.create(title='Detail Course', teacher=cls.teacher, is_published=True)
        cls.cohort = CourseRun.objects.create(course=cls.course, title='A', kind='cohort')
        cls.other_run = CourseRun.objects.create(course=cls.course, title='B', kind='cohort')
        cls.cohort.teachers.add(cls.tutor)
        cls.enrollment = Enrollment.objects.create(course=cls.course, run=cls.cohort, student=cls.student)
        cls.other_enrollment = Enrollment.objects.create(course=cls.course, run=cls.other_run, student=cls.student)
        Enrollment.objects.create(course=cls.course, run=cls.cohort, student=cls.peer)
        cls.module = Module.objects.create(course=cls.course, title='Module', is_published=True)
        cls.lesson = Lesson.objects.create(course=cls.course, module=cls.module, title='Lesson', is_published=True)
        cls.step = Step.objects.create(lesson=cls.lesson, title='Text', is_published=True)
        StepProgress.objects.create(step=cls.step, enrollment=cls.enrollment)
        cls.assignment = Assignment.objects.create(course=cls.course, title='Essay', is_published=True)
        Submission.objects.create(assignment=cls.assignment, student=cls.student, enrollment=cls.enrollment, attempt_no=1, text_answer='Answer in group A', status='graded', score=70, feedback='Good', graded_at=timezone.now())
        Submission.objects.create(assignment=cls.assignment, student=cls.student, enrollment=cls.other_enrollment, attempt_no=1, text_answer='Private group B')
        Submission.objects.create(assignment=cls.assignment, student=cls.peer, enrollment=Enrollment.objects.get(run=cls.cohort, student=cls.peer), attempt_no=1, text_answer='Peer private answer')
        cls.quiz = Quiz.objects.create(course=cls.course, title='Quiz', is_published=True)
        cls.question = Question.objects.create(quiz=cls.quiz, body='2+2?', options=['3', '4'], correct_index=1, position=1)
        cls.blank = Question.objects.create(quiz=cls.quiz, body='Not answered', options=['A', 'B'], correct_index=0, position=2)
        QuizAttempt.objects.create(quiz=cls.quiz, student=cls.student, enrollment=cls.enrollment, attempt_no=1,
            answers={str(cls.question.id): 0}, deadline_at=timezone.now(), finished_at=timezone.now(), status='finished', score=0, max_score=2)
        cls.problem = CodeProblem.objects.create(course=cls.course, title='Sum', statement='Sum two')
        CodeSubmission.objects.create(problem=cls.problem, enrollment=cls.enrollment, code='print(5)', status='accepted', passed=3, total=3)
        CodeSubmission.objects.create(problem=cls.problem, enrollment=cls.other_enrollment, code='SECRET_GROUP_B', status='rejected')

    def url(self, run=None, student=None):
        return f'/api/study/courses/{self.course.id}/students/{(student or self.student).id}/?run_id={(run or self.cohort).id}'

    def test_teacher_sees_steps_written_answers_quiz_choices_and_code(self):
        self.client.force_login(self.teacher)
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['progress']['percent'], 100)
        self.assertTrue(data['lessons'][0]['completed'])
        self.assertIsNotNone(data['lessons'][0]['steps'][0]['completed_at'])
        self.assertEqual(data['assignments'][0]['submissions'][0]['text_answer'], 'Answer in group A')
        answers = data['quizzes'][0]['attempts'][0]['answers']
        self.assertEqual(answers[0]['selected_index'], 0)
        self.assertFalse(answers[0]['correct'])
        self.assertEqual(answers[0]['correct_index'], 1)
        self.assertIsNone(answers[1]['selected_index'])
        self.assertEqual(data['code_problems'][0]['submissions'][0]['code'], 'print(5)')
        self.assertNotIn('Private group B', str(data))
        self.assertNotIn('Peer private answer', str(data))
        self.assertNotIn('SECRET_GROUP_B', str(data))

    def test_student_peer_and_unauthorized_teacher_cannot_read_answers(self):
        self.assertEqual(self.client.get(self.url()).status_code, 401)
        for user in [self.student, self.peer, get_user_model().objects.create_user(username='unrelated', role='teacher')]:
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.url()).status_code, 403)

    def test_tutor_scope_and_removed_enrollment_preserves_teacher_access(self):
        self.client.force_login(self.tutor)
        self.assertEqual(self.client.get(self.url()).status_code, 200)
        self.assertEqual(self.client.get(self.url(self.other_run)).status_code, 403)
        self.enrollment.status = 'removed'
        self.enrollment.save()
        self.assertEqual(self.client.get(self.url()).json()['status'], 'removed')

    def test_unknown_enrollment_and_other_course_run_are_rejected(self):
        self.client.force_login(self.teacher)
        outsider = get_user_model().objects.create_user(username='not_enrolled')
        self.assertEqual(self.client.get(self.url(student=outsider)).status_code, 404)
        other_course = Course.objects.create(title='Other')
        wrong_run = CourseRun.objects.create(course=other_course)
        self.assertEqual(self.client.get(self.url(run=wrong_run)).status_code, 404)

    def test_draft_steps_do_not_make_published_lesson_incomplete(self):
        Step.objects.create(lesson=self.lesson, position=2, title='Draft', is_published=False)
        self.client.force_login(self.teacher)
        data = self.client.get(self.url()).json()
        self.assertTrue(data['lessons'][0]['completed'])
        self.assertFalse(data['lessons'][0]['steps'][1]['is_published'])

    def test_completion_is_computed_from_assessment_not_manual_theory_marker(self):
        step = Step.objects.create(lesson=self.lesson, position=2, title='Essay step', is_published=True, kind='assignment', assignment=self.assignment, pass_percent=80)
        StepProgress.objects.create(step=step, enrollment=self.enrollment)
        self.client.force_login(self.teacher)
        data = self.client.get(self.url()).json()
        self.assertFalse(data['lessons'][0]['completed'])
        self.assertFalse(data['lessons'][0]['steps'][1]['completed'])
        self.assertEqual(data['progress']['percent'], 50)

