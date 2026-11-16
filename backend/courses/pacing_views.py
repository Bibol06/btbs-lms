from datetime import timedelta
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from common import api, body, boolean, integer, date, ApiError
from assessment.models import Quiz, QuizAttempt, ActivitySchedule
from learning.models import Module
from .access import require_run, can_manage_run
from .models import CourseRun, RunModuleRelease, RunCheckpoint
from .pacing import module_release, checkpoint_dates, sync_checkpoint_schedules, module_deadline_states


def plan_data(run, user):
    manager = can_manage_run(user, run)
    now = timezone.now()
    enrollments = list(run.enrollments.filter(status__in=['active', 'completed']).select_related('course', 'run')) if manager else list(
        run.enrollments.filter(student=user).select_related('course', 'run'))
    states = module_deadline_states(run, enrollments, now)
    modules = run.course.modules.all() if manager else run.course.modules.filter(is_published=True)
    result = []
    for module in modules.prefetch_related('lessons'):
        release = module_release(module, run)
        stored = run.module_releases.filter(module=module).first()
        lesson = module.lessons.filter(is_published=True).first()
        reason = ''
        if not manager and lesson:
            from learning.services import require_lesson_visible
            try:
                require_lesson_visible(user, lesson, run)
            except ApiError as exc:
                reason = exc.message
        result.append({'id': module.id, 'title': module.title, 'is_published': module.is_published,
            **release, 'override_opens_at': stored.opens_at if stored else None,
            'available': bool(lesson) and not reason and module.is_published and release['scheduled'] and (not release['opens_at'] or release['opens_at'] <= now),
            'locked_reason': reason or ('Содержание модуля ещё готовится' if not lesson else ''),
            'lesson_id': lesson.id if lesson else None,
            'deadline_state': (states.get((enrollments[0].id, module.id), {}).get('state') if enrollments and not manager else None),
            'completed_steps': states.get((enrollments[0].id, module.id), {}).get('completed_steps', 0) if enrollments and not manager else 0,
            'total_steps': states.get((enrollments[0].id, module.id), {}).get('total_steps', 0) if enrollments and not manager else 0,
            'overdue_count': sum(states.get((e.id, module.id), {}).get('overdue', False) for e in enrollments) if manager else None,
            'completed_count': sum(states.get((e.id, module.id), {}).get('completed', False) for e in enrollments) if manager else None,
            'waiting_count': sum(states.get((e.id, module.id), {}).get('state') == 'waiting' for e in enrollments) if manager else None})
    checkpoints = []
    ordered = sorted(run.checkpoints.select_related('run', 'quiz'), key=lambda row: (checkpoint_dates(row)[1] or now, row.kind == 'monthly'))
    for row in ordered:
        starts, ends = checkpoint_dates(row)
        attempts = row.quiz.attempts.filter(enrollment__run=run)
        if not manager:
            attempts = attempts.filter(student=user)
        best = max((100 * a.score/a.max_score for a in attempts.filter(status='finished', max_score__gt=0)), default=None)
        checkpoints.append({'id': row.id, 'quiz_id': row.quiz_id, 'title': row.quiz.title, 'kind': row.kind, 'period': row.period,
            'required': row.required, 'pass_percent': row.pass_percent,
            'opens_at': starts, 'closes_at': ends, 'override_opens_at': row.opens_at, 'override_closes_at': row.closes_at,
            'is_published': row.quiz.is_published, 'has_attempts': attempts.exists(),
            'state': 'draft' if not row.quiz.is_published else 'upcoming' if starts and now < starts else 'closed' if ends and now >= ends else 'open',
            'best_percent': round(best) if best is not None else None, 'passed': best is not None and best >= row.pass_percent})
    return {'run_id': run.id, 'course_id': run.course_id, 'kind': run.kind, 'release_mode': run.release_mode,
        'starts_at': run.starts_at, 'can_manage': manager, 'modules': result, 'checkpoints': checkpoints,
        'quizzes': list(run.course.quizzes.values('id', 'title', 'is_published')) if manager else []}


@require_http_methods(['GET', 'PUT'])
@api
def learning_plan(request, run_id):
    run = get_object_or_404(CourseRun.objects.select_related('course'), pk=run_id)
    require_run(request, run, manage=request.method == 'PUT')
    if request.method == 'GET':
        return JsonResponse(plan_data(run, request.user))
    data = body(request)
    mode = data.get('release_mode', run.release_mode)
    if mode not in ['manual', 'weekly', 'dates']:
        raise ApiError('Выберите режим открытия модулей')
    if run.kind != 'cohort' and mode == 'weekly':
        raise ApiError('Недельный план доступен для учебных групп')
    starts = date(data, 'starts_at') if 'starts_at' in data else run.starts_at
    if mode == 'weekly' and not starts:
        raise ApiError('Укажите дату начала учебных недель')
    if starts and run.ends_at and starts >= run.ends_at:
        raise ApiError('Окончание должно быть позже начала')
    modules = data.get('modules', [])
    checks = data.get('checkpoints') if 'checkpoints' in data else [
        {'quiz_id': row.quiz_id, 'kind': row.kind, 'period': row.period,
         'required': row.required, 'pass_percent': row.pass_percent,
         'override_opens_at': row.opens_at.isoformat() if row.opens_at else None,
         'override_closes_at': row.closes_at.isoformat() if row.closes_at else None}
        for row in run.checkpoints.all()]
    if not isinstance(modules, list) or not isinstance(checks, list) or len(modules) > 520 or len(checks) > 650:
        raise ApiError('Неверный учебный план')
    module_values, seen_modules = [], set()
    for item in modules:
        if not isinstance(item, dict):
            raise ApiError('Неверный учебный план')
        mid = integer(item, 'id', 1, 2**63-1)
        module = Module.objects.filter(course=run.course, id=mid).first()
        if mid in seen_modules or not module:
            raise ApiError('Модуль другого курса или указан повторно')
        seen_modules.add(mid)
        week = integer(item, 'week', 1, 520, 1)
        opens = date(item, 'opens_at') if 'opens_at' in item else date(item, 'override_opens_at')
        due = date(item, 'due_at')
        effective_open = (opens or starts + timedelta(weeks=week-1)) if mode == 'weekly' and starts else opens if mode == 'dates' else module.opens_at
        if due and (effective_open and due <= effective_open or starts and due <= starts):
            raise ApiError('Дедлайн модуля должен быть позже открытия и начала обучения')
        if due and run.ends_at and due > run.ends_at:
            raise ApiError('Дедлайн модуля должен быть не позже окончания обучения')
        module_values.append({'module_id': mid, 'week': week, 'opens_at': opens, 'due_at': due})
    values, seen_quizzes, seen_periods = [], set(), set()
    for item in checks:
        if not isinstance(item, dict) or item.get('kind') not in ['weekly', 'monthly']:
            raise ApiError('Выберите недельный тест или контроль за 4 недели')
        quiz_id = integer(item, 'quiz_id', 1, 2**63-1)
        period = integer(item, 'period', 1, 130 if item['kind'] == 'monthly' else 520)
        get_object_or_404(Quiz, id=quiz_id, course=run.course)  # the quiz must belong to this course
        if quiz_id in seen_quizzes or (item['kind'], period) in seen_periods:
            raise ApiError('Для каждого периода нужен отдельный тест')
        seen_quizzes.add(quiz_id); seen_periods.add((item['kind'], period))
        v = {'quiz_id': quiz_id, 'kind': item['kind'], 'period': period,
            'required': boolean(item, 'required', True), 'pass_percent': integer(item, 'pass_percent', 0, 100, 60),
            'opens_at': date(item, 'override_opens_at'), 'closes_at': date(item, 'override_closes_at')}
        sample = RunCheckpoint(run=run, **v)
        sample.run.starts_at = starts
        opens, closes = checkpoint_dates(sample)
        if not opens or not closes or closes <= opens:
            raise ApiError('Укажите корректное окно прохождения теста')
        if starts and opens < starts or run.ends_at and closes > run.ends_at:
            raise ApiError('Окно теста должно находиться в пределах обучения группы')
        values.append(v)
    with transaction.atomic():
        run = CourseRun.objects.select_for_update().get(pk=run.id)
        existing = list(run.checkpoints.all())
        for old in existing:
            used = QuizAttempt.objects.filter(quiz=old.quiz, enrollment__run=run).exists()
            replacement = next((v for v in values if v['quiz_id'] == old.quiz_id), None)
            if used and (replacement is None or any(getattr(old, key) != replacement[key] for key in ['kind', 'period', 'pass_percent', 'opens_at', 'closes_at']) or run.starts_at != starts):
                raise ApiError('Тест с попытками нельзя удалять или переносить. Его результаты сохраняются.')
        if run.starts_at != starts and QuizAttempt.objects.filter(quiz__checkpoints__run=run, enrollment__run=run).exists():
            raise ApiError('Начало группы нельзя переносить после контрольных попыток')
        run.starts_at, run.release_mode = starts, mode
        run.save(update_fields=['starts_at', 'release_mode'])
        if 'modules' in data:
            run.module_releases.all().delete()
            RunModuleRelease.objects.bulk_create([RunModuleRelease(run=run, **v) for v in module_values])
        for old in existing:
            if old.quiz_id not in seen_quizzes:
                ActivitySchedule.objects.filter(run=run, quiz_id=old.quiz_id).delete()
        run.checkpoints.all().delete()
        RunCheckpoint.objects.bulk_create([RunCheckpoint(run=run, **v) for v in values])
        sync_checkpoint_schedules(run)
        from communication.services import audit
        audit(request.user, run.course, 'run.learning_plan_updated', {'run_id': run.id, 'mode': mode, 'modules': len(module_values), 'checkpoints': len(values)})
    from learning.services import refresh_completion
    for enrollment in run.enrollments.filter(status__in=['active', 'completed']).select_related('course', 'run'):
        refresh_completion(enrollment)
    return JsonResponse(plan_data(run, request.user))
