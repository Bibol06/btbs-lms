import secrets
import threading
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from common import api, authenticated, body, text, raw_text, integer, boolean, ApiError
from courses.models import Course
from courses.models import Enrollment
from courses.access import can_manage_course, can_manage_run, resolve_run, require_run, require_learning_enrollment
from learning.services import require_activity_visible
from .models import CodeProblem, TestCase, CodeSubmission
from .runner import runtime_path
from .tasks import judge_submission, practice_run, practice_key, practice_busy_key, PRACTICE_TTL, QUEUE_EXPIRES, STALE_AFTER

# Limits checks that run inline in the web process (no Celery broker configured).
CAPACITY = threading.BoundedSemaphore(settings.LMS_CODEJUDGE_SLOTS)


@require_http_methods(['GET', 'POST'])
@api
def problems(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    run = resolve_run(request, course)
    require_run(request, run)
    if not can_manage_course(request.user, course):
        raise ApiError('Конструктор задач доступен редактору курса', 403)
    if request.method == 'POST':
        data = body(request)
        cases = data.get('test_cases')
        if not isinstance(cases, list) or not 1 <= len(cases) <= 20:
            raise ApiError('Добавьте от 1 до 20 тестов')
        values = []
        for case in cases:
            if not isinstance(case, dict):
                raise ApiError('Неверный формат теста')
            values.append({'stdin': raw_text(case, 'stdin', 10000), 'expected': raw_text(case, 'expected', 10000), 'is_sample': boolean(case, 'is_sample', False)})
        with transaction.atomic():
            problem = CodeProblem.objects.create(course=course, title=text(data, 'title', 200, True), statement=text(data, 'statement', 30000, True),
                starter_code=raw_text(data, 'starter_code', 20000), max_attempts=integer(data, 'max_attempts', 1, 100, 20))
            TestCase.objects.bulk_create([TestCase(problem=problem, position=i+1, **case) for i, case in enumerate(values)])
        return JsonResponse({'id': problem.id}, status=201)
    return JsonResponse({'problems': list(CodeProblem.objects.filter(course=course).values('id', 'title'))})


def problem_access(request, problem):
    run = resolve_run(request, problem.course)
    require_run(request, run)
    if not can_manage_run(request.user, run) and not problem.steps.filter(is_published=True).exists():
        raise ApiError('Задача не опубликована', 404)
    require_activity_visible(request.user, problem, run, 'code')
    return run


@require_http_methods(['GET', 'PATCH'])
@api
def problem_detail(request, problem_id):
    problem = get_object_or_404(CodeProblem.objects.select_related('course'), pk=problem_id)
    run = problem_access(request, problem)
    if request.method == 'PATCH':
        if not can_manage_course(request.user, problem.course):
            raise ApiError('Изменять задачу может редактор курса', 403)
        data = body(request)
        with transaction.atomic():
            problem = CodeProblem.objects.select_for_update().get(pk=problem.id)
            if problem.submissions.exclude(status='service_error').exists():
                raise ApiError('После отправок условие и тесты фиксируются. Создайте новую задачу.')
            values = data.get('test_cases')
            if not isinstance(values, list) or not 1 <= len(values) <= 20 or any(not isinstance(v, dict) for v in values):
                raise ApiError('Добавьте от 1 до 20 тестов')
            cases = [{'stdin': raw_text(v, 'stdin', 10000), 'expected': raw_text(v, 'expected', 10000), 'is_sample': boolean(v, 'is_sample', False)} for v in values]
            problem.title = text(data, 'title', 200, True)
            problem.statement = text(data, 'statement', 30000, True)
            problem.starter_code = raw_text(data, 'starter_code', 20000)
            problem.max_attempts = integer(data, 'max_attempts', 1, 100, 20)
            problem.save()
            problem.test_cases.all().delete()
            TestCase.objects.bulk_create([TestCase(problem=problem, position=i+1, **v) for i, v in enumerate(cases)])
        return JsonResponse({'message': 'Задача сохранена'})
    submissions = problem.submissions.filter(enrollment__run=run, enrollment__student=request.user).order_by('-id')
    return JsonResponse({'problem': {'id': problem.id, 'title': problem.title, 'statement': problem.statement,
        'starter_code': problem.starter_code, 'max_attempts': problem.max_attempts,
        'samples': list(problem.test_cases.filter(is_sample=True).values('stdin', 'expected'))},
        'submissions': list(submissions.values('id', 'status', 'passed', 'total', 'details', 'created_at')[:30]),
        'editor': {'can_edit': not problem.submissions.exclude(status='service_error').exists(), 'test_cases': list(problem.test_cases.values('stdin', 'expected', 'is_sample'))} if can_manage_course(request.user, problem.course) else None,
        'can_manage': can_manage_run(request.user, run),
        'can_submit': Enrollment.objects.filter(run=run, student=request.user, status__in=['active', 'completed']).exists(),
        'draft_key': f'lms-python-{request.user.id}-{run.id}-{problem.id}',
        'attempts_used': submissions.exclude(status='service_error').count(), 'available': runtime_path().is_file()})


def submission_payload(record):
    if record.status == 'running':
        return {'id': record.id, 'status': 'running'}
    return {'id': record.id, 'status': record.status, 'passed': record.passed, 'total': record.total, 'details': record.details}


def expire_stale(submissions):
    submissions.filter(status='running', created_at__lt=timezone.now()-STALE_AFTER).update(status='service_error')


def practice_payload(entry):
    if 'error' in entry:
        raise ApiError(entry['error'], entry['code'])
    return entry.get('result') or {'status': 'running'}


@require_POST
@api
def execute(request, problem_id):
    """Queue a check. Answers 200 with the verdict when it finished inline (no broker),
    otherwise 202 with an id/token to poll via submission_status / practice_status."""
    problem = get_object_or_404(CodeProblem.objects.select_related('course'), pk=problem_id)
    run = problem_access(request, problem)
    data = body(request)
    code = raw_text(data, 'code', 20000, True)
    submit = boolean(data, 'submit', False)
    stdin = raw_text(data, 'stdin', 10000)
    inline = settings.CELERY_TASK_ALWAYS_EAGER
    if inline and not CAPACITY.acquire(blocking=False):
        raise ApiError('Проверяющая система занята. Повторите через несколько секунд.', 429)
    try:
        if submit:
            with transaction.atomic():
                problem = CodeProblem.objects.select_for_update().get(pk=problem.id)
                enrollment = require_learning_enrollment(request, run, lock=True)
                expire_stale(problem.submissions.filter(enrollment=enrollment))
                if problem.submissions.filter(enrollment=enrollment, status='running').exists():
                    raise ApiError('Предыдущее решение ещё проверяется', 409)
                if problem.submissions.filter(enrollment=enrollment).exclude(status='service_error').count() >= problem.max_attempts:
                    raise ApiError('Попытки отправки решения использованы')
                if not problem.test_cases.exists():
                    raise ApiError('В задаче нет проверочных тестов')
                record = CodeSubmission.objects.create(problem=problem, enrollment=enrollment, code=code)
            try:
                judge_submission.apply_async((record.id,), expires=QUEUE_EXPIRES)
            except Exception:
                CodeSubmission.objects.filter(pk=record.pk, status='running').update(status='service_error')
                raise
            record.refresh_from_db()
            return JsonResponse(submission_payload(record), status=202 if record.status == 'running' else 200)
        # Practice execution never changes grades and uses only the student's own stdin.
        token = secrets.token_urlsafe(16)
        # One queued practice run per user, so nobody can fill the shared queue.
        if not cache.add(practice_busy_key(request.user.id), token, QUEUE_EXPIRES + 30):
            raise ApiError('Предыдущий запуск ещё выполняется. Дождитесь результата.', 429)
        cache.set(practice_key(token), {'user': request.user.id}, PRACTICE_TTL)
        practice_run.apply_async((token, request.user.id, code, stdin), expires=QUEUE_EXPIRES)
        entry = cache.get(practice_key(token)) or {}
        if 'result' in entry or 'error' in entry:
            return JsonResponse(practice_payload(entry))
        return JsonResponse({'status': 'running', 'run_token': token}, status=202)
    finally:
        if inline:
            CAPACITY.release()


@require_GET
@api
def submission_status(request, submission_id):
    authenticated(request)
    submissions = CodeSubmission.objects.filter(pk=submission_id, enrollment__student=request.user)
    expire_stale(submissions)
    return JsonResponse(submission_payload(get_object_or_404(submissions)))


@require_GET
@api
def practice_status(request, token):
    authenticated(request)
    entry = cache.get(practice_key(token))
    if not entry or entry.get('user') != request.user.id:
        raise ApiError('Результат запуска не найден или устарел', 404)
    return JsonResponse(practice_payload(entry))
