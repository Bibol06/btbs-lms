"""Direct uploads go to staging, then immutable validated media keys."""
from datetime import timedelta
from io import BytesIO
import mimetypes
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from common import api, authenticated, body, text, integer, ApiError
from courses.access import can_manage_course
from media_storage import s3_backend
from media_paths import course_prefix, remote_media_key
from .models import Lesson, LessonMaterial, MediaUpload, Step
from .upload_views import ALLOWED_EXTENSIONS, VIDEO_EXTENSIONS, valid_file_signature


def client():
    return s3_backend().connection.meta.client


def require_s3():
    if settings.MEDIA_STORAGE_MODE != 's3' or not settings.MEDIA_S3_BUCKET:
        raise ApiError('S3 ещё не подключён. Используйте обычную загрузку.', 409)


def require_editor(request, lesson):
    authenticated(request)
    if not can_manage_course(request.user, lesson.course):
        raise ApiError('Нет прав на загрузку материалов', 403)


def delete_staging(upload, s3=None):
    try:
        s3 = s3 or client()
        from .multipart import abort_parts
        abort_parts(s3, upload)
        s3.delete_object(Bucket=settings.MEDIA_S3_BUCKET, Key=upload.staging_key)
        return True
    except Exception:
        return False


@require_GET
@api
def upload_config(request):
    authenticated(request)
    enabled = settings.MEDIA_STORAGE_MODE == 's3' and bool(settings.MEDIA_S3_BUCKET)
    return JsonResponse({'mode': settings.MEDIA_STORAGE_MODE, 'direct_upload': enabled,
        'video_limit_mb': 2048 if enabled else 100, 'document_limit_mb': 20,
        'multipart_upload': enabled and settings.MEDIA_MULTIPART_ENABLED})


@require_POST
@api
def initiate(request, lesson_id):
    lesson = get_object_or_404(Lesson.objects.select_related('course'), pk=lesson_id)
    require_editor(request, lesson); require_s3()
    data = body(request)
    filename = Path(text(data, 'filename', 200, True).replace('\\', '/')).name
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ApiError('Этот формат файла не поддерживается')
    size = integer(data, 'size', 1, (2048 if extension in VIDEO_EXTENSIONS else 20)*1024*1024)
    content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
    title = text(data, 'title', 200) or Path(filename).stem
    multipart = data.get('multipart') is True
    fingerprint = text(data, 'fingerprint', 64)
    if multipart:
        import re
        if not settings.MEDIA_MULTIPART_ENABLED:
            raise ApiError('Загрузка частями ещё не настроена.', 409)
        if not re.fullmatch('[a-f0-9]{64}', fingerprint):
            raise ApiError('Не удалось проверить выбранный файл.')
        previous = MediaUpload.objects.filter(lesson=lesson, owner=request.user, fingerprint=fingerprint, size=size,
            filename=filename, state='pending', expires_at__gt=timezone.now()).exclude(multipart_id='').order_by('-created_at').first()
        if previous:
            return JsonResponse({'id': previous.id, 'multipart': True, 'part_size': previous.part_size})
    upload = MediaUpload(lesson=lesson, owner=request.user, filename=filename, title=title, size=size,
        content_type=content_type,
        staging_key=f'_staging/{course_prefix(lesson.course_id)}lessons/lesson-{lesson.id}/{uuid4().hex}{extension}',
        expires_at=timezone.now()+timedelta(hours=24 if multipart else 2))
    try:
        if multipart:
            from .multipart import PART_SIZE
            upload.multipart_id = client().create_multipart_upload(Bucket=settings.MEDIA_S3_BUCKET, Key=upload.staging_key, ContentType=content_type)['UploadId']
            upload.part_size, upload.fingerprint = PART_SIZE, fingerprint
            try:
                upload.save()
            except Exception:
                delete_staging(upload)
                raise
            return JsonResponse({'id': upload.id, 'multipart': True, 'part_size': upload.part_size}, status=201)
        form = client().generate_presigned_post(Bucket=settings.MEDIA_S3_BUCKET, Key=upload.staging_key,
            Fields={'Content-Type': content_type}, Conditions=[{'Content-Type': content_type}, ['content-length-range', size, size]], ExpiresIn=3600)
    except Exception:
        raise ApiError('Не удалось подготовить загрузку в S3. Проверьте настройки хранилища.', 503)
    upload.save()
    return JsonResponse({'id': upload.id, 'upload': form, 'expires_at': upload.expires_at}, status=201)


@require_POST
@api
def complete(request, upload_id):
    authenticated(request); require_s3()
    with transaction.atomic():
        upload = get_object_or_404(MediaUpload.objects.select_for_update(of=('self',)).select_related('lesson__course', 'material'), pk=upload_id, owner=request.user)
        require_editor(request, upload.lesson)
        if upload.state == 'complete':
            if not upload.material_id:
                raise ApiError('Материал был удалён')
            from .views import serialize_material
            return JsonResponse({'material': serialize_material(upload.material)})
        if upload.state != 'pending' or upload.expires_at < timezone.now():
            raise ApiError('Срок загрузки истёк. Выберите файл ещё раз.')
        s3 = client()
        from .multipart import assemble
        try:
            assemble(s3, upload)
        except ApiError:
            raise
        except Exception:
            raise ApiError('Не удалось подтвердить загрузку. Повторите проверку файла.', 503)
        draft = LessonMaterial(lesson=upload.lesson, title=upload.title)
        final_key = remote_media_key(draft, upload.filename)
        try:
            head = s3.head_object(Bucket=settings.MEDIA_S3_BUCKET, Key=upload.staging_key)
            if head['ContentLength'] != upload.size or head.get('ContentType') != upload.content_type:
                raise ApiError('Размер или формат загруженного файла не совпадает с заявленным')
            sample = s3.get_object(Bucket=settings.MEDIA_S3_BUCKET, Key=upload.staging_key, Range='bytes=0-15', IfMatch=head['ETag'])['Body']
            header = sample.read(); sample.close()
            if not valid_file_signature(BytesIO(header), Path(upload.filename).suffix.lower()):
                raise ApiError('Содержимое файла не соответствует его формату')
            # The upload URL only writes staging. It cannot replace a published object.
            s3.copy_object(Bucket=settings.MEDIA_S3_BUCKET, Key=final_key,
                CopySource={'Bucket': settings.MEDIA_S3_BUCKET, 'Key': upload.staging_key}, CopySourceIfMatch=head['ETag'],
                MetadataDirective='REPLACE', ContentType=upload.content_type, CacheControl='private, no-store')
        except ApiError:
            delete_staging(upload, s3)
            raise
        except Exception:
            raise ApiError('Не удалось подтвердить загрузку. Повторите проверку файла.', 503)
        try:
            from courses.models import Course
            Course.objects.select_for_update().get(pk=upload.lesson.course_id)
            material = LessonMaterial.objects.create(lesson=upload.lesson, title=upload.title, file=final_key)
            last = upload.lesson.steps.aggregate(value=Max('position'))['value'] or 0
            Step.objects.create(lesson=upload.lesson, title=material.title, kind='file', material=material,
                position=last+1, is_published=upload.lesson.is_published)
            upload.state, upload.material = 'complete', material
            upload.save(update_fields=['state', 'material'])
            from communication.services import notify, course_target
            if upload.lesson.is_published and upload.lesson.course.is_published:
                recipients = set(upload.lesson.course.enrollments.filter(status__in=['active', 'completed']).values_list('student_id', flat=True))
                notify(f'material:{material.id}', 'material', upload.lesson.course, recipients,
                       'Добавлен учебный материал', course_target(upload.lesson.course, lesson_id=upload.lesson_id))
        except Exception:
            s3.delete_object(Bucket=settings.MEDIA_S3_BUCKET, Key=final_key)
            raise
        transaction.on_commit(lambda: delete_staging(upload, s3))
    from .views import serialize_material
    return JsonResponse({'material': serialize_material(material)}, status=201)


@require_POST
@api
def abort(request, upload_id):
    authenticated(request); require_s3()
    with transaction.atomic():
        upload = get_object_or_404(MediaUpload.objects.select_for_update(), pk=upload_id, owner=request.user)
        if upload.state == 'pending':
            upload.state = 'cancelled'; upload.save(update_fields=['state'])
            transaction.on_commit(lambda: delete_staging(upload))
    return JsonResponse({'state': upload.state})


@require_http_methods(['GET', 'POST'])
@api
def parts(request, upload_id):
    authenticated(request); require_s3()
    upload = get_object_or_404(MediaUpload.objects.select_related('lesson__course'), pk=upload_id, owner=request.user)
    require_editor(request, upload.lesson)
    if not upload.multipart_id or upload.state != 'pending' or upload.expires_at <= timezone.now():
        raise ApiError('Срок загрузки истёк. Выберите файл ещё раз.', 409)
    from .multipart import uploaded_parts, params
    import math
    try:
        s3 = client()
        if request.method == 'GET':
            from botocore.exceptions import ClientError
            try:
                rows = uploaded_parts(s3, upload)
            except ClientError as exc:
                if exc.response['Error']['Code'] != 'NoSuchUpload':
                    raise
                s3.head_object(Bucket=settings.MEDIA_S3_BUCKET, Key=upload.staging_key)
                return JsonResponse({'parts': [], 'assembled': True})
            return JsonResponse({'parts': [{'number': p['PartNumber'], 'size': p['Size']} for p in rows], 'assembled': False})
        number = integer(body(request), 'number', 1, math.ceil(upload.size / upload.part_size))
        size = min(upload.part_size, upload.size - (number-1)*upload.part_size)
        url = s3.generate_presigned_url('upload_part', Params={**params(upload), 'PartNumber': number, 'ContentLength': size}, ExpiresIn=900)
        return JsonResponse({'url': url})
    except ApiError:
        raise
    except Exception:
        raise ApiError('Не удалось связаться с S3. Повторите загрузку.', 503)
