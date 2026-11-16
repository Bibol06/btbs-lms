import time
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from courses.models import Enrollment
from analytics.models import TrackingCoverage
from analytics.tracking import capture_progress


class Command(BaseCommand):
    help = 'Capture current progress without fabricating historical values; optional worker.'

    def add_arguments(self, parser):
        parser.add_argument('--loop', action='store_true')

    def handle(self, *args, **options):
        while True:
            TrackingCoverage.objects.get_or_create(pk=1)
            count = 0
            queryset = Enrollment.objects.select_related('course', 'run').order_by('id')
            last = 0
            while True:
                rows = list(queryset.filter(id__gt=last)[:100])
                if not rows:
                    break
                for enrollment in rows:
                    capture_progress(enrollment, None)
                    count += 1
                last = rows[-1].id
            self.stdout.write(f'Current progress observed for {count} enrollments')
            if not options['loop']:
                break
            close_old_connections()
            time.sleep(60)
