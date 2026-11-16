from pathlib import Path

from django.core.validators import URLValidator
from django.db import transaction
from django.db.models import Max
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.views.decorators.clickjacking import xframe_options_sameorigin

from common import api, authenticated, body, text, boolean, ApiError
from courses.access import can_manage_course, is_enrolled, resolve_run, can_manage_run, require_run
from courses.models import Course
from .models import Lesson, LessonMaterial


def serialize_material(material):
    return {'id': material.id, 'title': material.title, 'filename': Path(material.file.name).name,
            'url': f'/api/learning/materials/{material.id}/open/',
            'kind': 'video' if Path(material.file.name).suffix.lower() in {'.mp4', '.webm'} else 'file'}


@require_GET
@api
def course_lessons(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    run = resolve_run(request, course)
    manage = can_manage_run(request.user, run)
    if not course.is_published and not manage:
        raise ApiError('Курс не найден', 404)
    full_access = manage or (course.is_published and is_enrolled(request.user, course, run))
    qs = course.lessons.all() if manage else course.lessons.filter(is_published=True).exclude(module__is_published=False)
    completed = set()
    if request.user.is_authenticated:
        from assessment.models import LessonProgress
        completed = set(LessonProgress.objects.filter(student=request.user, lesson__course=course, enrollment__run=run).values_list('lesson_id', flat=True))
    lessons = []
    from .services import require_lesson_visible
    for l in qs.select_related('module').prefetch_related('materials'):
        allowed = full_access
        if allowed:
            try:
                require_run(request, run)
                require_lesson_visible(request.user, l, run)
            except ApiError:
                allowed = False
        materials = [serialize_material(m) for m in l.materials.all() if not m.is_inline] if allowed else []
        for m in materials:
            m['url'] += f'?run_id={run.id}'
        lessons.append({'id': l.id, 'title': l.title, 'content': l.content if allowed else '',
            'video_url': l.video_url if allowed else '', 'position': l.position,
            'is_published': l.is_published, 'locked': not allowed, 'completed': l.id in completed, 'materials': materials})
    return JsonResponse({'course': course.title, 'description': course.description, 'course_id': course.id, 'is_published': course.is_published,
                         'is_enrolled': is_enrolled(request.user, course, run), 'can_manage': manage,
                         'lessons': lessons, 'total': len(lessons)})


@require_GET
@api
@xframe_options_sameorigin
def open_material(request, material_id):
    material = get_object_or_404(LessonMaterial.objects.select_related('lesson__course'), pk=material_id)
    if material.is_inline:
        from .image_views import open_lesson_image
        return open_lesson_image(request, material_id)
    lesson, course = material.lesson, material.lesson.course
    run = resolve_run(request, course)
    if not (can_manage_run(request.user, run) or (course.is_published and is_enrolled(request.user, course, run) and lesson.is_published)):
        raise ApiError('Войдите и запишитесь на опубликованный курс', 403 if request.user.is_authenticated else 401)
    require_run(request, run)
    from .services import require_lesson_visible
    require_lesson_visible(request.user, lesson, run)
    filename = Path(material.file.name).name
    from media_storage import private_file_response
    return private_file_response(material.file, attachment=Path(filename).suffix.lower() not in {'.pdf', '.mp4', '.webm'}, filename=filename)


def lesson_values(data, lesson=None):
    result = {
        'title': text(data, 'title', 200, required=True, default=lesson.title if lesson else ''),
        'content': text(data, 'content', 50000, default=lesson.content if lesson else ''),
        'video_url': text(data, 'video_url', 200, default=lesson.video_url if lesson else ''),
        'is_published': boolean(data, 'is_published', lesson.is_published if lesson else False),
    }
    if result['video_url']:
        URLValidator(schemes=['http', 'https'])(result['video_url'])
    return result


@require_POST
@api
def teacher_create_lesson(request, course_id):
    authenticated(request)
    data = body(request)
    values = lesson_values(data)
    with transaction.atomic():
        course = get_object_or_404(Course.objects.select_for_update(), pk=course_id)
        if not can_manage_course(request.user, course):
            raise ApiError('Нет прав на создание урока', 403)
        last = course.lessons.aggregate(last=Max('position'))['last'] or 0
        from .models import Module, Step
        module = get_object_or_404(Module, pk=data['module_id'], course=course) if data.get('module_id') else Module.objects.get_or_create(course=course, position=1, defaults={'title': 'Основная программа', 'is_published': True})[0]
        lesson = Lesson.objects.create(course=course, module=module, position=last + 1, **values)
        from .image_views import validate_image_references
        validate_image_references(lesson.content, lesson)
        Step.objects.create(lesson=lesson, title=lesson.title, content=lesson.content, kind='text', position=1, is_published=lesson.is_published)
    return JsonResponse({'message': 'Урок создан', 'lesson': {'id': lesson.id, **values, 'position': lesson.position}}, status=201)


@require_http_methods(['PATCH', 'DELETE'])
@api
def manage_lesson(request, lesson_id):
    authenticated(request)
    with transaction.atomic():
        lesson = get_object_or_404(Lesson.objects.select_related('course'), pk=lesson_id)
        Course.objects.select_for_update().get(pk=lesson.course_id)
        if not can_manage_course(request.user, lesson.course):
            raise ApiError('Нет прав на изменение урока', 403)
        if request.method == 'DELETE':
            lesson.delete()
            return JsonResponse({'message': 'Урок удалён'})
        data = body(request)
        if 'module_id' in data:
            from .models import Module
            lesson.module = get_object_or_404(Module, pk=data['module_id'], course=lesson.course)
        values = lesson_values(data, lesson)
        from .image_views import validate_image_references
        validate_image_references(values['content'], lesson)
        for key, value in values.items():
            setattr(lesson, key, value)
        lesson.save()
    return JsonResponse({'message': 'Урок обновлён'})


@require_http_methods(['DELETE'])
@api
def delete_material(request, material_id):
    authenticated(request)
    with transaction.atomic():
        material = get_object_or_404(LessonMaterial.objects.select_related('lesson__course'), pk=material_id)
        Course.objects.select_for_update().get(pk=material.lesson.course_id)
        if not can_manage_course(request.user, material.lesson.course):
            raise ApiError('Нет прав на удаление материала', 403)
        material.steps.all().delete()
        material.delete()
    return JsonResponse({'message': 'Материал удалён'})
