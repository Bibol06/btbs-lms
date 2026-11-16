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
