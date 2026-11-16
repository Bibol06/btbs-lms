import time
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from accounts.recovery import deliver_reset_mail


class Command(BaseCommand):
    help = 'Deliver queued recovery mail; --once for one pass. Backups use a separate worker.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true')

    def handle(self, *args, **options):
        while True:
            close_old_connections()
            try:
                sent = deliver_reset_mail()
                if sent:
                    self.stdout.write(f'Recovery emails delivered: {sent}')
            except Exception as exc:
                self.stderr.write(f'Recovery delivery failed: {type(exc).__name__}')
                if options['once']:
                    raise
            if options['once']:
                return
            time.sleep(15)
