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

    def test_structure_checks_each_prerequisite_once_not_per_lesson(self):
        few = self.count(*self.build(3, 1, prerequisites=True))
        many = self.count(*self.build(3, 6, prerequisites=True))
        self.assertEqual(few, many)
