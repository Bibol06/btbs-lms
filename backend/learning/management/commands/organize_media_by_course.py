import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from courses.models import Course, CourseImage
from assessment.models import Submission
from learning.models import LessonMaterial
from course_media import copied_course_files
from media_paths import REMOTE_PREFIX, media_directory


MODELS = [LessonMaterial, CourseImage, Submission]


def records(model):
    relations = {LessonMaterial: ['lesson__course'], CourseImage: ['course'],
                 Submission: ['assignment__course', 'enrollment']}
    return model.objects.exclude(file='').select_related(*relations[model]).order_by('pk')


def course_id(row):
    return (row.lesson.course_id if isinstance(row, LessonMaterial) else
            row.assignment.course_id if isinstance(row, Submission) else row.course_id)


def organized(row):
    prefix = REMOTE_PREFIX + media_directory(row, row.file.name)
    return row.file.name.startswith(prefix) and '/' not in row.file.name[len(prefix):]


class Command(BaseCommand):
    help = 'Organize referenced media into S3 course folders, retaining all source files for recovery.'

    def add_arguments(self, parser):
        parser.add_argument('--execute', action='store_true')
        parser.add_argument('--course-id', type=int)
        parser.add_argument('--local-only', action='store_true')
        parser.add_argument('--report', help='Write a local JSON old/new reference manifest (required with --execute)')

    def handle(self, *args, **options):
        report = Path(options['report']).resolve() if options['report'] else None
        if options['execute'] and not report:
            raise CommandError('--execute requires --report for recovery')
        if report and (report.exists() or not report.parent.is_dir()):
            raise CommandError('Report must be a new file in an existing directory')
        if options['course_id'] and not Course.objects.filter(pk=options['course_id']).exists():
            raise CommandError('Course does not exist')
        plan = []
        titles = dict(Course.objects.values_list('id', 'title'))
        for model in MODELS:
            for row in records(model):
                if options['course_id'] and course_id(row) != options['course_id']:
                    continue
                if options['local_only'] and row.file.name.startswith(REMOTE_PREFIX):
                    continue
                if not organized(row):
                    plan.append({'model': model._meta.label_lower, 'id': row.pk, 'course_id': course_id(row),
                                 'old': row.file.name, 'directory': REMOTE_PREFIX + media_directory(row, row.file.name)})
        for cid in sorted({item['course_id'] for item in plan}):
            count = sum(item['course_id'] == cid for item in plan)
            self.stdout.write(f'course-{cid}: {titles[cid]} — {count} file(s)')
        self.stdout.write(f'References to organize: {len(plan)}')
        if not options['execute']:
            self.stdout.write('Dry run. Back up the database, then use --execute --report PATH. No files changed.')
            return
        from django.apps import apps
        from django.conf import settings
        if not settings.MEDIA_S3_BUCKET or settings.MEDIA_STORAGE_MODE != 's3':
            raise CommandError('Enable and configure S3 before executing')
        manifest = {'created_at': timezone.now().isoformat(), 'source_files_retained': True, 'files': []}

        def write_report():
            pending = report.with_suffix(report.suffix + '.tmp')
            pending.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
            pending.replace(report)

        write_report()
        for item in plan:
            model = apps.get_model(item['model'])
            # Record the new key before committing the DB switch. A crash between
            # disk and DB writes is recoverable by checking the actual DB reference.
            with copied_course_files() as copy_file, transaction.atomic():
                Course.objects.select_for_update().get(pk=item['course_id'])
                row = model.objects.select_for_update().get(pk=item['id'])
                if row.file.name != item['old'] or organized(row):
                    continue
                if course_id(row) != item['course_id']:
                    raise CommandError('Media ownership changed. Rerun the dry run.')
                target = copy_file(row.file, row)
                manifest['files'].append({**item, 'new': target})
                write_report()
                model.objects.filter(pk=row.pk, file=item['old']).update(file=target)
            self.stdout.write(f'Organized {item["model"]} #{item["id"]} in course-{item["course_id"]}')
        self.stdout.write('Finished. Source files retained; reruns skip already organized references.')
