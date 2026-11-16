import shutil
from django.conf import settings
from django.db import connection
from django.db.models import Count, Q
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.utils import timezone
from common import api, authenticated, ApiError
from .permissions import is_system_admin
from .identity import display_name
from .models import SystemAuditEvent
from .backups import backup_status, root, write_json


def require_system(request):
    authenticated(request)
    if not is_system_admin(request.user):
        raise ApiError('Раздел доступен системному администратору', 403)


@require_GET
@api
def status(request):
    require_system(request)
    with connection.cursor() as cursor:
        cursor.execute('SELECT 1'); database_ok = cursor.fetchone()[0] == 1
    from learning.models import LessonMaterial, MediaUpload
    from courses.models import CourseImage
    from assessment.models import Submission
    models = [LessonMaterial, CourseImage, Submission]
    local = sum(m.objects.exclude(file='').exclude(file__startswith='_s3/').count() for m in models)
    remote = sum(m.objects.filter(file__startswith='_s3/').count() for m in models)
    # Count DB references only; opening the page never lists/downloads S3 objects.
    from courses.models import Course
    from media_paths import course_prefix
    course_files = {}
    for model, owner, category in [(LessonMaterial, 'lesson__course_id', 'materials'),
                                    (CourseImage, 'course_id', 'images'),
                                    (Submission, 'assignment__course_id', 'answers')]:
        for row in model.objects.exclude(file='').values(owner).annotate(
                total=Count('id'), remote=Count('id', filter=Q(file__startswith='_s3/'))):
            entry = course_files.setdefault(row[owner], {'materials': 0, 'images': 0, 'answers': 0, 's3_files': 0, 'local_files': 0})
            entry[category] += row['total']
            entry['s3_files'] += row['remote']; entry['local_files'] += row['total'] - row['remote']
    courses = [{'id': c.id, 'title': c.title, 'prefix': '_s3/' + course_prefix(c.id), **course_files[c.id]}
               for c in Course.objects.filter(id__in=course_files).order_by('id')]
    disk = shutil.disk_usage(settings.BASE_DIR)
    from .models import PasswordResetDelivery
    mail_mode = 'smtp' if settings.EMAIL_BACKEND == 'django.core.mail.backends.smtp.EmailBackend' else 'local'
    return JsonResponse({'database_ok': database_ok, 'database_engine': connection.vendor,
        'backups': backup_status(),
        'recovery_mail': {'mode': mail_mode, 'pending': PasswordResetDelivery.objects.filter(state='pending').count(),
                          'failed': PasswordResetDelivery.objects.filter(state='failed').count()},
        'storage': {'mode': settings.MEDIA_STORAGE_MODE, 'configured': bool(settings.MEDIA_S3_BUCKET),
            'region': settings.MEDIA_S3_REGION, 'local_files': local, 's3_files': remote,
            'pending_uploads': MediaUpload.objects.filter(state='pending').count(), 'courses': courses},
        'disk_free_gb': round(disk.free/1024**3, 1),
        'audit': [{'id': e.id, 'actor': display_name(e.actor), 'target': display_name(e.target) if e.target else None,
            'action': e.action, 'created_at': e.created_at} for e in SystemAuditEvent.objects.select_related('actor', 'target').order_by('-id')[:25]]})


@require_POST
@api
def check_storage(request):
    require_system(request)
    if not settings.MEDIA_S3_BUCKET:
        raise ApiError('S3 ещё не настроен. Заполните параметры в backend/.env.', 409)
    from media_storage import s3_backend
    try:
        s3_backend().connection.meta.client.head_bucket(Bucket=settings.MEDIA_S3_BUCKET)
    except Exception:
        SystemAuditEvent.objects.create(actor=request.user, action='storage.connection_failed')
        raise ApiError('Не удалось подключиться к S3. Проверьте bucket, endpoint и права ключа.', 503)
    SystemAuditEvent.objects.create(actor=request.user, action='storage.connection_verified')
    return JsonResponse({'message': 'Подключение к S3 проверено'})


@require_POST
@api
def request_backup(request):
    require_system(request)
    state = backup_status()
    if not state.get('running') and not state['queued']:
        write_json(root() / 'requested.json', {'requested_at': timezone.now().isoformat()})
        SystemAuditEvent.objects.create(actor=request.user, action='backup.requested')
    return JsonResponse({'message': 'Создание резервной копии поставлено в очередь.'}, status=202)
