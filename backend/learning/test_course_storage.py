import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, PropertyMock, patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings

from common import ApiError
from courses.models import Course, CourseImage, Enrollment
from assessment.models import Assignment, Submission
from learning.models import Lesson, LessonMaterial
from media_paths import course_media_upload_to, media_directory
from media_storage import HybridMediaStorage


def contents(field):
    with field.open('rb') as stream:
        return stream.read()


class CoursePathsTests(SimpleTestCase):
    def test_paths_have_stable_ownership_no_user_supplied_directories_or_titles(self):
        course = Course(id=12, title='Python / ../ unsafe name')
        lesson = Lesson(id=45, course=course)
        material = LessonMaterial(lesson=lesson)
        path = course_media_upload_to(material, r'..\another-course\Video.MP4')
        self.assertRegex(path, r'^courses/course-12/lessons/lesson-45/videos/[a-f0-9]{32}\.mp4$')
        before = media_directory(material, 'video.mp4')
        course.title = 'Renamed'; lesson.title = 'Moved'; lesson.position = 88
        self.assertEqual(media_directory(material, 'video.mp4'), before)
        material.is_inline = True
        self.assertIn('/images/', course_media_upload_to(material, 'picture.png'))
        self.assertEqual(media_directory(CourseImage(course=course), 'pic.png'), 'courses/course-12/images/')

    def test_answers_are_separated_by_course_group_assignment_enrollment_and_attempt(self):
        assignment = Assignment(id=5, course_id=12)
        enrollment = Enrollment(id=7, course_id=12, run_id=9, student_id=100)
        answer = Submission(assignment=assignment, enrollment=enrollment, attempt_no=2)
        key = course_media_upload_to(answer, 'answer.pdf')
        self.assertTrue(key.startswith('courses/course-12/groups/run-9/assignments/assignment-5/answers/enrollment-7/attempt-2/'))
        self.assertLess(len(key), Submission._meta.get_field('file').max_length)
        answer.attempt_no = 3
        self.assertNotEqual(media_directory(answer, 'answer.pdf'), str(Path(key).parent).replace('\\', '/') + '/')


@override_settings(MEDIA_STORAGE_MODE='s3', MEDIA_S3_BUCKET='test-course-media')
class CourseStorageTests(TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(); self.addCleanup(self.directory.cleanup)
        self.remote = FileSystemStorage(location=self.directory.name + '/remote')
        self.local = FileSystemStorage(location=self.directory.name + '/local')
        for attr, storage in [('remote', self.remote), ('local', self.local)]:
            p = patch.object(HybridMediaStorage, attr, new_callable=PropertyMock, return_value=storage)
            p.start(); self.addCleanup(p.stop)
        self.client_s3 = Mock()
        self.client_s3.head_object.side_effect = lambda **kw: {'ContentLength': self.remote.size(kw['Key']), 'ETag': '"original"'}

        def copy(**kw):
            with self.remote.open(kw['CopySource']['Key'], 'rb') as source:
                self.remote.save(kw['Key'], source)
        self.client_s3.copy_object.side_effect = copy
        self.client_s3.upload_fileobj.side_effect = lambda stream, bucket, key, **kw: self.remote.save(key, stream)
        backend = Mock(); backend.connection.meta.client = self.client_s3
        p = patch('course_media.s3_backend', return_value=backend); p.start(); self.addCleanup(p.stop)
        self.teacher = get_user_model().objects.create_user(username='course-storage-teacher', role='teacher')
        self.course = Course.objects.create(title='Source', teacher=self.teacher)
        self.lesson = Lesson.objects.create(course=self.course, title='Lesson')
        self.client.force_login(self.teacher)

    def legacy_material(self):
        key = self.remote.save('_s3/migrated/video.mp4', ContentFile(b'original media'))
        return LessonMaterial.objects.create(lesson=self.lesson, title='Video', file=key)

    def run_organizer(self, report, **kwargs):
        call_command('organize_media_by_course', execute=True, report=str(report), stdout=StringIO(), **kwargs)

    def test_new_uploads_use_course_folder_and_never_overwrite_same_filename(self):
        first = LessonMaterial.objects.create(lesson=self.lesson, title='First', file=ContentFile(b'one', name='same.pdf'))
        second = LessonMaterial.objects.create(lesson=self.lesson, title='Second', file=ContentFile(b'two', name='same.pdf'))
        prefix = f'_s3/courses/course-{self.course.pk}/lessons/lesson-{self.lesson.pk}/materials/'
        self.assertTrue(first.file.name.startswith(prefix)); self.assertTrue(second.file.name.startswith(prefix))
        self.assertNotEqual(first.file.name, second.file.name)
        self.assertEqual(contents(first.file), b'one'); self.assertEqual(contents(second.file), b'two')

    def test_organizer_dry_run_and_idempotent_copy_keep_source_and_manifest(self):
        material = self.legacy_material(); original = material.file.name
        call_command('organize_media_by_course', stdout=StringIO())
        material.refresh_from_db(); self.assertEqual(material.file.name, original)
        report = Path(self.directory.name) / 'report.json'
        self.run_organizer(report)
        material.refresh_from_db(); self.assertIn(f'/course-{self.course.pk}/', material.file.name)
        self.assertTrue(self.remote.exists(original))
        self.assertEqual(contents(material.file), b'original media')
        row = json.loads(report.read_text(encoding='utf-8'))['files'][0]
        self.assertEqual((row['old'], row['new']), (original, material.file.name))
        self.assertEqual(self.client_s3.copy_object.call_args.kwargs['CopySourceIfMatch'], '"original"')
        self.run_organizer(Path(self.directory.name) / 'again.json')
        self.assertEqual(self.client_s3.copy_object.call_count, 1)
        with self.assertRaises(CommandError): self.run_organizer(report)

    def test_shared_legacy_image_is_split_into_independent_course_folders(self):
        key = self.remote.save('_s3/migrated/shared.png', ContentFile(b'image'))
        first = CourseImage.objects.create(course=self.course, title='First', file=key)
        other = Course.objects.create(title='Other', teacher=self.teacher)
        second = CourseImage.objects.create(course=other, title='Second', file=key)
        self.run_organizer(Path(self.directory.name) / 'images.json')
        first.refresh_from_db(); second.refresh_from_db()
        self.assertTrue(first.file.name.startswith(f'_s3/courses/course-{self.course.pk}/images/'))
        self.assertTrue(second.file.name.startswith(f'_s3/courses/course-{other.pk}/images/'))
        with self.captureOnCommitCallbacks(execute=True): self.course.delete()
        self.assertTrue(self.remote.exists(second.file.name)); self.assertTrue(self.remote.exists(key))

    def test_failed_copy_keeps_database_source_and_cleans_new_object(self):
        material = self.legacy_material(); old = material.file.name
        head = self.client_s3.head_object.side_effect
        self.client_s3.head_object.side_effect = lambda **kw: head(**kw) if kw['Key'] == old else {'ContentLength': 999}
        with self.assertRaises(ApiError): self.run_organizer(Path(self.directory.name) / 'failed.json')
        material.refresh_from_db(); self.assertEqual(material.file.name, old)
        target = self.client_s3.copy_object.call_args.kwargs['Key']
        self.assertFalse(self.remote.exists(target)); self.assertTrue(self.remote.exists(old))

    def test_cloning_s3_course_copies_assets_to_new_owner_folder(self):
        material = self.legacy_material(); old = material.file.name
        response = self.client.post(f'/api/workspace/courses/{self.course.pk}/clone/',
                                    json.dumps({'title': 'Copy'}), content_type='application/json')
        self.assertEqual(response.status_code, 201, response.content)
        target = Course.objects.get(pk=response.json()['course_id'])
        copied = LessonMaterial.objects.get(lesson__course=target)
        self.assertTrue(copied.file.name.startswith(f'_s3/courses/course-{target.pk}/'))
        self.assertNotEqual(copied.file.name, old)
        with self.captureOnCommitCallbacks(execute=True): self.course.delete()
        self.assertEqual(contents(copied.file), b'original media')

    def test_clone_rolls_back_database_and_cleans_copies_when_later_write_fails(self):
        self.legacy_material()
        with patch('workspace.author_views.audit', side_effect=RuntimeError('failure')):
            with self.assertRaises(RuntimeError):
                self.client.post(f'/api/workspace/courses/{self.course.pk}/clone/',
                                 json.dumps({'title': 'Failed copy'}), content_type='application/json')
        self.assertEqual(Course.objects.count(), 1)
        target = self.client_s3.copy_object.call_args.kwargs['Key']
        self.assertFalse(self.remote.exists(target))

    def test_local_migration_uses_same_layout_retains_local_original(self):
        original = self.local.save('lesson_materials/old.pdf', ContentFile(b'%PDF-original'))
        material = LessonMaterial.objects.create(lesson=self.lesson, title='Local', file=original)
        report = Path(self.directory.name) / 'local.json'
        call_command('migrate_media_to_s3', execute=True, report=str(report), stdout=StringIO())
        material.refresh_from_db()
        self.assertTrue(material.file.name.startswith(f'_s3/courses/course-{self.course.pk}/'))
        self.assertTrue(self.local.exists(original)); self.assertEqual(contents(material.file), b'%PDF-original')
