
from pathlib import Path

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST
from django.db import transaction

from courses.access import can_manage_course
from courses.models import Course
from common import api
from .models import Lesson, LessonMaterial


ALLOWED_EXTENSIONS = {
    ".pdf", ".docx", ".pptx",
    ".doc", ".ppt",
    ".mp4", ".webm",
    ".jpg", ".jpeg", ".png"
}

VIDEO_EXTENSIONS = {".mp4", ".webm"}


def valid_file_signature(file, extension):
    header = file.read(16)
    file.seek(0)

    if extension == ".pdf":
        return header.startswith(b"%PDF-")

    if extension in {".docx", ".pptx"}:
        return header.startswith(b"PK\x03\x04")

    if extension in {".doc", ".ppt"}:
        return header.startswith(
            b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
        )

    if extension == ".mp4":
        return header[4:8] == b"ftyp"

    if extension == ".webm":
        return header.startswith(b"\x1a\x45\xdf\xa3")

    if extension == ".png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")

    if extension in {".jpg", ".jpeg"}:
        return header.startswith(b"\xff\xd8\xff")

    return False


@require_POST
@api
def upload_lesson_material(request, lesson_id):

    if not request.user.is_authenticated:
        return JsonResponse(
            {"error": "Необходима авторизация"},
            status=401
        )

    lesson = get_object_or_404(
        Lesson.objects.select_related("course"),
        id=lesson_id
    )

    if not can_manage_course(request.user, lesson.course):
        return JsonResponse(
            {"error": "Нет прав на загрузку материалов"},
            status=403
        )

    uploaded_file = request.FILES.get("file")

    if uploaded_file is None:
        return JsonResponse(
            {"error": "Выберите файл"},
            status=400
        )

    extension = Path(uploaded_file.name).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        return JsonResponse(
            {"error": "Этот формат файла не поддерживается"},
            status=400
        )

    max_size = (
        100 * 1024 * 1024
        if extension in VIDEO_EXTENSIONS
        else 20 * 1024 * 1024
    )

    if uploaded_file.size == 0 or uploaded_file.size > max_size:
        return JsonResponse(
            {"error": "Неверный размер файла. Лимит: 100 МБ для видео, 20 МБ для документов"},
            status=400
        )

    if not valid_file_signature(uploaded_file, extension):
        return JsonResponse(
            {"error": "Содержимое файла не соответствует его формату"},
            status=400
        )

    title = request.POST.get("title", "").strip()

    if not title:
        from .naming import readable_title
        title = readable_title(uploaded_file.name)

    if len(title) > 200:
        return JsonResponse(
            {"error": "Слишком длинное название"},
            status=400
        )

    material = LessonMaterial(lesson=lesson, title=title)
    try:
        with transaction.atomic():
            Course.objects.select_for_update().get(pk=lesson.course_id)
            get_object_or_404(Lesson, pk=lesson_id)
            material.file.save(uploaded_file.name, uploaded_file, save=False)
            material.save()
            from .models import Step
            from django.db.models import Max
            last = lesson.steps.aggregate(value=Max('position'))['value'] or 0
            Step.objects.create(lesson=lesson, title=material.title, kind='file', material=material,
                                position=last+1, is_published=lesson.is_published)
            from communication.services import notify, course_target
            recipients = set(lesson.course.enrollments.filter(status__in=['active', 'completed']).values_list('student_id', flat=True))
            if lesson.is_published and lesson.course.is_published:
                notify(f'material:{material.id}', 'material', lesson.course, recipients,
                       'Добавлен учебный материал', course_target(lesson.course, lesson_id=lesson.id))
    except Exception:
        if material.file:
            material.file.delete(save=False)
        raise

    return JsonResponse({
        "message": "Файл успешно загружен",
        "material": {
            "id": material.id,
            "title": material.title,
            "url": f"/api/learning/materials/{material.id}/open/",
            "kind": (
                "video"
                if extension in VIDEO_EXTENSIONS
                else "file"
            )
        }
    }, status=201)
