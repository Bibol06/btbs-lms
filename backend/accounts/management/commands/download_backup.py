from django.core.management.base import BaseCommand, CommandError
from accounts.backup_remote import download_archive


class Command(BaseCommand):
    help = 'Download a verified encrypted S3 archive; never overwrite an existing file.'

    def add_arguments(self, parser):
        parser.add_argument('--name', required=True)
        parser.add_argument('--destination', required=True)
        parser.add_argument('--version-id')

    def handle(self, *args, **options):
        try:
            path = download_archive(options['name'], options['destination'], options['version_id'])
        except Exception as exc:
            raise CommandError('Backup download failed; check bucket access, name, destination and checksum.') from exc
        self.stdout.write(f'Verified archive: {path.name}')
