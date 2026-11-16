from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from communication.models import AuditEvent
from courses.models import Course, CourseRun, Enrollment
from learning.models import Lesson, Step, StepProgress
from .models import Assignment, AssignmentExtension, Submission, GradeReview


class ManagementAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.admin = User.objects.create_user(username='control_admin', role='admin')
        cls.owner = User.objects.create_user(username='control_owner', role='teacher')
        cls.other = User.objects.create_user(username='control_other', role='teacher')
        cls.tutor = User.objects.create_user(username='control_tutor')
        cls.student = User.objects.create_user(username='control_student', first_name='Думан', last_name='Нурланов')
        cls.peer = User.objects.create_user(username='control_peer', first_name='Аружан', last_name='Садыкова')
        cls.course = Course.objects.create(title='Managed course', teacher=cls.owner, is_published=True)
        cls.foreign_course = Course.objects.create(title='Other private course', teacher=cls.other)
        cls.group = CourseRun.objects.create(course=cls.course, title='My group', kind='cohort')
        cls.other_group = CourseRun.objects.create(course=cls.course, title='Other group', kind='cohort')
        cls.foreign_group = CourseRun.objects.create(course=cls.foreign_course, title='Private group', kind='cohort')
        cls.group.teachers.add(cls.tutor)
        cls.enrollment = Enrollment.objects.create(course=cls.course, run=cls.group, student=cls.student)
        cls.other_enrollment = Enrollment.objects.create(course=cls.course, run=cls.other_group, student=cls.student)
        cls.foreign_enrollment = Enrollment.objects.create(course=cls.foreign_course, run=cls.foreign_group, student=cls.peer)
        cls.assignment = Assignment.objects.create(course=cls.course, title='Work', is_published=True)
        cls.private_assignment = Assignment.objects.create(course=cls.foreign_course, title='Private work', is_published=True)
        cls.own_work = Submission.objects.create(assignment=cls.assignment, enrollment=cls.enrollment, student=cls.student, attempt_no=1,
            reviewer=cls.tutor, review_due_at=timezone.now()-timedelta(hours=1))
        cls.other_work = Submission.objects.create(assignment=cls.assignment, enrollment=cls.other_enrollment, student=cls.student, attempt_no=1, reviewer=cls.owner)
        cls.foreign_work = Submission.objects.create(assignment=cls.private_assignment, enrollment=cls.foreign_enrollment, student=cls.peer, attempt_no=1)
        GradeReview.objects.create(submission=cls.own_work, reviewer=cls.tutor, action='returned', feedback='Fix')
        cls.lesson = Lesson.objects.create(course=cls.course, title='Introduction', is_published=True)
        cls.step = Step.objects.create(lesson=cls.lesson, title='Theory', is_published=True)
        StepProgress.objects.create(enrollment=cls.enrollment, step=cls.step)
        AuditEvent.objects.create(actor=cls.owner, course=cls.course, action='run.updated')
        AuditEvent.objects.create(actor=cls.other, course=cls.foreign_course, action='run.updated')

    def get(self, path):
        return self.client.get('/api/study/management/' + path)

    def test_management_and_queue_require_authentication_and_student_is_denied(self):
        paths = ['overview/', 'students/', 'teachers/', 'courses/', 'activity/', f'enrollments/{self.enrollment.id}/tasks/']
        for path in paths:
            self.assertEqual(self.get(path).status_code, 401, path)
        self.client.force_login(self.student)
        for path in paths:
            self.assertEqual(self.get(path).status_code, 403, path)
        self.assertEqual(self.client.get('/api/study/review-queue/').status_code, 403)
        self.assertEqual(self.client.get('/api/study/agenda/').status_code, 200)

    def test_teacher_only_receives_own_courses_and_enrollments(self):
        self.client.force_login(self.owner)
        data = self.get('overview/').json()
        self.assertEqual(data['scope'], 'assigned_courses')
        self.assertEqual(data['metrics']['courses'], 1)
        self.assertEqual(data['metrics']['pending'], 2)
        self.assertNotIn('users', data['metrics'])
        self.assertEqual({r['course_id'] for r in data['runs']}, {self.course.id})
        rows = self.get('students/').json()['students']
        self.assertEqual({s['enrollment_id'] for s in rows}, {self.enrollment.id, self.other_enrollment.id})
        self.assertEqual(self.get(f'students/?course_id={self.foreign_course.id}').json()['total'], 0)
        for path in ('teachers/', 'courses/', 'activity/'):
            self.assertEqual(self.get(path).status_code, 403)

    def test_run_teacher_cannot_see_same_students_other_group_or_foreign_tasks(self):
        self.client.force_login(self.tutor)
        self.assertTrue(self.client.get('/api/auth/me/').json()['can_teach'])
        data = self.get('overview/').json()
        self.assertEqual(data['metrics']['pending'], 1)
        rows = self.get('students/').json()['students']
        self.assertEqual([s['enrollment_id'] for s in rows], [self.enrollment.id])
        self.assertEqual(rows[0]['progress']['percent'], 100)
        self.assertEqual(self.get(f'enrollments/{self.other_enrollment.id}/tasks/').status_code, 404)
        self.assertEqual(self.get(f'enrollments/{self.foreign_enrollment.id}/tasks/').status_code, 404)
        tasks = self.get(f'enrollments/{self.enrollment.id}/tasks/').json()['tasks']
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]['run_id'], self.group.id)
        self.assertEqual(tasks[0]['state'], 'waiting')
        self.assertTrue(tasks[0]['review_overdue'])

    def test_admin_global_metrics_and_teacher_responsibility_are_correct(self):
        self.client.force_login(self.admin)
        data = self.get('overview/').json()
        self.assertEqual(data['scope'], 'platform')
        self.assertEqual(data['metrics']['courses'], 2)
        self.assertEqual(data['metrics']['students'], 2)
        self.assertEqual(data['metrics']['pending'], 3)
        self.assertEqual(data['metrics']['overdue'], 1)
        self.assertEqual(data['metrics']['unassigned'], 1)
        tutors = self.get('teachers/').json()['teachers']
        tutor = next(t for t in tutors if t['id'] == self.tutor.id)
        self.assertEqual((tutor['courses'], tutor['groups'], tutor['students'], tutor['pending'], tutor['overdue'], tutor['reviewed_week']), (1, 1, 1, 1, 1, 1))
        other = next(t for t in tutors if t['id'] == self.other.id)
        self.assertEqual(other['unassigned'], 1)
        self.assertEqual(self.get('activity/').json()['total'], 2)
        courses = self.get('courses/').json()['courses']
        course = next(c for c in courses if c['id'] == self.course.id)
        self.assertEqual((course['pending'], course['overdue']), (2, 1))
        self.assertEqual(self.get(f'enrollments/{self.foreign_enrollment.id}/tasks/').status_code, 200)

    def test_review_filters_cannot_expand_teacher_scope(self):
        self.client.force_login(self.tutor)
        url = '/api/study/review-queue/'
        self.assertEqual(self.client.get(url+f'?run_id={self.other_group.id}').json()['total'], 0)
        self.assertEqual(self.client.get(url+f'?reviewer_id={self.owner.id}').json()['total'], 0)
        own = self.client.get(url+f'?reviewer_id={self.tutor.id}&course_id={self.course.id}').json()
        self.assertEqual([s['id'] for s in own['works']], [self.own_work.id])
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(url+f'?reviewer_id={self.owner.id}').json()['total'], 1)
        self.assertEqual(self.client.get(url+'?reviewer_id=oops').status_code, 400)

    def test_pagination_search_status_and_historical_access(self):
        self.client.force_login(self.admin)
        User = get_user_model()
        for i in range(21):
            user = User.objects.create_user(username=f'roster_{i}')
            Enrollment.objects.create(course=self.course, run=self.group, student=user)
        first = self.get('students/').json()
        self.assertEqual(len(first['students']), 20)
        self.assertEqual(first['next_page'], 2)
        second = self.get('students/?page=2').json()
        self.assertFalse({s['enrollment_id'] for s in first['students']} & {s['enrollment_id'] for s in second['students']})
        self.assertEqual(self.get('students/?search=Нурланов').json()['total'], 2)
        self.assertEqual(self.get('students/?status=unknown').status_code, 400)
        self.assertEqual(self.get('students/?page=0').status_code, 400)
        Enrollment.objects.filter(pk=self.enrollment.id).update(status='removed')
        historical = self.get(f'enrollments/{self.enrollment.id}/tasks/').json()
        self.assertTrue(historical['historical'])
        self.assertEqual(historical['tasks'], [])
        self.assertEqual(self.get('students/?status=removed').json()['total'], 1)

    def test_course_owner_with_default_role_gets_teaching_workspace_capability(self):
        owner = get_user_model().objects.create_user(username='default_role_owner')
        Course.objects.create(title='Owned', teacher=owner)
        self.client.force_login(owner)
        me = self.client.get('/api/auth/me/').json()
        self.assertTrue(me['can_teach'])
        self.assertEqual(me['role_label'], 'Преподаватель')
        self.assertEqual(self.get('overview/').json()['metrics']['courses'], 1)
        self.assertEqual(self.get('courses/').status_code, 403)

    def test_monitoring_does_not_change_roles_answers_or_submit_work(self):
        self.client.force_login(self.admin)
        before = list(Submission.objects.order_by('id').values('id', 'status', 'score', 'text_answer', 'reviewer_id'))
        for path in ['overview/', 'students/', 'teachers/', 'courses/', 'activity/', f'enrollments/{self.enrollment.id}/tasks/']:
            self.assertEqual(self.get(path).status_code, 200)
            self.assertEqual(self.client.post('/api/study/management/'+path, data='{}', content_type='application/json').status_code, 405)
        self.assertEqual(before, list(Submission.objects.order_by('id').values('id', 'status', 'score', 'text_answer', 'reviewer_id')))
        self.tutor.refresh_from_db()
        self.assertEqual(self.tutor.role, 'student')

    def test_student_home_deadlines_match_personal_tasks_and_hide_waiting_and_locked_work(self):
        now = timezone.now()
        Assignment.objects.filter(pk=self.assignment.id).update(due_at=now+timedelta(days=2))
        revision = Assignment.objects.create(course=self.course, title='Personal revision', is_published=True, due_at=now-timedelta(days=1))
        Submission.objects.create(assignment=revision, enrollment=self.enrollment, student=self.student, attempt_no=1, status='returned')
        due = now+timedelta(days=3)
        AssignmentExtension.objects.create(assignment=revision, enrollment=self.enrollment, deadline_at=due, granted_by=self.owner)
        hidden = Assignment.objects.create(course=self.course, title='Locked assignment', is_published=True, due_at=now+timedelta(days=1))
        Step.objects.create(lesson=self.lesson, title='Locked', kind='assignment', assignment=hidden, is_published=False, position=2)
        self.client.force_login(self.student)
        data = self.client.get('/api/courses/my-learning/').json()
        row = next(e for e in data['enrollments'] if e['id'] == self.enrollment.id)
        self.assertEqual([d['title'] for d in row['deadlines']], ['Personal revision'])
        self.assertEqual(row['deadlines'][0]['label'], 'Исправить до')
        self.assertEqual(row['pending'], 1)
