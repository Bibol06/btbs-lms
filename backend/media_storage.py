"""Private S3 objects alongside pre-existing local files during migration."""
from pathlib import PurePosixPath
from uuid import uuid4
from media_paths import REMOTE_PREFIX
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.files.storage import Storage, FileSystemStorage
from django.utils.functional import cached_property

def s3_options():
    if not settings.MEDIA_S3_BUCKET:
        raise ImproperlyConfigured('Укажите MEDIA_S3_BUCKET перед подключением S3')
    region = settings.MEDIA_S3_REGION or 'us-east-1'
    # Pin the AWS endpoint as well as the signing region. The SDK's legacy
    # presigner can otherwise select s3.amazonaws.com and receive a regional
    # redirect, which invalidates the signed Host header (e.g. in eu-north-1).
    suffix = 'amazonaws.com.cn' if region.startswith('cn-') else 'amazonaws.com'
    endpoint = settings.MEDIA_S3_ENDPOINT or f'https://s3.{region}.{suffix}'
    return {'bucket_name': settings.MEDIA_S3_BUCKET, 'region_name': region,
        'endpoint_url': endpoint,
        'access_key': settings.MEDIA_S3_ACCESS_KEY or None, 'secret_key': settings.MEDIA_S3_SECRET_KEY or None,
        'default_acl': None, 'querystring_auth': True, 'querystring_expire': 600,
        'signature_version': 's3v4', 'addressing_style': settings.MEDIA_S3_ADDRESSING_STYLE,
        'file_overwrite': False, 'custom_domain': None}


def s3_backend():
    from storages.backends.s3 import S3Storage
    return S3Storage(**s3_options())


class HybridMediaStorage(Storage):
    @cached_property
    def local(self):
        return FileSystemStorage()

    @cached_property
    def remote(self):
        return s3_backend()

    @staticmethod
    def is_remote(name):
        return str(name).startswith(REMOTE_PREFIX)

    def backend(self, name):
        return self.remote if self.is_remote(name) else self.local

    def _open(self, name, mode='rb'):
        return self.backend(name).open(name, mode)

    def _save(self, name, content):
        if settings.MEDIA_STORAGE_MODE == 's3':
            # upload_to already owns the course/lesson namespace and UUID.
            if name.startswith('courses/course-'):
                return self.remote.save(REMOTE_PREFIX + name, content)
            original = PurePosixPath(name)
            key = f'{REMOTE_PREFIX}{original.parent}/{uuid4().hex}{original.suffix.lower()}'
            return self.remote.save(key, content)
        return self.local.save(name, content)

    def exists(self, name):
        return self.backend(name).exists(name)

    def size(self, name):
        return self.backend(name).size(name)

    def delete(self, name):
        return self.backend(name).delete(name)

    def path(self, name):
        return self.backend(name).path(name)

    def url(self, name):
        return self.backend(name).url(name)

    def get_modified_time(self, name):
        return self.backend(name).get_modified_time(name)


def private_file_response(field, *, content_type=None, filename=None, attachment=False):
    """Call only after the application has checked membership and release dates."""
    from pathlib import Path
    from django.http import FileResponse, HttpResponseRedirect
    from common import ApiError
    name = field.name
    if name.startswith(REMOTE_PREFIX):
        storage = field.storage
        from urllib.parse import quote
        disposition = ('attachment' if attachment else 'inline') + "; filename*=UTF-8''" + quote(filename or Path(name).name)
        try:
            from cdn import signed_media_url
            lifetime = 3600 if name.lower().endswith(('.mp4', '.webm')) else 600
            url = signed_media_url(name, lifetime) or storage.remote.url(name, expire=lifetime,
                parameters={'ResponseContentDisposition': disposition, **({'ResponseContentType': content_type} if content_type else {})})
        except Exception:
            raise ApiError('Хранилище временно недоступно. Обратитесь к системному администратору.', 503)
        response = HttpResponseRedirect(url)
    else:
        try:
            opened = field.open('rb')
        except (OSError, ValueError):
            raise ApiError('Файл не найден на сервере', 404)
        response = FileResponse(opened, content_type=content_type, as_attachment=attachment, filename=filename)
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response
