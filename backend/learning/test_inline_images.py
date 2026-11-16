import base64
import json
import tempfile
from io import BytesIO
from datetime import timedelta
from pathlib import Path

from PIL import Image

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone

from courses.models import Course, CourseRun, Enrollment
from .models import Lesson, LessonMaterial, Module, Step


PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=')


class InlineImageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user(username='image_owner', role='teacher')
        cls.other = User.objects.create_user(username='image_other', role='teacher')
        cls.student = User.objects.create_user(username='image_student')
        cls.peer = User.objects.create_user(username='image_peer')
        cls.course = Course.objects.create(teacher=cls.owner, title='Images', is_published=True)
        cls.cohort = CourseRun.objects.create(course=cls.course, title='A', kind='cohort')
        cls.other_cohort = CourseRun.objects.create(course=cls.course, title='B', kind='cohort')
        Enrollment.objects.create(course=cls.course, run=cls.cohort, student=cls.student)
        Enrollment.objects.create(course=cls.course, run=cls.other_cohort, student=cls.peer)
        cls.module = Module.objects.create(course=cls.course, title='Module', is_published=True)
        cls.lesson = Lesson.objects.create(course=cls.course, module=cls.module, title='Lesson', is_published=True)
        cls.step = Step.objects.create(lesson=cls.lesson, title='Theory', is_published=True)

    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.settings = override_settings(MEDIA_ROOT=self.media.name)
        self.settings.enable()
        self.addCleanup(self.settings.disable)
        self.addCleanup(self.media.cleanup)

    def upload(self, *, content=PNG, name='example.png', user=None, lesson=None):
        self.client.force_login(user or self.owner)
        return self.client.post(f'/api/learning/teacher/lessons/{(lesson or self.lesson).id}/images/',
            {'file': SimpleUploadedFile(name, content), 'title': 'Addition example'})

    def image(self):
        response = self.upload()
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()['image']

    def source(self, image):
        return f"## Example\n\n![Addition]({image['url']})\n\nUse `print()` and Python."

    def get_image(self, image, *, user=None, legacy=False, cohort=None):
        self.client.force_login(user or self.student)
        path = f"/api/learning/materials/{image['id']}/open/" if legacy else image['url']
        return self.client.get(f'{path}?run_id={(cohort or self.cohort).id}')

    def test_upload_creates_private_illustration_without_extra_file_step(self):
        count = self.lesson.steps.count()
        image = self.image()
        material = LessonMaterial.objects.get(pk=image['id'])
        self.assertTrue(material.is_inline)
        self.assertEqual(self.lesson.steps.count(), count)
        self.assertEqual(material.title, 'Addition example')
        self.assertTrue(Path(material.file.path).is_file())
        response = self.get_image(image, user=self.owner)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), PNG)

    def test_students_and_foreign_teachers_cannot_upload(self):
        for user in [self.student, self.other]:
            self.assertEqual(self.upload(user=user).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.post(f'/api/learning/teacher/lessons/{self.lesson.id}/images/', {'file': SimpleUploadedFile('x.png', PNG)}).status_code, 401)
        self.assertFalse(LessonMaterial.objects.exists())

    def test_invalid_file_types_sizes_and_headers_are_rejected(self):
        for name, content in [('x.svg', b'<svg/>'), ('x.png', b'<script>alert(1)</script>'), ('x.png', PNG[:40]), ('x.png', b''), ('x.jpg', PNG), ('x.png', b'a' * (8 * 1024 * 1024 + 1))]:
            with self.subTest(name=name, length=len(content)):
                self.assertEqual(self.upload(name=name, content=content).status_code, 400)
        self.assertFalse(LessonMaterial.objects.exists())

    def test_valid_jpeg_and_pixel_limit(self):
        buffer = BytesIO()
        Image.new('RGB', (20, 20), 'white').save(buffer, format='JPEG')
        self.assertEqual(self.upload(name='photo.jpg', content=buffer.getvalue()).status_code, 201)
        buffer = BytesIO()
        Image.new('1', (5000, 4000)).save(buffer, format='PNG')
        self.assertEqual(self.upload(name='oversized.png', content=buffer.getvalue()).status_code, 400)

    def test_draft_image_cannot_be_read_through_new_or_legacy_route(self):
        image = self.image()
        for legacy in [False, True]:
            self.assertEqual(self.get_image(image, legacy=legacy).status_code, 404)
        self.step.content = self.source(image)
        self.step.is_published = False
        self.step.save()
        self.assertEqual(self.get_image(image).status_code, 404)

    def test_visible_image_is_inline_private_and_uses_lesson_group_permissions(self):
        image = self.image()
        self.step.content = self.source(image)
        self.step.save()
        for legacy in [False, True]:
            response = self.get_image(image, legacy=legacy)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Content-Type'], 'image/png')
            self.assertEqual(response['Cache-Control'], 'private, no-store')
            self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
            self.assertNotIn('attachment', response.get('Content-Disposition', ''))
            self.assertEqual(b''.join(response.streaming_content), PNG)
        self.assertEqual(self.get_image(image, user=self.peer).status_code, 403)
        self.assertEqual(self.get_image(image, user=self.other).status_code, 403)

    def test_scheduled_module_and_unpublished_course_still_protect_images(self):
        image = self.image()
        self.step.content = self.source(image)
        self.step.save()
        self.module.opens_at = timezone.now() + timedelta(days=1)
        self.module.save()
        self.assertEqual(self.get_image(image).status_code, 403)
        self.course.is_published = False
        self.course.save()
        self.assertEqual(self.get_image(image).status_code, 403)

    def test_plain_url_does_not_publish_a_draft_illustration(self):
        image = self.image()
        self.step.content = f"Unpublished picture: {image['url']}"
        self.step.save()
        self.assertEqual(self.get_image(image).status_code, 404)

    def test_code_examples_neither_validate_nor_publish_image_references(self):
        image = self.image()
        self.client.force_login(self.owner)
        code = f"```python\n![Example]({image['url']})\n```\n\n`![example](/api/learning/images/999999/)`"
        response = self.client.patch(f'/api/learning/steps/{self.step.id}/?run_id={self.cohort.id}', json.dumps({'content': code}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.step.refresh_from_db()
        self.assertEqual(self.step.content, code)
        self.assertEqual(self.get_image(image).status_code, 404)

    def test_step_content_rejects_images_from_other_lessons(self):
        image = self.image()
        other_lesson = Lesson.objects.create(course=self.course, module=self.module, title='Other', position=2, is_published=True)
        self.client.force_login(self.owner)
        payload = {'title': 'Wrong picture', 'kind': 'text', 'content': self.source(image)}
        response = self.client.post(f'/api/learning/lessons/{other_lesson.id}/steps/', json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        response = self.client.patch(f'/api/learning/steps/{self.step.id}/?run_id={self.cohort.id}', json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.step.refresh_from_db()
        self.assertEqual(self.step.content, payload['content'])

    def test_inline_illustrations_do_not_appear_as_file_choices(self):
        image = self.image()
        self.client.force_login(self.owner)
        data = self.client.get(f'/api/learning/courses/{self.course.id}/lessons/?run_id={self.cohort.id}').json()
        self.assertEqual(data['lessons'][0]['materials'], [])
        response = self.client.post(f'/api/learning/lessons/{self.lesson.id}/steps/', json.dumps({'title': 'Not a file step', 'kind': 'file', 'material_id': image['id']}), content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_course_copy_rewrites_image_references_and_preserves_original(self):
        image = self.image()
        self.step.content = self.source(image)
        self.step.save()
        self.lesson.content = self.source(image)
        self.lesson.save()
        self.client.force_login(self.owner)
        response = self.client.post(f'/api/workspace/courses/{self.course.id}/clone/', json.dumps({'title': 'Image course copy'}), content_type='application/json')
        self.assertEqual(response.status_code, 201, response.content)
        target = Course.objects.get(pk=response.json()['course_id'])
        copied_image = LessonMaterial.objects.get(lesson__course=target)
        self.assertTrue(copied_image.is_inline)
        copied_step = Step.objects.get(lesson__course=target)
        self.assertIn(f'/api/learning/images/{copied_image.id}/', copied_step.content)
        self.assertNotIn(image['url'], copied_step.content)
        self.assertEqual(target.lessons.get().content, copied_step.content)
        self.step.refresh_from_db()
        self.assertEqual(self.step.content, self.source(image))
