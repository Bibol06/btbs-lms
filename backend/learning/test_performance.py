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
