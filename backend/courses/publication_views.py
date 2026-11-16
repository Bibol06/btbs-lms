"""Explicit publishing and release diagnostics without bypassing course access rules."""
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from common import ApiError, api, authenticated, body, boolean, integer
from communication.services import audit, notify_published_step
from learning.models import Module, Lesson, Step
from .access import can_manage_course, resolve_run
from .models import Course


def require_editor(request, course):
    authenticated(request)
    if not can_manage_course(request.user, course):
        raise ApiError('Нет прав редактора содержания курса', 403)


def step_content_issue(step):
    """Validate only what is necessary to make this step usable by a learner."""
    if step.kind == 'text' and not step.content.strip():
        return 'Добавьте текст учебного шага'
    if step.kind == 'video' and not step.video_url:
        return 'Добавьте ссылку на видео'
    if step.kind == 'file' and (not step.material_id or not step.material.file):
        return 'Выберите загруженный файл'
    if step.kind == 'assignment' and not step.assignment_id:
        return 'Выберите задание для шага'
    if step.kind == 'quiz':
        if not step.quiz_id:
            return 'Выберите тест для шага'
        questions = list(step.quiz.questions.all())
        if not questions:
            return 'Добавьте хотя бы один вопрос в тест'
        for question in questions:
            options = question.options
            if (not question.body.strip() or not isinstance(options, list) or not 2 <= len(options) <= 8
                    or any(not isinstance(value, str) or not value.strip() for value in options)
                    or len(set(options)) != len(options) or not 0 <= question.correct_index < len(options)):
                return 'Заполните вопросы, варианты и правильные ответы теста'
    if step.kind == 'code' and (not step.code_problem_id or not step.code_problem.test_cases.exists()):
        return 'Добавьте задачу Python с проверочными тестами'
    for related in [step.assignment, step.quiz, step.code_problem]:
        if related and related.course_id != step.lesson.course_id:
            return 'Материал относится к другому курсу'
    if step.material_id and step.material.lesson_id != step.lesson_id:
        return 'Файл относится к другому уроку'
    return None


def readiness_data(course, run):
    from assessment.models import ActivitySchedule
    now = timezone.now()
    modules = list(course.modules.select_related('prerequisite').all())
    lessons = list(course.lessons.select_related('module').all())
    steps = list(Step.objects.filter(lesson__course=course).select_related(
        'lesson__module', 'assignment', 'quiz', 'code_problem', 'material').prefetch_related('quiz__questions', 'code_problem__test_cases'))
    issues = []

    def issue(scope, obj, reason, message, date=None, level='blocking'):
        issues.append({'scope': scope, 'id': obj.id, 'title': obj.title,
                       'reason': reason, 'code': reason, 'date': date, 'message': message, 'level': level})

    if not course.is_published:
        issue('course', course, 'course_draft', 'Курс находится в черновике')
    if not steps:
        issue('course', course, 'published_empty' if course.is_published else 'empty_course', 'В курсе пока нет учебных шагов')
    if run.starts_at and run.starts_at > now:
        issue('run', run, 'run_scheduled', 'Обучение в группе ещё не началось', run.starts_at)
    if run.ends_at and run.ends_at <= now:
        issue('run', run, 'run_ended', 'Срок обучения в группе завершён', run.ends_at)
    if not run.is_open:
        issue('run', run, 'enrollment_closed', 'Запись в группу закрыта; записанные ученики сохраняют доступ', level='warning')
    for module in modules:
        from .pacing import module_release
        release = module_release(module, run)
        if not module.is_published:
            issue('module', module, 'module_draft', 'Модуль не опубликован')
        if not release['scheduled']:
            issue('module', module, 'module_unplanned', 'Модуль ещё не включён в учебный план группы')
        if release['opens_at'] and release['opens_at'] > now:
            issue('module', module, 'module_scheduled', 'Модуль откроется в указанное время', release['opens_at'])
        if module.prerequisite_id:
            issue('module', module, 'module_prerequisite', 'Сначала нужно завершить обязательные шаги предыдущего модуля', level='warning')
    lesson_ids_with_steps = {step.lesson_id for step in steps}
    for lesson in lessons:
        if not lesson.is_published:
            issue('lesson', lesson, 'lesson_draft', 'Урок не опубликован')
        if lesson.id not in lesson_ids_with_steps:
            issue('lesson', lesson, 'lesson_empty', 'Добавьте учебный шаг в урок')
    seen_activities = set()
    schedules = {(('quiz', row.quiz_id) if row.quiz_id else ('assignment', row.assignment_id)): row
                 for row in ActivitySchedule.objects.filter(run=run)}
    available = 0
    run_available = not ((run.starts_at and run.starts_at > now) or (run.ends_at and run.ends_at <= now))
    for step in steps:
        if not step.is_published:
            issue('step', step, 'step_draft', 'Учебный шаг не опубликован')
        missing = step_content_issue(step)
        if missing:
            issue('step', step, 'quiz_empty' if step.kind == 'quiz' and step.quiz_id and not step.quiz.questions.all() else 'missing_content', missing)
        activity = step.quiz if step.kind == 'quiz' else step.assignment if step.kind == 'assignment' else None
        if activity and not activity.is_published and (step.kind, activity.id) not in seen_activities:
            issue(step.kind, activity, f'{step.kind}_draft', 'Тест не опубликован' if step.kind == 'quiz' else 'Задание не опубликовано')
            seen_activities.add((step.kind, activity.id))
        activity_available = True
        if activity:
            settings = schedules.get((step.kind, activity.id), activity)
            if step.kind == 'quiz' and settings.opens_at and settings.opens_at > now:
                activity_available = False
                if (step.kind, activity.id, 'scheduled') not in seen_activities:
                    issue('quiz', activity, 'quiz_scheduled', 'Тест откроется в указанное время', settings.opens_at)
                    seen_activities.add((step.kind, activity.id, 'scheduled'))
            if step.kind == 'quiz' and settings.closes_at and settings.closes_at <= now:
                activity_available = False
                if (step.kind, activity.id, 'closed') not in seen_activities:
                    issue('quiz', activity, 'quiz_closed', 'Срок прохождения теста завершён', settings.closes_at)
                    seen_activities.add((step.kind, activity.id, 'closed'))
            if step.kind == 'assignment':
                closed_at = settings.cutoff_at if settings.cutoff_at and settings.cutoff_at <= now else settings.due_at if settings.due_at and settings.due_at <= now and not settings.allow_late else None
                if closed_at:
                    activity_available = False
                    if (step.kind, activity.id, 'closed') not in seen_activities:
                        issue('assignment', activity, 'assignment_closed', 'Приём работ по заданию завершён', closed_at)
                        seen_activities.add((step.kind, activity.id, 'closed'))
        module = step.lesson.module
        release = module_release(module, run) if module else None
        module_available = not module or (module.is_published and release['scheduled'] and not (release['opens_at'] and release['opens_at'] > now) and not module.prerequisite_id)
        if (course.is_published and run_available and module_available and step.lesson.is_published
                and step.is_published and not missing and activity_available and (not activity or activity.is_published)):
            available += 1
    quiz_ids = {step.quiz_id for step in steps if step.quiz_id}
    assignment_ids = {step.assignment_id for step in steps if step.assignment_id}
    summary = {
        'modules': len(modules), 'lessons': len(lessons), 'steps': len(steps),
        'published_steps': sum(step.is_published for step in steps), 'available_steps': available,
        'unpublished_modules': sum(not module.is_published for module in modules),
        'unpublished_lessons': sum(not lesson.is_published for lesson in lessons),
        'unpublished_steps': sum(not step.is_published for step in steps),
        'unpublished_quizzes': course.quizzes.filter(id__in=quiz_ids, is_published=False).count(),
        'unpublished_assignments': course.assignments.filter(id__in=assignment_ids, is_published=False).count(),
        'blocking_count': sum(item['level'] == 'blocking' for item in issues),
        'ready_now': bool(available),
    }
    return {'course_id': course.id, 'course': course.title, 'is_published': course.is_published,
            'run_id': run.id, 'server_now': now, 'can_publish': True, 'summary': summary, 'issues': issues}


@require_GET
@api
def readiness(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    require_editor(request, course)
    return JsonResponse(readiness_data(course, resolve_run(request, course)))


@require_POST
@api
def publish(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    require_editor(request, course)
    run = resolve_run(request, course)
    data = body(request)
    scope = data.get('scope', 'course')
    if not isinstance(scope, str) or scope not in {'course', 'module', 'lesson'}:
        raise ApiError('Выберите курс, модуль или урок для публикации')
    descendants = boolean(data, 'include_descendants', True)
    with transaction.atomic():
        course = Course.objects.select_for_update().get(pk=course.id)
        modules = Module.objects.filter(course=course)
        lessons = Lesson.objects.filter(course=course)
        if scope == 'module':
            target = get_object_or_404(modules, pk=integer(data, 'target_id', 1, 2**63-1))
            modules = modules.filter(pk=target.pk)
            lessons = lessons.filter(module=target) if descendants else lessons.none()
        elif scope == 'lesson':
            target = get_object_or_404(lessons, pk=integer(data, 'target_id', 1, 2**63-1))
            modules = modules.filter(pk=target.module_id)
            lessons = lessons.filter(pk=target.pk)
        elif data.get('target_id') is not None and integer(data, 'target_id', 1, 2**63-1) != course.id:
            raise ApiError('Выбран другой курс')
        if scope == 'course' and not descendants:
            modules, lessons = modules.none(), lessons.none()
        # Lock placements while validating the exact objects this action will publish.
        module_ids = list(modules.select_for_update().values_list('id', flat=True))
        lesson_ids = list(lessons.select_for_update().values_list('id', flat=True))
        steps = list(Step.objects.select_for_update(of=('self',)).filter(lesson_id__in=lesson_ids).select_related(
            'lesson__course', 'lesson__module', 'assignment', 'quiz', 'code_problem', 'material').prefetch_related('quiz__questions')) if descendants else []
        invalid = [{'scope': 'step', 'id': step.id, 'title': step.title, 'reason': 'missing_content', 'message': message}
                   for step in steps if (message := step_content_issue(step))]
        if invalid:
            return JsonResponse({'error': 'Заполните материалы перед публикацией', 'issues': invalid}, status=400)
        from assessment.models import Quiz, Assignment
        published = {
            'course': int(not course.is_published),
            'modules': Module.objects.filter(id__in=module_ids, is_published=False).update(is_published=True),
            'lessons': Lesson.objects.filter(id__in=lesson_ids, is_published=False).update(is_published=True),
            'steps': Step.objects.filter(id__in=[step.id for step in steps], is_published=False).update(is_published=True),
            'quizzes': Quiz.objects.filter(course=course, id__in={step.quiz_id for step in steps if step.quiz_id}, is_published=False).update(is_published=True),
            'assignments': Assignment.objects.filter(course=course, id__in={step.assignment_id for step in steps if step.assignment_id}, is_published=False).update(is_published=True),
        }
        course.is_published = True
        course.save(update_fields=['is_published'])
        for step in Step.objects.filter(id__in=[step.id for step in steps]).select_related('lesson__course', 'lesson__module'):
            notify_published_step(step)
        audit(request.user, course, 'course.publication', {'scope': scope, 'target_id': data.get('target_id'), 'include_descendants': descendants, 'published': published})
    return JsonResponse({'message': 'Публикация сохранена. Даты открытия и условия прохождения не изменены.',
                         'published': published, 'readiness': readiness_data(course, run)})


@require_POST
@api
def open_module_now(request, course_id, module_id):
    course = get_object_or_404(Course, pk=course_id)
    require_editor(request, course)
    run = resolve_run(request, course)
    with transaction.atomic():
        module = get_object_or_404(Module.objects.select_for_update(), pk=module_id, course=course)
        previous = module.opens_at
        if run.release_mode in ['weekly', 'dates']:
            from .models import RunModuleRelease
            release, _ = RunModuleRelease.objects.get_or_create(run=run, module=module, defaults={'week': 1})
            previous = release.opens_at
            release.opens_at = timezone.now()
            release.save(update_fields=['opens_at'])
        else:
            module.opens_at = None
            module.save(update_fields=['opens_at'])
        audit(request.user, course, 'module.opened_now', {'module_id': module.id, 'run_id': run.id,
            'previous_opens_at': previous.isoformat() if previous else None})
    return JsonResponse({'message': 'Модуль открыт. Публикация и обязательные предыдущие модули не изменены.',
                         'module_id': module.id, 'opens_at': release.opens_at if run.release_mode in ['weekly', 'dates'] else None,
                         'readiness': readiness_data(course, run)})
