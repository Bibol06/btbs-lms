import time
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from analytics.tasks import capture_all_progress


class Command(BaseCommand):
    help = 'Capture current progress without fabricating historical values; optional worker.'

    def add_arguments(self, parser):
        parser.add_argument('--loop', action='store_true')

    def handle(self, *args, **options):
        while True:
            count = capture_all_progress()
            self.stdout.write(f'Current progress observed for {count} enrollments')
            if not options['loop']:
                break
            close_old_connections()
            time.sleep(60)
