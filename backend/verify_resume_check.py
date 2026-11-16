"""Verify and remove only the two explicitly named November 15 UI test uploads."""
import hashlib
import json
import os
from pathlib import Path
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.conf import settings
from learning.models import MediaUpload, Step
from learning.media_views import client

names = ['resume-check.mp4', 'resume-check-large.mp4']
uploads = list(MediaUpload.objects.filter(lesson__course_id=8, filename__in=names))
assert len(uploads) == 2 and all(u.state == 'complete' and u.material_id for u in uploads)
large = next(u for u in uploads if u.filename == names[1])
assert str(large.id) == '1dd86813-1aa4-48c3-9649-974c61f8fa3a'
expected = hashlib.file_digest(Path('/tmp/resume-check-large.mp4').open('rb'), 'sha256').hexdigest()
s3 = client()
body = s3.get_object(Bucket=settings.MEDIA_S3_BUCKET, Key=large.material.file.name)['Body']
try:
    digest = hashlib.sha256()
    while chunk := body.read(1024 * 1024):
        digest.update(chunk)
finally:
    body.close()
assert digest.hexdigest() == expected
result = dict(ok=True, bytes=large.size, same_session=True, sha256_verified=True,
    browser_playback=True, duration_seconds=328.549297)
for upload in uploads:
    material = upload.material
    assert material.title.startswith(('Проверка продолжения видео', 'Проверка возобновления'))
    Step.objects.filter(material=material).delete()
    s3.delete_object(Bucket=settings.MEDIA_S3_BUCKET, Key=material.file.name)
    upload.delete()
    material.delete()
result['test_materials_removed'] = True
print(json.dumps(result))
