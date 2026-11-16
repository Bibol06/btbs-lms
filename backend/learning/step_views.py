from django.db import transaction
from django.db.models import Max, Prefetch
from django.core.validators import URLValidator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from common import api, authenticated, body, text, integer, boolean, date, ApiError
from courses.models import Course, Enrollment
from courses.access import can_manage_course, can_manage_run, resolve_run, require_run, require_learning_enrollment
from .models import Module, Lesson, Step, StepProgress
from .services import require_lesson_visible, visible_steps, step_completed, course_progress, refresh_completion, with_step_progress


def content_editor(request, course):
    authenticated(request)
    if not can_manage_course(request.user, course):
        raise ApiError('Нет прав редактора курса', 403)


@require_http_methods(['GET', 'POST'])
@api
def structure(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    run = resolve_run(request, course)
    if request.method == 'POST':
        content_editor(request, course)
        data = body(request)
        with transaction.atomic():
            Course.objects.select_for_update().get(pk=course.id)
            last = course.modules.aggregate(v=Max('position'))['v'] or 0
            module = Module.objects.create(course=course, title=text(data, 'title', 200, True), position=last+1, is_published=boolean(data, 'is_published', False))
        return JsonResponse({'id': module.id}, status=201)
    require_run(request, run)
    manager = can_manage_run(request.user, run)
    run._module_release_map = {row.module_id: row for row in run.module_releases.all()}
    enrollment = Enrollment.objects.filter(run=run, student=request.user).first()
    from courses.pacing import module_deadline_states
    deadline_states = module_deadline_states(run, [enrollment] if enrollment else [])
    modules = course.modules.all() if manager else course.modules.filter(is_published=True)
    result = []
    lessons_query = Lesson.objects.select_related('module__prerequisite').prefetch_related(Prefetch('steps', queryset=with_step_progress(Step.objects.all(), enrollment)))
    for module in modules.prefetch_related(Prefetch('lessons', queryset=lessons_query)):
        lessons = []
        for lesson in module.lessons.all():
            if not manager and not lesson.is_published:
                continue
            reason = ''
            try:
                require_lesson_visible(request.user, lesson, run, manager=manager)
            except ApiError as exc:
                reason = exc.message
            steps = [{'id': s.id, 'title': s.title, 'kind': s.kind, 'position': s.position,
                      'is_published': s.is_published, 'required': s.required,
                      'completed': step_completed(s, enrollment), 'locked': bool(reason)}
                     for s in lesson.steps.all() if manager or s.is_published]
            lessons.append({'id': lesson.id, 'title': lesson.title, 'position': lesson.position, 'is_published': lesson.is_published, 'locked_reason': reason, 'steps': steps})
        from courses.pacing import module_release
        release = module_release(module, run)
        result.append({'id': module.id, 'title': module.title, 'position': module.position, 'is_published': module.is_published,
                       'opens_at': release['opens_at'], 'due_at': release['due_at'],
                       'deadline_state': deadline_states.get((enrollment.id, module.id), {}).get('state') if enrollment else None,
                       'release_week': release['week'], 'prerequisite_id': module.prerequisite_id, 'lessons': lessons})
    return JsonResponse({'modules': result, 'run_id': run.id, 'can_edit': can_manage_course(request.user, course),
                         'can_manage': manager, 'last_step_id': enrollment.last_step_id if enrollment else None,
                         'progress': course_progress(course, enrollment)})


@require_http_methods(['PATCH', 'DELETE'])
@api
def module_detail(request, module_id):
    module = get_object_or_404(Module.objects.select_related('course'), pk=module_id)
    content_editor(request, module.course)
    if request.method == 'DELETE':
        if module.lessons.exists():
            raise ApiError('Сначала перенесите или удалите уроки этого модуля')
        module.delete()
        return JsonResponse({'message': 'Модуль удалён'})
    data = body(request)
    module.title = text(data, 'title', 200, True, module.title)
    module.is_published = boolean(data, 'is_published', module.is_published)
    if 'opens_at' in data:
        module.opens_at = date(data, 'opens_at')
    if 'prerequisite_id' in data:
        prerequisite = get_object_or_404(Module, pk=integer(data, 'prerequisite_id', 1, 2**63-1), course=module.course) if data['prerequisite_id'] else None
        seen = {module.id}
        cursor = prerequisite
        while cursor:
            if cursor.id in seen:
                raise ApiError('Модули не могут зависеть друг от друга по кругу')
            seen.add(cursor.id)
            cursor = cursor.prerequisite
        module.prerequisite = prerequisite
    module.save()
    return JsonResponse({'message': 'Модуль сохранён'})


def step_values(data, lesson, current=None):
    kind = data.get('kind', current.kind if current else 'text')
    if kind not in ['text', 'video', 'file', 'assignment', 'quiz', 'code']:
        raise ApiError('Неизвестный тип шага')
    result = {'kind': kind, 'title': text(data, 'title', 200, True, current.title if current else ''),
              'content': text(data, 'content', 100000, default=current.content if current else ''),
              'video_url': text(data, 'video_url', 200, default=current.video_url if current else ''),
              'is_published': boolean(data, 'is_published', current.is_published if current else False),
              'required': boolean(data, 'required', current.required if current else True),
              'pass_percent': integer(data, 'pass_percent', 0, 100, current.pass_percent if current else 60)}
    from .image_views import validate_image_references
    validate_image_references(result['content'], lesson)
    if result['video_url']:
        URLValidator(schemes=['http', 'https'])(result['video_url'])
    from assessment.models import Assignment, Quiz
    from codejudge.models import CodeProblem
    from .models import LessonMaterial
    for key, model in [('assignment', Assignment), ('quiz', Quiz), ('code_problem', CodeProblem), ('material', LessonMaterial)]:
        value = data.get(key+'_id', getattr(current, key+'_id', None) if current else None)
        if value is not None:
            if type(value) is not int:
                raise ApiError('Неверная ссылка на материал шага')
            obj = get_object_or_404(model, pk=value)
            if key == 'material' and obj.is_inline:
                raise ApiError('Вставьте иллюстрацию в текст урока вместо файлового шага')
            object_course = obj.lesson.course_id if key == 'material' else obj.course_id
            if object_course != lesson.course_id or (key == 'material' and obj.lesson_id != lesson.id):
                raise ApiError('Материал относится к другому уроку или курсу')
            result[key] = obj
        else:
            result[key] = None
    field = {'assignment': 'assignment', 'quiz': 'quiz', 'code': 'code_problem', 'file': 'material'}.get(kind)
    if field and not result[field]:
        raise ApiError('Выберите задание, тест, файл или задачу для шага')
    if kind == 'video' and not result['video_url']:
        raise ApiError('Укажите ссылку на видео')
    return result


@require_POST
@api
def create_step(request, lesson_id):
    lesson = get_object_or_404(Lesson.objects.select_related('course'), pk=lesson_id)
    content_editor(request, lesson.course)
    values = step_values(body(request), lesson)
    with transaction.atomic():
        Lesson.objects.select_for_update().get(pk=lesson.id)
        last = lesson.steps.aggregate(v=Max('position'))['v'] or 0
        step = Step.objects.create(lesson=lesson, position=last+1, **values)
        from communication.services import notify_published_step
        notify_published_step(step)
    return JsonResponse({'id': step.id}, status=201)


@require_http_methods(['GET', 'PATCH', 'DELETE'])
@api
def step_detail(request, step_id):
    step = get_object_or_404(Step.objects.select_related('lesson__course', 'lesson__module', 'material'), pk=step_id)
    course = step.lesson.course
    if request.method != 'GET':
        content_editor(request, course)
        if request.method == 'DELETE':
            step.delete()
            return JsonResponse({'message': 'Шаг удалён'})
        with transaction.atomic():
            for key, value in step_values(body(request), step.lesson, step).items():
                setattr(step, key, value)
            step.save()
            from communication.services import notify_published_step
            notify_published_step(step)
    run = resolve_run(request, course)
    require_run(request, run)
    require_lesson_visible(request.user, step.lesson, run)
    if not step.is_published and not can_manage_run(request.user, run):
        raise ApiError('Шаг не опубликован', 404)
    enrollment = Enrollment.objects.filter(run=run, student=request.user).first()
    from .views import serialize_material
    material = serialize_material(step.material) if step.material else None
    if material:
        material['url'] += f'?run_id={run.id}'
    return JsonResponse({'step': {'id': step.id, 'lesson_id': step.lesson_id, 'title': step.title, 'kind': step.kind,
        'content': step.content, 'video_url': step.video_url, 'is_published': step.is_published, 'required': step.required,
        'pass_percent': step.pass_percent, 'material': material, 'material_id': step.material_id,
        'assignment_id': step.assignment_id, 'quiz_id': step.quiz_id, 'code_problem_id': step.code_problem_id,
        'completed': step_completed(step, enrollment)}})


@require_POST
@api
def step_visit(request, step_id):
    step = get_object_or_404(Step.objects.select_related('lesson__course', 'lesson__module'), pk=step_id)
    run = resolve_run(request, step.lesson.course)
    require_run(request, run)
    require_lesson_visible(request.user, step.lesson, run)
    if not step.is_published and not can_manage_run(request.user, run):
        raise ApiError('Шаг не опубликован', 404)
    enrollment = Enrollment.objects.filter(run=run, student=request.user, status__in=['active', 'completed']).first()
    if enrollment:
        enrollment.last_step, enrollment.last_seen_at = step, timezone.now()
        enrollment.save(update_fields=['last_step', 'last_seen_at'])
    from analytics.tracking import record, capture_progress
    from learning.services import course_progress
    bucket = int(timezone.now().timestamp()) // 300
    values = body(request) if request.content_type == 'application/json' else {}
    visit_id = values.get('visit_id')
    if visit_id is not None:
        from uuid import UUID
        if not isinstance(visit_id, str):
            raise ApiError('Некорректный идентификатор открытия')
        visit_id = UUID(visit_id).hex
    key = f'view:{request.user.id}:{run.id}:{step.id}:{visit_id or bucket}'
    record(request.user, 'step_view', enrollment=enrollment, run=run, step=step, dedupe=key)
    if enrollment:
        capture_progress(enrollment, course_progress(step.lesson.course, enrollment))
    return JsonResponse({'message': 'Место сохранено'})


@require_POST
@api
def complete_step(request, step_id):
    step = get_object_or_404(Step.objects.select_related('lesson__course', 'lesson__module'), pk=step_id)
    run = resolve_run(request, step.lesson.course)
    with transaction.atomic():
        enrollment = require_learning_enrollment(request, run, lock=True)
        require_lesson_visible(request.user, step.lesson, run)
        if not step.is_published:
            raise ApiError('Шаг не опубликован', 404)
        if step.kind not in ['text', 'video', 'file']:
            raise ApiError('Выполнение этого шага определяется результатом проверки')
        completed = boolean(body(request), 'completed', True)
        if completed:
            _, changed = StepProgress.objects.get_or_create(step=step, enrollment=enrollment)
        else:
            changed, _ = StepProgress.objects.filter(step=step, enrollment=enrollment).delete()
        progress = refresh_completion(enrollment)
        if changed:
            from analytics.tracking import record
            record(request.user, 'step_completed' if completed else 'step_reopened', enrollment=enrollment, step=step)
    return JsonResponse({'completed': completed, 'progress': progress})


@require_POST
@api
def reorder(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    content_editor(request, course)
    data = body(request)
    kind = data.get('kind')
    if kind == 'modules':
        qs = course.modules.all()
    elif kind == 'lessons':
        module = get_object_or_404(Module, pk=integer(data, 'parent_id', 1, 2**63-1), course=course)
        # Lesson positions remain course-wide for compatibility; order all lessons together.
        qs = course.lessons.all()
    elif kind == 'steps':
        lesson = get_object_or_404(Lesson, pk=integer(data, 'parent_id', 1, 2**63-1), course=course)
        qs = lesson.steps.all()
    else:
        raise ApiError('Неверный тип порядка')
    ids = data.get('ids')
    if not isinstance(ids, list) or any(type(i) is not int for i in ids) or set(ids) != set(qs.values_list('id', flat=True)) or len(ids) != qs.count():
        raise ApiError('Передайте каждый элемент списка ровно один раз')
    with transaction.atomic():
        if kind == 'steps':
            Lesson.objects.select_for_update().get(pk=lesson.id)
        else:
            Course.objects.select_for_update().get(pk=course.id)
        if set(ids) != set(qs.values_list('id', flat=True)):
            raise ApiError('Список изменился. Обновите программу курса.')
        from django.db.models import F
        offset = (qs.aggregate(v=Max('position'))['v'] or 0) + len(ids) + 1
        qs.update(position=F('position') + offset)
        for position, obj_id in enumerate(ids, 1):
            qs.filter(pk=obj_id).update(position=position)
    return JsonResponse({'message': 'Порядок сохранён'})
