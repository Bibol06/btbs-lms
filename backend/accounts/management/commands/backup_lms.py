from django.core.management.base import BaseCommand, CommandError
from accounts.backups import BackupError, BackupBusy, create_backup
from django.db import close_old_connections
import time


class Command(BaseCommand):
    help = 'Create an encrypted database + local/S3 media backup.'

    def add_arguments(self, parser):
        parser.add_argument('--if-due', action='store_true')
        parser.add_argument('--loop', action='store_true')

    def handle(self, *args, **options):
        while True:
            close_old_connections()
            try:
                result = create_backup(if_due=options['if_due'] or options['loop'])
                if result:
                    self.stdout.write(f'Backup ready: {result.name}')
            except BackupBusy as exc:
                if not options['if_due'] and not options['loop']:
                    raise CommandError(str(exc)) from exc
            except BackupError as exc:
                if not options['loop']:
                    raise CommandError(str(exc)) from exc
                self.stderr.write(str(exc))
            if not options['loop']:
                return
            time.sleep(30)
