"""Copy course assets without making a second course depend on the first one."""
from contextlib import contextmanager
from pathlib import PurePosixPath
from django.conf import settings
from django.core.files.storage import default_storage
from media_paths import REMOTE_PREFIX, remote_media_key
from media_storage import s3_backend


@contextmanager
def copied_course_files():
    """Wrap the DB transaction too, so rollback removes only new, unused objects."""
    created = []

    def perform_copy(source, target):
        if not source:
            return ''
        if not source.name.startswith(REMOTE_PREFIX) and settings.MEDIA_STORAGE_MODE != 's3':
            # Legacy local clones keep sharing their immutable files until migrated.
            return source.name
        key = remote_media_key(target, PurePosixPath(source.name).name)
        created.append(key)
        s3 = s3_backend().connection.meta.client
        if source.name.startswith(REMOTE_PREFIX):
            head = s3.head_object(Bucket=settings.MEDIA_S3_BUCKET, Key=source.name)
            s3.copy_object(Bucket=settings.MEDIA_S3_BUCKET, Key=key,
                CopySource={'Bucket': settings.MEDIA_S3_BUCKET, 'Key': source.name},
                CopySourceIfMatch=head['ETag'], MetadataDirective='COPY')
            size = head['ContentLength']
        else:
            import mimetypes
            with source.open('rb') as stream:
                size = source.size
                s3.upload_fileobj(stream, settings.MEDIA_S3_BUCKET, key,
                    ExtraArgs={'ContentType': mimetypes.guess_type(source.name)[0] or 'application/octet-stream',
                               'CacheControl': 'private, no-store'})
        if s3.head_object(Bucket=settings.MEDIA_S3_BUCKET, Key=key)['ContentLength'] != size:
            raise OSError('Course media copy size mismatch')
        return key

    def copy_file(source, target):
        try:
            return perform_copy(source, target)
        except Exception:
            from common import ApiError
            raise ApiError('Хранилище временно недоступно. Обратитесь к системному администратору.', 503) from None

    try:
        yield copy_file
    except Exception:
        from file_cleanup import delete_unreferenced
        for name in created:
            delete_unreferenced(default_storage, name)
        raise
