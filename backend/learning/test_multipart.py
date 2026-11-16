import json
from unittest.mock import Mock, patch
from django.test import TestCase, override_settings
from accounts.models import User
from courses.models import Course
from .models import Lesson, MediaUpload
from .multipart import PART_SIZE, assemble
from common import ApiError


@override_settings(MEDIA_STORAGE_MODE='s3', MEDIA_S3_BUCKET='test-bucket', MEDIA_MULTIPART_ENABLED=True)
class MultipartTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create(username='multipart-teacher', role='teacher')
        self.other = User.objects.create(username='multipart-other', role='teacher')
        self.course = Course.objects.create(title='Video', teacher=self.teacher)
        self.lesson = Lesson.objects.create(course=self.course, title='Video')
        self.s3 = Mock()
        self.s3.create_multipart_upload.return_value = {'UploadId': 'test-upload-id'}
        self.s3.generate_presigned_url.return_value = 'https://example.test/part'
        self.s3.get_paginator.return_value.paginate.return_value = [{'Parts': []}]
        patched = patch('learning.media_views.client', return_value=self.s3)
        patched.start(); self.addCleanup(patched.stop)
        self.client.force_login(self.teacher)

    def start(self, fingerprint='a'*64):
        return self.client.post(f'/api/media/lessons/{self.lesson.id}/uploads/', json.dumps({
            'filename': 'movie.mp4', 'size': PART_SIZE+50, 'multipart': True, 'fingerprint': fingerprint}), content_type='application/json')

    def test_resume_same_file_and_new_session_for_changed_content(self):
        a = self.start(); b = self.start()
        self.assertEqual(a.status_code, 201)
        self.assertEqual(a.json()['id'], b.json()['id'])
        self.assertNotEqual(a.json()['id'], self.start('b'*64).json()['id'])
        self.assertEqual(self.s3.create_multipart_upload.call_count, 2)

    def test_owner_and_course_permissions_are_rechecked(self):
        uid = self.start().json()['id']
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(f'/api/media/uploads/{uid}/parts/').status_code, 404)
        self.client.force_login(self.teacher)
        self.course.teacher = self.other; self.course.save()
        self.assertEqual(self.client.get(f'/api/media/uploads/{uid}/parts/').status_code, 403)

    def test_part_numbers_and_lengths_are_bound_in_signature(self):
        uid = self.start().json()['id']
        path = f'/api/media/uploads/{uid}/parts/'
        for number in [0, 3, True]:
            self.assertEqual(self.client.post(path, json.dumps({'number': number}), content_type='application/json').status_code, 400)
        self.assertEqual(self.client.post(path, '{"number":2}', content_type='application/json').status_code, 200)
        self.assertEqual(self.s3.generate_presigned_url.call_args.kwargs['Params']['ContentLength'], 50)

    def test_incomplete_upload_is_preserved(self):
        uid = self.start().json()['id']
        response = self.client.post(f'/api/media/uploads/{uid}/complete/', '{}', content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.s3.abort_multipart_upload.assert_not_called()
        self.assertEqual(MediaUpload.objects.get(pk=uid).state, 'pending')

    def test_assembly_uses_s3_parts_and_checks_sizes(self):
        uid = self.start().json()['id']; upload = MediaUpload.objects.get(pk=uid)
        parts = [{'PartNumber': 1, 'Size': PART_SIZE, 'ETag': 'one'}, {'PartNumber': 2, 'Size': 50, 'ETag': 'two'}]
        self.s3.get_paginator.return_value.paginate.return_value = [{'Parts': parts}]
        assemble(self.s3, upload)
        self.assertEqual(self.s3.complete_multipart_upload.call_args.kwargs['MultipartUpload']['Parts'], [{'PartNumber': 1, 'ETag': 'one'}, {'PartNumber': 2, 'ETag': 'two'}])
        parts[1]['Size'] = 51
        with self.assertRaises(ApiError): assemble(self.s3, upload)

    def test_abort_and_expiry_cannot_issue_more_signed_parts(self):
        uid = self.start().json()['id']
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(f'/api/media/uploads/{uid}/abort/', '{}', content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.s3.abort_multipart_upload.assert_called_once()
        self.assertEqual(self.client.get(f'/api/media/uploads/{uid}/parts/').status_code, 409)
