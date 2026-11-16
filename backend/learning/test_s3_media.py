import json
import tempfile
from datetime import timedelta
from io import BytesIO
from unittest.mock import Mock, PropertyMock, patch
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.test import TestCase, SimpleTestCase, override_settings
from django.utils import timezone
from courses.models import Course, CourseRun, Enrollment
from media_storage import HybridMediaStorage
from .models import Lesson, Module, LessonMaterial, MediaUpload, Step, StorageDeletion

VIDEO = b'\x00\x00\x00\x18ftypisom\x00\x00\x00\x00example'


@override_settings(MEDIA_S3_BUCKET='test-private-bucket',MEDIA_S3_REGION='eu-north-1',MEDIA_S3_ENDPOINT='',
                   MEDIA_S3_ACCESS_KEY='test-access-key',MEDIA_S3_SECRET_KEY='test-secret-key',MEDIA_S3_ADDRESSING_STYLE='auto')
class S3SigningTests(SimpleTestCase):
    def test_download_and_post_signatures_use_regional_endpoint_without_redirects(self):
        from urllib.parse import urlsplit,parse_qs
        from media_storage import s3_backend
        storage=s3_backend()
        signed=storage.url('_s3/example.mp4')
        self.assertIn(urlsplit(signed).hostname,['s3.eu-north-1.amazonaws.com','test-private-bucket.s3.eu-north-1.amazonaws.com'])
        self.assertTrue(urlsplit(signed).path.endswith('/_s3/example.mp4'))
        query=parse_qs(urlsplit(signed).query)
        self.assertEqual(query['X-Amz-Algorithm'],['AWS4-HMAC-SHA256'])
        self.assertTrue(query['X-Amz-Credential'][0].endswith('/eu-north-1/s3/aws4_request'))
        post=storage.connection.meta.client.generate_presigned_post(Bucket='test-private-bucket',Key='_staging/example.mp4')
        self.assertIn(urlsplit(post['url']).hostname,['s3.eu-north-1.amazonaws.com','test-private-bucket.s3.eu-north-1.amazonaws.com'])


@override_settings(MEDIA_STORAGE_MODE='s3', MEDIA_S3_BUCKET='private-lms')
class S3MediaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User=get_user_model()
        cls.teacher=User.objects.create_user(username='s3_owner',role='teacher')
        cls.other=User.objects.create_user(username='s3_other',role='teacher')
        cls.student=User.objects.create_user(username='s3_student')
        cls.course=Course.objects.create(teacher=cls.teacher,title='Media',is_published=True)
        cls.cohort=CourseRun.objects.create(course=cls.course,title='Group',kind='cohort')
        Enrollment.objects.create(course=cls.course,run=cls.cohort,student=cls.student)
        cls.module=Module.objects.create(course=cls.course,title='Module',is_published=True)
        cls.lesson=Lesson.objects.create(course=cls.course,module=cls.module,title='Lesson',is_published=True)

    def setUp(self):
        self.s3=Mock()
        self.s3.generate_presigned_post.side_effect=lambda **kw: {'url':'https://private-storage.example/upload','fields':{'key':kw['Key']}}
        self.s3.head_object.return_value={'ContentLength':len(VIDEO),'ContentType':'video/mp4','ETag':'"etag1"'}
        self.s3.get_object.side_effect=lambda **kw: {'Body':BytesIO(VIDEO[:16])}
        p=patch('learning.media_views.client',return_value=self.s3);p.start();self.addCleanup(p.stop)
        self.client.force_login(self.teacher)

    def start(self,user=None):
        if user:self.client.force_login(user)
        return self.client.post(f'/api/media/lessons/{self.lesson.id}/uploads/',json.dumps({'filename':'Lecture.mp4','size':len(VIDEO),'title':'Lecture'}),content_type='application/json')

    def finish(self,uid):
        return self.client.post(f'/api/media/uploads/{uid}/complete/','{}',content_type='application/json')

    def test_presigned_upload_is_scoped_and_size_limited(self):
        response=self.start();self.assertEqual(response.status_code,201,response.content)
        upload=MediaUpload.objects.get(id=response.json()['id'])
        call=self.s3.generate_presigned_post.call_args.kwargs
        self.assertTrue(call['Key'].startswith('_staging/'))
        self.assertTrue(call['Key'].startswith(f'_staging/courses/course-{self.course.id}/lessons/lesson-{self.lesson.id}/'))
        self.assertIn(['content-length-range',len(VIDEO),len(VIDEO)],call['Conditions'])
        self.assertEqual(upload.owner,self.teacher)
        self.assertEqual(response.json()['upload']['url'],'https://private-storage.example/upload')

    def test_student_and_foreign_teacher_cannot_get_upload_permission(self):
        for user in [self.student,self.other]:
            self.assertEqual(self.start(user).status_code,403)
        self.assertFalse(MediaUpload.objects.exists())

    def test_completion_validates_and_copies_to_a_distinct_immutable_key(self):
        uid=self.start().json()['id']
        response=self.finish(uid);self.assertEqual(response.status_code,201,response.content)
        row=MediaUpload.objects.get(pk=uid)
        self.assertEqual(row.state,'complete');self.assertTrue(row.material.file.name.startswith('_s3/'))
        self.assertNotEqual(row.staging_key,row.material.file.name)
        self.assertTrue(row.material.file.name.startswith(f'_s3/courses/course-{self.course.id}/lessons/lesson-{self.lesson.id}/videos/'))
        copy=self.s3.copy_object.call_args.kwargs
        self.assertEqual(copy['CopySourceIfMatch'],'"etag1"')
        self.assertEqual(copy['ContentType'],'video/mp4')
        self.assertTrue(Step.objects.filter(material=row.material).exists())
        self.assertEqual(self.finish(uid).status_code,200)
        self.assertEqual(self.s3.copy_object.call_count,1)

    def test_wrong_size_mime_or_signature_never_creates_material(self):
        for change in [{'ContentLength':99},{'ContentType':'text/html'},None]:
            uid=self.start().json()['id']
            self.s3.head_object.return_value={'ContentLength':len(VIDEO),'ContentType':'video/mp4','ETag':'"etag1"',**(change or {})}
            self.s3.get_object.side_effect=lambda **kw: {'Body':BytesIO(b'<script>evil</sc>')}
            self.assertEqual(self.finish(uid).status_code,400)
            self.assertFalse(LessonMaterial.objects.exists())
        self.s3.copy_object.assert_not_called()

    def test_another_account_cannot_finalize_and_revoked_editor_cannot_attach(self):
        uid=self.start().json()['id'];self.client.force_login(self.other)
        self.assertEqual(self.finish(uid).status_code,404)
        self.client.force_login(self.teacher)
        self.course.teacher=self.other;self.course.save(update_fields=['teacher'])
        self.assertEqual(self.finish(uid).status_code,403)

    def test_expiry_and_cancellation_do_not_publish_anything(self):
        uid=self.start().json()['id'];MediaUpload.objects.filter(pk=uid).update(expires_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(self.finish(uid).status_code,400)
        uid=self.start().json()['id']
        with self.captureOnCommitCallbacks(execute=True):
            response=self.client.post(f'/api/media/uploads/{uid}/abort/','{}',content_type='application/json')
        self.assertEqual(response.status_code,200);self.assertEqual(self.finish(uid).status_code,400)
        self.assertFalse(LessonMaterial.objects.exists())

    def test_signed_playback_requires_enrollment_and_open_module(self):
        material=LessonMaterial.objects.create(lesson=self.lesson,title='Video',file='_s3/lesson_materials/video.mp4')
        backend=Mock();backend.url.return_value='https://private-storage.example/signed?token=temporary'
        with patch.object(HybridMediaStorage,'remote',new_callable=PropertyMock,return_value=backend):
            self.client.force_login(self.other)
            self.assertEqual(self.client.get(f'/api/learning/materials/{material.id}/open/?run_id={self.cohort.id}').status_code,403)
            self.client.force_login(self.student);self.module.opens_at=timezone.now()+timedelta(days=1);self.module.save()
            self.assertEqual(self.client.get(f'/api/learning/materials/{material.id}/open/?run_id={self.cohort.id}').status_code,403)
            backend.url.assert_not_called()
            self.module.opens_at=None;self.module.save()
            response=self.client.get(f'/api/learning/materials/{material.id}/open/?run_id={self.cohort.id}')
            self.assertEqual(response.status_code,302);self.assertEqual(response['Cache-Control'],'private, no-store')
            self.assertEqual(backend.url.call_args.kwargs['expire'],3600)

    @override_settings(MEDIA_STORAGE_MODE='local')
    def test_without_s3_ordinary_upload_mode_remains_available(self):
        response=self.client.get('/api/media/config/').json()
        self.assertFalse(response['direct_upload']);self.assertEqual(response['video_limit_mb'],100)
        self.assertEqual(self.start().status_code,409)

    def test_oversized_or_unsupported_direct_upload_is_rejected(self):
        for name,size in [('evil.html',30),('big.mp4',3*1024**3),('empty.mp4',0)]:
            response=self.client.post(f'/api/media/lessons/{self.lesson.id}/uploads/',json.dumps({'filename':name,'size':size}),content_type='application/json')
            self.assertEqual(response.status_code,400)

    def test_hybrid_storage_keeps_local_originals_readable_when_s3_enabled(self):
        with tempfile.TemporaryDirectory() as folder:
            local=FileSystemStorage(location=folder+'/local');remote=FileSystemStorage(location=folder+'/remote')
            local.save('old.pdf',ContentFile(b'old'))
            storage=HybridMediaStorage();storage.__dict__.update(local=local,remote=remote)
            name=storage.save('lesson_materials/new.mp4',ContentFile(VIDEO))
            self.assertTrue(name.startswith('_s3/'))
            self.assertEqual(storage.open('old.pdf').read(),b'old')
            self.assertEqual(storage.open(name).read(),VIDEO)

    def test_failed_physical_deletion_is_queued_for_retry(self):
        from file_cleanup import delete_unreferenced
        storage=Mock();storage.delete.side_effect=OSError('offline')
        delete_unreferenced(storage,'_s3/not-referenced.mp4')
        self.assertEqual(StorageDeletion.objects.get().attempts,1)
        storage.delete.side_effect=None;delete_unreferenced(storage,'_s3/not-referenced.mp4')
        self.assertFalse(StorageDeletion.objects.exists())

    def test_cleanup_removes_expired_upload_session_but_keeps_published_material(self):
        from django.core.management import call_command
        uid=self.start().json()['id']; self.assertEqual(self.finish(uid).status_code,201)
        upload=MediaUpload.objects.get(pk=uid); material_id=upload.material_id
        MediaUpload.objects.filter(pk=uid).update(expires_at=timezone.now()-timedelta(hours=1))
        call_command('cleanup_media_uploads',stdout=__import__('io').StringIO())
        self.assertFalse(MediaUpload.objects.filter(pk=uid).exists())
        self.assertTrue(LessonMaterial.objects.filter(pk=material_id).exists())
        self.s3.delete_object.assert_called_with(Bucket='private-lms',Key=upload.staging_key)
