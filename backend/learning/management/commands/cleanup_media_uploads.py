from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from django.utils import timezone
from learning.models import MediaUpload, StorageDeletion
from learning.media_views import delete_staging
from file_cleanup import delete_unreferenced


class Command(BaseCommand):
    help = 'Clean expired S3 staging uploads and retry queued file deletions'

    def handle(self, *args, **options):
        count = 0
        for upload in MediaUpload.objects.filter(expires_at__lt=timezone.now()):
            if delete_staging(upload):
                # The short-lived upload session is no longer needed. Keep its
                # published material; do not re-delete staging on every run.
                upload.delete()
                count += 1
        for row in StorageDeletion.objects.all():
            delete_unreferenced(default_storage, row.name)
        self.stdout.write(f'Expired staging objects cleaned: {count}. Pending deletions: {StorageDeletion.objects.count()}')
