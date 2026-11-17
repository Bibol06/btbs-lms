from unittest.mock import patch
from django.test import TestCase
from django.core.cache import cache
from accounts.models import User
from courses.models import Course, CourseRun, Enrollment
from courses.catalog_cache import attach_counts
from analytics.models import ProgressSnapshot
from .models import Lesson, Step, StepProgress
from .services import course_progress, refresh_completions, with_step_progress, step_completed


class PerformanceRegressionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.course = Course.objects.create(title='Load regression', is_published=True)
        self.run = CourseRun.objects.create(course=self.course)
        self.student = User.objects.create(username='load-regression')
        self.enrollment = Enrollment.objects.create(course=self.course, run=self.run, student=self.student)
        self.lesson = Lesson.objects.create(course=self.course, title='Lesson', is_published=True)
        self.steps = [Step.objects.create(lesson=self.lesson, title=str(n), position=n+1, is_published=True) for n in range(20)]

    def test_progress_flags_are_one_query_and_isolated_by_enrollment(self):
        StepProgress.objects.create(enrollment=self.enrollment, step=self.steps[0])
        with self.assertNumQueries(1):
            flags = [step_completed(s, self.enrollment) for s in with_step_progress(Step.objects.all(), self.enrollment)]
        self.assertEqual(sum(flags), 1)
        other = User.objects.create(username='other-load')
        other_e = Enrollment.objects.create(course=self.course, run=self.run, student=other)
        self.assertFalse(step_completed(with_step_progress(Step.objects.all(), self.enrollment).first(), other_e))

    def test_progress_does_not_fetch_lesson_bodies_or_repeat_program_query(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        from .services import progress_steps, course_progress_many
        with CaptureQueriesContext(connection) as captured:
            steps = progress_steps({self.course.pk})
        self.assertEqual(len(captured), 1)
        self.assertNotIn('"content"', captured[0]['sql'])
        with CaptureQueriesContext(connection) as captured:
            result = course_progress_many([self.enrollment], steps=steps)
        self.assertEqual(result[self.enrollment.pk]['total'], 20)
        self.assertFalse(any('FROM "learning_step"' in q['sql'] for q in captured))

    def test_batch_snapshots_match_progress_and_preserve_archived_status(self):
        expected = course_progress(self.course, self.enrollment)
        self.assertEqual(refresh_completions([self.enrollment])[self.enrollment.pk], expected)
        refresh_completions([self.enrollment])
        self.assertEqual(ProgressSnapshot.objects.count(), 1)
        StepProgress.objects.bulk_create([StepProgress(enrollment=self.enrollment, step=s) for s in self.steps])
        self.assertEqual(refresh_completions([self.enrollment])[self.enrollment.pk]['percent'], 100)
        self.assertEqual(self.enrollment.status, 'completed')
        self.enrollment.status = 'archived'; self.enrollment.save()
        StepProgress.objects.all().delete()
        refresh_completions([self.enrollment])
        self.assertEqual(self.enrollment.status, 'archived')
        self.assertEqual(ProgressSnapshot.objects.count(), 3)

    def test_count_cache_invalidates_and_survives_cache_outage(self):
        self.assertEqual(attach_counts([self.course])[0].public_lessons, 1)
        self.lesson.is_published = False; self.lesson.save()
        self.assertEqual(attach_counts([self.course])[0].public_lessons, 0)
        with patch('courses.catalog_cache.cache.get_many', side_effect=ConnectionError), patch('courses.catalog_cache.cache.set_many', side_effect=ConnectionError):
            self.assertEqual(attach_counts([self.course])[0].all_lessons, 1)


class QueryScalingTests(TestCase):
    """Dashboard and course-plan queries must not grow with lessons/activities (N+1)."""

    def build(self, modules, lessons, prerequisites=False):
        from django.test import Client
        from assessment.models import Assignment, Quiz
        from courses.models import RunCheckpoint
        from .models import Module
        user = User.objects.create(username=f'scale-{modules}-{lessons}-{prerequisites}', role='student')
        course = Course.objects.create(title='Scale', is_published=True)
        run = CourseRun.objects.create(course=course)
        previous = None
        for mi in range(modules):
            module = Module.objects.create(course=course, title='M', position=mi + 1, is_published=True,
                                           prerequisite=previous if prerequisites else None)
            previous = module
            RunCheckpoint.objects.create(run=run, kind='weekly', period=mi + 1,
                                         quiz=Quiz.objects.create(course=course, title='C', is_published=True))
            for li in range(lessons):
                lesson = Lesson.objects.create(course=course, module=module, title='L', position=mi * 100 + li + 1, is_published=True)
                Step.objects.create(lesson=lesson, title='T', position=1, is_published=True)
                Step.objects.create(lesson=lesson, title='Q', kind='quiz', position=2, is_published=True,
                                    quiz=Quiz.objects.create(course=course, title='Q', is_published=True))
                Step.objects.create(lesson=lesson, title='A', kind='assignment', position=3, is_published=True,
                                    assignment=Assignment.objects.create(course=course, title='A', is_published=True))
        Enrollment.objects.create(student=user, course=course, run=run)
        client = Client()
        client.force_login(user)
        return client, f'/api/learning/courses/{course.pk}/structure/?run_id={run.pk}'

    def count(self, client, path):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        client.get(path)  # first call writes baseline progress snapshots
        with CaptureQueriesContext(connection) as captured:
            self.assertEqual(client.get(path).status_code, 200)
        return len(captured)

    def test_my_learning_is_constant_in_course_size(self):
        small = self.count(self.build(1, 1)[0], '/api/courses/my-learning/')
        large = self.count(self.build(4, 5)[0], '/api/courses/my-learning/')
        self.assertEqual(small, large)

    def test_structure_is_constant_in_lessons_and_checkpoints(self):
        small = self.count(*self.build(1, 1))
        large = self.count(*self.build(4, 5))
        self.assertEqual(small, large)

    def test_my_learning_is_constant_in_number_of_courses(self):
        from courses.models import RunModuleRelease
        from django.utils import timezone
        from datetime import timedelta
        counts = []
        for n in (1, 4):
            client, _ = self.build(1, n + 1)  # distinct user per iteration
            user = Enrollment.objects.latest('id').student
            for i in range(n - 1):
                course = Course.objects.create(title=f'Extra {i}', is_published=True)
                run = CourseRun.objects.create(course=course)
                from .models import Module
                from assessment.models import Quiz
                module = Module.objects.create(course=course, title='M', position=1, is_published=True)
                RunModuleRelease.objects.create(run=run, module=module, due_at=timezone.now() + timedelta(days=3))
                lesson = Lesson.objects.create(course=course, module=module, title='L', position=1, is_published=True)
                Step.objects.create(lesson=lesson, title='Q', kind='quiz', position=1, is_published=True,
                                    quiz=Quiz.objects.create(course=course, title='Q', is_published=True))
                Enrollment.objects.create(student=user, course=course, run=run)
            first = Enrollment.objects.filter(student=user).earliest('id')
            module = first.course.modules.first()
            RunModuleRelease.objects.create(run=first.run, module=module, due_at=timezone.now() + timedelta(days=3))
            counts.append(self.count(client, '/api/courses/my-learning/'))
        self.assertEqual(counts[0], counts[1])

    def test_structure_checks_each_prerequisite_once_not_per_lesson(self):
        few = self.count(*self.build(3, 1, prerequisites=True))
        many = self.count(*self.build(3, 6, prerequisites=True))
        self.assertEqual(few, many)


class ManagedRunIdsTests(TestCase):
    def test_matches_can_manage_run_for_every_role(self):
        from courses.access import can_manage_run, managed_run_ids
        from courses.models import CourseMember
        owner = User.objects.create(username='owner', role='teacher')
        editor = User.objects.create(username='editor', role='teacher')
        group_teacher = User.objects.create(username='group-teacher', role='teacher')
        admin = User.objects.create(username='admin', role='admin')
        inactive = User.objects.create(username='inactive', role='teacher', is_active=False)
        student = User.objects.create(username='student', role='student')
        runs = []
        for n in range(3):
            course = Course.objects.create(title=f'C{n}', is_published=True, teacher=owner if n == 0 else None)
            runs.append(CourseRun.objects.create(course=course, kind='cohort', title=f'R{n}'))
        CourseMember.objects.create(course=runs[1].course, user=editor)
        CourseMember.objects.create(course=runs[1].course, user=inactive)
        runs[2].teachers.add(group_teacher, inactive)
        for user in (owner, editor, group_teacher, admin, inactive, student):
            expected = {run.id for run in runs if can_manage_run(user, run)}
            self.assertEqual(managed_run_ids(user, runs), expected, user.username)
        self.assertEqual(managed_run_ids(admin, runs), {run.id for run in runs})
        self.assertEqual(managed_run_ids(owner, runs), {runs[0].id})

    def test_enrollment_batch_matches_can_manage_run(self):
        from courses.access import can_manage_run, managed_enrollment_ids
        from courses.models import CourseMember
        owner = User.objects.create(username='owner', role='teacher')
        editor = User.objects.create(username='editor', role='teacher')
        group_teacher = User.objects.create(username='group-teacher', role='teacher')
        admin = User.objects.create(username='admin', role='admin')
        student = User.objects.create(username='student', role='student')
        course = Course.objects.create(title='C', is_published=True, teacher=owner)
        other = Course.objects.create(title='O', is_published=True)
        runs = [CourseRun.objects.create(course=course, kind='cohort', title='R'), CourseRun.objects.create(course=other, kind='cohort', title='S')]
        CourseMember.objects.create(course=other, user=editor)
        runs[0].teachers.add(group_teacher)
        enrollments = [Enrollment.objects.create(student=u, course=r.course, run=r) for u in (owner, editor, group_teacher, admin, student) for r in runs]
        enrollments = list(Enrollment.objects.filter(id__in=[e.id for e in enrollments]).select_related('student', 'run__course'))
        self.assertEqual(managed_enrollment_ids(enrollments), {e.id for e in enrollments if can_manage_run(e.student, e.run)})


class GroupPageScalingTests(TestCase):
    """Teacher, admin and course pages must not grow with the number of students or activities."""

    def build(self, students, lessons):
        from assessment.models import Assignment, Question, Quiz, QuizAttempt, Submission
        from codejudge.models import CodeProblem, CodeSubmission, TestCase as CodeCase
        from django.utils import timezone
        from .models import Module
        tag = f'{students}-{lessons}'
        teacher = User.objects.create(username=f'teacher-{tag}', role='teacher')
        course = Course.objects.create(title=f'Group {tag}', is_published=True, teacher=teacher)
        run = CourseRun.objects.create(course=course, kind='cohort', title='G')
        module = Module.objects.create(course=course, title='M', position=1, is_published=True)
        problem = CodeProblem.objects.create(course=course, title='P', statement='s')
        CodeCase.objects.create(problem=problem, stdin='1', expected='1')
        activities = []
        for n in range(lessons):
            lesson = Lesson.objects.create(course=course, module=module, title='L', position=n + 1, is_published=True)
            quiz = Quiz.objects.create(course=course, title='Q', is_published=True)
            Question.objects.create(quiz=quiz, body='b', position=1, options=['a', 'b'], correct_index=0)
            task = Assignment.objects.create(course=course, title='A', is_published=True, due_at=timezone.now())
            Step.objects.create(lesson=lesson, title='T', position=1, is_published=True)
            Step.objects.create(lesson=lesson, title='Q', kind='quiz', quiz=quiz, position=2, is_published=True, pass_percent=50)
            Step.objects.create(lesson=lesson, title='A', kind='assignment', assignment=task, position=3, is_published=True)
            activities.append((quiz, task))
        Step.objects.create(lesson=lesson, title='C', kind='code', code_problem=problem, position=4, is_published=True)
        for n in range(students):
            student = User.objects.create(username=f'student-{tag}-{n}', role='student')
            e = Enrollment.objects.create(student=student, course=course, run=run)
            for quiz, task in activities:
                QuizAttempt.objects.create(enrollment=e, student=student, quiz=quiz, attempt_no=1, status='finished', score=1, max_score=1,
                                           deadline_at=timezone.now(), finished_at=timezone.now(), answers={})
                Submission.objects.create(enrollment=e, student=student, assignment=task, attempt_no=1, status='submitted', reviewer=teacher)
            CodeSubmission.objects.create(problem=problem, enrollment=e, code='x', status='accepted', passed=1, total=1)
        return teacher, student, course, run

    def count(self, user, path):
        from django.db import connection
        from django.test import Client
        from django.test.utils import CaptureQueriesContext
        client = Client()
        client.force_login(user)
        client.get(path)  # first call may write snapshots or finalize attempts
        with CaptureQueriesContext(connection) as captured:
            self.assertEqual(client.get(path).status_code, 200)
        return len(captured)

    def pages(self, students, lessons):
        teacher, student, course, run = self.build(students, lessons)
        study = f'/api/study/courses/{course.id}/?run_id={run.id}'
        return {'student course page': self.count(student, study), 'teacher course page': self.count(teacher, study),
                'course report': self.count(teacher, f'/api/study/courses/{course.id}/report/?run_id={run.id}'),
                'teacher home': self.count(teacher, '/api/workspace/home/'),
                'teacher analytics': self.count(teacher, f'/api/analytics/dashboard/?run_id={run.id}')}

    def test_pages_are_constant_in_students_and_activities(self):
        self.assertEqual(self.pages(2, 1), self.pages(6, 3))

    def test_admin_analytics_is_constant_in_students_and_teachers(self):
        admin = User.objects.create(username='scale-admin', role='admin')
        self.build(2, 1)
        few = self.count(admin, '/api/analytics/dashboard/')
        self.build(6, 3)
        self.assertEqual(few, self.count(admin, '/api/analytics/dashboard/'))
