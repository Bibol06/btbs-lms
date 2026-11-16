from celery import shared_task

from background import exclusive


def cleanup_expired_uploads():
    """Delete expired S3 staging uploads and retry queued file deletions."""
    from django.core.files.storage import default_storage
    from django.utils import timezone
    from file_cleanup import delete_unreferenced
    from learning.media_views import delete_staging
    from learning.models import MediaUpload, StorageDeletion
    count = 0
    for upload in MediaUpload.objects.filter(expires_at__lt=timezone.now()):
        if delete_staging(upload):
            # The short-lived upload session is no longer needed. Keep its
            # published material; do not re-delete staging on every run.
            upload.delete()
            count += 1
    for row in StorageDeletion.objects.all():
        delete_unreferenced(default_storage, row.name)
    return count, StorageDeletion.objects.count()


@shared_task
@exclusive(ttl=3000)
def cleanup_media_uploads():
    return cleanup_expired_uploads()
