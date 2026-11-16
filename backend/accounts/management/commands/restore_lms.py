from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from accounts.backups import BackupError, restore_backup


class Command(BaseCommand):
    help = 'Verify and restore only into a NEW lms_restore_* database and a NEW media directory.'

    def add_arguments(self, parser):
        parser.add_argument('--archive', type=Path, required=True)
        parser.add_argument('--database', required=True)
        parser.add_argument('--media-root', type=Path, required=True)

    def handle(self, *args, **options):
        try:
            result = restore_backup(options['archive'], options['database'], options['media_root'])
        except BackupError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(f"Restore verified: {result['database']}; media files: {result['media_files']}. Live database unchanged.")
