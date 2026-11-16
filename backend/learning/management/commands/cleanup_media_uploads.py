from django.core.management.base import BaseCommand
from learning.tasks import cleanup_expired_uploads


class Command(BaseCommand):
    help = 'Clean expired S3 staging uploads and retry queued file deletions'

    def handle(self, *args, **options):
        count, pending = cleanup_expired_uploads()
        self.stdout.write(f'Expired staging objects cleaned: {count}. Pending deletions: {pending}')
