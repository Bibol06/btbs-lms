"""Explicit live S3 transfer check with synthetic bytes and a disposable database."""
import os, json, hashlib, urllib.request
from datetime import datetime
from pathlib import Path
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.conf import settings
from django.db import connection, connections
from django.test import Client
from learning.models import Lesson, MediaUpload, LessonMaterial
from learning.media_views import client, delete_staging
from courses.models import Course
from accounts.models import User

settings.MEDIA_MULTIPART_ENABLED = True
settings.ALLOWED_HOSTS = ['testserver']
settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
original = connection.settings_dict['NAME']
name = 'test_btbs_media_' + datetime.now().strftime('%Y%m%d%H%M%S')
connection.settings_dict['TEST']['NAME'] = name
created = False
report = {'kind': 'Synthetic MP4-signature bytes; transfer/resume test, not playback', 'ok': False}
try:
    connection.creation.create_test_db(verbosity=0, autoclobber=False, serialize=False); created = True
    owner = User.objects.create(username='s3-smoke-owner', role='teacher')
    course = Course.objects.create(title='Disposable S3 transfer check', teacher=owner, is_published=False)
    lesson = Lesson.objects.create(course=course, title='Disposable upload', is_published=False)
    browser = Client(); browser.force_login(owner)
    payload = b'\x00\x00\x00\x18ftypmp42' + b'\x00'*(21*1024*1024-12)
    fingerprint = hashlib.sha256(payload).hexdigest()
    data = {'filename':'btbs-transfer-check.mp4','size':len(payload),'multipart':True,'fingerprint':fingerprint}
    def post(path, data):
        response = browser.post(path, json.dumps(data), content_type='application/json')
        if response.status_code >= 400: raise RuntimeError(f'API {response.status_code}: {response.json().get("error", "failed")}')
        return response.json()
    started = post(f'/api/media/lessons/{lesson.id}/uploads/', data)
    uid, part_size = started['id'], started['part_size']
    base = f'/api/media/uploads/{uid}'
    def part(number):
        chunk = payload[(number-1)*part_size:number*part_size]
        signed = post(base+'/parts/', {'number':number})['url']
        req = urllib.request.Request(signed, data=chunk, method='PUT', headers={'Content-Length':str(len(chunk))})
        with urllib.request.urlopen(req, timeout=90) as response: assert response.status == 200
    part(1)
    resumed = post(f'/api/media/lessons/{lesson.id}/uploads/', data)
    assert resumed['id'] == uid
    assert browser.get(base+'/parts/').json()['parts'] == [{'number':1,'size':part_size}]
    incomplete = browser.post(base+'/complete/', '{}', content_type='application/json')
    assert incomplete.status_code == 400
    for number in range(2, (len(payload)+part_size-1)//part_size+1): part(number)
    result = post(base+'/complete/', {})
    item = LessonMaterial.objects.get(pk=result['material']['id'])
    s3 = client(); stream = s3.get_object(Bucket=settings.MEDIA_S3_BUCKET, Key=item.file.name)['Body']
    sha = hashlib.sha256()
    try:
        while chunk := stream.read(1024*1024): sha.update(chunk)
    finally: stream.close()
    assert sha.hexdigest() == fingerprint
    report.update(ok=True, bytes=len(payload), parts=3, resumed=True, rejected_incomplete=True, sha256_verified=True)
    print('Live multipart: uploaded first part, resumed same session, completed and SHA256 verified.', flush=True)
finally:
    if created:
        for upload in MediaUpload.objects.all(): delete_staging(upload)
        for item in LessonMaterial.objects.exclude(file=''):
            if item.file.name.startswith('_s3/'):
                client().delete_object(Bucket=settings.MEDIA_S3_BUCKET, Key=item.file.name)
        connections.close_all()
        connection.creation.destroy_test_db(original, verbosity=0)
        report['temporary_database_removed'] = True
    Path(__file__).resolve().parents[1].joinpath('.local/live-multipart-report.json').write_text(json.dumps(report,indent=2))
