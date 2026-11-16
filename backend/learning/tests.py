from django.contrib.auth import get_user_model
from django.test import TestCase
from courses.models import Course, Enrollment
from .models import Lesson


class LessonAccessTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.student = User.objects.create_user(username='learner', password='SecurePass2026!', role='student')
        self.course = Course.objects.create(title='Python', is_published=True)
        self.lesson = Lesson.objects.create(course=self.course, title='Short lesson',
            content='SECRET FULL CONTENT', is_published=True, position=1)
        self.url = f'/api/learning/courses/{self.course.id}/lessons/'

    def test_guest_only_sees_title(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        item = resp.json()['lessons'][0]
        self.assertEqual(item['title'], 'Short lesson')
        self.assertEqual(item['content'], '')
        self.assertTrue(item['locked'])

    def test_student_receives_content_only_after_enrollment(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(self.url).json()['lessons'][0]['content'], '')
        Enrollment.objects.create(course=self.course, student=self.student)
        self.assertEqual(self.client.get(self.url).json()['lessons'][0]['content'], 'SECRET FULL CONTENT')
        self.course.is_published = False
        self.course.save()
        self.assertEqual(self.client.get(self.url).status_code, 404)
