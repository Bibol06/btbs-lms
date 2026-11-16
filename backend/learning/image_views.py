"""Private inline illustrations, attached to the lesson whose text uses them."""
import re
from pathlib import Path
from uuid import uuid4

from django.db import transaction
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from common import ApiError, api, authenticated
from courses.access import can_manage_course, can_manage_run, require_run, resolve_run
from .models import Lesson, LessonMaterial
from .services import require_lesson_visible
from image_uploads import validate_image_upload

IMAGE_REFERENCE = re.compile(r'!\[[^\]\r\n]*\]\(/api/learning/images/([1-9]\d*)/(?:\?run_id=\d+)?\)')


def image_reference_source(content):
    """Mask examples inside code without changing offsets in the authored text."""
    lines, fenced = [], False
    for line in content.splitlines(keepends=True):
        if fenced:
            if re.match(r'^\s*```\s*$', line):
                fenced = False
            lines.append(''.join('\n' if character == '\n' else ' ' for character in line))
        elif re.match(r'^\s*```', line):
            fenced = True
            lines.append(''.join('\n' if character == '\n' else ' ' for character in line))
        else:
            lines.append(re.sub(r'`[^`\n]+`', lambda match: ' ' * len(match.group(0)), line))
    return ''.join(lines)


def image_ids(content):
    return {int(value) for value in IMAGE_REFERENCE.findall(image_reference_source(content))}


def validate_image_references(content, lesson):
    ids = image_ids(content)
    if ids and LessonMaterial.objects.filter(id__in=ids, lesson=lesson, is_inline=True).count() != len(ids):
        raise ApiError('Иллюстрация относится к другому уроку или недоступна')


def rewrite_image_references(content, materials):
    for match in reversed(list(IMAGE_REFERENCE.finditer(image_reference_source(content)))):
        original = int(match.group(1))
        replacement = materials.get(original)
        if replacement:
            text = content[match.start():match.end()].replace(f'/images/{original}/', f'/images/{replacement.id}/')
            content = content[:match.start()] + text + content[match.end():]
    return content


@require_POST
@api
def upload_lesson_image(request, lesson_id):
    authenticated(request)
    lesson = get_object_or_404(Lesson.objects.select_related('course'), pk=lesson_id)
    if not can_manage_course(request.user, lesson.course):
        raise ApiError('Нет прав на загрузку материалов', 403)
    file = request.FILES.get('file')
    extension = validate_image_upload(file)
    title = request.POST.get('title', '').strip() or Path(file.name).stem[:200]
    if len(title) > 200:
        raise ApiError('Слишком длинное название')
    material = LessonMaterial(lesson=lesson, title=title, is_inline=True)
    try:
        with transaction.atomic():
            # Serialize with course/lesson deletion and content edits.
            from courses.models import Course
            Course.objects.select_for_update().get(pk=lesson.course_id)
            get_object_or_404(Lesson, pk=lesson_id)
            material.file.save(f'{uuid4().hex}{extension}', file, save=False)
            material.save()
    except Exception:
        if material.file:
            material.file.delete(save=False)
        raise
    return JsonResponse({'image': {'id': material.id, 'title': material.title,
        'url': f'/api/learning/images/{material.id}/'}}, status=201)


@require_GET
@api
def open_lesson_image(request, image_id):
    image = get_object_or_404(LessonMaterial.objects.select_related('lesson__course', 'lesson__module'), pk=image_id, is_inline=True)
    lesson = image.lesson
    cohort = resolve_run(request, lesson.course)
    require_run(request, cohort)
    require_lesson_visible(request.user, lesson, cohort)
    if not can_manage_run(request.user, cohort):
        # Uploading a picture in a draft must not disclose it through a guessed ID.
        reference = f'/api/learning/images/{image.id}/'
        visible = image.id in image_ids(lesson.content)
        if not visible:
            visible = any(image.id in image_ids(content)
                for content in lesson.steps.filter(kind='text', is_published=True, content__contains=reference).values_list('content', flat=True))
        if not visible:
            raise ApiError('Иллюстрация ещё не опубликована', 404)
    extension = Path(image.file.name).suffix.lower()
    if extension not in {'.png', '.jpg', '.jpeg'}:
        raise ApiError('Файл не найден на сервере', 404)
    from media_storage import private_file_response
    return private_file_response(image.file, content_type='image/png' if extension == '.png' else 'image/jpeg')
