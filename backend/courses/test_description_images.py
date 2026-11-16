import json
import tempfile
from io import BytesIO
from pathlib import Path

from PIL import Image
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from .models import Course, CourseImage, CourseMember, CourseRun

PNG = b'\x89PNG\r\n\x1a\n'


class DescriptionImageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user(username='description_owner', role='teacher')
        cls.editor = User.objects.create_user(username='description_editor', role='teacher')
        cls.tutor = User.objects.create_user(username='description_tutor', role='teacher')
        cls.student = User.objects.create_user(username='description_student')
        cls.admin = User.objects.create_user(username='description_admin', role='admin')
        cls.course = Course.objects.create(teacher=cls.owner, title='Illustrated course', description='Original description')
        CourseMember.objects.create(course=cls.course, user=cls.editor)
        cls.cohort = CourseRun.objects.create(course=cls.course, title='Self-paced')
        cls.cohort.teachers.add(cls.tutor)

    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.settings = override_settings(MEDIA_ROOT=self.media.name)
        self.settings.enable()
        self.addCleanup(self.settings.disable)
        self.addCleanup(self.media.cleanup)

    def upload(self, *, user=None, content=None, filename='banner.png'):
        self.client.force_login(user or self.owner)
        if content is None:
            buffer = BytesIO()
            Image.new('RGB', (12, 6), 'teal').save(buffer, format='PNG')
            content = buffer.getvalue()
        return self.client.post(f'/api/courses/teacher/{self.course.id}/images/', {
            'file': SimpleUploadedFile(filename, content), 'title': 'Course banner'})

    def image(self):
        response = self.upload()
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()['image']

    def patch(self, description, course=None):
        self.client.force_login(self.owner)
        return self.client.patch(f'/api/courses/teacher/{(course or self.course).id}/',
            json.dumps({'description': description}), content_type='application/json')

    def source(self, image):
        return f"## About Python\n\n![Course banner]({image['url']})\n\nKeep `print()` unchanged."

    def public(self, description):
        self.course.description = description
        self.course.is_published = True
        self.course.save()
        self.client.logout()

    def test_upload_and_editor_preview_are_private_until_description_is_published(self):
        image = self.image()
        row = CourseImage.objects.get(pk=image['id'])
        self.assertTrue(Path(row.file.path).exists())
        response = self.client.get(image['url'])
        self.assertEqual(response.status_code, 200)
        b''.join(response.streaming_content)
        self.client.logout()
        self.assertEqual(self.client.get(image['url']).status_code, 404)
        self.public('No picture is referenced here')
        self.assertEqual(self.client.get(image['url']).status_code, 404)
        self.assertEqual(self.patch(self.source(image)).status_code, 200)
        self.client.logout()
        response = self.client.get(image['url'])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/png')
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        self.assertNotIn('attachment', response.get('Content-Disposition', ''))
        self.assertTrue(b''.join(response.streaming_content).startswith(b'\x89PNG'))
        self.course.is_published = False
        self.course.save(update_fields=['is_published'])
        self.assertEqual(self.client.get(image['url']).status_code, 404)

    def test_only_course_editors_and_admin_can_upload(self):
        for user in [self.student, self.tutor]:
            self.assertEqual(self.upload(user=user).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.post(f'/api/courses/teacher/{self.course.id}/images/').status_code, 401)
        for user in [self.owner, self.editor, self.admin]:
            self.assertEqual(self.upload(user=user).status_code, 201)
        self.assertEqual(CourseImage.objects.count(), 3)

    def test_corrupt_images_wrong_extensions_and_empty_files_are_rejected(self):
        for filename, content in [('x.svg', b'<svg/>'), ('x.png', b'<script>evil</script>'), ('x.png', b''), ('x.jpg', PNG), ('x.png', b'a' * (8 * 1024 * 1024 + 1))]:
            with self.subTest(filename=filename, size=len(content)):
                self.assertEqual(self.upload(filename=filename, content=content).status_code, 400)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(f'/api/courses/teacher/{self.course.id}/images/').status_code, 400)
        self.assertFalse(CourseImage.objects.exists())

    def test_valid_jpeg_and_pixel_limit_use_shared_validation(self):
        buffer = BytesIO()
        Image.new('RGB', (20, 10)).save(buffer, format='JPEG')
        response = self.upload(filename='photo.jpg', content=buffer.getvalue())
        self.assertEqual(response.status_code, 201)
        response = self.client.get(response.json()['image']['url'])
        self.assertEqual(response['Content-Type'], 'image/jpeg')
        b''.join(response.streaming_content)
        buffer = BytesIO()
        Image.new('1', (5000, 4000)).save(buffer, format='PNG')
        self.assertEqual(self.upload(content=buffer.getvalue()).status_code, 400)

    def test_plain_links_and_code_examples_do_not_publish_images(self):
        image = self.image()
        for content in [image['url'], f"`![example]({image['url']})`", f"```markdown\n![example]({image['url']})\n```"]:
            self.public(content)
            self.assertEqual(self.client.get(image['url']).status_code, 404)

    def test_description_cannot_use_other_courses_images_or_private_lesson_assets(self):
        image = self.image()
        other = Course.objects.create(teacher=self.owner, title='Other course', description='Keep this')
        self.assertEqual(self.patch(self.source(image), other).status_code, 400)
        other.refresh_from_db()
        self.assertEqual(other.description, 'Keep this')
        self.assertEqual(self.patch('![Private lesson](/api/learning/images/999/)').status_code, 400)
        self.assertEqual(self.patch('![Missing](/api/courses/images/999999/)').status_code, 400)
        self.assertEqual(self.patch('`![Example](/api/courses/images/999999/)`').status_code, 200)

    def test_new_course_cannot_reuse_another_course_image(self):
        image = self.image()
        response = self.client.post('/api/courses/teacher/', json.dumps({
            'title': 'New course', 'description': self.source(image)}), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Course.objects.filter(title='New course').exists())

    def test_removing_reference_hides_image_and_keeps_description_text(self):
        image = self.image()
        self.public(self.source(image))
        self.assertEqual(self.patch('Updated original text with `Python`').status_code, 200)
        self.client.logout()
        self.assertEqual(self.client.get(image['url']).status_code, 404)
        self.course.refresh_from_db()
        self.assertEqual(self.course.description, 'Updated original text with `Python`')

    def test_course_copy_rewrites_image_ids_and_last_reference_owns_file_cleanup(self):
        image = self.image()
        self.assertEqual(self.patch(self.source(image)).status_code, 200)
        response = self.client.post(f'/api/workspace/courses/{self.course.id}/clone/',
            json.dumps({'title': 'Illustrated copy'}), content_type='application/json')
        self.assertEqual(response.status_code, 201, response.content)
        copied = Course.objects.get(pk=response.json()['course_id'])
        copied_image = copied.description_images.get()
        self.assertIn(f'/api/courses/images/{copied_image.id}/', copied.description)
        self.assertNotIn(image['url'], copied.description)
        self.course.refresh_from_db()
        self.assertEqual(self.course.description, self.source(image))
        path = Path(copied_image.file.path)
        with self.captureOnCommitCallbacks(execute=True):
            self.course.delete()
        self.assertTrue(path.exists(), 'Deleting the source must not break its copied image')
        response = self.client.get(f'/api/courses/images/{copied_image.id}/')
        self.assertEqual(response.status_code, 200)
        b''.join(response.streaming_content)
        with self.captureOnCommitCallbacks(execute=True):
            copied.delete()
        self.assertFalse(path.exists())

    def test_missing_physical_image_returns_not_found(self):
        image = self.image()
        row = CourseImage.objects.get(pk=image['id'])
        row.file.storage.delete(row.file.name)
        self.assertEqual(self.client.get(image['url']).status_code, 404)
