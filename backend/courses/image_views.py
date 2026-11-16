"""Description illustrations are public only when referenced by a published course."""
import re
from pathlib import Path
from uuid import uuid4

from django.db import transaction
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from common import ApiError, api, authenticated
from image_uploads import validate_image_upload
from learning.image_views import image_reference_source
from .access import can_manage_course
from .models import Course, CourseImage

IMAGE_REFERENCE = re.compile(r'!\[[^\]\r\n]*\]\(/api/courses/images/([1-9]\d*)/\)')


def image_ids(content):
    return {int(value) for value in IMAGE_REFERENCE.findall(image_reference_source(content))}


def validate_description_images(content, course=None):
    ids = image_ids(content)
    if ids and (course is None or CourseImage.objects.filter(course=course, id__in=ids).count() != len(ids)):
        raise ApiError('Изображение относится к другому курсу или недоступно')
    # Private lesson images cannot serve as public course-description assets.
    from learning.image_views import image_ids as lesson_image_ids
    if lesson_image_ids(content):
        raise ApiError('Загрузите изображение через редактор описания курса')


def rewrite_description_images(content, images):
    for match in reversed(list(IMAGE_REFERENCE.finditer(image_reference_source(content)))):
        original = int(match.group(1))
        replacement = images.get(original)
        if replacement:
            text = content[match.start():match.end()].replace(f'/images/{original}/', f'/images/{replacement.id}/')
            content = content[:match.start()] + text + content[match.end():]
    return content


@require_POST
@api
def upload_course_image(request, course_id):
    authenticated(request)
    course = get_object_or_404(Course, pk=course_id)
    if not can_manage_course(request.user, course):
        raise ApiError('Нет прав на изменение курса', 403)
    file = request.FILES.get('file')
    extension = validate_image_upload(file)
    title = request.POST.get('title', '').strip() or Path(file.name).stem[:200]
    if len(title) > 200:
        raise ApiError('Слишком длинное название')
    image = CourseImage(course=course, title=title)
    try:
        with transaction.atomic():
            get_object_or_404(Course.objects.select_for_update(), pk=course_id)
            image.file.save(f'{uuid4().hex}{extension}', file, save=False)
            image.save()
    except Exception:
        if image.file:
            image.file.delete(save=False)
        raise
    return JsonResponse({'image': {'id': image.id, 'title': image.title,
        'url': f'/api/courses/images/{image.id}/'}}, status=201)


@require_GET
@api
def open_course_image(request, image_id):
    image = get_object_or_404(CourseImage.objects.select_related('course'), pk=image_id)
    course = image.course
    if not can_manage_course(request.user, course) and (not course.is_published or image.id not in image_ids(course.description)):
        raise ApiError('Изображение ещё не опубликовано', 404)
    extension = Path(image.file.name).suffix.lower()
    if extension not in {'.png', '.jpg', '.jpeg'}:
        raise ApiError('Файл не найден на сервере', 404)
    from media_storage import private_file_response
    return private_file_response(image.file, content_type='image/png' if extension == '.png' else 'image/jpeg')
