"""Read-only deployed CDN check. Never print signed URLs or file contents."""
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from cdn import signed_media_url
from learning.models import LessonMaterial

item = LessonMaterial.objects.filter(file__startswith='_s3/').first()
if item is None:
    raise RuntimeError('No stored lesson material available for CDN verification')
signed = signed_media_url(item.file.name)
if not signed:
    raise RuntimeError('CDN is disabled')

def status(url, headers=None):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=30) as response:
            return response.status, len(response.read(16))
    except urllib.error.HTTPError as error:
        code = error.code
        error.close()
        return code, 0

full, _ = status(signed)
unsigned, _ = status(signed.split('?', 1)[0])
partial, size = status(signed, {'Range': 'bytes=0-15'})
result = {'signed_status': full, 'unsigned_status': unsigned, 'range_status': partial, 'range_bytes': size}
assert (full, unsigned, partial, size) == (200, 403, 206, 16), result
print(json.dumps(result))
