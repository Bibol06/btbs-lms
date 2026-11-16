"""Compatibility entry point: local migration uses the same course namespace."""
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = 'Copy referenced local media into S3 course folders. Local originals remain intact.'

    def add_arguments(self, parser):
        parser.add_argument('--execute', action='store_true')
        parser.add_argument('--report')
        parser.add_argument('--course-id', type=int)

    def handle(self, *args, **options):
        report = options['report']
        if options['execute'] and not report:
            directory = settings.BASE_DIR.parent / '.local' / 'backups'
            directory.mkdir(parents=True, exist_ok=True)
            report = str(directory / f's3-local-migration-{timezone.now():%Y%m%d-%H%M%S-%f}.json')
        call_command('organize_media_by_course', execute=options['execute'], report=report,
                     course_id=options['course_id'], local_only=True, stdout=self.stdout)
        if report:
            self.stdout.write(f'Recovery manifest: {report}')
