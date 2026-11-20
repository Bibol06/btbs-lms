from django.contrib.auth import get_user_model
from django.test import TestCase
from .models import Course, Enrollment


class CoursePermissionsTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.student = User.objects.create_user(username='s1', password='SecurePass--2026', role='student')
        self.teacher = User.objects.create_user(username='t1', password='SecurePass--2026', role='teacher')
        self.course = Course.objects.create(title='Public Python', is_published=True)
        self.draft = Course.objects.create(title='Draft Python', is_published=False)

    def test_guest_sees_only_public_courses(self):
        response = self.client.get('/api/courses/')
        self.assertEqual(response.status_code, 200)
        titles = [x['title'] for x in response.json()['courses']]
        self.assertIn('Public Python', titles)
        self.assertNotIn('Draft Python', titles)

    def test_teacher_can_learn_another_course(self):
        self.client.force_login(self.teacher)
        response = self.client.post(f'/api/courses/{self.course.id}/enroll/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Enrollment.objects.count(), 1)

    def test_student_can_enroll_only_in_published(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.post(f'/api/courses/{self.draft.id}/enroll/').status_code, 403)
        self.assertEqual(self.client.post(f'/api/courses/{self.course.id}/enroll/').status_code, 200)
        self.assertEqual(self.client.post(f'/api/courses/{self.course.id}/enroll/').status_code, 200)
        self.assertEqual(Enrollment.objects.count(), 1)


class CatalogProgressTests(TestCase):
    """Catalog cards show the learner's own progress, batched (redesign phase 3)."""

    def setUp(self):
        from learning.models import Lesson, Step, StepProgress
        from .models import default_run
        self.student = get_user_model().objects.create_user(username='cp1', password='SecurePass--2026', role='student')
        self.courses = []
        for n in range(4):
            course = Course.objects.create(title=f'Course {n}', is_published=True)
            lesson = Lesson.objects.create(course=course, title='L', is_published=True)
            steps = [Step.objects.create(lesson=lesson, title=f'S{i}', position=i + 1, is_published=True) for i in range(4)]
            enrollment = Enrollment.objects.create(student=self.student, course=course, run=default_run(course))
            for step in steps[:n]:
                StepProgress.objects.create(enrollment=enrollment, step=step)
            self.courses.append(course)
        self.other = Course.objects.create(title='Not enrolled', is_published=True)

    def test_enrolled_courses_carry_percent(self):
        self.client.force_login(self.student)
        rows = {row['title']: row for row in self.client.get('/api/courses/').json()['courses']}
        self.assertEqual([rows[f'Course {n}']['progress'] for n in range(4)], [0, 25, 50, 75])
        self.assertEqual(rows['Course 1']['progress_run_id'], Enrollment.objects.get(student=self.student, course=self.courses[1]).run_id)
        self.assertNotIn('progress', rows['Not enrolled'])

    def test_guest_gets_no_progress(self):
        rows = self.client.get('/api/courses/').json()['courses']
        self.assertTrue(all('progress' not in row for row in rows))

    def test_query_count_does_not_grow_with_courses(self):
        self.client.force_login(self.student)
        self.client.get('/api/courses/')
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(connection) as few:
            self.client.get('/api/courses/')
        from learning.models import Lesson, Step
        from .models import default_run
        for n in range(6):
            course = Course.objects.create(title=f'Extra {n}', is_published=True)
            Step.objects.create(lesson=Lesson.objects.create(course=course, title='L', is_published=True), title='S', position=1, is_published=True)
            Enrollment.objects.create(student=self.student, course=course, run=default_run(course))
        with CaptureQueriesContext(connection) as many:
            self.client.get('/api/courses/')
        self.assertLessEqual(len(many), len(few) + 1)
