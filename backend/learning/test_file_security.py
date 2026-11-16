import tempfile
from django.test import TestCase, Client, override_settings
from django.core.files.base import ContentFile
from accounts.models import User
from courses.models import Course, CourseRun, Enrollment
from .models import Lesson, LessonMaterial


class PrivateFileSecurityTests(TestCase):
    def test_private_pdf_access_and_embedded_headers(self):
        with tempfile.TemporaryDirectory() as root, override_settings(MEDIA_ROOT=root, MEDIA_STORAGE_MODE='local'):
            teacher = User.objects.create(username='file-teacher', role='teacher')
            student = User.objects.create(username='file-student', role='student')
            course = Course.objects.create(title='Private course', teacher=teacher, is_published=True)
            run = CourseRun.objects.create(course=course)
            lesson = Lesson.objects.create(course=course, title='Lesson', is_published=True)
            material = LessonMaterial.objects.create(lesson=lesson, title='Document', file=ContentFile(b'%PDF-1.4\n', name='document.pdf'))
            url = f'/api/learning/materials/{material.pk}/open/?run_id={run.pk}'
            self.assertIn(self.client.get(url).status_code, (401, 403))
            self.client.force_login(student)
            self.assertEqual(self.client.get(url).status_code, 403)
            Enrollment.objects.create(student=student, course=course, run=run)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['X-Frame-Options'], 'SAMEORIGIN')
            self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
            self.assertIn('private', response['Cache-Control'])
            lesson.is_published = False
            lesson.save()
            self.assertIn(self.client.get(url).status_code, (403, 404))
            response.close()

    def test_login_requires_csrf(self):
        browser = Client(enforce_csrf_checks=True)
        self.assertEqual(browser.post('/api/auth/login/', {'username': 'x', 'password': 'x'}).status_code, 403)
